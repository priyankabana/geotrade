#!/usr/bin/env python3
"""Company news from the source: SEC EDGAR current reports.

Why this exists alongside the GDELT ingester. GDELT indexes press coverage and
permits one request every five seconds; a pass over 138 US companies measured
at 88 seconds each once their throttle engaged, which is three hours. EDGAR is
the issuer's own filing system, it publishes a documented JSON API, and its
fair-access policy permits ten requests a second. The same 138 companies land
in well under a minute.

What we store is also better evidence. An 8-K is a *current report*: the law
requires it within four business days of a material event, and the item number
says what kind of event it was. "Item 5.02" is not a journalist's reading of a
leadership change, it is the company stating one happened. That is the same
standard the rest of this project holds itself to - a claim, with the document
it came from behind it.

Concurrency: threads, not processes. Every one of these requests spends its
life waiting on a socket, so the GIL is released the entire time and processes
would buy nothing but memory and startup cost. The worker count is set so the
request rate stays inside EDGAR's published limit, not so it saturates the
machine.

    python3 -I scripts/ingest_edgar_news.py --mic XNAS,XNYS
    python3 -I scripts/ingest_edgar_news.py --all --days 120
"""
import json, os, re, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
UA = os.environ.get("ATLAS_CONTACT",
                    "AtlasResearch/0.2 (academic project; contact via repository)")
SOURCE_ID = "sec-edgar"
QUERY_ID = "edgar-submissions-1.0"

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

# EDGAR's fair-access policy is ten requests a second from one client. Eight
# workers with a shared 0.11s pacer keeps us under it with room to spare, and
# the pacer is what actually enforces the rate - worker count alone does not,
# because a fast response immediately frees a worker to fire again.
WORKERS = 8
MIN_GAP_S = 0.11

# The item number is the filing's own statement of what kind of event this was.
# Only the ones that are news to a reader are listed; the rest fall back to the
# form's own name. Source: SEC Form 8-K, items 1.01-9.01.
ITEMS = {
    "1.01": "Entered a material agreement",
    "1.02": "Terminated a material agreement",
    "1.03": "Bankruptcy or receivership",
    "1.05": "Material cybersecurity incident",
    "2.01": "Completed an acquisition or disposition of assets",
    "2.02": "Results of operations and financial condition",
    "2.03": "Took on a material financial obligation",
    "2.04": "Triggered an obligation to accelerate a debt",
    "2.05": "Committed to an exit or disposal plan",
    "2.06": "Material impairment",
    "3.01": "Delisting notice or failure to satisfy a listing rule",
    "3.02": "Unregistered sale of equity securities",
    "3.03": "Material modification to the rights of security holders",
    "4.01": "Changed its accountant",
    "4.02": "Previously issued financial statements can no longer be relied on",
    "5.01": "Change in control",
    "5.02": "Departure or appointment of directors or officers",
    "5.03": "Amended its charter or bylaws",
    "5.07": "Submitted matters to a shareholder vote",
    "7.01": "Regulation FD disclosure",
    "8.01": "Other material event",
    "9.01": "Financial statements and exhibits",
}

FORMS = {
    "8-K": "Current report", "8-K/A": "Current report (amended)",
    "6-K": "Foreign issuer report", "10-Q": "Quarterly report",
    "10-K": "Annual report", "10-K/A": "Annual report (amended)",
    "S-1": "Registration statement", "424B4": "Prospectus",
    "SC 13D": "Activist stake disclosed", "SC 13G": "Passive stake disclosed",
    "DEF 14A": "Proxy statement", "425": "Merger communication",
}

# Which forms carry news. A Form 4 (an insider sold 300 shares) is filed
# hundreds of times a year and would drown everything that matters.
NEWSWORTHY = set(FORMS) | {"8-K", "6-K"}

_gate = threading.Lock()
_next_at = [0.0]


def paced_get(url: str, tries: int = 3):
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
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                return json.loads(raw)
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


def headline(form: str, items: str, desc: str) -> str:
    """What this filing says happened, in a sentence a reader can scan.

    The description the filer typed is used when it is a real one. Filers
    routinely put the form number in that field instead ("8-K"), which tells
    the reader nothing they cannot see already, so those are discarded.
    """
    codes = [c.strip() for c in re.split(r"[,;]", items or "") if c.strip()]
    said = [ITEMS[c] for c in codes if c in ITEMS and c != "9.01"]
    if said:
        return said[0] if len(said) == 1 else said[0] + f" (+{len(said) - 1} more)"
    d = (desc or "").strip()
    if d and not re.fullmatch(r"(?i)form\s*[\w/\-\. ]{0,10}", d) and len(d) > 8:
        return d[:200]
    return FORMS.get(form, form)


def recent(cik: int, since: str):
    """The company's own filings, newest first, trimmed to what is news."""
    data = paced_get(SUBMISSIONS.format(cik=cik))
    if not data:
        return None
    r = (data.get("filings") or {}).get("recent") or {}
    out = []
    forms = r.get("form") or []
    for i, form in enumerate(forms):
        if form not in NEWSWORTHY:
            continue
        filed = (r.get("filingDate") or [None] * len(forms))[i]
        if not filed or filed < since:
            continue
        acc = (r.get("accessionNumber") or [""] * len(forms))[i].replace("-", "")
        doc = (r.get("primaryDocument") or [""] * len(forms))[i]
        if not acc:
            continue
        url = ARCHIVE.format(cik=cik, acc=acc, doc=doc or "")
        out.append({
            "url": url,
            "headline": headline(form,
                                 (r.get("items") or [""] * len(forms))[i],
                                 (r.get("primaryDocDescription") or [""] * len(forms))[i]),
            "form": form,
            "filed": filed,
        })
    return out


def main():
    argv = sys.argv[1:]
    days = 120
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
    mics = ["XNAS", "XNYS"]
    if "--mic" in argv:
        mics = [m.strip().upper() for m in argv[argv.index("--mic") + 1].split(",") if m.strip()]
    everyone = "--all" in argv
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    conn = psycopg.connect(DSN)
    c = conn.cursor()
    scope = "" if everyone else """
        AND (e.id IN (SELECT from_entity_id FROM dependency_edge)
          OR e.id IN (SELECT to_entity_id   FROM dependency_edge))"""
    c.execute(f"""
        SELECT e.id, e.common_name, li.ticker, ei.value
        FROM entity e
        JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
        JOIN entity_identifier ei ON ei.entity_id = e.id AND ei.scheme = 'CIK'
        WHERE li.exchange_mic = ANY(%s) {scope}
        ORDER BY e.common_name""", (mics,))
    todo = c.fetchall()
    if not todo:
        print("  nothing to fetch")
        return 0

    print(f"  {len(todo)} companies, {WORKERS} workers, "
          f"<= {1 / MIN_GAP_S:.0f} req/s (EDGAR permits 10), filings since {since}")
    t0 = time.monotonic()

    def work(row):
        eid, name, ticker, cik = row
        try:
            return eid, name, ticker, recent(int(cik), since)
        except (TypeError, ValueError):
            return eid, name, ticker, None

    added = empty = failed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for eid, name, ticker, items in pool.map(work, todo):
            if items is None:
                failed += 1
                print(f"    ! {name[:36]:38} could not be read")
                continue
            if not items:
                empty += 1
                continue
            n = 0
            for it in items:
                c.execute("""
                    INSERT INTO company_news
                        (entity_id, source_id, url, headline, domain, language,
                         published_at, query_id)
                    VALUES (%s, %s, %s, %s, 'sec.gov', 'English', %s, %s)
                    ON CONFLICT (entity_id, url) DO NOTHING""",
                          (eid, SOURCE_ID, it["url"], f"{it['form']}: {it['headline']}",
                           it["filed"], QUERY_ID))
                n += c.rowcount
            conn.commit()
            added += n
            if n:
                print(f"    {name[:36]:38} +{n:<4} ({len(items)} filings since {since})")

    c.execute("""SELECT count(*) AS h, count(DISTINCT entity_id) AS co
                 FROM company_news WHERE source_id = %s""", (SOURCE_ID,))
    got = c.fetchone()
    print(f"\n  {added} new filings in {time.monotonic() - t0:.0f}s "
          f"({empty} companies had none since {since}, {failed} unreadable)")
    print(f"  EDGAR rows now: {got[0]} across {got[1]} companies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
