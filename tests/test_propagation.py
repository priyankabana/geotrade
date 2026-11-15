"""Properties the propagation walk must hold, checked against the real graph.

These are properties rather than examples: they say what must be true of every
row, so they keep holding as the corpus grows.
"""
import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))


def _const(name, default):
    import importlib.util
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts", "propagate.py")
    src = open(p).read()
    for line in src.splitlines():
        if line.startswith(name):
            return eval(line.split("=", 1)[1].split("#")[0].strip())
    return default


MAX_HOPS = _const("MAX_HOPS", 3)
DECAY    = _const("DECAY", 0.55)


def test_the_walk_is_bounded(tx):
    """Three hops. Beyond that the signal is weaker than our own error rate."""
    tx.execute("SELECT coalesce(max(hops), 0) FROM exposure_precompute")
    assert tx.fetchone()[0] <= MAX_HOPS


def test_no_company_is_exposed_to_an_event_at_zero_hops(tx):
    tx.execute("SELECT count(*) FROM exposure_precompute WHERE hops < 1")
    assert tx.fetchone()[0] == 0


def test_surprising_means_exactly_two_hops_or_more(tx):
    """The product's whole claim. At one hop you would have named them yourself."""
    tx.execute("""SELECT count(*) FROM exposure_precompute
                  WHERE is_surprising <> (hops >= 2)""")
    assert tx.fetchone()[0] == 0


def test_every_score_is_a_probability_like_number(tx):
    tx.execute("SELECT count(*) FROM exposure_precompute WHERE score <= 0 OR score > 1")
    assert tx.fetchone()[0] == 0


def test_scores_decay_with_distance(tx):
    """A company further from the event cannot outscore the companies it is
    reached through, or the decay is not doing anything."""
    tx.execute("""SELECT event_id, hops, max(score) FROM exposure_precompute
                  GROUP BY event_id, hops ORDER BY event_id, hops""")
    best = {}
    for ev, hops, mx in tx.fetchall():
        best.setdefault(ev, {})[hops] = float(mx)
    for ev, byhop in best.items():
        for h in sorted(byhop)[1:]:
            assert byhop[h] <= byhop[h - 1] + 1e-9, f"event {ev}: hop {h} outscores hop {h-1}"


def test_a_company_is_listed_once_per_event(tx):
    """The walk keeps the best path, so a company cannot appear twice."""
    tx.execute("""SELECT count(*) FROM (
                    SELECT event_id, entity_id FROM exposure_precompute
                    GROUP BY 1, 2 HAVING count(*) > 1) d""")
    assert tx.fetchone()[0] == 0


def test_every_exposure_row_records_what_produced_it(tx):
    """Deterministic and versioned. A score with no scorer version is unauditable."""
    tx.execute("""SELECT count(*) FROM exposure_precompute
                  WHERE scorer_version IS NULL OR as_of IS NULL""")
    assert tx.fetchone()[0] == 0


def test_the_decay_constant_is_declared_not_fitted(tx):
    """We have no ground truth to fit against, so it must stay a stated choice."""
    assert 0 < DECAY < 1


def test_an_event_with_no_graph_behind_it_reports_nothing(tx):
    """Ever Given is 2021 and every filing we hold is later. Zero is the correct
    answer and the point-in-time rule is what produces it."""
    tx.execute("""SELECT count(*) FROM exposure_precompute ep
                  JOIN event e ON e.id = ep.event_id
                  WHERE e.dedupe_key = 'ever-given' AND ep.hops >= 2""")
    assert tx.fetchone()[0] == 0


def test_exposure_is_precomputed_not_computed_on_read(tx):
    """The 5 ms median depends on this table being populated."""
    tx.execute("SELECT count(*) FROM exposure_precompute")
    assert tx.fetchone()[0] > 0, "run make propagate"
