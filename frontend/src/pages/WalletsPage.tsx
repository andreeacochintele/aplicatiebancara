import { ArrowLeftRight, ChevronDown, ChevronUp, Copy, CreditCard, Plus, Star, TrendingUp, X, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { FXMarketRate, FXQuote, FXRateHistory, Transaction, Wallet } from "../types";
import { formatCardNumberInput, formatExpiryInput, formatIban, parseExpiryInput, walletLabel } from "../utils";

const RATE_ACCENT = "var(--easyb-rate-accent, #5b5fef)";
// matches backend/app/fx/service.py's _RATES_TO_RON — keep both in sync
const SUPPORTED_CURRENCIES = [
  "RON", "EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "PLN", "TRY",
  "BRL", "CNY", "CZK", "DKK", "HKD", "HUF", "IDR", "ILS", "INR", "ISK",
  "KRW", "MXN", "MYR", "NOK", "NZD", "PHP", "SEK", "SGD", "THB", "ZAR",
];

function hueFromString(value: string): number {
  return Math.abs([...value].reduce((sum, ch) => sum + ch.charCodeAt(0), 0)) % 360;
}

function colorForCurrency(currency: string): string {
  const hue = hueFromString(currency);
  const index = (hue % 5) + 1;
  return `var(--easyb-currency-color-${index}, hsl(${hue} 65% 55%))`;
}

function formatTransactionDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatTransactionType(type: string, t: (key: string, options?: Record<string, unknown>) => string): string {
  const fallback = type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
  return t(`common.txType.${type}`, { defaultValue: fallback });
}

function RateTrendChart({ history }: { history: FXRateHistory }) {
  const data = history.points.map((p) => ({ date: p.date, rate: Number(p.rate) }));
  const short = (date: string) => date.slice(5).replace("-", "/");

  const values = data.map((d) => d.rate);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.2 || Math.max(min * 0.005, 0.0001);
  const domain: [number, number] = [min - pad, max + pad];

  return (
    <div className="easyb-rate-chart">
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="rateFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={RATE_ACCENT} stopOpacity={0.3} />
              <stop offset="100%" stopColor={RATE_ACCENT} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tickFormatter={short}
            tick={{ fontSize: 10, fill: "var(--easyb-text-faint)" }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis domain={domain} hide />
          <Tooltip
            formatter={(value: number) => [value.toFixed(4), `1 ${history.source_currency} =`]}
            labelFormatter={(label: string) => label}
            contentStyle={{ borderRadius: 10, border: "1px solid var(--easyb-border)", fontSize: 12 }}
          />
          <Area
            type="monotone"
            dataKey="rate"
            stroke={RATE_ACCENT}
            strokeWidth={2}
            fill="url(#rateFill)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function WalletsPage() {
  const { t } = useTranslation();
  const { accessToken } = useAuth();
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [amount, setAmount] = useState("100");
  const [quote, setQuote] = useState<FXQuote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [settingMainId, setSettingMainId] = useState<string | null>(null);
  const [newCurrency, setNewCurrency] = useState("");
  const [newNickname, setNewNickname] = useState("");
  const [addingAccount, setAddingAccount] = useState(false);
  const [deletingWallet, setDeletingWallet] = useState<Wallet | null>(null);
  const [closeDestinationId, setCloseDestinationId] = useState("");
  const [closePreviewRate, setClosePreviewRate] = useState<FXMarketRate | null>(null);
  const [closingAccount, setClosingAccount] = useState(false);
  const [convertRate, setConvertRate] = useState<FXMarketRate | null>(null);
  const [chartSourceCurrency, setChartSourceCurrency] = useState("");
  const [chartTargetCurrency, setChartTargetCurrency] = useState("");
  const [chartDays, setChartDays] = useState(14);
  const [rateHistory, setRateHistory] = useState<FXRateHistory | null>(null);
  const [expandedTransactionWalletIds, setExpandedTransactionWalletIds] = useState<Set<string>>(() => new Set());
  const [copiedWalletId, setCopiedWalletId] = useState<string | null>(null);
  const [toppingUpWallet, setToppingUpWallet] = useState<Wallet | null>(null);
  const [topUpCardNumber, setTopUpCardNumber] = useState("");
  const [topUpExpiry, setTopUpExpiry] = useState("");
  const [topUpCvv, setTopUpCvv] = useState("");
  const [topUpCardholderName, setTopUpCardholderName] = useState("");
  const [topUpAmount, setTopUpAmount] = useState("");
  const [submittingTopUp, setSubmittingTopUp] = useState(false);

  function copyIban(wallet: Wallet) {
    navigator.clipboard.writeText(wallet.iban).then(() => {
      setCopiedWalletId(wallet.id);
      setTimeout(() => setCopiedWalletId((current) => (current === wallet.id ? null : current)), 1500);
    });
  }

  function loadWallets() {
    if (!accessToken) return;
    apiRequest<Wallet[]>("/wallets", { token: accessToken }).then(setWallets).catch(() => setWallets([]));
  }

  function loadTransactions() {
    if (!accessToken) return;
    apiRequest<Transaction[]>("/transactions", { token: accessToken }).then(setTransactions).catch(() => setTransactions([]));
  }

  useEffect(loadWallets, [accessToken]);
  useEffect(loadTransactions, [accessToken]);

  function toggleWalletTransactions(walletId: string) {
    setExpandedTransactionWalletIds((current) => {
      const next = new Set(current);
      if (next.has(walletId)) {
        next.delete(walletId);
      } else {
        next.add(walletId);
      }
      return next;
    });
  }

  const activeWallets = wallets.filter((w) => w.status !== "CLOSED");
  const transactionsByWallet = useMemo(
    () =>
      transactions.reduce<Record<string, Transaction[]>>((groups, transaction) => {
        for (const walletId of [transaction.source_wallet_id, transaction.destination_wallet_id]) {
          if (!walletId) continue;
          groups[walletId] = [...(groups[walletId] ?? []), transaction];
        }
        return groups;
      }, {}),
    [transactions],
  );
  const closeDestinationOptions = activeWallets.filter((w) => w.id !== deletingWallet?.id && w.status === "ACTIVE");
  const closeDestination = closeDestinationOptions.find((w) => w.id === closeDestinationId);

  useEffect(() => {
    if (!deletingWallet) {
      setCloseDestinationId("");
      return;
    }
    const fallback = closeDestinationOptions.find((w) => w.is_main) ?? closeDestinationOptions[0];
    setCloseDestinationId(fallback?.id ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deletingWallet]);

  useEffect(() => {
    if (!accessToken || !deletingWallet || !closeDestination || deletingWallet.currency === closeDestination.currency) {
      setClosePreviewRate(null);
      return;
    }
    apiRequest<FXMarketRate>(
      `/fx/rate?source_currency=${deletingWallet.currency}&target_currency=${closeDestination.currency}`,
      { token: accessToken },
    )
      .then(setClosePreviewRate)
      .catch(() => setClosePreviewRate(null));
  }, [accessToken, deletingWallet, closeDestination]);

  async function confirmDeleteAccount() {
    if (!accessToken || !deletingWallet || !closeDestinationId || closingAccount) return;
    setClosingAccount(true);
    setError(null);
    try {
      await apiRequest(
        `/wallets/${deletingWallet.id}?destination_wallet_id=${closeDestinationId}`,
        { method: "DELETE", token: accessToken },
      );
      setDeletingWallet(null);
      loadWallets();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("wallets.couldNotCloseAccount"));
    } finally {
      setClosingAccount(false);
    }
  }

  async function addAccount() {
    if (!accessToken || addingAccount) return;
    const currency = newCurrency || SUPPORTED_CURRENCIES[0];
    setAddingAccount(true);
    setError(null);
    try {
      await apiRequest("/wallets", {
        method: "POST",
        token: accessToken,
        body: { currency, nickname: newNickname.trim() || null },
      });
      setNewCurrency("");
      setNewNickname("");
      loadWallets();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("wallets.couldNotAddAccount"));
    } finally {
      setAddingAccount(false);
    }
  }

  function closeTopUpModal() {
    setToppingUpWallet(null);
    setTopUpCardNumber("");
    setTopUpExpiry("");
    setTopUpCvv("");
    setTopUpCardholderName("");
    setTopUpAmount("");
  }

  async function submitTopUp() {
    if (!accessToken || !toppingUpWallet || submittingTopUp) return;
    const expiry = parseExpiryInput(topUpExpiry);
    if (!expiry) {
      setError(t("wallets.couldNotAddMoney"));
      return;
    }
    setSubmittingTopUp(true);
    setError(null);
    try {
      await apiRequest("/transactions/top-up", {
        method: "POST",
        token: accessToken,
        body: {
          destination_wallet_id: toppingUpWallet.id,
          card_number: topUpCardNumber,
          cardholder_name: topUpCardholderName,
          expiry_month: expiry.month,
          expiry_year: expiry.year,
          cvv: topUpCvv,
          amount: topUpAmount,
        },
      });
      setResult(t("wallets.topUpSuccess", { amount: topUpAmount, currency: toppingUpWallet.currency }));
      closeTopUpModal();
      loadWallets();
      loadTransactions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("wallets.couldNotAddMoney"));
    } finally {
      setSubmittingTopUp(false);
    }
  }

  async function setMainWallet(walletId: string) {
    if (!accessToken || settingMainId) return;
    setSettingMainId(walletId);
    setError(null);
    try {
      await apiRequest(`/wallets/${walletId}/set-main`, { method: "PATCH", token: accessToken });
      loadWallets();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("wallets.couldNotSetMainWallet"));
    } finally {
      setSettingMainId(null);
    }
  }

  useEffect(() => {
    if (activeWallets.length < 2) return;
    if (!sourceId) setSourceId(activeWallets[0].id);
    if (!targetId) {
      const other = activeWallets.find((w) => w.id !== activeWallets[0].id);
      if (other) setTargetId(other.id);
    }
  }, [activeWallets, sourceId, targetId]);

  useEffect(() => {
    if (activeWallets.length === 0) return;
    if (!chartSourceCurrency) setChartSourceCurrency(activeWallets[0].currency);
    if (!chartTargetCurrency) {
      const other = activeWallets.find((w) => w.currency !== activeWallets[0].currency);
      setChartTargetCurrency(other?.currency ?? (activeWallets[0].currency === "EUR" ? "USD" : "EUR"));
    }
  }, [activeWallets, chartSourceCurrency, chartTargetCurrency]);

  const source = activeWallets.find((w) => w.id === sourceId);
  const target = activeWallets.find((w) => w.id === targetId);
  // targetId can also be a "new:<currency>" sentinel for a currency the user
  // doesn't hold a wallet in yet (see the "To" <select> below) — Exchange
  // shouldn't require pre-creating an account just to convert into it.
  const targetCurrency = target?.currency ?? (targetId.startsWith("new:") ? targetId.slice(4) : undefined);

  useEffect(() => {
    if (!accessToken || !source || !targetCurrency || source.currency === targetCurrency) {
      setConvertRate(null);
      return;
    }
    apiRequest<FXMarketRate>(
      `/fx/rate?source_currency=${source.currency}&target_currency=${targetCurrency}`,
      { token: accessToken },
    )
      .then(setConvertRate)
      .catch(() => setConvertRate(null));
  }, [accessToken, source?.currency, targetCurrency]);

  useEffect(() => {
    if (!accessToken || !chartSourceCurrency || !chartTargetCurrency || chartSourceCurrency === chartTargetCurrency) {
      setRateHistory(null);
      return;
    }
    apiRequest<FXRateHistory>(
      `/fx/rate/history?source_currency=${chartSourceCurrency}&target_currency=${chartTargetCurrency}&days=${chartDays}`,
      { token: accessToken },
    )
      .then(setRateHistory)
      .catch(() => setRateHistory(null));
  }, [accessToken, chartSourceCurrency, chartTargetCurrency, chartDays]);

  const bankRate = convertRate ? Number(convertRate.rate) * (1 - Number(convertRate.fee_rate)) : null;
  const convertedAmount =
    bankRate !== null && amount && !Number.isNaN(Number(amount)) ? Number(amount) * bankRate : null;

  async function getQuote() {
    if (!accessToken || !source || !targetCurrency) return;
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const newQuote = await apiRequest<FXQuote>("/fx/quote", {
        method: "POST",
        token: accessToken,
        body: { source_currency: source.currency, target_currency: targetCurrency, source_amount: amount },
      });
      setQuote(newQuote);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("wallets.couldNotGetQuote"));
    } finally {
      setBusy(false);
    }
  }

  async function acceptQuote() {
    if (!accessToken || !source || !targetCurrency || !quote) return;
    setError(null);
    setBusy(true);
    try {
      // Exchange doesn't require the destination currency to already have an
      // account — create it on the fly (zero-balance) so users can convert
      // into any supported currency, not just ones they set up beforehand.
      let destinationWalletId = target?.id;
      if (!destinationWalletId) {
        const newWallet = await apiRequest<Wallet>("/wallets", {
          method: "POST",
          token: accessToken,
          body: { currency: targetCurrency },
        });
        destinationWalletId = newWallet.id;
      }
      await apiRequest("/transactions/transfer", {
        method: "POST",
        token: accessToken,
        body: {
          source_wallet_id: source.id,
          destination_wallet_id: destinationWalletId,
          amount: quote.source_amount,
          fx_quote_id: quote.id,
          description: `FX conversion ${source.currency} -> ${targetCurrency}`,
        },
      });
      setResult(
        t("wallets.convertedMessage", {
          sourceAmount: quote.source_amount,
          sourceCurrency: source.currency,
          targetAmount: quote.target_amount,
          targetCurrency,
        }),
      );
      setQuote(null);
      setTargetId(destinationWalletId);
      loadWallets();
      loadTransactions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("wallets.conversionFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="easyb-col">
      <div className="easyb-card">
        <div className="easyb-section-header">
          <div>
            <h2>{t("wallets.title")}</h2>
          </div>
          <div className="easyb-add-account">
            <select value={newCurrency || SUPPORTED_CURRENCIES[0]} onChange={(e) => setNewCurrency(e.target.value)}>
              {SUPPORTED_CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <input
              type="text"
              value={newNickname}
              onChange={(e) => setNewNickname(e.target.value)}
              placeholder={t("wallets.nicknamePlaceholder")}
              style={{ width: 160 }}
            />
            <button type="button" onClick={addAccount} disabled={addingAccount}>
              <Plus size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
              {t("wallets.addAccount")}
            </button>
          </div>
        </div>

        <div className="easyb-wallet-grid">
          {activeWallets.map((wallet) => {
            const isTransactionsExpanded = expandedTransactionWalletIds.has(wallet.id);
            const walletTransactions = (transactionsByWallet[wallet.id] ?? [])
              .sort((first, second) => new Date(second.created_at).getTime() - new Date(first.created_at).getTime())
              .slice(0, 8);
            return (
              <div
                className="easyb-wallet-card"
                key={wallet.id}
                style={{ "--wallet-accent": colorForCurrency(wallet.currency) } as CSSProperties}
              >
                <div className="easyb-wallet-card__top">
                  <span className="easyb-wallet-card__code">
                    {wallet.currency}
                    {wallet.nickname && (
                      <span style={{ fontWeight: 500, color: "var(--easyb-text-soft)" }}> · {wallet.nickname}</span>
                    )}
                  </span>
                  {wallet.is_main && <span className="easyb-chip easyb-chip-violet">{t("wallets.main")}</span>}
                </div>
                <div className="easyb-wallet-card__amount" style={{ color: "var(--wallet-accent)" }}>
                  {wallet.available_balance}
                </div>
                <div className="easyb-wallet-card__sub">
                  {wallet.reserved_balance !== "0" && wallet.reserved_balance !== "0.00"
                    ? t("wallets.reserved", { amount: wallet.reserved_balance, currency: wallet.currency })
                    : t("wallets.nothingOnHold")}
                </div>
                <button
                  type="button"
                  className="easyb-wallet-card__iban"
                  onClick={() => copyIban(wallet)}
                  title={t("wallets.copyIban")}
                >
                  <span>{formatIban(wallet.iban)}</span>
                  <Copy size={12} />
                  {copiedWalletId === wallet.id && <span className="easyb-wallet-card__iban-copied">{t("wallets.copied")}</span>}
                </button>
                <button
                  type="button"
                  className="easyb-wallet-history-toggle"
                  onClick={() => toggleWalletTransactions(wallet.id)}
                  aria-expanded={isTransactionsExpanded}
                >
                  <span>{isTransactionsExpanded ? t("wallets.hideHistory") : t("wallets.transactionHistory")}</span>
                  {isTransactionsExpanded ? <ChevronUp size={16} strokeWidth={2.2} /> : <ChevronDown size={16} strokeWidth={2.2} />}
                </button>
                {isTransactionsExpanded && (
                  <div className="easyb-wallet-activity">
                    {walletTransactions.length === 0 ? (
                      <div className="easyb-wallet-activity__empty">{t("wallets.noAccountTransactions")}</div>
                    ) : (
                      <div className="easyb-wallet-activity__list">
                        {walletTransactions.map((transaction) => {
                          const isIncoming = transaction.destination_wallet_id === wallet.id;
                          return (
                            <div className="easyb-wallet-activity__row" key={transaction.id}>
                              <div>
                                <strong>{transaction.description || formatTransactionType(transaction.type, t)}</strong>
                                <span>{formatTransactionDate(transaction.created_at)}</span>
                              </div>
                              <div className={isIncoming ? "easyb-wallet-activity__amount--in" : "easyb-wallet-activity__amount--out"}>
                                {isIncoming ? "+" : "-"}
                                {Number(transaction.amount).toLocaleString(undefined, {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })}{" "}
                                {transaction.currency}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
                <div className="easyb-wallet-card__footer">
                  {wallet.status === "ACTIVE" && (
                    <button
                      type="button"
                      className="easyb-wallet-card__topup"
                      onClick={() => setToppingUpWallet(wallet)}
                    >
                      <CreditCard size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
                      {t("wallets.addMoney")}
                    </button>
                  )}
                  {!wallet.is_main && wallet.status === "ACTIVE" && (
                    <div className="easyb-wallet-card__actions">
                      <button
                        type="button"
                        className="easyb-wallet-card__set-main"
                        onClick={() => setMainWallet(wallet.id)}
                        disabled={settingMainId === wallet.id}
                      >
                        <Star size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
                        {t("wallets.setAsMain")}
                      </button>
                      <button
                        type="button"
                        className="easyb-wallet-card__delete"
                        onClick={() => setDeletingWallet(wallet)}
                      >
                        <XCircle size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
                        {t("wallets.close")}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {activeWallets.length === 0 && <p className="easyb-tx-meta">{t("wallets.noWalletsYet")}</p>}
        </div>
        {error && <p role="alert">{error}</p>}
        {result && <p role="status">{result}</p>}
      </div>

      {activeWallets.length >= 2 && (
        <div className="easyb-exchange-row">
          <div className="easyb-card easyb-exchange-card">
            <div className="easyb-section-header">
              <div>
                <div className="easyb-eyebrow">{t("wallets.currency")}</div>
                <h2>
                  <ArrowLeftRight size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
                  {t("wallets.exchange")}
                </h2>
              </div>
            </div>

            {bankRate !== null && convertRate && (
              <div className="easyb-rate-banner">
                <div className="easyb-rate-banner__headline">
                  <TrendingUp size={16} />
                  1 {convertRate.source_currency} = {Number(convertRate.rate).toFixed(4)} {convertRate.target_currency}
                </div>
                {/* Same rate a "Get quote" call below will price with, shown the same way the
                    resulting quote card shows its own "Rate" line — fee is a separate line item
                    there (not baked into the rate), so it's kept separate here too. */}
                <div className="easyb-rate-banner__sub">{t("wallets.liveBankRate")}</div>
                {convertedAmount !== null && (
                  <div className="easyb-rate-banner__amount">
                    {amount} {convertRate.source_currency} = <strong>{convertedAmount.toFixed(2)} {convertRate.target_currency}</strong>
                  </div>
                )}
              </div>
            )}

            <div className="easyb-convert-grid">
              <label>
                {t("wallets.from")}
                <select value={sourceId} onChange={(e) => { setSourceId(e.target.value); setQuote(null); }}>
                  {activeWallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {walletLabel(w)} · {w.available_balance}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("wallets.to")}
                <select value={targetId} onChange={(e) => { setTargetId(e.target.value); setQuote(null); }}>
                  {activeWallets
                    .filter((w) => w.id !== sourceId)
                    .map((w) => (
                      <option key={w.id} value={w.id}>
                        {walletLabel(w)}
                      </option>
                    ))}
                  {SUPPORTED_CURRENCIES.filter(
                    (c) => c !== source?.currency && !activeWallets.some((w) => w.currency === c),
                  ).map((c) => (
                    <option key={`new:${c}`} value={`new:${c}`}>
                      {t("wallets.newAccount", { currency: c })}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 12, fontSize: 12.5, fontWeight: 600 }}>
              {t("wallets.amountFor", { currency: source?.currency })}
              <input value={amount} onChange={(e) => { setAmount(e.target.value); setQuote(null); }} />
            </label>

            <div className="easyb-convert-submit">
              <button onClick={getQuote} disabled={busy || !source || !targetCurrency}>
                {t("wallets.getQuote")}
              </button>
            </div>

            {error && <p role="alert">{error}</p>}
            {result && <p>{result}</p>}

            {quote && (
              <div className="easyb-quote-card">
                <div className="easyb-quote-card__header">
                  <div className="easyb-eyebrow" style={{ marginBottom: 0 }}>
                    {t("wallets.quoteExpires", { time: new Date(quote.expires_at).toLocaleTimeString() })}
                  </div>
                  <button type="button" className="easyb-quote-card__close" onClick={() => setQuote(null)} aria-label={t("wallets.cancelThisQuote")}>
                    <X size={14} />
                  </button>
                </div>
                <div className="easyb-quote-row">
                  <span>{t("wallets.rate")}</span>
                  <span>
                    1 {quote.source_currency} = {Number(quote.exchange_rate).toFixed(4)} {quote.target_currency}
                  </span>
                </div>
                <div className="easyb-quote-row">
                  <span>{t("wallets.fee")}</span>
                  <span>
                    {quote.fee} {quote.source_currency}
                  </span>
                </div>
                <div className="easyb-quote-row total">
                  <span>{t("wallets.youReceive")}</span>
                  <span>
                    {quote.target_amount} {quote.target_currency}
                  </span>
                </div>
                <div className="easyb-quote-card__actions">
                  <button className="easyb-btn-ghost" onClick={() => setQuote(null)} disabled={busy}>
                    {t("wallets.cancel")}
                  </button>
                  <button onClick={acceptQuote} disabled={busy}>
                    {t("wallets.acceptQuote")}
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="easyb-card easyb-exchange-card">
            <div className="easyb-section-header">
              <div>
                <div className="easyb-eyebrow">{t("wallets.liveEcbDays", { days: chartDays })}</div>
                <h2>{t("wallets.rateTrend")}</h2>
              </div>
              <div className="easyb-period-picker">
                {[7, 14, 30, 90].map((days) => (
                  <button
                    key={days}
                    type="button"
                    className={days === chartDays ? "easyb-period-picker__option is-active" : "easyb-period-picker__option"}
                    onClick={() => setChartDays(days)}
                  >
                    {days}D
                  </button>
                ))}
              </div>
            </div>

            <div className="easyb-convert-grid">
              <label>
                {t("wallets.from")}
                <select value={chartSourceCurrency} onChange={(e) => setChartSourceCurrency(e.target.value)}>
                  {SUPPORTED_CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("wallets.to")}
                <select value={chartTargetCurrency} onChange={(e) => setChartTargetCurrency(e.target.value)}>
                  {SUPPORTED_CURRENCIES.filter((c) => c !== chartSourceCurrency).map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {rateHistory && rateHistory.points.length > 1 ? (
              <RateTrendChart history={rateHistory} />
            ) : (
              <p className="easyb-tx-meta" style={{ marginTop: 14 }}>
                {t("wallets.notEnoughHistory")}
              </p>
            )}
          </div>
        </div>
      )}

      {deletingWallet && (
        <div className="folder-modal-backdrop" onClick={() => !closingAccount && setDeletingWallet(null)}>
          <div className="easyb-card" style={{ maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
            <div className="easyb-eyebrow">{t("wallets.closeAccount")}</div>
            <h2 style={{ marginBottom: 10 }}>{t("wallets.walletSuffix", { label: walletLabel(deletingWallet) })}</h2>
            <p style={{ fontSize: 13.5, color: "var(--easyb-text-soft)", lineHeight: 1.6 }}>
              {t("wallets.holdsBalance")}{" "}
              <strong style={{ color: "var(--easyb-text)" }}>
                {deletingWallet.available_balance} {deletingWallet.currency}
              </strong>
              {t("wallets.cannotBeUndone")}
            </p>

            {Number(deletingWallet.available_balance) > 0 && closeDestinationOptions.length > 0 && (
              <label style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
                {t("wallets.moveBalanceTo")}
                <select value={closeDestinationId} onChange={(e) => setCloseDestinationId(e.target.value)}>
                  {closeDestinationOptions.map((w) => (
                    <option key={w.id} value={w.id}>
                      {walletLabel(w)}
                      {w.is_main ? t("wallets.mainSuffix") : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {Number(deletingWallet.available_balance) > 0 && closeDestination && (
              <p style={{ fontSize: 13.5, lineHeight: 1.6 }}>
                {deletingWallet.currency === closeDestination.currency ? (
                  <>
                    <strong style={{ color: "var(--easyb-text)" }}>
                      {deletingWallet.available_balance} {deletingWallet.currency}
                    </strong>{" "}
                    {t("wallets.willBeMovedTo", { destination: walletLabel(closeDestination) })}
                  </>
                ) : closePreviewRate ? (
                  <>
                    {t("wallets.estimatedReceive")}{" "}
                    <strong style={{ color: "var(--easyb-text)" }}>
                      {(
                        Number(deletingWallet.available_balance) *
                        Number(closePreviewRate.rate) *
                        (1 - Number(closePreviewRate.fee_rate))
                      ).toFixed(2)}{" "}
                      {closeDestination.currency}
                    </strong>{" "}
                    {t("wallets.inDestinationLiveRate", { destination: walletLabel(closeDestination) })}
                  </>
                ) : (
                  t("wallets.fetchingEstimate")
                )}
              </p>
            )}

            {closeDestinationOptions.length === 0 && (
              <p role="alert">{t("wallets.noOtherActiveAccount")}</p>
            )}

            {error && <p role="alert">{error}</p>}
            <div className="easyb-quote-card__actions" style={{ marginTop: 6 }}>
              <button className="easyb-btn-ghost" onClick={() => setDeletingWallet(null)} disabled={closingAccount}>
                {t("wallets.cancel")}
              </button>
              <button
                onClick={confirmDeleteAccount}
                disabled={closingAccount || !closeDestinationId}
              >
                {closingAccount ? t("wallets.closing") : t("wallets.yesCloseAccount")}
              </button>
            </div>
          </div>
        </div>
      )}

      {toppingUpWallet && (
        <div className="folder-modal-backdrop" onClick={() => !submittingTopUp && closeTopUpModal()} role="presentation">
          <div
            className="easyb-card"
            style={{ maxWidth: 420 }}
            role="dialog"
            aria-modal="true"
            aria-label={t("wallets.addMoney")}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="easyb-eyebrow">{t("wallets.addMoney")}</div>
            <h2 style={{ marginBottom: 10 }}>{t("wallets.walletSuffix", { label: walletLabel(toppingUpWallet) })}</h2>
            <p style={{ fontSize: 13.5, color: "var(--easyb-text-soft)", lineHeight: 1.6, marginBottom: 10 }}>
              {t("wallets.cardDetailsHint")}
            </p>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
              {t("wallets.cardNumber")}
              <input
                inputMode="numeric"
                autoComplete="off"
                maxLength={19}
                value={topUpCardNumber}
                onChange={(e) => setTopUpCardNumber(formatCardNumberInput(e.target.value))}
                placeholder={t("wallets.cardNumberPlaceholder")}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
              {t("wallets.cardholderName")}
              <input
                autoComplete="off"
                value={topUpCardholderName}
                onChange={(e) => setTopUpCardholderName(e.target.value)}
                placeholder={t("wallets.cardholderNamePlaceholder")}
              />
            </label>
            <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
                {t("wallets.cardExpiry")}
                <input
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={5}
                  value={topUpExpiry}
                  onChange={(e) => setTopUpExpiry(formatExpiryInput(e.target.value))}
                  placeholder="MM/YY"
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, width: 120, flex: "0 0 120px" }}>
                {t("wallets.cardCvv")}
                <input
                  inputMode="numeric"
                  autoComplete="new-password"
                  maxLength={3}
                  value={topUpCvv}
                  onChange={(e) => setTopUpCvv(e.target.value.replace(/\D/g, "").slice(0, 3))}
                  placeholder="•••"
                  style={{ boxSizing: "border-box", textAlign: "center", letterSpacing: "0.2em", width: "100%" }}
                />
              </label>
            </div>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
              {t("wallets.topUpAmount")}
              <input
                inputMode="decimal"
                value={topUpAmount}
                onChange={(e) => setTopUpAmount(e.target.value)}
                placeholder="0.00"
              />
            </label>
            {error && <p role="alert">{error}</p>}
            <div className="easyb-quote-card__actions" style={{ marginTop: 6 }}>
              <button className="easyb-btn-ghost" onClick={closeTopUpModal} disabled={submittingTopUp}>
                {t("wallets.cancel")}
              </button>
              <button
                onClick={submitTopUp}
                disabled={submittingTopUp || !topUpCardNumber || !topUpExpiry || !topUpCvv || !topUpAmount}
              >
                {submittingTopUp ? t("wallets.addingMoney") : t("wallets.addMoney")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
