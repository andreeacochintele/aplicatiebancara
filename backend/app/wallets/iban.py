"""Sandbox IBAN generation for wallets — mirrors the mock PAN approach in
app/cards/service.py: not a real bank account, but a checksum-valid IBAN
(ISO 7064 mod 97-10) so it looks and validates like a real one."""
import secrets

BANK_CODE = "EASY"
COUNTRY_CODE = "RO"


def _iban_check_digits(bban: str) -> str:
    rearranged = bban + COUNTRY_CODE + "00"
    numeric = "".join(str(ord(char) - 55) if char.isalpha() else char for char in rearranged)
    return f"{98 - (int(numeric) % 97):02d}"


def generate_iban() -> str:
    account_number = "".join(str(secrets.randbelow(10)) for _ in range(16))
    bban = BANK_CODE + account_number
    return f"{COUNTRY_CODE}{_iban_check_digits(bban)}{bban}"
