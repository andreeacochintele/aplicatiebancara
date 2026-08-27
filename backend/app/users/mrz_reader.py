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


def _crop_to_ink_bbox(gray: np.ndarray, *, threshold: float = 200.0) -> np.ndarray | None:
    """The tightest bounding-box crop containing pixels darker than
    `threshold`, or None if there's no ink at all (a blank cell, e.g. '<')."""
    mask = gray < threshold
    if not mask.any():
        return None
    row_indices = np.where(mask.any(axis=1))[0]
    col_indices = np.where(mask.any(axis=0))[0]
    top, bottom = row_indices[0], row_indices[-1]
    left, right = col_indices[0], col_indices[-1]
    return gray[top : bottom + 1, left : right + 1]


def _normalize_for_matching(gray: np.ndarray) -> np.ndarray:
    """Crops to the ink's own bounding box and centers it on a blank
    `_CELL_SIZE` canvas, preserving aspect ratio. Makes matching invariant
    to the glyph's exact position/scale within whatever box it arrived in -
    without this, comparing raw fixed-position renders is extremely
    sensitive to sub-pixel alignment differences between the reference
    render and a real (or even just differently-rendered) source image."""
    target_w, target_h = _CELL_SIZE
    canvas = np.full((target_h, target_w), 255.0)
    ink = _crop_to_ink_bbox(gray)
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
        # OCR-B has no glyph for '<' (it's an MRZ filler convention, not a
        # printable character on the document) — an empty/blank cell is the
        # correct reference to match against.
        if ch != "<":
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


def read_mrz_line(line_image: Image.Image, character_count: int) -> str:
    """Segment `line_image` into `character_count` equal-width cells - the
    MRZ font is monospaced, so simple equal-width slicing is the standard
    approach - and return the best-matching character for each cell."""
    grayscale = line_image.convert("L")
    width, height = grayscale.size
    cell_width = width / character_count
    characters = []
    for index in range(character_count):
        left = round(index * cell_width)
        right = round((index + 1) * cell_width)
        cell = grayscale.crop((left, 0, max(right, left + 1), height))
        normalized = _normalize_for_matching(np.asarray(cell, dtype=np.float64))
        best_char, _score = _best_match(normalized)
        characters.append(best_char)
    return "".join(characters)


__all__ = ["read_mrz_line"]
