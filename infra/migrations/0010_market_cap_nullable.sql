-- A market cap known only as a band must not be stored as zero.
--
-- load_csv accepts a row where only market_cap_band is present (for example
-- "large") with no market_cap_usd figure. The value column was NOT NULL, so the
-- loader wrote 0, which reads as a real zero-dollar market cap rather than as
-- "unknown". The public extract already drops this constraint and nulls the
-- value (export_public_db.py), so the fabricated zero only ever existed in the
-- working database. Make value nullable here too, so a band can be recorded on
-- its own and the number left genuinely absent.

ALTER TABLE entity_metric ALTER COLUMN value DROP NOT NULL;
