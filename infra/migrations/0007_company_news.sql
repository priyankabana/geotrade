-- News per company, from the one index we are allowed to read.
--
-- TradingView's news widget is thin outside the large caps: NVIDIA gets a full
-- feed, CEVA gets "No data yet". That is most of our graph, because disclosure
-- inversion means the companies that carry evidence are small suppliers rather
-- than household names.
--
-- The alternative is not to scrape Yahoo, MarketWatch, CNBC, Nikkei or SCMP.
-- Their terms prohibit automated extraction, and docs/sources.md already
-- rejected NewsAPI on the same ground. GDELT indexes those outlets itself,
-- publishes an API, and permits links and headlines - which is all a reader
-- needs to click through to the publisher, who then gets the visit.
--
-- So we store the link and the headline and never the article body.
CREATE TABLE IF NOT EXISTS company_news (
    id            bigserial PRIMARY KEY,
    entity_id     uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    source_id     text NOT NULL,
    url           text NOT NULL,
    headline      text,
    domain        text,
    language      text,
    published_at  timestamptz,
    retrieved_at  timestamptz NOT NULL DEFAULT now(),
    -- The search that found it, kept so a bad query can be withdrawn by name
    -- rather than by guessing which rows it produced.
    query_id      text
);

CREATE UNIQUE INDEX IF NOT EXISTS company_news_uq ON company_news (entity_id, url);
CREATE INDEX IF NOT EXISTS company_news_recent_ix
    ON company_news (entity_id, published_at DESC NULLS LAST);

-- When each company was last asked about, so a refresh can go round the
-- universe in order instead of re-asking the same twenty names.
CREATE TABLE IF NOT EXISTS company_news_cursor (
    entity_id    uuid PRIMARY KEY REFERENCES entity(id) ON DELETE CASCADE,
    last_fetched timestamptz NOT NULL DEFAULT now(),
    found        int NOT NULL DEFAULT 0
);
