import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.budgets.models import BudgetPeriod
from app.budgets.repository import BudgetRepository
from app.budgets.schemas import BudgetCreate
from app.budgets.service import BudgetService
from app.core.exceptions import NotFoundError, ValidationError
from app.merchants.models import Merchant
from app.transactions.models import Transaction, TransactionStatus, TransactionType
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture()
def seeded_user(db_session):
    return UserService(db_session).create_user(
        UserCreate(email="budget-user@example.com", password="Sup3rSecret!", first_name="Budget", last_name="User")
    )


def test_create_budget_rejects_non_positive_limit(db_session, seeded_user):
    service = BudgetService(db_session)
    with pytest.raises(ValidationError):
        service.create_budget(seeded_user.id, BudgetCreate(name="Restaurants", limit_amount=Decimal("0")))


def test_budget_without_category_reports_zero_spent(db_session, seeded_user):
    service = BudgetService(db_session)
    budget = service.create_budget(seeded_user.id, BudgetCreate(name="Restaurants", limit_amount=Decimal("1000.00")))

    assert budget.category is None
    assert budget.spent_amount == Decimal("0")
    assert budget.percent_used == 0.0
    assert budget.remaining_amount == Decimal("1000.00")


def test_budget_with_category_computes_spent_and_remaining(db_session, seeded_user):
    service = BudgetService(db_session)
    service.create_budget(
        seeded_user.id, BudgetCreate(name="Restaurants", limit_amount=Decimal("1000.00"), category="Food")
    )

    food_merchant = Merchant(name="KFC", category="Food", verified=True)
    retail_merchant = Merchant(name="Zara", category="Retail", verified=True)
    db_session.add_all([food_merchant, retail_merchant])
    db_session.flush()

    now = datetime.now(timezone.utc)
    matching = [
        Transaction(
            initiator_user_id=seeded_user.id,
            type=TransactionType.CARD_PAYMENT,
            status=TransactionStatus.COMPLETED,
            amount=amount,
            currency="RON",
            merchant_id=food_merchant.id,
            created_at=now,
        )
        for amount in (Decimal("300.00"), Decimal("500.00"))
    ]
    other_category = Transaction(
        initiator_user_id=seeded_user.id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("999.00"),
        currency="RON",
        merchant_id=retail_merchant.id,
        created_at=now,
    )
    # A transfer to the same "Food" category ID would be meaningless (no
    # merchant, not a purchase) - confirms the type filter, not just the
    # category match, is doing real work.
    not_a_purchase = Transaction(
        initiator_user_id=seeded_user.id,
        type=TransactionType.LOAN_PAYMENT,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("1600.00"),
        currency="RON",
        created_at=now,
    )
    db_session.add_all([*matching, other_category, not_a_purchase])
    db_session.flush()

    result = service.list_budgets(seeded_user.id)[0]

    assert result.spent_amount == Decimal("800.00")
    assert result.percent_used == 80.0
    assert result.remaining_amount == Decimal("200.00")


def test_weekly_budget_period_spans_at_most_seven_days(db_session, seeded_user):
    service = BudgetService(db_session)
    budget = service.create_budget(
        seeded_user.id, BudgetCreate(name="Groceries", limit_amount=Decimal("200.00"), period=BudgetPeriod.WEEKLY)
    )

    assert 0 <= budget.days_remaining <= 6


def test_delete_budget_removes_it(db_session, seeded_user):
    service = BudgetService(db_session)
    budget = service.create_budget(seeded_user.id, BudgetCreate(name="Stale test budget", limit_amount=Decimal("500.00")))

    service.delete_budget(seeded_user.id, budget.id)

    assert BudgetRepository(db_session).get_by_id(budget.id) is None


def test_delete_unknown_budget_raises_not_found(db_session, seeded_user):
    service = BudgetService(db_session)
    with pytest.raises(NotFoundError):
        service.delete_budget(seeded_user.id, uuid.uuid4())


def test_delete_someone_elses_budget_raises_not_found(db_session, seeded_user):
    other_user = UserService(db_session).create_user(
        UserCreate(email="other-budget-user@example.com", password="Sup3rSecret!", first_name="Other", last_name="User")
    )
    service = BudgetService(db_session)
    budget = service.create_budget(seeded_user.id, BudgetCreate(name="Mine", limit_amount=Decimal("100.00")))

    with pytest.raises(NotFoundError):
        service.delete_budget(other_user.id, budget.id)
