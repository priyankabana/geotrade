"""The propagation walk, on graphs small enough to reason about by hand.

The property tests in test_propagation.py check the stored output. These check
the algorithm itself: that a chain decays, that a cycle terminates, that the
best path wins, and that the hop bound really bounds.

Pure - no database.
"""
import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
prop = pytest.importorskip("propagate")

walk = prop.walk


def g(**edges):
    """out_edges[b] = everyone who depends on b. Weight and confidence 1.0 so
    the arithmetic in a test is only the decay."""
    return {k: [(d, 1.0, 1.0) for d in v] for k, v in edges.items()}


def test_a_seed_sits_at_hop_one_with_the_event_severity():
    best = walk({}, ["A"], 0.8)
    assert best["A"] == (0.8, 1, [])


def test_a_dependant_is_reached_at_hop_two():
    best = walk(g(A=["B"]), ["A"], 1.0)
    assert best["B"][1] == 2
    assert best["B"][0] == pytest.approx(prop.DECAY)


def test_each_further_hop_decays_again():
    best = walk(g(A=["B"], B=["C"]), ["A"], 1.0)
    assert best["C"][0] == pytest.approx(prop.DECAY ** 2)
    assert best["C"][1] == 3


def test_the_walk_stops_at_the_hop_bound():
    """The seed is hop 1, so MAX_HOPS=3 traverses two edges, not three.

    Worth stating plainly: "a bounded three-hop walk" means a company three
    levels from the event, which is two dependencies away from the companies
    the event hit directly."""
    chain = g(A=["B"], B=["C"], C=["D"], D=["E"])
    best = walk(chain, ["A"], 1.0, max_hops=3)
    assert best["A"][1] == 1 and best["B"][1] == 2 and best["C"][1] == 3
    assert "D" not in best, "the walk went past its bound"

    deeper = walk(chain, ["A"], 1.0, max_hops=4, floor=0.0)
    assert deeper["D"][1] == 4, "raising the bound did not reach further"


def test_direction_matters_a_dependency_is_not_symmetric():
    """out_edges[A] = [B] means B depends on A. An event at B must not reach A."""
    best = walk(g(A=["B"]), ["B"], 1.0)
    assert "A" not in best


def test_a_cycle_terminates():
    best = walk(g(A=["B"], B=["A"]), ["A"], 1.0)
    assert set(best) == {"A", "B"}
    assert best["A"][1] == 1


def test_a_company_reachable_two_ways_keeps_the_stronger_path():
    """A -> B(weak) -> D and A -> C(strong) -> D. D should score via C."""
    out = {"A": [("B", 0.1, 1.0), ("C", 0.9, 1.0)],
           "B": [("D", 1.0, 1.0)], "C": [("D", 1.0, 1.0)]}
    best = walk(out, ["A"], 1.0)
    assert best["D"][0] == pytest.approx(0.9 * prop.DECAY ** 2)


def test_a_weak_edge_is_dropped_below_the_floor():
    out = {"A": [("B", 0.001, 0.001)]}
    best = walk(out, ["A"], 1.0)
    assert "B" not in best, "a negligible path was kept"


def test_weight_and_confidence_both_count():
    out = {"A": [("B", 0.5, 0.5)]}
    best = walk(out, ["A"], 1.0)
    assert best["B"][0] == pytest.approx(0.5 * 0.5 * prop.DECAY)


def test_several_seeds_all_start_at_hop_one():
    best = walk({}, ["A", "B", "C"], 0.5)
    assert all(best[k] == (0.5, 1, []) for k in "ABC")


def test_a_bigger_event_reaches_further():
    """A company just under the floor for a small event clears it for a big one."""
    out = {"A": [("B", 0.09, 1.0)]}
    assert "B" not in walk(out, ["A"], 0.3)
    assert "B" in walk(out, ["A"], 1.0)


def test_the_path_records_how_we_got_there():
    """An exposure nobody can trace back is not evidence."""
    best = walk(g(A=["B"], B=["C"]), ["A"], 1.0)
    assert best["C"][2] == ["A", "B"]


def test_the_same_inputs_always_give_the_same_answer():
    out = {"A": [("B", 0.7, 0.9), ("C", 0.6, 0.8)],
           "B": [("D", 0.5, 0.7)], "C": [("D", 0.9, 0.9)]}
    first = walk(out, ["A"], 0.85)
    for _ in range(20):
        assert walk(out, ["A"], 0.85) == first


def test_an_empty_graph_reaches_only_its_seeds():
    assert set(walk({}, ["A"], 1.0)) == {"A"}


def test_no_seeds_reaches_nobody():
    """A 2021 event against a 2025 corpus. Zero is the correct answer."""
    assert walk(g(A=["B"]), [], 1.0) == {}


def test_a_seed_is_never_downgraded_by_a_longer_path_to_itself():
    best = walk(g(A=["B"], B=["A"]), ["A"], 1.0)
    assert best["A"][0] == 1.0 and best["A"][1] == 1


def test_a_hub_with_many_dependants_reaches_all_of_them():
    best = walk(g(A=[f"d{i}" for i in range(50)]), ["A"], 1.0)
    assert len([k for k in best if k.startswith("d")]) == 50


def test_the_constants_are_declared_not_fitted():
    assert 0 < prop.DECAY < 1
    assert prop.MAX_HOPS >= 2, "two hops is the minimum for anything to surprise anyone"
    assert 0 < prop.FLOOR < 1
