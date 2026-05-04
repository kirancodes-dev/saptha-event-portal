"""
Shared Flask extensions — imported by both app.py and route modules.
Creating extensions here (without app) lets blueprints use @limiter.limit()
decorators without circular imports.
"""
from flask_limiter import Limiter
import flask_limiter.util

limiter = Limiter(
    key_func=flask_limiter.util.get_remote_address,
    default_limits=[],
)
