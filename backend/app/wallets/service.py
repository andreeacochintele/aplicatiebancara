"""Wallet business rules: one wallet per currency per user, exactly one main wallet."""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError, is_unique_violation
from app.wallets.iban import generate_iban
from app.wallets.models import Wallet, WalletStatus
from app.wallets.repository import WalletRepository
from app.wallets.schemas import WalletCreate


class WalletService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = WalletRepository(db)

    def create_wallet(self, user_id: uuid.UUID, data: WalletCreate) -> Wallet:
        currency = data.currency.upper()
        # Local import: avoids a module-level cycle, same as the FX import in
        # close_wallet below.
        from app.fx.service import SUPPORTED_CURRENCIES

        if currency not in SUPPORTED_CURRENCIES:
            raise ValidationError(f"Unsupported currency '{currency}'")

        existing = self.repository.get_by_user_and_currency(user_id, currency)
        if existing is not None and existing.status != WalletStatus.CLOSED:
            raise ConflictError(f"Wallet for currency '{currency}' already exists")

        was_closed = existing is not None
        active_wallets = [w for w in self.repository.list_for_user(user_id) if w.status != WalletStatus.CLOSED]
        make_main = data.is_main
        if make_main:
            for wallet in active_wallets:
                wallet.is_main = False
        elif not active_wallets:
            # first (non-closed) wallet for a user is automatically the main wallet
            make_main = True

        if was_closed:
            # Reopening a previously closed currency reuses its row: the
            # (user_id, currency) DB constraint means a second insert for the
            # same pair fails even after the old wallet was closed. Re-fetch:
            # list_for_user() above re-hydrated this same row under the
            # Supabase REST shim (no SQLAlchemy identity map there), so
            # `existing` is no longer the tracked instance for it.
            existing = self.repository.get_by_user_and_currency(user_id, currency)
            if existing is None:
                raise NotFoundError("Wallet not found")
            existing.status = WalletStatus.ACTIVE
            existing.is_main = make_main
            # Deliberate: a closed account's IBAN is retired, same as a real
            # bank would — a reopened account is a new account that happens
            # to reuse this row (schema-forced, see above), not a resumption
            # of the old one.
            existing.iban = generate_iban()
            self.db.flush()
            return existing

        # iban is explicit here (rather than relying on the model's
        # column default) because the Supabase REST session serializes
        # attributes as-is and never triggers SQLAlchemy's Python-side
        # INSERT defaults, so a left-unset iban would hit the DB as null.
        wallet = Wallet(user_id=user_id, currency=currency, is_main=make_main, iban=generate_iban())
        try:
            return self.repository.add(wallet)
        except Exception as exc:
            if not is_unique_violation(exc):
                raise
            self.db.rollback()
            # The precondition check above already ran, so this only fires
            # when a concurrent request won the race between check and
            # insert.
            raise ConflictError(f"Wallet for currency '{currency}' already exists") from None

    def list_wallets(self, user_id: uuid.UUID) -> list[Wallet]:
        return self.repository.list_for_user(user_id)

    def set_main_wallet(self, user_id: uuid.UUID, wallet_id: uuid.UUID) -> Wallet:
        wallets = self.repository.list_for_user(user_id)
        target = next((wallet for wallet in wallets if wallet.id == wallet_id), None)
        if target is None:
            raise NotFoundError("Wallet not found")
        if target.status != WalletStatus.ACTIVE:
            raise ValidationError("Only an active wallet can be set as main")

        for wallet in wallets:
            wallet.is_main = wallet.id == wallet_id
        self.db.flush()
        return target

    def close_wallet(self, user_id: uuid.UUID, wallet_id: uuid.UUID) -> Wallet:
        """Close a non-main wallet, sweeping any remaining balance into the
        main wallet first (same-currency transfer, or a normal priced FX
        quote+transfer when currencies differ — no fee waiver: this goes
        through the same paths a customer-initiated move would)."""
        wallets = self.repository.list_for_user(user_id)
        target = next((wallet for wallet in wallets if wallet.id == wallet_id), None)
        if target is None:
            raise NotFoundError("Wallet not found")
        if target.status != WalletStatus.ACTIVE:
            raise ValidationError(f"Wallet is {target.status.value}, cannot be closed")
        if target.is_main:
            raise ValidationError("Cannot close the main wallet — set another wallet as main first")
        if target.reserved_balance > 0:
            raise ValidationError("Wallet has funds on hold and cannot be closed")

        main_wallet = next((wallet for wallet in wallets if wallet.is_main), None)
        if main_wallet is None:
            raise ConflictError("No main wallet to receive the closed wallet's balance")

        if target.available_balance > 0:
            # Local imports: avoids a module-level cycle (transactions/fx
            # pull in wallets.repository, not wallets.service).
            from app.fx.schemas import FXQuoteRequest
            from app.fx.service import FXService
            from app.transactions.schemas import InternalTransferCreate
            from app.transactions.service import TransactionService

            transactions = TransactionService(self.db)
            description = f"Wallet closure - {target.currency} balance moved to {main_wallet.currency}"
            if target.currency == main_wallet.currency:
                transactions.create_internal_transfer(
                    user_id,
                    InternalTransferCreate(
                        source_wallet_id=target.id,
                        destination_wallet_id=main_wallet.id,
                        amount=target.available_balance,
                        description=description,
                    ),
                )
            else:
                quote = FXService(self.db).get_quote(
                    user_id,
                    FXQuoteRequest(
                        source_currency=target.currency,
                        target_currency=main_wallet.currency,
                        source_amount=target.available_balance,
                    ),
                )
                transactions.create_internal_transfer(
                    user_id,
                    InternalTransferCreate(
                        source_wallet_id=target.id,
                        destination_wallet_id=main_wallet.id,
                        amount=quote.source_amount,
                        fx_quote_id=quote.id,
                        description=description,
                    ),
                )

        # Re-fetch: TransactionService's internal wallet lookups hydrate their
        # own instances under the Supabase REST shim (no SQLAlchemy identity
        # map there), so `target` may no longer be the tracked object for
        # this row once the transfer above has run. Mutate the current one.
        target = self.repository.get_by_id(wallet_id)
        if target is None:
            raise NotFoundError("Wallet not found")
        target.status = WalletStatus.CLOSED
        self.db.flush()
        return target
