# Problem statement

> Working codename: **Atlas**. The real name is chosen at the end. The product name lives
> in one constant in `packages/shared` and one environment variable, and appears nowhere
> else in hardcoded form, so renaming is two edits.

> **Supersedes the digital-twin framing of 26–27 August 2026.** That framing is not
> deleted — it is recorded, with the reasoning that moved us, in [`../SUPERSEDED.md`](../SUPERSEDED.md),
> and its customer-facing half survives as a Phase 5 feature. Read that file before
> arguing for the old version.

## The one-sentence version

When something happens in the world — a port closes, a plant burns, a country restricts
an export — the companies hit first are obvious and the companies hit third are not.
Atlas builds the chain of who depends on whom from what thousands of companies have
already said in public, then shows you the names you would never have thought to check,
with the exact sentence that proves each one.

## The problem with the obvious approach

The natural way to build this is to read large companies' filings and extract their
suppliers. It does not work, and it fails quietly rather than loudly.

Supplier identities are competitively sensitive. A large company's annual filing says
"certain suppliers," "a limited number of vendors," "a facility located in Asia." Build
top-down from large caps and you get a sparse graph of hedged legal language, four months
in, after the pipeline is already built. That is the single most likely way this project
dies.

## The inversion that fixes it

**Large companies hide their suppliers. Small suppliers advertise their large customers.**

A marquee customer is a small company's primary credential, so it appears in their annual
report, their investor deck, their website and their press releases. Accounting rules push
the same way: a customer representing 10% or more of revenue must be disclosed. The edge
you cannot get from the buyer, you get free from the seller.

So Atlas builds the graph **bottom-up, from the smaller side**, and treats extraction from
large-cap filings as corroboration rather than the primary source.

**This is not a theory.** A zero-cost keyword-and-gazetteer pass over ten real
semiconductor 10-Ks surfaced Lam Research and Applied Materials six times each in Ichor
Holdings' filing, and the same pair in Ultra Clean Holdings' — with no model involved
([`cost.md`](cost.md)). And the mechanism is mechanical, not manual: EDGAR full-text
search run against a large buyer's name returns *the filings of the smaller companies who
named them*. The thesis is one free API call.

## The value is the non-obvious name

Nobody needs to be told that chip equipment makers are exposed to a Taiwan Strait
disruption. Any analyst already has the first-order names. The entire product value sits
in the mid-cap three hops out that nobody thought to check, with a citation proving the
link.

Every screen, every ranking and every metric is designed around surfacing the non-obvious,
not around being comprehensive. `is_surprising` is a column in the database and a visual
distinction in the UI, because it is the argument.

## Slow layer, fast layer

Filings change quarterly and give us **structure** — who depends on whom. News, port
notices and shipping data change hourly and give us **state** — what is happening now.

Keeping these as two explicitly separate layers is the answer to "isn't your data stale?"
The structure being months old is fine, because dependencies genuinely move slowly. The
state is live.

## The constraints that are the architecture

1. **Every edge carries its evidence.** Document, section, character offsets, exact
   sentence. `dependency_edge.chunk_id` is `NOT NULL` from the first migration. If we
   cannot cite it, we do not assert it.
2. **The model extracts and explains. It never scores.** It reads a sentence and reports
   what that sentence says, with the span. Confidence, exposure weight and impact are
   computed afterwards by deterministic, version-controlled, unit-tested code.
3. **The graph knows what it knew and when.** Every edge has `valid_from` (the filing's
   publication date, never the period it covers) and `valid_to`. Every read goes through
   `edges_as_of`. The backtest harness is physically unable to see an edge published after
   the event it is scoring.
4. **Zero marginal cost.** A full re-extraction is an overnight job, not a budget line,
   so the prompt can change weekly. See [`adr/0001-building-at-zero-marginal-cost.md`](adr/0001-building-at-zero-marginal-cost.md).

## Who this is for

Not traders. Not retail investors. The user is somebody accountable for a dependency they
did not choose:

- **Procurement and supply-chain risk** at a mid-market manufacturer — needs tier-2 and
  tier-3 visibility they cannot get from their own records.
- **Credit teams** at lenders doing supply-chain or trade finance — needs disclosed
  dependence as an underwriting input, with provenance.
- **Trade-credit insurers** — needs correlated exposure across a book: one event, many policies.
- **Smaller research shops** without a terminal — needs cited, non-obvious names.

Biased deliberately toward buyers who do **not** already have a Bloomberg terminal.

## Three surfaces

- **Live** — map plus ranked side panel, non-obvious names flagged.
- **Replay** — scrub a past disruption, then reveal who actually reported an impact the
  following quarter.
- **Simulation** — define a shock, run it forward, get a cited impact table and a brief.

## The line we do not cross

We ship exposure data and cited research. Never a recommendation. No buy/sell, no target
prices, no portfolio advice. The reasoning, including why this is a legal question and not
a stylistic one, is in [`../COMPLIANCE.md`](../COMPLIANCE.md).

## How we know it worked

- **Surprise, at acceptable precision.** Of the companies we surface for an event, what
  share would the user not have listed themselves — and of those, what share hold up when
  checked? A system that returns only obvious names can be 100% accurate and worthless.
- Extraction precision and recall against the golden set, measured in CI on every change.
- A backtest that provably cannot see the future, with the test written before the harness.
- Share of edges with a named counterparty rather than an inferred one.
- Cost per document, tracked in CI.

## What we have deliberately not built

Revenue-impact estimates. We can say a company disclosed dependence on a disrupted
counterparty and show the sentence. We cannot say what it costs them, and a number we
cannot defend is worse than no number. Stopping here is a product decision, not a gap.
