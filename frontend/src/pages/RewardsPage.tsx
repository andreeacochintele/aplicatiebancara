import { CreditCard, Gift, ShieldCheck, Sparkles, Store, Trophy, Users, X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import { bestCardTierBenefits, pointsPerRonForCard, pointsPerRonLabel } from "../config/rewardPolicy";
import { useAuth } from "../hooks/useAuth";
import type { Card, Merchant, PurchaseResult, RewardAccount, RewardBenefit, RewardTier } from "../types";

function formatCardLabel(card: Card): string {
  const tier = card.tier ? card.tier[0] + card.tier.slice(1).toLowerCase() : "One-time";
  return `${tier} ${card.type[0]}${card.type.slice(1).toLowerCase()} •••• ${card.last_four}`;
}

function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function ConfirmModal({
  title,
  onCancel,
  onConfirm,
  confirmLabel,
  busy,
  children,
}: {
  title: string;
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel: string;
  busy: boolean;
  children: ReactNode;
}) {
  return (
    <div
      role="presentation"
      onClick={onCancel}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15, 17, 25, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
        padding: "1rem",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="tile"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: "380px", width: "100%" }}
      >
        <div className="tile__header">
          <span className="eyebrow">{title}</span>
          <button
            type="button"
            className="button--ghost card-panel__icon-action"
            onClick={onCancel}
            aria-label="Close"
            style={{ marginLeft: "auto" }}
          >
            <X size={15} strokeWidth={2.2} />
          </button>
        </div>
        {children}
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", justifyContent: "flex-end" }}>
          <button type="button" className="button--ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
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
  const [newlyEarned, setNewlyEarned] = useState<PurchaseResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [confirmBenefit, setConfirmBenefit] = useState<RewardBenefit | null>(null);
  const [selectedMerchant, setSelectedMerchant] = useState<Merchant | null>(null);
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [showFullHistory, setShowFullHistory] = useState(false);

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

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 3200);
    return () => clearTimeout(id);
  }, [toast]);

  useEffect(() => {
    if (!confirmBenefit && !selectedMerchant) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setConfirmBenefit(null);
        setSelectedMerchant(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [confirmBenefit, selectedMerchant]);

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

  async function confirmRedeemBenefit() {
    if (!accessToken || !confirmBenefit) return;
    const benefit = confirmBenefit;
    setError(null);
    setBusy(true);
    try {
      const updated = await apiRequest<RewardAccount>(`/rewards/benefits/${benefit.id}/redeem`, {
        method: "POST",
        token: accessToken,
      });
      setRewards(updated);
      loadBenefits();
      setConfirmBenefit(null);
      setToast(`Redeemed "${benefit.name}" for ${benefit.points_cost ?? 0} points.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Redeem failed");
      setConfirmBenefit(null);
    } finally {
      setBusy(false);
    }
  }

  function inviteFriends() {
    // No referral system on the backend yet — kept as a clearly-labeled mock
    // rather than a fabricated points reward, per the same "informational
    // only" pattern already used for cashback amounts.
    setToast("Referral link copied — demo only, not wired to a real invite flow yet.");
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
  const cardBenefits = bestCardTierBenefits(cards);
  const categories = ["All", ...Array.from(new Set(merchants.map((m) => m.category)))];
  const visibleMerchants = categoryFilter === "All" ? merchants : merchants.filter((m) => m.category === categoryFilter);
  const history = rewards ? (showFullHistory ? rewards.transactions : rewards.transactions.slice(0, 5)) : [];

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* 1. Rewards balance hero */}
      <div className="tile" style={{ background: "var(--aurora-gradient, #5b5fef)", color: "#fff", border: "none" }}>
        <div className="eyebrow" style={{ color: "rgba(255,255,255,0.75)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <Sparkles size={14} strokeWidth={2.2} />
          Your balance
        </div>
        <div className="balance-hero__amount" style={{ color: "#fff" }}>
          {rewards ? rewards.points_balance : "—"} <span style={{ fontSize: "1.1rem", fontWeight: 600 }}>pts</span>
        </div>
        {rewards && (
          <div style={{ color: "rgba(255,255,255,0.75)", fontSize: "0.85rem" }}>
            ≈ {rewards.points_balance} RON value · {rewards.tier.name}
          </div>
        )}
        <div style={{ marginTop: "1rem", display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
          <button type="button" onClick={() => scrollToId("rewards-pay")} style={{ background: "#fff", color: "#4548c9", border: "none" }}>
            Earn points
          </button>
          <button
            type="button"
            onClick={() => scrollToId("rewards-catalog")}
            style={{ background: "rgba(255,255,255,0.16)", color: "#fff", border: "1px solid rgba(255,255,255,0.4)" }}
          >
            Redeem points
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ flex: "2 1 560px", display: "flex", flexDirection: "column", gap: "1.25rem", minWidth: 0 }}>
          {/* 2. Your cards & rewards */}
          <div className="tile">
            <div className="tile__header">
              <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <CreditCard size={14} strokeWidth={2.2} />
                Your cards & rewards
              </span>
            </div>
            <p className="eyebrow" style={{ marginTop: "-0.4rem", marginBottom: "0.75rem" }}>
              Card tier sets how many points you earn per RON, and a Gold or Platinum card also grants you at least
              Premium or Metal reward tier right away — see below.
            </p>
            {cards.length > 0 ? (
              <div className="card-tier-grid">
                {cards.map((card) => (
                  <article
                    className={`card-tier card-tier--${(card.tier ?? "regular").toLowerCase()}`}
                    key={card.id}
                  >
                    <div className="card-tier__header">
                      <span className="card-tier__name">{formatCardLabel(card)}</span>
                      <span className={card.status === "ACTIVE" ? "tag tag--accent" : "tag tag--neutral"}>
                        {card.status}
                      </span>
                    </div>
                    <p>{pointsPerRonLabel(card)} on card payments</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="eyebrow">No cards yet.</p>
            )}
          </div>

          {/* 3. Rewards catalog / redeem points */}
          <div className="tile" id="rewards-catalog">
            <div className="tile__header">
              <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Gift size={14} strokeWidth={2.2} />
                Redeem your points
              </span>
            </div>
            {benefits.length > 0 ? (
              <div className="card-gallery">
                {benefits.map((benefit) => {
                  const missing =
                    rewards && benefit.points_cost !== null ? benefit.points_cost - rewards.points_balance : null;
                  return (
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
                          <button onClick={() => setConfirmBenefit(benefit)} disabled={busy}>
                            Redeem
                          </button>
                        ) : (
                          <span className="eyebrow">
                            {missing && missing > 0 ? `Need ${missing} more points` : benefit.reason_if_locked}
                          </span>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="eyebrow">No benefits in the catalog yet.</p>
            )}
          </div>

          {/* 4. Progress toward next reward tier */}
          <div className="tile">
            <div className="tile__header">
              <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Trophy size={14} strokeWidth={2.2} />
                Reward tier (Standard / Premium / Metal)
              </span>
            </div>
            <p className="eyebrow" style={{ marginTop: "-0.4rem", marginBottom: "0.75rem" }}>
              Earned through lifetime points — a Gold/Platinum card also grants an immediate floor (at least
              Premium/Metal), so it can start higher than your points alone would.
            </p>
            {rewards && rewards.tier_boosted_by_card && (
              <p className="tag tag--accent" style={{ width: "fit-content", marginBottom: "0.75rem" }}>
                Currently boosted by your card, not (only) by points
              </p>
            )}
            {rewards && rewards.next_tier && (
              <div className="bar-row" style={{ marginBottom: tiers.length > 0 ? "1rem" : 0 }}>
                <span className="bar-row__label">
                  {rewards.tier.name} → {rewards.next_tier.name}
                </span>
                <div className="bar-row__track">
                  <div className="bar-row__fill" style={{ width: `${tierProgressPercent}%` }} />
                </div>
                <span className="bar-row__value">{rewards.points_to_next_tier} points to go</span>
              </div>
            )}
            {tiers.length > 0 ? (
              <div className="card-tier-grid">
                {tiers.map((tier, index) => {
                  const currentIndex = rewards ? tiers.findIndex((t) => t.id === rewards.tier.id) : -1;
                  const isCurrent = rewards?.tier.id === tier.id;
                  const unlocked = currentIndex >= 0 && index <= currentIndex;
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

          {/* 5. Partner merchants and cashback */}
          <div className="tile" id="rewards-pay">
            <div className="tile__header">
              <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Store size={14} strokeWidth={2.2} />
                Partner offers — earn cashback
              </span>
            </div>

            {categories.length > 2 && (
              <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.85rem" }}>
                {categories.map((category) => (
                  <button
                    key={category}
                    type="button"
                    className={category === categoryFilter ? "" : "button--ghost"}
                    onClick={() => setCategoryFilter(category)}
                    style={{ padding: "0.3rem 0.75rem", fontSize: "0.8rem" }}
                  >
                    {category}
                  </button>
                ))}
              </div>
            )}

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
                {selectedCard && (
                  <div className="tag tag--accent" style={{ width: "fit-content" }}>
                    {pointsPerRonLabel(selectedCard)} with this card
                  </div>
                )}
              </article>
            )}

            {visibleMerchants.length > 0 ? (
              <div className="card-gallery">
                {visibleMerchants.map((merchant) => (
                  <article className="card-panel" key={merchant.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedMerchant(merchant)}
                      style={{
                        all: "unset",
                        cursor: "pointer",
                        display: "block",
                        width: "100%",
                      }}
                      aria-label={`View details for ${merchant.name}`}
                    >
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
                      {selectedCard && (
                        <div className="eyebrow" style={{ marginTop: "0.4rem" }}>
                          Earn {pointsPerRonForCard(selectedCard)} pts / RON with your card
                        </div>
                      )}
                    </button>
                    <div className="card-panel__actions">
                      <button onClick={() => handlePay(merchant.id)} disabled={busy || !payCardId}>
                        Pay {payAmount || 0} RON
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="eyebrow">No merchants in this category.</p>
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
            {error && <p role="alert">{error}</p>}
          </div>
        </div>

        {/* Side section */}
        <div style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: "1.25rem", minWidth: "280px" }}>
          {/* 6. Card-dependent benefits */}
          <div className="tile">
            <div className="tile__header">
              <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <ShieldCheck size={14} strokeWidth={2.2} />
                Your benefits
              </span>
            </div>
            {cardBenefits.length > 0 ? (
              <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: "0.6rem" }}>
                {cardBenefits.map((benefit) => (
                  <li key={benefit.label}>
                    <div className="card-panel__value" style={{ fontSize: "0.88rem" }}>
                      {benefit.label}
                    </div>
                    <div className="eyebrow">{benefit.detail}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="eyebrow">Upgrade to a Gold or Platinum card to unlock benefits.</p>
            )}
          </div>

          {/* 7. Referral / earn more points */}
          <div className="tile" style={{ background: "var(--aurora-gradient, #5b5fef)", color: "#fff", border: "none" }}>
            <div className="eyebrow" style={{ color: "rgba(255,255,255,0.75)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <Users size={14} strokeWidth={2.2} />
              Want more points?
            </div>
            <p style={{ margin: "0.5rem 0 0.85rem", fontSize: "0.9rem" }}>
              Invite friends and earn 500 pts for each successful referral.
            </p>
            <button type="button" onClick={inviteFriends} style={{ background: "#fff", color: "#4548c9", border: "none" }}>
              Invite friends
            </button>
          </div>

          {/* 8. Rewards points history */}
          <div className="tile">
            <div className="tile__header">
              <span className="eyebrow">Points history</span>
            </div>
            {history.length > 0 ? (
              <>
                <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: "0.5rem" }}>
                  {history.map((tx) => (
                    <li key={tx.id} style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                      <span style={{ fontSize: "0.85rem" }}>{tx.description ?? tx.type}</span>
                      <span
                        style={{
                          fontWeight: 700,
                          color: tx.points >= 0 ? "var(--aurora-green, #2e9e5b)" : "var(--color-text-muted)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {tx.points > 0 ? `+${tx.points}` : tx.points}
                      </span>
                    </li>
                  ))}
                </ul>
                {rewards && rewards.transactions.length > 5 && (
                  <button
                    type="button"
                    className="button--ghost"
                    onClick={() => setShowFullHistory((current) => !current)}
                    style={{ marginTop: "0.75rem", fontSize: "0.8rem" }}
                  >
                    {showFullHistory ? "Show less" : "View all"}
                  </button>
                )}
              </>
            ) : (
              <p className="eyebrow">No reward activity yet.</p>
            )}
          </div>

          {rewards && rewards.redemptions.length > 0 && (
            <div className="tile">
              <div className="tile__header">
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
            </div>
          )}
        </div>
      </div>

      {confirmBenefit && rewards && (
        <ConfirmModal
          title="Redeem reward?"
          onCancel={() => setConfirmBenefit(null)}
          onConfirm={confirmRedeemBenefit}
          confirmLabel={busy ? "Redeeming…" : `Redeem ${confirmBenefit.points_cost ?? 0} pts`}
          busy={busy}
        >
          <p style={{ fontWeight: 700, fontSize: "1.05rem", margin: "0.5rem 0" }}>{confirmBenefit.name}</p>
          <p className="eyebrow">Cost: {confirmBenefit.points_cost ?? 0} points</p>
          <p className="eyebrow">Current balance: {rewards.points_balance} points</p>
          <p className="eyebrow">
            Balance after redemption: {rewards.points_balance - (confirmBenefit.points_cost ?? 0)} points
          </p>
        </ConfirmModal>
      )}

      {selectedMerchant && (
        <ConfirmModal
          title={selectedMerchant.name}
          onCancel={() => setSelectedMerchant(null)}
          onConfirm={() => {
            setSelectedMerchant(null);
            handlePay(selectedMerchant.id);
          }}
          confirmLabel={`Pay ${payAmount || 0} RON`}
          busy={busy || !payCardId}
        >
          <p className="eyebrow">{selectedMerchant.category}</p>
          {selectedMerchant.active_offer ? (
            <>
              <p style={{ margin: "0.4rem 0" }}>{selectedMerchant.active_offer.cashback_percent}% cashback</p>
              {selectedMerchant.active_offer.minimum_spend && (
                <p className="eyebrow">Minimum spend: {selectedMerchant.active_offer.minimum_spend} RON</p>
              )}
              {selectedMerchant.active_offer.maximum_cashback && (
                <p className="eyebrow">Max cashback: {selectedMerchant.active_offer.maximum_cashback} RON</p>
              )}
            </>
          ) : (
            <p className="eyebrow">No active cashback offer right now.</p>
          )}
          {selectedCard && (
            <p className="eyebrow" style={{ marginTop: "0.5rem" }}>
              With your {formatCardLabel(selectedCard)}: {pointsPerRonForCard(selectedCard)} pts / RON
            </p>
          )}
          {!selectedMerchant.verified && (
            <p className="eyebrow">Not verified yet — purchases here don't earn points.</p>
          )}
        </ConfirmModal>
      )}

      {toast && (
        <div
          role="status"
          className="tile"
          style={{
            position: "fixed",
            bottom: "1.5rem",
            right: "1.5rem",
            zIndex: 60,
            maxWidth: "320px",
            boxShadow: "var(--shadow-md, 0 8px 24px rgba(0,0,0,0.18))",
          }}
        >
          {toast}
        </div>
      )}
    </section>
  );
}
