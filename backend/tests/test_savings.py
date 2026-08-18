import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.savings.schemas import SavingsGoalCreate
from app.savings.service import SavingsService
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="savings-user@example.com", password="Sup3rSecret!", first_name="Save", last_name="User")
    )


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


def test_goal_without_target_date_has_no_monthly_needed(db_session, seeded_user):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )

    assert goal.monthly_amount_needed is None


def test_contribute_increases_current_amount(db_session, seeded_user):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )

    updated = service.contribute(seeded_user.id, goal.id, Decimal("250.00"))

    assert updated.current_amount == Decimal("250.00")


def test_contribute_rejects_non_positive_amount(db_session, seeded_user):
    service = SavingsService(db_session)
    goal = service.create_goal(
        seeded_user.id, SavingsGoalCreate(name="Emergency fund", target_amount=Decimal("1000.00"))
    )

    with pytest.raises(ValidationError):
        service.contribute(seeded_user.id, goal.id, Decimal("0"))


def test_contribute_to_unknown_goal_raises_not_found(db_session, seeded_user):
    service = SavingsService(db_session)
    with pytest.raises(NotFoundError):
        service.contribute(seeded_user.id, uuid.uuid4(), Decimal("10"))
