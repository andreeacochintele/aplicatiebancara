"""Deterministic, from-scratch character recognition for a single
already-cropped MRZ line image, via template matching against the OCR-B
font (`assets/ocrb/OCRB.ttf` — see that folder's NOTICE.md for license).

No Tesseract, no EasyOCR, no ML/AI model of any kind — per the project's
AI-provider constraint (CLAUDE.md) and the plan's explicit decision that
this feature stays 100% deterministic. The MRZ character set is small and
fixed (A-Z, 0-9, '<') and the font is fixed (OCR-B, mandated by ICAO 9303),
which is what makes plain template matching a workable approach without a
trained OCR engine.

## Scope

This reads ONE line image that the caller has already cropped reasonably
tightly around just the text row — correct height, not rotated. Locating
the MRZ band within an arbitrary photo of the back of an ID card (and
correcting for skew/perspective/lighting) is a separate, harder problem
this module does not attempt; that lives in the upload/extraction flow
that will call this function once it exists.

## Accuracy is UNVERIFIED against a real photo

`test_mrz_reader.py` validates the segmentation+matching pipeline against a
line synthetically rendered with the same font, which proves the mechanics
work — it says nothing about real-world robustness to camera angle,
lighting, focus, or JPEG compression artifacts. Treat this as a first pass
to be tuned once a real test photo is available, not a finished OCR engine.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Every character that can legally appear in an MRZ: digits, A-Z, and the
# '<' filler.
_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ<"
_FONT_PATH = Path(__file__).parent / "assets" / "ocrb" / "OCRB.ttf"
_GLYPH_POINT_SIZE = 64
# All glyphs (reference and cropped-cell alike) are normalized to this pixel
# box before comparison, so the input image's actual resolution doesn't
# need to match the reference rendering's.
_CELL_SIZE = (32, 48)

_reference_glyphs_cache: dict[str, np.ndarray] | None = None
# Generous scratch canvas for rendering one character before normalizing -
# large enough that no glyph at _GLYPH_POINT_SIZE can clip against an edge.
_SCRATCH_SIZE = (_GLYPH_POINT_SIZE * 2, _GLYPH_POINT_SIZE * 2)


def _otsu_threshold(gray: np.ndarray) -> float:
    """Otsu's method: the gray-level that best splits `gray` into two
    classes (ink/background) by maximizing between-class variance. A fixed
    threshold (this module's original approach) was tuned against
    synthetic test renders with a true-white (255) background; a real
    photo's "white" card background is whatever the camera/lighting made
    it - confirmed against a real photo to sit anywhere from ~110 to ~190,
    which a fixed threshold of 200 misreads as ink across the entire
    image. Falls back to 128.0 if `gray` has no pixels (shouldn't happen
    for a real crop)."""
    histogram, _ = np.histogram(gray, bins=256, range=(0, 256))
    histogram = histogram.astype(np.float64)
    total = histogram.sum()
    if total == 0:
        return 128.0
    levels = np.arange(256)
    sum_all = float(np.dot(levels, histogram))
    weight_bg = np.cumsum(histogram)
    sum_bg = np.cumsum(levels * histogram)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_bg = np.where(weight_bg > 0, sum_bg / weight_bg, 0.0)
        weight_fg = total - weight_bg
        mean_fg = np.where(weight_fg > 0, (sum_all - sum_bg) / weight_fg, 0.0)
        between_class_variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
    return float(np.argmax(between_class_variance))


def _crop_to_ink_bbox(gray: np.ndarray, *, threshold: float, min_ink_pixels: int = 2) -> np.ndarray | None:
    """The tightest bounding-box crop containing pixels darker than
    `threshold`, or None if there's no ink at all (a blank cell, e.g. '<').

    A row/column only counts if it has at least `min_ink_pixels` dark
    pixels, not just one - confirmed against a real photo that a single
    stray dark pixel (anti-aliasing/blur bleeding in from a neighboring
    character at the cell boundary) can otherwise blow the bbox out far
    past the actual glyph, which then gets compressed and mis-centered
    when rescaled to fill it. A genuine glyph stroke is never one pixel
    wide in a single row/column, so this costs no real coverage."""
    mask = gray < threshold
    if not mask.any():
        return None
    row_indices = np.where(mask.sum(axis=1) >= min_ink_pixels)[0]
    col_indices = np.where(mask.sum(axis=0) >= min_ink_pixels)[0]
    if row_indices.size == 0 or col_indices.size == 0:
        return None
    top, bottom = row_indices[0], row_indices[-1]
    left, right = col_indices[0], col_indices[-1]
    return gray[top : bottom + 1, left : right + 1]


def _normalize_for_matching(gray: np.ndarray) -> np.ndarray:
    """Crops to the ink's own bounding box and centers it on a blank
    `_CELL_SIZE` canvas, preserving aspect ratio. Makes matching invariant
    to the glyph's exact position/scale within whatever box it arrived in -
    without this, comparing raw fixed-position renders is extremely
    sensitive to sub-pixel alignment differences between the reference
    render and a real (or even just differently-rendered) source image.

    The ink/background split uses this array's own Otsu threshold rather
    than a fixed value - computed fresh per call so it adapts to each
    glyph cell's own local brightness (a real photo's lighting isn't
    uniform line-to-line, let alone cell-to-cell) as well as to the
    synthetic reference renders' true-white background."""
    target_w, target_h = _CELL_SIZE
    canvas = np.full((target_h, target_w), 255.0)
    ink = _crop_to_ink_bbox(gray, threshold=_otsu_threshold(gray))
    if ink is None:
        return canvas
    ink_h, ink_w = ink.shape
    max_w, max_h = target_w - 4, target_h - 4
    # No upper cap at 1.0 here (deliberately) - ink must be scaled to fill
    # the target box regardless of the source render's size, or comparisons
    # across differently-sized source images would never line up.
    scale = min(max_w / ink_w, max_h / ink_h)
    new_w, new_h = max(1, round(ink_w * scale)), max(1, round(ink_h * scale))
    resized = np.asarray(Image.fromarray(ink.astype(np.uint8)).resize((new_w, new_h)), dtype=np.float64)
    top, left = (target_h - new_h) // 2, (target_w - new_w) // 2
    canvas[top : top + new_h, left : left + new_w] = resized
    return canvas


def _render_reference_glyphs() -> dict[str, np.ndarray]:
    font = ImageFont.truetype(str(_FONT_PATH), _GLYPH_POINT_SIZE)
    glyphs: dict[str, np.ndarray] = {}
    for ch in _ALPHABET:
        image = Image.new("L", _SCRATCH_SIZE, color=255)
        draw = ImageDraw.Draw(image)
        # OCR-B does have a real glyph for '<' (confirmed against a real
        # card photo: the filler prints as a visible chevron, not blank
        # space - the original assumption here was wrong), so it's
        # rendered like every other character.
        draw.text((_SCRATCH_SIZE[0] // 4, _SCRATCH_SIZE[1] // 4), ch, font=font, fill=0)
        glyphs[ch] = _normalize_for_matching(np.asarray(image, dtype=np.float64))
    return glyphs


def _reference_glyphs() -> dict[str, np.ndarray]:
    global _reference_glyphs_cache
    if _reference_glyphs_cache is None:
        _reference_glyphs_cache = _render_reference_glyphs()
    return _reference_glyphs_cache


def _normalized_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Zero-mean normalized cross-correlation - invariant to brightness/
    contrast offsets between the reference render and a real photo crop,
    which raw pixel distance would not be."""
    a_centered, b_centered = a - a.mean(), b - b.mean()
    denominator = np.linalg.norm(a_centered) * np.linalg.norm(b_centered)
    if denominator < 1e-9:
        # Both effectively blank (e.g. comparing a blank cell to '<') - a
        # perfect match in that case, not "no signal."
        return 1.0 if np.linalg.norm(a_centered) < 1e-9 and np.linalg.norm(b_centered) < 1e-9 else 0.0
    return float(np.dot(a_centered.flatten(), b_centered.flatten()) / denominator)


def _best_match(cell_array: np.ndarray) -> tuple[str, float]:
    best_char, best_score = "<", -1.0
    for ch, glyph in _reference_glyphs().items():
        score = _normalized_correlation(cell_array, glyph)
        if score > best_score:
            best_char, best_score = ch, score
    return best_char, best_score


def _horizontal_ink_bounds(gray: np.ndarray, *, threshold: float) -> tuple[int, int] | None:
    """Leftmost/rightmost (exclusive) columns containing ink, or None if the
    line has none at all."""
    mask = gray < threshold
    if not mask.any():
        return None
    col_indices = np.where(mask.any(axis=0))[0]
    return int(col_indices[0]), int(col_indices[-1]) + 1


_BOUNDARY_SEARCH_FRACTION = 0.2
_BOUNDARY_SMOOTHING_WINDOW = 3  # columns, odd so the moving average stays centered


def _snapped_cell_boundaries(col_dark_fraction: np.ndarray, *, left_bound: int, right_bound: int, character_count: int) -> list[int]:
    """`character_count + 1` boundary columns, starting from the naive
    equal-width division but each interior one nudged to the locally
    lowest-ink column within a search window around it - confirmed against
    a real photo that pure equal-width division drifts enough (slight
    perspective/lens distortion across the line, real character pitch not
    perfectly uniform pixel-for-pixel) to bleed each cell into its
    neighbor's ink. A real gap between two printed characters is always a
    true local minimum in ink density, so this stays anchored to the
    overall structure while correcting for that drift.

    Searches a light moving-average of the density profile, not the raw
    per-column values - confirmed against a real photo that a single noisy
    column (anti-aliasing speckle) can otherwise look like a deeper "gap"
    than the true one a character-width away, snapping the boundary to the
    wrong valley entirely."""
    kernel = np.ones(_BOUNDARY_SMOOTHING_WINDOW) / _BOUNDARY_SMOOTHING_WINDOW
    smoothed = np.convolve(col_dark_fraction, kernel, mode="same")
    cell_width = (right_bound - left_bound) / character_count
    search_radius = max(1, round(cell_width * _BOUNDARY_SEARCH_FRACTION))
    boundaries = [left_bound]
    for index in range(1, character_count):
        raw = left_bound + round(index * cell_width)
        window_start, window_end = max(left_bound, raw - search_radius), min(right_bound, raw + search_radius)
        window = smoothed[window_start:window_end]
        boundaries.append(window_start + int(np.argmin(window)) if window.size else raw)
    boundaries.append(right_bound)
    return boundaries


def read_mrz_line(line_image: Image.Image, character_count: int) -> str:
    """Segment `line_image` into `character_count` cells - the MRZ font is
    monospaced, so equal-width slicing is the standard starting point - and
    return the best-matching character for each cell.

    Slices within the line's own horizontal ink extent, not its full pixel
    width: a real photo's line crop carries whatever margin sits between
    the card's edge and the photo's edge (confirmed against a real photo -
    dividing the full width put every single cell out of alignment with
    its actual character). Every MRZ line read here starts and ends with a
    real (non-'<') character by construction (a document/date/check-digit
    field never opens or closes a line), so the ink extent's own bounds are
    a reliable anchor regardless of how much filler sits in between."""
    grayscale = line_image.convert("L")
    height = grayscale.size[1]
    array = np.asarray(grayscale, dtype=np.float64)
    ink_threshold = _otsu_threshold(array)
    bounds = _horizontal_ink_bounds(array, threshold=ink_threshold)
    if bounds is None:
        return "<" * character_count
    left_bound, right_bound = bounds
    col_dark_fraction = (array < ink_threshold).mean(axis=0)
    boundaries = _snapped_cell_boundaries(col_dark_fraction, left_bound=left_bound, right_bound=right_bound, character_count=character_count)
    characters = []
    for index in range(character_count):
        left, right = boundaries[index], boundaries[index + 1]
        cell = grayscale.crop((left, 0, max(right, left + 1), height))
        normalized = _normalize_for_matching(np.asarray(cell, dtype=np.float64))
        best_char, _score = _best_match(normalized)
        characters.append(best_char)
    return "".join(characters)


__all__ = ["read_mrz_line"]
