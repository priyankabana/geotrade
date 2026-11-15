#!/usr/bin/env python3
"""Draw a seeded sample of distinct relationships for hand judging.

The graph's unit is the relationship, not the sentence: one Ducommun -> Boeing
dependency cited by sixteen sentences is one edge a user would see, so precision
has to be counted that way or a single well-cited pair would swamp the number.

The sample is written to eval/pairs.txt BEFORE any judging, with a fixed seed,
so the set being judged cannot be quietly reshaped by what the judging finds.
"""
import os, random, textwrap
import psycopg

DSN  = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
SEED = int(os.environ.get("SAMPLE_SEED", 20261115))
N    = int(os.environ.get("SAMPLE_N", 80))

SQL = """
SELECT DISTINCT ON (de.from_entity_id, de.to_entity_id, de.edge_type)
       ef.legal_name, et.legal_name, de.edge_type, de.evidence_type,
       de.confidence, dc.materiality_pct, dc.relationship_class, dc.quote,
       (SELECT count(*) FROM dependency_edge x
         WHERE x.from_entity_id=de.from_entity_id
           AND x.to_entity_id=de.to_entity_id
           AND x.edge_type=de.edge_type) AS cites
FROM dependency_edge de
JOIN dependency_claim dc ON dc.id = de.claim_id
JOIN entity ef ON ef.id = de.from_entity_id
JOIN entity et ON et.id = de.to_entity_id
ORDER BY de.from_entity_id, de.to_entity_id, de.edge_type, de.confidence DESC, length(dc.quote) ASC
"""

def main():
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(SQL)
        rows = cur.fetchall()

    conc = [r for r in rows if r[3] == "named_concentration"]
    narr = [r for r in rows if r[3] != "named_concentration"]
    rnd  = random.Random(SEED)
    # stratify so the weaker evidence class cannot hide behind the stronger one
    take = lambda pool, k: rnd.sample(pool, min(k, len(pool)))
    share = round(N * len(conc) / max(len(rows), 1))
    sample = take(conc, share) + take(narr, N - share)
    rnd.shuffle(sample)

    os.makedirs("eval", exist_ok=True)
    # Never the historical audit files by default: eval/pairs.txt holds the
    # first audit, the 62.5% baseline, and overwriting it would erase the only
    # record of where the extractor started.
    out = os.environ.get("SAMPLE_OUT", "eval/sample_latest.txt")
    with open(out, "w") as fh:
        fh.write(f"seed={SEED}  population={len(rows)} relationships "
                 f"({len(conc)} concentration / {len(narr)} narrative)  sample={len(sample)}\n")
        fh.write("judge each: TRUE if the quote really states this dependency, "
                 "FALSE otherwise\n\n")
        for i, (f, t, et, ev, cf, pct, rc, q, n) in enumerate(sample, 1):
            fh.write(f"[{i:02d}] {f}  --{et}-->  {t}\n")
            fh.write(f"     {ev}  class={rc}  conf={cf}  pct={pct}  cited_by={n}\n")
            fh.write(textwrap.fill(q.strip(), 96,
                     initial_indent="     “", subsequent_indent="      ") + "”\n\n")
    print(f"population {len(rows)} relationships; wrote {len(sample)} to {out}")

if __name__ == "__main__":
    main()
