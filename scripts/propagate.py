#!/usr/bin/env python3
"""Seed events, walk the dependency graph, precompute exposure.

    python3 -I scripts/propagate.py

The walk is deterministic and bounded at three hops. No model is involved: the
language model's job is to report what a sentence says, and the numbers come
from this file, which is version controlled and can be read by anyone who
challenges a score.
"""
import os
from collections import defaultdict
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
SCORER = "walk-1.0"
MAX_HOPS = 3
DECAY = 0.55          # each hop out, exposure is worth a little over half

# Real disruptions, with the sectors a seed rule maps them onto. Dates are the
# date the world learned, not the date it happened: a graph read must never use
# anything published after the moment it is modelling.
EVENTS = [
 dict(key="taiwan-strait", name="Taiwan Strait shipping disruption", type="chokepoint",
      public="2026-01-04T06:00:00Z", occurred="2026-01-04T02:10:00Z", severity=0.85,
      lat=24.5, lon=119.5, place="Taiwan Strait", country="TW",
      chokepoints=["TAIWAN_STRAIT"], commodities=["semiconductors","substrates"],
      sectors=["SEMI_DEVICES","SEMI_EQUIP","ELECTRONIC_COMPONENTS","COMPUTER_HARDWARE"]),
 dict(key="hormuz-2026", name="Strait of Hormuz tanker insurance withdrawal",
      type="chokepoint", public="2026-11-10T07:00:00Z", occurred="2026-11-09T22:00:00Z",
      severity=0.80, lat=26.57, lon=56.25, place="Strait of Hormuz", country="OM",
      chokepoints=["HORMUZ"], commodities=["crude oil","petrochemical feedstock"],
      sectors=["SPECIALTY_CHEM","METALS_STEEL","MACHINERY","AUTO_COMPONENTS",
               "SHIPPING_LOGISTICS"]),
 dict(key="renesas-fire", name="Renesas Naka fab fire", type="plant_outage",
      public="2021-03-19T09:00:00Z", occurred="2021-03-19T05:47:00Z", severity=0.78,
      lat=36.46, lon=140.53, place="Naka, Ibaraki", country="JP",
      chokepoints=[], commodities=["automotive semiconductors"],
      sectors=["AUTO_COMPONENTS","SEMI_DEVICES","ELECTRONIC_COMPONENTS"]),
 dict(key="storm-uri", name="Texas winter storm Uri shuts Austin fabs", type="weather",
      public="2021-02-16T12:00:00Z", occurred="2021-02-15T00:00:00Z", severity=0.72,
      lat=30.27, lon=-97.74, place="Austin, Texas", country="US",
      chokepoints=[], commodities=["semiconductors","polymers"],
      sectors=["SEMI_DEVICES","SEMI_EQUIP","SPECIALTY_CHEM"]),
 dict(key="ever-given", name="Ever Given blocks the Suez Canal", type="chokepoint",
      public="2021-03-23T11:00:00Z", occurred="2021-03-23T07:40:00Z", severity=0.70,
      lat=30.02, lon=32.58, place="Suez Canal", country="EG",
      chokepoints=["SUEZ"], commodities=["containerised freight"],
      sectors=["SHIPPING_LOGISTICS","RETAIL","AUTO_COMPONENTS","MACHINERY"]),
 dict(key="gallium-controls", name="China gallium and germanium export controls",
      type="export_control", public="2023-07-03T10:00:00Z", occurred="2023-08-01T00:00:00Z",
      severity=0.66, lat=39.90, lon=116.40, place="Beijing", country="CN",
      chokepoints=[], commodities=["gallium","germanium"],
      sectors=["SEMI_DEVICES","ELECTRONIC_COMPONENTS","METALS_STEEL","AEROSPACE_DEFENSE"]),
 dict(key="japan-korea-2019", name="Japan restricts three materials to South Korea",
      type="export_control", public="2019-07-01T09:00:00Z", occurred="2019-07-04T00:00:00Z",
      severity=0.60, lat=35.68, lon=139.69, place="Tokyo", country="JP",
      chokepoints=[], commodities=["photoresist","hydrogen fluoride"],
      sectors=["SEMI_DEVICES","SEMI_EQUIP","SPECIALTY_CHEM"]),
]


def main():
    conn = psycopg.connect(DSN, autocommit=False)
    cur = conn.cursor()

    cur.execute("SELECT id FROM tenant WHERE name='demo' LIMIT 1")
    row = cur.fetchone()
    if row:
        tenant = row[0]
    else:
        cur.execute("INSERT INTO tenant (name) VALUES ('demo') RETURNING id")
        tenant = cur.fetchone()[0]
    conn.commit()

    # ---- events -------------------------------------------------------
    ids = {}
    for e in EVENTS:
        cur.execute("SELECT id FROM event WHERE dedupe_key=%s", (e["key"],))
        got = cur.fetchone()
        if got:
            ids[e["key"]] = got[0]; continue
        cur.execute("""
            INSERT INTO event (name, event_type, first_occurred_utc, became_public_utc,
                confirmation_level, severity, severity_version, commodities,
                chokepoints, dedupe_key)
            VALUES (%s,%s,%s,%s,'primary_confirmed',%s,'seed-1.0',%s,%s,%s)
            RETURNING id""",
            (e["name"], e["type"], e["occurred"], e["public"], e["severity"],
             e["commodities"], e["chokepoints"], e["key"]))
        eid = cur.fetchone()[0]
        ids[e["key"]] = eid
        cur.execute("""INSERT INTO event_location (event_id, name, country, geom, radius_km,
                       geocode_confidence)
                       VALUES (%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, 300, 1.0)""",
                    (eid, e["place"], e["country"], e["lon"], e["lat"]))
    conn.commit()
    print(f"  {len(ids)} events seeded")

    # ---- the graph, loaded once ---------------------------------------
    cur.execute("""SELECT from_entity_id, to_entity_id, weight, confidence, valid_from
                   FROM dependency_edge""")
    out_edges = defaultdict(list)
    for a, b, w, c, vf in cur.fetchall():
        out_edges[b].append((a, float(w or 0.25), float(c or 0.5), vf))
    print(f"  graph: {sum(len(v) for v in out_edges.values()):,} edges")

    cur.execute("DELETE FROM exposure_precompute WHERE tenant_id=%s", (tenant,))
    conn.commit()

    total = 0
    for e in EVENTS:
        eid = ids[e["key"]]
        asof = e["public"]

        # Hop 1 is the hubs the event lands on: the companies that others in the
        # affected sectors have named as counterparties. Seeding the whole sector
        # instead would put everyone at hop 1 and leave nothing to discover, which
        # is the opposite of what this product is for.
        cur.execute("""
            SELECT DISTINCT de.to_entity_id
            FROM dependency_edge de
            JOIN entity f ON f.id = de.from_entity_id
            WHERE f.atlas_sector = ANY(%s)
              AND de.valid_from <= %s
        """, (e["sectors"], asof))
        seeds = [r[0] for r in cur.fetchall()]

        # plus anyone headquartered where the event physically is
        cur.execute("""SELECT e2.id FROM entity e2
                       JOIN entity_location l ON l.entity_id = e2.id AND l.role='hq'
                       WHERE l.country = %s AND e2.atlas_sector = ANY(%s)""",
                    (e["country"], e["sectors"]))
        seeds = list({*seeds, *[r[0] for r in cur.fetchall()]})

        best = {}
        paths = {}
        frontier = [(s, e["severity"], 1, []) for s in seeds]
        for s, sc, h, p in frontier:
            best[s] = (sc, h, p)

        # Walk outward. An edge "A depends on B" means a hit on B reaches A.
        for hop in range(2, MAX_HOPS + 1):
            nxt = []
            for node, (sc, h, p) in list(best.items()):
                if h != hop - 1:
                    continue
                for dependant, w, conf, vf in out_edges.get(node, []):
                    # point-in-time: an edge published after the event cannot be used
                    if vf is not None and vf.isoformat() > asof:
                        continue   # published after the event: cannot be used
                    new = sc * w * conf * DECAY
                    if new < 0.02:
                        continue
                    cur_best = best.get(dependant)
                    if cur_best is None or new > cur_best[0]:
                        nxt.append((dependant, new, hop, p + [node]))
            for n, sc, h, p in nxt:
                cur_best = best.get(n)
                if cur_best is None or sc > cur_best[0]:
                    best[n] = (sc, h, p)

        rows = [(tenant, eid, ent, round(sc, 4), h, h >= 2, asof, SCORER)
                for ent, (sc, h, p) in best.items() if sc >= 0.02]
        for r in rows:
            cur.execute("""INSERT INTO exposure_precompute
                (tenant_id, event_id, entity_id, score, hops, is_surprising,
                 path_edge_ids, as_of, scorer_version)
                VALUES (%s,%s,%s,%s,%s,%s,ARRAY[]::uuid[],%s,%s)
                ON CONFLICT DO NOTHING""", r)
        conn.commit()
        surp = sum(1 for r in rows if r[5])
        print(f"  {e['name'][:46]:48} {len(rows):5} exposed  {surp:4} beyond hop 1")
        total += len(rows)

    print(f"\n  {total:,} exposure rows precomputed")
    conn.close()

if __name__ == "__main__":
    main()
