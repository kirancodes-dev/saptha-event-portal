# Certificate fonts

Noto Sans, Noto Sans Kannada and Noto Sans Devanagari (regular and bold, static
TrueType), from https://github.com/notofonts/notofonts.github.io (`fonts/*/hinted/ttf`),
fetched 2026-10-19. SIL Open Font License 1.1 (`OFL.txt`).

`certificate_pdf.py` draws certificates with them: Latin text in Noto Sans,
Kannada and Devanagari runs in their own font, shaped with HarfBuzz
(`uharfbuzz`) so conjuncts and vowel signs join correctly (UPG-123).
