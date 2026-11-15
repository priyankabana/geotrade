"""Migrations must apply to an empty database, once each, in order.

`make migrate` used to run 0001 by name and nothing else, so a fresh database
came up with no tenancy fix and no alias review queue, and re-running it failed
on the first CREATE TABLE. Nothing recorded what had already run.

These tests build a real throwaway database each time, because a migration that
only works against a database somebody has already massaged is not a migration.
"""
import hashlib, os, pathlib, subprocess, sys, uuid
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "infra" / "migrations"
ADMIN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")


@pytest.fixture
def fresh_db():
    """An empty database, dropped again whatever the test does."""
    psycopg = pytest.importorskip("psycopg")
    name = "atlas_t_" + uuid.uuid4().hex[:10]
    try:
        admin = psycopg.connect(ADMIN, autocommit=True, connect_timeout=3)
    except Exception as exc:
        pytest.skip(f"no database: {exc}")
    with admin.cursor() as c:
        c.execute(f'CREATE DATABASE "{name}"')
    dsn = ADMIN.rsplit("/", 1)[0] + "/" + name
    try:
        yield dsn
    finally:
        with admin.cursor() as c:
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                      "WHERE datname = %s", (name,))
            c.execute(f'DROP DATABASE IF EXISTS "{name}"')
        admin.close()


def run(dsn, *args):
    env = dict(os.environ, DATABASE_URL=dsn)
    return subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "migrate.py"), *args],
                          capture_output=True, text=True, env=env, cwd=ROOT, timeout=180)


def query(dsn, sql):
    import psycopg
    with psycopg.connect(dsn) as c, c.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


def test_there_is_at_least_one_migration():
    assert list(MIGRATIONS.glob("*.sql"))


def test_migrations_are_ordered_by_a_zero_padded_number():
    for p in MIGRATIONS.glob("*.sql"):
        assert p.name[:4].isdigit(), f"{p.name} will not sort predictably"


def test_the_whole_schema_applies_to_an_empty_database(fresh_db):
    r = run(fresh_db)
    assert r.returncode == 0, r.stdout + r.stderr
    assert query(fresh_db, "SELECT count(*) FROM information_schema.tables "
                           "WHERE table_schema='public'") > 20


def test_running_twice_changes_nothing(fresh_db):
    assert run(fresh_db).returncode == 0
    second = run(fresh_db)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "0 applied" in second.stdout


def test_every_migration_is_recorded_with_the_text_that_was_applied(fresh_db):
    run(fresh_db)
    import psycopg
    with psycopg.connect(fresh_db) as c, c.cursor() as cur:
        cur.execute("SELECT filename, sha256 FROM schema_migration")
        recorded = dict(cur.fetchall())
    for p in MIGRATIONS.glob("*.sql"):
        assert recorded[p.name] == hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_citation_constraint_exists_in_a_fresh_schema(fresh_db):
    """The product's guarantee has to survive a rebuild from nothing."""
    run(fresh_db)
    assert query(fresh_db, """SELECT is_nullable FROM information_schema.columns
                              WHERE table_name='dependency_edge'
                                AND column_name='chunk_id'""") == "NO"


def test_row_level_security_is_on_and_forced_in_a_fresh_schema(fresh_db):
    run(fresh_db)
    assert query(fresh_db, """SELECT count(*) FROM pg_class
                              WHERE relrowsecurity AND relforcerowsecurity""") == 3


def test_the_app_role_exists_and_cannot_write(fresh_db):
    run(fresh_db)
    assert query(fresh_db, "SELECT count(*) FROM pg_roles WHERE rolname='atlas_app'") == 1
    assert query(fresh_db, "SELECT usesuper FROM pg_user WHERE usename='atlas_app'") is False


def test_the_only_sanctioned_read_path_exists(fresh_db):
    run(fresh_db)
    assert query(fresh_db, "SELECT count(*) FROM pg_proc WHERE proname='edges_as_of'") == 1


def test_an_unset_tenant_means_nothing_rather_than_an_error(fresh_db):
    """current_setting() throws when the setting was never made. The policy must
    treat an absent tenant as 'see nothing', not as a crash."""
    run(fresh_db)
    assert query(fresh_db, "SELECT current_tenant() IS NULL") is True


def test_baseline_records_without_executing(fresh_db):
    """Adopting a database that was built by hand must not try to re-run DDL."""
    r = run(fresh_db, "--baseline")
    assert r.returncode == 0, r.stdout + r.stderr
    assert query(fresh_db, "SELECT count(*) FROM schema_migration") == len(
        list(MIGRATIONS.glob("*.sql")))
    assert query(fresh_db, "SELECT count(*) FROM information_schema.tables "
                           "WHERE table_schema='public'") < 5, "baseline executed DDL"


def test_status_reports_an_edit_to_a_migration_that_already_ran(fresh_db, tmp_path):
    """A migration that has run is history. Changing it silently would leave two
    databases with the same version and different schemas."""
    run(fresh_db)
    import psycopg
    with psycopg.connect(fresh_db, autocommit=True) as c, c.cursor() as cur:
        cur.execute("UPDATE schema_migration SET sha256 = 'tampered' "
                    "WHERE filename = (SELECT min(filename) FROM schema_migration)")
    out = run(fresh_db, "--status").stdout
    assert "CHANGED" in out.upper()
