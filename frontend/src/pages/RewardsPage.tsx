import { CreditCard, Gift, ShieldCheck, Sparkles, Store, Users, X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/apiClient";
import {
  bestOwnedCardTier,
  cardTierCashbackPercent,
  cardTierRewardBullets,
  combinedRateLabel,
  pointsPerRonLabel,
  pointsToRon,
} from "../config/rewardPolicy";
import { useAuth } from "../hooks/useAuth";
import type {
  Card,
  CardPaymentPreferences,
  CardTier,
  Merchant,
  PurchaseResult,
  RewardAccount,
  RewardBenefit,
  Wallet,
} from "../types";

function formatCardTierLabel(tier: CardTier | null): string {
  return tier ? tier[0] + tier.slice(1).toLowerCase() : "One-time";
}

function formatCardTypeLabel(type: Card["type"]): string {
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatCardLabel(card: Card): string {
  return `${formatCardTierLabel(card.tier)} ${card.type[0]}${card.type.slice(1).toLowerCase()} •••• ${card.last_four}`;
}

function cardToneClass(card: Card): string {
  if (card.type === "ONE_TIME") return "bank-card bank-card--one-time";
  const tier = (card.tier ?? "REGULAR").toLowerCase();
  return `bank-card bank-card--${card.type.toLowerCase()} bank-card--${tier}`;
}

function cardStatusClass(status: Card["status"]): string {
  if (status === "ACTIVE") return "tag tag--accent";
  if (status === "FROZEN") return "tag tag--warning";
  return "tag tag--neutral";
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
  const { accessToken, user } = useAuth();
  const cardholderName = user ? `${user.first_name} ${user.last_name}`.trim() : "Card holder";
  const [rewards, setRewards] = useState<RewardAccount | null>(null);
  const [benefits, setBenefits] = useState<RewardBenefit[]>([]);
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [preferencesByCard, setPreferencesByCard] = useState<Record<string, CardPaymentPreferences>>({});
  const [payCardId, setPayCardId] = useState("");
  const [payAmount, setPayAmount] = useState("50");
  const [newlyEarned, setNewlyEarned] = useState<PurchaseResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [confirmBenefit, setConfirmBenefit] = useState<RewardBenefit | null>(null);
  const [redeemCardId, setRedeemCardId] = useState("");
  const [selectedMerchant, setSelectedMerchant] = useState<Merchant | null>(null);
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [showFullHistory, setShowFullHistory] = useState(false);
  const [areCardsExpanded, setAreCardsExpanded] = useState(true);
  const [areVouchersExpanded, setAreVouchersExpanded] = useState(false);
  const [isInviteExpanded, setIsInviteExpanded] = useState(false);
  const [codeReveal, setCodeReveal] = useState<{ title: string; subtitle: string; code: string } | null>(null);
  const [copyFeedback, setCopyFeedback] = useState(false);
  const [inviteCopyFeedback, setInviteCopyFeedback] = useState(false);
  const [markingUsedId, setMarkingUsedId] = useState<string | null>(null);

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

  function loadCards() {
    if (!accessToken) return;
    apiRequest<Card[]>("/cards", { token: accessToken }).then((list) => {
      setCards(list);
      if (list.length > 0) setPayCardId((current) => current || list[0].id);
      // Fetched per-card so the pay form can show which wallet/currency a
      // card will actually charge — preferred_wallet_id (set on the Cards
      // page) silently overrides default_wallet_id, which was the source
      // of the "money left the wrong wallet" surprise.
      Promise.all(
        list.map((card) =>
          apiRequest<CardPaymentPreferences>(`/cards/${card.id}/payment-preferences`, { token: accessToken }).then(
            (prefs) => [card.id, prefs] as const,
          ),
        ),
      )
        .then((entries) => setPreferencesByCard(Object.fromEntries(entries)))
        .catch(() => undefined);
    }).catch(() => setCards([]));
  }

  function loadWallets() {
    if (!accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then(setWallets).catch(() => setWallets([]));
  }

  function effectiveWallet(card: Card | undefined): Wallet | undefined {
    if (!card) return undefined;
    const walletId = preferencesByCard[card.id]?.preferred_wallet_id ?? card.default_wallet_id;
    return wallets.find((w) => w.id === walletId);
  }

  function refreshAfterChange() {
    loadRewards();
    loadBenefits();
  }

  // Revolut-style: points are earned from the user's own real card payments,
  // matched to a merchant automatically — never a manually typed amount.
  async function syncRewards(): Promise<PurchaseResult[]> {
    if (!accessToken) return [];
    try {
      const earned = await apiRequest<PurchaseResult[]>("/merchants/sync-rewards", {
        method: "POST",
        token: accessToken,
      });
      setNewlyEarned(earned);
      if (earned.length > 0) refreshAfterChange();
      return earned;
    } catch {
      return [];
    }
  }

  function syncRewardsFromTransactions() {
    syncRewards();
  }

  useEffect(loadRewards, [accessToken]);
  useEffect(loadBenefits, [accessToken]);
  useEffect(loadMerchants, [accessToken]);
  useEffect(loadCards, [accessToken]);
  useEffect(loadWallets, [accessToken]);
  useEffect(syncRewardsFromTransactions, [accessToken]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 3200);
    return () => clearTimeout(id);
  }, [toast]);

  useEffect(() => {
    if (!confirmBenefit && !selectedMerchant && !codeReveal) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setConfirmBenefit(null);
        setSelectedMerchant(null);
        setCodeReveal(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [confirmBenefit, selectedMerchant, codeReveal]);

  async function handlePay(merchant: Merchant) {
    if (!accessToken || !payCardId) return;
    setError(null);
    setBusy(true);
    try {
      const transaction = await apiRequest<{ id: string }>("/transactions/card-payment", {
        method: "POST",
        token: accessToken,
        body: { card_id: payCardId, merchant_id: merchant.id, amount: payAmount },
      });
      const receipt = `Receipt #${transaction.id.slice(0, 8).toUpperCase()}`;
      const earned = await syncRewards();
      const match = earned.find((p) => p.merchant_id === merchant.id);
      if (match) {
        // Partner Offers is a pure earning flow (simulated real purchase) —
        // informational confirmation only, no code/voucher. Redeem codes
        // belong to the "Redeem your points" catalog below instead. Points
        // and cashback are independent: cashback is real money credited
        // back to the wallet, never extra points, so they're shown as two
        // separate numbers rather than a combined total.
        const cashback = Number(match.cashback_amount) > 0 ? ` · ${match.cashback_amount} ${match.currency} cashback credited to your wallet` : "";
        setToast(
          `Payment confirmed — ${receipt} · Earned ${match.points_earned} points${cashback}`,
        );
      } else if (!merchant.verified) {
        setToast(`Payment confirmed — ${receipt} · 0 points earned (merchant not verified yet)`);
      } else {
        setToast(`Payment confirmed — ${receipt}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Payment failed");
    } finally {
      setBusy(false);
    }
  }

  async function confirmRedeemBenefit() {
    if (!accessToken || !confirmBenefit || !redeemCardId) return;
    const benefit = confirmBenefit;
    setError(null);
    setBusy(true);
    try {
      const updated = await apiRequest<RewardAccount>(`/rewards/benefits/${benefit.id}/redeem`, {
        method: "POST",
        token: accessToken,
        body: { card_id: redeemCardId },
      });
      setRewards(updated);
      loadBenefits();
      setConfirmBenefit(null);
      const redemption = updated.redemptions[0];
      if (redemption?.redemption_code) {
        const validUntil = redemption.expires_at ? new Date(redemption.expires_at).toLocaleDateString() : null;
        setCodeReveal({
          title: `Redeemed "${benefit.name}"`,
          subtitle:
            `${benefit.points_cost ?? 0} points spent — show this code at ${benefit.partner_name ?? "the partner"} to claim it.` +
            (validUntil ? ` Valid until ${validUntil}, also saved under My vouchers below.` : ""),
          code: redemption.redemption_code,
        });
      } else {
        setToast(`Redeemed "${benefit.name}" for ${benefit.points_cost ?? 0} points.`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Redeem failed");
      setConfirmBenefit(null);
    } finally {
      setBusy(false);
    }
  }

  async function markVoucherUsed(redemptionId: string) {
    if (!accessToken) return;
    setMarkingUsedId(redemptionId);
    setError(null);
    try {
      const updated = await apiRequest<RewardAccount>(`/rewards/redemptions/${redemptionId}/use`, {
        method: "POST",
        token: accessToken,
      });
      setRewards(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not mark voucher as used");
    } finally {
      setMarkingUsedId(null);
    }
  }

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 1800);
    } catch {
      // Clipboard blocked (e.g. insecure context) — the code stays visible
      // on screen and permanently in Points history / My vouchers either way.
    }
  }

  // The code itself is real and persistent (RewardAccount.referral_code,
  // generated once server-side and reused). Only what happens with it
  // afterwards — validating a friend signed up, crediting 500 pts — is
  // still mock, per the same "informational only" pattern already used
  // for cashback amounts.
  const inviteLink = rewards?.referral_code ? `${window.location.origin}/invite/${rewards.referral_code}` : "";

  async function copyInviteLink() {
    if (!inviteLink) return;
    try {
      await navigator.clipboard.writeText(inviteLink);
      setInviteCopyFeedback(true);
      setTimeout(() => setInviteCopyFeedback(false), 1800);
    } catch {
      // Clipboard blocked — the link stays visible in the panel either way.
    }
  }

  const selectedCard = cards.find((card) => card.id === payCardId);
  const bestTier = bestOwnedCardTier(cards);
  const cardBenefits = bestTier ? cardTierRewardBullets(bestTier) : [];
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
            ≈ {pointsToRon(rewards.points_balance)} RON value · {rewards.lifetime_points_earned} lifetime points
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
              <button
                type="button"
                className="button--ghost"
                onClick={() => setAreCardsExpanded((current) => !current)}
                aria-expanded={areCardsExpanded}
              >
                {areCardsExpanded ? "Retract" : "Expand"}
              </button>
            </div>
            <p className="eyebrow" style={{ marginTop: "-0.4rem", marginBottom: "0.75rem" }}>
              Card tier sets how many points you earn per RON, and which rewards in the catalog below you can redeem
              — some require owning at least a Gold or Platinum card.
            </p>
            {areCardsExpanded && cards.length > 0 ? (
              <div className="card-gallery">
                {cards.map((card) => (
                  <article className="card-panel" key={card.id}>
                    <div className={cardToneClass(card)}>
                      <div className="bank-card__top">
                        <div className="bank-card__identity">
                          <span className="bank-card__brand">AURORA</span>
                          <span className="bank-card__product">
                            {card.tier
                              ? `${formatCardTierLabel(card.tier)} ${formatCardTypeLabel(card.type)}`
                              : "One-time"}
                          </span>
                        </div>
                        <span className={cardStatusClass(card.status)}>{card.status}</span>
                      </div>
                      <div className="bank-card__middle">
                        <div className="bank-card__chip" aria-hidden="true" />
                        <span className="bank-card__mark">{card.type === "ONE_TIME" ? "1x" : card.type}</span>
                      </div>
                      <div className="bank-card__number-row">
                        <div className="bank-card__number">{card.masked_pan}</div>
                      </div>
                      <div className="bank-card__holder">
                        <span>Card holder</span>
                        <strong>{cardholderName}</strong>
                      </div>
                      <div className="bank-card__footer">
                        <span>
                          {card.tier
                            ? `${formatCardTierLabel(card.tier)} ${formatCardTypeLabel(card.type)}`
                            : formatCardTypeLabel(card.type)}
                        </span>
                        <span className="bank-card__security">
                          <span>
                            EXP {String(card.expiration_month).padStart(2, "0")}/{card.expiration_year}
                          </span>
                        </span>
                      </div>
                    </div>
                    <div className="card-panel__meta">
                      <div>
                        <div className="eyebrow">This card's perks</div>
                        <ul style={{ margin: "0.3rem 0 0", padding: 0, listStyle: "none", display: "grid", gap: "0.25rem" }}>
                          {cardTierRewardBullets(card.tier ?? "REGULAR").map((perk) => (
                            <li key={perk} className="card-panel__value" style={{ fontSize: "0.85rem" }}>
                              {perk}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : areCardsExpanded ? (
              <p className="eyebrow">No cards yet.</p>
            ) : (
              <p className="eyebrow">
                {cards.length} card{cards.length === 1 ? "" : "s"} — expand to view.
              </p>
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
                              {benefit.min_card_tier ? ` · ${formatCardTierLabel(benefit.min_card_tier)}+ card` : ""}
                            </div>
                          )}
                        </div>
                        <span className="tag tag--outline">
                          {benefit.points_cost !== null ? `${benefit.points_cost} pts` : "Free"}
                        </span>
                      </div>
                      <div className="card-panel__actions">
                        {benefit.can_redeem ? (
                          <button
                            onClick={() => {
                              setConfirmBenefit(benefit);
                              setRedeemCardId(payCardId || cards[0]?.id || "");
                            }}
                            disabled={busy || cards.length === 0}
                          >
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

          {/* 4. Partner merchants and cashback */}
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
              <div
                className="tile"
                style={{
                  maxWidth: "460px",
                  margin: "0 auto 1.25rem",
                  background: "linear-gradient(135deg, rgba(91,95,239,0.09), rgba(255,111,165,0.06))",
                  border: "1px solid rgba(91,95,239,0.2)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.55rem", marginBottom: "0.9rem" }}>
                  <span
                    aria-hidden="true"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: "2rem",
                      height: "2rem",
                      borderRadius: "0.65rem",
                      background: "var(--aurora-gradient, #5b5fef)",
                      color: "#fff",
                      flexShrink: 0,
                    }}
                  >
                    <CreditCard size={15} strokeWidth={2.4} />
                  </span>
                  <span className="eyebrow" style={{ fontSize: "0.85rem" }}>
                    Pay with card
                  </span>
                </div>
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "flex-end" }}>
                  <div style={{ flex: "2 1 220px", minWidth: 0 }}>
                    <label className="eyebrow" style={{ display: "block", marginBottom: "0.3rem" }}>
                      Card
                    </label>
                    <select
                      value={payCardId}
                      onChange={(e) => setPayCardId(e.target.value)}
                      style={{ width: "100%" }}
                    >
                      {cards.map((card) => (
                        <option key={card.id} value={card.id}>
                          {formatCardLabel(card)} — {effectiveWallet(card)?.currency ?? "…"} wallet
                        </option>
                      ))}
                    </select>
                  </div>
                  <div style={{ flex: "1 1 110px" }}>
                    <label className="eyebrow" style={{ display: "block", marginBottom: "0.3rem" }}>
                      Amount ({effectiveWallet(selectedCard)?.currency ?? "RON"})
                    </label>
                    <input
                      value={payAmount}
                      onChange={(e) => setPayAmount(e.target.value)}
                      style={{ width: "100%" }}
                    />
                  </div>
                </div>
                {selectedCard && (
                  <div
                    className="tag tag--accent"
                    style={{
                      width: "fit-content",
                      marginTop: "0.85rem",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.35rem",
                    }}
                  >
                    <Sparkles size={12} strokeWidth={2.4} />
                    {pointsPerRonLabel(selectedCard)}
                    {cardTierCashbackPercent(selectedCard) > 0
                      ? ` · ${cardTierCashbackPercent(selectedCard)}% tier cashback to wallet at partners`
                      : ""}
                  </div>
                )}
                <p className="eyebrow" style={{ marginTop: "0.6rem", marginBottom: 0 }}>
                  Pays from {effectiveWallet(selectedCard)?.currency ?? "unknown"} wallet · pick a merchant below
                </p>
              </div>
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
                          Earn {combinedRateLabel(selectedCard, Number(merchant.active_offer?.cashback_percent ?? 0))}
                        </div>
                      )}
                    </button>
                    <div className="card-panel__actions">
                      <button onClick={() => handlePay(merchant)} disabled={busy || !payCardId}>
                        Pay {payAmount || 0} {effectiveWallet(selectedCard)?.currency ?? "RON"}
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
                    {Number(purchase.cashback_amount) > 0
                      ? ` · ${purchase.cashback_amount} ${purchase.currency} cashback credited to your wallet`
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
          {/* 5. Card-dependent benefits */}
          <div className="tile">
            <div className="tile__header">
              <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <ShieldCheck size={14} strokeWidth={2.2} />
                Your benefits
              </span>
            </div>
            {bestTier && (
              <div className="eyebrow" style={{ marginBottom: "0.5rem" }}>
                From your best card tier: {formatCardTierLabel(bestTier)}
              </div>
            )}
            {cardBenefits.length > 0 ? (
              <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: "0.5rem" }}>
                {cardBenefits.map((benefit) => (
                  <li key={benefit} className="card-panel__value" style={{ fontSize: "0.88rem" }}>
                    {benefit}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="eyebrow">Upgrade to a Gold or Platinum card to unlock benefits.</p>
            )}
          </div>

          {/* 6. Referral / earn more points */}
          <div className="tile" style={{ background: "var(--aurora-gradient, #5b5fef)", color: "#fff", border: "none" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="eyebrow" style={{ color: "rgba(255,255,255,0.75)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Users size={14} strokeWidth={2.2} />
                Want more points?
              </div>
              {isInviteExpanded && (
                <button
                  type="button"
                  className="button--ghost"
                  onClick={() => setIsInviteExpanded(false)}
                  aria-expanded={isInviteExpanded}
                  style={{ color: "#fff", borderColor: "rgba(255,255,255,0.5)" }}
                >
                  Retract
                </button>
              )}
            </div>
            <p style={{ margin: "0.5rem 0 0.85rem", fontSize: "0.9rem" }}>
              Invite friends and earn 500 pts for each successful referral.
            </p>
            {isInviteExpanded ? (
              <div>
                <p style={{ margin: "0 0 0.4rem", fontSize: "0.8rem", opacity: 0.85 }}>Your invite link:</p>
                <div
                  style={{
                    background: "rgba(255,255,255,0.16)",
                    border: "1px dashed rgba(255,255,255,0.5)",
                    borderRadius: "0.6rem",
                    padding: "0.6rem",
                    fontFamily: "monospace",
                    fontSize: "0.8rem",
                    wordBreak: "break-all",
                    marginBottom: "0.75rem",
                  }}
                >
                  {inviteLink}
                </div>
                <button
                  type="button"
                  onClick={copyInviteLink}
                  style={{ background: "#fff", color: "#4548c9", border: "none" }}
                >
                  {inviteCopyFeedback ? "Copied!" : "Copy link"}
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setIsInviteExpanded(true)}
                disabled={!rewards?.referral_code}
                aria-expanded={isInviteExpanded}
                style={{ background: "#fff", color: "#4548c9", border: "none" }}
              >
                Invite friends
              </button>
            )}
          </div>

          {/* 7. Rewards points history */}
          <div className="tile">
            <div className="tile__header">
              <span className="eyebrow">Points history</span>
            </div>
            {history.length > 0 ? (
              <>
                <div style={{ maxHeight: "360px", overflowY: "auto", paddingRight: "0.25rem" }}>
                  <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: "0.5rem" }}>
                    {history.map((tx) => (
                      <li key={tx.id} style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                        <span style={{ fontSize: "0.85rem" }}>
                          {tx.description ?? tx.type}
                          {tx.proof_code && (
                            <div className="eyebrow" style={{ marginTop: "0.1rem" }}>
                              Code: {tx.proof_code}
                            </div>
                          )}
                        </span>
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
                </div>
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
                <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <Gift size={14} strokeWidth={2.2} />
                  My vouchers ({rewards.redemptions.length})
                </span>
                <button
                  type="button"
                  className="button--ghost"
                  onClick={() => setAreVouchersExpanded((current) => !current)}
                  aria-expanded={areVouchersExpanded}
                >
                  {areVouchersExpanded ? "Retract" : "Expand"}
                </button>
              </div>
              {areVouchersExpanded ? (
                <div style={{ maxHeight: "360px", overflowY: "auto", paddingRight: "0.25rem" }}>
                <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: "0.6rem" }}>
                  {rewards.redemptions.map((redemption) => (
                    <li
                      key={redemption.id}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: "0.75rem",
                        padding: "0.6rem 0",
                        borderBottom: "1px solid var(--aurora-border, rgba(0,0,0,0.08))",
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{redemption.benefit_name}</div>
                        {redemption.redemption_code && (
                          <div style={{ fontFamily: "monospace", fontSize: "0.85rem", marginTop: "0.15rem" }}>
                            {redemption.redemption_code}
                          </div>
                        )}
                        <div className="eyebrow" style={{ marginTop: "0.2rem" }}>
                          {redemption.points_spent} pts · redeemed {new Date(redemption.redeemed_at).toLocaleDateString()}
                          {redemption.status === "VALID" && redemption.expires_at
                            ? ` · valid until ${new Date(redemption.expires_at).toLocaleDateString()}`
                            : redemption.status === "USED" && redemption.used_at
                              ? ` · used ${new Date(redemption.used_at).toLocaleDateString()}`
                              : redemption.status === "EXPIRED" && redemption.expires_at
                                ? ` · expired ${new Date(redemption.expires_at).toLocaleDateString()}`
                                : ""}
                        </div>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.35rem" }}>
                        <span
                          className={
                            redemption.status === "VALID"
                              ? "tag tag--accent"
                              : redemption.status === "USED"
                                ? "tag tag--neutral"
                                : "tag tag--warning"
                          }
                        >
                          {redemption.status === "VALID" ? "Valid" : redemption.status === "USED" ? "Used" : "Expired"}
                        </span>
                        {redemption.status === "VALID" && (
                          <button
                            type="button"
                            className="button--ghost"
                            style={{ fontSize: "0.75rem" }}
                            disabled={markingUsedId === redemption.id}
                            onClick={() => markVoucherUsed(redemption.id)}
                          >
                            {markingUsedId === redemption.id ? "Marking…" : "Mark as used"}
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
                </div>
              ) : (
                <p className="eyebrow">
                  {rewards.redemptions.length} voucher{rewards.redemptions.length === 1 ? "" : "s"} — expand to view.
                </p>
              )}
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
          busy={busy || !redeemCardId}
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
            handlePay(selectedMerchant);
          }}
          confirmLabel={`Pay ${payAmount || 0} ${effectiveWallet(selectedCard)?.currency ?? "RON"}`}
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
              With your {formatCardLabel(selectedCard)}:{" "}
              {combinedRateLabel(selectedCard, Number(selectedMerchant.active_offer?.cashback_percent ?? 0))}
            </p>
          )}
          {!selectedMerchant.verified && (
            <p className="eyebrow">Not verified yet — purchases here don't earn points.</p>
          )}
        </ConfirmModal>
      )}

      {codeReveal && (
        <div
          role="presentation"
          onClick={() => setCodeReveal(null)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 17, 25, 0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 70,
            padding: "1rem",
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={codeReveal.title}
            className="tile"
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: "420px",
              width: "100%",
              textAlign: "center",
              background: "var(--aurora-gradient, #5b5fef)",
              color: "#fff",
              border: "none",
            }}
          >
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="button--ghost"
                onClick={() => setCodeReveal(null)}
                aria-label="Close"
                style={{ color: "#fff" }}
              >
                <X size={16} strokeWidth={2.2} />
              </button>
            </div>
            <Sparkles size={22} strokeWidth={2} style={{ marginBottom: "0.5rem" }} />
            <p style={{ fontWeight: 700, fontSize: "1.05rem", margin: "0 0 0.75rem" }}>{codeReveal.title}</p>
            <div
              style={{
                background: "rgba(255,255,255,0.16)",
                border: "1px dashed rgba(255,255,255,0.5)",
                borderRadius: "0.75rem",
                padding: "1rem",
                fontFamily: "monospace",
                fontSize: "1.6rem",
                fontWeight: 700,
                letterSpacing: "0.05em",
                margin: "0 0 0.75rem",
                wordBreak: "break-all",
              }}
            >
              {codeReveal.code}
            </div>
            <p style={{ fontSize: "0.85rem", opacity: 0.9, margin: "0 0 1rem" }}>{codeReveal.subtitle}</p>
            <div style={{ display: "flex", gap: "0.6rem", justifyContent: "center", flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={() => copyCode(codeReveal.code)}
                style={{ background: "#fff", color: "#4548c9", border: "none" }}
              >
                {copyFeedback ? "Copied!" : "Copy code"}
              </button>
              <button
                type="button"
                className="button--ghost"
                onClick={() => setCodeReveal(null)}
                style={{ color: "#fff", border: "1px solid rgba(255,255,255,0.5)" }}
              >
                Done
              </button>
            </div>
          </div>
        </div>
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
