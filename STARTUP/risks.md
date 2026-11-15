# What kills this

Ranked by how likely they are to actually happen, not by how dramatic they sound.

---

## 1. Coverage never reaches usefulness

**The risk.** 194 relationships is a demonstration. A buyer needs the companies
*they* care about to be in the graph, and the chance that a given portfolio
intersects our 79 companies is small.

**Why it is the top risk.** Every other problem is solvable by work. This one is
solvable by work too, but it is a lot of work, and until it is done nobody can
use the product for anything real.

**What reduces it.** Ingestion is already parallel and rate-limited against
EDGAR; the corpus is bounded by time, not by method. Going from 225 filings to
5,000 is an overnight run, not a redesign. The honest unknown is whether
relationship density grows proportionally.

**Leading indicator.** Relationships per filing ingested. Right now it is about
0.9. If that holds, 5,000 filings is roughly 4,000 relationships.

---

## 2. Precision is not good enough to act on

**The risk.** 68.3% on narrative edges means roughly one in three of those is
wrong. For a user making a decision, that may be worse than nothing, because a
wrong edge presented with a citation is *more* convincing than a wrong edge
presented bare.

**What reduces it.** The product leads with the concentration tier, which
measured 26 of 26. The UI labels the tiers differently. And stage two is
designed to be swapped for a model, which is where the remaining failures -
entity ambiguity, competitor lists, acquired brands - have to be solved.

**What would make this fatal.** If a model-backed stage two does not materially
beat 68%, the method has a ceiling we did not expect, and the narrative tier
should probably be withheld from users entirely.

---

## 3. We never talk to a user

**The risk.** Five engineering students build a technically careful system that
nobody wants, and find out after the capstone ends.

**Status: this risk is currently live.** We have had zero conversations with
anyone in a procurement, risk or buy-side role. Everything we believe about
demand is inference from the structure of the problem.

**What reduces it.** Ten conversations. Not a survey, not a landing page. The
question to ask is not "would you use this" but "tell me about the last time you
needed to know who else was exposed, and what you actually did".

---

## 4. Legal and licensing

**The risk.** We redistribute sentences from filings and identifiers from market
data. Filings are public domain. Licensed identifiers are not.

**What reduces it.** CUSIP and SEDOL are withheld at the API layer. We declined
licensed transcript data specifically because its terms forbade republishing the
source sentence. GICS was avoided for the same reason. These decisions are
recorded in `docs/sources.md` and `COMPLIANCE.md`.

**Residual.** We are students, not lawyers, and we have not had any of this
reviewed. Before anything commercial, it needs to be.

---

## 5. Someone trades on a wrong edge

**The risk.** A user reads an edge, acts on it, loses money, and the edge was one
of our 32%.

**What reduces it.** We make no recommendations anywhere. We publish precision
alongside the data. The two evidence tiers are visually distinct. Every edge
carries the sentence so the user can check it in five seconds.

**What does not reduce it.** A disclaimer. If the product is used this way, a
disclaimer is decoration.

---

## 6. The regulator changes format

**The risk.** EDGAR changes its document structure and ingestion breaks.

**Why it is low.** It breaks loudly, not silently, and segmentation is isolated
in `scripts/ingest.py`. It is a maintenance cost, not an existential one.

---

## 7. A large incumbent does this properly

**The risk.** Bloomberg or FactSet decides citation-first relationship data is
worth building well, and they have the corpus and the distribution.

**Honest assessment.** If this becomes valuable, this happens. The defence is
not technical - it is being the system that researchers and auditors already
trust and cite, which is a position built over years, not a moat we have now.

---

## 8. The team dissolves at graduation

**The risk.** Five people with five job offers in different cities.

**What reduces it.** Nothing we can engineer. What we can do is make the repo
survive the team: documented decisions, `make` targets that work on a cold
machine, an evaluation anyone can re-run, and ownership written down.

---

## The one-line summary

The thing most likely to kill Atlas is not that it is wrong. It is that it is
**too small and talks to nobody**. Both are fixed by work we have not done yet,
and neither is fixed by more code.
