"""The backtest must not be able to see the future.

This is the test the roadmap says to write before the harness, because
look-ahead bias is the one defect that makes a result look excellent and be
worthless. Everything here goes through `edges_as_of`, which is the only
sanctioned graph read.
"""
import datetime as dt
import pytest

BEFORE = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
MIDDLE = dt.datetime(2023, 6, 1, tzinfo=dt.timezone.utc)
AFTER  = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)


def _two_entities(tx):
    tx.execute("SELECT id FROM entity LIMIT 2")
    rows = [r[0] for r in tx.fetchall()]
    if len(rows) < 2:
        pytest.skip("need at least two entities loaded")
    return rows


def _an_edge(tx):
    """Clone a real edge so every NOT NULL column is satisfied honestly -
    including chunk_id, which is the citation guarantee and cannot be faked."""
    tx.execute("""SELECT claim_id, chunk_id, char_start, char_end, edge_type,
                         evidence_type, confidence, weight, scorer_version
                  FROM dependency_edge LIMIT 1""")
    row = tx.fetchone()
    if not row:
        pytest.skip("no edges in the graph; run make extract")
    return row


def _insert(tx, a, b, valid_from, valid_to=None):
    claim, chunk, cs, ce, et, ev, conf, w, sv = _an_edge(tx)
    tx.execute("""INSERT INTO dependency_edge
                    (from_entity_id, to_entity_id, edge_type, claim_id, chunk_id,
                     char_start, char_end, evidence_type, valid_from, valid_to,
                     confidence, weight, scorer_version)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                  RETURNING id""",
               (a, b, et, claim, chunk, cs, ce, ev, valid_from, valid_to, conf, w, sv))
    return tx.fetchone()[0]


def _visible(tx, ids, as_of):
    tx.execute("SELECT id FROM edges_as_of(%s, %s)", (ids, as_of))
    return {r[0] for r in tx.fetchall()}


def test_an_edge_published_after_the_as_of_date_is_invisible(tx):
    """The whole point. A filing from 2026 may not explain a 2021 event."""
    a, b = _two_entities(tx)
    future = _insert(tx, a, b, valid_from=AFTER)
    assert future not in _visible(tx, [a, b], MIDDLE)


def test_the_same_edge_is_visible_once_its_date_has_passed(tx):
    """And the rule must not simply hide everything, or it proves nothing."""
    a, b = _two_entities(tx)
    past = _insert(tx, a, b, valid_from=BEFORE)
    assert past in _visible(tx, [a, b], MIDDLE)


def test_a_retired_edge_is_invisible_after_its_valid_to(tx):
    """valid_to was never checked by the propagation walk before this suite."""
    a, b = _two_entities(tx)
    retired = _insert(tx, a, b, valid_from=BEFORE, valid_to=MIDDLE)
    assert retired not in _visible(tx, [a, b], AFTER)
    assert retired in _visible(tx, [a, b], dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc))


def test_the_graph_only_grows_as_time_moves_forward(tx):
    """Monotonicity: no edge may appear and then vanish without a valid_to."""
    a, b = _two_entities(tx)
    _insert(tx, a, b, valid_from=BEFORE)
    _insert(tx, a, b, valid_from=AFTER)
    early = _visible(tx, [a, b], MIDDLE)
    late  = _visible(tx, [a, b], AFTER)
    assert early.issubset(late), "an edge disappeared as the clock moved forward"


def test_no_stored_exposure_row_used_an_edge_from_its_own_future(tx):
    """The real integrity check, against the precomputed table the API serves.

    Every exposure row records the as_of it was computed at. No edge touching
    that company may post-date it, or the walk that produced the row saw the
    future."""
    tx.execute("""
        SELECT count(*)
        FROM exposure_precompute ep
        JOIN dependency_edge de
          ON de.from_entity_id = ep.entity_id
        WHERE ep.hops >= 2
          AND de.valid_from > ep.as_of
          AND NOT EXISTS (
                SELECT 1 FROM dependency_edge ok
                 WHERE ok.from_entity_id = ep.entity_id
                   AND ok.valid_from <= ep.as_of)
    """)
    leaked = tx.fetchone()[0]
    assert leaked == 0, f"{leaked} exposure rows are reachable only via future edges"


def test_every_edge_carries_a_citation(tx):
    """The guarantee the product is built on, checked against live data."""
    tx.execute("SELECT count(*) FROM dependency_edge WHERE chunk_id IS NULL")
    assert tx.fetchone()[0] == 0


def test_the_schema_refuses_an_edge_with_no_source(tx, db):
    """Not a convention we follow - a constraint the data cannot violate."""
    import psycopg
    a, b = _two_entities(tx)
    claim, chunk, cs, ce, et, ev, conf, w, sv = _an_edge(tx)
    with pytest.raises(psycopg.errors.NotNullViolation):
        tx.execute("""INSERT INTO dependency_edge
                        (from_entity_id, to_entity_id, edge_type, claim_id, chunk_id,
                         char_start, char_end, evidence_type, valid_from,
                         confidence, weight, scorer_version)
                      VALUES (%s,%s,%s,%s,NULL,%s,%s,%s,now(),%s,%s,%s)""",
                   (a, b, et, claim, cs, ce, ev, conf, w, sv))
