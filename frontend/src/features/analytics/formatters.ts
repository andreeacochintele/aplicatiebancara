// Presentation-only helpers for the Analytics page: friendly labels and the
// deterministic per-category colour used by both the donut and its legend.
// No transaction_categories table exists yet (blocked on the Payments module),
// so "category" here is still TransactionType — this just relabels it for display
// without touching the stored value.

const TYPE_LABELS: Record<string, string> = {
  CARD_PAYMENT: "Card payments",
  TRANSFER: "Transfers",
  CASHBACK: "Cashback",
  LOAN_PAYMENT: "Loan payments",
  SCHEDULED_PAYMENT: "Scheduled payments",
  BILL_SPLIT_PAYMENT: "Bill splits",
  FX: "Currency exchange",
};

export function friendlyTransactionType(type: string): string {
  return (
    TYPE_LABELS[type] ??
    type
      .toLowerCase()
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function monthLabel(year: number, month: number): string {
  return `${MONTH_NAMES[month - 1]} ${year}`;
}

export function hueFromString(value: string): number {
  return Math.abs([...value].reduce((sum, ch) => sum + ch.charCodeAt(0), 0)) % 360;
}

export function colorForType(type: string): string {
  const hue = hueFromString(type);
  const index = (hue % 5) + 1;
  return `var(--easyb-type-color-${index}, hsl(${hue} 62% 55%))`;
}
