"""Shared fixtures. Database-backed tests skip cleanly when no database is up,
so `make test` works on a laptop with nothing running and in CI alike."""
import os
import pytest

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")


@pytest.fixture(scope="session")
def db():
    psycopg = pytest.importorskip("psycopg")
    try:
        conn = psycopg.connect(DSN, connect_timeout=3)
    except Exception as exc:
        pytest.skip(f"no database: {exc}")
    conn.autocommit = False
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def tx(db):
    """Every test runs inside a transaction that is always rolled back, so the
    suite can insert freely and never alters the real graph."""
    cur = db.cursor()
    cur.execute("SAVEPOINT test_sp")
    yield cur
    cur.execute("ROLLBACK TO SAVEPOINT test_sp")
    cur.close()
