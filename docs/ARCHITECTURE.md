# Architecture & stack

Decisions are made, not surveyed. Where a choice was close, the reason is noted so a
future you can revisit it with context.

## System shape

```
  Public event sources                  Customer's own reality
  ────────────────────                  ──────────────────────
  GDELT (global events, free)           supplier list (CSV / form)
  Port + vessel status                  lanes: origin → destination
  Tariff / sanctions notices            SKUs, input commodities
  Weather & cyclone advisories          contract dates, volumes
  Commodity spot prices                            │
          │                                        │
          ▼                                        ▼
  ┌───────────────────┐              ┌──────────────────────────┐
  │  ingest workers   │              │   customer graph builder │
  │  dedupe, geocode, │              │   (their private twin)   │
  │  classify, score  │              └──────────────┬───────────┘
  └─────────┬─────────┘                             │
            └───────────────┬─────────────────────-─┘
                            ▼
              ┌───────────────────────────┐
              │   propagation engine      │  event → lane → supplier →
              │   (weighted graph walk)   │  SKU → cost/delay estimate
              └─────────────┬─────────────┘
                            ▼
              ┌───────────────────────────┐
              │  FastAPI  +  Postgres     │
              │  PostGIS · Redis · queue  │
              └─────────────┬─────────────┘
                            ▼
              ┌───────────────────────────┐
              │  React SPA                │
              │  globe · map · dashboard  │
              │  replay · simulator       │
              └───────────────────────────┘
```

## Stack

| Layer | Choice | Why this one |
|---|---|---|
| Frontend | React + TypeScript + Vite | Team knows it; Vite is fast; TS catches the class of bug that kills group projects |
| 3D globe | `react-globe.gl` (three.js) | The look we want, and it is MIT licensed — we use the library ourselves, not anyone's build of it |
| 2D map | MapLibre GL + a free tile source | Open source, no Mapbox billing surprise |
| Charts | Visx or ECharts | Avoid the generic dashboard look; both allow real custom design |
| State/data | TanStack Query | Caching, refetch, stale-while-revalidate for free |
| Backend | FastAPI (Python) | Same language as the ML/data work — one language across 3 of the 5 workstreams |
| DB | Postgres + **PostGIS** | Geospatial is a first-class need: ports, lanes, distances, intersections |
| Cache/queue | Redis + RQ or Celery | Ingest runs on a schedule; API must never block on it |
| ML | scikit-learn first, PyTorch only if needed | Start with gradient boosting on tabular features. Resist deep learning until a simple model is beaten |
| LLM | Claude API (Sonnet) | Narrative explanation + mitigation playbooks. **Explanation layer, never the scoring layer** |
| Auth | Clerk or Supabase Auth | Do not hand-roll auth. It is a solved problem and a great way to lose two weeks |
| Hosting | Vercel (web) · Fly.io or Render (api) · Neon (Postgres) | All have real free tiers |
| CI | GitHub Actions | Lint + typecheck + test on every PR |

### The one non-obvious call

**The LLM does not compute the score.** It explains a score that deterministic code
produced. If an examiner asks "how does it decide," the answer must be a documented
algorithm, not "we asked an AI." Models that reason in a black box are unmarkable and
unsellable. Use Claude for the *sentence*, not the *number*.

## Data sources — start free

- **GDELT** — global event database, updates every 15 minutes, free, geocoded. This
  is the unlock that makes the project feasible with no data budget. Start here.
- **Port & vessel status** — AIS-derived feeds have limited free tiers; begin with
  scheduled scrapes of public port authority notices for a shortlist of ~30 ports.
- **Tariff / sanctions** — official gazette + government notification feeds.
- **Weather** — open forecast APIs for cyclone and storm advisories on lanes.
- **Commodity prices** — free-tier market data for input cost exposure only.

Every source gets an adapter behind one interface, so swapping a paid provider in
later is a one-file change.

## Repo layout — one monorepo

Five people, one repo. Polyrepo means version skew, five sets of CI, and a week lost
to plumbing.

```
atlas/
├── apps/
│   ├── web/          React SPA
│   ├── api/          FastAPI service
│   └── ingest/       scheduled workers (own deploy, shared models)
├── packages/
│   └── shared/       types + schemas shared web↔api
├── infra/            docker-compose for local dev, deploy config
├── docs/             this folder — specs live in git, not in chat
└── .github/          CI, PR template, issue templates
```

`docker-compose up` in `infra/` must give any teammate Postgres + Redis + API + web
running locally. Getting this working in week 1 pays for itself ten times over.

## Non-negotiables

1. **`main` is always deployable.** Branch protection on. No direct pushes.
2. **Every PR needs one approving review.** One, not two — five students need velocity.
3. **Secrets never enter git.** `.env.example` is committed; `.env` never is.
4. **Migrations are code.** Alembic from day one. No hand-edited production schemas.
5. **If it is not in an issue, it does not exist.** Verbal agreements evaporate.
