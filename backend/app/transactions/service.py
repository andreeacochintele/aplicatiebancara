"""Deterministic transaction engine.

architecture.md §44 rule 3: financial operations (balances, ledger, FX rate)
are computed in code, never by an LLM. This is the reference implementation
of internal wallet-to-wallet transfers with paired ledger entries
(architecture.md §7), same-currency or cross-currency via a priced FX quote
(architecture.md §5).

Fraud scoring (app/fraud/service.py) hooks into create_card_payment and can
route a payment to PENDING_REVIEW + a HOLD instead of completing it — see
the FraudService call below.

Reward sync (points + cashback, app/merchants/service.py) also hooks into
create_card_payment: a COMPLETED card payment triggers
MerchantService.sync_purchases_from_transactions right away, instead of
only lazily the next time the Rewards page happens to load. A payment held
for fraud review is skipped here (its status isn't COMPLETED yet) — it's
not synced until something else calls sync-rewards again after the case is
approved (app/fraud/service.py's approve() does not itself trigger a sync).
"""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.cards.models import CardStatus, CardTier, CardType, CreditCardAccount
from app.cards.repository import CardRepository
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.fraud.service import FraudService
from app.fx.service import FXService
from app.merchants.models import MerchantStatus
from app.merchants.repository import MerchantRepository
from app.merchants.service import MerchantService
from app.notifications.service import NotificationsService
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.repository import TransactionRepository
from app.transactions.schemas import CardPaymentCreate, CreditCardRepaymentCreate, InternalTransferCreate
from app.wallets.models import Wallet
from app.wallets.repository import WalletRepository

logger = logging.getLogger(__name__)


class TransactionService:
    CREDIT_LIMITS = {
        CardTier.REGULAR: Decimal("5000.00"),
        CardTier.GOLD: Decimal("15000.00"),
        CardTier.PLATINUM: Decimal("30000.00"),
    }
    CREDIT_APRS = {
        CardTier.REGULAR: Decimal("18.90"),
        CardTier.GOLD: Decimal("17.50"),
        CardTier.PLATINUM: Decimal("15.90"),
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = TransactionRepository(db)
        self.wallets = WalletRepository(db)
        self.fx = FXService(db)
        self.cards = CardRepository(db)
        self.merchants = MerchantRepository(db)
        self.notifications = NotificationsService(db)

    def create_internal_transfer(
        self,
        initiator_user_id: uuid.UUID,
        data: InternalTransferCreate,
        *,
        screen_for_fraud: bool = True,
    ) -> Transaction:
        """`screen_for_fraud` defaults to True so any new caller is covered by
        default. It's turned off only for settlement flows that immediately
        record their own outcome against the returned transaction — paying a
        bill-split share or a payment request marks the participant/request
        PAID and notifies the payee right away (app/payments/service.py),
        which would be wrong if the money were sitting on a fraud HOLD. Those
        flows are user-to-user settlements of an amount both sides already
        agreed on, so screening them is also the weaker case."""
        if data.amount <= 0:
            raise ValidationError("Transfer amount must be positive")

        source, destination = self._lock_wallet_pair(data.source_wallet_id, data.destination_wallet_id)
        if source is None or destination is None:
            raise NotFoundError("Source or destination wallet not found")
        if source.user_id != initiator_user_id:
            raise ValidationError("Source wallet does not belong to the initiating user")

        if source.currency == destination.currency:
            return self._execute_same_currency_transfer(
                initiator_user_id, source, destination, data, screen_for_fraud
            )
        return self._execute_fx_transfer(initiator_user_id, source, destination, data, screen_for_fraud)

    def _lock_wallet_pair(
        self, id_a: uuid.UUID, id_b: uuid.UUID
    ) -> tuple[Wallet | None, Wallet | None]:
        """Locks both wallet rows for the rest of this transaction, always in
        the same (sorted-by-id) order regardless of which one is source vs
        destination — otherwise two concurrent transfers moving money in
        opposite directions between the same pair of wallets could each lock
        their own "source" first and then deadlock waiting for the other's
        "destination"."""
        first_id, second_id = sorted([id_a, id_b], key=str)
        first = self.wallets.get_by_id_for_update(first_id)
        second = self.wallets.get_by_id_for_update(second_id) if second_id != first_id else first
        by_id = {w.id: w for w in (first, second) if w is not None}
        return by_id.get(id_a), by_id.get(id_b)

    def _execute_same_currency_transfer(
        self,
        initiator_user_id: uuid.UUID,
        source: Wallet,
        destination: Wallet,
        data: InternalTransferCreate,
        screen_for_fraud: bool = True,
    ) -> Transaction:
        if source.available_balance < data.amount:
            raise ConflictError("Insufficient available balance")

        transaction = self.repository.add(
            Transaction(
                initiator_user_id=initiator_user_id,
                source_wallet_id=source.id,
                destination_wallet_id=destination.id,
                type=TransactionType.TRANSFER,
                status=TransactionStatus.PROCESSING,
                amount=data.amount,
                currency=source.currency,
                description=data.description,
                processed_at=datetime.now(timezone.utc),
            )
        )

        # Same seam as create_card_payment's: scoring runs before any money
        # moves, and a blocked transfer is HOLD'd + set to PENDING_REVIEW by
        # FraudService, so neither leg of _settle() ever runs. The
        # destination is credited later, by FraudService.approve().
        if screen_for_fraud and FraudService(self.db).evaluate_transaction(transaction, source).blocked:
            return transaction

        self._settle(transaction, source, data.amount, destination, data.amount)
        return transaction

    def _execute_fx_transfer(
        self,
        initiator_user_id: uuid.UUID,
        source: Wallet,
        destination: Wallet,
        data: InternalTransferCreate,
        screen_for_fraud: bool = True,
    ) -> Transaction:
        if data.fx_quote_id is None:
            raise ValidationError("Cross-currency transfers require an fx_quote_id — request one via POST /fx/quote")

        quote = self.fx.get_valid_quote_for_user(initiator_user_id, data.fx_quote_id)
        if quote.source_currency != source.currency or quote.target_currency != destination.currency:
            raise ValidationError("FX quote currencies don't match the selected wallets")
        if quote.source_amount != data.amount:
            raise ValidationError("Transfer amount doesn't match the quoted source amount")
        if source.available_balance < quote.source_amount:
            raise ConflictError("Insufficient available balance")

        transaction = self.repository.add(
            Transaction(
                initiator_user_id=initiator_user_id,
                source_wallet_id=source.id,
                destination_wallet_id=destination.id,
                type=TransactionType.TRANSFER,
                status=TransactionStatus.PROCESSING,
                amount=quote.target_amount,
                currency=destination.currency,
                source_amount=quote.source_amount,
                source_currency=quote.source_currency,
                exchange_rate=quote.exchange_rate,
                fx_quote_id=quote.id,
                description=data.description,
                processed_at=datetime.now(timezone.utc),
            )
        )
        # The quote is consumed by the attempt itself, held or not: the
        # transaction already carries the priced source_amount/target amount
        # and exchange_rate that FraudService.approve() will settle with, and
        # leaving the quote OPEN would let the same pricing fund a second
        # transfer while this one sits under review.
        if screen_for_fraud and FraudService(self.db).evaluate_transaction(transaction, source).blocked:
            self.fx.mark_accepted(quote)
            return transaction

        self._settle(transaction, source, quote.source_amount, destination, quote.target_amount)
        self.fx.mark_accepted(quote)
        return transaction

    def _settle(
        self,
        transaction: Transaction,
        source: Wallet,
        source_amount: Decimal,
        destination: Wallet,
        destination_amount: Decimal,
    ) -> None:
        """Move balances and write the paired ledger entries. Each entry is in
        its own wallet's currency — that's what keeps a cross-currency
        transfer's ledger auditable (architecture.md §7)."""
        source.available_balance -= source_amount
        destination.available_balance += destination_amount

        self.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=source.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=source_amount,
                currency=source.currency,
                balance_after=source.available_balance,
            )
        )
        self.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=destination.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.CREDIT,
                amount=destination_amount,
                currency=destination.currency,
                balance_after=destination.available_balance,
            )
        )

        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.now(timezone.utc)
        self.db.flush()

        # Best-effort: a notification failure must never make an otherwise-
        # successful transfer look like it failed.
        try:
            self.notifications.create(
                destination.user_id,
                type="TRANSACTION",
                title="Money received",
                message=f"You received {destination_amount} {destination.currency}.",
                related_transaction_id=transaction.id,
            )
        except Exception:
            logger.exception("Failed to create 'money received' notification for transaction %s", transaction.id)

    def create_card_payment(self, initiator_user_id: uuid.UUID, data: CardPaymentCreate) -> Transaction:
        """A card payment to a merchant — unlike a transfer, money leaves the
        system to an external counterparty. Debit and one-time cards write a
        wallet DEBIT ledger entry; credit cards increase used credit instead.
        `merchant_id` is set on the Transaction: it's the
        only signal the rewards module (app/merchants) uses to decide
        whether to credit points, via its own read-only sync — this method
        never calls into rewards/merchants itself."""
        if data.amount <= 0:
            raise ValidationError("Payment amount must be positive")

        card = self.cards.get_by_id(data.card_id)
        if card is None or card.user_id != initiator_user_id:
            raise NotFoundError("Card not found")
        if data.cvv != card.mock_cvv:
            raise ValidationError("Incorrect CVV")
        if self._card_is_expired(card):
            card.status = CardStatus.EXPIRED
            self.db.flush()
            raise ValidationError("Card is expired")
        if card.status != CardStatus.ACTIVE:
            raise ValidationError(f"Card is {card.status.value}, payments require an ACTIVE card")

        merchant = self.merchants.get_by_id(data.merchant_id)
        if merchant is None or merchant.status != MerchantStatus.ACTIVE:
            raise NotFoundError("Merchant not found")

        if card.type == CardType.CREDIT:
            account = self._get_or_create_credit_account(card)
            if account.used_amount + data.amount > account.credit_limit:
                raise ConflictError("Insufficient available credit")

            transaction = self.repository.add(
                Transaction(
                    initiator_user_id=initiator_user_id,
                    source_wallet_id=None,
                    merchant_id=merchant.id,
                    card_id=card.id,
                    type=TransactionType.CARD_PAYMENT,
                    status=TransactionStatus.PROCESSING,
                    amount=data.amount,
                    currency=account.currency,
                    description=data.description or f"Credit card payment to {merchant.name}",
                    processed_at=datetime.now(timezone.utc),
                )
            )
            account.used_amount += data.amount
            account.updated_at = datetime.now(timezone.utc)
            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = datetime.now(timezone.utc)
            self.db.flush()
            self._sync_rewards(initiator_user_id)
            return transaction

        preferences = self.cards.get_preferences(card.id)
        wallet_id = (preferences.preferred_wallet_id if preferences is not None else None) or card.default_wallet_id
        if wallet_id is None:
            raise ValidationError("Card has no wallet to pay from — set a default or preferred wallet first")

        wallet = self.wallets.get_by_id_for_update(wallet_id)
        if wallet is None or wallet.user_id != initiator_user_id:
            raise NotFoundError("Card's wallet not found")
        if wallet.available_balance < data.amount:
            raise ConflictError("Insufficient available balance")

        transaction = self.repository.add(
            Transaction(
                initiator_user_id=initiator_user_id,
                source_wallet_id=wallet.id,
                merchant_id=merchant.id,
                card_id=card.id,
                type=TransactionType.CARD_PAYMENT,
                status=TransactionStatus.PROCESSING,
                amount=data.amount,
                currency=wallet.currency,
                description=data.description or f"Card payment to {merchant.name}",
                processed_at=datetime.now(timezone.utc),
            )
        )

        # Fraud scoring happens before the funds actually move: a blocked
        # transaction gets HOLD'd (and set to PENDING_REVIEW) by
        # FraudService itself, and this method returns early without ever
        # reaching the DEBIT below. See app/fraud/service.py.
        fraud_result = FraudService(self.db).evaluate_transaction(transaction, wallet)
        if fraud_result.blocked:
            return transaction

        wallet.available_balance -= data.amount
        self.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=data.amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )

        # ONE_TIME cards are meant for exactly one purchase — consuming the
        # single use here (rather than adding a method to app/cards, which
        # isn't this module's) keeps the diff to this one seam.
        if card.type == CardType.ONE_TIME:
            card.one_time_remaining = max(0, (card.one_time_remaining or 1) - 1)
            if card.one_time_remaining == 0:
                card.status = CardStatus.CANCELLED

        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        self._sync_rewards(initiator_user_id)
        return transaction

    def _sync_rewards(self, user_id: uuid.UUID) -> None:
        """Best-effort: a completed card payment should show up as earned
        points/cashback immediately rather than only the next time the
        Rewards page happens to sync on its own. Reuses the same
        already-earned dedup MerchantService.sync_purchases_from_transactions
        already does, so this is safe to call after every completed payment."""
        MerchantService(self.db).sync_purchases_from_transactions(user_id)

    def _card_is_expired(self, card) -> bool:
        now = datetime.now(timezone.utc)
        return (card.expiration_year, card.expiration_month) < (now.year, now.month)

    def create_credit_card_repayment(self, initiator_user_id: uuid.UUID, data: CreditCardRepaymentCreate) -> Transaction:
        if data.amount <= 0:
            raise ValidationError("Payment amount must be positive")

        card = self.cards.get_by_id(data.card_id)
        if card is None or card.user_id != initiator_user_id:
            raise NotFoundError("Card not found")
        if card.type != CardType.CREDIT:
            raise ValidationError("Only credit cards can be repaid")
        if card.status != CardStatus.ACTIVE:
            raise ValidationError(f"Card is {card.status.value}, repayments require an ACTIVE card")

        account = self._get_or_create_credit_account(card)
        if data.amount > account.used_amount:
            raise ValidationError("Payment is higher than the current card balance")

        wallet = self.wallets.get_by_id_for_update(data.source_wallet_id)
        if wallet is None or wallet.user_id != initiator_user_id:
            raise NotFoundError("Source wallet not found")
        if wallet.currency != account.currency:
            raise ValidationError("Repayment source currency must match the credit card account currency")
        if wallet.available_balance < data.amount:
            raise ConflictError("Insufficient available balance")

        transaction = self.repository.add(
            Transaction(
                initiator_user_id=initiator_user_id,
                source_wallet_id=wallet.id,
                card_id=card.id,
                type=TransactionType.LOAN_PAYMENT,
                status=TransactionStatus.PROCESSING,
                amount=data.amount,
                currency=wallet.currency,
                description=f"Credit card repayment for card ending {card.last_four}",
                processed_at=datetime.now(timezone.utc),
            )
        )
        wallet.available_balance -= data.amount
        account.used_amount -= data.amount
        account.updated_at = datetime.now(timezone.utc)
        self.repository.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.DEBIT,
                amount=data.amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )
        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        return transaction

    def _get_or_create_credit_account(self, card) -> CreditCardAccount:
        account = self.cards.get_credit_account(card.id)
        if account is not None:
            return account
        tier = card.tier or CardTier.REGULAR
        return self.cards.add_credit_account(
            CreditCardAccount(
                card_id=card.id,
                user_id=card.user_id,
                credit_limit=self.CREDIT_LIMITS[tier],
                annual_interest_rate=self.CREDIT_APRS[tier],
            )
        )

    def list_for_user(self, user_id: uuid.UUID) -> list[Transaction]:
        return self.repository.list_for_user(user_id)

    def get_for_user(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction:
        transaction = self.repository.get_for_user(user_id, transaction_id)
        if transaction is None:
            raise NotFoundError("Transaction not found")
        return transaction
