// Shared utility functions (formatting, validation, etc.).

/** Groups an IBAN into 4-character blocks for display, e.g.
 * "RO49EASY1234567890123456" -> "RO49 EASY 1234 5678 9012 3456".
 * Purely cosmetic — never use the result for copy/paste or API calls,
 * the raw (unspaced) value is what the backend expects. */
export function formatIban(iban: string): string {
  return iban.replace(/(.{4})/g, "$1 ").trim();
}
