from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.cards.models import CardTier
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.exceptions import NotFoundError, ValidationError
from app.merchants.schemas import CashbackOfferCreate, MerchantCreate
from app.merchants.service import MerchantService
from app.notifications.service import NotificationsService
from app.rewards.service import RewardsService
from app.transactions.models import Transaction, TransactionStatus, TransactionType
from app.transactions.schemas import CardPaymentCreate
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="merchant-user@example.com", password="Sup3rSecret!", first_name="Merch", last_name="User")
    )


def _active_offer_window() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=1), today + timedelta(days=30)


def _card_payment(
    db_session,
    user_id,
    amount,
    description,
    status=TransactionStatus.COMPLETED,
    card_id=None,
    currency="RON",
    created_at=None,
) -> Transaction:
    transaction = Transaction(
        initiator_user_id=user_id,
        type=TransactionType.CARD_PAYMENT,
        status=status,
        amount=amount,
        currency=currency,
        description=description,
        card_id=card_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(transaction)
    db_session.flush()
    return transaction


def _wallet_for_card(db_session, user_id, currency="RON"):
    wallet_service = WalletService(db_session)
    existing_wallet = wallet_service.repository.get_by_user_and_currency(user_id, currency)
    if existing_wallet is not None:
        return existing_wallet
    return wallet_service.create_wallet(user_id, WalletCreate(currency=currency))


def _tier_card(db_session, user_id, tier: CardTier, currency="RON"):
    wallet = _wallet_for_card(db_session, user_id, currency)
    return CardService(db_session).create_card(user_id, CardCreate(tier=tier, default_wallet_id=wallet.id))


def test_list_merchants_only_returns_active(db_session):
    from app.merchants.models import MerchantStatus

    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="Nike", category="Retail"))
    inactive = service.create_merchant(MerchantCreate(name="Old Shop", category="Retail"))

    merchant_row = service.repository.get_by_id(inactive.id)
    merchant_row.status = MerchantStatus.INACTIVE
    db_session.flush()

    merchants = service.list_merchants()

    assert {m.name for m in merchants} == {"Nike"}


def test_create_cashback_offer_rejects_non_positive_percent(db_session):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="Nike", category="Retail"))
    start, end = _active_offer_window()

    with pytest.raises(ValidationError):
        service.create_cashback_offer(
            merchant.id,
            CashbackOfferCreate(cashback_percent=Decimal("0"), start_date=start, end_date=end),
        )


def test_create_cashback_offer_for_unknown_merchant_raises_not_found(db_session):
    import uuid

    service = MerchantService(db_session)
    start, end = _active_offer_window()

    with pytest.raises(NotFoundError):
        service.create_cashback_offer(
            uuid.uuid4(),
            CashbackOfferCreate(cashback_percent=Decimal("7"), start_date=start, end_date=end),
        )


def test_sync_awards_points_and_computes_cashback_from_real_transaction(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    start, end = _active_offer_window()
    service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(cashback_percent=Decimal("7"), start_date=start, end_date=end),
    )
    _card_payment(db_session, seeded_user.id, Decimal("400.00"), "Nike - Shopping")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert len(results) == 1
    result = results[0]
    # Points depend only on the card multiplier — no card_id here -> REGULAR/
    # default 1x, so points_earned is exactly the RON amount: 400. Cashback
    # (7% partner offer, no tier since there's no card) is a fully separate
    # number: 400 RON * 7% = 28 RON — money, not points.
    assert result.points_earned == 400
    assert result.cashback_percent == Decimal("7")
    assert result.cashback_amount == Decimal("28.00")
    assert result.reward_points_balance == 400
    assert result.proof_code is not None
    assert result.proof_code.startswith("PUR-")

    rewards_account = RewardsService(db_session).get_account(seeded_user.id)
    assert rewards_account.points_balance == 400
    assert rewards_account.transactions[0].proof_code == result.proof_code


def test_sync_scales_points_by_card_tier(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    card = _tier_card(db_session, seeded_user.id, CardTier.GOLD)
    _card_payment(db_session, seeded_user.id, Decimal("200.00"), "Nike - Shopping", card_id=card.id)

    results = merchant_service.sync_purchases_from_transactions(seeded_user.id)

    # 200 RON * 1.5x (GOLD) = 300 points. Cashback is separate: GOLD's 2%
    # tier cashback with no active offer = 200 * 2% = 4 RON, money only.
    assert results[0].points_earned == 300
    assert results[0].cashback_percent == Decimal("2")
    assert results[0].cashback_amount == Decimal("4.00")


def test_sync_platinum_card_doubles_points(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    card = _tier_card(db_session, seeded_user.id, CardTier.PLATINUM)
    _card_payment(db_session, seeded_user.id, Decimal("200.00"), "Nike - Shopping", card_id=card.id)

    results = merchant_service.sync_purchases_from_transactions(seeded_user.id)

    # 200 RON * 2x (PLATINUM) = 400 points. Cashback: PLATINUM's 4% tier
    # cashback with no active offer = 200 * 4% = 8 RON, money only.
    assert results[0].points_earned == 400
    assert results[0].cashback_percent == Decimal("4")
    assert results[0].cashback_amount == Decimal("8.00")


def test_sync_combines_tier_and_partner_cashback_amounts(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    start, end = _active_offer_window()
    merchant_service.create_cashback_offer(
        merchant.id, CashbackOfferCreate(cashback_percent=Decimal("5"), start_date=start, end_date=end)
    )
    card = _tier_card(db_session, seeded_user.id, CardTier.GOLD)
    _card_payment(db_session, seeded_user.id, Decimal("200.00"), "Nike - Shopping", card_id=card.id)

    results = merchant_service.sync_purchases_from_transactions(seeded_user.id)
    result = results[0]

    # Points: 200 * 1.5x = 300, completely unaffected by cashback. Cashback:
    # (2% tier + 5% partner) * 200 RON = 14 RON, credited as money.
    assert result.points_earned == 300
    assert result.cashback_percent == Decimal("7")
    assert result.cashback_amount == Decimal("14.00")


def test_sync_matches_the_hand_worked_example_50_ron_regular_card_8pct_offer(db_session, seeded_user):
    """Pins the exact worked example from the points-formula spec: 50 RON on
    a REGULAR card (1x multiplier) at a merchant with an 8% partner offer
    should give exactly 50 points (cashback has zero effect on this number)
    and 4 RON of cashback money — not 130, 260, or any figure that mixes the
    two together."""
    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    start, end = _active_offer_window()
    merchant_service.create_cashback_offer(
        merchant.id, CashbackOfferCreate(cashback_percent=Decimal("8"), start_date=start, end_date=end)
    )
    card = _tier_card(db_session, seeded_user.id, CardTier.REGULAR)
    _card_payment(db_session, seeded_user.id, Decimal("50.00"), "Nike - Shopping", card_id=card.id)

    result = merchant_service.sync_purchases_from_transactions(seeded_user.id)[0]

    assert result.points_earned == 50
    assert result.cashback_percent == Decimal("8")
    assert result.cashback_amount == Decimal("4.00")


def test_sync_awards_tier_cashback_even_without_a_partner_offer(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    card = _tier_card(db_session, seeded_user.id, CardTier.PLATINUM)
    _card_payment(db_session, seeded_user.id, Decimal("100.00"), "Nike - Shopping", card_id=card.id)

    results = merchant_service.sync_purchases_from_transactions(seeded_user.id)
    result = results[0]

    assert result.points_earned == 200  # 100 RON * 2x (PLATINUM), no partner offer needed
    assert result.cashback_percent == Decimal("4")  # tier cashback alone still applies
    assert result.cashback_amount == Decimal("4.00")  # 100 RON * 4%


def test_sync_credits_cashback_to_the_debited_wallet_as_real_money(db_session, seeded_user):
    """End-to-end with the real payment flow (TransactionService.create_card_payment,
    which actually debits a wallet and sets source_wallet_id) — the exact
    scenario from the spec: 50 RON, REGULAR card, 10% total cashback should
    leave the wallet net -45 RON (debited 50, credited back 5) and award
    exactly 50 points, with cashback never touching the points number.
    create_card_payment auto-syncs rewards on completion (see its
    docstring), so both the debit AND the cashback credit land in the same
    call — no separate sync_purchases_from_transactions call needed."""
    wallet = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("500.00")
    db_session.flush()

    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    start, end = _active_offer_window()
    merchant_service.create_cashback_offer(
        merchant.id, CashbackOfferCreate(cashback_percent=Decimal("10"), start_date=start, end_date=end)
    )
    card = CardService(db_session).create_card(seeded_user.id, CardCreate(default_wallet_id=wallet.id))

    TransactionService(db_session).create_card_payment(
        seeded_user.id,
        CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("50.00"), cvv=card.mock_cvv),
    )

    # A later explicit sync finds nothing new left to earn — it already
    # happened inside create_card_payment.
    assert merchant_service.sync_purchases_from_transactions(seeded_user.id) == []

    account = RewardsService(db_session).get_account(seeded_user.id)
    assert account.lifetime_points_earned == 50
    assert wallet.available_balance == Decimal("455.00")  # 500 - 50 debited + 5 cashback credited back
    # Net effect vs. the original 500: -45, matching the worked example exactly.
    assert Decimal("500.00") - wallet.available_balance == Decimal("45.00")

    # Cashback must be a real, standalone Transaction (not just a balance
    # tweak) so it shows up in the Transactions list and in analytics'
    # spending-by-type breakdown — same as the existing CASHBACK seed
    # example ("Cashback - Nike") already does.
    cashback_tx = (
        db_session.query(Transaction)
        .filter(Transaction.type == TransactionType.CASHBACK, Transaction.destination_wallet_id == wallet.id)
        .one()
    )
    assert cashback_tx.amount == Decimal("5.00")
    assert cashback_tx.currency == "RON"
    assert cashback_tx.status == TransactionStatus.COMPLETED
    assert cashback_tx.source_wallet_id is None
    assert cashback_tx.description == "Cashback - Nike"
    assert len(cashback_tx.ledger_entries) == 1
    assert cashback_tx.ledger_entries[0].entry_type.value == "CREDIT"

    notifications = [
        n for n in NotificationsService(db_session).list_for_user(seeded_user.id) if n.type == "CASHBACK"
    ]
    assert len(notifications) == 1
    assert notifications[0].type == "CASHBACK"
    assert notifications[0].message == "You earned 5.00 RON cashback from Nike."
    assert notifications[0].related_transaction_id == cashback_tx.id
    assert notifications[0].is_read is False


def test_sync_credits_cashback_even_if_the_notification_write_fails(db_session, seeded_user, monkeypatch):
    """A notification is best-effort — if creating it blows up (e.g. a
    shared DB that's behind on migrations, exactly what happened live), the
    cashback money and the points already earned must not be rolled back or
    silently dropped. The failure has to be in place BEFORE the payment now:
    create_card_payment syncs rewards internally on completion, so that's
    where the notification write actually happens, not in a later separate
    sync call."""
    wallet = WalletService(db_session).create_wallet(seeded_user.id, WalletCreate(currency="RON"))
    wallet.available_balance = Decimal("500.00")
    db_session.flush()

    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    start, end = _active_offer_window()
    merchant_service.create_cashback_offer(
        merchant.id, CashbackOfferCreate(cashback_percent=Decimal("10"), start_date=start, end_date=end)
    )
    card = CardService(db_session).create_card(seeded_user.id, CardCreate(default_wallet_id=wallet.id))

    monkeypatch.setattr(NotificationsService, "create", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError))

    TransactionService(db_session).create_card_payment(
        seeded_user.id,
        CardPaymentCreate(card_id=card.id, merchant_id=merchant.id, amount=Decimal("50.00"), cvv=card.mock_cvv),
    )

    account = RewardsService(db_session).get_account(seeded_user.id)
    assert account.lifetime_points_earned == 50
    assert wallet.available_balance == Decimal("455.00")
    cashback_notifications = [
        n for n in NotificationsService(db_session).list_for_user(seeded_user.id) if n.type == "CASHBACK"
    ]
    assert cashback_notifications == []


def test_sync_without_a_known_card_uses_base_rate(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    _card_payment(db_session, seeded_user.id, Decimal("200.00"), "Nike - Shopping")  # no card_id, e.g. seed data

    results = merchant_service.sync_purchases_from_transactions(seeded_user.id)

    assert results[0].points_earned == 200


def test_sync_converts_non_ron_amount_to_ron_before_scoring_points(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    card = _tier_card(db_session, seeded_user.id, CardTier.REGULAR, currency="EUR")
    # 100 EUR at the mocked 4.97 RON/EUR rate (app/fx/service.py) -> 497 RON -> 497 points at 1x.
    _card_payment(db_session, seeded_user.id, Decimal("100.00"), "Nike - Shopping", card_id=card.id, currency="EUR")

    results = merchant_service.sync_purchases_from_transactions(seeded_user.id)

    assert results[0].points_earned == 497


def test_sync_caps_cashback_at_maximum(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="Starbucks", category="Food", verified=True))
    start, end = _active_offer_window()
    service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(
            cashback_percent=Decimal("10"), maximum_cashback=Decimal("5.00"), start_date=start, end_date=end
        ),
    )
    _card_payment(db_session, seeded_user.id, Decimal("200.00"), "Starbucks - Coffee")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results[0].cashback_amount == Decimal("5.00")


def test_sync_below_minimum_spend_earns_no_cashback(db_session, seeded_user):
    service = MerchantService(db_session)
    merchant = service.create_merchant(MerchantCreate(name="eMAG", category="Retail", verified=True))
    start, end = _active_offer_window()
    service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(cashback_percent=Decimal("5"), minimum_spend=Decimal("100.00"), start_date=start, end_date=end),
    )
    _card_payment(db_session, seeded_user.id, Decimal("50.00"), "eMAG order")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results[0].cashback_percent is None
    assert results[0].cashback_amount == Decimal("0")
    assert results[0].points_earned == 50


def test_sync_uses_the_offer_active_when_the_payment_was_made_not_when_it_syncs(db_session, seeded_user):
    """A payment held for fraud review can be approved (and therefore
    synced) well after its original date — it must earn whatever offer was
    active when the purchase actually happened, not whatever's active (or
    already expired) on the day the sync happens to run."""
    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    today = date.today()
    merchant_service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(
            cashback_percent=Decimal("7"),
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=20),
        ),
    )
    _card_payment(
        db_session,
        seeded_user.id,
        Decimal("100.00"),
        "Nike - Shopping",
        created_at=datetime.now(timezone.utc) - timedelta(days=25),
    )

    result = merchant_service.sync_purchases_from_transactions(seeded_user.id)[0]

    assert result.cashback_percent == Decimal("7")
    assert result.cashback_amount == Decimal("7.00")


def test_sync_does_not_apply_an_offer_that_started_after_the_payment_was_made(db_session, seeded_user):
    merchant_service = MerchantService(db_session)
    merchant = merchant_service.create_merchant(MerchantCreate(name="Nike", category="Retail", verified=True))
    today = date.today()
    merchant_service.create_cashback_offer(
        merchant.id,
        CashbackOfferCreate(cashback_percent=Decimal("7"), start_date=today - timedelta(days=1), end_date=today + timedelta(days=30)),
    )
    _card_payment(
        db_session,
        seeded_user.id,
        Decimal("100.00"),
        "Nike - Shopping",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )

    result = merchant_service.sync_purchases_from_transactions(seeded_user.id)[0]

    assert result.cashback_percent is None
    assert result.cashback_amount == Decimal("0")


def test_sync_ignores_unverified_merchants(db_session, seeded_user):
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel"))  # verified defaults to False
    _card_payment(db_session, seeded_user.id, Decimal("120.00"), "OMV - Fuel")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results == []
    assert RewardsService(db_session).get_account(seeded_user.id).points_balance == 0


def test_sync_ignores_transactions_at_unknown_merchants(db_session, seeded_user):
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel"))
    _card_payment(db_session, seeded_user.id, Decimal("120.00"), "Unlisted Shop")

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results == []


def test_sync_ignores_non_completed_or_non_card_transactions(db_session, seeded_user):
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel"))
    _card_payment(db_session, seeded_user.id, Decimal("100.00"), "OMV - Fuel", status=TransactionStatus.PENDING_REVIEW)
    pending = Transaction(
        initiator_user_id=seeded_user.id,
        type=TransactionType.TRANSFER,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("100.00"),
        currency="RON",
        description="OMV - Fuel",
    )
    db_session.add(pending)
    db_session.flush()

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results == []


def test_sync_does_not_double_award_the_same_transaction(db_session, seeded_user):
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel", verified=True))
    _card_payment(db_session, seeded_user.id, Decimal("100.00"), "OMV - Fuel")

    first = service.sync_purchases_from_transactions(seeded_user.id)
    second = service.sync_purchases_from_transactions(seeded_user.id)

    assert len(first) == 1
    assert second == []
    assert RewardsService(db_session).get_account(seeded_user.id).points_balance == 100


def test_sync_survives_a_concurrent_award_race(db_session, seeded_user, monkeypatch):
    """Simulates two overlapping sync calls both passing the has_earned_for_transaction
    check before either commits — the unique constraint (migration 0011) plus the
    per-row savepoint should make the loser skip that transaction instead of
    crashing the whole sync call or double-crediting points."""
    service = MerchantService(db_session)
    service.create_merchant(MerchantCreate(name="OMV", category="Fuel", verified=True))
    payment = _card_payment(db_session, seeded_user.id, Decimal("100.00"), "OMV - Fuel")

    # A "concurrent" request already committed its award for this transaction...
    RewardsService(db_session).earn_points(
        seeded_user.id, 100, description="Card payment at OMV", source_transaction_id=payment.id
    )
    # ...but pretend our check ran before that commit was visible, so this call
    # still attempts to insert a second reward_transaction for the same payment.
    monkeypatch.setattr(RewardsService, "has_earned_for_transaction", lambda self, source_transaction_id: False)

    results = service.sync_purchases_from_transactions(seeded_user.id)

    assert results == []
    assert RewardsService(db_session).get_account(seeded_user.id).points_balance == 100
