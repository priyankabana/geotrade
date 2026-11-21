#!/usr/bin/env python3
"""Pull the text of 10-Q, 10-K and 8-K filings from SEC EDGAR.

The news table holds headlines, and a headline is a thin thing to judge a
company on. This fetches the filings themselves and keeps the sections that
carry meaning: management's own discussion, the risk factors, and the results
announcement attached to an 8-K.

Why EDGAR and not a terminal. Transcripts and filings are sold by several
vendors whose licences forbid redistributing what you pull. This project's
claim is that every figure traces to a public document anyone can open, so
the source has to be the regulator's own copy. EDGAR permits automated access
at ten requests a second with an identifying User-Agent, and that is the whole
arrangement.

    python3 -I scripts/ingest_filings.py --forms 10-Q,10-K --limit 50
    python3 -I scripts/ingest_filings.py --forms 8-K --days 30 --calendar
"""
import html
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
UA = os.environ.get("ATLAS_CONTACT",
                    "AtlasResearch/0.2 (academic project; contact via repository)")

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

WORKERS = int(os.environ.get("EDGAR_WORKERS", "10"))
FILINGS_PER_COMPANY = int(os.environ.get("EDGAR_FILINGS_PER_COMPANY", "4"))
# Two passes can run at once over different slices of the universe; the pacer
# is tunable so their combined request rate still fits inside EDGAR's ten a
# second rather than each assuming it has the whole budget.
MIN_GAP_S = float(os.environ.get("EDGAR_MIN_GAP_S", "0.12"))
MAX_SECTION_CHARS = 60_000

_gate = threading.Lock()
_next_at = [0.0]


def paced(url: str, tries: int = 3):
    """One request, never faster than the shared pacer allows."""
    for attempt in range(tries):
        with _gate:
            wait = _next_at[0] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _next_at[0] = time.monotonic() + MIN_GAP_S
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept-Encoding": "gzip, deflate",
                "Host": url.split("/")[2]})
            with urllib.request.urlopen(req, timeout=40) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 403) and attempt + 1 < tries:
                time.sleep(2.0 * (attempt + 1))
                continue
            return None
        except Exception:
            if attempt + 1 < tries:
                time.sleep(1.0)
                continue
            return None
    return None


# ------------------------------------------------------------------ text ---
SCRIPTY = re.compile(r"(?is)<(script|style|xbrl)[^>]*>.*?</\1>")
TAGS = re.compile(r"(?s)<[^>]+>")
SPACE = re.compile(r"[ \t\xa0]+")
BLANKS = re.compile(r"\n{3,}")


def to_text(raw: bytes) -> str:
    """HTML to readable prose, keeping paragraph breaks.

    Filings are heavily nested tables, so block tags become newlines before
    the rest is stripped; otherwise every sentence runs into the next and the
    section headings become impossible to find.
    """
    s = raw.decode("utf-8", errors="ignore")
    s = SCRIPTY.sub(" ", s)
    s = re.sub(r"(?i)</(p|div|tr|h[1-6]|li|table)>", "\n", s)
    s = re.sub(r"(?i)<br[^>]*>", "\n", s)
    s = TAGS.sub(" ", s)
    s = html.unescape(s)
    s = SPACE.sub(" ", s)
    s = "\n".join(line.strip() for line in s.split("\n"))
    return BLANKS.sub("\n\n", s).strip()


# Headings as filers actually write them: the numbering is stable, the wording
# drifts, and the table of contents repeats every heading once before the body.
SECTIONS = [
    ("risk_factors", re.compile(r"(?im)^\s*item\s*1a\b[.\s\-–—:]*risk\s+factors")),
    # Filers write a curly apostrophe in "Management's" far more often than a
    # straight one, and the heading frequently wraps onto the next line after
    # the item number. Both were costing us every MD&A section.
    ("mdna", re.compile(
        r"(?im)^\s*item\s*[27]\b[.\s\-–—:]*\n?\s*management[’'ʼ]?s?\s+discussion")),
    ("results", re.compile(r"(?im)^\s*item\s*2\.02\b[.\s\-–—:]*result")),
]
NEXT_ITEM = re.compile(r"(?im)^\s*item\s*\d+[A-Za-z]?(\.\d+)?\b")


def split_sections(text: str) -> list:
    """Return (name, heading, body) for the sections we care about.

    The last occurrence of a heading is used, not the first: the first is
    almost always the table of contents entry, which is one line long.
    """
    out = []
    for name, rx in SECTIONS:
        starts = [m for m in rx.finditer(text)]
        if not starts:
            continue
        m = starts[-1]
        after = text[m.end():]
        nxt = NEXT_ITEM.search(after)
        body = after[:nxt.start()] if nxt else after
        body = body.strip()
        if len(body) < 400:                 # a stub or a stray index entry
            continue
        out.append((name, m.group(0).strip()[:200], body[:MAX_SECTION_CHARS]))
    return out


# -------------------------------------------------------------- calendar ---
DATE_NEAR = re.compile(
    r"(?i)\b(?:on|for)\s+((?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},\s+20\d\d)")
PERIOD = re.compile(r"(?i)\b(first|second|third|fourth)\s+quarter\b|\bQ([1-4])\b|"
                    r"\bfull[- ]year\b")


def calendar_from(text: str) -> tuple:
    """A reporting date a company announced in its own 8-K, if it gave one."""
    m = DATE_NEAR.search(text[:6000])
    if not m:
        return None, ""
    try:
        when = datetime.strptime(m.group(1), "%B %d, %Y").date()
    except ValueError:
        return None, ""
    p = PERIOD.search(text[:6000])
    return when, (p.group(0) if p else "")


# ------------------------------------------------------------------ main ---
def recent(cik: int, forms: set, since: str) -> list:
    raw = paced(SUBMISSIONS.format(cik=cik))
    if not raw:
        return []
    import json
    r = (json.loads(raw).get("filings") or {}).get("recent") or {}
    names = r.get("form") or []
    out = []
    for i, form in enumerate(names):
        if form not in forms:
            continue
        filed = (r.get("filingDate") or [None] * len(names))[i]
        if not filed or filed < since:
            continue
        acc = (r.get("accessionNumber") or [""] * len(names))[i].replace("-", "")
        doc = (r.get("primaryDocument") or [""] * len(names))[i]
        if not acc or not doc:
            continue
        out.append({"accession": acc, "form": form, "filed": filed,
                    "period": (r.get("reportDate") or [None] * len(names))[i] or None,
                    "url": ARCHIVE.format(cik=cik, acc=acc, doc=doc)})
    return out


def main() -> int:
    argv = sys.argv[1:]
    forms = set((argv[argv.index("--forms") + 1] if "--forms" in argv
                 else "10-Q,10-K").split(","))
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 400
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 40
    want_calendar = "--calendar" in argv
    offset = int(argv[argv.index("--offset") + 1]) if "--offset" in argv else 0
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    conn = psycopg.connect(DSN, row_factory=dict_row)
    cur = conn.cursor()
    cur.execute("""
        SELECT e.id, e.common_name, ei.value AS cik
        FROM entity e
        JOIN entity_identifier ei ON ei.entity_id = e.id AND ei.scheme = 'CIK'
        WHERE e.id IN (SELECT from_entity_id FROM dependency_edge
                       UNION SELECT to_entity_id FROM dependency_edge)
        ORDER BY e.common_name
        LIMIT %s OFFSET %s""", (limit, offset))
    todo = cur.fetchall()
    if not todo:
        print("  no companies with a CIK in scope")
        return 0

    print(f"  {len(todo)} companies, forms {sorted(forms)}, filed since {since}")
    t0 = time.monotonic()
    sections = events = 0
    done_n = [0]

    def work(row):
        """Index lookup AND document fetch, both inside the worker.

        The first version only parallelised the index call and then downloaded
        the documents one at a time in the consumer loop. Since a 10-K is a
        few hundred kilobytes and the index is a few, that left the slow part
        entirely sequential: measured at 3.9 minutes per company. Fetching and
        parsing here, and handing finished text back, is the whole fix.
        """
        try:
            filings = recent(int(row["cik"]), forms, since)
        except (TypeError, ValueError):
            return row, []
        done = []
        for f in filings[:FILINGS_PER_COMPANY]:
            raw = paced(f["url"])
            if not raw:
                continue
            text = to_text(raw)
            done.append((f, split_sections(text), text[:6000]))
        return row, done

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for row, filings in pool.map(work, todo):
            for f, parsed, head_text in filings:
                for name, heading, body in parsed:
                    cur.execute("""
                        INSERT INTO filing_section
                          (entity_id, accession, form, filed_date, period_end,
                           section, heading, body, char_count, source_url)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (accession, section, heading) DO NOTHING""",
                        (row["id"], f["accession"], f["form"], f["filed"],
                         f["period"], name, heading, body, len(body), f["url"]))
                    sections += cur.rowcount
                if want_calendar and f["form"].startswith("8-K"):
                    when, period = calendar_from(head_text)
                    if when:
                        cur.execute("""
                            INSERT INTO earnings_event
                              (entity_id, event_date, period_label, status,
                               source_url, source_form)
                            VALUES (%s,%s,%s,'scheduled',%s,%s)
                            ON CONFLICT (entity_id, event_date, period_label)
                            DO NOTHING""",
                            (row["id"], when, period, f["url"], f["form"]))
                        events += cur.rowcount
            conn.commit()
            done_n[0] += 1
            print(f"    [{done_n[0]:>3}/{len(todo)}] {row['common_name'][:32]:34} "
                  f"{len(filings)} filings  {time.monotonic() - t0:6.0f}s elapsed",
                  flush=True)

    print(f"\n  {sections} sections, {events} calendar entries "
          f"in {time.monotonic() - t0:.0f}s")
    cur.execute("SELECT section, count(*) FROM filing_section GROUP BY 1 ORDER BY 2 DESC")
    for r in cur.fetchall():
        print(f"    {r['section']:16} {r['count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
