#!/usr/bin/env python3
"""Measure recall: of the disclosures that are plainly there, how many did we get?

Precision asks whether what we produced is true. Recall asks what we missed, and
until now we have claimed no number for it.

The method has to avoid the obvious trap: if we look for misses using the same
rules the extractor uses, we will find none by construction. So the candidate
set comes from a deliberately different and much blunter pattern - a percentage
sitting near a customer or supplier word, in a sentence that also contains a
capitalised multi-word name. That over-generates on purpose. Every candidate is
then marked with whether the extractor produced a claim from the same sentence,
and the output is written for a human to judge, because only a human can say
whether a given miss was a real disclosure.

    python3 -I scripts/measure_recall.py          # -> eval/recall_candidates.txt
"""
import os, re, sys, random, textwrap
import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import sentences

DSN  = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
SEED = 4417
N    = 60

# Deliberately blunter than the extractor: a disclosure-shaped sentence.
PCT      = re.compile(r"\b\d{1,3}(?:\.\d+)?\s*%")
PARTY    = re.compile(r"(?i)\b(customers?|suppliers?|vendors?|distributors?)\b")
DISCLOSE = re.compile(r"(?i)\b(accounted\s+for|represented|comprised|were\s+approximately"
                      r"|exceeded|accounting\s+for|or\s+more\s+of)\b")
# a capitalised multi-word name, mid-sentence: something is being named here
NAMED    = re.compile(r"(?<![.!?]\s)\b[A-Z][a-zA-Z&.\-]+(?:\s+(?:of|and|de)?\s*[A-Z][a-zA-Z&.\-]+)+")
NOISE    = re.compile(r"(?i)\b(table\s+of\s+contents|item\s+\d|form\s+10-|united\s+states"
                      r"|securities\s+and\s+exchange)\b")


def main():
    conn = psycopg.connect(DSN); cur = conn.cursor()
    cur.execute("""SELECT c.id, c.char_start, c.text, e.legal_name
                   FROM chunk c
                   JOIN document d ON d.id = c.document_id
                   JOIN entity e   ON e.id = d.entity_id""")
    chunks = cur.fetchall()

    cur.execute("SELECT chunk_id, char_start, char_end, counterparty_text FROM dependency_claim")
    claimed = {}
    for cid, a, b, who in cur.fetchall():
        claimed.setdefault(cid, []).append((a, b, who))
    conn.close()

    cands = []
    for cid, cstart, text, filer in chunks:
        for s0, s1, sent in sentences(text):
            if len(sent) > 700 or NOISE.search(sent):
                continue
            if not (PCT.search(sent) and PARTY.search(sent) and DISCLOSE.search(sent)):
                continue
            if not NAMED.search(sent):
                continue
            # Did the extractor produce anything from THIS sentence? Claims store
            # document-relative offsets (chunk start + sentence start), so the
            # match is exact rather than a guess at the text.
            got = [w for a, b, w in claimed.get(cid, []) if a == cstart + s0]
            cands.append((filer, sent.strip(), got))

    rnd = random.Random(SEED); rnd.shuffle(cands)
    sample = cands[:N]
    hit = sum(1 for _, _, g in sample if g)

    os.makedirs("eval", exist_ok=True)
    with open("eval/recall_candidates.txt", "w") as fh:
        fh.write(f"seed={SEED}  {len(cands)} disclosure-shaped sentences found in the corpus, "
                 f"sample={len(sample)}\n")
        fh.write("Judge each: does this sentence actually disclose a named counterparty?\n")
        fh.write("CAPTURED means the extractor produced a claim naming someone from it.\n\n")
        for i, (filer, sent, got) in enumerate(sample, 1):
            mark = f"CAPTURED ({', '.join(sorted(set(got))[:3])})" if got else "MISSED"
            fh.write(f"[{i:02d}] {mark}   filer: {filer}\n")
            fh.write(textwrap.fill(" ".join(sent.split()), 96,
                     initial_indent="     ", subsequent_indent="     ") + "\n\n")

    print(f"  {len(cands)} disclosure-shaped sentences in the corpus")
    print(f"  sample of {len(sample)}: {hit} captured, {len(sample)-hit} not")
    print(f"  upper bound on recall before judging: {hit/len(sample):.1%}")
    print("  -> eval/recall_candidates.txt  (the misses still need reading:")
    print("     a candidate is not automatically a real disclosure)")


if __name__ == "__main__":
    main()
