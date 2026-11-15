# Glossary

Every term, three layers:

1. **One sentence** a ten-year-old gets.
2. **What it actually is** — a paragraph with a real company and real numbers.
3. **In our code** — where it lives in Atlas and what breaks if we get it wrong.

Rule: no term is used twice in this repo before it has an entry here.

## A note on the numbers

Figures marked `[verify]` are recalled, not read. Each names the document to check
against. **Clear every `[verify]` before this file is treated as finished** — owner:
extraction lead, due week 2. R7 forbids publishing a number we did not produce; marking
our own uncertainty is how we keep that rule while still teaching.

Figures marked `[measured YYYY-MM-DD]` came from an actual run of
[`scripts/measure_corpus.py`](../scripts/measure_corpus.py) and can be reproduced.

---

## Topic index

**Filing types** — 8-K · 10-K · 10-Q · 20-F
**Where the useful sentences live** — MD&A · Risk factors · Segment reporting and the major-customer note · Customer concentration disclosure · Earnings call
**Getting the documents** — EDGAR · EDGAR full-text search · CIK
**Reading them correctly** — Filed date vs period end · Fiscal year · Hedged disclosure language · Forward-looking statement · Materiality · Sole source
**Our own machinery** — Coverage universe · Dependency edge · Entity resolution · Golden set
**Not cheating** — As-of query · Look-ahead bias · MNPI

---

## 8-K

**In one sentence.** When something big suddenly happens at an American public company, it has four business days to tell everyone — that announcement is an 8-K.

**What it actually is.** A 10-K comes once a year and a 10-Q once a quarter, but the world does not wait. A fire, a resignation, a signed contract, a lost customer, an acquisition — each triggers an 8-K. Every 8-K carries an Item number saying what kind of event it is: 1.01 entry into a material agreement, 2.02 results of operations, 5.02 departure of officers, 8.01 other events. The real content is usually in an attached exhibit, most often Ex-99.1, a press release. This matters enormously to us: **Item 1.01 is one of the few places a company names a counterparty in its own filing**, because you cannot announce a material supply agreement without saying who it is with.

**In our code.** 8-Ks are the hinge between the slow layer and the fast layer — a document with a `filed_at` that is close to real time. `apps/ingest` polls for them; Ex-99 exhibits are a Tier-1 adapter target. Two ways to get this wrong. If we mis-parse the Item number we either flood the queue with routine earnings releases or silently miss every contract announcement. And an 8-K's `filed_at` is its own date — inheriting it from a parent filing would put an edge into the graph before it was public and quietly break every point-in-time guarantee downstream.

## 10-K

**In one sentence.** Once a year every American public company must write a long, dull, legally binding description of itself and hand it to the government, which publishes it free.

**What it actually is.** The 10-K is the annual report in its regulatory form, and it has a fixed skeleton: Item 1 Business, Item 1A Risk Factors, Item 2 Properties, Item 3 Legal Proceedings, Item 7 Management's Discussion and Analysis, Item 8 Financial Statements and the notes beneath them. Deadlines depend on company size — 60 days after fiscal year end for the largest filers, 75 for the middle tier, 90 for the smallest. The fixed skeleton is the gift: unlike a glossy annual report, a 10-K's sections are mandated and labelled, so a machine can find Item 1A without understanding English. In our own sample of ten semiconductor-sector 10-Ks, the median document was 323,000 characters of text once HTML was stripped `[measured 2026-09-20]`.

**In our code.** `document.doc_type = '10-K'`. `apps/ingest` segments on Item boundaries and writes a `section` row per Item with character offsets, then chunks within sections. Getting Item detection right is worth real money: targeting Items 1, 1A and 7 plus the concentration notes, rather than the whole document, removed roughly half the text before a single model call `[measured 2026-09-20]`. Getting it wrong costs more than tokens — a supplier named in Item 1 Business is a much stronger signal than the same name in a legal-proceedings exhibit, and if we cannot tell which section a sentence came from we cannot weight it.

## 10-Q

**In one sentence.** The smaller, unaudited version of the 10-K, filed three times a year between the annual ones.

**What it actually is.** Public companies report quarterly. Three of those quarters get a 10-Q, due 40 or 45 days after quarter end depending on filer size; the fourth is folded into the 10-K. A 10-Q is shorter, unaudited, and mostly updates the numbers — but it carries a risk-factor section that only says what has *changed*, and that delta is useful. If a supplier relationship broke in Q2, the 10-Q is where it first appears in writing.

**In our code.** 10-Qs are our main mechanism for *retiring* edges, not creating them. When a concentration note that named a customer in the 10-K stops naming them two quarters later, that is the signal to set `dependency_edge.valid_to`. An edge that is never retired is worse than an edge that was never created, because the graph looks confident about something that stopped being true.

## 20-F

**In one sentence.** The 10-K's equivalent for foreign companies listed in America.

**What it actually is.** A company incorporated outside the US that lists on a US exchange is a "foreign private issuer" and files a 20-F instead of a 10-K, due within four months of fiscal year end. This matters more than it sounds for us: in a semiconductor graph, some of the most important nodes are foreign private issuers — TSMC and ASML both file 20-F `[verify: check each company's EDGAR filing history]`. A pipeline that only understands 10-K will build a graph of American suppliers pointing at a hole where Taiwan should be.

**In our code.** `document.doc_type IN ('10-K','20-F')` everywhere we mean "annual filing". The section structure differs — a 20-F uses Items 1–19 with different meanings, so the segmenter needs a second rule set. Treating 20-F as 10-K is the kind of bug that produces a graph that is quietly missing its most important nodes and still looks fine.

## As-of query (point-in-time query)

**In one sentence.** Asking "what did we know on this date?" instead of "what do we know now?"

**What it actually is.** Our graph changes as filings arrive. An as-of query fixes a date and returns the graph exactly as it stood then — every edge that had been published by that date and had not yet been superseded, and nothing else. This is the difference between a research product and a toy. Every serious financial data vendor sells point-in-time history as a premium product precisely because reconstructing it after the fact is nearly impossible, and because without it no backtest means anything.

**In our code.** One function, `edges_as_of(entity_ids, as_of)`, filtering `valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)`. There is no second path — an ORM query that forgets `as_of` is a bug class we design out rather than remember to avoid. Every read API endpoint takes `as_of` and defaults it to `now()` explicitly rather than implicitly. See [Look-ahead bias](#look-ahead-bias) for the test that must exist before the backtest harness does.

## CIK

**In one sentence.** The permanent ID number the SEC gives every company that files with it.

**What it actually is.** Central Index Key — a ten-digit zero-padded number, `0001275014` for Ultra Clean Holdings `[measured 2026-09-20, from SEC company_tickers.json]`. The important property is that it survives everything: a company can change its name, change its ticker, move exchanges, and keep the same CIK. Tickers do not have this property. Tickers get reused — when a company delists, its symbol goes back in the pool and can be reassigned to somebody else entirely.

**In our code.** `entity.cik` is the primary external key for US filers, and it is what `entity_alias` rows resolve *to*. Never key anything on ticker. The classic disaster here is a ticker collision welding two unrelated companies into one node, which then inherits both their edges and produces a confidently wrong exposure list that no one can debug because the data looks internally consistent.

## Coverage universe

**In one sentence.** The list of companies we actually watch — everything else is outside our map.

**What it actually is.** No product covers every company, so every research product declares a universe and is honest about its edges. Ours for Phase 1 is roughly 200 companies in the semiconductor and electronics hardware chain, deliberately weighted about 70/30 toward small and mid caps rather than the household names, because the inversion says the smaller side is where named counterparties live. The pilot slice is smaller still — see [`docs/coverage-universe.md`](../docs/coverage-universe.md).

**In our code.** `entity.in_universe` plus a `universe_vintage` so we can reconstruct what the universe was on a past date. That second part matters more than it looks: if we add 50 companies in week 12 and then backtest a 2021 event, we have quietly introduced **survivorship bias** — we would be scoring the past using a universe assembled with knowledge of the present. A universe is a point-in-time object like everything else here.

## Customer concentration disclosure

**In one sentence.** If one customer buys a big slice of what you sell, you have to warn your investors — because if that customer walks, you are in serious trouble.

**What it actually is.** Under US segment-reporting rules, when revenue from a single external customer reaches 10% or more of total revenue, the company must disclose that fact, the amount, and which segment it sits in `[verify: ASC 280-10-50-42]`. It is **not** required to name the customer, and plenty write "Customer A accounted for 22% of revenue." But many small suppliers name them anyway, because a marquee customer is their best credential in front of investors. India's rule is the same shape — Ind AS 108, same 10% threshold, same absence of any naming requirement. In our own measured sample, Ichor Holdings' 10-K surfaced Lam Research and Applied Materials six times each, and Ultra Clean Holdings surfaced the same pair `[measured 2026-09-20]`.

**In our code.** This single accounting rule is why Atlas is built from the small side. Apple never has to tell you who makes its audio codecs; Cirrus Logic has to tell the market that one customer is most of its revenue, and chooses to name them `[verify: Cirrus Logic 10-K, customer concentration note]`. Our extractor targets this note specifically, and `dependency_edge.evidence_type` distinguishes `named_concentration` from `named_narrative`. **The trap is the threshold.** A supplier at 9.9% of revenue never appears in this note at all, so absence of a concentration disclosure is not absence of a relationship, and no scoring code may ever treat it as one.

## Dependency edge

**In one sentence.** Our word for one company relying on another, plus the exact sentence that proves it.

**What it actually is.** Atlas's atomic unit. An edge says: this entity depends on that entity, in this way, and here is the document, section, character range and sentence where a company said so. It is not an opinion and not an inference. If the sentence is removed, the edge must be removed with it.

**In our code.** `dependency_edge(from_entity_id, to_entity_id, edge_type, chunk_id NOT NULL, char_start, char_end, valid_from, valid_to, evidence_type, extractor_version, confidence)`. `chunk_id` is `NOT NULL` in the first migration and stays that way — the schema, not a code review, is what enforces the citation rule. `confidence` is written by deterministic scoring code, never by the model. Anonymous dependencies ("a limited number of suppliers") never become edges; they are stored as `dependency_claim` rows with `counterparty_resolved = false`, so the UI can honestly say "this company states it is single-sourced but does not say by whom" without inventing a node to point at.

## EDGAR

**In one sentence.** The free government website where every American public company's filings are published, the moment they are filed.

**What it actually is.** Electronic Data Gathering, Analysis and Retrieval. Every filing since the mid-1990s, free, no account, no key. Crucially, the SEC publishes an explicit fair-access policy rather than leaving it ambiguous: declare a real User-Agent with a contact email and stay under 10 requests per second. That combination — free, bulk, and *explicitly permitted* — is rarer than it sounds, and it is the single biggest reason Phase 1 is a US vintage. We verified access on 2026-09-20: `company_tickers.json` returned HTTP 200 in 3.2 seconds with a declared User-Agent `[measured 2026-09-20]`.

**In our code.** `apps/ingest/adapters/edgar.py`. The User-Agent is read from config and must carry a real project contact address before any real run — the placeholder in `scripts/measure_corpus.py` is not acceptable in production. Rate limiting is enforced in the adapter, not by the caller remembering.

## EDGAR full-text search

**In one sentence.** A search box across the actual text of filings — so you can ask "who mentioned Applied Materials?" instead of "what did Applied Materials file?"

**What it actually is.** A separate EDGAR service that indexes filing *contents* from 2001 onward `[verify: SEC's stated coverage start date]`, rather than just filing metadata. It answers the reverse question from the one EDGAR normally answers, and that reversal is the bottom-up inversion made mechanical. Search for a large buyer's name and what comes back is not their filings — it is **the filings of the smaller companies who named them as a customer**.

**In our code.** This is how the coverage universe assembles itself instead of being asserted from a screener. `apps/ingest/universe.py` queries full-text search for each of ~25 anchor buyers, collects the filer CIKs that mention them, ranks by mention count and SIC code, and proposes the supplier tier. The thesis of the entire product is a single free API call, which is a good thing to be able to say in an interview and a better thing to be able to demonstrate.

## Earnings call

**In one sentence.** A scheduled phone call where a company's bosses explain the quarter's results and then take questions from analysts — and the questions are the interesting part.

**What it actually is.** Two halves. **Prepared remarks** are written, lawyered and rehearsed, and say roughly what the filing says. **Q&A** is live, and an analyst who covers the sector full-time will ask the direct question management avoided in print: "Is TSMC still your sole foundry at that node?" Management usually answers, because refusing to is itself a signal. This is why transcripts are Tier-1 evidence and often more specific than the filing they accompany. Note the asymmetry between markets: SEBI requires Indian listed companies to publish transcripts; the US does not `[verify: SEBI LODR transcript requirement and which tier of companies it binds]`.

**In our code.** `document.doc_type = 'transcript'`, with `section.kind IN ('prepared','qa')` — the split matters because a claim from Q&A should be weighted differently from one in prepared remarks. Transcripts are **opportunistic** in Phase 1, not a dependency: we take what companies publish on their own IR sites and what appears as an 8-K Ex-99, and we declined licensed transcript feeds because their redistribution terms would stop us showing the quote. See [`COMPLIANCE.md`](../COMPLIANCE.md).

## Entity resolution

**In one sentence.** Working out that "TSMC", "Taiwan Semiconductor Manufacturing Company Limited" and "台積電" are one company, and that two different "Apex Industries" are two.

**What it actually is.** The unglamorous problem that decides whether the graph is real. Filings name companies inconsistently: legal names, trading names, former names, abbreviations, subsidiaries that are really the parent, parents that are really a subsidiary. Our measured run hit both failure directions in one afternoon. Matching on substrings produced `OPERA` inside "OPERATIONS" and `UNITI` inside "OPPORTUNITIES" — false merges from sloppy matching. Fixing that with word-boundary matching then exposed the harder class: Cirrus Logic's filing surfaced Qualcomm, Synaptics, Skyworks and Analog Devices, which are all real companies, correctly matched, and **competitors rather than counterparties** `[measured 2026-09-20]`.

**In our code.** `entity` plus `entity_alias(entity_id, alias, source, valid_from, valid_to)`. Merges are temporal: a merge decided in week 14 gets `valid_from` = the decision date and does not retroactively rewrite what the graph looked like in week 3. Free help exists and we should use it — GLEIF publishes global Legal Entity Identifier data including parent relationships `[verify: GLEIF licence terms and Level 2 parent data coverage]`. The failure mode is not subtle: merge two companies and you weld two subgraphs together, and every exposure list downstream is wrong in a way that looks perfectly consistent.

## Filed date vs period end

**In one sentence.** The difference between when something happened and when the public was allowed to know.

**What it actually is.** Every filing has two dates and they are weeks or months apart. Axcelis' 10-K in our sample covers the year ending 2024-12-31 and was filed on 2025-02-28 `[measured 2026-09-20]`. Everything in that document describes 2024, but none of it was public until the last day of February 2025. For a product that claims to reconstruct the past, only one of those dates is legitimate.

**In our code.** `document.period_end` and `document.filed_at` are separate columns, and `dependency_edge.valid_from = document.filed_at`, never `period_end`. Using `period_end` would hand us two months of free clairvoyance in every single backtest — invisible in the output, fatal to the claim. This is also why the Phase 1 vintage is defined as "annual filings with `filed_at` in calendar 2025" rather than "FY2024": the filing-date definition is the one the query actually uses, so making it the universe definition removes a whole category of off-by-one.

## Fiscal year

**In one sentence.** A company's own private twelve-month year, which often does not start in January.

**What it actually is.** Companies pick their own year end. In our ten-company sample the fiscal year ends landed on 2024-12-27, 2024-12-28, 2024-12-31, 2025-03-29 and 2025-10-31 — five different dates across ten companies in a single sector `[measured 2026-09-20]`. Cirrus Logic's "fiscal 2025" ended in March 2025. Kulicke & Soffa's ended in October. So "FY2025" means different things for different companies and comparing them as if it meant one thing is simply an error.

**In our code.** We never join on fiscal year labels. `period_end` is a date and comparisons are date comparisons. The off-by-one this prevents is the classic one in financial data: treating a fiscal-year label as a calendar year, then attributing an event to the wrong reporting period and "discovering" that companies disclosed an impact before the event occurred.

## Forward-looking statement

**In one sentence.** A company's guess about the future, wrapped in a legal warning that it is only a guess.

**What it actually is.** Statements about what a company expects, plans or believes will happen. US law gives these a safe harbour — under the Private Securities Litigation Reform Act of 1995, a company generally cannot be sued for a forward-looking statement that turns out wrong, provided it was identified as forward-looking and accompanied by meaningful cautionary language. That is why every filing carries the boilerplate paragraph, and why so much filing language is hedged: the hedging is what buys the protection.

**In our code.** A dependency claim in a forward-looking sentence is a different object from one in a statement of historical fact. "We purchased 40% of our wafers from X" is a fact. "We expect to source a majority of our wafers from X" is a plan that may not happen. The extraction schema carries `tense` and the scoring code weights them differently. Treating the second as the first builds a graph of intentions and calls it a graph of dependencies.

## Golden set

**In one sentence.** A batch of documents a human has read carefully, with the right answers written down, used to grade the machine.

**What it actually is.** Without one, "our extraction is accurate" is a feeling. With one, it is precision and recall, measured on every change. Ours is not a separate chore — it is the direct output of the week-3 validation experiment, where five people annotate 40 documents by hand. Two annotators per document, independently, so we can also measure whether the *guideline* is applicable rather than just whether the model agrees with one person's reading.

**In our code.** Stored as fixtures, run in CI on every pull request that touches extraction, with precision and recall printed in the PR. A change that improves recall and quietly costs precision must be visible before merge, not discovered in week 16. The golden set also calibrates the free stage-one filter: our prototype passes 28.2% of chunks to the model `[measured 2026-09-20]`, but the number that actually matters is what fraction of *true* edges that filter throws away, and only human annotations can tell us that.

## Hedged disclosure language

**In one sentence.** The deliberately vague phrases companies use to admit a dependency without naming anyone.

**What it actually is.** "Certain suppliers." "A limited number of vendors." "One of our largest customers." "A significant portion of our revenue." "A facility located in Asia." None of these are accidents — they satisfy the disclosure obligation while giving competitors nothing. Learning to read them is most of what separates someone who can use filings from someone who cannot, and building the lexicon of them is a deliverable of week 3.

**In our code.** These phrases are the extractor's explicit **negative class**. A chunk containing "we depend on a limited number of suppliers" must not produce an edge, because there is no counterparty to point at and inventing a placeholder node would corrupt the graph. It produces a `dependency_claim` with `counterparty_resolved = false`. That row is not wasted: it lets a company be flagged as *disclosing concentration without naming it*, which is genuinely useful information and is honest about being an absence.

## Look-ahead bias

**In one sentence.** Using something you only found out later to judge a decision made earlier — like marking an exam with an answer key the student never had.

**What it actually is.** On 19 March 2021 a fire hit Renesas' Naka fab. Suppose we ask Atlas who was exposed. Our graph holds an edge saying Company X depends on Renesas — extracted from a filing published in February 2022, eleven months *after* the fire, in which management explained the disruption it caused. Score the 2021 event with that 2022 edge and we are "predicting" a fire using a document that exists only because the fire happened. Every accuracy number produced this way is inflated, and the inflation is invisible unless you go looking. This is the standard way quantitative research products embarrass themselves, and a reviewer detects it with one question: what date does your graph query use?

**In our code.** Every read goes through `edges_as_of`. The test that must exist **before** the backtest harness does: seed an edge whose `valid_from` is one day after a known event, run the backtest, assert the edge is absent from the result and the exposure score is byte-identical to the run without it. If that test does not exist, every number we publish is a lie we have not noticed yet.

## Materiality

**In one sentence.** Whether a fact is big enough that a sensible investor would want to know it.

**What it actually is.** The legal threshold that decides what must be disclosed. The US standard comes from *TSC Industries v. Northway* (1976): information is material if there is a substantial likelihood a reasonable shareholder would consider it important in deciding how to vote or invest `[verify: exact wording]`. It is deliberately not a number, which is why companies and their lawyers argue about it. For us it explains the shape of our raw material — a company discloses a supplier relationship when it is material, so **the graph we can build is structurally a graph of large dependencies**.

**In our code.** No column, but it bounds every claim we make. It is the honest answer to "is your graph complete?" — no, and it cannot be, because disclosure is triggered by materiality and the small dependencies are exactly the ones that never trip the threshold. Since the product's value lives in the non-obvious third-hop name, and non-obvious often means small, this tension is real and we measure it rather than talk around it: week 3 records, for every named counterparty found, whether a materiality figure was attached and whether it sat above or below 10%.

## MD&A

**In one sentence.** The section where management explains, in prose, why the numbers moved.

**What it actually is.** Item 7, Management's Discussion and Analysis. The financial statements say revenue fell 12%; MD&A is where management has to say *why*, in sentences. That makes it the densest source of causal language in the whole document — "the decline was primarily attributable to reduced orders from our largest customer" is the kind of sentence that exists nowhere else. It is written by people, reviewed by lawyers, and sits between the boilerplate of Item 1A and the tables of Item 8.

**In our code.** One of the three Items we target, alongside Item 1 and Item 1A. Targeting those three plus the concentration notes, rather than ingesting whole documents, cut the text we process roughly in half before any filtering `[measured 2026-09-20]`. MD&A also disproportionately contains the *quantified* claims — the percentages that let deterministic scoring code assign an exposure weight instead of guessing.

## MNPI

**In one sentence.** Important company information the public does not have yet — and trading on it is a crime.

**What it actually is.** Material non-public information. If you know something material before the market does and you trade on it, or pass it to someone who does, that is insider trading. An entire industry sits near this line: expert networks that connect investors to industry insiders, alternative-data vendors selling satellite imagery of car parks and scraped credit-card panels. Some of it is legal, some has ended in prosecutions, and the boundary is not always obvious in advance. Regulation FD, adopted in 2000, is the related rule that stopped companies selectively briefing favoured analysts before telling everyone else.

**In our code.** There is no column for this because we never touch it. Every source in `docs/sources.md` is public and published, and the whole point of citing a filed document with character offsets is that anybody can check we read something they could have read too. This is a feature we advertise, not a limitation we apologise for: a procurement team at a listed company can use Atlas without their compliance officer having to think about it, which is a genuine commercial advantage over anything built on expert calls.

## Risk factors

**In one sentence.** The chapter where a company lists everything that could go wrong, mostly to avoid being sued later.

**What it actually is.** Item 1A, mandated since 2005. Companies list every plausible threat, which makes it simultaneously the most useful and the most useless section in the filing. Useless because it is defensive boilerplate written to pre-empt litigation, and much of it is copied year to year. Useful because it is the one place a company will admit "we depend on a single facility in Taiwan" or "a significant portion of our components are sourced from a single supplier" — the dependency is stated even when the counterparty is not.

**In our code.** Targeted, but treated as Tier 2. Risk factors are where **geography, commodity and jurisdiction** edges come from even when no counterparty is named — which is worth having, because a chokepoint event propagates through a geographic edge perfectly well. The trap is volume: Item 1A is long, repetitive and full of dependency vocabulary with no named counterparty, so it generates the most stage-one filter hits per unit of real signal. Year-over-year diffing is the obvious defence and it is a Phase 2 task.

## Segment reporting and the major-customer note

**In one sentence.** The part of the accounts that breaks the business into pieces and says how much each piece earns, and where.

**What it actually is.** A company with several distinct businesses must report them separately — revenue, profit and assets per segment — along with revenue by geography. The same standard carries the major-customer requirement described under [Customer concentration disclosure](#customer-concentration-disclosure). Two different things live in the same note, and both are ours: revenue-by-geography anchors a company to actual places on the map, and the customer note is where named edges hide.

**In our code.** Revenue-by-geography populates the geographic weights the propagation engine needs — a company earning 60% of revenue in Asia is exposed to an Asian chokepoint differently from one earning 5% there, and that is a number rather than a guess. The note is also short and high-yield, which is why our segmenter pulls a window around concentration and segment headings even when those headings sit outside the three targeted Items.

## Sole source

**In one sentence.** Only one company in the world makes the part you need, so if they stop, you stop.

**What it actually is.** Single sourcing, and it is the highest-value disclosure we can find. Many dependencies are soft — you could switch suppliers in a quarter at some cost. A sole-source dependency is hard: there is no substitute, and a disruption passes through at full strength. Companies disclose it because it is material, and they usually disclose it while refusing to say who the sole source is. Sometimes the industry answers the question for them — if a filing says its supplier is the only qualified producer of a particular photoresist, the set of candidates is very small.

**In our code.** `dependency_edge.substitutability`, set by deterministic rules from phrases the extractor returns verbatim — "sole source", "single source", "only qualified supplier". It is one of the largest multipliers in the propagation engine, which is exactly why the model is not allowed anywhere near the number. The model reports that the sentence contains the phrase "sole source" and returns the span; version-controlled scoring code decides what that is worth.

---

## Queued next (terms 26–50)

Buy-side and sell-side · Chokepoint · Precision and recall · Restatement · Survivorship bias ·
Tier-1 and tier-2 supplier · XBRL · SIC code · LEI · Reg FD · SEBI LODR · BRSR ·
Ind AS 108 · Free float and market cap bands · Investor presentation · Red herring prospectus ·
Bitemporality · Calibration · Inter-annotator agreement · Negative class · Chunk overlap ·
Event deduplication · Geocoding · Severity score · Surprise metric
