#!/usr/bin/env python3
"""Recompute alias ambiguity on the form that is actually matched against.

The flag was set from the raw alias, but matching uses alias_norm, which has had
the corporate suffix stripped. "Benchmark Holdings plc" looks like a safe
three-token name and normalises to "BENCHMARK", an ordinary English word that
appears in thousands of filings. Same for Service Corporation, Value-Holdings
and dozens of others.

Rule: a single-token alias_norm is usable only if it is not an English word and
is at least four characters. Multi-token names are specific enough to keep.
"""
import os, re
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")

try:
    ENGLISH = {w.strip().upper() for w in open("/usr/share/dict/words") if len(w.strip()) > 2}
except OSError:
    ENGLISH = set()

# Words the dictionary misses but every filing uses.
EXTRA = {"HOLDINGS","GROUP","SYSTEMS","TECHNOLOGIES","TECHNOLOGY","INDUSTRIES",
 "SOLUTIONS","PARTNERS","CAPITAL","FINANCIAL","GLOBAL","NATIONAL","GENERAL",
 "UNITED","FIRST","TRUST","ENERGY","SERVICES","PRODUCTS","COMPANY","ELECTRONICS",
 "SEMICONDUCTOR","MATERIALS","RESOURCES","PHARMACEUTICALS","PROPERTIES",
 "COMMUNICATIONS","BENCHMARK","MARKETS","SERVICE","VALUE","STRATEGY","PATTERN",
 "RELIABILITY","PROGRESS","SUMMIT","PIONEER","FRONTIER","HERITAGE","LIBERTY",
 "SENTINEL","VANTAGE","MOMENTUM","CATALYST","ADVANTAGE","PRECISION","SYNERGY",
 "APEX","NOVA","ORION","ENVIRONMENTAL","COMMERCIAL","INTERNATIONAL","AMERICAN",
 "STANDARD","UNIVERSAL","PREMIER","SELECT","DIRECT","EXPRESS","PRIME","CORE",
 "UNION","CENTRAL","PACIFIC","ATLANTIC","NORTHERN","SOUTHERN","EASTERN","WESTERN"}

# Multi-token names that are also ordinary accounting or business phrases. These
# appear in every filing and would otherwise match on every page.
STOP_PHRASES = {
 "FAIR VALUE","CURRENCY EXCHANGE","CASH FLOW","INTEREST RATE","NET INCOME",
 "WORKING CAPITAL","GROSS MARGIN","COST OF SALES","BALANCE SHEET","INCOME TAX",
 "SUPPLY CHAIN","MARKET VALUE","BOOK VALUE","SHARE CAPITAL","RISK MANAGEMENT",
 "HUMAN RESOURCES","REAL ESTATE","PUBLIC STORAGE","GENERAL ELECTRIC CAPITAL",
 "CREDIT SUISSE FIRST","OPERATING PARTNERSHIP","CAPITAL MARKETS","MONEY MARKET",
 "STOCK EXCHANGE","ANNUAL REPORT","COMMON STOCK","PREFERRED STOCK","TOTAL RETURN",
 "GROWTH FUND","INCOME FUND","VALUE FUND","GLOBAL MARKETS","WORLD MARKETS",
 "NEW ENGLAND","NORTH AMERICAN","SOUTH AMERICAN","UNITED STATES","GREAT LAKES",
 "FIRST QUARTER","SECOND SIGHT","THIRD POINT","FOURTH WAVE","OPEN TEXT",
 "CHECK POINT","POINT OF CARE","LINE OF CREDIT","TERM LOAN","SENIOR NOTES",
}

def main():
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, alias_norm FROM entity_alias WHERE NOT is_ambiguous")
        rows = cur.fetchall()
        print(f"  checking {len(rows):,} aliases currently marked usable")

        bad = []
        for aid, norm in rows:
            toks = (norm or "").split()
            if len(toks) == 1:
                t = toks[0]
                if len(t) < 4 or t in ENGLISH or t in EXTRA:
                    bad.append(aid)
            elif norm in STOP_PHRASES:
                bad.append(aid)
            # Stripping a leading "Group"/"Holdings" can leave a key like
            # "1 AUTOMOTIVE", which matches "Tier-1 automotive suppliers".
            elif toks and (toks[0].isdigit() or any(t.isdigit() and len(t) <= 2 for t in toks)):
                bad.append(aid)
            # every token generic -> matches ordinary prose
            elif all(t in ENGLISH or t in EXTRA for t in toks) and len(toks) <= 2:
                bad.append(aid)
        print(f"  suppressing {len(bad):,} aliases that are ordinary words or phrases")

        for i in range(0, len(bad), 5000):
            cur.execute("""UPDATE entity_alias
                           SET is_ambiguous = true,
                               ambiguity_note = 'normalised form is a single ordinary word'
                           WHERE id = ANY(%s)""", (bad[i:i+5000],))
        conn.commit()

        cur.execute("SELECT count(*) FROM entity_alias WHERE NOT is_ambiguous")
        print(f"  usable gazetteer now: {cur.fetchone()[0]:,}")
        cur.execute("""SELECT count(*) FROM (SELECT DISTINCT alias_norm FROM entity_alias
                       WHERE NOT is_ambiguous AND length(alias_norm) >= 5) t""")
        print(f"  distinct match keys:  {cur.fetchone()[0]:,}")

if __name__ == "__main__":
    main()
