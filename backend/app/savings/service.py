"""Savings goal business rules.

contribute() and withdraw() move real money through the standard ledger —
see each method's docstring — following the same pattern
CreditService.make_early_repayment() and PaymentService.create_iban_transfer()
already use for a wallet debit/credit with an optional FX quote: current_amount
is never incremented/decremented on its own without a matching
Transaction + WalletLedgerEntry.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.database import utcnow
from app.fx.models import FXQuote
from app.fx.service import FXService
from app.savings.models import SavingsGoal, SavingsGoalStatus
from app.savings.repository import SavingsGoalRepository
from app.savings.schemas import (
    SavingsContribution,
    SavingsGoalCreate,
    SavingsGoalDeleteRequest,
    SavingsGoalPublic,
    SavingsWithdrawal,
)
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.repository import TransactionRepository
from app.wallets.models import Wallet
from app.wallets.repository import WalletRepository


class SavingsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = SavingsGoalRepository(db)
        self.transactions = TransactionRepository(db)
        self.wallets = WalletRepository(db)
        self.fx = FXService(db)

    def create_goal(self, user_id: uuid.UUID, data: SavingsGoalCreate) -> SavingsGoalPublic:
        if data.target_amount <= 0:
            raise ValidationError("target_amount must be positive")
        if data.initial_amount < 0:
            raise ValidationError("initial_amount cannot be negative")

        goal = SavingsGoal(
            user_id=user_id,
            name=data.name,
            target_amount=data.target_amount,
            current_amount=data.initial_amount,
            currency=data.currency.upper(),
            target_date=data.target_date,
            status=SavingsGoalStatus.COMPLETED if data.initial_amount >= data.target_amount else SavingsGoalStatus.ACTIVE,
        )
        self.repository.add(goal)
        return self._to_public(goal)

    def list_goals(self, user_id: uuid.UUID) -> list[SavingsGoalPublic]:
        return [self._to_public(goal) for goal in self.repository.list_for_user(user_id)]

    def contribute(self, user_id: uuid.UUID, goal_id: uuid.UUID, data: SavingsContribution) -> SavingsGoalPublic:
        """Debits `data.wallet_id` for `data.amount` (in that wallet's own
        currency) and credits the goal by the equivalent in the goal's
        currency — same-currency: 1:1, no quote needed. Cross-currency:
        `data.fx_quote_id` is required, from POST /fx/quote with
        source_currency=wallet currency, target_currency=goal currency,
        source_amount=data.amount (same quote-then-confirm mechanism
        PaymentService.create_iban_transfer uses)."""
        if data.amount <= 0:
            raise ValidationError("amount must be positive")

        goal = self._get_owned_goal(user_id, goal_id)
        if goal.status != SavingsGoalStatus.ACTIVE:
            raise ValidationError(f"Savings goal is {goal.status.value.lower()}, not accepting contributions")

        wallet = self._get_owned_wallet(user_id, data.wallet_id)

        quote: FXQuote | None = None
        if wallet.currency == goal.currency:
            credited_amount = data.amount
        else:
            quote = self._require_quote(user_id, data.fx_quote_id, wallet.currency, goal.currency, data.amount)
            credited_amount = quote.target_amount

        if wallet.available_balance < data.amount:
            raise ConflictError("Insufficient available balance")

        now = utcnow()
        transaction = self.transactions.add(
            Transaction(
                initiator_user_id=user_id,
                source_wallet_id=wallet.id,
                destination_wallet_id=None,
                type=TransactionType.SAVINGS_CONTRIBUTION,
                status=TransactionStatus.PROCESSING,
                amount=credited_amount,
                currency=goal.currency,
                source_amount=data.amount if quote is not None else None,
                source_currency=wallet.currency if quote is not None else None,
                exchange_rate=quote.exchange_rate if quote is not None else None,
                fx_quote_id=quote.id if quote is not None else None,
                description=f"Savings contribution - {goal.name}",
                processed_at=now,
            )
        )

        wallet.available_balance -= data.amount
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=data.amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )

        goal.current_amount += credited_amount
        if goal.current_amount >= goal.target_amount:
            goal.status = SavingsGoalStatus.COMPLETED

        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = now
        if quote is not None:
            self.fx.mark_accepted(quote)

        self.db.flush()
        return self._to_public(goal)

    def withdraw(self, user_id: uuid.UUID, goal_id: uuid.UUID, data: SavingsWithdrawal) -> SavingsGoalPublic:
        """Withdraws the goal's *entire* current_amount back to
        `data.wallet_id` and marks the goal WITHDRAWN - no partial
        withdrawal. Allowed from ACTIVE or COMPLETED (changing your mind
        on a still-in-progress goal is fine, same mechanism either way).
        Cross-currency: `data.fx_quote_id` required, quoted for the goal's
        full current_amount (source_currency=goal currency,
        target_currency=wallet currency)."""
        goal = self._get_owned_goal(user_id, goal_id)
        if goal.status == SavingsGoalStatus.WITHDRAWN:
            raise ValidationError("Savings goal has already been withdrawn")
        if goal.current_amount <= 0:
            raise ValidationError("Nothing to withdraw")

        wallet = self._get_owned_wallet(user_id, data.wallet_id)

        quote: FXQuote | None = None
        if wallet.currency == goal.currency:
            credited_amount = goal.current_amount
        else:
            quote = self._require_quote(user_id, data.fx_quote_id, goal.currency, wallet.currency, goal.current_amount)
            credited_amount = quote.target_amount

        now = utcnow()
        transaction = self.transactions.add(
            Transaction(
                initiator_user_id=user_id,
                source_wallet_id=None,
                destination_wallet_id=wallet.id,
                type=TransactionType.SAVINGS_WITHDRAWAL,
                status=TransactionStatus.PROCESSING,
                amount=credited_amount,
                currency=wallet.currency,
                source_amount=goal.current_amount if quote is not None else None,
                source_currency=goal.currency if quote is not None else None,
                exchange_rate=quote.exchange_rate if quote is not None else None,
                fx_quote_id=quote.id if quote is not None else None,
                description=f"Savings withdrawal - {goal.name}",
                processed_at=now,
            )
        )

        wallet.available_balance += credited_amount
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=credited_amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )

        goal.current_amount = Decimal("0")
        goal.status = SavingsGoalStatus.WITHDRAWN

        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = now
        if quote is not None:
            self.fx.mark_accepted(quote)

        self.db.flush()
        return self._to_public(goal)

    def delete_goal(self, user_id: uuid.UUID, goal_id: uuid.UUID, data: SavingsGoalDeleteRequest) -> None:
        """Deletes a goal outright — available regardless of status. If it
        still has money in it, that money is withdrawn to `data.wallet_id`
        first (via withdraw() itself, so it's the exact same ledger path,
        not a shortcut) so nothing is ever silently lost by deleting."""
        goal = self._get_owned_goal(user_id, goal_id)

        if goal.current_amount > 0:
            if data.wallet_id is None:
                raise ValidationError(
                    "wallet_id is required to return this goal's remaining balance before deleting it"
                )
            self.withdraw(user_id, goal_id, SavingsWithdrawal(wallet_id=data.wallet_id, fx_quote_id=data.fx_quote_id))

        self.repository.delete(goal)
        self.db.flush()

    def _get_owned_goal(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> SavingsGoal:
        goal = self.repository.get_by_id(goal_id)
        if goal is None or goal.user_id != user_id:
            raise NotFoundError("Savings goal not found")
        # See _to_public's docstring note - same defensive normalization,
        # needed here too since contribute()/withdraw() branch on status
        # directly rather than going through _to_public first.
        goal.status = goal.status or SavingsGoalStatus.ACTIVE
        return goal

    def _get_owned_wallet(self, user_id: uuid.UUID, wallet_id: uuid.UUID) -> Wallet:
        wallet = self.wallets.get_by_id(wallet_id)
        if wallet is None or wallet.user_id != user_id:
            raise NotFoundError("Wallet not found")
        return wallet

    def _require_quote(
        self,
        user_id: uuid.UUID,
        fx_quote_id: uuid.UUID | None,
        expected_source_currency: str,
        expected_target_currency: str,
        expected_source_amount: Decimal,
    ) -> FXQuote:
        if fx_quote_id is None:
            raise ValidationError("Cross-currency contributions/withdrawals require an fx_quote_id")
        quote = self.fx.get_valid_quote_for_user(user_id, fx_quote_id)
        if quote.source_currency != expected_source_currency or quote.target_currency != expected_target_currency:
            raise ValidationError("FX quote currencies don't match the selected wallet/goal")
        if quote.source_amount != expected_source_amount:
            raise ValidationError("FX quote amount doesn't match the requested amount")
        return quote

    def _to_public(self, goal: SavingsGoal) -> SavingsGoalPublic:
        # Defensive against a shared database that hasn't run migration
        # 0037 yet: SupabaseRestSession hydrates strictly from whatever
        # keys the row actually has, so an old row with no status column
        # at all leaves this None rather than defaulting to ACTIVE the way
        # a freshly-constructed SavingsGoal() would.
        status = goal.status or SavingsGoalStatus.ACTIVE
        percent_complete = (
            round(float(goal.current_amount / goal.target_amount) * 100, 1) if goal.target_amount else 0.0
        )
        remaining = goal.target_amount - goal.current_amount
        monthly_needed = None
        if status == SavingsGoalStatus.ACTIVE and goal.target_date is not None and remaining > 0:
            months = self._months_between(datetime.now(timezone.utc).date(), goal.target_date)
            monthly_needed = (remaining / months).quantize(Decimal("0.01"))

        return SavingsGoalPublic(
            id=goal.id,
            name=goal.name,
            target_amount=goal.target_amount,
            current_amount=goal.current_amount,
            currency=goal.currency,
            target_date=goal.target_date,
            status=status,
            percent_complete=percent_complete,
            monthly_amount_needed=monthly_needed,
            created_at=goal.created_at,
        )

    @staticmethod
    def _months_between(today: date, target: date) -> int:
        months = (target.year - today.year) * 12 + (target.month - today.month)
        return max(months, 1)
