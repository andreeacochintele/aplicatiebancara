import { useEffect, useState } from "react";

import { apiRequest } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";
import type { Budget, SavingsGoal } from "../types";

export function AnalyticsPage() {
  const { accessToken } = useAuth();
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [savingsGoals, setSavingsGoals] = useState<SavingsGoal[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    apiRequest<Budget[]>("/budgets", { token: accessToken })
      .then(setBudgets)
      .catch(() => setBudgets([]));
    apiRequest<SavingsGoal[]>("/savings", { token: accessToken })
      .then(setSavingsGoals)
      .catch(() => setSavingsGoals([]));
  }, [accessToken]);

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
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
