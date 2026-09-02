import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

/** The app-wide "which month am I looking at" selection, as `YYYY-MM`. */
export type PeriodMonth = { value: string; year: number; month: number };

const STORAGE_KEY = "banking_app_period";

/** How many months back the selector offers, including the current one. */
export const PERIOD_MONTH_CHOICES = 12;

interface PeriodContextValue {
  /** The selected month. Never null — defaults to the real current month. */
  period: PeriodMonth;
  /** Months available to pick, newest first. */
  choices: PeriodMonth[];
  setPeriod: (value: string) => void;
  /** True while the selection is the real current month. */
  isCurrentMonth: boolean;
  /** `year=YYYY&month=M`, ready to append to a request. */
  query: string;
}

export const PeriodContext = createContext<PeriodContextValue | undefined>(undefined);

/** "August 2026" / "august 2026", in the caller's locale. Lives here rather
 *  than in PeriodSelect because anything narrating the selected month needs
 *  to name it the same way the selector does. `style` trades width for
 *  readability: the pill on a card header uses "short", prose uses "long". */
export function formatPeriodMonth(
  month: PeriodMonth,
  locale: string,
  style: "long" | "short" = "long",
): string {
  return new Date(month.year, month.month - 1, 1).toLocaleDateString(locale, {
    month: style,
    year: "numeric",
  });
}

function toMonth(date: Date): PeriodMonth {
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  return { value: `${year}-${String(month).padStart(2, "0")}`, year, month };
}

function recentMonths(count: number): PeriodMonth[] {
  const now = new Date();
  // Date() normalises a negative month index into the previous year, so this
  // never needs manual year/month rollover arithmetic — which is exactly the
  // kind of thing that breaks silently on the 1st of January.
  return Array.from({ length: count }, (_, index) =>
    toMonth(new Date(now.getFullYear(), now.getMonth() - index, 1)),
  );
}

export function PeriodProvider({ children }: { children: ReactNode }) {
  const choices = useMemo(() => recentMonths(PERIOD_MONTH_CHOICES), []);
  const currentValue = choices[0].value;

  const [value, setValue] = useState<string>(() => {
    // A month stored on a previous visit can have fallen out of the window
    // (or be from a browser that hasn't been opened in a year), so it is only
    // honoured while it is still one of the offered choices.
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored && choices.some((choice) => choice.value === stored) ? stored : currentValue;
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, value);
  }, [value]);

  const setPeriod = useCallback((next: string) => setValue(next), []);

  const contextValue = useMemo<PeriodContextValue>(() => {
    const period = choices.find((choice) => choice.value === value) ?? choices[0];
    return {
      period,
      choices,
      setPeriod,
      isCurrentMonth: period.value === currentValue,
      query: `year=${period.year}&month=${period.month}`,
    };
  }, [choices, value, setPeriod, currentValue]);

  return <PeriodContext.Provider value={contextValue}>{children}</PeriodContext.Provider>;
}
