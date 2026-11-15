# Data model and collection spec

Everything we need to collect, and where it lands. Templates with the exact headers are
in [`data/templates/`](../data/templates/) — copy one, fill it, open a PR.

**Six markets:** United States, India, United Kingdom, Australia, Canada, Germany.

---

## The one idea that makes six markets cheap

Split the database in two.

| Layer | What it holds | Cost | Scope |
|---|---|---|---|
| **Reference** | Companies, names, identifiers, listings, sectors, exchanges, places | Nearly free. CSV in, load, done. | **Global and broad from day one** |
| **Evidence** | Documents, chunks, extracted claims, cited edges | Expensive. Fetch, parse, chunk, extract, review. | **Narrow — one sector, one market, one vintage** |

Collecting 10,000 companies across six markets is a weekend of CSV work. Extracting
dependency edges from 10,000 companies' filings is a year. These are different problems
and the schema keeps them apart.

**And the broad reference layer directly improves the narrow evidence layer.** Stage one
of extraction is a gazetteer match — measured, it does all the filtering work while the
keyword lexicon eliminates nothing ([`cost.md`](cost.md)). Today that gazetteer is 7,751
US names, so a US filing naming TSMC, Infineon, ASML or Samsung produces a miss. Loading
India, the UK, Australia, Canada and Germany raises recall on the **US** corpus. The
broad collection is not a detour from Phase 1; it is an input to it.

---

## Three warnings before anyone collects a row

### 1. Survivorship bias — the one that silently ruins the backtest

If you collect "the top 1,200 US companies" today, you have collected the top 1,200
companies *that survived to today*. The ones that went bankrupt, got acquired or were
delisted are missing — and they are exactly the companies that got hit hardest by past
disruptions. Backtest a 2021 event against a 2026 universe and the result is flattering
and meaningless. It is the universe-level version of [look-ahead
bias](../LEARN/glossary.md#look-ahead-bias).

**What to do:** include delisted and acquired companies with `status` and
`delisting_date` filled in. Never silently drop them. And `index_membership.csv` is
collected **with dates** so we can ask what the index held in 2021, not just today.

Where historical constituents are genuinely unavailable for free, collect today's and
record `collected_on` — then every backtest reports "universe as of 2026-10-22" next to
its number. A stated bias is survivable. A hidden one is not.

### 2. GICS sector names are licensed

GICS belongs to MSCI and S&P. ICB belongs to FTSE. Using either in a shipped product is a
licensing problem, not a grey area.

**What to do:** collect the **free government classification** for each market — SIC or
NAICS (US), NIC (India), SIC (UK), ANZSIC (Australia), NAICS (Canada), WZ or NACE
(Germany) — into `classification_scheme` / `classification_code`. Then map everything to
`atlas_sector`, our own published taxonomy in `sectors.csv`. If a sector name on screen
came from a licensed taxonomy, it does not ship.

### 3. Every date needs a timezone, and `filed_at` needs two

An Indian company files at 19:40 IST. A German company files at 19:40 CET. Those are four
hours apart and event ordering in replay depends on getting it right. We store
`filed_at_utc` **and** `filed_at_local` **and** `filed_tz`, because converting to UTC
loses information we cannot recover, and the local time is what a human will check against
the source page.

---

## Collection priority

| Tier | Files | When | Blocks |
|---|---|---|---|
| **0** | `companies.csv` · `aliases.csv` · `exchanges.csv` · `sectors.csv` | **Now** | Everything. The gazetteer, the globe, entity resolution. |
| **1** | `filings.csv` · `ir_sites.csv` · `index_membership.csv` | This week | Extraction, the week-3 gate, survivorship defence. |
| **2** | `prices_daily.csv` · `ports.csv` · `events_benchmark.csv` | Phase 2–3 | The sector drill-down, the map, replay. |

---

# Tier 0

## `companies.csv` — the spine

One row per **listing**. A company listed on two exchanges gets two rows sharing one
`lei`; the loader merges them into one entity with two listings.

| Column | Required | Format | Notes |
|---|---|---|---|
| `company_uid` | **yes** | `{exchange_mic}:{ticker}` uppercase | `XNAS:UCTT`, `XNSE:BHARATFORG`, `XLON:BP`. Our key. Never reuse. |
| `legal_name` | **yes** | text | Exactly as written in filings, including `Limited`, `Inc.`, `AG`, `plc`. Do not tidy it. |
| `common_name` | **yes** | text | What people call it. `Bharat Forge`, not `Bharat Forge Limited`. |
| `former_names` | no | `A\|B\|C` | Previous legal names. High value for entity resolution — an old filing uses the old name. |
| `ticker` | **yes** | text | As the exchange prints it. |
| `exchange_mic` | **yes** | ISO 10383 | `XNAS` `XNYS` `XASE` `XNSE` `XBOM` `XLON` `XASX` `XTSE` `XTSX` `XETR` `XFRA` |
| `country_incorporation` | **yes** | ISO 3166-1 alpha-2 | Where it is legally registered. |
| `country_hq` | **yes** | ISO 3166-1 alpha-2 | Where it actually operates from. **Often different** — and the difference matters for jurisdiction edges. |
| `cik` | US only | 10 digits, zero-padded | `0001275014`. Blank for non-US. |
| `lei` | if it exists | 20 chars | **The cross-market key.** GLEIF, free. This is what joins a company's NSE listing to its NYSE ADR. Chase it harder than anything else here. |
| `isin` | **yes** | 12 chars | `US90385V1070`. The universal security identifier. |
| `sedol` | UK/intl | 7 chars | |
| `cusip` | US/CA | 9 chars | |
| `figi` | no | 12 chars | OpenFIGI, free. |
| `classification_scheme` | **yes** | `SIC`/`NAICS`/`NIC`/`ANZSIC`/`NACE`/`WZ` | **Not GICS, not ICB.** See warning 2. |
| `classification_code` | **yes** | text | `3674` |
| `classification_name` | no | text | `Semiconductors and Related Devices` |
| `atlas_sector` | **yes** | code from `sectors.csv` | Our taxonomy. Fill after `sectors.csv` exists. |
| `market_cap_usd` | **yes** | number | Converted. For the band and for universe weighting. |
| `market_cap_local` | no | number | |
| `currency` | **yes** | ISO 4217 | `USD` `INR` `GBP` `AUD` `CAD` `EUR` |
| `market_cap_as_of` | **yes** | `YYYY-MM-DD` | **A market cap without a date is a number with no meaning.** |
| `market_cap_band` | **yes** | see below | |
| `market_cap_band_basis` | **yes** | text | How the band was decided. `sec_file_rank:412` means it came from SEC's market-cap ordering, not a measured cap. **A proxy labelled as a proxy is fine; one that looks like a measurement is not.** |
| `shares_outstanding` | no | number | |
| `free_float_pct` | no | 0–100 | Matters in India, where promoter holdings are large. |
| `fiscal_year_end` | **yes** | `MM-DD` | `12-31`, `03-31`, `06-30`. India is overwhelmingly `03-31`. Drives the filing calendar. |
| `listing_date` | no | `YYYY-MM-DD` | |
| `delisting_date` | if delisted | `YYYY-MM-DD` | **Fill this. Do not drop the row.** |
| `status` | **yes** | `active`/`delisted`/`acquired`/`merged`/`suspended` | |
| `successor_uid` | if acquired | `company_uid` | Who absorbed it. Lets edges move when a company is bought. |
| `website` | **yes** | URL | |
| `ir_url` | **yes** | URL | Investor relations landing page. Feeds `ir_sites.csv`. |
| `filings_url` | no | URL | Direct link to its filings index, where one exists. |
| `hq_address` | no | text | |
| `hq_city` | **yes** | text | |
| `hq_state` | no | text | |
| `hq_country` | **yes** | ISO 3166-1 alpha-2 | |
| `hq_lat` | **yes** | decimal, 5dp | **The globe needs this.** |
| `hq_lon` | **yes** | decimal, 5dp | |
| `hq_geo_precision` | **yes** | `city`/`state`/`country` | How exact the coordinate is. A state centroid rendered as a precise dot is a lie told by a map. |
| `employees` | no | integer | |
| `employees_as_of` | no | `YYYY-MM-DD` | |
| `description` | **yes** | 1–2 sentences | **From the company's own words**, from its filing or IR page. Not from a model. |
| `index_membership` | no | `SP500\|NIFTY50\|...` | Today's membership. Historical goes in `index_membership.csv`. |
| `source_id` | **yes** | from `sources.md` | Where this row came from. |
| `source_url` | **yes** | URL | The exact page. |
| `collected_by` | **yes** | initials or email | |
| `collected_on` | **yes** | `YYYY-MM-DD` | |
| `notes` | no | text | Anything odd. Odd things are usually real. |

**Market cap bands (USD, so they compare across markets):**

| Band | Range |
|---|---|
| `mega` | > $200B |
| `large` | $10B – $200B |
| `mid` | $2B – $10B |
| `small` | $300M – $2B |
| `micro` | < $300M |

> **The bands are not decoration.** The whole thesis is that `small` and `mid` name their
> customers and `mega` and `large` do not. This column is how we weight the universe and
> how we report the week-3 result. Get it right.

### Targets per market

| Market | Exchanges | Target | Where the signal is |
|---|---|---|---|
| United States | XNAS, XNYS, XASE | 1,500–2,000 | Russell-style breadth. Do not stop at the S&P 500 — that is the wrong end. |
| India | XNSE, XBOM | 750–1,000 | Nifty 500 **plus** smallcap. Auto ancillaries, specialty chemicals, API makers. |
| United Kingdom | XLON | 350–500 | FTSE 350 + AIM industrials |
| Australia | XASX | 250–350 | ASX 300. Mining and materials — upstream of everything. |
| Canada | XTSE, XTSX | 250–350 | TSX + Venture. Mining, energy. |
| Germany | XETR, XFRA | 250–350 | DAX/MDAX/SDAX. Industrials, auto, chemicals. |

**≈ 3,500–4,500 rows total.** That is the gazetteer, and bigger is strictly better.

---

## `aliases.csv` — what actually makes extraction work

The highest-leverage file here. One row per *string a document might use* for a company.

| Column | Required | Notes |
|---|---|---|
| `company_uid` | **yes** | |
| `alias` | **yes** | The string as text would write it. `TSMC`. `Taiwan Semiconductor`. `TSMC Arizona`. |
| `alias_type` | **yes** | `legal` `common` `former` `ticker` `abbreviation` `subsidiary` `brand` `local_script` `transliteration` |
| `language` | **yes** | ISO 639-1. `en` unless genuinely otherwise. |
| `script` | no | `latin` `devanagari` `han` `kana` |
| `valid_from` | no | When the name became true. Blank = always. Essential for `former`. |
| `valid_to` | no | Blank = still current. |
| `is_ambiguous` | **yes** | `yes`/`no` — does this string collide with an ordinary word or another company? |
| `ambiguity_note` | if yes | Why. |
| `source_id`, `source_url`, `collected_by`, `collected_on` | **yes** | |

> **`is_ambiguous` exists because we already got burned by it.** The first gazetteer
> matched `OPERA` inside "OPERATIONS", `UNITI` inside "OPPORTUNITIES", `CURRENC` inside
> "CURRENCY" and `CAN B` inside "CAN BE" — 60% of chunks passing on phantom matches
> ([`cost.md`](cost.md)). Any single-word alias that is also an English word gets
> `is_ambiguous=yes` and is only matched with extra conditions. Flag generously; a false
> flag costs recall, an unflagged collision corrupts the graph.

**Aim for 3–8 aliases per company.** Minimum set: legal name, common name, ticker,
legal name without the suffix, any former name, any well-known abbreviation.

---

## `exchanges.csv`

| Column | Notes |
|---|---|
| `mic`, `operating_mic` | ISO 10383 |
| `name`, `country`, `city` | |
| `timezone` | **IANA**: `America/New_York`, `Asia/Kolkata`, `Europe/Berlin`. Not `EST`. |
| `currency` | ISO 4217 |
| `open_local`, `close_local` | `HH:MM` |
| `website`, `filings_portal_url`, `terms_url` | `terms_url` feeds the `sources.md` gate |
| `collected_by`, `collected_on` | |

~11 rows. Half an hour.

---

## `sectors.csv` — our own taxonomy, because GICS is licensed

| Column | Notes |
|---|---|
| `atlas_sector_code` | `SEMI_EQUIP`, `AUTO_COMPONENTS`, `SPECIALTY_CHEM` |
| `name` | Human-readable |
| `parent_code` | Two levels is enough. Resist three. |
| `definition` | One sentence. What is in, what is out. |
| `example_companies` | 3–5 `company_uid`s so a human can sanity-check the boundary |
| `maps_sic`, `maps_naics`, `maps_nace`, `maps_nic`, `maps_anzsic`, `maps_wz` | Pipe-separated codes that map here |

Build **supply-chain-shaped**, not finance-shaped. Finance taxonomies group by what a
company sells to investors. We need grouping by what flows between companies — so
`SEMI_EQUIP` and `SEMI_MATERIALS` are separate even though a finance taxonomy calls both
"Information Technology", because a photoresist shortage hits one and not the other.

Start with 25–40 sectors. Only the ones in our six markets.

---

# Tier 1

## `filings.csv` — the document index

| Column | Required | Notes |
|---|---|---|
| `company_uid` | **yes** | |
| `doc_type` | **yes** | `10-K` `10-Q` `8-K` `20-F` `annual_report` `transcript` `investor_deck` `press_release` `lodr_disclosure` `rns` `sedar_filing` |
| `doc_subtype` | no | 8-K item number, RNS category |
| `period_start`, `period_end` | **yes** | What the document *covers* |
| `fiscal_year_label` | no | As the company writes it — `FY2025`. **Never join on this.** |
| `filed_at_utc` | **yes** | ISO 8601 with `Z`. **This becomes `valid_from` on every edge.** |
| `filed_at_local` | **yes** | As the source page shows it |
| `filed_tz` | **yes** | IANA |
| `source_id` | **yes** | from `sources.md` — no row without a verified source |
| `external_id` | **yes** | Accession number, NSE announcement id, RNS number, SEDAR id |
| `landing_url`, `primary_doc_url` | **yes** | Human page, and the actual file |
| `mime` | **yes** | `text/html` `application/pdf` |
| `language` | **yes** | ISO 639-1 |
| `pages` | no | PDFs only |
| `is_amendment` | **yes** | `yes`/`no` |
| `amends_external_id` | if amendment | **Restatements rewrite history.** An amended filing supersedes; the original keeps its `valid_from`. |
| `retrieved_at_utc` | **yes** | When *we* fetched it |
| `sha256` | **yes** | Of the fetched bytes. Detects silent re-publication. |
| `bytes` | **yes** | |
| `collected_by`, `collected_on` | **yes** | |

**Scope for now:** annual filings only, `filed_at` in calendar 2025, pilot universe first.
Do not index six markets of filings. That is the expensive layer.

## `ir_sites.csv`

Unchanged from [`research-prompts.md`](research-prompts.md) P2, plus `company_uid`. This
is the one that cannot be scripted and decides whether transcripts are in Phase 1.

## `index_membership.csv` — the survivorship defence

| Column | Notes |
|---|---|
| `index_code` | `SP500` `NIFTY50` `NIFTY500` `FTSE100` `ASX200` `TSX60` `DAX` `MDAX` |
| `index_name`, `company_uid`, `ticker` | |
| `valid_from` | **When it joined the index** |
| `valid_to` | When it left. Blank = still in. |
| `source_id`, `source_url`, `collected_by`, `collected_on` | |

Historical constituents are often not free. Collect what you can; where you cannot, record
today's with `valid_from = collected_on` and we report the limitation rather than hide it.

---

# Tier 2

## `prices_daily.csv` — for the country → sector drill-down

`company_uid, trade_date, open, high, low, close, adj_close, volume, currency, split_adjusted, source_id, retrieved_at_utc`

> **Licensing matters more here than anywhere else in this document.** Live and intraday
> exchange data is licensed in all six markets. Delayed and end-of-day data varies by
> source and some free providers forbid redistribution outright. **No price source gets
> loaded until it has a `verified` row in [`sources.md`](sources.md)** with a quoted
> licence. If we can only display and not redistribute, the sector view is computed
> server-side and we never ship a price history endpoint.
>
> `adj_close` matters: an unadjusted series shows a 50% "crash" on every stock split.

## `ports.csv`

`unlocode, name, name_local, country, lat, lon, port_type, chokepoints, annual_teu, teu_as_of, authority_name, authority_url, notices_url, notices_format, timezone, source_id, collected_by, collected_on`

`chokepoints` is pipe-separated: `SUEZ|MALACCA|HORMUZ|PANAMA|TAIWAN_STRAIT|BAB_EL_MANDEB|BOSPHORUS`.
That column is what makes an event reach a company.

## `events_benchmark.csv`

Unchanged from [`research-prompts.md`](research-prompts.md) P3. Note `first_occurred_utc`
and `became_public_utc` are separate — the event-layer version of period-end vs filed-date.

---

## Rules for everyone collecting

1. **One row per source.** If two sources disagree, two rows, both kept, flagged. Do not average.
2. **Never fabricate a cell.** Blank beats a guess. A guessed `lei` is worse than an empty one because it will silently merge two companies.
3. **`collected_by` and `collected_on` on every row.** When something is wrong in week 14 we need to know who to ask.
4. **Run the validator before you open a PR:** `python3 scripts/validate_collection.py data/companies/your_file.csv`
5. **Do not tidy `legal_name`.** `Ichor Holdings, Ltd.` with the comma is the string in the filing. Our matcher normalises; our storage preserves.
6. **Delisted companies stay in.** See warning 1.

## Where to put files

```
data/companies/us.csv  india.csv  uk.csv  australia.csv  canada.csv  germany.csv
data/aliases/<same>
data/reference/exchanges.csv  sectors.csv  ports.csv
data/filings/pilot_2025.csv
data/ir_coverage/ir_sites.csv
data/events/benchmark.csv
data/indices/index_membership.csv
```

Split by market so five people are not editing one file. The loader globs the directory.
