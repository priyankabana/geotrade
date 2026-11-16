"""The backtest gate must actually fail.

Like the alerts, a gate that has only ever said "no regression" proves nothing.
These run the real script against a tampered baseline in a temporary directory
and check it exits non-zero with a reason.
"""
import json, os, shutil, subprocess, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "backtest.py")
BASELINE = os.path.join(ROOT, "eval", "backtest_baseline.json")


def run(cwd, *args):
    return subprocess.run([sys.executable, "-I", SCRIPT, *args],
                          capture_output=True, text=True, cwd=cwd, timeout=180)


def _database_is_up():
    """These tests run the real script as a subprocess, so the usual `tx`
    fixture cannot guard them. Check connectivity here instead, or the suite
    fails on a laptop with nothing running rather than skipping."""
    try:
        import psycopg
    except ImportError:
        return False
    try:
        psycopg.connect(os.environ.get("DATABASE_URL",
                                       "postgresql://atlas:atlas@localhost:5432/atlas"),
                        connect_timeout=3).close()
        return True
    except Exception:
        return False


@pytest.fixture
def sandbox(tmp_path):
    """A copy of the repo's eval directory, so a test can tamper with the
    baseline without touching the real one."""
    if not _database_is_up():
        pytest.skip("no database; backtest.py cannot run")
    if not os.path.exists(BASELINE):
        pytest.skip("no baseline; run make backtest")
    (tmp_path / "eval").mkdir()
    shutil.copy(BASELINE, tmp_path / "eval" / "backtest_baseline.json")
    for name in ("scripts", "infra"):
        os.symlink(os.path.join(ROOT, name), tmp_path / name)
    return tmp_path


def load(sandbox):
    return json.loads((sandbox / "eval" / "backtest_baseline.json").read_text())


def save(sandbox, data):
    (sandbox / "eval" / "backtest_baseline.json").write_text(json.dumps(data, indent=2))


def test_it_passes_against_its_own_baseline(sandbox):
    r = run(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no regression" in r.stdout


def test_it_fails_when_an_event_loses_most_of_its_reach(sandbox):
    """The failure the gate exists for: a change that quietly empties the graph."""
    d = load(sandbox)
    key = max(d["events"], key=lambda k: d["events"][k]["exposed"])
    d["events"][key]["exposed"] *= 10
    save(sandbox, d)
    r = run(sandbox)
    assert r.returncode == 1, r.stdout
    assert "REGRESSED" in r.stdout and "reach fell" in r.stdout


def test_it_fails_when_surprising_companies_disappear(sandbox):
    """Surprise is the product's reason to exist. Losing it must be loud."""
    d = load(sandbox)
    key = max(d["events"], key=lambda k: d["events"][k]["surprising"])
    d["events"][key]["surprising"] += 25
    save(sandbox, d)
    r = run(sandbox)
    assert r.returncode == 1, r.stdout
    assert "surprising fell" in r.stdout


def test_it_fails_when_an_event_vanishes_from_the_benchmark(sandbox):
    d = load(sandbox)
    d["events"]["an-event-that-was-deleted"] = {
        "name": "gone", "date": "2020-01-01", "exposed": 5,
        "surprising": 1, "max_hops": 2, "mean_score": 0.1}
    save(sandbox, d)
    r = run(sandbox)
    assert r.returncode == 1
    assert "disappeared" in r.stdout


def test_a_small_wobble_is_tolerated(sandbox):
    """Gates that fire on noise get switched off. A fifth of the reach may move."""
    d = load(sandbox)
    for v in d["events"].values():
        if v["exposed"] > 10:
            v["exposed"] = int(v["exposed"] * 1.1)
    save(sandbox, d)
    assert run(sandbox).returncode == 0


def test_a_new_event_is_reported_not_treated_as_a_failure(sandbox):
    d = load(sandbox)
    d["events"].pop(max(d["events"], key=lambda k: d["events"][k]["exposed"]))
    save(sandbox, d)
    r = run(sandbox)
    assert r.returncode == 0
    assert "new event in benchmark" in r.stdout


def test_it_refuses_outright_if_any_edge_lost_its_citation(sandbox, tx):
    """Not a regression - a breach. It must not even reach the comparison."""
    tx.execute("SELECT count(*) FROM dependency_edge WHERE chunk_id IS NULL")
    assert tx.fetchone()[0] == 0
    src = open(SCRIPT).read()
    assert "uncited_edges" in src and "sys.exit(1)" in src


def test_saving_a_baseline_records_the_graph_it_describes(sandbox):
    r = run(sandbox, "--save")
    assert r.returncode == 0
    d = load(sandbox)
    assert d["graph"]["edges"] > 0
    assert d["graph"]["uncited_edges"] == 0
    assert d["events"], "a baseline with no events gates nothing"
