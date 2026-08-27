"""Ties mrz_reader (single-line OCR) and mrz (line parsing) together to go
from a whole "back of the ID card" photo to a parsed, checksum-validated
identity — trying both TD1 (new card) and TD2 (old card) since the caller
doesn't know in advance which one it's looking at. DB-agnostic and
image-only on purpose (no User/UserProfile here) — see users/service.py
for the cross-check against the profile the user filled in at step 2.

## The weakest, least-validated part of this whole feature

Locating the MRZ band within an arbitrary uploaded photo — as opposed to
reading an already-cropped line, which mrz_reader.py handles — is a crude
heuristic here: assume the band sits in the bottom `_MRZ_BAND_FRACTION` of
the photo (per ICAO 9303's physical MRZ zone placement near the card's
bottom edge) and split that strip into equal-height lines. Real photos
vary enormously in framing, rotation, and how tightly the card fills the
frame; none of that is corrected for here. This is the piece most likely
to need rework once tested against a real photo (see mrz.py and
mrz_reader.py module docstrings for the other two documented unknowns:
the old card's TD2 layout, and real-photo OCR accuracy).
"""
import base64
import binascii
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.core.validation import cnp_checksum_is_valid
from app.users.mrz import MrzFormatError, parse_td1, parse_td2, reconstruct_romanian_cnp_from_td2
from app.users.mrz_reader import read_mrz_line

_MRZ_BAND_FRACTION = 0.28  # bottom ~28% of the photo, per ICAO 9303's physical MRZ zone placement
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB decoded — generous for a phone photo, cheap to reject earlier


@dataclass(frozen=True)
class ExtractedIdentity:
    detected_format: str  # "TD1" or "TD2"
    surname: str
    given_names: str
    cnp: str | None
    date_of_birth: date | None
    date_of_expiry: date | None


def decode_base64_image(value: str) -> Image.Image | None:
    """None (not an exception) on any failure — a corrupt/non-image upload
    is just another failed extraction attempt from the caller's point of
    view, not a different error class."""
    # Tolerate a data: URL prefix (data:image/jpeg;base64,...) - common from
    # <input type="file"> + FileReader on the frontend.
    _, _, encoded = value.rpartition(",") if value.startswith("data:") else (None, None, value)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not raw or len(raw) > _MAX_IMAGE_BYTES:
        return None
    try:
        image = Image.open(BytesIO(raw))
        image.load()
        return image
    except UnidentifiedImageError:
        return None


def _band_lines(back_image: Image.Image, line_count: int) -> list[Image.Image]:
    width, height = back_image.size
    band_top = round(height * (1 - _MRZ_BAND_FRACTION))
    band = back_image.crop((0, band_top, width, height))
    line_height = band.size[1] / line_count
    return [band.crop((0, round(i * line_height), width, round((i + 1) * line_height))) for i in range(line_count)]


def _try_td1(back_image: Image.Image) -> ExtractedIdentity | None:
    try:
        line1_img, line2_img, line3_img = _band_lines(back_image, 3)
        result = parse_td1(
            read_mrz_line(line1_img, 30),
            read_mrz_line(line2_img, 30),
            read_mrz_line(line3_img, 30),
        )
    except MrzFormatError:
        return None
    if not result.all_checks_valid:
        return None
    # Hypothesis, unverified against a real card (see module docstring on
    # the old card's equivalent): the new card's larger optional-data field
    # (15 chars, vs. the old card's 7) holds the full, untruncated CNP.
    cnp = result.optional_data_1 if len(result.optional_data_1) == 13 and cnp_checksum_is_valid(result.optional_data_1) else None
    return ExtractedIdentity(
        detected_format="TD1",
        surname=result.surname,
        given_names=result.given_names,
        cnp=cnp,
        date_of_birth=result.date_of_birth,
        date_of_expiry=result.date_of_expiry,
    )


def _try_td2(back_image: Image.Image) -> ExtractedIdentity | None:
    try:
        line1_img, line2_img = _band_lines(back_image, 2)
        result = parse_td2(read_mrz_line(line1_img, 36), read_mrz_line(line2_img, 36))
    except MrzFormatError:
        return None
    if not result.all_checks_valid:
        return None
    return ExtractedIdentity(
        detected_format="TD2",
        surname=result.surname,
        given_names=result.given_names,
        cnp=reconstruct_romanian_cnp_from_td2(result),
        date_of_birth=result.date_of_birth,
        date_of_expiry=result.date_of_expiry,
    )


def extract_identity_from_back_image(back_image: Image.Image) -> ExtractedIdentity | None:
    """Try TD1 (new card) then TD2 (old card); return the first one whose
    MRZ checksums check out, or None if neither does."""
    for attempt in (_try_td1, _try_td2):
        candidate = attempt(back_image)
        if candidate is not None:
            return candidate
    return None


__all__ = ["ExtractedIdentity", "decode_base64_image", "extract_identity_from_back_image"]
