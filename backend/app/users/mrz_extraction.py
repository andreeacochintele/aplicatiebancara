"""Ties mrz_reader (single-line OCR) and mrz (line parsing) together to go
from a whole "back of the ID card" photo to a parsed, checksum-validated
identity — trying both TD1 (new card) and TD2 (old card) since the caller
doesn't know in advance which one it's looking at. DB-agnostic and
image-only on purpose (no User/UserProfile here) — see users/service.py
for the cross-check against the profile the user filled in at step 2.

## Locating the MRZ band within an arbitrary uploaded photo

A first cut assumed the MRZ sits in a fixed bottom fraction of the photo
(per ICAO 9303's physical placement near the card's bottom edge). Tested
against a real photo, that broke: the card doesn't fill the frame flush to
its bottom pixel (there's a margin below the MRZ before the photo's own
edge), so a fixed-fraction crop either missed the top line entirely or
included blank/border rows - see git history on this file for the exact
failure.

`_detect_text_bands` below instead scans the photo bottom-up for
contiguous horizontal bands of moderate ink density (real text rows have
some-but-not-all of their width covered in dark pixels; blank rows have
~none, and a photo's crop edge/border tends to be ~all) and returns the
bottom-most `line_count` such bands. This works because the MRZ is, by
ICAO 9303 placement, the bottom-most text block on the card - nothing
legitimate should print below it. Still unverified: rotation/skew
correction (none attempted), and behavior when the uploaded photo has
real background (table, hand, etc.) below the card rather than a tight
crop - see mrz.py and mrz_reader.py module docstrings for the other two
documented unknowns (the old card's TD2 layout, and real-photo OCR
accuracy in general).
"""
import base64
import binascii
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.core.validation import cnp_checksum_is_valid
from app.users.mrz import MrzFormatError, Td1MrzResult, Td2MrzResult, parse_td1, parse_td2, reconstruct_romanian_cnp_from_td2
from app.users.mrz_reader import _otsu_threshold, read_mrz_line

# DEBUG here dumps the raw per-line OCR output and which checksum(s) failed
# for every failed attempt - the only way to tell a bad band-location guess
# (garbage/misaligned read) apart from a near-miss (photo quality). Off by
# default since it's per-upload-attempt verbose; see app.ai.observability
# for the same env-var-gated-logger pattern used elsewhere in this repo.
# Own StreamHandler + propagate=False, same as app.ai.observability - the
# root logger here has no handler of its own, so without this DEBUG (and
# even INFO) records silently hit logging.lastResort (WARNING) and vanish.
logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("IDENTITY_DOCUMENT_LOG_LEVEL", "INFO").upper())
logger.propagate = False
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s"))
    logger.addHandler(_handler)

_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB decoded — generous for a phone photo, cheap to reject earlier

# Row is "text" if its dark-pixel fraction (relative to this photo's own
# Otsu ink/background split - a fixed absolute threshold assumes a
# true-white background, which a real photo's lighting doesn't give you;
# see mrz_reader.py's _otsu_threshold) is above the min (rules out blank
# rows between/around lines) and below the max (rules out a near-solid dark
# row - a photo crop edge or border, confirmed against a real photo to read
# as ~1.0 where genuine MRZ text rows read ~0.2-0.4).
_ROW_INK_MIN_FRACTION = 0.05
_ROW_INK_MAX_FRACTION = 0.8
_MIN_BAND_HEIGHT_PX = 8  # rejects single-row noise blips from counting as a line
_LINE_CROP_PADDING_PX = 3  # a little headroom so ascenders/descenders at a band's edge aren't clipped

# TEMP debugging aid, not meant to survive the branch: with DEBUG logging on,
# dump exactly what _band_lines() cropped out of the uploaded photo to disk
# so it can actually be looked at, rather than guessing blind from garbage
# OCR output which region is at fault. Delete this whole block (and its call
# site below) once the band-location heuristic is confirmed working against
# a real card.
_DEBUG_DUMP_DIR = Path(__file__).resolve().parents[2] / ".identity_debug"


def _dump_debug_images(back_image: Image.Image) -> None:
    # PYTEST_CURRENT_TEST is set by pytest for the duration of each test - a
    # container running the suite with the debug env var still on must not
    # clobber a real capture sitting in the dump dir with synthetic fixture
    # images (this happened once; that's why this guard exists).
    if not logger.isEnabledFor(logging.DEBUG) or "PYTEST_CURRENT_TEST" in os.environ:
        return
    _DEBUG_DUMP_DIR.mkdir(exist_ok=True)
    back_image.convert("RGB").save(_DEBUG_DUMP_DIR / "back_original.png")
    for line_count, label in ((3, "td1"), (2, "td2")):
        lines = _band_lines(back_image, line_count)
        if lines is None:
            logger.debug("dump: could not locate %d text bands for %s", line_count, label)
            continue
        for index, line_img in enumerate(lines):
            line_img.convert("RGB").save(_DEBUG_DUMP_DIR / f"{label}_line{index + 1}.png")
    logger.debug("dumped debug images to %s", _DEBUG_DUMP_DIR)


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


def _detect_text_bands(gray: np.ndarray, *, line_count: int) -> list[tuple[int, int]] | None:
    """Scan `gray` bottom-up for `line_count` contiguous horizontal text
    bands, returned as (top, bottom) y-ranges in top-to-bottom (reading)
    order - or None if fewer than that many distinct bands are found."""
    height = gray.shape[0]
    dark_fraction = (gray < _otsu_threshold(gray)).mean(axis=1)
    is_text_row = (dark_fraction > _ROW_INK_MIN_FRACTION) & (dark_fraction < _ROW_INK_MAX_FRACTION)
    bands: list[tuple[int, int]] = []
    y = height - 1
    while y >= 0 and len(bands) < line_count:
        if is_text_row[y]:
            band_bottom = y + 1
            while y >= 0 and is_text_row[y]:
                y -= 1
            band_top = y + 1
            if band_bottom - band_top >= _MIN_BAND_HEIGHT_PX:
                bands.append((band_top, band_bottom))
        else:
            y -= 1
    if len(bands) < line_count:
        return None
    return list(reversed(bands))


def _band_lines(back_image: Image.Image, line_count: int) -> list[Image.Image] | None:
    width, height = back_image.size
    gray = np.asarray(back_image.convert("L"), dtype=np.float64)
    bands = _detect_text_bands(gray, line_count=line_count)
    if bands is None:
        return None
    lines = []
    for top, bottom in bands:
        padded_top = max(0, top - _LINE_CROP_PADDING_PX)
        padded_bottom = min(height, bottom + _LINE_CROP_PADDING_PX)
        lines.append(back_image.crop((0, padded_top, width, padded_bottom)))
    return lines


def _failed_checks(result: Td1MrzResult | Td2MrzResult) -> list[str]:
    return [
        name
        for name, valid in (
            ("document_number", result.document_number_check_valid),
            ("date_of_birth", result.date_of_birth is not None and result.date_of_birth_check_valid),
            ("date_of_expiry", result.date_of_expiry is not None and result.date_of_expiry_check_valid),
            ("composite", result.composite_check_valid),
        )
        if not valid
    ]


def _try_td1(back_image: Image.Image) -> ExtractedIdentity | None:
    line_images = _band_lines(back_image, 3)
    if line_images is None:
        logger.debug("TD1 attempt: could not locate 3 distinct text bands")
        return None
    try:
        lines = [read_mrz_line(img, 30) for img in line_images]
        result = parse_td1(*lines)
    except MrzFormatError as exc:
        logger.debug("TD1 attempt: malformed MRZ lines (%s)", exc)
        return None
    if not result.all_checks_valid:
        logger.debug("TD1 attempt: read lines %s, failed checks %s", lines, _failed_checks(result))
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
    line_images = _band_lines(back_image, 2)
    if line_images is None:
        logger.debug("TD2 attempt: could not locate 2 distinct text bands")
        return None
    try:
        lines = [read_mrz_line(img, 36) for img in line_images]
        result = parse_td2(*lines)
    except MrzFormatError as exc:
        logger.debug("TD2 attempt: malformed MRZ lines (%s)", exc)
        return None
    if not result.all_checks_valid:
        logger.debug("TD2 attempt: read lines %s, failed checks %s", lines, _failed_checks(result))
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
    _dump_debug_images(back_image)
    for attempt in (_try_td1, _try_td2):
        candidate = attempt(back_image)
        if candidate is not None:
            return candidate
    return None


__all__ = ["ExtractedIdentity", "decode_base64_image", "extract_identity_from_back_image"]
