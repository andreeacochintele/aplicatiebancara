import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Merchant, PurchaseResult, RewardAccount, RewardBenefit } from "../types";

export function RewardsPage() {
  const { accessToken } = useAuth();
  const [rewards, setRewards] = useState<RewardAccount | null>(null);
  const [benefits, setBenefits] = useState<RewardBenefit[]>([]);
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [redeemPoints, setRedeemPoints] = useState("100");
  const [newlyEarned, setNewlyEarned] = useState<PurchaseResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function loadRewards() {
    if (!accessToken) return;
    apiRequest<RewardAccount>("/rewards", { token: accessToken }).then(setRewards).catch(() => setRewards(null));
  }

  function loadBenefits() {
    if (!accessToken) return;
    apiRequest<RewardBenefit[]>("/rewards/benefits", { token: accessToken }).then(setBenefits).catch(() => setBenefits([]));
  }

  function loadMerchants() {
    if (!accessToken) return;
    apiRequest<Merchant[]>("/merchants", { token: accessToken }).then(setMerchants).catch(() => setMerchants([]));
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
  useEffect(loadBenefits, [accessToken]);
  useEffect(loadMerchants, [accessToken]);
  useEffect(syncRewardsFromTransactions, [accessToken]);

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

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="eyebrow">
          Reward points {rewards && <span className="tag tag--accent">{rewards.tier.name}</span>}
        </div>
        <div className="balance-hero__amount">{rewards ? rewards.points_balance : "—"}</div>
        {rewards && (
          <div className="eyebrow" style={{ marginTop: "0.2rem" }}>
            {rewards.lifetime_points_earned} lifetime points
          </div>
        )}

        {rewards && (
          <div style={{ marginTop: "0.75rem" }}>
            <div className="eyebrow">Your {rewards.tier.name} perks</div>
            <ul style={{ margin: "0.35rem 0 0", paddingLeft: "1.1rem" }}>
              {rewards.tier.perks.map((perk) => (
                <li key={perk}>{perk}</li>
              ))}
            </ul>
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
                    <span className="tag tag--neutral">{tx.type}</span>
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
          <span className="eyebrow">Benefits catalog</span>
        </div>
        {benefits.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Benefit</th>
                <th>Category</th>
                <th>Cost</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {benefits.map((benefit) => (
                <tr key={benefit.id}>
                  <td>
                    {benefit.name}
                    {benefit.partner_name && (
                      <div className="eyebrow" style={{ marginTop: "0.1rem" }}>
                        {benefit.partner_name}
                        {benefit.min_tier ? ` · ${benefit.min_tier.name}+` : ""}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className="tag tag--neutral">{benefit.category.replace("_", " ")}</span>
                  </td>
                  <td>{benefit.points_cost !== null ? `${benefit.points_cost} pts` : "Free with tier"}</td>
                  <td>
                    {benefit.can_redeem ? (
                      <button onClick={() => handleRedeemBenefit(benefit.id)} disabled={busy}>
                        Redeem
                      </button>
                    ) : (
                      <span className="eyebrow">{benefit.reason_if_locked}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
          <span className="eyebrow">Merchants & cashback offers</span>
        </div>
        {merchants.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Merchant</th>
                <th>Category</th>
                <th>Cashback</th>
              </tr>
            </thead>
            <tbody>
              {merchants.map((merchant) => (
                <tr key={merchant.id}>
                  <td>{merchant.name}</td>
                  <td>{merchant.category}</td>
                  <td>
                    {merchant.active_offer ? (
                      <span className="tag tag--accent">{merchant.active_offer.cashback_percent}%</span>
                    ) : (
                      <span className="eyebrow">No active offer</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
