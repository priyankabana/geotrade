"""The evaluation's sampler.

If this is biased or irreproducible, every precision number we publish is
worthless - so it is worth more scrutiny than almost anything else in the repo.

Pure - no database.
"""
import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sp = pytest.importorskip("sample_pairs")

draw = sp.stratified_sample


def pop(n_conc=28, n_narr=179):
    """A population shaped like the real one: a small strong tier, a large
    weak one. Row index 3 is the evidence type, as in the real query."""
    return ([("f%d" % i, "t%d" % i, "customer_concentration", "named_concentration")
             for i in range(n_conc)]
            + [("f%d" % i, "t%d" % i, "customer_concentration", "named_narrative")
               for i in range(n_conc, n_conc + n_narr)])


def test_the_same_seed_always_draws_the_same_sample():
    rows = pop()
    first = draw(rows, 80, 4242)[2]
    for _ in range(10):
        assert draw(rows, 80, 4242)[2] == first


def test_a_different_seed_draws_a_different_sample():
    rows = pop()
    a = {r[0] for r in draw(rows, 80, 1)[2]}
    b = {r[0] for r in draw(rows, 80, 2)[2]}
    assert a != b, "the seed does nothing"


def test_it_draws_the_number_asked_for():
    assert len(draw(pop(), 80, 7)[2]) == 80


def test_nothing_is_sampled_twice():
    """A duplicate would be judged twice and counted twice."""
    s = draw(pop(), 80, 7)[2]
    assert len(s) == len({r[0] for r in s})


def test_every_sampled_row_came_from_the_population():
    """The sampler must never invent a row to judge."""
    rows = pop()
    assert all(r in rows for r in draw(rows, 80, 7)[2])


def test_the_two_tiers_are_kept_in_proportion():
    """28 of 207 is 13.5%, so a sample of 80 should hold about 11 of them.
    A plain random draw could easily return two and say nothing about either
    class."""
    rows = pop(28, 179)
    s = draw(rows, 80, 7)[2]
    got = sum(1 for r in s if r[3] == "named_concentration")
    assert 9 <= got <= 13, f"{got} concentration rows in a sample of 80"


def test_proportion_holds_at_other_sizes():
    rows = pop(28, 179)
    for n in (20, 40, 120):
        s = draw(rows, n, 11)[2]
        got = sum(1 for r in s if r[3] == "named_concentration")
        expect = n * 28 / 207
        assert abs(got - expect) <= 2, f"n={n}: {got} vs about {expect:.1f}"


def test_asking_for_more_than_exists_returns_everything_once():
    rows = pop(5, 5)
    s = draw(rows, 500, 3)[2]
    assert len(s) == 10 and len({r[0] for r in s}) == 10


def test_an_empty_population_does_not_crash():
    assert draw([], 50, 3)[2] == []


def test_a_population_of_one_tier_only_still_works():
    rows = pop(0, 30)
    s = draw(rows, 10, 3)[2]
    assert len(s) == 10
    assert all(r[3] == "named_narrative" for r in s)


def test_the_sample_is_shuffled_not_tier_ordered():
    """If every concentration row came first, a judge reading top to bottom
    would form an impression of the strong tier before seeing the weak one."""
    rows = pop(40, 40)
    s = draw(rows, 60, 5)[2]
    tiers = [r[3] == "named_concentration" for r in s]
    first_weak = tiers.index(False)
    assert any(tiers[first_weak:]), "all the strong rows are at the front"


def test_the_draw_does_not_favour_the_front_of_the_population():
    """Order the database returns rows in must not influence who gets judged.
    Across many seeds, each row should be drawn about equally often."""
    rows = pop(0, 100)
    counts = {r[0]: 0 for r in rows}
    for seed in range(300):
        for r in draw(rows, 10, seed)[2]:
            counts[r[0]] += 1
    lo, hi = min(counts.values()), max(counts.values())
    assert lo > 0, "some rows can never be drawn"
    assert hi < lo * 4, f"draw is lopsided: {lo}..{hi}"


def test_the_sample_is_written_before_any_judging():
    """The ordering that stops a judge quietly reshaping the set. Checked in
    the source, because it is a property of the procedure, not the output."""
    src = open(os.path.join(ROOT, "scripts", "sample_pairs.py")).read()
    assert "BEFORE any judging" in src or "before" in src.lower()
    assert src.index("stratified_sample(") < src.index('open(out, "w")')


def test_the_historical_audit_files_are_never_the_default_target():
    """eval/pairs.txt is the only record of the 62.5% baseline. make sample
    overwrote it once already."""
    src = open(os.path.join(ROOT, "scripts", "sample_pairs.py")).read()
    assert '"eval/pairs.txt"' not in src
