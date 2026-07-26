"""
Shared Flask extensions — imported by both app.py and route modules.
Creating extensions here (without app) lets blueprints use @limiter.limit()
decorators without circular imports.
"""
try:
    from flask_limiter import Limiter
    import flask_limiter.util
    limiter = Limiter(
        key_func=flask_limiter.util.get_remote_address,
        default_limits=[],
    )
except ImportError:
    class DummyLimiter:
        def init_app(self, app):
            pass
        def limit(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator
        def exempt(self, f):
            return f
    limiter = DummyLimiter()
