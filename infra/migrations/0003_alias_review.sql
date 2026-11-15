-- A human decision about an ambiguous alias, with a date on it.
--
-- Some alias_norms resolve to more than one entity. Two kinds, and they need
-- opposite treatment:
--
--   duplicates  - "Cyclacel Pharmaceuticals Inc" and "Cyclacel Pharmaceuticals
--                 Inc." are one company loaded twice. Merge.
--   collisions  - "METRO" is Metro AG, Metro Inc. and Ceconomy. Picking one
--                 arbitrarily is how a sentence about a German wholesaler
--                 becomes an edge to a Canadian grocer.
--
-- The extractor used to take whichever row came back first. That is a decision,
-- made by the query planner, with nobody accountable for it and no record. This
-- table makes it a decision a person made on a date, and reversible.

CREATE TABLE IF NOT EXISTS alias_decision (
    alias_norm   text PRIMARY KEY,
    decision     text NOT NULL CHECK (decision IN ('prefer', 'suppress', 'merge')),
    entity_id    uuid REFERENCES entity(id) ON DELETE CASCADE,   -- for 'prefer'
    decided_by   text NOT NULL,
    decided_at   timestamptz NOT NULL DEFAULT now(),
    note         text,
    CONSTRAINT prefer_needs_an_entity
        CHECK (decision <> 'prefer' OR entity_id IS NOT NULL)
);

GRANT SELECT ON alias_decision TO atlas_app;

-- Which ambiguous aliases are still waiting on a person. Only aliases that are
-- usable at all: suppressed ones cannot reach the extractor anyway.
CREATE OR REPLACE VIEW alias_review_queue AS
SELECT a.alias_norm,
       count(DISTINCT a.entity_id)                                   AS entity_count,
       array_agg(DISTINCT e.legal_name ORDER BY e.legal_name)        AS candidates,
       array_agg(DISTINCT a.entity_id)                               AS entity_ids
FROM entity_alias a
JOIN entity e ON e.id = a.entity_id
WHERE NOT a.is_ambiguous
  AND length(a.alias_norm) >= 5
  AND NOT EXISTS (SELECT 1 FROM alias_decision d WHERE d.alias_norm = a.alias_norm)
GROUP BY a.alias_norm
HAVING count(DISTINCT a.entity_id) > 1;

GRANT SELECT ON alias_review_queue TO atlas_app;
