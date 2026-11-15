"""Tenancy proven by test, not by inspection.

Migration 0001 declared row-level security and wrote the policies. They never
ran, because the API connected as the table owner and Postgres exempts owners
and superusers. Setting a tenant id belonging to nobody still returned every
row. These tests exist so that cannot quietly come back.

They connect as `atlas_app`, which is what the API uses: not an owner, not a
superuser, therefore subject to the policies.
"""
import os
import pytest

APP_DSN = os.environ.get("ATLAS_APP_DSN",
                         "postgresql://atlas_app:atlas_app@localhost:5432/atlas")
NOBODY = "00000000-0000-0000-0000-000000000000"
SCOPED = ("exposure_precompute", "universe_member", "coverage_universe")


@pytest.fixture(scope="module")
def app_conn():
    psycopg = pytest.importorskip("psycopg")
    try:
        conn = psycopg.connect(APP_DSN, connect_timeout=3, autocommit=True)
    except Exception as exc:
        pytest.skip(f"no atlas_app role: {exc}. Apply 0002_tenancy_and_keys.sql")
    yield conn
    conn.close()


def count(conn, table, tenant=None):
    with conn.cursor() as c:
        if tenant is None:
            c.execute("SELECT set_config('atlas.tenant_id', '', false)")
        else:
            c.execute("SELECT set_config('atlas.tenant_id', %s, false)", (tenant,))
        c.execute(f"SELECT count(*) FROM {table}")
        return c.fetchone()[0]


def real_tenant(conn):
    with conn.cursor() as c:
        c.execute("SELECT id FROM tenant ORDER BY created_at LIMIT 1")
        row = c.fetchone()
    if not row:
        pytest.skip("no tenant rows")
    return str(row[0])


@pytest.mark.parametrize("table", SCOPED)
def test_a_caller_with_no_tenant_sees_nothing(app_conn, table):
    """Forgetting to authenticate must yield an empty result, never someone
    else's rows. The policy used to throw instead, which is also wrong."""
    assert count(app_conn, table, None) == 0


@pytest.mark.parametrize("table", SCOPED)
def test_a_caller_with_the_wrong_tenant_sees_nothing(app_conn, table):
    assert count(app_conn, table, NOBODY) == 0


def test_the_right_tenant_does_see_its_own_rows(app_conn):
    """And the policy must not simply hide everything, or it proves nothing."""
    t = real_tenant(app_conn)
    assert count(app_conn, "exposure_precompute", t) > 0


def test_the_app_role_cannot_write(app_conn):
    """A read API has no business holding write rights."""
    import psycopg
    t = real_tenant(app_conn)
    with app_conn.cursor() as c:
        c.execute("SELECT set_config('atlas.tenant_id', %s, false)", (t,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM exposure_precompute")


def test_the_app_role_is_neither_owner_nor_superuser(app_conn):
    """The two conditions under which Postgres silently skips every policy."""
    with app_conn.cursor() as c:
        c.execute("SELECT usesuper FROM pg_user WHERE usename = current_user")
        assert c.fetchone()[0] is False, "atlas_app is a superuser; policies are bypassed"
        c.execute("""SELECT count(*) FROM pg_class
                     WHERE relname = ANY(%s) AND pg_get_userbyid(relowner) = current_user""",
                  (list(SCOPED),))
        assert c.fetchone()[0] == 0, "atlas_app owns a protected table; policies are bypassed"


@pytest.mark.parametrize("table", SCOPED)
def test_policies_are_forced_so_the_owner_cannot_reopen_the_hole(app_conn, table):
    with app_conn.cursor() as c:
        c.execute("""SELECT relrowsecurity, relforcerowsecurity
                     FROM pg_class WHERE relname = %s""", (table,))
        enabled, forced = c.fetchone()
        assert enabled, f"{table} has row-level security switched off"
        assert forced, f"{table} does not FORCE row-level security"


def test_api_keys_are_stored_only_as_hashes(app_conn):
    """The table must be useless to anyone who reads it, including us."""
    with app_conn.cursor() as c:
        c.execute("""SELECT column_name FROM information_schema.columns
                     WHERE table_name = 'api_key'""")
        cols = {r[0] for r in c.fetchall()}
    assert "key_sha256" in cols
    assert not {"key", "secret", "token", "plaintext"} & cols
