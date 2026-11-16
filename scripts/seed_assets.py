#!/usr/bin/env python3
"""The tradeable universe: what a disruption can be expressed against.

Stocks are linked to `entity` wherever we hold one, because that link is what
lets a stock's signal rest on a filing instead of on a rule. Everything else -
commodities, indices, currencies, crypto, ETFs, bonds - has no filing and never
will: no 10-K says what gold does when a strait closes. Those rows exist so the
rules engine has something to point at, and they are labelled as rules in the
output.

    python3 -I scripts/seed_assets.py
"""
import os, sys
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")

# (symbol, name, class, currency, ticker-to-match-or-None, note)
ASSETS = [
 # --- commodities ---------------------------------------------------------
 ("XAUUSD", "Gold",            "commodity", "USD", None, "Safe-haven precious metal"),
 ("XAGUSD", "Silver",          "commodity", "USD", None, "Precious and industrial metal"),
 ("BRENT",  "Brent Crude Oil", "commodity", "USD", None, "Seaborne crude benchmark"),
 ("WTI",    "WTI Crude Oil",   "commodity", "USD", None, "US crude benchmark"),
 ("NATGAS", "Natural Gas",     "commodity", "USD", None, "Henry Hub natural gas"),
 ("COPPER", "Copper",          "commodity", "USD", None, "Industrial bellwether metal"),
 ("CORN",   "Corn",            "commodity", "USD", None, "Grain"),
 ("WHEAT",  "Wheat",           "commodity", "USD", None, "Grain"),
 ("SOYBEANS","Soybeans",       "commodity", "USD", None, "Oilseed, China-sensitive"),
 # --- equity indices ------------------------------------------------------
 ("SPX",  "S&P 500",      "equity_index", "USD", None, "US large cap"),
 ("NDX",  "Nasdaq 100",   "equity_index", "USD", None, "US technology"),
 ("DJI",  "Dow Jones",    "equity_index", "USD", None, "US industrials"),
 ("DAX",  "DAX",          "equity_index", "EUR", None, "German large cap"),
 ("NKY",  "Nikkei 225",   "equity_index", "JPY", None, "Japanese large cap"),
 ("HSI",  "Hang Seng",    "equity_index", "HKD", None, "Hong Kong large cap"),
 ("TWII", "TAIEX",        "equity_index", "TWD", None, "Taiwan large cap"),
 # --- fx ------------------------------------------------------------------
 ("EURUSD","EUR/USD","fx","USD",None,"Euro vs US dollar"),
 ("USDJPY","USD/JPY","fx","JPY",None,"US dollar vs yen"),
 ("USDCHF","USD/CHF","fx","CHF",None,"US dollar vs Swiss franc"),
 ("GBPUSD","GBP/USD","fx","USD",None,"Sterling vs US dollar"),
 ("USDCNY","USD/CNY","fx","CNY",None,"US dollar vs renminbi"),
 ("DXY",   "US Dollar Index","fx","USD",None,"Trade-weighted dollar"),
 # --- crypto --------------------------------------------------------------
 ("BTCUSD","Bitcoin","crypto","USD",None,"Largest crypto asset"),
 ("ETHUSD","Ethereum","crypto","USD",None,"Smart-contract platform"),
 # --- etfs ----------------------------------------------------------------
 ("GLD","Gold ETF (GLD)","etf","USD",None,"Physically backed gold"),
 ("ITA","Aerospace & Defense ETF (ITA)","etf","USD",None,"US defence primes"),
 ("XLE","Energy Sector ETF (XLE)","etf","USD",None,"US energy majors"),
 ("SOXX","Semiconductor ETF (SOXX)","etf","USD",None,"US-listed semiconductors"),
 # --- bonds ---------------------------------------------------------------
 ("TLT","US 20Y+ Treasury (TLT)","bond","USD",None,"Long-duration US government debt"),
 ("IEF","US 7-10Y Treasury (IEF)","bond","USD",None,"Intermediate US government debt"),
 # --- stocks: linked to entity by ticker where we hold one ----------------
 ("LMT","Lockheed Martin","stock","USD","LMT",None),
 ("GD", "General Dynamics","stock","USD","GD", None),
 ("RTX","RTX Corporation","stock","USD","RTX",None),
 ("NOC","Northrop Grumman","stock","USD","NOC",None),
 ("BA", "Boeing","stock","USD","BA", None),
 ("XOM","ExxonMobil","stock","USD","XOM",None),
 ("CVX","Chevron","stock","USD","CVX",None),
 ("SHEL","Shell","stock","USD","SHEL",None),
 ("BP", "BP plc","stock","USD","BP", None),
 ("TSM","TSMC","stock","USD","TSM",None),
 ("INTC","Intel","stock","USD","INTC",None),
 ("AMD","AMD","stock","USD","AMD",None),
 ("NVDA","NVIDIA","stock","USD","NVDA",None),
 ("AAPL","Apple","stock","USD","AAPL",None),
 ("CAT","Caterpillar","stock","USD","CAT",None),
 ("DE", "Deere","stock","USD","DE", None),
]


# Every company that carries evidence is also a tradeable stock, and those are
# the ones that can have a cited signal at all.
#
# Seeding only the famous tickers produced a dashboard with 196 rule signals and
# zero cited ones, which is disclosure inversion showing up in the product: a
# large buyer never names its suppliers, so Lockheed, Exxon and NVIDIA have no
# outgoing edges and nothing to cite. The companies that do disclose are small
# suppliers nobody puts on a watchlist - and they are exactly what Atlas found.
GRAPH_STOCKS = """
    SELECT DISTINCT li.ticker, e.common_name, e.id, li.exchange_mic
    FROM entity e
    JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
    WHERE li.ticker IS NOT NULL
      AND (e.id IN (SELECT from_entity_id FROM dependency_edge)
        OR e.id IN (SELECT to_entity_id   FROM dependency_edge))
"""

# Where a venue uses a suffix or a different ticker for the same company, the
# hand-written row above wins: it is the symbol a person would actually type.
CURRENCY_BY_MIC = {"XNYS": "USD", "XNAS": "USD", "XASX": "AUD", "XLON": "GBP",
                   "XETR": "EUR", "XTSE": "CAD", "XNSE": "INR", "XBOM": "INR"}


def seed_graph_stocks(cur):
    cur.execute(GRAPH_STOCKS)
    n = 0
    for ticker, name, eid, mic in cur.fetchall():
        cur.execute("""
            INSERT INTO asset (symbol, name, asset_class, currency, entity_id, note)
            VALUES (%s,%s,'stock',%s,%s,'Carries cited dependency evidence')
            ON CONFLICT (symbol) DO UPDATE
               SET entity_id = COALESCE(asset.entity_id, EXCLUDED.entity_id)""",
            (ticker, name[:120], CURRENCY_BY_MIC.get(mic, "USD"), eid))
        n += 1
    return n


def main():
    conn = psycopg.connect(DSN)
    cur = conn.cursor()
    linked = unlinked = 0
    for symbol, name, cls, ccy, ticker, note in ASSETS:
        eid = None
        if ticker:
            # Primary listing only: the same ticker on a secondary venue is the
            # same company, and two rows would double-count its exposure.
            cur.execute("""SELECT li.entity_id FROM entity_listing li
                           WHERE li.ticker = %s AND li.is_primary
                           ORDER BY li.exchange_mic LIMIT 1""", (ticker,))
            row = cur.fetchone()
            eid = row[0] if row else None
            linked += bool(eid)
            unlinked += not eid
        cur.execute("""
            INSERT INTO asset (symbol, name, asset_class, currency, entity_id, note)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (symbol) DO UPDATE
               SET name=EXCLUDED.name, asset_class=EXCLUDED.asset_class,
                   currency=EXCLUDED.currency, entity_id=EXCLUDED.entity_id,
                   note=EXCLUDED.note""",
            (symbol, name, cls, ccy, eid, note))
    graph_n = seed_graph_stocks(cur)
    conn.commit()
    print(f"  {graph_n} stocks seeded from companies that carry evidence")
    cur.execute("""SELECT asset_class, count(*), count(entity_id)
                   FROM asset GROUP BY 1 ORDER BY 2 DESC""")
    for cls, n, lk in cur.fetchall():
        print(f"  {cls:<14} {n:3}  linked to an entity: {lk}")
    print(f"\n  {linked} stocks linked to companies we hold evidence for, "
          f"{unlinked} not in the universe")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
