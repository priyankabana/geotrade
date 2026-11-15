# Phase 1 coverage universe

**SEC EDGAR (United States) · semiconductor and electronics hardware supply chain ·
annual filings with `filed_at` in calendar year 2025.**

Pilot slice of 42 companies for weeks 3–6, expanding to ~200 for Phase 1 proper,
weighted roughly 70/30 toward small and mid caps rather than the household names.

---

## Why one sector, one market, one vintage

Depth on 200 companies beats a thin layer on 8,000. A dependency graph is only useful
if it is dense enough that a path exists between two companies that are actually
connected — and density within a sector is what produces paths. Eight thousand companies
spread across every industry would produce a scatter of disconnected pairs, which looks
like more data and is worth less.

One vintage matters for a second reason: it makes the point-in-time machinery testable.
A single closed vintage gives a graph with a known `as_of`, and the following year's
filings give a second vintage to test edge supersession against. Two vintages is the
minimum to prove the temporal model works at all.

---

## Why semiconductors and electronics hardware

**Named-customer density is the highest of any sector.** These companies sell to a
handful of enormous buyers, and the concentration is large enough to trip the 10%
disclosure threshold constantly. This is not a theory — a zero-cost keyword-and-gazetteer
pass over ten real 10-Ks surfaced Lam Research and Applied Materials six times each in
Ichor Holdings' filing, and the same pair in Ultra Clean Holdings' `[measured 2026-09-20,
scripts/measure_corpus.py]`. The inversion was visible in the raw output before any model
was involved.

**It is the most geographically legible chain on earth.** Hsinchu, the Taiwan Strait,
Malacca, Busan, Kyushu, Veldhoven, Penang, Phoenix, Austin. The primary surface is a
globe, and this sector genuinely lives in specific places that matter. Most sectors do
not render this well, and pretending otherwise would give us a map for decoration.

**Its shock history is unusually well documented, with checkable aftermaths.** Replay mode
needs events where the *following* quarter's filings say who actually got hit. This sector
has at least four: Japan's export controls on three materials to South Korea (July 2019),
Texas storm Uri shutting the Austin-area fabs (February 2021), the Renesas Naka fab fire
(19 March 2021), and China's gallium and germanium export controls (announced July 2023).
Export controls are especially valuable to us because they hit a *commodity* across every
company that touches it, which is exactly the shape a dependency graph is built to trace.

**The filings are structurally clean.** Item segmentation succeeded on 10 of 10 documents
using item-number-plus-heading matching `[measured 2026-09-20]`. Section targeting removed
46.2% of each document before any filtering.

### Sectors considered and rejected

**Auto components.** Genuinely strong — tier-1 suppliers name their OEM customers
constantly, and the concentration percentages are high. Rejected as first choice on
geography: the chain runs through industrial parks rather than chokepoints, and it does
not render on a globe. Held as the **fallback if the week-3 gate fails**, because if the
named-counterparty yield in semis comes in under 30% the problem is the sector, not the
thesis, and this is where we would test that.

**Pharmaceutical APIs and specialty chemicals.** The China-to-India-to-US generics chain
is a famous and real chokepoint story. Rejected because API makers disclose customer
concentration far less often by name — much of the chain is contract manufacturing under
confidentiality, which is precisely the disclosure behaviour the inversion needs and does
not get here.

**Energy and shipping.** Fits the Hormuz framing that runs through the brief, and the
geography is perfect. Rejected because the dependencies are commodity and route
dependencies rather than named-counterparty dependencies. We would build a good map and
almost no graph, and the graph is the product.

---

## Why the United States, and not India

This is the decision most likely to be challenged, so the reasoning is written out.

**EDGAR is the only free, bulk, machine-readable filing corpus with an explicit
programmatic-access policy.** Declare a real User-Agent with a contact address, stay under
10 requests per second. Free, bulk *and explicitly permitted* is a rarer combination than
it sounds. Verified working on 2026-09-20.

**NSE and BSE terms do not clearly permit automated access.** Under our own gate rule in
[`sources.md`](sources.md), `unclear` is `rejected`. We are not going to write a rule in
week 1 and break it in week 3.

**US filings are structurally parseable; Indian annual reports are not.** A 10-K has
mandated, labelled Items. An Indian annual report is a 300-page PDF whose structure is a
design choice. That difference is the difference between a working chunker in week 4 and
a month lost to PDF extraction.

**And EDGAR full-text search is the inversion's engine.** Searching filing *contents* for
a buyer's name returns the suppliers who named them. India has no free equivalent, so the
universe would have to be assembled by hand.

### What we gave up, and why India is vintage two rather than a road not taken

**SEBI requires Indian listed companies to publish earnings-call transcripts. The SEC does
not.** `[verify: SEBI LODR transcript requirement, which tier of companies it binds, and
the deadline — see research-prompts.md P7]`

Transcripts are Tier-1 evidence, and often more specific than the filing they accompany,
because an analyst asks the direct question management avoided in print. This is a real
structural advantage that the US corpus lacks and cannot acquire.

So an India vintage is not a consolation prize. **It gains a Tier-1 source the US corpus
structurally lacks**, and the right sequencing is to prove the extraction, citation and
point-in-time machinery on the corpus that is easiest to fetch, then add the corpus that
is richer to read. Adding a second disclosure regime is also, by itself, a strong Phase 5
story: two regulators, two document structures, two naming conventions, one entity
resolution layer.

### One correction, because the instinct is natural and wrong

The Indian equivalent of this universe is **not the Nifty 50.**

The Nifty 50 is fifty of the largest companies in India — structurally the exact companies
that hide their suppliers, which is the failure mode the entire inversion exists to avoid.
Building on the Nifty 50 would reproduce, in a second market, the top-down mistake the
brief was written to prevent.

The Indian universe would be the **smallcap and midcap auto-ancillary, specialty-chemical
and API names** — the companies whose investor decks carry customer logo slides and
revenue-by-customer charts, and who file those decks with the exchanges as a regulatory
disclosure. Same inversion, different market.

---

## Why `filed_at` in calendar 2025

Not "FY2024." The vintage is defined by **filing date**, for three reasons.

**It is the definition the query actually uses.** `dependency_edge.valid_from =
document.filed_at`. Defining the universe the same way the graph is queried removes a
whole category of off-by-one error.

**It teaches the distinction on day one.** Every member of the team has to internalise
that a document describes one period and becomes public in another. Making it the universe
definition forces the issue in week 1 rather than week 13.

**Fiscal years do not line up and filing dates do.** In our ten-company sample, fiscal year
ends landed on five different dates spanning 2024-12-27 to 2025-10-31 — and all ten annual
filings had `filed_at` in calendar 2025 `[measured 2026-09-20]`. The filing-date definition
captured every company exactly once. A fiscal-year definition would have captured some
twice and others not at all.

It also gives us a **closed, immutable vintage**. Calendar 2025 is over; nothing new will
arrive in it. Filings from 2026 — which already exist, since December-year-end companies
filed in February 2026 — become vintage two, for testing supersession and for the live
layer. Backtesting against a closed past vintage with known outcomes is exactly what we
want in Phase 4.

---

## How the universe is built — the inversion, made mechanical

Do not pick companies from a screener. Let the disclosure asymmetry assemble the list.

1. **Seed with anchor buyers** — the large caps everyone already knows are exposed. These
   are not the product; they are search terms.
2. **Query EDGAR full-text search for each anchor's name.** What comes back is not the
   anchor's filings. It is **the filings of the smaller companies who named the anchor as a
   customer** — the exact edge the buyer would never disclose.
3. **Rank the hits** by mention count, SIC code (3674 semiconductors, 3559 semiconductor
   equipment, 3672 printed circuit boards, 3827 and 3825 instruments, 3661 and 3663
   communications equipment) and market-cap band.
4. **Keep the small and mid caps.** Add a second-degree pass on the strongest suppliers.
5. **Record why each company is in the universe**, in `data/universe/pilot.csv`. A company
   that entered because three filings named it is a different thing from one added by hand.

Step 2 is the whole thesis in one free API call.

---

## The pilot slice — 42 companies, weeks 3–6

Start small. The pilot exists so the extraction owner can change a prompt and re-run the
entire corpus before lunch — 560 stage-two calls, under an hour on one laptop
([`cost.md`](cost.md)).

**30 companies already resolved to CIKs** from SEC's own `company_tickers.json`
`[measured 2026-09-20]`. These are real and can be fetched today.

| Role | Ticker | CIK | Name |
|---|---|---|---|
| anchor | AAPL | 0000320193 | Apple Inc. |
| anchor | NVDA | 0001045810 | NVIDIA Corp |
| anchor | INTC | 0000050863 | Intel Corp |
| anchor | MU | 0000723125 | Micron Technology Inc |
| anchor | TXN | 0000097476 | Texas Instruments Inc |
| anchor | AMAT | 0000006951 | Applied Materials Inc |
| anchor | LRCX | 0000707549 | Lam Research Corp |
| anchor | KLAC | 0000319201 | KLA Corp |
| supplier | UCTT | 0001275014 | Ultra Clean Holdings, Inc. |
| supplier | ICHR | 0001652535 | Ichor Holdings, Ltd. |
| supplier | CRUS | 0000772406 | Cirrus Logic, Inc. |
| supplier | FORM | 0001039399 | FormFactor Inc |
| supplier | PLAB | 0000810136 | Photronics Inc |
| supplier | KLIC | 0000056978 | Kulicke & Soffa Industries Inc |
| supplier | ONTO | 0000704532 | Onto Innovation Inc. |
| supplier | ACLS | 0001113232 | Axcelis Technologies Inc |
| supplier | AMKR | 0001047127 | Amkor Technology, Inc. |
| supplier | COHU | 0000021535 | Cohu Inc |
| supplier | AEIS | 0000927003 | Advanced Energy Industries Inc |
| supplier | MKSI | 0001049502 | MKS Inc |
| supplier | VECO | 0000103145 | Veeco Instruments Inc |
| supplier | NVMI | 0001109345 | Nova Ltd. |
| supplier | CAMT | 0001109138 | Camtek Ltd |
| supplier | SWKS | 0000004127 | Skyworks Solutions, Inc. |
| supplier | QRVO | 0001604778 | Qorvo, Inc. |
| EMS | BHE | 0000863436 | Benchmark Electronics Inc |
| EMS | SANM | 0000897723 | Sanmina Corp |
| EMS | PLXS | 0000785786 | Plexus Corp |
| EMS | TTMI | 0001116942 | TTM Technologies Inc |
| EMS | OSIS | 0001039065 | OSI Systems Inc |

**The remaining ~12 come from the full-text search expansion**, not from us adding names
we thought of. That is the point of the method — if we hand-pick the whole list we have
tested our own knowledge of the sector rather than the technique.

Two additions to resolve by hand, because foreign private issuers file 20-F and are
easy to miss: **TSMC and ASML** `[verify: both file 20-F; resolve CIKs from
company_tickers.json or EDGAR company search]`. A semiconductor graph missing Taiwan is
a graph with a hole where its most important node should be.

---

## Known weaknesses of this universe

**The 10% threshold is a visibility floor.** A supplier at 9.9% of revenue never appears
in a concentration note. The product's value is in the non-obvious third-hop name, and
non-obvious often means small, so the disclosures that are easiest to find are
systematically the *least* surprising ones. Week 3 measures this directly by recording,
for every named counterparty, whether a materiality figure was attached and whether it sat
above or below 10%.

**Competitor lists are the dominant false-positive class.** Cirrus Logic's filing surfaced
Qualcomm, Synaptics, Skyworks and Analog Devices — all correctly matched companies, none of
them counterparties `[measured 2026-09-20]`. Item 1's Competition subsection sits next to
dependency vocabulary and will fool any rules-based approach. The extraction schema needs
`competitor` as an explicit negative class the model must choose, not a default it can
fall into.

**Single sector means single-sector conclusions.** Nothing measured here transfers to
pharmaceuticals or autos without re-measuring, and we should not claim it does.

**n = 10 so far.** Every number in this file marked `[measured]` comes from ten documents,
all 10-Ks, one sector. It is enough to make decisions with and not enough to publish.
