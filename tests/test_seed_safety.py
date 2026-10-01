"""
tests/test_seed_safety.py — BLK-10: seed, setup and wipe scripts refuse
production-looking databases before anything connects, unless the operator
passes --i-know-this-is-production on the command line.
"""
import ast
import glob
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = ['seed_*.py', 'saptha_full_seed.py', 'demo_reset.py', 'setup_*.py', 'init_*.py',
            'fix_superadmin.py', 'reset_system.py', 'wipe_data.py', 'delete_data.py',
            'scripts/*.py', 'scratch/seed_*.py', 'scratch/set_*password*.py']
SKIP = {'seed_safety.py'}


def _tracked():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True)
    return set(out.stdout.split())


SCRIPTS = sorted({f for p in PATTERNS for f in glob.glob(p, root_dir=ROOT)
                  if f in _tracked() and os.path.basename(f) not in SKIP})

# Runs a script with every way of reaching a database replaced by "exit 99"
RUNNER = r"""
import runpy, sys
def connect(*a, **k):
    sys.stderr.write('CONNECT-ATTEMPT\n'); sys.exit(99)
import sqlalchemy, sqlalchemy.engine
sqlalchemy.create_engine = sqlalchemy.engine.create_engine = connect
for mod, names in (('firebase_admin', ('initialize_app',)), ('requests', ('get', 'post', 'request'))):
    try:
        m = __import__(mod)
        for n in names:
            setattr(m, n, connect)
    except ImportError:
        pass
script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name='__main__')
"""

PRODUCTION_LIKE = {
    'remote DATABASE_URL': {'DATABASE_URL': 'postgresql://user@prod-host.example/db'},
    'CLOUD_SQL_INSTANCE': {'CLOUD_SQL_INSTANCE': 'proj:region:instance'},
    'FLASK_ENV=production': {'FLASK_ENV': 'production'},
    'Cloud SQL socket URL': {'DATABASE_URL': 'postgresql://user@/db?host=/cloudsql/proj:region:inst'},
}


def _run(script, extra_env, *args):
    env = dict(os.environ, **extra_env)
    return subprocess.run([sys.executable, '-c', RUNNER, script, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


def test_there_are_scripts_to_check():
    assert len(SCRIPTS) >= 25, SCRIPTS


@pytest.mark.parametrize('script', SCRIPTS)
def test_every_script_calls_the_guard_before_any_other_import(script):
    tree = ast.parse(open(os.path.join(ROOT, script)).read())
    stdlib_ok = {'os', 'sys', '__future__'}
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and getattr(node.value.func, 'id', '') == 'guard':
            return
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # docstring
        if isinstance(node, ast.ImportFrom) and node.module == 'seed_safety':
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            if all((n or '').split('.')[0] in stdlib_ok for n in names):
                continue
        if isinstance(node, ast.Expr) and 'sys.path' in ast.unparse(node):
            continue
        pytest.fail(f'{script}: line {node.lineno} runs before guard(): {ast.unparse(node)[:80]}')
    pytest.fail(f'{script}: never calls guard()')


@pytest.mark.parametrize('script', SCRIPTS)
@pytest.mark.parametrize('case', list(PRODUCTION_LIKE))
def test_production_like_targets_are_refused_before_any_connection(script, case):
    result = _run(script, PRODUCTION_LIKE[case])
    assert result.returncode == 3, (script, case, result.returncode, result.stderr[-500:])
    assert 'CONNECT-ATTEMPT' not in result.stderr
    assert 'prod-host.example/db' not in result.stderr  # never echoes the URL


def test_only_the_command_line_flag_overrides_the_guard():
    script = 'seed_all_roles_demo.py'
    env = PRODUCTION_LIKE['remote DATABASE_URL']
    # An environment variable can't stand in for the flag
    refused = _run(script, dict(env, I_KNOW_THIS_IS_PRODUCTION='1', SEED_OVERRIDE='--i-know-this-is-production'))
    assert refused.returncode == 3
    # With the flag, the guard lets it through (and the next step is a connection)
    allowed = _run(script, env, '--i-know-this-is-production')
    assert allowed.returncode == 99 and 'CONNECT-ATTEMPT' in allowed.stderr, allowed.stderr[-500:]


def test_firestore_scripts_also_need_the_project_named(tmp_path):
    script = 'seed_demo.py'
    key = tmp_path / 'fake-service-account.json'
    key.write_text('{"project_id": "demo-project"}')
    env = {'GOOGLE_APPLICATION_CREDENTIALS': str(key), 'FIRESTORE_EMULATOR_HOST': ''}
    no_project = _run(script, env)
    assert no_project.returncode == 3 and 'confirm-firestore-project' in no_project.stderr
    wrong = _run(script, env, '--confirm-firestore-project=someone-elses-project')
    assert wrong.returncode == 3
    named = _run(script, env, '--confirm-firestore-project=demo-project')
    assert named.returncode == 99 and 'CONNECT-ATTEMPT' in named.stderr  # past the guard


def test_local_databases_are_allowed():
    from seed_safety import production_reasons
    for url in ('sqlite:///local.db', 'postgresql://u@localhost/db', 'postgresql://u@db:5432/app',
                'postgresql://postgres:@/test?host=/tmp/pg-socket'):
        assert production_reasons({'DATABASE_URL': url}) == [], url
    assert production_reasons({}) == []


# ── BLK-10b: no known passwords ────────────────────────────────────────────

def _password_literals(source):
    """String literals used as passwords: password-named dict keys, keyword
    arguments and variables, and generate_password_hash('...')."""
    def named(n):
        n = (n or '').lower()
        return 'pass' in n or n.endswith('_pw') or n in ('pw', 'pwd')

    def literal(v):
        return isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            found += [node.lineno for k, v in zip(node.keys, node.values)
                      if isinstance(k, ast.Constant) and isinstance(k.value, str) and named(k.value) and literal(v)]
        elif isinstance(node, ast.Call):
            found += [node.lineno for kw in node.keywords if named(kw.arg) and literal(kw.value)]
            fn = getattr(node.func, 'id', None) or getattr(node.func, 'attr', None)
            if fn == 'generate_password_hash' and node.args and literal(node.args[0]):
                found.append(node.lineno)
        elif isinstance(node, ast.Assign) and literal(node.value):
            found += [node.lineno for t in node.targets if isinstance(t, ast.Name) and named(t.id)]
    return found


@pytest.mark.parametrize('script', SCRIPTS)
def test_no_script_uses_a_string_literal_as_a_password(script):
    assert _password_literals(open(os.path.join(ROOT, script)).read()) == [], script


def _seed(tmp_path, name, **env):
    db_file = tmp_path / f'{name}.db'
    run_env = dict(os.environ, DATABASE_URL=f'sqlite:///{db_file}', CLOUD_SQL_INSTANCE='', FLASK_ENV='development',
                   **{k: v for k, v in env.items()})
    for role in ('SUPERADMIN', 'CLUBSPOC', 'EVENTCOORDINATOR', 'JUDGE', 'STUDENT'):
        run_env.setdefault(f'SEED_{role}_PASSWORD', '')
    out = subprocess.run([sys.executable, 'seed_all_roles_demo.py'], cwd=ROOT, env=run_env,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-1500:]
    import sqlite3
    with sqlite3.connect(db_file) as conn:
        hashes = dict(conn.execute('SELECT id, "passwordHash" FROM users'))
    printed = {}
    tail = out.stdout.split('Seeded account passwords', 1)[1]
    for line in tail.strip().splitlines()[1:]:
        role, value = line.split(None, 1)
        printed[role] = value.strip()
    return hashes, printed


def test_seed_passwords_come_from_the_environment_or_are_random(tmp_path):
    from werkzeug.security import check_password_hash

    hashes, printed = _seed(tmp_path, 'from-env', SEED_SUPERADMIN_PASSWORD='env-admin-Pass-42',
                            SEED_STUDENT_PASSWORD='env-student-Pass-42')
    assert check_password_hash(hashes['admin@snpsu.edu.in'], 'env-admin-Pass-42')
    assert check_password_hash(hashes['student001@snpsu.edu.in'], 'env-student-Pass-42')
    assert printed['SUPERADMIN'] == '(from SEED_SUPERADMIN_PASSWORD)'  # never echoed
    assert 'env-admin-Pass-42' not in printed.values()

    first_hashes, first = _seed(tmp_path, 'random-1')
    second_hashes, second = _seed(tmp_path, 'random-2')
    assert check_password_hash(first_hashes['admin@snpsu.edu.in'], first['SUPERADMIN'])
    assert check_password_hash(first_hashes['spoc@snpsu.edu.in'], first['CLUBSPOC'])
    assert first['SUPERADMIN'] != second['SUPERADMIN']
    assert first['STUDENT'] != second['STUDENT']
    assert len(first['SUPERADMIN']) >= 12
