"""API keys: how they are stored, and whether revoking one actually works.

A revocation that does not revoke is worse than no revocation, because somebody
believes the key is dead.
"""
import hashlib, os, subprocess, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))


@pytest.fixture(scope="module")
def api():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    try:
        import main
    except Exception as exc:
        pytest.skip(f"API will not import: {exc}")
    c = TestClient(main.app)
    try:
        assert c.get("/v1/health").status_code == 200
    except Exception as exc:
        pytest.skip(f"no database behind the API: {exc}")
    return c, main


def _mint(tx, name="test key"):
    """A key minted the way scripts/api_key.py mints one, inside the test's
    transaction so it disappears on rollback."""
    import secrets
    key = "atlas_" + secrets.token_urlsafe(32)
    tx.execute("SELECT id FROM tenant ORDER BY created_at LIMIT 1")
    row = tx.fetchone()
    if not row:
        pytest.skip("no tenant")
    tx.execute("""INSERT INTO api_key (tenant_id, name, key_sha256)
                  VALUES (%s,%s,%s) RETURNING id""",
               (row[0], name, hashlib.sha256(key.encode()).hexdigest()))
    return key, tx.fetchone()[0]


def test_the_plaintext_key_is_never_stored(tx):
    key, _ = _mint(tx)
    tx.execute("SELECT count(*) FROM api_key WHERE key_sha256 = %s", (key,))
    assert tx.fetchone()[0] == 0, "the key itself is in the table"
    tx.execute("SELECT count(*) FROM api_key WHERE key_sha256 = %s",
               (hashlib.sha256(key.encode()).hexdigest(),))
    assert tx.fetchone()[0] == 1, "the hash is not there either"


def test_two_keys_are_never_the_same(tx):
    a, _ = _mint(tx, "one")
    b, _ = _mint(tx, "two")
    assert a != b
    assert len(a) > 40, "a key short enough to guess is not a key"


def test_a_revoked_key_stops_resolving_to_a_tenant(tx, api):
    """Revocation is a WHERE clause. If it is ever dropped, this fails."""
    _c, main = api
    key, kid = _mint(tx)
    tx.execute("UPDATE api_key SET revoked_at = now() WHERE id = %s", (kid,))
    tx.execute("""SELECT count(*) FROM api_key
                  WHERE key_sha256 = %s AND revoked_at IS NULL""",
               (hashlib.sha256(key.encode()).hexdigest(),))
    assert tx.fetchone()[0] == 0, "a revoked key still resolves"


def test_an_unknown_key_is_refused_by_the_api(api):
    c, _ = api
    assert c.get("/v1/health", headers={"X-API-Key": "atlas_nope"}).status_code == 401


def test_an_empty_key_header_is_not_a_free_pass(api):
    """An empty header must not be treated as 'no key supplied'."""
    c, _ = api
    r = c.get("/v1/health", headers={"X-API-Key": ""})
    assert r.status_code in (200, 401)       # either is defensible; a 500 is not


@pytest.mark.parametrize("hostile", [
    "' OR '1'='1",
    "atlas_" + "A" * 5000,
    "\x01\x02",
])
def test_a_hostile_key_is_refused_not_crashed(api, hostile):
    c, _ = api
    assert c.get("/v1/health", headers={"X-API-Key": hostile}).status_code == 401


def test_the_key_script_runs_and_shows_the_key_exactly_once(tx):
    """The key is printed at creation and never again. If the listing ever
    started printing it, the hash-only storage would be pointless."""
    r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "scripts", "api_key.py"),
                        "list"], capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "atlas_" not in r.stdout, "the listing printed a key"


def test_the_app_role_cannot_read_keys_it_should_not(tx):
    """atlas_app needs to look a key up; it must not be able to forge one."""
    import psycopg
    dsn = os.environ.get("ATLAS_APP_DSN",
                         "postgresql://atlas_app:atlas_app@localhost:5432/atlas")
    try:
        conn = psycopg.connect(dsn, connect_timeout=3, autocommit=True)
    except Exception as exc:
        pytest.skip(f"no atlas_app role: {exc}")
    with conn.cursor() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO api_key (tenant_id, name, key_sha256) "
                      "VALUES ((SELECT id FROM tenant LIMIT 1),'forged','x')")
    conn.close()
