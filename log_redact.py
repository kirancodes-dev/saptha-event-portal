"""
log_redact.py — keep emailed link tokens out of the logs (UPG-152).

Set-password, password-reset and cancel links carry their token in the path,
so a logged request path would log the token. `redact` replaces it with
"[redacted]"; the app's request logs and gunicorn's access log use it.
No Flask import, so gunicorn.conf.py can load it.
"""
import re

_TOKEN_PATH = re.compile(r'(/(?:set_password|reset_token|forms/cancel)/)[^\s/?#"]+')


def redact(text):
    """`text` with every link token in it replaced by [redacted]."""
    if not text:
        return text
    return _TOKEN_PATH.sub(r'\1[redacted]', str(text))
