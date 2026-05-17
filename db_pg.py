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

_engine = None
_SessionLocal = None


def _build_engine():
    global _engine, _SessionLocal

    if DATABASE_URL:
        # Local dev: use direct connection string
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5)

    elif CLOUD_SQL_INSTANCE:
        # Production: Cloud SQL Connector (IAM auth, no password needed)
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
            pool_size=5,
        )

    else:
        raise RuntimeError(
            "Set DATABASE_URL (local) or CLOUD_SQL_INSTANCE (production) "
            "environment variable to connect to PostgreSQL."
        )

    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
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
    """Context manager yielding a SQLAlchemy session with auto-commit/rollback."""
    if _SessionLocal is None:
        _build_engine()
    session: Session = _SessionLocal()
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
