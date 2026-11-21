#!/usr/bin/env python3
"""Headlines per company, from GDELT.

Why not scrape the obvious places: Yahoo Finance, MarketWatch, CNBC, Seeking
Alpha, Benzinga, Nikkei, Handelsblatt and SCMP all prohibit automated
extraction in their terms. `docs/sources.md` rejected NewsAPI for the same
reason, and the rule there is not "be careful", it is that an unclear licence
is a rejection. GDELT indexes those same outlets, publishes an API, and permits
links and headlines - so that is what we store. Never the article body: the
click goes to the publisher, which is the arrangement that makes this fair.

GDELT enforces one request every five seconds, so a full pass over the
universe takes hours. This goes round-robin by least-recently-fetched and is
meant to be run repeatedly, not once:

    python3 -I scripts/ingest_company_news.py --limit 40
    python3 -I scripts/ingest_company_news.py --limit 40 --all

By default only companies that carry evidence are refreshed - those are the
ones a reader can actually reach - and `--all` opens it to the whole universe.
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
UA = os.environ.get("ATLAS_CONTACT",
                    "AtlasResearch/0.2 (academic project; contact via repository)")
SOURCE_ID = "gdelt-doc"
QUERY_ID = "company-news-1.0"

GAP_S = 6.0
BACKOFF_S = 20.0
URL = ("https://api.gdeltproject.org/api/v2/doc/doc?query={q}"
       "&mode=artlist&maxrecords=25&sort=datedesc&format=json&timespan={days}d")

# Legal-form noise makes the query worse, not better: "Cerence Inc" finds less
# than "Cerence" because outlets write the short name.
FORMS = re.compile(r"(?i)\b(inc|corp|corporation|co|ltd|limited|plc|llc|lp|nv|sa|ag|"
                   r"holdings?|group|company|the|technologies|technology)\b\.?")

# A one-word name that is also an ordinary word brings back everything. These
# need the ticker to disambiguate rather than the name alone.
TOO_GENERIC = {"apple", "amazon", "shell", "unity", "block", "match", "gap",
               "target", "visa", "nike", "ford", "arm", "box", "chase", "pool",
               "square", "open", "sky", "alpha", "delta", "range", "core",
               # Found the same way the others were - by reading what came
               # back. "Sydney cafe set alight in alleged arson attack" was
               # filed under Alight Inc. Checking every single-word name in
               # the universe against /usr/share/dict/words turned up these.
               "alight", "credo", "dana", "brunswick"}


def clean(name: str) -> str:
    out = FORMS.sub(" ", name or "")
    return re.sub(r"[^\w&.\- ]", " ", out).strip()


def build_query(name: str, ticker: str | None) -> str | None:
    base = clean(name)
    if len(base) < 3:
        return None
    if base.lower() in TOO_GENERIC:
        if not ticker:
            return None
        return f'"{base}" ("{ticker}" OR stock OR shares OR earnings)'
    return f'"{base}"'


def fetch(query: str, days: int):
    url = URL.format(q=urllib.parse.quote(query), days=days)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=45).read()
            try:
                return json.loads(raw).get("articles", []) or []
            except json.JSONDecodeError:
                # An over-broad query is answered with an HTML notice, not JSON.
                return []
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                return None
            time.sleep(BACKOFF_S * (attempt + 1))
        except Exception:
            return None
    return None


def about(headline: str, name: str, ticker: str | None) -> bool:
    """Is this headline about the company, or merely near it?

    GDELT matches the article body, so a query for "Advanced Micro Devices"
    returned NVIDIA's chief executive resigning, a chip-smuggling prosecution
    in Taipei, and "On Wall Street, stocks sway as market aims for a winning
    week" - all genuinely mentioning AMD somewhere, none of them about AMD.
    Putting those on AMD's page would be worse than having no news at all,
    because a reader cannot tell which rows are wrong.

    The test is the same one the extractor uses on a sentence: the subject has
    to be named where the claim is made. Here that is the headline.
    """
    h = headline or ""
    low = h.lower()
    if not low:
        return False
    base = clean(name).lower()

    # Substring matching put "he broke his arm in the warehouse" on Arm
    # Holdings' page. Word boundaries, and a name that is also an ordinary
    # English word never qualifies on its own however it is spelled.
    def word(term: str, hay: str) -> bool:
        return bool(term) and re.search(rf"\b{re.escape(term)}\b", hay) is not None

    if base and base not in TOO_GENERIC and len(base) >= 4 and word(base, low):
        return True

    # A multi-word name also counts on its distinctive first word: "Cerence
    # posts a loss" is about Cerence.
    head = base.split()[0] if base else ""
    if head and head not in TOO_GENERIC and len(head) > 4 and word(head, low):
        return True

    # Tickers are short enough to collide with ordinary words, so they only
    # count written as a ticker - capitals, in the original casing.
    if ticker and len(ticker) >= 3 and word(ticker, h):
        return True
    return False


def seen(s):
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def purge(conn, apply: bool) -> int:
    """Re-test stored headlines against the current subject filter.

    The filter was added after the first rows were already in, and a rule that
    only applies to what we fetch next is not a rule. Same discipline as
    scripts/retract.py: re-test, withdraw, never add.
    """
    cur = conn.cursor()
    # Only press rows are re-tested. An EDGAR filing is filed BY the company,
    # so "does the headline name it" is the wrong question to ask of one:
    # "8-K: Results of operations" names no one and is still unambiguously
    # that filer's. Judging it by this filter would delete the most reliable
    # rows in the table.
    cur.execute("""SELECT n.id, n.headline, e.common_name, li.ticker
                   FROM company_news n
                   JOIN entity e ON e.id = n.entity_id
                   LEFT JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
                   WHERE n.source_id = %s""", (SOURCE_ID,))
    doomed = [(nid, head, who) for nid, head, who, tick in cur.fetchall()
              if not about(head, who, tick)]
    if not doomed:
        print("  every stored headline still names its company")
        return 0
    print(f"  {len(doomed)} headlines mention a company without being about it:")
    for _, head, who in doomed[:10]:
        print(f"    [{who[:22]:24}] {(head or '')[:66]}")
    if len(doomed) > 10:
        print(f"    ... and {len(doomed) - 10} more")
    if not apply:
        print("\n  --apply to remove them")
        return 0
    cur.execute("DELETE FROM company_news WHERE id = ANY(%s)", ([d[0] for d in doomed],))
    gone = cur.rowcount
    conn.commit()
    cur.execute("SELECT count(*) FROM company_news")
    print(f"\n  removed {gone}; {cur.fetchone()[0]} headlines remain")
    return 0


def main():
    argv = sys.argv[1:]
    if "--purge" in argv:
        return purge(psycopg.connect(DSN), "--apply" in argv)
    limit = 40
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    days = 14
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
    everyone = "--all" in argv
    mics = None
    if "--mic" in argv:
        mics = [m.strip().upper() for m in argv[argv.index("--mic") + 1].split(",") if m.strip()]

    conn = psycopg.connect(DSN)
    cur = conn.cursor()

    scope = "" if everyone else """
        AND (e.id IN (SELECT from_entity_id FROM dependency_edge)
          OR e.id IN (SELECT to_entity_id   FROM dependency_edge))"""
    if mics:
        scope += "\n        AND li.exchange_mic = ANY(%s)" % ("'{" + ",".join(mics) + "}'",)
    cur.execute(f"""
        SELECT e.id, e.common_name, li.ticker
        FROM entity e
        JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
        LEFT JOIN company_news_cursor c ON c.entity_id = e.id
        WHERE TRUE {scope}
        ORDER BY c.last_fetched NULLS FIRST, e.common_name
        LIMIT %s""", (limit,))
    todo = cur.fetchall()
    if not todo:
        print("  nothing to refresh")
        return 0

    print(f"  {len(todo)} companies, one query every {GAP_S:.0f}s "
          f"(~{len(todo) * GAP_S / 60:.0f} min)")
    added = skipped = failed = 0
    for i, (eid, name, ticker) in enumerate(todo):
        q = build_query(name, ticker)
        if not q:
            skipped += 1
            continue
        if i:
            time.sleep(GAP_S)
        arts = fetch(q, days)
        if arts is None:
            failed += 1
            print(f"    ! {name[:34]:36} rate limited")
            continue

        n = 0
        off_topic = 0
        for a in arts:
            url_ = (a.get("url") or "")[:2000]
            if not url_:
                continue
            if not about(a.get("title"), name, ticker):
                off_topic += 1
                continue
            cur.execute("""
                INSERT INTO company_news (entity_id, source_id, url, headline,
                    domain, language, published_at, query_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (entity_id, url) DO NOTHING""",
                (eid, SOURCE_ID, url_, (a.get("title") or "")[:400] or None,
                 (a.get("domain") or "")[:120] or None,
                 (a.get("language") or "")[:40] or None,
                 seen(a.get("seendate")), QUERY_ID))
            n += cur.rowcount
        cur.execute("""
            INSERT INTO company_news_cursor (entity_id, last_fetched, found)
            VALUES (%s, now(), %s)
            ON CONFLICT (entity_id) DO UPDATE
               SET last_fetched = now(), found = EXCLUDED.found""", (eid, len(arts)))
        conn.commit()
        added += n
        if n or off_topic:
            print(f"    {name[:34]:36} +{n:<3} kept of {len(arts)} "
                  f"({off_topic} mentioned it without being about it)")

    cur.execute("SELECT count(*), count(DISTINCT entity_id) FROM company_news")
    total, covered = cur.fetchone()
    print(f"\n  {added} new headlines, {skipped} names too generic to query, "
          f"{failed} rate limited")
    print(f"  company_news: {total} rows across {covered} companies")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
