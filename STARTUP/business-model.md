# Business model

Early and incomplete. Written now because one part of it — **bring your own tier-1** — is
the commercial answer to "why would anyone pay," and it needs to be on the record before
we build, even though it ships last.

---

## Bring your own tier-1

**The feature, in one sentence:** the customer uploads their supplier list, we resolve
those names against the public graph, and we hand back the two hops they could not have
typed.

This is the delivery surface the original digital-twin framing was reaching for, correctly
positioned. The twin was never the data asset — see [`../SUPERSEDED.md`](../SUPERSEDED.md).

### Why it is the commercial answer

A procurement manager who uploads forty suppliers into a risk tool learns nothing, because
they typed those forty names in themselves. They already know their tier-1. That is the
definition of tier-1.

What they cannot type in — what is genuinely absent from their own records, their ERP and
their head — is who their suppliers depend on. A fire at a plant they have never heard of,
two hops away, arrives as a delivery failure with no warning and no explanation. That is
the actual experience of supply-chain disruption for a mid-market manufacturer, and it is
the thing nobody sells them an answer to.

So the value exchange is precise:

| They give us | We give them |
|---|---|
| A list of names they already have | The hops they don't, with the sentence proving each one |

Everything else in the product is how we are able to do that: the extraction, the citation
enforcement, the point-in-time graph. This is the moment a customer experiences it.

### Why it ships last, not first

It needs the public graph to exist and to be dense. A resolution layer over a sparse graph
returns "we found nothing about your suppliers," which is the single worst first impression
available to us. **Phase 5 at the earliest, and only once the week-3 and Phase-2 density
numbers support it.**

### What it needs

- Entity resolution good enough to match a messy uploaded name — "Bharat Forge Ltd.",
  "BHARAT FORGE", "Bharat Forge Limited, Pune" — to a graph node. This is the hardest
  dependency and the reason it comes late.
- Tenant isolation, already required from the first migration. An uploaded supplier list
  is the most commercially sensitive thing a customer will ever give us.
- An honest empty state. "We have no coverage of 6 of your 40 suppliers" said clearly is
  worth more than a confident silence, and it is also a coverage-expansion signal.

### What it is not

Not a digital twin. We are not modelling their lanes, their POs, their SKUs or their
freight costs. We resolve names against a graph and return paths with citations. Scope
creep back toward the twin is the specific failure mode to watch for, and the test is
simple: **if a feature needs data only the customer has, it is out of scope.**

---

## Who pays

Bias toward buyers who do **not** already have a Bloomberg terminal, because those buyers
are not being served and are reachable by five students. Detail in `wedge.md`.

| Buyer | Their job | Why they'd pay |
|---|---|---|
| Mid-market procurement and supply-chain risk | Keep the line running | Tier-2 and tier-3 visibility they cannot get anywhere |
| Credit teams at lenders — supply-chain and trade finance | Decide whether a borrower is fragile | Disclosed dependence as an underwriting input, with provenance |
| Trade-credit insurers | Price the risk a buyer fails to pay | Correlated exposure across a book — one event, many policies |
| Smaller research shops | Produce notes without a terminal | Cited, non-obvious names |

---

## Three revenue paths, ranked

**1 — Seats, for procurement and credit teams.** Most likely. Small teams, 3–10 seats, a
recurring line item that already exists in their budget under "risk tools." Bring your own
tier-1 is the upgrade trigger.

**2 — API, for insurers and lenders.** Higher value per customer, longer sale, needs
reliability we will not have for a year. Exposure-as-a-field inside their own underwriting
model. Best long-term shape; wrong first shape.

**3 — Per-report research.** Fastest to first rupee and does not scale. Genuinely useful as
a discovery mechanism — writing a real report for a real buyer teaches us more about the
product than ten interviews — but it is a services business, not this one.

---

## Unit economics

The cost side is unusual and worth stating plainly: **marginal cost per customer is
approximately zero**, because the graph is built once and served to everyone. See
[`../docs/cost.md`](../docs/cost.md) and [`../docs/adr/0001-building-at-zero-marginal-cost.md`](../docs/adr/0001-building-at-zero-marginal-cost.md).

| Line | Measured or assumed | Value |
|---|---|---|
| Full corpus re-extraction, 200 companies | `[M]` calls, `[E]` rate | ~4,960 model calls, ~9.2M tokens — one overnight run |
| Stage-two calls per document | `[M]` | 11.6 chunks × 1.15 retry ≈ 13 |
| Extraction cost per document at ₹0 | measured | ₹0 — local model, our own hardware |
| Incremental cost of customer number 2 | structural | ₹0 |
| Cost per document if we bought a frontier model | `[E]` | to be priced in `cost.md` before any ADR-0001 reversal |

**What has to be true for this to work**

1. The graph is dense enough that a typical uploaded supplier list resolves to real paths.
   Week 3 and Phase 2 test this. **This is the assumption everything else rests on.**
2. Surprising names hold up on inspection. Precision at the surprising end, specifically —
   surprising and wrong destroys trust faster than obvious and right builds it.
3. Somebody with a budget has this problem badly enough to sign something. **Untested.**
   Zero practitioner conversations so far, and that is currently the weakest line in
   `INTERVIEW/rubric.md`.

---

## Not yet written

Pricing levels · the free tier's shape and what it deliberately withholds · churn
assumptions · what we charge for the API · whether the per-report path is worth running
in parallel during Phase 3.

Owner: product and discovery. These need at least a few real conversations before the
numbers in them mean anything, and inventing them now would violate R7.
