#!/usr/bin/env python3
"""Build data/companies/us.csv and data/aliases/us.csv from SEC primary sources.

Sources, all free and licence-clear (see docs/sources.md):
  company_tickers_exchange.json  ticker, CIK, legal name, exchange  (market-cap ordered)
  data.sec.gov/submissions/      SIC, HQ address, fiscal year end, former names, filer size
  US-Cities-Database (MIT)       city -> lat/lon

Nothing here is invented. Where SEC does not publish a field (market cap, LEI, ISIN)
the column is left empty for a human to fill rather than guessed.
"""
import csv, json, gzip, os, re, sys, time, urllib.request, datetime, threading
from concurrent.futures import ThreadPoolExecutor

UA   = os.environ.get("ATLAS_UA", "Atlas Capstone Research contact@example.com")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP  = os.environ.get("ATLAS_TMP", "/tmp")
TOP_N = int(os.environ.get("ATLAS_TOP_N", "2000"))
# Pilot-slice companies that rank below TOP_N by market cap but are required by
# docs/coverage-universe.md. The inversion lives in the small caps, so the universe
# must not be a pure market-cap truncation.
FORCE = {"UCTT","ICHR","CRUS","FORM","PLAB","KLIC","ONTO","ACLS","AMKR","COHU","AEIS",
         "MKSI","VECO","NVMI","CAMT","BHE","SANM","PLXS","TTMI","OSIS","SWKS","QRVO",
         "AMAT","LRCX","KLAC","INTC","MU","TXN","NVDA","AAPL"}
TODAY = datetime.date.today().isoformat()

MIC = {"Nasdaq": "XNAS", "NYSE": "XNYS", "NYSE American": "XASE",
       "NYSEAmerican": "XASE", "CBOE": "XCBO", "TXSE": "TXSE"}

_lock = threading.Lock()
_next = [0.0]
RATE = 9.0           # requests/sec, under SEC's published 10/s ceiling

def _throttle():
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _next[0] - now)
        _next[0] = max(now, _next[0]) + 1.0 / RATE
    if wait:
        time.sleep(wait)

def get(url, dest=None):
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                d = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    d = gzip.decompress(d)
                if dest:
                    open(dest, "wb").write(d)
                return d.decode("utf-8", "replace")
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))

# ---------------------------------------------------------------- sectors
# First-pass SIC -> atlas_sector mapping. Supply-chain shaped, not finance shaped:
# SEMI_EQUIP and SEMI_MATERIALS are separate because a photoresist shortage hits one
# and not the other, even though a finance taxonomy calls both "Information Technology".
# NEEDS HUMAN REVIEW - this is a starting point, not a finished taxonomy.
SECTORS = [
 ("SEMI_DEVICES","Semiconductor Devices","TECH_HARDWARE","Designers and makers of integrated circuits and discrete semiconductors.",["3674"]),
 ("SEMI_EQUIP","Semiconductor Equipment & Subsystems","TECH_HARDWARE","Capital equipment and subsystems used to fabricate semiconductors.",["3559"]),
 ("ELECTRONIC_COMPONENTS","Electronic Components & PCBs","TECH_HARDWARE","Passive components, connectors, printed circuit boards, assemblies.",["3670","3672","3677","3678","3679"]),
 ("INSTRUMENTS","Measurement & Test Instruments","TECH_HARDWARE","Metrology, inspection, laboratory and industrial instruments.",["3812","3821","3822","3823","3824","3825","3826","3827","3829"]),
 ("COMPUTER_HARDWARE","Computer Hardware & Storage","TECH_HARDWARE","Computers, peripherals, storage systems.",["3570","3571","3572","3575","3576","3577","3578","3579"]),
 ("COMMS_EQUIPMENT","Communications Equipment","TECH_HARDWARE","Telecom and network equipment.",["3661","3663","3669"]),
 ("ELECTRICAL_EQUIP","Electrical Equipment","INDUSTRIALS","Motors, transformers, switchgear, batteries, lighting.",["3600","3612","3613","3620","3621","3630","3634","3640","3641","3645","3646","3648","3651","3652","3690","3691","3694","3695"]),
 ("AUTO_OEM","Automotive OEM","CONSUMER_DURABLES","Vehicle manufacturers.",["3711","3713","3716"]),
 ("AUTO_COMPONENTS","Automotive Components","CONSUMER_DURABLES","Parts and systems supplied to vehicle manufacturers.",["3714","3715","3751","3792","3465","3694"]),
 ("AEROSPACE_DEFENSE","Aerospace & Defence","INDUSTRIALS","Aircraft, spacecraft, defence systems and their suppliers.",["3720","3721","3724","3728","3760","3761","3764","3769","3480","3489"]),
 ("MACHINERY","Industrial Machinery","INDUSTRIALS","General and special industry machinery.",["3510","3520","3523","3524","3530","3531","3532","3533","3537","3540","3541","3550","3555","3560","3561","3562","3564","3567","3569","3580","3585","3590"]),
 ("METALS_STEEL","Steel & Fabricated Metals","MATERIALS","Primary metals, steel, fabricated metal products.",["3310","3312","3313","3315","3316","3317","3320","3330","3334","3341","3350","3357","3360","3390","3411","3412","3420","3430","3440","3443","3444","3448","3450","3460","3470"]),
 ("MINING_METALS","Mining & Metal Ores","MATERIALS","Extraction of metal ores and minerals.",["1000","1040","1090","1220","1221","1400","1040"]),
 ("CHEMICALS_BASIC","Basic Chemicals","MATERIALS","Commodity industrial and agricultural chemicals.",["2800","2810","2820","2821","2860","2890"]),
 ("SPECIALTY_CHEM","Specialty Chemicals","MATERIALS","Formulated chemicals, coatings, adhesives, electronic materials.",["2840","2842","2844","2851","2870","2891","3080","3081","3086","3089"]),
 ("PHARMA","Pharmaceuticals","HEALTHCARE","Drug manufacturers, generics and APIs.",["2834","2835","2836"]),
 ("MEDICAL_DEVICES","Medical Devices","HEALTHCARE","Surgical, diagnostic and therapeutic devices.",["3841","3842","3843","3844","3845","3851"]),
 ("HEALTHCARE_SERVICES","Healthcare Services","HEALTHCARE","Hospitals, clinics, labs, managed care.",["8000","8011","8060","8062","8071","8090","8093","6324"]),
 ("BIOTECH","Biotechnology & Research","HEALTHCARE","Research-stage biotech and contract research.",["8731"]),
 ("OIL_GAS_UPSTREAM","Oil & Gas Upstream","ENERGY","Exploration, drilling and production.",["1311","1381","1382","1389"]),
 ("OIL_GAS_DOWNSTREAM","Refining & Pipelines","ENERGY","Refining, midstream and distribution.",["2911","2990","4610","4612","4613","5172"]),
 ("UTILITIES","Utilities","UTILITIES","Electric, gas and water utilities.",["4911","4922","4923","4924","4931","4932","4941","4991"]),
 ("SHIPPING_LOGISTICS","Shipping & Logistics","TRANSPORT","Marine transport, freight forwarding, warehousing, trucking.",["4400","4412","4210","4213","4220","4231","4700","4731"]),
 ("AIRLINES","Airlines & Air Freight","TRANSPORT","Passenger and cargo aviation.",["4512","4513","4522","4581"]),
 ("RAIL","Railroads","TRANSPORT","Rail transport.",["4011"]),
 ("SOFTWARE","Software","TECH_SERVICES","Packaged software and SaaS.",["7372","7371","7373"]),
 ("IT_SERVICES","IT & Internet Services","TECH_SERVICES","Data processing, hosting, internet services, IT consulting.",["7370","7374","7379","7389"]),
 ("FOOD_BEVERAGE","Food & Beverage","CONSUMER_STAPLES","Food processing, beverages, tobacco.",["2000","2011","2013","2020","2024","2030","2040","2050","2052","2060","2070","2080","2082","2086","2090","2092","2100","2111"]),
 ("TEXTILES_APPAREL","Textiles & Apparel","CONSUMER_DISCRETIONARY","Fabrics, clothing, footwear.",["2200","2211","2250","2253","2273","2300","2320","2330","2340","3021","3140"]),
 ("PAPER_PACKAGING","Paper & Packaging","MATERIALS","Pulp, paper, containers and packaging.",["2600","2611","2621","2631","2650","2653","2670","2673","3220","3221","3411"]),
 ("CONSTRUCTION_MATERIALS","Construction & Building Materials","INDUSTRIALS","Contractors, cement, glass, aggregates.",["1520","1531","1540","1600","1623","1700","3241","3270","3272","3281","2400","2430","2451"]),
 ("RETAIL","Retail & Distribution","CONSUMER_DISCRETIONARY","Wholesale and retail trade.",["5000","5010","5020","5030","5040","5045","5047","5050","5063","5064","5065","5070","5080","5090","5100","5110","5122","5130","5140","5150","5160","5171","5190","5200","5211","5311","5331","5399","5400","5411","5412","5500","5531","5600","5621","5651","5661","5700","5712","5731","5734","5735","5810","5812","5900","5912","5940","5944","5945","5960","5961","5990"]),
 ("BANKS","Banks & Lending","FINANCIALS","Deposit-taking and lending institutions.",["6020","6021","6022","6035","6036","6099","6111","6141","6153","6159","6162","6163","6199"]),
 ("INSURANCE","Insurance","FINANCIALS","Life, property, casualty and trade-credit insurers.",["6311","6321","6331","6351","6361","6399","6411"]),
 ("CAPITAL_MARKETS","Capital Markets & Asset Management","FINANCIALS","Brokers, exchanges, asset managers, holding companies.",["6200","6211","6221","6282","6770","6726","6189"]),
 ("REAL_ESTATE","Real Estate & REITs","REAL_ESTATE","Property owners, developers and REITs.",["6500","6510","6512","6513","6519","6531","6552","6798"]),
 ("MEDIA_ENTERTAINMENT","Media & Entertainment","COMMUNICATION","Broadcasting, publishing, film, gaming.",["2711","2721","2731","2741","4813","4822","4832","4833","4841","4899","7812","7819","7822","7829","7900","7948","7990","7993","7996"]),
 ("CONSUMER_PRODUCTS","Household & Personal Products","CONSUMER_STAPLES","Cleaning, personal care, household durables.",["2840","3060","3080","3630","3944","3949","3990","3960"]),
 ("OTHER","Unclassified","OTHER","SIC code not yet mapped. Needs human review.",[]),
]
SIC2SECTOR = {}
for code, _n, _p, _d, sics in SECTORS:
    for s in sics:
        SIC2SECTOR.setdefault(s, code)

SIC_PREFIX = [("35","MACHINERY"),("36","ELECTRICAL_EQUIP"),("37","AUTO_COMPONENTS"),
              ("38","INSTRUMENTS"),("28","SPECIALTY_CHEM"),("33","METALS_STEEL"),
              ("34","METALS_STEEL"),("20","FOOD_BEVERAGE"),("22","TEXTILES_APPAREL"),
              ("23","TEXTILES_APPAREL"),("26","PAPER_PACKAGING"),("27","MEDIA_ENTERTAINMENT"),
              ("13","OIL_GAS_UPSTREAM"),("10","MINING_METALS"),("12","MINING_METALS"),
              ("16","CONSTRUCTION_MATERIALS"),("15","CONSTRUCTION_MATERIALS"),
              ("17","CONSTRUCTION_MATERIALS"),("24","CONSTRUCTION_MATERIALS"),
              ("32","CONSTRUCTION_MATERIALS"),("49","UTILITIES"),("48","MEDIA_ENTERTAINMENT"),
              ("47","SHIPPING_LOGISTICS"),("44","SHIPPING_LOGISTICS"),("42","SHIPPING_LOGISTICS"),
              ("45","AIRLINES"),("40","RAIL"),("41","SHIPPING_LOGISTICS"),("46","OIL_GAS_DOWNSTREAM"),
              ("50","RETAIL"),("51","RETAIL"),("52","RETAIL"),("53","RETAIL"),("54","RETAIL"),
              ("55","RETAIL"),("56","RETAIL"),("57","RETAIL"),("58","RETAIL"),("59","RETAIL"),
              ("60","BANKS"),("61","BANKS"),("62","CAPITAL_MARKETS"),("63","INSURANCE"),
              ("64","INSURANCE"),("65","REAL_ESTATE"),("67","CAPITAL_MARKETS"),
              ("73","IT_SERVICES"),("80","HEALTHCARE_SERVICES"),("87","BIOTECH"),
              ("29","OIL_GAS_DOWNSTREAM"),("30","SPECIALTY_CHEM"),("31","TEXTILES_APPAREL"),
              ("39","CONSUMER_PRODUCTS"),("79","MEDIA_ENTERTAINMENT"),("78","MEDIA_ENTERTAINMENT"),
              ("21","FOOD_BEVERAGE"),("25","CONSTRUCTION_MATERIALS")]

def sector_for(sic):
    if not sic: return "OTHER"
    sic = str(sic).strip().zfill(4)
    if sic in SIC2SECTOR: return SIC2SECTOR[sic]
    for p, s in SIC_PREFIX:
        if sic.startswith(p): return s
    return "OTHER"

# market cap band from the SEC file's own market-cap ordering. A RANK PROXY, not a
# measured market cap - recorded as such in market_cap_band_basis so nobody mistakes it.
def band_for_rank(rank):
    if rank < 50:    return "mega"
    if rank < 600:   return "large"
    if rank < 1400:  return "mid"
    return "small"

SUFFIX = re.compile(r"[,\.]?\s*\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|LLC|PLC|NV|SA|AG|LP|HOLDINGS|HOLDING|GROUP|TRUST|THE)\b\.?", re.I)
TAIL   = re.compile(r"\s*/[A-Z]{2,4}\b.*$")
try:
    ENGLISH = {w.strip().upper() for w in open("/usr/share/dict/words") if len(w.strip()) > 3}
except OSError:
    ENGLISH = set()

def titleish(n):
    """SEC stores many names SHOUTED. Make a readable common name without losing meaning."""
    n = TAIL.sub("", n).strip().rstrip(",")
    if n.isupper() and len(n) > 4:
        small = {"OF","AND","THE","FOR","A","AN","IN","ON","AT","TO","DE","LA"}
        parts = []
        for i, w in enumerate(n.split()):
            if w in ("USA","US","USA.","LLC","PLC","NV","SA","AG","LP","III","II","IV","IT","AI"):
                parts.append(w)
            elif w.lower() in small and i:
                parts.append(w.lower())
            else:
                parts.append(w.capitalize())
        n = " ".join(parts)
    return n

def short_name(n):
    s = SUFFIX.sub(" ", TAIL.sub("", n))
    return re.sub(r"\s+", " ", s).strip(" ,.&-")

def main():
    print(f"[{time.strftime('%H:%M:%S')}] fetching company_tickers_exchange.json")
    cte = json.loads(get("https://www.sec.gov/files/company_tickers_exchange.json"))
    rows = cte["data"]
    print(f"  {len(rows)} filers, market-cap ordered")

    # ---- gazetteer: every exchange-listed + OTC name, no API calls needed
    gaz_path = os.path.join(ROOT, "data/reference/us_filer_gazetteer.csv")
    with open(gaz_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cik","legal_name","short_name","ticker","exchange","rank","is_ambiguous"])
        for i, (cik, name, tk, ex) in enumerate(rows):
            sn = short_name(name)
            amb = "yes" if (len(sn.split()) == 1 and sn.upper() in ENGLISH) or len(sn) < 4 else "no"
            w.writerow([str(cik).zfill(10), name, sn, tk or "", ex or "", i, amb])
    print(f"  wrote gazetteer: {len(rows)} names -> {gaz_path}")

    # ---- geocoder
    cities = {}
    cpath = os.path.join(TMP, "uscities.csv")
    if os.path.exists(cpath):
        for r in csv.DictReader(open(cpath)):
            cities[(r["STATE_CODE"].upper(), r["CITY"].upper())] = (r["LATITUDE"], r["LONGITUDE"])
        print(f"  geocoder: {len(cities)} US cities")
    state_centroid = {}
    for (st, _c), (la, lo) in cities.items():
        state_centroid.setdefault(st, []).append((float(la), float(lo)))
    state_centroid = {k: (sum(a for a, _ in v)/len(v), sum(b for _, b in v)/len(v))
                      for k, v in state_centroid.items()}

    # GeoNames cities15000 (CC BY 4.0). SEC leaves stateOrCountry empty for most
    # foreign filers, so the only usable signal is the city string.
    world = {}
    gpath = os.path.join(TMP, "cities15000.txt")
    if os.path.exists(gpath):
        for line in open(gpath, encoding="utf-8"):
            f = line.rstrip("\n").split("\t")
            if len(f) < 15: continue
            try: pop = int(f[14] or 0)
            except ValueError: pop = 0
            for nm in {f[1].upper(), f[2].upper()}:
                prev = world.get(nm)
                if prev is None or pop > prev[0]:
                    world[nm] = (pop, f[4], f[5], f[8])
        print(f"  geocoder: {len(world)} world cities (GeoNames, CC BY 4.0)")

    def geocode_world(city):
        """Exact city match, then the longest token. Returns (lat, lon, cc) or None."""
        if not city: return None
        c = re.sub(r"[^A-Z \-']", " ", city.upper()).strip()
        for key in (c, re.sub(r"^(DR|ST|SAINT|THE)\s+", "", c)):
            if key in world:
                _p, la, lo, cc = world[key]; return (la, lo, cc)
        toks = [t for t in c.split() if len(t) >= 4]
        if toks:
            best = max(toks, key=len)
            if best in world:
                _p, la, lo, cc = world[best]; return (la, lo, cc)
        return None

    listed = [(i, r) for i, r in enumerate(rows) if r[3] in MIC]
    targets = listed[:TOP_N]
    have = {r[2] for _i, r in targets}
    forced = [(i, r) for i, r in listed if r[2] in FORCE and r[2] not in have]
    targets += forced
    print(f"  +{len(forced)} forced pilot tickers below rank {TOP_N}: "
          f"{', '.join(sorted(r[2] for _i, r in forced))}")
    print(f"[{time.strftime('%H:%M:%S')}] fetching {len(targets)} submissions at ~9/s "
          f"(~{len(targets)//9//60}m{len(targets)//9%60}s)")

    cdir = os.path.join(ROOT, "data/companies"); os.makedirs(cdir, exist_ok=True)
    adir = os.path.join(ROOT, "data/aliases");   os.makedirs(adir, exist_ok=True)
    cfh = open(os.path.join(cdir, "us.csv"), "w", newline="")
    afh = open(os.path.join(adir, "us.csv"), "w", newline="")
    CCOLS = ["company_uid","legal_name","common_name","former_names","ticker","exchange_mic",
        "country_incorporation","country_hq","cik","lei","isin","sedol","cusip","figi",
        "classification_scheme","classification_code","classification_name","atlas_sector",
        "market_cap_usd","market_cap_local","currency","market_cap_as_of","market_cap_band",
        "market_cap_band_basis","shares_outstanding","free_float_pct","fiscal_year_end",
        "listing_date","delisting_date","status","successor_uid","website","ir_url","filings_url",
        "hq_address","hq_city","hq_state","hq_country","hq_lat","hq_lon","hq_geo_precision",
        "employees","employees_as_of","description","index_membership","source_id","source_url",
        "collected_by","collected_on","notes"]
    ACOLS = ["company_uid","alias","alias_type","language","script","valid_from","valid_to",
             "is_ambiguous","ambiguity_note","source_id","source_url","collected_by","collected_on"]
    cw = csv.DictWriter(cfh, CCOLS); cw.writeheader()
    aw = csv.DictWriter(afh, ACOLS); aw.writeheader()

    ok = fail = nalias = 0
    results = {}
    lock2 = threading.Lock()

    def fetch(item):
        nonlocal ok, fail
        rank, (cik, name, tk, ex) = item
        cik10 = str(cik).zfill(10)
        try:
            sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik10}.json"))
        except Exception as e:
            with lock2:
                fail += 1
            return
        with lock2:
            results[rank] = (cik10, name, tk, ex, sub)
            ok += 1
            if ok % 250 == 0:
                print(f"  [{time.strftime('%H:%M:%S')}] {ok}/{len(targets)} fetched", flush=True)

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(fetch, targets))
    print(f"  [{time.strftime('%H:%M:%S')}] fetched {ok}, failed {fail}; writing CSVs", flush=True)

    for rank in sorted(results):
        cik10, name, tk, ex, sub = results[rank]
        uid = f"{MIC[ex]}:{tk}"
        a = (sub.get("addresses") or {}).get("business") or {}
        soc = (a.get("stateOrCountry") or "").upper()
        city = (a.get("city") or "").upper()
        is_us_state = soc in state_centroid
        lat = lon = ""; prec = ""; cc = ""
        if is_us_state and (soc, city) in cities:
            lat, lon = cities[(soc, city)]; prec = "city"; cc = "US"
        else:
            hit = geocode_world(city)
            if hit:
                lat, lon, cc = hit; prec = "city"
            elif is_us_state:
                la, lo = state_centroid[soc]
                lat, lon, cc, prec = f"{la:.5f}", f"{lo:.5f}", "US", "state"
        if is_us_state: cc = "US"

        fye = (sub.get("fiscalYearEnd") or "").strip()
        fye = f"{fye[:2]}-{fye[2:]}" if len(fye) == 4 else ""
        formers = [f.get("name","") for f in (sub.get("formerNames") or []) if f.get("name")]
        legal = sub.get("name") or name
        sic = (sub.get("sic") or "").strip()

        cw.writerow({
          "company_uid": uid, "legal_name": legal, "common_name": titleish(short_name(legal)),
          "former_names": "|".join(formers), "ticker": tk, "exchange_mic": MIC[ex],
          # SEC's stateOrCountry uses EDGAR's own code list, not ISO 3166, and is
          # frequently empty for foreign filers. Derive country from the geocoder
          # instead of guessing, and leave it blank rather than defaulting to US.
          "country_incorporation": "US" if is_us_state else cc,
          "country_hq": cc,
          "cik": cik10, "lei": "", "isin": "", "sedol": "", "cusip": "", "figi": "",
          "classification_scheme": "SIC", "classification_code": sic,
          "classification_name": sub.get("sicDescription") or "",
          "atlas_sector": sector_for(sic),
          "market_cap_usd": "", "market_cap_local": "", "currency": "USD",
          "market_cap_as_of": TODAY, "market_cap_band": band_for_rank(rank),
          "market_cap_band_basis": f"sec_file_rank:{rank}",
          "shares_outstanding": "", "free_float_pct": "", "fiscal_year_end": fye,
          "listing_date": "", "delisting_date": "", "status": "active", "successor_uid": "",
          "website": sub.get("website") or "", "ir_url": sub.get("investorWebsite") or "",
          "filings_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik10}&type=10-K",
          "hq_address": " ".join(x for x in (a.get("street1"), a.get("street2")) if x),
          "hq_city": (a.get("city") or "").title(), "hq_state": soc if is_us_state else "",
          "hq_country": cc,
          "hq_lat": lat, "hq_lon": lon, "hq_geo_precision": prec,
          "employees": "", "employees_as_of": "", "description": "", "index_membership": "",
          "source_id": "sec-submissions",
          "source_url": f"https://data.sec.gov/submissions/CIK{cik10}.json",
          "collected_by": "build_us_universe.py", "collected_on": TODAY,
          "notes": f"filer_category={sub.get('category') or ''}",
        })

        seen = set()
        def alias(txt, typ, vf="", vt=""):
            nonlocal nalias
            txt = (txt or "").strip()
            key = (txt.upper(), typ)
            if not txt or key in seen: return
            seen.add(key)
            toks = re.sub(r"[^A-Za-z0-9& ]", " ", txt).split()
            amb = (len(toks) == 1 and toks[0].upper() in ENGLISH) or len(txt) < 4
            aw.writerow({"company_uid": uid, "alias": txt, "alias_type": typ, "language": "en",
                "script": "latin", "valid_from": vf, "valid_to": vt,
                "is_ambiguous": "yes" if amb else "no",
                "ambiguity_note": "single token is an ordinary English word" if amb else "",
                "source_id": "sec-submissions",
                "source_url": f"https://data.sec.gov/submissions/CIK{cik10}.json",
                "collected_by": "build_us_universe.py", "collected_on": TODAY})
            nalias += 1

        alias(legal, "legal")
        alias(titleish(short_name(legal)), "common")
        alias(short_name(legal), "abbreviation")
        alias(tk, "ticker")
        for f in (sub.get("formerNames") or []):
            alias(f.get("name"), "former", (f.get("from") or "")[:10], (f.get("to") or "")[:10])


    cfh.close(); afh.close()

    spath = os.path.join(ROOT, "data/reference/sectors.csv")
    with open(spath, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["atlas_sector_code","name","parent_code","definition","example_companies",
                    "maps_sic","maps_naics","maps_nace","maps_nic","maps_anzsic","maps_wz"])
        for code, nm, parent, defn, sics in SECTORS:
            w.writerow([code, nm, parent, defn, "", "|".join(sics), "", "", "", "", ""])

    print(f"\n[{time.strftime('%H:%M:%S')}] DONE  companies={ok} failed={fail} aliases={nalias}")
    print(f"  data/companies/us.csv  data/aliases/us.csv")
    print(f"  data/reference/sectors.csv ({len(SECTORS)} sectors)")
    print(f"  data/reference/us_filer_gazetteer.csv ({len(rows)} names)")

if __name__ == "__main__":
    main()
