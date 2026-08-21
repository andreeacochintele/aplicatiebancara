import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Eye, EyeOff, Lock, Trash2, Unlock } from "lucide-react";

import { ApiError, apiRequest } from "../api/apiClient";
import { cardTierRewardBullets } from "../config/rewardPolicy";
import { useAuth } from "../hooks/useAuth";
import type { Card, CardTier, CardType, Transaction, Wallet } from "../types";

const CARD_TYPES: CardType[] = ["DEBIT", "CREDIT", "ONE_TIME"];
const MAX_CARDS = 5;
// Single source of truth for the reward numbers lives in config/rewardPolicy.ts
// (shared with RewardsPage.tsx) - this just maps it into the shape this page renders.
const CARD_TIER_REWARDS: Record<CardTier, string[]> = {
  REGULAR: cardTierRewardBullets("REGULAR"),
  GOLD: cardTierRewardBullets("GOLD"),
  PLATINUM: cardTierRewardBullets("PLATINUM"),
};
const CARD_TIER_LABELS: Record<CardTier, string> = {
  REGULAR: "Regular",
  GOLD: "Gold",
  PLATINUM: "Platinum",
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
const MOCK_CARD_MERCHANTS = ["Carrefour", "Netflix", "OMV", "Starbucks", "eMAG", "Uber"];
type CreditPaymentSourceType = "ACCOUNT" | "DEBIT_CARD";
type CreditPaymentAmountMode = "FULL_BALANCE" | "CUSTOM";

interface CardTransactionDisplay {
  id: string;
  description: string;
  created_at: string;
  amount: string;
  currency: string;
  status: string;
}

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

function creditStatementBalance(card: Card): number {
  return Number(card.credit_account?.used_amount ?? "0");
}

function creditAvailableBalance(card: Card, balanceDue: number): number {
  const creditLimit = Number(card.credit_account?.credit_limit ?? CREDIT_CARD_LIMITS[card.tier ?? "REGULAR"]);
  return Math.max(0, creditLimit - balanceDue);
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

function formatTransactionType(type: string): string {
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatTransactionDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function mockCardTransactions(card: Card, wallet?: Wallet): CardTransactionDisplay[] {
  const seed = Number(card.last_four) || card.id.length;
  const currency = wallet?.currency ?? "RON";
  const multiplier = card.tier === "PLATINUM" ? 1.35 : card.tier === "GOLD" ? 1.15 : 1;
  const count = card.type === "ONE_TIME" ? 1 : 3;

  return Array.from({ length: count }, (_, index) => {
    const merchant = MOCK_CARD_MERCHANTS[(seed + index) % MOCK_CARD_MERCHANTS.length];
    const amount = ((18 + ((seed + index * 17) % 140)) * multiplier).toFixed(2);
    const date = new Date();
    date.setDate(date.getDate() - (index * 3 + 1));

    return {
      id: `mock-${card.id}-${index}`,
      description: `${merchant} card payment`,
      created_at: date.toISOString(),
      amount,
      currency,
      status: index === 0 ? "COMPLETED" : "SETTLED",
    };
  });
}

export function CardsPage() {
  const { accessToken, logout, user } = useAuth();
  const [cards, setCards] = useState<Card[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [selectedType, setSelectedType] = useState<CardType | "">("");
  const [selectedTier, setSelectedTier] = useState<CardTier>("REGULAR");
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [actionCardId, setActionCardId] = useState<string | null>(null);
  const [deletingCardId, setDeletingCardId] = useState<string | null>(null);
  const [revealedCardIds, setRevealedCardIds] = useState<Set<string>>(() => new Set());
  const [expandedTransactionCardIds, setExpandedTransactionCardIds] = useState<Set<string>>(() => new Set());
  const [paymentPanelCardId, setPaymentPanelCardId] = useState<string | null>(null);
  const [paymentSourceType, setPaymentSourceType] = useState<CreditPaymentSourceType>("ACCOUNT");
  const [paymentSourceId, setPaymentSourceId] = useState("");
  const [paymentAmountMode, setPaymentAmountMode] = useState<CreditPaymentAmountMode>("FULL_BALANCE");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentMessage, setPaymentMessage] = useState<string | null>(null);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [creditBalanceOverrides, setCreditBalanceOverrides] = useState<Record<string, number>>({});
  const [localCardActivity, setLocalCardActivity] = useState<Record<string, CardTransactionDisplay[]>>({});
  const [error, setError] = useState<string | null>(null);

  const activeWallets = useMemo(() => wallets.filter((wallet) => wallet.status === "ACTIVE"), [wallets]);
  const activeDebitCards = useMemo(
    () => cards.filter((card) => card.type === "DEBIT" && card.status === "ACTIVE" && card.default_wallet_id),
    [cards],
  );
  const debitRepresentedWalletIds = useMemo(
    () => new Set(activeDebitCards.map((card) => card.default_wallet_id).filter((walletId): walletId is string => Boolean(walletId))),
    [activeDebitCards],
  );
  const directPaymentWallets = useMemo(
    () => activeWallets.filter((wallet) => !debitRepresentedWalletIds.has(wallet.id)),
    [activeWallets, debitRepresentedWalletIds],
  );
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
      try {
        const transactionsResponse = await apiRequest<Transaction[]>("/transactions", { token });
        setTransactions(transactionsResponse);
      } catch {
        setTransactions([]);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setCards([]);
      setWallets([]);
      setTransactions([]);
      setError(err instanceof ApiError ? err.message : "Could not load cards.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken) return;
    void loadCardsData(accessToken);
  }, [accessToken, logout]);

  useEffect(() => {
    if (!paymentPanelCardId || paymentSourceId === "") return;
    const paymentCard = cards.find((card) => card.id === paymentPanelCardId);
    const currency = paymentCard?.credit_account?.currency ?? "RON";
    const sourceStillExists =
      paymentSourceType === "ACCOUNT"
        ? directPaymentWallets.some((wallet) => wallet.id === paymentSourceId && wallet.currency === currency)
        : activeDebitCards.some((card) => {
            const linkedWallet = wallets.find((wallet) => wallet.id === card.default_wallet_id);
            return card.id === paymentSourceId && linkedWallet?.currency === currency;
          });

    if (!sourceStillExists) {
      const nextAccount = directPaymentWallets.find((wallet) => wallet.currency === currency);
      const nextDebitCard = activeDebitCards.find((card) => {
        const linkedWallet = wallets.find((wallet) => wallet.id === card.default_wallet_id);
        return linkedWallet?.currency === currency;
      });
      setPaymentSourceType(nextAccount ? "ACCOUNT" : "DEBIT_CARD");
      setPaymentSourceId(nextAccount?.id ?? nextDebitCard?.id ?? "");
      setPaymentMessage(null);
      setPaymentError(null);
    }
  }, [activeDebitCards, cards, directPaymentWallets, paymentPanelCardId, paymentSourceId, paymentSourceType, wallets]);

  async function createCard() {
    if (!accessToken || isSaving || !canCreateCard) return;
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
      setExpandedTransactionCardIds((current) => {
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

  function toggleCardTransactions(cardId: string) {
    setExpandedTransactionCardIds((current) => {
      const next = new Set(current);
      if (next.has(cardId)) {
        next.delete(cardId);
      } else {
        next.add(cardId);
      }
      return next;
    });
  }

  function resetPaymentForm(nextCardId: string | null, currency = "RON") {
    const nextAccount = directPaymentWallets.find((wallet) => wallet.currency === currency);
    const nextDebitCard = activeDebitCards.find((card) => {
      const linkedWallet = wallets.find((wallet) => wallet.id === card.default_wallet_id);
      return linkedWallet?.currency === currency;
    });
    setPaymentPanelCardId(nextCardId);
    setPaymentSourceType(nextAccount ? "ACCOUNT" : "DEBIT_CARD");
    setPaymentSourceId(nextAccount?.id ?? nextDebitCard?.id ?? "");
    setPaymentAmountMode("FULL_BALANCE");
    setPaymentAmount("");
    setPaymentMessage(null);
    setPaymentError(null);
  }

  function togglePaymentPanel(card: Card) {
    resetPaymentForm(paymentPanelCardId === card.id ? null : card.id, card.credit_account?.currency ?? "RON");
  }

  function paymentSourceWalletId(): string {
    if (paymentSourceType === "ACCOUNT") return paymentSourceId;
    return activeDebitCards.find((card) => card.id === paymentSourceId)?.default_wallet_id ?? "";
  }

  function paymentSourceLabel(): string {
    if (paymentSourceType === "ACCOUNT") {
      const wallet = wallets.find((item) => item.id === paymentSourceId);
      return wallet ? walletDisplayName(wallet) : "selected account";
    }
    const debitCard = activeDebitCards.find((card) => card.id === paymentSourceId);
    const wallet = debitCard ? wallets.find((item) => item.id === debitCard.default_wallet_id) : undefined;
    return debitCard ? `Debit **** ${debitCard.last_four}${wallet ? ` from ${walletDisplayName(wallet)}` : ""}` : "selected debit card";
  }

  async function submitCreditCardPayment(card: Card) {
    if (!accessToken) return;
    const sourceWalletId = paymentSourceWalletId();
    const sourceWallet = wallets.find((wallet) => wallet.id === sourceWalletId);
    const sourceDebitCard = paymentSourceType === "DEBIT_CARD" ? activeDebitCards.find((sourceCard) => sourceCard.id === paymentSourceId) : null;
    const currentBalanceDue = creditBalanceOverrides[card.id] ?? creditStatementBalance(card);
    const amount = paymentAmountMode === "FULL_BALANCE" ? currentBalanceDue : Number(paymentAmount);

    setPaymentMessage(null);
    setPaymentError(null);

    if (!sourceWallet) {
      setPaymentError("Choose a payment source.");
      return;
    }
    if (sourceWallet.currency !== (card.credit_account?.currency ?? "RON")) {
      setPaymentError("Choose a source in the same currency as the credit card balance.");
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setPaymentError("Enter a valid payment amount.");
      return;
    }
    if (amount > Number(sourceWallet.available_balance)) {
      setPaymentError("The selected source does not have enough available balance.");
      return;
    }
    if (amount > currentBalanceDue) {
      setPaymentError("Payment is higher than the current card balance.");
      return;
    }

    const nextBalanceDue = Math.max(0, currentBalanceDue - amount);
    try {
      await apiRequest<Transaction>("/transactions/credit-card-repayment", {
        method: "POST",
        token: accessToken,
        body: {
          card_id: card.id,
          source_wallet_id: sourceWallet.id,
          amount: amount.toFixed(2),
        },
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setPaymentError(err instanceof ApiError ? err.message : "Could not pay credit card.");
      return;
    }

    setWallets((current) =>
      current.map((wallet) =>
        wallet.id === sourceWallet.id
          ? { ...wallet, available_balance: Math.max(0, Number(wallet.available_balance) - amount).toFixed(2) }
          : wallet,
      ),
    );
    setCards((current) =>
      current.map((item) =>
        item.id === card.id && item.credit_account
          ? {
              ...item,
              credit_account: {
                ...item.credit_account,
                used_amount: nextBalanceDue.toFixed(2),
                available_credit: creditAvailableBalance(item, nextBalanceDue).toFixed(2),
              },
            }
          : item,
      ),
    );
    setCreditBalanceOverrides((current) => ({ ...current, [card.id]: nextBalanceDue }));
    setLocalCardActivity((current) => {
      const paidAt = new Date().toISOString();
      const creditActivity: CardTransactionDisplay = {
        id: `payment-${card.id}-${paidAt}`,
        description: "Credit card payment received",
        created_at: paidAt,
        amount: amount.toFixed(2),
        currency: "RON",
        status: "COMPLETED",
      };
      const next = { ...current, [card.id]: [creditActivity, ...(current[card.id] ?? [])] };

      if (sourceDebitCard) {
        const debitActivity: CardTransactionDisplay = {
          id: `payment-source-${sourceDebitCard.id}-${paidAt}`,
          description: `Payment to credit card **** ${card.last_four}`,
          created_at: paidAt,
          amount: amount.toFixed(2),
          currency: sourceWallet.currency,
          status: "COMPLETED",
        };
        next[sourceDebitCard.id] = [debitActivity, ...(current[sourceDebitCard.id] ?? [])];
      }

      return next;
    });
    setPaymentAmount("");
    setPaymentMessage(`${formatCurrencyAmount(amount, sourceWallet.currency)} paid from ${paymentSourceLabel()}.`);
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Card controls</span>
        </div>
        <div className={`card-control-layout${selectedReusableCardType ? "" : " card-control-layout--single"}`}>
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

          {selectedReusableCardType && (
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
              const isTransactionsExpanded = expandedTransactionCardIds.has(card.id);
              const cardTransactions = transactions
                .filter((transaction) => transaction.card_id === card.id)
                .sort((first, second) => new Date(second.created_at).getTime() - new Date(first.created_at).getTime());
              const cardTransactionRows =
                cardTransactions.length > 0
                  ? cardTransactions.map((transaction) => ({
                      id: transaction.id,
                      description: transaction.description || formatTransactionType(transaction.type),
                      created_at: transaction.created_at,
                      amount: transaction.amount,
                      currency: transaction.currency,
                      status: transaction.status,
                    }))
                  : mockCardTransactions(card, wallet);
              const cardActivityRows = [...(localCardActivity[card.id] ?? []), ...cardTransactionRows];
              const isShowingPlaceholderTransactions = cardTransactions.length === 0 && !localCardActivity[card.id]?.length;
              const isAccountLinkedCard = card.type === "DEBIT" || card.type === "ONE_TIME";
              const isCreditCard = card.type === "CREDIT";
              const creditBalanceDue = creditBalanceOverrides[card.id] ?? creditStatementBalance(card);
              const creditAvailable = creditAvailableBalance(card, creditBalanceDue);
              const creditAccountCurrency = card.credit_account?.currency ?? "RON";
              const isPaymentPanelOpen = paymentPanelCardId === card.id;
              const paymentSourceOptions = [
                ...directPaymentWallets
                  .filter((sourceWallet) => sourceWallet.currency === creditAccountCurrency)
                  .map((sourceWallet) => ({
                    value: `ACCOUNT:${sourceWallet.id}`,
                    walletId: sourceWallet.id,
                    label: `${walletDisplayName(sourceWallet)} account`,
                  })),
                ...activeDebitCards
                  .map((debitCard) => {
                    const linkedWallet = wallets.find((item) => item.id === debitCard.default_wallet_id);
                    return {
                      value: `DEBIT_CARD:${debitCard.id}`,
                      walletId: debitCard.default_wallet_id ?? "",
                      label: `Debit **** ${debitCard.last_four}${linkedWallet ? ` - ${walletDisplayName(linkedWallet)}` : ""}`,
                      currency: linkedWallet?.currency,
                    };
                  })
                  .filter((source) => source.currency === creditAccountCurrency),
              ];
              const selectedPaymentWalletId =
                paymentSourceType === "ACCOUNT"
                  ? paymentSourceId
                  : activeDebitCards.find((debitCard) => debitCard.id === paymentSourceId)?.default_wallet_id;
              const selectedPaymentWallet = wallets.find((item) => item.id === selectedPaymentWalletId);
              const selectedPaymentSourceValue = paymentSourceId ? `${paymentSourceType}:${paymentSourceId}` : "";
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
                          ? formatCurrencyAmount(creditAvailable, creditAccountCurrency)
                          : isAccountLinkedCard
                            ? wallet
                              ? walletDisplayName(wallet)
                              : "Not linked"
                            : "Not required"}
                      </div>
                      {wallet && isAccountLinkedCard && (
                        <div className="card-panel__subvalue">Wallet balance {formatWalletBalance(wallet)}</div>
                      )}
                      {isCreditCard && (
                        <div className="card-panel__subvalue">
                          Balance due {formatCurrencyAmount(creditBalanceDue, creditAccountCurrency)}
                        </div>
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

                  {isCreditCard && (
                    <>
                      <button
                        type="button"
                        className="card-panel__payment-toggle"
                        onClick={() => togglePaymentPanel(card)}
                        aria-expanded={isPaymentPanelOpen}
                      >
                        {isPaymentPanelOpen ? "Close payment" : "Make a payment"}
                      </button>

                      {isPaymentPanelOpen && (
                        <div className="credit-card-payment">
                          <div className="credit-card-payment__summary">
                            <div>
                              <span>Card balance</span>
                              <strong>{formatCurrencyAmount(creditBalanceDue, creditAccountCurrency)}</strong>
                            </div>
                            <div>
                              <span>Available after payment</span>
                              <strong>
                                {formatCurrencyAmount(
                                  creditAvailableBalance(
                                    card,
                                    Math.max(0, creditBalanceDue - (paymentAmountMode === "FULL_BALANCE" ? creditBalanceDue : Number(paymentAmount) || 0)),
                                  ),
                                  creditAccountCurrency,
                                )}
                              </strong>
                            </div>
                          </div>

                          <div className="credit-card-payment__grid">
                            <label>
                              Pay from
                              <select
                                value={selectedPaymentSourceValue}
                                disabled={paymentSourceOptions.length === 0}
                                onChange={(event) => {
                                  const [nextType, nextId] = event.target.value.split(":") as [CreditPaymentSourceType, string];
                                  setPaymentSourceType(nextType);
                                  setPaymentSourceId(nextId ?? "");
                                  setPaymentError(null);
                                  setPaymentMessage(null);
                                }}
                              >
                                {paymentSourceOptions.length === 0 ? (
                                  <option value="">No payment source available</option>
                                ) : (
                                  paymentSourceOptions.map((source) => (
                                    <option key={source.value} value={source.value}>
                                      {source.label}
                                    </option>
                                  ))
                                )}
                              </select>
                              {selectedPaymentWallet && (
                                <small className="credit-card-payment__source-balance">
                                  Available {formatWalletBalance(selectedPaymentWallet)}
                                </small>
                              )}
                            </label>

                            <div className="credit-card-payment__amount">
                              <span>Amount</span>
                              <div className="credit-card-payment__amount-options">
                                <label>
                                  <input
                                    type="radio"
                                    name={`credit-payment-amount-${card.id}`}
                                    checked={paymentAmountMode === "FULL_BALANCE"}
                                    onChange={() => {
                                      setPaymentAmountMode("FULL_BALANCE");
                                      setPaymentError(null);
                                      setPaymentMessage(null);
                                    }}
                                  />
                                  Whole balance
                                </label>
                                <label>
                                  <input
                                    type="radio"
                                    name={`credit-payment-amount-${card.id}`}
                                    checked={paymentAmountMode === "CUSTOM"}
                                    onChange={() => {
                                      setPaymentAmountMode("CUSTOM");
                                      setPaymentError(null);
                                      setPaymentMessage(null);
                                    }}
                                  />
                                  Enter amount
                                </label>
                              </div>
                              {paymentAmountMode === "CUSTOM" ? (
                                <input
                                  type="number"
                                  min="0"
                                  step="0.01"
                                  value={paymentAmount}
                                  onChange={(event) => {
                                    setPaymentAmount(event.target.value);
                                    setPaymentError(null);
                                    setPaymentMessage(null);
                                  }}
                                  placeholder="0.00"
                                />
                              ) : (
                                <strong>{formatCurrencyAmount(creditBalanceDue, creditAccountCurrency)}</strong>
                              )}
                            </div>
                          </div>

                          <button type="button" className="credit-card-payment__submit" onClick={() => submitCreditCardPayment(card)}>
                            Pay credit card
                          </button>
                          {paymentError && <div className="credit-card-payment__error">{paymentError}</div>}
                          {paymentMessage && <div className="credit-card-payment__message">{paymentMessage}</div>}
                        </div>
                      )}
                    </>
                  )}

                  <button
                    type="button"
                    className="card-panel__details-toggle"
                    onClick={() => toggleCardTransactions(card.id)}
                    aria-expanded={isTransactionsExpanded}
                  >
                    <span>{isTransactionsExpanded ? "Retract" : "Show more"}</span>
                    <span className="card-panel__details-icon">
                      {isTransactionsExpanded ? <ChevronUp size={16} strokeWidth={2.2} /> : <ChevronDown size={16} strokeWidth={2.2} />}
                    </span>
                  </button>

                  {isTransactionsExpanded && (
                    <div className="card-transactions">
                      {isShowingPlaceholderTransactions && (
                        <div className="card-transactions__note">Recent card activity</div>
                      )}
                      {cardActivityRows.slice(0, 5).map((transaction) => (
                          <div className="card-transaction-row" key={transaction.id}>
                            <div>
                              <strong>{transaction.description}</strong>
                              <span>{formatTransactionDate(transaction.created_at)}</span>
                            </div>
                            <div>
                              <strong>
                                {Number(transaction.amount).toLocaleString(undefined, {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}{" "}
                                {transaction.currency}
                              </strong>
                              <span>{transaction.status}</span>
                            </div>
                          </div>
                        ))}
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
