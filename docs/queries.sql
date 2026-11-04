-- Handy queries. Paste into psql, or into the Query tab at http://localhost:8081
--
--   psql postgresql://atlas:atlas@localhost:5432/atlas
--   make query Q="select count(*) from entity"

-- ───────────────────────────── coverage ─────────────────────────────

-- companies per country
SELECT l.country, count(*) AS companies
FROM entity_location l WHERE l.role = 'hq'
GROUP BY 1 ORDER BY 2 DESC;

-- companies per exchange
SELECT li.exchange_mic, x.name, count(*) AS companies
FROM entity_listing li JOIN exchange x ON x.mic = li.exchange_mic
GROUP BY 1, 2 ORDER BY 3 DESC;

-- one row per country: companies, sectors, how many we could geocode to a city
SELECT l.country,
       count(*)                                        AS companies,
       count(DISTINCT e.atlas_sector)                  AS sectors,
       count(*) FILTER (WHERE l.city IS NOT NULL)      AS city_located
FROM entity_location l JOIN entity e ON e.id = l.entity_id
WHERE l.role = 'hq'
GROUP BY 1 ORDER BY 2 DESC;

-- ───────────────────────── country → sector ─────────────────────────

-- sectors inside one country  (change 'IN' to US, GB, DE, CA, AU …)
SELECT e.atlas_sector, s.name, count(*) AS companies
FROM entity e
JOIN entity_location l ON l.entity_id = e.id AND l.role = 'hq'
LEFT JOIN atlas_sector s ON s.code = e.atlas_sector
WHERE l.country = 'IN'
GROUP BY 1, 2 ORDER BY 3 DESC;

-- the same thing for every country at once, as a grid
SELECT s.name AS sector,
       count(*) FILTER (WHERE l.country = 'US') AS us,
       count(*) FILTER (WHERE l.country = 'IN') AS india,
       count(*) FILTER (WHERE l.country = 'GB') AS uk,
       count(*) FILTER (WHERE l.country = 'DE') AS germany,
       count(*) FILTER (WHERE l.country = 'CA') AS canada,
       count(*) FILTER (WHERE l.country = 'AU') AS australia
FROM entity e
JOIN entity_location l ON l.entity_id = e.id AND l.role = 'hq'
JOIN atlas_sector s ON s.code = e.atlas_sector
GROUP BY 1 ORDER BY 2 DESC NULLS LAST;

-- ───────────────────── country → sector → company ───────────────────

-- the companies themselves
SELECT li.company_uid, e.common_name, l.city, m.band AS cap_band
FROM entity e
JOIN entity_listing li  ON li.entity_id = e.id AND li.is_primary
JOIN entity_location l  ON l.entity_id = e.id AND l.role = 'hq'
LEFT JOIN entity_metric m ON m.entity_id = e.id AND m.metric = 'market_cap_usd'
WHERE l.country = 'IN'
  AND e.atlas_sector IN ('SEMI_DEVICES', 'SEMI_EQUIP', 'ELECTRONIC_COMPONENTS')
ORDER BY e.common_name;

-- find a company by any of its names — this is the gazetteer doing its job
SELECT DISTINCT li.company_uid, e.common_name, a.alias, a.alias_type
FROM entity_alias a
JOIN entity e          ON e.id = a.entity_id
JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
WHERE a.alias_norm LIKE '%RELIANCE%'
ORDER BY e.common_name LIMIT 20;

-- everything we hold about one company
SELECT e.legal_name, e.common_name, e.atlas_sector, e.status, e.website,
       l.city, l.country, m.band,
       (SELECT string_agg(scheme || ' ' || value, ' · ')
          FROM entity_identifier i WHERE i.entity_id = e.id) AS identifiers,
       (SELECT string_agg(alias, ' | ')
          FROM entity_alias a WHERE a.entity_id = e.id AND a.alias_type = 'former') AS former_names
FROM entity_listing li
JOIN entity e           ON e.id = li.entity_id
LEFT JOIN entity_location l ON l.entity_id = e.id AND l.role = 'hq'
LEFT JOIN entity_metric m   ON m.entity_id = e.id AND m.metric = 'market_cap_usd'
WHERE li.company_uid = 'XNSE:DIXON';

-- ───────────────────────── data quality ─────────────────────────────

-- the gazetteer stage-one extraction will match against
SELECT alias_type,
       count(*) FILTER (WHERE NOT is_ambiguous) AS usable,
       count(*) FILTER (WHERE is_ambiguous)     AS suppressed
FROM entity_alias GROUP BY 1 ORDER BY 2 DESC;

-- how precisely each company is placed on the globe
SELECT CASE WHEN l.city IS NOT NULL THEN 'city' ELSE 'country centroid' END AS precision,
       count(*)
FROM entity_location l WHERE l.role = 'hq' GROUP BY 1;

-- companies within 100 km of a point (PostGIS) — here, Santa Clara
SELECT e.common_name, l.city
FROM entity_location l JOIN entity e ON e.id = l.entity_id
WHERE ST_DWithin(l.geom, ST_SetSRID(ST_MakePoint(-121.95, 37.35), 4326)::geography, 100000)
ORDER BY e.common_name LIMIT 20;

-- ─────────────────────── the evidence layer ─────────────────────────
-- These are empty until extraction runs. That is Phase 1, not a bug.

SELECT count(*) AS documents FROM document;
SELECT count(*) AS cited_edges FROM dependency_edge;
SELECT count(*) FROM edges_as_of(ARRAY[]::uuid[], now());   -- point-in-time read path
