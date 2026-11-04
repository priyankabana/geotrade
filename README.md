# GeoTrade

> Location-based market analysis: a 3D globe of ~23k listed companies across six markets, built as the reference layer for tracing **who is exposed when something happens in the world** — with every dependency claim tied to the exact sentence in a public filing.

Final-year B.Tech (Computer Engineering) **team project** — *GeoTrade: Location-Based Market Analysis and Trade Optimization System*. Internal codename in the code and docs: **Atlas**.

> **Not a trading product.** It shows exposure and evidence; it never says what to buy or sell. See [COMPLIANCE.md](COMPLIANCE.md).

## Screenshots

![Demo](demo/atlas-demo.gif)

> _TODO: add `docs/screenshots/globe.png`, `docs/screenshots/drilldown.png`, `docs/screenshots/replay.png`._

## Why

When a port closes or a factory burns down, the directly hit companies are obvious. The companies affected *next* — because they quietly depend on the ones that were hit — are hard to find. Public filings contain sentences like *"two customers accounted for 41% of our revenue."* GeoTrade's goal is to read those filings, build the dependency graph, put it on a map, and cite the source sentence for every edge. **If it can't show the sentence, it doesn't make the claim.**

## Status (honest)

| Area | State |
| --- | --- |
| Reference layer | Built. Locally loaded with ~23k companies across US, India, UK, Germany, Canada, Australia (aliases, sectors, geocoded HQs). This repo ships a **41-company sample**; see [Data](#data). |
| Schema | Built. 25 PostgreSQL/PostGIS tables + `edges_as_of()` point-in-time read function. Citation enforced in schema (`dependency_edge.chunk_id NOT NULL`). |
| Read API | Built. FastAPI endpoints for globe points, country → sector → company drill-down, company detail. |
| Frontend | Built. 3D globe (night earth, density bins, propagation arcs), Live / Replay / Simulate modes, drill-down panels, citation component. |
| Dependency extraction (filings → edges) | **Not built yet.** There are zero real dependency edges; Replay/Simulate use a clearly-labelled **illustrative worked example** with real companies but placeholder quotes. |

## Features

- **3D globe** (`react-globe.gl` / three.js) of geolocated company HQs, with country density bins and arcs.
- **Drill-down:** country → sector → company, served by the read API.
- **Live / Replay / Simulate** modes; Replay steps through a timeline reading the graph "as it stood" at each date.
- **Citation component:** every edge renders its filer, document type, section, filing date and source URL.
- **Offline mode:** the frontend detects when the API is down, shows "API offline" and falls back to the bundled worked example.
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
    WEB -. API down .-> EX[bundled worked example]
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

Frontend only (no database): `cd apps/web && npm ci && npm run dev` — it runs in offline mode with the worked example.

`make help` lists every target; [RUNNING.md](RUNNING.md) has ports, the browser DB viewer (`make db-ui`) and troubleshooting.

## Data

Only small, redistributable data is committed:

| Path | What |
| --- | --- |
| `data/companies/sample.csv`, `data/aliases/sample.csv` | 41 companies / 136 aliases across 6 markets (names, tickers, MIC, ISIN/LEI, city, lat/lon). Descriptions, market caps and vendor codes removed. |
| `data/reference/us_filer_gazetteer.csv`, `sectors.csv` | Derived from SEC EDGAR (public domain). |
| `data/templates/*.csv` | Empty collection templates (column contracts). |

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
  web/                     React + TS + Vite frontend (globe, panels, timeline, citation)
packages/shared/src/api.ts Shared API types (imported as @shared/*)
infra/
  docker-compose.yml       Postgres+PostGIS, Redis, pgweb
  migrations/              0001_initial_schema.sql (25 tables, edges_as_of)
scripts/                   build_us_universe · normalise_vendor_csv · validate_collection · load_csv
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

## Deployment notes

Not deployed yet. Intended free-tier setup:

- **Frontend → Vercel** (or Netlify): root `apps/web`, build `npm run build`, output `dist`, env `VITE_API_URL=https://<api-host>`. Without an API it still works in offline/worked-example mode.
- **API → Render / Railway / Fly.io**: root `apps/api`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`, env `DATABASE_URL`, `CORS_ORIGINS=https://<your-vercel-domain>`.
- **Database → Neon / Supabase / Railway Postgres** with the **PostGIS** extension enabled; run `infra/migrations/0001_initial_schema.sql`, then `DATABASE_URL=... python3 -I scripts/load_csv.py`.

## Team project & my contributions

This was built by a team of five final-year students. Ownership areas are described in [docs/TEAM.md](docs/TEAM.md).

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

Contains data from [GeoNames](https://www.geonames.org/), CC BY 4.0. Globe textures from [three-globe](https://github.com/vasturiano/three-globe) (MIT); imagery NASA Visible Earth (public domain) — see [apps/web/public/textures/SOURCE.md](apps/web/public/textures/SOURCE.md). Company reference data from [SEC EDGAR](https://www.sec.gov/edgar), public domain. US city coordinates from [US-Cities-Database](https://github.com/kelvins/US-Cities-Database), MIT.

## License

MIT © 2026 Priyanka Bana — see [LICENSE](LICENSE).
