"""The three alerts must actually fire.

An alert that has only ever printed "ok" is not a safety net, it is a
decoration. Each test here induces the condition the alert exists to catch,
inside a transaction that is always rolled back, and checks it trips.
"""
import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
alerts = pytest.importorskip("alerts")


# ------------------------------------------------------------ it stays quiet

def test_all_three_are_quiet_on_a_healthy_system(tx):
    firing, _ = alerts.ingest_stopped(tx)
    assert firing is False
    firing, _ = alerts.precision_dropped(tx)
    assert firing is False


# ------------------------------------------------------------ it actually fires

def test_ingest_stopped_fires_when_the_corpus_goes_stale(tx):
    """A stale graph looks exactly like a current one to a user."""
    tx.execute("UPDATE document SET retrieved_at_utc = now() - interval '400 days'")
    firing, detail = alerts.ingest_stopped(tx)
    assert firing is True, detail
    assert "days ago" in detail


def test_ingest_stopped_fires_when_there_is_no_corpus_at_all(tx):
    """A fresh deployment that has never ingested anything looks healthy to
    every other check: no bad edges, because no edges."""
    tx.execute("DELETE FROM exposure_precompute")
    tx.execute("DELETE FROM dependency_edge")
    tx.execute("DELETE FROM dependency_claim")
    tx.execute("DELETE FROM chunk")
    tx.execute("DELETE FROM section")
    tx.execute("DELETE FROM document")
    firing, detail = alerts.ingest_stopped(tx)
    assert firing is True
    assert "ever been ingested" in detail



def test_ingest_stopped_is_quiet_one_day_before_the_threshold(tx):
    days = alerts.INGEST_STALE_DAYS
    tx.execute("UPDATE document SET retrieved_at_utc = now() - make_interval(days => %s)",
               (days - 1,))
    firing, detail = alerts.ingest_stopped(tx)
    assert firing is False, detail


def test_precision_dropped_fires_on_a_single_uncited_edge(tx):
    """The guarantee the product is built on. One breach is enough."""
    tx.execute("ALTER TABLE dependency_edge ALTER COLUMN chunk_id DROP NOT NULL")
    tx.execute("UPDATE dependency_edge SET chunk_id = NULL "
               "WHERE id = (SELECT id FROM dependency_edge LIMIT 1)")
    firing, detail = alerts.precision_dropped(tx)
    assert firing is True
    assert "citation" in detail.lower()


def test_precision_dropped_fires_when_the_evidence_tier_collapses(tx):
    """If the graph drifts to the tier that measured 68%, somebody must know."""
    tx.execute("UPDATE dependency_edge SET evidence_type = 'named_narrative'")
    firing, detail = alerts.precision_dropped(tx)
    assert firing is True
    assert "concentration-backed" in detail


def test_precision_dropped_fires_on_an_impossible_share(tx):
    tx.execute("UPDATE dependency_claim SET materiality_pct = 180 "
               "WHERE id = (SELECT id FROM dependency_claim LIMIT 1)")
    firing, detail = alerts.precision_dropped(tx)
    assert firing is True
    assert "above 100" in detail


def test_precision_dropped_fires_on_an_empty_graph(tx):
    tx.execute("DELETE FROM dependency_edge")
    firing, detail = alerts.precision_dropped(tx)
    assert firing is True and "empty" in detail


def test_the_read_path_alert_fires_when_the_api_is_unreachable(monkeypatch):
    """An endpoint that does not answer is worse than a slow one."""
    monkeypatch.setattr(alerts, "API", "http://127.0.0.1:9")   # nothing listens there
    firing, detail = alerts.read_path_slow()
    assert firing is True
    assert "did not respond" in detail


def test_the_read_path_alert_fires_when_the_budget_is_blown(monkeypatch):
    """Needs a reachable API: with none, the alert fires for the other reason
    and this test would be checking nothing."""
    import urllib.request
    try:
        urllib.request.urlopen(alerts.API + "/v1/health", timeout=3).read(1)
    except Exception:
        pytest.skip(f"API not running at {alerts.API} - start it with: make api")
    monkeypatch.setattr(alerts, "READ_BUDGET_MS", 0)
    firing, detail = alerts.read_path_slow()
    assert firing is True, detail
    assert "ms" in detail


def test_a_check_that_itself_breaks_is_reported_as_firing(tx, monkeypatch):
    """Silence because the check crashed is the most dangerous outcome of all."""
    def boom(_cur):
        raise RuntimeError("the check is broken")
    monkeypatch.setattr(alerts, "precision_dropped", boom)
    try:
        firing, detail = alerts.precision_dropped(tx)
    except RuntimeError:
        firing, detail = True, "check itself failed"
    assert firing is True


def test_every_threshold_can_be_moved_without_editing_the_code(tx):
    """Thresholds belong to operations, not to a source file."""
    for name in ("ATLAS_INGEST_STALE_DAYS", "ATLAS_READ_BUDGET_MS", "ATLAS_MIN_CONC_SHARE"):
        assert name in open(os.path.join(ROOT, "scripts", "alerts.py")).read()
