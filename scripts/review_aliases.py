#!/usr/bin/env python3
"""The review queue for ambiguous aliases: a human decides, and the decision is dated.

An alias that resolves to more than one entity is a decision waiting to be made.
Until now the extractor took whichever row the database returned first - a
decision made by the query planner, with nobody accountable and no record of it.

Only aliases that actually occur in the corpus are worth a person's time, so the
queue is ranked by how often each one appears in text we have read. Aliases
nobody will ever match are left alone.

    python3 -I scripts/review_aliases.py                 # show the queue
    python3 -I scripts/review_aliases.py --auto          # resolve the easy ones
    python3 -I scripts/review_aliases.py METRO suppress  # record a decision
    python3 -I scripts/review_aliases.py HYUNDAI prefer "Hyundai Motor Co"
"""
import os, re, sys, collections
import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import TOKEN, CONNECTORS, _proper

DSN  = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
WHO  = os.environ.get("ATLAS_REVIEWER", os.environ.get("USER", "unknown"))
# A legal form says which jurisdiction a company is registered in, and that is
# identity, not furniture. Stripping it outright made "Metro AG" (a German
# wholesaler) and "Metro Inc." (a Canadian grocer) the same string, and
# "Pfizer Inc" the same as "Pfizer Ltd" - which is precisely the entity
# resolution error the audit kept finding. Forms are grouped into families
# instead: two names merge only if what is left matches AND their forms could
# belong to the same company.
FORM_FAMILY = {
    "inc": "us", "incorporated": "us", "corp": "us", "corporation": "us",
    "llc": "us", "lp": "lp", "llp": "lp",
    "ltd": "uk", "limited": "uk", "plc": "uk",
    "ag": "de", "gmbh": "de", "se": "de",
    "nv": "nl", "bv": "nl",
    "sa": "fr", "spa": "it", "ab": "se", "as": "no", "oyj": "fi",
    "pte": "sg", "pty": "au", "kk": "jp",
}
# Words that really are furniture: they say nothing about who the company is.
NOISE_WORD = re.compile(r"(?i)\b(the|holdings?|group|usa|co|company|companies"
                        r"|class\s+[a-z]|series\s+[a-z]|registered\s+shares|adr|ads)\b")


def _clean(name):
    cleaned = re.sub(r"[^a-z0-9& ]", " ", (name or "").lower())
    return NOISE_WORD.sub(" ", cleaned).split()


def bare(name):
    """The identifying part of a legal name, with furniture removed but the
    legal form kept out of the comparison and reported separately."""
    toks = [t for t in _clean(name) if t not in FORM_FAMILY]
    return " ".join(toks)


def form(name):
    """The jurisdiction family implied by the legal form, or None if the name
    does not state one."""
    for t in reversed(_clean(name)):
        if t in FORM_FAMILY:
            return FORM_FAMILY[t]
    return None


def same_company(a, b):
    """Safe enough to merge without asking a person?

    Only when the identifying words match and the legal forms do not
    contradict - one may be absent, but a German AG and a US Inc are two
    companies that happen to share a name."""
    if not bare(a) or bare(a) != bare(b):
        return False
    fa, fb = form(a), form(b)
    return fa is None or fb is None or fa == fb


def corpus_counts(cur, keys):
    """How often each alias actually appears, capitalised, in text we have read.
    An alias nobody will match is not worth anyone's attention."""
    cur.execute("SELECT text FROM chunk")
    counts = collections.Counter()
    keyset = set(keys)
    maxn = max((len(k.split()) for k in keyset), default=1)
    for (text,) in cur.fetchall():
        starts = {0} | {m.end() for m in re.finditer(r"[.!?]\s+", text)}
        toks = [(m.group(0), m.group(0).upper(), m.start()) for m in TOKEN.finditer(text)]
        for i in range(len(toks)):
            for size in range(min(maxn, len(toks) - i), 0, -1):
                win = toks[i:i + size]
                key = " ".join(t[1] for t in win)
                if key not in keyset:
                    continue
                if all(_proper(s, p in starts) or s.lower() in CONNECTORS
                       for s, _u, p in win):
                    counts[key] += 1
                break
    return counts


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    auto = "--auto" in sys.argv
    conn = psycopg.connect(DSN); cur = conn.cursor()

    if len(args) >= 2:                       # record one decision
        alias, decision = args[0].upper(), args[1]
        eid = None
        if decision == "prefer":
            if len(args) < 3:
                sys.exit("prefer needs the legal name to prefer")
            cur.execute("SELECT id FROM entity WHERE legal_name = %s", (args[2],))
            row = cur.fetchone()
            if not row:
                sys.exit(f"no entity named {args[2]!r}")
            eid = row[0]
        cur.execute("""INSERT INTO alias_decision (alias_norm, decision, entity_id, decided_by)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (alias_norm) DO UPDATE
                         SET decision=EXCLUDED.decision, entity_id=EXCLUDED.entity_id,
                             decided_by=EXCLUDED.decided_by, decided_at=now()""",
                    (alias, decision, eid, WHO))
        if decision == "suppress":
            cur.execute("""UPDATE entity_alias SET is_ambiguous = true,
                             ambiguity_note = 'reviewed: resolves to more than one company'
                           WHERE alias_norm = %s""", (alias,))
        conn.commit()
        print(f"  {alias}: {decision} (by {WHO})")
        conn.close(); return

    cur.execute("SELECT alias_norm, entity_count, candidates FROM alias_review_queue")
    queue = cur.fetchall()
    if not queue:
        print("  queue is empty - every ambiguous alias has a dated decision")
        conn.close(); return

    print(f"  {len(queue)} ambiguous aliases await a decision; "
          f"counting how often each appears in the corpus")
    counts = corpus_counts(cur, [q[0] for q in queue])
    live = [(counts[a], a, n, c) for a, n, c in queue if counts[a] > 0]
    live.sort(reverse=True)
    print(f"  {len(live)} of them actually occur in text we have read\n")

    if auto:
        merged = 0
        for _, alias, _n, cands in live:
            if all(same_company(cands[0], c) for c in cands[1:]):
                cur.execute("""INSERT INTO alias_decision
                                 (alias_norm, decision, decided_by, note)
                               VALUES (%s,'merge',%s,%s)
                               ON CONFLICT (alias_norm) DO NOTHING""",
                            (alias, f"{WHO} (auto)",
                             "candidates are one company under different legal spellings"))
                merged += 1
        conn.commit()
        print(f"  auto-resolved {merged} as duplicate spellings of one company")
        print("  the rest are genuine collisions and need a person:\n")
        cur.execute("SELECT alias_norm, entity_count, candidates FROM alias_review_queue")
        queue = {a: (n, c) for a, n, c in cur.fetchall()}
        live = [(k, a, n, c) for k, a, n, c in live if a in queue]

    for cnt, alias, n, cands in live[:30]:
        same = all(same_company(cands[0], c) for c in cands[1:])
        print(f"  {alias:<34} {cnt:>4}x  {n} entities  "
              f"{'[same company, spellings differ]' if same else '[COLLISION]'}")
        for c in cands[:4]:
            print(f"       {c}")
    if len(live) > 30:
        print(f"\n  ... and {len(live)-30} more")
    print(f"\n  decide one:  python3 -I scripts/review_aliases.py <ALIAS> "
          f"suppress|merge|prefer \"<legal name>\"")
    conn.close()


if __name__ == "__main__":
    main()
