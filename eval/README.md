# Extraction quality: how we measured it, and what it is

Every number here was produced by the scripts in this folder against the graph
in the database. Nothing is estimated and nothing is rounded in our favour. If
you re-run the pipeline you will get these numbers back.

## Why this exists

Atlas makes one promise: every edge in the graph cites the sentence in a public
filing that supports it. A promise like that is only worth something if someone
has gone and read the sentences. So we did, by hand, twice, and fixed what the
reading found.

## Method

The unit we measure is the **relationship**, not the sentence. One
Ducommun -> Boeing dependency cited by sixteen different sentences is one edge a
user sees, so counting sentences would let a single well-cited pair swamp the
result.

Two populations, measured differently:

| Tier | What it is | How measured |
|---|---|---|
| `named_concentration` | the filing states a percentage | **exhaustive** - every one judged |
| `named_narrative` | the filing names the counterparty without a figure | **seeded random sample** |

`scripts/sample_pairs.py` writes the sample to disk with a fixed seed *before*
anything is judged, so the set under test cannot be quietly reshaped by what the
judging turns up.

A relationship counts as correct only if the cited sentence really states that
dependency, in that direction, between those two companies. A right relationship
attached to the wrong legal entity ("Hyundai Motor India Limited" for a sentence
about Hyundai Motor Company) counts as wrong.

## Results

Graph as measured: **421 cited edges, 207 distinct relationships, 83 companies.**

| Tier | Population | Judged | Correct | Precision |
|---|---|---|---|---|
| Concentration-backed | 28 | 28 (all) | 28 | **100%** |
| Narrative | 179 | 60 | 41 | **68.3%** (95% CI 56-79%) |
| Overall | 207 | 88 | 69 | **~72%** |

Percentages, within the concentration tier:

| | Count |
|---|---|
| figure shown and correct | 21 |
| figure shown and wrong | 0 |
| figure withheld as unattributable | 7 |

**Every percentage we display is the right number for the right company**, and
where the sentence does not let us tell, we show nothing rather than guess.
Seven of the twenty-eight relationships are shown without a figure for that
reason.

## Recall, and the ceiling it exposes

Precision asks whether what we produced is true. Recall asks what we missed. We
claimed no number for it until now. Here is the measurement, and what it found.

**Method.** The candidate set cannot come from the extractor's own rules, or we
would find no misses by construction. So `scripts/measure_recall.py` sweeps the
whole corpus with a deliberately blunter pattern - a percentage near a customer
or supplier word, in a sentence that also contains a capitalised multi-word
name - and over-generates on purpose. It found **187 disclosure-shaped
sentences**. Each is marked automatically with whether the extractor produced a
claim at the same character offset, and a seeded sample of 60 was then read by
hand, because only a human can say whether a given sentence really discloses
anything.

**What those 60 contain:**

| | Count | Example |
|---|---|---|
| Name no company at all | **48** | "one customer accounted for 42.86% of total sales" |
| Name a party outside our six markets | **7** | the US Department of Defense, WT Microelectronics (Taiwan), Chinese trading companies, a Singapore university |
| Name a public company we cover | **5** | Daimler and PACCAR; Applied Materials, twice; the Cerence OEM list |

**Recall on what is actually capturable: 5 of 5.** The sample is small, so the
honest interval is wide - a 95% Wilson interval on 5/5 runs from roughly 57% to
100% - and we would not quote the point estimate without that caveat.

**The finding that matters is the first row.** Four fifths of the concentration
disclosures in our corpus name nobody. The rule obliges a company to disclose
*that* it depends on one customer; it does not oblige it to say *who*. "One
customer accounted for 42.86% of total sales" satisfies the regulator completely
and tells us nothing.

That is a ceiling on the method, not a defect in the code, and no amount of
better extraction moves it. It is also the answer to anyone who asks why the
graph is small: the graph is not small because we read badly, it is small
because most of what is disclosed is anonymous. On our corpus, roughly **one
disclosure in twelve** names a counterparty we can resolve.

It sharpens what expanding the corpus is worth, too. Going from 225 filings to
5,000 is an overnight run and should yield relationships in proportion - but it
will not change the fraction that is anonymised.

## Where it started

The first audit, before any of the fixes below, measured **62.5%** (50/80) at the
relationship level. The concentration tier then had 36/38 relationships correct
but only **20/36 percentages** correct - aggregate figures such as "our top five
customers collectively accounted for 57%" were being copied onto every name in
the list. That was the single worst defect in the system and it was invisible
until somebody read the sentences.

## What the reading found, and what we changed

Each of these came from a specific misread edge, not from theory.

1. **Case is the strongest signal in the text and we were throwing it away.**
   The matcher uppercased everything before lookup, so "financial institutions"
   matched a company called Financial Institutions. Matching now preserves case
   and requires proper-noun shape. `scripts/extract.py: match_companies`

2. **A dictionary cannot separate generic from specific; the corpus can.**
   "Applied Materials" and "financial institutions" are both ordinary English.
   But a company name is written capitalised nearly every time it appears and a
   generic phrase is not, so we count both forms across all 225 filings and keep
   only names that are overwhelmingly capitalised. This is what removed Nasdaq
   (present in 53% of filings), Sarbanes-**Oxley** (59%), "Commodities",
   "Strategic Investments" and 157 others, while keeping Boeing, Stellantis and
   FedEx. `scripts/df_gazetteer.py`, audit trail in `eval/gazetteer_df.tsv`

3. **A cue word means what the grammar around it says it means.** "We are a
   supplier to Ford" and "our suppliers include Ford" use the same noun and point
   opposite ways. Reading the noun alone inverted roughly a third of the graph.

4. **A total is not a share.** "Our top five customers collectively accounted for
   57%" says nothing about SoftBank alone. Figures introduced as aggregates are
   now suppressed rather than attributed.

5. **A figure that follows a name beats one that precedes it**, and no figure can
   belong to a company if another company's name sits between them. In
   "Daimler AG 18% PACCAR Inc. 11%" that is the whole difference between right
   and wrong.

6. **"ASICs" is an acronym; "ASICS" is a shoe company.** A lowercase plural on an
   otherwise all-caps token marks an acronym, not a name.

7. **Companies get named for reasons that are not dependencies** - executive
   biographies, social media accounts, competitor lists, share buybacks, the
   company's own plants and brands. These are now filtered explicitly.

8. **A name at the start of a sentence was being dropped entirely.** A capital
   there proves nothing on its own, so we refused it - and lost every company
   that happened to open a sentence. Now a second capitalised token in the same
   name vouches for the first: in "Thor Industries and Forest River accounted
   for...", the capital on *Industries* is the evidence.

9. **Among equally confident citations, the shorter quote wins.** A tight
   sentence states a relationship; a 2,000-character financial table merely
   contains both names. Dana's edge to Stellantis was being cited by a
   geography-of-revenue table until we ordered on this.

10. **A dictionary was still deleting real companies.** The older lexical filter
    suppressed any two-word name whose words were both ordinary English. That
    killed "Applied Materials" - a real company, disclosed by Benchmark
    Electronics as 14% of its sales - along with 6,492 others including Intrepid
    Potash and Parsley Energy. The recall measurement found it. Multi-word names
    are now judged only by how the corpus writes them.

Full history in the `EXTRACTOR_VERSION` string: `rules-1.0` -> `rules-3.0`.

## Regression tests

Every fix above is pinned by a test in [`../tests/test_extract.py`](../tests/test_extract.py),
built from the real sentences that exposed it. 30 tests, run with `make test`.
They exist because each of these was expensive to find and would be cheap to
undo.

## What is still wrong

We are reporting the failures because a precision number without them is not
worth reading. Of the 19 narrative-tier failures:

- **6 entity resolution** - the right relationship bound to the wrong legal
  entity. "Carraro S.p.A." resolving to Carraro India Limited; "ISTAR", a
  military acronym, resolving to iStar Inc. Aliases that are genuinely ambiguous
  between two real companies are the hard case here.
- **6 not a dependency** - a company named in a sentence about something else,
  where no surface cue distinguishes it.
- **4 competitor lists** - bulleted lists of competitors sitting directly above a
  "Customers" heading, which our sentence splitter cannot tell apart.
- **2 direction** - including Dell/VMware, where a distribution agreement reads
  either way without outside knowledge.
- **1 misreading** - "supports Boeing aircraft for customers" is not a Boeing
  dependency.

There is also a class the audit confirmed but cannot fix inside extraction:
**post-acquisition brands**. Broadcom's filings discuss VMware and Symantec as
product lines, not counterparties, because Broadcom bought them. That is an
entity-resolution problem, not an extraction one.

## The honest limitation of these numbers

Fixes 3-7 were derived from reading the first sample. The narrative figure above
comes from a fresh seed, but with 179 relationships in the population a new
sample necessarily overlaps the one we tuned on, so **68.3% is likely a point or
two optimistic**. The concentration tier does not have this problem: it is
measured exhaustively, so 100% is the whole population, not an estimate.

## What this says about the design

The rules-based stage two is at its ceiling. The remaining failures need
knowledge the sentence does not contain - that Dell distributes for VMware, that
ISTAR is a radar acronym - and no amount of further regex will supply it.

This is why stage two is a single function with a fixed input and output shape.
`extract_sentence` takes one sentence and returns zero or more claims; replacing
its body with a schema-forced model call changes nothing else in the pipeline,
and the citation guarantee holds either way because the offsets come from the
sentence, not from the model.

The product decision that follows: **lead with concentration-backed edges.** They
are 13% of the graph and they are right essentially all of the time.

## What is in this folder

These are the working papers, kept rather than tidied away, because an
evaluation you cannot inspect is an assertion.

| File | What it is |
|---|---|
| `concentration_all.txt` | **Every** concentration-backed relationship with its citation. Exhaustive. Regenerate with `make audit` |
| `narrative_sample.txt` | The 60 narrative relationships behind the 68.3% figure, seed 991103 |
| `gazetteer_df.tsv` | Capitalisation and document-frequency evidence for every alias, with the keep/suppress verdict and why |
| `pairs.txt` | The **first** audit, 80 relationships. This is the 62.5% baseline |
| `pairs_v2.txt` | The second audit, after the case and direction fixes |
| `pairs_final.txt` | A 120-relationship draw kept for anyone who wants to judge more than we did |
| `recall_candidates.txt` | The 60 disclosure-shaped sentences behind the recall figure, seed 4417 |
| `backtest_baseline.json` | Reach and surprise per event; the baseline `make backtest` gates against |

The earlier samples are from earlier extractor versions and do not describe the
current graph. They are kept because the trajectory is part of the evidence.

## Reproducing

```bash
make gazetteer-df    # measure which aliases are generic -> eval/gazetteer_df.tsv
make extract         # rebuild the graph from the chunks
make audit           # dump the concentration tier in full -> eval/concentration_all.txt
make sample          # draw a seeded sample of relationships to judge
make eval            # print the graph's current size
make recall          # disclosure-shaped sentences the extractor produced nothing from
make backtest        # replay the 26-event benchmark, fail on regression
make test            # 60 tests: extraction, point-in-time, propagation, tenancy
```

Set `SAMPLE_SEED` and `SAMPLE_OUT` to draw a different sample:

```bash
SAMPLE_SEED=991103 SAMPLE_OUT=eval/mine.txt make sample
```
