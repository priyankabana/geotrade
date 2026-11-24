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
import os, pathlib, re, sys
import psycopg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extract import (BIO, CITATION_LIST, COMPETITOR, CONFERRED,
                     EXTRACTOR_VERSION, NOISE, PERSON_ROLE)

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")

# Whole-sentence filters: if the quote matches, the claim goes.
FILTERS = [("citation list", CITATION_LIST), ("noise", NOISE), ("biography", BIO),
           # Added with rules-3.4, after a rival ended up on a company page as
           # one of its customers.
           ("rival, not a counterparty", COMPETITOR)]


def positional_reject(quote, counterparty):
    """The two rules that depend on where the name sits, not just whether a
    phrase appears somewhere in the sentence.

    Applied as whole-sentence filters these were worse than useless: they
    flagged CF Industries' genuine supply relationship with Mitsui, because
    the sentence says Mitsui *was certified* rather than that Mitsui did the
    certifying, and DEFSEC's agreement with Microsoft, because a job title
    appeared 236 characters away. extract.py tests position, so this has to
    as well or the two disagree about the same sentence.
    """
    if not quote or not counterparty:
        return None
    word = counterparty.split()[0]
    i = quote.lower().find(word.lower())
    if i < 0:
        return None
    j = i + len(word)

    # A job title has to be beside the name, not merely in the paragraph.
    if PERSON_ROLE.search(quote[max(0, i - 70):min(len(quote), j + 70)]):
        return "a person, not a company"

    # "... as a Tier 1 Supplier by S&P Global": only the name that follows
    # "by" is conferring the title. A company named before the phrase is the
    # one receiving it.
    conf = CONFERRED.search(quote)
    if conf and conf.end() < i and re.search(r"(?i)\bby\s*$", quote[max(0, i - 10):i]):
        return "a title conferred, not a trade"
    return None


def main():
    apply = "--apply" in sys.argv
    conn = psycopg.connect(DSN)
    cur = conn.cursor()
    cur.execute("""SELECT dc.id, dc.quote, e.common_name,
                          (SELECT count(*) FROM dependency_edge de WHERE de.claim_id = dc.id),
                          dc.counterparty_text
                   FROM dependency_claim dc
                   JOIN entity e ON e.id = dc.subject_entity_id""")
    doomed = []
    for cid, quote, who, edges, counterparty in cur.fetchall():
        hit = None
        for label, rx in FILTERS:
            if quote and rx.search(quote):
                hit = label
                break
        hit = hit or positional_reject(quote, counterparty)
        if hit:
            doomed.append((cid, hit, who, edges, quote))

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
