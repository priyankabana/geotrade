#!/usr/bin/env python3
"""Turn events into per-asset signals, in two clearly separated tiers.

Tier one, `cited_dependency`: a company disclosed a dependency in a filing, an
event hits that dependency, and the signal carries the edge - and therefore the
sentence. This is the tier Atlas exists for.

Tier two, `rule`: a named rule in this file fired. No company said this. A rule
is an argument we are making about how a disruption transmits to something that
has no filings at all - crude oil, an index, a currency. Each rule has an id and
a stated reason, both of which go into the row, so a reader can see exactly what
is being asserted and on whose authority.

**Direction is not advice.** `up` and `down` describe which way a disruption
pushes on a business or a price, not what anyone should do about it. Atlas does
not know your price, your position or your horizon, and it does not pretend to.

    python3 -I scripts/signals.py
    python3 -I scripts/signals.py --explain HORMUZ
"""
import os, pathlib, sys
import psycopg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
SIGNAL_VERSION = "signals-1.0"

# Tier-one signals model exposure to a disruption. Every event this pipeline
# ingests is a negative shock - a fire, a port closure, a ransomware outage -
# so a company that depends on the disrupted party is pressed downward. The
# direction is therefore a constant of the model, not something derived from
# the event, and it is named here so the assumption is visible and can be
# argued with rather than buried as a string literal in the insert. A pipeline
# that one day ingests a positive event would have to revisit this.
DISRUPTION_DIRECTION = "down"

# A rule fires when the event carries any of `chokepoints`, `commodities` or
# `types` listed. `weight` scales the event's own severity - it never invents a
# level of its own, so a quiet event cannot produce a loud signal.
RULES = [
 dict(id="oil-chokepoint-crude",
      chokepoints=["HORMUZ", "RED_SEA", "BAB_EL_MANDEB", "SUEZ"],
      commodities=["crude oil", "LNG", "petrochemical feedstock"],
      types=[], weight=0.90,
      assets={"BRENT": "up", "WTI": "up", "XLE": "up", "NATGAS": "up"},
      why="Chokepoint disruption removes seaborne barrels faster than supply can reroute."),
 dict(id="oil-chokepoint-consumers",
      chokepoints=["HORMUZ", "RED_SEA", "BAB_EL_MANDEB"],
      commodities=["crude oil"], types=[], weight=0.60,
      assets={"SPX": "down", "NKY": "down", "DAX": "down"},
      why="Oil importers carry a higher input cost; Japan and Germany import nearly all their crude."),
 dict(id="conflict-safe-haven",
      chokepoints=["HORMUZ", "RED_SEA", "BAB_EL_MANDEB", "TAIWAN_STRAIT"],
      commodities=[], types=["chokepoint"], weight=0.70,
      assets={"XAUUSD": "up", "GLD": "up", "XAGUSD": "up",
              "TLT": "up", "IEF": "up", "USDCHF": "down", "DXY": "up"},
      why="Shipping and military risk moves capital into gold, government debt and the franc."),
 dict(id="defence-demand",
      chokepoints=["HORMUZ", "TAIWAN_STRAIT", "RED_SEA"],
      commodities=[], types=["chokepoint"], weight=0.65,
      assets={"ITA": "up", "LMT": "up", "RTX": "up", "NOC": "up", "GD": "up"},
      why="Sustained military risk raises expected defence procurement."),
 dict(id="semi-supply-shock",
      chokepoints=["TAIWAN_STRAIT"],
      commodities=["semiconductors", "substrates", "lithography equipment"],
      types=["export_control", "plant_outage"], weight=0.85,
      assets={"SOXX": "down", "NDX": "down", "TWII": "down", "AAPL": "down",
              "NVDA": "down", "AMD": "down", "TSM": "down"},
      why="Advanced logic has no short-run substitute; qualifying a new fab takes quarters."),
 dict(id="semi-domestic-substitute",
      chokepoints=["TAIWAN_STRAIT"], commodities=["semiconductors"],
      types=["export_control"], weight=0.40,
      assets={"INTC": "up"},
      why="Capacity outside the affected region gains value when a concentrated source is interrupted."),
 dict(id="freight-cost",
      chokepoints=["SUEZ", "PANAMA", "RED_SEA", "BAB_EL_MANDEB", "MALACCA"],
      commodities=["containerised freight"], types=["labour_action"], weight=0.75,
      assets={"SPX": "down", "DJI": "down"},
      why="Rerouting a blocked canal adds sea days, freight cost and working capital."),
 dict(id="critical-minerals",
      chokepoints=[],
      commodities=["rare earths", "gallium", "germanium", "graphite"],
      types=["export_control"], weight=0.70,
      assets={"COPPER": "up", "SOXX": "down", "ITA": "down", "NVDA": "down"},
      why="Restricting a concentrated input raises its price and squeezes buyers with no alternative."),
 dict(id="china-trade-retaliation",
      chokepoints=[], commodities=["semiconductors", "rare earths"],
      types=["export_control"], weight=0.55,
      assets={"HSI": "down", "USDCNY": "up", "SOYBEANS": "down"},
      why="Export-control rounds have drawn agricultural retaliation and a weaker managed currency."),
 dict(id="energy-supply-europe",
      chokepoints=[], commodities=["natural gas", "LNG"], types=[], weight=0.65,
      assets={"NATGAS": "up", "DAX": "down", "EURUSD": "down"},
      why="European industry is gas-intensive and prices at the margin."),
 dict(id="physical-hazard-broad",
      chokepoints=[], commodities=[],
      types=["earthquake", "storm", "flood", "volcano", "wildfire", "tsunami"],
      weight=0.35,
      assets={"XAUUSD": "up"},
      why="A large natural hazard is a mild risk-off impulse at index level."),
]


def fires(rule, chokepoints, commodities, etype):
    return (bool(set(rule["chokepoints"]) & set(chokepoints or []))
            or bool(set(rule["commodities"]) & set(commodities or []))
            or etype in rule["types"])


def main():
    argv = sys.argv[1:]
    conn = psycopg.connect(DSN)
    cur = conn.cursor()

    cur.execute("SELECT id, symbol, entity_id FROM asset")
    by_symbol = {r[1]: (r[0], r[2]) for r in cur.fetchall()}
    cur.execute("SELECT entity_id, id, symbol FROM asset WHERE entity_id IS NOT NULL")
    by_entity = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    # The same threshold propagation uses. An event that is too quiet to spread
    # through the graph must not still produce rule signals, or the board shows
    # a row for an event the exposure view says touched nobody.
    from propagate import SEED_MIN_SEVERITY
    cur.execute("""SELECT id, name, event_type, severity, commodities, chokepoints,
                          became_public_utc, COALESCE(source_feed,'benchmark')
                   FROM event WHERE severity >= %s
                   ORDER BY became_public_utc DESC""", (SEED_MIN_SEVERITY,))
    events = cur.fetchall()

    cited = ruled = 0
    for eid, ename, etype, sev, commodities, chokepoints, asof, feed in events:
        sev = float(sev)
        cur.execute("DELETE FROM asset_signal WHERE event_id = %s", (eid,))

        # --- tier one: a company disclosed this, and we can show the sentence --
        cur.execute("""
            SELECT ep.entity_id, ep.score, ep.hops
            FROM exposure_precompute ep
            WHERE ep.event_id = %s AND ep.entity_id = ANY(%s)
            ORDER BY ep.score DESC""",
            (eid, list(by_entity.keys()) or [None]))
        for ent, score, hops in cur.fetchall():
            asset_id, symbol = by_entity[ent]
            # The edge that makes this a disclosure rather than an assertion:
            # the company's own strongest dependency that was already on the
            # record when the event became public. A later filing would be
            # look-ahead.
            # A company is citable two ways round, and looking only one way
            # lost almost all of them. Either it disclosed depending on
            # somebody, or somebody disclosed depending on it - and under
            # disclosure inversion the second is how the large, well known
            # names enter the graph at all. Both are filed sentences.
            cur.execute("""
                SELECT de.id, dc.quote,
                       CASE WHEN de.from_entity_id = %(ent)s
                            THEN e_to.common_name ELSE e_from.common_name END,
                       de.from_entity_id = %(ent)s AS outbound
                FROM dependency_edge de
                JOIN dependency_claim dc ON dc.id = de.claim_id
                JOIN entity e_to   ON e_to.id   = de.to_entity_id
                JOIN entity e_from ON e_from.id = de.from_entity_id
                WHERE (de.from_entity_id = %(ent)s OR de.to_entity_id = %(ent)s)
                  AND de.valid_from <= %(asof)s
                ORDER BY de.confidence DESC, length(dc.quote) ASC
                LIMIT 1""", {"ent": ent, "asof": asof})
            edge = cur.fetchone()
            if not edge:
                continue
            edge_id, quote, counterparty, outbound = edge
            cur.execute("""
                INSERT INTO asset_signal (event_id, asset_id, direction, basis,
                    magnitude, hops, edge_id, rationale, as_of, scorer_version)
                VALUES (%s,%s,%s,'cited_dependency',%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING""",
                (eid, asset_id, DISRUPTION_DIRECTION,
                 round(float(score), 3), hops, edge_id,
                 # The quote is rendered directly beneath this line on the
                 # board, so repeating it here printed the sentence twice.
                 (f"Disclosed dependence on {counterparty}"
                  if outbound else
                  f"{counterparty} disclosed depending on this company")
                 + f" · {hops} hop{'s' if hops != 1 else ''} from this event",
                 asof, SIGNAL_VERSION))
            cited += cur.rowcount

        # --- tier two: a rule we are asserting, named so it can be argued with -
        for rule in RULES:
            if not fires(rule, chokepoints, commodities, etype):
                continue
            mag = round(sev * rule["weight"], 3)
            for symbol, direction in rule["assets"].items():
                got = by_symbol.get(symbol)
                if not got:
                    continue
                cur.execute("""
                    INSERT INTO asset_signal (event_id, asset_id, direction, basis,
                        magnitude, hops, rule_id, rationale, as_of, scorer_version)
                    VALUES (%s,%s,%s,'rule',%s,NULL,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING""",
                    (eid, got[0], direction, mag, rule["id"], rule["why"],
                     asof, SIGNAL_VERSION))
                ruled += cur.rowcount
    conn.commit()

    cur.execute("""SELECT basis, direction, count(*) FROM asset_signal
                   GROUP BY 1,2 ORDER BY 1,3 DESC""")
    print()
    for basis, direction, n in cur.fetchall():
        print(f"  {basis:<18} {direction:<8} {n:5}")
    cur.execute("SELECT count(DISTINCT event_id), count(DISTINCT asset_id) FROM asset_signal")
    ne, na = cur.fetchone()
    print(f"\n  {cited + ruled} signals across {ne} events and {na} assets")
    print(f"  {cited} carry a filing sentence, {ruled} carry a named rule")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
