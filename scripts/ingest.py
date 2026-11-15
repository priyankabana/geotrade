#!/usr/bin/env python3
"""Fetch real annual filings and turn them into chunks with character offsets.

    python3 -I scripts/ingest.py [limit]

Writes `document`, `section` and `chunk`. Character offsets are preserved end to
end, because the whole product rests on being able to point at the exact sentence
in the exact document.
"""
import gzip, hashlib, html, os, re, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import psycopg

UA    = os.environ.get("ATLAS_UA", "Atlas Capstone Research contact@example.com")
DSN   = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
DEFAULT_LIMIT = 250
CHUNK_CHARS, OVERLAP = 4800, 600

# Sectors where suppliers name their customers. This is the inversion, as a filter.
SECTORS = ('SEMI_DEVICES','SEMI_EQUIP','ELECTRONIC_COMPONENTS','COMPUTER_HARDWARE',
           'COMMS_EQUIPMENT','INSTRUMENTS','ELECTRICAL_EQUIP','AUTO_COMPONENTS',
           'MACHINERY','AEROSPACE_DEFENSE','SPECIALTY_CHEM','METALS_STEEL')

_lock, _next, RATE = threading.Lock(), [0.0], 8.0

def _throttle():                      # SEC fair access: stay under 10 req/s
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _next[0] - now)
        _next[0] = max(now, _next[0]) + 1.0 / RATE
    if wait: time.sleep(wait)

def get(url, binary=False):
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = r.read()
                if r.headers.get("Content-Encoding") == "gzip": d = gzip.decompress(d)
                return d if binary else d.decode("utf-8", "replace")
        except Exception:
            if a == 2: raise
            time.sleep(1.5 * (a + 1))

def strip_html(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s).replace("\xa0", " "))

HEADINGS = [("1", r"business"), ("1A", r"risk\s+factors"), ("1B", r"unresolved"),
            ("2", r"propert"), ("3", r"legal\s+proceed"), ("4", r"mine\s+safety"),
            ("5", r"market\s+for"), ("6", r"(selected|reserved)"),
            ("7", r"management.s\s+discussion"), ("7A", r"quantitative"),
            ("8", r"financial\s+statements\s+and\s+supplement"),
            ("9", r"changes\s+in\s+and\s+disagree"), ("9A", r"controls\s+and\s+procedures")]

def segment(text):
    """Item number plus expected heading, chosen backwards so the table of
    contents (every Item within a few thousand chars) loses to the real body."""
    pos = {it: [m.start() for m in re.finditer(rf"(?is)\bitem\s*{it}\s*[\.\:\-]?\s*{h}", text)]
           for it, h in HEADINGS}
    chosen, limit = {}, len(text)
    for it, _ in reversed(HEADINGS):
        c = [p for p in pos[it] if p < limit]
        if c: chosen[it] = c[-1]; limit = c[-1]
    keys = sorted(chosen, key=lambda k: chosen[k])
    return {k: (chosen[k], chosen[keys[i+1]] if i+1 < len(keys) else len(text))
            for i, k in enumerate(keys)}

NOTE = re.compile(r"(?i)(concentrations?\s+of\s+(credit\s+)?risk|major\s+customers?"
                  r"|significant\s+customers?|segment\s+(information|reporting))")
TARGET = ("1", "1A", "7")

def pick_spans(text):
    sp = segment(text)
    want = [sp[i] for i in TARGET if i in sp]
    ok = len(want) == 3 and all(e - s > 4000 for s, e in want)
    if not ok:
        want = [(0, min(len(text), 400_000))]
    for m in NOTE.finditer(text):
        want.append((max(0, m.start() - 2500), min(len(text), m.start() + 6000)))
    want.sort()
    merged = []
    for s, e in want:
        if merged and s <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], e)
        else: merged.append([s, e])
    return merged, ok, (sp if ok else {})

def main(limit=None):
    LIMIT = DEFAULT_LIMIT if limit is None else limit
    conn = psycopg.connect(DSN, autocommit=False)
    cur = conn.cursor()
    cur.execute("""
        SELECT e.id, e.legal_name, i.value, li.company_uid
        FROM entity e
        JOIN entity_identifier i ON i.entity_id = e.id AND i.scheme = 'CIK'
        JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
        WHERE e.atlas_sector = ANY(%s)
          AND NOT EXISTS (SELECT 1 FROM document d WHERE d.entity_id = e.id)
        ORDER BY e.common_name
        LIMIT %s
    """, (list(SECTORS), LIMIT))
    targets = cur.fetchall()
    print(f"  {len(targets)} companies to ingest")

    results, lock = [], threading.Lock()
    done = [0]

    def work(t):
        eid, name, cik, uid = t
        try:
            sub = __import__("json").loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
            r = sub["filings"]["recent"]
            idx = next((i for i, f in enumerate(r["form"]) if f in ("10-K", "20-F")), None)
            if idx is None: return
            acc = r["accessionNumber"][idx].replace("-", "")
            doc = r["primaryDocument"][idx]
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
            raw = get(url, binary=True)
            text = strip_html(raw.decode("utf-8", "replace"))
            if len(text) < 20000: return
            spans, seg_ok, items = pick_spans(text)
            with lock:
                results.append(dict(eid=eid, name=name, uid=uid, cik=cik, text=text,
                                    spans=spans, seg_ok=seg_ok, items=items,
                                    form=r["form"][idx],
                                    acc=r["accessionNumber"][idx],
                                    filed=r["filingDate"][idx],
                                    period=r["reportDate"][idx] or None,
                                    url=url, sha=hashlib.sha256(raw).hexdigest(),
                                    nbytes=len(raw)))
                done[0] += 1
                if done[0] % 25 == 0: print(f"    [{time.strftime('%H:%M:%S')}] fetched {done[0]}", flush=True)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(work, targets))
    print(f"  fetched {len(results)} filings; writing to database")

    nd = ns = nc = 0
    for r in results:
        now = datetime.now(timezone.utc)
        cur.execute("""
            INSERT INTO document (entity_id, doc_type, period_end, filed_at_utc,
                filed_at_local, filed_tz, source_id, external_id, landing_url,
                primary_doc_url, mime, language, is_amendment, retrieved_at_utc,
                sha256, bytes)
            VALUES (%s,%s,%s,%s,%s,'America/New_York','sec-edgar-archive',%s,%s,%s,
                    'text/html','en',false,%s,%s,%s)
            ON CONFLICT (source_id, external_id) DO NOTHING
            RETURNING id
        """, (r["eid"], r["form"], r["period"], f"{r['filed']}T00:00:00+00:00",
              f"{r['filed']} 00:00:00", r["acc"], r["url"], r["url"],
              now, r["sha"], r["nbytes"]))
        got = cur.fetchone()
        if not got: continue
        did = got[0]; nd += 1

        for code, (s, e) in (r["items"] or {}).items():
            cur.execute("""INSERT INTO section (document_id, item_code, title, kind,
                           char_start, char_end) VALUES (%s,%s,%s,'item',%s,%s)""",
                        (did, code, f"Item {code}", s, e))
            ns += 1

        ordinal = 0
        for s, e in r["spans"]:
            seg = r["text"][s:e]
            step = CHUNK_CHARS - OVERLAP
            for off in range(0, max(len(seg), 1), step):
                body = seg[off:off + CHUNK_CHARS]
                if len(body) < 200: continue
                cs = s + off
                cur.execute("""INSERT INTO chunk (document_id, ordinal, char_start,
                               char_end, text, sha256)
                               VALUES (%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (document_id, ordinal) DO NOTHING""",
                            (did, ordinal, cs, cs + len(body), body,
                             hashlib.sha256(body.encode()).hexdigest()))
                ordinal += 1; nc += 1
        if nd % 25 == 0: conn.commit()
    conn.commit()
    print(f"  documents {nd}   sections {ns}   chunks {nc}")
    cur.execute("SELECT count(*) FROM document"); print(f"  documents in db: {cur.fetchone()[0]}")
    cur.execute("SELECT count(*) FROM chunk");    print(f"  chunks in db:    {cur.fetchone()[0]}")
    conn.close()

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
