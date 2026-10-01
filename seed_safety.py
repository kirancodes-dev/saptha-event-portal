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
unless FIRESTORE_EMULATOR_HOST points at a local emulator.

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


def _firestore_project():
    path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS') or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'serviceAccountKey.json')
    try:
        with open(path) as fh:
            return json.load(fh).get('project_id', '')
    except (OSError, ValueError):
        return ''


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
        expected = _firestore_project()
        if not confirmed or (expected and confirmed != expected):
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
