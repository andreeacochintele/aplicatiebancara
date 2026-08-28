import {
  CheckCircle2, Clock3, PiggyBank, PieChart as PieChartIcon, RefreshCw, Sparkles, Target, TrendingUp, X, type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  Area, AreaChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { apiRequest, ApiError } from "../api/apiClient";
import { colorForType } from "../features/analytics/formatters";
import { generateAnalyticsInsights, type AnalyticsInsight } from "../features/analytics/insights";
import { useAuth } from "../hooks/useAuth";
import type {
  AIInsight,
  BalanceHistoryResponse,
  Budget,
  ForecastResponse,
  FXQuote,
  MonthlyTrendResponse,
  NetWorthHistoryResponse,
  NetWorthResponse,
  SavingsGoal,
  SpendingByCategoryResponse,
  WalletBalanceItem,
} from "../types";

type NetWorthPeriod = "1m" | "3m" | "6m" | "1y";

const PERIOD_LABEL: Record<NetWorthPeriod, string> = {
  "1m": "This month",
  "3m": "3 months",
  "6m": "6 months",
  "1y": "1 year",
};

const INSIGHT_STYLE: Record<AnalyticsInsight["id"], { bg: string; fg: string; icon: LucideIcon }> = {
  trend: { bg: "var(--easyb-violet-soft)", fg: "var(--easyb-violet)", icon: TrendingUp },
  category: { bg: "var(--easyb-accent-soft)", fg: "var(--easyb-accent-dark)", icon: PieChartIcon },
  budget: { bg: "var(--easyb-green-soft)", fg: "var(--easyb-green)", icon: Target },
  forecast: { bg: "var(--easyb-pink-soft)", fg: "var(--easyb-pink)", icon: Clock3 },
};

function shortDate(date: string): string {
  return date.slice(5).replace("-", "/");
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function NetWorthTrendChart({ history }: { history: NetWorthHistoryResponse }) {
  const data = history.history.map((point) => ({ date: point.date, value: Number(point.value) }));
  if (data.length < 2) {
    return <p className="easyb-eyebrow light">Not enough history yet to chart this period.</p>;
  }
  const values = data.map((d) => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.15 || Math.max(Math.abs(min) * 0.01, 1);

  return (
    <div style={{ margin: "10px -6px -4px" }}>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={data} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="netWorthFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#fff" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#fff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            tick={{ fontSize: 10, fill: "rgba(255,255,255,0.6)" }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={28}
          />
          <YAxis domain={[min - pad, max + pad]} hide />
          <Tooltip
            formatter={(value: number) => [`${value.toFixed(2)} ${history.base_currency}`, "Net worth"]}
            labelFormatter={(label: string) => label}
            contentStyle={{
              borderRadius: 10,
              border: "1px solid var(--easyb-border)",
              fontSize: 12,
              background: "var(--easyb-surface)",
              color: "var(--easyb-text)",
            }}
            itemStyle={{ color: "var(--easyb-text)" }}
            labelStyle={{ color: "var(--easyb-text-soft)" }}
          />
          <Area type="monotone" dataKey="value" stroke="#fff" strokeWidth={2} fill="url(#netWorthFill)" dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function ForecastChart({ forecast }: { forecast: ForecastResponse }) {
  const data = forecast.projected_series.map((point) => ({ date: point.date, balance: Number(point.projected_balance) }));
  if (data.length < 2) {
    return <p className="easyb-tx-meta">Not enough days left this month to project a trend.</p>;
  }
  const values = data.map((d) => d.balance);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.2 || Math.max(Math.abs(min) * 0.02, 1);

  return (
    <ResponsiveContainer width="100%" height={140}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="forecastFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--easyb-accent)" stopOpacity={0.25} />
            <stop offset="100%" stopColor="var(--easyb-accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 10, fill: "var(--easyb-text-faint)" }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
        <YAxis domain={[min - pad, max + pad]} hide />
        <Tooltip
          formatter={(value: number) => [`${value.toFixed(2)} ${forecast.currency}`, "Projected balance"]}
          contentStyle={{
            borderRadius: 10,
            border: "1px solid var(--easyb-border)",
            fontSize: 12,
            background: "var(--easyb-surface)",
            color: "var(--easyb-text)",
          }}
          itemStyle={{ color: "var(--easyb-text)" }}
          labelStyle={{ color: "var(--easyb-text-soft)" }}
        />
        <Area type="monotone" dataKey="balance" stroke="var(--easyb-accent)" strokeWidth={2} fill="url(#forecastFill)" dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function BalanceHistoryChart({ history }: { history: BalanceHistoryResponse }) {
  const data = history.history.map((point) => ({ date: point.date, balance: Number(point.balance) }));
  if (data.length < 2) {
    return <p className="easyb-tx-meta">Not enough ledger history in this range to chart a trend.</p>;
  }
  const values = data.map((d) => d.balance);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.2 || Math.max(Math.abs(min) * 0.02, 1);

  return (
    <ResponsiveContainer width="100%" height={140}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="balanceHistoryFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--easyb-violet)" stopOpacity={0.25} />
            <stop offset="100%" stopColor="var(--easyb-violet)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 10, fill: "var(--easyb-text-faint)" }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
        <YAxis domain={[min - pad, max + pad]} hide />
        <Tooltip
          formatter={(value: number) => [`${value.toFixed(2)} ${history.currency}`, "Balance"]}
          contentStyle={{
            borderRadius: 10,
            border: "1px solid var(--easyb-border)",
            fontSize: 12,
            background: "var(--easyb-surface)",
            color: "var(--easyb-text)",
          }}
          itemStyle={{ color: "var(--easyb-text)" }}
          labelStyle={{ color: "var(--easyb-text-soft)" }}
        />
        <Area type="monotone" dataKey="balance" stroke="var(--easyb-violet)" strokeWidth={2} fill="url(#balanceHistoryFill)" dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

type MoneyModalMode = "contribute" | "withdraw" | "delete";

function SavingsMoneyModal({
  goal,
  mode,
  wallets,
  accessToken,
  onClose,
  onSuccess,
}: {
  goal: SavingsGoal;
  mode: MoneyModalMode;
  wallets: WalletBalanceItem[];
  accessToken: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const hasSavedMoney = Number(goal.current_amount) > 0;
  // Delete only needs a wallet when there's money to return - an
  // already-withdrawn (0 balance) goal is a plain confirm, nothing to move.
  const needsWallet = mode === "contribute" || mode === "withdraw" || (mode === "delete" && hasSavedMoney);

  const [walletId, setWalletId] = useState(wallets[0]?.wallet_id ?? "");
  const [amount, setAmount] = useState("");
  const [quote, setQuote] = useState<FXQuote | null>(null);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wallet = wallets.find((w) => w.wallet_id === walletId);
  const crossCurrency = needsWallet && wallet !== undefined && wallet.currency !== goal.currency;
  // Withdrawing (or deleting a goal that still has money) always moves the
  // goal's entire current_amount - there's no amount to type in for those,
  // just where it should land.
  const fixedAmount = goal.current_amount;
  const requestAmount = mode === "contribute" ? amount : fixedAmount;

  useEffect(() => {
    setQuote(null);
    setQuoteError(null);
  }, [walletId, amount, mode]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  async function fetchQuote() {
    if (!wallet || !requestAmount || Number(requestAmount) <= 0) return;
    setQuoteError(null);
    setBusy(true);
    try {
      const sourceCurrency = mode === "contribute" ? wallet.currency : goal.currency;
      const targetCurrency = mode === "contribute" ? goal.currency : wallet.currency;
      const newQuote = await apiRequest<FXQuote>("/fx/quote", {
        method: "POST",
        token: accessToken,
        body: { source_currency: sourceCurrency, target_currency: targetCurrency, source_amount: requestAmount },
      });
      setQuote(newQuote);
    } catch (err) {
      setQuoteError(err instanceof ApiError ? err.message : "Could not get a conversion quote");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (needsWallet && (!wallet || !requestAmount)) return;
    if (crossCurrency && !quote) return;
    setError(null);
    setBusy(true);
    try {
      if (mode === "contribute") {
        await apiRequest<SavingsGoal>(`/savings/${goal.id}/contribute`, {
          method: "POST",
          token: accessToken,
          body: { wallet_id: walletId, amount, fx_quote_id: crossCurrency ? quote?.id : undefined },
        });
      } else if (mode === "withdraw") {
        await apiRequest<SavingsGoal>(`/savings/${goal.id}/withdraw`, {
          method: "POST",
          token: accessToken,
          body: { wallet_id: walletId, fx_quote_id: crossCurrency ? quote?.id : undefined },
        });
      } else {
        await apiRequest<void>(`/savings/${goal.id}`, {
          method: "DELETE",
          token: accessToken,
          body: needsWallet ? { wallet_id: walletId, fx_quote_id: crossCurrency ? quote?.id : undefined } : {},
        });
      }
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const canConfirm =
    !busy &&
    (!needsWallet || (!!wallet && Number(requestAmount) > 0 && (!crossCurrency || quote !== null)));

  return (
    <div
      role="presentation"
      onClick={onClose}
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
        aria-label={mode === "contribute" ? "Add money to goal" : mode === "withdraw" ? "Withdraw from goal" : "Delete goal"}
        className="tile"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: "380px", width: "100%" }}
      >
        <div className="tile__header">
          <span className="eyebrow">
            {mode === "contribute" ? `Add money — ${goal.name}` : mode === "withdraw" ? `Withdraw — ${goal.name}` : `Delete — ${goal.name}`}
          </span>
          <button
            type="button"
            className="button--ghost card-panel__icon-action"
            onClick={onClose}
            aria-label="Close"
            style={{ marginLeft: "auto" }}
          >
            <X size={15} strokeWidth={2.2} />
          </button>
        </div>

        {mode === "delete" && (
          <p style={{ marginBottom: "0.75rem" }}>
            Are you sure you want to delete the "{goal.name}" savings goal?
            {hasSavedMoney ? " The money you've saved will be returned to a wallet." : " This can't be undone."}
          </p>
        )}

        {needsWallet && (
          <label style={{ display: "block", marginBottom: "0.75rem" }}>
            {mode === "contribute" ? "From wallet" : "To wallet"}
            <select value={walletId} onChange={(e) => setWalletId(e.target.value)} style={{ width: "100%", marginTop: "0.3rem" }}>
              {wallets.map((w) => (
                <option key={w.wallet_id} value={w.wallet_id}>
                  {w.currency} — {w.available_balance} available
                </option>
              ))}
            </select>
          </label>
        )}

        {mode === "contribute" && (
          <label style={{ display: "block", marginBottom: "0.75rem" }}>
            Amount {wallet ? `(${wallet.currency})` : ""}
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              style={{ width: "100%", marginTop: "0.3rem" }}
            />
          </label>
        )}
        {mode === "withdraw" && (
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
            Withdraws the full {fixedAmount} {goal.currency} saved so far.
          </p>
        )}
        {mode === "delete" && hasSavedMoney && (
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
            Returns the full {fixedAmount} {goal.currency} saved so far.
          </p>
        )}

        {crossCurrency && wallet && (
          <div
            className="eyebrow"
            style={{
              marginBottom: "0.75rem",
              padding: "0.6rem 0.75rem",
              borderRadius: "0.6rem",
              background: "var(--easyb-surface-alt)",
              border: "1px dashed var(--easyb-border)",
            }}
          >
            {quote ? (
              <>
                ≈ {quote.target_amount} {mode === "contribute" ? goal.currency : wallet.currency}
                {" · rate "}
                {quote.exchange_rate}
                {" · quote expires "}
                {new Date(quote.expires_at).toLocaleTimeString()}
              </>
            ) : (
              <>
                {mode === "contribute"
                  ? `Converting ${wallet.currency} to ${goal.currency} — get a quote first.`
                  : `Converting ${goal.currency} to ${wallet.currency} — get a quote first.`}
                <div style={{ marginTop: "0.5rem" }}>
                  <button type="button" className="button--ghost" onClick={fetchQuote} disabled={busy || !requestAmount || Number(requestAmount) <= 0}>
                    Get quote
                  </button>
                </div>
              </>
            )}
            {quoteError && (
              <p className="status-line status-line--error" style={{ marginTop: "0.4rem" }}>
                {quoteError}
              </p>
            )}
          </div>
        )}

        {error && <p className="status-line status-line--error">{error}</p>}

        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", justifyContent: "flex-end" }}>
          <button type="button" className="button--ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className={mode === "delete" ? "button--danger" : undefined}
            onClick={confirm}
            disabled={!canConfirm}
          >
            {busy ? "Working…" : mode === "contribute" ? "Add money" : mode === "withdraw" ? "Withdraw" : "Delete goal"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function AnalyticsPage() {
  const { accessToken } = useAuth();
  const [netWorth, setNetWorth] = useState<NetWorthResponse | null>(null);
  const [netWorthHistory, setNetWorthHistory] = useState<NetWorthHistoryResponse | null>(null);
  const [netWorthPeriod, setNetWorthPeriod] = useState<NetWorthPeriod>("1m");
  const [spendingByCategory, setSpendingByCategory] = useState<SpendingByCategoryResponse | null>(null);
  const [monthlyTrend, setMonthlyTrend] = useState<MonthlyTrendResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [historyDateFrom, setHistoryDateFrom] = useState("");
  const [historyDateTo, setHistoryDateTo] = useState("");
  const [balanceHistory, setBalanceHistory] = useState<BalanceHistoryResponse | null>(null);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [savingsGoals, setSavingsGoals] = useState<SavingsGoal[]>([]);
  const [aiInsights, setAiInsights] = useState<AIInsight[] | null>(null);
  const [dismissingInsightId, setDismissingInsightId] = useState<string | null>(null);
  const [refreshingInsights, setRefreshingInsights] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  const [goalFormOpen, setGoalFormOpen] = useState(false);
  const [goalName, setGoalName] = useState("");
  const [goalAmount, setGoalAmount] = useState("");
  const [goalCurrency, setGoalCurrency] = useState("RON");
  const [goalTargetDate, setGoalTargetDate] = useState("");
  const [goalSubmitting, setGoalSubmitting] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);

  const [moneyModal, setMoneyModal] = useState<{ goal: SavingsGoal; mode: MoneyModalMode } | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;

    apiRequest<NetWorthResponse>("/analytics/net-worth", { token: accessToken })
      .then((data) => !cancelled && setNetWorth(data))
      .catch(() => !cancelled && setLoadError(true));
    apiRequest<SpendingByCategoryResponse>("/analytics/spending-by-category", { token: accessToken })
      .then((data) => !cancelled && setSpendingByCategory(data))
      .catch(() => !cancelled && setSpendingByCategory(null));
    apiRequest<MonthlyTrendResponse>("/analytics/monthly-trend?months=6", { token: accessToken })
      .then((data) => !cancelled && setMonthlyTrend(data))
      .catch(() => !cancelled && setMonthlyTrend(null));
    apiRequest<ForecastResponse>("/analytics/forecast", { token: accessToken })
      .then((data) => !cancelled && setForecast(data))
      .catch(() => !cancelled && setForecast(null));
    apiRequest<Budget[]>("/budgets", { token: accessToken })
      .then((data) => !cancelled && setBudgets(data))
      .catch(() => !cancelled && setBudgets([]));
    apiRequest<SavingsGoal[]>("/savings", { token: accessToken })
      .then((data) => !cancelled && setSavingsGoals(data))
      .catch(() => !cancelled && setSavingsGoals([]));
    // Cache-miss (first load in 24h) can take a while - a real Azure call
    // per flagged category, see ai/personal_finance/insights.py. Kept as
    // its own isolated promise so it never blocks the rest of the page.
    apiRequest<AIInsight[]>("/analytics/insights", { token: accessToken })
      .then((data) => !cancelled && setAiInsights(data))
      .catch(() => !cancelled && setAiInsights([]));

    return () => {
      cancelled = true;
    };
  }, [accessToken, reloadTick]);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    apiRequest<NetWorthHistoryResponse>(`/analytics/net-worth-history?period=${netWorthPeriod}`, { token: accessToken })
      .then((data) => !cancelled && setNetWorthHistory(data))
      .catch(() => !cancelled && setNetWorthHistory(null));
    return () => {
      cancelled = true;
    };
  }, [accessToken, netWorthPeriod, reloadTick]);

  const isCustomForecastRange = historyDateFrom !== "" && historyDateTo !== "" && historyDateFrom <= historyDateTo;

  useEffect(() => {
    if (!accessToken || !isCustomForecastRange) {
      setBalanceHistory(null);
      return;
    }
    let cancelled = false;
    apiRequest<BalanceHistoryResponse>(
      `/analytics/balance-history?date_from=${historyDateFrom}&date_to=${historyDateTo}`,
      { token: accessToken },
    )
      .then((data) => !cancelled && setBalanceHistory(data))
      .catch(() => !cancelled && setBalanceHistory(null));
    return () => {
      cancelled = true;
    };
  }, [accessToken, isCustomForecastRange, historyDateFrom, historyDateTo, reloadTick]);

  const spendingCurrency = netWorth?.base_currency ?? spendingByCategory?.items[0]?.currency;
  const spendingItems = spendingByCategory?.items.filter((item) => item.currency === spendingCurrency) ?? [];
  const spendingTotal = spendingItems.reduce((sum, item) => sum + Number(item.total_amount), 0);
  const donutData = spendingItems.map((item) => ({
    key: `${item.category}-${item.currency}`,
    name: item.category,
    value: Number(item.total_amount),
    color: colorForType(item.category),
  }));

  const insights = generateAnalyticsInsights({ monthlyTrend, spendingItems, budgets, forecast });

  const netWorthChangePercent = (() => {
    const history = netWorthHistory?.history ?? [];
    if (history.length < 2) return null;
    const first = Number(history[0].value);
    const last = Number(history[history.length - 1].value);
    if (first === 0) return null;
    return ((last - first) / Math.abs(first)) * 100;
  })();

  const walletCurrencies = Array.from(new Set(netWorth?.wallets.map((w) => w.currency) ?? ["RON"]));

  async function refreshInsights() {
    if (!accessToken || refreshingInsights) return;
    setRefreshingInsights(true);
    try {
      const data = await apiRequest<AIInsight[]>("/analytics/insights?refresh=true", { token: accessToken });
      setAiInsights(data);
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "Could not refresh recommendations");
    } finally {
      setRefreshingInsights(false);
    }
  }

  async function dismissInsight(insight: AIInsight) {
    if (!accessToken) return;
    setDismissingInsightId(insight.id);
    try {
      await apiRequest<void>(`/analytics/insights/${insight.id}/dismiss`, { method: "POST", token: accessToken });
      setAiInsights((current) => current?.filter((i) => i.id !== insight.id) ?? current);
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : "Could not dismiss this recommendation");
    } finally {
      setDismissingInsightId(null);
    }
  }

  async function submitGoal(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || !goalName.trim() || !goalAmount) return;
    setGoalSubmitting(true);
    setGoalError(null);
    try {
      await apiRequest<SavingsGoal>("/savings", {
        method: "POST",
        token: accessToken,
        body: {
          name: goalName.trim(),
          target_amount: goalAmount,
          currency: goalCurrency,
          target_date: goalTargetDate || null,
        },
      });
      setGoalName("");
      setGoalAmount("");
      setGoalTargetDate("");
      setGoalFormOpen(false);
      setReloadTick((tick) => tick + 1);
    } catch (err) {
      setGoalError(err instanceof ApiError ? err.message : "Could not create savings goal");
    } finally {
      setGoalSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <div className="tile" style={{ padding: "1.5rem" }}>
        <p className="status-line status-line--error">We couldn't load your analytics.</p>
        <button type="button" onClick={() => { setLoadError(false); setReloadTick((tick) => tick + 1); }}>
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="easyb-page">
      <div className="easyb-col">
        <div className="easyb-card easyb-hero">
          <div className="easyb-hero-blob easyb-blob-1" />
          <div className="easyb-hero-blob easyb-blob-2" />
          <div className="easyb-hero-top">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
              <div className="easyb-eyebrow light">Net worth</div>
              <select
                className="easyb-hero-select"
                value={netWorthPeriod}
                onChange={(e) => setNetWorthPeriod(e.target.value as NetWorthPeriod)}
              >
                {(Object.keys(PERIOD_LABEL) as NetWorthPeriod[]).map((period) => (
                  <option key={period} value={period}>
                    {PERIOD_LABEL[period]}
                  </option>
                ))}
              </select>
            </div>
            <div className="easyb-hero-amount">
              {netWorth ? `${netWorth.total_available_balance} ${netWorth.base_currency}` : "—"}
            </div>
            {netWorthChangePercent !== null && (
              <div className="easyb-hero-sub" style={{ color: netWorthChangePercent >= 0 ? "#7ee3ab" : "#ff9b9b" }}>
                {netWorthChangePercent >= 0 ? "↑" : "↓"} {Math.abs(netWorthChangePercent).toFixed(1)}% vs {PERIOD_LABEL[netWorthPeriod].toLowerCase()} ago
              </div>
            )}
          </div>
          {netWorthHistory && <NetWorthTrendChart history={netWorthHistory} />}
        </div>

        <div className="easyb-card">
          <div className="easyb-section-header">
            <div>
              <div className="easyb-eyebrow">This period</div>
              <h2>Spending overview</h2>
            </div>
          </div>
          {donutData.length > 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: 40, flexWrap: "wrap" }}>
              <div className="easyb-donut-wrap" style={{ flex: "0 0 320px", width: 320 }}>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie data={donutData} dataKey="value" nameKey="name" innerRadius={90} outerRadius={130} paddingAngle={2} stroke="none">
                      {donutData.map((item) => (
                        <Cell key={item.key} fill={item.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number, name: string) => [`${value.toFixed(2)} ${spendingCurrency ?? ""}`, name]}
                      contentStyle={{
                        borderRadius: 10,
                        border: "1px solid var(--easyb-border)",
                        fontSize: 12,
                        background: "var(--easyb-surface)",
                        color: "var(--easyb-text)",
                      }}
                      itemStyle={{ color: "var(--easyb-text)" }}
                      labelStyle={{ color: "var(--easyb-text-soft)" }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="easyb-donut-center">
                  <div className="easyb-donut-total" style={{ fontSize: 32 }}>{spendingTotal.toFixed(0)}</div>
                  <div className="easyb-donut-label" style={{ fontSize: 13 }}>{spendingCurrency ?? ""}</div>
                </div>
              </div>
              <div
                className="easyb-legend"
                style={{
                  flex: "1 1 320px",
                  marginTop: 0,
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(180px, 1fr))",
                  columnGap: 32,
                }}
              >
                {donutData.map((item) => (
                  <Link
                    className="easyb-legend-row"
                    to="/transactions"
                    key={item.key}
                    style={{ textDecoration: "none", color: "inherit", cursor: "pointer", fontSize: 16, padding: "8px 0" }}
                  >
                    <span className="easyb-legend-dot" style={{ background: item.color, width: 10, height: 10 }} />
                    <span className="easyb-legend-name">{item.name}</span>
                    <span className="easyb-legend-pct">
                      {spendingTotal > 0 ? Math.round((item.value / spendingTotal) * 100) : 0}%
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          ) : (
            <p className="easyb-tx-meta">No spending activity for this period.</p>
          )}
        </div>

        <div className="easyb-card">
          <div className="easyb-section-header">
            <h2>Cash-flow forecast</h2>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "flex-end", marginBottom: 10 }}>
            <label style={{ flex: 1, minWidth: 120 }}>
              From
              <input
                type="date"
                value={historyDateFrom}
                max={historyDateTo || todayISO()}
                onChange={(e) => setHistoryDateFrom(e.target.value)}
              />
            </label>
            <label style={{ flex: 1, minWidth: 120 }}>
              To
              <input
                type="date"
                value={historyDateTo}
                min={historyDateFrom}
                max={todayISO()}
                onChange={(e) => setHistoryDateTo(e.target.value)}
              />
            </label>
            {isCustomForecastRange && (
              <button
                type="button"
                className="button--ghost"
                onClick={() => {
                  setHistoryDateFrom("");
                  setHistoryDateTo("");
                }}
              >
                Back to forecast
              </button>
            )}
          </div>
          {isCustomForecastRange ? (
            balanceHistory ? (
              <>
                <div className="balance-hero__amount" style={{ fontSize: "1.75rem" }}>
                  {balanceHistory.history.length > 0
                    ? balanceHistory.history[balanceHistory.history.length - 1].balance
                    : "—"}{" "}
                  {balanceHistory.currency}
                </div>
                <div className="easyb-tx-meta" style={{ marginBottom: 8 }}>
                  Balance history for {balanceHistory.date_from} → {balanceHistory.date_to}
                </div>
                <BalanceHistoryChart history={balanceHistory} />
                <p className="easyb-tx-meta" style={{ marginTop: 8 }}>{balanceHistory.note}</p>
              </>
            ) : (
              <p className="easyb-tx-meta">Loading balance history…</p>
            )
          ) : forecast ? (
            <>
              <div className="balance-hero__amount" style={{ fontSize: "1.75rem" }}>
                {forecast.projected_month_end_balance} {forecast.currency}
              </div>
              <div className="easyb-tx-meta" style={{ marginBottom: 8 }}>
                Current balance: {forecast.current_balance} {forecast.currency} · {forecast.days_remaining} days left this month
              </div>
              <ForecastChart forecast={forecast} />
              <p className="easyb-tx-meta" style={{ marginTop: 8 }}>{forecast.note}</p>
            </>
          ) : (
            <p className="easyb-tx-meta">No forecast available yet.</p>
          )}
        </div>

        <div className="easyb-card" id="analytics-savings-goals">
          <div className="easyb-section-header">
            <h2>Savings goals</h2>
          </div>
          {savingsGoals.length > 0 ? (
            savingsGoals.map((goal) => (
              <div className="goal-card" key={goal.id}>
                <div className="goal-card__top">
                  <span className="goal-card__name">
                    {goal.name}
                    {goal.status === "COMPLETED" && (
                      <span
                        className="easyb-chip easyb-chip-green"
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                      >
                        <CheckCircle2 size={12} strokeWidth={2.4} /> Completed
                      </span>
                    )}
                    {goal.status === "WITHDRAWN" && <span className="easyb-chip easyb-chip-neutral">Withdrawn</span>}
                  </span>
                  <span className="goal-card__amount">
                    {goal.current_amount} / {goal.target_amount} {goal.currency}
                  </span>
                </div>
                <div className="goal-card__track">
                  <div
                    className="goal-card__fill"
                    style={{
                      width: `${Math.min(goal.percent_complete, 100)}%`,
                      background:
                        goal.status === "COMPLETED"
                          ? "var(--easyb-green)"
                          : goal.status === "WITHDRAWN"
                            ? "var(--easyb-text-faint)"
                            : undefined,
                    }}
                  />
                </div>
                <div className="goal-card__footer">
                  <span className="goal-card__percent">{goal.percent_complete}%</span>
                  <span className="goal-card__meta">
                    {goal.status === "WITHDRAWN"
                      ? "Withdrawn back to a wallet"
                      : goal.status === "COMPLETED"
                        ? "Goal reached!"
                        : goal.target_date
                          ? `Target ${goal.target_date}${goal.monthly_amount_needed ? ` · save ${goal.monthly_amount_needed} ${goal.currency} a month to arrive on time` : ""}`
                          : "No target date"}
                  </span>
                </div>
                <div className="goal-card__actions">
                  {goal.status === "ACTIVE" && (netWorth?.wallets.length ?? 0) > 0 && (
                    <button type="button" onClick={() => setMoneyModal({ goal, mode: "contribute" })}>
                      Add money
                    </button>
                  )}
                  {goal.status !== "WITHDRAWN" && Number(goal.current_amount) > 0 && (netWorth?.wallets.length ?? 0) > 0 && (
                    <button type="button" className="button--ghost" onClick={() => setMoneyModal({ goal, mode: "withdraw" })}>
                      Withdraw
                    </button>
                  )}
                  <button type="button" className="button--ghost" onClick={() => setMoneyModal({ goal, mode: "delete" })}>
                    Delete
                  </button>
                </div>
              </div>
            ))
          ) : (
            <p className="easyb-tx-meta">No savings goals yet.</p>
          )}

          {goalFormOpen && (
            <form className="easyb-inline-form" onSubmit={submitGoal}>
              {goalError && <p className="status-line status-line--error">{goalError}</p>}
              <div className="easyb-inline-form-row">
                <label>
                  Name
                  <input value={goalName} onChange={(e) => setGoalName(e.target.value)} placeholder="e.g. Emergency fund" required />
                </label>
                <label>
                  Target amount
                  <input type="number" min="1" step="0.01" value={goalAmount} onChange={(e) => setGoalAmount(e.target.value)} required />
                </label>
              </div>
              <div className="easyb-inline-form-row">
                <label>
                  Currency
                  <select value={goalCurrency} onChange={(e) => setGoalCurrency(e.target.value)}>
                    {walletCurrencies.map((currency) => (
                      <option key={currency} value={currency}>
                        {currency}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Target date (optional)
                  <input type="date" value={goalTargetDate} onChange={(e) => setGoalTargetDate(e.target.value)} />
                </label>
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <button type="submit" disabled={goalSubmitting}>
                  {goalSubmitting ? "Creating…" : "Create goal"}
                </button>
                <button type="button" className="button--ghost" onClick={() => setGoalFormOpen(false)}>
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      <div className="easyb-col">
        <div className="easyb-card">
          <div className="easyb-section-header">
            <h2>Insights</h2>
          </div>
          {insights.length > 0 ? (
            insights.map((insight) => {
              const style = INSIGHT_STYLE[insight.id];
              const Icon = style.icon;
              return (
                <div className="easyb-insight-row" key={insight.id}>
                  <span className="easyb-insight-icon" style={{ background: style.bg, color: style.fg }}>
                    <Icon size={16} />
                  </span>
                  <div>
                    <div className="easyb-insight-text">{insight.message}</div>
                    {insight.ctaTo && (
                      <Link className="easyb-link-btn" to={insight.ctaTo} style={{ fontSize: 12, marginTop: 4 }}>
                        {insight.ctaLabel}
                      </Link>
                    )}
                  </div>
                </div>
              );
            })
          ) : (
            <p className="easyb-tx-meta">Not enough activity yet to generate insights.</p>
          )}
        </div>

        <div className="easyb-card">
          <div className="easyb-section-header">
            <span className="easyb-eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <Sparkles size={14} strokeWidth={2.2} />
              Spending recommendations
            </span>
            <button
              type="button"
              className="button--ghost card-panel__icon-action"
              onClick={refreshInsights}
              disabled={refreshingInsights || aiInsights === null}
              aria-label="Refresh spending recommendations"
              style={{ marginLeft: "auto" }}
            >
              <RefreshCw size={14} strokeWidth={2.2} className={refreshingInsights ? "spin" : undefined} />
            </button>
          </div>
          {aiInsights === null ? (
            <p className="easyb-tx-meta">Checking your spending…</p>
          ) : aiInsights.length > 0 ? (
            aiInsights.map((insight) => (
              <div className="easyb-insight-row" key={insight.id}>
                <span
                  className="easyb-insight-icon"
                  style={{ background: "var(--easyb-violet-soft)", color: "var(--easyb-violet)" }}
                >
                  <Sparkles size={16} />
                </span>
                <div style={{ flex: 1 }}>
                  <div className="easyb-insight-text">{insight.message}</div>
                  {insight.category && (
                    <span className="easyb-chip easyb-chip-violet" style={{ marginTop: "0.35rem" }}>
                      {insight.category}
                      {insight.currency ? ` · ${insight.currency}` : ""}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  className="button--ghost"
                  style={{ fontSize: "0.72rem", padding: "0.2rem 0.55rem", flexShrink: 0 }}
                  disabled={dismissingInsightId === insight.id}
                  onClick={() => dismissInsight(insight)}
                >
                  {dismissingInsightId === insight.id ? "…" : "Dismiss"}
                </button>
              </div>
            ))
          ) : (
            <p className="easyb-tx-meta">No spending recommendations right now.</p>
          )}
        </div>

        <div className="easyb-card easyb-savings-cta">
          <PiggyBank size={22} style={{ marginBottom: 8 }} />
          <h2>Set a savings goal</h2>
          <p>Create a goal and track your progress automatically.</p>
          <button
            type="button"
            onClick={() => {
              setGoalFormOpen(true);
              document.getElementById("analytics-savings-goals")?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          >
            Create goal
          </button>
        </div>
      </div>

      {moneyModal && accessToken && (
        <SavingsMoneyModal
          goal={moneyModal.goal}
          mode={moneyModal.mode}
          wallets={netWorth?.wallets ?? []}
          accessToken={accessToken}
          onClose={() => setMoneyModal(null)}
          onSuccess={() => {
            setMoneyModal(null);
            setReloadTick((tick) => tick + 1);
          }}
        />
      )}
    </div>
  );
}
