import { useEffect, useState } from "react";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type {
  Budget,
  ForecastResponse,
  MonthlyTrendResponse,
  NetWorthResponse,
  SavingsGoal,
  SpendingByTypeResponse,
} from "../types";

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function AnalyticsPage() {
  const { accessToken } = useAuth();
  const [netWorth, setNetWorth] = useState<NetWorthResponse | null>(null);
  const [spendingByType, setSpendingByType] = useState<SpendingByTypeResponse | null>(null);
  const [monthlyTrend, setMonthlyTrend] = useState<MonthlyTrendResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [savingsGoals, setSavingsGoals] = useState<SavingsGoal[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    apiRequest<NetWorthResponse>("/analytics/net-worth", { token: accessToken })
      .then(setNetWorth)
      .catch(() => setNetWorth(null));
    apiRequest<SpendingByTypeResponse>("/analytics/spending-by-type", { token: accessToken })
      .then(setSpendingByType)
      .catch(() => setSpendingByType(null));
    apiRequest<MonthlyTrendResponse>("/analytics/monthly-trend?months=6", { token: accessToken })
      .then(setMonthlyTrend)
      .catch(() => setMonthlyTrend(null));
    apiRequest<ForecastResponse>("/analytics/forecast", { token: accessToken })
      .then(setForecast)
      .catch(() => setForecast(null));
    apiRequest<Budget[]>("/budgets", { token: accessToken })
      .then(setBudgets)
      .catch(() => setBudgets([]));
    apiRequest<SavingsGoal[]>("/savings", { token: accessToken })
      .then(setSavingsGoals)
      .catch(() => setSavingsGoals([]));
  }, [accessToken]);

  const maxSpendingAmount = Math.max(
    1,
    ...(spendingByType?.items.map((item) => Number(item.total_amount)) ?? [0]),
  );
  const maxTrendAmount = Math.max(
    1,
    ...(monthlyTrend?.items.map((item) => Number(item.total_amount)) ?? [0]),
  );

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="eyebrow">Net worth</div>
        <div className="balance-hero__amount">
          {netWorth ? `${netWorth.total_available_balance} ${netWorth.base_currency}` : "—"}
        </div>
        <div className="wallet-grid">
          {netWorth?.wallets.map((wallet) => (
            <div className="wallet-chip" key={wallet.wallet_id}>
              <div className="wallet-chip__ccy">
                {wallet.currency}
                {wallet.is_main && <span className="tag tag--accent">MAIN</span>}
              </div>
              <div className="wallet-chip__amount">{wallet.available_balance}</div>
              {wallet.currency !== netWorth?.base_currency && (
                <div className="eyebrow" style={{ marginTop: "0.2rem" }}>
                  ≈ {wallet.converted_available_balance} {netWorth?.base_currency}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">
            Spending by type {spendingByType && `· ${spendingByType.period_start.slice(0, 7)}`}
          </span>
        </div>
        {spendingByType && spendingByType.items.length > 0 ? (
          spendingByType.items.map((item) => (
            <div className="bar-row" key={item.type}>
              <span className="bar-row__label">{item.type}</span>
              <div className="bar-row__track">
                <div
                  className="bar-row__fill"
                  style={{ width: `${(Number(item.total_amount) / maxSpendingAmount) * 100}%` }}
                />
              </div>
              <span className="bar-row__value">
                {item.total_amount} {item.currency}
              </span>
            </div>
          ))
        ) : (
          <p className="eyebrow">No completed transactions this month yet.</p>
        )}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Monthly trend · last 6 months</span>
        </div>
        {monthlyTrend && monthlyTrend.items.length > 0 ? (
          monthlyTrend.items.map((item) => (
            <div className="bar-row" key={`${item.year}-${item.month}-${item.currency}`}>
              <span className="bar-row__label">
                {MONTH_NAMES[item.month - 1]} {item.year}
              </span>
              <div className="bar-row__track">
                <div
                  className="bar-row__fill"
                  style={{ width: `${(Number(item.total_amount) / maxTrendAmount) * 100}%` }}
                />
              </div>
              <span className="bar-row__value">
                {item.total_amount} {item.currency}
              </span>
            </div>
          ))
        ) : (
          <p className="eyebrow">No spending history yet.</p>
        )}
      </div>

      <div className="tile">
        <div className="eyebrow">Cash-flow forecast</div>
        <div className="balance-hero__amount">
          {forecast
            ? `${forecast.projected_month_end_balance} ${forecast.currency}`
            : "—"}
        </div>
        {forecast && (
          <>
            <div className="eyebrow" style={{ marginTop: "0.35rem" }}>
              Current balance: {forecast.current_balance} {forecast.currency} · {forecast.days_remaining} days left
              this month
            </div>
            <div className="eyebrow" style={{ marginTop: "0.5rem" }}>
              {forecast.note}
            </div>
          </>
        )}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Budgets</span>
        </div>
        {budgets.length > 0 ? (
          budgets.map((budget) => (
            <div key={budget.id} style={{ marginBottom: "0.75rem" }}>
              <div className="bar-row">
                <span className="bar-row__label">{budget.name}</span>
                <div className="bar-row__track">
                  <div
                    className="bar-row__fill"
                    style={{ width: `${Math.min(budget.percent_used, 100)}%` }}
                  />
                </div>
                <span className="bar-row__value">
                  {budget.spent_amount} / {budget.limit_amount} {budget.currency}
                </span>
              </div>
              <div className="eyebrow" style={{ paddingLeft: "0.1rem" }}>
                {budget.percent_used}% used · {budget.period.toLowerCase()} · {budget.days_remaining} days left
              </div>
            </div>
          ))
        ) : (
          <p className="eyebrow">No budgets yet.</p>
        )}
      </div>

      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">Savings goals</span>
        </div>
        {savingsGoals.length > 0 ? (
          savingsGoals.map((goal) => (
            <div key={goal.id} style={{ marginBottom: "0.75rem" }}>
              <div className="bar-row">
                <span className="bar-row__label">{goal.name}</span>
                <div className="bar-row__track">
                  <div
                    className="bar-row__fill"
                    style={{ width: `${Math.min(goal.percent_complete, 100)}%` }}
                  />
                </div>
                <span className="bar-row__value">
                  {goal.current_amount} / {goal.target_amount} {goal.currency}
                </span>
              </div>
              <div className="eyebrow" style={{ paddingLeft: "0.1rem" }}>
                {goal.target_date
                  ? `Target ${goal.target_date}${
                      goal.monthly_amount_needed
                        ? ` · save ${goal.monthly_amount_needed} ${goal.currency} a month to arrive on time`
                        : ""
                    }`
                  : "No target date"}
              </div>
            </div>
          ))
        ) : (
          <p className="eyebrow">No savings goals yet.</p>
        )}
      </div>
    </section>
  );
}
