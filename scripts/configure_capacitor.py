#!/usr/bin/env python3
"""Configure capacitor.config.json from BASE_URL environment variable.

Usage:
    BASE_URL="https://events.example.edu" python scripts/configure_capacitor.py
    python scripts/configure_capacitor.py https://events.example.edu
"""

import json
import os
import sys
from urllib.parse import urlparse


def configure_capacitor(base_url: str = None, output_path: str = "capacitor.config.json") -> dict:
    if not base_url:
        base_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BASE_URL", "")

    base_url = (base_url or "").strip()
    if not base_url:
        base_url = "https://events.example.edu"

    if not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"

    parsed = urlparse(base_url)
    host = parsed.netloc or parsed.path
    if ":" in host:
        host = host.split(":")[0]

    # Reconstruct normalized URL
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or host
    normalized_url = f"{scheme}://{netloc}"

    config = {
        "appId": "com.sapthaevent.app",
        "appName": "SapthaEvent",
        "webDir": "static",
        "server": {
            "url": normalized_url,
            "allowNavigation": [
                host
            ]
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"Configured {output_path} with url: {normalized_url}, host: {host}")
    return config


if __name__ == "__main__":
    configure_capacitor()
