# Sources

**The gate: every source gets a row here before it gets an adapter.**

No exceptions, including for sources someone on the team already knows well. Knowing how
a source behaves is not the same as having established that we may use it, and the row is
where those two things are separated.

## The rule

A row reaches `verified` only when a **human** has opened the terms page and the
`robots.txt`, and pasted a literal quotation into `licence_quote`. An assistant's summary
of terms is a lead, not evidence — see [`research-prompts.md`](research-prompts.md), rule zero.

**If `may_we_fetch` or `may_we_redistribute` is `unclear` after a human has read the
terms, the source is rejected.** Not deferred, not used cautiously. Rejected. We would
rather defend six sources than apologise for forty.

## Status values

| Status | Meaning |
|---|---|
| `candidate` | Someone proposed it. No terms read. **No adapter may be written.** |
| `verified` | A human read the terms, quoted them, signed the row. Adapter permitted. |
| `rejected` | Terms forbid it, are unclear, or the source is unusable. Row stays, with the reason. |

Rejected rows are never deleted. "Why didn't you use X?" is a question we should be able
to answer from the repo rather than from memory.

---

## Verified

| source_id | name | what it gives us | access | rate limit | may fetch | may redistribute | verified by | on |
|---|---|---|---|---|---|---|---|---|
| `sec-edgar-archive` | SEC EDGAR filing archive | 10-K, 10-Q, 8-K, 20-F full text | HTTPS, no key | 10 req/s, User-Agent required | yes | yes — US government work, not copyrightable | — | **pending signature** |
| `sec-submissions` | `data.sec.gov` submissions JSON | per-company filing index: form, `filingDate`, `reportDate`, accession, primary document | HTTPS JSON | 10 req/s, User-Agent required | yes | yes | — | **pending signature** |
| `sec-tickers` | `company_tickers.json` | ticker ↔ CIK ↔ legal name for all US filers | HTTPS JSON | 10 req/s, User-Agent required | yes | yes | — | **pending signature** |
| `sec-fts` | EDGAR full-text search (`efts.sec.gov`) | filings *mentioning* a given name — the inversion's engine | HTTPS JSON | 10 req/s, User-Agent required | yes | yes | — | **pending signature** |
| `sec-cte` | `company_tickers_exchange.json` | ticker ↔ CIK ↔ name ↔ **exchange**, ordered by market cap | HTTPS JSON | 10 req/s, User-Agent required | yes | yes | — | **pending signature** |
| `us-cities-db` | US-Cities-Database (kelvins) | 29,738 US city → lat/lon | GitHub raw CSV | none | yes | yes — **MIT** | auto | 2026-10-23 |
| `geonames-cities15000` | GeoNames cities15000 | 39,026 world city → lat/lon + country | HTTPS zip | none | yes | yes — **CC BY 4.0**, attribution required | auto | 2026-10-23 |
| `usgs-earthquake` | USGS earthquake feed | M4.5+ earthquakes, last 30 days: magnitude, epicentre, time | HTTPS GeoJSON | none stated | yes | yes — **US government work**, not copyrightable | auto | 2026-11-16 |
| `nasa-eonet` | NASA Earth Observatory Natural Event Tracker | open natural hazards: storms, wildfires, volcanoes, floods, with coordinates | HTTPS JSON | none stated | yes | yes — **US government work** | auto | 2026-11-16 |
| `gdelt-doc` | GDELT 2.0 Document API | world news article index, 15-minute cadence, used to **detect** named disruptions | HTTPS JSON | **1 request / 5 s**, enforced | yes | links and headlines only — **article text is the publisher's** | auto | 2026-11-16 |
| `gdelt-company` | GDELT 2.0, company queries | the same index, queried per company for shocks — a departure, a recall, a halt, an investigation | HTTPS JSON | **1 request / 5 s**, enforced | yes | links and headlines only | auto | 2026-11-17 |

**Measured 2026-09-20:** `company_tickers.json` returned HTTP 200, 799,073 bytes, in
3.21 s with a declared User-Agent. Ten 10-K documents fetched and parsed successfully
across four distinct EDGAR URL shapes. Access works; the terms quotation is what is
still owed.

> **Attribution owed.** GeoNames is CC BY 4.0, so the product must carry
> "Contains data from GeoNames, CC BY 4.0" wherever its geocoding is visible. Owner:
> frontend. Due: before the first public deploy. An attribution we owe and have not
> paid is a licence breach, not a to-do.
>
> **The SEC rows say `pending signature`, and that is deliberate.** Access has been
> tested, terms have not been formally read and quoted by a person. Until somebody does
> that and signs, these are not `verified`, and this file should show that honestly
> rather than round it up. Owner: disclosure ingestion. Due: week 1.
>
> The User-Agent used in `scripts/measure_corpus.py` is a placeholder. The SEC asks for a
> real contact address. **Set a real project address before any run larger than a test.**

> **The event feeds, and what each number is allowed to mean.** Before 2026-11-16 every
> event in the graph was a literal in `scripts/propagate.py` and `event_source` had never
> held a row — nothing in Atlas watched the world. These three feeds change that, and the
> rule they are held to is the one the rest of the pipeline follows: **a feed may decide
> that something happened; it may not decide how much it matters unless it publishes its
> own scale.**
>
> * **USGS** publishes moment magnitude, mapped by one formula to 0–1 between M4 and M9.
> * **NASA EONET** publishes cyclone wind speed in knots, mapped onto the **Saffir–Simpson**
>   thresholds. Categories with no magnitude take one documented constant each.
> * **GDELT publishes no severity at all.** A GDELT event therefore takes its severity from
>   a versioned topic table in `scripts/ingest_events.py` and never from the article text.
>   GDELT decides *whether*; the table decides *how much*, and the table is in version
>   control where it can be argued with. A topic needs **5 distinct domains** before it
>   becomes an event and **12** before it is called corroborated.
>
> GDELT rate-limits to one request every five seconds and answers a faster caller with a
> 429 that is not JSON, so the adapter waits rather than retrying into the same wall.

> **Why a separate row for the same API.** `gdelt-doc` watches nine supply-chain
> topics and seeds propagation by sector and geography, which is an educated guess
> about who is affected. `gdelt-company` watches named companies and seeds
> propagation on the company itself, so every hop outward is an edge somebody filed.
> They have different seeding rules and different failure modes, and a row that
> covered both would hide that.
>
> The gap this closed is worth recording. On 2026-11-17 GDELT carried the departure
> of NVIDIA's chief executive across eighteen domains, including a story explicitly
> about supply-chain contracts — and Atlas saw none of it, because every one of the
> nine watched topics was a chokepoint or an export control. The feed was working;
> the question was never asked. A watchlist is a claim about what matters, and it
> should be read as one.

---

## Rejected or blocked

| source_id | name | what it would have given us | status |
|---|---|---|---|
| `gdacs` | Global Disaster Alert and Coordination System (EC/UN) | disaster alerts with a published green/orange/red severity and coordinates | **blocked** — the site's WAF rejects an automated client outright (`Request Rejected`, support id, no feed), with any User-Agent. Not a licence problem; we simply cannot fetch it. |
| `reliefweb` | UN OCHA ReliefWeb disasters API | disasters by country and type, with status | **blocked** — v1 decommissioned; v2 returns `AccessDeniedHttpException` without an `appname` approved by a person at OCHA. Open terms, closed door. Request the appname and revisit. |
| `newsapi` | NewsAPI.org | general news search | **rejected** — free tier is explicitly development-only; production use requires a paid plan. Using it in a deployed project would breach the terms whatever the volume. |
| `financial-news-sites` | Yahoo Finance, MarketWatch, CNBC, Seeking Alpha, Investing.com, Benzinga, Motley Fool, Nikkei, kabutan, minkabu, Toyo Keizai, finanzen.net, boerse.de, Handelsblatt, Manager Magazin, Financial Post, Globe and Mail, BNN Bloomberg, Stockhouse, Caixin, Yicai, SCMP, China Daily, Sina Finance, Eastmoney, Xueqiu | per-ticker news | **rejected — do not scrape.** Each of these prohibits automated extraction in its terms of use. A capstone that scrapes them is one `robots.txt` away from being indefensible, and the headlines are available legally through GDELT, which indexes these same outlets. |

> **The news question, answered once.** The obvious way to get per-company news is to
> scrape the sites that publish it. We are not going to, and the reason is the rule at
> the top of this file rather than caution: their terms prohibit automated extraction,
> which makes `may_we_fetch` **no**, not unclear.
>
> **GDELT indexes those same outlets** — Yahoo, MarketWatch, CNBC, Nikkei, Handelsblatt,
> SCMP and the rest — publishes an API, and permits links and headlines. So
> `scripts/ingest_company_news.py` stores a link, a headline, a domain and a date, and
> **never the article body**. The click goes to the publisher, who gets the visit. That
> is the arrangement that makes reading an index of someone's work fair.
>
> Two categories are worth adding later and are safe: **regulator disclosure feeds**
> (EDINET and TDnet for Japan, SEDAR+ for Canada, cninfo / SSE / SZSE / HKEXnews for
> China and Hong Kong) are public record exactly as EDGAR is; and the **press-release
> wires** (Business Wire, PR Newswire, GlobeNewswire) publish RSS intended for
> redistribution. Both are the company's own words, which is the kind of evidence this
> project is built on — unlike a journalist's article, which is the journalist's.

Both blocked rows stay here rather than being quietly dropped, because "why didn't you use
GDACS?" is exactly the kind of question this file exists to answer.

---

## Supplied by the team — provenance question outstanding

| source_id | name | what it gives us | status |
|---|---|---|---|
| `vendor-market-csv` | Seven market CSVs in `../data/` | 29,442 rows → **23,020 companies** after cross-listing dedupe, across US, India, UK, Germany, Canada, Australia. Legal and former names, tickers, ISIN, LEI, market cap, HQ address, description. | **`candidate` — in use for development, not cleared for publication** |

This is the richest input we have and it did not come through an adapter we wrote, so it
goes through the gate like anything else. **Three things must be answered before anything
derived from it is published**, owner: whoever supplied it, due week 1:

1. **Where did it come from, and what do its terms say about redistribution?** A row-level
   answer, not "it's public data". Quote the terms.
2. **Licensed identifier columns.** The raw files carry `sedol` (7.9% filled) and `cusip`
   (71.4%). SEDOL is LSEG's and CUSIP is CUSIP Global Services'. Both are **dropped at the
   normaliser boundary** and excluded from API responses — see `scripts/normalise_vendor_csv.py`.
   We keep ISIN, LEI and CIK, which we can publish.
3. **The classification taxonomy.** `classification_code` and `primary_indsec` carry vendor
   codes (`SEC500`, `I211`) with no stated licence, so we do not store or display them. Our
   `atlas_sector` is derived from the plain-English `classification_name` and `description`
   text instead.

**What we found in it, recorded honestly:**
- 10,820 rows were the same company listed on more than one exchange. Apple appears as a
  Frankfurt line. Collapsed to one node per company by ISIN, preferring the home listing.
- `country_hq` records the *market*, not the company. Every German row says "Germany",
  including the Canadian and Japanese companies cross-listed there. We derive country from
  the address text, then the ISIN prefix, then the geocoded city.
- `status` is `A` for all 29,442 rows. **The universe contains no delisted companies**, so
  it carries survivorship bias. Any backtest run against it must state "universe as of
  2026-10-23". See `docs/data-model.md` warning 1.
- 65% geocoded to city precision, 34% to country centroid, 3 rows not at all. Precision is
  recorded per row in `hq_geo_precision` rather than averaged away.

---

## Candidates — no adapter until verified

| source_id | name | category | what it gives us | blocking question |
|---|---|---|---|---|
| `gdelt` | GDELT Project | events | global news events, geocoded, 15-min cadence | May we store extracted metadata? May we store article text? Almost certainly not the latter. |
| `gleif-lei` | GLEIF LEI concatenated files | reference | legal names, former names, **direct and ultimate parent relationships** | Licence terms. If permissive, this is our single most valuable free entity-resolution input. |
| `unlocode` | UN/LOCODE | reference | port and location codes | Licence terms and redistribution. |
| `naturalearth` | Natural Earth | reference | coastlines, countries, ports for the map | Believed public domain — quote it. |
| `sec-sic` | SEC SIC code list | reference | industry classification for universe construction | Same terms as EDGAR, confirm. |
| `port-authorities` | ~30 port and canal authorities | events, primary | authoritative closure and congestion notices | Per-site terms, one row each. Thirty rows, not one. |
| `export-gazettes` | National export-control gazettes (US, EU, JP, KR, CN, TW, IN) | events, primary | export restrictions — the highest-value event type we have | Per-jurisdiction terms. |
| `ir-sites` | Company IR websites, 42 in the pilot | disclosure | transcripts, investor decks, press releases | Per-site `robots.txt` and terms. Cannot be generalised — each company is its own row. |
| `wikidata` | Wikidata | reference | company identifier crosswalk, name variants | CC0 believed — quote it. |

---

## Rejected

| source_id | name | why |
|---|---|---|
| `licensed-transcripts` | Commercial earnings-call transcript providers | **Redistribution terms are incompatible with our citation guarantee.** We would be able to read the transcript and unable to show the sentence. The quote is the product, so a source we cannot quote from has negative value: it would let us assert edges we cannot evidence. Declined on terms, not on price — we would decline this at ₹0. See [`COMPLIANCE.md`](../COMPLIANCE.md). |
| `nse-bse-scrape` | Automated access to NSE / BSE websites | Terms do not clearly permit automated access. Under the gate rule, `unclear` is `rejected`. Revisit for the India vintage only with a quoted permission or an official bulk route. Company IR sites remain separately assessable. |
| `expert-networks` | Expert networks, channel checks | Category we never touch. Not a terms question — an MNPI question. See [`COMPLIANCE.md`](../COMPLIANCE.md). |

---

## On sources brought in by the team

Knowledge of which sources exist, how they behave and which endpoints matter is welcome
and valuable, and it travels with people. **Bytes do not.** No exported databases, no
credentials, no licensed feeds, no code written on anyone's employer's time. Everything
here is public and fetched by our own code on our own accounts.

When a source arrives this way, it enters as a `candidate` like any other and goes through
the same gate. If we cannot confirm from its own public terms that we may fetch and
redistribute it, we say so and leave it out — however good it is, and however well
somebody knows it.
