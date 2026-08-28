"""Deterministic parsing of the Machine Readable Zone (MRZ) on identity
documents, per ICAO Doc 9303 Part 5 (TD1 — ID-1 card size, 3 lines x 30
chars) and Part 6 (TD2 — ID-2 card size, 2 lines x 36 chars).

This module only turns an already-read grid of MRZ characters into
structured, checksum-validated fields. It does not read pixels off a photo
(see the future `mrz_reader.py` for template-matching OCR) and it does not
compare the result against a user's declared profile data (that's the
service layer's job, once step 3's upload endpoint exists).

## Romanian identity cards: two different physical/MRZ formats

- New card (ID-1 size, credit-card sized, issued 2021+): standard ICAO TD1.
  `parse_td1()` below is a straightforward, high-confidence implementation
  of the public ICAO 9303 spec.
- Old card ("buletin", ID-2 size, larger plastic, issued 1997-2021): per
  HG 839/2006 (the Romanian regulation defining its format), its optical
  reading zone is 102mm x 17mm and contains "codul numeric personal (fara
  data nasterii)" - the personal numeric code WITHOUT the birth date. This
  strongly implies TD2 (2 lines x 36 chars), not TD1 - the dimensions match
  TD2's zone much better than TD1's, and 13 - 6 (YYMMDD digits) = 7 digits
  matches TD2's "optional data" field width (positions 29-35) exactly.
  `parse_td2()` implements the generic ICAO TD2 spec (high confidence - it's
  a public standard); `reconstruct_romanian_cnp_from_td2()` layers the
  Romania-specific interpretation on top (UNVERIFIED - no real old-format
  card was available to confirm field positions/padding against; treat its
  output as a hypothesis the service layer's cross-check will either
  corroborate or refute in practice, not a certainty).
"""
import re
from dataclasses import dataclass
from datetime import date

from app.core.validation import cnp_checksum_is_valid

_CHECK_WEIGHTS = (7, 3, 1)
_MRZ_CHAR_PATTERN = re.compile(r"^[A-Z0-9<]+$")

# OCR-B renders a few digit/letter pairs - 0/O especially - close enough
# that template matching alone can't always tell them apart (confirmed
# against both a real card photo and a synthetic render in mrz_reader.py's
# tests). Fields the ICAO 9303 spec defines as strictly numeric (dates,
# individual check digits) never legitimately contain a letter, so any
# letter read there is necessarily a misread of its digit look-alike -
# canonicalize it back before parsing/checksumming. Deliberately NOT
# applied to document_number or optional_data, which the spec allows to be
# genuinely alphanumeric.
_DIGIT_LOOKALIKES = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "S": "5", "Z": "2", "B": "8"})


def _canonicalize_numeric_field(raw: str) -> str:
    return raw.translate(_DIGIT_LOOKALIKES)


class MrzFormatError(ValueError):
    """Raised when input isn't a well-formed MRZ line (wrong length or an
    invalid character) - a structural problem, not a failed checksum. A
    failed checksum is an expected, common outcome (bad photo, real typo on
    the document) and is reported via the result's `*_check_valid` fields
    instead of an exception."""


def _char_value(ch: str) -> int:
    if ch.isdigit():
        return int(ch)
    if ch == "<":
        return 0
    return ord(ch) - ord("A") + 10  # 'A'-'Z' -> 10-35


def compute_check_digit(data: str) -> int:
    """ICAO 9303 check digit: MOD-10 over `data` with weights 7-3-1 cycling
    per character, left to right."""
    total = 0
    for index, ch in enumerate(data):
        total += _char_value(ch) * _CHECK_WEIGHTS[index % 3]
    return total % 10


def _require_mrz_line(line: str, expected_length: int, line_number: int) -> str:
    if len(line) != expected_length:
        raise MrzFormatError(f"line {line_number} must be exactly {expected_length} characters, got {len(line)}")
    if not _MRZ_CHAR_PATTERN.fullmatch(line):
        raise MrzFormatError(f"line {line_number} contains characters outside A-Z, 0-9, '<'")
    return line


def _check_digit_valid(data: str, check_char: str) -> bool:
    return check_char.isdigit() and compute_check_digit(data) == int(check_char)


def _year_2000_or_1900(two_digit_year: int, *, today: date) -> int:
    """Standard MRZ convention for a date-of-birth's ambiguous 2-digit year:
    prefer the 2000s unless that would place the birth date in the future,
    in which case it must be the 1900s."""
    candidate = 2000 + two_digit_year
    return candidate if candidate <= today.year else 1900 + two_digit_year


def _parse_yymmdd(raw: str, *, is_birth_date: bool) -> date | None:
    if not raw.isdigit() or len(raw) != 6:
        return None
    two_digit_year, month, day = int(raw[0:2]), int(raw[2:4]), int(raw[4:6])
    year = _year_2000_or_1900(two_digit_year, today=date.today()) if is_birth_date else 2000 + two_digit_year
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _split_name_field(name_field: str) -> tuple[str, str]:
    """'SURNAME<<GIVEN<NAMES<<<<<' -> ('SURNAME', 'GIVEN NAMES')."""
    surname_part, _, given_part = name_field.partition("<<")
    surname = surname_part.replace("<", " ").strip()
    given_names = " ".join(part for part in given_part.split("<") if part)
    return surname, given_names


@dataclass(frozen=True)
class Td1MrzResult:
    document_type: str
    issuing_state: str
    document_number: str
    document_number_check_valid: bool
    date_of_birth: date | None
    date_of_birth_check_valid: bool
    sex: str
    date_of_expiry: date | None
    date_of_expiry_check_valid: bool
    nationality: str
    optional_data_1: str
    optional_data_2: str
    composite_check_valid: bool
    surname: str
    given_names: str

    @property
    def all_checks_valid(self) -> bool:
        return (
            self.document_number_check_valid
            and self.date_of_birth is not None
            and self.date_of_birth_check_valid
            and self.date_of_expiry is not None
            and self.date_of_expiry_check_valid
            and self.composite_check_valid
        )


def parse_td1(line1: str, line2: str, line3: str) -> Td1MrzResult:
    """Parse a TD1 (ID-1 card, 3 x 30 char) MRZ. Field positions per ICAO
    9303 Part 5. Raises `MrzFormatError` if the lines aren't well-formed
    MRZ text; a wrong/mismatched check digit is reported via the result's
    boolean fields, not an exception."""
    _require_mrz_line(line1, 30, 1)
    _require_mrz_line(line2, 30, 2)
    _require_mrz_line(line3, 30, 3)

    document_number = line1[5:14]
    document_number_check_char = _canonicalize_numeric_field(line1[14])
    document_number_check_valid = _check_digit_valid(document_number, document_number_check_char)
    # Optional-data is issuer-defined free text per the generic ICAO spec,
    # but the Romanian CNP this project's caller expects here (see
    # mrz_extraction.py's _try_td1) is purely numeric, so the same
    # digit/letter look-alike correction applies - canonicalized here so
    # both the returned field and composite_input below agree.
    optional_data_1 = _canonicalize_numeric_field(line1[15:30])

    # Both segments below are always-numeric by spec (date + its check
    # digit) - canonicalized once and reused as-is in composite_input so
    # the individual and composite checks never disagree about what was
    # actually read.
    date_of_birth_segment = _canonicalize_numeric_field(line2[0:7])
    date_of_birth_raw, date_of_birth_check_char = date_of_birth_segment[:6], date_of_birth_segment[6]
    date_of_birth = _parse_yymmdd(date_of_birth_raw, is_birth_date=True)
    date_of_birth_check_valid = _check_digit_valid(date_of_birth_raw, date_of_birth_check_char)
    sex = line2[7]
    date_of_expiry_segment = _canonicalize_numeric_field(line2[8:15])
    date_of_expiry_raw, date_of_expiry_check_char = date_of_expiry_segment[:6], date_of_expiry_segment[6]
    date_of_expiry = _parse_yymmdd(date_of_expiry_raw, is_birth_date=False)
    date_of_expiry_check_valid = _check_digit_valid(date_of_expiry_raw, date_of_expiry_check_char)
    nationality = line2[15:18]
    optional_data_2 = line2[18:29]

    composite_input = document_number + document_number_check_char + optional_data_1 + date_of_birth_segment + date_of_expiry_segment + optional_data_2
    composite_check_valid = _check_digit_valid(composite_input, _canonicalize_numeric_field(line2[29]))

    surname, given_names = _split_name_field(line3)

    return Td1MrzResult(
        document_type=line1[0:2].replace("<", ""),
        issuing_state=line1[2:5],
        document_number=document_number.replace("<", ""),
        document_number_check_valid=document_number_check_valid,
        date_of_birth=date_of_birth,
        date_of_birth_check_valid=date_of_birth_check_valid,
        sex=sex,
        date_of_expiry=date_of_expiry,
        date_of_expiry_check_valid=date_of_expiry_check_valid,
        nationality=nationality,
        optional_data_1=optional_data_1.replace("<", ""),
        optional_data_2=optional_data_2.replace("<", ""),
        composite_check_valid=composite_check_valid,
        surname=surname,
        given_names=given_names,
    )


@dataclass(frozen=True)
class Td2MrzResult:
    document_type: str
    issuing_state: str
    surname: str
    given_names: str
    document_number: str
    document_number_check_valid: bool
    nationality: str
    date_of_birth: date | None
    date_of_birth_check_valid: bool
    sex: str
    date_of_expiry: date | None
    date_of_expiry_check_valid: bool
    optional_data: str
    composite_check_valid: bool

    @property
    def all_checks_valid(self) -> bool:
        return (
            self.document_number_check_valid
            and self.date_of_birth is not None
            and self.date_of_birth_check_valid
            and self.date_of_expiry is not None
            and self.date_of_expiry_check_valid
            and self.composite_check_valid
        )


def parse_td2(line1: str, line2: str) -> Td2MrzResult:
    """Parse a TD2 (ID-2 card, 2 x 36 char) MRZ per the generic, public
    ICAO 9303 Part 6 spec - this structure itself is standard and not
    Romania-specific. See the module docstring for the (unverified)
    Romania-specific interpretation of the optional-data field."""
    _require_mrz_line(line1, 36, 1)
    _require_mrz_line(line2, 36, 2)

    surname, given_names = _split_name_field(line1[5:36])

    document_number = line2[0:9]
    document_number_check_char = _canonicalize_numeric_field(line2[9])
    document_number_check_valid = _check_digit_valid(document_number, document_number_check_char)
    nationality = line2[10:13]

    # Always-numeric segments (date + its check digit) canonicalized once
    # and reused as-is in composite_input - see parse_td1 for why.
    date_of_birth_segment = _canonicalize_numeric_field(line2[13:20])
    date_of_birth_raw, date_of_birth_check_char = date_of_birth_segment[:6], date_of_birth_segment[6]
    date_of_birth = _parse_yymmdd(date_of_birth_raw, is_birth_date=True)
    date_of_birth_check_valid = _check_digit_valid(date_of_birth_raw, date_of_birth_check_char)
    sex = line2[20]
    date_of_expiry_segment = _canonicalize_numeric_field(line2[21:28])
    date_of_expiry_raw, date_of_expiry_check_char = date_of_expiry_segment[:6], date_of_expiry_segment[6]
    date_of_expiry = _parse_yymmdd(date_of_expiry_raw, is_birth_date=False)
    date_of_expiry_check_valid = _check_digit_valid(date_of_expiry_raw, date_of_expiry_check_char)
    # Same reasoning as TD1's optional_data_1: free text per the generic
    # spec, but the Romanian CNP fragment this project reconstructs from it
    # (reconstruct_romanian_cnp_from_td2 below) is purely numeric.
    optional_data = _canonicalize_numeric_field(line2[28:35])

    composite_input = document_number + document_number_check_char + date_of_birth_segment + date_of_expiry_segment + optional_data
    composite_check_valid = _check_digit_valid(composite_input, _canonicalize_numeric_field(line2[35]))

    return Td2MrzResult(
        document_type=line1[0:2].replace("<", ""),
        issuing_state=line1[2:5],
        surname=surname,
        given_names=given_names,
        document_number=document_number.replace("<", ""),
        document_number_check_valid=document_number_check_valid,
        nationality=nationality,
        date_of_birth=date_of_birth,
        date_of_birth_check_valid=date_of_birth_check_valid,
        sex=sex,
        date_of_expiry=date_of_expiry,
        date_of_expiry_check_valid=date_of_expiry_check_valid,
        optional_data=optional_data.replace("<", ""),
        composite_check_valid=composite_check_valid,
    )


def reconstruct_romanian_cnp_from_td2(result: Td2MrzResult) -> str | None:
    """UNVERIFIED (see module docstring): best-effort reconstruction of the
    full 13-digit CNP from an old-format Romanian ID card's TD2 optional-data
    field, which HG 839/2006 describes as holding the personal numeric code
    "fara data nasterii" (without the birth date) - i.e. 13 - 6 = 7 digits,
    matching the field's width exactly. Returns None if the pieces needed
    don't line up (missing/invalid birth date, wrong-shaped optional data),
    rather than guessing. Only returns a candidate whose own MOD-11 checksum
    checks out (`cnp_checksum_is_valid`) - a failed checksum here means
    either a misread MRZ character or that this reconstruction hypothesis
    itself is wrong, and either way a guess isn't worth returning."""
    if result.date_of_birth is None:
        return None
    fragment = result.optional_data
    if len(fragment) != 7 or not fragment.isdigit():
        return None
    sex_century_digit, county_sequence_and_check = fragment[0], fragment[1:]
    candidate = f"{sex_century_digit}{result.date_of_birth.strftime('%y%m%d')}{county_sequence_and_check}"
    return candidate if len(candidate) == 13 and cnp_checksum_is_valid(candidate) else None


__all__ = [
    "MrzFormatError",
    "Td1MrzResult",
    "Td2MrzResult",
    "compute_check_digit",
    "parse_td1",
    "parse_td2",
    "reconstruct_romanian_cnp_from_td2",
    "cnp_checksum_is_valid",
]
