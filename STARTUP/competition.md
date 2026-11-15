# Who else does this, and where we actually stand

Rule for this document: **no competitor numbers we have not verified.** We do not
know what Interos charges and we are not going to put a figure in a deck and be
asked where it came from. Where we are guessing, it says so.

## The categories

**1. Supply-chain risk platforms.** Interos, Resilinc, Everstream Analytics,
Exiger, Sphera. They map multi-tier supplier networks and sell risk monitoring,
largely to procurement and compliance teams in large enterprises.

- *How they get their data:* a mix of customer-supplied supplier lists, partner
  disclosure, trade and shipping records, and inference.
- *Where we differ:* for the most part you get an assertion, not a sentence. The
  relationship is asserted; you cannot click through to the document that proves
  it. Our entire design is the opposite trade.
- *Where they beat us, badly:* coverage. They have orders of magnitude more
  relationships than our 194. We should never pretend otherwise.

**2. Financial data terminals.** Bloomberg SPLC, FactSet Supply Chain
Relationships, S&P Capital IQ.

- *How they get their data:* substantially from the same place we do - disclosed
  customer and supplier relationships in filings - plus licensed and proprietary
  sources.
- *Where we differ:* they sell to people who already pay for a terminal, and the
  relationship data is one tab inside a very large product. The citation is
  usually present but the point-in-time discipline, and whether a backtest can
  trust it, is not something you can inspect.
- *Where they beat us:* everything to do with scale, history and distribution.

**3. Component and electronics supply data.** Z2Data, SiliconExpert, Supplyframe.
Deep in bills of materials and part-level sourcing. Adjacent to us rather than
competing: they are below the company level, we are at it.

**4. The actual status quo.** An analyst with a search box and a week. This is
what we really displace, and underestimating how good a determined human is at
this would be a mistake. What they cannot do is answer it in five milliseconds
across a whole portfolio at a specific past date.

## Where we are genuinely different

1. **Every edge carries its sentence, enforced in the schema.** `chunk_id` is
   `NOT NULL`. This is not a feature we added, it is a constraint the data
   cannot violate.

2. **We publish our precision, split by evidence type, and the sample we judged.**
   26 of 26 where a percentage is disclosed; 68.3% of a random 60 where it is
   not. We have not found a competitor who publishes anything comparable. That
   may be because they are larger and more cautious, not because they are worse.

3. **Point-in-time correctness is structural, not a filter.** One read path,
   `edges_as_of`. A 2021 event returns nothing from 2025 filings, visibly.

4. **Bottom-up by construction.** We do not ask the buyer, because the buyer has
   no reason to answer. We read the people who are legally required to tell.

## Where we are genuinely weak

- **Coverage.** 79 companies with edges. This is a capstone corpus, not a
  product.
- **One regulator.** EDGAR only, because it is free and machine-readable.
- **Recall unmeasured.** We do not know what fraction of disclosed relationships
  we capture.
- **No distribution.** No customers, no pilots, no design partners. We have not
  spoken to a single procurement or buy-side user.

## The honest positioning

We are not competing with Interos on coverage and we will lose that comparison
every time. The defensible claim is narrower and truer:

> For relationships that a public company has actually disclosed, Atlas gives
> you the relationship, the sentence that states it, the date it became public,
> and a measured precision for the class of evidence it came from.

The customer for that is not the procurement manager who wants a complete
network map. It is anyone who must *defend* a conclusion - a risk committee, an
auditor, a regulator-facing analyst, a researcher who needs a backtest that
survives scrutiny.

## What would change this assessment

- A real conversation with anyone in category 1's customer base. We have had
  zero, and everything above is desk research.
- A measured recall number. If recall is very low, the "defensible subset"
  positioning gets much harder.
- Any competitor publishing a precision figure, which would remove our clearest
  differentiator.

## Needs verification before this goes in any deck

- Pricing for any named product above.
- Market size for supply-chain risk software.
- Whether Bloomberg SPLC exposes point-in-time relationship history.
- Whether any category 1 vendor publishes extraction precision.
