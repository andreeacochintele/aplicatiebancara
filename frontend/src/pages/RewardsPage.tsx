import { CreditCard, Gift, Sparkles, Store, Trophy } from "lucide-react";
import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Card, Merchant, PurchaseResult, RewardAccount, RewardBenefit, RewardTier } from "../types";

const CARD_TIER_MULTIPLIER: Record<string, number> = { REGULAR: 1, GOLD: 1.5, PLATINUM: 2 };

function formatCardLabel(card: Card): string {
  const tier = card.tier ? card.tier[0] + card.tier.slice(1).toLowerCase() : "One-time";
  return `${tier} ${card.type[0]}${card.type.slice(1).toLowerCase()} •••• ${card.last_four}`;
}

function pointsMultiplierLabel(card: Card | undefined): string | null {
  const multiplier = card?.tier ? CARD_TIER_MULTIPLIER[card.tier] : undefined;
  if (!multiplier || multiplier <= 1) return null;
  return `This card earns ${multiplier}x points on purchases`;
}

export function RewardsPage() {
  const { accessToken } = useAuth();
  const [rewards, setRewards] = useState<RewardAccount | null>(null);
  const [tiers, setTiers] = useState<RewardTier[]>([]);
  const [benefits, setBenefits] = useState<RewardBenefit[]>([]);
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [payCardId, setPayCardId] = useState("");
  const [payAmount, setPayAmount] = useState("50");
  const [redeemPoints, setRedeemPoints] = useState("100");
  const [newlyEarned, setNewlyEarned] = useState<PurchaseResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function loadRewards() {
    if (!accessToken) return;
    apiRequest<RewardAccount>("/rewards", { token: accessToken }).then(setRewards).catch(() => setRewards(null));
  }

  function loadTiers() {
    if (!accessToken) return;
    apiRequest<RewardTier[]>("/rewards/tiers", { token: accessToken }).then(setTiers).catch(() => setTiers([]));
  }

  function loadBenefits() {
    if (!accessToken) return;
    apiRequest<RewardBenefit[]>("/rewards/benefits", { token: accessToken }).then(setBenefits).catch(() => setBenefits([]));
  }

  function loadMerchants() {
    if (!accessToken) return;
    apiRequest<Merchant[]>("/merchants", { token: accessToken }).then(setMerchants).catch(() => setMerchants([]));
  }

  function loadCards() {
    if (!accessToken) return;
    apiRequest<Card[]>("/cards", { token: accessToken }).then((list) => {
      setCards(list);
      if (list.length > 0) setPayCardId((current) => current || list[0].id);
    }).catch(() => setCards([]));
  }

  function refreshAfterChange() {
    loadRewards();
    loadBenefits();
  }

  function syncRewardsFromTransactions() {
    if (!accessToken) return;
    // Revolut-style: points are earned from the user's own real card payments,
    // matched to a merchant automatically — never a manually typed amount.
    apiRequest<PurchaseResult[]>("/merchants/sync-rewards", { method: "POST", token: accessToken })
      .then((earned) => {
        setNewlyEarned(earned);
        if (earned.length > 0) refreshAfterChange();
      })
      .catch(() => undefined);
  }

  useEffect(loadRewards, [accessToken]);
  useEffect(loadTiers, [accessToken]);
  useEffect(loadBenefits, [accessToken]);
  useEffect(loadMerchants, [accessToken]);
  useEffect(loadCards, [accessToken]);
  useEffect(syncRewardsFromTransactions, [accessToken]);

  async function handlePay(merchantId: string) {
    if (!accessToken || !payCardId) return;
    setError(null);
    setBusy(true);
    try {
      await apiRequest("/transactions/card-payment", {
        method: "POST",
        token: accessToken,
        body: { card_id: payCardId, merchant_id: merchantId, amount: payAmount },
      });
      syncRewardsFromTransactions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Payment failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleRedeem() {
    if (!accessToken) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await apiRequest<RewardAccount>("/rewards/redeem", {
        method: "POST",
        token: accessToken,
        body: { points: Number(redeemPoints) },
      });
      setRewards(updated);
      loadBenefits();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Redeem failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleRedeemBenefit(benefitId: string) {
    if (!accessToken) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await apiRequest<RewardAccount>(`/rewards/benefits/${benefitId}/redeem`, {
        method: "POST",
        token: accessToken,
      });
      setRewards(updated);
      loadBenefits();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Redeem failed");
    } finally {
      setBusy(false);
    }
  }

  const tierProgressPercent =
    rewards && rewards.next_tier
      ? Math.min(
          100,
          ((rewards.lifetime_points_earned - (rewards.tier.min_lifetime_points ?? 0)) /
            (rewards.next_tier.min_lifetime_points - rewards.tier.min_lifetime_points)) *
            100,
        )
      : 100;

  const selectedCard = cards.find((card) => card.id === payCardId);
  const multiplierHint = pointsMultiplierLabel(selectedCard);

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <Sparkles size={14} strokeWidth={2.2} />
          Reward points {rewards && <span className="tag tag--accent">{rewards.tier.name}</span>}
        </div>
        <div className="balance-hero__amount">{rewards ? rewards.points_balance : "—"}</div>
        {rewards && (
          <div className="eyebrow" style={{ marginTop: "0.2rem" }}>
            {rewards.lifetime_points_earned} lifetime points
          </div>
        )}

        {rewards && rewards.next_tier && (
          <div style={{ marginTop: "0.75rem" }}>
            <div className="bar-row">
              <span className="bar-row__label">→ {rewards.next_tier.name}</span>
              <div className="bar-row__track">
                <div className="bar-row__fill" style={{ width: `${tierProgressPercent}%` }} />
              </div>
              <span className="bar-row__value">{rewards.points_to_next_tier} points to go</span>
            </div>
          </div>
        )}

        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem", alignItems: "flex-end" }}>
          <label>
            Redeem points
            <input value={redeemPoints} onChange={(e) => setRedeemPoints(e.target.value)} />
          </label>
          <button onClick={handleRedeem} disabled={busy || !rewards}>
            Redeem
          </button>
        </div>

        {error && <p role="alert">{error}</p>}

        <div className="tile__header" style={{ marginTop: "1rem" }}>
          <span className="eyebrow">History</span>
        </div>
        {rewards && rewards.transactions.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Points</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {rewards.transactions.map((tx) => (
                <tr key={tx.id}>
                  <td>
                    <span className={tx.points >= 0 ? "tag tag--accent" : "tag tag--neutral"}>{tx.type}</span>
                  </td>
                  <td>{tx.points > 0 ? `+${tx.points}` : tx.points}</td>
                  <td>{tx.description ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="eyebrow">No reward activity yet.</p>
        )}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Trophy size={14} strokeWidth={2.2} />
            Tier ladder
          </span>
        </div>
        {tiers.length > 0 ? (
          <div className="card-tier-grid">
            {tiers.map((tier) => {
              const isCurrent = rewards?.tier.id === tier.id;
              const unlocked = rewards ? rewards.lifetime_points_earned >= tier.min_lifetime_points : false;
              return (
                <article className={`card-tier card-tier--${tier.name.toLowerCase()}`} key={tier.id}>
                  <div className="card-tier__header">
                    <span className="card-tier__name">{tier.name}</span>
                    {isCurrent ? (
                      <span className="tag tag--accent">Current</span>
                    ) : unlocked ? (
                      <span className="tag tag--outline">Unlocked</span>
                    ) : (
                      <span className="tag tag--neutral">{tier.min_lifetime_points} pts</span>
                    )}
                  </div>
                  <div className="card-tier__products">
                    {tier.perks.map((perk) => (
                      <span key={perk}>{perk}</span>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="eyebrow">Tiers aren't set up yet.</p>
        )}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Gift size={14} strokeWidth={2.2} />
            Benefits catalog
          </span>
        </div>
        {benefits.length > 0 ? (
          <div className="card-gallery">
            {benefits.map((benefit) => (
              <article className="card-panel" key={benefit.id}>
                <div className="card-panel__meta">
                  <div>
                    <div className="eyebrow">{benefit.category.replace("_", " ")}</div>
                    <div className="card-panel__value">{benefit.name}</div>
                    {benefit.partner_name && (
                      <div className="eyebrow" style={{ marginTop: "0.15rem" }}>
                        {benefit.partner_name}
                        {benefit.min_tier ? ` · ${benefit.min_tier.name}+` : ""}
                      </div>
                    )}
                  </div>
                  <span className="tag tag--outline">
                    {benefit.points_cost !== null ? `${benefit.points_cost} pts` : "Free with tier"}
                  </span>
                </div>
                <div className="card-panel__actions">
                  {benefit.can_redeem ? (
                    <button onClick={() => handleRedeemBenefit(benefit.id)} disabled={busy}>
                      Redeem
                    </button>
                  ) : (
                    <span className="eyebrow">{benefit.reason_if_locked}</span>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="eyebrow">No benefits in the catalog yet.</p>
        )}

        {rewards && rewards.redemptions.length > 0 && (
          <>
            <div className="tile__header" style={{ marginTop: "1rem" }}>
              <span className="eyebrow">Redeemed</span>
            </div>
            <table>
              <tbody>
                {rewards.redemptions.map((redemption) => (
                  <tr key={redemption.id}>
                    <td>{redemption.benefit_name}</td>
                    <td>{redemption.points_spent} pts</td>
                    <td>{new Date(redemption.redeemed_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Store size={14} strokeWidth={2.2} />
            Merchants & cashback offers
          </span>
        </div>

        {cards.length > 0 && (
          <article className="card-panel" style={{ maxWidth: "420px", marginBottom: "1rem" }}>
            <div className="card-panel__meta">
              <div style={{ flex: 1 }}>
                <div className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <CreditCard size={14} strokeWidth={2.2} />
                  Pay with card
                </div>
                <select
                  value={payCardId}
                  onChange={(e) => setPayCardId(e.target.value)}
                  style={{ marginTop: "0.35rem", width: "100%" }}
                >
                  {cards.map((card) => (
                    <option key={card.id} value={card.id}>
                      {formatCardLabel(card)}
                    </option>
                  ))}
                </select>
              </div>
              <label>
                Amount (RON)
                <input value={payAmount} onChange={(e) => setPayAmount(e.target.value)} style={{ width: "6rem" }} />
              </label>
            </div>
            {multiplierHint && (
              <div className="tag tag--accent" style={{ width: "fit-content" }}>
                {multiplierHint}
              </div>
            )}
          </article>
        )}

        {merchants.length > 0 ? (
          <div className="card-gallery">
            {merchants.map((merchant) => (
              <article className="card-panel" key={merchant.id}>
                <div className="card-panel__meta">
                  <div>
                    <div className="eyebrow">{merchant.category}</div>
                    <div className="card-panel__value">{merchant.name}</div>
                    {!merchant.verified && (
                      <div className="eyebrow" style={{ marginTop: "0.15rem" }}>
                        Not verified — doesn't earn points yet
                      </div>
                    )}
                  </div>
                  {merchant.active_offer ? (
                    <span className="tag tag--accent">{merchant.active_offer.cashback_percent}% cashback</span>
                  ) : (
                    <span className="tag tag--outline">No active offer</span>
                  )}
                </div>
                <div className="card-panel__actions">
                  <button onClick={() => handlePay(merchant.id)} disabled={busy || !payCardId}>
                    Pay {payAmount || 0} RON
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="eyebrow">No merchants yet.</p>
        )}

        {newlyEarned.length > 0 && (
          <div className="eyebrow" style={{ marginTop: "0.75rem" }}>
            {newlyEarned.map((purchase) => (
              <div key={purchase.merchant_id}>
                Earned {purchase.points_earned} points from a real card payment
                {purchase.cashback_percent
                  ? ` · ~${purchase.cashback_amount} ${purchase.currency} cashback (informational, not credited to a wallet yet)`
                  : ""}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
