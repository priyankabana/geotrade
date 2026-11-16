#!/usr/bin/env python3
"""Fetch real-world disruptions from public feeds into `event`.

Until this existed, every event in the graph was a literal in propagate.py.
They were real and correctly dated, but a person typed them, and `event_source`
- the table that records which feed reported what - had never held a row. That
is the honest measure of how much of Atlas watched the world: none of it.

Three feeds, chosen because their terms are clean and because each publishes
its own severity scale, so we never have to invent one:

  usgs-earthquake   earthquake.usgs.gov       public domain, no key
  gdacs             gdacs.org                 EU/UN open data, no key
  gdelt-doc         api.gdeltproject.org      open, no key

**Every number here is traceable to the source.** Magnitude comes from USGS and
is converted by one published formula. GDACS alert level is green/orange/red
and maps to three constants. GDELT does not publish a severity, so a GDELT
event takes its severity from a versioned topic table in this file, never from
the article text and never from a model - the same discipline as the rest of
the pipeline: the model reports what a document says, the numbers come from
version-controlled rules.

    python3 -I scripts/ingest_events.py              # all feeds
    python3 -I scripts/ingest_events.py --dry-run    # fetch, print, write nothing
    python3 -I scripts/ingest_events.py --feed usgs
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://atlas:atlas@localhost:5432/atlas")
SEVERITY_VERSION = "feed-1.0"
# A real contact address is what the SEC and most public feeds ask of automated
# clients. ATLAS_CONTACT overrides it.
UA = os.environ.get("ATLAS_CONTACT", "AtlasResearch/0.2 (academic project; contact via repository)")

# --- sector vocabulary -------------------------------------------------------
# Propagation starts from companies in the sectors an event touches. For a
# physical hazard that is anything with plant, inventory or vehicles in the
# radius; a bank branch in the same city is not a supply-chain exposure and
# seeding it would make the number meaningless.
PHYSICAL = ["AUTO_COMPONENTS", "AUTO_OEM", "SEMI_DEVICES", "SEMI_EQUIP",
            "ELECTRONIC_COMPONENTS", "COMPUTER_HARDWARE", "TECH_HARDWARE",
            "MACHINERY", "METALS_STEEL", "MINING_METALS", "CHEMICALS_BASIC",
            "SPECIALTY_CHEM", "PAPER_PACKAGING", "CONSTRUCTION_MATERIALS",
            "TEXTILES_APPAREL", "FOOD_BEVERAGE", "SHIPPING_LOGISTICS",
            "TRANSPORT", "RAIL", "UTILITIES", "ENERGY", "OIL_GAS_DOWNSTREAM",
            "OIL_GAS_UPSTREAM", "INSTRUMENTS", "ELECTRICAL_EQUIP",
            "MEDICAL_DEVICES", "CONSUMER_DURABLES", "AEROSPACE_DEFENSE"]
SEMI = ["SEMI_DEVICES", "SEMI_EQUIP", "ELECTRONIC_COMPONENTS", "COMPUTER_HARDWARE",
        "TECH_HARDWARE", "INSTRUMENTS"]
FREIGHT = ["SHIPPING_LOGISTICS", "TRANSPORT", "RETAIL", "AUTO_COMPONENTS",
           "MACHINERY", "FOOD_BEVERAGE", "TEXTILES_APPAREL"]
ENERGY = ["ENERGY", "OIL_GAS_UPSTREAM", "OIL_GAS_DOWNSTREAM", "UTILITIES",
          "CHEMICALS_BASIC", "SPECIALTY_CHEM", "AIRLINES", "TRANSPORT"]


def http(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


# --- feed: USGS --------------------------------------------------------------
USGS_URL = ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
            "4.5_month.geojson")


def usgs(limit=40):
    """Earthquakes of magnitude 4.5+ in the last month. Public domain.

    Severity is moment magnitude mapped linearly onto 0..1 between M4 and M9.
    M9 is about the largest earthquake instruments have recorded, so the top of
    the scale is an observed bound rather than a guess. The radius is the one
    the felt-shaking literature gives roughly: it doubles every magnitude step.
    """
    data = json.loads(http(USGS_URL))
    out = []
    for f in data.get("features", [])[:limit * 3]:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        mag = p.get("mag")
        coords = g.get("coordinates") or []
        if mag is None or len(coords) < 2:
            continue
        when = datetime.fromtimestamp(p["time"] / 1000, timezone.utc)
        out.append(dict(
            key=f"usgs-{f['id']}", feed="usgs-earthquake",
            name=f"M{mag:.1f} earthquake - {p.get('place') or 'unknown location'}",
            type="earthquake", occurred=when, public=when,
            severity=round(clamp((mag - 4.0) / 5.0, 0.05, 1.0), 3),
            lat=coords[1], lon=coords[0], place=p.get("place"), country=None,
            radius_km=round(clamp(2 ** (mag - 4.0) * 40, 40, 800)),
            commodities=[], chokepoints=[], sectors=PHYSICAL,
            # USGS is the operator of the instruments. There is no higher
            # authority on whether an earthquake happened.
            confirmation="primary_confirmed",
            sources=[(p.get("url"), p.get("title"), when)],
        ))
        if len(out) >= limit:
            break
    return out


# --- feed: NASA EONET -------------------------------------------------------
# GDACS was the first choice and is refused at the edge: its WAF rejects an
# automated client outright, with a support id and no feed. ReliefWeb's v2 API
# needs an appname approved by a person at OCHA. Both are listed in
# docs/sources.md as blocked rather than quietly dropped. EONET is NASA, is
# public domain, needs no key, and publishes coordinates and a magnitude.
EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=120"

# Storm magnitudes arrive in knots, so severity is the Saffir-Simpson scale -
# a published scale with named thresholds, not a curve chosen to look good.
SAFFIR = [(137, 1.00), (113, 0.85), (96, 0.70), (83, 0.55), (64, 0.45), (34, 0.30)]
# Categories EONET tracks that carry no magnitude. One constant each, and they
# are deliberately low: an open wildfire is a hazard, not a Cat-5 hurricane.
EONET_BASE = {"Wildfires": 0.30, "Volcanoes": 0.40, "Severe Storms": 0.35,
              "Floods": 0.40, "Earthquakes": 0.40, "Landslides": 0.30,
              "Drought": 0.25, "Dust and Haze": 0.20, "Sea and Lake Ice": 0.15,
              "Snow": 0.20, "Temperature Extremes": 0.25, "Water Color": 0.10,
              "Manmade": 0.30}
EONET_RADIUS = {"Severe Storms": 350, "Volcanoes": 120, "Wildfires": 60,
                "Floods": 150, "Earthquakes": 200}
EONET_TYPE = {"Severe Storms": "storm", "Volcanoes": "volcano",
              "Wildfires": "wildfire", "Floods": "flood",
              "Earthquakes": "earthquake", "Drought": "drought",
              "Landslides": "landslide"}


PRESCRIBED = re.compile(r"(?i)\b(prescribed|controlled|planned)\s+(fire|burn)")


def _saffir(kts):
    for floor, sev in SAFFIR:
        if kts >= floor:
            return sev
    return 0.15


def eonet(limit=40):
    """NASA's Earth Observatory Natural Event Tracker: open natural hazards."""
    data = json.loads(http(EONET_URL))
    out = []
    for ev in data.get("events", []):
        geoms = ev.get("geometry") or []
        cats = [c.get("title") for c in ev.get("categories") or []]
        cat = cats[0] if cats else None
        if not geoms or not cat:
            continue
        title = ev.get("title") or ""
        # EONET lists controlled burns in the Wildfires category. A planned
        # burn is somebody's forestry schedule, not a disruption, and letting
        # them through buried the real fires under them.
        if PRESCRIBED.search(title):
            continue

        g = geoms[-1]                       # the most recent fix for the event
        coords = g.get("coordinates") or []
        if g.get("type") != "Point" or len(coords) < 2:
            continue                        # tracks and polygons need a centroid

        if g.get("magnitudeUnit") == "kts" and g.get("magnitudeValue") is not None:
            sev = _saffir(float(g["magnitudeValue"]))
        else:
            sev = EONET_BASE.get(cat, 0.25)

        when = _iso(g.get("date")) or datetime.now(timezone.utc)
        out.append(dict(
            key=f"eonet-{ev['id']}", feed="nasa-eonet",
            name=(title or cat)[:200],
            type=EONET_TYPE.get(cat, "natural_hazard"),
            occurred=_iso((geoms[0] or {}).get("date")) or when, public=when,
            severity=round(sev, 3),
            lat=coords[1], lon=coords[0], place=ev.get("title"), country=None,
            radius_km=EONET_RADIUS.get(cat, 150),
            commodities=[], chokepoints=[], sectors=PHYSICAL,
            # EONET republishes an operational agency's observation - JTWC for
            # a cyclone, USGS for a volcano - so the event itself is confirmed
            # even while its impact is not.
            confirmation="corroborated",
            sources=[(s_.get("url"), f"{ev.get('title')} ({s_.get('id')})", when)
                     for s_ in (ev.get("sources") or []) if s_.get("url")]
                    or [(ev.get("link"), ev.get("title"), when)],
        ))
        if len(out) >= limit:
            break
    return out


# --- feed: GDELT -------------------------------------------------------------
# GDELT indexes world news every 15 minutes. It does not publish a severity, so
# detection is live and the severity is a constant attached to the disruption
# class below. That split matters: the feed decides *whether* something is
# happening, this table decides *how much a disruption of that kind is worth*,
# and the table is in version control where it can be argued with.
GDELT_URL = ("https://api.gdeltproject.org/api/v2/doc/doc"
             "?query={q}&mode=artlist&maxrecords=60&format=json&timespan={days}d")

WATCH = [
    dict(key="hormuz", q='"strait of hormuz" (closure OR tanker OR attack OR insurance)',
         name="Strait of Hormuz disruption reported", type="chokepoint",
         severity=0.80, lat=26.57, lon=56.25, place="Strait of Hormuz", country="OM",
         radius_km=300, chokepoints=["HORMUZ"],
         commodities=["crude oil", "LNG", "petrochemical feedstock"], sectors=ENERGY),
    dict(key="red-sea", q='"red sea" (shipping OR houthi OR vessel) (attack OR divert OR reroute)',
         name="Red Sea shipping disruption reported", type="chokepoint",
         severity=0.70, lat=13.6, lon=42.8, place="Bab el-Mandeb", country="YE",
         radius_km=400, chokepoints=["RED_SEA", "BAB_EL_MANDEB"],
         commodities=["containerised freight", "crude oil"], sectors=FREIGHT),
    dict(key="taiwan-strait", q='"taiwan strait" (blockade OR military OR drill OR shipping)',
         name="Taiwan Strait tension reported", type="chokepoint",
         severity=0.85, lat=24.5, lon=119.5, place="Taiwan Strait", country="TW",
         radius_km=300, chokepoints=["TAIWAN_STRAIT"],
         commodities=["semiconductors", "substrates"], sectors=SEMI),
    dict(key="suez", q='"suez canal" (blocked OR disruption OR traffic OR transit)',
         name="Suez Canal disruption reported", type="chokepoint",
         severity=0.70, lat=30.02, lon=32.58, place="Suez Canal", country="EG",
         radius_km=200, chokepoints=["SUEZ"], commodities=["containerised freight"],
         sectors=FREIGHT),
    dict(key="panama", q='"panama canal" (drought OR restriction OR transit OR backlog)',
         name="Panama Canal transit restriction reported", type="chokepoint",
         severity=0.55, lat=9.08, lon=-79.68, place="Panama Canal", country="PA",
         radius_km=200, chokepoints=["PANAMA"], commodities=["containerised freight", "grain"],
         sectors=FREIGHT),
    dict(key="chip-export-controls",
         q='(semiconductor OR chip) "export control" (china OR netherlands OR japan)',
         name="Semiconductor export controls reported", type="export_control",
         severity=0.66, lat=39.90, lon=116.40, place="Beijing", country="CN",
         radius_km=100, chokepoints=[],
         commodities=["semiconductors", "lithography equipment"], sectors=SEMI),
    dict(key="rare-earth-controls",
         q='("rare earth" OR gallium OR germanium OR graphite) (export OR restriction OR quota)',
         name="Critical mineral export restriction reported", type="export_control",
         severity=0.62, lat=39.90, lon=116.40, place="Beijing", country="CN",
         radius_km=100, chokepoints=[],
         commodities=["rare earths", "gallium", "germanium", "graphite"],
         sectors=SEMI + ["MINING_METALS", "AEROSPACE_DEFENSE", "AUTO_COMPONENTS"]),
    dict(key="port-strike", q='(port OR dockworkers OR longshore) (strike OR walkout OR shutdown)',
         name="Port labour stoppage reported", type="labour_action",
         severity=0.50, lat=33.74, lon=-118.27, place="Port of Los Angeles", country="US",
         radius_km=150, chokepoints=[], commodities=["containerised freight"],
         sectors=FREIGHT),
    dict(key="fab-outage",
         q='(fab OR foundry OR "chip plant" OR refinery) (fire OR explosion OR outage OR halted)',
         name="Production facility outage reported", type="plant_outage",
         severity=0.58, lat=35.68, lon=139.69, place="reported facility", country="JP",
         radius_km=120, chokepoints=[], commodities=["semiconductors", "chemicals"],
         sectors=SEMI + ["SPECIALTY_CHEM", "CHEMICALS_BASIC"]),
]

# One article proves a newsroom wrote something. Independent outlets agreeing is
# the weakest corroboration worth acting on, so a topic needs this many distinct
# domains in the window before it becomes an event at all.
MIN_DOMAINS = 5
GDELT_GAP_S = 6.0
GDELT_BACKOFF_S = 20.0
CORROBORATED_AT = 12


def gdelt(days=7, topics=None):
    out = []
    for i, w in enumerate(topics or WATCH):
        # "Please limit requests to one every 5 seconds" is what the service
        # answers a faster caller with, so this waits rather than retrying into
        # the same wall.
        if i:
            time.sleep(GDELT_GAP_S)
        url = GDELT_URL.format(q=urllib.parse.quote(w["q"]), days=days)
        raw = None
        for attempt in range(3):
            try:
                raw = http(url)
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429:
                    print(f"    ! gdelt {w['key']}: {exc}")
                    break
                time.sleep(GDELT_BACKOFF_S * (attempt + 1))
            except Exception as exc:                  # a feed being down is not fatal
                print(f"    ! gdelt {w['key']}: {exc}")
                break
        if raw is None:
            print(f"    ! gdelt {w['key']}: rate limited after 3 attempts")
            continue
        try:
            arts = json.loads(raw).get("articles", []) or []
        except json.JSONDecodeError:
            # GDELT answers an overloaded query with an HTML notice, not JSON.
            print(f"    ! gdelt {w['key']}: non-JSON response ({len(raw)} bytes)")
            continue
        domains = {a.get("domain") for a in arts if a.get("domain")}
        if len(domains) < MIN_DOMAINS:
            continue
        dates = [_gdelt_date(a.get("seendate")) for a in arts]
        dates = sorted(d for d in dates if d)
        first, last = (dates[0], dates[-1]) if dates else (None, None)
        now = datetime.now(timezone.utc)
        # The window is part of the identity: the same topic flaring in March
        # and again in October is two events, not one row updated twice.
        week = (last or now).strftime("%G-W%V")
        out.append(dict(
            key=f"gdelt-{w['key']}-{week}", feed="gdelt-doc",
            name=w["name"], type=w["type"],
            occurred=first or now, public=last or now,
            severity=w["severity"],
            lat=w["lat"], lon=w["lon"], place=w["place"], country=w["country"],
            radius_km=w["radius_km"], commodities=w["commodities"],
            chokepoints=w["chokepoints"], sectors=w["sectors"],
            confirmation="corroborated" if len(domains) >= CORROBORATED_AT else "unconfirmed",
            sources=[(a.get("url"), a.get("title"), _gdelt_date(a.get("seendate")))
                     for a in arts[:25] if a.get("url")],
            domains=len(domains),
        ))
    return out


# --- small parsers -----------------------------------------------------------
def _gdelt_date(s):
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


FEEDS = {"usgs": usgs, "eonet": eonet, "gdelt": gdelt}


# --- write -------------------------------------------------------------------
def store(conn, events):
    cur = conn.cursor()
    new = updated = srcs = 0
    for e in events:
        cur.execute("SELECT id FROM event WHERE dedupe_key = %s", (e["key"],))
        row = cur.fetchone()
        if row:
            eid = row[0]
            updated += 1
        else:
            cur.execute("""
                INSERT INTO event (name, event_type, first_occurred_utc,
                    became_public_utc, confirmation_level, severity,
                    severity_version, commodities, chokepoints, dedupe_key,
                    seed_sectors, source_feed)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (e["name"][:200], e["type"], e["occurred"], e["public"],
                 e["confirmation"], e["severity"], SEVERITY_VERSION,
                 e["commodities"], e["chokepoints"], e["key"],
                 e["sectors"], e["feed"]))
            eid = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO event_location (event_id, name, country, geom,
                    radius_km, geocode_confidence)
                VALUES (%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s, %s)""",
                (eid, (e.get("place") or "")[:120], e.get("country"),
                 e["lon"], e["lat"], e.get("radius_km", 300),
                 # A feed that publishes coordinates is giving us its own
                 # geocode; a chokepoint we looked up ourselves is exact.
                 1.0 if e["feed"] == "gdelt-doc" else 0.9))
            new += 1

        for url, headline, when in e.get("sources", []):
            if not url:
                continue
            cur.execute("""
                INSERT INTO event_source (event_id, source_id, url, headline,
                    published_at_utc, is_primary, retrieved_at_utc)
                VALUES (%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (event_id, url) DO NOTHING""",
                (eid, e["feed"], url[:2000], (headline or "")[:500] or None,
                 when, e["feed"] != "gdelt-doc"))
            srcs += cur.rowcount
    conn.commit()
    return new, updated, srcs


def main():
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    want = None
    if "--feed" in argv:
        want = argv[argv.index("--feed") + 1].split(",")

    events = []
    for name, fn in FEEDS.items():
        if want and name not in want:
            continue
        print(f"  {name} ...", end=" ", flush=True)
        try:
            got = fn()
        except Exception as exc:
            print(f"FAILED: {exc}")
            continue
        print(f"{len(got)} events")
        events.extend(got)

    if not events:
        print("\nnothing fetched")
        return 1

    for e in sorted(events, key=lambda x: -x["severity"])[:12]:
        print(f"    {e['severity']:.2f}  {e['feed']:<16} {e['name'][:62]}")

    if dry:
        print(f"\n--dry-run: {len(events)} events, nothing written")
        return 0

    conn = psycopg.connect(DSN)
    new, updated, srcs = store(conn, events)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM event")
    total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM event_source")
    nsrc = cur.fetchone()[0]
    conn.close()
    print(f"\n  {new} new, {updated} already known, {srcs} source links added")
    print(f"  event {total} rows, event_source {nsrc} rows")
    print("\n  next: python3 -I scripts/propagate.py   (recompute exposure)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
