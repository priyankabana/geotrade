# Runbook

For whoever is holding it when something breaks, including you in six months
when you have forgotten all of this.

Every command here is real. If one of them does not work, that is a bug in this
document and it should be fixed in the same pull request that discovers it.

---

## Nothing works this morning

Almost always: the machine restarted and Docker is not running, so the database
is down and the two servers died with it. One command brings all three back and
tells you what it found:

```bash
make up
```

It starts Docker Desktop if it has to, waits for Postgres to accept
connections, restarts the API and the web server detached, and prints their
status. It takes a few seconds. Nothing is rebuilt and no data is touched.

If the test suite was failing before you ran it, that was the same cause: 151
of the 294 tests need a database or a running server and skip themselves
without one. **A skipped test is not a failing test.** If you see failures
rather than skips, something is genuinely wrong.

## Bring the whole thing up from nothing

```bash
make dev        # Postgres + PostGIS + Redis, migrations, reference data
make api        # read API on :8000
make web        # frontend on :5173
```

Check it is actually alive, not merely running:

```bash
curl -s localhost:8000/v1/health
make eval       # what is in the graph right now
make alerts     # the three things that would page someone
```

Rebuild the evidence layer end to end:

```bash
make pipeline   # link-cik -> ingest -> gazetteer-df -> extract -> propagate
make backtest   # replay the event benchmark, fail on regression
```

---

## The three alerts

`make alerts` exits with the number of firing alerts, so it can run on a timer.

### 1. `ingest_stopped`

**What it means.** No document has been retrieved in more than 14 days. The
graph is going stale and nothing about the UI says so.

**Why it pages someone.** A stale graph looks identical to a current one. The
user sees the same confident citations and does not know the last filing we read
is from last quarter.

**What to do.**
```bash
make ingest                     # does it still work at all?
curl -s -H "User-Agent: $ATLAS_UA" https://data.sec.gov/submissions/CIK0000320193.json | head -c 200
```
If EDGAR returns 403, our User-Agent is wrong or we have been rate limited: we
hold ourselves to 8 requests a second and SEC expects a contactable UA. If it
returns HTML where JSON should be, the format changed and `scripts/ingest.py`
needs its segmentation updated. That breaks loudly, which is the intended
design.

### 2. `precision_dropped`

**What it means.** One of: an edge exists with no citation; the share of
concentration-backed edges has fallen below 8%; or a claim asserts a share above
100%.

**Why it pages someone.** This is the product lying. An uncited edge breaks the
only promise we make. A collapse in the concentration share means the graph is
drifting toward the evidence tier that measured 68% rather than the one that
measured 100%.

**What to do.**
```bash
make audit                      # dump the concentration tier and read it
make sample                     # draw a fresh sample and judge 20 by hand
python3 -I -m pytest -q tests/test_extract.py
```
If the extractor changed, the 30 regression tests say which rule broke. If they
all pass and precision still looks wrong, the corpus has changed shape and the
honest response is to re-measure and publish the new number, not to adjust the
threshold.

### 3. `read_path_over_budget`

**What it means.** An endpoint took longer than 200 ms.

**Why it pages someone.** It is the budget we publish, and the demo is run in
front of people.

**What to do.** Exposure is precomputed; if a read is slow, something is
computing at request time.
```bash
grep '"event": "request"' /tmp/atlas_api.log | tail -40   # which path, how slow
make query Q="select count(*) from exposure_precompute"   # is it populated at all?
make propagate                                            # repopulate if empty
```
An empty `exposure_precompute` is the usual cause: the API falls back to
returning nothing slowly rather than something fast.

---

## Common failures

**`make api` starts but every query returns nothing.**
The API connects as `atlas_app`, which is subject to row-level security. If the
tenant is not set, the correct behaviour is to return zero rows. Check a key
resolves to a tenant:
```bash
make keys
curl -s -H "X-API-Key: $KEY" localhost:8000/v1/health
```

**Tenancy tests skip instead of running.**
The `atlas_app` role does not exist. Apply the migrations:
```bash
make migrate          # applies everything that has not run yet
make migrate-status   # shows what has and has not
```
A database built before the migration runner existed has an empty ledger, so
`make migrate` will try to re-run 0001 and fail on the first `CREATE TABLE`.
Adopt it instead, which records the files without executing any of them:
```bash
python3 -I scripts/migrate.py --baseline
```

**`make extract` produces far fewer edges than expected.**
Run `make gazetteer-df` first. Extraction matches against aliases the corpus has
shown to be specific rather than generic, and that filter has to be rebuilt after
loading a new market.

**The globe is blank but the API is healthy.**
A three.js version mismatch. `react-globe.gl` needs three >= 0.179; this project
pins `three@0.180.0`. Check `apps/web/package.json` before debugging anything
else.

**Playwright or the demo recording fails.**
Both the API and the web server must already be running. `make demo` drives a
real browser against a real database; it does not start them for you.

---

## Routine work

| Cadence | Command | Why |
|---|---|---|
| On every change | `make test` | 294 tests: extraction, ingestion, API, data integrity, migrations, point-in-time, propagation, tenancy, browser end-to-end |
| On every change to extraction | `make backtest` | reach and surprise must not regress silently |
| Weekly | `make alerts` | the three above |
| Weekly | `make eval` | the graph's size, in public |
| After ingesting a market | `make gazetteer-df && make extract` | the alias filter is corpus-dependent |
| Before a review | `make audit` and read ten | no number goes into a slide unread |

---

## Keys and tenants

```bash
make key NAME="Anushka laptop"     # shown once, stored only as a SHA-256
make keys                          # list, with last-used dates
python3 -I scripts/api_key.py revoke <id>
```

Set `ATLAS_REQUIRE_KEY=1` to close the public endpoints. Health stays open so
the alerts can reach it.

---

## What to say if it breaks during a demo

Say what broke and move to the part that works. The database, the API and the
globe fail independently; `make eval` and `make audit` need neither the API nor
the browser, and reading a real cited sentence out of `eval/concentration_all.txt`
makes the point without any of it running.
