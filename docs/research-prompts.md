# Research prompts — source discovery and data collection

For the team to run, in parallel, starting now. Paste a prompt into whatever assistant
you use, or do it by hand. Either way the **output contract** is what matters: results
land in a named CSV in a fixed shape, so five people's work merges instead of colliding.

---

## Rule zero — read this before running anything

**An assistant's answer about a website's terms is a lead, not a fact.**

Models hallucinate licence terms with total confidence. They will tell you a source is
"freely available for commercial use" because that sentence appears near that kind of
website in their training data. Nothing enters [`sources.md`](sources.md) until a human
has opened the actual terms page, the actual `robots.txt`, and pasted the actual
sentence into the row.

So every prompt below ends with the same instruction: **return URLs to the primary
evidence, not conclusions about it.** You are using the model to find the terms page
fast, not to read it for you. The row in `sources.md` is signed by a person with a date,
and that signature means "I opened this myself."

This is not bureaucracy. A source with misread terms is the one failure mode that can
end the project rather than delay it.

---

## The output contract

Everything produced by these prompts lands in one of four files.

```
data/sources/candidates.csv      one row per candidate source        (P1, P3, P4, P5, P6, P7)
data/universe/pilot.csv          one row per company in the pilot    (P2)
data/ir_coverage/ir_sites.csv    one row per company's IR site       (P2)
data/events/benchmark.csv        one row per known historical event  (P3)
```

**`data/sources/candidates.csv`** — columns, in this order:

```
source_id, name, url, terms_url, robots_url, category, what_it_gives_us,
access_method, rate_limit, requires_user_agent, licence_name, licence_quote,
may_we_fetch, may_we_redistribute, display_only, cost, update_frequency,
geographic_coverage, historical_depth, stability_notes, verified_by, verified_on, status
```

`may_we_fetch` / `may_we_redistribute` take exactly one of `yes` / `no` / `unclear`.
`licence_quote` is a literal quotation from the terms page, not a summary.
`status` is `candidate` / `verified` / `rejected`, and a row cannot become `verified`
without a `licence_quote` and a `verified_by`.

**If `may_we_fetch` or `may_we_redistribute` is `unclear` after a human has read the
terms, the source is rejected.** That is the gate. We would rather have six sources we
can defend than forty we cannot.

---

## P1 — The disclosure corpus (owner: disclosure ingestion)

Mostly solved already; run this to close the gaps rather than to discover the source.

> I am building a pipeline that downloads SEC filings programmatically for a research
> project. I already know about EDGAR's main archive, the `data.sec.gov/submissions/`
> JSON endpoint, `company_tickers.json`, and EDGAR full-text search at `efts.sec.gov`.
>
> For each of those, and for any bulk-download option I have not listed, tell me:
> the exact base URL, what the response shape is, the documented rate limit, the
> required User-Agent format, whether there is a bulk archive that avoids per-document
> requests, and how far back coverage goes.
>
> Then tell me the known failure modes people hit: inconsistent primary-document
> filenames, filings where the main document is an exhibit, amended filings (10-K/A)
> and how they relate to the original, and anything that changed in the last three years.
>
> **Return the SEC's own documentation URL for every claim.** Where you are not certain
> a rate limit or coverage date is current, say so explicitly rather than guessing.
> Output as rows for `data/sources/candidates.csv` using the column list I paste below.

**Already verified and in `sources.md`:** EDGAR archive, submissions JSON, company_tickers.json.
`company_tickers.json` returned HTTP 200 in 3.2s with a declared User-Agent on 2026-09-20,
and yielded a 7,751-name gazetteer after filtering.

---

## P2 — IR-site coverage of the pilot universe (owner: everyone, this is the week-3 bulk job)

This is the highest-value collection job we have, because it answers a question nobody
can answer from a desk: **do the companies in our universe actually publish transcripts
and investor decks on their own websites?** We committed to measuring it rather than
assuming it.

This is manual and it is meant to be. One company takes about four minutes. Forty-two
companies split five ways is under forty minutes each.

For each company in `data/universe/pilot.csv`, open its investor relations page and fill
one row of `data/ir_coverage/ir_sites.csv`:

```
ticker, cik, ir_url, transcripts_published, transcript_oldest, transcript_format,
decks_published, deck_count_last_2y, press_releases_url, robots_txt_allows_ir_path,
terms_page_url, notes, checked_by, checked_on
```

`transcripts_published` is `yes` / `no` / `partial` — partial meaning prepared remarks
only, which is common and much less useful to us than Q&A.

Use this to find the page fast, then verify by hand:

> For the company with ticker {TICKER}, find the official investor relations website —
> the company's own domain, not a third-party aggregator like Seeking Alpha, Motley Fool,
> StockAnalysis or Investing.com.
>
> Give me: the IR landing page URL, the URL of the quarterly-results or events page, and
> the URL of the press-releases page. Tell me whether the company appears to post earnings
> call transcripts or only audio replays or only slide decks.
>
> Do not guess a URL pattern. If you are not confident the page exists at that address,
> say so and give me the company's main domain instead so I can navigate there myself.

**The gate:** if fewer than 30% of the pilot universe publishes usable transcripts on
their own site, transcripts drop out of Phase 1 and the graph is built on filings plus
investor decks. Record the number either way.

---

## P3 — News sources, and how we decide which ones are *correct*

This is the one you asked about, and the obvious approach is the wrong one. Asking a
model "which news websites are most accurate" produces a confident list of famous
mastheads and teaches us nothing — it is an opinion poll, and it is the sort of thing an
interviewer will take apart in about fifteen seconds.

**Instead: build a benchmark of events whose ground truth we already know, then measure
candidate sources against it.** This turns source selection into a measurement, which is
the same move we made with the cost model and the same move we are making in week 3.

### Step one — build the benchmark

Fill `data/events/benchmark.csv` with 20 disruptions from the last six years that are
relevant to the semiconductor and electronics chain, where what happened is now settled
and documented:

```
event_id, name, event_type, first_occurred_utc, became_public_utc, location_name,
lat, lon, chokepoint, ground_truth_url, ground_truth_quote, downstream_effect_known,
downstream_evidence_url, added_by, added_on
```

Start from these, which are well documented and have checkable aftermaths — verify every
date against a primary source before it goes in the file:

- Japan's export controls on three materials to South Korea, July 2019
- Texas winter storm Uri and the Austin-area fab shutdowns, February 2021
- The Renesas Naka fab fire, 19 March 2021
- The Ever Given grounding in the Suez Canal, 23–29 March 2021
- The Taiwan drought and fab water restrictions, 2021
- China's gallium and germanium export controls, announced July 2023
- Red Sea diversions and Suez traffic collapse, from late 2023
- The Panama Canal draught restrictions, 2023–24

`became_public_utc` is deliberately separate from `first_occurred_utc`. A fire starts at
a moment; the world learns at a later moment; our system can only ever react to the
second. Getting the team thinking in those two timestamps now prevents a whole class of
backtest error later — it is the event-layer version of filed date versus period end.

### Step two — score candidate sources against it

> I am evaluating news sources for a system that detects supply-chain disruptions
> affecting the semiconductor industry. I need to judge sources on reliability, not
> reputation.
>
> For each source I name below, find its coverage of this specific event: {EVENT NAME,
> DATE}. Give me the URL of its earliest article on the event, the publication timestamp
> if the page exposes one, and whether the article was later corrected or updated.
>
> Then tell me, with links to the source's own pages: does it publish a corrections
> policy? Does it expose machine-readable timestamps in its HTML or RSS? Does it offer
> RSS, a sitemap, or an API? What do its terms of use say about automated access and
> about reproducing headlines?
>
> **Do not characterise the source's general accuracy or bias.** I want per-event
> evidence and links only.

Score every candidate on these, and put the scores in the `notes` column:

| Criterion | Why it matters to us | Fails if |
|---|---|---|
| **Primary or secondary** | A port authority notice *is* the event; a news article is a report about it | — |
| **Machine-readable timestamp, UTC** | Replay orders events in time; a source with only "2 days ago" cannot be ordered | No parseable published time |
| **Distinguishes published from updated** | An article silently rewritten changes history under us | No updated time exposed |
| **Corrections policy** | A source that never corrects cannot be trusted in a backtest | No published policy |
| **Structured access** | RSS or API means no HTML scraping and no breakage when the site redesigns | Scrape-only |
| **Terms permit fetching** | Rule zero | `unclear` after a human read |
| **Terms permit showing a headline and link** | The citation is the product; if we cannot quote, the source is worthless to us | Cannot display any excerpt |
| **Syndication behaviour** | Wire copy appears on 40 sites under 40 URLs and wrecks deduplication | Pure syndication, no original reporting |
| **Latency on the benchmark events** | Median minutes from `became_public_utc` to publication | Consistently last |
| **Coverage of our chokepoints** | Global product, and most outlets are regional | Misses half the benchmark |

### The architecture this produces

We do not need many news sources. We need **recall from one broad source and confirmation
from a few trustworthy ones.**

- **GDELT for recall** — free, geocoded, updates every fifteen minutes, global. It gives
  URLs and extracted metadata rather than article text, which matters for redistribution.
  `[verify: GDELT's own licence page, and specifically whether article text may be stored]`
- **Primary sources for confirmation** — port authority notices, canal authority
  advisories, government export-control gazettes, company 8-Ks. These *are* the event.
- **The promotion rule:** an event from GDELT alone is `unconfirmed` and never drives a
  user-visible exposure claim. It is promoted to `confirmed` only when a primary source
  or an independently-reported secondary source corroborates it.

That rule is the honest answer to "how do you know your news is correct," and it is a
design decision rather than a hope. Write it into the event schema as
`event.confirmation_level`, not into a comment.

---

## P4 — Ports, canals and chokepoints (owner: platform, events and release)

> I need official, public status and notice pages for the following ports and waterways:
> {LIST}. For each, give me: the port or canal authority's official domain, the URL of
> its notices/advisories/circulars page, whether that page offers RSS or a downloadable
> feed, what languages it publishes in, and the URL of its terms of use.
>
> Only official authority sources. No news coverage, no commercial logistics platforms,
> no aggregators. If an authority has no public notices page, say so explicitly rather
> than substituting something else.

Target list for Phase 1, weighted to the electronics chain rather than to bulk shipping:
Kaohsiung, Taipei, Keelung, Busan, Shanghai, Ningbo-Zhoushan, Shenzhen, Hong Kong,
Singapore, Port Klang, Tanjung Pelepas, Penang, Laem Chabang, Ho Chi Minh, Yokohama,
Nagoya, Kobe, Los Angeles, Long Beach, Oakland, Rotterdam, Antwerp, Hamburg,
Jebel Ali, Suez Canal Authority, Panama Canal Authority, Strait of Malacca advisories,
Strait of Hormuz advisories, Taiwan Strait advisories, Nhava Sheva, Chennai, Mundra.

Also worth a row each: national export-control and sanctions gazettes for the US, EU,
Japan, South Korea, China, Taiwan and India. Export controls are the single most
graph-relevant event type we have, because they hit a *commodity* across every company
that touches it, which is exactly what a dependency graph is for.

---

## P5 — Reference and geospatial data (owner: backend)

> For each of these reference datasets, find the canonical download URL, the licence
> under which it is published with a link to the licence text, the file format, the
> update frequency, and whether registration is required:
> UN/LOCODE, Natural Earth (countries, ports, coastlines), the SEC's SIC code list,
> GLEIF Legal Entity Identifier concatenated files including Level 2 relationship data,
> Wikidata company identifiers, and any open dataset mapping vessel routes to chokepoints.
>
> **Quote the licence, do not summarise it.** For any dataset where you cannot find a
> licence statement, say so.

**GLEIF deserves special attention.** The Legal Entity Identifier system publishes global
company reference data including *direct and ultimate parent relationships* — a free,
open corporate hierarchy `[verify: GLEIF licence and Level 2 coverage]`. If those terms
are as permissive as they appear, this is the single most valuable free input to entity
resolution we will find, and it solves the "is this subsidiary the same company as its
parent" problem that would otherwise eat weeks of Phase 2.

---

## P6 — Entity resolution aids (owner: extraction and entity resolution)

> I am building a company name matching system. Filings refer to the same company as
> "TSMC", "Taiwan Semiconductor Manufacturing Company Limited", "TSMC Arizona" and
> "Taiwan Semiconductor". I need public, licence-clear sources of company name variants,
> former names, subsidiaries and parent relationships.
>
> For each candidate source tell me: what identifiers it carries, whether it includes
> former names and trading names, whether it includes corporate hierarchy, coverage by
> country, licence with a link, and access method.
>
> I specifically want to know which of these are usable without a commercial licence.
> Where a source is commercial, say so plainly rather than describing its free tier as
> if it were the product.

Our own measured starting point: SEC's `company_tickers.json` gives 7,751 usable US-listed
company names after filtering out single-token names that are ordinary English words
`[measured 2026-09-20]`. That filter is not optional — before it, the matcher "found"
Opera inside OPERATIONS and Uniti inside OPPORTUNITIES.

---

## P7 — India, for vintage two (owner: disclosure ingestion, low priority, do not let it displace P2)

Phase 1 is a US vintage. India is vintage two, and it is worth scouting now so the
collection is not wasted — but it must not compete with P2 for time this month.

> For Indian listed companies, I need to know what disclosure documents are published,
> where, and under what terms. Specifically:
>
> 1. What does SEBI's LODR regulation require regarding publication of earnings call
>    audio recordings and transcripts — which companies does it bind, what is the
>    deadline, and where must they be published? Cite the regulation and the SEBI
>    circular.
> 2. Are annual reports, investor presentations and transcripts available from company
>    websites, from NSE, from BSE, or all three?
> 3. What do NSE's and BSE's terms of use say about automated access to their websites
>    and data? Quote the relevant clause and link it.
> 4. Is there any official bulk or API access to Indian filings comparable to SEC EDGAR?
>
> Quote regulations and terms directly. Do not tell me what is "generally permitted".

The strategic point, recorded in [`coverage-universe.md`](coverage-universe.md): **SEBI
requires transcript publication and the SEC does not.** An India vintage therefore gains
a Tier-1 source the US corpus structurally lacks. That is a reason India is vintage two
rather than a road not taken.

One correction worth making early, because the instinct is natural and wrong: the Indian
equivalent of our universe is **not** the Nifty 50. The Nifty 50 is fifty of the largest
companies in India — structurally the exact companies that hide their suppliers, which is
the failure mode the whole inversion exists to avoid. The Indian universe would be the
smallcap and midcap auto-ancillary, specialty-chemical and API names, where investor
decks carry customer logo slides and revenue-by-customer charts.

---

## P8 — Terms verification (run on every candidate before it is promoted)

> For the website {URL}, find and quote verbatim:
> 1. The terms of use or terms of service section covering automated access, scraping,
>    crawling or bots.
> 2. The contents of {URL}/robots.txt.
> 3. Any stated rate limit or required User-Agent.
> 4. Any statement about redistributing, republishing or displaying their content.
> 5. The copyright notice.
>
> Quote exactly and give the URL each quote came from. If a section does not exist,
> say "not found" — do not infer what the terms probably are from similar sites.

Then a human opens those URLs, confirms the quotes, and signs the row. **A model's
confirmation is not a signature.**

---

## P9 — Competitive landscape (owner: product and discovery, for `STARTUP/market.md`)

> For each of these companies — Everstream Analytics, Interos, Resilinc, Exiger, Altana,
> Sayari, Kpler, AlphaSense, S&P Global Market Intelligence, project44, Prewave, Craft —
> tell me: what they actually sell, who buys it, where their underlying data comes from,
> and their publicly stated pricing if any exists.
>
> For each, give me one sentence on **what they do better than a public-disclosure
> dependency graph would**, and one on what they cannot do. Be specific about data
> provenance — some build from customer-uploaded supplier lists, some from shipping
> manifests and bills of lading, some from news. That distinction is what I care about.
>
> Cite the company's own site or published reporting. Do not estimate revenue or
> headcount unless you can link a source.

The honest framing for `market.md`: several of these are better funded and better staffed
than us. What none of them do is make every single assertion click through to the sentence
in the filing that supports it. Provenance as a first-class product feature is the gap,
and "here is what they do better than us" is a section we write ourselves rather than skip.

---

## Work packet — what to collect this week

| # | Job | Owner | Output | Size |
|---|---|---|---|---|
| 1 | Build the 42-company pilot universe from EDGAR full-text search | disclosure ingestion | `data/universe/pilot.csv` | ~3 h, scripted |
| 2 | IR-site coverage sweep, all 42 | **all five**, ~9 companies each | `data/ir_coverage/ir_sites.csv` | ~40 min each |
| 3 | 20-event benchmark with verified dates and ground truth | platform, events and release | `data/events/benchmark.csv` | ~4 h |
| 4 | Port and canal authority notice pages, 30 ports | platform, events and release | `data/sources/candidates.csv` | ~3 h |
| 5 | Reference datasets, licence-quoted | backend | `data/sources/candidates.csv` | ~2 h |
| 6 | Entity resolution aids, GLEIF first | extraction | `data/sources/candidates.csv` | ~2 h |

Job 2 is the one that must not slip. It produces the transcript-coverage number that
decides whether transcripts are in Phase 1 at all, and it cannot be scripted, bought or
reasoned about — somebody has to open forty-two websites.
