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
  - Local dev:  Direct TCP via DATABASE_URL env var (postgres://user:pass@host/db)
  - Production: Cloud SQL Connector using CLOUD_SQL_INSTANCE env var (auto-IAM auth)
"""
import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
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


def _build_engine():
    global _engine, _replica_engine, _SessionLocal, _SessionLocalReplica

    # PgBouncer transaction-pooling works best without server-side prepared statements.
    # We pass statement_cache_size=0 if using drivers that cache queries by default.
    connect_args = {}

    if DATABASE_URL:
        # Local dev: use direct connection string with pooling parameters
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=PGBOUNCER_POOL_SIZE,
            max_overflow=PGBOUNCER_MAX_OVERFLOW,
            pool_recycle=PGBOUNCER_POOL_RECYCLE,
            connect_args=connect_args
        )

    elif CLOUD_SQL_INSTANCE:
        # Production: Cloud SQL Connector (IAM auth, no password needed)
        try:
            from google.cloud.sql.connector import Connector

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

            _engine = create_engine(
                "postgresql+pg8000://",
                creator=getconn,
                pool_pre_ping=True,
                pool_size=PGBOUNCER_POOL_SIZE,
                max_overflow=PGBOUNCER_MAX_OVERFLOW,
                pool_recycle=PGBOUNCER_POOL_RECYCLE,
                connect_args=connect_args
            )
        except ImportError:
            import logging
            logging.getLogger(__name__).warning("google-cloud-sql-connector not installed. Falling back to local SQLite: sqlite:///saptha_fallback.db")
            _engine = create_engine("sqlite:///saptha_fallback.db", pool_pre_ping=True)

    else:
        import logging
        logging.getLogger(__name__).warning("No database URL set. Falling back to local SQLite: sqlite:///saptha_fallback.db")
        _engine = create_engine("sqlite:///saptha_fallback.db", pool_pre_ping=True)

    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

    # Build read-replica engine if READ_REPLICA_URL is configured
    rep_url = READ_REPLICA_URL or DATABASE_URL
    if rep_url and not rep_url.startswith("sqlite"):
        try:
            _replica_engine = create_engine(
                rep_url,
                pool_pre_ping=True,
                pool_size=PGBOUNCER_POOL_SIZE,
                max_overflow=PGBOUNCER_MAX_OVERFLOW,
                pool_recycle=PGBOUNCER_POOL_RECYCLE,
                connect_args=connect_args
            )
            _SessionLocalReplica = sessionmaker(bind=_replica_engine, autocommit=False, autoflush=False)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Failed to initialize replica engine: %s", exc)

    return _engine


def get_engine():
    if _engine is None:
        _build_engine()
    return _engine


def init_db():
    """Create all tables if they don't exist. Call once at app startup."""
    engine = get_engine()
    Base.metadata.create_all(engine)


@contextmanager
def get_session() -> "contextmanager[Session]":
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
    else:
        session: Session = _SessionLocal()

    # Dynamic multi-tenant schema partitioning path
    try:
        from flask import has_app_context, g
        if has_app_context() and getattr(g, 'org', None):
            org_slug = g.org.get('slug')
            if org_slug:
                schema_name = f"tenant_{org_slug.replace('-', '_')}"
                if session.bind.dialect.name == 'postgresql':
                    session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name};"))
                    session.execute(text(f"SET search_path TO {schema_name}, public;"))
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
