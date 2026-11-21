#!/usr/bin/env python3
"""Sentiment over the text this project already holds.

Review 1 listed sentiment classification; Review 3 recorded that it was not
built. This is that component, written to the same rule as everything else
here: a score is stored with the words it was read from and the version of the
scorer that produced it, so a disputed number can be recomputed rather than
argued about.

Two methods sit behind one schema.

  lexicon   A finance-tuned word list with negation and intensifier handling.
            Deterministic, offline, free, and reproducible by hand from the
            table in this file. This is the default.

  model     A language model asked for the same JSON. Better on sarcasm,
            hedging and analyst phrasing. Costs money and needs a key, so it
            is opt-in and the version string records which model scored a row.

Both write the same columns, so switching methods is measurable instead of a
matter of taste: score the same held-out passages twice and compare.

    python3 -I scripts/sentiment.py --source news --limit 500
    python3 -I scripts/sentiment.py --source filings --method model
    python3 -I scripts/sentiment.py --report
"""
import os
import re
import sys
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")

LEXICON_VERSION = "lexicon-1.1"
MODEL_NAME = os.environ.get("SENTIMENT_MODEL", "gpt-4o-mini")

# --------------------------------------------------------------- lexicon ---
# Weights are deliberate and reviewable. Financial text is not ordinary
# English: "beat" and "miss" are not about violence, "guidance" is not advice,
# and "charge" is usually a write-off. A general-purpose sentiment list gets
# these backwards, which is the main reason a bespoke table earns its place.
POSITIVE = {
    "beat": 0.8, "beats": 0.8, "exceeded": 0.7, "exceeds": 0.7, "outperform": 0.7,
    "record": 0.6, "surge": 0.8, "surged": 0.8, "soar": 0.8, "soared": 0.8,
    "rally": 0.6, "rallied": 0.6, "growth": 0.5, "grew": 0.5, "rose": 0.5,
    "upgrade": 0.7, "upgraded": 0.7, "raised": 0.5, "raises": 0.5,
    "profit": 0.5, "profitable": 0.6, "strong": 0.5, "robust": 0.5,
    "expansion": 0.5, "expands": 0.5, "approval": 0.7, "approved": 0.7,
    "awarded": 0.6, "wins": 0.6, "won": 0.5, "partnership": 0.4,
    "dividend": 0.4, "buyback": 0.5, "recovery": 0.5, "rebound": 0.6,
    "milestone": 0.4, "breakthrough": 0.7, "accelerate": 0.5,
}
NEGATIVE = {
    "miss": -0.8, "missed": -0.8, "misses": -0.8, "shortfall": -0.7,
    "plunge": -0.9, "plunged": -0.9, "slump": -0.8, "slumped": -0.8,
    "tumble": -0.8, "tumbled": -0.8, "fell": -0.5, "falls": -0.5,
    "decline": -0.6, "declined": -0.6, "downgrade": -0.7, "downgraded": -0.7,
    "loss": -0.6, "losses": -0.6, "lawsuit": -0.6, "sued": -0.6,
    "investigation": -0.7, "probe": -0.6, "fraud": -0.9, "recall": -0.7,
    "layoffs": -0.7, "layoff": -0.7, "cuts": -0.4, "cut": -0.4,
    "bankruptcy": -1.0, "default": -0.9, "delisting": -0.9, "halted": -0.7,
    "impairment": -0.7, "writedown": -0.7, "write-down": -0.7,
    "warning": -0.6, "warns": -0.6, "weak": -0.5, "weaker": -0.5,
    "disruption": -0.6, "shortage": -0.6, "delay": -0.5, "delayed": -0.5,
    "resign": -0.5, "resigned": -0.5, "departure": -0.4, "ousted": -0.7,
    "breach": -0.7, "outage": -0.6, "strike": -0.5, "tariff": -0.4,
    "headwind": -0.5, "slowdown": -0.6,
    # the standing vocabulary of Item 1A
    "litigation": -0.5, "competition": -0.3, "risk": -0.3, "uncertainty": -0.4,
    "volatility": -0.4, "adverse": -0.6, "adversely": -0.6, "penalty": -0.6,
    "fine": -0.5, "dispute": -0.5, "constraint": -0.4, "exposure": -0.3,
    "dependence": -0.4, "concentration": -0.3, "obsolete": -0.6,
    "contamination": -0.6, "injunction": -0.6, "restructuring": -0.5,
    "deficiency": -0.6, "material weakness": -0.8, "going concern": -0.9,
}
NEGATORS = {"not", "no", "never", "without", "fails", "failed", "unable",
            "neither", "nor", "lacks", "lacking", "cannot", "ceased"}
INTENSIFIERS = {"very": 1.4, "sharply": 1.5, "significantly": 1.4, "steeply": 1.5,
                "slightly": 0.6, "marginally": 0.5, "modestly": 0.7,
                "massively": 1.6, "record": 1.3, "dramatically": 1.5}

EVENT_RULES = [
    # Miss is tested before beat, and a negated beat counts as a miss: "did
    # not beat expectations" was being filed as an earnings beat.
    ("earnings_miss", re.compile(
        r"(?i)\b(miss\w*|fell short|below)\b.{0,30}\b(estimat|expect|consensus)"
        r"|\b(did ?n[o']t|failed to|could ?n[o']t)\b.{0,20}\b(beat\w*|exceed\w*|top\w*)\b")),
    ("earnings_beat", re.compile(
        r"(?i)\b(beat\w*|exceed\w*|topp\w+|surpass\w*)\b.{0,30}\b(estimat|expect|consensus)")),
    ("guidance", re.compile(r"(?i)\b(guidance|outlook|forecast)\b")),
    ("m_and_a", re.compile(r"(?i)\b(acquir\w+|merger|takeover|buyout|stake in)\b")),
    ("leadership", re.compile(r"(?i)\b(chief execut\w+|ceo|cfo|chairman)\b.{0,40}\b(resign\w*|step\w* down|appoint\w*|depart\w*)")),
    ("legal", re.compile(r"(?i)\b(lawsuit|sued|settlement|court|antitrust|investigation|probe)\b")),
    ("regulatory", re.compile(r"(?i)\b(regulat\w+|approval|fda|sec filing|sanction\w*|tariff)\b")),
    ("supply_chain", re.compile(r"(?i)\b(supply chain|shortage|disruption|logistics|shipment\w*)\b")),
    ("layoffs", re.compile(r"(?i)\b(layoff\w*|job cuts|redundanc\w+|restructur\w+)\b")),
    ("product", re.compile(r"(?i)\b(launch\w*|unveil\w*|new product|rollout)\b")),
]
HORIZON_RULES = [
    ("immediate", re.compile(r"(?i)\b(today|yesterday|this morning|halted|breaking|intraday)\b")),
    ("structural", re.compile(r"(?i)\b(multi[- ]year|long[- ]term|by 20\d\d|strategic shift|decade)\b")),
]
WORD = re.compile(r"[A-Za-z][A-Za-z\-']+")


def lookup(word: str):
    """Weight for a word, trying its singular if the plural is not listed.

    The table was written in the singular and the filings are written in the
    plural: "shortages", "breaches" and "tariffs" all scored nothing, which
    on a risk factors section meant scoring nothing at all.
    """
    w = POSITIVE.get(word)
    if w is None:
        w = NEGATIVE.get(word)
    if w is not None:
        return w
    for suffix, cut in (("ies", 3), ("es", 2), ("s", 1)):
        if word.endswith(suffix) and len(word) > cut + 2:
            stem = word[:-cut] + ("y" if suffix == "ies" else "")
            w = POSITIVE.get(stem)
            if w is None:
                w = NEGATIVE.get(stem)
            if w is not None:
                return w
    return None


def score_lexicon(text: str) -> dict:
    """Score a passage from the table above.

    The arithmetic is plain on purpose. Hits are summed, divided by a soft
    denominator so a long article is not automatically more extreme than a
    headline, and clamped. Anyone can reproduce a figure by reading the words.
    """
    words = [w.lower() for w in WORD.findall(text or "")]
    if not words:
        return dict(label="neutral", score=0.0, confidence=0.0,
                    horizon="unknown", event_type="other", topics=[], hits=0)

    total, hits, topics, weights = 0.0, 0, [], []
    for i, w in enumerate(words):
        weight = lookup(w)
        if weight is None:
            continue
        window = words[max(0, i - 3):i]
        if any(n in window for n in NEGATORS):
            weight = -weight * 0.8          # negation flips, and softens
        for mod, factor in INTENSIFIERS.items():
            if mod in window:
                weight *= factor
                break
        total += weight
        weights.append(weight)
        hits += 1
        topics.append(w)

    if not hits:
        return dict(label="neutral", score=0.0, confidence=0.1,
                    horizon="unknown", event_type=event_of(text), topics=[], hits=0)

    # Balance, not volume. The first version divided by the square root of the
    # hit count, which worked on headlines and saturated on filings: a 30,000
    # character risk section accumulates so many negative words that every one
    # of them pinned at exactly -1.000 and the companies became
    # indistinguishable. Dividing the signed total by the total magnitude asks
    # a length-independent question instead: of the sentiment in this text,
    # how much of it points one way.
    magnitude = sum(abs(w) for w in weights)
    balance = (total / magnitude) if magnitude else 0.0
    # Balance says which way the text leans; the second term says how much
    # evidence there is for that lean. Two agreeing words in a headline were
    # otherwise scoring a flat 1.000, the same as fifty in a filing.
    evidence = hits / (hits + 4.0)
    score = max(-1.0, min(1.0, balance * evidence))
    label = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"

    # Evidence carries the confidence: a one-word hit is a guess, and thirty
    # agreeing hits are not. Disagreement inside the passage pulls it back
    # down, which is what the score itself already reflects.
    confidence = max(0.0, min(1.0, (min(hits, 20) / 20) * 0.7 + abs(score) * 0.3))

    return dict(label=label, score=round(score, 3), confidence=round(confidence, 3),
                horizon=horizon_of(text), event_type=event_of(text),
                topics=sorted(set(topics))[:8], hits=hits)


def event_of(text: str) -> str:
    for name, rx in EVENT_RULES:
        if rx.search(text or ""):
            return name
    return "other"


def horizon_of(text: str) -> str:
    for name, rx in HORIZON_RULES:
        if rx.search(text or ""):
            return name
    return "medium"


# ----------------------------------------------------------------- model ---
SYSTEM_PROMPT = """You are a financial analyst reading text about a listed company.
Return ONLY a JSON object, no prose and no markdown fence:

{"label":"positive|negative|neutral",
 "score":<float -1.0..1.0>,
 "confidence":<float 0.0..1.0>,
 "horizon":"immediate|medium|structural",
 "event_type":"earnings_beat|earnings_miss|guidance|m_and_a|leadership|legal|regulatory|supply_chain|layoffs|product|other",
 "topics":["lowercase","tags"]}

Judge the effect on the company named, not the mood of the writing. A factual
report of a bad result is negative even when calmly worded. Set confidence low
when the passage is ambiguous or the subject is unclear."""


def score_model(text: str) -> dict:
    """Same schema, asked of a language model.

    The schema is enforced on the way back: anything that does not parse, or
    that falls outside the declared ranges, is rejected rather than coerced.
    A model that will not answer in the agreed shape does not get to write a
    row.
    """
    from openai import OpenAI          # imported here so lexicon runs with no deps

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    reply = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": text[:6000]}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    import json
    data = json.loads(reply.choices[0].message.content)
    return validate(data)


def validate(data: dict) -> dict:
    """Reject anything outside the contract instead of quietly fixing it."""
    label = str(data.get("label", "")).lower()
    if label not in {"positive", "negative", "neutral"}:
        raise ValueError(f"label not in schema: {label!r}")
    score = float(data["score"])
    conf = float(data["confidence"])
    if not -1.0 <= score <= 1.0 or not 0.0 <= conf <= 1.0:
        raise ValueError("score or confidence out of range")
    horizon = str(data.get("horizon", "unknown")).lower()
    if horizon not in {"immediate", "medium", "structural", "unknown"}:
        horizon = "unknown"
    topics = [str(t).lower()[:40] for t in (data.get("topics") or [])][:8]
    return dict(label=label, score=round(score, 3), confidence=round(conf, 3),
                horizon=horizon, event_type=str(data.get("event_type", "other"))[:40],
                topics=topics, hits=None)


# ------------------------------------------------------------------ store ---
SOURCES = {
    "news": """
        SELECT n.id, n.entity_id, n.headline AS text
        FROM company_news n
        LEFT JOIN sentiment_score s
               ON s.subject_kind = 'news' AND s.subject_id = n.id
              AND s.scorer_version = %(version)s
        WHERE n.headline IS NOT NULL AND s.id IS NULL
        ORDER BY n.published_at DESC NULLS LAST
        LIMIT %(limit)s""",
    "filings": """
        SELECT f.id, f.entity_id, f.body AS text
        FROM filing_section f
        LEFT JOIN sentiment_score s
               ON s.subject_kind = 'filing_section' AND s.subject_id = f.id
              AND s.scorer_version = %(version)s
        WHERE s.id IS NULL
        ORDER BY f.filed_date DESC
        LIMIT %(limit)s""",
}
KIND = {"news": "news", "filings": "filing_section"}


def run(source: str, method: str, limit: int) -> int:
    version = LEXICON_VERSION if method == "lexicon" else f"model-{MODEL_NAME}"
    scorer = score_lexicon if method == "lexicon" else score_model

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        cur = conn.cursor()
        cur.execute(SOURCES[source], {"version": version, "limit": limit})
        rows = cur.fetchall()
        if not rows:
            print("  nothing left to score at this version")
            return 0

        print(f"  {len(rows)} passages, {method}, version {version}")
        written = failed = 0
        for r in rows:
            try:
                s = scorer(r["text"])
            except Exception as exc:                       # noqa: BLE001
                failed += 1
                if failed <= 3:
                    print(f"    ! {type(exc).__name__}: {str(exc)[:70]}")
                continue
            cur.execute("""
                INSERT INTO sentiment_score
                    (entity_id, subject_kind, subject_id, label, score, confidence,
                     horizon, event_type, topics, excerpt, method, scorer_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (subject_kind, subject_id, scorer_version) DO NOTHING""",
                (r["entity_id"], KIND[source], r["id"], s["label"], s["score"],
                 s["confidence"], s["horizon"], s["event_type"], s["topics"],
                 (r["text"] or "")[:600], method, version))
            written += cur.rowcount
        conn.commit()

    print(f"\n  {written} scored, {failed} failed")
    return 0


def report() -> int:
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT scorer_version, subject_kind, label, count(*) AS n,
                   round(avg(score), 3) AS mean_score,
                   round(avg(confidence), 3) AS mean_conf
            FROM sentiment_score
            GROUP BY 1,2,3 ORDER BY 1,2,3""")
        rows = cur.fetchall()
    if not rows:
        print("  nothing scored yet")
        return 0
    print(f"  {'version':22} {'subject':15} {'label':9} {'n':>6} {'score':>7} {'conf':>6}")
    for r in rows:
        print(f"  {r['scorer_version']:22} {r['subject_kind']:15} {r['label']:9} "
              f"{r['n']:>6} {r['mean_score']:>7} {r['mean_conf']:>6}")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if "--report" in argv:
        return report()
    source = argv[argv.index("--source") + 1] if "--source" in argv else "news"
    method = argv[argv.index("--method") + 1] if "--method" in argv else "lexicon"
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 500
    if source not in SOURCES:
        print(f"  --source must be one of {', '.join(SOURCES)}")
        return 1
    if method == "model" and not os.environ.get("OPENAI_API_KEY"):
        print("  --method model needs OPENAI_API_KEY in the environment")
        return 1
    return run(source, method, limit)


if __name__ == "__main__":
    sys.exit(main())
