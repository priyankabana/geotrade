#!/usr/bin/env python3
"""Apply every migration that has not been applied yet, in order, once each.

`make migrate` used to run 0001 and nothing else, by name. A fresh database
therefore came up without the tenancy fix (0002) or the alias review queue
(0003), and re-running it on an existing database failed on the first
CREATE TABLE. Both are the same missing piece: nothing recorded what had
already run.

Each file is applied inside a transaction and recorded with the SHA-256 of the
text that was applied, so an edit to a migration that has already run is
reported rather than silently ignored.

    python3 -I scripts/migrate.py             # apply what is pending
    python3 -I scripts/migrate.py --status    # show what has run
    python3 -I scripts/migrate.py --baseline  # adopt a database built by hand
"""
import hashlib, os, pathlib, sys
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
HERE = pathlib.Path(__file__).resolve().parent.parent / "infra" / "migrations"

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migration (
    filename    text PRIMARY KEY,
    sha256      text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
)
"""


def main():
    files = sorted(p for p in HERE.glob("*.sql"))
    if not files:
        sys.exit(f"no migrations found in {HERE}")

    conn = psycopg.connect(DSN, autocommit=False)
    cur = conn.cursor()
    cur.execute(LEDGER)
    conn.commit()

    cur.execute("SELECT filename, sha256 FROM schema_migration")
    done = dict(cur.fetchall())

    if "--baseline" in sys.argv:
        # For a database whose schema was applied by hand before this runner
        # existed: record every file as done without running any of it.
        for p in files:
            cur.execute("""INSERT INTO schema_migration (filename, sha256)
                           VALUES (%s,%s) ON CONFLICT (filename) DO NOTHING""",
                        (p.name, hashlib.sha256(p.read_bytes()).hexdigest()))
        conn.commit()
        print(f"  baselined: {len(files)} migrations recorded as already applied")
        print("  nothing was executed. Use this only on a database that already "
              "has the schema.")
        conn.close()
        return

    if "--status" in sys.argv:
        for p in files:
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            if p.name not in done:
                state = "pending"
            elif done[p.name] != sha:
                state = "APPLIED, BUT THE FILE HAS CHANGED SINCE"
            else:
                state = "applied"
            print(f"  {p.name:<34} {state}")
        conn.close()
        return

    changed = [p.name for p in files
               if p.name in done
               and done[p.name] != hashlib.sha256(p.read_bytes()).hexdigest()]
    if changed:
        print("  warning: these have already run but their text has changed since.")
        print("           A migration that has run is history; add a new one instead.")
        for n in changed:
            print(f"             {n}")

    applied = 0
    for p in files:
        if p.name in done:
            continue
        sql = p.read_text()
        print(f"  applying {p.name}")
        try:
            cur.execute(sql)
            cur.execute("INSERT INTO schema_migration (filename, sha256) VALUES (%s,%s)",
                        (p.name, hashlib.sha256(p.read_bytes()).hexdigest()))
            conn.commit()
            applied += 1
        except Exception as exc:
            conn.rollback()
            conn.close()
            sys.exit(f"  FAILED on {p.name}: {exc}")

    print(f"  {applied} applied, {len(files) - applied} already present; "
          f"schema is at {files[-1].name}")
    conn.close()


if __name__ == "__main__":
    main()
