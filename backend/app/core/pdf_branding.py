"""Shared branded-PDF header/footer for every generated PDF (statements,
business exports, ...) so they all look like they came from the same bank
instead of each module rolling its own letterhead."""
import os
import unicodedata
from datetime import datetime, timezone

from fpdf import FPDF

# fpdf's core "Helvetica" font only supports Latin-1 (WinAnsi) glyphs — any
# other character raises FPDFUnicodeEncodingException and 500s the whole
# export. Every string here can come from user input (a transaction
# description, a business name, ...), so anything reaching pdf.cell() must
# go through this first rather than trusting the caller to only ever type
# plain ASCII. Romanian diacritics (ă â î ș ț) are the case that matters
# most for this app; "smart" Unicode punctuation is the other common source
# (curly quotes, em/en dashes, ellipsis) since those get auto-substituted by
# a lot of phone keyboards and browsers.
_PDF_PUNCTUATION_MAP = {
    "—": "-",  # em dash —
    "–": "-",  # en dash –
    "‘": "'",  # left single quote '
    "’": "'",  # right single quote '
    "“": '"',  # left double quote "
    "”": '"',  # right double quote "
    "…": "...",  # ellipsis …
}


def pdf_safe_text(value: str | None) -> str:
    """Best-effort transliteration to Latin-1: decomposes accented letters
    (ă -> a, ș -> s, ...) and swaps common smart-punctuation for ASCII
    equivalents, then drops anything that still can't be represented rather
    than crashing. A cosmetic downgrade (accents lost) is an acceptable
    trade for "the export always succeeds"."""
    if not value:
        return ""
    for char, replacement in _PDF_PUNCTUATION_MAP.items():
        value = value.replace(char, replacement)
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("latin-1", "ignore").decode("latin-1")

# Brand palette (see frontend/src/styles/easyb.css --easyb-gradient):
# violet -> purple -> pink. FPDF has no gradient fill primitive, so the
# header band approximates it with a strip of interpolated solid-color rects.
GRADIENT_STOPS = [(91, 95, 239), (155, 93, 229), (255, 111, 165)]
TEXT_DARK = (21, 21, 31)
TEXT_SOFT = (108, 108, 130)
BORDER = (235, 235, 243)
ROW_ALT = (251, 251, 254)
GREEN = (28, 160, 99)
RED = (216, 81, 79)
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "easyb_logo.png")


def gradient_color(t: float) -> tuple[int, int, int]:
    segment = min(int(t * (len(GRADIENT_STOPS) - 1)), len(GRADIENT_STOPS) - 2)
    local_t = t * (len(GRADIENT_STOPS) - 1) - segment
    a, b = GRADIENT_STOPS[segment], GRADIENT_STOPS[segment + 1]
    return tuple(round(a[i] + (b[i] - a[i]) * local_t) for i in range(3))


class BrandedPDF(FPDF):
    """Set `.subtitle` and `.footer_note` before the first add_page() call —
    header()/footer() read them each time FPDF invokes these callbacks."""

    subtitle = ""
    footer_note = "sandbox export, not a legal document"
    BAND_HEIGHT = 16

    def header(self) -> None:
        steps = 60
        step_width = self.w / steps
        for i in range(steps):
            self.set_fill_color(*gradient_color(i / (steps - 1)))
            self.rect(i * step_width, 0, step_width + 0.5, self.BAND_HEIGHT, style="F")
        if os.path.exists(LOGO_PATH):
            self.image(LOGO_PATH, x=10, y=3, h=10)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 15)
        self.set_xy(22, 3)
        self.cell(0, 10, "EasyB", align="L")
        if self.subtitle:
            self.set_text_color(*TEXT_DARK)
            self.set_font("Helvetica", "", 10)
            self.set_xy(0, self.BAND_HEIGHT + 3)
            self.cell(self.w - 10, 6, self.subtitle, align="R")
        self.set_y(self.BAND_HEIGHT + 12)
        self.set_text_color(*TEXT_DARK)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_draw_color(*BORDER)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*TEXT_SOFT)
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.set_xy(10, -12)
        self.cell(self.w / 2 - 10, 8, f"Generated {generated} - {self.footer_note}")
        self.set_xy(self.w / 2, -12)
        self.cell(self.w / 2 - 10, 8, f"Page {self.page_no()}/{{nb}}", align="R")


def new_branded_pdf(subtitle: str, orientation: str = "P") -> BrandedPDF:
    pdf = BrandedPDF(orientation=orientation)
    pdf.subtitle = subtitle
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    return pdf
