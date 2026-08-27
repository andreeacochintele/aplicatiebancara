from decimal import Decimal

import pytest

from app.cards.models import CardStatus, CardTier, CardType
from app.cards.schemas import CardCreate, CardPaymentPreferencesUpdate
from app.cards.service import CardService
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.fx.models import FXQuoteStatus
from app.fx.schemas import FXQuoteRequest
from app.fx.service import FXService
from app.merchants.schemas import MerchantCreate
from app.merchants.service import MerchantService
from app.transactions.models import TransactionStatus, TransactionType
from app.transactions.schemas import CardPaymentCreate, CreditCardRepaymentCreate, InternalTransferCreate
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def two_ron_wallets(db_session):
    users = UserService(db_session)
    wallets = WalletService(db_session)

    sender = users.create_user(
        UserCreate(email="sender@example.com", password="Sup3rSecret!", first_name="Send", last_name="Er")
    )
    receiver = users.create_user(
        UserCreate(email="receiver@example.com", password="Sup3rSecret!", first_name="Rece", last_name="Iver")
    )

    sender_wallet = wallets.create_wallet(sender.id, WalletCreate(currency="RON"))
    receiver_wallet = wallets.create_wallet(receiver.id, WalletCreate(currency="RON"))
    sender_wallet.available_balance = Decimal("500.00")
    db_session.flush()

    return sender, sender_wallet, receiver_wallet


def test_internal_transfer_moves_balance_and_writes_ledger(db_session, two_ron_wallets):
    sender, sender_wallet, receiver_wallet = two_ron_wallets
    service = TransactionService(db_session)

    transaction = service.create_internal_transfer(
        sender.id,
        InternalTransferCreate(
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("100.00"),
            description="Test transfer",
        ),
    )

    assert transaction.status == TransactionStatus.COMPLETED
    assert sender_wallet.available_balance == Decimal("400.00")
    assert receiver_wallet.available_balance == Decimal("100.00")
    assert len(transaction.ledger_entries) == 2


def test_transfer_rejects_insufficient_balance(db_session, two_ron_wallets):
    sender, sender_wallet, receiver_wallet = two_ron_wallets
    service = TransactionService(db_session)

    with pytest.raises(ConflictError):
        service.create_internal_transfer(
            sender.id,
            InternalTransferCreate(
                source_wallet_id=sender_wallet.id,
                destination_wallet_id=receiver_wallet.id,
                amount=Decimal("999999.00"),
            ),
        )


def test_transfer_rejects_non_positive_amount(db_session, two_ron_wallets):
    sender, sender_wallet, receiver_wallet = two_ron_wallets
    service = TransactionService(db_session)

    with pytest.raises(ValidationError):
        service.create_internal_transfer(
            sender.id,
            InternalTransferCreate(
                source_wallet_id=sender_wallet.id,
                destination_wallet_id=receiver_wallet.id,
                amount=Decimal("0.00"),
            ),
        )


def test_recipient_can_list_incoming_transfer(db_session, two_ron_wallets):
    sender, sender_wallet, receiver_wallet = two_ron_wallets
    service = TransactionService(db_session)

    transaction = service.create_internal_transfer(
        sender.id,
        InternalTransferCreate(
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("75.00"),
            description="Incoming visibility",
        ),
    )

    transactions = service.list_for_user(receiver_wallet.user_id)

    assert [item.id for item in transactions] == [transaction.id]


def test_recipient_can_fetch_incoming_transfer(db_session, two_ron_wallets):
    sender, sender_wallet, receiver_wallet = two_ron_wallets
    service = TransactionService(db_session)

    transaction = service.create_internal_transfer(
        sender.id,
        InternalTransferCreate(
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("75.00"),
        ),
    )

    fetched = service.get_for_user(receiver_wallet.user_id, transaction.id)

    assert fetched.id == transaction.id


def test_unrelated_user_cannot_fetch_transfer(db_session, two_ron_wallets):
    users = UserService(db_session)
    unrelated = users.create_user(
        UserCreate(email="unrelated@example.com", password="Sup3rSecret!", first_name="Un", last_name="Related")
    )
    sender, sender_wallet, receiver_wallet = two_ron_wallets
    service = TransactionService(db_session)
    transaction = service.create_internal_transfer(
        sender.id,
        InternalTransferCreate(
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("75.00"),
        ),
    )

    with pytest.raises(NotFoundError):
        service.get_for_user(unrelated.id, transaction.id)


@pytest.fixture()
def eur_to_ron_wallets(db_session):
    users = UserService(db_session)
    wallets = WalletService(db_session)

    sender = users.create_user(
        UserCreate(email="fx-sender@example.com", password="Sup3rSecret!", first_name="Send", last_name="Er")
    )
    receiver = users.create_user(
        UserCreate(email="fx-receiver@example.com", password="Sup3rSecret!", first_name="Rece", last_name="Iver")
    )

    sender_wallet = wallets.create_wallet(sender.id, WalletCreate(currency="EUR"))
    receiver_wallet = wallets.create_wallet(receiver.id, WalletCreate(currency="RON"))
    sender_wallet.available_balance = Decimal("500.00")
    db_session.flush()

    return sender, sender_wallet, receiver_wallet


def test_cross_currency_transfer_uses_quote(db_session, eur_to_ron_wallets):
    sender, sender_wallet, receiver_wallet = eur_to_ron_wallets
    quote = FXService(db_session).get_quote(
        sender.id, FXQuoteRequest(source_currency="EUR", target_currency="RON", source_amount=Decimal("100"))
    )
    db_session.flush()

    transaction = TransactionService(db_session).create_internal_transfer(
        sender.id,
        InternalTransferCreate(
            source_wallet_id=sender_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("100"),
            fx_quote_id=quote.id,
        ),
    )

    assert transaction.status == TransactionStatus.COMPLETED
    assert transaction.currency == "RON"
    assert transaction.amount == quote.target_amount
    assert transaction.source_currency == "EUR"
    assert transaction.source_amount == Decimal("100")
    assert transaction.exchange_rate == quote.exchange_rate
    assert sender_wallet.available_balance == Decimal("400.00")
    assert receiver_wallet.available_balance == quote.target_amount
    assert quote.status == FXQuoteStatus.ACCEPTED


def test_cross_currency_transfer_requires_quote(db_session, eur_to_ron_wallets):
    sender, sender_wallet, receiver_wallet = eur_to_ron_wallets

    with pytest.raises(ValidationError):
        TransactionService(db_session).create_internal_transfer(
            sender.id,
            InternalTransferCreate(
                source_wallet_id=sender_wallet.id,
                destination_wallet_id=receiver_wallet.id,
                amount=Decimal("100"),
            ),
        )


def test_cross_currency_transfer_rejects_amount_quote_mismatch(db_session, eur_to_ron_wallets):
    sender, sender_wallet, receiver_wallet = eur_to_ron_wallets
    quote = FXService(db_session).get_quote(
        sender.id, FXQuoteRequest(source_currency="EUR", target_currency="RON", source_amount=Decimal("100"))
    )
    db_session.flush()

    with pytest.raises(ValidationError):
        TransactionService(db_session).create_internal_transfer(
            sender.id,
            InternalTransferCreate(
                source_wallet_id=sender_wallet.id,
                destination_wallet_id=receiver_wallet.id,
                amount=Decimal("50"),  # doesn't match the quoted 100
                fx_quote_id=quote.id,
            ),
        )


@pytest.fixture()
def payer_with_wallet_and_merchant(db_session):
    payer = UserService(db_session).create_user(
        UserCreate(email="payer@example.com", password="Sup3rSecret!", first_name="Pay", last_name="Er")
    )
    wallet = WalletService(db_session).create_wallet(payer.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("500.00")
    db_session.flush()
    merchant = MerchantService(db_session).create_merchant(MerchantCreate(name="Nike", category="Retail"))
    return payer, wallet, merchant


def test_card_payment_debits_wallet_and_tags_merchant(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(payer.id, CardCreate(default_wallet_id=wallet.id))

    transaction = TransactionService(db_session).create_card_payment(
        payer.id, CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("120.00"), cvv=card.mock_cvv)
    )

    assert transaction.status == TransactionStatus.COMPLETED
    assert transaction.type == TransactionType.CARD_PAYMENT
    assert transaction.merchant_id == merchant.id
    assert transaction.card_id == card.id
    assert wallet.available_balance == Decimal("380.00")
    assert len(transaction.ledger_entries) == 1
    assert transaction.ledger_entries[0].entry_type.value == "DEBIT"


def test_credit_card_payment_uses_credit_account_not_wallet(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(
        payer.id, CardCreate(type=CardType.CREDIT, tier=CardTier.REGULAR)
    )

    transaction = TransactionService(db_session).create_card_payment(
        payer.id, CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("120.00"), cvv=card.mock_cvv)
    )

    assert transaction.status == TransactionStatus.COMPLETED
    assert transaction.type == TransactionType.CARD_PAYMENT
    assert transaction.source_wallet_id is None
    assert transaction.merchant_id == merchant.id
    assert transaction.card_id == card.id
    assert wallet.available_balance == Decimal("500.00")
    assert card.credit_account.used_amount == Decimal("120.00")
    assert card.credit_account.available_credit == Decimal("4880.00")
    assert transaction.ledger_entries == []


def test_credit_card_repayment_debits_wallet_and_restores_credit(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(
        payer.id, CardCreate(type=CardType.CREDIT, tier=CardTier.REGULAR)
    )
    service = TransactionService(db_session)
    service.create_card_payment(
        payer.id, CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("120.00"), cvv=card.mock_cvv)
    )

    transaction = service.create_credit_card_repayment(
        payer.id, CreditCardRepaymentCreate(card_id=card.id, source_wallet_id=wallet.id, amount=Decimal("50.00"))
    )

    assert transaction.status == TransactionStatus.COMPLETED
    assert transaction.type == TransactionType.LOAN_PAYMENT
    assert transaction.source_wallet_id == wallet.id
    assert transaction.card_id == card.id
    assert wallet.available_balance == Decimal("450.00")
    assert card.credit_account.used_amount == Decimal("70.00")
    assert card.credit_account.available_credit == Decimal("4930.00")
    assert len(transaction.ledger_entries) == 1
    assert transaction.ledger_entries[0].entry_type.value == "DEBIT"


def test_credit_card_payment_rejects_over_limit(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(
        payer.id, CardCreate(type=CardType.CREDIT, tier=CardTier.REGULAR)
    )

    with pytest.raises(ConflictError):
        TransactionService(db_session).create_card_payment(
            payer.id, CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("5000.01"), cvv=card.mock_cvv)
        )

    assert wallet.available_balance == Decimal("500.00")
    assert card.credit_account.used_amount == Decimal("0.00")


def test_card_payment_rejects_wrong_cvv(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(payer.id, CardCreate(default_wallet_id=wallet.id))
    wrong_cvv = "000" if card.mock_cvv != "000" else "111"

    with pytest.raises(ValidationError):
        TransactionService(db_session).create_card_payment(
            payer.id, CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("50.00"), cvv=wrong_cvv)
        )
    assert wallet.available_balance == Decimal("500.00")


def test_card_payment_rejects_another_cards_cvv(db_session, payer_with_wallet_and_merchant):
    """A CVV that's valid for a different card the same user owns must not
    authorize a payment on this one — the check is card-specific, not just
    "any CVV this user has"."""
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card_service = CardService(db_session)
    card = card_service.create_card(payer.id, CardCreate(default_wallet_id=wallet.id))
    other_wallet = WalletService(db_session).create_wallet(payer.id, WalletCreate(currency="EUR"))
    other_card = card_service.create_card(payer.id, CardCreate(default_wallet_id=other_wallet.id))
    assert other_card.mock_cvv != card.mock_cvv

    with pytest.raises(ValidationError):
        TransactionService(db_session).create_card_payment(
            payer.id,
            CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("50.00"), cvv=other_card.mock_cvv),
        )
    assert wallet.available_balance == Decimal("500.00")


def test_card_payment_rejects_frozen_card(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card_service = CardService(db_session)
    card = card_service.create_card(payer.id, CardCreate(default_wallet_id=wallet.id))
    card_service.freeze_card(payer.id, card.id)

    with pytest.raises(ValidationError):
        TransactionService(db_session).create_card_payment(
            payer.id,
            CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("50.00"), cvv=card.mock_cvv),
        )
    assert wallet.available_balance == Decimal("500.00")


def test_card_payment_rejects_and_marks_expired_card(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(payer.id, CardCreate(default_wallet_id=wallet.id))
    card.expiration_month = 1
    card.expiration_year = 2000

    with pytest.raises(ValidationError, match="expired"):
        TransactionService(db_session).create_card_payment(
            payer.id,
            CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("50.00"), cvv=card.mock_cvv),
        )

    assert card.status == CardStatus.EXPIRED
    assert wallet.available_balance == Decimal("500.00")


def test_credit_card_payment_rejects_and_marks_expired_card(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(
        payer.id, CardCreate(type=CardType.CREDIT, tier=CardTier.REGULAR)
    )
    card.expiration_month = 1
    card.expiration_year = 2000

    with pytest.raises(ValidationError, match="expired"):
        TransactionService(db_session).create_card_payment(
            payer.id,
            CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("50.00"), cvv=card.mock_cvv),
        )

    assert card.status == CardStatus.EXPIRED
    assert wallet.available_balance == Decimal("500.00")
    assert card.credit_account is not None
    assert card.credit_account.used_amount == Decimal("0.00")


def test_card_payment_rejects_insufficient_balance(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(payer.id, CardCreate(default_wallet_id=wallet.id))

    with pytest.raises(ConflictError):
        TransactionService(db_session).create_card_payment(
            payer.id,
            CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("999999.00"), cvv=card.mock_cvv),
        )


def test_card_payment_rejects_unknown_merchant(db_session, payer_with_wallet_and_merchant):
    import uuid

    payer, wallet, _merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(payer.id, CardCreate(default_wallet_id=wallet.id))

    with pytest.raises(NotFoundError):
        TransactionService(db_session).create_card_payment(
            payer.id,
            CardPaymentCreate(card_id=card.id, merchant_id=uuid.uuid4(), amount=Decimal("10.00"), cvv=card.mock_cvv),
        )


def test_one_time_card_is_cancelled_after_its_single_payment(db_session, payer_with_wallet_and_merchant):
    payer, wallet, merchant = payer_with_wallet_and_merchant
    card = CardService(db_session).create_card(
        payer.id, CardCreate(type=CardType.ONE_TIME, default_wallet_id=wallet.id)
    )
    assert card.one_time_remaining == 1

    TransactionService(db_session).create_card_payment(
        payer.id, CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("30.00"), cvv=card.mock_cvv)
    )

    assert card.one_time_remaining == 0
    assert card.status == CardStatus.CANCELLED


def test_card_payment_uses_preferred_wallet_over_default(db_session, payer_with_wallet_and_merchant):
    payer, default_wallet, merchant = payer_with_wallet_and_merchant
    wallets = WalletService(db_session)
    preferred_wallet = wallets.create_wallet(payer.id, WalletCreate(currency="EUR"))
    preferred_wallet.available_balance = Decimal("200.00")
    db_session.flush()

    card_service = CardService(db_session)
    card = card_service.create_card(payer.id, CardCreate(default_wallet_id=default_wallet.id))
    card_service.update_payment_preferences(
        payer.id, card.id, CardPaymentPreferencesUpdate(preferred_wallet_id=preferred_wallet.id)
    )

    transaction = TransactionService(db_session).create_card_payment(
        payer.id, CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("40.00"), cvv=card.mock_cvv)
    )

    assert transaction.source_wallet_id == preferred_wallet.id
    assert preferred_wallet.available_balance == Decimal("160.00")
    assert default_wallet.available_balance == Decimal("500.00")
