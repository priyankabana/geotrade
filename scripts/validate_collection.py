#!/usr/bin/env python3
"""Validate a collection CSV before it goes near a PR.

    python3 scripts/validate_collection.py data/companies/india.csv

Catches the mistakes that are cheap now and expensive in week 14: a guessed LEI that
would merge two companies, a market cap with no date, a delisted company silently
dropped, an alias that collides with ordinary English.
"""
import csv, sys, re, os, datetime

ISO2 = re.compile(r"^[A-Z]{2}$")
MIC  = re.compile(r"^[A-Z0-9]{4}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LEI  = re.compile(r"^[A-Z0-9]{18}\d{2}$")
ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
CIK  = re.compile(r"^\d{10}$")
UID  = re.compile(r"^[A-Z0-9]{4}:[A-Z0-9._-]+$")
CCY  = re.compile(r"^[A-Z]{3}$")

BANDS  = {"mega","large","mid","small","micro"}
STATUS = {"active","delisted","acquired","merged","suspended"}
ALIAS_TYPES = {"legal","common","former","ticker","abbreviation",
               "subsidiary","brand","local_script","transliteration"}

# Single-token aliases that are ordinary English words get flagged. This list exists
# because the first gazetteer matched OPERA inside OPERATIONS. See docs/cost.md.
try:
    ENGLISH = {w.strip().upper() for w in open("/usr/share/dict/words") if len(w.strip()) > 3}
except OSError:
    ENGLISH = set()

class Report:
    def __init__(self): self.errors, self.warnings = [], []
    def err(self, row, msg):  self.errors.append((row, msg))
    def warn(self, row, msg): self.warnings.append((row, msg))

def req(r, rep, n, col, pattern=None, allowed=None):
    v = (r.get(col) or "").strip()
    if not v:
        rep.err(n, f"{col} is required and empty"); return None
    if pattern and not pattern.match(v):
        rep.err(n, f"{col}={v!r} is malformed")
    if allowed and v not in allowed:
        rep.err(n, f"{col}={v!r} not in {sorted(allowed)}")
    return v

def opt(r, col):
    return (r.get(col) or "").strip()

def check_companies(rows, rep):
    seen_uid, seen_lei, seen_isin = {}, {}, {}
    for n, r in enumerate(rows, 2):
        acknowledged = "UNGEOCODED" in opt(r, "notes")
        uid = req(r, rep, n, "company_uid", UID)
        req(r, rep, n, "legal_name"); req(r, rep, n, "common_name")
        req(r, rep, n, "exchange_mic", MIC); req(r, rep, n, "ticker")
        if not opt(r, "country_incorporation") and acknowledged:
            rep.warn(n, "country_incorporation empty (ungeocoded row)")
        else:
            req(r, rep, n, "country_incorporation", ISO2)
        req(r, rep, n, "currency", CCY)
        req(r, rep, n, "market_cap_as_of", DATE)
        req(r, rep, n, "market_cap_band", allowed=BANDS)
        status = req(r, rep, n, "status", allowed=STATUS)
        req(r, rep, n, "source_id"); req(r, rep, n, "source_url")
        req(r, rep, n, "collected_by"); req(r, rep, n, "collected_on", DATE)

        if uid:
            if uid in seen_uid: rep.err(n, f"duplicate company_uid, first seen line {seen_uid[uid]}")
            else: seen_uid[uid] = n

        for col, pat, store in (("lei", LEI, seen_lei), ("isin", ISIN, seen_isin), ("cik", CIK, None)):
            v = opt(r, col)
            if v:
                if not pat.match(v): rep.err(n, f"{col}={v!r} is malformed")
                elif store is not None:
                    if v in store: rep.err(n, f"duplicate {col} {v} — two rows claim one company "
                                              f"(first seen line {store[v]}). If dual-listed that is "
                                              f"correct; otherwise one of them is a guess.")
                    else: store[v] = n

        if not opt(r, "lei"):
            rep.warn(n, "no LEI — this is the key that joins markets, chase it before settling")

        # A gap you have marked is a known limitation. A gap you have not marked is a
        # silent one, and silent gaps are what make a map lie.
        for col in ("hq_lat", "hq_lon"):
            v = opt(r, col)
            if not v:
                (rep.warn if acknowledged else rep.err)(
                    n, f"{col} empty — company will not render on the globe"
                    + ("" if acknowledged else "; geocode it or mark notes UNGEOCODED"))
            else:
                try:
                    f = float(v)
                    lim = 90 if col == "hq_lat" else 180
                    if abs(f) > lim: rep.err(n, f"{col}={v} out of range")
                    if abs(f) < 0.001: rep.warn(n, f"{col} is ~0 — null island, probably a failed geocode")
                except ValueError: rep.err(n, f"{col}={v!r} is not a number")

        fy = opt(r, "fiscal_year_end")
        if fy and not re.match(r"^\d{2}-\d{2}$", fy):
            rep.err(n, f"fiscal_year_end={fy!r} must be MM-DD, not a year")

        if status in ("delisted", "acquired", "merged") and not opt(r, "delisting_date"):
            rep.err(n, f"status={status} but delisting_date is empty")
        if status in ("acquired", "merged") and not opt(r, "successor_uid"):
            rep.warn(n, f"status={status} with no successor_uid — edges cannot follow the acquisition")
        if opt(r, "delisting_date") and status == "active":
            rep.err(n, "has delisting_date but status=active")

        cs = opt(r, "classification_scheme").upper()
        if cs in ("GICS", "ICB"):
            rep.err(n, f"{cs} is licensed (MSCI/S&P, FTSE) and cannot ship. "
                       f"Use SIC/NAICS/NIC/ANZSIC/NACE/WZ and map to atlas_sector.")
        if not opt(r, "description"):
            rep.warn(n, "no description — take it from the company's own words, not a model")

    actives = sum(1 for r in rows if opt(r, "status") == "active")
    if rows and actives == len(rows):
        rep.warn(0, f"all {len(rows)} companies are active — this universe has survivorship "
                    f"bias. SEC's current ticker file lists only live filers, so delisted and "
                    f"acquired companies are absent. Any backtest using it must state "
                    f"'universe as of <collected_on>'. See docs/data-model.md warning 1.")

def check_aliases(rows, rep):
    per_company = {}
    for n, r in enumerate(rows, 2):
        uid = req(r, rep, n, "company_uid", UID)
        alias = req(r, rep, n, "alias")
        req(r, rep, n, "alias_type", allowed=ALIAS_TYPES)
        req(r, rep, n, "source_id"); req(r, rep, n, "collected_by")
        req(r, rep, n, "collected_on", DATE)
        flag = opt(r, "is_ambiguous").lower()
        if flag not in ("yes", "no"):
            rep.err(n, "is_ambiguous must be yes or no")
        if flag == "yes" and not opt(r, "ambiguity_note"):
            rep.err(n, "is_ambiguous=yes needs an ambiguity_note")
        if alias:
            per_company[uid] = per_company.get(uid, 0) + 1
            toks = re.sub(r"[^A-Za-z0-9& ]", " ", alias).split()
            if len(toks) == 1 and toks[0].upper() in ENGLISH and flag != "yes":
                rep.err(n, f"alias {alias!r} is an ordinary English word but is_ambiguous=no. "
                           f"This is how OPERA matched inside OPERATIONS.")
            if len(alias) < 3 and flag != "yes":
                rep.warn(n, f"alias {alias!r} is very short — almost certainly ambiguous")
            if opt(r, "alias_type") == "former" and not opt(r, "valid_to"):
                rep.warn(n, "alias_type=former with no valid_to — when did it stop being true?")
    for uid, c in per_company.items():
        if c < 3:
            rep.warn(0, f"{uid} has only {c} alias(es). Aim for 3-8: legal, common, ticker, "
                        f"suffix-stripped, any former name.")

CHECKS = {"company_uid,legal_name": check_companies, "company_uid,alias": check_aliases}

def main(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print(f"{path}: no data rows"); return 1
    header = ",".join(list(rows[0].keys())[:2])
    fn = CHECKS.get(header)
    if not fn:
        print(f"{path}: unrecognised header starting {header!r} — no validator for this file yet")
        return 1
    rep = Report(); fn(rows, rep)
    for n, m in rep.errors:   print(f"ERROR   line {n}: {m}" if n else f"ERROR   {m}")
    for n, m in rep.warnings: print(f"warn    line {n}: {m}" if n else f"warn    {m}")
    print(f"\n{path}: {len(rows)} rows, {len(rep.errors)} errors, {len(rep.warnings)} warnings")
    return 1 if rep.errors else 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    sys.exit(max(main(p) for p in sys.argv[1:]))
