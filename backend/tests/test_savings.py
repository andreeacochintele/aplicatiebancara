import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.fx.schemas import FXQuoteRequest
from app.fx.service import FXService
from app.savings.models import SavingsGoalStatus
from app.savings.schemas import SavingsContribution, SavingsGoalCreate, SavingsGoalDeleteRequest, SavingsWithdrawal
from app.savings.service import SavingsService
from app.transactions.models import WalletLedgerEntry
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.repository import WalletRepository
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="savings-user@example.com", password="Sup3rSecret!", first_name="Save", last_name="User")
    )


def _funded_wallet(db_session, user_id, currency):
    wallet = WalletService(db_session).create_wallet(user_id, WalletCreate(currency=currency))
    db_session.flush()
    # Fund it directly by reaching past the wallets module - this is test
    # setup, not the deposit code path under test.
    real_wallet = WalletRepository(db_session).get_by_id(wallet.id)
    real_wallet.available_balance = Decimal("1000.00")
    db_session.flush()
    return real_wallet


@pytest.fixture()
def ron_wallet(db_session, seeded_user):
    return _funded_wallet(db_session, seeded_user.id, "RON")


@pytest.fixture()
def usd_wallet(db_session, seeded_user):
    return _funded_wallet(db_session, seeded_user.id, "USD")


def _months_from(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def test_create_goal_rejects_non_positive_target(db_session, seeded_user):
    service = SavingsService(db_session)
    with pytest.raises(ValidationError):
        service.create_goal(seeded_user.id, SavingsGoalCreate(name="Trip", target_amount=Decimal("0")))


def test_create_goal_computes_percent_and_monthly_needed(db_session, seeded_user):
    service = SavingsService(db_session)
    today = datetime.now(timezone.utc).date()
    target_date = _months_from(today, 4)

    goal = service.create_goal(
        seeded_user.id,
        SavingsGoalCreate(
            name="Japan trip",
            target_amount=Decimal("2000.00"),
            target_date=target_date,
            initial_amount=Decimal("1000.00"),
        ),
    )

    assert goal.current_amount == Decimal("1000.00")
    assert goal.percent_complete == 50.0
    assert goal.monthly_amount_needed == Decimal("250.00")
    assert goal.status == SavingsGoalStatus.ACTIVE


def test_create_goal_with_initial_amount_already_at_target_is_completed(db_session, seeded_user):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id,
        SavingsGoalCreate(name="Done already", target_amount=Decimal("500.00"), initial_amount=Decimal("500.00")),
    )
    assert goal.status == SavingsGoalStatus.COMPLETED


def test_goal_without_target_date_has_no_monthly_needed(db_session, seeded_user):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )

    assert goal.monthly_amount_needed is None


def test_contribute_debits_wallet_through_ledger_and_increases_goal(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )

    updated = service.contribute(
        seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("250.00"))
    )

    assert updated.current_amount == Decimal("250.00")
    assert updated.status == SavingsGoalStatus.ACTIVE
    assert ron_wallet.available_balance == Decimal("750.00")

    ledger_entries = list(db_session.scalars(select(WalletLedgerEntry).where(WalletLedgerEntry.wallet_id == ron_wallet.id)))
    assert len(ledger_entries) == 1
    assert ledger_entries[0].entry_type.value == "DEBIT"
    assert ledger_entries[0].amount == Decimal("250.00")
    assert ledger_entries[0].balance_after == Decimal("750.00")


def test_contribute_rejects_non_positive_amount(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )

    with pytest.raises(ValidationError):
        service.contribute(seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("0")))


def test_contribute_to_unknown_goal_raises_not_found(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    with pytest.raises(NotFoundError):
        service.contribute(
            seeded_user.id, uuid.uuid4(), SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("10"))
        )


def test_contribute_rejects_insufficient_balance(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("5000.00"))
    )

    with pytest.raises(ConflictError):
        service.contribute(
            seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("1500.00"))
        )
    # Balance must be untouched by the rejected attempt.
    assert ron_wallet.available_balance == Decimal("1000.00")


def test_contribute_reaching_target_marks_goal_completed(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("500.00"))
    )

    updated = service.contribute(
        seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("500.00"))
    )

    assert updated.status == SavingsGoalStatus.COMPLETED

    with pytest.raises(ValidationError):
        service.contribute(
            seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("10.00"))
        )


def test_contribute_overshooting_target_still_credits_full_amount(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("500.00"))
    )

    updated = service.contribute(
        seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("600.00"))
    )

    assert updated.current_amount == Decimal("600.00")
    assert updated.status == SavingsGoalStatus.COMPLETED


def test_contribute_cross_currency_uses_fx_quote(db_session, seeded_user, ron_wallet, usd_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Japan trip", target_amount=Decimal("5000.00"), currency="RON")
    )

    quote = FXService(db_session).get_quote(
        seeded_user.id,
        FXQuoteRequest(source_currency="USD", target_currency="RON", source_amount=Decimal("100.00")),
    )

    updated = service.contribute(
        seeded_user.id,
        goal.id,
        SavingsContribution(wallet_id=usd_wallet.id, amount=Decimal("100.00"), fx_quote_id=quote.id),
    )

    assert usd_wallet.available_balance == Decimal("900.00")
    assert updated.current_amount == quote.target_amount
    assert updated.current_amount > Decimal("0")


def test_contribute_cross_currency_without_quote_is_rejected(db_session, seeded_user, usd_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Japan trip", target_amount=Decimal("5000.00"), currency="RON")
    )

    with pytest.raises(ValidationError):
        service.contribute(seeded_user.id, goal.id, SavingsContribution(wallet_id=usd_wallet.id, amount=Decimal("100.00")))


def test_withdraw_credits_wallet_and_marks_goal_withdrawn(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )
    service.contribute(seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("400.00")))
    assert ron_wallet.available_balance == Decimal("600.00")

    updated = service.withdraw(seeded_user.id, goal.id, SavingsWithdrawal(wallet_id=ron_wallet.id))

    assert updated.status == SavingsGoalStatus.WITHDRAWN
    assert updated.current_amount == Decimal("0")
    assert ron_wallet.available_balance == Decimal("1000.00")

    with pytest.raises(ValidationError):
        service.withdraw(seeded_user.id, goal.id, SavingsWithdrawal(wallet_id=ron_wallet.id))


def test_withdraw_nothing_saved_is_rejected(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )

    with pytest.raises(ValidationError):
        service.withdraw(seeded_user.id, goal.id, SavingsWithdrawal(wallet_id=ron_wallet.id))


def test_withdraw_allowed_while_still_active_not_just_completed(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )
    service.contribute(seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("100.00")))

    updated = service.withdraw(seeded_user.id, goal.id, SavingsWithdrawal(wallet_id=ron_wallet.id))

    assert updated.status == SavingsGoalStatus.WITHDRAWN
    assert ron_wallet.available_balance == Decimal("1000.00")


def test_delete_already_withdrawn_goal_needs_no_wallet(db_session, seeded_user, ron_wallet):
    from app.savings.repository import SavingsGoalRepository

    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )
    service.contribute(seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("100.00")))
    service.withdraw(seeded_user.id, goal.id, SavingsWithdrawal(wallet_id=ron_wallet.id))

    service.delete_goal(seeded_user.id, goal.id, SavingsGoalDeleteRequest())

    assert SavingsGoalRepository(db_session).get_by_id(goal.id) is None


def test_delete_goal_with_money_requires_wallet_id(db_session, seeded_user, ron_wallet):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )
    service.contribute(seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("10.00")))

    with pytest.raises(ValidationError):
        service.delete_goal(seeded_user.id, goal.id, SavingsGoalDeleteRequest())


def test_delete_goal_with_money_returns_it_to_wallet_first(db_session, seeded_user, ron_wallet):
    from app.savings.repository import SavingsGoalRepository

    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )
    service.contribute(seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("10.00")))
    assert ron_wallet.available_balance == Decimal("990.00")

    service.delete_goal(seeded_user.id, goal.id, SavingsGoalDeleteRequest(wallet_id=ron_wallet.id))

    assert ron_wallet.available_balance == Decimal("1000.00")
    assert SavingsGoalRepository(db_session).get_by_id(goal.id) is None


def test_delete_completed_goal_with_money_still_returns_it(db_session, seeded_user, ron_wallet):
    """The user's own scenario: a completed goal should not sit forever,
    and deleting it must never lose the money in it."""
    from app.savings.repository import SavingsGoalRepository

    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("500.00"))
    )
    updated = service.contribute(
        seeded_user.id, goal.id, SavingsContribution(wallet_id=ron_wallet.id, amount=Decimal("500.00"))
    )
    assert updated.status == SavingsGoalStatus.COMPLETED

    service.delete_goal(seeded_user.id, goal.id, SavingsGoalDeleteRequest(wallet_id=ron_wallet.id))

    assert ron_wallet.available_balance == Decimal("1000.00")
    assert SavingsGoalRepository(db_session).get_by_id(goal.id) is None


def test_delete_unknown_goal_raises_not_found(db_session, seeded_user):
    service = SavingsService(db_session)
    with pytest.raises(NotFoundError):
        service.delete_goal(seeded_user.id, uuid.uuid4(), SavingsGoalDeleteRequest())
