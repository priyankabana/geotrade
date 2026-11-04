# Team of 5 — ownership, tooling, rhythm

## Ownership areas

These are **areas of ownership, not silos**. Everyone writes code across the repo;
the owner is who decides, who reviews, and who is accountable at the demo.

| # | Area | Owns | Main surface |
|---|---|---|---|
| 1 | **Data & ingestion** | GDELT pipeline, source adapters, dedupe, geocoding, event taxonomy | `apps/ingest` |
| 2 | **Backend & graph** | API, schema, PostGIS models, propagation engine | `apps/api` |
| 3 | **Intelligence** | Event classification, impact scoring, backtest harness, LLM explanation layer | `apps/api/ml` |
| 4 | **Frontend & viz** | Globe, map, dashboard, replay UI, design system | `apps/web` |
| 5 | **Product & platform** | Onboarding, auth, billing, CI/CD, deploys — **plus customer discovery** | `infra`, cross-cutting |

Role 5 is the one teams get wrong. It is not "the leftover role" — it is the person
who makes sure the thing ships and that someone outside the team actually wants it.
Give it to whoever is most stubborn about finishing.

## Tooling — pick these, stop debating

**GitHub organisation, one private repo.** Free. Create the org rather than putting
the repo on one person's account: it survives the project, and nobody's grade depends
on one person's login.

**GitHub Projects** for the board. Not Trello, not Jira. It lives beside the code and
links issues to PRs automatically, so the board updates itself when work merges.

**Discord** for communication. Channels:

```
#announcements   decisions only, low traffic, everyone reads
#standup         daily async post, 3 lines each
#eng-backend     #eng-frontend     #eng-data
#design          screenshots, critique, references
#customers       every call, every quote, every rejection
#random
🔊 pair-room     always-on voice for working sessions
```

Wire GitHub notifications into a `#github` channel so merges and CI failures land
where people already are.

**Docs live in `docs/` in the repo.** Not Notion, not Google Docs. Specs get reviewed
in PRs alongside the code they describe, and they are versioned with it.

**Figma** for design, one shared file, before anything is built in code.

## Rhythm

| When | What | Length |
|---|---|---|
| Mon | Sprint planning — pick issues, assign, size | 45 min |
| Daily | Async standup in `#standup`: yesterday / today / blocked | 3 lines |
| Wed | Unblock call — only if someone is stuck | 20 min |
| Fri | **Demo.** Everyone shows something running. Not slides | 30 min |
| Fri | Retro — what to keep, what to change | 15 min |

Two-week sprints. The Friday demo is the forcing function: a thing that runs, every
single week, from week one. Teams that skip this discover in month four that three
people's work does not connect.

## Git workflow

```
main            protected, always deployable
└── feat/globe-replay-scrubber      one branch per issue
    fix/dedupe-collision
    chore/ci-cache
```

- Branch from `main`, name it `type/short-description`
- Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`
- Open a **draft PR on day one** of the branch, not when finished — reviewers see
  direction early, and it kills the week-long surprise PR
- One approving review to merge. Squash merge, so `main` history stays readable
- Link the issue: `Closes #47`

**Branch protection settings** (Settings → Branches → add rule on `main`):
require a PR, require 1 approval, require CI to pass, no force pushes.

## The rules that actually prevent group-project failure

1. **Nobody works alone on a critical path for more than 3 days.** Rotate pairing.
2. **Integrate weekly, not at the end.** The Friday demo enforces this.
3. **Write the interface first.** Agree the API contract in `packages/shared` before
   frontend and backend go build against imagined shapes.
4. **One person cannot be the only one who can deploy.** Document it, and have a
   second person do a deploy in week 2 to prove the doc works.
5. **Log every customer conversation in `#customers`**, including the ones that go
   badly. Those are the useful ones.
