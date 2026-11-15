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
SCORER = "walk-1.1"
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
 # ---- the rest of the 20-event benchmark -----------------------------------
 # Real, dated disruptions spanning 2011-2026. Most predate every filing we
 # hold, so the graph correctly reaches nobody beyond hop 1: that is the
 # point-in-time rule demonstrated across twenty cases rather than asserted once.
 dict(key="tohoku-2011", name="Tohoku earthquake and tsunami", type="earthquake",
      public="2011-03-11T06:00:00Z", occurred="2011-03-11T05:46:00Z", severity=0.95,
      lat=38.32, lon=142.37, place="Tohoku, Japan", country="JP", radius_km=600,
      chokepoints=[], commodities=["automotive semiconductors","pigments","batteries"],
      sectors=["AUTO_COMPONENTS","AUTO_OEM","SEMI_DEVICES","ELECTRONIC_COMPONENTS",
               "SPECIALTY_CHEM"]),
 dict(key="thai-floods-2011", name="Thailand floods shut hard-disk plants", type="weather",
      public="2011-10-10T06:00:00Z", occurred="2011-10-04T00:00:00Z", severity=0.80,
      lat=14.35, lon=100.58, place="Ayutthaya, Thailand", country="TH", radius_km=200,
      chokepoints=[], commodities=["hard disk drives","electronic components"],
      sectors=["COMPUTER_HARDWARE","ELECTRONIC_COMPONENTS","TECH_HARDWARE"]),
 dict(key="kumamoto-2016", name="Kumamoto earthquake halts image sensor output",
      type="earthquake", public="2016-04-16T06:00:00Z", occurred="2016-04-15T16:25:00Z",
      severity=0.74, lat=32.79, lon=130.74, place="Kumamoto, Japan", country="JP",
      radius_km=150, chokepoints=[], commodities=["image sensors","automotive parts"],
      sectors=["SEMI_DEVICES","ELECTRONIC_COMPONENTS","AUTO_COMPONENTS"]),
 dict(key="notpetya-2017", name="NotPetya cyberattack halts Maersk terminals",
      type="cyber", public="2017-06-27T12:00:00Z", occurred="2017-06-27T09:00:00Z",
      severity=0.72, lat=55.68, lon=12.57, place="Copenhagen", country="DK",
      radius_km=400, chokepoints=[], commodities=["containerised freight"],
      sectors=["SHIPPING_LOGISTICS","TRANSPORT","RETAIL"]),
 dict(key="akm-fire-2020", name="Asahi Kasei Nobeoka plant fire", type="plant_outage",
      public="2020-10-21T06:00:00Z", occurred="2020-10-20T01:00:00Z", severity=0.70,
      lat=32.58, lon=131.66, place="Nobeoka, Miyazaki", country="JP", radius_km=120,
      chokepoints=[], commodities=["audio codecs","analogue semiconductors"],
      sectors=["SEMI_DEVICES","ELECTRONIC_COMPONENTS","AUTO_COMPONENTS"]),
 dict(key="colonial-2021", name="Colonial Pipeline ransomware shutdown", type="cyber",
      public="2021-05-08T12:00:00Z", occurred="2021-05-07T00:00:00Z", severity=0.68,
      lat=34.07, lon=-84.29, place="Alpharetta, Georgia", country="US", radius_km=800,
      chokepoints=[], commodities=["refined fuels"],
      sectors=["OIL_GAS_DOWNSTREAM","ENERGY","TRANSPORT","AIRLINES"]),
 dict(key="ida-2021", name="Hurricane Ida shuts Gulf petrochemical plants", type="weather",
      public="2021-08-29T12:00:00Z", occurred="2021-08-29T16:55:00Z", severity=0.71,
      lat=29.95, lon=-90.07, place="Louisiana, United States", country="US", radius_km=300,
      chokepoints=[], commodities=["polymers","petrochemical feedstock"],
      sectors=["SPECIALTY_CHEM","CHEMICALS_BASIC","OIL_GAS_DOWNSTREAM","PAPER_PACKAGING"]),
 dict(key="asml-fire-2022", name="Fire at ASML Berlin component plant",
      type="plant_outage", public="2022-01-03T08:00:00Z", occurred="2022-01-02T00:00:00Z",
      severity=0.60, lat=52.52, lon=13.40, place="Berlin", country="DE", radius_km=100,
      chokepoints=[], commodities=["lithography components"],
      sectors=["SEMI_EQUIP","SEMI_DEVICES","INSTRUMENTS"]),
 dict(key="ukraine-2022", name="Invasion of Ukraine disrupts neon and palladium",
      type="conflict", public="2022-02-24T05:00:00Z", occurred="2022-02-24T03:00:00Z",
      severity=0.88, lat=50.45, lon=30.52, place="Kyiv", country="UA", radius_km=900,
      chokepoints=[], commodities=["neon","palladium","wheat","titanium"],
      sectors=["SEMI_DEVICES","AUTO_COMPONENTS","AEROSPACE_DEFENSE","METALS_STEEL",
               "FOOD_BEVERAGE"]),
 dict(key="kojima-2022", name="Kojima Industries cyberattack stops Toyota lines",
      type="cyber", public="2022-02-28T06:00:00Z", occurred="2022-02-26T00:00:00Z",
      severity=0.62, lat=34.90, lon=137.08, place="Toyota City, Aichi", country="JP",
      radius_km=150, chokepoints=[], commodities=["plastic interior parts"],
      sectors=["AUTO_COMPONENTS","AUTO_OEM"]),
 dict(key="shanghai-2022", name="Shanghai lockdown halts port and factories",
      type="policy", public="2022-03-28T00:00:00Z", occurred="2022-03-28T00:00:00Z",
      severity=0.82, lat=31.23, lon=121.47, place="Shanghai", country="CN", radius_km=250,
      chokepoints=[], commodities=["containerised freight","electronics","vehicles"],
      sectors=["SHIPPING_LOGISTICS","ELECTRONIC_COMPONENTS","AUTO_COMPONENTS",
               "CONSUMER_DURABLES","RETAIL"]),
 dict(key="freeport-lng-2022", name="Freeport LNG terminal explosion", type="plant_outage",
      public="2022-06-08T18:00:00Z", occurred="2022-06-08T16:40:00Z", severity=0.64,
      lat=28.95, lon=-95.31, place="Freeport, Texas", country="US", radius_km=200,
      chokepoints=[], commodities=["liquefied natural gas"],
      sectors=["ENERGY","OIL_GAS_DOWNSTREAM","UTILITIES","CHEMICALS_BASIC"]),
 dict(key="sichuan-2022", name="Sichuan drought forces industrial power cuts",
      type="weather", public="2022-08-15T06:00:00Z", occurred="2022-08-15T00:00:00Z",
      severity=0.66, lat=30.57, lon=104.07, place="Chengdu, Sichuan", country="CN",
      radius_km=300, chokepoints=[], commodities=["lithium","polysilicon","electronics"],
      sectors=["MINING_METALS","ELECTRONIC_COMPONENTS","AUTO_COMPONENTS","MATERIALS"]),
 dict(key="turkey-quake-2023", name="Turkiye and Syria earthquake", type="earthquake",
      public="2023-02-06T04:00:00Z", occurred="2023-02-06T01:17:00Z", severity=0.90,
      lat=37.17, lon=37.03, place="Gaziantep", country="TR", radius_km=400,
      chokepoints=[], commodities=["textiles","steel","cement"],
      sectors=["TEXTILES_APPAREL","METALS_STEEL","CONSTRUCTION_MATERIALS","AUTO_COMPONENTS"]),
 dict(key="panama-drought-2023", name="Panama Canal drought cuts daily transits",
      type="chokepoint", public="2023-07-25T12:00:00Z", occurred="2023-07-25T00:00:00Z",
      severity=0.58, lat=9.08, lon=-79.68, place="Panama Canal", country="PA",
      radius_km=200, chokepoints=["PANAMA"],
      commodities=["containerised freight","grain","LPG"],
      sectors=["SHIPPING_LOGISTICS","TRANSPORT","RETAIL","FOOD_BEVERAGE"]),
 dict(key="red-sea-2023", name="Red Sea attacks divert shipping from Suez",
      type="conflict", public="2023-12-15T08:00:00Z", occurred="2023-12-15T00:00:00Z",
      severity=0.76, lat=12.58, lon=43.33, place="Bab el-Mandeb", country="YE",
      radius_km=400, chokepoints=["BAB_EL_MANDEB","SUEZ"],
      commodities=["containerised freight","crude oil"],
      sectors=["SHIPPING_LOGISTICS","TRANSPORT","RETAIL","AUTO_COMPONENTS","ENERGY"]),
 dict(key="noto-2024", name="Noto Peninsula earthquake", type="earthquake",
      public="2024-01-01T08:00:00Z", occurred="2024-01-01T07:10:00Z", severity=0.73,
      lat=37.50, lon=137.27, place="Ishikawa, Japan", country="JP", radius_km=200,
      chokepoints=[], commodities=["semiconductors","electronic components"],
      sectors=["SEMI_DEVICES","ELECTRONIC_COMPONENTS","MACHINERY"]),
 dict(key="baltimore-2024", name="Key Bridge collapse closes Baltimore port",
      type="accident", public="2024-03-26T06:00:00Z", occurred="2024-03-26T05:28:00Z",
      severity=0.61, lat=39.22, lon=-76.53, place="Baltimore, Maryland", country="US",
      radius_km=150, chokepoints=[], commodities=["vehicles","coal","containerised freight"],
      sectors=["SHIPPING_LOGISTICS","AUTO_OEM","TRANSPORT","MINING_METALS"]),
 dict(key="hualien-2024", name="Hualien earthquake shakes Taiwanese fabs",
      type="earthquake", public="2024-04-03T00:00:00Z", occurred="2024-04-02T23:58:00Z",
      severity=0.75, lat=23.83, lon=121.56, place="Hualien, Taiwan", country="TW",
      radius_km=250, chokepoints=[], commodities=["semiconductors","substrates"],
      sectors=["SEMI_DEVICES","SEMI_EQUIP","ELECTRONIC_COMPONENTS","COMPUTER_HARDWARE"]),
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
                       VALUES (%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s, 1.0)""",
                    (eid, e["place"], e["country"], e["lon"], e["lat"],
                     e.get("radius_km", 300)))
    conn.commit()
    print(f"  {len(ids)} events seeded")

    # ---- the graph ------------------------------------------------------
    # Loaded per event through edges_as_of, which is the only sanctioned read.
    # Loading the whole graph once and filtering in Python was the second path
    # this project says it does not have, and it compared timestamps as strings
    # and never looked at valid_to at all.
    def graph_as_of(as_of):
        cur.execute("""SELECT e.from_entity_id, e.to_entity_id, e.weight, e.confidence
                       FROM edges_as_of(
                            (SELECT array_agg(id) FROM entity), %s) e""", (as_of,))
        out = defaultdict(list)
        for a, b, w, c in cur.fetchall():
            out[b].append((a, float(w or 0.25), float(c or 0.5)))
        return out

    cur.execute("SELECT count(*) FROM dependency_edge")
    print(f"  graph: {cur.fetchone()[0]:,} edges, read as of each event's date")

    cur.execute("DELETE FROM exposure_precompute WHERE tenant_id=%s", (tenant,))
    conn.commit()

    total = 0
    for e in EVENTS:
        eid = ids[e["key"]]
        asof = e["public"]
        out_edges = graph_as_of(asof)

        # Hop 1 is the hubs the event lands on: the companies that others in the
        # affected sectors have named as counterparties. Seeding the whole sector
        # instead would put everyone at hop 1 and leave nothing to discover, which
        # is the opposite of what this product is for.
        cur.execute("""
            SELECT DISTINCT de.to_entity_id
            FROM edges_as_of((SELECT array_agg(id) FROM entity), %s) de
            JOIN entity f ON f.id = de.from_entity_id
            WHERE f.atlas_sector = ANY(%s)
        """, (asof, e["sectors"]))
        seeds = [r[0] for r in cur.fetchall()]

        # plus anyone headquartered inside the event's actual radius. Matching on
        # country instead put every US semiconductor company in the blast radius
        # of a storm in Austin, which is not a claim we can defend. The event
        # carries a geography and a radius, so use them.
        cur.execute("""SELECT e2.id FROM entity e2
                       JOIN entity_location l  ON l.entity_id = e2.id AND l.role='hq'
                       JOIN event_location  el ON el.event_id = %s
                       WHERE e2.atlas_sector = ANY(%s)
                         AND ST_DWithin(l.geom, el.geom,
                                        COALESCE(el.radius_km, 300) * 1000)""",
                    (eid, e["sectors"]))
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
                for dependant, w, conf in out_edges.get(node, []):
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
