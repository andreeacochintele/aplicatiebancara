import type { Card, CardTier } from "../types";

/**
 * Centralized, display-only reward policy for card tiers. The real points
 * are always computed server-side (CARD_TIER_POINT_MULTIPLIER in
 * backend/app/merchants/service.py) — this mirrors those same numbers so the
 * UI never has to guess or duplicate the rule in multiple components.
 */
export const CARD_TIER_POINTS_PER_RON: Record<CardTier, number> = {
  REGULAR: 1,
  GOLD: 2,
  PLATINUM: 3,
};

export function pointsPerRonForCard(card: Pick<Card, "tier">): number {
  return card.tier ? CARD_TIER_POINTS_PER_RON[card.tier] : 1;
}

export function pointsPerRonLabel(card: Pick<Card, "tier">): string {
  const rate = pointsPerRonForCard(card);
  return `${rate} pt${rate === 1 ? "" : "s"} / RON`;
}

export interface CardTierBenefit {
  label: string;
  detail: string;
}

/**
 * Descriptive perks unlocked by owning a card of at least this tier — same
 * kind of informational-only content as RewardTier.perks already is
 * (rewards/models.py). Each tier's list is written cumulatively (Platinum
 * already includes Gold's perks at their best value), so picking a user's
 * single highest owned card tier is enough to get the deduplicated "best
 * benefit wins" result the design calls for.
 */
export const CARD_TIER_BENEFITS: Record<CardTier, CardTierBenefit[]> = {
  REGULAR: [],
  GOLD: [
    { label: "Airport lounge access", detail: "1 visit / year" },
    { label: "Purchase protection", detail: "Up to 5,000 RON" },
  ],
  PLATINUM: [
    { label: "Airport lounge access", detail: "2 visits / year" },
    { label: "Travel insurance", detail: "Included" },
    { label: "Purchase protection", detail: "Up to 10,000 RON" },
    { label: "Priority customer support", detail: "Included" },
  ],
};

const TIER_RANK: Record<CardTier, number> = { REGULAR: 0, GOLD: 1, PLATINUM: 2 };

export function bestCardTierBenefits(cards: Card[]): CardTierBenefit[] {
  const highest = cards
    .map((card) => card.tier)
    .filter((tier): tier is CardTier => tier !== null)
    .sort((a, b) => TIER_RANK[b] - TIER_RANK[a])[0];
  return highest ? CARD_TIER_BENEFITS[highest] : [];
}
