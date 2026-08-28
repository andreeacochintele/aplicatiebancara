"""Validates the whole image -> ExtractedIdentity pipeline (band
localization + dual-format detection + line reading + parsing) against
synthetic "back of card" photos built with the real OCR-B font. Proves the
mechanics; says nothing about real-photo robustness — see
mrz_extraction.py's module docstring."""
import base64
from datetime import date
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.users.mrz import compute_check_digit
from app.users.mrz_extraction import decode_base64_image, extract_identity_from_back_image
from app.users.mrz_reader import _FONT_PATH

_CARD_SIZE = (1010, 638)  # roughly ID-1 proportions at ~300dpi
# Where these synthetic fixtures place their MRZ text - arbitrary (adaptive
# band detection doesn't care where the text sits), just needs some blank
# margin above and below so the detector sees clear gaps.
_TEXT_BAND_START_FRACTION = 0.28


def _checked(data: str) -> str:
    return f"{data}{compute_check_digit(data)}"


def _fitting_font_size(cell_width: float, cell_height: float) -> int:
    """The largest point size whose widest MRZ character still fits inside
    a `cell_width`-wide slot - TD2 packs 36 chars into the same image width
    TD1 uses for 30, so its per-character budget is narrower even though
    each line is individually taller (only 2 lines to split the band
    into). Sizing purely off line height, as a first cut did, rendered
    characters wide enough to bleed into their neighbors and corrupt the
    whole line - a test-fixture bug, not a bug in the reader being tested."""
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


def _blank_card() -> Image.Image:
    return Image.new("L", _CARD_SIZE, color=255)


def _band_top(card_height: int) -> int:
    return round(card_height * (1 - _TEXT_BAND_START_FRACTION))


def _build_td1_card() -> Image.Image:
    card = _blank_card()
    band_top = _band_top(card.height)
    line_height = (card.height - band_top) / 3
    line1 = "I<" + "ROU" + _checked("RT1234567") + "<" * 15
    line2_prefix = _checked("900101") + "F" + _checked("300101") + "ROU" + "<" * 11
    composite_input = line1[5:30] + line2_prefix[0:7] + line2_prefix[8:15] + line2_prefix[18:29]
    line2 = line2_prefix + str(compute_check_digit(composite_input))
    line3 = "IONESCU<<MARIA<ELENA" + "<" * 10
    for i, line in enumerate((line1, line2, line3)):
        _render_line_onto(card, line, top=round(band_top + i * line_height), height=round(line_height))
    return card


def _build_td2_card() -> Image.Image:
    card = _blank_card()
    band_top = _band_top(card.height)
    line_height = (card.height - band_top) / 2
    name_field = "IONESCU<<MARIA<ELENA"
    line1 = "I<" + "ROU" + name_field + "<" * (36 - 5 - len(name_field))
    # optional data "1123457": S=1 + county/seq/check "123457" -> reconstructed CNP 1900101123457.
    line2_prefix = _checked("RT1234567") + "ROU" + _checked("900101") + "F" + _checked("300101") + "1123457"
    composite_input = line2_prefix[0:10] + line2_prefix[13:20] + line2_prefix[21:35]
    line2 = line2_prefix + str(compute_check_digit(composite_input))
    for i, line in enumerate((line1, line2)):
        _render_line_onto(card, line, top=round(band_top + i * line_height), height=round(line_height))
    return card


def test_extracts_identity_from_a_synthetic_td1_card():
    card = _build_td1_card()

    result = extract_identity_from_back_image(card)

    assert result is not None
    assert result.detected_format == "TD1"
    assert result.surname == "IONESCU"
    assert result.given_names == "MARIA ELENA"
    assert result.date_of_birth == date(1990, 1, 1)
    assert result.date_of_expiry == date(2030, 1, 1)


def test_extracts_identity_from_a_synthetic_td2_card():
    card = _build_td2_card()

    result = extract_identity_from_back_image(card)

    assert result is not None
    assert result.detected_format == "TD2"
    assert result.surname == "IONESCU"
    assert result.cnp == "1900101123457"
    assert result.date_of_birth == date(1990, 1, 1)


def test_returns_none_for_a_blank_card():
    assert extract_identity_from_back_image(_blank_card()) is None


class TestDecodeBase64Image:
    def _as_base64(self, image: Image.Image) -> str:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def test_round_trips_a_real_image(self):
        original = Image.new("RGB", (10, 10), color=(255, 0, 0))
        decoded = decode_base64_image(self._as_base64(original))

        assert decoded is not None
        assert decoded.size == (10, 10)

    def test_accepts_a_data_url_prefix(self):
        original = Image.new("RGB", (5, 5), color=(0, 255, 0))
        data_url = f"data:image/png;base64,{self._as_base64(original)}"

        assert decode_base64_image(data_url) is not None

    def test_returns_none_for_invalid_base64(self):
        assert decode_base64_image("not-valid-base64!!!") is None

    def test_returns_none_for_base64_that_isnt_an_image(self):
        garbage = base64.b64encode(b"just some plain bytes, not an image").decode("ascii")
        assert decode_base64_image(garbage) is None
