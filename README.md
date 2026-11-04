# GeoTrade

> Location-based market analysis: a 3D globe of ~23k listed companies across six markets, built as the reference layer for tracing **who is exposed when something happens in the world** — with every dependency claim tied to the exact sentence in a public filing.

Final-year B.Tech (Computer Engineering) **team project** — *GeoTrade: Location-Based Market Analysis and Trade Optimization System*. Internal codename in the code and docs: **Atlas**.

> **Not a trading product.** It shows exposure and evidence; it never says what to buy or sell. See [COMPLIANCE.md](COMPLIANCE.md).

**Live demo:** https://geotrade-priyanka.vercel.app (static build, no backend; see [Deployment](#deployment))
**Repo:** https://github.com/priyankabana/geotrade

![Globe view](docs/screenshots/globe.jpg)

## Why

When something happens in the world (a port closes, a factory burns down, a country
restricts an export), some companies are obviously affected and everyone already knows
who they are. The companies affected next, because they quietly buy from the ones that
were hit, are much harder to find.

GeoTrade is our attempt to build that list. Listed companies have to disclose certain
things, and buried in those filings are sentences like *"two customers accounted for 41%
of our revenue."* The plan is to read those filings, work out who depends on whom, draw it
on a globe, and attach the exact sentence that proves every connection. **If we cannot show
the sentence, we do not make the claim.**

## What we built so far

Phase 0 is the reference layer: a clean, geolocated universe of listed companies that the
extraction phase will resolve company names against. All numbers below were measured on
the real (local) database, not estimated.

| | Number | Where it comes from |
|---|---|---|
| Raw input rows | **29,442** | seven market files (US NYSE, US Nasdaq, India, UK, Germany, Canada, Australia) |
| Companies after cleaning | **23,020** | one node per company, `SELECT count(*) FROM entity` |
| Cross-listing duplicates collapsed | **6,059** | same security on several exchanges, merged by ISIN, giving 23,383 securities |
| Share classes collapsed | **363** | several share classes of one issuer, merged by LEI, giving 23,020 companies |
| Geolocated HQs | **23,018** | 65% to city precision, 35% to country centroid, 2 not at all |
| HQ countries | **90** | country derived from the address text, not the listing market |
| Name aliases | **82,756** generated, **82,751** loaded | legal, common, former and short forms |
| Usable gazetteer aliases | **59,567** | aliases left after suppressing ambiguous ones like "Apple" or "Target" |
| Sectors | **34** | our own supply-chain shaped taxonomy |
| Schema | **25 tables** | PostGIS, row-level security on 3 tenant tables, 17 indexes |
| Dependency edges | **0** | extraction is the next phase; the UI says so instead of faking it |

API latency against the local Postgres + PostGIS database (200 sequential requests per
endpoint, 20 for the full point dump; measured 2026-11-04):

| Endpoint | p50 | p95 |
|---|---|---|
| `GET /v1/health` | 2.6 ms | 3.2 ms |
| `GET /v1/countries/US/sectors` | 17 ms | 23 ms |
| `GET /v1/countries/US/sectors/SEMI_EQUIP/companies` | 20 ms | 29 ms |
| `GET /v1/companies/XNAS:AMAT` | 14 ms | 23 ms |
| `GET /v1/globe/countries` | 53 ms | 57 ms |
| `GET /v1/globe/points?limit=30000` | 376 ms | 526 ms |

Every drill-down endpoint is well inside our 200 ms read budget. The full point dump is
not, which is one reason the static demo ships the globe as pre-aggregated counts.

![Drill-down: country to sector to company](docs/screenshots/drilldown.jpg)

## Status (honest)

| Area | State |
| --- | --- |
| Reference layer | Built. Locally loaded with 23,020 companies across 90 HQ countries (aliases, sectors, geocoded HQs). This repo ships a **41-company sample**; the public demo ships aggregates plus a 300-company named sample. See [Data](#data). |
| Schema | Built. 25 PostgreSQL/PostGIS tables + `edges_as_of()` point-in-time read function. Citation enforced in schema (`dependency_edge.chunk_id NOT NULL`). |
| Read API | Built. FastAPI endpoints for globe points, country → sector → company drill-down, company detail. |
| Frontend | Built. 3D globe (night earth, density bins, propagation arcs), Live / Replay / Simulate modes, drill-down panels, citation component, static-snapshot fallback. |
| Dependency extraction (filings → edges) | **Not built yet.** There are zero real dependency edges; Replay/Simulate use a clearly-labelled **illustrative worked example** with real companies but placeholder quotes. |

## Data cleaning

`scripts/normalise_vendor_csv.py` turns the raw market files into the collection format the
loader expects. The problems it fixes are the reason it exists:

- **Cross-listings.** Apple appears as a Frankfurt line. Without merging, one company
  becomes several graph nodes and the graph silently splits. Rows are collapsed by ISIN
  (6,059 duplicates) with the home-market listing kept as primary, then share classes of
  the same issuer are merged by LEI (363 more). Malformed ISINs are blanked first so they
  cannot group unrelated companies.
- **Country means market, not company.** Every German row said "Germany", including
  Canadian and Japanese companies listed in Frankfurt. Country is derived from the
  address text, then the ISIN prefix, then the geocoded city.
- **Typos and codes.** Country spellings like "Unitedkingdom" are normalised; vendor
  exchange codes are mapped to ISO 10383 MICs.
- **Geocoding.** Cities are matched against GeoNames, scoped to the country so Springfield
  lands in the right one. Precision is stored per row (`city` or `country`).
- **Licensed columns.** SEDOL and CUSIP are dropped at the normaliser boundary. Vendor
  classification codes are not stored; our sector is derived from plain-English text.
- **Market cap is left empty** where the source gives local currency only and we have no
  FX source with a verified licence. A converted number would be invented.

## Features

- **3D globe** (`react-globe.gl` / three.js) of geolocated company HQs, with country density bins and arcs.
- **Drill-down:** country → sector → company, served by the read API.
- **Live / Replay / Simulate** modes; Replay steps through a timeline reading the graph "as it stood" at each date.
- **Citation component:** every edge renders its filer, document type, section, filing date and source URL.
- **Static snapshot fallback:** if the API cannot be reached, the frontend reads `apps/web/public/snapshot/` instead, so the deployed demo shows real coverage (23,018 companies in 90 countries as counts, 300 named companies) with no backend.
- **Data pipeline scripts:** build a US universe from SEC EDGAR, normalise multi-market CSVs (cross-listing dedupe, ISO MIC mapping, country repair, GeoNames geocoding), validate collection CSVs, load into Postgres idempotently, and measure extraction cost against real filings.
- **Licensing discipline:** licensed identifiers (SEDOL, CUSIP) and vendor classification codes are dropped at the normaliser boundary.

## Architecture

```mermaid
flowchart LR
    subgraph Sources
      SEC[SEC EDGAR<br/>tickers + submissions]
      GEO[GeoNames / US-Cities<br/>geocoding]
      CSV[market CSVs<br/>(not in repo)]
    end
    SEC --> B[scripts/build_us_universe.py]
    CSV --> N[scripts/normalise_vendor_csv.py]
    GEO --> B
    GEO --> N
    B --> D[(data/companies<br/>data/aliases)]
    N --> D
    D --> V[scripts/validate_collection.py]
    V --> L[scripts/load_csv.py]
    L --> PG[(PostgreSQL 16 + PostGIS<br/>25 tables, edges_as_of)]
    PG --> API[FastAPI read API<br/>apps/api]
    API --> WEB[React + TS + Vite<br/>3D globe · apps/web]
    API --> BS[scripts/build_snapshot.py]
    BS --> SNAP[static snapshot<br/>apps/web/public/snapshot]
    WEB -. API down .-> SNAP
```

Planned (see [docs/ROADMAP.md](docs/ROADMAP.md)): filing ingestion → chunking → gazetteer match → LLM extraction of dependency claims → cited `dependency_edge` rows → exposure propagation. The LLM extracts and explains; it never produces a score.

## Tech stack

| Layer | Tech |
| --- | --- |
| Frontend | React 18, TypeScript 5, Vite 5, react-globe.gl, three.js, d3-geo, topojson |
| API | Python, FastAPI, Uvicorn, psycopg 3 |
| Database | PostgreSQL 16 + PostGIS 3.4 (Docker), Redis (provisioned, not used yet) |
| Tooling | Docker Compose, Make, GitHub Actions, pgweb |

## Quick start

Prerequisites: Docker Desktop, Python 3.11+, Node 20+.

```bash
git clone https://github.com/priyankabana/geotrade.git
cd geotrade
cp .env.example .env

python3 -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt          # fastapi, uvicorn, psycopg

make db         # Postgres + PostGIS + Redis in Docker
make migrate    # apply infra/migrations/0001_initial_schema.sql
make load       # load data/companies/*.csv + data/aliases/*.csv (41-company sample)
make api        # http://localhost:8000  (docs at /docs, health at /v1/health)

# in a second terminal
cd apps/web && npm ci && npm run dev    # http://localhost:5173
```

Frontend only (no database): `cd apps/web && npm ci && npm run dev` — the API probe fails and the app runs on the static snapshot (header shows `static demo`).

`make help` lists every target; [RUNNING.md](RUNNING.md) has ports, the browser DB viewer (`make db-ui`) and troubleshooting.

## Data

Only small, redistributable data is committed:

| Path | What |
| --- | --- |
| `data/companies/sample.csv`, `data/aliases/sample.csv` | 41 companies / 136 aliases across 6 markets (names, tickers, MIC, ISIN/LEI, city, lat/lon). Descriptions, market caps and vendor codes removed. |
| `data/reference/us_filer_gazetteer.csv`, `sectors.csv` | Derived from SEC EDGAR (public domain). |
| `data/templates/*.csv` | Empty collection templates (column contracts). |
| `apps/web/public/snapshot/` | Public demo snapshot: per-country and per-sector **counts** for all 23,020 companies, plus 300 named companies (name, ticker, CIK, country, city, lat/lon, sector). Rebuild with `python3 -I scripts/build_snapshot.py --api http://localhost:8000`. Policy: [docs/sources.md](docs/sources.md), "Public demo snapshot". |

To build a full dataset:

```bash
# US universe from SEC EDGAR only (public domain). Needs a real contact email.
export ATLAS_UA="Your Name your.email@example.com"
ATLAS_TOP_N=2000 python3 -I scripts/build_us_universe.py      # writes data/companies/us.csv, data/aliases/us.csv
make validate && make load
```

The team's multi-market CSVs (India/UK/Germany/Canada/Australia) came from a supplied market dataset whose redistribution terms are **not cleared**, so neither the raw files nor their normalised output are published. If you have your own market CSVs in the same layout: `python3 -I scripts/normalise_vendor_csv.py <dir>` (set `ATLAS_GEONAMES` to a GeoNames `cities1000.txt` path).

## Environment variables

| Variable | Used by | Example | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | API, `load_csv.py` | `postgresql://atlas:atlas@localhost:5432/atlas` | Local default matches docker-compose |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | docker-compose | `atlas` / `…` / `atlas` | Local-dev defaults; override for anything shared |
| `CORS_ORIGINS` | API | `http://localhost:5173` | Comma-separated allowed frontend origins |
| `ATLAS_PRODUCT_NAME` | API | `GeoTrade` | Shown in health + OpenAPI title |
| `VITE_API_URL` | Web (build time) | `http://localhost:8000` | Where the browser finds the API |
| `VITE_PRODUCT_NAME` | Web (build time) | `GeoTrade` | Product name in the UI |
| `ATLAS_UA` | SEC scripts | `Name email@example.com` | SEC requires a real contact User-Agent |
| `ATLAS_TOP_N`, `ATLAS_TMP`, `ATLAS_GEONAMES` | data scripts | `2000`, `/tmp`, path | Optional |
| `REDIS_URL` | — | `redis://localhost:6379/0` | Reserved; not used yet |

Note: the Makefile does not auto-load `.env`; the defaults above work for local dev, or `set -a; source .env; set +a` first.

## Project structure

```
apps/
  api/main.py              FastAPI read API (globe, drill-down, company detail)
  web/                     React + TS + Vite frontend (globe, panels, timeline, citation; public/snapshot = static demo data)
packages/shared/src/api.ts Shared API types (imported as @shared/*)
infra/
  docker-compose.yml       Postgres+PostGIS, Redis, pgweb
  migrations/              0001_initial_schema.sql (25 tables, edges_as_of)
scripts/                   build_us_universe · normalise_vendor_csv · validate_collection · load_csv · build_snapshot
                           measure_corpus · repair_geocode · narrate · record_demo
data/                      sample + reference CSVs, collection templates
docs/                      problem statement, architecture, data model, sources, roadmap, cost, ADRs
demo/                      demo GIF, poster, presentation page
COMPLIANCE.md · SUPERSEDED.md · LEARN/glossary.md · TEAM/demo-script.md
```

## Testing

```bash
cd apps/web && npm run typecheck && npm run build       # passes
python3 -I scripts/validate_collection.py data/companies/*.csv data/aliases/*.csv
python3 -m compileall -q apps/api scripts
```

There is no automated unit-test suite yet (planned with the extraction phase). CI (`.github/workflows/ci.yml`) runs the checks above.

## Deployment

**Frontend → Vercel** (live at https://geotrade-priyanka.vercel.app). The root
[`vercel.json`](vercel.json) installs and builds `apps/web` and serves `apps/web/dist`.
Leave `VITE_API_URL` unset: the app probes `http://localhost:8000`, fails, and serves the
static snapshot, so no backend or environment variables are needed.

Full stack (optional, free tier):

- **API → Render / Railway / Fly.io**: root `apps/api`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`, env `DATABASE_URL`, `CORS_ORIGINS=https://geotrade-priyanka.vercel.app`. Then set `VITE_API_URL` on Vercel and redeploy.
- **Database → Neon / Supabase / Railway Postgres** with **PostGIS** enabled; run `infra/migrations/0001_initial_schema.sql`, then `DATABASE_URL=... python3 -I scripts/load_csv.py`.

## Team

GeoTrade is a final-year B.Tech team project. Contributors: **Priyanka Bana** and
**Krish Oswal**. How the team split ownership areas is described in [docs/TEAM.md](docs/TEAM.md).

**My contributions** _(TODO — Priyanka to fill in)_:

- [ ] TODO: area I owned (e.g. API / schema / frontend / data pipeline)
- [ ] TODO: specific feature(s) I designed and implemented
- [ ] TODO: data / infra work (scripts, migrations, CI)
- [ ] TODO: docs / demo / presentation work

## What I learned

- Modelling a point-in-time graph in PostgreSQL (`edges_as_of`) so history is never read with information from the future.
- Using PostGIS geography types for geolocated entities and serving them to a WebGL globe.
- Entity resolution in practice: cross-listing dedupe by ISIN, exchange-code → ISO MIC mapping, alias gazetteers and ambiguity suppression.
- Data licensing as an engineering constraint: tracking provenance per row and refusing data whose redistribution terms are unclear.
- Designing a frontend that degrades honestly (offline mode, labelled illustrative data) instead of faking results.
- Working in a 5-person team with ownership areas, PR reviews and CI.

## Attribution

Contains data from [GeoNames](https://www.geonames.org/), CC BY 4.0. Globe textures from [three-globe](https://github.com/vasturiano/three-globe) (MIT); imagery NASA Visible Earth (public domain) — see [apps/web/public/textures/SOURCE.md](apps/web/public/textures/SOURCE.md). Company identity from [SEC EDGAR](https://www.sec.gov/edgar), public domain. US city coordinates from [US-Cities-Database](https://github.com/kelvins/US-Cities-Database), MIT.

## License

MIT © 2026 Priyanka Bana — see [LICENSE](LICENSE).
