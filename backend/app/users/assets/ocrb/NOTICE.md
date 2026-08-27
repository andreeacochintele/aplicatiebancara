# OCR-B font — provenance and license

`OCRB.ttf` is used by `backend/app/users/mrz_reader.py` to render reference
glyphs for template-matching characters read off an identity document's
Machine Readable Zone (MRZ). It is not shipped to the frontend or used to
render any text shown to users — it's a backend-only OCR reference asset.

## Source

Downloaded from the **Tsukurimashou Project** (Matthew Skala),
package `ocr-0.3.1.zip`: <https://tsukurimashou.org/ocr.php.en>

Documentation: <https://tsukurimashou.org/ocr.pdf>

## License

Per the package's own documentation (`ocr.pdf`, section 3, "OCR B"):

> The version in this package descends from a set of Metafont definitions
> by Norbert Schwarz of Ruhr-Universitaet Bochum, bearing dates ranging
> from 1986 to 2010. He originally distributed it under a "non-commercial
> use only" restriction but has since released it for unrestricted use and
> distribution. [...] I [Matthew Skala] make no copyright claim on these
> fonts myself. I do not believe anyone else makes a copyright claim that
> would conflict with the use of these fonts in a commercial project.

In short: free for unrestricted use, including commercial, per the
copyright holder's own release statement. No attribution requirement is
stated, but this file exists so the provenance is traceable for the team.

The package also includes `.otf` and `.pfb`/`.afm` versions and several
non-standard styles (italic, light, expanded, etc.) — only the plain
`OCRB.ttf` is used here.
