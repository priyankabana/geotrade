-- Live event ingestion.
--
-- Until now every event in the graph was a literal in scripts/propagate.py: a
-- real, dated disruption, but typed in by a person. `event_source` has existed
-- since 0001 and has never held a row, which is the honest measure of how much
-- of this system watches the world. Nothing did.
--
-- Two columns are needed before a fetched event can be propagated.

-- The seed rule. Propagation starts from the companies in the sectors an event
-- touches, and that list used to live beside the event in Python. A fetched
-- event has no Python literal to live in, so the list belongs on the row.
ALTER TABLE event ADD COLUMN IF NOT EXISTS seed_sectors text[];

-- Which feed produced it, so a bad adapter can be retracted by name rather
-- than by hand. NULL means a hand-written benchmark event.
ALTER TABLE event ADD COLUMN IF NOT EXISTS source_feed text;

-- dedupe_key is what ingestion matches on to avoid inserting the same
-- earthquake twice. It was never actually unique, so two runs of the same
-- fetch would have produced two rows that propagation then scored separately.
CREATE UNIQUE INDEX IF NOT EXISTS event_dedupe_key_uq
    ON event (dedupe_key) WHERE dedupe_key IS NOT NULL;

-- One source URL may corroborate only one event once.
CREATE UNIQUE INDEX IF NOT EXISTS event_source_url_uq
    ON event_source (event_id, url);

CREATE INDEX IF NOT EXISTS event_source_feed_ix ON event (source_feed);
