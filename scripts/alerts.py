#!/usr/bin/env python3
"""The three alerts that would wake somebody up, as a check you can actually run.

The roadmap names three. They are the three because each one means the product
is lying to a user rather than merely being unavailable:

  1. ingest stopped      - the graph is silently going stale
  2. precision dropped   - we are serving edges we would not stand behind
  3. read path over budget - the demo and the API are failing in front of people

Exit status is the number of firing alerts, so cron or CI can act on it.

    python3 -I scripts/alerts.py
    python3 -I scripts/alerts.py --json
"""
import os, sys, json, time, datetime, urllib.request
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
API = os.environ.get("ATLAS_API", "http://localhost:8000")

INGEST_STALE_DAYS = int(os.environ.get("ATLAS_INGEST_STALE_DAYS", 14))
READ_BUDGET_MS    = int(os.environ.get("ATLAS_READ_BUDGET_MS", 200))
MIN_CONC_SHARE    = float(os.environ.get("ATLAS_MIN_CONC_SHARE", 0.08))


def ingest_stopped(cur):
    """A corpus that stops growing looks exactly like one that is up to date."""
    cur.execute("SELECT max(retrieved_at_utc) FROM document")
    last = cur.fetchone()[0]
    if last is None:
        return True, "no documents have ever been ingested"
    age = (datetime.datetime.now(datetime.timezone.utc) - last).days
    return age > INGEST_STALE_DAYS, f"last document retrieved {age} days ago"


def precision_dropped(cur):
    """We cannot re-judge the graph by hand on a cron, so we watch the two
    proxies that moved first every time precision moved in the audit: the share
    of edges that are concentration-backed, and whether anything uncited or
    unattributed has appeared."""
    cur.execute("SELECT count(*) FROM dependency_edge WHERE chunk_id IS NULL")
    uncited = cur.fetchone()[0]
    if uncited:
        return True, f"{uncited} edges carry no citation - the core guarantee is broken"

    cur.execute("""SELECT count(*) FILTER (WHERE evidence_type='named_concentration'),
                          count(*) FROM dependency_edge""")
    conc, total = cur.fetchone()
    if total == 0:
        return True, "the graph is empty"
    share = conc / total
    if share < MIN_CONC_SHARE:
        return True, (f"only {share:.1%} of edges are concentration-backed "
                      f"(floor {MIN_CONC_SHARE:.0%}); the graph is drifting toward "
                      f"the weaker evidence tier")

    cur.execute("""SELECT count(*) FROM dependency_claim
                   WHERE materiality_pct IS NOT NULL AND materiality_pct > 100""")
    impossible = cur.fetchone()[0]
    if impossible:
        return True, f"{impossible} claims assert a share above 100%"

    return False, f"{share:.1%} of edges concentration-backed, every edge cited"


def read_path_slow():
    """The 200 ms budget is a promise. Measure it, do not assume it."""
    worst, path = 0.0, None
    for p in ("/v1/health", "/v1/globe/countries", "/v1/events"):
        try:
            t0 = time.monotonic()
            with urllib.request.urlopen(f"{API}{p}", timeout=10) as r:
                r.read()
            ms = (time.monotonic() - t0) * 1000
        except Exception as exc:
            return True, f"{p} did not respond: {exc}"
        if ms > worst:
            worst, path = ms, p
    return worst > READ_BUDGET_MS, f"slowest endpoint {path} at {worst:.0f} ms"


def main():
    results = []
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        for name, fn in (("ingest_stopped", lambda: ingest_stopped(cur)),
                         ("precision_dropped", lambda: precision_dropped(cur)),
                         ("read_path_over_budget", read_path_slow)):
            try:
                firing, detail = fn()
            except Exception as exc:
                firing, detail = True, f"check itself failed: {exc}"
            results.append(dict(alert=name, firing=firing, detail=detail))

    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"  {'FIRING ' if r['firing'] else 'ok     '} "
                  f"{r['alert']:<24} {r['detail']}")
    sys.exit(sum(1 for r in results if r["firing"]))


if __name__ == "__main__":
    main()
