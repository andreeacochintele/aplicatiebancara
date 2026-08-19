import uuid

import pytest

from app.cards.models import CardTier
from app.cards.schemas import CardCreate
from app.cards.service import CardService
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.rewards.models import BenefitCategory, RewardBenefit
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
    assert account.tier.name == "STANDARD"
    assert account.transactions == []


def test_platinum_card_grants_metal_tier_floor_even_with_zero_points(db_session, seeded_user):
    CardService(db_session).create_card(seeded_user.id, CardCreate(tier=CardTier.PLATINUM))

    account = RewardsService(db_session).get_account(seeded_user.id)

    assert account.lifetime_points_earned == 0
    assert account.tier.name == "METAL"
    assert account.tier_boosted_by_card is True
    assert account.next_tier is None


def test_gold_card_grants_premium_floor(db_session, seeded_user):
    CardService(db_session).create_card(seeded_user.id, CardCreate(tier=CardTier.GOLD))

    account = RewardsService(db_session).get_account(seeded_user.id)

    assert account.tier.name == "PREMIUM"
    assert account.tier_boosted_by_card is True


def test_regular_card_does_not_boost_tier(db_session, seeded_user):
    CardService(db_session).create_card(seeded_user.id, CardCreate(tier=CardTier.REGULAR))

    account = RewardsService(db_session).get_account(seeded_user.id)

    assert account.tier.name == "STANDARD"
    assert account.tier_boosted_by_card is False


def test_points_earned_tier_wins_when_higher_than_card_floor(db_session, seeded_user):
    service = RewardsService(db_session)
    CardService(db_session).create_card(seeded_user.id, CardCreate(tier=CardTier.GOLD))  # floor: PREMIUM
    service.earn_points(seeded_user.id, 9000, description="test")  # well past METAL's 8000 threshold

    account = service.get_account(seeded_user.id)

    assert account.tier.name == "METAL"
    assert account.tier_boosted_by_card is False  # points alone already got here


def test_list_tiers_returns_the_full_ladder_in_order(db_session, seeded_reward_tiers):
    tiers = RewardsService(db_session).list_tiers()

    assert [tier.name for tier in tiers] == ["STANDARD", "PREMIUM", "METAL"]
    assert tiers[0].min_lifetime_points == 0
    assert tiers[1].min_lifetime_points > tiers[0].min_lifetime_points
    assert tiers[2].min_lifetime_points > tiers[1].min_lifetime_points


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


def test_tier_upgrades_from_lifetime_points_and_survives_redemption(db_session, seeded_user):
    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 2500)

    account = service.get_account(seeded_user.id)
    assert account.tier.name == "PREMIUM"
    assert account.next_tier.name == "METAL"
    assert account.points_to_next_tier == 8000 - 2500

    after_redeem = service.redeem_points(seeded_user.id, 1000)
    assert after_redeem.tier.name == "PREMIUM"  # spending points doesn't demote the tier


def test_list_benefits_locks_by_tier_and_points(db_session, seeded_user, seeded_reward_tiers):
    lounge = RewardBenefit(
        name="Priority Pass Lounge Access",
        category=BenefitCategory.LOUNGE_ACCESS,
        description="One lounge visit",
        points_cost=1500,
        min_tier_id=seeded_reward_tiers["PREMIUM"].id,
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
    assert "PREMIUM" in lounge_public.reason_if_locked
    assert discount_public.can_redeem is False
    assert discount_public.reason_if_locked == "Not enough points"


def test_redeem_benefit_spends_points_and_records_redemption(db_session, seeded_user, seeded_reward_tiers):
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

    account = service.redeem_benefit(seeded_user.id, discount.id)

    assert account.points_balance == 200
    assert len(account.redemptions) == 1
    assert account.redemptions[0].benefit_name == "10% off at eMAG"
    assert account.redemptions[0].points_spent == 300


def test_redeem_benefit_rejects_below_required_tier(db_session, seeded_user, seeded_reward_tiers):
    lounge = RewardBenefit(
        name="Priority Pass Lounge Access",
        category=BenefitCategory.LOUNGE_ACCESS,
        description="One lounge visit",
        points_cost=1500,
        min_tier_id=seeded_reward_tiers["PREMIUM"].id,
        partner_name="Priority Pass",
    )
    db_session.add(lounge)
    db_session.flush()

    service = RewardsService(db_session)
    service.earn_points(seeded_user.id, 1000)  # below PREMIUM's 2000-point threshold, still STANDARD

    with pytest.raises(ValidationError):
        service.redeem_benefit(seeded_user.id, lounge.id)


def test_redeem_unknown_benefit_raises_not_found(db_session, seeded_user):
    with pytest.raises(NotFoundError):
        RewardsService(db_session).redeem_benefit(seeded_user.id, uuid.uuid4())
