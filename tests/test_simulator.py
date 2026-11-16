"""The simulator runs the propagation walk a second time, in TypeScript.

Two implementations of one algorithm is a standing invitation to drift, and the
drift would be invisible: the simulator would keep producing plausible numbers
that were not Atlas's numbers. These tests are the thing that makes the second
implementation safe to have.

Skips cleanly when the web or API server is not running.
"""
import json
import os
import sys
import urllib.request

import pytest

# Same convention the other tests use: scripts/ is not a package.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

WEB = os.environ.get("ATLAS_WEB", "http://localhost:5173")
API = os.environ.get("ATLAS_API", "http://localhost:8000")

# Mirrors the walk in Simulator.tsx. Kept here rather than read out of the
# bundle because the point is to compare two independent transcriptions.
JS_WALK = """([seedUid, sev]) => {
  const g = window.__atlasGraph
  if (!g) return null
  const out = new Map()
  for (const e of g.edges) {
    const a = out.get(e.to); if (a) a.push(e); else out.set(e.to, [e])
  }
  const best = new Map([[seedUid, {score: sev, hops: 1}]])
  for (let hop = 2; hop <= g.walk.maxHops; hop++) {
    const next = []
    for (const [uid, cur] of [...best.entries()]) {
      if (cur.hops !== hop - 1) continue
      for (const e of out.get(uid) ?? []) {
        const score = cur.score * e.weight * e.confidence * g.walk.decay
        if (score < g.walk.floor) continue
        const held = best.get(e.from)
        if (!held || score > held.score) next.push([e.from, score, hop])
      }
    }
    for (const [uid, score, hops] of next) {
      const held = best.get(uid)
      if (!held || score > held.score) best.set(uid, {score, hops})
    }
  }
  best.delete(seedUid)
  return Object.fromEntries([...best.entries()]
    .map(([k, v]) => [k, [Math.round(v.score * 1e6) / 1e6, v.hops]]))
}"""


def _up(url):
    try:
        urllib.request.urlopen(url, timeout=3).read(1)
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def graph():
    if not _up(API + "/v1/health"):
        pytest.skip(f"API not running at {API}")
    return json.loads(urllib.request.urlopen(API + "/v1/graph", timeout=20).read())


def test_the_endpoint_publishes_the_walk_constants(graph):
    """The simulator takes decay and the hop bound from the server rather than
    hard-coding them, so a change in propagate.py cannot leave it behind."""
    from propagate import DECAY, FLOOR, MAX_HOPS
    assert graph["walk"] == {"maxHops": MAX_HOPS, "decay": DECAY, "floor": FLOOR,
                             "scorerVersion": "walk-1.1"}


def test_edges_point_from_the_discloser_to_the_disclosed(graph):
    """Direction is the easiest thing to get backwards here, and getting it
    backwards would make the simulator confidently wrong rather than broken."""
    assert graph["edges"], "no edges published"
    for e in graph["edges"][:50]:
        assert e["from"] != e["to"]
        assert e["citation"]["quote"], "an edge without its sentence"
        assert 0 < e["confidence"] <= 1
        assert 0 < e["weight"] <= 1


@pytest.fixture(scope="module")
def page(graph):
    pytest.importorskip("playwright.sync_api")
    if not _up(WEB):
        pytest.skip(f"web server not running at {WEB}")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.goto(WEB, wait_until="networkidle")
        pg.get_by_role("button", name="simulate", exact=True).click()
        pg.wait_for_timeout(3000)
        yield pg
        b.close()


def _seeds(graph, n=3):
    out = {}
    for e in graph["edges"]:
        out.setdefault(e["to"], []).append((e["from"], e["weight"], e["confidence"]))
    ranked = sorted(((len(v), k) for k, v in out.items()), reverse=True)
    return out, [k for _, k in ranked[:n]]


@pytest.mark.parametrize("severity", [0.8, 0.45])
def test_the_browser_walk_matches_the_python_walk(graph, page, severity):
    """Same seeds, same severity, same companies, same scores to six places."""
    from propagate import walk
    out, seeds = _seeds(graph)
    for seed in seeds:
        expected = {k: [round(v[0], 6), v[1]]
                    for k, v in walk(out, [seed], severity).items() if k != seed}
        got = page.evaluate(JS_WALK, [seed, severity])
        assert got is not None, "the simulator never published its graph"
        got = {k: [v[0], v[1]] for k, v in got.items()}
        assert got == expected, f"walk disagrees for {seed} at severity {severity}"


def test_the_simulator_reaches_someone_and_cites_why(page):
    """A simulator that renders an empty list every time is not working."""
    page.wait_for_timeout(500)
    assert page.locator(".sim .sig").count() > 0, "no company was reached"
    assert page.locator(".sim blockquote").count() > 0, "a hop with no filed sentence"
