import {
  Clock3, PiggyBank, PieChart as PieChartIcon, Plus, Target, TrendingUp, type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  Area, AreaChart, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { apiRequest, ApiError } from "../api/apiClient";
import { colorForType, friendlyTransactionType, monthLabel } from "../features/analytics/formatters";
import { generateAnalyticsInsights, type AnalyticsInsight } from "../features/analytics/insights";
import { useAuth } from "../hooks/useAuth";
import type {
  Budget,
  ForecastResponse,
  MonthlyTrendResponse,
  NetWorthHistoryResponse,
  NetWorthResponse,
  SavingsGoal,
  SpendingByTypeResponse,
} from "../types";

type NetWorthPeriod = "1m" | "3m" | "6m" | "1y";

const PERIOD_LABEL: Record<NetWorthPeriod, string> = {
  "1m": "This month",
  "3m": "3 months",
  "6m": "6 months",
  "1y": "1 year",
};

const INSIGHT_STYLE: Record<AnalyticsInsight["id"], { bg: string; fg: string; icon: LucideIcon }> = {
  trend: { bg: "var(--aurora-violet-soft)", fg: "var(--aurora-violet)", icon: TrendingUp },
  category: { bg: "var(--aurora-accent-soft)", fg: "var(--aurora-accent-dark)", icon: PieChartIcon },
  budget: { bg: "var(--aurora-green-soft)", fg: "var(--aurora-green)", icon: Target },
  forecast: { bg: "var(--aurora-pink-soft)", fg: "var(--aurora-pink)", icon: Clock3 },
};

function shortDate(date: string): string {
  return date.slice(5).replace("-", "/");
}

function NetWorthTrendChart({ history }: { history: NetWorthHistoryResponse }) {
  const data = history.history.map((point) => ({ date: point.date, value: Number(point.value) }));
  if (data.length < 2) {
    return <p className="aurora-eyebrow light">Not enough history yet to chart this period.</p>;
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
            contentStyle={{ borderRadius: 10, border: "1px solid var(--aurora-border)", fontSize: 12 }}
          />
          <Area type="monotone" dataKey="value" stroke="#fff" strokeWidth={2} fill="url(#netWorthFill)" dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function MonthlyTrendChart({ trend }: { trend: MonthlyTrendResponse }) {
  const data = trend.totals_by_month.map((item) => ({
    label: monthLabel(item.year, item.month),
    amount: Number(item.total_amount),
  }));
  if (data.length === 0) {
    return <p className="aurora-tx-meta">No spending history yet.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={data} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--aurora-text-faint)" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: "var(--aurora-text-faint)" }} axisLine={false} tickLine={false} width={44} />
        <Tooltip
          formatter={(value: number) => [`${value.toFixed(2)} ${trend.base_currency}`, "Spending"]}
          contentStyle={{ borderRadius: 10, border: "1px solid var(--aurora-border)", fontSize: 12 }}
        />
        <Line type="monotone" dataKey="amount" stroke="var(--aurora-accent)" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function ForecastChart({ forecast }: { forecast: ForecastResponse }) {
  const data = forecast.projected_series.map((point) => ({ date: point.date, balance: Number(point.projected_balance) }));
  if (data.length < 2) {
    return <p className="aurora-tx-meta">Not enough days left this month to project a trend.</p>;
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
            <stop offset="0%" stopColor="var(--aurora-accent)" stopOpacity={0.25} />
            <stop offset="100%" stopColor="var(--aurora-accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 10, fill: "var(--aurora-text-faint)" }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
        <YAxis domain={[min - pad, max + pad]} hide />
        <Tooltip
          formatter={(value: number) => [`${value.toFixed(2)} ${forecast.currency}`, "Projected balance"]}
          contentStyle={{ borderRadius: 10, border: "1px solid var(--aurora-border)", fontSize: 12 }}
        />
        <Area type="monotone" dataKey="balance" stroke="var(--aurora-accent)" strokeWidth={2} fill="url(#forecastFill)" dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function budgetFillColor(percentUsed: number): string {
  if (percentUsed >= 100) return "var(--aurora-red)";
  if (percentUsed >= 80) return "var(--aurora-amber)";
  return "var(--aurora-accent)";
}

export function AnalyticsPage() {
  const { accessToken } = useAuth();
  const [netWorth, setNetWorth] = useState<NetWorthResponse | null>(null);
  const [netWorthHistory, setNetWorthHistory] = useState<NetWorthHistoryResponse | null>(null);
  const [netWorthPeriod, setNetWorthPeriod] = useState<NetWorthPeriod>("1m");
  const [spendingByType, setSpendingByType] = useState<SpendingByTypeResponse | null>(null);
  const [monthlyTrend, setMonthlyTrend] = useState<MonthlyTrendResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [savingsGoals, setSavingsGoals] = useState<SavingsGoal[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  const [goalFormOpen, setGoalFormOpen] = useState(false);
  const [goalName, setGoalName] = useState("");
  const [goalAmount, setGoalAmount] = useState("");
  const [goalCurrency, setGoalCurrency] = useState("RON");
  const [goalTargetDate, setGoalTargetDate] = useState("");
  const [goalSubmitting, setGoalSubmitting] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;

    apiRequest<NetWorthResponse>("/analytics/net-worth", { token: accessToken })
      .then((data) => !cancelled && setNetWorth(data))
      .catch(() => !cancelled && setLoadError(true));
    apiRequest<SpendingByTypeResponse>("/analytics/spending-by-type", { token: accessToken })
      .then((data) => !cancelled && setSpendingByType(data))
      .catch(() => !cancelled && setSpendingByType(null));
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

  const spendingCurrency = netWorth?.base_currency ?? spendingByType?.items[0]?.currency;
  const spendingItems = spendingByType?.items.filter((item) => item.currency === spendingCurrency) ?? [];
  const spendingTotal = spendingItems.reduce((sum, item) => sum + Number(item.total_amount), 0);
  const donutData = spendingItems.map((item) => ({
    key: `${item.type}-${item.currency}`,
    name: friendlyTransactionType(item.type),
    value: Number(item.total_amount),
    color: colorForType(item.type),
  }));

  const insights = generateAnalyticsInsights({ monthlyTrend, spendingByType, budgets, forecast });

  const netWorthChangePercent = (() => {
    const history = netWorthHistory?.history ?? [];
    if (history.length < 2) return null;
    const first = Number(history[0].value);
    const last = Number(history[history.length - 1].value);
    if (first === 0) return null;
    return ((last - first) / Math.abs(first)) * 100;
  })();

  const walletCurrencies = Array.from(new Set(netWorth?.wallets.map((w) => w.currency) ?? ["RON"]));

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
    <div className="aurora-page">
      <div className="aurora-col">
        <div className="aurora-card aurora-hero">
          <div className="aurora-hero-blob aurora-blob-1" />
          <div className="aurora-hero-blob aurora-blob-2" />
          <div className="aurora-hero-top">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
              <div className="aurora-eyebrow light">Net worth</div>
              <select
                className="aurora-hero-select"
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
            <div className="aurora-hero-amount">
              {netWorth ? `${netWorth.total_available_balance} ${netWorth.base_currency}` : "—"}
            </div>
            {netWorthChangePercent !== null && (
              <div className="aurora-hero-sub" style={{ color: netWorthChangePercent >= 0 ? "#7ee3ab" : "#ff9b9b" }}>
                {netWorthChangePercent >= 0 ? "↑" : "↓"} {Math.abs(netWorthChangePercent).toFixed(1)}% vs {PERIOD_LABEL[netWorthPeriod].toLowerCase()} ago
              </div>
            )}
          </div>
          {netWorthHistory && <NetWorthTrendChart history={netWorthHistory} />}
        </div>

        <div className="aurora-wallet-grid">
          {netWorth?.wallets.map((wallet) => (
            <Link
              className="aurora-wallet-card"
              key={wallet.wallet_id}
              to="/wallets"
              style={{ "--wallet-accent": colorForType(wallet.currency), textDecoration: "none", color: "inherit", display: "block" } as CSSProperties}
            >
              <div className="aurora-wallet-card__top">
                <span className="aurora-wallet-card__code">{wallet.currency}</span>
                {wallet.is_main && <span className="aurora-chip aurora-chip-violet">Main</span>}
              </div>
              <div className="aurora-wallet-card__amount" style={{ color: "var(--wallet-accent)" }}>
                {wallet.available_balance}
              </div>
              {wallet.currency !== netWorth.base_currency && (
                <div className="aurora-wallet-card__sub">
                  ≈ {wallet.converted_available_balance} {netWorth.base_currency}
                </div>
              )}
            </Link>
          ))}
        </div>

        <div className="aurora-analytics-grid">
          <div className="aurora-card">
            <div className="aurora-section-header">
              <div>
                <div className="aurora-eyebrow">This period</div>
                <h2>Spending overview</h2>
              </div>
            </div>
            {donutData.length > 0 ? (
              <>
                <div className="aurora-donut-wrap">
                  <ResponsiveContainer width="100%" height={150}>
                    <PieChart>
                      <Pie data={donutData} dataKey="value" nameKey="name" innerRadius={48} outerRadius={68} paddingAngle={2} stroke="none">
                        {donutData.map((item) => (
                          <Cell key={item.key} fill={item.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(value: number, name: string) => [`${value.toFixed(2)} ${spendingCurrency ?? ""}`, name]}
                        contentStyle={{ borderRadius: 10, border: "1px solid var(--aurora-border)", fontSize: 12 }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="aurora-donut-center">
                    <div className="aurora-donut-total">{spendingTotal.toFixed(0)}</div>
                    <div className="aurora-donut-label">{spendingCurrency ?? ""}</div>
                  </div>
                </div>
                <div className="aurora-legend">
                  {donutData.map((item) => (
                    <Link
                      className="aurora-legend-row"
                      to="/transactions"
                      key={item.key}
                      style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
                    >
                      <span className="aurora-legend-dot" style={{ background: item.color }} />
                      <span className="aurora-legend-name">{item.name}</span>
                      <span className="aurora-legend-pct">
                        {spendingTotal > 0 ? Math.round((item.value / spendingTotal) * 100) : 0}%
                      </span>
                    </Link>
                  ))}
                </div>
              </>
            ) : (
              <p className="aurora-tx-meta">No spending activity for this period.</p>
            )}
          </div>

          <div className="aurora-card">
            <div className="aurora-section-header">
              <h2>Monthly trend · last 6 months</h2>
            </div>
            {monthlyTrend ? <MonthlyTrendChart trend={monthlyTrend} /> : <p className="aurora-tx-meta">We need more transaction history to show a trend.</p>}
          </div>
        </div>

        <div className="aurora-analytics-grid">
          <div className="aurora-card">
            <div className="aurora-section-header">
              <h2>Cash-flow forecast</h2>
            </div>
            {forecast ? (
              <>
                <div className="balance-hero__amount" style={{ fontSize: "1.6rem" }}>
                  {forecast.projected_month_end_balance} {forecast.currency}
                </div>
                <div className="aurora-tx-meta" style={{ marginBottom: 8 }}>
                  Current balance: {forecast.current_balance} {forecast.currency} · {forecast.days_remaining} days left this month
                </div>
                <ForecastChart forecast={forecast} />
                <p className="aurora-tx-meta" style={{ marginTop: 8 }}>{forecast.note}</p>
              </>
            ) : (
              <p className="aurora-tx-meta">No forecast available yet.</p>
            )}
          </div>

          <div className="aurora-card">
            <div className="aurora-section-header">
              <h2>Budgets</h2>
            </div>
            {budgets.length > 0 ? (
              budgets.map((budget) => (
                <div key={budget.id} style={{ marginBottom: "0.9rem" }}>
                  <div className="bar-row">
                    <span className="bar-row__label">{budget.name}</span>
                    <div className="bar-row__track">
                      <div
                        className="bar-row__fill"
                        style={{ width: `${Math.min(budget.percent_used, 100)}%`, background: budgetFillColor(budget.percent_used) }}
                      />
                    </div>
                    <span className="bar-row__value">
                      {budget.spent_amount} / {budget.limit_amount} {budget.currency}
                    </span>
                  </div>
                  <div className="aurora-tx-meta" style={{ paddingLeft: "0.1rem" }}>
                    {budget.percent_used >= 100
                      ? `Budget exceeded by ${(Number(budget.spent_amount) - Number(budget.limit_amount)).toFixed(2)} ${budget.currency}`
                      : `${budget.percent_used}% used`}
                    {" · "}
                    {budget.period.toLowerCase()} · {budget.days_remaining} days left
                  </div>
                </div>
              ))
            ) : (
              <p className="aurora-tx-meta">You don't have any active budgets.</p>
            )}
          </div>
        </div>

        <div className="aurora-card" id="analytics-savings-goals">
          <div className="aurora-section-header">
            <h2>Savings goals</h2>
            <button type="button" className="aurora-link-btn" onClick={() => setGoalFormOpen((open) => !open)} style={{ background: "none" }}>
              <Plus size={14} /> New goal
            </button>
          </div>
          {savingsGoals.length > 0 ? (
            savingsGoals.map((goal) => (
              <div key={goal.id} style={{ marginBottom: "0.75rem" }}>
                <div className="bar-row">
                  <span className="bar-row__label">{goal.name}</span>
                  <div className="bar-row__track">
                    <div className="bar-row__fill" style={{ width: `${Math.min(goal.percent_complete, 100)}%` }} />
                  </div>
                  <span className="bar-row__value">
                    {goal.current_amount} / {goal.target_amount} {goal.currency}
                  </span>
                </div>
                <div className="aurora-tx-meta" style={{ paddingLeft: "0.1rem" }}>
                  {goal.target_date
                    ? `Target ${goal.target_date}${goal.monthly_amount_needed ? ` · save ${goal.monthly_amount_needed} ${goal.currency} a month to arrive on time` : ""}`
                    : "No target date"}
                </div>
              </div>
            ))
          ) : (
            <p className="aurora-tx-meta">No savings goals yet.</p>
          )}

          {goalFormOpen && (
            <form className="aurora-inline-form" onSubmit={submitGoal}>
              {goalError && <p className="status-line status-line--error">{goalError}</p>}
              <div className="aurora-inline-form-row">
                <label>
                  Name
                  <input value={goalName} onChange={(e) => setGoalName(e.target.value)} placeholder="e.g. Emergency fund" required />
                </label>
                <label>
                  Target amount
                  <input type="number" min="1" step="0.01" value={goalAmount} onChange={(e) => setGoalAmount(e.target.value)} required />
                </label>
              </div>
              <div className="aurora-inline-form-row">
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

      <div className="aurora-col">
        <div className="aurora-card">
          <div className="aurora-section-header">
            <h2>Insights</h2>
          </div>
          {insights.length > 0 ? (
            insights.map((insight) => {
              const style = INSIGHT_STYLE[insight.id];
              const Icon = style.icon;
              return (
                <div className="aurora-insight-row" key={insight.id}>
                  <span className="aurora-insight-icon" style={{ background: style.bg, color: style.fg }}>
                    <Icon size={16} />
                  </span>
                  <div>
                    <div className="aurora-insight-text">{insight.message}</div>
                    {insight.ctaTo && (
                      <Link className="aurora-link-btn" to={insight.ctaTo} style={{ fontSize: 12, marginTop: 4 }}>
                        {insight.ctaLabel}
                      </Link>
                    )}
                  </div>
                </div>
              );
            })
          ) : (
            <p className="aurora-tx-meta">Not enough activity yet to generate insights.</p>
          )}
        </div>

        <div className="aurora-card aurora-savings-cta">
          <PiggyBank size={22} style={{ marginBottom: 8 }} />
          <h2>Set a savings goal</h2>
          <p>Create a goal and track your progress automatically.</p>
          <button
            type="button"
            onClick={() => {
              setGoalFormOpen(true);
              scrollToId("analytics-savings-goals");
            }}
          >
            Create goal
          </button>
        </div>
      </div>
    </div>
  );
}
