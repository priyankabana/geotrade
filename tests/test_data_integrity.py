"""Invariants the data itself must satisfy, checked against the live database.

Code tests say the functions behave. These say the rows are sane - which is a
different question, and the one that decides whether a citation can be trusted.
"""
import pytest


def one(tx, sql, args=None):
    """psycopg only parses %-placeholders when parameters are supplied, so a
    query containing a literal % (a LIKE pattern, a regex) must be sent without
    any - otherwise '10 %' looks like a malformed placeholder."""
    tx.execute(sql) if args is None else tx.execute(sql, args)
    return tx.fetchone()[0]


# ------------------------------------------------- the citation, at row level

def test_the_quote_is_really_at_the_offsets_it_claims(tx):
    """The heart of it. A citation says: this sentence, at these characters, in
    this document. If the stored quote is not actually there, the link a user
    clicks points at the wrong words and the whole guarantee is theatre."""
    tx.execute("""
        SELECT dc.id, dc.quote, dc.char_start, dc.char_end, c.char_start, c.text
        FROM dependency_claim dc
        JOIN chunk c ON c.id = dc.chunk_id
        LIMIT 400
    """)
    rows = tx.fetchall()
    if not rows:
        pytest.skip("no claims; run make extract")
    bad = []
    for cid, quote, a, b, chunk_start, text in rows:
        local = text[a - chunk_start: b - chunk_start]
        # the stored quote is whitespace-normalised and capped, so compare that way
        if " ".join(quote.split())[:200] not in " ".join(local.split()):
            bad.append(cid)
    assert not bad, f"{len(bad)} of {len(rows)} quotes are not at their stated offsets"


def test_no_claim_points_outside_its_chunk(tx):
    assert one(tx, """SELECT count(*) FROM dependency_claim dc JOIN chunk c ON c.id=dc.chunk_id
                      WHERE dc.char_start < c.char_start OR dc.char_end > c.char_end""") == 0


def test_every_offset_range_is_non_empty_and_forward(tx):
    assert one(tx, """SELECT count(*) FROM dependency_claim
                      WHERE char_end <= char_start OR char_start < 0""") == 0


def test_no_edge_outlives_the_claim_it_came_from(tx):
    assert one(tx, """SELECT count(*) FROM dependency_edge de
                      LEFT JOIN dependency_claim dc ON dc.id = de.claim_id
                      WHERE dc.id IS NULL""") == 0


def test_every_edge_cites_the_same_chunk_as_its_claim(tx):
    assert one(tx, """SELECT count(*) FROM dependency_edge de
                      JOIN dependency_claim dc ON dc.id = de.claim_id
                      WHERE de.chunk_id <> dc.chunk_id""") == 0


def test_no_company_depends_on_itself(tx):
    assert one(tx, "SELECT count(*) FROM dependency_edge WHERE from_entity_id = to_entity_id") == 0


def test_every_quote_has_words_in_it(tx):
    assert one(tx, """SELECT count(*) FROM dependency_claim
                      WHERE quote IS NULL OR length(btrim(quote)) < 10""") == 0


def test_only_resolved_named_relationships_became_edges(tx):
    """Claims are everything we read. Edges are what we are willing to assert."""
    assert one(tx, """SELECT count(*) FROM dependency_edge de
                      JOIN dependency_claim dc ON dc.id = de.claim_id
                      WHERE NOT dc.counterparty_resolved
                         OR dc.specificity <> 'named'
                         OR dc.relationship_class NOT IN ('supplier','customer')""") == 0


def test_a_competitor_or_a_hypothetical_never_became_an_edge(tx):
    """The audit found competitor lists sitting directly above a Customers
    heading. They are recorded as claims and must not reach the graph."""
    assert one(tx, """SELECT count(*) FROM dependency_edge de
                      JOIN dependency_claim dc ON dc.id = de.claim_id
                      WHERE dc.relationship_class IN
                            ('competitor','partner','former','hypothetical')""") == 0


# ------------------------------------------------------------- scoring sanity

def test_every_confidence_is_a_fraction(tx):
    assert one(tx, "SELECT count(*) FROM dependency_edge WHERE confidence <= 0 OR confidence > 1") == 0


def test_every_weight_is_a_fraction(tx):
    assert one(tx, "SELECT count(*) FROM dependency_edge WHERE weight < 0 OR weight > 1") == 0


def test_no_disclosed_share_exceeds_everything(tx):
    assert one(tx, """SELECT count(*) FROM dependency_claim
                      WHERE materiality_pct IS NOT NULL
                        AND (materiality_pct < 0 OR materiality_pct > 100)""") == 0


def test_every_edge_records_which_scorer_produced_it(tx):
    """A number with no version behind it cannot be reproduced or defended."""
    assert one(tx, """SELECT count(*) FROM dependency_edge
                      WHERE scorer_version IS NULL OR scorer_version = ''""") == 0


def test_every_claim_records_which_extractor_produced_it(tx):
    assert one(tx, """SELECT count(*) FROM dependency_claim
                      WHERE extractor_version IS NULL OR extractor_version = ''""") == 0


def test_a_concentration_edge_really_has_concentration_evidence(tx):
    """Labelling the stronger tier is what the UI styles differently. It must
    mean something."""
    assert one(tx, """SELECT count(*) FROM dependency_edge de
                      JOIN dependency_claim dc ON dc.id = de.claim_id
                      WHERE de.evidence_type = 'named_concentration'
                        AND dc.materiality_pct IS NULL
                        AND dc.quote !~* 'accounted for|10 ?%|percent'""") == 0


# ------------------------------------------------------------- the reference layer

def test_every_edge_joins_to_a_real_company_at_both_ends(tx):
    assert one(tx, """SELECT count(*) FROM dependency_edge de
                      LEFT JOIN entity a ON a.id = de.from_entity_id
                      LEFT JOIN entity b ON b.id = de.to_entity_id
                      WHERE a.id IS NULL OR b.id IS NULL""") == 0


def test_coordinates_are_on_the_planet(tx):
    assert one(tx, """SELECT count(*) FROM entity_location
                      WHERE geom IS NOT NULL
                        AND (ST_Y(geom::geometry) NOT BETWEEN -90 AND 90
                          OR ST_X(geom::geometry) NOT BETWEEN -180 AND 180)""") == 0


def test_no_company_has_two_primary_listings(tx):
    assert one(tx, """SELECT count(*) FROM (
                        SELECT entity_id FROM entity_listing WHERE is_primary
                        GROUP BY entity_id HAVING count(*) > 1) d""") == 0


def test_no_two_companies_share_a_company_uid(tx):
    assert one(tx, """SELECT count(*) FROM (
                        SELECT company_uid FROM entity_listing
                        GROUP BY company_uid HAVING count(DISTINCT entity_id) > 1) d""") == 0


def test_every_chunk_belongs_to_a_document(tx):
    assert one(tx, """SELECT count(*) FROM chunk c
                      LEFT JOIN document d ON d.id = c.document_id
                      WHERE d.id IS NULL""") == 0


def test_no_document_was_ingested_twice(tx):
    assert one(tx, """SELECT count(*) FROM (
                        SELECT entity_id, external_id FROM document
                        WHERE external_id IS NOT NULL
                        GROUP BY 1,2 HAVING count(*) > 1) d""") == 0


def test_every_document_has_a_url_a_reader_can_open(tx):
    assert one(tx, """SELECT count(*) FROM document
                      WHERE primary_doc_url IS NULL
                         OR primary_doc_url NOT LIKE 'http%'""") == 0


def test_no_edge_predates_the_filing_it_came_from(tx):
    """valid_from is the filing date. An edge older than its own source would
    make the point-in-time rule meaningless."""
    assert one(tx, """SELECT count(*) FROM dependency_edge de
                      JOIN chunk c   ON c.id = de.chunk_id
                      JOIN document d ON d.id = c.document_id
                      WHERE de.valid_from < d.filed_at_utc""") == 0


def test_aliases_marked_usable_are_long_enough_to_match_on(tx):
    assert one(tx, """SELECT count(*) FROM entity_alias
                      WHERE NOT is_ambiguous AND length(btrim(alias_norm)) = 0""") == 0


def test_every_suppressed_alias_says_why(tx):
    """A suppression with no note cannot be reviewed or reversed."""
    assert one(tx, """SELECT count(*) FROM entity_alias
                      WHERE is_ambiguous AND (ambiguity_note IS NULL
                                              OR btrim(ambiguity_note) = '')""") == 0


def test_one_sentence_never_says_a_company_is_both_supplier_and_customer(tx):
    """A company named twice in one sentence gives one claim per mention - in
    "Boeing and RTX were our largest customers, with Boeing generating 13%",
    only the second mention sits next to a figure, so the percentages differ
    legitimately and the API picks the better-evidenced one.

    What must never differ is the direction. If one sentence says a company is
    both our supplier and our customer, the extractor has contradicted itself
    and one of the two edges is wrong."""
    tx.execute("""
        SELECT count(*) FROM (
          SELECT chunk_id, char_start, counterparty_entity_id
          FROM dependency_claim
          GROUP BY 1,2,3
          HAVING count(DISTINCT direction) > 1
              OR count(DISTINCT relationship_class) > 1
        ) d
    """)
    assert tx.fetchone()[0] == 0, "one sentence placed a company on both sides"



def test_one_extractor_version_produced_the_whole_graph(tx):
    """A graph half-built by two versions cannot be reasoned about: half of it
    has fixes the other half does not."""
    tx.execute("SELECT count(DISTINCT extractor_version) FROM dependency_claim")
    assert tx.fetchone()[0] <= 1, "run make extract to rebuild the graph in one version"
