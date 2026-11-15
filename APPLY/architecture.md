# Atlas — technical architecture on Google Cloud

Submitted with the Google AI Startup Buildathon application. Team G27, Pune.

## The shape

Two layers, kept apart on purpose.

**Reference layer — global, broad, cheap.** Every listed company we can identify:
canonical and historical names, exchange listings, international identifiers, industry
classification, geocoded headquarters. Loading a new market is a data job, not a
migration, because identifiers and listings are rows rather than columns.

**Evidence layer — narrow, deep, expensive.** Documents, text chunks with character
offsets, extracted claims, and cited dependency edges. This is where the models run and
where every cost sits.

Separating them is what makes the economics work: 23,020 companies cost almost nothing
to hold; extracting relationships from their filings is the part worth spending on.

## The pipeline

```
Cloud Scheduler ──▶ Pub/Sub ──▶ Cloud Storage        01  INGEST
                                   │                     filings, transcripts, news
                                   ▼
                            Document AI               02  PARSE
                                   │                     sections, tables, offsets
                                   ▼
                     Gemma on Cloud Run + gazetteer  03  FILTER   ◀── no paid tokens
                                   │                     removes ~85% of text
                                   ▼
                      Gemini on Vertex AI            04  EXTRACT
                                   │                     schema-forced, returns the span
                                   ▼
                  Vertex embeddings + pg_trgm         05  RESOLVE
                                   │                     mention → canonical company
                                   ▼
              AlloyDB for PostgreSQL + PostGIS        06  SERVE
                                                         graph, geospatial, point-in-time
```

Serving: Cloud Run services behind an API; exposure results precomputed so the read path
stays under 200 ms. BigQuery holds the corpus and the evaluation history. Maps Platform
does geocoding and backs the globe.

## Why the filter stage exists

Measured on ten real annual filings:

| Stage | Effect |
|---|---|
| Section targeting | removes **46%** of each document |
| Lexicon + gazetteer filter (no model) | removes a further **72%** of the remainder |
| **Reaches a language model** | **~15% of the original document** |

A frontier model across every listed company on earth is only affordable because of this
stage. Gemma runs it on our own Cloud Run instances; Gemini never sees the 85% that was
thrown away.

## Three invariants enforced in the schema

Rules that depend on everyone remembering them are not rules.

1. **No claim without a citation.** `dependency_edge.chunk_id` is `NOT NULL`. An uncited
   edge cannot be written, even by accident.
2. **The graph knows when it knew.** Every edge carries `valid_from` (the date the
   information became public, never the period it covers) and `valid_to`. Every read goes
   through one `edges_as_of(entity_ids, as_of)` function. There is no second path, so a
   backtest cannot see information published after the event it is scoring.
3. **Tenant isolation from migration one.** Row-level security on every tenant-scoped
   table, with the isolation test in the same pull request.

## The model never scores

Gemini reads a sentence and reports what that sentence says, with character offsets, and
writes the human explanation. Confidence, exposure weight and substitutability are
computed afterwards by version-controlled, unit-tested code.

This matters for three reasons. A regulator can be shown the algorithm. We can debug a
wrong answer. And a model upgrade cannot silently move every number in the product.

## How it scales

| Scale | What breaks | What we do |
|---|---|---|
| 23k companies (today) | nothing | single AlloyDB instance |
| 200k companies | extraction throughput | Cloud Run autoscaling on the Gemma filter; batch Gemini via Vertex |
| 1M+ documents/yr | corpus size and re-extraction cost | BigQuery for the corpus, extraction cached by chunk hash so only new text is re-read |
| Multi-region customers | read latency | precomputed exposure replicated regionally |

Adding a market is a data load. Adding a language is a Gemini prompt and an alias set.
Neither is a migration.

## What is already running

Postgres 16 with PostGIS, 25 tables, 23,020 companies, 82,751 aliases, 23,018 geocoded
headquarters. FastAPI read service at a 5 ms median. React and TypeScript client with a
WebGL globe and three operating modes. One-command local setup.

The Buildathon migration path is deliberate: AlloyDB is PostgreSQL, so the schema moves
as-is. Cloud Run takes the existing containers. The only genuinely new work is the model
layer, which is the work we came here to do.
