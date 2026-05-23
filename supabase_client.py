"""
supabase_client.py — Initializer helper for the Supabase API Client.
"""
import os
from flask import current_app
from supabase import create_client, Client


def get_supabase_client() -> Client:
    """Initialize and return the Supabase client.

    Attempts to retrieve credentials from Flask's current_app context first,
    falling back to os.environ for standalone scripts/background tasks.
    """
    supabase_url = None
    supabase_key = None

    # Try Flask application context config first
    try:
        if current_app:
            supabase_url = current_app.config.get("SUPABASE_URL")
            supabase_key = current_app.config.get("SUPABASE_KEY")
    except RuntimeError:
        # Working outside application context
        pass

    # Fallback to environment variables
    if not supabase_url:
        supabase_url = os.environ.get("SUPABASE_URL")
    if not supabase_key:
        supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY must be configured "
            "in app.config or environment variables."
        )

    return create_client(supabase_url, supabase_key)
