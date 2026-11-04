-- Atlas initial schema.
--
-- Two layers, kept apart on purpose:
--   reference  - companies, names, identifiers, places. Global, broad, cheap.
--   evidence   - documents, chunks, claims, cited edges. Narrow, deep, expensive.
--
-- Three invariants this file enforces in the schema rather than in review:
--   1. dependency_edge.chunk_id is NOT NULL. No citation, no edge.
--   2. Every edge carries valid_from/valid_to. There is no non-temporal read path.
--   3. Every tenant-scoped table has tenant_id and row-level security, from migration one.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- fuzzy name matching for entity resolution
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================ REFERENCE LAYER

CREATE TABLE exchange (
    mic               char(4) PRIMARY KEY,           -- ISO 10383
    operating_mic     char(4),
    name              text NOT NULL,
    country           char(2) NOT NULL,              -- ISO 3166-1 alpha-2
    city              text,
    timezone          text NOT NULL,                 -- IANA, e.g. 'Asia/Kolkata'
    currency          char(3) NOT NULL,              -- ISO 4217
    open_local        time,
    close_local       time,
    website           text,
    filings_portal_url text,
    terms_url         text
);

CREATE TABLE atlas_sector (
    code              text PRIMARY KEY,
    name              text NOT NULL,
    parent_code       text REFERENCES atlas_sector(code),
    definition        text NOT NULL,
    -- Deliberately our own taxonomy: GICS and ICB are licensed and cannot ship.
    maps_sic          text[],
    maps_naics        text[],
    maps_nace         text[],
    maps_nic          text[],
    maps_anzsic       text[],
    maps_wz           text[]
);

-- The company itself. One row per real-world company, however many places it lists.
CREATE TABLE entity (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    legal_name        text NOT NULL,
    common_name       text NOT NULL,
    country_incorporation char(2) NOT NULL,
    country_hq        char(2),
    atlas_sector      text REFERENCES atlas_sector(code),
    fiscal_year_end   char(5),                       -- 'MM-DD'
    status            text NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','delisted','acquired','merged','suspended')),
    successor_id      uuid REFERENCES entity(id),    -- set when acquired; edges follow this
    website           text,
    ir_url            text,
    description       text,
    employees         integer,
    employees_as_of   date,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- Identifiers are ROWS, not columns.
-- A company has many, gains them over time, and adding Australia must not mean
-- adding an asx_code column. scheme IN (CIK, LEI, ISIN, SEDOL, CUSIP, FIGI, NSE, BSE, ...)
CREATE TABLE entity_identifier (
    id                bigserial PRIMARY KEY,
    entity_id         uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    scheme            text NOT NULL,
    value             text NOT NULL,
    valid_from        date,
    valid_to          date,
    source_id         text NOT NULL,
    source_url        text,
    collected_by      text NOT NULL,
    collected_on      date NOT NULL
);
-- An identifier may be reused after a company dies, so uniqueness is per open interval.
CREATE UNIQUE INDEX entity_identifier_live_uq
    ON entity_identifier (scheme, value) WHERE valid_to IS NULL;
CREATE INDEX entity_identifier_entity_ix ON entity_identifier (entity_id, scheme);

-- Listings are ROWS too. Dual listings are normal (BHP on ASX and LSE; Infosys on NSE and NYSE).
CREATE TABLE entity_listing (
    id                bigserial PRIMARY KEY,
    entity_id         uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    exchange_mic      char(4) NOT NULL REFERENCES exchange(mic),
    ticker            text NOT NULL,
    company_uid       text NOT NULL UNIQUE,          -- '{MIC}:{TICKER}', the collection key
    is_primary        boolean NOT NULL DEFAULT false,
    listed_from       date,
    listed_to         date,                          -- NOT NULL means delisted. Keep the row.
    currency          char(3),
    free_float_pct    numeric(5,2),
    shares_outstanding bigint
);
CREATE INDEX entity_listing_entity_ix ON entity_listing (entity_id);

-- Market cap is a point-in-time fact, so it is a measurement, not a column on entity.
CREATE TABLE entity_metric (
    id                bigserial PRIMARY KEY,
    entity_id         uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    metric            text NOT NULL,                 -- 'market_cap_usd', 'employees', ...
    value             numeric NOT NULL,
    currency          char(3),
    as_of             date NOT NULL,
    band              text CHECK (band IN ('mega','large','mid','small','micro')),
    source_id         text NOT NULL,
    collected_on      date NOT NULL
);
CREATE INDEX entity_metric_lookup ON entity_metric (entity_id, metric, as_of DESC);

-- The gazetteer. This table is what stage-one extraction actually runs against.
CREATE TABLE entity_alias (
    id                bigserial PRIMARY KEY,
    entity_id         uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    alias             text NOT NULL,
    alias_norm        text NOT NULL,                 -- uppercased, suffixes stripped, punctuation removed
    alias_type        text NOT NULL CHECK (alias_type IN
                      ('legal','common','former','ticker','abbreviation',
                       'subsidiary','brand','local_script','transliteration')),
    language          char(2) NOT NULL DEFAULT 'en',
    script            text,
    token_count       smallint NOT NULL,
    -- Set when the alias collides with ordinary prose. The first gazetteer matched
    -- OPERA inside OPERATIONS and UNITI inside OPPORTUNITIES; see docs/cost.md.
    is_ambiguous      boolean NOT NULL DEFAULT false,
    ambiguity_note    text,
    valid_from        date,
    valid_to          date,
    source_id         text NOT NULL,
    collected_by      text NOT NULL,
    collected_on      date NOT NULL
);
CREATE INDEX entity_alias_norm_ix  ON entity_alias (alias_norm) WHERE NOT is_ambiguous;
CREATE INDEX entity_alias_trgm_ix  ON entity_alias USING gin (alias_norm gin_trgm_ops);

CREATE TABLE entity_classification (
    entity_id         uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    scheme            text NOT NULL,                 -- SIC | NAICS | NIC | ANZSIC | NACE | WZ
    code              text NOT NULL,
    name              text,
    valid_from        date,
    valid_to          date,
    PRIMARY KEY (entity_id, scheme, code)
);

CREATE TABLE entity_location (
    id                bigserial PRIMARY KEY,
    entity_id         uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    role              text NOT NULL CHECK (role IN ('hq','plant','fab','office','warehouse','mine')),
    address           text,
    city              text,
    state             text,
    country           char(2) NOT NULL,
    geom              geography(Point,4326) NOT NULL,
    valid_from        date,
    valid_to          date,
    source_id         text NOT NULL,
    chunk_id          uuid                           -- if asserted by a filing, cite it
);
CREATE INDEX entity_location_geom_ix ON entity_location USING gist (geom);

-- Point-in-time index membership. Without valid_from/valid_to, every backtest
-- inherits survivorship bias from a universe assembled today.
CREATE TABLE index_membership (
    id                bigserial PRIMARY KEY,
    index_code        text NOT NULL,
    entity_id         uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    valid_from        date NOT NULL,
    valid_to          date,
    source_id         text NOT NULL,
    collected_on      date NOT NULL
);
CREATE INDEX index_membership_asof ON index_membership (index_code, valid_from, valid_to);

CREATE TABLE port (
    unlocode          char(5) PRIMARY KEY,
    name              text NOT NULL,
    name_local        text,
    country           char(2) NOT NULL,
    geom              geography(Point,4326) NOT NULL,
    port_type         text,
    chokepoints       text[],                        -- SUEZ, MALACCA, HORMUZ, TAIWAN_STRAIT...
    annual_teu        bigint,
    teu_as_of         date,
    authority_name    text,
    authority_url     text,
    notices_url       text,
    timezone          text,
    source_id         text NOT NULL
);
CREATE INDEX port_geom_ix ON port USING gist (geom);

-- ============================================================ EVIDENCE LAYER

CREATE TABLE document (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id         uuid NOT NULL REFERENCES entity(id),
    doc_type          text NOT NULL,
    doc_subtype       text,
    period_start      date,
    period_end        date,
    fiscal_year_label text,                          -- the company's own label. NEVER join on this.
    -- filed_at_utc is the moment the information became PUBLIC. It becomes valid_from
    -- on every edge extracted from this document. period_end is what it describes.
    -- Confusing the two hands every backtest weeks of free clairvoyance.
    filed_at_utc      timestamptz NOT NULL,
    filed_at_local    timestamp NOT NULL,
    filed_tz          text NOT NULL,                 -- IANA
    source_id         text NOT NULL,
    external_id       text NOT NULL,
    landing_url       text,
    primary_doc_url   text NOT NULL,
    mime              text NOT NULL,
    language          char(2) NOT NULL DEFAULT 'en',
    pages             integer,
    is_amendment      boolean NOT NULL DEFAULT false,
    amends_document_id uuid REFERENCES document(id),
    retrieved_at_utc  timestamptz NOT NULL,
    sha256            char(64) NOT NULL,
    bytes             bigint NOT NULL,
    UNIQUE (source_id, external_id)
);
CREATE INDEX document_entity_filed_ix ON document (entity_id, filed_at_utc DESC);

CREATE TABLE section (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id       uuid NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    item_code         text,                          -- '1', '1A', '7' for 10-K; 'qa'/'prepared' for transcripts
    title             text,
    kind              text,
    char_start        integer NOT NULL,
    char_end          integer NOT NULL,
    CHECK (char_end > char_start)
);

CREATE TABLE chunk (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id       uuid NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    section_id        uuid REFERENCES section(id),
    ordinal           integer NOT NULL,
    char_start        integer NOT NULL,
    char_end          integer NOT NULL,
    text              text NOT NULL,
    sha256            char(64) NOT NULL,             -- the extraction cache key
    passed_stage_one  boolean,
    stage_one_version text,
    embedding_ref     text,                          -- Qdrant point id; embeddings computed locally
    UNIQUE (document_id, ordinal)
);
CREATE INDEX chunk_sha_ix ON chunk (sha256);

-- Re-extraction must be free. Keyed by content + both versions, so a prompt change
-- re-runs everything by design and an unchanged corpus costs zero calls.
CREATE TABLE extraction_cache (
    chunk_sha256      char(64) NOT NULL,
    extractor_version text NOT NULL,
    prompt_version    text NOT NULL,
    result_json       jsonb NOT NULL,
    model_id          text NOT NULL,
    input_tokens      integer,
    output_tokens     integer,
    latency_ms        integer,
    created_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_sha256, extractor_version, prompt_version)
);

-- What the model said, before any resolution or scoring. Including the ones that
-- never become edges: "a limited number of suppliers" lands here and stops.
CREATE TABLE dependency_claim (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id          uuid NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    subject_entity_id uuid NOT NULL REFERENCES entity(id),
    counterparty_text text,                          -- verbatim as written
    counterparty_entity_id uuid REFERENCES entity(id),
    counterparty_resolved boolean NOT NULL DEFAULT false,
    direction         text NOT NULL CHECK (direction IN ('upstream','downstream','peer')),
    specificity       text NOT NULL CHECK (specificity IN
                      ('named','typed_anonymous','geographic','commodity')),
    -- 'competitor' is a first-class answer the model must choose, not a default it
    -- falls into. Competitor lists in Item 1 are the dominant false positive.
    relationship_class text NOT NULL CHECK (relationship_class IN
                      ('supplier','customer','competitor','partner','former','hypothetical')),
    tense             text CHECK (tense IN ('historical','current','forward_looking')),
    substitutability  text CHECK (substitutability IN ('sole_source','single_source','limited','multiple','unstated')),
    materiality_pct   numeric(5,2),
    materiality_text  text,
    quote             text NOT NULL,
    char_start        integer NOT NULL,
    char_end          integer NOT NULL,
    extractor_version text NOT NULL,
    model_id          text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX dependency_claim_chunk_ix ON dependency_claim (chunk_id);

-- The graph. Only resolved, named claims reach here.
CREATE TABLE dependency_edge (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_entity_id    uuid NOT NULL REFERENCES entity(id),
    to_entity_id      uuid NOT NULL REFERENCES entity(id),
    edge_type         text NOT NULL,
    claim_id          uuid NOT NULL REFERENCES dependency_claim(id),
    chunk_id          uuid NOT NULL REFERENCES chunk(id),   -- NOT NULL. No citation, no edge.
    char_start        integer NOT NULL,
    char_end          integer NOT NULL,
    evidence_type     text NOT NULL CHECK (evidence_type IN
                      ('named_concentration','named_narrative','named_qa','named_contract')),
    -- valid_from = document.filed_at_utc. Never period_end.
    valid_from        timestamptz NOT NULL,
    valid_to          timestamptz,
    superseded_by     uuid REFERENCES dependency_edge(id),
    -- Written by versioned, unit-tested scoring code. Never by a model.
    confidence        numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    weight            numeric(6,4),
    scorer_version    text NOT NULL,
    reviewed_by       text,
    reviewed_at       timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CHECK (from_entity_id <> to_entity_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
-- Every graph read filters on this index. There is no non-temporal read path.
CREATE INDEX dependency_edge_asof_ix ON dependency_edge (from_entity_id, valid_from, valid_to);
CREATE INDEX dependency_edge_rev_ix  ON dependency_edge (to_entity_id, valid_from, valid_to);

-- Corrections append, never delete. Deleting would rewrite history and break every
-- point-in-time query that ran before the correction.
CREATE TABLE correction (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    edge_id           uuid NOT NULL REFERENCES dependency_edge(id),
    reported_by       text,
    reported_at       timestamptz NOT NULL DEFAULT now(),
    reason            text NOT NULL,
    resolution        text CHECK (resolution IN ('upheld','retired','amended','pending')),
    resolved_by       text,
    resolved_at       timestamptz,
    notes             text
);

-- ============================================================ EVENT LAYER

CREATE TABLE event (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name              text NOT NULL,
    event_type        text NOT NULL,
    -- Two timestamps, deliberately. A fire starts at one moment; the world learns at
    -- another; we can only ever react to the second.
    first_occurred_utc timestamptz,
    became_public_utc timestamptz NOT NULL,
    -- An event seen only in aggregated news never drives a user-visible claim.
    confirmation_level text NOT NULL DEFAULT 'unconfirmed'
                      CHECK (confirmation_level IN ('unconfirmed','corroborated','primary_confirmed')),
    severity          numeric(4,3),
    severity_version  text,
    commodities       text[],
    chokepoints       text[],
    dedupe_key        text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX event_public_ix ON event (became_public_utc DESC);

CREATE TABLE event_location (
    id                bigserial PRIMARY KEY,
    event_id          uuid NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    name              text,
    country           char(2),
    geom              geography(Point,4326) NOT NULL,
    radius_km         numeric,
    geocode_confidence numeric(4,3)
);
CREATE INDEX event_location_geom_ix ON event_location USING gist (geom);

CREATE TABLE event_source (
    id                bigserial PRIMARY KEY,
    event_id          uuid NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    source_id         text NOT NULL,
    url               text NOT NULL,
    headline          text,
    published_at_utc  timestamptz,
    updated_at_utc    timestamptz,
    is_primary        boolean NOT NULL DEFAULT false,
    retrieved_at_utc  timestamptz NOT NULL
);

-- ============================================================ TENANTS + DERIVED

CREATE TABLE tenant (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name              text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE coverage_universe (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id         uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    name              text NOT NULL,
    vintage           text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE universe_member (
    universe_id       uuid NOT NULL REFERENCES coverage_universe(id) ON DELETE CASCADE,
    entity_id         uuid NOT NULL REFERENCES entity(id),
    tenant_id         uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    reason            text,                          -- why this company is in. 'fts:AMAT x3' vs 'manual'
    valid_from        timestamptz NOT NULL,
    valid_to          timestamptz,
    PRIMARY KEY (universe_id, entity_id, valid_from)
);

-- Read path budget is under 200ms, so exposure is never computed on page load.
CREATE TABLE exposure_precompute (
    id                bigserial PRIMARY KEY,
    tenant_id         uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    event_id          uuid NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    entity_id         uuid NOT NULL REFERENCES entity(id),
    score             numeric(6,4) NOT NULL,
    hops              smallint NOT NULL CHECK (hops BETWEEN 1 AND 3),
    is_surprising     boolean NOT NULL,              -- the product's whole argument, as a column
    path_edge_ids     uuid[] NOT NULL,
    as_of             timestamptz NOT NULL,
    scorer_version    text NOT NULL,
    computed_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, event_id, entity_id, as_of, scorer_version)
);
CREATE INDEX exposure_rank_ix ON exposure_precompute (tenant_id, event_id, score DESC);

-- Row-level security in migration one, with the isolation test in the same PR.
-- One customer seeing another's universe is the failure that ends a company, and it
-- is trivially preventable before there is data and nearly impossible to retrofit after.
ALTER TABLE coverage_universe   ENABLE ROW LEVEL SECURITY;
ALTER TABLE universe_member     ENABLE ROW LEVEL SECURITY;
ALTER TABLE exposure_precompute ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON coverage_universe
    USING (tenant_id = current_setting('atlas.tenant_id')::uuid);
CREATE POLICY tenant_isolation ON universe_member
    USING (tenant_id = current_setting('atlas.tenant_id')::uuid);
CREATE POLICY tenant_isolation ON exposure_precompute
    USING (tenant_id = current_setting('atlas.tenant_id')::uuid);

-- The only sanctioned graph read. An ORM query that forgets as_of is a bug class
-- we design out rather than remember to avoid.
CREATE OR REPLACE FUNCTION edges_as_of(p_entity_ids uuid[], p_as_of timestamptz)
RETURNS SETOF dependency_edge
LANGUAGE sql STABLE AS $$
    SELECT * FROM dependency_edge
    WHERE (from_entity_id = ANY(p_entity_ids) OR to_entity_id = ANY(p_entity_ids))
      AND valid_from <= p_as_of
      AND (valid_to IS NULL OR valid_to > p_as_of);
$$;
