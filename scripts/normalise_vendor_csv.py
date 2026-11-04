#!/usr/bin/env python3
"""Normalise the supplied market CSVs into the Atlas collection format.

    python3 -I scripts/normalise_vendor_csv.py ../data

Does five things the raw files need before they are a database:
  1. Collapses cross-listing duplicates. Apple appears as a Frankfurt listing; without
     this, one company becomes several nodes and the graph silently splits.
  2. Maps vendor exchange codes to ISO 10383 MICs.
  3. Normalises country names (the raw data has 'Unitedkingdom', 'Uited States').
  4. Recovers hq_city from hq_address, which is 94% filled where city is 56%.
  5. Geocodes against GeoNames, country-scoped so Springfield lands in the right one.

Leaves market_cap_usd EMPTY. The source gives local currency only, and we have no
FX source with a verified licence, so a converted number would be invented.
"""
import csv, os, re, sys, glob, collections, datetime

csv.field_size_limit(10 ** 7)
ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO   = os.environ.get("ATLAS_GEONAMES", "/tmp/cities1000.txt")
TODAY = datetime.date.today().isoformat()

MIC = {"O":"XNAS","N":"XNYS","A":"XASE","TXSE":"TXSE","BSE":"XBOM","NSE":"XNSE",
       "L":"XLON","ISD":"XLON","AU":"XASX","V":"XTSX","T":"XTSE","CNX":"XCNQ",
       "DE":"XETR","F":"XFRA","SG":"XSTU","BE":"XBER","MU":"XMUN","HM":"XHAM",
       "DU":"XDUS","TG":"XGAT"}
MIC_COUNTRY = {"XNAS":"US","XNYS":"US","XASE":"US","TXSE":"US","XBOM":"IN","XNSE":"IN",
               "XLON":"GB","XASX":"AU","XTSX":"CA","XTSE":"CA","XCNQ":"CA",
               "XETR":"DE","XFRA":"DE","XSTU":"DE","XBER":"DE","XMUN":"DE",
               "XHAM":"DE","XDUS":"DE","XGAT":"DE"}
# Lower is more likely to be the company's primary listing.
PRIORITY = {"XNAS":1,"XNYS":1,"XNSE":1,"XLON":1,"XASX":1,"XTSE":1,"XETR":1,
            "XASE":2,"XBOM":2,"XTSX":2,"XFRA":2,"XCNQ":3,"TXSE":3,"XSTU":3,
            "XBER":3,"XMUN":4,"XHAM":4,"XDUS":4,"XGAT":4}

COUNTRY = {"united states":"US","usa":"US","us":"US","united state":"US","uited states":"US",
 "united kingdom":"GB","unitedkingdom":"GB","uk":"GB","great britain":"GB","england":"GB",
 "germany":"DE","deutschland":"DE","india":"IN","canada":"CA","australia":"AU",
 "ireland":"IE","switzerland":"CH","netherlands":"NL","france":"FR","japan":"JP",
 "china":"CN","hong kong":"HK","singapore":"SG","israel":"IL","sweden":"SE",
 "norway":"NO","denmark":"DK","finland":"FI","spain":"ES","italy":"IT","austria":"AT",
 "belgium":"BE","luxembourg":"LU","bermuda":"BM","cayman islands":"KY","jersey":"JE",
 "guernsey":"GG","isle of man":"IM","british virgin islands":"VG","panama":"PA",
 "brazil":"BR","mexico":"MX","south africa":"ZA","new zealand":"NZ","south korea":"KR",
 "korea":"KR","taiwan":"TW","malaysia":"MY","indonesia":"ID","thailand":"TH",
 "philippines":"PH","vietnam":"VN","russia":"RU","poland":"PL","portugal":"PT",
 "greece":"GR","turkey":"TR","czech republic":"CZ","hungary":"HU","romania":"RO",
 "argentina":"AR","chile":"CL","colombia":"CO","peru":"PE","uruguay":"UY",
 "united arab emirates":"AE","saudi arabia":"SA","qatar":"QA","kuwait":"KW",
 "egypt":"EG","nigeria":"NG","kenya":"KE","morocco":"MA","malta":"MT","cyprus":"CY",
 "iceland":"IS","liechtenstein":"LI","monaco":"MC","mauritius":"MU","sri lanka":"LK",
 "bangladesh":"BD","pakistan":"PK","nepal":"NP","kazakhstan":"KZ","ukraine":"UA"}

BAND = {"mega":"mega","large":"large","mid":"mid","small":"small","micro":"micro"}

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")

# Same rule the validator applies: a one-word alias that is also an ordinary English
# word gets flagged. "Amazon" and "Alphabet" are real company names and real words,
# and the gazetteer must not rely on them alone. Multi-token forms ("Amazon.com, Inc.")
# stay usable, so the company is still reachable.
try:
    ENGLISH_WORDS = {w.strip().upper() for w in open("/usr/share/dict/words") if len(w.strip()) > 3}
except OSError:
    ENGLISH_WORDS = set()
# Preference and preferred shares are separate securities of the same company. A
# dependency graph node must be a company: Enbridge appears 18 times in the raw data.
PREF_TICKER = re.compile(r"\.(PR|PF|P)\b|\.PR\.|\.PF\.", re.I)
PREF_NAME   = re.compile(r"\b(preference|preferred|pref\.?)\b", re.I)

def is_pref(r):
    return bool(PREF_TICKER.search(r.get("ticker") or "")
                or PREF_NAME.search(r.get("common_name") or "")
                or PREF_NAME.search(r.get("legal_name") or ""))

# classification_name is plain English ("Metals & mining sector"); the paired numeric
# codes are a vendor taxonomy we have no licence to republish, so we map from the words.
SECTOR_WORDS = [
 # Most specific first. Matched against classification_name, then description.
 (("semi equipment","wafer fab","wafer fabrication","photomask","lithograph",
   "semiconductor manufacturing equipment","semiconductor capital equipment",
   "fluid delivery","wafer handling","ion implant","chemical mechanical planar"), "SEMI_EQUIP"),
 (("semiconductor","integrated circuit","microchip"," chip ","foundry","analog ic",
   "memory chip","microcontroller","wafer"), "SEMI_DEVICES"),
 (("printed circuit","electronic component","connector","passive component",
   "contract manufactur","electronics manufacturing services","pcb"), "ELECTRONIC_COMPONENTS"),
 (("electrical manufacturing","electrical equipment","transformer","switchgear",
   "cable","battery","electric motor"), "ELECTRICAL_EQUIP"),
 (("instrument","metrology","measurement","test and measurement","sensor"), "INSTRUMENTS"),
 (("computer hardware","data storage","server","peripheral","personal computer"), "COMPUTER_HARDWARE"),
 (("telecom equipment","communications equipment","networking equipment","router"), "COMMS_EQUIPMENT"),
 (("biotechnolog","clinical-stage","clinical stage","gene therap","vaccine"), "BIOTECH"),
 (("pharmaceutic","generic drug","active pharmaceutical","drug manufactur"), "PHARMA"),
 (("medical device","medical equipment","diagnostic","surgical","healthcare equipment",
   "health care equipment"), "MEDICAL_DEVICES"),
 (("hospital","healthcare service","health care sector","managed care","clinic"), "HEALTHCARE_SERVICES"),
 (("metals & mining","metals and mining","mining sector","gold mining","copper",
   "iron ore","coal","lithium","uranium","nickel","zinc","silver","exploration"), "MINING_METALS"),
 (("steel","aluminium","aluminum","foundry metal","fabricated metal"), "METALS_STEEL"),
 (("specialty chem","chemicals sector","agrochemical","fertiliser","fertilizer",
   "coating","adhesive","polymer","petrochemical"), "SPECIALTY_CHEM"),
 (("oil & gas","oil and gas","petroleum","crude","upstream","drilling","energy sector"), "OIL_GAS_UPSTREAM"),
 (("refin","pipeline","midstream","lng"), "OIL_GAS_DOWNSTREAM"),
 (("utilit","electric power","power generation","renewable energy","solar power","water supply"), "UTILITIES"),
 (("bank sector","banking","bank ","nbfc","lending","microfinance","credit union"), "BANKS"),
 (("insurance","reinsur","assurance"), "INSURANCE"),
 (("asset management","capital market","investment trust","equity investment",
   "venture capital","private equity","brokerage","securities firm","holding company",
   "finance/nbfc","financials sector","finance sector"), "CAPITAL_MARKETS"),
 (("real estate","reit","property develop"), "REAL_ESTATE"),
 (("automobile","automotive","auto part","auto component","vehicle","tyre","tire","commercial vehicle"), "AUTO_COMPONENTS"),
 (("aerospace","defence","defense","aviation manufactur"), "AEROSPACE_DEFENSE"),
 (("machinery","industrial engineering","capital good","industrial sector","engineering sector"), "MACHINERY"),
 (("shipping","logistic","freight","marine transport","port operat","railway","rail transport",
   "airline","airport","courier","supply chain"), "SHIPPING_LOGISTICS"),
 (("construction","building material","cement","infrastructure","engineering & construction",
   "homebuild"), "CONSTRUCTION_MATERIALS"),
 (("retail","e-commerce","commercial trading & distribution","distribution sector",
   "consumer discretionary","supermarket","department store","wholesale"), "RETAIL"),
 (("food","beverage","agricultur","tobacco","brewer","dairy","sugar","tea ","coffee"), "FOOD_BEVERAGE"),
 (("textile","apparel","clothing","footwear","luxury good","garment","leather"), "TEXTILES_APPAREL"),
 (("paper","packaging","forest product","pulp"), "PAPER_PACKAGING"),
 (("media","entertainment","publish","broadcast","gaming","casino","leisure","travel",
   "hotel","restaurant","film"), "MEDIA_ENTERTAINMENT"),
 (("household","personal product","cosmetic","consumer staple","personal care"), "CONSUMER_PRODUCTS"),
 (("software","internet","it service","information technology","cloud","saas",
   "technology sector","data analytics","cyber"), "SOFTWARE"),
]
# Index names are not sectors. 7,916 German rows carry 'Total German Market ex DAX
# Index' in the classification field, which says nothing about what the company does.
NOT_A_SECTOR = re.compile(r"(?i)\bindex\b|\bmarket ex\b|\ball shares?\b|\bcomposite\b")
# Too coarse to classify on. "Technology sector" covers ASML and a payroll SaaS alike,
# so these defer to the description and are only used if the description says nothing.
GENERIC = {"technology sector","materials sector","industrial sector","financials sector",
           "finance sector","consumer sector","services sector","miscellaneous sector",
           "diversified sector","general sector","others sector","other sector"}

SIC2 = {"35":"MACHINERY","36":"ELECTRONIC_COMPONENTS","37":"AUTO_COMPONENTS","38":"INSTRUMENTS",
        "28":"SPECIALTY_CHEM","33":"METALS_STEEL","13":"OIL_GAS_UPSTREAM","10":"MINING_METALS",
        "60":"BANKS","63":"INSURANCE","65":"REAL_ESTATE","73":"SOFTWARE","80":"HEALTHCARE_SERVICES"}

COUNTRY_BY_LEN = sorted(COUNTRY.items(), key=lambda kv: -len(kv[0]))

def _name2iso(name):
    n = re.sub(r"[^a-z ]", " ", (name or "").strip().lower())
    n = re.sub(r"\s+", " ", n).strip()
    if n in COUNTRY: return COUNTRY[n]
    if len(n) == 2 and n.upper() in set(COUNTRY.values()): return n.upper()
    return ""

def country_from_address(addr):
    """The address is the only field that tells the truth about where a company sits.
    GERMANY.csv marks every row country_hq='Germany', including the Canadian and
    Japanese companies cross-listed in Frankfurt, so hq_country cannot be trusted."""
    a = re.sub(r"[^a-z ]", " ", (addr or "").lower())
    a = " " + re.sub(r"\s+", " ", a).strip() + " "
    for name, cc in COUNTRY_BY_LEN:
        if len(name) > 3 and f" {name} " in a:
            return cc
    return ""

def iso2(name, isin="", mic="", addr=""):
    return (country_from_address(addr)
            or (isin[:2].upper() if isin and isin[:2].isalpha() else "")
            or _name2iso(name)
            or MIC_COUNTRY.get(mic, ""))

def _match(txt):
    t = " " + re.sub(r"\s+", " ", (txt or "").lower()) + " "
    for words, code in SECTOR_WORDS:
        if any(w in t for w in words): return code
    return ""

def sector_for(row):
    cls = (row.get("classification_name") or "").strip()
    if NOT_A_SECTOR.search(cls): cls = ""
    generic = cls.lower() in GENERIC
    if generic:
        return (_match(row.get("description", "")[:400]) or _match(cls)
                or SIC2.get((row.get("sic") or "").strip()[:2], "") or "OTHER")
    # classification first (short and deliberate), then the description, which is
    # plain English and filled on 99.8% of rows.
    return (_match(cls)
            or _match(row.get("description", "")[:400])
            or SIC2.get((row.get("sic") or "").strip()[:2], "")
            or "OTHER")

def load_geo():
    """Index by (country, name) and also globally by name, so a row whose country we
    got wrong still geocodes off an unambiguous city name."""
    city, glob_, cen = {}, {}, collections.defaultdict(list)
    if not os.path.exists(GEO):
        print(f"  ! {GEO} missing - no geocoding"); return city, glob_, {}
    for line in open(GEO, encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        if len(f) < 15: continue
        try: pop = int(f[14] or 0)
        except ValueError: pop = 0
        cc = f[8]
        names = {f[1].upper(), f[2].upper()}
        for nm in names:
            k = (cc, nm)
            if k not in city or pop > city[k][0]: city[k] = (pop, f[4], f[5])
            if nm not in glob_ or pop > glob_[nm][0]: glob_[nm] = (pop, f[4], f[5], cc)
        cen[cc].append((float(f[4]), float(f[5]), pop))
    centroid = {cc: (sum(a*p for a,_b,p in v)/(sum(p for _a,_b,p in v) or 1),
                     sum(b*p for _a,b,p in v)/(sum(p for _a,_b,p in v) or 1))
                for cc, v in cen.items()}
    return city, glob_, centroid

POSTCODE = re.compile(r"^[\d\- ]+$|^[A-Z]{1,2}\d")
def city_candidates(row):
    out = []
    if row.get("hq_city","").strip(): out.append(row["hq_city"].strip().upper())
    addr = (row.get("hq_address") or "").upper()
    for tok in reversed([t.strip() for t in addr.split(",")]):
        tok = re.sub(r"\b\d{4,}\b", "", tok).strip(" .-")
        if 2 < len(tok) < 40 and not POSTCODE.match(tok): out.append(tok)
    return out

def main(src):
    files = sorted(glob.glob(os.path.join(src, "*.csv")))
    if not files: sys.exit(f"no CSVs in {src}")
    raw = []
    for f in files:
        with open(f, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh): raw.append(r)
    print(f"  read {len(raw):,} rows from {len(files)} files")

    # Some rows carry a ticker or a BSE scrip code in the ISIN column. A malformed
    # ISIN is worse than none: it would group unrelated companies during dedupe.
    bad_isin = 0
    for r in raw:
        v = (r.get("isin") or "").strip().upper()
        if v and not ISIN_RE.match(v):
            r["isin"] = ""; bad_isin += 1
    if bad_isin: print(f"  blanked {bad_isin} malformed ISINs")

    # ---- 1. dedupe cross-listings by ISIN ------------------------------------
    groups = collections.defaultdict(list)
    singles = []
    for r in raw:
        isin = (r.get("isin") or "").strip().upper()
        (groups[isin] if isin else singles).append(r)

    def score(r):
        mic = MIC.get((r.get("exchange_code") or "").strip(), "")
        isin = (r.get("isin") or "").strip().upper()
        home = 0 if (isin[:2] and MIC_COUNTRY.get(mic) == isin[:2]) else 1
        return (home, PRIORITY.get(mic, 9), -(float(r.get("shares_outstanding") or 0) or 0))

    kept, dropped = [], 0
    for isin, rows in groups.items():
        rows.sort(key=score)
        kept.append(rows[0]); dropped += len(rows) - 1
        rows[0]["_also_listed"] = "|".join(
            f"{MIC.get(x.get('exchange_code',''),'?')}:{x.get('ticker','')}" for x in rows[1:])
    kept += singles
    print(f"  collapsed {dropped:,} cross-listing duplicates -> {len(kept):,} securities")

    # ---- 1b. collapse share classes by LEI -----------------------------------
    by_lei = collections.defaultdict(list)
    no_lei = []
    for r in kept:
        lei = (r.get("lei") or "").strip().upper()
        (by_lei[lei] if len(lei) == 20 else no_lei).append(r)

    def class_score(r):
        # ordinary share first, then the shortest ticker, then the largest float
        return (1 if is_pref(r) else 0, len(r.get("ticker") or ""),
                -(float(r.get("shares_outstanding") or 0) or 0))

    merged, pref_dropped = [], 0
    for lei, group in by_lei.items():
        group.sort(key=class_score)
        head = group[0]
        extra = [f"{MIC.get(x.get('exchange_code',''),'?')}:{x.get('ticker','')}" for x in group[1:]]
        if extra:
            head["_also_listed"] = "|".join(
                filter(None, [head.get("_also_listed", "")] + extra))
        pref_dropped += len(group) - 1
        merged.append(head)
    kept = merged + no_lei
    print(f"  collapsed {pref_dropped:,} share classes by LEI -> {len(kept):,} companies")

    # ---- 2. geocode ----------------------------------------------------------
    city, glob_, centroid = load_geo()
    print(f"  geocoder: {len(city):,} (country,city) pairs, {len(glob_):,} global names")

    out = collections.defaultdict(list)
    aliases = collections.defaultdict(list)
    stat = collections.Counter()
    seen_uid = set()

    for r in kept:
        mic = MIC.get((r.get("exchange_code") or "").strip(), "")
        if not mic: stat["no_mic"] += 1; continue
        tk = re.sub(r"[^A-Za-z0-9._-]", "", (r.get("ticker") or "").strip().upper())
        if not tk: stat["no_ticker"] += 1; continue
        uid = f"{mic}:{tk}"
        if uid in seen_uid: stat["dupe_uid"] += 1; continue
        seen_uid.add(uid)

        isin_v = (r.get("isin") or "").strip().upper()
        cc = iso2(r.get("hq_country") or r.get("country_hq"), isin_v, mic,
                  r.get("hq_address") or "")

        lat = lon = ""; prec = ""; city_name = ""
        cands = city_candidates(r)
        for cand in cands:
            if cc and (cc, cand) in city:
                _p, lat, lon = city[(cc, cand)]; prec = "city"; city_name = cand.title(); break
        if not lat:
            # country may be wrong; fall back to the most populous city of that name
            for cand in cands:
                hit = glob_.get(cand)
                if hit and hit[0] >= 20000:
                    _p, lat, lon, hcc = hit
                    prec = "city"; city_name = cand.title()
                    # The address named no country, so trust where the city actually is
                    # over an ISIN prefix (Ichor is Cayman-registered, Fremont-based).
                    if not cc or not country_from_address(r.get("hq_address") or ""):
                        cc = hcc
                    break
        if not lat and cc and cc in centroid:
            la, lo = centroid[cc]; lat, lon = f"{la:.5f}", f"{lo:.5f}"; prec = "country"
        stat[f"geo_{prec or 'none'}"] += 1

        band = BAND.get((r.get("market_cap_band") or "").strip().lower(), "")
        market = r["market"]
        note = []
        if r.get("_also_listed"): note.append("also listed " + r["_also_listed"])
        if not lat: note.append("UNGEOCODED")
        if prec == "country": note.append("geo=country centroid")

        out[market].append({
          "company_uid": uid, "legal_name": r["legal_name"], "common_name": r["common_name"],
          "former_names": r.get("former_names","").replace(" | ","|"),
          "ticker": tk, "exchange_mic": mic,
          "country_incorporation": isin_v[:2] if isin_v[:2].isalpha() else cc,
          "country_hq": cc, "cik": "", "lei": (r.get("lei") or "").strip(),
          # SEDOL and CUSIP are licensed. Dropped at the boundary rather than carried
          # into our store and remembered about later. ISIN, LEI and CIK are the keys
          # we can actually publish.
          "isin": isin_v, "sedol": "", "cusip": "",
          "figi": (r.get("figi") or "").strip(),
          "classification_scheme": "NAICS" if r.get("naics") else ("SIC" if r.get("sic") else "VENDOR_TEXT"),
          "classification_code": (r.get("naics") or r.get("sic") or "").strip(),
          "classification_name": (r.get("classification_name") or "").strip(),
          "atlas_sector": sector_for(r),
          "market_cap_usd": "", "market_cap_local": (r.get("market_cap_local") or "").strip(),
          "currency": (r.get("currency") or "").strip(),
          "market_cap_as_of": (r.get("market_cap_as_of") or "").strip() or TODAY,
          "market_cap_band": band or "micro",
          "market_cap_band_basis": "vendor_supplied" if band else "default:micro",
          "shares_outstanding": (r.get("shares_outstanding") or "").strip(),
          "free_float_pct": "", "fiscal_year_end": "",
          "listing_date": (r.get("listing_date") or "").strip(), "delisting_date": "",
          "status": "active", "successor_uid": "",
          "website": (r.get("website") or "").strip(), "ir_url": (r.get("ir_url") or "").strip(),
          "filings_url": (r.get("filings_url") or "").strip(),
          "hq_address": (r.get("hq_address") or "").strip(),
          "hq_city": city_name or (r.get("hq_city") or "").title(),
          "hq_state": (r.get("hq_state") or "").strip(), "hq_country": cc,
          "hq_lat": lat, "hq_lon": lon, "hq_geo_precision": prec,
          "employees": (r.get("employees") or "").strip(), "employees_as_of": "",
          "description": (r.get("description") or "").strip()[:600],
          "index_membership": (r.get("index_membership") or "").strip(),
          "source_id": "vendor-market-csv", "source_url": f"data/{market}.csv",
          "collected_by": (r.get("collected_by") or "team").strip(),
          "collected_on": (r.get("collected_on") or "").strip() or TODAY,
          "notes": "; ".join(note),
        })

        def al(txt, typ):
            txt = (txt or "").strip()
            if not txt: return
            toks = re.sub(r"[^A-Za-z0-9& ]", " ", txt).split()
            amb = len(toks) == 1 and (len(txt) < 5 or toks[0].upper() in ENGLISH_WORDS)
            aliases[market].append({"company_uid": uid, "alias": txt, "alias_type": typ,
              "language":"en","script":"latin","valid_from":"","valid_to":"",
              "is_ambiguous":"yes" if amb else "no",
              "ambiguity_note":("single token that is also an ordinary English word"
                                if amb else ""),
              "source_id":"vendor-market-csv","source_url":f"data/{market}.csv",
              "collected_by":"normalise_vendor_csv.py","collected_on":TODAY})
        al(r["legal_name"], "legal"); al(r["common_name"], "common"); al(tk, "ticker")
        for fn in (r.get("former_names") or "").split("|"): al(fn, "former")
        for ft in (r.get("former_tickers") or "").split("|"): al(ft, "ticker")

    CCOLS = list(out[next(iter(out))][0].keys())
    ACOLS = ["company_uid","alias","alias_type","language","script","valid_from","valid_to",
             "is_ambiguous","ambiguity_note","source_id","source_url","collected_by","collected_on"]
    cdir = os.path.join(ROOT, "data/companies"); adir = os.path.join(ROOT, "data/aliases")
    os.makedirs(cdir, exist_ok=True); os.makedirs(adir, exist_ok=True)
    tot = ta = 0
    for market, rows in sorted(out.items()):
        slug = market.lower().replace("-", "_")
        with open(os.path.join(cdir, f"{slug}.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, CCOLS); w.writeheader(); w.writerows(rows)
        with open(os.path.join(adir, f"{slug}.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, ACOLS); w.writeheader(); w.writerows(aliases[market])
        print(f"  {slug:12} {len(rows):6,} companies  {len(aliases[market]):6,} aliases")
        tot += len(rows); ta += len(aliases[market])
    print(f"  {'TOTAL':12} {tot:6,} companies  {ta:6,} aliases")
    print("  " + "  ".join(f"{k}={v:,}" for k, v in sorted(stat.items())))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../data")
