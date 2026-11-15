# Who owns what

Group G27, Final Year Computer Engineering, Vishwakarma University, Pune.
Internal guide: Prof. Tareek Pattewar.

These are **areas of ownership, not silos.** Everyone reads and writes code
across the repo. The owner is the person who decides, who reviews, and who
answers for that area at the review and the viva.

| Owner | Area | Surfaces they answer for |
|---|---|---|
| **Priyanka Bana** | Evidence layer and extraction | `scripts/extract.py`, `scripts/df_gazetteer.py`, `scripts/fix_gazetteer.py`, `eval/` |
| **Krish Oswal** | Backend, schema and graph | `apps/api/`, `infra/migrations/`, `scripts/propagate.py` |
| **Ishanya Bhumkar** | Ingestion and the corpus | `scripts/ingest.py`, `scripts/link_cik.py`, `scripts/load_csv.py`, `apps/ingest/` |
| **Anushka Pallod** | Frontend and visualisation | `apps/web/`, `packages/shared/` |
| **Ayush Gawali** | Platform, demo and documentation | `infra/`, `Makefile`, `scripts/record_demo.py`, `docs/`, `TEAM/` |

## What each owner must be able to do unaided

Not "has read about". Can do, at a terminal, while someone watches.

**Evidence layer — Priyanka.** Explain why the extractor preserves case.
Explain the difference between the concentration tier and the narrative tier and
quote the measured precision of each. Draw a fresh sample and judge ten
relationships live. Name three failure classes we have not fixed and say why.

**Backend and graph — Krish.** Explain why `dependency_edge.chunk_id` is
`NOT NULL` and what that buys. Explain `edges_as_of()` and why there is exactly
one read path. Explain why propagation stops at three hops. Show that a 2021
event returns nothing and explain why that is correct.

**Ingestion — Ishanya.** Explain how a filing becomes chunks: fetch, Item
segmentation, 4800/600 chunking. Explain why chunks overlap. Explain the rate
limit we hold ourselves to against EDGAR and why we hold it. Explain why we
declined licensed transcript data.

**Frontend — Anushka.** Explain why the two evidence tiers are styled
differently and point at the measured numbers behind that choice. Click from an
edge on screen through to the sentence on the SEC's own servers. Explain why a
percentage is never shown without its basis.

**Platform and demo — Ayush.** Bring the whole system up from a cold machine
with `make`. Explain what each pipeline stage does and roughly how long it
takes. Run the demo end to end without narration and without it breaking.

## The rule that matters most

**Nobody presents a number they cannot point at.** Every figure we state in a
review, a report or the viva traces to `eval/README.md` or to a script in this
repo. If you are about to say a number and you cannot name its source, say
"I don't have that measured" instead. That answer costs us nothing. A number we
cannot defend costs us the viva.

## Cross-cutting rules

- Anyone may open a PR against any area. The owner reviews it.
- The owner does not get to block work in their area indefinitely; if a review
  stalls more than a day, it goes to the group.
- Changes to the schema, to the citation guarantee, or to the scorer are group
  decisions, not owner decisions. Those three are the project's integrity.
- Documentation changes ship in the same PR as the code they describe.
