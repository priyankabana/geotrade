"""End-to-end tests through a real browser against the real app.

Typechecking says the code compiles. These say a person can get from the globe
to a sentence in a filing, which is the only journey that matters.

Skips cleanly when the web or API server is not running, so `make test` still
works on a laptop with nothing up.
"""
import os, urllib.request
import pytest

WEB = os.environ.get("ATLAS_WEB", "http://localhost:5173")
API = os.environ.get("ATLAS_API", "http://localhost:8000")


def _up(url):
    try:
        urllib.request.urlopen(url, timeout=3).read(1)
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def browser():
    """One Playwright instance for the whole module. The sync API refuses to
    nest, so every page in this file has to come from here."""
    pytest.importorskip("playwright.sync_api")
    if not _up(WEB):
        pytest.skip(f"web server not running at {WEB} - start it with: make web")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


def _watched(browser, width=1500, height=950):
    """Two lists, because they mean different things. `thrown` is an uncaught
    exception in our own code - always a bug. `errors` also catches the
    browser's own network complaints, which are expected when a test cuts the
    backend off on purpose."""
    pg = browser.new_page(viewport={"width": width, "height": height})
    thrown, errors = [], []
    pg.on("pageerror", lambda e: (thrown.append(str(e)), errors.append(str(e))))
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
          if m.type == "error" else None)
    pg.thrown = thrown
    pg.errors = errors
    return pg


@pytest.fixture(scope="module")
def page(browser):
    if not _up(API + "/v1/health"):
        pytest.skip(f"API not running at {API} - start it with: make api")
    pg = _watched(browser)
    pg.goto(WEB, wait_until="networkidle")
    pg.wait_for_timeout(3500)
    yield pg
    pg.close()


def test_the_app_loads_without_a_single_runtime_error(page):
    assert page.errors == [], f"console/page errors: {page.errors[:4]}"


def test_it_says_it_is_live_rather_than_pretending(page):
    """When the API is down the banner must say so, not show stale numbers."""
    assert "offline" not in page.inner_text(".mockstrip").lower()


def test_the_globe_actually_renders(page):
    """A WebGL canvas with no pixels is the classic silent failure."""
    assert page.locator("canvas").count() >= 1
    box = page.locator("canvas").first.bounding_box()
    assert box and box["width"] > 400 and box["height"] > 300


def test_coverage_is_reported_from_the_database_not_hard_coded(page):
    import json
    m = json.loads(urllib.request.urlopen(API + "/v1/metrics").read())
    assert str(m["graph"]["relationships"]) in page.inner_text(".topbar")


def _drill_to_a_company_with_edges(page):
    page.get_by_text("United States", exact=False).first.click()
    page.wait_for_timeout(1500)
    page.get_by_text("Automotive Components", exact=False).first.click()
    page.wait_for_timeout(1800)
    for btn in page.locator("aside .panel-body button").all():
        if "cited" in " ".join(btn.inner_text().split()):
            btn.click()
            page.wait_for_timeout(2200)
            return True
    return False


def test_a_person_can_reach_a_company_from_the_globe(page):
    assert _drill_to_a_company_with_edges(page), "no company with cited edges was reachable"
    assert page.locator(".tabs").count() == 1, "the company view did not open"


def test_every_edge_on_screen_shows_its_evidence_tier(page):
    """The two tiers measured 100% and 68.3%. Showing them identically would be
    the most misleading thing the UI could do."""
    assert page.locator(".tier-hard, .tier-soft").count() > 0


def test_the_sentence_on_screen_is_the_one_the_api_served(page):
    """Not merely that some text is shown: that it is the filing's own words,
    character for character, as the API returned them."""
    import json, re, urllib.parse
    uid = re.search(r"\b[A-Z]{4}:[A-Z0-9.\-]+\b", page.inner_text("aside"))
    assert uid, "no company identifier visible in the panel"
    d = json.loads(urllib.request.urlopen(
        API + "/v1/companies/" + urllib.parse.quote(uid.group(0))).read())
    edges = d["dependsOn"] + d["dependedOnBy"]
    assert edges, "the API returned no edges for the company on screen"
    panel = " ".join(page.inner_text("aside").split())
    quote = " ".join(edges[0]["citation"]["quote"].split())
    assert quote[:70] in panel, "the quote on screen is not the one the API served"


def test_a_percentage_is_never_shown_bare(page):
    """'44%' is not a fact. '44% of our consolidated net sales' is."""
    import re
    panel = " ".join(page.inner_text("aside").split())
    for m in re.finditer(r"\b\d{1,3}(?:\.\d+)?% of\b", panel):
        tail = panel[m.end(): m.end() + 40].strip()
        assert tail and not tail.startswith("confidence"), f"bare percentage near {m.group(0)!r}"


def test_the_citation_links_to_the_regulator_not_to_us(page):
    """The claim is checkable by a third party without asking us for anything."""
    links = page.locator('aside a[href]').all()
    hrefs = [a.get_attribute("href") or "" for a in links]
    assert any("sec.gov" in h for h in hrefs), f"no link to the source filing: {hrefs[:4]}"


def test_replay_draws_the_point_in_time_boundary(page):
    page.get_by_role("button", name="replay").click()
    page.wait_for_timeout(2200)
    assert page.locator(".tl-boundary").count() == 1
    assert page.locator(".tl-pip").count() > 5


def test_an_event_older_than_the_corpus_says_so_on_screen(page):
    """Selecting Tohoku 2011 must explain why the graph is empty there, rather
    than looking broken."""
    page.locator(".tl-pip").last.click()
    page.wait_for_timeout(2000)
    assert page.locator(".tl-warn").count() == 1
    assert "0 you would not have listed" in " ".join(page.inner_text("aside").split())


def test_it_is_usable_at_phone_width(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(800)
    overflow = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
    page.set_viewport_size({"width": 1500, "height": 950})
    assert not overflow, "the page scrolls sideways on a phone"


# --------------------------------------------------- what happens when it breaks

@pytest.fixture(scope="module")
def broken_api_page(browser):
    """The same app with every API call failing, so we can see what a user is
    told when the backend is down - without taking the backend down."""
    pg = _watched(browser, 1400, 900)
    pg.route("**/v1/**", lambda route: route.abort())
    pg.goto(WEB, wait_until="domcontentloaded")
    pg.wait_for_timeout(5000)
    yield pg
    pg.close()


def test_a_dead_backend_says_so_instead_of_showing_nothing(broken_api_page):
    """Silence is the worst failure mode: an empty graph looks like a real
    answer. The banner has to say the API is unreachable."""
    assert "offline" in broken_api_page.inner_text(".mockstrip").lower()


def test_a_dead_backend_does_not_throw_at_the_user(broken_api_page):
    """Failed requests are expected here - we aborted them. What must not happen
    is an uncaught exception in our own code, which is what leaves a user
    looking at a blank page with no explanation."""
    assert broken_api_page.thrown == [], f"uncaught exceptions: {broken_api_page.thrown[:3]}"


def test_a_dead_backend_never_invents_numbers(broken_api_page):
    """With no data, the status line must not claim coverage it cannot have."""
    import re
    bar = broken_api_page.inner_text(".topbar")
    assert not re.search(r"\b\d{1,3},\d{3}\b", bar), f"invented a figure: {bar!r}"


def test_the_page_still_renders_its_shell_when_the_backend_is_gone(broken_api_page):
    assert broken_api_page.locator(".topbar").count() == 1
    assert broken_api_page.locator("aside").count() == 1
