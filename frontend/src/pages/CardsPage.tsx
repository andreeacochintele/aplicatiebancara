import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Copy, Eye, EyeOff, Lock, Settings, Trash2, Unlock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ApiError, apiRequest } from "../api/apiClient";
import { cardTierRewardBullets } from "../config/rewardPolicy";
import { useAuth } from "../hooks/useAuth";
import type { Card, CardSensitiveDetails, CardTier, CardType, CreditApplication, Transaction, Wallet } from "../types";

const CARD_TYPES: CardType[] = ["DEBIT", "CREDIT", "ONE_TIME"];
const CREDIT_CARD_CURRENCIES = ["RON", "EUR", "USD", "GBP"];
const CURRENT_ACCOUNT_CURRENCIES = [
  "RON", "EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "PLN", "TRY",
  "BRL", "CNY", "CZK", "DKK", "HKD", "HUF", "IDR", "ILS", "INR", "ISK",
  "KRW", "MXN", "MYR", "NOK", "NZD", "PHP", "SEK", "SGD", "THB", "ZAR",
];
const MAX_CARDS_PER_TYPE = 5;
type CreditIssueMode = "SECURED" | "ADMIN_REVIEW";
type DebitIssueMode = "EXISTING_ACCOUNT" | "NEW_ACCOUNT";
// Single source of truth for the reward numbers lives in config/rewardPolicy.ts
// (shared with RewardsPage.tsx) - this just maps it into the shape this page renders.
const CARD_TIER_REWARDS: Record<CardTier, string[]> = {
  REGULAR: cardTierRewardBullets("REGULAR"),
  GOLD: cardTierRewardBullets("GOLD"),
  PLATINUM: cardTierRewardBullets("PLATINUM"),
};
const CREDIT_CARD_LIMITS: Record<CardTier, number> = {
  REGULAR: 5000,
  GOLD: 15000,
  PLATINUM: 30000,
};

function tierLabel(tier: CardTier, t: (key: string) => string): string {
  if (tier === "REGULAR") return t("cards.regular");
  if (tier === "GOLD") return t("cards.gold");
  return t("cards.platinum");
}

function cardTierProductList(t: (key: string) => string) {
  return [
    {
      name: "REGULAR" as CardTier,
      label: t("cards.regular"),
      description: t("cards.regularDescription"),
      debit: t("cards.standardDebit"),
      credit: t("cards.standardCredit"),
      rewards: CARD_TIER_REWARDS.REGULAR,
    },
    {
      name: "GOLD" as CardTier,
      label: t("cards.gold"),
      description: t("cards.goldDescription"),
      debit: t("cards.goldDebit"),
      credit: t("cards.goldCredit"),
      rewards: CARD_TIER_REWARDS.GOLD,
    },
    {
      name: "PLATINUM" as CardTier,
      label: t("cards.platinum"),
      description: t("cards.platinumDescription"),
      debit: t("cards.platinumDebit"),
      credit: t("cards.platinumCredit"),
      rewards: CARD_TIER_REWARDS.PLATINUM,
    },
  ];
}
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
  direction: "in" | "out";
}

function formatCardType(type: CardType, t: (key: string, options?: Record<string, unknown>) => string): string {
  const fallback = type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
  return t(`cards.cardType.${type}`, { defaultValue: fallback });
}

function statusClass(status: Card["status"]): string {
  if (status === "ACTIVE") return "tag tag--accent";
  if (status === "FROZEN") return "tag tag--warning";
  return "tag tag--neutral";
}

function formatCardTier(tier: CardTier | null, t: (key: string) => string): string {
  return tier ? tierLabel(tier, t) : t("cards.noTier");
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
  const base = wallet.nickname ? `${wallet.currency} — ${wallet.nickname}` : wallet.currency;
  return `${base}${wallet.is_main ? " - Main" : ""}`;
}

function walletOptionLabel(wallet: Wallet, debitAlreadyExists: boolean, t: (key: string, options?: Record<string, unknown>) => string): string {
  const balance = Number(wallet.available_balance).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return debitAlreadyExists
    ? t("cards.debitAlreadyExists", { label: walletDisplayName(wallet) })
    : `${walletDisplayName(wallet)} - ${balance}`;
}

function selectedTierDetails(type: CardType | "", tier: CardTier, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (type === "DEBIT") return cardTierProductList(t).find((item) => item.name === tier)?.description ?? "";
  if (type === "CREDIT") return t("cards.creditCardTierHint");
  return "";
}

function formatTransactionType(type: string, t: (key: string, options?: Record<string, unknown>) => string): string {
  const fallback = type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
  return t(`common.txType.${type}`, { defaultValue: fallback });
}

function formatTransactionDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function mockCardTransactions(card: Card, t: (key: string, options?: Record<string, unknown>) => string, wallet?: Wallet): CardTransactionDisplay[] {
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
      description: t("cards.mockCardPayment", { merchant }),
      created_at: date.toISOString(),
      amount,
      currency,
      status: index === 0 ? "COMPLETED" : "SETTLED",
      direction: "out",
    };
  });
}

function cardTransactionDirection(transaction: Transaction, card: Card): "in" | "out" {
  if (card.type === "CREDIT") {
    const description = transaction.description?.toLowerCase() ?? "";
    return transaction.type === "LOAN_PAYMENT" && description.includes("credit card repayment") ? "in" : "out";
  }
  if (card.default_wallet_id && transaction.destination_wallet_id === card.default_wallet_id) return "in";
  return "out";
}

export function CardsPage() {
  const { t } = useTranslation();
  const { accessToken, logout, user } = useAuth();
  const CARD_TIER_PRODUCT_LIST = useMemo(() => cardTierProductList(t), [t]);
  const [cards, setCards] = useState<Card[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [selectedType, setSelectedType] = useState<CardType | "">("");
  const [selectedTier, setSelectedTier] = useState<CardTier>("REGULAR");
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const [debitIssueMode, setDebitIssueMode] = useState<DebitIssueMode>("EXISTING_ACCOUNT");
  const [selectedDebitCurrency, setSelectedDebitCurrency] = useState("RON");
  const [selectedCreditCurrency, setSelectedCreditCurrency] = useState("RON");
  const [creditIssueMode, setCreditIssueMode] = useState<CreditIssueMode>("SECURED");
  const [collateralCardId, setCollateralCardId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [actionCardId, setActionCardId] = useState<string | null>(null);
  const [deletingCardId, setDeletingCardId] = useState<string | null>(null);
  const [revealedCardIds, setRevealedCardIds] = useState<Set<string>>(() => new Set());
  const [cardDetailsById, setCardDetailsById] = useState<Record<string, CardSensitiveDetails>>({});
  const [pinPromptCardId, setPinPromptCardId] = useState<string | null>(null);
  const [pinSettingsCardIds, setPinSettingsCardIds] = useState<Set<string>>(() => new Set());
  const [pinInputs, setPinInputs] = useState<Record<string, string>>({});
  const [pinSettingsInputs, setPinSettingsInputs] = useState<Record<string, string>>({});
  const [pinActionCardId, setPinActionCardId] = useState<string | null>(null);
  const [cardSecurityErrors, setCardSecurityErrors] = useState<Record<string, string>>({});
  const [cardSecurityMessages, setCardSecurityMessages] = useState<Record<string, string>>({});
  const [copiedCardId, setCopiedCardId] = useState<string | null>(null);
  const [expandedTransactionCardIds, setExpandedTransactionCardIds] = useState<Set<string>>(() => new Set());
  const [paymentPanelCardId, setPaymentPanelCardId] = useState<string | null>(null);
  const [paymentSourceType, setPaymentSourceType] = useState<CreditPaymentSourceType>("ACCOUNT");
  const [paymentSourceId, setPaymentSourceId] = useState("");
  const [paymentAmountMode, setPaymentAmountMode] = useState<CreditPaymentAmountMode>("FULL_BALANCE");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentMessage, setPaymentMessage] = useState<string | null>(null);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [creditBalanceOverrides, setCreditBalanceOverrides] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
  const missingCurrentAccountCurrencies = useMemo(
    () => CURRENT_ACCOUNT_CURRENCIES.filter((currency) => !activeWallets.some((wallet) => wallet.currency === currency)),
    [activeWallets],
  );
  const cardholderName = user ? `${user.first_name} ${user.last_name}`.trim() : t("cards.cardHolder");
  const selectedReusableCardType = selectedType === "DEBIT" || selectedType === "CREDIT";
  const selectedAccountLinkedCard = selectedType === "DEBIT" || selectedType === "ONE_TIME";
  const collateralDebitCards = useMemo(
    () =>
      activeDebitCards
        .map((card) => ({ card, wallet: wallets.find((wallet) => wallet.id === card.default_wallet_id) }))
        .filter(
          (item): item is { card: Card; wallet: Wallet } =>
            Boolean(item.wallet) && item.wallet?.currency === selectedCreditCurrency,
        ),
    [activeDebitCards, selectedCreditCurrency, wallets],
  );
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
  const selectedAccountAlreadyHasDebit =
    selectedType === "DEBIT" &&
    debitIssueMode === "EXISTING_ACCOUNT" &&
    selectedWalletId !== "" &&
    debitWalletIds.has(selectedWalletId);
  const selectedOneTimeAlreadyExists = selectedType === "ONE_TIME" && hasOneTimePaymentCard;
  const debitNewAccountAlreadyExists =
    selectedType === "DEBIT" &&
    debitIssueMode === "NEW_ACCOUNT" &&
    activeWallets.some((wallet) => wallet.currency === selectedDebitCurrency);
  const hasNewDebitAccountCurrency = debitIssueMode !== "NEW_ACCOUNT" || missingCurrentAccountCurrencies.length > 0;
  const selectedCollateralSource = collateralDebitCards.find((item) => item.card.id === collateralCardId);
  const tierCreditAmount = CREDIT_CARD_LIMITS[selectedTier].toFixed(2);
  const parsedCreditAmount = CREDIT_CARD_LIMITS[selectedTier];
  const creditAmountIsValid = parsedCreditAmount > 0;
  const selectedCollateralHasFunds =
    selectedType !== "CREDIT" ||
    creditIssueMode !== "SECURED" ||
    (selectedCollateralSource !== undefined && Number(selectedCollateralSource.wallet.available_balance) >= parsedCreditAmount);
  const selectedTypeCardCount = selectedType === "" ? 0 : cards.filter((card) => card.type === selectedType).length;
  const cardLimitReached =
    selectedType === "DEBIT" || selectedType === "CREDIT" ? selectedTypeCardCount >= MAX_CARDS_PER_TYPE : false;
  const selectedTypeLabel = selectedType === "" ? t("cards.cardFallback") : formatCardType(selectedType, t);
  const canCreateCard =
    selectedType !== "" &&
    !cardLimitReached &&
    (!selectedAccountLinkedCard ||
      (selectedType === "DEBIT" && debitIssueMode === "NEW_ACCOUNT") ||
      selectedWalletId !== "") &&
    (selectedType !== "CREDIT" ||
      (creditAmountIsValid &&
        (creditIssueMode === "ADMIN_REVIEW" || (selectedCollateralSource !== undefined && selectedCollateralHasFunds)))) &&
    !selectedAccountAlreadyHasDebit &&
    !debitNewAccountAlreadyExists &&
    hasNewDebitAccountCurrency &&
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
      setError(err instanceof ApiError ? err.message : t("cards.couldNotLoadCards"));
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

  useEffect(() => {
    if (selectedType !== "CREDIT" || collateralCardId) return;
    setCollateralCardId(collateralDebitCards[0]?.card.id ?? "");
  }, [collateralCardId, collateralDebitCards, selectedType]);

  useEffect(() => {
    if (selectedType !== "DEBIT" || debitIssueMode !== "NEW_ACCOUNT") return;
    if (missingCurrentAccountCurrencies.includes(selectedDebitCurrency)) return;
    setSelectedDebitCurrency(missingCurrentAccountCurrencies[0] ?? "");
  }, [debitIssueMode, missingCurrentAccountCurrencies, selectedDebitCurrency, selectedType]);

  useEffect(() => {
    if (selectedType !== "CREDIT") return;
    if (collateralDebitCards.some(({ card }) => card.id === collateralCardId)) return;
    setCollateralCardId(collateralDebitCards[0]?.card.id ?? "");
  }, [collateralCardId, collateralDebitCards, selectedCreditCurrency, selectedType]);

  async function createCard() {
    if (!accessToken || isSaving || !canCreateCard) return;
    setIsSaving(true);
    setError(null);
    setNotice(null);
    try {
      if (selectedType === "CREDIT" && creditIssueMode === "ADMIN_REVIEW") {
        await apiRequest<CreditApplication>("/credit/applications", {
          method: "POST",
          token: accessToken,
          body: {
            type: "CREDIT_CARD",
            loan_product_type: null,
            requested_amount: tierCreditAmount,
            currency: selectedCreditCurrency,
            requested_term_months: null,
          },
        });
        setNotice("Credit card request sent for credit score evaluation.");
        return;
      }

      const card = await apiRequest<Card>("/cards", {
        method: "POST",
        token: accessToken,
        body: {
          type: selectedType,
          tier: selectedReusableCardType ? selectedTier : null,
          default_wallet_id:
            selectedAccountLinkedCard && !(selectedType === "DEBIT" && debitIssueMode === "NEW_ACCOUNT")
              ? selectedWalletId || null
              : null,
          new_wallet_currency: selectedType === "DEBIT" && debitIssueMode === "NEW_ACCOUNT" ? selectedDebitCurrency : null,
          currency: selectedType === "CREDIT" ? selectedCreditCurrency : null,
          collateral_wallet_id:
            selectedType === "CREDIT" && creditIssueMode === "SECURED"
              ? selectedCollateralSource?.wallet.id ?? null
              : null,
          collateral_amount: selectedType === "CREDIT" && creditIssueMode === "SECURED" ? tierCreditAmount : null,
        },
      });
      setCards((current) => [card, ...current]);
      setNotice(
        selectedType === "CREDIT"
          ? `Secured credit card created with ${parsedCreditAmount.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })} ${card.credit_account?.currency ?? selectedCreditCurrency} collateral.`
          : selectedType === "DEBIT" && debitIssueMode === "NEW_ACCOUNT"
            ? `${selectedDebitCurrency} current account created and linked to the debit card.`
          : null,
      );
      if (selectedType === "CREDIT" || (selectedType === "DEBIT" && debitIssueMode === "NEW_ACCOUNT")) {
        void loadCardsData(accessToken);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("cards.couldNotCreateCard"));
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
      setError(err instanceof ApiError ? err.message : t("cards.couldNotUpdateCard"));
    } finally {
      setActionCardId(null);
    }
  }

  async function deleteCard(card: Card) {
    if (!accessToken || deletingCardId) return;
    const confirmed = window.confirm(t("cards.deleteCardConfirm", { lastFour: card.last_four }));
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
      setCardDetailsById((current) => {
        const next = { ...current };
        delete next[card.id];
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
      setError(err instanceof ApiError ? err.message : t("cards.couldNotDeleteCard"));
    } finally {
      setDeletingCardId(null);
    }
  }

  function clearCardSecurityFeedback(cardId: string) {
    setCardSecurityErrors((current) => {
      const next = { ...current };
      delete next[cardId];
      return next;
    });
    setCardSecurityMessages((current) => {
      const next = { ...current };
      delete next[cardId];
      return next;
    });
  }

  function toggleCardReveal(card: Card) {
    setRevealedCardIds((current) => {
      const next = new Set(current);
      if (next.has(card.id)) {
        next.delete(card.id);
        return next;
      }
      if (cardDetailsById[card.id]) next.add(card.id);
      return next;
    });
    if (!cardDetailsById[card.id]) {
      if (card.has_pin) {
        setPinPromptCardId(card.id);
      } else {
        setPinSettingsCardIds((current) => {
          const next = new Set(current);
          next.add(card.id);
          return next;
        });
      }
      clearCardSecurityFeedback(card.id);
    }
  }

  function togglePinSettings(card: Card) {
    setPinSettingsCardIds((current) => {
      const next = new Set(current);
      if (next.has(card.id)) {
        next.delete(card.id);
      } else {
        next.add(card.id);
      }
      return next;
    });
    setPinSettingsInputs((current) => ({ ...current, [card.id]: "" }));
    clearCardSecurityFeedback(card.id);
  }

  async function saveCardPin(card: Card, pin: string): Promise<Card> {
    const updated = await apiRequest<Card>(`/cards/${card.id}/pin`, {
      method: "PATCH",
      token: accessToken,
      body: { pin },
    });
    const updatedWithPin = { ...updated, has_pin: true };
    setCards((current) => current.map((item) => (item.id === updated.id ? updatedWithPin : item)));
    return updatedWithPin;
  }

  async function updateCardPin(card: Card) {
    if (!accessToken || pinActionCardId) return;
    const pin = pinSettingsInputs[card.id] ?? "";
    clearCardSecurityFeedback(card.id);
    if (!/^\d{4}$/.test(pin)) {
      setCardSecurityErrors((current) => ({ ...current, [card.id]: t("cards.pinMustBe4Digits") }));
      return;
    }

    setPinActionCardId(card.id);
    try {
      await saveCardPin(card, pin);
      setPinSettingsInputs((current) => ({ ...current, [card.id]: "" }));
      setPinSettingsCardIds((current) => {
        const next = new Set(current);
        next.delete(card.id);
        return next;
      });
      setCardSecurityMessages((current) => ({ ...current, [card.id]: t("cards.pinSaved") }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setCardSecurityErrors((current) => ({
        ...current,
        [card.id]: err instanceof ApiError ? err.message : t("cards.couldNotSavePin"),
      }));
    } finally {
      setPinActionCardId(null);
    }
  }

  function showRevealedCardDetails(cardId: string, details: CardSensitiveDetails) {
    setCardDetailsById((current) => ({ ...current, [cardId]: details }));
    setRevealedCardIds((current) => {
      const next = new Set(current);
      next.add(cardId);
      return next;
    });
    setPinInputs((current) => ({ ...current, [cardId]: "" }));
    setPinPromptCardId(null);
  }

  async function revealCardDetails(card: Card) {
    if (!accessToken || pinActionCardId) return;
    const pin = pinInputs[card.id] ?? "";
    clearCardSecurityFeedback(card.id);
    if (!/^\d{4}$/.test(pin)) {
      setCardSecurityErrors((current) => ({ ...current, [card.id]: t("cards.enter4DigitPin") }));
      return;
    }

    setPinActionCardId(card.id);
    try {
      const details = await apiRequest<CardSensitiveDetails>(`/cards/${card.id}/reveal`, {
        method: "POST",
        token: accessToken,
        body: { pin },
      });
      showRevealedCardDetails(card.id, details);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      if (err instanceof ApiError && err.message.includes("Set a card PIN")) {
        try {
          await saveCardPin(card, pin);
          const details = await apiRequest<CardSensitiveDetails>(`/cards/${card.id}/reveal`, {
            method: "POST",
            token: accessToken,
            body: { pin },
          });
          showRevealedCardDetails(card.id, details);
          setCardSecurityMessages((current) => ({ ...current, [card.id]: t("cards.pinSaved") }));
          return;
        } catch (retryErr) {
          if (retryErr instanceof ApiError && retryErr.status === 401) {
            logout();
            return;
          }
          setPinSettingsCardIds((current) => {
            const next = new Set(current);
            next.add(card.id);
            return next;
          });
          setPinPromptCardId(null);
          setCards((current) => current.map((item) => (item.id === card.id ? { ...item, has_pin: false } : item)));
          setCardSecurityErrors((current) => ({
            ...current,
            [card.id]: retryErr instanceof ApiError || retryErr instanceof Error ? retryErr.message : t("cards.couldNotSavePin"),
          }));
          return;
        }
      }
      setCardSecurityErrors((current) => ({
        ...current,
        [card.id]: err instanceof ApiError || err instanceof Error ? err.message : t("cards.couldNotRevealDetails"),
      }));
    } finally {
      setPinActionCardId(null);
    }
  }

  function copyCardNumberFallback(cardNumber: string) {
    const textarea = document.createElement("textarea");
    textarea.value = cardNumber;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "0";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();

    try {
      return document.execCommand("copy");
    } finally {
      document.body.removeChild(textarea);
    }
  }

  async function copyCardNumber(card: Card) {
    const details = cardDetailsById[card.id];
    if (!details) {
      if (card.has_pin) {
        setPinPromptCardId(card.id);
        setCardSecurityErrors((current) => ({ ...current, [card.id]: t("cards.enterPinToCopy") }));
      } else {
        setPinSettingsCardIds((current) => {
          const next = new Set(current);
          next.add(card.id);
          return next;
        });
        setCardSecurityErrors((current) => ({ ...current, [card.id]: t("cards.setPinBeforeCopy") }));
      }
      return;
    }
    const cardNumber = details.mock_pan.replace(/\s/g, "");

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(cardNumber);
      } else if (!copyCardNumberFallback(cardNumber)) {
        throw new Error("Clipboard copy failed");
      }
      setCopiedCardId(card.id);
      setError(null);
      window.setTimeout(() => {
        setCopiedCardId((current) => (current === card.id ? null : current));
      }, 1600);
    } catch {
      if (copyCardNumberFallback(cardNumber)) {
        setCopiedCardId(card.id);
        setError(null);
        window.setTimeout(() => {
          setCopiedCardId((current) => (current === card.id ? null : current));
        }, 1600);
      } else {
        setError(t("cards.couldNotCopyCardNumber"));
      }
    }
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
      return wallet ? walletDisplayName(wallet) : t("cards.selectedAccount");
    }
    const debitCard = activeDebitCards.find((card) => card.id === paymentSourceId);
    const wallet = debitCard ? wallets.find((item) => item.id === debitCard.default_wallet_id) : undefined;
    return debitCard
      ? wallet
        ? t("cards.debitLastFourWithWallet", { lastFour: debitCard.last_four, wallet: walletDisplayName(wallet) })
        : t("cards.debitLastFour", { lastFour: debitCard.last_four })
      : t("cards.selectedDebitCard");
  }

  async function submitCreditCardPayment(card: Card) {
    if (!accessToken) return;
    const sourceWalletId = paymentSourceWalletId();
    const sourceWallet = wallets.find((wallet) => wallet.id === sourceWalletId);
    const currentBalanceDue = creditBalanceOverrides[card.id] ?? creditStatementBalance(card);
    const amount = paymentAmountMode === "FULL_BALANCE" ? currentBalanceDue : Number(paymentAmount);

    setPaymentMessage(null);
    setPaymentError(null);

    if (!sourceWallet) {
      setPaymentError(t("cards.chooseSource"));
      return;
    }
    if (sourceWallet.currency !== (card.credit_account?.currency ?? "RON")) {
      setPaymentError(t("cards.chooseSameCurrencySource"));
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setPaymentError(t("cards.enterValidAmount"));
      return;
    }
    if (amount > Number(sourceWallet.available_balance)) {
      setPaymentError(t("cards.insufficientBalance"));
      return;
    }
    if (amount > currentBalanceDue) {
      setPaymentError(t("cards.higherThanBalance"));
      return;
    }

    const nextBalanceDue = Math.max(0, currentBalanceDue - amount);
    let repaymentTransaction: Transaction;
    try {
      repaymentTransaction = await apiRequest<Transaction>("/transactions/credit-card-repayment", {
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
      setPaymentError(err instanceof ApiError ? err.message : t("cards.couldNotPayCreditCard"));
      return;
    }

    setTransactions((current) => [repaymentTransaction, ...current.filter((transaction) => transaction.id !== repaymentTransaction.id)]);
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
    setPaymentAmount("");
    setPaymentMessage(t("cards.paidVia", { amount: formatCurrencyAmount(amount, sourceWallet.currency), source: paymentSourceLabel() }));
    void loadCardsData(accessToken);
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("cards.cardControls")}</span>
        </div>
        <div className={`card-control-layout${selectedReusableCardType ? "" : " card-control-layout--single"}`}>
          <div className="card-control-form">
            <label>
              {t("cards.cardTypeLabel")}
              <select
                value={selectedType}
                onChange={(event) => {
                  const nextType = event.target.value as CardType | "";
                  setSelectedType(nextType);
                  if (nextType === "ONE_TIME") {
                    setSelectedTier("REGULAR");
                  }
                  if (nextType === "CREDIT") {
                    setSelectedWalletId("");
                  }
                  if (nextType === "DEBIT") {
                    setDebitIssueMode("EXISTING_ACCOUNT");
                  }
                }}
              >
                <option value="" disabled hidden>
                  {t("cards.selectCardType")}
                </option>
                {CARD_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {formatCardType(type, t)}
                  </option>
                ))}
              </select>
            </label>
            {selectedAccountLinkedCard && (
              <>
                {selectedType === "DEBIT" && (
                  <div className="credit-issue-controls debit-issue-controls">
                    <span className="eyebrow">{t("cards.currentAccount")}</span>
                    <div className="credit-issue-mode">
                      <button
                        type="button"
                        className={debitIssueMode === "EXISTING_ACCOUNT" ? "active" : ""}
                        onClick={() => setDebitIssueMode("EXISTING_ACCOUNT")}
                      >
                        {t("cards.existingAccount")}
                      </button>
                      <button
                        type="button"
                        className={debitIssueMode === "NEW_ACCOUNT" ? "active" : ""}
                        onClick={() => {
                          setDebitIssueMode("NEW_ACCOUNT");
                          setSelectedDebitCurrency((current) =>
                            missingCurrentAccountCurrencies.includes(current)
                              ? current
                              : missingCurrentAccountCurrencies[0] ?? "",
                          );
                        }}
                      >
                        {t("cards.newAccount")}
                      </button>
                    </div>
                    {debitIssueMode === "NEW_ACCOUNT" && (
                      <label>
                        {t("cards.currency")}
                        <select
                          value={selectedDebitCurrency}
                          onChange={(event) => setSelectedDebitCurrency(event.target.value)}
                        >
                          {missingCurrentAccountCurrencies.map((currency) => (
                            <option key={currency} value={currency}>
                              {currency}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                  </div>
                )}
                {(selectedType !== "DEBIT" || debitIssueMode === "EXISTING_ACCOUNT") && (
                  <label>
                    {t("cards.account")}
                    <select value={selectedWalletId} onChange={(event) => setSelectedWalletId(event.target.value)}>
                      <option value="">{t("cards.selectAccount")}</option>
                      {activeWallets.map((wallet) => {
                        const debitAlreadyExists = selectedType === "DEBIT" && debitWalletIds.has(wallet.id);
                        return (
                          <option key={wallet.id} value={wallet.id} disabled={debitAlreadyExists}>
                            {walletOptionLabel(wallet, debitAlreadyExists, t)}
                          </option>
                        );
                      })}
                    </select>
                  </label>
                )}
              </>
            )}
            {selectedReusableCardType && (
              <div className="compact-tier-picker" aria-label={t("cards.tier")}>
                <span className="eyebrow">{t("cards.tier")}</span>
                <div className="compact-tier-picker__options">
                  {CARD_TIER_PRODUCT_LIST.map((tier) => {
                    const tierValue = tier.name;
                    const isSelected = tierValue === selectedTier;
                    return (
                      <button
                        type="button"
                        className={`compact-tier-option${isSelected ? " active" : ""}`}
                        key={tier.name}
                        onClick={() => setSelectedTier(tierValue)}
                        aria-pressed={isSelected}
                      >
                        <strong>{tier.label}</strong>
                        <span>{selectedType === "DEBIT" ? tier.debit : tier.credit}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {selectedType === "CREDIT" && (
              <div className="credit-issue-controls">
                <span className="eyebrow">{t("cards.issuancePath")}</span>
                <div className="credit-issue-mode">
                  <button
                    type="button"
                    className={creditIssueMode === "SECURED" ? "active" : ""}
                    onClick={() => setCreditIssueMode("SECURED")}
                  >
                    {t("cards.useCollateral")}
                  </button>
                  <button
                    type="button"
                    className={creditIssueMode === "ADMIN_REVIEW" ? "active" : ""}
                    onClick={() => setCreditIssueMode("ADMIN_REVIEW")}
                  >
                    {t("cards.creditScoreEvaluation")}
                  </button>
                </div>
                <div className="credit-tier-limit">
                  <span>{t("cards.creditLimit")}</span>
                  <strong>{formatCurrencyAmount(CREDIT_CARD_LIMITS[selectedTier], selectedCreditCurrency)}</strong>
                </div>
                <label>
                  {t("cards.currency")}
                  <select
                    value={selectedCreditCurrency}
                    onChange={(event) => setSelectedCreditCurrency(event.target.value)}
                  >
                    {CREDIT_CARD_CURRENCIES.map((currency) => (
                      <option key={currency} value={currency}>
                        {currency}
                      </option>
                    ))}
                  </select>
                </label>
                {creditIssueMode === "SECURED" && (
                  <label>
                    {t("cards.collateralDebitCard")}
                    <select value={collateralCardId} onChange={(event) => setCollateralCardId(event.target.value)}>
                      <option value="" disabled hidden>
                        {t("cards.selectDebitCard")}
                      </option>
                      {collateralDebitCards.map(({ card, wallet }) => (
                        <option key={card.id} value={card.id}>
                          {t("cards.debitLastFourWithWallet", { lastFour: card.last_four, wallet: `${walletDisplayName(wallet)} - ${formatWalletBalance(wallet)}` })}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            )}
            <button type="button" onClick={createCard} disabled={isSaving || !canCreateCard}>
              {isSaving
                ? t("cards.creating")
                : cardLimitReached
                  ? t("cards.limitReached", { type: selectedTypeLabel })
                : selectedType === ""
                  ? t("cards.selectCardTypeButton")
                : selectedAccountAlreadyHasDebit
                  ? t("cards.accountAlreadyHasDebit")
                : debitNewAccountAlreadyExists
                  ? t("cards.accountAlreadyExists", { currency: selectedDebitCurrency })
                : selectedType === "DEBIT" && debitIssueMode === "NEW_ACCOUNT" && !hasNewDebitAccountCurrency
                  ? t("cards.allCurrenciesExist")
                : selectedOneTimeAlreadyExists
                  ? t("cards.oneTimeCardExists")
                : selectedAccountLinkedCard &&
                    !(selectedType === "DEBIT" && debitIssueMode === "NEW_ACCOUNT") &&
                    !selectedWalletId
                  ? t("cards.selectAccountButton")
                : selectedType === "CREDIT" && !creditAmountIsValid
                  ? t("cards.enterCreditLimit")
                : selectedType === "CREDIT" && creditIssueMode === "SECURED" && !selectedCollateralSource
                  ? t("cards.selectCollateral")
                : selectedType === "CREDIT" && creditIssueMode === "SECURED" && !selectedCollateralHasFunds
                  ? t("cards.insufficientCollateral")
                : selectedType === "CREDIT" && creditIssueMode === "ADMIN_REVIEW"
                  ? t("cards.sendForEvaluation")
                : selectedReusableCardType
                  ? selectedType === "DEBIT" && debitIssueMode === "NEW_ACCOUNT"
                    ? t("cards.createAccountAndDebit", { currency: selectedDebitCurrency })
                    : t("cards.createTierCard", { tier: tierLabel(selectedTier, t), type: formatCardType(selectedType, t) })
                  : t("cards.createOneTimeCard")}
            </button>
          </div>

          {selectedReusableCardType && (
            <aside className="card-choice-explainer">
              <span className="eyebrow">{t("cards.selectionDetails")}</span>
              <strong>
                {tierLabel(selectedTier, t)} {formatCardType(selectedType, t)}
              </strong>
              <p>{selectedTierDetails(selectedType, selectedTier, t)}</p>
              <div className="card-choice-explainer__chips">
                {CARD_TIER_REWARDS[selectedTier].slice(0, 3).map((reward) => (
                  <span key={reward}>{reward}</span>
                ))}
              </div>
              <small>
                {selectedType === "DEBIT"
                  ? t("cards.debitSpendsFrom")
                  : creditIssueMode === "SECURED"
                    ? t("cards.securedCardsImmediate")
                    : t("cards.adminReviewNote")}
              </small>
            </aside>
          )}
        </div>
        {cardLimitReached && (
          <p className="eyebrow" style={{ margin: "0.85rem 0 0" }}>
            {t("cards.cardLimitNote", { max: MAX_CARDS_PER_TYPE, type: selectedTypeLabel.toLowerCase() })}
          </p>
        )}
        {notice && <p style={{ color: "var(--color-success)", margin: "0.85rem 0 0" }}>{notice}</p>}
        {error && <p style={{ color: "var(--color-warning)", margin: "0.85rem 0 0" }}>{error}</p>}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("cards.myCards")}</span>
        </div>
        {isLoading && <div className="card-empty">{t("cards.loadingCards")}</div>}
        {!isLoading && cards.length === 0 && <div className="card-empty">{t("cards.noCardsYet")}</div>}
        {!isLoading && cards.length > 0 && (
          <div className="card-gallery">
            {cards.map((card) => {
              const wallet = wallets.find((item) => item.id === card.default_wallet_id);
              const isRevealed = revealedCardIds.has(card.id);
              const sensitiveDetails = cardDetailsById[card.id];
              const isPinPromptOpen = pinPromptCardId === card.id;
              const isPinSettingsOpen = pinSettingsCardIds.has(card.id);
              const cardSecurityError = cardSecurityErrors[card.id];
              const cardSecurityMessage = cardSecurityMessages[card.id];
              const isTransactionsExpanded = expandedTransactionCardIds.has(card.id);
              const isAccountLinkedCard = card.type === "DEBIT" || card.type === "ONE_TIME";
              const cardTransactions = transactions
                .filter(
                  (transaction) =>
                    transaction.card_id === card.id ||
                    (isAccountLinkedCard &&
                      card.default_wallet_id &&
                      (transaction.destination_wallet_id === card.default_wallet_id ||
                        transaction.source_wallet_id === card.default_wallet_id)),
                )
                .sort((first, second) => new Date(second.created_at).getTime() - new Date(first.created_at).getTime());
              const cardTransactionRows =
                cardTransactions.length > 0
                  ? cardTransactions.map((transaction) => ({
                      id: transaction.id,
                      description: transaction.description || formatTransactionType(transaction.type, t),
                      created_at: transaction.created_at,
                      amount: transaction.amount,
                      currency: transaction.currency,
                      status: transaction.status,
                      direction: cardTransactionDirection(transaction, card),
                    }))
                  : mockCardTransactions(card, t, wallet);
              const cardActivityRows = [...cardTransactionRows].sort(
                (first, second) => new Date(second.created_at).getTime() - new Date(first.created_at).getTime(),
              );
              const isShowingPlaceholderTransactions = cardTransactions.length === 0;
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
                    label: t("cards.accountSuffix", { wallet: walletDisplayName(sourceWallet) }),
                  })),
                ...activeDebitCards
                  .map((debitCard) => {
                    const linkedWallet = wallets.find((item) => item.id === debitCard.default_wallet_id);
                    return {
                      value: `DEBIT_CARD:${debitCard.id}`,
                      walletId: debitCard.default_wallet_id ?? "",
                      label: linkedWallet
                        ? t("cards.debitLastFourWithWallet", { lastFour: debitCard.last_four, wallet: walletDisplayName(linkedWallet) })
                        : t("cards.debitLastFour", { lastFour: debitCard.last_four }),
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
                        <span className="bank-card__brand">EASYB</span>
                        <span className="bank-card__product">
                          {card.tier ? `${formatCardTier(card.tier, t)} ${formatCardType(card.type, t)}` : t("cards.oneTime")}
                        </span>
                      </div>
                      <div className="bank-card__top-actions">
                        <span className={statusClass(card.status)}>{card.status}</span>
                        <button
                          type="button"
                          className="bank-card__lock"
                          onClick={() => updateCardStatus(card)}
                          disabled={actionCardId === card.id || (card.status !== "ACTIVE" && card.status !== "FROZEN")}
                          aria-label={card.status === "FROZEN" ? t("cards.unfreezeCard") : t("cards.freezeCard")}
                          title={card.status === "FROZEN" ? t("cards.unfreezeCard") : t("cards.freezeCard")}
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
                      <div className="bank-card__number">{isRevealed && sensitiveDetails ? sensitiveDetails.mock_pan : card.masked_pan}</div>
                      <button
                        type="button"
                        className={`bank-card__copy${copiedCardId === card.id ? " bank-card__copy--copied" : ""}`}
                        onClick={() => copyCardNumber(card)}
                        aria-label={copiedCardId === card.id ? t("cards.cardNumberCopied") : t("cards.copyCardNumber")}
                        title={copiedCardId === card.id ? t("cards.copied") : t("cards.copyCardNumber")}
                      >
                        <Copy size={16} strokeWidth={2.2} />
                      </button>
                      <button
                        type="button"
                        className="bank-card__reveal"
                        onClick={() => toggleCardReveal(card)}
                        aria-label={isRevealed ? t("cards.hideCardDetails") : t("cards.revealCardDetails")}
                        title={isRevealed ? t("cards.hideCardDetails") : t("cards.revealCardDetails")}
                      >
                        {isRevealed ? <Eye size={16} strokeWidth={2.2} /> : <EyeOff size={16} strokeWidth={2.2} />}
                      </button>
                    </div>
                    <div className="bank-card__holder">
                      <span>{t("cards.cardHolder")}</span>
                      <strong>{cardholderName}</strong>
                    </div>
                    <div className="bank-card__footer">
                      <span>
                        {card.tier ? `${formatCardTier(card.tier, t)} ${formatCardType(card.type, t)}` : formatCardType(card.type, t)}
                      </span>
                      <span className="bank-card__security">
                        <span>
                          EXP {String(card.expiration_month).padStart(2, "0")}/{card.expiration_year}
                        </span>
                        <span>{t("cards.mockCvv", { cvv: isRevealed && sensitiveDetails ? sensitiveDetails.mock_cvv : "***" })}</span>
                      </span>
                    </div>
                  </div>

                  {isPinPromptOpen && (
                    <div className="card-detail-pin">
                      <label>
                        {t("cards.pin")}
                        <input
                          type="text"
                          className="card-pin-input"
                          inputMode="numeric"
                          autoComplete="off"
                          autoCorrect="off"
                          spellCheck={false}
                          name={`card-pin-unlock-${card.id}`}
                          maxLength={4}
                          value={pinInputs[card.id] ?? ""}
                          onChange={(event) => {
                            const pin = event.target.value.replace(/\D/g, "").slice(0, 4);
                            setPinInputs((current) => ({ ...current, [card.id]: pin }));
                            clearCardSecurityFeedback(card.id);
                          }}
                          placeholder="0000"
                        />
                      </label>
                      <button
                        type="button"
                        className="card-detail-pin__submit"
                        onClick={() => revealCardDetails(card)}
                        disabled={pinActionCardId === card.id}
                      >
                        {pinActionCardId === card.id ? t("cards.checking") : t("cards.viewDetails")}
                      </button>
                      {cardSecurityError && <div className="card-detail-pin__error">{cardSecurityError}</div>}
                    </div>
                  )}

                  <div className="card-panel__meta">
                    <div>
                      <div className="eyebrow">{isCreditCard ? t("cards.availableCredit") : t("cards.linkedAccount")}</div>
                      <div className="card-panel__value">
                        {isCreditCard
                          ? formatCurrencyAmount(creditAvailable, creditAccountCurrency)
                          : isAccountLinkedCard
                            ? wallet
                              ? walletDisplayName(wallet)
                              : t("cards.notLinked")
                            : t("cards.notRequired")}
                      </div>
                      {wallet && isAccountLinkedCard && (
                        <div className="card-panel__subvalue">{t("cards.walletBalance", { balance: formatWalletBalance(wallet) })}</div>
                      )}
                      {isCreditCard && (
                        <div className="card-panel__subvalue">
                          {t("cards.balanceDue", { amount: formatCurrencyAmount(creditBalanceDue, creditAccountCurrency) })}
                        </div>
                      )}
                    </div>
                    <div className="card-panel__actions">
                      <button
                        type="button"
                        className="card-panel__icon-action"
                        onClick={() => togglePinSettings(card)}
                        aria-label={t("cards.cardSettings")}
                        title={t("cards.cardSettings")}
                      >
                        <Settings size={16} strokeWidth={2.2} />
                      </button>
                      <button
                        type="button"
                        className="card-panel__icon-action button--danger"
                        onClick={() => deleteCard(card)}
                        disabled={deletingCardId === card.id}
                        aria-label={t("cards.deleteCard")}
                        title={t("cards.deleteCard")}
                      >
                        <Trash2 size={16} strokeWidth={2.2} />
                      </button>
                    </div>
                  </div>

                  <div className={`card-panel__control-row${isCreditCard ? "" : " card-panel__control-row--single"}`}>
                    {isCreditCard && (
                      <button
                        type="button"
                        className="card-panel__payment-toggle"
                        onClick={() => togglePaymentPanel(card)}
                        aria-expanded={isPaymentPanelOpen}
                      >
                        {isPaymentPanelOpen ? t("cards.closePayment") : t("cards.makeAPayment")}
                      </button>
                    )}

                    <button
                      type="button"
                      className={`card-panel__details-toggle${isCreditCard ? " card-panel__details-toggle--credit" : ""}`}
                      onClick={() => toggleCardTransactions(card.id)}
                      aria-expanded={isTransactionsExpanded}
                    >
                      <span>{isTransactionsExpanded ? t("cards.hideHistory") : t("cards.transactionHistory")}</span>
                      <span className="card-panel__details-icon">
                        {isTransactionsExpanded ? <ChevronUp size={16} strokeWidth={2.2} /> : <ChevronDown size={16} strokeWidth={2.2} />}
                      </span>
                    </button>
                  </div>

                  {(isPinSettingsOpen || (!isPinPromptOpen && cardSecurityError) || cardSecurityMessage) && (
                    <div className="credit-card-payment">
                      {isPinSettingsOpen && (
                        <div className="credit-card-payment__grid">
                          <label>
                            {t("cards.cardPin")}
                            <input
                              type="text"
                              className="card-pin-input"
                              inputMode="numeric"
                              autoComplete="off"
                              autoCorrect="off"
                              spellCheck={false}
                              name={`card-pin-reset-${card.id}`}
                              maxLength={4}
                              value={pinSettingsInputs[card.id] ?? ""}
                              onChange={(event) => {
                                const pin = event.target.value.replace(/\D/g, "").slice(0, 4);
                                setPinSettingsInputs((current) => ({ ...current, [card.id]: pin }));
                                clearCardSecurityFeedback(card.id);
                              }}
                              placeholder="0000"
                            />
                          </label>
                          <button
                            type="button"
                            className="credit-card-payment__submit"
                            onClick={() => updateCardPin(card)}
                            disabled={pinActionCardId === card.id}
                          >
                            {pinActionCardId === card.id ? t("cards.saving") : card.has_pin ? t("cards.resetPin") : t("cards.setPin")}
                          </button>
                        </div>
                      )}

                      {!isPinPromptOpen && cardSecurityError && <div className="credit-card-payment__error">{cardSecurityError}</div>}
                      {cardSecurityMessage && <div className="credit-card-payment__message">{cardSecurityMessage}</div>}
                    </div>
                  )}

                  {isCreditCard && isPaymentPanelOpen && (
                    <div className="credit-card-payment">
                      <div className="credit-card-payment__summary">
                        <div>
                          <span>{t("cards.cardBalance")}</span>
                          <strong>{formatCurrencyAmount(creditBalanceDue, creditAccountCurrency)}</strong>
                        </div>
                        <div>
                          <span>{t("cards.availableAfterPayment")}</span>
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
                          {t("cards.payFrom")}
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
                              <option value="">{t("cards.noPaymentSourceAvailable")}</option>
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
                              {t("cards.available", { balance: formatWalletBalance(selectedPaymentWallet) })}
                            </small>
                          )}
                        </label>

                        <div className="credit-card-payment__amount">
                          <span>{t("cards.amount")}</span>
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
                              {t("cards.wholeBalance")}
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
                              {t("cards.enterAmount")}
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
                            <strong className="credit-card-payment__amount-preview">
                              {formatCurrencyAmount(creditBalanceDue, creditAccountCurrency)}
                            </strong>
                          )}
                        </div>
                      </div>

                      <button
                        type="button"
                        className="credit-card-payment__submit"
                        onClick={() => submitCreditCardPayment(card)}
                        disabled={creditBalanceDue <= 0}
                      >
                        {t("cards.payCreditCard")}
                      </button>
                      {paymentError && <div className="credit-card-payment__error">{paymentError}</div>}
                      {paymentMessage && <div className="credit-card-payment__message">{paymentMessage}</div>}
                    </div>
                  )}

                  {isTransactionsExpanded && (
                    <div className="card-transactions">
                      {isShowingPlaceholderTransactions && (
                        <div className="card-transactions__note">{t("cards.recentCardActivity")}</div>
                      )}
                      {cardActivityRows.slice(0, 8).map((transaction) => (
                          <div className="card-transaction-row" key={transaction.id}>
                            <div>
                              <strong>{transaction.description}</strong>
                              <span>{formatTransactionDate(transaction.created_at)}</span>
                            </div>
                            <div className={`card-transaction-row__amount card-transaction-row__amount--${transaction.direction}`}>
                              <strong>
                                {transaction.direction === "in" ? "+" : "-"}
                                {Number(transaction.amount).toLocaleString(undefined, {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}{" "}
                                {transaction.currency}
                              </strong>
                              <span>{t(`common.status.${transaction.status}`, { defaultValue: transaction.status })}</span>
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
