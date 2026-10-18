"""
tests/test_native_store_migration.py — UPG-58: the native document store's
table comes from a migration, not from start-up. `alembic upgrade head`
creates `native_document_store` and matches the models; with production
settings, writing and reading a native collection issues no CREATE.
"""
from tests import test_migrations_baseline as base
from tests.test_migrations_baseline import COMPARE, _alembic, _python

sqlite_url = base.sqlite_url
pg_url = base.pg_url

NATIVE = r'''
import json
from sqlalchemy import event, inspect
import db_pg
ddl = []
event.listen(db_pg.get_engine(), "before_cursor_execute",
             lambda conn, cursor, stmt, *a: ddl.append(stmt.strip()[:40]) if stmt.strip().upper().startswith(("CREATE", "ALTER")) else None)
from db_adapter import SQLFirestoreAdapter
db = SQLFirestoreAdapter()
db.collection("announcements").document("upg58-check").set({"message": "hello", "priority": "info"})
read = db.collection("announcements").document("upg58-check").get().to_dict()
tables = inspect(db_pg.get_engine()).get_table_names()
print("NATIVE=" + json.dumps({"read": read.get("message"), "ddl": ddl, "table": "native_document_store" in tables}))
'''


def _check(url):
    _alembic(url, 'upgrade', 'head')
    assert _python(COMPARE, url, 'DIFFS') == []
    result = _python(NATIVE, url, 'NATIVE', FLASK_ENV='production', ALLOW_SQLITE_IN_PRODUCTION='true')
    assert result == {'read': 'hello', 'ddl': [], 'table': True}


def test_the_native_store_comes_from_the_migration_on_sqlite(sqlite_url):
    _check(sqlite_url)


def test_the_native_store_comes_from_the_migration_on_postgresql(pg_url):
    _check(pg_url)
