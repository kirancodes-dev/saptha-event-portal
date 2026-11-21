"""
services_releases.py — the portal's versions and what changed in each (UPG-373).

The list lives in config/releases.json, newest first; the top entry is the
version of this code. A new entry starts after each deploy, and every finished
item goes into the top entry until then (tests/test_releases.py checks that the
changelog's finished items are all listed).
"""
import json
import os
from functools import lru_cache

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'releases.json')


@lru_cache(maxsize=1)
def releases() -> list:
    """Every version, newest first; [] if the file can't be read."""
    try:
        with open(PATH, encoding='utf-8') as f:
            return list(json.load(f).get('releases') or [])
    except (OSError, ValueError):
        return []


def current() -> dict:
    """The version of this code: {'version', 'date', 'title', ...}, or {}."""
    found = releases()
    return found[0] if found else {}


def version() -> str:
    """'v1.16', or '' when the list can't be read."""
    v = current().get('version')
    return f"v{v}" if v else ''
