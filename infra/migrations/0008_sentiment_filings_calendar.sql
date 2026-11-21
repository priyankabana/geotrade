-- Sentiment, filing text and the earnings calendar.
--
-- Review 1 listed sentiment classification and the project did not build it;
-- Review 3 said so plainly. This is that layer, held to the same rule as the
-- rest of the system: a score exists only with the text it was read from and
-- the version of the scorer that produced it, so any number on screen can be
-- traced back and recomputed.

-- ---------------------------------------------------------------- filings --
-- The body of a filing, section by section. EDGAR serves the whole document;
-- what a reader and a model both want is the part that carries meaning, so
-- the section is the unit rather than the file.
CREATE TABLE IF NOT EXISTS filing_section (
  id             BIGSERIAL PRIMARY KEY,
  entity_id      UUID        NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  accession      TEXT        NOT NULL,
  form           TEXT        NOT NULL,
  filed_date     DATE        NOT NULL,
  period_end     DATE,
  section        TEXT        NOT NULL,     -- mdna | risk_factors | results | other
  heading        TEXT        NOT NULL DEFAULT '',
  body           TEXT        NOT NULL,
  char_count     INT         NOT NULL,
  source_url     TEXT        NOT NULL,
  retrieved_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (accession, section, heading)
);
CREATE INDEX IF NOT EXISTS filing_section_entity_ix
  ON filing_section (entity_id, filed_date DESC);

-- --------------------------------------------------------------- calendar --
-- When a company next reports. Taken from its own 8-K announcing the date,
-- never from a vendor's calendar, so every row points at a filing.
CREATE TABLE IF NOT EXISTS earnings_event (
  id            BIGSERIAL PRIMARY KEY,
  entity_id     UUID        NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  event_date    DATE        NOT NULL,
  period_label  TEXT        NOT NULL DEFAULT '',
  status        TEXT        NOT NULL DEFAULT 'scheduled'
                CHECK (status IN ('scheduled', 'reported')),
  source_url    TEXT        NOT NULL,
  source_form   TEXT        NOT NULL DEFAULT '',
  retrieved_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (entity_id, event_date, period_label)
);
CREATE INDEX IF NOT EXISTS earnings_event_date_ix
  ON earnings_event (event_date, entity_id);

-- -------------------------------------------------------------- sentiment --
-- One row per scored passage. subject_kind and subject_id say what was read;
-- excerpt keeps the words the score came from, so a disputed number can be
-- checked against its own evidence the way a dependency edge can.
CREATE TABLE IF NOT EXISTS sentiment_score (
  id             BIGSERIAL PRIMARY KEY,
  entity_id      UUID        NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  subject_kind   TEXT        NOT NULL
                 CHECK (subject_kind IN ('news', 'filing_section', 'transcript')),
  subject_id     BIGINT      NOT NULL,
  label          TEXT        NOT NULL CHECK (label IN ('positive', 'negative', 'neutral')),
  score          NUMERIC(4,3) NOT NULL CHECK (score BETWEEN -1 AND 1),
  confidence     NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  horizon        TEXT        NOT NULL DEFAULT 'unknown'
                 CHECK (horizon IN ('immediate', 'medium', 'structural', 'unknown')),
  event_type     TEXT        NOT NULL DEFAULT 'other',
  topics         TEXT[]      NOT NULL DEFAULT '{}',
  excerpt        TEXT        NOT NULL,
  method         TEXT        NOT NULL CHECK (method IN ('lexicon', 'model')),
  scorer_version TEXT        NOT NULL,
  scored_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (subject_kind, subject_id, scorer_version)
);
CREATE INDEX IF NOT EXISTS sentiment_entity_ix
  ON sentiment_score (entity_id, scored_at DESC);

-- A score with no words behind it is the thing this project exists to avoid.
ALTER TABLE sentiment_score
  DROP CONSTRAINT IF EXISTS sentiment_excerpt_ck;
ALTER TABLE sentiment_score
  ADD CONSTRAINT sentiment_excerpt_ck CHECK (length(btrim(excerpt)) > 0);
