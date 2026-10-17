from contextlib import contextmanager
import atexit
import os
import threading
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
POOL_MAX_SIZE = int(os.getenv("DATABASE_POOL_MAX_SIZE", "32"))


def reset_session(conn):
    conn.execute("SELECT pg_advisory_unlock_all()")
    conn.commit()


pool = ConnectionPool(settings.database_url, min_size=2, max_size=POOL_MAX_SIZE, open=False, kwargs={"row_factory": dict_row}, timeout=15, max_waiting=128, reset=reset_session)
_pool_lock = threading.Lock()
_pool_started = False
atexit.register(pool.close)


@contextmanager
def connection():
    global _pool_started
    if not _pool_started:
        with _pool_lock:
            if not _pool_started:
                pool.open(wait=True, timeout=15)
                _pool_started = True
    with pool.connection() as conn:
        yield conn


def migrate():
    from app.ingestion.schema import ensure_schema

    with connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version text PRIMARY KEY, applied_at timestamptz DEFAULT now())")
        ensure_schema(conn)
        for path in sorted((__import__('pathlib').Path(__file__).resolve().parent.parent / "migrations").glob("*.sql")):
            if not conn.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (path.name,)).fetchone():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations(version) VALUES(%s)", (path.name,))
