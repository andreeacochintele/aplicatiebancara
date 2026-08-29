import { CreditCard, Gift, RefreshCw, ShieldCheck, Sparkles, Store, Users, X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest, ApiError } from "../api/apiClient";
import {
  bestOwnedCardTier,
  cardTierCashbackPercent,
  cardTierRewardBullets,
  combinedRateLabel,
  pointsPerRonLabel,
} from "../config/rewardPolicy";
import { CategoryIconBadge, CategoryPill, PointsPill } from "../features/rewards";
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

function formatCardTierLabel(tier: CardTier | null, t: (key: string) => string): string {
  return tier ? tier[0] + tier.slice(1).toLowerCase() : t("rewards.oneTime");
}

function formatCardTypeLabel(type: Card["type"]): string {
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatCardLabel(card: Card, t: (key: string) => string): string {
  return `${formatCardTierLabel(card.tier, t)} ${card.type[0]}${card.type.slice(1).toLowerCase()} •••• ${card.last_four}`;
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
  const { t } = useTranslation();
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
            aria-label={t("rewards.close")}
            style={{ marginLeft: "auto" }}
          >
            <X size={15} strokeWidth={2.2} />
          </button>
        </div>
        {children}
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", justifyContent: "flex-end" }}>
          <button type="button" className="button--ghost" onClick={onCancel}>
            {t("rewards.cancel")}
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
  const { t } = useTranslation();
  const { accessToken, user } = useAuth();
  const cardholderName = user ? `${user.first_name} ${user.last_name}`.trim() : t("rewards.cardHolderFallback");
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
  const [cvvInput, setCvvInput] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [showFullHistory, setShowFullHistory] = useState(false);
  const [areCardsExpanded, setAreCardsExpanded] = useState(true);
  const [areVouchersExpanded, setAreVouchersExpanded] = useState(false);
  const [isInviteExpanded, setIsInviteExpanded] = useState(false);
  const [codeReveal, setCodeReveal] = useState<{ title: string; subtitle: string; code: string } | null>(null);
  const [copyFeedback, setCopyFeedback] = useState(false);
  const [inviteCopyFeedback, setInviteCopyFeedback] = useState(false);
  const [markingUsedId, setMarkingUsedId] = useState<string | null>(null);
  const [refreshingHistory, setRefreshingHistory] = useState(false);

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

  function paymentCurrency(card: Card | undefined): string {
    if (!card) return "RON";
    if (card.type === "CREDIT") return card.credit_account?.currency ?? "RON";
    return effectiveWallet(card)?.currency ?? "RON";
  }

  function cardFundingLabel(card: Card): string {
    if (card.type === "CREDIT") {
      const availableCredit = Number(card.credit_account?.available_credit ?? 0).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
      return t("rewards.availableCreditAmount", { amount: availableCredit, currency: card.credit_account?.currency ?? "RON" });
    }
    return t("rewards.walletCurrency", { currency: effectiveWallet(card)?.currency ?? "unknown" });
  }

  function selectedCardFundingLabel(card: Card | undefined): string {
    if (!card) return t("rewards.pickCardBelow");
    if (card.type === "CREDIT") return t("rewards.usesAvailableCredit");
    return t("rewards.paysFromWallet", { currency: effectiveWallet(card)?.currency ?? "unknown" });
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

  // A real card payment only becomes a reward transaction once sync-rewards
  // runs (see syncRewards above), which otherwise only happens on page load
  // and right after a payment made from this page's own pay form — a
  // payment made elsewhere (Cards page, another tab) needs this manual
  // nudge instead of a full page reload.
  async function refreshPointsHistory() {
    if (!accessToken || refreshingHistory) return;
    setRefreshingHistory(true);
    try {
      await syncRewards();
    } finally {
      loadRewards();
      setRefreshingHistory(false);
    }
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

  function openPayConfirm(merchant: Merchant) {
    setError(null);
    setCvvInput("");
    setSelectedMerchant(merchant);
  }

  async function handlePay(merchant: Merchant) {
    if (!accessToken || !payCardId) return;
    setError(null);
    setBusy(true);
    try {
      const transaction = await apiRequest<{ id: string }>("/transactions/card-payment", {
        method: "POST",
        token: accessToken,
        body: { card_id: payCardId, merchant_id: merchant.id, amount: payAmount, cvv: cvvInput },
      });
      // Confirmed and debited — close the confirmation and clear the CVV
      // field. A failed attempt (wrong CVV, insufficient balance, etc.)
      // falls through to the catch block instead, which deliberately does
      // NOT close the modal, so the user can just retry without re-picking
      // the merchant and card.
      setSelectedMerchant(null);
      setCvvInput("");
      const receipt = t("rewards.receiptNumber", { id: transaction.id.slice(0, 8).toUpperCase() });
      loadCards();
      const earned = await syncRewards();
      const match = earned.find((p) => p.merchant_id === merchant.id);
      if (match) {
        // Partner Offers is a pure earning flow (simulated real purchase) —
        // informational confirmation only, no code/voucher. Redeem codes
        // belong to the "Redeem your points" catalog below instead. Points
        // and cashback are independent: cashback is real money credited
        // back to the wallet, never extra points, so they're shown as two
        // separate numbers rather than a combined total.
        const cashback =
          Number(match.cashback_amount) > 0
            ? t("rewards.cashbackCreditedToWallet", { amount: match.cashback_amount, currency: match.currency })
            : "";
        setToast(t("rewards.paymentConfirmedEarned", { receipt, points: match.points_earned, cashback }));
      } else if (!merchant.verified) {
        setToast(t("rewards.paymentConfirmedNotVerified", { receipt }));
      } else {
        setToast(t("rewards.paymentConfirmed", { receipt }));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("rewards.paymentFailed"));
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
          title: t("rewards.redeemedTitle", { name: benefit.name }),
          subtitle:
            t("rewards.redeemedSubtitle", { points: benefit.points_cost ?? 0, partner: benefit.partner_name ?? t("rewards.thePartner") }) +
            (validUntil ? t("rewards.validUntilAlsoSaved", { date: validUntil }) : ""),
          code: redemption.redemption_code,
        });
      } else {
        setToast(t("rewards.redeemedToast", { name: benefit.name, points: benefit.points_cost ?? 0 }));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("rewards.redeemFailed"));
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
      setError(err instanceof ApiError ? err.message : t("rewards.couldNotMarkVoucherUsed"));
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
      <div className="tile" style={{ background: "var(--easyb-gradient, #5b5fef)", color: "#fff", border: "none" }}>
        <div className="eyebrow" style={{ color: "rgba(255,255,255,0.75)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <Sparkles size={14} strokeWidth={2.2} />
          {t("rewards.yourBalance")}
        </div>
        <div className="balance-hero__amount" style={{ color: "#fff" }}>
          {rewards ? rewards.points_balance : "—"} <span style={{ fontSize: "1.1rem", fontWeight: 600 }}>{t("rewards.pts")}</span>
        </div>
        <div style={{ marginTop: "1rem", display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
          <button type="button" onClick={() => scrollToId("rewards-pay")} style={{ background: "#fff", color: "#4548c9", border: "none" }}>
            {t("rewards.earnPoints")}
          </button>
          <button
            type="button"
            onClick={() => scrollToId("rewards-catalog")}
            style={{ background: "rgba(255,255,255,0.16)", color: "#fff", border: "1px solid rgba(255,255,255,0.4)" }}
          >
            {t("rewards.redeemPoints")}
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
                {t("rewards.yourCardsAndRewards")}
              </span>
              <button
                type="button"
                className="button--ghost"
                onClick={() => setAreCardsExpanded((current) => !current)}
                aria-expanded={areCardsExpanded}
              >
                {areCardsExpanded ? t("rewards.retract") : t("rewards.expand")}
              </button>
            </div>
            <p className="eyebrow" style={{ marginTop: "-0.4rem", marginBottom: "0.75rem" }}>
              {t("rewards.cardTierHint")}
            </p>
            {areCardsExpanded && cards.length > 0 ? (
              <div className="card-gallery">
                {cards.map((card) => (
                  <article className="card-panel" key={card.id}>
                    <div className={cardToneClass(card)}>
                      <div className="bank-card__top">
                        <div className="bank-card__identity">
                          <span className="bank-card__brand">EASYB</span>
                          <span className="bank-card__product">
                            {card.tier
                              ? `${formatCardTierLabel(card.tier, t)} ${formatCardTypeLabel(card.type)}`
                              : t("rewards.oneTime")}
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
                        <span>{t("rewards.cardHolder")}</span>
                        <strong>{cardholderName}</strong>
                      </div>
                      <div className="bank-card__footer">
                        <span>
                          {card.tier
                            ? `${formatCardTierLabel(card.tier, t)} ${formatCardTypeLabel(card.type)}`
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
                        <div className="eyebrow">{t("rewards.thisCardsPerks")}</div>
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
              <p className="eyebrow">{t("rewards.noCardsYet")}</p>
            ) : (
              <p className="eyebrow">{t("rewards.cardCount", { count: cards.length })}</p>
            )}
          </div>

          {/* 3. Rewards catalog / redeem points */}
          <div className="tile" id="rewards-catalog">
            <div className="tile__header">
              <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Gift size={14} strokeWidth={2.2} />
                {t("rewards.redeemYourPoints")}
              </span>
            </div>
            {benefits.length > 0 ? (
              <div className="card-gallery">
                {benefits.map((benefit) => {
                  const missing =
                    rewards && benefit.points_cost !== null ? benefit.points_cost - rewards.points_balance : null;
                  return (
                    <article className="card-panel reward-card" key={benefit.id}>
                      <div className="reward-card__top">
                        <CategoryIconBadge category={benefit.category} />
                        <PointsPill>{benefit.points_cost !== null ? `${benefit.points_cost} ${t("rewards.pts")}` : t("rewards.free")}</PointsPill>
                      </div>
                      <div className="card-panel__meta">
                        <div>
                          <div className="eyebrow">{benefit.category.replace("_", " ")}</div>
                          <div className="card-panel__value">{benefit.name}</div>
                          {benefit.partner_name && (
                            <div className="eyebrow" style={{ marginTop: "0.15rem" }}>
                              {benefit.partner_name}
                              {benefit.min_card_tier ? ` · ${formatCardTierLabel(benefit.min_card_tier, t)}+ card` : ""}
                            </div>
                          )}
                        </div>
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
                            {t("rewards.redeem")}
                          </button>
                        ) : (
                          <span className="eyebrow">
                            {missing && missing > 0 ? t("rewards.needMorePoints", { count: missing }) : benefit.reason_if_locked}
                          </span>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="eyebrow">{t("rewards.noBenefitsYet")}</p>
            )}
          </div>

          {/* 4. Partner merchants and cashback */}
          <div className="tile" id="rewards-pay">
            <div className="tile__header">
              <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Store size={14} strokeWidth={2.2} />
                {t("rewards.partnerOffers")}
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
                      background: "var(--easyb-gradient, #5b5fef)",
                      color: "#fff",
                      flexShrink: 0,
                    }}
                  >
                    <CreditCard size={15} strokeWidth={2.4} />
                  </span>
                  <span className="eyebrow" style={{ fontSize: "0.85rem" }}>
                    {t("rewards.payWithCard")}
                  </span>
                </div>
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "flex-end" }}>
                  <div style={{ flex: "2 1 220px", minWidth: 0 }}>
                    <label className="eyebrow" style={{ display: "block", marginBottom: "0.3rem" }}>
                      {t("rewards.card")}
                    </label>
                    <select
                      value={payCardId}
                      onChange={(e) => setPayCardId(e.target.value)}
                      style={{ width: "100%" }}
                    >
                      {cards.map((card) => (
                        <option key={card.id} value={card.id}>
                          {formatCardLabel(card, t)} - {cardFundingLabel(card)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div style={{ flex: "1 1 110px" }}>
                    <label className="eyebrow" style={{ display: "block", marginBottom: "0.3rem" }}>
                      {t("rewards.amountWithCurrency", { currency: paymentCurrency(selectedCard) })}
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
                      ? t("rewards.tierCashbackToWallet", { percent: cardTierCashbackPercent(selectedCard) })
                      : ""}
                  </div>
                )}
                <p className="eyebrow" style={{ marginTop: "0.6rem", marginBottom: 0 }}>
                  {selectedCardFundingLabel(selectedCard)}
                </p>
              </div>
            )}

            {visibleMerchants.length > 0 ? (
              <div className="card-gallery">
                {visibleMerchants.map((merchant) => {
                  return (
                    <article className="card-panel reward-card" key={merchant.id}>
                      <button
                        type="button"
                        onClick={() => openPayConfirm(merchant)}
                        style={{
                          all: "unset",
                          cursor: "pointer",
                          display: "block",
                          width: "100%",
                        }}
                        aria-label={t("rewards.viewDetailsFor", { name: merchant.name })}
                      >
                        <div className="reward-card__top">
                          <CategoryIconBadge category={merchant.category} />
                          {merchant.active_offer ? (
                            <CategoryPill category={merchant.category}>
                              {t("rewards.cashbackPercent", { percent: merchant.active_offer.cashback_percent })}
                            </CategoryPill>
                          ) : (
                            <span className="tag tag--outline">{t("rewards.noActiveOffer")}</span>
                          )}
                        </div>
                        <div className="card-panel__meta">
                          <div>
                            <div className="eyebrow">{merchant.category}</div>
                            <div className="card-panel__value">{merchant.name}</div>
                            {!merchant.verified && (
                              <div className="eyebrow" style={{ marginTop: "0.15rem" }}>
                                {t("rewards.notVerifiedNoPoints")}
                              </div>
                            )}
                          </div>
                        </div>
                        {selectedCard && (
                          <div className="eyebrow" style={{ marginTop: "0.4rem" }}>
                            {t("rewards.earnRate", { rate: combinedRateLabel(selectedCard, Number(merchant.active_offer?.cashback_percent ?? 0)) })}
                          </div>
                        )}
                      </button>
                      <div className="card-panel__actions">
                        <button onClick={() => openPayConfirm(merchant)} disabled={busy || !payCardId}>
                          {t("rewards.pay", { amount: payAmount || 0, currency: effectiveWallet(selectedCard)?.currency ?? "RON" })}
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="eyebrow">{t("rewards.noMerchantsInCategory")}</p>
            )}

            {newlyEarned.length > 0 && (
              <div className="eyebrow" style={{ marginTop: "0.75rem" }}>
                {newlyEarned.map((purchase) => (
                  <div key={purchase.merchant_id}>
                    {t("rewards.earnedFromRealPayment", {
                      points: purchase.points_earned,
                      cashback:
                        Number(purchase.cashback_amount) > 0
                          ? t("rewards.cashbackCreditedToWallet", { amount: purchase.cashback_amount, currency: purchase.currency })
                          : "",
                    })}
                  </div>
                ))}
              </div>
            )}
            {error && !selectedMerchant && <p role="alert">{error}</p>}
          </div>
        </div>

        {/* Side section */}
        <div style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: "1.25rem", minWidth: "280px" }}>
          {/* 5. Card-dependent benefits */}
          <div className="tile">
            <div className="tile__header">
              <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <ShieldCheck size={14} strokeWidth={2.2} />
                {t("rewards.yourBenefits")}
              </span>
            </div>
            {bestTier && (
              <div className="eyebrow" style={{ marginBottom: "0.5rem" }}>
                {t("rewards.fromBestCardTier", { tier: formatCardTierLabel(bestTier, t) })}
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
              <p className="eyebrow">{t("rewards.upgradeToUnlock")}</p>
            )}
          </div>

          {/* 6. Referral / earn more points */}
          <div className="tile" style={{ background: "var(--easyb-gradient, #5b5fef)", color: "#fff", border: "none" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="eyebrow" style={{ color: "rgba(255,255,255,0.75)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Users size={14} strokeWidth={2.2} />
                {t("rewards.wantMorePoints")}
              </div>
              {isInviteExpanded && (
                <button
                  type="button"
                  className="button--ghost"
                  onClick={() => setIsInviteExpanded(false)}
                  aria-expanded={isInviteExpanded}
                  style={{ color: "#fff", borderColor: "rgba(255,255,255,0.5)" }}
                >
                  {t("rewards.retract")}
                </button>
              )}
            </div>
            <p style={{ margin: "0.5rem 0 0.85rem", fontSize: "0.9rem" }}>
              {t("rewards.inviteEarnPoints")}
            </p>
            {isInviteExpanded ? (
              <div>
                <p style={{ margin: "0 0 0.4rem", fontSize: "0.8rem", opacity: 0.85 }}>{t("rewards.yourInviteLink")}</p>
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
                  {inviteCopyFeedback ? t("rewards.copied") : t("rewards.copyLink")}
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
                {t("rewards.inviteFriends")}
              </button>
            )}
          </div>

          {/* 7. Rewards points history */}
          <div className="tile">
            <div className="tile__header">
              <span className="eyebrow">{t("rewards.pointsHistory")}</span>
              <button
                type="button"
                className="button--ghost card-panel__icon-action"
                onClick={refreshPointsHistory}
                disabled={refreshingHistory}
                aria-label={t("rewards.refreshPointsHistory")}
                style={{ marginLeft: "auto" }}
              >
                <RefreshCw size={14} strokeWidth={2.2} className={refreshingHistory ? "spin" : undefined} />
              </button>
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
                              {t("rewards.code", { code: tx.proof_code })}
                            </div>
                          )}
                        </span>
                        <span
                          style={{
                            fontWeight: 700,
                            color: tx.points >= 0 ? "var(--easyb-green, #2e9e5b)" : "var(--color-text-muted)",
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
                    {showFullHistory ? t("rewards.showLess") : t("rewards.viewAll")}
                  </button>
                )}
              </>
            ) : (
              <p className="eyebrow">{t("rewards.noRewardActivity")}</p>
            )}
          </div>

          {rewards && rewards.redemptions.length > 0 && (
            <div className="tile">
              <div className="tile__header">
                <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <Gift size={14} strokeWidth={2.2} />
                  {t("rewards.myVouchers", { count: rewards.redemptions.length })}
                </span>
                <button
                  type="button"
                  className="button--ghost"
                  onClick={() => setAreVouchersExpanded((current) => !current)}
                  aria-expanded={areVouchersExpanded}
                >
                  {areVouchersExpanded ? t("rewards.retract") : t("rewards.expand")}
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
                        borderBottom: "1px solid var(--easyb-border, rgba(0,0,0,0.08))",
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
                          {t("rewards.ptsRedeemedOn", { points: redemption.points_spent, date: new Date(redemption.redeemed_at).toLocaleDateString() })}
                          {redemption.status === "VALID" && redemption.expires_at
                            ? t("rewards.validUntil", { date: new Date(redemption.expires_at).toLocaleDateString() })
                            : redemption.status === "USED" && redemption.used_at
                              ? t("rewards.usedOn", { date: new Date(redemption.used_at).toLocaleDateString() })
                              : redemption.status === "EXPIRED" && redemption.expires_at
                                ? t("rewards.expiredOn", { date: new Date(redemption.expires_at).toLocaleDateString() })
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
                          {redemption.status === "VALID" ? t("rewards.valid") : redemption.status === "USED" ? t("rewards.used") : t("rewards.expired")}
                        </span>
                        {redemption.status === "VALID" && (
                          <button
                            type="button"
                            className="button--ghost"
                            style={{ fontSize: "0.75rem" }}
                            disabled={markingUsedId === redemption.id}
                            onClick={() => markVoucherUsed(redemption.id)}
                          >
                            {markingUsedId === redemption.id ? t("rewards.marking") : t("rewards.markAsUsed")}
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
                </div>
              ) : (
                <p className="eyebrow">{t("rewards.voucherCount", { count: rewards.redemptions.length })}</p>
              )}
            </div>
          )}
        </div>
      </div>

      {confirmBenefit && rewards && (
        <ConfirmModal
          title={t("rewards.redeemRewardQuestion")}
          onCancel={() => setConfirmBenefit(null)}
          onConfirm={confirmRedeemBenefit}
          confirmLabel={busy ? t("rewards.redeeming") : t("rewards.redeemPts", { points: confirmBenefit.points_cost ?? 0 })}
          busy={busy || !redeemCardId}
        >
          <p style={{ fontWeight: 700, fontSize: "1.05rem", margin: "0.5rem 0" }}>{confirmBenefit.name}</p>
          <p className="eyebrow">{t("rewards.cost", { points: confirmBenefit.points_cost ?? 0 })}</p>
          <p className="eyebrow">{t("rewards.currentBalance", { points: rewards.points_balance })}</p>
          <p className="eyebrow">
            {t("rewards.balanceAfterRedemption", { points: rewards.points_balance - (confirmBenefit.points_cost ?? 0) })}
          </p>
        </ConfirmModal>
      )}

      {selectedMerchant && (
        <ConfirmModal
          title={t("rewards.confirmPayment")}
          onCancel={() => {
            setSelectedMerchant(null);
            setCvvInput("");
          }}
          onConfirm={() => handlePay(selectedMerchant)}
          confirmLabel={busy ? t("rewards.paying") : t("rewards.pay", { amount: payAmount || 0, currency: effectiveWallet(selectedCard)?.currency ?? "RON" })}
          busy={busy || !payCardId || cvvInput.length !== 3}
        >
          {selectedCard && (
            <div className={cardToneClass(selectedCard)} style={{ marginBottom: "0.85rem" }}>
              <div className="bank-card__top">
                <div className="bank-card__identity">
                  <span className="bank-card__brand">EASYB</span>
                  <span className="bank-card__product">
                    {selectedCard.tier
                      ? `${formatCardTierLabel(selectedCard.tier, t)} ${formatCardTypeLabel(selectedCard.type)}`
                      : t("rewards.oneTime")}
                  </span>
                </div>
              </div>
              <div className="bank-card__middle">
                <div className="bank-card__chip" aria-hidden="true" />
                <span className="bank-card__mark">{selectedCard.type === "ONE_TIME" ? "1x" : selectedCard.type}</span>
              </div>
              <div className="bank-card__number-row">
                <div className="bank-card__number">{selectedCard.masked_pan}</div>
              </div>
              <div className="bank-card__holder">
                <span>{t("rewards.cardHolder")}</span>
                <strong>{cardholderName}</strong>
              </div>
              <div className="bank-card__footer">
                <span>
                  {selectedCard.tier
                    ? `${formatCardTierLabel(selectedCard.tier, t)} ${formatCardTypeLabel(selectedCard.type)}`
                    : formatCardTypeLabel(selectedCard.type)}
                </span>
                <span className="bank-card__security">
                  <span>
                    EXP {String(selectedCard.expiration_month).padStart(2, "0")}/{selectedCard.expiration_year}
                  </span>
                </span>
              </div>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "space-between", margin: "0.3rem 0" }}>
            <span className="eyebrow">{t("rewards.merchant")}</span>
            <strong>{selectedMerchant.name}</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", margin: "0.3rem 0" }}>
            <span className="eyebrow">{t("rewards.amount")}</span>
            <strong>
              {payAmount || 0} {effectiveWallet(selectedCard)?.currency ?? "RON"}
            </strong>
          </div>

          {selectedMerchant.active_offer ? (
            <>
              <p style={{ margin: "0.4rem 0" }}>{t("rewards.cashbackPercent", { percent: selectedMerchant.active_offer.cashback_percent })}</p>
              {selectedMerchant.active_offer.minimum_spend && (
                <p className="eyebrow">{t("rewards.minimumSpend", { amount: selectedMerchant.active_offer.minimum_spend })}</p>
              )}
              {selectedMerchant.active_offer.maximum_cashback && (
                <p className="eyebrow">{t("rewards.maxCashback", { amount: selectedMerchant.active_offer.maximum_cashback })}</p>
              )}
            </>
          ) : (
            <p className="eyebrow">{t("rewards.noActiveCashbackOffer")}</p>
          )}
          {selectedCard && (
            <p className="eyebrow" style={{ marginTop: "0.3rem" }}>
              {t("rewards.withYourCard", {
                card: formatCardLabel(selectedCard, t),
                rate: combinedRateLabel(selectedCard, Number(selectedMerchant.active_offer?.cashback_percent ?? 0)),
              })}
            </p>
          )}
          {!selectedMerchant.verified && (
            <p className="eyebrow">{t("rewards.notVerifiedNoPointsPurchase")}</p>
          )}

          <label style={{ display: "block", marginTop: "0.75rem" }}>
            {t("rewards.cvvLabel", { card: selectedCard ? formatCardLabel(selectedCard, t) : t("rewards.cardFallback") })}
            <input
              value={cvvInput}
              onChange={(e) => setCvvInput(e.target.value.replace(/\D/g, "").slice(0, 3))}
              inputMode="numeric"
              autoComplete="off"
              placeholder="•••"
              style={{ width: "6rem", letterSpacing: "0.3em" }}
            />
          </label>
          {error && (
            <p role="alert" style={{ color: "var(--easyb-danger, #d1435b)", marginTop: "0.5rem" }}>
              {error}
            </p>
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
              background: "var(--easyb-gradient, #5b5fef)",
              color: "#fff",
              border: "none",
            }}
          >
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="button--ghost"
                onClick={() => setCodeReveal(null)}
                aria-label={t("rewards.close")}
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
                {copyFeedback ? t("rewards.copied") : t("rewards.copyCode")}
              </button>
              <button
                type="button"
                className="button--ghost"
                onClick={() => setCodeReveal(null)}
                style={{ color: "#fff", border: "1px solid rgba(255,255,255,0.5)" }}
              >
                {t("rewards.done")}
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
