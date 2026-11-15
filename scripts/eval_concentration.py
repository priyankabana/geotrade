#!/usr/bin/env python3
"""Dump every concentration-backed relationship for exhaustive hand-judging.

This tier is small enough to judge completely, so we do: no sampling, no
confidence interval, no estimate. 26 of 26 is the whole population.

Where several sentences support the same relationship we show the best one:
highest confidence, and among equals the shortest quote, because a tight
sentence states a relationship while a long financial table merely contains
both names.

Writes eval/concentration_all.txt.
"""
import os, textwrap
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")

SQL = """
SELECT DISTINCT ON (de.from_entity_id, de.to_entity_id, de.edge_type)
       ef.legal_name, et.legal_name, de.edge_type,
       dc.materiality_pct, dc.materiality_text, dc.quote
FROM dependency_edge de
JOIN dependency_claim dc ON dc.id = de.claim_id
JOIN entity ef ON ef.id = de.from_entity_id
JOIN entity et ON et.id = de.to_entity_id
WHERE de.evidence_type = 'named_concentration'
ORDER BY de.from_entity_id, de.to_entity_id, de.edge_type,
         de.confidence DESC, length(dc.quote) ASC
"""

def main():
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(SQL)
        rows = cur.fetchall()

    os.makedirs("eval", exist_ok=True)
    shown = sum(1 for r in rows if r[3] is not None)
    with open("eval/concentration_all.txt", "w") as fh:
        fh.write(f"ALL {len(rows)} concentration-backed relationships "
                 f"(exhaustive, not sampled)\n")
        fh.write(f"{shown} carry a percentage; {len(rows) - shown} are shown without one "
                 f"because the sentence does not permit safe attribution.\n\n")
        for i, (f, t, et, pct, basis, q) in enumerate(rows, 1):
            kind = "-->" if et.startswith("customer") else "<--"
            fh.write(f"[{i:02d}] {f}  {kind}  {t}\n")
            fh.write(f"     pct={pct}" + (f"  of {basis}" if basis else "") + "\n")
            fh.write(textwrap.fill(" ".join(q.split()), 100,
                     initial_indent="     ", subsequent_indent="     ")[:700] + "\n\n")
    print(f"{len(rows)} relationships, {shown} with a percentage "
          f"-> eval/concentration_all.txt")

if __name__ == "__main__":
    main()
