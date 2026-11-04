# ADR 0001 — Building at zero marginal cost

**Status:** accepted · **Date:** 2026-09-20 · **Deciders:** all five

## Context

Five students, no funding, twenty weeks. The budget for this project is ₹0, and that is
a fact about our situation rather than a temporary condition we expect to fix.

The naive reading is that this limits ambition. It does not, but it does change the
architecture, and the change has to be made deliberately at the start rather than
discovered in week 12 when a free tier runs out mid-backfill.

The real risk of a budget constraint is not that we cannot afford a run. It is that the
*first* extraction run silently becomes permanent. If re-extracting the corpus is
expensive or slow or requires someone's permission, nobody will do it, the prompt will
never be improved after week 6, and extraction precision will be whatever it happened to
be on the first attempt. Iteration is how extraction gets good, and iteration has a price
we must drive to zero.

## Decision

Design so that a full re-extraction of the corpus costs nothing and can be run weekly
without anyone hesitating.

1. **Stage one of extraction is not an LLM.** A hedge-phrase and entity-cue lexicon, a
   gazetteer built from SEC's own `company_tickers.json`, and a small classifier trained
   on the week-3 human annotations. Measured today at 28.2% of targeted chunks passed to
   stage two, with 46.2% of each document already removed by section targeting `[measured
   2026-09-20]`.
2. **Stage two is free-tier hosted APIs or a local model through Ollama**, with
   schema-forced output. We assume rate limits, never cost limits. The extraction queue
   runs slowly overnight rather than fast and expensive.
3. **Embeddings run locally** with an open model. No embedding API under any circumstances.
4. **Every extraction is cached by chunk hash.** Re-extract only what changed.
5. **All infrastructure on free tiers.** If a design needs a paid tier, it is the wrong
   design for us.
6. **Cost is tracked in CI** like precision, in [`docs/cost.md`](../cost.md), measured
   rather than estimated.

## Options considered

**Pay for a frontier model on the whole corpus.** Best extraction quality, and it is
what a funded team would do. Rejected: no budget, and it creates the iteration trap above.

**Frontier model on a sample, local model on the rest.** Attractive, and rejected for a
subtler reason — it makes precision a function of which model happened to see a document,
so the golden-set number stops describing the system. If we ever do this, the model
version must be a column on every edge and reported separately.

**Pure rules, no LLM at all.** Cheapest, and genuinely tempting given that a zero-cost
filter already surfaced Lam Research and Applied Materials from Ichor's filing. Rejected
because the hard part is not finding the name, it is deciding whether the sentence asserts
a dependency, a competitor relationship, a past relationship, or a hypothetical one. Our
own measurement showed the false-positive class is competitor lists, which rules cannot
separate from customer lists without understanding the sentence.

## Consequences

**Good.** Re-extraction is an overnight job — about 5,000 model calls for the full Phase 1
corpus, under an hour for the 42-company pilot. The prompt can change weekly. Cost per
document is a CI metric from day one, which is a thing very few student projects and not
all companies can say. And "we built it to run at zero marginal cost, here is the measured
compression" is a stronger engineering story than "we spent money on a big model".

**Bad, and accepted.** A local 8B model extracts worse than a frontier model, so our
precision ceiling is lower than it could be, and we should say so rather than pretend the
constraint was free. Schema-forced output is less reliable on small models, so the retry
rate is a real number we have not measured yet. Wall-clock time replaces money as the
scarce resource, which means a bad prompt costs a night rather than a rupee — cheaper, but
not free, and it puts a hard ceiling on how many iterations fit in twenty weeks.

**Also accepted.** Running extraction on team laptops means the corpus lives on five
machines and reproducibility depends on discipline. Chunk-hash caching with a committed
cache manifest is the mitigation.

## What would reverse this

A budget. With ₹50,000 we would buy, in this order:

1. **A frontier model for stage two on the full corpus.** Roughly 9.2M tokens per full
   run; the precision gain on ambiguous sentences is the single biggest lever on product
   quality, and ambiguous sentences are exactly where competitor-versus-customer lives.
2. **Licensed earnings-call transcripts** — but only if redistribution terms permit showing
   the quote. If they do not, we still decline them at any price. See [`COMPLIANCE.md`](../../COMPLIANCE.md).
3. **A paid Postgres tier with point-in-time restore**, because losing the graph in week 17
   is a project-ending event and free tiers do not protect against it.

We would not buy: a hosted vector database, a paid map tile provider, or a graph database.
