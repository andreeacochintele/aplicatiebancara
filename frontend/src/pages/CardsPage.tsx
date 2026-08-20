import { useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Eye, EyeOff, Lock, Trash2, Unlock } from "lucide-react";

import { ApiError, apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Card, CardPaymentPreferences, CardTier, CardType, Wallet } from "../types";

const CARD_TYPES: CardType[] = ["DEBIT", "CREDIT", "ONE_TIME"];
const CARD_TIERS: CardTier[] = ["REGULAR", "GOLD", "PLATINUM"];
const MAX_CARDS = 5;
const CARD_TIER_DETAILS: Record<CardTier, string> = {
  REGULAR: "Standard everyday card controls.",
  GOLD: "Cashback boosts and stronger everyday card support.",
  PLATINUM: "Premium travel, insurance and concierge-style card benefits.",
};
const CARD_TIER_REWARDS: Record<CardTier, string[]> = {
  REGULAR: ["1x reward points", "Standard card controls", "Basic spending notifications"],
  GOLD: ["1.5x reward points", "2% partner cashback", "Priority card support", "Higher daily card limits"],
  PLATINUM: ["2x reward points", "4% partner cashback", "Travel insurance", "Airport lounge access"],
};
const CARD_TIER_LABELS: Record<CardTier, string> = {
  REGULAR: "Regular",
  GOLD: "Gold",
  PLATINUM: "Platinum",
};
const CARD_TIER_PRODUCTS: Record<CardTier, { debit: string; credit: string }> = {
  REGULAR: {
    debit: "Regular debit",
    credit: "Regular credit",
  },
  GOLD: {
    debit: "Gold debit",
    credit: "Gold credit",
  },
  PLATINUM: {
    debit: "Platinum debit",
    credit: "Platinum credit",
  },
};
const CARD_TIER_PRODUCT_LIST = [
  {
    name: "Regular",
    description: "Everyday debit or credit card with standard limits and core banking controls.",
    debit: "Standard debit",
    credit: "Standard credit",
    rewards: CARD_TIER_REWARDS.REGULAR,
  },
  {
    name: "Gold",
    description: "A stronger everyday tier with cashback boosts and faster support.",
    debit: "Gold debit",
    credit: "Gold credit",
    rewards: CARD_TIER_REWARDS.GOLD,
  },
  {
    name: "Platinum",
    description: "A premium tier focused on travel, protection and higher-touch service.",
    debit: "Platinum debit",
    credit: "Platinum credit",
    rewards: CARD_TIER_REWARDS.PLATINUM,
  },
];

function formatCardType(type: CardType): string {
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function statusClass(status: Card["status"]): string {
  if (status === "ACTIVE") return "tag tag--accent";
  if (status === "FROZEN") return "tag tag--warning";
  return "tag tag--neutral";
}

function formatCardTier(tier: CardTier | null): string {
  return tier ? CARD_TIER_LABELS[tier] : "No tier";
}

function cardToneClass(card: Card): string {
  if (card.type === "ONE_TIME") return "bank-card bank-card--one-time";
  const tier = (card.tier ?? "REGULAR").toLowerCase();
  return `bank-card bank-card--${card.type.toLowerCase()} bank-card--${tier}`;
}

export function CardsPage() {
  const { accessToken, logout, user } = useAuth();
  const [cards, setCards] = useState<Card[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [preferences, setPreferences] = useState<Record<string, CardPaymentPreferences>>({});
  const [draftPreferences, setDraftPreferences] = useState<Record<string, CardPaymentPreferences>>({});
  const [selectedType, setSelectedType] = useState<CardType>("DEBIT");
  const [selectedTier, setSelectedTier] = useState<CardTier>("REGULAR");
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [actionCardId, setActionCardId] = useState<string | null>(null);
  const [deletingCardId, setDeletingCardId] = useState<string | null>(null);
  const [preferencesCardId, setPreferencesCardId] = useState<string | null>(null);
  const [areTiersExpanded, setAreTiersExpanded] = useState(true);
  const [revealedCardIds, setRevealedCardIds] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);

  const activeWallets = useMemo(() => wallets.filter((wallet) => wallet.status === "ACTIVE"), [wallets]);
  const cardholderName = user ? `${user.first_name} ${user.last_name}`.trim() : "Card holder";
  const selectedReusableCardType = selectedType === "DEBIT" || selectedType === "CREDIT";
  const cardLimitReached = cards.length >= MAX_CARDS;

  async function loadCardsData(token: string) {
    setIsLoading(true);
    setError(null);
    try {
      const [cardsResponse, walletsResponse] = await Promise.all([
        apiRequest<Card[]>("/cards", { token }),
        apiRequest<Wallet[]>("/wallets", { token }),
      ]);
      const preferencesResponse = await Promise.all(
        cardsResponse.map((card) =>
          apiRequest<CardPaymentPreferences>(`/cards/${card.id}/payment-preferences`, { token }),
        ),
      );
      const preferencesByCard = Object.fromEntries(
        preferencesResponse.map((item) => [item.card_id, item]),
      );
      setCards(cardsResponse);
      setWallets(walletsResponse);
      setPreferences(preferencesByCard);
      setDraftPreferences(preferencesByCard);
      const mainWallet = walletsResponse.find((wallet) => wallet.is_main && wallet.status === "ACTIVE");
      setSelectedWalletId((current) => current || mainWallet?.id || "");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setCards([]);
      setWallets([]);
      setPreferences({});
      setDraftPreferences({});
      setError(err instanceof ApiError ? err.message : "Could not load cards.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken) return;
    void loadCardsData(accessToken);
  }, [accessToken, logout]);

  async function createCard() {
    if (!accessToken || isSaving || cardLimitReached) return;
    setIsSaving(true);
    setError(null);
    try {
      const card = await apiRequest<Card>("/cards", {
        method: "POST",
        token: accessToken,
        body: {
          type: selectedType,
          tier: selectedReusableCardType ? selectedTier : null,
          default_wallet_id: selectedWalletId || null,
        },
      });
      setCards((current) => [card, ...current]);
      const cardPreferences = await apiRequest<CardPaymentPreferences>(`/cards/${card.id}/payment-preferences`, {
        token: accessToken,
      });
      setPreferences((current) => ({ ...current, [card.id]: cardPreferences }));
      setDraftPreferences((current) => ({ ...current, [card.id]: cardPreferences }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not create card.");
    } finally {
      setIsSaving(false);
    }
  }

  async function updateCardStatus(card: Card) {
    if (!accessToken || actionCardId) return;
    const path = card.status === "FROZEN" ? `/cards/${card.id}/unfreeze` : `/cards/${card.id}/freeze`;
    setActionCardId(card.id);
    setError(null);
    try {
      const updated = await apiRequest<Card>(path, {
        method: "PATCH",
        token: accessToken,
      });
      setCards((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not update card.");
    } finally {
      setActionCardId(null);
    }
  }

  async function deleteCard(card: Card) {
    if (!accessToken || deletingCardId) return;
    const confirmed = window.confirm(`Delete card ending in ${card.last_four}?`);
    if (!confirmed) return;

    setDeletingCardId(card.id);
    setError(null);
    try {
      await apiRequest<void>(`/cards/${card.id}`, {
        method: "DELETE",
        token: accessToken,
      });
      setCards((current) => current.filter((item) => item.id !== card.id));
      setPreferences((current) => {
        const next = { ...current };
        delete next[card.id];
        return next;
      });
      setDraftPreferences((current) => {
        const next = { ...current };
        delete next[card.id];
        return next;
      });
      setRevealedCardIds((current) => {
        const next = new Set(current);
        next.delete(card.id);
        return next;
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not delete card.");
    } finally {
      setDeletingCardId(null);
    }
  }

  function toggleCardReveal(cardId: string) {
    setRevealedCardIds((current) => {
      const next = new Set(current);
      if (next.has(cardId)) {
        next.delete(cardId);
      } else {
        next.add(cardId);
      }
      return next;
    });
  }

  function updatePreferenceDraft(cardId: string, updates: Partial<CardPaymentPreferences>) {
    const currentDraft = draftPreferences[cardId] ?? preferences[cardId];
    if (!currentDraft) return;
    const nextDraft = {
      ...currentDraft,
      ...updates,
    };
    setDraftPreferences((current) => ({
      ...current,
      [cardId]: nextDraft,
    }));
    void savePaymentPreferences(cardId, nextDraft);
  }

  async function savePaymentPreferences(cardId: string, draft: CardPaymentPreferences) {
    if (!accessToken) return;
    setPreferencesCardId(cardId);
    setError(null);
    try {
      const updated = await apiRequest<CardPaymentPreferences>(`/cards/${cardId}/payment-preferences`, {
        method: "PATCH",
        token: accessToken,
        body: {
          preferred_wallet_id: draft.preferred_wallet_id,
          allow_main_wallet_fx: draft.allow_main_wallet_fx,
        },
      });
      setPreferences((current) => ({ ...current, [cardId]: updated }));
      setDraftPreferences((current) => ({ ...current, [cardId]: updated }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not save card preferences.");
    } finally {
      setPreferencesCardId((current) => (current === cardId ? null : current));
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Card controls</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: "0.75rem" }}>
          <label>
            Card type
            <select
              value={selectedType}
              onChange={(event) => {
                const nextType = event.target.value as CardType;
                setSelectedType(nextType);
                if (nextType === "ONE_TIME") {
                  setSelectedTier("REGULAR");
                }
              }}
            >
              {CARD_TYPES.map((type) => (
                <option key={type} value={type}>
                  {formatCardType(type)}
                </option>
              ))}
            </select>
          </label>
          {selectedReusableCardType && (
            <label>
              Tier
              <select value={selectedTier} onChange={(event) => setSelectedTier(event.target.value as CardTier)}>
                {CARD_TIERS.map((tier) => (
                  <option key={tier} value={tier}>
                    {CARD_TIER_LABELS[tier]}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Default wallet
            <select value={selectedWalletId} onChange={(event) => setSelectedWalletId(event.target.value)}>
              <option value="">No default wallet</option>
              {activeWallets.map((wallet) => (
                <option key={wallet.id} value={wallet.id}>
                  {wallet.currency}
                  {wallet.is_main ? " - Main" : ""}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={createCard} disabled={isSaving || cardLimitReached} style={{ alignSelf: "end" }}>
            {isSaving
              ? "Creating..."
              : cardLimitReached
                ? "Card limit reached"
              : selectedReusableCardType
                ? `Create ${CARD_TIER_LABELS[selectedTier]} ${formatCardType(selectedType)}`
                : "Create one-time card"}
          </button>
        </div>
        {cardLimitReached && (
          <p className="eyebrow" style={{ margin: "0.85rem 0 0" }}>
            You can have up to {MAX_CARDS} cards.
          </p>
        )}
        <div className="card-tier-summary" style={{ marginTop: "0.85rem" }}>
          {selectedReusableCardType ? (
            <>
              <span>{CARD_TIER_DETAILS[selectedTier]}</span>
              <span className="tag tag--outline">
                {selectedType === "DEBIT"
                  ? CARD_TIER_PRODUCTS[selectedTier].debit
                  : CARD_TIER_PRODUCTS[selectedTier].credit}
              </span>
              <span className="card-tier-summary__rewards">
                {CARD_TIER_REWARDS[selectedTier].map((reward) => (
                  <span key={reward}>{reward}</span>
                ))}
              </span>
            </>
          ) : (
            <>
              <span>Single-use cards are created without Regular, Gold or Platinum tiers.</span>
              <span className="tag tag--outline">No tier</span>
            </>
          )}
        </div>
        {error && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{error}</p>}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Card tier levels</span>
          <button
            type="button"
            className="button--ghost"
            onClick={() => setAreTiersExpanded((current) => !current)}
            aria-expanded={areTiersExpanded}
          >
            {areTiersExpanded ? "Retract" : "Expand"}
          </button>
        </div>
        {areTiersExpanded ? (
          <>
            <div className="card-tier-grid">
              {CARD_TIER_PRODUCT_LIST.map((tier) => (
                <article className={`card-tier card-tier--${tier.name.toLowerCase()}`} key={tier.name}>
                  <div className="card-tier__header">
                    <span className="card-tier__name">{tier.name}</span>
                    <span className="tag tag--neutral">Debit + Credit</span>
                  </div>
                  <p>{tier.description}</p>
                  <div className="card-tier__rewards">
                    {tier.rewards.map((reward) => (
                      <span key={reward}>{reward}</span>
                    ))}
                  </div>
                  <div className="card-tier__products">
                    <span>{tier.debit}</span>
                    <span>{tier.credit}</span>
                  </div>
                </article>
              ))}
            </div>
            <div className="card-tier-note">
              <span className="tag tag--outline">One-time card</span>
              <span>Single-use cards do not have Regular, Gold or Platinum tiers.</span>
            </div>
          </>
        ) : (
          <div className="card-tier-summary">
            <span>Regular, Gold and Platinum apply only to debit and credit cards.</span>
            <span className="tag tag--outline">One-time cards excluded</span>
          </div>
        )}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">My cards</span>
        </div>
        {isLoading && <div className="card-empty">Loading cards...</div>}
        {!isLoading && cards.length === 0 && <div className="card-empty">No cards yet.</div>}
        {!isLoading && cards.length > 0 && (
          <div className="card-gallery">
            {cards.map((card) => {
              const wallet = wallets.find((item) => item.id === card.default_wallet_id);
              const draft = draftPreferences[card.id];
              const isRevealed = revealedCardIds.has(card.id);
              return (
                <article className="card-panel" key={card.id}>
                  <div className={cardToneClass(card)}>
                    <div className="bank-card__top">
                      <div className="bank-card__identity">
                        <span className="bank-card__brand">AURORA</span>
                        <span className="bank-card__product">
                          {card.tier ? `${formatCardTier(card.tier)} ${formatCardType(card.type)}` : "One-time"}
                        </span>
                      </div>
                      <div className="bank-card__top-actions">
                        <span className={statusClass(card.status)}>{card.status}</span>
                        <button
                          type="button"
                          className="bank-card__lock"
                          onClick={() => updateCardStatus(card)}
                          disabled={actionCardId === card.id || (card.status !== "ACTIVE" && card.status !== "FROZEN")}
                          aria-label={card.status === "FROZEN" ? "Unfreeze card" : "Freeze card"}
                          title={card.status === "FROZEN" ? "Unfreeze card" : "Freeze card"}
                        >
                          {card.status === "FROZEN" ? (
                            <Unlock size={15} strokeWidth={2.2} />
                          ) : (
                            <Lock size={15} strokeWidth={2.2} />
                          )}
                        </button>
                      </div>
                    </div>
                    <div className="bank-card__middle">
                      <div className="bank-card__chip" aria-hidden="true" />
                      <span className="bank-card__mark">{card.type === "ONE_TIME" ? "1x" : card.type}</span>
                    </div>
                    <div className="bank-card__number-row">
                      <div className="bank-card__number">{isRevealed ? card.mock_pan : card.masked_pan}</div>
                      <button
                        type="button"
                        className="bank-card__reveal"
                        onClick={() => toggleCardReveal(card.id)}
                        aria-label={isRevealed ? "Hide card details" : "Reveal card details"}
                        title={isRevealed ? "Hide card details" : "Reveal card details"}
                      >
                        {isRevealed ? <Eye size={16} strokeWidth={2.2} /> : <EyeOff size={16} strokeWidth={2.2} />}
                      </button>
                    </div>
                    <div className="bank-card__holder">
                      <span>Card holder</span>
                      <strong>{cardholderName}</strong>
                    </div>
                    <div className="bank-card__footer">
                      <span>
                        {card.tier ? `${formatCardTier(card.tier)} ${formatCardType(card.type)}` : formatCardType(card.type)}
                      </span>
                      <span className="bank-card__security">
                        <span>
                          EXP {String(card.expiration_month).padStart(2, "0")}/{card.expiration_year}
                        </span>
                        <span>Mock CVV {isRevealed ? card.mock_cvv : "***"}</span>
                      </span>
                    </div>
                  </div>

                  <div className="card-panel__meta">
                    <div>
                      <div className="eyebrow">Default wallet</div>
                      <div className="card-panel__value">{wallet ? wallet.currency : "None"}</div>
                    </div>
                    <div className="card-panel__actions">
                      <button
                        type="button"
                        className="card-panel__icon-action button--danger"
                        onClick={() => deleteCard(card)}
                        disabled={deletingCardId === card.id}
                        aria-label="Delete card"
                        title="Delete card"
                      >
                        <Trash2 size={16} strokeWidth={2.2} />
                      </button>
                    </div>
                  </div>
                  {draft && (
                    <div className="card-preferences">
                      <label>
                        Preferred wallet
                        <select
                          value={draft.preferred_wallet_id ?? ""}
                          onChange={(event) =>
                            updatePreferenceDraft(card.id, {
                              preferred_wallet_id: event.target.value || null,
                            })
                          }
                        >
                          <option value="">No preferred wallet</option>
                          {activeWallets.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.currency}
                              {item.is_main ? " - Main" : ""}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        className={`card-preference-toggle${draft.allow_main_wallet_fx ? " active" : ""}`}
                        title="Allow main-wallet FX fallback"
                        aria-label="Allow main-wallet FX fallback"
                        aria-pressed={draft.allow_main_wallet_fx}
                        onClick={() =>
                          updatePreferenceDraft(card.id, { allow_main_wallet_fx: !draft.allow_main_wallet_fx })
                        }
                      >
                        <ArrowLeftRight size={16} strokeWidth={2.2} aria-hidden="true" />
                      </button>
                      {preferencesCardId === card.id && <div className="eyebrow">Saving...</div>}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
