# Google AI Startup Buildathon 2026 — application answers

Team G27 · Vishwakarma University, Pune · City Buildathon: **Pune, 20–21 November**
Applications close **13 November**. Pitch deck: see `APPLY/README.md` for the link.

Everything below is copy-paste ready. Where a form field is shorter than the answer,
use the **short** version. Figures in `[brackets]` are the only things you must fill in.

---

## Startup / product name

**Atlas**

> Note: the university project is registered as *GeoTrade*. For this application use
> **Atlas** — GeoTrade is the name of an existing third-party product we studied, and
> judges may search it. Keeping them separate protects you.

## One line (under 150 characters)

> Atlas reads every public company filing and works out who depends on whom, so when
> anything breaks you know who gets hit three hops out — with the sentence that proves it.

## One line (under 80 characters)

> The dependency graph of the world economy, built from public filings.

## Idea — short (about 100 words)

> When a port closes or a plant burns down, everyone knows which companies are hit
> directly. Nobody knows who is hit second and third, because no list of those
> dependencies exists. Atlas builds it. We read the documents listed companies are
> legally required to publish, extract who depends on whom, place every company on a
> globe, and propagate real-world events through the graph. Every relationship we
> assert links back to the exact sentence in the source document. We have 23,020
> companies across six markets already loaded and running.

## Idea — long (about 300 words)

> **The problem.** Supply-chain and market risk tools answer the easy question. They
> tell you about the company that was hit. They cannot tell you about the mid-cap two
> or three steps away that quietly depends on it, because building that map requires
> reading tens of thousands of long, unstructured documents — and until multimodal
> models, that was not economically possible.
>
> **Why nobody has done it.** The obvious approach is to extract suppliers from large
> companies' filings. It fails. Supplier identity is commercially sensitive, so large
> filers write it out of the document: "certain suppliers", "a limited number of
> vendors". Build top-down and four months later you have a pipeline and an empty graph.
>
> **Our inversion.** Large companies hide their suppliers. Small suppliers *advertise*
> their large customers, because a marquee customer is their best credential — and
> accounting standards force disclosure of any customer above ten percent of revenue.
> So we build the graph from the smaller side of every relationship. We tested this on
> ten real semiconductor filings before writing any pipeline: one supplier named its two
> largest customers six times each in its own annual report, and a second, unrelated
> supplier named the same pair.
>
> **What exists today.** 23,020 companies across the US, India, UK, Germany, Canada and
> Australia, de-duplicated across cross-listings and share classes, 82,751 name aliases,
> 23,018 geocoded headquarters, a 25-table PostgreSQL and PostGIS schema, a read API at a
> 5 ms median, and a WebGL globe with live, replay and simulation modes. The evidence
> layer runs end to end on 225 real SEC filings and produces 194 distinct dependency
> relationships, every one carrying the sentence that proves it. We hand-judged 86 of
> them against the filings: **26 of 26 correct where the filing discloses a percentage,
> 68.3% on a random sample where it only names a counterparty.** Built by five students
> in twelve weeks with no funding.
>
> **What we build with Google.** The intelligence layer: Gemini for extraction, Gemma for
> the pre-filter, Gemini Live so you can ask the globe a question out loud, and Agent
> Skills for overnight monitoring.

## Solution — what the product does

> Atlas has one graph and three ways to query it.
>
> **Live.** A globe of 23,018 headquarters. An event lands, arcs propagate outward, and
> companies more than one hop from the event are visually marked — those are the names
> the user would not have listed themselves.
>
> **Replay.** Scrub to any past disruption. The graph is read as it stood that morning,
> never with anything filed later, so the backtest cannot cheat. Then reveal who actually
> reported an impact the following quarter.
>
> **Simulate.** Define a shock that has not happened. Run it forward and get a ranked,
> cited exposure table and a written brief.
>
> Every row carries the document, the section and the exact supporting sentence. The rule
> is enforced in the database schema: a dependency edge cannot be written without the
> identifier of the text chunk it came from, so an uncited claim is impossible even by
> accident.

---

## The five evaluation criteria

### 01 · Founder profile

> Five final-year Computer Engineering students at Vishwakarma University, Pune, who have
> already shipped the hard half of this product. In twelve weeks, alongside coursework,
> with no funding and no licensed data, we built a normalised six-market company database,
> a 25-table geospatial schema, a read API and an interactive 3D client.
>
> The detail that matters most: before writing any pipeline we ran an experiment to test
> whether our central assumption was even true, and designed the evaluation so it could
> prove us wrong. Most teams discover their core assumption was false in month four. We
> checked in week three.
>
> Priyanka Bana — product, platform, discovery
> Ishanya Bhumkar — disclosure ingestion and source adapters
> Krish Oswal — extraction and entity resolution
> Anushka Pallod — backend, schema and propagation engine
> Ayush Gawali — frontend and visualisation

### 02 · Product potential

> The problem is specific and the failure is expensive: a disruption reaches a company
> through a dependency it never mapped, and it finds out when the delivery does not
> arrive. The product answers that in seconds with evidence attached.
>
> What makes it defensible is the citation rule. Competitors give you a risk score. We
> give you a risk score plus the sentence a company published about itself. In a category
> where buyers have been burned by black-box scores, provenance is the product.

### 03 · Market viability

> Four buyer groups ask the same question and have no tool:
> procurement and supply-chain risk teams at mid-market manufacturers; credit teams at
> lenders doing supply-chain and trade finance; trade-credit insurers who need correlated
> exposure across a book; and research shops and family offices with no terminal budget.
>
> We deliberately target buyers **below the terminal line**. Incumbents sell to the top of
> the market at enterprise prices; the larger group underneath has the same problem, a
> budget line already labelled risk, and nothing to spend it on.
>
> India is our strongest market, not our second. SEBI requires listed companies to publish
> earnings-call transcripts; the SEC does not. The single richest source of named
> dependencies is structurally available here and not in the US. We have 4,974 Indian
> companies loaded already.
>
> Model: seats first (3–10 per team), API second (exposure as a field inside an insurer's
> own model), per-report third as a discovery mechanism. The graph is built once and served
> to everyone, so marginal cost per customer is near zero.

### 04 · Technical architecture

> Six stages, all on Google Cloud. See `APPLY/architecture.md` for the full version.
>
> Ingest (Cloud Scheduler + Pub/Sub + Cloud Storage) → Parse (Document AI) →
> Filter (Gemma on Cloud Run + an 82,751-name gazetteer) → Extract (Gemini on Vertex AI,
> schema-forced) → Resolve (Vertex embeddings + trigram similarity) →
> Serve (AlloyDB for PostgreSQL with PostGIS, exposure precomputed).
>
> Three invariants are enforced by the schema rather than by convention: no dependency
> edge without its citation; every edge carries validity dates so the graph can be queried
> as it stood on any past date; row-level security from the first migration.
>
> The model never produces a score. Gemini reports what a sentence says and writes the
> explanation; confidence and exposure weights come from version-controlled, unit-tested
> code. That is what makes the output defensible to a regulator and debuggable by us.

### 05 · Use of Google AI

> **Gemini / Gemini Omni** — multimodal extraction. A 300-page filing with tables, an
> investor deck and an hour of earnings-call audio become one input. In an earnings call
> the analyst's question is often worth more than the prepared answer; Omni hears both.
>
> **Gemma on Cloud Run** — self-hosted pre-filter. Measured on real filings it removes 85%
> of text before a paid token is spent. This is the unit economics of the whole company.
>
> **Gemini Live** — the interface nobody in this category has. Ask the globe out loud:
> "if the Taiwan Strait closes for three weeks, which of my suppliers stop shipping?"
> Spoken, ranked, cited answer while the globe flies to the event.
>
> **Google Agent Skills** — one monitoring agent per customer, owning a coverage list,
> reading the night's filings and filing a cited brief by morning.
>
> **Nano Banana** — a generated visual for every brief: the dependency chain drawn, the
> chokepoint mapped, ready for a board pack.
>
> **Vertex AI, AlloyDB, BigQuery, Cloud Run, Document AI, Maps Platform** — models,
> graph, corpus, services, parsing and geocoding on one platform.
>
> **Google AI Studio and Antigravity** — how five people ship this in two days.

---

## Two-day build plan (City Buildathon, Pune, 20–21 Nov)

| When | What ships |
|---|---|
| Day 1 AM | Gemini on Vertex replaces the extraction stub. First real cited edges in the graph. |
| Day 1 PM | Gemma on Cloud Run takes over the pre-filter. Cost per document measured live. |
| Day 2 AM | Gemini Live wired to the graph. Speak a question, hear a cited answer. |
| Day 2 PM | An Agent Skill files the first overnight briefing. Demo against the real database. |

We can be this specific because the graph, schema, API and globe already exist. We are
not building a product from zero in two days; we are adding the intelligence layer to one
that already runs.

## Traction, stated honestly

- 23,020 companies, 6 markets, 90 countries of incorporation, 19 exchanges
- 82,751 name aliases; 23,018 geocoded headquarters
- 25-table schema with citation, point-in-time validity and tenancy enforced in SQL
- Read API at a 5 ms median against a 200 ms budget
- 85% text reduction measured before any model call, reproducible with one command
- Zero errors across the automated data validation suite
- 225 real SEC filings ingested; 402 cited edges; **194 distinct dependency relationships**
- **Precision, hand-measured and published:** 26 of 26 correct where a percentage is
  disclosed (exhaustive, not sampled); 68.3% on a random sample of 60 narrative edges.
  The sample, the seed and every judgement are in the repo at `eval/`
- 20 of 21 displayed percentages are the right figure for the right company; 5 further
  figures are withheld because the sentence does not permit safe attribution
- **Not yet:** paying customers. Recall is unmeasured and we claim no number for it.
  Stage two of extraction is still deterministic rules, not a model - which is precisely
  what we would spend Google credits on first, with the evaluation already built to
  measure the delta against these exact samples.

## Things to fill in before you submit

- `[₹__]` price points on the market slide (slide 12)
- Confirm the role assignment on the team slide (slide 15) — swap if I guessed wrong
- Your preferred city: **Pune** (already set)
