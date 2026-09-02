import {
  CheckCircle2, Clock3, PiggyBank, PieChart as PieChartIcon, Plus, RefreshCw, Sparkles, Target, TrendingUp, X, type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  Area, AreaChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { apiRequest, ApiError } from "../api/apiClient";
import { PeriodSelect } from "../components/PeriodSelect";
import { colorForType } from "../features/analytics/formatters";
import { generateAnalyticsInsights, type AnalyticsInsight } from "../features/analytics/insights";
import { useAuth } from "../hooks/useAuth";
import { usePeriod } from "../hooks/usePeriod";
import { formatPeriodMonth } from "../store/PeriodContext";
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
  TopCounterpartiesResponse,
  WalletBalanceItem,
} from "../types";

type NetWorthPeriod = "1m" | "3m" | "6m" | "1y";

const NET_WORTH_PERIODS: NetWorthPeriod[] = ["1m", "3m", "6m", "1y"];


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
  const { t } = useTranslation();
  const data = history.history.map((point) => ({ date: point.date, value: Number(point.value) }));
  if (data.length < 2) {
    return <p className="easyb-eyebrow light">{t("analytics.notEnoughHistory")}</p>;
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
            formatter={(value: number) => [`${value.toFixed(2)} ${history.base_currency}`, t("analytics.netWorth")]}
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
  const { t } = useTranslation();
  const data = forecast.projected_series.map((point) => ({ date: point.date, balance: Number(point.projected_balance) }));
  if (data.length < 2) {
    return <p className="easyb-tx-meta">{t("analytics.notEnoughDaysLeft")}</p>;
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
          formatter={(value: number) => [`${value.toFixed(2)} ${forecast.currency}`, t("analytics.projectedBalance")]}
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
  const { t } = useTranslation();
  const data = history.history.map((point) => ({ date: point.date, balance: Number(point.balance) }));
  if (data.length < 2) {
    return <p className="easyb-tx-meta">{t("analytics.notEnoughLedgerHistory")}</p>;
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
  const { t } = useTranslation();
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
      setQuoteError(err instanceof ApiError ? err.message : t("analytics.couldNotGetQuote"));
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
      setError(err instanceof ApiError ? err.message : t("analytics.somethingWentWrong"));
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
        aria-label={mode === "contribute" ? t("analytics.addMoneyToGoal") : mode === "withdraw" ? t("analytics.withdrawFromGoal") : t("analytics.deleteGoal")}
        className="tile"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: "380px", width: "100%" }}
      >
        <div className="tile__header">
          <span className="eyebrow">
            {mode === "contribute"
              ? t("analytics.addMoneyTitle", { name: goal.name })
              : mode === "withdraw"
                ? t("analytics.withdrawTitle", { name: goal.name })
                : t("analytics.deleteTitle", { name: goal.name })}
          </span>
          <button
            type="button"
            className="button--ghost card-panel__icon-action"
            onClick={onClose}
            aria-label={t("analytics.close")}
            style={{ marginLeft: "auto" }}
          >
            <X size={15} strokeWidth={2.2} />
          </button>
        </div>

        {mode === "delete" && (
          <p style={{ marginBottom: "0.75rem" }}>
            {t("analytics.deleteConfirm", { name: goal.name })}
            {hasSavedMoney ? t("analytics.moneyReturnedToWallet") : t("analytics.cannotBeUndone")}
          </p>
        )}

        {needsWallet && (
          <label style={{ display: "block", marginBottom: "0.75rem" }}>
            {mode === "contribute" ? t("analytics.fromWallet") : t("analytics.toWallet")}
            <select value={walletId} onChange={(e) => setWalletId(e.target.value)} style={{ width: "100%", marginTop: "0.3rem" }}>
              {wallets.map((w) => (
                <option key={w.wallet_id} value={w.wallet_id}>
                  {t("analytics.availableSuffix", { currency: w.currency, balance: w.available_balance })}
                </option>
              ))}
            </select>
          </label>
        )}

        {mode === "contribute" && (
          <label style={{ display: "block", marginBottom: "0.75rem" }}>
            {t("analytics.amount")} {wallet ? `(${wallet.currency})` : ""}
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
            {t("analytics.withdrawsFull", { amount: fixedAmount, currency: goal.currency })}
          </p>
        )}
        {mode === "delete" && hasSavedMoney && (
          <p className="eyebrow" style={{ marginBottom: "0.75rem" }}>
            {t("analytics.returnsFull", { amount: fixedAmount, currency: goal.currency })}
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
              t("analytics.quoteSummary", {
                amount: quote.target_amount,
                currency: mode === "contribute" ? goal.currency : wallet.currency,
                rate: quote.exchange_rate,
                time: new Date(quote.expires_at).toLocaleTimeString(),
              })
            ) : (
              <>
                {mode === "contribute"
                  ? t("analytics.convertingContribute", { from: wallet.currency, to: goal.currency })
                  : t("analytics.convertingWithdraw", { from: goal.currency, to: wallet.currency })}
                <div style={{ marginTop: "0.5rem" }}>
                  <button type="button" className="button--ghost" onClick={fetchQuote} disabled={busy || !requestAmount || Number(requestAmount) <= 0}>
                    {t("analytics.getQuote")}
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
            {t("analytics.cancel")}
          </button>
          <button
            type="button"
            className={mode === "delete" ? "button--danger" : undefined}
            onClick={confirm}
            disabled={!canConfirm}
          >
            {busy ? t("analytics.working") : mode === "contribute" ? t("analytics.addMoney") : mode === "withdraw" ? t("analytics.withdraw") : t("analytics.deleteGoal")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function AnalyticsPage() {
  const { t, i18n } = useTranslation();
  const { query: periodQuery, period, isCurrentMonth } = usePeriod();
  const { accessToken, user } = useAuth();
  const isBusiness = user?.user_type === "BUSINESS";
  const [netWorth, setNetWorth] = useState<NetWorthResponse | null>(null);
  const [netWorthHistory, setNetWorthHistory] = useState<NetWorthHistoryResponse | null>(null);
  const [netWorthPeriod, setNetWorthPeriod] = useState<NetWorthPeriod>("1m");
  const [spendingByCategory, setSpendingByCategory] = useState<SpendingByCategoryResponse | null>(null);
  const [topCounterparties, setTopCounterparties] = useState<TopCounterpartiesResponse | null>(null);
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
    apiRequest<MonthlyTrendResponse>("/analytics/monthly-trend?months=6", { token: accessToken })
      .then((data) => !cancelled && setMonthlyTrend(data))
      .catch(() => !cancelled && setMonthlyTrend(null));
    apiRequest<ForecastResponse>("/analytics/forecast", { token: accessToken })
      .then((data) => !cancelled && setForecast(data))
      .catch(() => !cancelled && setForecast(null));
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
  }, [accessToken, reloadTick, isBusiness]);

  // Everything the app-wide month selector actually moves, kept in its own
  // effect rather than merged into the load above: re-running that block on
  // every month change would also re-request /analytics/insights, which on a
  // cache miss is a real Azure call per flagged category.
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;

    apiRequest<SpendingByCategoryResponse>(`/analytics/spending-by-category?${periodQuery}`, { token: accessToken })
      .then((data) => !cancelled && setSpendingByCategory(data))
      .catch(() => !cancelled && setSpendingByCategory(null));
    if (isBusiness) {
      apiRequest<TopCounterpartiesResponse>(`/analytics/top-counterparties?${periodQuery}`, { token: accessToken })
        .then((data) => !cancelled && setTopCounterparties(data))
        .catch(() => !cancelled && setTopCounterparties(null));
    }
    apiRequest<Budget[]>(`/budgets?${periodQuery}`, { token: accessToken })
      .then((data) => !cancelled && setBudgets(data))
      .catch(() => !cancelled && setBudgets([]));

    return () => {
      cancelled = true;
    };
  }, [accessToken, reloadTick, isBusiness, periodQuery]);

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

  const insights = generateAnalyticsInsights({
    monthlyTrend,
    spendingItems,
    budgets,
    forecast,
    isCurrentMonth,
    periodLabel: formatPeriodMonth(period, i18n.language),
  });

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
      window.alert(err instanceof ApiError ? err.message : t("analytics.couldNotRefreshRecommendations"));
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
      window.alert(err instanceof ApiError ? err.message : t("analytics.couldNotDismissRecommendation"));
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
      setGoalError(err instanceof ApiError ? err.message : t("analytics.couldNotCreateSavingsGoal"));
    } finally {
      setGoalSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <div className="tile" style={{ padding: "1.5rem" }}>
        <p className="status-line status-line--error">{t("analytics.couldNotLoad")}</p>
        <button type="button" onClick={() => { setLoadError(false); setReloadTick((tick) => tick + 1); }}>
          {t("analytics.tryAgain")}
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
              <div className="easyb-eyebrow light">{t("analytics.netWorth")}</div>
              <select
                className="easyb-hero-select"
                value={netWorthPeriod}
                onChange={(e) => setNetWorthPeriod(e.target.value as NetWorthPeriod)}
              >
                {NET_WORTH_PERIODS.map((period) => (
                  <option key={period} value={period}>
                    {t(`analytics.period.${period}`)}
                  </option>
                ))}
              </select>
            </div>
            <div className="easyb-hero-amount">
              {netWorth ? `${netWorth.total_available_balance} ${netWorth.base_currency}` : "—"}
            </div>
            {netWorthChangePercent !== null && (
              <div className="easyb-hero-sub" style={{ color: netWorthChangePercent >= 0 ? "#7ee3ab" : "#ff9b9b" }}>
                {netWorthChangePercent >= 0 ? "↑" : "↓"} {Math.abs(netWorthChangePercent).toFixed(1)}% {t("analytics.vsAgo", { period: t(`analytics.period.${netWorthPeriod}`).toLowerCase() })}
              </div>
            )}
          </div>
          {netWorthHistory && <NetWorthTrendChart history={netWorthHistory} />}
        </div>

        <div className="easyb-card">
          <div className="easyb-section-header">
            <div>
              <div className="easyb-eyebrow">{t("analytics.thisPeriod")}</div>
              <h2>{t("analytics.spendingOverview")}</h2>
            </div>
            <PeriodSelect />
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
            <p className="easyb-tx-meta">{t("analytics.noSpendingActivity")}</p>
          )}
        </div>

        {isBusiness && (
          <div className="easyb-card">
            <div className="easyb-section-header">
              <div>
                <div className="easyb-eyebrow">{t("analytics.thisPeriodBusiness")}</div>
                <h2>{t("analytics.topVendors")}</h2>
              </div>
            </div>
            {topCounterparties && topCounterparties.items.length > 0 ? (
              <div className="easyb-legend">
                {topCounterparties.items.map((item, index) => (
                  <div className="easyb-legend-row" key={`${item.name}-${item.currency}`}>
                    <span className="easyb-legend-dot" style={{ background: colorForType(String(index)) }} />
                    <span className="easyb-legend-name">
                      {item.name}
                      <span style={{ color: "var(--easyb-text-faint)", fontWeight: 400 }}>
                        {" "}
                        · {t("analytics.payment", { count: item.transaction_count })}
                      </span>
                    </span>
                    <span className="easyb-legend-pct">
                      {Number(item.total_amount).toFixed(2)} {item.currency}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="easyb-tx-meta">{t("analytics.noVendorSpend")}</p>
            )}
          </div>
        )}

        <div className="easyb-card">
          <div className="easyb-section-header">
            <h2>{t("analytics.cashFlowForecast")}</h2>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "flex-end", marginBottom: 10 }}>
            <label style={{ flex: 1, minWidth: 120 }}>
              {t("analytics.from")}
              <input
                type="date"
                value={historyDateFrom}
                max={historyDateTo || todayISO()}
                onChange={(e) => setHistoryDateFrom(e.target.value)}
              />
            </label>
            <label style={{ flex: 1, minWidth: 120 }}>
              {t("analytics.to")}
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
                {t("analytics.backToForecast")}
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
                  {t("analytics.balanceHistoryFor", { from: balanceHistory.date_from, to: balanceHistory.date_to })}
                </div>
                <BalanceHistoryChart history={balanceHistory} />
                <p className="easyb-tx-meta" style={{ marginTop: 8 }}>{balanceHistory.note}</p>
              </>
            ) : (
              <p className="easyb-tx-meta">{t("analytics.loadingBalanceHistory")}</p>
            )
          ) : forecast ? (
            <>
              <div className="balance-hero__amount" style={{ fontSize: "1.75rem" }}>
                {forecast.projected_month_end_balance} {forecast.currency}
              </div>
              <div className="easyb-tx-meta" style={{ marginBottom: 8 }}>
                {t("analytics.currentBalance", { balance: forecast.current_balance, currency: forecast.currency, days: forecast.days_remaining })}
              </div>
              <ForecastChart forecast={forecast} />
            </>
          ) : (
            <p className="easyb-tx-meta">{t("analytics.noForecastAvailable")}</p>
          )}
        </div>

        <div className="easyb-card" id="analytics-savings-goals">
          <div className="easyb-section-header">
            <h2>{t("analytics.savingsGoals")}</h2>
            <button
              type="button"
              className="easyb-link-btn"
              onClick={() => setGoalFormOpen((open) => !open)}
              style={{ background: "none", marginLeft: "auto" }}
            >
              <Plus size={14} /> {t("analytics.newGoal")}
            </button>
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
                        <CheckCircle2 size={12} strokeWidth={2.4} /> {t("analytics.completed")}
                      </span>
                    )}
                    {goal.status === "WITHDRAWN" && <span className="easyb-chip easyb-chip-neutral">{t("analytics.withdrawn")}</span>}
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
                      ? t("analytics.withdrawnBackToWallet")
                      : goal.status === "COMPLETED"
                        ? t("analytics.goalReached")
                        : goal.target_date
                          ? `${t("analytics.targetDate", { date: goal.target_date })}${goal.monthly_amount_needed ? t("analytics.saveMonthlyToArrive", { amount: goal.monthly_amount_needed, currency: goal.currency }) : ""}`
                          : t("analytics.noTargetDate")}
                  </span>
                </div>
                <div className="goal-card__actions">
                  {goal.status === "ACTIVE" && (netWorth?.wallets.length ?? 0) > 0 && (
                    <button type="button" onClick={() => setMoneyModal({ goal, mode: "contribute" })}>
                      {t("analytics.addMoney")}
                    </button>
                  )}
                  {goal.status !== "WITHDRAWN" && Number(goal.current_amount) > 0 && (netWorth?.wallets.length ?? 0) > 0 && (
                    <button type="button" className="button--ghost" onClick={() => setMoneyModal({ goal, mode: "withdraw" })}>
                      {t("analytics.withdraw")}
                    </button>
                  )}
                  <button type="button" className="button--ghost" onClick={() => setMoneyModal({ goal, mode: "delete" })}>
                    {t("analytics.delete")}
                  </button>
                </div>
              </div>
            ))
          ) : (
            <p className="easyb-tx-meta">{t("analytics.noSavingsGoalsYet")}</p>
          )}

          {goalFormOpen && (
            <form className="easyb-inline-form" onSubmit={submitGoal}>
              {goalError && <p className="status-line status-line--error">{goalError}</p>}
              <div className="easyb-inline-form-row">
                <label>
                  {t("analytics.name")}
                  <input value={goalName} onChange={(e) => setGoalName(e.target.value)} placeholder={t("analytics.namePlaceholder")} required />
                </label>
                <label>
                  {t("analytics.targetAmount")}
                  <input type="number" min="1" step="0.01" value={goalAmount} onChange={(e) => setGoalAmount(e.target.value)} required />
                </label>
              </div>
              <div className="easyb-inline-form-row">
                <label>
                  {t("analytics.currency")}
                  <select value={goalCurrency} onChange={(e) => setGoalCurrency(e.target.value)}>
                    {walletCurrencies.map((currency) => (
                      <option key={currency} value={currency}>
                        {currency}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("analytics.targetDateOptional")}
                  <input type="date" value={goalTargetDate} onChange={(e) => setGoalTargetDate(e.target.value)} />
                </label>
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <button type="submit" disabled={goalSubmitting}>
                  {goalSubmitting ? t("analytics.creating") : t("analytics.createGoal")}
                </button>
                <button type="button" className="button--ghost" onClick={() => setGoalFormOpen(false)}>
                  {t("analytics.cancel")}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      <div className="easyb-col">
        <div className="easyb-card">
          <div className="easyb-section-header">
            <h2>{t("analytics.insights")}</h2>
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
            <p className="easyb-tx-meta">{t("analytics.notEnoughActivityForInsights")}</p>
          )}
        </div>

        <div className="easyb-card">
          <div className="easyb-section-header">
            <span className="easyb-eyebrow" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <Sparkles size={14} strokeWidth={2.2} />
              {t("analytics.spendingRecommendations")}
            </span>
            <button
              type="button"
              className="button--ghost card-panel__icon-action"
              onClick={refreshInsights}
              disabled={refreshingInsights || aiInsights === null}
              aria-label={t("analytics.refreshRecommendations")}
              style={{ marginLeft: "auto" }}
            >
              <RefreshCw size={14} strokeWidth={2.2} className={refreshingInsights ? "spin" : undefined} />
            </button>
          </div>
          {aiInsights === null ? (
            <p className="easyb-tx-meta">{t("analytics.checkingSpending")}</p>
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
                  {dismissingInsightId === insight.id ? t("analytics.dismissing") : t("analytics.dismiss")}
                </button>
              </div>
            ))
          ) : (
            <p className="easyb-tx-meta">{t("analytics.noRecommendationsRightNow")}</p>
          )}
        </div>

        <div className="easyb-card easyb-savings-cta">
          <PiggyBank size={22} style={{ marginBottom: 8 }} />
          <h2>{t("analytics.setSavingsGoal")}</h2>
          <p>{t("analytics.setSavingsGoalDescription")}</p>
          <button
            type="button"
            onClick={() => {
              setGoalFormOpen(true);
              document.getElementById("analytics-savings-goals")?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          >
            {t("analytics.createGoal")}
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
