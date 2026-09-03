// IBAN / BIC checking for the transfer form.
//
// Advisory only: the API still accepts whatever it is sent, so this exists to
// catch a mistyped account before the money moves, and to notice when an
// account is not an IBAN at all — the case where the payment needs a BIC to
// be routable.

/** Total IBAN length per country, from the ISO 13616 registry. A country
 *  being absent is meaningful, not an omission: it means that country does
 *  not use IBAN (US, CA, AU, NZ, JP, CN, IN, ZA, ...), so an account number
 *  from there is expected to fail the shape check and be routed by BIC. */
const IBAN_LENGTHS: Readonly<Record<string, number>> = {
  AD: 24, AE: 23, AL: 28, AT: 20, AZ: 28, BA: 20, BE: 16, BG: 22, BH: 22,
  BI: 27, BR: 29, BY: 28, CH: 21, CR: 22, CY: 28, CZ: 24, DE: 22, DJ: 27,
  DK: 18, DO: 28, EE: 20, EG: 29, ES: 24, FI: 18, FO: 18, FR: 27, GB: 22,
  GE: 22, GI: 23, GL: 18, GR: 27, GT: 28, HR: 21, HU: 28, IE: 22, IL: 23,
  IQ: 23, IS: 26, IT: 27, JO: 30, KW: 30, KZ: 20, LB: 28, LC: 32, LI: 21,
  LT: 20, LU: 20, LV: 21, LY: 25, MC: 27, MD: 24, ME: 22, MK: 19, MR: 27,
  MT: 31, MU: 30, NL: 18, NO: 15, PK: 24, PL: 28, PS: 29, PT: 25, QA: 29,
  RO: 24, RS: 22, RU: 33, SA: 24, SC: 31, SD: 18, SE: 24, SI: 19, SK: 24,
  SM: 27, SO: 23, ST: 25, SV: 28, TL: 23, TN: 24, TR: 26, UA: 29, VA: 22,
  VG: 24, XK: 20,
};

export type IbanCheck =
  | { status: "empty" }
  | { status: "valid" }
  /** Right country and length, wrong check digits — a typo. The fix is to
   *  correct the number, so this must NOT offer a BIC. */
  | { status: "bad-checksum" }
  /** Right country, wrong number of characters — also a typo. */
  | { status: "bad-length"; expected: number }
  /** Not an IBAN at all: no country+check-digit prefix, or a country that
   *  does not issue IBANs. This is the case a BIC is for. */
  | { status: "not-iban" };

/** Strips the spaces people paste in from statements, and the app's own
 *  formatIban output. */
export function normaliseIban(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

/** ISO 7064 mod 97-10: move the first four characters to the end, turn
 *  letters into digits (A=10 ... Z=35), and check the whole thing leaves a
 *  remainder of 1 when divided by 97. Done digit-group by digit-group
 *  because the number is far past Number.MAX_SAFE_INTEGER. */
function mod97(iban: string): number {
  const rearranged = iban.slice(4) + iban.slice(0, 4);
  let remainder = 0;
  for (const char of rearranged) {
    const part = char >= "A" && char <= "Z" ? String(char.charCodeAt(0) - 55) : char;
    for (const digit of part) {
      remainder = (remainder * 10 + Number(digit)) % 97;
    }
  }
  return remainder;
}

export function checkIban(value: string): IbanCheck {
  const iban = normaliseIban(value);
  if (iban === "") return { status: "empty" };
  // Two letters then two digits is what makes something an IBAN candidate.
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]+$/.test(iban)) return { status: "not-iban" };

  const expected = IBAN_LENGTHS[iban.slice(0, 2)];
  if (expected === undefined) return { status: "not-iban" };
  if (iban.length !== expected) return { status: "bad-length", expected };
  if (mod97(iban) !== 1) return { status: "bad-checksum" };
  return { status: "valid" };
}

/** True when the account needs a BIC to be routable — i.e. it is not an
 *  IBAN. A mistyped IBAN deliberately does not count: the user should fix
 *  the number rather than reach for a BIC. */
export function needsBic(check: IbanCheck): boolean {
  return check.status === "not-iban";
}

/** ISO 9362: four letters (institution), two letters (country), two
 *  alphanumerics (location), and an optional three-character branch. */
const BIC_PATTERN = /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/;

export function normaliseBic(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

export function isValidBic(value: string): boolean {
  return BIC_PATTERN.test(normaliseBic(value));
}
