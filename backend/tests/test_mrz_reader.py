"""Validates the template-matching segmentation+comparison mechanics against
a synthetically rendered MRZ line (same font used to build the reference
glyphs AND the "scanned" line, deliberately, so this proves the pipeline
logic is correct). It does NOT validate real-world accuracy against an
actual photo - see mrz_reader.py's module docstring."""
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.users.mrz_reader import _FONT_PATH, read_mrz_line

pytestmark = pytest.mark.skipif(not Path(_FONT_PATH).exists(), reason="OCR-B font asset missing")


def _render_line(text: str, *, point_size: int = 40, margin: int = 6) -> Image.Image:
    """Render `text` monospaced with the real OCR-B font, at a size/margin
    different from mrz_reader's own reference rendering, so the test isn't
    trivially comparing identical images."""
    font = ImageFont.truetype(str(_FONT_PATH), point_size)
    char_width = max(font.getbbox(ch)[2] for ch in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ") + margin
    width, height = char_width * len(text), point_size + 2 * margin
    image = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(image)
    for index, ch in enumerate(text):
        draw.text((index * char_width + margin // 2, margin), ch, font=font, fill=0)
    return image


@pytest.mark.parametrize(
    "text",
    [
        "I<ROURT12345674<<<<<<<<<<<<<<<",
        "9001011F3001019ROU<<<<<<<<<<<0",
        "IONESCU<<MARIA<ELENA<<<<<<<<<<",
        "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
    ],
)
def test_read_mrz_line_recovers_synthetic_text(text):
    image = _render_line(text)

    result = read_mrz_line(image, character_count=len(text))

    assert result == text


def test_read_mrz_line_is_robust_to_render_size_difference():
    text = "L898902C36UTO7408122F1204159<<<<"
    image = _render_line(text, point_size=64, margin=10)

    result = read_mrz_line(image, character_count=len(text))

    assert result == text
