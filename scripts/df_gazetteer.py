#!/usr/bin/env python3
"""Suppress gazetteer entries empirically instead of lexically.

A dictionary cannot tell us that "Financial Institutions" is generic and
"Applied Materials" is not: both are ordinary English words. The corpus can.
A company name is written capitalised nearly every time it appears. A generic
phrase is written lowercase most of the time. So for every candidate alias we
count, across the whole corpus:

    cap  - occurrences that are shaped like a proper noun
    low  - occurrences of the same words that are not

and keep only the aliases that are overwhelmingly capitalised. Document
frequency is the secondary check: a name in a third of all filings is a
category, not a counterparty.

Writes its reasoning to eval/gazetteer_df.tsv so the decision is auditable.
"""
import os, re, sys, collections
import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import TOKEN, CONNECTORS, _proper      # one matcher, one definition

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
CAP_RATIO = 0.65   # below this the phrase is ordinary prose
DF_FRAC   = 0.12   # above this fraction of documents it is a category
MAXN      = 4

def verdict(cap, low, doc_freq):
    """Keep this alias, or suppress it, and say which reason.

    Two independent ways a name earns suppression:

      prose     - the corpus mostly writes it in lower case, so it is an
                  ordinary phrase that happens to collide with a company name.
                  "financial institutions" scored 3 capitalised against 623
                  lower-case; "Applied Materials" scored 28 against 2.

      category  - it is capitalised, but it turns up in so many filings that it
                  names a category rather than a counterparty. Nasdaq appeared
                  in 53% of our documents and Sarbanes-Oxley in 59%.

    Order matters: prose is checked first, so a phrase that is both lower-case
    and ubiquitous is reported as prose, which is the more useful reason.
    """
    total = cap + low
    if total == 0:
        return "keep"                  # never seen; nothing to judge it on
    if cap / total < CAP_RATIO:
        return "prose"
    if doc_freq > DF_FRAC:
        return "category"
    return "keep"


def main():
    conn = psycopg.connect(DSN)
    cur = conn.cursor()
    cur.execute("""SELECT DISTINCT alias_norm FROM entity_alias
                   WHERE NOT is_ambiguous AND length(alias_norm) >= 5""")
    keys = {r[0] for r in cur.fetchall()}
    print(f"  {len(keys):,} candidate keys")

    cur.execute("SELECT document_id, text FROM chunk")
    chunks = cur.fetchall()
    ndoc = len({d for d, _ in chunks})
    print(f"  scanning {len(chunks):,} chunks across {ndoc} documents")

    cap = collections.Counter()
    low = collections.Counter()
    docs = collections.defaultdict(set)

    for n, (did, text) in enumerate(chunks, 1):
        if n % 2000 == 0:
            print(f"    {n:,}/{len(chunks):,}")
        # sentence starts, so an opening capital is not mistaken for a name
        starts = {0} | {m.end() for m in re.finditer(r"[.!?]\s+", text)}
        toks = [(m.group(0), m.group(0).upper(), m.start()) for m in TOKEN.finditer(text)]
        L = len(toks)
        for i in range(L):
            for size in range(min(MAXN, L - i), 0, -1):
                win = toks[i:i + size]
                key = " ".join(t[1] for t in win)
                if key not in keys:
                    continue
                ok = True
                for j, (surface, _u, pos) in enumerate(win):
                    if surface.lower() in CONNECTORS and 0 < j < size - 1:
                        continue
                    if not _proper(surface, pos in starts):
                        ok = False
                        break
                if ok:
                    cap[key] += 1
                    docs[key].add(did)
                else:
                    low[key] += 1
                break      # longest match at this position only

    seen = set(cap) | set(low)
    print(f"  {len(seen):,} keys occur at all")

    os.makedirs("eval", exist_ok=True)
    bad = []
    with open("eval/gazetteer_df.tsv", "w") as fh:
        fh.write("alias_norm\tcap\tlow\tcap_ratio\tdoc_freq\tverdict\n")
        for k in sorted(seen, key=lambda k: (-(cap[k] + low[k]), k)):
            c, l = cap[k], low[k]
            ratio = c / (c + l)
            df = len(docs[k]) / ndoc
            why = verdict(c, l, df)
            if why != "keep":
                bad.append(k)
            fh.write(f"{k}\t{c}\t{l}\t{ratio:.3f}\t{df:.3f}\t{why}\n")

    print(f"  suppressing {len(bad):,} keys "
          f"({sum(1 for k in bad if cap[k]/(cap[k]+low[k]) < CAP_RATIO):,} prose, "
          f"{sum(1 for k in bad if cap[k]/(cap[k]+low[k]) >= CAP_RATIO):,} category)")

    for i in range(0, len(bad), 2000):
        cur.execute("""UPDATE entity_alias SET is_ambiguous = true,
                         ambiguity_note = 'measured: mostly lowercase in corpus, or present in too many filings'
                       WHERE alias_norm = ANY(%s) AND NOT is_ambiguous""", (bad[i:i+2000],))
    conn.commit()
    cur.execute("""SELECT count(*) FROM (SELECT DISTINCT alias_norm FROM entity_alias
                   WHERE NOT is_ambiguous AND length(alias_norm) >= 5) t""")
    print(f"  match keys remaining: {cur.fetchone()[0]:,}")
    conn.close()

if __name__ == "__main__":
    main()
