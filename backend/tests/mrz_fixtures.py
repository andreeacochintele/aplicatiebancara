"""Shared helper for building a synthetic "back of ID card" MRZ photo
(TD1/new-card layout) in tests, rendered with the real OCR-B font. See
app/users/mrz_extraction.py's module docstring for why a real font render
is needed at all instead of a plain string fixture."""
import base64
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.users.mrz import compute_check_digit
from app.users.mrz_reader import _FONT_PATH

CARD_SIZE = (1010, 638)  # roughly ID-1 proportions at ~300dpi
# Where this fixture places its MRZ text - arbitrary (adaptive band
# detection doesn't care where the text sits), just needs blank margin
# above and below so the detector sees clear gaps.
_TEXT_BAND_START_FRACTION = 0.28


def _checked(data: str) -> str:
    return f"{data}{compute_check_digit(data)}"


def _fitting_font_size(cell_width: float, cell_height: float) -> int:
    point_size = max(6, round(cell_height * 0.75))
    while point_size > 6:
        font = ImageFont.truetype(str(_FONT_PATH), point_size)
        max_char_width = max(font.getbbox(ch)[2] for ch in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        if max_char_width <= cell_width * 0.85:
            return point_size
        point_size -= 1
    return point_size


def _render_line_onto(canvas: Image.Image, text: str, *, top: int, height: int) -> None:
    draw = ImageDraw.Draw(canvas)
    char_width = canvas.width / len(text)
    font = ImageFont.truetype(str(_FONT_PATH), _fitting_font_size(char_width, height))
    for index, ch in enumerate(text):
        draw.text((round(index * char_width), top), ch, font=font, fill=0)


def build_td1_card_base64(
    *,
    surname: str = "IONESCU",
    given_names: str = "ANA",
    document_number: str = "RT1234567",
    dob: str = "900101",
    sex: str = "F",
    expiry: str = "300101",
    nationality: str = "ROU",
    cnp: str | None = "1900101123457",
) -> str:
    card = Image.new("L", CARD_SIZE, color=255)
    band_top = round(card.height * (1 - _TEXT_BAND_START_FRACTION))
    line_height = (card.height - band_top) / 3

    optional_data_1 = (cnp or "").ljust(15, "<")[:15]
    line1 = "I<" + "ROU" + _checked(document_number) + optional_data_1
    line2_prefix = _checked(dob) + sex + _checked(expiry) + nationality + "<" * 11
    composite_input = line1[5:30] + line2_prefix[0:7] + line2_prefix[8:15] + line2_prefix[18:29]
    line2 = line2_prefix + str(compute_check_digit(composite_input))
    name_field = f"{surname}<<{given_names}"
    line3 = name_field + "<" * (30 - len(name_field))

    for i, line in enumerate((line1, line2, line3)):
        _render_line_onto(card, line, top=round(band_top + i * line_height), height=round(line_height))

    buffer = BytesIO()
    card.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
