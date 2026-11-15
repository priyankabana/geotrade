#!/usr/bin/env python3
"""Attach SEC CIKs to the US companies already in the database.

The vendor market files carry no CIK, so nothing in the graph can be matched to
an EDGAR filing yet. SEC publishes ticker -> CIK itself; this joins on ticker for
the US exchanges and writes entity_identifier rows.
"""
import gzip, json, os, sys, urllib.request
import psycopg

UA  = os.environ.get("ATLAS_UA", "Atlas Capstone Research contact@example.com")
DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
US_MICS = ("XNAS", "XNYS", "XASE")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            d = gzip.decompress(d)
    return d.decode("utf-8", "replace")


def main():
    print("  fetching SEC ticker -> CIK map")
    data = json.loads(fetch("https://www.sec.gov/files/company_tickers_exchange.json"))
    by_ticker = {}
    for cik, _name, tk, _ex in data["data"]:
        if tk:
            by_ticker.setdefault(tk.upper(), str(cik).zfill(10))
    print(f"  {len(by_ticker):,} tickers from SEC")

    with psycopg.connect(DSN, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT li.entity_id, li.ticker
            FROM entity_listing li
            WHERE li.exchange_mic = ANY(%s)
              AND NOT EXISTS (SELECT 1 FROM entity_identifier i
                              WHERE i.entity_id = li.entity_id AND i.scheme = 'CIK')
        """, (list(US_MICS),))
        rows = cur.fetchall()
        print(f"  {len(rows):,} US listings without a CIK")

        hit = 0
        for eid, ticker in rows:
            cik = by_ticker.get((ticker or "").upper())
            if not cik:
                continue
            cur.execute("""
                INSERT INTO entity_identifier
                    (entity_id, scheme, value, source_id, source_url, collected_by, collected_on)
                VALUES (%s,'CIK',%s,'sec-cte',
                        'https://www.sec.gov/files/company_tickers_exchange.json',
                        'link_cik.py', CURRENT_DATE)
                ON CONFLICT DO NOTHING
            """, (eid, cik))
            hit += 1
        conn.commit()
        print(f"  matched {hit:,} companies to a CIK")

        cur.execute("SELECT count(*) FROM entity_identifier WHERE scheme='CIK'")
        print(f"  CIKs in database now: {cur.fetchone()[0]:,}")


if __name__ == "__main__":
    main()
