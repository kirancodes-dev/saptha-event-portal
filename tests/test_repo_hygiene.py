"""
tests/test_repo_hygiene.py — Nothing that holds user data or credentials may be
tracked in git (BLK-01): local databases, .env files, service-account keys,
compiled Python, the Data Connect emulator's data folder and Flask's instance/.

Also pins the .gitignore rules that keep those files out. CI runs this file in
its own job (see .github/workflows/ci.yml, "Repo hygiene & secret scan").
"""
import ast
import json
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (pattern on the repo-relative path, reason)
FORBIDDEN = [
    (re.compile(r'(^|/)\.env(\.[^/]+)?$'), '.env file (only .env.example may be tracked)'),
    (re.compile(r'\.db$'), 'database file'),
    (re.compile(r'\.sqlite[^/]*$'), 'SQLite database file'),
    (re.compile(r'(^|/)(serviceAccountKey|service-account[^/]*)\.json$'), 'service-account key file'),
    (re.compile(r'\.pyc$'), 'compiled Python'),
    (re.compile(r'(^|/)__pycache__/'), 'compiled Python cache'),
    (re.compile(r'^dataconnect/\.dataconnect/'), 'Data Connect emulator data (local Postgres)'),
    (re.compile(r'^instance/'), 'Flask instance folder (local config / databases)'),
]
ALLOWED = [re.compile(r'(^|/)\.env\.example$')]


def forbidden_reason(path):
    if any(a.search(path) for a in ALLOWED):
        return None
    for pattern, reason in FORBIDDEN:
        if pattern.search(path):
            return reason
    return None


def _git(*args):
    return subprocess.run(['git', '-C', ROOT, *args], capture_output=True, text=True)


@pytest.fixture(scope='module')
def tracked_files():
    top = _git('rev-parse', '--show-toplevel')
    if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(ROOT):
        pytest.skip('not running from a git checkout of this repository')
    out = _git('ls-files', '-z')
    assert out.returncode == 0, out.stderr
    return [p for p in out.stdout.split('\0') if p]


def test_no_forbidden_files_are_tracked(tracked_files):
    offenders = [f'{p}  ({forbidden_reason(p)})' for p in tracked_files if forbidden_reason(p)]
    assert not offenders, (
        'These files must not be committed (remove with `git rm --cached`, '
        'they are covered by .gitignore):\n  ' + '\n  '.join(offenders))


def test_no_service_account_credentials_in_tracked_json(tracked_files):
    offenders = []
    for path in tracked_files:
        if not path.endswith('.json'):
            continue
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full) or os.path.getsize(full) > 2_000_000:
            continue
        try:
            with open(full, encoding='utf-8') as fh:
                data = json.load(fh)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and data.get('type') == 'service_account' and data.get('private_key'):
            offenders.append(path)
    assert not offenders, f'service-account credentials committed: {offenders}'


@pytest.mark.parametrize('path', [
    '.env', '.env.production', 'config/.env.local', 'saptha_fallback.db', 'instance/event_portal.db',
    'data/app.sqlite3', 'x.sqlite-journal', 'serviceAccountKey.json', 'keys/service-account-prod.json',
    '__pycache__/app.cpython-311.pyc', 'pkg/mod.pyc', 'dataconnect/.dataconnect/pgliteData/pg17/PG_VERSION',
])
def test_patterns_flag_forbidden_paths(path):
    assert forbidden_reason(path)


@pytest.mark.parametrize('path', [
    '.env.example', 'saptha-event-portal/.env.example', 'db_adapter.py', 'docs/DATABASE.md',
    'dataconnect/schema/schema.gql', 'dataconnect/dataconnect.yaml', 'tests/test_db_documents.py',
])
def test_patterns_allow_normal_paths(path):
    assert forbidden_reason(path) is None


@pytest.mark.parametrize('path,ignored', [
    ('.env', True), ('.env.production', True), ('sub/.env.local', True),
    ('.env.example', False), ('sub/dir/.env.example', False),
    ('local.db', True), ('data.sqlite', True), ('data.sqlite3', True),
    ('instance/config.py', True), ('dataconnect/.dataconnect/pgliteData/x', True),
    ('__pycache__/m.cpython-311.pyc', True), ('pkg/m.pyc', True),
    ('service-account.json', True), ('service-account-prod.json', True), ('serviceAccountKey.json', True),
    ('dataconnect/schema/schema.gql', False),
])
def test_gitignore_rules(tracked_files, path, ignored):
    # Only this repo's .gitignore counts, not a developer's global excludes file;
    # --no-index so the rule is checked even if such a file were (wrongly) tracked
    r = _git('-c', 'core.excludesFile=/dev/null', 'check-ignore', '--no-index', '-q', path)
    assert (r.returncode == 0) is ignored, f'{path}: expected ignored={ignored}'


# ── No mail password in tracked files (UPG-41) ──────────────────────────────
# A Gmail app password sat in utils_email.py's docstring from 2026-04-19, in a
# format gitleaks doesn't flag. The functions/ copy goes in Phase 5 (UPG-15);
# scratch/ is cleaned up there too.
MAIL_PASSWORD_NAMES = {'MAIL_PASS', 'MAIL_PASSWORD'}
MAIL_PASSWORD_SKIP = ('functions/', 'scratch/')
# NAME = value, NAME: value, NAME=value, "NAME": "value" in text or a string
_MAIL_PASSWORD_TEXT = re.compile(
    r'''\bMAIL_PASS(?:WORD)?["']?[ \t]*[:=][ \t]*["']?(?P<value>[^\s"',;)}\]]*)''')


def _placeholder(value):
    # empty, or a reference to the real value: $VAR, ${{ secrets.X }}, <your password>, {name}
    return not value or value[0] in '$<{'


def _mail_password_in_text(text):
    return [m.group(0) for m in _MAIL_PASSWORD_TEXT.finditer(text) if not _placeholder(m.group('value'))]


_LOOKUPS = {'get', 'getenv', 'pop', 'setdefault'}


def _has_literal(node):
    """A non-empty string in the expression, other than a key it looks up
    (os.environ.get('MAIL_PASS'), config['MAIL_PASS'])."""
    keys = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and n.args:
            func = n.func
            if (func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')) in _LOOKUPS:
                keys.add(id(n.args[0]))
        elif isinstance(n, ast.Subscript):
            keys.add(id(n.slice))
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip()
               and id(n) not in keys for n in ast.walk(node))


def _names_mail_password(node):
    if isinstance(node, ast.Name):
        return node.id in MAIL_PASSWORD_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in MAIL_PASSWORD_NAMES
    if isinstance(node, ast.Subscript):
        return isinstance(node.slice, ast.Constant) and node.slice.value in MAIL_PASSWORD_NAMES
    return isinstance(node, ast.Constant) and node.value in MAIL_PASSWORD_NAMES


def mail_passwords_in_python(source):
    """Code that gives MAIL_PASS / MAIL_PASSWORD a string value (an assignment,
    a dict entry, a keyword, a default such as os.environ.get('MAIL_PASS', 'x')),
    and any string (docstrings included) that spells out such an assignment."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_names_mail_password(t) for t in targets) and node.value is not None and _has_literal(node.value):
                found.append(ast.unparse(node))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if key is not None and _names_mail_password(key) and _has_literal(value):
                    found.append(ast.unparse(node))
        elif isinstance(node, ast.Call):
            if any(k.arg in MAIL_PASSWORD_NAMES and _has_literal(k.value) for k in node.keywords):
                found.append(ast.unparse(node))
            elif len(node.args) >= 2 and _names_mail_password(node.args[0]) and _has_literal(node.args[1]):
                found.append(ast.unparse(node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found += _mail_password_in_text(node.value)
    return found


def test_no_mail_password_in_tracked_files(tracked_files):
    offenders = []
    for path in tracked_files:
        if path.startswith(MAIL_PASSWORD_SKIP):
            continue
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            continue
        with open(full, 'rb') as fh:
            raw = fh.read()
        if b'\0' in raw[:8192]:
            continue  # binary
        text = raw.decode('utf-8', errors='replace')
        if path.endswith('.py'):
            hits = mail_passwords_in_python(text)
        else:
            hits = _mail_password_in_text(text)
        offenders += [f'{path}: {hit}' for hit in hits]
    assert not offenders, ('A mail password value is committed; use the MAIL_PASS environment '
                           'variable and revoke the password:\n  ' + '\n  '.join(offenders))


# The examples spell the names as <PASS> and <PASSWORD>, so this file itself
# passes the scan above.
def _example(text):
    return text.replace('<PASSWORD>', 'MAIL_PASSWORD').replace('<PASS>', 'MAIL_PASS')


@pytest.mark.parametrize('source', [
    '"""\nLAST RESORT: Gmail SMTP\n      <PASS> = abcdefghijklmnop\n"""',
    '<PASSWORD> = "SET_THIS_IN_ENV"',
    '<PASSWORD> = _raw or "fallback-secret"',
    'class C:\n    <PASS>: str = "abcd efgh ijkl mnop"',
    'os.environ["<PASS>"] = "abcdefghijklmnop"',
    'os.environ.setdefault("<PASS>", "abcdefghijklmnop")',
    'x = os.environ.get("<PASS>", "abcdefghijklmnop")',
    'cfg = {"<PASS>": "abcdefghijklmnop"}',
    'app.config.update(<PASSWORD>="abcdefghijklmnop")',
    'help = "set <PASS>=abcdefghijklmnop in .env"',
])
def test_the_mail_password_check_flags_values(source):
    assert mail_passwords_in_python(_example(source))


@pytest.mark.parametrize('source', [
    '<PASSWORD> = os.environ.get("<PASS>")',
    '<PASSWORD> = app.config["<PASSWORD>"]',
    '<PASSWORD> = _mail_pass_raw or ""',
    'mail_pass = os.environ.get("<PASS>", "").strip()',
    'PROVIDERS = ("MAIL_USER", "<PASS>")',
    'monkeypatch.setenv(name, "x")',
    '"""MAIL_USER + <PASS> -> SMTP login; <PASS> is an app password."""',
    'msg = "Gmail: MAIL_USER or <PASS> not set."',
])
def test_the_mail_password_check_allows_names_and_lookups(source):
    assert mail_passwords_in_python(_example(source)) == []


@pytest.mark.parametrize('text,flagged', [
    ('<PASS>=abcdefghijklmnop\n', True),
    ('  <PASS>: hunter2hunter22\n', True),
    ('<PASS>=\n', False),
    ('<PASS>: ${{ secrets.<PASS> }}\n', False),
    ('<PASS>=<your app password>\n', False),
    ('- `<PASS>`: **two different values**\n', False),
])
def test_the_mail_password_check_reads_config_and_docs(text, flagged):
    assert bool(_mail_password_in_text(_example(text))) is flagged
