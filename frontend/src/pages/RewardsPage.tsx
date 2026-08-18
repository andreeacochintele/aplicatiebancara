import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Merchant, PurchaseResult, RewardAccount } from "../types";

export function RewardsPage() {
  const { accessToken } = useAuth();
  const [rewards, setRewards] = useState<RewardAccount | null>(null);
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [redeemPoints, setRedeemPoints] = useState("100");
  const [purchaseMerchantId, setPurchaseMerchantId] = useState("");
  const [purchaseAmount, setPurchaseAmount] = useState("100");
  const [lastPurchase, setLastPurchase] = useState<PurchaseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function loadRewards() {
    if (!accessToken) return;
    apiRequest<RewardAccount>("/rewards", { token: accessToken }).then(setRewards).catch(() => setRewards(null));
  }

  function loadMerchants() {
    if (!accessToken) return;
    apiRequest<Merchant[]>("/merchants", { token: accessToken }).then((list) => {
      setMerchants(list);
      if (list.length > 0) setPurchaseMerchantId((current) => current || list[0].id);
    }).catch(() => setMerchants([]));
  }

  useEffect(loadRewards, [accessToken]);
  useEffect(loadMerchants, [accessToken]);

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
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Redeem failed");
    } finally {
      setBusy(false);
    }
  }

  async function handlePurchase() {
    if (!accessToken || !purchaseMerchantId) return;
    setError(null);
    setBusy(true);
    try {
      const result = await apiRequest<PurchaseResult>(`/merchants/${purchaseMerchantId}/purchases`, {
        method: "POST",
        token: accessToken,
        body: { amount: purchaseAmount, currency: "RON" },
      });
      setLastPurchase(result);
      loadRewards();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Purchase failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="eyebrow">Reward points</div>
        <div className="balance-hero__amount">{rewards ? rewards.points_balance : "—"}</div>

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

        {merchants.length > 0 && (
          <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", alignItems: "flex-end" }}>
            <label>
              Merchant
              <select value={purchaseMerchantId} onChange={(e) => setPurchaseMerchantId(e.target.value)}>
                {merchants.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Amount (RON)
              <input value={purchaseAmount} onChange={(e) => setPurchaseAmount(e.target.value)} />
            </label>
            <button onClick={handlePurchase} disabled={busy}>
              Record purchase
            </button>
          </div>
        )}

        {lastPurchase && (
          <div className="eyebrow" style={{ marginTop: "0.75rem" }}>
            Earned {lastPurchase.points_earned} points
            {lastPurchase.cashback_percent
              ? ` · ~${lastPurchase.cashback_amount} ${lastPurchase.currency} cashback (informational, not credited to a wallet yet)`
              : ""}
          </div>
        )}
      </div>
    </section>
  );
}
