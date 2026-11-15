# Compliance, in plain words

Written to be read by someone who is not a lawyer, because the people who need to follow
it are five engineering students. Where something is genuinely uncertain it says so
rather than sounding confident.

---

## 1. We publish data and research, not recommendations

**The line: we tell you who is exposed and show you the sentence that proves it. We never
tell you what to do about it.**

No buy, no sell, no hold. No target prices. No portfolio construction. No "this stock will
fall." An exposure score is a measurement of disclosed dependence, not a view on a security.

### Why this matters, kept verbatim from the original problem statement

> **Regulation.** Publishing buy/sell recommendations on securities in India without
> SEBI registration as a Research Analyst is illegal. A student project that takes money
> for trading signals is a real legal problem, not a technicality.
>
> **No buyer.** Retail traders do not pay for signals, and they churn in weeks. There is
> no startup underneath it.
>
> **Unfalsifiable.** "Geopolitics predicts markets" cannot be validated honestly in a
> two-semester window. An examiner is right to be sceptical, and we would have no defence.

That reasoning was written for a different product and it survives the change intact. It
is the clearest statement in the repo of why we sit where we sit.

### What would change if we crossed the line

Printing a price target, or a rating, or "reduce exposure to this name," would likely put
us inside SEBI's Research Analyst regulations — registration, qualifications, compliance
officer, record-keeping, disclosure of interest. `[verify: SEBI (Research Analysts)
Regulations 2014 and subsequent amendments — read the actual text before relying on this.
Owner: product and discovery. Due: week 4.]`

The practical rule for the team: **if a sentence in the UI could be read as advice about
a security, it does not ship.** "Eleven companies in your coverage disclose dependence on
this supplier" is a fact. "Eleven companies look vulnerable" is a nudge. The second one
is out, and the difference is not pedantry.

---

## 2. Public sources only

Everything we use is published and available to anyone. Filings, transcripts companies
put on their own websites, investor decks, press releases, port authority notices,
government gazettes, open reference data.

**We never touch material non-public information.** No expert networks, no channel checks,
no paying people for what their employer knows, no alternative data whose provenance we
cannot explain. This is not caution about a grey area — it is a category we stay out of
entirely.

This is a feature we advertise rather than a limitation we apologise for. A procurement
team at a listed company can use Atlas without their compliance officer having to think
about it. Several well-funded products in this space cannot say that.

The citation architecture is also what makes the claim checkable. Every assertion clicks
through to a document anyone could have read. "Public-only" is not a promise you have to
take on trust; it is visible in every row of output.

### A source we declined, and why

We were offered a route to licensed earnings-call transcripts and turned it down.

Not on price — we would have declined at ₹0. The redistribution terms on licensed
transcript feeds would have let us *read* the transcript and not *show* the sentence.
For us that is worse than having no transcripts at all, because it would mean asserting
edges we could not evidence, in a product whose entire argument is that every edge is
evidenced.

**We declined a data source because its terms were incompatible with our citation
guarantee.** That sentence is the shortest accurate description of what this product is.

---

## 3. Data terms, per source

One row per source in [`docs/sources.md`](docs/sources.md), before any adapter is written:
licence, rate limit, required user-agent, redistribute or display-only, who verified it
and when.

Three rules that are easy to state and easy to break:

- **A human reads the terms.** An assistant's summary of a licence is a lead, not evidence.
- **`unclear` means rejected.** Not "used carefully."
- **Per-site, not per-category.** Forty-two company IR sites are forty-two rows. "IR sites
  are generally fine" is not a finding about any particular site.

We declare a real User-Agent with a contact address, we stay under published rate limits,
and we cache aggressively so we fetch each document once. Being a well-behaved client is
both the polite thing and the thing that keeps access.

---

## 4. Clean room

**Nothing belonging to any employer enters this repo.** No exported databases, no
credentials, no licensed vendor data, no code written on company time, no internal
documents.

What carries across is knowledge: which sources exist, how they behave, which endpoints
matter, where the quirks are. That travels with a person and is theirs. Bytes are not.

When a source arrives through someone's professional knowledge, it enters `sources.md` as
a `candidate` and goes through the identical gate. No shortcuts for sources we happen to
trust.

The honest answer at the viva, if asked: we studied the landscape, including products
some of us know professionally, and then built our own thing from public data. That is
normal practice and there is nothing to manage about it.

---

## 5. Personal data

Named executives and analysts appear throughout our corpus. An earnings call transcript is
full of people's names, job titles and spoken words.

What we store: names and roles **only** where they appear in the cited span, because
removing them would break the citation. What we do not store: contact details, anything
inferred about a person, any profile of an individual assembled across documents.

We never build a person-node in the graph. Nodes are companies, places and commodities.
This is a deliberate design constraint and not an accident of scope — the moment a person
becomes an entity with edges, we are in a different regulatory world.

`[verify: India's Digital Personal Data Protection Act 2023 — what obligations attach to
processing personal data that is already lawfully published, whether our use qualifies for
any publicly-available-data provision, and what retention and deletion duties apply.
Owner: platform. Due: week 6. Do not rely on this section until that is done.]`

---

## 6. Tenant isolation

Row-level security in the first migration, and an isolation test in the same pull request.
Not the migration after, and not a test written later.

One customer seeing another customer's coverage universe, watchlist or uploaded supplier
list is the failure that ends a company. It is also trivially preventable if the constraint
exists before there is any data to leak, and nearly impossible to retrofit with confidence
once there is.

The test asserts that a query authenticated as tenant A returns zero rows belonging to
tenant B, run against every table carrying a `tenant_id`, and fails the build if a new
table appears without one.

---

## 7. If we are wrong about a company

We will assert, in public, that Company A depends on Company B. Sometimes we will be wrong
— a misparsed sentence, a bad entity merge, a supplier relationship that ended two years
ago. Somebody might make a decision on it.

**Why the citation is a legal shield as well as a product feature.** We do not assert
"A depends on B" as our own opinion. We assert "on 2025-02-21, in this filing, at these
character offsets, A said this sentence" — and we show the sentence. That is a statement
about a public document, verifiable by the reader, which is a very different kind of claim
from an opinion we formed. When the underlying sentence says what we say it says, the
worst case is that the *company* was wrong, and the reader can see exactly what they said.

This is also why the LLM is not allowed to paraphrase into an edge. A paraphrase is our
words. A span is theirs.

**Corrections process.**

1. Anyone can report an edge as wrong, from the UI, with one click on the citation.
2. It lands in the review queue with the document, the span and the reporter's reason.
3. A human checks the span against the source. Median target: two working days.
4. If wrong, the edge gets `valid_to` set and a `correction` row recording what was wrong
   and when we learned it. **We do not delete it.** Deleting would rewrite history and
   break every point-in-time query that ran before the correction.
5. Corrections are counted and published. A correction rate we report ourselves is
   credibility; one somebody else discovers is not.

Every user-facing exposure claim carries the same line: *this reflects what companies have
publicly disclosed, may be incomplete, and is not investment advice.* Not buried in a
footer — next to the number.
