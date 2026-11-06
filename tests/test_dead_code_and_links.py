"""
tests/test_dead_code_and_links.py — UPG-15: every internal link, form action
and fetch URL in the templates and the app's scripts reaches a route; the
removed copies, scripts and unregistered blueprints stay gone; seeding is one
command (seed.py and its seeds/ package); no tracked file sets a default
walk-in password.
"""
import glob
import os
import re
import subprocess

import pytest
from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import RequestRedirect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# href=/action=/src=/formaction= "/…", or fetch("/…"); a trailing `+` means the
# rest of the URL is built in script ('/event/' + id)
URL = re.compile(r'''(?:\b(?:href|action|src|formaction)\s*=\s*|fetch\(\s*)(["'`])'''
                 r'''(/(?:\{\{.*?\}\}|\{%.*?%\}|\$\{.*?\}|[^"'`\s{$])*)\1(\s*\+)?''')


def _tracked():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.split()


def _sources():
    pages = glob.glob(os.path.join(ROOT, 'templates', '**', '*.html'), recursive=True)
    scripts = [p for p in glob.glob(os.path.join(ROOT, 'static', 'js', '**', '*.js'), recursive=True)
               if '.min.' not in p and 'vendor' not in p]
    return pages + scripts


def _internal_urls(text):
    for m in URL.finditer(text):
        raw = m.group(2)
        if raw.startswith('//'):                       # protocol-relative: another site
            continue
        url = re.sub(r'\{\{.*?\}\}|\$\{.*?\}', '1', raw)   # a Jinja or JS value stands in as "1"
        url = re.sub(r'\{%.*?%\}', '', url).split('?')[0].split('#')[0]
        yield raw, url, bool(m.group(3))


def _resolves(adapter, rules, url, built_in_script):
    if built_in_script:
        return any(rule.startswith(url) for rule in rules)
    for method in ('GET', 'POST'):
        try:
            adapter.match(url, method=method)
            return True
        except (MethodNotAllowed, RequestRedirect):
            return True
        except NotFound:
            continue
    return False


def test_every_internal_link_action_and_fetch_url_reaches_a_route(real_app):
    flask_app, _ = real_app
    adapter = flask_app.url_map.bind('localhost')
    rules = [r.rule for r in flask_app.url_map.iter_rules()]
    checked, broken = 0, []
    for path in _sources():
        with open(path, encoding='utf-8') as f:
            text = f.read()
        for raw, url, built in _internal_urls(text):
            checked += 1
            if not _resolves(adapter, rules, url, built):
                broken.append(f"{os.path.relpath(path, ROOT)}: {raw}")
    assert checked > 400                               # the scan really reads the pages
    assert broken == []


def test_the_link_check_catches_a_dead_link(real_app):
    flask_app, _ = real_app
    adapter = flask_app.url_map.bind('localhost')
    rules = [r.rule for r in flask_app.url_map.iter_rules()]
    sample = ('<a href="/no/such/page">x</a><a href="/event/{{ e.id }}">ok</a>'
              '<script>fetch(`/api/zzz/${id}`); location.href = \'/spoc/nothing/\' + id;</script>')
    verdicts = {raw: _resolves(adapter, rules, url, built) for raw, url, built in _internal_urls(sample)}
    assert verdicts == {'/no/such/page': False, '/event/{{ e.id }}': True, '/api/zzz/${id}': False,
                        '/spoc/nothing/': False}


GONE = ('catalyst.json', 'reset_system.py', 'run_alembic.py', 'saptha-event-portal', 'routes_public.py',
        'routes_head.py', 'routes_super.py', 'routes_api.py', 'seed_demo.py', 'seed_data.py', 'seed_events.py',
        'saptha_full_seed.py', 'scripts/seed_events.py', 'scripts/seed_emulator.py')


def test_the_removed_copies_and_scripts_stay_gone():
    tracked = _tracked()
    assert not [f for f in tracked if f.startswith(('functions/saptha_app/', 'scratch/'))]
    assert not [f for f in GONE if f in tracked]
    # One seed command: seed.py (and the guard it uses); its data sets live in seeds/
    assert sorted(f for f in tracked if re.fullmatch(r'seed[^/]*\.py', f)) == ['seed.py', 'seed_safety.py']
    assert not [f for f in tracked if re.fullmatch(r'scripts/seed[^/]*\.py', f)]


def test_every_blueprint_in_a_route_module_is_registered(real_app):
    flask_app, _ = real_app
    defined = {}
    for path in (f for f in _tracked() if re.fullmatch(r'routes_[^/]*\.py', f)):
        with open(os.path.join(ROOT, path), encoding='utf-8') as f:
            for name in re.findall(r'''\bBlueprint\(\s*['"]([^'"]+)['"]''', f.read()):
                defined[name] = path
    assert len(defined) > 20
    assert {n: p for n, p in defined.items() if n not in flask_app.blueprints} == {}


def test_no_tracked_file_sets_a_default_walk_in_password():
    hits = subprocess.run(['git', 'grep', '-l', 'WALKIN_DEFAULT_PASSWORD', '--', '.', ':!docs/',
                           ':!tests/test_dead_code_and_links.py'],
                          cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert hits == []


@pytest.mark.parametrize('profile', ['demo', 'events', 'scale', 'showcase'])
def test_every_seed_profile_is_behind_the_guard(profile):
    from tests.test_seed_safety import PRODUCTION_LIKE, _run
    result = _run('seed.py', PRODUCTION_LIKE['remote DATABASE_URL'], '--profile', profile)
    assert result.returncode == 3 and 'CONNECT-ATTEMPT' not in result.stderr, result.stderr[-500:]


@pytest.mark.parametrize('profile', ['demo', 'events', 'showcase'])
def test_the_override_flag_reaches_every_profile(profile):
    # seed.py's guard takes the flag out of argv; the seed module's own guard
    # must still honour it (the showcase module calls guard() before connecting)
    from tests.test_seed_safety import PRODUCTION_LIKE, _run
    result = _run('seed.py', PRODUCTION_LIKE['remote DATABASE_URL'], '--profile', profile, '--i-know-this-is-production')
    assert result.returncode == 99 and 'CONNECT-ATTEMPT' in result.stderr, result.stderr[-500:]
