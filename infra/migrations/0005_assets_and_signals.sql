-- Assets and signals: the tradeable surface.
--
-- Atlas's graph is company-to-company. That answers "who is exposed", but a
-- person watching a disruption also wants to know which of the things they can
-- actually trade are implicated - and most of those are not companies at all.
--
-- The two cannot be justified the same way, and the schema says so rather than
-- leaving it to a caption. Every signal carries a `basis`:
--
--   cited_dependency  a company disclosed this dependency in a filing, and
--                     `edge_id` points at the edge, which points at the
--                     sentence. This is the claim Atlas is actually built on.
--
--   rule              a named, version-controlled rule in scripts/signals.py
--                     fired. No company said this. A rule is an argument we are
--                     making, and `rule_id` names which one so it can be
--                     disputed, changed, or thrown out.
--
-- A reader can therefore filter the whole dashboard down to only the rows that
-- rest on evidence, which is the question a sceptical examiner asks first.

CREATE TABLE IF NOT EXISTS asset (
    id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol       text NOT NULL UNIQUE,
    name         text NOT NULL,
    asset_class  text NOT NULL CHECK (asset_class IN
                   ('commodity','equity_index','fx','crypto','stock','etf','bond')),
    currency     char(3),
    -- Set when the asset is a company we actually hold evidence for, which is
    -- what lets a stock row be backed by a filing instead of by a rule.
    entity_id    uuid REFERENCES entity(id),
    note         text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS asset_class_ix  ON asset (asset_class);
CREATE INDEX IF NOT EXISTS asset_entity_ix ON asset (entity_id);

CREATE TABLE IF NOT EXISTS asset_signal (
    id              bigserial PRIMARY KEY,
    event_id        uuid NOT NULL REFERENCES event(id) ON DELETE CASCADE,
    asset_id        uuid NOT NULL REFERENCES asset(id) ON DELETE CASCADE,

    -- Deliberately not "buy" and "sell". This says which way a disruption
    -- pushes on a business, which is a claim about the world. What anyone
    -- should do about it depends on price, position and horizon - none of
    -- which Atlas knows, and none of which it is willing to pretend to know.
    direction       text NOT NULL CHECK (direction IN ('up','down','unclear')),

    basis           text NOT NULL CHECK (basis IN ('cited_dependency','rule')),
    magnitude       numeric(4,3) NOT NULL,
    hops            int,

    -- Exactly one of these is set, enforced below.
    edge_id         uuid REFERENCES dependency_edge(id) ON DELETE CASCADE,
    rule_id         text,

    rationale       text NOT NULL,
    as_of           timestamptz NOT NULL,
    scorer_version  text NOT NULL,
    computed_at     timestamptz NOT NULL DEFAULT now(),

    -- A cited signal without an edge is an uncited signal wearing a label, and
    -- a rule signal without a rule id cannot be argued with. Neither is allowed
    -- to exist.
    CONSTRAINT asset_signal_basis_ck CHECK (
        (basis = 'cited_dependency' AND edge_id IS NOT NULL AND rule_id IS NULL)
     OR (basis = 'rule'             AND rule_id IS NOT NULL AND edge_id IS NULL)
    ),
    CONSTRAINT asset_signal_once UNIQUE (event_id, asset_id, basis, rule_id, edge_id)
);

CREATE INDEX IF NOT EXISTS asset_signal_event_ix ON asset_signal (event_id, magnitude DESC);
CREATE INDEX IF NOT EXISTS asset_signal_basis_ix ON asset_signal (basis);
