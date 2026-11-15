"""v2 - fixes the two bugs v1 exposed:
   (1) substring gazetteer matching (OPERA inside OPERATIONS) -> token n-gram matching
   (2) single-token company names that are ordinary English words -> suppressed via wordlist
   Also fixes Item segmentation by matching item-number + expected heading text.
"""
import json, re, time, urllib.request, html, gzip, statistics

UA = "Atlas Capstone Research contact@example.com"
CHUNK_TOK, OVERLAP_TOK, CPT = 1200, 150, 4

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = r.read()
                if r.headers.get("Content-Encoding") == "gzip": d = gzip.decompress(d)
                return d.decode("utf-8", "replace")
        except Exception:
            if a == 2: raise
            time.sleep(2)

def strip_html(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s)

ENGLISH = {w.strip().upper() for w in open("/usr/share/dict/words") if len(w.strip()) > 3}
EXTRA_STOP = {"TARGET","STRATEGY","PATTERN","RELIABILITY","PROGRESS","MARATHON","SUMMIT","PIONEER",
              "FRONTIER","HERITAGE","LIBERTY","SENTINEL","VANTAGE","MOMENTUM","CATALYST","BENCHMARK",
              "ADVANTAGE","PRECISION","RESOLUTE","INTEGRA","SYNERGY","VERTEX","APEX","NOVA","ORION"}
SUFFIX = re.compile(r"\b(INC|CORP|CORPORATION|CO|LTD|LIMITED|LLC|PLC|N V|NV|S A|SA|AG|LP|COM|THE)\b\.?", re.I)
TAIL    = re.compile(r"\s*/(DE|NEW|MD|DC|CA|TX|NY|FI|MN|OH|PA|VA|WA|GA|IL|NJ|MA|CO|UT)\b.*$", re.I)

def norm(title):
    t = TAIL.sub(" ", title.upper())
    t = SUFFIX.sub(" ", t)
    t = re.sub(r"[^A-Z0-9& ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def build_gazetteer(tickers):
    """A name earns a place only if it cannot be confused with ordinary prose."""
    g, dropped = {}, 0
    for v in tickers.values():
        n = norm(v["title"])
        toks = n.split()
        if not toks: continue
        if len(toks) == 1:
            w = toks[0]
            if w in ENGLISH or w in EXTRA_STOP or len(w) < 4:
                dropped += 1; continue          # 'Target', 'Opera', 'Pattern' never enter
        if len(n) < 4: dropped += 1; continue
        g.setdefault(n, v["ticker"])
    return g, dropped

DEP_CUE = re.compile(r"""(?ix)\b(
   suppl(y|ier|iers|ied) | customers? | sole[ -]sourc\w* | single[ -]sourc\w* | sole\s+suppl\w*
 | foundry | foundries | contract\s+manufactur\w* | subcontract\w* | outsourc\w* | vendors?
 | distributors? | resellers? | original\s+equipment | end[ -]customers? | wafer\s+fabrication
 | accounted\s+for\s+(approximately\s+)?\d+ | \d+(\.\d+)?%\s+of\s+(our\s+|net\s+|total\s+|consolidated\s+)*revenue
 | purchas\w+\s+from | manufactured\s+by | supplied\s+by | depend\w*\s+on | relian\w+\s+on )\b""")

HEADINGS = [("1", r"business"), ("1A", r"risk\s+factors"), ("1B", r"unresolved"),
            ("2", r"propert"), ("3", r"legal\s+proceed"), ("4", r"mine\s+safety"),
            ("5", r"market\s+for"), ("6", r"(selected|reserved)"), ("7", r"management.s\s+discussion"),
            ("7A", r"quantitative"), ("8", r"financial\s+statements\s+and\s+supplement"),
            ("9", r"changes\s+in\s+and\s+disagree"), ("9A", r"controls\s+and\s+procedures")]

def segment(text):
    pos = {}
    for it, head in HEADINGS:
        pat = rf"(?is)\bitem\s*{it}\s*[\.\:\-—]?\s*{head}"
        pos[it] = [m.start() for m in re.finditer(pat, text)]
    chosen, limit = {}, len(text)
    for it, _ in reversed(HEADINGS):
        c = [p for p in pos[it] if p < limit]
        if c: chosen[it] = c[-1]; limit = c[-1]
    keys = sorted(chosen, key=lambda k: chosen[k]); spans = {}
    for i, k in enumerate(keys):
        spans[k] = (chosen[k], chosen[keys[i+1]] if i+1 < len(keys) else len(text))
    return spans

NOTE_CUE = re.compile(r"(?i)(concentrations?\s+of\s+(credit\s+)?risk|major\s+customers?|significant\s+customers?|segment\s+(information|reporting|and\s+geographic))")

def merge(spans):
    spans = sorted(spans); out = []
    for s, e in spans:
        if out and s <= out[-1][1]: out[-1][1] = max(out[-1][1], e)
        else: out.append([s, e])
    return out

def chunk(t):
    size, step = CHUNK_TOK*CPT, (CHUNK_TOK-OVERLAP_TOK)*CPT
    return [t[i:i+size] for i in range(0, max(len(t),1), step)]

WORD = re.compile(r"[A-Z0-9&]+")
def ngrams(c, gaz):
    toks = WORD.findall(c.upper())
    hits = set()
    for n in (3, 2, 1):
        for i in range(len(toks)-n+1):
            g = " ".join(toks[i:i+n])
            if g in gaz: hits.add(g)
    return hits

def run(pairs):
    tickers = json.load(open("tickers.json"))
    gaz, dropped = build_gazetteer(tickers)
    print(f"gazetteer {len(gaz)} names kept, {dropped} dropped as English words or too short\n")
    print(f"{'tkr':6} {'filed':11} {'FYend':11} {'doc kB':>7} {'tgt kB':>7} {'chk':>4} {'cue':>4} {'gaz':>4} {'BOTH':>5} {'pass':>6}  seg")
    rows=[]
    for tk, cik, name in pairs:
        try:
            sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
            r = sub["filings"]["recent"]
            cands=[i for i,f in enumerate(r["form"]) if f=="10-K"]
            i25=[i for i in cands if r["filingDate"][i][:4]=="2025"]
            idx = i25[0] if i25 else cands[0]
            acc=r["accessionNumber"][idx].replace("-",""); doc=r["primaryDocument"][idx]
            url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
            text=strip_html(get(url)); sp=segment(text)
            want=[sp[i] for i in ("1","1A","7") if i in sp]
            seg_ok = len(want)==3 and all(e-s>4000 for s,e in want)
            if not seg_ok: want=[(0,len(text))]
            for m in NOTE_CUE.finditer(text): want.append((max(0,m.start()-2500), m.start()+6000))
            tgt="".join(text[s:e] for s,e in merge(want))
            ch=chunk(tgt); cue=gz=both=0; named={}
            for c in ch:
                hc=bool(DEP_CUE.search(c))
                hits=ngrams(c,gaz)-{norm(name)}
                hits={h for h in hits if h not in norm(name)}
                if hc: cue+=1
                if hits: gz+=1
                if hc and hits:
                    both+=1
                    for h in hits: named[h]=named.get(h,0)+1
            rows.append(dict(tk=tk,filed=r["filingDate"][idx],doc=len(text),tgt=len(tgt),
                             chunks=len(ch),cue=cue,gaz=gz,both=both,seg_ok=seg_ok,
                             named=sorted(named.items(),key=lambda x:-x[1])[:8]))
            print(f"{tk:6} {r['filingDate'][idx]:11} {r['reportDate'][idx]:11} {len(text)//1000:>7} {len(tgt)//1000:>7} "
                  f"{len(ch):>4} {cue:>4} {gz:>4} {both:>5} {both/max(len(ch),1)*100:>5.0f}%  {'ok' if seg_ok else 'FALLBACK'}")
            top=", ".join(f"{n.title()}({c})" for n,c in sorted(named.items(),key=lambda x:-x[1])[:7])
            if top: print(f"       -> {top}")
            time.sleep(0.15)
        except Exception as e:
            print(f"{tk:6} FAILED {type(e).__name__}: {e}")
    json.dump(rows, open("measured_v2.json","w"), indent=1)
    if rows:
        pr=[r['both']/max(r['chunks'],1) for r in rows]
        print(f"\nchunks/doc  median {statistics.median([r['chunks'] for r in rows]):.0f}  mean {statistics.mean([r['chunks'] for r in rows]):.0f}")
        print(f"stage-1 pass rate  median {statistics.median(pr)*100:.1f}%  mean {statistics.mean(pr)*100:.1f}%  min {min(pr)*100:.1f}%  max {max(pr)*100:.1f}%")
        print(f"surviving chunks/doc  median {statistics.median([r['both'] for r in rows]):.0f}  mean {statistics.mean([r['both'] for r in rows]):.1f}")
        print(f"segmentation clean on {sum(r['seg_ok'] for r in rows)}/{len(rows)} documents")

run(json.load(open("pairs.json")))
