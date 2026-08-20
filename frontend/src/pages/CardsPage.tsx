import { useEffect, useMemo, useState } from "react";
import { Eye, EyeOff, Lock, Trash2, Unlock } from "lucide-react";

import { ApiError, apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Card, CardTier, CardType, Wallet } from "../types";

const CARD_TYPES: CardType[] = ["DEBIT", "CREDIT", "ONE_TIME"];
const MAX_CARDS = 5;
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
const CREDIT_CARD_LIMITS: Record<CardTier, number> = {
  REGULAR: 5000,
  GOLD: 15000,
  PLATINUM: 30000,
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

function formatCurrencyAmount(value: number, currency = "RON"): string {
  return `${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function formatWalletBalance(wallet: Wallet): string {
  return `${Number(wallet.available_balance).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${wallet.currency}`;
}

function creditAvailableAmount(card: Card): string {
  return formatCurrencyAmount(CREDIT_CARD_LIMITS[card.tier ?? "REGULAR"]);
}

function walletDisplayName(wallet: Wallet): string {
  return `${wallet.currency}${wallet.is_main ? " - Main" : ""}`;
}

function walletOptionLabel(wallet: Wallet, debitAlreadyExists: boolean): string {
  const balance = Number(wallet.available_balance).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return debitAlreadyExists
    ? `${walletDisplayName(wallet)} - debit exists`
    : `${walletDisplayName(wallet)} - ${balance}`;
}

function selectedTierDetails(type: CardType | "", tier: CardTier): string {
  if (type === "DEBIT") return CARD_TIER_PRODUCT_LIST.find((item) => item.name.toUpperCase() === tier)?.description ?? "";
  if (type === "CREDIT") return "Credit card tier controls available credit, rewards and service level.";
  return "";
}

export function CardsPage() {
  const { accessToken, logout, user } = useAuth();
  const [cards, setCards] = useState<Card[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [selectedType, setSelectedType] = useState<CardType | "">("");
  const [selectedTier, setSelectedTier] = useState<CardTier>("REGULAR");
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [actionCardId, setActionCardId] = useState<string | null>(null);
  const [deletingCardId, setDeletingCardId] = useState<string | null>(null);
  const [revealedCardIds, setRevealedCardIds] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);

  const activeWallets = useMemo(() => wallets.filter((wallet) => wallet.status === "ACTIVE"), [wallets]);
  const cardholderName = user ? `${user.first_name} ${user.last_name}`.trim() : "Card holder";
  const selectedReusableCardType = selectedType === "DEBIT" || selectedType === "CREDIT";
  const selectedAccountLinkedCard = selectedType === "DEBIT" || selectedType === "ONE_TIME";
  const debitWalletIds = useMemo(
    () =>
      new Set(
        cards
          .filter((card) => card.type === "DEBIT" && card.default_wallet_id)
          .map((card) => card.default_wallet_id as string),
      ),
    [cards],
  );
  const hasOneTimePaymentCard = useMemo(
    () => cards.some((card) => card.type === "ONE_TIME" && (card.status === "ACTIVE" || card.status === "FROZEN")),
    [cards],
  );
  const selectedAccountAlreadyHasDebit = selectedType === "DEBIT" && selectedWalletId !== "" && debitWalletIds.has(selectedWalletId);
  const selectedOneTimeAlreadyExists = selectedType === "ONE_TIME" && hasOneTimePaymentCard;
  const cardLimitReached = cards.length >= MAX_CARDS;
  const canCreateCard =
    selectedType !== "" &&
    !cardLimitReached &&
    (!selectedAccountLinkedCard || selectedWalletId !== "") &&
    !selectedAccountAlreadyHasDebit &&
    !selectedOneTimeAlreadyExists;

  async function loadCardsData(token: string) {
    setIsLoading(true);
    setError(null);
    try {
      const [cardsResponse, walletsResponse] = await Promise.all([
        apiRequest<Card[]>("/cards", { token }),
        apiRequest<Wallet[]>("/wallets", { token }),
      ]);
      setCards(cardsResponse);
      setWallets(walletsResponse);
      const mainWallet = walletsResponse.find((wallet) => wallet.is_main && wallet.status === "ACTIVE");
      setSelectedWalletId((current) => current || mainWallet?.id || "");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setCards([]);
      setWallets([]);
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
    if (!accessToken || isSaving || !canCreateCard || selectedType === "") return;
    setIsSaving(true);
    setError(null);
    try {
      const card = await apiRequest<Card>("/cards", {
        method: "POST",
        token: accessToken,
        body: {
          type: selectedType,
          tier: selectedReusableCardType ? selectedTier : null,
          default_wallet_id: selectedAccountLinkedCard ? selectedWalletId || null : null,
        },
      });
      setCards((current) => [card, ...current]);
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

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Card controls</span>
        </div>
        <div className="card-control-layout">
          <div className="card-control-form">
            <label>
              Card type
              <select
                value={selectedType}
                onChange={(event) => {
                  const nextType = event.target.value as CardType | "";
                  setSelectedType(nextType);
                  if (nextType === "ONE_TIME") {
                    setSelectedTier("REGULAR");
                  }
                }}
              >
                <option value="">Select card type</option>
                {CARD_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {formatCardType(type)}
                  </option>
                ))}
              </select>
            </label>
            {selectedAccountLinkedCard && (
              <label>
                Account
                <select value={selectedWalletId} onChange={(event) => setSelectedWalletId(event.target.value)}>
                  <option value="">Select account</option>
                  {activeWallets.map((wallet) => {
                    const debitAlreadyExists = selectedType === "DEBIT" && debitWalletIds.has(wallet.id);
                    return (
                      <option key={wallet.id} value={wallet.id} disabled={debitAlreadyExists}>
                        {walletOptionLabel(wallet, debitAlreadyExists)}
                      </option>
                    );
                  })}
                </select>
              </label>
            )}
            {selectedReusableCardType && (
              <div className="compact-tier-picker" aria-label="Card tier">
                <span className="eyebrow">Tier</span>
                <div className="compact-tier-picker__options">
                  {CARD_TIER_PRODUCT_LIST.map((tier) => {
                    const tierValue = tier.name.toUpperCase() as CardTier;
                    const isSelected = tierValue === selectedTier;
                    return (
                      <button
                        type="button"
                        className={`compact-tier-option${isSelected ? " active" : ""}`}
                        key={tier.name}
                        onClick={() => setSelectedTier(tierValue)}
                        aria-pressed={isSelected}
                      >
                        <strong>{tier.name}</strong>
                        <span>{selectedType === "DEBIT" ? tier.debit : tier.credit}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {selectedType === "" && (
              <div className="selected-tier-overview">
                <span className="eyebrow">Card setup</span>
                <strong>Select a card type</strong>
                <span>Account selection appears only for debit and one-time payment cards.</span>
              </div>
            )}
            <button type="button" onClick={createCard} disabled={isSaving || !canCreateCard}>
              {isSaving
                ? "Creating..."
                : cardLimitReached
                  ? "Card limit reached"
                : selectedType === ""
                  ? "Select card type"
                : selectedAccountAlreadyHasDebit
                  ? "Account already has debit"
                : selectedOneTimeAlreadyExists
                  ? "One-time card already exists"
                : selectedAccountLinkedCard && !selectedWalletId
                  ? "Select account"
                : selectedReusableCardType
                  ? `Create ${CARD_TIER_LABELS[selectedTier]} ${formatCardType(selectedType)}`
                  : "Create one-time card"}
            </button>
          </div>

          {selectedReusableCardType ? (
            <aside className="card-choice-explainer">
              <span className="eyebrow">Selection details</span>
              <strong>
                {CARD_TIER_LABELS[selectedTier]} {formatCardType(selectedType)}
              </strong>
              <p>{selectedTierDetails(selectedType, selectedTier)}</p>
              <div className="card-choice-explainer__chips">
                {CARD_TIER_REWARDS[selectedTier].slice(0, 3).map((reward) => (
                  <span key={reward}>{reward}</span>
                ))}
              </div>
              <small>
                {selectedType === "DEBIT"
                  ? "Debit cards spend from the selected linked account."
                  : `Available credit preview: ${formatCurrencyAmount(CREDIT_CARD_LIMITS[selectedTier])}`}
              </small>
            </aside>
          ) : selectedType === "ONE_TIME" ? (
            <aside className="card-choice-explainer">
              <span className="eyebrow">Selection details</span>
              <strong>One-time payment card</strong>
              <p>Single-use payment card linked to the selected account. It is intended for temporary or one-off payments.</p>
              <small>One-time cards do not use tier levels.</small>
            </aside>
          ) : (
            <div />
          )}
        </div>
        {cardLimitReached && (
          <p className="eyebrow" style={{ margin: "0.85rem 0 0" }}>
            You can have up to {MAX_CARDS} cards.
          </p>
        )}
        {error && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{error}</p>}
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
              const isRevealed = revealedCardIds.has(card.id);
              const isAccountLinkedCard = card.type === "DEBIT" || card.type === "ONE_TIME";
              const isCreditCard = card.type === "CREDIT";
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
                      <div className="eyebrow">{isCreditCard ? "Available credit" : "Linked account"}</div>
                      <div className="card-panel__value">
                        {isCreditCard
                          ? creditAvailableAmount(card)
                          : isAccountLinkedCard
                            ? wallet
                              ? walletDisplayName(wallet)
                              : "Not linked"
                            : "Not required"}
                      </div>
                      {wallet && isAccountLinkedCard && (
                        <div className="card-panel__subvalue">Wallet balance {formatWalletBalance(wallet)}</div>
                      )}
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
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
