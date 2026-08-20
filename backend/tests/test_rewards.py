import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.cards.models import CardTier
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.rewards.models import BenefitCategory, BenefitRedemption, RewardBenefit
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
    assert account.lifetime_points_earned == 0
    assert account.transactions == []


def test_referral_code_is_generated_once_and_persists(db_session, seeded_user):
    service = RewardsService(db_session)

    first = service.get_account(seeded_user.id)
    second = service.get_account(seeded_user.id)

    assert first.referral_code is not None
    assert first.referral_code.startswith("AURORA-")
    assert first.referral_code == second.referral_code


def test_earn_points_increases_balance_and_records_ledger_entry(db_session, seeded_user):
    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 120, description="Purchase at Nike")

    account = service.get_account(seeded_user.id)

    assert account.points_balance == 120
    assert account.lifetime_points_earned == 120
    assert len(account.transactions) == 1
    assert account.transactions[0].points == 120
    assert account.transactions[0].type == "EARN"


def test_earn_points_rejects_non_positive_amount(db_session, seeded_user):
    with pytest.raises(ValidationError):
        RewardsService(db_session).earn_points(seeded_user.id, 0)


def test_redeem_points_decreases_balance_but_not_lifetime_points(db_session, seeded_user):
    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 500)

    account = service.redeem_points(seeded_user.id, 200)

    assert account.points_balance == 300
    assert account.lifetime_points_earned == 500
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


def _regular_card(db_session, user_id):
    return CardService(db_session).create_card(user_id, CardCreate(tier=CardTier.REGULAR))


def _gold_card(db_session, user_id):
    return CardService(db_session).create_card(user_id, CardCreate(tier=CardTier.GOLD))


def _platinum_card(db_session, user_id):
    return CardService(db_session).create_card(user_id, CardCreate(tier=CardTier.PLATINUM))


def test_list_benefits_locks_by_card_tier_and_points(db_session, seeded_user):
    _regular_card(db_session, seeded_user.id)
    lounge = RewardBenefit(
        name="Priority Pass Lounge Access",
        category=BenefitCategory.LOUNGE_ACCESS,
        description="One lounge visit",
        points_cost=1500,
        min_card_tier=CardTier.GOLD,
        partner_name="Priority Pass",
    )
    discount = RewardBenefit(
        name="10% off at eMAG",
        category=BenefitCategory.RETAIL_DISCOUNT,
        description="10% voucher",
        points_cost=300,
        partner_name="eMAG",
    )
    db_session.add_all([lounge, discount])
    db_session.flush()

    service = RewardsService(db_session)
    benefits = service.list_benefits(seeded_user.id)

    lounge_public = next(b for b in benefits if b.name == "Priority Pass Lounge Access")
    discount_public = next(b for b in benefits if b.name == "10% off at eMAG")

    assert lounge_public.can_redeem is False
    assert "Gold" in lounge_public.reason_if_locked
    assert discount_public.can_redeem is False
    assert discount_public.reason_if_locked == "Not enough points"


def test_list_benefits_unlocks_with_a_high_enough_card_tier(db_session, seeded_user):
    _platinum_card(db_session, seeded_user.id)
    lounge = RewardBenefit(
        name="Priority Pass Lounge Access",
        category=BenefitCategory.LOUNGE_ACCESS,
        description="One lounge visit",
        points_cost=1500,
        min_card_tier=CardTier.GOLD,
        partner_name="Priority Pass",
    )
    db_session.add(lounge)
    db_session.flush()
    RewardsService(db_session).earn_points(seeded_user.id, 1500)

    benefits = RewardsService(db_session).list_benefits(seeded_user.id)

    lounge_public = next(b for b in benefits if b.name == "Priority Pass Lounge Access")
    assert lounge_public.can_redeem is True  # Platinum satisfies a GOLD-tier gate


def test_redeem_benefit_spends_points_records_redemption_and_generates_a_code(db_session, seeded_user):
    card = _regular_card(db_session, seeded_user.id)
    discount = RewardBenefit(
        name="10% off at eMAG",
        category=BenefitCategory.RETAIL_DISCOUNT,
        description="10% voucher",
        points_cost=300,
        partner_name="eMAG",
    )
    db_session.add(discount)
    db_session.flush()

    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 500)

    account = service.redeem_benefit(seeded_user.id, discount.id, card.id)

    assert account.points_balance == 200
    assert len(account.redemptions) == 1
    redemption = account.redemptions[0]
    assert redemption.benefit_name == "10% off at eMAG"
    assert redemption.points_spent == 300
    assert redemption.card_id == card.id
    assert redemption.redemption_code is not None
    assert redemption.redemption_code.startswith("RWD-")
    assert redemption.status == "VALID"
    assert redemption.used_at is None
    assert redemption.expires_at is not None


def test_redeem_benefit_rejects_below_required_card_tier(db_session, seeded_user):
    card = _regular_card(db_session, seeded_user.id)
    lounge = RewardBenefit(
        name="Priority Pass Lounge Access",
        category=BenefitCategory.LOUNGE_ACCESS,
        description="One lounge visit",
        points_cost=1500,
        min_card_tier=CardTier.PLATINUM,
        partner_name="Priority Pass",
    )
    db_session.add(lounge)
    db_session.flush()

    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 2000)  # plenty of points, wrong card tier

    with pytest.raises(ValidationError):
        service.redeem_benefit(seeded_user.id, lounge.id, card.id)


def test_redeem_benefit_uses_best_owned_card_tier_not_the_selected_receipt_card(db_session, seeded_user):
    """Eligibility must be global (any card the user owns), not scoped to
    whichever card happens to be selected in the redemption's "pay with"
    dropdown — that field is receipt-only. A Platinum owner picking their
    Regular card as the receipt card should still be able to redeem a
    Gold-gated benefit."""
    regular_card = _regular_card(db_session, seeded_user.id)
    _platinum_card(db_session, seeded_user.id)  # owned, but not the one passed below
    lounge = RewardBenefit(
        name="Priority Pass Lounge Access",
        category=BenefitCategory.LOUNGE_ACCESS,
        description="One lounge visit",
        points_cost=1500,
        min_card_tier=CardTier.GOLD,
        partner_name="Priority Pass",
    )
    db_session.add(lounge)
    db_session.flush()

    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 1500)

    account = service.redeem_benefit(seeded_user.id, lounge.id, regular_card.id)

    assert account.points_balance == 0
    assert len(account.redemptions) == 1
    assert account.redemptions[0].card_id == regular_card.id  # receipt card, unchanged


def test_redeem_benefit_rejects_insufficient_points(db_session, seeded_user):
    card = _gold_card(db_session, seeded_user.id)
    discount = RewardBenefit(
        name="10% off at eMAG",
        category=BenefitCategory.RETAIL_DISCOUNT,
        description="10% voucher",
        points_cost=300,
        partner_name="eMAG",
    )
    db_session.add(discount)
    db_session.flush()

    with pytest.raises(ConflictError):
        RewardsService(db_session).redeem_benefit(seeded_user.id, discount.id, card.id)


def test_redeem_benefit_rejects_someone_elses_card(db_session, seeded_user):
    other_user = UserService(db_session).create_user(
        UserCreate(email="other-user@example.com", password="Sup3rSecret!", first_name="Other", last_name="User")
    )
    other_card = _regular_card(db_session, other_user.id)
    discount = RewardBenefit(
        name="10% off at eMAG",
        category=BenefitCategory.RETAIL_DISCOUNT,
        description="10% voucher",
        points_cost=300,
        partner_name="eMAG",
    )
    db_session.add(discount)
    db_session.flush()
    RewardsService(db_session).earn_points(seeded_user.id, 500)

    with pytest.raises(NotFoundError):
        RewardsService(db_session).redeem_benefit(seeded_user.id, discount.id, other_card.id)


def test_redeem_unknown_benefit_raises_not_found(db_session, seeded_user):
    card = _regular_card(db_session, seeded_user.id)
    with pytest.raises(NotFoundError):
        RewardsService(db_session).redeem_benefit(seeded_user.id, uuid.uuid4(), card.id)


def test_redeem_benefit_with_unknown_card_raises_not_found(db_session, seeded_user):
    discount = RewardBenefit(
        name="10% off at eMAG",
        category=BenefitCategory.RETAIL_DISCOUNT,
        description="10% voucher",
        points_cost=300,
        partner_name="eMAG",
    )
    db_session.add(discount)
    db_session.flush()
    RewardsService(db_session).earn_points(seeded_user.id, 500)

    with pytest.raises(NotFoundError):
        RewardsService(db_session).redeem_benefit(seeded_user.id, discount.id, uuid.uuid4())


def _redeem_a_benefit(db_session, user_id, card_id) -> uuid.UUID:
    discount = RewardBenefit(
        name="10% off at eMAG",
        category=BenefitCategory.RETAIL_DISCOUNT,
        description="10% voucher",
        points_cost=300,
        partner_name="eMAG",
    )
    db_session.add(discount)
    db_session.flush()
    service = RewardsService(db_session)
    service.earn_points(user_id, 500)
    account = service.redeem_benefit(user_id, discount.id, card_id)
    return account.redemptions[0].id


def test_mark_redemption_used_flips_status_to_used(db_session, seeded_user):
    card = _regular_card(db_session, seeded_user.id)
    redemption_id = _redeem_a_benefit(db_session, seeded_user.id, card.id)

    account = RewardsService(db_session).mark_redemption_used(seeded_user.id, redemption_id)

    redemption = next(r for r in account.redemptions if r.id == redemption_id)
    assert redemption.status == "USED"
    assert redemption.used_at is not None


def test_mark_redemption_used_rejects_already_used(db_session, seeded_user):
    card = _regular_card(db_session, seeded_user.id)
    redemption_id = _redeem_a_benefit(db_session, seeded_user.id, card.id)
    service = RewardsService(db_session)
    service.mark_redemption_used(seeded_user.id, redemption_id)

    with pytest.raises(ValidationError):
        service.mark_redemption_used(seeded_user.id, redemption_id)


def test_mark_redemption_used_rejects_expired_voucher(db_session, seeded_user):
    card = _regular_card(db_session, seeded_user.id)
    redemption_id = _redeem_a_benefit(db_session, seeded_user.id, card.id)
    redemption = db_session.get(BenefitRedemption, redemption_id)
    redemption.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.flush()

    with pytest.raises(ValidationError):
        RewardsService(db_session).mark_redemption_used(seeded_user.id, redemption_id)


def test_mark_redemption_used_rejects_someone_elses_redemption(db_session, seeded_user):
    other_user = UserService(db_session).create_user(
        UserCreate(email="other-voucher-user@example.com", password="Sup3rSecret!", first_name="Other", last_name="User")
    )
    card = _regular_card(db_session, seeded_user.id)
    redemption_id = _redeem_a_benefit(db_session, seeded_user.id, card.id)

    with pytest.raises(NotFoundError):
        RewardsService(db_session).mark_redemption_used(other_user.id, redemption_id)


def test_mark_redemption_used_rejects_unknown_redemption(db_session, seeded_user):
    with pytest.raises(NotFoundError):
        RewardsService(db_session).mark_redemption_used(seeded_user.id, uuid.uuid4())
