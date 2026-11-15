-- Make the tenancy that migration 0001 declared actually bite, and give the API
-- something to authenticate with.
--
-- 0001 enabled row-level security and wrote the policies, but the API connects
-- as `atlas`, which owns the tables and is a superuser. Postgres exempts both,
-- so the policies never ran. Setting a tenant id that belongs to nobody still
-- returned every row. A guarantee that is documented and not enforced is worse
-- than no guarantee, because people rely on it.

-- 1. A role that is not the owner and not a superuser, so policies apply to it.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_app') THEN
        CREATE ROLE atlas_app LOGIN PASSWORD 'atlas_app';
    END IF;
END $$;

GRANT CONNECT ON DATABASE atlas TO atlas_app;
GRANT USAGE  ON SCHEMA public   TO atlas_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO atlas_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO atlas_app;

-- 2. Force the policies even for the owner, so a future migration that runs as
--    atlas cannot silently reintroduce the hole.
ALTER TABLE exposure_precompute FORCE ROW LEVEL SECURITY;
ALTER TABLE universe_member     FORCE ROW LEVEL SECURITY;
ALTER TABLE coverage_universe   FORCE ROW LEVEL SECURITY;

-- 3. The policies in 0001 compare against current_setting('atlas.tenant_id'),
--    which throws if the setting was never made. Make an unset tenant mean
--    "see nothing" rather than "crash", so a caller who forgets to authenticate
--    gets an empty result and never someone else's data.
CREATE OR REPLACE FUNCTION current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('atlas.tenant_id', true), '')::uuid;
$$;

DROP POLICY IF EXISTS tenant_isolation ON exposure_precompute;
DROP POLICY IF EXISTS tenant_isolation ON universe_member;
DROP POLICY IF EXISTS tenant_isolation ON coverage_universe;

CREATE POLICY tenant_isolation ON exposure_precompute
    USING (tenant_id = current_tenant());
CREATE POLICY tenant_isolation ON universe_member
    USING (tenant_id = current_tenant());
CREATE POLICY tenant_isolation ON coverage_universe
    USING (tenant_id = current_tenant());

-- 4. API keys. We store only a SHA-256 of the key, so the table is useless to
--    anyone who reads it, including us.
CREATE TABLE IF NOT EXISTS api_key (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    name        text NOT NULL,
    key_sha256  text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at  timestamptz
);
CREATE INDEX IF NOT EXISTS api_key_lookup_ix ON api_key (key_sha256) WHERE revoked_at IS NULL;

GRANT SELECT ON api_key TO atlas_app;
GRANT UPDATE (last_used_at) ON api_key TO atlas_app;
