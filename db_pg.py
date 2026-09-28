"""
db_pg.py — PostgreSQL connection via Cloud SQL Connector (Firebase SQL Connect)

Usage:
  from db_pg import get_session, init_db

  # Create all tables (run once on startup):
  init_db()

  # Use in a route:
  with get_session() as session:
      events = session.query(Event).filter_by(status='active').all()

Connection method:
  - DATABASE_URL (recommended): postgresql://user:pass@host:5432/db
  - CLOUD_SQL_INSTANCE: Cloud SQL Connector (auto-IAM auth when DB_PASS is empty)
  - Neither set: local SQLite file (development only; refused when FLASK_ENV=production)
"""
import os

try:
    from sqlalchemy import create_engine, event, text
except Exception:
    sqlalchemy = None
try:
    from sqlalchemy.orm import sessionmaker, Session
except Exception:
    sqlalchemy = None
from contextlib import contextmanager

from models_pg import Base

# ── Config ───────────────────────────────────────────────────────────────────
DATABASE_URL      = os.environ.get("DATABASE_URL", "")
CLOUD_SQL_INSTANCE = os.environ.get("CLOUD_SQL_INSTANCE", "")
DB_USER           = os.environ.get("DB_USER", "postgres")
DB_PASS           = os.environ.get("DB_PASS", "")
DB_NAME           = os.environ.get("DB_NAME", "saptha")
READ_REPLICA_URL  = os.environ.get("READ_REPLICA_URL", "")

# PgBouncer Optimizations
PGBOUNCER_POOL_SIZE = int(os.environ.get("PGBOUNCER_POOL_SIZE", "20"))
PGBOUNCER_MAX_OVERFLOW = int(os.environ.get("PGBOUNCER_MAX_OVERFLOW", "10"))
PGBOUNCER_POOL_RECYCLE = int(os.environ.get("PGBOUNCER_POOL_RECYCLE", "1800"))

_engine = None
_replica_engine = None
_SessionLocal = None
_SessionLocalReplica = None


class DatabaseConfigError(RuntimeError):
    """Raised when production is started without a usable PostgreSQL database."""


# Local development database (gitignored). Absolute, so the app finds the same
# file whatever directory it is started from.
LOCAL_SQLITE_PATH = os.environ.get(
    "LOCAL_SQLITE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "saptha_fallback.db"),
)


def _is_production():
    return os.environ.get("FLASK_ENV") == "production"


def _sqlite_engine(url):
    engine = create_engine(url, pool_pre_ping=True,
                           connect_args={"check_same_thread": False, "timeout": 30})

    # Enforce foreign keys like PostgreSQL does, so local runs surface the same errors
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _postgres_engine(url, **kwargs):
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=PGBOUNCER_POOL_SIZE,
        max_overflow=PGBOUNCER_MAX_OVERFLOW,
        pool_recycle=PGBOUNCER_POOL_RECYCLE,
        **kwargs,
    )


def _normalize_url(url):
    # Heroku/Supabase-style URLs use the scheme SQLAlchemy 2 no longer accepts.
    # Without an explicit driver SQLAlchemy 2.1 picks psycopg 3; we ship psycopg2.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


def _build_engine():
    """Pick the database: DATABASE_URL, else Cloud SQL, else local SQLite (dev only)."""
    global _engine, _replica_engine, _SessionLocal, _SessionLocalReplica
    import logging
    log = logging.getLogger(__name__)
    allow_sqlite = (not _is_production()
                    or os.environ.get("ALLOW_SQLITE_IN_PRODUCTION", "").lower() == "true")

    if DATABASE_URL:
        url = _normalize_url(DATABASE_URL)
        if url.startswith("sqlite"):
            if not allow_sqlite:
                raise DatabaseConfigError(
                    "DATABASE_URL points at SQLite in production. Use PostgreSQL, "
                    "or set ALLOW_SQLITE_IN_PRODUCTION=true for a throwaway demo.")
            _engine = _sqlite_engine(url)
        else:
            _engine = _postgres_engine(url)

    elif CLOUD_SQL_INSTANCE:
        # Cloud SQL Connector (IAM auth when DB_PASS is empty)
        try:
            from google.cloud.sql.connector import Connector
        except ImportError as exc:
            raise DatabaseConfigError(
                "CLOUD_SQL_INSTANCE is set but cloud-sql-python-connector is not "
                "installed: pip install 'cloud-sql-python-connector[pg8000]'") from exc

        connector = Connector()

        def getconn():
            return connector.connect(
                CLOUD_SQL_INSTANCE,
                "pg8000",
                user=DB_USER,
                password=DB_PASS or None,
                db=DB_NAME,
                enable_iam_auth=(not DB_PASS),
            )

        _engine = _postgres_engine("postgresql+pg8000://", creator=getconn)

    else:
        if not allow_sqlite:
            raise DatabaseConfigError(
                "No database configured. Set DATABASE_URL to a PostgreSQL URL "
                "(or CLOUD_SQL_INSTANCE) when FLASK_ENV=production.")
        log.info("No DATABASE_URL set — using local SQLite at %s", LOCAL_SQLITE_PATH)
        _engine = _sqlite_engine(f"sqlite:///{LOCAL_SQLITE_PATH}")

    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

    # Read replica only when one is explicitly configured
    if READ_REPLICA_URL:
        try:
            _replica_engine = _postgres_engine(_normalize_url(READ_REPLICA_URL))
            _SessionLocalReplica = sessionmaker(bind=_replica_engine, autocommit=False, autoflush=False)
        except Exception as exc:
            log.warning("Failed to initialize replica engine: %s", exc)

    return _engine


def get_engine():
    if _engine is None:
        _build_engine()
    return _engine


def init_db():
    """Create all tables and missing columns if they don't exist. Call once at app startup."""
    engine = get_engine()
    if engine is not None:
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(engine)
            existing_tables = set(inspector.get_table_names())
            tables_to_create = [
                table for name, table in Base.metadata.tables.items()
                if name not in existing_tables
            ]
            if tables_to_create:
                Base.metadata.create_all(engine, tables=tables_to_create)

            # Reconcile columns added to the models after the table was created.
            # Only nullable columns can be added to a populated table safely.
            with engine.connect() as conn:
                for table_name, table in Base.metadata.tables.items():
                    if table_name not in existing_tables:
                        continue
                    existing_cols = {col['name'] for col in inspector.get_columns(table_name)}
                    for col in table.columns:
                        if col.name in existing_cols or not col.nullable:
                            continue
                        col_type = col.type.compile(engine.dialect)
                        conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type}'))
                        conn.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).info("init_db note: %s", exc)


@contextmanager
def get_session():
    """Context manager yielding a SQLAlchemy session with auto-commit/rollback and read-replica routing."""
    if _SessionLocal is None:
        _build_engine()

    use_replica = False
    try:
        from flask import has_request_context, request
        if has_request_context() and request.method in ('GET', 'HEAD', 'OPTIONS'):
            use_replica = True
    except ImportError:
        pass

    if use_replica and _SessionLocalReplica is not None:
        session: Session = _SessionLocalReplica()
    elif callable(_SessionLocal):
        session: Session = _SessionLocal()
    else:
        raise RuntimeError("SQLAlchemy SessionLocal is uninitialized.")

    # Optional per-tenant schema routing (opt-in). SET LOCAL is scoped to the
    # transaction, so it never leaks onto the next request's pooled connection.
    if os.environ.get("MULTI_TENANT_SCHEMAS", "").lower() == "true":
        try:
            from flask import has_app_context, g
            if has_app_context() and getattr(g, 'org', None):
                org_slug = g.org.get('slug')
                if org_slug and session.bind is not None and session.bind.dialect.name == 'postgresql':
                    schema_name = "tenant_" + "".join(c if c.isalnum() else "_" for c in org_slug)
                    session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
                    session.execute(text(f'SET LOCAL search_path TO "{schema_name}", public'))
        except Exception:
            pass

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping():
    """Test the database connection. Returns True if healthy."""
    try:
        with get_session() as s:
            s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
