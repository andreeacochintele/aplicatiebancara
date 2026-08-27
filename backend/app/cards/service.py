"""Cards business rules."""
import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.cards.models import Card, CardPaymentPreferences, CardStatus, CardTier, CardType, CreditCardAccount
from app.cards.repository import CardRepository
from app.cards.schemas import CardCreate, CardPaymentPreferencesUpdate, CardSensitiveDetails
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password, verify_password
from app.database import utcnow
from app.transactions.models import LedgerEntryType, Transaction, TransactionStatus, TransactionType, WalletLedgerEntry
from app.transactions.repository import TransactionRepository
from app.wallets.models import WalletStatus
from app.wallets.repository import WalletRepository
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


class CardService:
    MAX_DEBIT_CARDS_PER_USER = 5
    MAX_CREDIT_CARDS_PER_USER = 5
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
        self.repository = CardRepository(db)
        self.wallets = WalletRepository(db)
        self.transactions = TransactionRepository(db)

    def create_card(
        self,
        user_id: uuid.UUID,
        data: CardCreate,
        *,
        admin_approved: bool = True,
        credit_limit: Decimal | None = None,
        annual_interest_rate: Decimal | None = None,
        currency: str | None = None,
    ) -> Card:
        existing_cards = self.repository.list_for_user(user_id)
        if data.type == CardType.DEBIT:
            debit_count = sum(1 for card in existing_cards if card.type == CardType.DEBIT)
            if debit_count >= self.MAX_DEBIT_CARDS_PER_USER:
                raise ConflictError("Debit card limit reached. You can have up to 5 debit cards.")
        if data.type == CardType.CREDIT:
            credit_count = sum(1 for card in existing_cards if card.type == CardType.CREDIT)
            if credit_count >= self.MAX_CREDIT_CARDS_PER_USER:
                raise ConflictError("Credit card limit reached. You can have up to 5 credit cards.")

        default_wallet_id = data.default_wallet_id
        if data.new_wallet_currency is not None:
            if data.type != CardType.DEBIT:
                raise ValidationError("New current accounts can only be created with debit cards")
            if data.default_wallet_id is not None:
                raise ValidationError("Choose an existing account or create a new account, not both")
            new_wallet = WalletService(self.db).create_wallet(
                user_id,
                WalletCreate(currency=data.new_wallet_currency),
            )
            default_wallet_id = new_wallet.id

        if data.type == CardType.ONE_TIME and data.tier is not None:
            raise ValidationError("One-time cards do not have tiers")

        if data.type in (CardType.DEBIT, CardType.ONE_TIME) and default_wallet_id is None:
            raise ValidationError("Debit and one-time cards must be linked to an account")

        if default_wallet_id is not None:
            wallet = self.wallets.get_by_id(default_wallet_id)
            if wallet is None or wallet.user_id != user_id:
                raise NotFoundError("Default wallet not found")
            if wallet.status != WalletStatus.ACTIVE:
                raise ValidationError("Default wallet must be active")

        collateral_wallet = None
        collateral_amount = Decimal("0.00")
        if data.type == CardType.CREDIT:
            requested_currency = data.currency.upper() if data.currency else None
            if requested_currency is not None and len(requested_currency) != 3:
                raise ValidationError("Currency must be a 3-letter code")
            currency = requested_currency or currency
            collateral_amount = self._money(data.collateral_amount or Decimal("0.00"))
            if data.collateral_wallet_id is not None or collateral_amount > 0:
                if data.collateral_wallet_id is None:
                    raise ValidationError("Collateral-backed credit cards require a collateral account")
                if collateral_amount <= 0:
                    raise ValidationError("Collateral amount must be positive")
                collateral_wallet = self.wallets.get_by_id(data.collateral_wallet_id)
                if collateral_wallet is None or collateral_wallet.user_id != user_id:
                    raise NotFoundError("Collateral account not found")
                if collateral_wallet.status != WalletStatus.ACTIVE:
                    raise ValidationError("Collateral account must be active")
                if requested_currency is not None and collateral_wallet.currency != requested_currency:
                    raise ValidationError("Collateral account currency must match the credit card currency")
                if collateral_wallet.available_balance < collateral_amount:
                    raise ConflictError("Insufficient funds for credit card collateral")
                currency = collateral_wallet.currency
                credit_limit = collateral_amount
            elif not admin_approved:
                raise ValidationError("Credit cards without collateral require admin approval")
        elif data.collateral_wallet_id is not None or data.collateral_amount is not None:
            raise ValidationError("Collateral is only available for credit cards")

        if data.type == CardType.DEBIT and default_wallet_id is not None:
            for existing_card in existing_cards:
                if existing_card.type == CardType.DEBIT and existing_card.default_wallet_id == default_wallet_id:
                    raise ConflictError("This account already has a debit card")

        if data.type == CardType.ONE_TIME:
            for existing_card in existing_cards:
                if existing_card.type == CardType.ONE_TIME and existing_card.status in (CardStatus.ACTIVE, CardStatus.FROZEN):
                    raise ConflictError("You can only have one one-time payment card")

        default_wallet_id = default_wallet_id if data.type in (CardType.DEBIT, CardType.ONE_TIME) else None
        last_four = f"{secrets.randbelow(10000):04d}"
        mock_pan = f"4000 {secrets.randbelow(10000):04d} {secrets.randbelow(10000):04d} {last_four}"
        mock_cvv = f"{secrets.randbelow(1000):03d}"
        now = datetime.now(timezone.utc)
        one_time_remaining = 1 if data.type == CardType.ONE_TIME else None
        tier = None if data.type == CardType.ONE_TIME else data.tier or CardTier.REGULAR

        card = Card(
            user_id=user_id,
            default_wallet_id=default_wallet_id,
            type=data.type,
            tier=tier,
            status=CardStatus.ACTIVE,
            masked_pan=f"**** **** **** {last_four}",
            last_four=last_four,
            mock_pan=mock_pan,
            mock_cvv=mock_cvv,
            expiration_month=now.month,
            expiration_year=now.year + 4,
            one_time_remaining=one_time_remaining,
        )
        card = self.repository.add(card)
        self.repository.add_preferences(
            CardPaymentPreferences(card_id=card.id, preferred_wallet_id=default_wallet_id)
        )
        if card.type == CardType.CREDIT:
            tier = card.tier or CardTier.REGULAR
            account_credit_limit = self._money(credit_limit or self.CREDIT_LIMITS[tier])
            card.credit_account = self.repository.add_credit_account(
                CreditCardAccount(
                    card_id=card.id,
                    user_id=user_id,
                    currency=(currency or "RON").upper(),
                    credit_limit=account_credit_limit,
                    annual_interest_rate=annual_interest_rate or self.CREDIT_APRS[tier],
                    collateral_wallet_id=collateral_wallet.id if collateral_wallet is not None else None,
                    collateral_amount=collateral_amount,
                )
            )
            if collateral_wallet is not None and collateral_amount > 0:
                self._reserve_collateral(user_id, collateral_wallet, collateral_amount, card)
        return card

    def list_cards(self, user_id: uuid.UUID) -> list[Card]:
        cards = self.repository.list_for_user(user_id)
        for card in cards:
            self._attach_pin_status(card)
            if card.type == CardType.CREDIT:
                card.credit_account = self._get_or_create_credit_account(card)
        return cards

    def get_for_user(self, user_id: uuid.UUID, card_id: uuid.UUID) -> Card:
        card = self.repository.get_by_id(card_id)
        if card is None or card.user_id != user_id:
            raise NotFoundError("Card not found")
        self._attach_pin_status(card)
        if card.type == CardType.CREDIT:
            card.credit_account = self._get_or_create_credit_account(card)
        return card

    def update_pin(self, user_id: uuid.UUID, card_id: uuid.UUID, pin: str) -> Card:
        card = self.get_for_user(user_id, card_id)
        self._validate_pin(pin)
        card.pin_hash = hash_password(pin)
        self._attach_pin_status(card)
        self.db.flush()
        return card

    def reveal_details(self, user_id: uuid.UUID, card_id: uuid.UUID, pin: str) -> CardSensitiveDetails:
        card = self.get_for_user(user_id, card_id)
        if not card.pin_hash:
            raise ValidationError("Set a card PIN before viewing card details")
        if not verify_password(pin, card.pin_hash):
            raise ValidationError("Incorrect card PIN")
        return CardSensitiveDetails(card_id=card.id, mock_pan=card.mock_pan, mock_cvv=card.mock_cvv)

    def _get_or_create_credit_account(self, card: Card) -> CreditCardAccount:
        account = self.repository.get_credit_account(card.id)
        if account is not None:
            return account
        tier = card.tier or CardTier.REGULAR
        return self.repository.add_credit_account(
            CreditCardAccount(
                card_id=card.id,
                user_id=card.user_id,
                credit_limit=self.CREDIT_LIMITS[tier],
                annual_interest_rate=self.CREDIT_APRS[tier],
                collateral_amount=Decimal("0.00"),
            )
        )

    def delete_card(self, user_id: uuid.UUID, card_id: uuid.UUID) -> None:
        card = self.get_for_user(user_id, card_id)
        if card.type == CardType.CREDIT and card.credit_account is not None:
            self._release_collateral(user_id, card)
        self.repository.delete(card)

    def _reserve_collateral(self, user_id: uuid.UUID, wallet, amount: Decimal, card: Card) -> None:
        now = utcnow()
        transaction = self.transactions.add(
            Transaction(
                initiator_user_id=user_id,
                source_wallet_id=wallet.id,
                card_id=card.id,
                type=TransactionType.CARD_PAYMENT,
                status=TransactionStatus.COMPLETED,
                amount=amount,
                currency=wallet.currency,
                description=f"Credit card collateral hold for **** {card.last_four}",
                processed_at=now,
                completed_at=now,
            )
        )
        wallet.available_balance = self._money(wallet.available_balance - amount)
        wallet.reserved_balance = self._money(wallet.reserved_balance + amount)
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.HOLD,
                amount=amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )
        self.db.flush()

    def _release_collateral(self, user_id: uuid.UUID, card: Card) -> None:
        account = card.credit_account
        collateral_amount = self._money(account.collateral_amount or Decimal("0.00")) if account is not None else Decimal("0.00")
        if account is None or account.collateral_wallet_id is None or collateral_amount <= 0:
            return
        if account.used_amount > 0:
            raise ConflictError("Pay the credit card balance before deleting this secured card")
        wallet = self.wallets.get_by_id(account.collateral_wallet_id)
        if wallet is None or wallet.user_id != user_id:
            raise NotFoundError("Collateral account not found")
        amount = collateral_amount
        if wallet.reserved_balance < amount:
            amount = self._money(wallet.reserved_balance)
        now = utcnow()
        transaction = self.transactions.add(
            Transaction(
                initiator_user_id=user_id,
                destination_wallet_id=wallet.id,
                card_id=card.id,
                type=TransactionType.CARD_PAYMENT,
                status=TransactionStatus.COMPLETED,
                amount=amount,
                currency=wallet.currency,
                description=f"Credit card collateral release for **** {card.last_four}",
                processed_at=now,
                completed_at=now,
            )
        )
        wallet.reserved_balance = self._money(wallet.reserved_balance - amount)
        wallet.available_balance = self._money(wallet.available_balance + amount)
        self.transactions.add_ledger_entry(
            WalletLedgerEntry(
                wallet_id=wallet.id,
                transaction_id=transaction.id,
                entry_type=LedgerEntryType.RELEASE,
                amount=amount,
                currency=wallet.currency,
                balance_after=wallet.available_balance,
            )
        )
        self.db.flush()

    def _money(self, value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.01"))

    def _attach_pin_status(self, card: Card) -> None:
        card.has_pin = bool(card.pin_hash)

    def _validate_pin(self, pin: str) -> None:
        if len(pin) != 4 or not pin.isdigit():
            raise ValidationError("Card PIN must be exactly 4 digits")

    def freeze_card(self, user_id: uuid.UUID, card_id: uuid.UUID) -> Card:
        card = self.get_for_user(user_id, card_id)
        if card.status == CardStatus.FROZEN:
            return card
        if card.status != CardStatus.ACTIVE:
            raise ValidationError("Only active cards can be frozen")
        card.status = CardStatus.FROZEN
        self.db.flush()
        return card

    def unfreeze_card(self, user_id: uuid.UUID, card_id: uuid.UUID) -> Card:
        card = self.get_for_user(user_id, card_id)
        if card.status == CardStatus.ACTIVE:
            return card
        if card.status != CardStatus.FROZEN:
            raise ValidationError("Only frozen cards can be unfrozen")
        card.status = CardStatus.ACTIVE
        self.db.flush()
        return card

    def get_payment_preferences(self, user_id: uuid.UUID, card_id: uuid.UUID) -> CardPaymentPreferences:
        card = self.get_for_user(user_id, card_id)
        preferences = self.repository.get_preferences(card.id)
        if preferences is None:
            preferences = self.repository.add_preferences(CardPaymentPreferences(card_id=card.id))
        return preferences

    def update_payment_preferences(
        self,
        user_id: uuid.UUID,
        card_id: uuid.UUID,
        data: CardPaymentPreferencesUpdate,
    ) -> CardPaymentPreferences:
        card = self.get_for_user(user_id, card_id)
        if data.preferred_wallet_id is not None:
            wallet = self.wallets.get_by_id(data.preferred_wallet_id)
            if wallet is None or wallet.user_id != user_id:
                raise NotFoundError("Preferred wallet not found")
            if wallet.status != WalletStatus.ACTIVE:
                raise ValidationError("Preferred wallet must be active")

        preferences = self.repository.get_preferences(card.id)
        if preferences is None:
            preferences = self.repository.add_preferences(CardPaymentPreferences(card_id=card.id))

        preferences.preferred_wallet_id = data.preferred_wallet_id
        preferences.allow_main_wallet_fx = data.allow_main_wallet_fx
        self.db.flush()
        return preferences
