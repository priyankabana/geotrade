#!/usr/bin/env python3
"""Withdraw claims and edges that the current extractor rules would now reject.

Extraction is incremental: it only reads chunks that have no claim yet, so
tightening a rule changes nothing about what is already in the graph. A rule
that only applies to filings we have not read yet is not a rule, it is a note
to self.

This re-tests every stored claim's own quote against the current filters and
removes the ones that no longer pass, together with the edges built on them.
It never adds anything - a loosened rule needs a re-extraction, not this.

    python3 -I scripts/retract.py            # report only
    python3 -I scripts/retract.py --apply    # remove them
"""
import os, pathlib, sys
import psycopg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extract import BIO, CITATION_LIST, EXTRACTOR_VERSION, NOISE

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")

FILTERS = [("citation list", CITATION_LIST), ("noise", NOISE), ("biography", BIO)]


def main():
    apply = "--apply" in sys.argv
    conn = psycopg.connect(DSN)
    cur = conn.cursor()
    cur.execute("""SELECT dc.id, dc.quote, e.common_name,
                          (SELECT count(*) FROM dependency_edge de WHERE de.claim_id = dc.id)
                   FROM dependency_claim dc
                   JOIN entity e ON e.id = dc.subject_entity_id""")
    doomed = []
    for cid, quote, who, edges in cur.fetchall():
        for label, rx in FILTERS:
            if quote and rx.search(quote):
                doomed.append((cid, label, who, edges, quote))
                break

    if not doomed:
        print(f"  nothing to retract; every stored claim still passes {EXTRACTOR_VERSION}")
        return 0

    print(f"  {len(doomed)} claims no longer pass {EXTRACTOR_VERSION}:\n")
    for _, label, who, edges, quote in doomed[:20]:
        flat = " ".join((quote or "").split())[:110]
        print(f"    [{label}] {who[:26]:28} {edges} edge(s)")
        print(f"       {flat}")
    if len(doomed) > 20:
        print(f"    ... and {len(doomed) - 20} more")

    if not apply:
        print("\n  --apply to remove them")
        return 0

    ids = [d[0] for d in doomed]
    cur.execute("DELETE FROM dependency_edge WHERE claim_id = ANY(%s)", (ids,))
    gone_edges = cur.rowcount
    cur.execute("DELETE FROM dependency_claim WHERE id = ANY(%s)", (ids,))
    gone_claims = cur.rowcount
    conn.commit()
    cur.execute("SELECT count(*) FROM dependency_edge")
    edges = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM dependency_claim")
    claims = cur.fetchone()[0]
    print(f"\n  removed {gone_claims} claims and {gone_edges} edges")
    print(f"  graph now {edges} edges from {claims} claims")
    print("\n  next: make refresh   (exposure and signals reference the removed edges)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
