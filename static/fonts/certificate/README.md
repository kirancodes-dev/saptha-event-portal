# Certificate fonts

Noto Sans, Noto Sans Kannada and Noto Sans Devanagari (regular and bold, static
TrueType), from https://github.com/notofonts/notofonts.github.io (`fonts/*/hinted/ttf`),
fetched 2026-10-19. SIL Open Font License 1.1 (`OFL.txt`).

`certificate_pdf.py` draws certificates with them: Latin text in Noto Sans,
Kannada and Devanagari runs in their own font, shaped with HarfBuzz
(`uharfbuzz`) so conjuncts and vowel signs join correctly (UPG-123).

## Fonts a box of the organiser's own design can use (UPG-330)

From Google Fonts (https://github.com/google/fonts, `ofl/*`), fetched 2026-11-20,
each under the SIL Open Font License 1.1 (its own copy in `licenses/`):

| Key | Files | Note |
|---|---|---|
| poppins | Poppins-Regular/Bold.ttf | static files as published |
| montserrat | Montserrat-Regular/Bold.ttf | static instances (wght 400/700) of the variable font |
| playfair | PlayfairDisplay-Regular/Bold.ttf | static instances of the variable font |
| cinzel | Cinzel-Regular/Bold.ttf | static instances of the variable font |
| tinos | Tinos-Regular/Bold.ttf | metric-compatible with Times New Roman |
| greatvibes | GreatVibes-Regular.ttf | script; no bold |
| dancing | DancingScript-Regular/Bold.ttf | static instances of the variable font |

The variable fonts were made static with
`fonttools varLib.instancer <font> wght=400 --static --update-name-table`
(and `wght=700`); `--update-name-table` gives each file its own PostScript
name, which ReportLab needs to tell regular from bold. `FACES` in
`certificate_pdf.py` lists them. An organiser can also upload their own
TrueType font for their event; that file is stored privately, not here.
