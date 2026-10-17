"""
tests/test_dockerignore.py — UPG-98: the container image never contains
credentials, local databases or the .env file, whatever tool builds it.
"""
import fnmatch


def _patterns():
    with open('.dockerignore', encoding='utf-8') as fh:
        return [l.strip() for l in fh if l.strip() and not l.startswith('#')]


def _ignored(path, patterns):
    """Docker's rules for these patterns: root-relative, ** for any depth, a
    directory covers its contents, and a later ! re-includes."""
    ignored = False
    for p in patterns:
        negate, p = p.startswith('!'), p.lstrip('!')
        candidates = {p, p.replace('**/', '')}
        hit = any(fnmatch.fnmatch(path, c) or path.startswith(c.rstrip('/') + '/') for c in candidates)
        if p.startswith('**/'):
            hit = hit or fnmatch.fnmatch(path.rsplit('/', 1)[-1], p[3:])
        if hit:
            ignored = not negate
    return ignored


def test_credentials_and_local_data_stay_out_of_the_image():
    patterns = _patterns()
    for path in ('serviceAccountKey.json', 'config/serviceAccountKey-prod.json', '.env', '.env.production',
                 'saptha_fallback.db', 'saptha_fallback.backup-2026-10-12-before-demo.db', 'instance/app.db',
                 'data/local.sqlite3', 'SapthaEvent_Project_Documentation.docx',
                 'android/app/build.gradle', 'functions/main.py', 'dataconnect/dataconnect.yaml'):
        assert _ignored(path, patterns), path


def test_the_app_itself_still_goes_in():
    patterns = _patterns()
    for path in ('app.py', 'routes_payment.py', 'templates/payment/checkout.html', 'static/css/global.css',
                 'requirements.txt', 'gunicorn.conf.py', 'migrations/env.py'):
        assert not _ignored(path, patterns), path
