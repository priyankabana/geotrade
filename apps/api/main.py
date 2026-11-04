"""Atlas read API. Serves the contract in packages/shared/src/api.ts from Postgres.

Read path budget is p95 < 200ms. Nothing here computes exposure - that is precomputed
by the propagation engine. These endpoints are the reference layer only; the evidence
layer endpoints arrive with Phase 2.
"""
import os
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
PRODUCT_NAME = os.environ.get("ATLAS_PRODUCT_NAME", "Atlas")

app = FastAPI(title=f"{PRODUCT_NAME} API", version="0.1.0")
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=["GET"], allow_headers=["*"])

_pool: psycopg.Connection | None = None

@contextmanager
def cur():
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg.connect(DSN, row_factory=dict_row, autocommit=True)
    with _pool.cursor() as c:
        yield c

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
        return {"ok": True, "entities": c.fetchone()["n"], "product": PRODUCT_NAME}

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
def globe_points(limit: int = 4000):
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
def companies(iso2: str, sector: str, limit: int = 200):
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
            raise HTTPException(404, f"no company {company_uid}")
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
            # Empty until extraction runs. An empty list is the honest answer; the UI
            # says "no edges cited" rather than implying the company has no dependencies.
            "dependsOn": [], "dependedOnBy": [], "unnamedDependencies": [],
            "documentCount": 0, "lastFiledAtUtc": None,
        }
