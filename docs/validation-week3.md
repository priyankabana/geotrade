# Week 3 validation experiment

**Pre-registered. Decision rules written before any document was read.**

The entire product rests on one assumption: that small and mid-cap filings name their
large customers often enough to build a dense graph, and that large-cap filings do not.
This experiment measures that assumption before we build four months of machinery on top
of it.

Reading the documents first and deciding what counts afterwards is how people talk
themselves into a thesis. So the gates below are fixed now, and the file is committed
before the sample is drawn.

**Status:** not yet run. Every table is blank on purpose.

---

## What we are measuring

1. **Named-counterparty yield** by document type and market-cap band. The core question.
2. **Resolvability** — can a human map the name to a real entity in under two minutes?
3. **Materiality attachment**, and whether it sits above or below the 10% threshold.
   This is the one that tests whether the product's *value* survives, not just its density.
4. **Inter-annotator agreement** — whether five people can apply one guideline.
5. **IR-site transcript and deck coverage** of the pilot universe.
6. **Stage-one filter recall** against what humans found.

---

## Sampling

**40 documents, stratified, seeded, frozen in git before anyone reads anything.**

| Stratum | n | Definition |
|---|---|---|
| Large cap 10-K | 20 | market cap > $10B, from the pilot universe |
| Small / mid cap 10-K | 10 | market cap $250M – $10B, from the pilot universe |
| Earnings call transcript | 10 | any band, from companies that publish on their own IR site |

Procedure:

1. Build `data/universe/pilot.csv` first.
2. Draw the sample with a fixed seed. Record the seed in the PR description.
3. Commit the 40 rows — ticker, CIK, accession number, URL, stratum — to
   `data/validation/sample.csv` **in a PR merged before annotation begins**.
4. Nobody reads a document before that PR merges.

Freezing the list is the whole defence against the most natural bias in the world: quietly
dropping a document that came back empty. If a document turns out to be unreadable, it
stays in the sample and is recorded as a failure with a reason.

**Two annotators per document, working independently and blind to each other.**
40 × 2 = 80 annotations across 5 people = 16 each. At roughly 25 minutes per document —
you read four named sections, not 200 pages — that is about 7 hours per person across a
week.

### One honest limitation, stated up front

With n = 20 in the large-cap arm, a true yield of 15% gives a 95% confidence interval of
roughly ±16 percentage points. **This experiment can tell "very low" from "very high." It
cannot tell 20% from 35%.** That is sufficient for the decision it exists to make — how to
weight the universe — and it is not sufficient to publish a precise yield figure. We will
report the interval, not just the point estimate.

The transcript arm is a **convenience sample**, not a random one: it can only be drawn
from companies that publish transcripts. It measures "when a transcript exists, how rich
is it", not "how rich are transcripts across the sector." Recorded as a caveat, not fixed.

---

## What a human counts

**The annotation unit is a candidate dependency mention:** a sentence, or two contiguous
sentences, asserting that the filer depends on — or is depended on by — a specific
external party.

Read only these sections. Do not read the whole document.

| Document | Sections to read |
|---|---|
| 10-K | Item 1 Business · Item 1A Risk Factors · Item 7 MD&A · the concentration-of-credit-risk, major-customer and segment notes |
| Transcript | Prepared remarks **and** Q&A, marked separately |

For every mention found, record five things.

**1 — Direction**

| Value | Meaning |
|---|---|
| `upstream` | filer depends on this party (supplier, foundry, contract manufacturer) |
| `downstream` | this party depends on the filer (customer) |
| `peer` | partner, JV, licensor — a relationship that is not a dependency |

**2 — Specificity**

| Value | Example | Becomes an edge? |
|---|---|---|
| `named` | "Lam Research" | **yes — this is the only class that does** |
| `typed_anonymous` | "a limited number of suppliers", "Customer A" | no |
| `geographic` | "a facility located in Taiwan" | geography edge only |
| `commodity` | "neon gas", "photoresist" | commodity edge only |

**3 — Resolvability.** Can you map the name to a real, specific entity in **under two
minutes**, using only public search? `yes` / `ambiguous` / `no`. Time yourself; this is
the number that tells us how hard Phase 2 is.

**4 — Materiality attached.** Is there a figure? `none` / `below_10pct` / `at_or_above_10pct`
/ `qualitative_only` (e.g. "sole source" with no number).

> **This axis is the one to get right.** The 10% disclosure threshold means the edges
> easiest to find are systematically the *largest* and therefore the *least surprising*.
> If nearly every named edge we find carries a figure at or above 10%, the graph will be
> dense and the surprise metric will struggle in Phase 3 — and we need to know that in
> week 3, not week 13.

**5 — Relationship class, including the negatives.** `supplier` / `customer` / `competitor`
/ `partner` / `former` / `hypothetical`.

> `competitor` is mandatory and is not a throwaway. Our prototype filter surfaced
> Qualcomm, Synaptics, Skyworks and Analog Devices from Cirrus Logic's filing — all
> correctly matched companies, none of them counterparties `[measured 2026-09-20]`. Item
> 1's Competition subsection sits right beside dependency vocabulary. These annotations
> become the negative class that teaches the extractor the difference.

Also record per document: **time taken**, **sections that could not be located**, and
every **hedge phrase** encountered verbatim.

---

## The tables

### Table 1 — Yield by stratum

| Stratum | n | docs with ≥1 named counterparty | % | named mentions, total | per doc, median | resolvable in <2 min | % resolvable |
|---|---|---|---|---|---|---|---|
| Large cap 10-K | 20 | | | | | | |
| Small / mid cap 10-K | 10 | | | | | | |
| Transcript — prepared | 10 | | | | | | |
| Transcript — Q&A | 10 | | | | | | |

### Table 2 — Specificity mix

| Stratum | named | typed_anonymous | geographic | commodity | total mentions |
|---|---|---|---|---|---|
| Large cap 10-K | | | | | |
| Small / mid cap 10-K | | | | | |
| Transcript | | | | | |

### Table 3 — Materiality attachment on named mentions

| Stratum | none | below_10pct | at_or_above_10pct | qualitative_only |
|---|---|---|---|---|
| Large cap 10-K | | | | |
| Small / mid cap 10-K | | | | |
| Transcript | | | | |

### Table 4 — Relationship class on named mentions

| Stratum | supplier | customer | competitor | partner | former | hypothetical |
|---|---|---|---|---|---|---|
| Large cap 10-K | | | | | | |
| Small / mid cap 10-K | | | | | | |
| Transcript | | | | | | |

### Table 5 — Inter-annotator agreement

| Metric | Value |
|---|---|
| Documents where both annotators' named counts differ by ≤ 25% | /40 |
| Mean absolute difference in named count | |
| Agreement on `specificity` where both found the same mention | % |
| Agreement on `relationship_class` | % |

### Table 6 — Same company, filing vs transcript

Only for companies where both are in the sample. This is the direct test of whether
transcripts are worth an adapter.

| Ticker | named in 10-K | named in transcript | ratio |
|---|---|---|---|

### Table 7 — IR-site coverage of the pilot universe

Filled from `data/ir_coverage/ir_sites.csv`, all 42 companies, not just the sampled 10.

| Metric | Count | % of 42 |
|---|---|---|
| Publish full transcripts (prepared + Q&A) | | |
| Publish prepared remarks only | | |
| Publish audio replay only | | |
| Publish investor decks, last 2 years | | |
| `robots.txt` permits the IR path | | |

### Table 8 — Stage-one filter, calibrated

The prototype passes 28.2% of chunks `[measured 2026-09-20]`. Pass rate was never the
number that mattered — **recall is.**

| Metric | Value |
|---|---|
| Named counterparties found by humans | |
| ...that fall in a chunk the filter passed | |
| **Filter recall** | **%** |
| Chunks passed | % |
| Human-found mentions the filter missed, by cause | |

---

## Pre-registered decision gates

### G1 — Small / mid cap named yield. *The main gate.*

| Result | Decision |
|---|---|
| **≥ 60%** of docs have ≥1 named counterparty | Inversion confirmed. Proceed as specified, universe 70/30 supplier-weighted. |
| **30–60%** | Proceed, but promote investor decks and 8-K Item 1.01 exhibits from Tier 1 *aspiration* to Phase 1 *adapters*. Filings alone will not be dense enough. |
| **< 30%** | **The sector is wrong, not the thesis.** Re-run on 15 auto-component documents before committing. One week budgeted; the fallback is named in `coverage-universe.md`. |

### G2 — Large-cap yield

Expected below 20%. Below 20% **confirms the inversion and is a finding, not a failure** —
it is the measured justification for weighting the universe toward suppliers, and it is
the answer to "companies don't name their suppliers, how do you have a graph at all?"

If large-cap yield comes in above 50%, do not celebrate. Check Table 4 first: it is most
likely competitor and partner mentions, not counterparties.

### G3 — Transcripts

| Result | Decision |
|---|---|
| Table 6 ratio **≥ 2.0** *and* Table 7 full-transcript coverage **≥ 30%** | Transcripts are Tier 1 with a Phase 1 adapter. |
| Ratio ≥ 2.0 but coverage < 30% | Rich but too sparse. Defer to Phase 3. Phase 1 graph is filings plus decks. |
| Ratio < 2.0 | Transcripts are not worth their ingestion cost. Drop to Tier 3 and say so. |

### G4 — Resolvability

Below 70% resolvable in under two minutes means entity resolution is harder than assumed.
The alias table and GLEIF integration move into Phase 1 and Phase 2 gets a week.

### G5 — Inter-annotator agreement

If more than 10 of 40 documents show annotators differing by over 25% on named count,
**the guideline is broken, not the annotators.** Stop. Rewrite it, re-annotate 10
documents, then continue. A golden set built on a rulebook five people apply differently
is worse than no golden set, because it produces precision numbers that mean nothing.

### G6 — Materiality distribution. *The gate nobody would think to set.*

If **over 80%** of named mentions carry a figure at or above 10%, the graph is being built
almost entirely from threshold-triggered disclosures — the large, obvious dependencies.

That does not stop Phase 1. It is an early warning that the **surprise metric** will
struggle, because the edges we can see are the ones an analyst already knows. The response
is to weight Phase 2 toward narrative mentions in Item 1 and transcript Q&A, which sit
below the threshold, and to say so in `metrics.md` rather than discover it in Phase 3.

---

## By-products — why this week pays for itself three times

1. **The golden set.** These 40 annotated documents become the ground truth for extraction
   precision and recall in CI from Phase 2 onward. It is not a separate chore.
2. **The hedge-phrase lexicon.** Every "certain suppliers" and "a limited number of"
   collected verbatim becomes the extractor's negative class and stage one's first input.
3. **The competitor negative class.** Table 4's `competitor` rows are the training signal
   for the one distinction rules cannot make.
4. **A human baseline.** Documents per hour a person can do, which is what "cost per
   document" should be compared against.

---

## Write-up

`docs/validation-week3-results.md`, with the raw counts, honestly, even if they are bad.
Then a plain statement of what the numbers imply for universe design and which gate fired.

If the result is bad, it is still the best week of the project: we measured the assumption
before building on it, and "we ran the experiment and changed the plan" is a better story
than any result we could have hoped for.
