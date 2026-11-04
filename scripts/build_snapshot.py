#!/usr/bin/env python3
"""Freeze a small, publishable slice of the read API into static JSON for the public demo.

    python3 -I scripts/build_snapshot.py --api http://localhost:8000
    python3 -I scripts/build_snapshot.py --from-dir /path/to/full/private/snapshot

Writes apps/web/public/snapshot/*.json. When the browser cannot reach the API
(the deployed Vercel build has no backend), apps/web/src/client.ts reads these
files instead, so the Live tab still shows real coverage.

Publication filter -- see docs/sources.md, "Public demo snapshot". The vendor market
files are NOT cleared for publication, so nothing row-level from them ships:

  * Aggregates only for the full universe: company count per country, company count
    per sector per country, and ONE weighted coverage point per country (the mean HQ
    position of that country's companies). No per-company coordinates, names or ids.
  * A capped named sample (MAX_NAMED, default 300) of well-known companies:
      - US/SEC filers: the highest-ranked filers in data/reference/us_filer_gazetteer.csv
        (SEC company_tickers_exchange.json order, i.e. by market cap; public domain).
        Legal name, ticker, exchange and CIK come from SEC. Display name, HQ city/coords
        and our own sector label are kept as plain facts.
      - Non-US: the committed 41-company sample in data/companies/sample.csv.
    Fields: name, ticker/exchange, CIK (SEC only), country, city, lat/lon, sector.
    Dropped: ISIN, LEI, FIGI, former names, market-cap band, descriptions, vendor codes,
    and every provenance column (source_id, collected_by, notes).

The "--from-dir" input is a full snapshot produced from the private database (never
committed). It must contain countries.json, points.json, sectors/*.json, company/*.json.
"""
import argparse, csv, datetime, glob, json, os, shutil, sys, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "apps", "web", "public", "snapshot")
GAZ = os.path.join(ROOT, "data", "reference", "us_filer_gazetteer.csv")
SAMPLE = os.path.join(ROOT, "data", "companies", "sample.csv")
SEC_MIC = {"Nasdaq": "XNAS", "NYSE": "XNYS", "NYSE American": "XASE", "CBOE": "XCBO"}
MAX_NAMED = int(os.environ.get("ATLAS_SNAPSHOT_MAX", "300"))

# A city field that is really a US state means the geocoder fell back to a guess;
# publish the country centroid instead of a wrong city.
US_STATES = {"alabama", "alaska", "arizona", "arkansas", "california", "colorado",
             "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho", "illinois",
             "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland",
             "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana",
             "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york state",
             "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
             "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah",
             "vermont", "virginia", "washington state", "west virginia", "wisconsin", "wyoming"}
US_CENTROID = (37.58178, -92.73712)
# Known geocoder misses in the source, corrected by hand with public facts.
HQ_FIX = {"XNAS:ASML": ("NL", "Veldhoven", 51.4183, 5.4024)}   # foreign filer, not US
CITY_AT_CENTROID = {"New York": (40.7128, -74.0060)}            # ambiguous name fell back


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=60) as r:
            return json.loads(r.read())

    def health(self): return self._get("/v1/health")
    def countries(self): return self._get("/v1/globe/countries")
    def points(self): return self._get("/v1/globe/points?limit=100000")
    def sectors(self, iso): return self._get(f"/v1/countries/{iso}/sectors")

    def company(self, uid):
        try:
            return self._get(f"/v1/companies/{urllib.parse.quote(uid)}")
        except Exception:
            return None


class Dir:
    """A full snapshot on disk (named+anon points, sharded company details)."""
    def __init__(self, d):
        self.d = d
        self._details = None

    def _load(self, rel):
        with open(os.path.join(self.d, rel)) as f:
            return json.load(f)

    def health(self): return self._load("health.json")
    def countries(self): return self._load("countries.json")

    def points(self):
        p = self._load("points.json")
        if isinstance(p, list):
            return p
        return p["named"] + [{"uid": "", "lat": la, "lon": lo, "country": c, "w": w}
                             for la, lo, w, c in p["anon"]]

    def sectors(self, iso):
        try:
            return self._load(f"sectors/{iso}.json")
        except FileNotFoundError:
            return []

    def company(self, uid):
        if self._details is None:
            self._details = {}
            for f in glob.glob(os.path.join(self.d, "company", "*.json")):
                with open(f) as fh:
                    self._details.update(json.load(fh))
        return self._details.get(uid)


def write(rel, obj):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def detail(uid, legal, common, iso, city, lat, lon, sector, mic, ticker, cik):
    if uid in HQ_FIX:
        iso, city, lat, lon = HQ_FIX[uid]
    if city and city.strip().lower() in US_STATES and iso == "US":
        city, (lat, lon) = None, US_CENTROID
    if iso == "US" and city in CITY_AT_CENTROID and abs(lat - US_CENTROID[0]) < 0.01:
        lat, lon = CITY_AT_CENTROID[city]
    return {
        "companyUid": uid, "legalName": legal, "commonName": common or legal,
        "formerNames": [], "countryHq": iso,
        "hq": {"lat": round(lat, 4), "lon": round(lon, 4), "city": city or None},
        "atlasSector": sector or "OTHER", "marketCapBand": None, "fiscalYearEnd": "",
        "status": "active",
        "listings": [{"exchangeMic": mic, "ticker": ticker, "isPrimary": True}],
        "identifiers": [{"scheme": "CIK", "value": cik}] if cik else [],
        "dependsOn": [], "dependedOnBy": [], "unnamedDependencies": [],
        "documentCount": 0, "lastFiledAtUtc": None,
    }


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--api")
    g.add_argument("--from-dir")
    a = ap.parse_args()
    src = Api(a.api) if a.api else Dir(a.from_dir)

    health = src.health()
    countries = src.countries()
    points = src.points()
    sector_names = {}

    # --- named sample -------------------------------------------------------
    named = {}
    # Non-US rows from the committed sample first (they give the globe its spread).
    with open(SAMPLE, newline="") as f:
        for r in csv.DictReader(f):
            iso = r["hq_country"]
            lat, lon = fnum(r["hq_lat"]), fnum(r["hq_lon"])
            if iso == "US" or lat is None or lon is None:
                continue
            mic, tic = r["company_uid"].split(":", 1)
            named[r["company_uid"]] = detail(r["company_uid"], r["legal_name"], r["common_name"],
                                             iso, r["hq_city"], lat, lon, r["atlas_sector"],
                                             mic, tic, None)
    # Then SEC filers in market-cap rank order until the cap.
    with open(GAZ, newline="") as f:
        gaz = sorted(csv.DictReader(f), key=lambda r: int(r["rank"] or 10**9))
    for r in gaz:
        if len(named) >= MAX_NAMED:
            break
        mic = SEC_MIC.get(r["exchange"])
        if not mic or not r["ticker"]:
            continue
        uid = f"{mic}:{r['ticker'].upper()}"
        if uid in named:
            continue
        d = src.company(uid)
        if not d or not d.get("hq"):
            continue
        named[uid] = detail(uid, r["legal_name"], d.get("commonName") or r["short_name"],
                            d["countryHq"], d["hq"].get("city"), d["hq"]["lat"], d["hq"]["lon"],
                            d.get("atlasSector"), mic, r["ticker"].upper(), r["cik"])

    # --- aggregates -----------------------------------------------------------
    named_per_country = {}
    for d in named.values():
        named_per_country[d["countryHq"]] = named_per_country.get(d["countryHq"], 0) + 1
    acc = {}
    for p in points:
        w = p.get("w", 1)
        s = acc.setdefault(p["country"], [0.0, 0.0, 0])
        s[0] += p["lat"] * w; s[1] += p["lon"] * w; s[2] += w
    tiles = []
    for c in countries:
        iso = c["country"]
        s = acc.get(iso)
        rest = c["companyCount"] - named_per_country.get(iso, 0)
        if s and s[2] and rest > 0:
            tiles.append([round(s[0] / s[2], 2), round(s[1] / s[2], 2), rest, iso])
    named_pts = [{"uid": d["companyUid"], "name": d["commonName"], "sector": d["atlasSector"],
                  "country": d["countryHq"], "lat": d["hq"]["lat"], "lon": d["hq"]["lon"]}
                 for d in named.values()]

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    write("points.json", {"named": named_pts, "anon": tiles})
    write("countries.json", [{**c, "sectorMoveSummary": None, "activeEventCount": 0} for c in countries])
    write("health.json", {"ok": True, "entities": health.get("entities"), "product": "GeoTrade"})
    for c in countries:
        secs = src.sectors(c["country"])
        for s in secs:
            sector_names[s["atlasSector"]] = s["name"]
        write(f"sectors/{c['country']}.json",
              [{"atlasSector": s["atlasSector"], "name": s["name"], "companyCount": s["companyCount"],
                "medianChangePct": None, "asOfTradeDate": None,
                "exposedCompanyCount": 0} for s in secs])

    published, rows = {}, {}
    for d in named.values():
        rows.setdefault((d["countryHq"], d["atlasSector"]), []).append({
            "companyUid": d["companyUid"], "commonName": d["commonName"], "legalName": d["legalName"],
            "marketCapBand": None, "marketCapUsd": None, "changePct": None,
            "citedEdgeCount": 0, "moveContext": None})
    for (iso, sec), rs in rows.items():
        rs.sort(key=lambda r: r["commonName"].lower())
        write(f"companies/{iso}/{sec}.json", rs)
        published.setdefault(iso, {})[sec] = len(rs)
    write("company.json", named)
    write("meta.json", {
        "generatedOn": datetime.date.today().isoformat(),
        "entities": health.get("entities"),
        "countries": len(countries),
        "geolocated": sum(p.get("w", 1) for p in points),
        "publishedCompanies": len(named),
        "published": published,
        "companiesWithEdges": sum(c.get("mappedCompanyCount", 0) for c in countries),
        "policy": "aggregates per country and sector + capped named sample; see docs/sources.md",
    })
    print(json.dumps({"entities": health.get("entities"), "countries": len(countries),
                      "named": len(named), "countryTiles": len(tiles)}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
