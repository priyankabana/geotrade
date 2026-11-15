# Cost of one full corpus extraction

Budget is ₹0. Not small — zero. So "what does a full re-extraction cost" is not an
accounting question, it is an architecture question: **can five students re-extract the
entire corpus overnight, every week, without anyone hesitating before they press the
button?** If yes, we can iterate on prompts and schemas freely, which is the only way
extraction precision ever gets good. If no, the first extraction run silently becomes
permanent and we are stuck with whatever it produced.

This file records measured numbers. Regenerate with:

```bash
python3 scripts/measure_corpus.py     # writes measured_v2.json
```

Every figure below marked `[M]` came from an actual run. Figures marked `[E]` are
estimates with the arithmetic shown, and each names the measurement that will replace it.

---

## What was measured

**Run 2026-09-20.** Ten real 10-Ks pulled from EDGAR, sector-representative: UCTT, ICHR,
CRUS, FORM, PLAB, KLIC, ONTO, ACLS, AMKR, AMAT. All ten had `filed_at` in calendar 2025,
which incidentally confirms the Phase 1 vintage definition works on real data — their
fiscal year ends spread from 2024-12-27 to 2025-10-31, and the filing-date definition
captures all of them exactly once.

| Stage | Measurement | Value |
|---|---|---|
| Raw document, HTML stripped | median characters | **323,000** `[M]` |
| After targeting Items 1, 1A, 7 + concentration/segment notes | median characters | **166,500** `[M]` |
| — text removed by section targeting | | **46.2%** `[M]` |
| Chunking at 1,200 tokens / 150 overlap | chunks per document, mean | **41.1** `[M]` |
| Stage-one filter: dependency cue only | chunks passed | 88.3% `[M]` |
| Stage-one filter: named-entity gazetteer only | chunks passed | 30.7% `[M]` |
| **Stage-one filter: both, conjunction** | **chunks passed** | **28.2%** `[M]` |
| Chunks reaching the LLM, per document | mean | **11.6** `[M]` |
| Item segmentation succeeded | documents | **10 / 10** `[M]` |

**The single most useful line in that table is the cue-only row.** The dependency-cue
lexicon on its own eliminates almost nothing — 88% of targeted chunks in a 10-K contain
the word "customer", "supplier", "vendor" or a revenue percentage. Filing prose is
saturated with dependency vocabulary. The work is done entirely by the requirement that
a *named company other than the filer* also appear. Anyone who builds stage one as a
keyword filter will discover this in week 5; we know it in week 0.

**Compression from raw filing to model input:** if we sent whole documents we would
produce 756 chunks across these ten filings. We send 116. **We put 15.3% of each filing
in front of a model** `[M]`.

---

## The answer: how many stage-two calls does one full extraction need?

Retry factor of 1.15 assumed for schema-validation failures `[E — replace with the
measured rate after the first full run; a local 8B model under schema forcing is the
uncertain part]`. Input per call is chunk (1,200 tok) plus prompt and tool-schema
overhead (~400 tok); output ~250 tok. Call it **1,850 tokens per call**.

### Pilot slice — 42 companies, annual filings only

```
42 docs × 41.1 chunks              = 1,726 chunks
1,726 × 28.2% stage-one pass       =   487 chunks reach the model
  487 × 1.15 retry factor          =   560 stage-two calls
  560 × 1,850 tokens               =  1.04M tokens
```

### Phase 1 full — 200 companies, annual filings only

```
200 docs × 41.1 chunks             = 8,220 chunks
8,220 × 28.2%                      = 2,318 chunks reach the model
2,318 × 1.15                       = 2,666 stage-two calls
2,666 × 1,850 tokens               =  4.93M tokens
```

### Phase 1 full, with opportunistic sources

Both add-ons are `[E]`. Deck and transcript coverage of the universe is measured in
week 3; chunk counts for those formats are not yet measured at all.

```
Investor decks   200 × 50% coverage × 12 chunks =  1,200 chunks × 40% =   480 × 1.15 =   552 calls
Transcripts      200 × 30% coverage × 4/yr = 240 docs × 18 chunks = 4,320 × 35% = 1,512 × 1.15 = 1,739 calls
                                                                                    ─────────────────────
Annual filings                                                                          2,666 calls
Total                                                                                  ~4,960 calls  ≈ 9.2M tokens
```

## **≈ 5,000 stage-two calls for one complete re-extraction of the Phase 1 corpus.**

---

## Is that free?

Yes, and it is not close.

| Route | Constraint | One full run |
|---|---|---|
| Local 8B via Ollama, one laptop | 5 s/call `[E]` | **6.9 hours** — overnight |
| Local 8B via Ollama, one laptop | 10 s/call `[E]` | 13.8 hours — overnight |
| Local, split across 5 team laptops | 5 s/call | **1.4 hours** |
| Free-tier hosted API | 1,000 req/day `[E — depends on provider]` | 5 days unattended |

The pilot slice is **560 calls — under an hour on one laptop.** That is the number that
matters for weeks 3–6, because it means the extraction owner can change the prompt and
re-run the whole pilot corpus before lunch.

**Conclusion: a full re-extraction is an overnight job, not a budget line.** The design
requirement is met. Rate limits are the constraint, never cost, and the extraction queue
is built to run slowly and unattended rather than fast and expensive.

---

## What makes it stay free

1. **Stage one is not an LLM.** A lexicon plus a gazetteer plus a small classifier
   trained on the week-3 annotations. Measured today at 28.2% pass; the target after
   calibration is a tighter filter at ≥95% recall against the golden set. Recall is the
   number that governs — a filter that is cheap and drops real edges has cost us the product.
2. **Section targeting before chunking.** 46.2% of each document removed for free `[M]`.
3. **Cache by chunk hash.** `extraction_cache(chunk_sha256, extractor_version, prompt_version, result_json)`.
   A prompt change re-runs everything by design. A new filing vintage re-runs only the
   new chunks. Re-running an unchanged corpus with an unchanged prompt costs zero calls.
4. **Local embeddings.** An open sentence-transformer on our own machines. No embedding
   API, ever — embeddings are the line item that scales with corpus size rather than
   with change, and paying per document for them is how this becomes a real bill.
5. **Free infrastructure tiers only.** If a design needs a paid tier, it is the wrong
   design for us.

---

## Tracked in CI

Cost is a test, the same way precision is. On every pull request touching extraction:

| Metric | Budget | Fails the build at |
|---|---|---|
| Stage-one pass rate | ≤ 30% | > 40% |
| Stage-one recall vs golden set | ≥ 95% | < 92% |
| Stage-two calls per document | ≤ 13 | > 18 |
| Tokens per document | ≤ 25,000 | > 35,000 |
| Full-corpus wall clock, pilot slice | ≤ 60 min | > 120 min |

A pull request that improves precision by widening the filter has to say so out loud,
with the number, before it merges.

---

## Known gaps in this model

- Retry rate under schema forcing is assumed, not measured. First real run fixes it.
- Investor-deck and transcript chunk counts are entirely unmeasured. Week 3.
- Chunks in slide decks and transcripts behave differently from filing prose; the
  28.2% pass rate does not transfer and should not be quoted for them.
- n = 10. Small, single-sector, and every document is a 10-K. A 20-F has a different
  structure and is not represented here at all.
