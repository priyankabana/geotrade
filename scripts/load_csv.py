#!/usr/bin/env python3
"""Load the collection CSVs into Postgres. Idempotent — safe to re-run.

    make load          # or: python3 -I scripts/load_csv.py

Loads the REFERENCE layer only (companies, aliases, sectors, exchanges). The
evidence layer is populated by the extraction pipeline, not by hand.
"""
import csv, glob, os, sys, datetime

try:
    import psycopg
except ImportError:
    sys.exit("pip install 'psycopg[binary]' first (see requirements.txt)")

DSN  = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def rows(pattern):
    for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                yield path, r

def nn(v):
    v = (v or "").strip()
    return v or None

def num(v):
    v = (v or "").strip()
    try:    return float(v)
    except ValueError: return None

def main():
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        # ---- sectors
        n = 0
        for _p, r in rows("data/reference/sectors.csv"):
            cur.execute("""
                INSERT INTO atlas_sector (code,name,parent_code,definition,maps_sic)
                VALUES (%s,%s,NULL,%s,%s)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name,
                    definition=EXCLUDED.definition, maps_sic=EXCLUDED.maps_sic
            """, (r["atlas_sector_code"], r["name"], r["definition"],
                  [s for s in (r.get("maps_sic") or "").split("|") if s]))
            n += 1
        # parents second, so the self-FK always resolves
        for _p, r in rows("data/reference/sectors.csv"):
            if nn(r.get("parent_code")):
                cur.execute("INSERT INTO atlas_sector (code,name,definition) VALUES (%s,%s,%s) "
                            "ON CONFLICT (code) DO NOTHING",
                            (r["parent_code"], r["parent_code"].replace("_", " ").title(), "Parent group."))
                cur.execute("UPDATE atlas_sector SET parent_code=%s WHERE code=%s",
                            (r["parent_code"], r["atlas_sector_code"]))
        conn.commit(); print(f"  atlas_sector      {n}")

        # ---- exchanges. Seeded from a table, then any MIC present in the data but
        # missing here is auto-created, so a new market never fails the load.
        EXCH = {
            "XNAS":("Nasdaq Stock Market","US","America/New_York","USD"),
            "XNYS":("New York Stock Exchange","US","America/New_York","USD"),
            "XASE":("NYSE American","US","America/New_York","USD"),
            "TXSE":("Texas Stock Exchange","US","America/Chicago","USD"),
            "XNSE":("National Stock Exchange of India","IN","Asia/Kolkata","INR"),
            "XBOM":("BSE Limited","IN","Asia/Kolkata","INR"),
            "XLON":("London Stock Exchange","GB","Europe/London","GBP"),
            "XASX":("Australian Securities Exchange","AU","Australia/Sydney","AUD"),
            "XTSE":("Toronto Stock Exchange","CA","America/Toronto","CAD"),
            "XTSX":("TSX Venture Exchange","CA","America/Toronto","CAD"),
            "XCNQ":("Canadian Securities Exchange","CA","America/Toronto","CAD"),
            "XETR":("Xetra","DE","Europe/Berlin","EUR"),
            "XFRA":("Frankfurt Stock Exchange","DE","Europe/Berlin","EUR"),
            "XSTU":("Boerse Stuttgart","DE","Europe/Berlin","EUR"),
            "XBER":("Boerse Berlin","DE","Europe/Berlin","EUR"),
            "XMUN":("Boerse Muenchen","DE","Europe/Berlin","EUR"),
            "XHAM":("Boerse Hamburg","DE","Europe/Berlin","EUR"),
            "XDUS":("Boerse Duesseldorf","DE","Europe/Berlin","EUR"),
            "XGAT":("Tradegate Exchange","DE","Europe/Berlin","EUR"),
        }
        present = {(r.get("exchange_mic") or "").strip()
                   for _p, r in rows("data/companies/*.csv")}
        for mic in sorted(m for m in present if m):
            name, country, tz, ccy = EXCH.get(mic, (mic, "", "UTC", ""))
            if mic not in EXCH:
                print(f"    ! unknown MIC {mic} - created as a stub, fill it in docs/data-model.md")
            cur.execute("INSERT INTO exchange (mic,name,country,timezone,currency) "
                        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (mic) DO NOTHING",
                        (mic, name, country or "ZZ", tz, ccy or "XXX"))
        conn.commit(); print(f"  exchange          {len(present)}")

        # ---- companies
        uid2id, n, skipped = {}, 0, 0
        for _p, r in rows("data/companies/*.csv"):
            uid = r["company_uid"].strip()
            if not uid:
                skipped += 1; continue
            cur.execute("""
                INSERT INTO entity (legal_name,common_name,country_incorporation,country_hq,
                                    atlas_sector,fiscal_year_end,status,website,ir_url,description)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (r["legal_name"], r["common_name"],
                  nn(r["country_incorporation"]) or "US", nn(r["country_hq"]),
                  nn(r["atlas_sector"]), nn(r["fiscal_year_end"]),
                  nn(r["status"]) or "active", nn(r["website"]), nn(r["ir_url"]),
                  nn(r["description"])))
            eid = cur.fetchone()[0]
            uid2id[uid] = eid

            cur.execute("""INSERT INTO entity_listing
                (entity_id,exchange_mic,ticker,company_uid,is_primary,currency)
                VALUES (%s,%s,%s,%s,true,%s) ON CONFLICT (company_uid) DO NOTHING""",
                (eid, r["exchange_mic"], r["ticker"], uid, nn(r["currency"])))

            for scheme, col in (("CIK","cik"),("LEI","lei"),("ISIN","isin"),
                                ("SEDOL","sedol"),("CUSIP","cusip"),("FIGI","figi")):
                if nn(r.get(col)):
                    cur.execute("""INSERT INTO entity_identifier
                        (entity_id,scheme,value,source_id,source_url,collected_by,collected_on)
                        VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                        (eid, scheme, r[col].strip(), r["source_id"], nn(r["source_url"]),
                         r["collected_by"], r["collected_on"]))

            if nn(r.get("classification_code")):
                cur.execute("""INSERT INTO entity_classification (entity_id,scheme,code,name)
                    VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (eid, r["classification_scheme"], r["classification_code"],
                     nn(r["classification_name"])))

            lat, lon = num(r.get("hq_lat")), num(r.get("hq_lon"))
            if lat is not None and lon is not None:
                cur.execute("""INSERT INTO entity_location
                    (entity_id,role,address,city,state,country,geom,source_id)
                    VALUES (%s,'hq',%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s)""",
                    (eid, nn(r["hq_address"]), nn(r["hq_city"]), nn(r["hq_state"]),
                     nn(r["hq_country"]) or "US", lon, lat, r["source_id"]))

            if num(r.get("market_cap_usd")) is not None or nn(r.get("market_cap_band")):
                cur.execute("""INSERT INTO entity_metric
                    (entity_id,metric,value,currency,as_of,band,source_id,collected_on)
                    VALUES (%s,'market_cap_usd',%s,'USD',%s,%s,%s,%s)""",
                    (eid, num(r.get("market_cap_usd")) or 0, r["market_cap_as_of"],
                     nn(r["market_cap_band"]), r["source_id"], r["collected_on"]))
            n += 1
            if n % 500 == 0:
                conn.commit(); print(f"    ...{n}")
        conn.commit(); print(f"  entity            {n} ({skipped} skipped)")

        # ---- aliases
        import re
        SUF = re.compile(r"\b(INC|CORP|CORPORATION|CO|LTD|LIMITED|LLC|PLC|NV|SA|AG|LP|HOLDINGS|GROUP|THE)\b\.?", re.I)
        a = miss = 0
        for _p, r in rows("data/aliases/*.csv"):
            eid = uid2id.get(r["company_uid"].strip())
            if not eid:
                miss += 1; continue
            norm = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9& ]", " ",
                          SUF.sub(" ", r["alias"].upper()))).strip()
            if not norm: continue
            cur.execute("""INSERT INTO entity_alias
                (entity_id,alias,alias_norm,alias_type,language,token_count,
                 is_ambiguous,ambiguity_note,valid_from,valid_to,source_id,collected_by,collected_on)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (eid, r["alias"], norm, r["alias_type"], nn(r["language"]) or "en",
                 len(norm.split()), r["is_ambiguous"].strip().lower() == "yes",
                 nn(r["ambiguity_note"]), nn(r["valid_from"]), nn(r["valid_to"]),
                 r["source_id"], r["collected_by"], r["collected_on"]))
            a += 1
            if a % 2000 == 0:
                conn.commit(); print(f"    ...{a}")
        conn.commit(); print(f"  entity_alias      {a} ({miss} orphaned)")

        for q, label in [
            ("SELECT count(*) FROM entity", "entities"),
            ("SELECT count(*) FROM entity_alias WHERE NOT is_ambiguous", "usable gazetteer aliases"),
            ("SELECT count(*) FROM entity_location", "geolocated"),
            ("SELECT count(DISTINCT atlas_sector) FROM entity WHERE atlas_sector IS NOT NULL", "sectors in use"),
        ]:
            cur.execute(q); print(f"  {label:26} {cur.fetchone()[0]}")

if __name__ == "__main__":
    print("loading reference layer ->", DSN.split("@")[-1])
    main()
    print("done")
