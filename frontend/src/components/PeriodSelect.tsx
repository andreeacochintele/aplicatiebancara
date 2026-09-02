import { useTranslation } from "react-i18next";

import { usePeriod } from "../hooks/usePeriod";
import type { PeriodMonth } from "../store/PeriodContext";

function label(month: PeriodMonth, locale: string): string {
  return new Date(month.year, month.month - 1, 1).toLocaleDateString(locale, {
    month: "long",
    year: "numeric",
  });
}

/**
 * App-wide month selector. Only the period-scoped views follow it — spending
 * breakdowns, top counterparties and monthly budgets. Point-in-time figures
 * (wallet balances, net worth, the month-end forecast) are always "now" by
 * definition and deliberately ignore it.
 */
export function PeriodSelect() {
  const { t, i18n } = useTranslation();
  const { period, choices, setPeriod, isCurrentMonth } = usePeriod();

  return (
    <select
      className={`easyb-period-select${isCurrentMonth ? "" : " easyb-period-select--past"}`}
      aria-label={t("period.selectMonth")}
      title={isCurrentMonth ? t("period.selectMonth") : t("period.viewingPast")}
      value={period.value}
      onChange={(event) => setPeriod(event.target.value)}
    >
      {choices.map((choice) => (
        <option key={choice.value} value={choice.value}>
          {label(choice, i18n.language)}
        </option>
      ))}
    </select>
  );
}
