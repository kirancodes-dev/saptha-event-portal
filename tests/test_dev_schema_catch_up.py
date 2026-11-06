"""
tests/test_dev_schema_catch_up.py — UPG-61: a development SQLite database made
before a NOT NULL column existed (here `events.activity_points`) gets the column,
NOT NULL with its default, at development start-up, and the SPOC dashboard works
on it. Runs in a subprocess with its own database file.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = r'''
import json, os
from sqlalchemy import create_engine, inspect, text
from werkzeug.security import generate_password_hash
from models_pg import Base
url = os.environ["DATABASE_URL"]
engine = create_engine(url)
Base.metadata.create_all(engine)
with engine.begin() as conn:
    conn.execute(text("ALTER TABLE events DROP COLUMN activity_points"))      # an old database
before = [c["name"] for c in inspect(engine).get_columns("events")]
engine.dispose()

import app as app_module                       # development start-up: init_db catches up
flask_app = app_module.app
flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
from models import db
import db_pg
col = next(c for c in inspect(db_pg.get_engine()).get_columns("events") if c["name"] == "activity_points")
db.collection("users").document("oldspoc@test.edu").set({"name": "Old SPOC", "role": "ClubSPOC", "category": "Technical",
                                                          "password": generate_password_hash("Old-pass-12345")}, merge=False)
client = flask_app.test_client()
client.post("/login", data={"role": "ClubSPOC", "email": "oldspoc@test.edu", "password": "Old-pass-12345"})
status = client.get("/spoc/dashboard").status_code
print("RESULT=" + json.dumps({"before": "activity_points" in before, "nullable": col["nullable"],
                              "default": str(col.get("default")), "dashboard": status}))
'''


def test_an_old_development_database_gets_the_not_null_column_and_the_dashboard_works(tmp_path):
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{tmp_path / 'old.db'}", DATABASE_TYPE='postgres', FLASK_ENV='development')
    env.pop('TEST_DATABASE_URL', None)
    r = subprocess.run([sys.executable, '-c', SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith('RESULT=')), None)
    assert line, (r.stdout[-800:], r.stderr[-2000:])
    result = json.loads(line[len('RESULT='):])
    assert result['before'] is False                       # the column really was missing
    assert result['nullable'] is False and result['default'].strip("'\"") in ('0', '0.0')
    assert result['dashboard'] == 200
