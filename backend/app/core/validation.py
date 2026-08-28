"""Shared field-level validators reused across request schemas."""
import re
import string
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field

_NAME_SEPARATORS = {" ", "-", "'"}
_SPECIAL_CHARS = set(string.punctuation)
_PASSWORD_MIN_LENGTH = 8
_PHONE_PATTERN = re.compile(r"\+[1-9]\d{7,14}")
_POSTAL_CODE_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9 -]{0,10}[A-Za-z0-9])?")
_MIN_BIRTH_YEAR = 1900
_MIN_ONBOARDING_AGE = 14
_MIN_OCCUPATION_LENGTH = 2
_MAX_MONTHLY_INCOME = Decimal("10000000")

# CNP (Romanian personal numeric code) checksum weights, per the official algorithm.
_CNP_WEIGHTS = (2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9)
# First digit (S) encodes sex + century of birth; 7/8 (resident foreigners) are
# conventionally issued for people born from 2000 onward.
_CNP_CENTURY_BY_S = {
    "1": 1900, "2": 1900,
    "3": 1800, "4": 1800,
    "5": 2000, "6": 2000,
    "7": 2000, "8": 2000,
}


def _validate_person_name(value: str) -> str:
    value = value.strip()
    if not value or not all(ch.isalpha() or ch in _NAME_SEPARATORS for ch in value):
        raise ValueError("must contain only letters, spaces, hyphens or apostrophes")
    if value[0] in _NAME_SEPARATORS or value[-1] in _NAME_SEPARATORS:
        raise ValueError("must not start or end with a separator")
    return value


def _validate_password_strength(value: str) -> str:
    if len(value) < _PASSWORD_MIN_LENGTH:
        raise ValueError(f"must be at least {_PASSWORD_MIN_LENGTH} characters long")
    if not any(ch.islower() for ch in value):
        raise ValueError("must contain at least one lowercase letter")
    if not any(ch.isupper() for ch in value):
        raise ValueError("must contain at least one uppercase letter")
    if not any(ch.isdigit() for ch in value):
        raise ValueError("must contain at least one digit")
    if not any(ch in _SPECIAL_CHARS for ch in value):
        raise ValueError("must contain at least one special character")
    return value


def _validate_phone_number(value: str) -> str:
    value = value.strip()
    if not _PHONE_PATTERN.fullmatch(value):
        raise ValueError("must be a valid phone number in international format, e.g. +40712345678")
    return value


def cnp_birth_date(value: str) -> date | None:
    """Best-effort birth date encoded in a CNP, or None when the century (S digit)
    doesn't determine one (e.g. S=9, other/undetermined cases)."""
    century = _CNP_CENTURY_BY_S.get(value[0])
    if century is None:
        return None
    try:
        return date(century + int(value[1:3]), int(value[3:5]), int(value[5:7]))
    except ValueError:
        return None


def cnp_checksum_is_valid(value: str) -> bool:
    """True if `value` is a 13-digit string whose control digit (position 13,
    MOD-11 over positions 1-12 with weights 2-7-9-1-4-6-3-5-8-2-7-9) matches.
    Structural-only check — doesn't verify the embedded date is a real one;
    see `cnp_birth_date` for that. Public because `mrz.py` also needs it to
    validate a CNP it reconstructs from an old-format ID card's MRZ."""
    if not value.isdigit() or len(value) != 13 or value[0] == "0":
        return False
    checksum = sum(int(digit) * weight for digit, weight in zip(value[:12], _CNP_WEIGHTS)) % 11
    control_digit = 1 if checksum == 10 else checksum
    return control_digit == int(value[12])


def _validate_cnp(value: str) -> str:
    value = value.strip()
    if not cnp_checksum_is_valid(value):
        raise ValueError("must be a valid 13-digit Romanian CNP")
    if value[0] != "9" and cnp_birth_date(value) is None:
        raise ValueError("CNP does not encode a valid birth date")
    return value


def _validate_date_of_birth(value: date) -> date:
    today = date.today()
    if value > today:
        raise ValueError("cannot be in the future")
    if value.year < _MIN_BIRTH_YEAR or value.year > today.year:
        raise ValueError(f"year must be between {_MIN_BIRTH_YEAR} and {today.year}")
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < _MIN_ONBOARDING_AGE:
        raise ValueError(f"you must be at least {_MIN_ONBOARDING_AGE} years old")
    return value


def _validate_street(value: str) -> str:
    value = value.strip()
    if not value or not any(ch.isalpha() for ch in value):
        raise ValueError("must contain at least one letter")
    return value


def _validate_optional_address_token(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not any(ch.isalnum() for ch in value):
        raise ValueError("must contain at least one letter or digit")
    return value


def _validate_postal_code(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _POSTAL_CODE_PATTERN.fullmatch(value):
        raise ValueError("must contain only letters, digits, spaces or hyphens (max 12 characters)")
    if not any(ch.isdigit() for ch in value):
        raise ValueError("must contain at least one digit")
    return value


def _validate_occupation(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) < _MIN_OCCUPATION_LENGTH:
        raise ValueError(f"must be at least {_MIN_OCCUPATION_LENGTH} characters long")
    if not any(ch.isalpha() for ch in value):
        raise ValueError("must contain at least one letter")
    return value


def _validate_monthly_income(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if value < 0:
        raise ValueError("must not be negative")
    if value > _MAX_MONTHLY_INCOME:
        raise ValueError(f"must be at most {_MAX_MONTHLY_INCOME}")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValueError("must have at most 2 decimal places")
    return value


PersonName = Annotated[str, Field(min_length=2, max_length=50), AfterValidator(_validate_person_name)]
StrongPassword = Annotated[str, AfterValidator(_validate_password_strength)]
PhoneNumber = Annotated[str, AfterValidator(_validate_phone_number)]
Cnp = Annotated[str, AfterValidator(_validate_cnp)]
DateOfBirth = Annotated[date, AfterValidator(_validate_date_of_birth)]
StreetName = Annotated[str, Field(min_length=1, max_length=255), AfterValidator(_validate_street)]
OptionalAddressToken = Annotated[str | None, Field(max_length=32), AfterValidator(_validate_optional_address_token)]
PostalCode = Annotated[str | None, Field(max_length=32), AfterValidator(_validate_postal_code)]
Occupation = Annotated[str | None, Field(max_length=100), AfterValidator(_validate_occupation)]
OptionalFreeText100 = Annotated[str | None, Field(max_length=100), AfterValidator(_validate_optional_address_token)]
OptionalFreeText255 = Annotated[str | None, Field(max_length=255), AfterValidator(_validate_optional_address_token)]
MonthlyIncome = Annotated[Decimal | None, AfterValidator(_validate_monthly_income)]
