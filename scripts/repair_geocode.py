#!/usr/bin/env python3
"""Fill hq_lat/hq_lon/hq_country for rows the first geocoding pass missed.

Runs against the CSV directly - no refetch. Widens the match to GeoNames'
alternatenames column, then falls back to a country centroid, recording the
weaker precision honestly in hq_geo_precision rather than hiding it.
"""
import csv, re, sys, os, collections

GEO = os.environ.get("ATLAS_GEONAMES", "/tmp/cities15000.txt")
# EDGAR uses its own two-char country codes, not ISO 3166. Only the ones we hit.
EDGAR_CC = {
 "A0":"CA","A1":"CA","A2":"CA","A3":"CA","A4":"CA","A5":"CA","A6":"CA","A7":"CA",
 "A8":"CA","A9":"CA","B0":"CA","B2":"CA","C3":"CN","D0":"IL","D5":"IN","D8":"ID",
 "E9":"JP","F4":"KY","G7":"LU","H6":"MX","K3":"NL","L2":"IL","L3":"IT","L6":"JE",
 "M2":"MY","N4":"NO","P7":"NL","Q2":"PA","R1":"SG","T3":"CH","U0":"GB","V8":"CH",
 "X0":"GB","Y7":"VG","Y8":"BM","1K":"HK","2M":"TW","K7":"NZ","T0":"KR","B8":"BR",
}

def load():
    city, country = {}, collections.defaultdict(list)
    for line in open(GEO, encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        if len(f) < 15: continue
        try: pop = int(f[14] or 0)
        except ValueError: pop = 0
        lat, lon, cc = f[4], f[5], f[8]
        names = {f[1].upper(), f[2].upper()}
        names |= {a.strip().upper() for a in (f[3] or "").split(",")
                  if 3 < len(a.strip()) < 40 and re.fullmatch(r"[A-Za-z \-'.]+", a.strip() or "x")}
        for nm in names:
            prev = city.get(nm)
            if prev is None or pop > prev[0]:
                city[nm] = (pop, lat, lon, cc)
        country[cc].append((float(lat), float(lon), pop))
    centroid = {}
    for cc, pts in country.items():
        tot = sum(p for _a, _b, p in pts) or 1
        centroid[cc] = (sum(a * p for a, _b, p in pts) / tot,
                        sum(b * p for _a, b, p in pts) / tot)
    return city, centroid

def main(path):
    city, centroid = load()
    print(f"  index: {len(city)} city names, {len(centroid)} country centroids")
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8-sig")))
    cols = list(rows[0].keys())
    fixed_city = fixed_country = still = 0
    for r in rows:
        if r["hq_lat"]:
            continue
        raw = (r["hq_city"] or "").upper()
        c = re.sub(r"[^A-Z \-']", " ", raw)
        c = re.sub(r"\s+", " ", c).strip()
        cands = [c, re.sub(r"^(DR|ST|SAINT|THE|PO BOX|C/O)\s+", "", c)]
        toks = [t for t in c.split() if len(t) >= 4]
        if toks: cands.append(max(toks, key=len))
        hit = next((city[k] for k in cands if k in city), None)
        if hit:
            _p, la, lo, cc = hit
            r["hq_lat"], r["hq_lon"], r["hq_country"] = la, lo, cc
            r["hq_geo_precision"] = "city"
            r["country_incorporation"] = r["country_incorporation"] or cc
            fixed_city += 1
            continue
        edgar = (r.get("hq_state") or "").upper() or (r.get("notes") or "")
        cc = EDGAR_CC.get(edgar[:2], "")
        if cc and cc in centroid:
            la, lo = centroid[cc]
            r["hq_lat"], r["hq_lon"] = f"{la:.5f}", f"{lo:.5f}"
            r["hq_country"] = cc
            r["country_incorporation"] = r["country_incorporation"] or cc
            r["hq_geo_precision"] = "country"
            r["notes"] = (r["notes"] + "; " if r["notes"] else "") + "geo=country centroid, city unmatched"
            fixed_country += 1
            continue
        still += 1
        r["notes"] = (r["notes"] + "; " if r["notes"] else "") + f"UNGEOCODED city={r['hq_city']!r}"
    w = csv.DictWriter(open(path, "w", newline=""), cols); w.writeheader(); w.writerows(rows)
    print(f"  city match {fixed_city}  country centroid {fixed_country}  still unresolved {still}")
    if still:
        print("  unresolved rows keep an explicit UNGEOCODED note. They are not guessed at.")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/companies/us.csv")
