// Deterministic, rule-based insight generation for the Analytics sidebar.
// No LLM involved — every rule here is a plain comparison over data the page
// already fetched (architecture.md: keep financial/derived-metric logic out
// of the model, see CLAUDE.md §12).
//
// Locale: `t` is passed in from the caller's own useTranslation() (see
// AnalyticsPage.tsx) rather than this module calling useTranslation() itself
// — it's a plain function, not a component/hook, so it can't use hooks
// directly. Message strings live in i18n/locales/{en,ro}.json under
// "analytics.insight*", not hardcoded here.
import type { TFunction } from "i18next";

import type { Budget, ForecastResponse, MonthlyTrendResponse, SpendingByCategoryItem } from "../../types";

export type InsightKind = "trend" | "category" | "budget" | "forecast";

export interface AnalyticsInsight {
  id: InsightKind;
  message: string;
  ctaLabel?: string;
  ctaTo?: string;
}

interface InsightInputs {
  monthlyTrend: MonthlyTrendResponse | null;
  // Already filtered to a single currency by the caller (see AnalyticsPage's
  // spendingItems) — summing across currencies here would silently mix them,
  // the same bug the donut chart next to these insights was already careful
  // to avoid.
  spendingItems: SpendingByCategoryItem[];
  budgets: Budget[];
  forecast: ForecastResponse | null;
  // Not every input here covers the same span. spendingItems and budgets follow
  // the selected month, but monthly-trend always ends at the real current month
  // and the forecast only ever projects the real one — neither endpoint takes a
  // year/month. Narrating all four as "this month" was therefore wrong as soon
  // as a past month was selected, so the two that cannot follow the selection
  // are dropped while it points at the past.
  isCurrentMonth: boolean;
  // Names the month spendingItems and budgets actually cover, e.g. "August 2026".
  periodLabel: string;
}

export function generateAnalyticsInsights(
  { monthlyTrend, spendingItems, budgets, forecast, isCurrentMonth, periodLabel }: InsightInputs,
  t: TFunction,
): AnalyticsInsight[] {
  const insights: AnalyticsInsight[] = [];

  const totals = monthlyTrend?.totals_by_month ?? [];
  if (isCurrentMonth && totals.length >= 2) {
    const current = Number(totals[totals.length - 1].total_amount);
    const previous = Number(totals[totals.length - 2].total_amount);
    if (previous > 0) {
      const pct = Math.round(((current - previous) / previous) * 100);
      if (Math.abs(pct) >= 5) {
        insights.push({
          id: "trend",
          message: t(pct > 0 ? "analytics.insightTrendHigher" : "analytics.insightTrendLower", {
            pct: Math.abs(pct),
          }),
          ctaLabel: t("analytics.insightViewTransactions"),
          ctaTo: "/transactions",
        });
      }
    }
  }

  const totalSpend = spendingItems.reduce((sum, item) => sum + Number(item.total_amount), 0);
  if (totalSpend > 0) {
    const top = [...spendingItems].sort((a, b) => Number(b.total_amount) - Number(a.total_amount))[0];
    const pct = Math.round((Number(top.total_amount) / totalSpend) * 100);
    if (pct >= 40) {
      insights.push({
        id: "category",
        message: t("analytics.insightCategoryShareInPeriod", { category: top.category, pct, period: periodLabel }),
        ctaLabel: t("analytics.insightViewBreakdown"),
        ctaTo: "/transactions",
      });
    }
  }

  // Weekly budgets stay on the real current week whatever month is selected
  // ("which week of August" has no answer, see BudgetService._period_bounds),
  // so only the monthly ones can be spoken about alongside a past month.
  const scopedBudgets = isCurrentMonth ? budgets : budgets.filter((budget) => budget.period === "MONTHLY");
  if (scopedBudgets.length > 0) {
    const overBudget = scopedBudgets.find((budget) => budget.percent_used >= 100);
    if (overBudget) {
      insights.push({
        id: "budget",
        message: isCurrentMonth
          ? t("analytics.insightBudgetOver", { name: overBudget.name })
          : t("analytics.insightBudgetOverInPeriod", { name: overBudget.name, period: periodLabel }),
      });
    } else {
      insights.push({
        id: "budget",
        message: isCurrentMonth
          ? t("analytics.insightBudgetOnTrack")
          : t("analytics.insightBudgetOnTrackInPeriod", { period: periodLabel }),
      });
    }
  }

  if (isCurrentMonth && forecast) {
    const positive = Number(forecast.projected_month_end_balance) >= Number(forecast.current_balance);
    insights.push({
      id: "forecast",
      message: t(positive ? "analytics.insightForecastPositive" : "analytics.insightForecastNegative"),
    });
  }

  return insights;
}
