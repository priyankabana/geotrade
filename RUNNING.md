# Running it — URLs, ports, credentials

Everything below runs on your own machine. The public frontend (static snapshot, no backend)
is at https://geotrade-priyanka.vercel.app; `make deploy` for the full stack is a
Phase 0 task that has not been done.

## Start everything

```bash
cd geotrade   # repo root

make db          # Postgres + PostGIS + Redis in Docker   (needs Docker Desktop open)
make db-ui       # database viewer -> http://localhost:8081
make migrate     # apply the schema (first time only)
make load        # load data/companies/*.csv into Postgres
make api         # read API   -> http://localhost:8000    (leave this terminal open)
make web         # frontend   -> http://localhost:5173    (new terminal)
```

`make dev` does db + migrate + load in one go. `make help` lists every target.

## The links

| What | URL | Notes |
|---|---|---|
| **Website** | **http://localhost:5173** | This is the one to show. Open it in Chrome. |
| API health | http://localhost:8000/v1/health | Should say `{"ok":true,"entities":23020}` |
| API docs (auto-generated) | http://localhost:8000/docs | FastAPI's interactive explorer — good for a viva |
| OpenAPI schema | http://localhost:8000/openapi.json | |
| **Database viewer** | **http://localhost:8081** | Browse tables and run SQL in a browser. No client needed. |
| Postgres (direct) | `postgresql://atlas:atlas@localhost:5432/atlas` | for TablePlus / DBeaver / pgAdmin |
| Redis | `redis://localhost:6379/0` | not used yet — Phase 3 |

Ports: **5173** web · **8000** API · **8081** db viewer · **5432** Postgres · **6379** Redis.

## Check everything is up

```bash
curl -s localhost:8000/v1/health                     # API + row count
curl -s localhost:5173 -o /dev/null -w '%{http_code}\n'   # web should print 200
docker compose -f infra/docker-compose.yml ps        # db + redis health
```

## Look inside the database

**`psql` is not installed on this Mac.** Any command that starts with `psql …` will say
"command not found". That is not a database problem — the database is running fine. Use
one of these instead.

### Easiest: the browser

```bash
make db-ui          # starts the viewer and opens it
```
→ **http://localhost:8081**

Click a table on the left to browse its rows. The **Query** tab runs SQL. Results export
as CSV, JSON or XML. Nothing to install — it runs in Docker alongside Postgres.

### One-off queries from the terminal

```bash
make query Q="select count(*) from entity"
make query Q="select atlas_sector, count(*) from entity group by 1 order by 2 desc limit 10"
```

### A full SQL shell

```bash
make psql           # drops you into psql inside the container
```

Then `\dt` lists tables, `\d entity` describes one, `\q` quits.

### If you want `psql` on the Mac itself

```bash
brew install libpq
echo 'export PATH="/opt/homebrew/opt/libpq/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
psql postgresql://atlas:atlas@localhost:5432/atlas
```

### A desktop GUI

TablePlus, DBeaver or pgAdmin all work. Connection details:

| field | value |
|---|---|
| host | `localhost` |
| port | `5432` |
| database | `atlas` |
| user | `atlas` |
| password | `atlas` |
| SSL | off / disable |

Ready-made queries live in [docs/queries.sql](docs/queries.sql) — country counts, the
country → sector → company drill-down, and the gazetteer. Paste any of them into psql or
into the Query tab at http://localhost:8081.

### Queries worth running

```sql
\dt                                    -- all 26 tables
\d dependency_edge                     -- inspect one

SELECT l.country, count(*) FROM entity_location l GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
SELECT atlas_sector, count(*) FROM entity GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
SELECT count(*) FROM entity_alias WHERE NOT is_ambiguous;   -- the gazetteer

-- the point-in-time read path (empty until extraction runs)
SELECT count(*) FROM edges_as_of(ARRAY[]::uuid[], now());
```

### If it really is down

```bash
docker info                                      # is Docker Desktop running?
docker compose -f infra/docker-compose.yml ps    # should say "healthy"
make db                                          # start it
```

## Where things live on disk

```
geotrade/
    ├── data/companies/*.csv       sample.csv in git; full universe built locally (see README)
    ├── data/aliases/*.csv         name variants (sample.csv in git)
    ├── data/reference/            sectors, gazetteer
    ├── infra/migrations/          the schema
    ├── apps/api/main.py           the read API
    ├── apps/web/                  the frontend
    ├── scripts/                   normalise · load · validate · measure · narrate · record
    └── docs/                      every decision, written down
```

## Showing it to someone

1. `make db && make api` in one terminal, `make web` in another.
2. Open **http://localhost:5173** in Chrome. Full screen it.
3. Drag the globe. Pick a country. Pick a sector. Click a company. Then hit **Replay**.
4. If anything breaks, fall back to the recorded walkthrough video (not stored in git).

**Over a network** (showing it on someone else's laptop on the same wifi):

```bash
cd apps/web && npm run dev -- --host     # prints a Network: http://192.168.x.x:5173 URL
# the API must also listen outside localhost:
cd apps/api && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```
Then set `VITE_API_URL=http://192.168.x.x:8000` before starting the web dev server, or
the browser on the other machine will still look for the API on its own localhost.

## Stop everything

```bash
make down                    # stops Postgres + Redis
pkill -f "uvicorn main:app"  # stops the API
pkill -f "vite"              # stops the frontend
```

## Not yet true

There is no public URL, no login, and no deployment. The stack is designed for Vercel
(web) · Fly.io (API) · Neon (Postgres), all on free tiers, and that is a Phase 0 item
still open — see `docs/ROADMAP.md`. Until then "live" means localhost on your machine.
