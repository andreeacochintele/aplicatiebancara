// Shared utility functions (formatting, validation, etc.).

/** Groups an IBAN into 4-character blocks for display, e.g.
 * "RO49EASY1234567890123456" -> "RO49 EASY 1234 5678 9012 3456".
 * Purely cosmetic — never use the result for copy/paste or API calls,
 * the raw (unspaced) value is what the backend expects. */
export function formatIban(iban: string): string {
  return iban.replace(/(.{4})/g, "$1 ").trim();
}

/** Four-per-em space (U+2005): a quarter of an em, so clearly narrower than
 *  a word space but wide enough to actually separate the groups. Tune the
 *  gap by swapping this one constant - U+202F and U+2009 are narrower,
 *  U+2004 wider. */
const DIGIT_GROUP_SEPARATOR = "\u2005";

/** Below five digits an amount reads fine unbroken; grouping "4009" only adds
 *  noise. Five is where the app's own balances start being hard to scan. */
const MIN_GROUPED_DIGITS = 5;

/** Groups the whole part of an amount in threes, e.g. "108764.28" ->
 * "108 764.28" and "-200000.0" -> "-200 000.0". The fractional part is left
 * exactly as given, so this never changes how many decimals a caller shows.
 *
 * Deliberately not Number.toLocaleString: that groups by the *browser's*
 * locale, which put commas in some screens and dots in others depending on
 * the machine, while every other amount in the app renders the raw decimal
 * string. Grouping here is the same everywhere and for everyone.
 *
 * Anything that is not a leading run of digits is returned untouched. */
export function groupDigits(value: string | number): string {
  const text = typeof value === "number" ? String(value) : value.trim();
  const parts = /^(-?)(\d+)(.*)$/.exec(text);
  if (parts === null) return text;
  const [, sign, whole, rest] = parts;
  if (whole.length < MIN_GROUPED_DIGITS) return text;
  return sign + whole.replace(/\B(?=(\d{3})+$)/g, DIGIT_GROUP_SEPARATOR) + rest;
}

/** An amount fixed to `fractionDigits` decimals and then digit-grouped.
 *  For the screens that want a consistent "1 234.50" rather than whatever
 *  precision the API happened to serialize. */
export function formatDecimalAmount(value: number, fractionDigits = 2): string {
  return groupDigits(value.toFixed(fractionDigits));
}

/** A user can hold more than one wallet in the same currency, so any
 * dropdown/list showing wallets needs more than the currency code to tell
 * them apart — the nickname when set, else the last 4 IBAN digits. */
export function walletLabel(wallet: { currency: string; nickname: string | null; iban: string }): string {
  if (wallet.nickname) return `${wallet.currency} — ${wallet.nickname}`;
  return `${wallet.currency} (····${wallet.iban.slice(-4)})`;
}

/** Live-formats a card-number input as the user types: digits only, capped
 * at 16, grouped every 4 characters — e.g. "4000123456786387" ->
 * "4000 1234 5678 6387". Matches the spacing EasyB's own mock_pan already
 * uses, so a copy-pasted card number from the Cards page needs no manual
 * cleanup, but the backend re-normalizes (strips whitespace) either way. */
export function formatCardNumberInput(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 16);
  return digits.replace(/(.{4})/g, "$1 ").trim();
}

/** Live-formats an expiry input as the user types: digits only, capped at 4,
 * auto-inserting "/" after the 2nd digit — e.g. "1225" -> "12/25". */
export function formatExpiryInput(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 4);
  return digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits;
}

/** Parses a "MM/YY" expiry display value into the full-year shape the
 * backend expects, or null if the input isn't a complete, valid MM/YY. */
export function parseExpiryInput(value: string): { month: number; year: number } | null {
  const match = /^(\d{2})\/(\d{2})$/.exec(value);
  if (!match) return null;
  const month = Number(match[1]);
  if (month < 1 || month > 12) return null;
  return { month, year: 2000 + Number(match[2]) };
}

/** Saves a file-download `fetch` Response to disk client-side: reads the
 * server-suggested filename off Content-Disposition (falling back to
 * `fallbackName`), then drives the browser's save dialog via a throwaway
 * object URL. Shared by every page that streams back a CSV/PDF export
 * instead of JSON. */
export async function downloadBlob(response: Response, fallbackName: string): Promise<void> {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = match?.[1] ?? fallbackName;
  link.click();
  URL.revokeObjectURL(objectUrl);
}
