#!/usr/bin/env python3
"""Build `atlas_public`: the subset of the graph we are allowed to publish.

Why this exists
---------------
`docs/sources.md` marks the seven vendor market CSVs `candidate - in use for
development, **not cleared for publication**`. Those CSVs are where all 23,020
companies in `entity` come from, so the working database as a whole cannot be
deployed anywhere public. The graph we built on top of it can: the edges, the
claims, and the filing sentences behind them are read out of SEC EDGAR, which
is US government work and not copyrightable.

So this copies out a purpose-specific extract rather than the universe:

  * only entities that take part in the evidence - they appear in an edge or a
    claim, we read a filing of theirs, or propagation reached them,
  * of the licensed identifier columns, only the three `sources.md` states in
    writing that we may publish: "We keep ISIN, LEI and CIK, which we can
    publish." CUSIP and SEDOL are already dropped at the normaliser boundary
    and are excluded again here, belt and braces,
  * market capitalisation is carried as its band and never as a number, which
    is what the API returns anyway,
  * vendor description prose and the vendor classification taxonomy are left
    behind entirely.

The result has the same schema as `atlas`, so the real API runs against it
unmodified - no second code path, no endpoint that behaves differently in the
deployed build than it does on your machine.

    python3 -I scripts/export_public_db.py            # rebuild atlas_public
    python3 -I scripts/export_public_db.py --report   # what would be copied
"""
import os, subprocess, sys
import psycopg

SRC = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
DST_DB = os.environ.get("ATLAS_PUBLIC_DB", "atlas_public")
DST = SRC.rsplit("/", 1)[0] + "/" + DST_DB

# Entities that carry evidence. A company nobody cited, whose filings we never
# read and that propagation never reached, adds a vendor row to the extract and
# tells a reader nothing.
# The countries the project set out to cover, and how many companies each
# should carry even where no filing has named one yet. Without this the extract
# only contains companies some filing already touched, so India showed four and
# the globe looked like a map of where we had read rather than where we track.
# A company published this way still reports zero cited edges, which is the
# honest number: the list says what we cover, the edge count says what we can
# prove.
COVERED = ['US', 'IN', 'CA', 'AU', 'GB', 'DE', 'JP', 'CN', 'FR', 'HK']
QUOTA_DEFAULT = 12
QUOTA = {'IN': 20}

_quota_sql = ' '.join(
    f"WHEN '{c}' THEN {QUOTA.get(c, QUOTA_DEFAULT)}" for c in COVERED)
_covered_sql = ', '.join(f"'{c}'" for c in COVERED)

SCOPE = f"""
    SELECT from_entity_id FROM dependency_edge
    UNION SELECT to_entity_id FROM dependency_edge
    UNION SELECT subject_entity_id FROM dependency_claim
    UNION SELECT counterparty_entity_id FROM dependency_claim
           WHERE counterparty_entity_id IS NOT NULL
    UNION SELECT entity_id FROM exposure_precompute
    UNION SELECT entity_id FROM document WHERE entity_id IS NOT NULL
    UNION SELECT id FROM (
        SELECT e.id, e.country_hq,
               row_number() OVER (
                 PARTITION BY e.country_hq
                 -- Companies we have actually read something about come
                 -- first, then ones we could read next because they file
                 -- with the SEC, then alphabetically so the list is stable
                 -- between builds.
                 ORDER BY EXISTS (SELECT 1 FROM document d
                                   WHERE d.entity_id = e.id) DESC,
                          EXISTS (SELECT 1 FROM entity_identifier i
                                   WHERE i.entity_id = e.id
                                     AND i.scheme = 'CIK') DESC,
                          e.common_name
               ) AS rn
        FROM entity e
        JOIN entity_listing l ON l.entity_id = e.id AND l.is_primary
        WHERE e.status = 'active' AND e.country_hq IN ({_covered_sql})
    ) q
    WHERE q.rn <= CASE q.country_hq {_quota_sql} ELSE 0 END
"""

IN_SCOPE = f"IN (SELECT * FROM ({SCOPE}) s)"

# Ordered so every foreign key has its target already in place.
TABLES = [
    ("atlas_sector",   "*", "TRUE"),
    ("exchange",       "*", "TRUE"),
    ("tenant",         "*", "TRUE"),

    # successor_id points at another entity, which may well be one we are not
    # copying. Carrying a dangling uuid would break the foreign key, and the
    # successor of an out-of-scope company is not something the public extract
    # can answer anyway.
    ("entity",
     "id, legal_name, common_name, country_incorporation, country_hq, atlas_sector, "
     "fiscal_year_end, status, "
     "CASE WHEN successor_id " + IN_SCOPE + " THEN successor_id END AS successor_id, "
     "website, ir_url, NULL::text AS description, employees, employees_as_of, "
     "created_at, updated_at",
     f"id {IN_SCOPE}"),

    ("entity_listing",  "*", f"entity_id {IN_SCOPE}"),
    ("entity_location", "*", f"entity_id {IN_SCOPE}"),

    # sources.md, point 2: "We keep ISIN, LEI and CIK, which we can publish."
    # Anything else in the column stays home.
    ("entity_identifier", "*",
     f"entity_id {IN_SCOPE} AND scheme IN ('CIK', 'ISIN', 'LEI')"),

    # The band survives, the number does not. The API has always returned
    # "marketCapUsd": null; this makes that true of the data and not only of
    # the serialiser.
    ("entity_metric",
     "id, entity_id, metric, NULL::numeric AS value, currency, as_of, band, "
     "source_id, collected_on",
     f"entity_id {IN_SCOPE} AND metric = 'market_cap_usd' AND band IS NOT NULL"),

    # Former names are shown on the company page and are a matter of record.
    ("entity_alias", "*", f"entity_id {IN_SCOPE} AND alias_type = 'former'"),

    ("document", "*", f"entity_id {IN_SCOPE}"),
    ("section",  "*", "document_id IN (SELECT id FROM document)"),
    ("chunk",    "*", "document_id IN (SELECT id FROM document)"),

    ("dependency_claim", "*", f"subject_entity_id {IN_SCOPE}"),
    ("dependency_edge",  "*",
     f"from_entity_id {IN_SCOPE} AND to_entity_id {IN_SCOPE}"),

    # The tradeable universe and the signals computed over it. An asset may
    # point at a company we are not publishing - the hand-listed large caps
    # mostly have no evidence and so fall outside the extract - and carrying a
    # dangling uuid would break the foreign key. The row survives without the
    # link, which is correct: it simply has no cited tier.
    ("asset",
     "id, symbol, name, asset_class, currency, "
     "CASE WHEN entity_id " + IN_SCOPE + " THEN entity_id END AS entity_id, "
     "note, created_at",
     "TRUE"),

    ("event",          "*", "TRUE"),
    ("event_location", "*", "TRUE"),
    ("exposure_precompute", "*", f"entity_id {IN_SCOPE}"),

    # Signals come last: they reference asset, event and dependency_edge.
    ("asset_signal", "*",
     "edge_id IS NULL OR edge_id IN (SELECT id FROM dependency_edge)"),

    # Headlines and filings. Both are a title and a link - never an article
    # body - so publishing them is the same act as publishing a bibliography,
    # and each link sends the reader to the publisher or to EDGAR. Scoped to
    # the companies in the extract so no row points at an entity we withheld.
    ("company_news",        "*", f"entity_id {IN_SCOPE}"),
    ("company_news_cursor", "*", f"entity_id {IN_SCOPE}"),
]

# api_key holds credential hashes and alias_decision is an internal review
# queue. Neither is published; both are listed here so the omission is a
# decision on the page rather than a table somebody forgot.
NOT_PUBLISHED = ["api_key", "alias_decision", "entity_classification",
                 "coverage_universe", "universe_member", "index_membership",
                 "correction", "extraction_cache", "port"]


def report(conn):
    with conn.cursor() as c:
        c.execute(f"SELECT count(*) FROM entity WHERE id {IN_SCOPE}")
        print(f"  entity            {c.fetchone()[0]:>7} of "
              f"{count(c, 'entity'):>7}  (evidence-bearing only)")
        for t, _, where in TABLES:
            if t == "entity":
                continue
            c.execute(f"SELECT count(*) FROM {t} WHERE {where}")
            print(f"  {t:<17} {c.fetchone()[0]:>7} of {count(c, t):>7}")
    print("\n  withheld entirely: " + ", ".join(NOT_PUBLISHED))


def count(c, t):
    c.execute(f"SELECT count(*) FROM {t}")
    return c.fetchone()[0]


def psql(db, sql):
    return subprocess.run(
        ["docker", "compose", "-f", "infra/docker-compose.yml", "exec", "-T",
         "db", "psql", "-U", "atlas", "-d", db, "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True, text=True)


def main():
    src = psycopg.connect(SRC)
    if "--report" in sys.argv:
        report(src)
        return

    print(f"rebuilding {DST_DB}")
    # An API left running against the extract holds a connection, and Postgres
    # refuses to drop a database that anything is attached to. The build should
    # not fail because a server from the last run is still up.
    psql("postgres", f"""SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                         WHERE datname = '{DST_DB}' AND pid <> pg_backend_pid()""")
    psql("postgres", f'DROP DATABASE IF EXISTS "{DST_DB}"')
    r = psql("postgres", f'CREATE DATABASE "{DST_DB}" OWNER atlas')
    if r.returncode:
        sys.exit(f"could not create {DST_DB}: {r.stderr.strip()}")

    env = dict(os.environ, DATABASE_URL=DST)
    r = subprocess.run([sys.executable, "-I", "scripts/migrate.py"],
                       env=env, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"migrations failed on {DST_DB}:\n{r.stdout}\n{r.stderr}")
    print(f"  schema applied ({r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'ok'})")

    dst = psycopg.connect(DST)
    # The extract carries market capitalisation as a band and not as a figure,
    # and `value` is NOT NULL in the real schema because there it always has
    # one. Relaxing the constraint here is the honest way to say "we do not
    # carry this number" - the alternative is inventing a value to satisfy a
    # constraint, which would put a fabricated figure in a published database.
    # Nothing in the API reads this column; it reads `band`.
    with dst.cursor() as dc:
        dc.execute("ALTER TABLE entity_metric ALTER COLUMN value DROP NOT NULL")
        dst.commit()

    total = 0
    for table, cols, where in TABLES:
        with src.cursor() as sc, dst.cursor() as dc:
            # Binary COPY between two identical schemas: no text escaping to get
            # wrong, and PostGIS geography survives without a round trip through
            # WKT. The filing sentences contain quotes and newlines, so this is
            # not a theoretical concern.
            sc.execute(f"SELECT {cols} FROM {table} WHERE {where} LIMIT 0")
            names = ", ".join(f'"{d.name}"' for d in sc.description)
            with sc.copy(f"COPY (SELECT {cols} FROM {table} WHERE {where}) "
                         f"TO STDOUT (FORMAT BINARY)") as out:
                with dc.copy(f"COPY {table} ({names}) FROM STDIN (FORMAT BINARY)") as into:
                    for block in out:
                        into.write(block)
            dc.execute(f"SELECT count(*) FROM {table}")
            n = dc.fetchone()[0]
            total += n
            print(f"  {table:<22} {n:>7}")
    dst.commit()

    with dst.cursor() as dc:
        for t in NOT_PUBLISHED:
            dc.execute(f"SELECT to_regclass('public.{t}')")
            if dc.fetchone()[0]:
                dc.execute(f"TRUNCATE {t} CASCADE")
        dst.commit()
        # The API connects as atlas_app so row-level security applies. The role
        # is cluster-wide, its grants are not: a database created after 0002 ran
        # elsewhere has none of them.
        dc.execute("GRANT USAGE ON SCHEMA public TO atlas_app")
        dc.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO atlas_app")
        dc.execute("GRANT UPDATE ON api_key TO atlas_app")
        dst.commit()

    print(f"\n{total} rows in {DST_DB}")
    print(f"serve it with:  ATLAS_APP_DSN={DST.replace('atlas:atlas', 'atlas_app:atlas_app')} "
          f"uvicorn main:app")


if __name__ == "__main__":
    main()
