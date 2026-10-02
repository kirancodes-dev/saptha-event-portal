"""
seed_safety.py — guard and passwords for seed, setup and wipe scripts (BLK-10).

Every such script calls ``guard()`` before importing anything that can open a
database. It refuses (exit code 3) when the target looks like production:

  * FLASK_ENV=production,
  * CLOUD_SQL_INSTANCE set,
  * DATABASE_URL pointing anywhere but SQLite, a local Unix socket or a local
    host (localhost, 127.0.0.1, ::1, or the docker-compose ``db`` service),

unless ``--i-know-this-is-production`` is on the command line (an environment
variable can't stand in for it). ``.env`` is loaded first, exactly as the app
would, because the risky case is a laptop whose ``.env`` points at the real
database.

Scripts that use the Firestore client directly (``guard(firestore=True)``)
must also name the project: ``--confirm-firestore-project=<project id>``,
unless FIRESTORE_EMULATOR_HOST points at a local emulator. The guard checks
the project of exactly the key the script then connects with
(``firestore_key()``, BLK-15), and refuses when it can't read one.

``seed_password(role)`` gives one password per role per run: the value of
``SEED_<ROLE>_PASSWORD`` if set, otherwise a random one. Generated passwords
are printed once when the script ends; values from the environment never are.
"""
import atexit
import json
import os
import secrets
import sys
from urllib.parse import urlparse

OVERRIDE_FLAG = '--i-know-this-is-production'
FIRESTORE_FLAG = '--confirm-firestore-project='
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1', 'db'}
REFUSED_EXIT = 3

_issued = {}


def _load_dotenv():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))


def production_reasons(env=None):
    """Why the configured database looks like production (empty if local)."""
    env = os.environ if env is None else env
    reasons = []
    if env.get('FLASK_ENV', '').strip().lower() == 'production':
        reasons.append('FLASK_ENV=production')
    if env.get('CLOUD_SQL_INSTANCE', '').strip():
        reasons.append('CLOUD_SQL_INSTANCE is set')
    url = env.get('DATABASE_URL', '').strip()
    if url and not url.lower().startswith('sqlite'):
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        if '/cloudsql/' in parsed.query:
            reasons.append('DATABASE_URL uses a Cloud SQL socket')
        # otherwise no host = a Unix socket on this machine (postgresql://user@/db?host=/path)
        elif host and host not in LOCAL_HOSTS:
            # the host only: never echo the URL, it may hold a password
            reasons.append(f"DATABASE_URL points at host '{host or '?'}'")
    return reasons


PROJECT_KEY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serviceAccountKey.json')


def firestore_credentials():
    """The service-account key a Firestore script connects with, as
    ``(source, info)``: where it came from and the parsed key (``None`` if
    that source can't be read). The first source that is set wins, even if it
    is broken, so a bad setting never silently falls through to another key:

      1. FIREBASE_CREDENTIALS (the JSON itself)
      2. FIREBASE_KEY_PATH
      3. serviceAccountKey.json in the current directory
      4. serviceAccountKey.json in the project root
      5. GOOGLE_APPLICATION_CREDENTIALS

    ``(None, None)`` when there is no key at all.
    """
    raw = os.environ.get('FIREBASE_CREDENTIALS', '').strip()
    if raw:
        return 'FIREBASE_CREDENTIALS', _parse(raw)
    for source in (os.environ.get('FIREBASE_KEY_PATH', '').strip(),
                   os.path.abspath('serviceAccountKey.json') if os.path.exists('serviceAccountKey.json') else '',
                   PROJECT_KEY if os.path.exists(PROJECT_KEY) else '',
                   os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '').strip()):
        if source:
            try:
                with open(source) as fh:
                    return source, _parse(fh.read())
            except OSError:
                return source, None
    return None, None


def _parse(text):
    try:
        info = json.loads(text)
    except ValueError:
        return None
    return info if isinstance(info, dict) else None


def firestore_key():
    """The key to pass to firebase_admin.credentials.Certificate: the same one
    guard(firestore=True) confirmed. Exits 1 if there is none."""
    source, info = firestore_credentials()
    if info is None:
        print(f"ERROR: can't read a Firestore service-account key from {source}." if source else
              "ERROR: no Firestore service-account key. Set FIREBASE_CREDENTIALS (the JSON) or "
              "FIREBASE_KEY_PATH, or place serviceAccountKey.json here or in the project root.")
        sys.exit(1)
    return info


def _refuse(lines):
    print('\n'.join(['Refusing to run:'] + [f'  - {line}' for line in lines]), file=sys.stderr)
    sys.exit(REFUSED_EXIT)


def guard(firestore=False, argv=None):
    argv = sys.argv if argv is None else argv
    _load_dotenv()

    reasons = production_reasons()
    if reasons and OVERRIDE_FLAG not in argv:
        _refuse(reasons + [f'If this really is intended, run again with {OVERRIDE_FLAG}.'])

    if firestore and not os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('localhost', '127.0.0.1')):
        confirmed = next((a[len(FIRESTORE_FLAG):] for a in argv if a.startswith(FIRESTORE_FLAG)), '')
        source, info = firestore_credentials()
        expected = str((info or {}).get('project_id') or '')
        if not expected:
            _refuse(["This script writes straight to a real Firestore project, but no project ID can be "
                     f"read from {source or 'any service-account key'}, so it can't be confirmed.",
                     'Set FIREBASE_CREDENTIALS or FIREBASE_KEY_PATH, or place serviceAccountKey.json '
                     'here or in the project root (or use the local emulator).'])
        if confirmed != expected:
            _refuse(['This script writes straight to a real Firestore project.',
                     f'Name it with {FIRESTORE_FLAG}<project id> (or use the local emulator).'])

    # Leave argv as scripts with their own argument parsing expect it
    for flag in [a for a in argv if a == OVERRIDE_FLAG or a.startswith(FIRESTORE_FLAG)]:
        argv.remove(flag)


def seed_password(role):
    """The password for every seeded account with this role, in this run."""
    role = role.upper().replace(' ', '_')
    if role not in _issued:
        from_env = os.environ.get(f'SEED_{role}_PASSWORD', '')
        _issued[role] = (from_env or secrets.token_urlsafe(12), bool(from_env))
        if len(_issued) == 1:
            atexit.register(_print_issued)
    return _issued[role][0]


def _print_issued():
    print('\nSeeded account passwords (shown once; not stored anywhere else):')
    for role, (value, from_env) in sorted(_issued.items()):
        print(f'  {role:<18} ' + (f'(from SEED_{role}_PASSWORD)' if from_env else value))
