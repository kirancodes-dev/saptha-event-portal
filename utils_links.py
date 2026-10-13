"""
utils_links.py — the address that links in emails, QR codes and messages
point to (UPG-91).

BASE_URL by default (BLK-16). When a request arrives on an address that is
trusted, links point there instead, so a link sent while the portal is used on
this machine, through an ngrok tunnel or in the cloud opens that same place.

Trusted addresses:
  * the host of BASE_URL;
  * every host in TRUSTED_HOSTS (comma-separated; "*.example.com" for subdomains);
  * outside production only: this machine (localhost, 127.0.0.1, ::1), the
    local network (private IP addresses) and ngrok tunnels.

Any other Host header, forged or not, gets BASE_URL: a request can't make the
portal email a link to someone else's site. Only the Host header is read;
X-Forwarded-Host is never trusted (ProxyFix x_host=0, app.py), while the one
proxy hop's X-Forwarded-Proto gives the scheme (ngrok and Cloud Run send https).
"""
import ipaddress
import os
from typing import Optional
from urllib.parse import urlparse

DEV_TUNNEL_SUFFIXES = ('.ngrok-free.app', '.ngrok-free.dev', '.ngrok.app', '.ngrok.io')


def _hostname(host: str) -> str:
    """'Example.com:5001' -> 'example.com'; '[::1]:5001' -> '::1'."""
    host = (host or '').strip().lower()
    if host.startswith('['):
        return host[1:host.find(']')] if ']' in host else ''
    return host.rsplit(':', 1)[0] if host.count(':') == 1 else host


def _listed(name: str, patterns) -> bool:
    for pattern in patterns:
        if pattern.startswith('*.') and (name.endswith(pattern[1:]) or name == pattern[2:]):
            return True
        if name == pattern:
            return True
    return False


def is_trusted_host(host: str, base_url: str, production: bool) -> bool:
    name = _hostname(host)
    if not name or any(c in name for c in '/\\@ '):
        return False
    if name == (urlparse(base_url).hostname or '').lower():
        return True
    listed = [p.strip().lower() for p in os.environ.get('TRUSTED_HOSTS', '').split(',') if p.strip()]
    if _listed(name, listed):
        return True
    if production:
        return False
    if name == 'localhost' or name.endswith(DEV_TUNNEL_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def request_origin(base_url: str) -> Optional[str]:
    """'scheme://host' of the current request when its host is trusted, else None
    (also outside a request, e.g. in scheduled jobs)."""
    try:
        from flask import current_app, has_request_context, request
    except ImportError:
        return None
    if not has_request_context():
        return None
    production = str(current_app.config.get('FLASK_ENV') or os.environ.get('FLASK_ENV', '')).lower() == 'production'
    host = request.host
    if not is_trusted_host(host, base_url, production):
        return None
    return f"{request.scheme}://{host}"
