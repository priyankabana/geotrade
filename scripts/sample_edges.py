#!/usr/bin/env python3
"""Draw a reproducible, stratified sample of graph edges for manual review.

    python3 -I scripts/sample_edges.py [n] > eval/sample.txt

Seeded so the same sample comes back every time, and written to a file before
anyone reads it, so a disappointing row cannot quietly be dropped.
"""
import os, sys, random, textwrap
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
N    = int(sys.argv[1]) if len(sys.argv) > 1 else 60
SEED = int(os.environ.get("ATLAS_SEED", "20261115"))

SQL = """
SELECT de.id, de.evidence_type, round(de.confidence,2) AS conf,
       dc.relationship_class, dc.direction, dc.substitutability, dc.materiality_pct,
       f.common_name AS filer, t.common_name AS counterparty,
       dc.counterparty_text, dc.quote, d.doc_type, d.filed_at_utc
FROM dependency_edge de
JOIN dependency_claim dc ON dc.id = de.claim_id
JOIN entity f ON f.id = de.from_entity_id
JOIN entity t ON t.id = de.to_entity_id
JOIN chunk ch ON ch.id = de.chunk_id
JOIN document d ON d.id = ch.document_id
WHERE de.evidence_type = %s
"""

def main():
    rnd = random.Random(SEED)
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        out = []
        for ev, want in (("named_concentration", N // 2), ("named_narrative", N - N // 2)):
            cur.execute(SQL, (ev,))
            rows = cur.fetchall()
            cols = [c.name for c in cur.description]
            rows = [dict(zip(cols, r)) for r in rows]
            rnd.shuffle(rows)
            out += rows[:want]

    print(f"# stratified edge sample · seed {SEED} · n={len(out)}")
    print("# judge each: CORRECT / WRONG / UNCLEAR, and why\n")
    for i, r in enumerate(out, 1):
        q = " ".join((r["quote"] or "").split())
        print(f"[{i:02}] {r['filer']}  ->  {r['counterparty']}")
        print(f"     matched_text={r['counterparty_text']!r}  class={r['relationship_class']}"
              f"/{r['direction']}  ev={r['evidence_type']}  conf={r['conf']}"
              f"  pct={r['materiality_pct']}  sub={r['substitutability']}")
        print(f"     {r['doc_type']} filed {str(r['filed_at_utc'])[:10]}")
        for line in textwrap.wrap(q[:420], 108):
            print(f"     | {line}")
        print()

if __name__ == "__main__":
    main()
