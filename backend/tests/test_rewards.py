import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.rewards.service import RewardsService
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="rewards-user@example.com", password="Sup3rSecret!", first_name="Reward", last_name="User")
    )


def test_new_user_has_zero_balance_and_empty_history(db_session, seeded_user):
    account = RewardsService(db_session).get_account(seeded_user.id)

    assert account.points_balance == 0
    assert account.transactions == []


def test_earn_points_increases_balance_and_records_ledger_entry(db_session, seeded_user):
    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 120, description="Purchase at Nike")

    account = service.get_account(seeded_user.id)

    assert account.points_balance == 120
    assert len(account.transactions) == 1
    assert account.transactions[0].points == 120
    assert account.transactions[0].type == "EARN"


def test_earn_points_rejects_non_positive_amount(db_session, seeded_user):
    with pytest.raises(ValidationError):
        RewardsService(db_session).earn_points(seeded_user.id, 0)


def test_redeem_points_decreases_balance(db_session, seeded_user):
    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 500)

    account = service.redeem_points(seeded_user.id, 200)

    assert account.points_balance == 300
    assert account.transactions[0].points == -200
    assert account.transactions[0].type == "SPEND"


def test_redeem_points_rejects_insufficient_balance(db_session, seeded_user):
    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 50)

    with pytest.raises(ConflictError):
        service.redeem_points(seeded_user.id, 51)


def test_redeem_points_rejects_non_positive_amount(db_session, seeded_user):
    with pytest.raises(ValidationError):
        RewardsService(db_session).redeem_points(seeded_user.id, 0)
