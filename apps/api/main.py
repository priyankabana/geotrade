"""Atlas read API. Serves the contract in packages/shared/src/api.ts from Postgres.

Read path budget is p95 < 200ms. Nothing here computes exposure - that is precomputed
by the propagation engine. These endpoints are the reference layer only; the evidence
layer endpoints arrive with Phase 2.
"""
import os, hashlib, time, json, logging
from contextlib import contextmanager
from contextvars import ContextVar
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# The API connects as atlas_app, which owns nothing and is not a superuser, so
# row-level security actually applies to it. Connecting as the owner - which is
# what this did until migration 0002 - meant the policies never ran.
DSN = os.environ.get("ATLAS_APP_DSN",
      os.environ.get("DATABASE_URL", "postgresql://atlas_app:atlas_app@localhost:5432/atlas"))
PRODUCT_NAME = os.environ.get("ATLAS_PRODUCT_NAME", "Atlas")
# Open endpoints are the public demo. Set ATLAS_REQUIRE_KEY=1 to require a key.
REQUIRE_KEY = os.environ.get("ATLAS_REQUIRE_KEY", "") not in ("", "0", "false")

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("atlas")
app = FastAPI(title=f"{PRODUCT_NAME} API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["GET"], allow_headers=["*"])

_pool = ConnectionPool(DSN, min_size=1, max_size=8, open=False,
                       kwargs={"row_factory": dict_row})
_tenant: ContextVar[str | None] = ContextVar("tenant", default=None)


@contextmanager
def cur():
    """One connection per use, with the tenant set inside a transaction.

    SET LOCAL is scoped to the transaction, so a connection returned to the pool
    can never carry one request's tenant into the next request's query."""
    if _pool.closed:
        _pool.open()
    with _pool.connection() as conn:
        with conn.cursor() as c:
            t = _tenant.get()
            if t:
                c.execute("SELECT set_config('atlas.tenant_id', %s, true)", (str(t),))
            yield c


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _tenant_for_key(key: str):
    if _pool.closed:
        _pool.open()
    with _pool.connection() as conn, conn.cursor() as c:
        c.execute("""SELECT tenant_id FROM api_key
                     WHERE key_sha256 = %s AND revoked_at IS NULL""", (_hash(key),))
        row = c.fetchone()
        if row:
            c.execute("UPDATE api_key SET last_used_at = now() WHERE key_sha256 = %s",
                      (_hash(key),))
        return row["tenant_id"] if row else None


def _default_tenant():
    if _pool.closed:
        _pool.open()
    with _pool.connection() as conn, conn.cursor() as c:
        c.execute("SELECT id FROM tenant ORDER BY created_at LIMIT 1")
        row = c.fetchone()
        return row["id"] if row else None


@app.middleware("http")
async def authenticate_and_log(request: Request, call_next):
    """Resolve the caller to a tenant, then emit one structured line per request.

    Logs are JSON because the three alerts in the runbook are built on them and
    grepping prose does not scale past one laptop."""
    started = time.monotonic()

    # Postgres text cannot hold a NUL byte, so one in a path parameter reached
    # the driver and came back as a 500. Reject control characters at the edge
    # instead: they are never part of a country code, a ticker or an event key.
    raw = request.url.path
    if "%00" in raw.lower() or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return _json_error(422, "path contains a control character")

    key = request.headers.get("x-api-key")
    tenant = _tenant_for_key(key) if key else None
    if key and tenant is None:
        return _json_error(401, "unknown or revoked API key")
    if tenant is None:
        if REQUIRE_KEY and request.url.path not in ("/v1/health", "/docs", "/openapi.json"):
            return _json_error(401, "X-API-Key required")
        tenant = _default_tenant()

    token = _tenant.set(tenant)
    try:
        response = await call_next(request)
    finally:
        _tenant.reset(token)
    ms = (time.monotonic() - started) * 1000
    log.info(json.dumps({
        "event": "request", "path": request.url.path, "method": request.method,
        "status": response.status_code, "ms": round(ms, 2),
        "tenant": str(tenant) if tenant else None,
        "authenticated": bool(key),
    }))
    response.headers["X-Response-Time-ms"] = f"{ms:.2f}"
    return response


def _json_error(status: int, detail: str):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": detail}, status_code=status)

COUNTRY_NAMES = {
    "US":"United States","CA":"Canada","GB":"United Kingdom","CN":"China","IE":"Ireland",
    "CH":"Switzerland","IL":"Israel","NL":"Netherlands","IN":"India","AU":"Australia",
    "DE":"Germany","JP":"Japan","TW":"Taiwan","KR":"South Korea","SG":"Singapore",
    "BR":"Brazil","FR":"France","SE":"Sweden","HK":"Hong Kong","MX":"Mexico",
    "KY":"Cayman Islands","BM":"Bermuda","IT":"Italy","ID":"Indonesia","ES":"Spain",
    "TH":"Thailand","VG":"British Virgin Islands","JE":"Jersey","GG":"Guernsey",
    "IM":"Isle of Man","LU":"Luxembourg","AT":"Austria","BE":"Belgium","DK":"Denmark",
    "FI":"Finland","NO":"Norway","PL":"Poland","PT":"Portugal","GR":"Greece",
    "TR":"Turkey","RU":"Russia","ZA":"South Africa","NZ":"New Zealand","MY":"Malaysia",
    "PH":"Philippines","VN":"Vietnam","AE":"United Arab Emirates","SA":"Saudi Arabia",
    "QA":"Qatar","KW":"Kuwait","EG":"Egypt","NG":"Nigeria","KE":"Kenya","MA":"Morocco",
    "MT":"Malta","CY":"Cyprus","IS":"Iceland","LI":"Liechtenstein","MC":"Monaco",
    "MU":"Mauritius","LK":"Sri Lanka","BD":"Bangladesh","PK":"Pakistan","NP":"Nepal",
    "KZ":"Kazakhstan","UA":"Ukraine","AR":"Argentina","CL":"Chile","CO":"Colombia",
    "PE":"Peru","UY":"Uruguay","PA":"Panama","CZ":"Czech Republic","HU":"Hungary",
    "RO":"Romania","SI":"Slovenia","SK":"Slovakia","HR":"Croatia","BG":"Bulgaria",
    "LT":"Lithuania","LV":"Latvia","EE":"Estonia","MN":"Mongolia","GI":"Gibraltar",
    "BS":"Bahamas","BB":"Barbados","CR":"Costa Rica","DO":"Dominican Republic",
    "JO":"Jordan","LB":"Lebanon","OM":"Oman","BH":"Bahrain","TZ":"Tanzania",
    "GH":"Ghana","ZW":"Zimbabwe","NA":"Namibia","BW":"Botswana","ZM":"Zambia",
    "MO":"Macao","KH":"Cambodia","LA":"Laos","MM":"Myanmar","FJ":"Fiji","PG":"Papua New Guinea",
}

@app.get("/v1/health")
def health():
    with cur() as c:
        c.execute("SELECT count(*) AS n FROM entity")
        n = c.fetchone()["n"]
        c.execute("SELECT count(*) AS n FROM dependency_edge")
        edges = c.fetchone()["n"]
        c.execute("SELECT count(*) AS n FROM exposure_precompute")
        exposure = c.fetchone()["n"]
    return {"ok": True, "entities": n, "edges": edges, "exposureRows": exposure,
            "product": PRODUCT_NAME, "requiresKey": REQUIRE_KEY}

@app.get("/v1/globe/countries")
def countries():
    with cur() as c:
        c.execute("""
            SELECT l.country,
                   count(DISTINCT e.id) AS company_count,
                   count(DISTINCT e.atlas_sector) AS sector_count,
                   count(DISTINCT d.from_entity_id) AS mapped
            FROM entity_location l
            JOIN entity e ON e.id = l.entity_id
            LEFT JOIN dependency_edge d ON d.from_entity_id = e.id
            WHERE l.role = 'hq'
            GROUP BY l.country ORDER BY 2 DESC
        """)
        return [{
            "country": r["country"],
            "name": COUNTRY_NAMES.get(r["country"], r["country"]),
            "companyCount": r["company_count"],
            "mappedCompanyCount": r["mapped"],
            "sectorCount": r["sector_count"],
            "activeEventCount": 0,
            # Null, not zero. No price source has a verified licence row yet, and a
            # zero would read as "flat" rather than "we are not allowed to tell you".
            "sectorMoveSummary": None,
        } for r in c.fetchall()]

@app.get("/v1/globe/points")
def globe_points(limit: int = Query(4000, ge=1, le=30000)):
    """Every geolocated company HQ. The globe should show the data, not just a shape."""
    with cur() as c:
        c.execute("""
            SELECT li.company_uid AS uid, e.common_name AS name, e.atlas_sector AS sector,
                   l.country, ST_Y(l.geom::geometry) AS lat, ST_X(l.geom::geometry) AS lon
            FROM entity_location l
            JOIN entity e ON e.id = l.entity_id
            JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
            WHERE l.role = 'hq'
            LIMIT %s
        """, (limit,))
        return [dict(r) for r in c.fetchall()]


@app.get("/v1/countries/{iso2}/sectors")
def sectors(iso2: str):
    with cur() as c:
        c.execute("""
            SELECT e.atlas_sector AS code, s.name, count(*) AS n
            FROM entity e
            JOIN entity_location l ON l.entity_id = e.id AND l.role = 'hq'
            LEFT JOIN atlas_sector s ON s.code = e.atlas_sector
            WHERE l.country = %s AND e.atlas_sector IS NOT NULL
            GROUP BY 1, 2
            -- 'Unclassified' is a gap in our mapping, not a sector anyone wants to
            -- browse, so it sorts last however big it is.
            ORDER BY (e.atlas_sector = 'OTHER'), count(*) DESC
        """, (iso2.upper(),))
        return [{
            "atlasSector": r["code"], "name": r["name"] or r["code"],
            "companyCount": r["n"], "medianChangePct": None,
            "asOfTradeDate": None, "exposedCompanyCount": 0,
        } for r in c.fetchall()]

@app.get("/v1/countries/{iso2}/sectors/{sector}/companies")
def companies(iso2: str, sector: str, limit: int = Query(200, ge=1, le=1000)):
    with cur() as c:
        c.execute("""
            SELECT li.company_uid, e.common_name, e.legal_name, m.band,
                   count(d.id) AS edges
            FROM entity e
            JOIN entity_location l ON l.entity_id = e.id AND l.role = 'hq'
            JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
            LEFT JOIN entity_metric m ON m.entity_id = e.id AND m.metric = 'market_cap_usd'
            LEFT JOIN dependency_edge d ON d.from_entity_id = e.id
            WHERE l.country = %s AND e.atlas_sector = %s
            GROUP BY 1,2,3,4
            ORDER BY count(d.id) DESC, e.common_name
            LIMIT %s
        """, (iso2.upper(), sector, limit))
        return [{
            "companyUid": r["company_uid"], "commonName": r["common_name"],
            "legalName": r["legal_name"], "marketCapBand": r["band"] or "small",
            "marketCapUsd": None, "changePct": None,
            "citedEdgeCount": r["edges"], "moveContext": None,
        } for r in c.fetchall()]

@app.get("/v1/companies/{company_uid}")
def company(company_uid: str):
    with cur() as c:
        c.execute("""
            SELECT e.id, e.legal_name, e.common_name, e.country_hq, e.atlas_sector,
                   e.fiscal_year_end, e.status, e.website, e.ir_url,
                   l.city, ST_Y(l.geom::geometry) AS lat, ST_X(l.geom::geometry) AS lon,
                   m.band
            FROM entity_listing li
            JOIN entity e ON e.id = li.entity_id
            LEFT JOIN entity_location l ON l.entity_id = e.id AND l.role = 'hq'
            LEFT JOIN entity_metric m ON m.entity_id = e.id AND m.metric = 'market_cap_usd'
            WHERE li.company_uid = %s
        """, (company_uid,))
        r = c.fetchone()
        if not r:
            raise HTTPException(404, f"no company {company_uid[:64]}")
        # CUSIP (CUSIP Global Services) and SEDOL (LSEG) are licensed identifiers.
        # They may sit in our own store; they do not go out in a response.
        c.execute("""SELECT scheme, value FROM entity_identifier
                     WHERE entity_id=%s AND scheme NOT IN ('CUSIP','SEDOL')""", (r["id"],))
        ids = [{"scheme": x["scheme"], "value": x["value"]} for x in c.fetchall()]
        c.execute("""SELECT alias FROM entity_alias
                     WHERE entity_id=%s AND alias_type='former'""", (r["id"],))
        formers = [x["alias"] for x in c.fetchall()]
        c.execute("""SELECT exchange_mic, ticker, is_primary FROM entity_listing
                     WHERE entity_id=%s""", (r["id"],))
        listings = [{"exchangeMic": x["exchange_mic"], "ticker": x["ticker"],
                     "isPrimary": x["is_primary"]} for x in c.fetchall()]
        return {
            "companyUid": company_uid, "legalName": r["legal_name"],
            "commonName": r["common_name"], "formerNames": formers,
            "countryHq": r["country_hq"] or "US",
            "hq": {"lat": r["lat"], "lon": r["lon"], "city": r["city"]},
            "atlasSector": r["atlas_sector"], "marketCapBand": r["band"] or "small",
            "fiscalYearEnd": r["fiscal_year_end"] or "", "status": r["status"],
            "listings": listings, "identifiers": ids,
            "dependsOn": _depends(c, r["id"], "from"),
            "dependedOnBy": _depends(c, r["id"], "to"),
            "unnamedDependencies": [],
            "documentCount": _count(c, "SELECT count(*) FROM document WHERE entity_id=%s", r["id"]),
            "lastFiledAtUtc": _last_filed(c, r["id"]),
        }


def _count(c, sql, *args):
    c.execute(sql, args); return c.fetchone()["count"]


def _last_filed(c, eid):
    c.execute("SELECT max(filed_at_utc) AS m FROM document WHERE entity_id=%s", (eid,))
    m = c.fetchone()["m"]
    return m.isoformat() if m else None


def _depends(c, eid, side):
    """One row per relationship, not per sentence.

    A company that names Boeing in sixteen places has one dependency on Boeing
    cited sixteen times. Returning all sixteen would show the reader the same
    fact over and over and make a well-documented relationship look like many.
    We return the best-supported citation and say how many others agree."""
    col = "de.from_entity_id" if side == "from" else "de.to_entity_id"
    # Among equally confident claims, the shorter quote is the better citation: a
    # tight sentence states the relationship, a 2,000-character financial table
    # merely contains both names. Whichever we pick is what the user is shown.
    c.execute(EDGE_SQL + f" WHERE {col} = %s"
              " ORDER BY de.confidence DESC, length(dc.quote) ASC", (eid,))
    rows = c.fetchall()

    best, seen = [], {}
    for r in rows:
        key = (r["cp_uid"] or r["cp_name"], r["edge_type"])
        if key in seen:
            e = seen[key]
            e["corroboratingCitations"] += 1
            # a better-evidenced citation promotes the row: a figure beats a bare
            # mention, and a figure whose basis is stated beats a naked number
            better = (e["materialityPct"] is None and r["materiality_pct"] is not None) or \
                     (e["materialityBasis"] is None and r["materiality_text"] is not None
                      and r["materiality_pct"] == e["materialityPct"])
            if better:
                keep = e["corroboratingCitations"]
                e.clear(); e.update(_edge(r)); e["corroboratingCitations"] = keep
            continue
        e = _edge(r)
        e["corroboratingCitations"] = 1
        if side == "to":
            e["counterparty"] = {"companyUid": None, "name": r["filer_name"]}
        seen[key] = e
        best.append(e)
    return best[:12]

# ───────────────────────── evidence layer ─────────────────────────

def _citation(r):
    """Every assertion the API makes carries the sentence it came from."""
    return {
        "chunkId": str(r["chunk_id"]), "documentId": str(r["document_id"]),
        "quote": (r["quote"] or "").strip(),
        "charStart": r["char_start"], "charEnd": r["char_end"],
        "docType": r["doc_type"], "sectionLabel": r.get("section_label"),
        "filedAtUtc": r["filed_at_utc"].isoformat() if r["filed_at_utc"] else None,
        "periodEnd": r["period_end"].isoformat() if r.get("period_end") else None,
        "sourceUrl": r["primary_doc_url"], "filerName": r["filer_name"],
    }


EDGE_SQL = """
    SELECT de.id, de.from_entity_id, de.edge_type, de.evidence_type,
           de.confidence, de.weight,
           de.scorer_version, de.valid_from, de.valid_to,
           de.char_start, de.char_end, de.chunk_id,
           dc.quote, dc.substitutability, dc.materiality_pct, dc.materiality_text,
           d.id AS document_id, d.doc_type, d.filed_at_utc, d.period_end,
           d.primary_doc_url,
           fe.common_name AS filer_name,
           ce.common_name AS cp_name, cli.company_uid AS cp_uid,
           sec.title AS section_label
    FROM dependency_edge de
    JOIN dependency_claim dc ON dc.id = de.claim_id
    JOIN chunk ch   ON ch.id = de.chunk_id
    JOIN document d ON d.id = ch.document_id
    JOIN entity fe  ON fe.id = de.from_entity_id
    JOIN entity ce  ON ce.id = de.to_entity_id
    LEFT JOIN entity_listing cli ON cli.entity_id = ce.id AND cli.is_primary
    LEFT JOIN section sec ON sec.id = ch.section_id
"""


def _edge(r):
    return {
        "edgeId": str(r["id"]),
        "counterparty": {"companyUid": r["cp_uid"], "name": r["cp_name"]},
        "edgeType": r["edge_type"], "evidenceType": r["evidence_type"],
        "substitutability": r["substitutability"] or "unstated",
        "materialityPct": float(r["materiality_pct"]) if r["materiality_pct"] is not None else None,
        # what the percentage is a percentage OF. A bare "44%" is not a fact;
        # "44% of our consolidated net sales" is. Null means the filing stated a
        # figure we could not safely attribute, so we do not show one.
        "materialityBasis": r["materiality_text"],
        "confidence": float(r["confidence"]),
        "scorerVersion": r["scorer_version"],
        "validFrom": r["valid_from"].isoformat() if r["valid_from"] else None,
        "validTo": r["valid_to"].isoformat() if r["valid_to"] else None,
        "citation": _citation(r),
    }


@app.get("/v1/metrics")
def metrics():
    """What the team looks at weekly, and what the timeline draws its boundary from.

    The surprise rate is the product's reason to exist: the share of exposed
    companies that are more than one hop from the event, which is the share a
    user could not have listed themselves."""
    with cur() as c:
        c.execute("""SELECT count(*) AS edges,
                            count(*) FILTER (WHERE evidence_type='named_concentration')
                              AS concentration,
                            count(DISTINCT from_entity_id) AS companies
                     FROM dependency_edge""")
        g = c.fetchone()
        c.execute("""SELECT count(*) FROM (SELECT DISTINCT from_entity_id, to_entity_id,
                     edge_type FROM dependency_edge) t""")
        rels = c.fetchone()["count"]
        c.execute("""SELECT min(filed_at_utc) AS first, max(filed_at_utc) AS last,
                            count(*) AS n FROM document""")
        d = c.fetchone()
        c.execute("""SELECT count(*) AS total,
                            count(*) FILTER (WHERE is_surprising) AS surprising
                     FROM exposure_precompute""")
        e = c.fetchone()
        c.execute("SELECT count(*) AS n FROM event")
        events = c.fetchone()["n"]

    total = e["total"] or 0
    return {
        "graph": {"citedEdges": g["edges"], "relationships": rels,
                  "concentrationBacked": g["concentration"],
                  "companiesWithEdges": g["companies"]},
        "corpus": {"documents": d["n"],
                   # Before this date the graph is empty, and any event earlier
                   # than it must return nothing. The UI draws this.
                   "earliestFiling": d["first"].isoformat() if d["first"] else None,
                   "latestFiling": d["last"].isoformat() if d["last"] else None},
        "exposure": {"events": events, "rows": total, "surprising": e["surprising"] or 0,
                     "surpriseRate": round((e["surprising"] or 0) / total, 4) if total else 0.0},
        # Hand-judged, not computed. See eval/README.md.
        "measuredPrecision": {
            "concentrationTier": {"judged": 26, "correct": 26, "method": "exhaustive"},
            "narrativeTier": {"judged": 60, "correct": 41, "method": "seeded random sample"},
        },
    }


@app.get("/v1/events")
def events():
    with cur() as c:
        c.execute("""
            SELECT ev.id, ev.name, ev.event_type, ev.first_occurred_utc,
                   ev.became_public_utc, ev.confirmation_level, ev.severity,
                   ev.commodities, ev.chokepoints, ev.dedupe_key,
                   l.name AS place, l.country,
                   ST_Y(l.geom::geometry) AS lat, ST_X(l.geom::geometry) AS lon,
                   (SELECT count(*) FROM exposure_precompute ep WHERE ep.event_id = ev.id) AS exposed,
                   (SELECT count(*) FROM exposure_precompute ep
                     WHERE ep.event_id = ev.id AND ep.is_surprising) AS surprising
            FROM event ev
            LEFT JOIN event_location l ON l.event_id = ev.id
            ORDER BY ev.became_public_utc DESC
        """)
        return [{
            "eventId": str(r["id"]), "key": r["dedupe_key"], "name": r["name"],
            "eventType": r["event_type"],
            "firstOccurredUtc": r["first_occurred_utc"].isoformat() if r["first_occurred_utc"] else None,
            "becamePublicUtc": r["became_public_utc"].isoformat(),
            "confirmationLevel": r["confirmation_level"],
            "severity": float(r["severity"]) if r["severity"] is not None else None,
            "commodities": r["commodities"] or [], "chokepoints": r["chokepoints"] or [],
            "locations": ([{"name": r["place"], "lat": r["lat"], "lon": r["lon"],
                            "country": r["country"]}] if r["lat"] is not None else []),
            "totalExposed": r["exposed"], "surprisingCount": r["surprising"],
        } for r in c.fetchall()]


@app.get("/v1/events/{event_id}/exposure")
def exposure(event_id: str, limit: int = Query(40, ge=1, le=500)):
    with cur() as c:
        c.execute("""SELECT ev.id, ev.name, ev.event_type, ev.first_occurred_utc,
                            ev.became_public_utc, ev.confirmation_level,
                            ev.commodities, ev.chokepoints, ev.dedupe_key,
                            l.name AS place, l.country,
                            ST_Y(l.geom::geometry) AS lat, ST_X(l.geom::geometry) AS lon
                     FROM event ev LEFT JOIN event_location l ON l.event_id = ev.id
                     WHERE ev.id::text = %s OR ev.dedupe_key = %s""", (event_id, event_id))
        ev = c.fetchone()
        if not ev:
            raise HTTPException(404, f"no event {event_id[:64]}")

        c.execute("""
            SELECT ep.score, ep.hops, ep.is_surprising, ep.as_of, ep.scorer_version,
                   e.id AS entity_id, e.common_name, e.atlas_sector,
                   li.company_uid, l.country, m.band
            FROM exposure_precompute ep
            JOIN entity e ON e.id = ep.entity_id
            LEFT JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
            LEFT JOIN entity_location l ON l.entity_id = e.id AND l.role = 'hq'
            LEFT JOIN entity_metric m ON m.entity_id = e.id AND m.metric = 'market_cap_usd'
            WHERE ep.event_id = %s
            ORDER BY ep.is_surprising DESC, ep.score DESC
            LIMIT %s
        """, (ev["id"], limit))
        rows = c.fetchall()

        ids = [r["entity_id"] for r in rows]
        paths = {}
        if ids:
            # This ran the same query twice and threw the first result away, then
            # issued one more query per edge row to ask who owned it - a lookup
            # the row already carried. Forty exposed companies meant hundreds of
            # round trips, and the endpoint spent 600 ms under load. One query,
            # one pass.
            c.execute(EDGE_SQL + """ WHERE de.from_entity_id = ANY(%s)
                                     ORDER BY de.confidence DESC, length(dc.quote) ASC""",
                      (ids,))
            for er in c.fetchall():
                owner = er["from_entity_id"]
                bucket = paths.setdefault(owner, [])
                if len(bucket) < 3:
                    bucket.append(_edge(er))

        c.execute("SELECT count(*) FROM exposure_precompute WHERE event_id=%s", (ev["id"],))
        total = c.fetchone()["count"]
        c.execute("SELECT count(*) FROM exposure_precompute WHERE event_id=%s AND is_surprising",
                  (ev["id"],))
        surp = c.fetchone()["count"]

        return {
            "event": {
                "eventId": str(ev["id"]), "name": ev["name"], "eventType": ev["event_type"],
                "firstOccurredUtc": ev["first_occurred_utc"].isoformat() if ev["first_occurred_utc"] else None,
                "becamePublicUtc": ev["became_public_utc"].isoformat(),
                "confirmationLevel": ev["confirmation_level"],
                "locations": ([{"name": ev["place"], "lat": ev["lat"], "lon": ev["lon"],
                                "country": ev["country"]}] if ev["lat"] is not None else []),
                "chokepoints": ev["chokepoints"] or [], "commodities": ev["commodities"] or [],
                "sources": [],
            },
            "asOf": rows[0]["as_of"].isoformat() if rows else ev["became_public_utc"].isoformat(),
            "scorerVersion": rows[0]["scorer_version"] if rows else "walk-1.0",
            "totalExposed": total, "surprisingCount": surp,
            "rows": [{
                "companyUid": r["company_uid"], "commonName": r["common_name"],
                "countryHq": r["country"] or "", "atlasSector": r["atlas_sector"],
                "marketCapBand": r["band"] or "small",
                "score": float(r["score"]), "hops": r["hops"],
                "isSurprising": r["is_surprising"],
                "path": paths.get(r["entity_id"], []),
            } for r in rows],
        }
