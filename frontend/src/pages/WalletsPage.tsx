import { ArrowLeftRight, ChevronDown, ChevronUp, Copy, Plus, Star, Trash2, TrendingUp, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { FXMarketRate, FXQuote, FXRateHistory, Transaction, Wallet } from "../types";

const RATE_ACCENT = "#5b5fef"; // same violet as --aurora-accent, kept as one deliberate hue for the trend line
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
  return `hsl(${hueFromString(currency)} 65% 55%)`;
}

function formatTransactionDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatTransactionType(type: string): string {
  return type
    .split("_")
    .map((part) => part[0] + part.slice(1).toLowerCase())
    .join(" ");
}

function formatIban(iban: string): string {
  return iban.replace(/(.{4})/g, "$1 ").trim();
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
    <div className="aurora-rate-chart">
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
            tick={{ fontSize: 10, fill: "var(--aurora-text-faint)" }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis domain={domain} hide />
          <Tooltip
            formatter={(value: number) => [value.toFixed(4), `1 ${history.source_currency} =`]}
            labelFormatter={(label: string) => label}
            contentStyle={{ borderRadius: 10, border: "1px solid var(--aurora-border)", fontSize: 12 }}
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
  const [addingAccount, setAddingAccount] = useState(false);
  const [deletingWallet, setDeletingWallet] = useState<Wallet | null>(null);
  const [closingAccount, setClosingAccount] = useState(false);
  const [convertRate, setConvertRate] = useState<FXMarketRate | null>(null);
  const [chartSourceCurrency, setChartSourceCurrency] = useState("");
  const [chartTargetCurrency, setChartTargetCurrency] = useState("");
  const [rateHistory, setRateHistory] = useState<FXRateHistory | null>(null);
  const [expandedTransactionWalletIds, setExpandedTransactionWalletIds] = useState<Set<string>>(() => new Set());
  const [copiedWalletId, setCopiedWalletId] = useState<string | null>(null);

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
  const mainWallet = activeWallets.find((w) => w.is_main);
  const missingCurrencies = SUPPORTED_CURRENCIES.filter((c) => !activeWallets.some((w) => w.currency === c));

  async function confirmDeleteAccount() {
    if (!accessToken || !deletingWallet || closingAccount) return;
    setClosingAccount(true);
    setError(null);
    try {
      await apiRequest(`/wallets/${deletingWallet.id}`, { method: "DELETE", token: accessToken });
      setDeletingWallet(null);
      loadWallets();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not close account");
    } finally {
      setClosingAccount(false);
    }
  }

  async function addAccount() {
    if (!accessToken || addingAccount) return;
    const currency = newCurrency || missingCurrencies[0];
    if (!currency) return;
    setAddingAccount(true);
    setError(null);
    try {
      await apiRequest("/wallets", { method: "POST", token: accessToken, body: { currency } });
      setNewCurrency("");
      loadWallets();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add account");
    } finally {
      setAddingAccount(false);
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
      setError(err instanceof ApiError ? err.message : "Could not set main wallet");
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
      `/fx/rate/history?source_currency=${chartSourceCurrency}&target_currency=${chartTargetCurrency}&days=14`,
      { token: accessToken },
    )
      .then(setRateHistory)
      .catch(() => setRateHistory(null));
  }, [accessToken, chartSourceCurrency, chartTargetCurrency]);

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
      setError(err instanceof ApiError ? err.message : "Could not get a quote");
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
      setResult(`Converted ${quote.source_amount} ${source.currency} to ${quote.target_amount} ${targetCurrency}.`);
      setQuote(null);
      setTargetId(destinationWalletId);
      loadWallets();
      loadTransactions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Conversion failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="aurora-col">
      <div className="aurora-card">
        <div className="aurora-section-header">
          <div>
            <div className="aurora-eyebrow">Your accounts</div>
            <h2>Wallets</h2>
          </div>
          {missingCurrencies.length > 0 && (
            <div className="aurora-add-account">
              <select value={newCurrency || missingCurrencies[0]} onChange={(e) => setNewCurrency(e.target.value)}>
                {missingCurrencies.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button type="button" onClick={addAccount} disabled={addingAccount}>
                <Plus size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
                Add account
              </button>
            </div>
          )}
        </div>

        <div className="aurora-wallet-grid">
          {activeWallets.map((wallet) => {
            const isTransactionsExpanded = expandedTransactionWalletIds.has(wallet.id);
            const walletTransactions = (transactionsByWallet[wallet.id] ?? [])
              .sort((first, second) => new Date(second.created_at).getTime() - new Date(first.created_at).getTime())
              .slice(0, 8);
            return (
              <div
                className="aurora-wallet-card"
                key={wallet.id}
                style={{ "--wallet-accent": colorForCurrency(wallet.currency) } as CSSProperties}
              >
                <div className="aurora-wallet-card__top">
                  <span className="aurora-wallet-card__code">{wallet.currency}</span>
                  {wallet.is_main && <span className="aurora-chip aurora-chip-violet">Main</span>}
                </div>
                <div className="aurora-wallet-card__amount" style={{ color: "var(--wallet-accent)" }}>
                  {wallet.available_balance}
                </div>
                <div className="aurora-wallet-card__sub">
                  {wallet.reserved_balance !== "0" && wallet.reserved_balance !== "0.00"
                    ? `${wallet.reserved_balance} ${wallet.currency} reserved`
                    : "Nothing on hold"}
                </div>
                <button
                  type="button"
                  className="aurora-wallet-card__iban"
                  onClick={() => copyIban(wallet)}
                  title="Copy IBAN"
                >
                  <span>{formatIban(wallet.iban)}</span>
                  <Copy size={12} />
                  {copiedWalletId === wallet.id && <span className="aurora-wallet-card__iban-copied">Copied</span>}
                </button>
                <button
                  type="button"
                  className="aurora-wallet-history-toggle"
                  onClick={() => toggleWalletTransactions(wallet.id)}
                  aria-expanded={isTransactionsExpanded}
                >
                  <span>{isTransactionsExpanded ? "Hide history" : "Transaction history"}</span>
                  {isTransactionsExpanded ? <ChevronUp size={16} strokeWidth={2.2} /> : <ChevronDown size={16} strokeWidth={2.2} />}
                </button>
                {isTransactionsExpanded && (
                  <div className="aurora-wallet-activity">
                    {walletTransactions.length === 0 ? (
                      <div className="aurora-wallet-activity__empty">No account transactions yet.</div>
                    ) : (
                      <div className="aurora-wallet-activity__list">
                        {walletTransactions.map((transaction) => {
                          const isIncoming = transaction.destination_wallet_id === wallet.id;
                          return (
                            <div className="aurora-wallet-activity__row" key={transaction.id}>
                              <div>
                                <strong>{transaction.description || formatTransactionType(transaction.type)}</strong>
                                <span>{formatTransactionDate(transaction.created_at)}</span>
                              </div>
                              <div className={isIncoming ? "aurora-wallet-activity__amount--in" : "aurora-wallet-activity__amount--out"}>
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
                <div className="aurora-wallet-card__footer">
                  <span aria-hidden="true" />
                  {!wallet.is_main && wallet.status === "ACTIVE" && (
                    <div className="aurora-wallet-card__actions">
                      <button
                        type="button"
                        className="aurora-wallet-card__set-main"
                        onClick={() => setMainWallet(wallet.id)}
                        disabled={settingMainId === wallet.id}
                      >
                        <Star size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
                        Set as main
                      </button>
                      <button
                        type="button"
                        className="aurora-wallet-card__delete"
                        onClick={() => setDeletingWallet(wallet)}
                      >
                        <Trash2 size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
                        Close
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {activeWallets.length === 0 && <p className="aurora-tx-meta">No wallets yet.</p>}
        </div>
        {error && <p role="alert">{error}</p>}
      </div>

      {activeWallets.length >= 2 && (
        <div className="aurora-exchange-row">
          <div className="aurora-card aurora-exchange-card">
            <div className="aurora-section-header">
              <div>
                <div className="aurora-eyebrow">Currency</div>
                <h2>
                  <ArrowLeftRight size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
                  Exchange
                </h2>
              </div>
            </div>

            {bankRate !== null && convertRate && (
              <div className="aurora-rate-banner">
                <div className="aurora-rate-banner__headline">
                  <TrendingUp size={16} />
                  1 {convertRate.source_currency} = {bankRate.toFixed(4)} {convertRate.target_currency}
                </div>
                <div className="aurora-rate-banner__sub">Bank rate, fee included</div>
                {convertedAmount !== null && (
                  <div className="aurora-rate-banner__amount">
                    {amount} {convertRate.source_currency} = <strong>{convertedAmount.toFixed(2)} {convertRate.target_currency}</strong>
                  </div>
                )}
              </div>
            )}

            <div className="aurora-convert-grid">
              <label>
                From
                <select value={sourceId} onChange={(e) => { setSourceId(e.target.value); setQuote(null); }}>
                  {activeWallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.currency} · {w.available_balance}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                To
                <select value={targetId} onChange={(e) => { setTargetId(e.target.value); setQuote(null); }}>
                  {activeWallets
                    .filter((w) => w.id !== sourceId)
                    .map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.currency}
                      </option>
                    ))}
                  {SUPPORTED_CURRENCIES.filter(
                    (c) => c !== source?.currency && !activeWallets.some((w) => w.currency === c),
                  ).map((c) => (
                    <option key={`new:${c}`} value={`new:${c}`}>
                      {c} (new account)
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 12, fontSize: 12.5, fontWeight: 600 }}>
              Amount ({source?.currency})
              <input value={amount} onChange={(e) => { setAmount(e.target.value); setQuote(null); }} />
            </label>

            <div className="aurora-convert-submit">
              <button onClick={getQuote} disabled={busy || !source || !targetCurrency}>
                Get quote
              </button>
            </div>

            {error && <p role="alert">{error}</p>}
            {result && <p>{result}</p>}

            {quote && (
              <div className="aurora-quote-card">
                <div className="aurora-quote-card__header">
                  <div className="aurora-eyebrow" style={{ marginBottom: 0 }}>
                    Quote expires {new Date(quote.expires_at).toLocaleTimeString()}
                  </div>
                  <button type="button" className="aurora-quote-card__close" onClick={() => setQuote(null)} aria-label="Cancel this quote">
                    <X size={14} />
                  </button>
                </div>
                <div className="aurora-quote-row">
                  <span>Rate</span>
                  <span>
                    1 {quote.source_currency} = {Number(quote.exchange_rate).toFixed(4)} {quote.target_currency}
                  </span>
                </div>
                <div className="aurora-quote-row">
                  <span>Fee</span>
                  <span>
                    {quote.fee} {quote.source_currency}
                  </span>
                </div>
                <div className="aurora-quote-row total">
                  <span>You receive</span>
                  <span>
                    {quote.target_amount} {quote.target_currency}
                  </span>
                </div>
                <div className="aurora-quote-card__actions">
                  <button className="aurora-btn-ghost" onClick={() => setQuote(null)} disabled={busy}>
                    Cancel
                  </button>
                  <button onClick={acceptQuote} disabled={busy}>
                    Accept quote
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="aurora-card aurora-exchange-card">
            <div className="aurora-section-header">
              <div>
                <div className="aurora-eyebrow">Live · ECB, 14 days</div>
                <h2>Rate trend</h2>
              </div>
            </div>

            <div className="aurora-convert-grid">
              <label>
                From
                <select value={chartSourceCurrency} onChange={(e) => setChartSourceCurrency(e.target.value)}>
                  {SUPPORTED_CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                To
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
              <p className="aurora-tx-meta" style={{ marginTop: 14 }}>
                Not enough history for this pair yet.
              </p>
            )}
          </div>
        </div>
      )}

      {deletingWallet && (
        <div className="folder-modal-backdrop" onClick={() => !closingAccount && setDeletingWallet(null)}>
          <div className="aurora-card" style={{ maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
            <div className="aurora-eyebrow">Close account</div>
            <h2 style={{ marginBottom: 10 }}>{deletingWallet.currency} wallet</h2>
            <p style={{ fontSize: 13.5, color: "var(--aurora-text-soft)", lineHeight: 1.6 }}>
              This account currently holds{" "}
              <strong style={{ color: "var(--aurora-text)" }}>
                {deletingWallet.available_balance} {deletingWallet.currency}
              </strong>
              .{" "}
              {Number(deletingWallet.available_balance) > 0 && mainWallet
                ? `It will be converted and transferred into your main ${mainWallet.currency} wallet.`
                : "The account has no balance to move."}{" "}
              This can't be undone, but you can reopen a {deletingWallet.currency} account later.
            </p>
            {error && <p role="alert">{error}</p>}
            <div className="aurora-quote-card__actions" style={{ marginTop: 6 }}>
              <button className="aurora-btn-ghost" onClick={() => setDeletingWallet(null)} disabled={closingAccount}>
                Cancel
              </button>
              <button onClick={confirmDeleteAccount} disabled={closingAccount}>
                {closingAccount ? "Closing…" : "Close account"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
