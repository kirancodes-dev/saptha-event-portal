"""
middleware_tenant.py — Tenant Resolution Middleware for SapthaEvent

Resolves the current organization (tenant) from the request context and
injects it into Flask's ``g`` object as ``g.org``.

Resolution order:
  1. Subdomain  — ``mit-manipal.sapthaevent.com``
  2. URL path   — ``/org/mit-manipal/...``
  3. Header     — ``X-Tenant-Domain: manipal.edu``
  4. Session    — ``session['org_id']``
  5. Default    — falls back to the configured default org
"""
import logging
from flask import g, request, session, abort
from models_tenant import get_org_by_slug, get_org_by_domain, get_org_by_id

logger = logging.getLogger(__name__)

# Routes that skip tenant resolution
PUBLIC_PATHS = frozenset([
    "/", "/login", "/register", "/logout", "/health", "/health/ready",
    "/favicon.ico", "/robots.txt", "/sitemap.xml", "/sw.js",
    "/manifest.webmanifest", "/offline", "/privacy", "/terms",
    "/api/v1/", "/api/v1/auth/login", "/api/v1/auth/register",
    "/api/v1/auth/refresh", "/api/v1/events",
    "/forgot_password", "/reset_password",
])

PUBLIC_PREFIXES = (
    "/static/", "/cdn-cgi/", "/.well-known/", "/verify/",
    "/event/", "/calendar", "/api/v1/events/",
    "/diag/", "/live/",
)


def init_tenant_middleware(app, db):
    """Register the tenant resolution middleware on the Flask app.

    Call this once during app initialization::

        from middleware_tenant import init_tenant_middleware
        init_tenant_middleware(app, db)
    """

    @app.before_request
    def resolve_tenant():
        """Resolve the current tenant before each request."""
        # Skip for public routes
        path = request.path
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            g.org = None
            return

        if db is None:
            g.org = None
            return

        org = None

        # 1. Subdomain resolution
        host = request.host.split(":")[0]  # remove port
        parts = host.split(".")
        if len(parts) >= 3:
            subdomain = parts[0]
            if subdomain not in ("www", "api", "admin"):
                org = get_org_by_slug(db, subdomain)
                if org:
                    logger.debug("Tenant resolved from subdomain: %s", subdomain)

        # 2. URL path resolution (/org/<slug>/...)
        if not org and path.startswith("/org/"):
            slug = path.split("/")[2] if len(path.split("/")) > 2 else ""
            if slug:
                org = get_org_by_slug(db, slug)
                if org:
                    logger.debug("Tenant resolved from path: %s", slug)

        # 3. Header resolution
        if not org:
            domain_header = request.headers.get("X-Tenant-Domain")
            if domain_header:
                org = get_org_by_domain(db, domain_header)
                if org:
                    logger.debug("Tenant resolved from header: %s", domain_header)

        # 4. JWT org_id (for API requests)
        if not org and hasattr(g, "jwt_user") and g.jwt_user:
            org_id = g.jwt_user.get("org_id")
            if org_id:
                org = get_org_by_id(db, org_id)

        # 5. Session fallback
        if not org:
            org_id = session.get("org_id")
            if org_id:
                org = get_org_by_id(db, org_id)
                if org:
                    logger.debug("Tenant resolved from session: %s", org_id)

        g.org = org

    @app.context_processor
    def inject_org():
        """Make ``org`` available in all Jinja2 templates."""
        return {"org": getattr(g, "org", None)}
