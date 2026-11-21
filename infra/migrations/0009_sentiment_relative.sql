-- Sentiment judged against its own section, not against zero.
--
-- The first scored batch exposed a flaw in reading these numbers naively.
-- Of 26 risk factor sections, 17 scored negative and none scored positive.
-- That is not a finding about the companies: Item 1A is a list of things that
-- could go wrong, so it is negative by construction. An absolute score over
-- that section measures the genre of the writing, not the business.
--
-- Management's discussion behaves quite differently, splitting 13 negative,
-- 7 neutral and 10 positive, because it is where a company explains results
-- it chose how to frame.
--
-- So the figure worth reading is relative: how does this company's risk
-- section compare with everyone else's risk section. A company whose risk
-- language is ordinary is saying nothing; one whose risk language is far
-- more negative than its peers' is saying something. The view below does
-- that comparison and leaves the stored score untouched.

CREATE OR REPLACE VIEW sentiment_relative AS
WITH scored AS (
  SELECT s.id,
         s.entity_id,
         s.subject_kind,
         COALESCE(f.section, 'headline') AS section,
         s.score,
         s.confidence,
         s.label,
         s.scorer_version,
         s.scored_at
  FROM sentiment_score s
  LEFT JOIN filing_section f
         ON s.subject_kind = 'filing_section' AND f.id = s.subject_id
),
baseline AS (
  SELECT section, scorer_version,
         avg(score)            AS mean_score,
         stddev_pop(score)     AS sd_score,
         count(*)              AS n_in_section
  FROM scored
  GROUP BY section, scorer_version
)
SELECT sc.id,
       sc.entity_id,
       sc.subject_kind,
       sc.section,
       sc.label,
       sc.score                                        AS raw_score,
       b.mean_score                                    AS section_mean,
       b.n_in_section,
       -- How far from the usual tone of this kind of text, in standard
       -- deviations. Null while a section has too few rows to have a
       -- baseline worth trusting: a comparison against four documents is
       -- not a comparison.
       CASE WHEN b.sd_score > 0 AND b.n_in_section >= 10
            THEN round(((sc.score - b.mean_score) / b.sd_score)::numeric, 3)
       END                                             AS relative_score,
       sc.confidence,
       sc.scorer_version,
       sc.scored_at
FROM scored sc
JOIN baseline b USING (section, scorer_version);

COMMENT ON VIEW sentiment_relative IS
  'Sentiment compared with the usual tone of the same section type. Risk '
  'factor sections are negative by construction, so only the relative figure '
  'carries information about a particular company.';
