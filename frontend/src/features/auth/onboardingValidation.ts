// Mirrors the server-side rules in backend/app/core/validation.py so the
// onboarding wizard can show errors before hitting the API.

const CNP_WEIGHTS = [2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9];
const CNP_CENTURY_BY_S: Record<string, number> = {
  "1": 1900,
  "2": 1900,
  "3": 1800,
  "4": 1800,
  "5": 2000,
  "6": 2000,
  "7": 2000,
  "8": 2000,
};
const MIN_BIRTH_YEAR = 1900;
const MIN_ONBOARDING_AGE = 14;

function isRealCalendarDate(year: number, month: number, day: number): boolean {
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day;
}

function toIsoDate(year: number, month: number, day: number): string {
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function cnpBirthDateIso(cnp: string): string | null {
  const century = CNP_CENTURY_BY_S[cnp[0]];
  if (century === undefined) return null;
  const year = century + Number(cnp.slice(1, 3));
  const month = Number(cnp.slice(3, 5));
  const day = Number(cnp.slice(5, 7));
  if (!isRealCalendarDate(year, month, day)) return null;
  return toIsoDate(year, month, day);
}

export function validateCnp(value: string): string | null {
  const trimmed = value.trim();
  if (!/^\d{13}$/.test(trimmed) || trimmed[0] === "0") {
    return "CNP must be a valid 13-digit Romanian CNP";
  }
  const digits = trimmed.split("").map(Number);
  const checksum = digits.slice(0, 12).reduce((sum, digit, i) => sum + digit * CNP_WEIGHTS[i], 0) % 11;
  const controlDigit = checksum === 10 ? 1 : checksum;
  if (controlDigit !== digits[12]) {
    return "CNP checksum is invalid";
  }
  if (trimmed[0] !== "9" && cnpBirthDateIso(trimmed) === null) {
    return "CNP does not encode a valid birth date";
  }
  return null;
}

export function cnpMatchesDateOfBirth(cnp: string, dateOfBirth: string): boolean {
  const expected = cnpBirthDateIso(cnp.trim());
  return expected === null || expected === dateOfBirth;
}

export function validateDateOfBirth(iso: string): string | null {
  if (!iso) return "Date of birth is required";
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d || !isRealCalendarDate(y, m, d)) {
    return "Enter a real date";
  }
  const today = new Date();
  const todayIso = toIsoDate(today.getFullYear(), today.getMonth() + 1, today.getDate());
  if (iso > todayIso) return "Date of birth cannot be in the future";
  const currentYear = today.getFullYear();
  if (y < MIN_BIRTH_YEAR || y > currentYear) return `Year must be between ${MIN_BIRTH_YEAR} and ${currentYear}`;
  let age = currentYear - y;
  const beforeBirthdayThisYear = today.getMonth() + 1 < m || (today.getMonth() + 1 === m && today.getDate() < d);
  if (beforeBirthdayThisYear) age -= 1;
  if (age < MIN_ONBOARDING_AGE) return `You must be at least ${MIN_ONBOARDING_AGE} years old`;
  return null;
}

export function validateStreet(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed || !/\p{L}/u.test(trimmed)) {
    return "Street must contain at least one letter";
  }
  return null;
}

export function validatePostalCode(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9 -]{0,10}[A-Za-z0-9])?$/.test(trimmed)) {
    return "Postal code must contain only letters, digits, spaces or hyphens (max 12 characters)";
  }
  if (!/\d/.test(trimmed)) {
    return "Postal code must contain at least one digit";
  }
  return null;
}

export function validateAddressToken(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!/[A-Za-z0-9]/.test(trimmed)) {
    return "Must contain at least one letter or digit";
  }
  return null;
}

const MIN_OCCUPATION_LENGTH = 2;
const MAX_MONTHLY_INCOME = 10_000_000;

export function validateOccupation(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.length < MIN_OCCUPATION_LENGTH) {
    return `Occupation must be at least ${MIN_OCCUPATION_LENGTH} characters long`;
  }
  if (!/\p{L}/u.test(trimmed)) {
    return "Occupation must contain at least one letter";
  }
  return null;
}

export function validateOptionalFreeText(value: string, label: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!/[\p{L}\p{N}]/u.test(trimmed)) {
    return `${label} must contain at least one letter or digit`;
  }
  return null;
}

export function validateMonthlyIncome(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const numeric = Number(trimmed);
  if (Number.isNaN(numeric)) return "Enter a valid amount";
  if (numeric < 0) return "Amount must not be negative";
  if (numeric > MAX_MONTHLY_INCOME) return `Amount must be at most ${MAX_MONTHLY_INCOME.toLocaleString()}`;
  const decimalPart = trimmed.split(".")[1];
  if (decimalPart && decimalPart.length > 2) return "Amount must have at most 2 decimal places";
  return null;
}
