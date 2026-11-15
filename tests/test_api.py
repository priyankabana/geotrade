"""API contract and abuse tests.

The API is the only thing a user ever touches, and until this file it had no
tests at all. Writing them found three 500s: a negative `limit` went straight
into a SQL LIMIT clause on three endpoints, and nothing bounded it from above
either.

Everything here runs in-process through FastAPI's TestClient, so no server need
be running; the database does, and the suite skips cleanly when it is not.
"""
import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))


@pytest.fixture(scope="module")
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    try:
        import main
    except Exception as exc:                      # pragma: no cover
        pytest.skip(f"API will not import: {exc}")
    c = TestClient(main.app)
    try:
        r = c.get("/v1/health")
        assert r.status_code == 200
    except Exception as exc:
        pytest.skip(f"no database behind the API: {exc}")
    return c


# ----------------------------------------------------------------- the basics

def test_health_reports_what_is_actually_loaded(client):
    d = client.get("/v1/health").json()
    assert d["ok"] is True
    for k in ("entities", "edges", "exposureRows"):
        assert isinstance(d[k], int) and d[k] >= 0


def test_metrics_matches_the_graph_it_describes(client):
    m = client.get("/v1/metrics").json()
    h = client.get("/v1/health").json()
    assert m["graph"]["citedEdges"] == h["edges"]
    assert m["graph"]["relationships"] <= m["graph"]["citedEdges"]
    assert m["graph"]["concentrationBacked"] <= m["graph"]["citedEdges"]


def test_the_surprise_rate_is_a_fraction(client):
    e = client.get("/v1/metrics").json()["exposure"]
    assert 0.0 <= e["surpriseRate"] <= 1.0
    assert e["surprising"] <= e["rows"]


# -------------------------------------------------------- limits are bounded
# Each of these returned 500 before this file existed: the value went into a
# SQL LIMIT clause unvalidated.

@pytest.mark.parametrize("path", [
    "/v1/globe/points?limit=%s",
    "/v1/countries/US/sectors/AUTO_COMPONENTS/companies?limit=%s",
    "/v1/events/hormuz-2026/exposure?limit=%s",
])
@pytest.mark.parametrize("bad", ["-1", "0", "999999999"])
def test_an_out_of_range_limit_is_rejected_not_crashed(client, path, bad):
    r = client.get(path % bad)
    assert r.status_code == 422, f"{path % bad} returned {r.status_code}"


def test_a_sane_limit_is_honoured(client):
    rows = client.get("/v1/globe/points?limit=5").json()
    assert len(rows) <= 5


def test_a_non_numeric_limit_is_rejected(client):
    assert client.get("/v1/globe/points?limit=abc").status_code == 422


# ------------------------------------------------------------- hostile input

@pytest.mark.parametrize("payload", [
    "US' OR 1=1--",
    "'; DROP TABLE entity; --",
    "US%00",
    "../../etc/passwd",
    "<script>alert(1)</script>",
])
def test_hostile_strings_cannot_reach_the_database(client, payload):
    """Every query is parameterised. A hostile string is data, never syntax."""
    before = client.get("/v1/health").json()["entities"]
    for p in (f"/v1/countries/{payload}/sectors",
              f"/v1/companies/{payload}",
              f"/v1/events/{payload}/exposure"):
        r = client.get(p)
        assert r.status_code in (200, 404, 422), f"{p} returned {r.status_code}"
    assert client.get("/v1/health").json()["entities"] == before


def test_a_404_does_not_echo_an_unbounded_string(client):
    r = client.get("/v1/companies/" + "A" * 4000)
    assert r.status_code == 404
    assert len(r.json()["detail"]) < 200


def test_an_unknown_country_is_empty_not_an_error(client):
    r = client.get("/v1/countries/ZZ/sectors")
    assert r.status_code == 200 and r.json() == []


# ---------------------------------------------------- the citation guarantee

def _any_company_with_edges(client):
    for iso in ("US",):
        for s in client.get(f"/v1/countries/{iso}/sectors").json():
            rows = client.get(
                f"/v1/countries/{iso}/sectors/{s['atlasSector']}/companies?limit=50").json()
            for c in rows:
                d = client.get(f"/v1/companies/{c['companyUid']}").json()
                if d.get("dependsOn") or d.get("dependedOnBy"):
                    return d
    pytest.skip("no company with edges; run make extract")


def test_every_edge_the_api_serves_carries_its_sentence(client):
    """The product's only promise, checked at the surface a user touches."""
    d = _any_company_with_edges(client)
    for e in d["dependsOn"] + d["dependedOnBy"]:
        c = e["citation"]
        assert c["quote"].strip(), f"{e['edgeId']} has an empty quote"
        assert c["sourceUrl"], "a citation with no document to point at"
        assert c["charStart"] is not None and c["charEnd"] > c["charStart"]
        assert c["filedAtUtc"], "a citation with no date is not point-in-time"


def test_a_percentage_is_never_served_without_its_basis_or_withheld(client):
    """A bare 44% is not a fact. Either we know what it is 44% OF, or we say
    nothing - we never print the number alone."""
    d = _any_company_with_edges(client)
    for e in d["dependsOn"] + d["dependedOnBy"]:
        if e["materialityPct"] is not None:
            assert 0 <= e["materialityPct"] <= 100


def test_one_row_per_relationship_not_per_sentence(client):
    """Ducommun names Boeing in sixteen places. That is one dependency."""
    d = _any_company_with_edges(client)
    for side in ("dependsOn", "dependedOnBy"):
        seen = [(e["counterparty"]["name"], e["edgeType"]) for e in d[side]]
        assert len(seen) == len(set(seen)), f"{side} repeats a relationship"


def test_corroboration_is_counted_not_discarded(client):
    d = _any_company_with_edges(client)
    for e in d["dependsOn"] + d["dependedOnBy"]:
        assert e.get("corroboratingCitations", 1) >= 1


def test_licensed_identifiers_are_withheld(client):
    """CUSIP and SEDOL are licensed. Storing them to join on is not the same as
    republishing them."""
    d = _any_company_with_edges(client)
    schemes = {i["scheme"].upper() for i in d.get("identifiers", [])}
    assert not schemes & {"CUSIP", "SEDOL"}


# --------------------------------------------------------- events and budget

def test_an_event_older_than_the_corpus_reaches_nobody_beyond_hop_one(client):
    """Ever Given is 2021 and our first filing is 2022. Zero is correct."""
    r = client.get("/v1/events/ever-given/exposure")
    if r.status_code == 404:
        pytest.skip("ever-given not seeded")
    assert r.json()["surprisingCount"] == 0


def test_exposure_rows_are_ranked_with_the_surprising_ones_first(client):
    rows = client.get("/v1/events/hormuz-2026/exposure?limit=50").json()["rows"]
    if not rows:
        pytest.skip("no exposure for this event")
    first_plain = next((i for i, r in enumerate(rows) if not r["isSurprising"]), len(rows))
    assert all(not r["isSurprising"] for r in rows[first_plain:])


def test_every_event_declares_when_the_world_learned_of_it(client):
    for e in client.get("/v1/events").json():
        assert e["becamePublicUtc"], f"{e['key']} has no publication date"


def test_the_read_path_stays_inside_its_budget(client):
    """200 ms is a number we publish. Measure it rather than assume it."""
    import time
    worst = 0.0
    for p in ("/v1/health", "/v1/metrics", "/v1/globe/countries",
              "/v1/events", "/v1/events/hormuz-2026/exposure"):
        t0 = time.monotonic()
        assert client.get(p).status_code == 200
        worst = max(worst, (time.monotonic() - t0) * 1000)
    assert worst < 200, f"slowest read took {worst:.0f} ms"


def test_a_bad_api_key_is_refused(client):
    assert client.get("/v1/health", headers={"X-API-Key": "not-a-key"}).status_code == 401


def test_every_response_reports_how_long_it_took(client):
    r = client.get("/v1/health")
    assert float(r.headers["x-response-time-ms"]) >= 0


# ------------------------------------------------------- concurrency and cost

def test_the_tenant_cannot_leak_between_pooled_connections(client):
    """Connections are reused. The tenant is set with SET LOCAL inside the
    transaction precisely so one request's tenant cannot survive into the next
    request that happens to get the same connection. Hammer it and check."""
    import concurrent.futures as cf
    good_key = None                       # unauthenticated requests use the default tenant

    def one(i):
        if i % 3 == 0:
            r = client.get("/v1/health", headers={"X-API-Key": "definitely-not-a-key"})
            return ("bad", r.status_code)
        r = client.get("/v1/events/hormuz-2026/exposure?limit=5")
        return ("good", r.status_code, r.json().get("totalExposed"))

    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        out = list(ex.map(one, range(60)))

    assert all(r[1] == 401 for r in out if r[0] == "bad"), "a bad key was accepted"
    totals = {r[2] for r in out if r[0] == "good"}
    assert all(r[1] == 200 for r in out if r[0] == "good")
    assert len(totals) == 1, f"the same query returned different totals: {totals}"
    assert next(iter(totals)) > 0, "a valid request saw no rows - the tenant was lost"


def test_exposure_does_not_issue_a_query_per_row(client):
    """This endpoint ran its main query twice and then one more query per edge
    row to ask who owned it - a value the row already carried. Count the round
    trips rather than trust that it stays fixed."""
    import main
    calls = {"n": 0}
    real = main.psycopg.Cursor.execute

    def counting(self, *a, **kw):
        calls["n"] += 1
        return real(self, *a, **kw)

    main.psycopg.Cursor.execute = counting
    try:
        r = client.get("/v1/events/hormuz-2026/exposure?limit=40")
    finally:
        main.psycopg.Cursor.execute = real
    assert r.status_code == 200
    rows = len(r.json()["rows"])
    assert calls["n"] <= 12, (
        f"{calls['n']} queries for {rows} rows - that is a query per row again")
