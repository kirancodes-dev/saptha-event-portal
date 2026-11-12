"""
tests/test_licence.py — UPG-249.

The README said "MIT License" but the repository had no LICENSE file, so GitHub
showed no licence and the project wasn't open source in law. The LICENSE file
holds the full MIT text with the README's copyright line.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_repository_has_the_mit_licence_the_readme_names():
    licence = (ROOT / 'LICENSE').read_text()
    assert licence.startswith('MIT License')
    assert 'Copyright (c) 2026 Sapthagiri NPS University' in licence
    assert 'Permission is hereby granted, free of charge' in licence
    assert 'WITHOUT WARRANTY OF ANY KIND' in licence             # the whole text, disclaimer included
    readme = (ROOT / 'README.md').read_text()
    assert 'Copyright (c) 2026 Sapthagiri NPS University' in readme and '(LICENSE)' in readme
