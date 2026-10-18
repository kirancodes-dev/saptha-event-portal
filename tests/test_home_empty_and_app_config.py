"""
tests/test_home_empty_and_app_config.py — UPG-53: on a database with no events
the home page shows its empty state, not a made-up hackathon. UPG-54: the
Android app's Capacitor config points at BASE_URL, never the retired Railway
host, and the config step writes only that host.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HOME = r'''
import json
import app as app_module
from models import db
events = sum(1 for _ in db.collection("events").stream())
resp = app_module.app.test_client().get("/")
print("HOME=" + json.dumps({"events": events, "status": resp.status_code, "html": resp.get_data(as_text=True)}))
'''


def test_with_no_events_the_home_page_shows_its_empty_state(tmp_path):
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{tmp_path / 'empty.db'}", FLASK_ENV='development',
               CLOUD_SQL_INSTANCE='')
    env.pop('TEST_DATABASE_URL', None)
    r = subprocess.run([sys.executable, '-c', HOME], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith('HOME=')), None)
    assert line, r.stderr[-1500:]
    result = json.loads(line[5:])
    assert result['events'] == 0 and result['status'] == 200
    html = result['html']
    assert 'No Events Currently Listed' in html
    assert 'demo-hackathon-2026' not in html and 'SapthaHack 2026' not in html


def test_the_capacitor_config_never_points_at_railway():
    tracked = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    configs = [f for f in tracked if os.path.basename(f).startswith('capacitor.config')]
    assert configs
    for path in configs + ['scripts/configure_capacitor.py', 'package.json']:
        with open(os.path.join(ROOT, path), encoding='utf-8') as f:
            text = f.read()
        assert 'railway.app' not in text and 'firebaseapp.com' not in text, path


def test_the_config_step_writes_only_the_base_url_host(tmp_path):
    out = tmp_path / 'capacitor.config.json'
    code = f'import sys; sys.path.insert(0, "scripts"); import configure_capacitor as c; c.configure_capacitor(output_path={str(out)!r})'
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, BASE_URL='https://events.example.edu/'))
    assert r.returncode == 0, r.stderr
    config = json.loads(out.read_text())
    assert config['server'] == {'url': 'https://events.example.edu', 'allowNavigation': ['events.example.edu']}
    with open(os.path.join(ROOT, 'package.json'), encoding='utf-8') as f:
        assert 'configure_capacitor.py' in f.read()             # the build runs the step before cap sync
