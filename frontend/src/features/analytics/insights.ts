// Deterministic, rule-based insight generation for the Analytics sidebar.
// No LLM involved — every rule here is a plain comparison over data the page
// already fetched (architecture.md: keep financial/derived-metric logic out
// of the model, see CLAUDE.md §12).
import type { Budget, ForecastResponse, MonthlyTrendResponse, SpendingByTypeResponse } from "../../types";
import { friendlyTransactionType } from "./formatters";

export type InsightKind = "trend" | "category" | "budget" | "forecast";

export interface AnalyticsInsight {
  id: InsightKind;
  message: string;
  ctaLabel?: string;
  ctaTo?: string;
}

interface InsightInputs {
  monthlyTrend: MonthlyTrendResponse | null;
  spendingByType: SpendingByTypeResponse | null;
  budgets: Budget[];
  forecast: ForecastResponse | null;
}

export function generateAnalyticsInsights({
  monthlyTrend,
  spendingByType,
  budgets,
  forecast,
}: InsightInputs): AnalyticsInsight[] {
  const insights: AnalyticsInsight[] = [];

  const totals = monthlyTrend?.totals_by_month ?? [];
  if (totals.length >= 2) {
    const current = Number(totals[totals.length - 1].total_amount);
    const previous = Number(totals[totals.length - 2].total_amount);
    if (previous > 0) {
      const pct = Math.round(((current - previous) / previous) * 100);
      if (Math.abs(pct) >= 5) {
        insights.push({
          id: "trend",
          message: `Your spending is ${Math.abs(pct)}% ${pct > 0 ? "higher" : "lower"} than last month.`,
          ctaLabel: "View transactions",
          ctaTo: "/transactions",
        });
      }
    }
  }

  const items = spendingByType?.items ?? [];
  const totalSpend = items.reduce((sum, item) => sum + Number(item.total_amount), 0);
  if (totalSpend > 0) {
    const top = [...items].sort((a, b) => Number(b.total_amount) - Number(a.total_amount))[0];
    const pct = Math.round((Number(top.total_amount) / totalSpend) * 100);
    if (pct >= 40) {
      insights.push({
        id: "category",
        message: `${friendlyTransactionType(top.type)} represent ${pct}% of your spending this month.`,
        ctaLabel: "View breakdown",
        ctaTo: "/transactions",
      });
    }
  }

  if (budgets.length > 0) {
    const overBudget = budgets.find((budget) => budget.percent_used >= 100);
    insights.push(
      overBudget
        ? { id: "budget", message: `${overBudget.name} is over budget.` }
        : { id: "budget", message: "You're on track to stay within budget." },
    );
  }

  if (forecast) {
    const positive = Number(forecast.projected_month_end_balance) >= Number(forecast.current_balance);
    insights.push({
      id: "forecast",
      message: positive
        ? "Your cash-flow forecast is positive this month."
        : "Your projected balance is trending down this month.",
    });
  }

  return insights;
}
