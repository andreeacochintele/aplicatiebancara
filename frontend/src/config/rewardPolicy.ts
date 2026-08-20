import type { Card, CardTier } from "../types";

/**
 * THE single source of truth for card-tier reward numbers — CardsPage.tsx
 * and RewardsPage.tsx both import from here instead of each hardcoding
 * their own copy (they used to disagree: CardsPage had 1x/1.5x/2x with
 * partner-cashback callouts, RewardsPage independently had 1x/2x/3x).
 * These are CardsPage's original numbers, kept as canonical since that's
 * where they were first established. The real points are always computed
 * server-side (CARD_TIER_POINT_MULTIPLIER in backend/app/merchants/service.py,
 * kept in sync with these same values by hand) — this is display-only.
 */
export const CARD_TIER_POINTS_PER_RON: Record<CardTier, number> = {
  REGULAR: 1,
  GOLD: 1.5,
  PLATINUM: 2,
};

// Card-tier cashback: a general perk of the card, applied at any verified
// partner regardless of whether that merchant has its own active offer.
// Stacks with (doesn't replace) the merchant's own offer percent. Must
// match backend/app/merchants/service.py's CARD_TIER_CASHBACK_PERCENT.
export const CARD_TIER_CASHBACK_PERCENT: Record<CardTier, number> = {
  REGULAR: 0,
  GOLD: 2,
  PLATINUM: 4,
};

// 1 RON = 20 points. Must match backend's POINT_VALUE_IN_RON — used both to
// show a balance's RON-equivalent and to convert cashback into bonus points.
export const POINT_VALUE_IN_RON = 0.05;

const CARD_TIER_EXTRA_PERKS: Record<CardTier, string[]> = {
  REGULAR: ["Standard card controls", "Basic spending notifications"],
  GOLD: ["2% tier cashback at partners", "Priority card support", "Higher daily card limits"],
  PLATINUM: ["4% tier cashback at partners", "Travel insurance", "Airport lounge access"],
};

export function pointsPerRonForCard(card: Pick<Card, "tier">): number {
  return card.tier ? CARD_TIER_POINTS_PER_RON[card.tier] : 1;
}

export function pointsPerRonLabel(card: Pick<Card, "tier">): string {
  const rate = pointsPerRonForCard(card);
  return `${rate} pt${rate === 1 ? "" : "s"} / RON`;
}

export function cardTierCashbackPercent(card: Pick<Card, "tier">): number {
  return card.tier ? CARD_TIER_CASHBACK_PERCENT[card.tier] : 0;
}

export function pointsToRon(points: number): number {
  return Math.round(points * POINT_VALUE_IN_RON);
}

/** "1 pt/RON · 6% cashback to wallet (4% tier + 2% partner)" — points and
 * cashback are independent (cashback never adds points, it's money credited
 * back to the wallet that paid), so this is deliberately a "·" separator,
 * not "+", for a card paying at a specific merchant. */
export function combinedRateLabel(card: Pick<Card, "tier">, partnerCashbackPercent: number): string {
  const tierCashback = cardTierCashbackPercent(card);
  const total = tierCashback + partnerCashbackPercent;
  const base = pointsPerRonLabel(card);
  if (total <= 0) return base;
  return `${base} · ${total}% cashback to wallet (${tierCashback}% tier + ${partnerCashbackPercent}% partner)`;
}

/** "1.5x reward points" etc., always derived from CARD_TIER_POINTS_PER_RON
 * rather than written out separately, so the headline number in this bullet
 * list can never drift from the number shown elsewhere. This is now also
 * THE list of a card tier's full benefits (not just the point rate) — used
 * both on CardsPage's tier panel and on RewardsPage, so there's one place
 * that knows what a Gold or Platinum card actually comes with. */
export function cardTierRewardBullets(tier: CardTier): string[] {
  const rate = CARD_TIER_POINTS_PER_RON[tier];
  return [`${rate}x reward points`, ...CARD_TIER_EXTRA_PERKS[tier]];
}

const TIER_RANK: Record<CardTier, number> = { REGULAR: 0, GOLD: 1, PLATINUM: 2 };

export function bestOwnedCardTier(cards: Card[]): CardTier | null {
  const highest = cards
    .map((card) => card.tier)
    .filter((tier): tier is CardTier => tier !== null)
    .sort((a, b) => TIER_RANK[b] - TIER_RANK[a])[0];
  return highest ?? null;
}
