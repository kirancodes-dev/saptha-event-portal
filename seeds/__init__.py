"""seeds — the data sets behind `python seed.py --profile …` (UPG-15).

Each module calls seed_safety.guard() before anything else, so it refuses a
production-looking database even when imported on its own.
"""
