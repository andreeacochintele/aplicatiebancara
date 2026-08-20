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

// Partner-cashback percentage is descriptive copy only (like the rest of
// this list) — it isn't a real, computed bonus on top of a merchant's own
// CashbackOffer; there's no backend field for "card tier stacks with
// merchant cashback".
const CARD_TIER_EXTRA_PERKS: Record<CardTier, string[]> = {
  REGULAR: ["Standard card controls", "Basic spending notifications"],
  GOLD: ["2% partner cashback", "Priority card support", "Higher daily card limits"],
  PLATINUM: ["4% partner cashback", "Travel insurance", "Airport lounge access"],
};

export function pointsPerRonForCard(card: Pick<Card, "tier">): number {
  return card.tier ? CARD_TIER_POINTS_PER_RON[card.tier] : 1;
}

export function pointsPerRonLabel(card: Pick<Card, "tier">): string {
  const rate = pointsPerRonForCard(card);
  return `${rate} pt${rate === 1 ? "" : "s"} / RON`;
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
