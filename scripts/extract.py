#!/usr/bin/env python3
"""Turn chunks into cited dependency claims, then into graph edges.

    python3 -I scripts/extract.py

Two stages, exactly as the architecture describes.

  Stage one  no model. A dependency-phrase lexicon plus the alias gazetteer.
             Measured on real filings it discards ~85% of text.
  Stage two  sentence-level relation extraction. It requires the company name
             and the dependency cue to sit in the SAME SENTENCE, which is what
             separates a real relationship from two facts that happen to share
             a paragraph.

Stage two is deliberately a single function, `extract_sentence`. Swapping it for
a schema-forced Gemini call changes nothing else in the pipeline: same inputs,
same output shape, same offsets.
"""
import os, re, sys
from collections import defaultdict
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
EXTRACTOR_VERSION = "rules-3.3"
SCORER_VERSION    = "deterministic-1.0"

# ---------------------------------------------------------------- lexicon
UPSTREAM = re.compile(r"""(?ix)\b(
    suppliers?  | vendors?   | sole\s+source | single\s+source | sole\s+supplier
  | foundry | foundries | contract\s+manufactur\w* | subcontract\w*
  | purchas\w+\s+(?:from|through) | sourced?\s+from | manufactured\s+by
  | supplied\s+by | procure\w*\s+from | rely\s+(?:up)?on | relian\w+\s+(?:up)?on
  | depend\w*\s+(?:up)?on | outsourc\w+\s+to )\b""")

DOWNSTREAM = re.compile(r"""(?ix)\b(
    customers? | end[-\s]customers? | accounted\s+for | represented\s+approximately
  | sales\s+to | revenues?\s+from | shipments?\s+to | distributors? | resellers?
  | original\s+equipment\s+manufacturer )\b""")

CONCENTRATION = re.compile(r"""(?ix)(
    accounted\s+for\s+(?:approximately\s+)?\d
  | \d{1,3}(?:\.\d+)?\s*%\s+of\s+(?:our\s+|net\s+|total\s+|consolidated\s+)*(?:revenue|sales|net\s+sales)
  | major\s+customers? | significant\s+customers? | concentrations?\s+of\s+credit\s+risk )""")

COMPETITOR = re.compile(r"(?i)\b(compet\w+|rival|peer\s+group)\b")
PARTNER    = re.compile(r"(?i)\b(joint\s+ventures?|partnership|collaborat\w+|alliance|licens\w+\s+agreement)\b")
FORMER     = re.compile(r"(?i)\b(former\w*|previously|no\s+longer|until\s+(?:fiscal\s+)?\d{4}|discontinued)\b")
FORWARD    = re.compile(r"(?i)\b(expects?|anticipat\w+|intends?|plans?|believes?|will|may|could|would|estimate\w*)\b")
SOLE       = re.compile(r"(?i)\b(sole[-\s]sourc\w*|single[-\s]sourc\w*|only\s+qualified|sole\s+suppl\w*)\b")
LIMITED    = re.compile(r"(?i)\b(limited\s+number|small\s+number|a\s+few\s+(?:key\s+)?(?:suppliers?|vendors?))\b")
PCT        = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")

# Python has no variable-width lookbehind, so boundaries are found first and
# the ones that follow an abbreviation are dropped afterwards.
ABBRS = {"inc","corp","co","ltd","limited","llc","plc","nv","sa","ag","lp","no","nos",
         "mr","mrs","ms","dr","st","vs","approx","fig","etc","jan","feb","mar","apr",
         "jun","jul","aug","sep","sept","oct","nov","dec","u.s","u.k","e.g","i.e"}
BOUND = re.compile(r"([.!?])[\s\u00a0]+(?=[A-Z0-9])")
LASTTOK = re.compile(r"([A-Za-z.]+)\.$")

def sentences(text):
    """Yield (start, end, sentence); offsets relative to `text`."""
    out, last = [], 0
    for m in BOUND.finditer(text):
        end = m.end(1)
        tail = text[max(0, end - 14):end]
        tok = LASTTOK.search(tail)
        if tok and tok.group(1).rstrip(".").lower() in ABBRS:
            continue
        if end - last > 12:
            out.append((last, end, text[last:end]))
        last = m.end()
    if len(text) - last > 12:
        out.append((last, len(text), text[last:]))
    return out


# Matching keeps the original case. "Applied Materials" is a proper noun and
# "financial institutions" is not; uppercasing everything before the lookup
# throws away the strongest signal the text has.
TOKEN = re.compile(r"[A-Za-z0-9&]+")
CONNECTORS = {"and", "of", "de", "la", "van", "der", "du", "del", "y"}

def tokenize(sent):
    return [(m.group(0), m.group(0).upper(), m.start(), m.end())
            for m in TOKEN.finditer(sent)]


ACRONYM_PLURAL = re.compile(r"^[A-Z0-9]{2,}s$")


def _proper(tok, first_in_sentence):
    """Could this token be part of a proper noun? Initial capital or all caps,
    and not merely the capital that opens every sentence.

    Tokens with no letters at all - "&" in "Deere & Company", the "3" in "3M" -
    carry no case information, so they neither prove nor disprove anything and
    are passed through."""
    if not any(c.isalpha() for c in tok):
        return True
    if ACRONYM_PLURAL.match(tok):      # ASICs, SoCs, OEMs - an acronym, not a name
        return False
    if not tok[:1].isupper():
        return False
    if first_in_sentence and tok.isalpha() and not tok.isupper():
        return False
    return True


def match_companies(sent, toks, gaz, maxn=4):
    """Longest-first, case-aware. -> [(key, entity_id, ntok, start, end)]"""
    hits, i, n = [], 0, len(toks)
    while i < n:
        matched = False
        for size in range(min(maxn, n - i), 0, -1):
            window = toks[i:i + size]
            key = " ".join(t[1] for t in window)
            if key not in gaz:
                continue
            # A capital at the start of a sentence proves nothing on its own, so a
            # single-token match there is refused. But in "Thor Industries and
            # Forest River accounted for...", the capital on Industries - which
            # is not sentence-initial - vouches for the whole name. Without this
            # every company that opens a sentence was being dropped.
            vouched = any(_proper(w[0], False) for k, w in enumerate(window)
                          if (i + k) != 0 and w[0].lower() not in CONNECTORS)
            ok = True
            for j, (surface, _u, _a, _b) in enumerate(window):
                if surface.lower() in CONNECTORS and 0 < j < size - 1:
                    continue
                first_in_sentence = (i + j) == 0 and not vouched
                if not _proper(surface, first_in_sentence):
                    ok = False
                    break
            if not ok:
                continue
            eid, ntok = gaz[key]
            hits.append((key, eid, ntok, window[0][2], window[-1][3]))
            i += size
            matched = True
            break
        if not matched:
            i += 1
    return hits


# A cue word only means what the grammar around it says it means. "We are a
# supplier to Ford" and "our suppliers include Ford" use the same noun and point
# opposite ways, and reading the noun alone inverts half the graph.
TIER_ONE    = re.compile(r"(?i)\btier[\s-]?(?:one|1|1st)\s+$")
SUPPLIER_TO = re.compile(r"(?i)\b(?:supplier|vendor|provider|manufacturer)s?\s+(?:to|for)\b")
CUSTOMER_OF = re.compile(r"(?i)\bcustomers?\s+of\s+(?!our\b|its\b|the\s+Company|these\b|such\b|this\b)")
NEGATED     = re.compile(r"(?i)\b(?:no|not|neither|none)\s+(?:single\s+|individual\s+)?$")
# the cue noun used as a modifier, which names nobody
MODIFIED    = re.compile(r"(?i)^\s*(?:payments?|base|bases|chain|chains|relationships?|"
                         r"diversity|agreements?|contracts?|service|satisfaction|experience|"
                         r"support|care|concentration|risk|code\s+of\s+conduct)\b")

# Sentences that mention companies for reasons that are not dependencies.
BIO   = re.compile(r"(?i)\b(?:mr|ms|mrs|dr)\.\s+[a-z]"
                   r"|\b(?:served\s+as|serves\s+as|served\s+multiple|"
                   r"prior\s+to\s+(?:this|joining)|was\s+appointed|has\s+served|"
                   r"held\s+(?:the\s+)?positions?|board\s+of\s+directors|"
                   r"vice\s+president|managing\s+director|chief\s+\w+\s+officer\s+of|"
                   r"biograph|age\s+\d\d\b)")
NOISE = re.compile(r"(?i)\b(?:social\s+media|search\s+engines?|facebook|instagram|linkedin|"
                   r"twitter|press\s+releases?|website|webcast|annual\s+meeting|"
                   r"vendors\s+in\s+this\s+category|principal\s+competitors|"
                   r"compete\s+(?:with|against)|competitors\s+include|our\s+(?:established\s+)?brands?\s+include|brand\s+portfolio|repurchas\w+|buy-?back|treasury\s+stock|board\s+authority|shares\s+of\s+[\w\s]{0,24}common\s+stock|include\s+but\s+are\s+not\s+limited\s+to\s+companies)\b")
# A bibliography is not a disclosure.
#
# Arbe Robotics' 20-F carries a "Sources:" block listing market-research
# reports, and one of them mentions NVIDIA. The extractor read that as Arbe
# disclosing a dependency on NVIDIA, which is wrong in a way that matters: it
# put a citation list into the one view where every row is supposed to be a
# sentence a company filed about its own business.
#
# These three shapes are what a reference block looks like and what running
# prose never does: a bullet glyph, an opening "Sources:", or a bare domain in
# parentheses the way a footnote cites one.
# Anchored, and only the heading.
#
# The first attempt also rejected any sentence containing a bullet glyph or a
# parenthesised domain, and that was badly wrong: SEC risk-factor sections are
# written as bulleted lists, so the bullet *is* the disclosure. Tested against
# the stored claims it would have withdrawn 55 of them, including "Customers
# typically pay us a monthly per-subscriber fee and include many of the leading
# MVPDs" and "We rely on third parties to manufacture our products" - exactly
# the sentences this project exists to find.
#
# What actually went wrong was narrower: a reference block opening with
# "Sources:". That is what this matches, and nothing else.
CITATION_LIST = re.compile(r"(?i)^\s*(?:sources?|references?|bibliography)\s*:")

# the name is the filer's own plant, brand or product, not another company
SELF_REF = re.compile(r"(?i)^\s*(?:[\u00ae\u2122]|(?:manufacturing\s+)?(?:plant|facility|facilities|segment|division|brands?|products?|vehicles?|platform|solutions?|operations?|business\s+unit)\b)")

MAX_GAP  = 260   # a company and a cue further apart than this are not one statement
PCT_AFTER  = 70   # a figure this far after a name can still be that name's
PCT_BEFORE = 25   # one before it almost never is
# A figure introduced as a total belongs to the group, not to each member of it.
# "Our top five customers collectively accounted for 57%" says nothing about
# SoftBank alone, and copying 57% onto every name in the list invents data.
AGGREGATE = re.compile(r"(?i)(?:top\s+(?:two|three|five|ten|\d+)\s+(?:customers|suppliers|clients)"
                       r"|(?:two|three|five|ten|\d+)\s+largest\s+(?:customers|suppliers|clients)"
                       r"|collectively|combined|in\s+the\s+aggregate|together"
                       r"|(?:many\s+)?others\s+and\s+represent)")
# what the percentage is a percentage OF
EQUITY   = re.compile(r"(?i)^\s*(?:noncontrolling|non-controlling|equity|ownership|"
                      r"voting|stake|interest\b|of\s+(?:the\s+)?(?:outstanding|issued))")
PURCHASE = re.compile(r"(?i)(?:inventory|purchases|materials\s+purchased|cost\s+of\s+(?:goods|sales))")
RESPECTIVELY = re.compile(r"(?i)\brespectively\b")
# Whether a share is of what we sell or of what we buy decides the direction, and
# we can read that even when we decline to attribute the figure to one company.
# Requires the possessive - "of our new RV inventory" - so that a negated clause
# like "no supplier accounted for 10% of materials purchased" does not match.
BUY_SIDE = re.compile(r"(?i)\bof\s+our\s+[\w\s]{0,24}?(?:inventory|purchases|procurement)\b")
BASIS = re.compile(r"(?i)\bof\s+((?:the\s+|our\s+|[A-Z][\w\u2019']*\u2019?'?s\s+)?"
                   r"(?:total\s+|consolidated\s+|net\s+|gross\s+|new\s+|worldwide\s+)*"
                   r"(?:revenues?|sales|accounts\s+receivable|inventory|purchases|supply)"
                   r"[^.,;)]{0,28})")
PCT_AT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
ACQUISITION = re.compile(r"(?i)\b(acquisitions?|acquired|acquire|mergers?|merged|divest\w*"
                         r"|amortization|purchase\s+price|goodwill|business\s+combination)\b")


def _dist(a, b, x, y):
    return 0 if (x <= a <= y or a <= x <= b) else min(abs(x - b), abs(a - y))


def nearest_pct(sent, a, b, found=()):
    """The percentage belonging to the company named at [a,b). Taking the
    largest number in the sentence hands one customer's share to every company
    in the same table row."""
    cands = []
    for m in PCT_AT.finditer(sent):
        d = _dist(a, b, m.start(), m.end())
        if d > (PCT_BEFORE if m.start() < a else PCT_AFTER):
            continue
        if m.start() < a:
            d += 1000          # any figure that follows the name outranks it
        if AGGREGATE.search(sent[max(0, m.start() - 120):m.start()]):
            continue               # a group total, not this company's share
        if EQUITY.match(sent[m.end():m.end() + 30]):
            continue               # a shareholding, not a revenue share
        lo, hi = (b, m.start()) if m.start() >= b else (m.end(), a)
        if any(lo <= f[3] and f[4] <= hi for f in found):
            continue               # another company's name sits in between;
                                   # in a table that figure is theirs, not ours
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if not 0 <= v <= 100:
            continue
        cands.append((d, v, m))
    if not cands:
        return None, None
    cands.sort()
    if RESPECTIVELY.search(sent) and len(cands) > 1 and cands[1][0] < 1000:
        return None, None      # a list paired by position we cannot line up
    return cands[0][1], cands[0][2]


def paired_pcts(sent, found):
    """"Sales to Apple and Qualcomm were 29.8% and 11.1%, respectively" pairs the
    nth name with the nth figure. Nearest-match hands Qualcomm Apple's number."""
    if not RESPECTIVELY.search(sent):
        return None
    pcts = [m for m in PCT_AT.finditer(sent)
            if not AGGREGATE.search(sent[max(0, m.start() - 120):m.start()])]
    if len(pcts) != len(found) or len(found) < 2:
        return None
    if len({f[1] for f in found}) != len(found):
        return None    # a name repeats in this sentence, so position proves nothing
    if any(p.start() < found[-1][3] for p in pcts):
        return None                # figures must all follow the list of names
    out = {}
    for (alias, _e, _n, a, _b), m in zip(found, pcts):
        try:
            v = float(m.group(1))
        except ValueError:
            return None
        if not 0 <= v <= 100:
            return None
        out[a] = (v, m)
    return out


def extract_sentence(sent, filer_tokens, gaz):
    """STAGE TWO. One sentence in, zero or more claims out.

    Replace this body with a schema-forced Gemini call and nothing else in the
    pipeline changes: same input, same output shape, same offsets.
    """
    if BIO.search(sent) or NOISE.search(sent) or CITATION_LIST.search(sent):
        return []

    cues = []
    for m, d in ([(m, "upstream") for m in UPSTREAM.finditer(sent)] +
                 [(m, "downstream") for m in DOWNSTREAM.finditer(sent)]):
        before, after = sent[max(0, m.start() - 24):m.start()], sent[m.end():m.end() + 24]
        if NEGATED.search(before):        # "No supplier accounted for 10% or more"
            continue
        if MODIFIED.match(after):         # "supplier payments", "customer base"
            continue
        if d == "upstream" and TIER_ONE.search(sent[max(0, m.start() - 16):m.start()]):
            d = "downstream"              # tier ones buy from everyone below them
        elif d == "upstream" and SUPPLIER_TO.match(sent, m.start()):
            d = "downstream"              # we are the supplier; they are the customer
        elif d == "downstream" and CUSTOMER_OF.match(sent, m.start()):
            d = "upstream"                # we are the customer; they are the supplier
        cues.append((m.start(), m.end(), d))
    if not cues:
        return []
    toks = tokenize(sent)
    if not toks:
        return []
    found = match_companies(sent, toks, gaz)
    if not found:
        return []

    conc = bool(CONCENTRATION.search(sent))
    comp = bool(COMPETITOR.search(sent))
    part = bool(PARTNER.search(sent))
    form = bool(FORMER.search(sent))
    fwd  = bool(FORWARD.search(sent))
    sole = bool(SOLE.search(sent))
    lim  = bool(LIMITED.search(sent))

    paired = paired_pcts(sent, found)

    out = []
    for alias, eid, ntok, a, b in found:
        if alias in filer_tokens:
            continue

        near = min(cues, key=lambda c: _dist(a, b, c[0], c[1]))
        gap = _dist(a, b, near[0], near[1])
        if gap > MAX_GAP:
            continue

        if SELF_REF.match(sent[b:b + 28]):
            continue              # "Metro(r) vehicles", "our Hopewell plant"

        lo, hi = max(0, a - 160), min(len(sent), b + 160)
        if ACQUISITION.search(sent[lo:hi]):
            continue          # a name in an acquisition clause is not a dependency

        direction = near[2]
        if comp:   rel = "competitor"
        elif form: rel = "former"
        elif part: rel = "partner"
        elif fwd:  rel = "hypothetical"
        else:      rel = "customer" if direction == "downstream" else "supplier"

        if paired and a in paired:
            pct, pm = paired[a]
        else:
            pct, pm = nearest_pct(sent, a, b, found)
        buy_side = BUY_SIDE.search(sent) or (
            pm is not None and PURCHASE.search(sent[pm.end():pm.end() + 60]))
        if buy_side:
            direction = "upstream"    # a share of what we buy, not of what we sell
            rel = "supplier" if rel == "customer" else rel
        basis = None
        if pm is not None:
            mb = BASIS.search(sent[pm.end():pm.end() + 90])
            if mb:
                basis = " ".join(mb.group(1).split())[:60]

        sub = "sole_source" if sole else ("limited" if lim else "unstated")
        ev  = "named_concentration" if (conc and pct is not None) else "named_narrative"

        conf = 0.50
        if pct is not None:   conf += 0.20
        if sub != "unstated": conf += 0.15
        if conc:              conf += 0.10
        if fwd:               conf -= 0.15
        conf += 0.05 if ntok >= 2 else -0.05
        conf -= min(0.15, gap / MAX_GAP * 0.15)

        out.append(dict(
            counterparty_text=alias.title(), counterparty_entity_id=eid,
            direction=direction, specificity="named", relationship_class=rel,
            tense="forward_looking" if fwd else "current",
            substitutability=sub, materiality_pct=pct, materiality_text=basis,
            evidence_type=ev,
            confidence=max(0.05, min(0.97, round(conf, 3)))))

    # A company named several times in one sentence yields one candidate per
    # mention, and those can disagree: "we rely on Google ... if Google changes
    # its algorithms" put Google on both sides of the same sentence and produced
    # two contradictory edges. One sentence asserts one relationship per company,
    # so keep the best-evidenced reading - highest confidence, which is the
    # mention nearest its cue and the one carrying a disclosed percentage.
    best = {}
    for cl in out:
        k = cl["counterparty_entity_id"]
        if k not in best or cl["confidence"] > best[k]["confidence"]:
            best[k] = cl
    return list(best.values())


def main():
    conn = psycopg.connect(DSN, autocommit=False)
    cur = conn.cursor()

    print("  loading gazetteer")
    # An alias that resolves to several entities is a decision. Where a person
    # has made one it is honoured; where nobody has, we still take the first row
    # the database returns, which is a decision made by the query planner. The
    # review queue (scripts/review_aliases.py) exists to shrink that second set.
    cur.execute("""
        SELECT a.alias_norm, a.entity_id, a.token_count
        FROM entity_alias a
        LEFT JOIN alias_decision d ON d.alias_norm = a.alias_norm
        WHERE NOT a.is_ambiguous
          AND length(a.alias_norm) >= 5
          AND (d.decision IS NULL
               OR d.decision = 'merge'
               OR (d.decision = 'prefer' AND d.entity_id = a.entity_id))
        ORDER BY (d.decision = 'prefer') DESC NULLS LAST
    """)
    gaz = {}
    for norm, eid, ntok in cur.fetchall():
        gaz.setdefault(norm, (eid, ntok or len(norm.split())))
    print(f"    {len(gaz):,} usable aliases")

    cur.execute("""SELECT c.id, c.document_id, c.char_start, c.text,
                          d.entity_id, e.legal_name, d.filed_at_utc
                   FROM chunk c
                   JOIN document d ON d.id = c.document_id
                   JOIN entity e   ON e.id = d.entity_id
                   WHERE NOT EXISTS (SELECT 1 FROM dependency_claim dc WHERE dc.chunk_id = c.id)""")
    chunks = cur.fetchall()
    print(f"  {len(chunks):,} chunks to process")

    SUF = re.compile(r"\b(INC|CORP|CORPORATION|CO|LTD|LIMITED|LLC|PLC|NV|SA|AG|LP|HOLDINGS|GROUP|THE)\b\.?", re.I)
    passed = claims = 0
    rows = []
    for cid, did, cstart, text, feid, fname, filed in chunks:
        # ---- STAGE ONE: cheap gate, no model
        if not (UPSTREAM.search(text) or DOWNSTREAM.search(text)):
            continue
        passed += 1
        filer_norm = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9& ]", " ",
                        SUF.sub(" ", (fname or "").upper()))).strip()
        filer_tokens = {filer_norm} | {t for t in filer_norm.split() if len(t) > 4}

        for s0, s1, sent in sentences(text):
            for cl in extract_sentence(sent, filer_tokens, gaz):
                rows.append((cid, feid, cl, cstart + s0, cstart + s1, sent.strip()[:1200]))
                claims += 1

    print(f"  stage one passed {passed:,} of {len(chunks):,} chunks ({passed/max(len(chunks),1)*100:.1f}%)")
    print(f"  stage two produced {claims:,} claims; writing")

    for cid, feid, cl, a, b, quote in rows:
        cur.execute("""
            INSERT INTO dependency_claim (chunk_id, subject_entity_id, counterparty_text,
                counterparty_entity_id, counterparty_resolved, direction, specificity,
                relationship_class, tense, substitutability, materiality_pct,
                materiality_text, quote,
                char_start, char_end, extractor_version, model_id)
            VALUES (%s,%s,%s,%s,true,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'none')
        """, (cid, feid, cl["counterparty_text"], cl["counterparty_entity_id"],
              cl["direction"], cl["specificity"], cl["relationship_class"], cl["tense"],
              cl["substitutability"], cl["materiality_pct"], cl["materiality_text"],
              quote, a, b, EXTRACTOR_VERSION))
    conn.commit()

    # ---- promote resolved, named, real relationships to graph edges
    print("  promoting claims to edges")
    cur.execute("""
        INSERT INTO dependency_edge (from_entity_id, to_entity_id, edge_type, claim_id,
            chunk_id, char_start, char_end, evidence_type, valid_from, confidence,
            weight, scorer_version)
        SELECT dc.subject_entity_id,
               dc.counterparty_entity_id,
               CASE WHEN dc.direction='downstream' THEN 'customer_concentration'
                    ELSE 'supplier_dependency' END,
               dc.id, dc.chunk_id, dc.char_start, dc.char_end,
               CASE WHEN dc.materiality_pct IS NOT NULL OR dc.quote ~* 'accounted for'
                    THEN 'named_concentration' ELSE 'named_narrative' END,
               d.filed_at_utc,
               LEAST(0.97, GREATEST(0.05,
                   0.50
                 + CASE WHEN dc.materiality_pct IS NOT NULL THEN 0.20 ELSE 0 END
                 + CASE WHEN dc.substitutability <> 'unstated' THEN 0.15 ELSE 0 END
                 + CASE WHEN dc.tense = 'forward_looking' THEN -0.15 ELSE 0 END)),
               CASE WHEN dc.materiality_pct IS NOT NULL
                    THEN LEAST(1.0, dc.materiality_pct / 100.0) ELSE 0.25 END,
               %s
        FROM dependency_claim dc
        JOIN chunk ch   ON ch.id = dc.chunk_id
        JOIN document d ON d.id = ch.document_id
        WHERE dc.counterparty_resolved
          AND dc.specificity = 'named'
          AND dc.relationship_class IN ('supplier','customer')
          AND dc.subject_entity_id <> dc.counterparty_entity_id
          AND NOT EXISTS (SELECT 1 FROM dependency_edge de WHERE de.claim_id = dc.id)
    """, (SCORER_VERSION,))
    conn.commit()

    for q, label in [
        ("SELECT count(*) FROM dependency_claim", "claims"),
        ("SELECT count(*) FROM dependency_edge", "edges"),
        ("SELECT count(DISTINCT from_entity_id) FROM dependency_edge", "companies with edges"),
        ("SELECT count(DISTINCT to_entity_id) FROM dependency_edge", "counterparties named"),
        ("SELECT count(*) FROM dependency_edge WHERE evidence_type='named_concentration'", "concentration-backed"),
    ]:
        cur.execute(q); print(f"  {label:24} {cur.fetchone()[0]:,}")
    conn.close()

if __name__ == "__main__":
    main()
