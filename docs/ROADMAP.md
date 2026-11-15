# Roadmap

Five people, ~20 weeks, part-time alongside coursework. **Every phase ends in something
that runs and can be demoed.** No phase ends with "the backend is nearly done."

> Supersedes the event-first roadmap of 26–27 August 2026. See [`../SUPERSEDED.md`](../SUPERSEDED.md).

---

## Phase 0 — Foundations (weeks 1–2) · **largely done**

The boring fortnight that decides whether the other eighteen work.

- [x] Monorepo, docs in git
- [x] `infra/docker-compose.yml` — Postgres 16 + PostGIS + Redis
- [x] `0001_initial_schema.sql` — 25 tables, citation and tenancy enforced in the schema
- [x] `packages/shared/src/api.ts` — API contract agreed before either side builds
- [x] `Makefile` — one command runs anything
- [x] Reference layer loaded: 2,002 US companies, 9,635 aliases, 10,443-name gazetteer
- [ ] GitHub org, branch protection, PR template, CI green on an empty PR
- [ ] gitleaks as pre-commit hook **and** CI check, before any secret can land
- [ ] Deploy hello-world web + api to production URLs. **Day 10, not month 5.**
- [ ] Figma file, design direction signed at the bottom of `DESIGN.md`
- [ ] Five names against five domains in `TEAM/ownership.md`

**Demo:** `make dev` brings up the stack and loads 2,000 companies on any teammate's laptop.

---

## Phase 1 — Documents in, chunks out (weeks 3–6)

- **Week 3 is the validation gate** ([`validation-week3.md`](validation-week3.md)) and it
  comes first. 40 documents, two annotators each, pre-registered decision rules. Nobody
  reads a document until the sample is frozen in git.
- EDGAR adapter: fetch, hash, store, respect the rate limit, never re-fetch unchanged
- Segmenter: Item boundaries. Measured at 10/10 on real 10-Ks; make it hold at 200
- Chunker with character offsets preserved end to end
- Stage one: lexicon + gazetteer + classifier trained on the week-3 annotations
- Stage two: schema-forced extraction, cached by chunk hash
- Golden set wired into CI with precision and recall printed on every PR

**Demo:** point at a ticker, watch a filing become cited claims, with the spans highlighted.

**Gate:** if small/mid-cap named yield is under 30%, the sector is wrong. Re-run on auto
components before building further. One week budgeted.

---

## Phase 2 — The graph (weeks 7–10)

- Entity resolution against the alias table; GLEIF parent relationships if terms permit
- Review queue for ambiguous merges — a human decides, and the decision is dated
- Claims become edges only when named and resolved; everything else stays a claim
- Deterministic scoring: confidence, weight, substitutability. Versioned and unit-tested
- Bitemporal queries live: `edges_as_of` is the only read path
- **The test that proves the backtest cannot see the future, written before the harness**

**Demo:** the same query at two `as_of` dates returning two different graphs.

---

## Phase 3 — Events and propagation (weeks 11–14)

- Event ingest: dedupe, geocode, classify, severity-score
- Promotion rule: `unconfirmed` events never drive a user-visible claim
- Propagation: bounded three-hop walk, deterministic, explainable, property-tested
- Exposure precomputed — never calculated on a page load
- **The surprise metric instrumented and on the dashboard the team looks at weekly**

**Demo:** a real event propagating to a ranked, cited exposure list in under 200ms.

---

## Phase 4 — Replay and simulation (weeks 15–17)

- Timeline scrubber with the point-in-time boundary drawn on screen
- Replay a real disruption, then reveal who actually reported an impact next quarter
- Forward simulation with a cited impact table and a written brief
- Backtest harness in CI against the 20-event benchmark

**Demo:** Renesas Naka 2021 replayed against the graph as it stood that morning.

---

## Phase 5 — Hardening and release (weeks 18–20)

- Auth, tenancy proven by test, not by inspection
- The three alerts that would page someone: ingest stopped, precision dropped, read path over budget
- Runbook, structured logs, cost-per-document in CI
- **Bring your own tier-1** if and only if graph density supports it
- Landing page, founder note, accuracy write-up, viva deck

**Demo:** somebody who is not on the team, using it, on camera.

---

## Parallel track — the other five markets

India, UK, Australia, Canada, Germany enter the **reference layer** as they are collected.
They improve US extraction immediately, because the gazetteer is what filters chunks and a
US filing naming TSMC or Infineon is currently a miss. They do **not** enter the evidence
layer until a market has a verified source row and a measured yield. Breadth is cheap;
depth is not.

---

## Risk register

| Risk | Likelihood | What we do about it |
|---|---|---|
| **Sparse graph** | **High** | The inversion. Measured in week 3 before anything is built on it. |
| Named edges are all above the 10% threshold, so nothing is surprising | Medium | Gate G6 measures it in week 3. Weight Phase 2 toward narrative mentions. |
| Competitor lists extracted as dependencies | **High — already observed** | `competitor` is a forced choice in the schema and a mandatory annotation axis. |
| Wrong entity merge discovered late | Medium | Merges are dated and reversible. Review queue from Phase 2. |
| Source changes its HTML | Medium | Adapter per source, hash every fetch, fail loudly. |
| Nobody will pay | **Unknown — untested** | Zero practitioner conversations so far. Currently our weakest line. |
| Team member goes dark near exams | High | No solo critical paths. Friday demo every week. |
| Scope creep back toward the digital twin | Medium | Test: if a feature needs data only the customer has, it is out. |
