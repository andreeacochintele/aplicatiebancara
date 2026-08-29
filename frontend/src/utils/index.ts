// Shared utility functions (formatting, validation, etc.).

/** Groups an IBAN into 4-character blocks for display, e.g.
 * "RO49EASY1234567890123456" -> "RO49 EASY 1234 5678 9012 3456".
 * Purely cosmetic — never use the result for copy/paste or API calls,
 * the raw (unspaced) value is what the backend expects. */
export function formatIban(iban: string): string {
  return iban.replace(/(.{4})/g, "$1 ").trim();
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
