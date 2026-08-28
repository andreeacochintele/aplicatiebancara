"""Wallet business rules: any number of wallets per currency per user
(distinguished by nickname), exactly one main wallet."""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
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

        active_wallets = [w for w in self.repository.list_for_user(user_id) if w.status != WalletStatus.CLOSED]
        make_main = data.is_main
        if make_main:
            for wallet in active_wallets:
                wallet.is_main = False
        elif not active_wallets:
            # first (non-closed) wallet for a user is automatically the main wallet
            make_main = True

        # iban is explicit here (rather than relying on the model's
        # column default) because the Supabase REST session serializes
        # attributes as-is and never triggers SQLAlchemy's Python-side
        # INSERT defaults, so a left-unset iban would hit the DB as null.
        wallet = Wallet(
            user_id=user_id,
            currency=currency,
            nickname=data.nickname,
            is_main=make_main,
            iban=generate_iban(),
        )
        return self.repository.add(wallet)

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

    def close_wallet(
        self,
        user_id: uuid.UUID,
        wallet_id: uuid.UUID,
        destination_wallet_id: uuid.UUID | None = None,
        fx_quote_id: uuid.UUID | None = None,
    ) -> Wallet:
        """Close a non-main wallet, sweeping any remaining balance into
        `destination_wallet_id` (defaults to the main wallet, preserving the
        old auto-sweep behavior when the caller doesn't pick one) — a
        same-currency transfer, or a priced FX quote+transfer when
        currencies differ. `fx_quote_id` lets the caller reuse a quote it
        already showed the user as a preview (POST /fx/quote); a fresh one
        is fetched only if none was passed. No fee waiver either way: this
        goes through the same paths a customer-initiated move would."""
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

        if destination_wallet_id is not None:
            destination = next((wallet for wallet in wallets if wallet.id == destination_wallet_id), None)
            if destination is None or destination.status != WalletStatus.ACTIVE:
                raise NotFoundError("Destination wallet not found")
            if destination.id == target.id:
                raise ValidationError("Choose a different wallet to receive the balance")
        else:
            destination = next((wallet for wallet in wallets if wallet.is_main), None)
        if destination is None:
            raise ConflictError("No destination wallet to receive the closed wallet's balance")

        if target.available_balance > 0:
            # Local imports: avoids a module-level cycle (transactions/fx
            # pull in wallets.repository, not wallets.service).
            from app.fx.schemas import FXQuoteRequest
            from app.fx.service import FXService
            from app.transactions.schemas import InternalTransferCreate
            from app.transactions.service import TransactionService

            transactions = TransactionService(self.db)
            description = f"Wallet closure - {target.currency} balance moved to {destination.currency}"
            if target.currency == destination.currency:
                transactions.create_internal_transfer(
                    user_id,
                    InternalTransferCreate(
                        source_wallet_id=target.id,
                        destination_wallet_id=destination.id,
                        amount=target.available_balance,
                        description=description,
                    ),
                )
            else:
                fx = FXService(self.db)
                quote = (
                    fx.get_valid_quote_for_user(user_id, fx_quote_id)
                    if fx_quote_id is not None
                    else fx.get_quote(
                        user_id,
                        FXQuoteRequest(
                            source_currency=target.currency,
                            target_currency=destination.currency,
                            source_amount=target.available_balance,
                        ),
                    )
                )
                transactions.create_internal_transfer(
                    user_id,
                    InternalTransferCreate(
                        source_wallet_id=target.id,
                        destination_wallet_id=destination.id,
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
