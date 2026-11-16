"""Headlines are only useful if they are about the company they are filed under.

GDELT matches the article body, so a query for a company name returns a great
deal that merely mentions it. A page of news where some rows are about a
different company is worse than a page with no news, because the reader cannot
tell which rows to believe - and that is the same failure mode the extractor
guards against with its own filters.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from ingest_company_news import about, build_query, clean


@pytest.mark.parametrize("headline,name,ticker", [
    ("Advanced Micro Devices (NASDAQ: AMD) Stock Price Down 8.1", "Advanced Micro Devices", "AMD"),
    ("Cerence posts a wider quarterly loss", "Cerence Inc", "CRNC"),
    ("NVDA: Nvidia Boss Jensen Huang Steps Down", "NVIDIA", "NVDA"),
    ("Aptiv raises full-year guidance", "Aptiv PLC", "APTV"),
])
def test_a_headline_naming_the_company_is_kept(headline, name, ticker):
    assert about(headline, name, ticker)


@pytest.mark.parametrize("headline,name,ticker", [
    # All of these came back from a real query for Advanced Micro Devices.
    ("On Wall Street, stocks sway as market aims for a winning week", "Advanced Micro Devices", "AMD"),
    ("Fallout from the Nvidia scandal may dampen the exuberance", "Advanced Micro Devices", "AMD"),
    ("英偉達晶片詐騙案 星洲再起訴1男子", "Advanced Micro Devices", "AMD"),
    ("", "Cerence", "CRNC"),
])
def test_a_headline_that_merely_mentions_it_is_dropped(headline, name, ticker):
    assert not about(headline, name, ticker)


def test_the_ticker_must_be_cased_as_a_ticker():
    """Three-letter tickers collide with ordinary words constantly. 'arm' in a
    sentence is a body part; 'ARM' is a company."""
    assert about("ARM beats expectations on royalty revenue", "Arm Holdings", "ARM")
    assert not about("he broke his arm in the warehouse", "Arm Holdings", "ARM")


def test_legal_forms_are_stripped_from_the_query():
    """Outlets write the short name, so querying the legal one finds less."""
    assert clean("Cerence Inc") == "Cerence"
    assert clean("Aptiv PLC") == "Aptiv"
    assert "Holdings" not in clean("Credo Technology Group Holding")


def test_a_name_that_is_an_ordinary_word_is_not_queried_bare():
    """'Apple' alone returns the fruit, the record label and the phone."""
    q = build_query("Apple Inc", "AAPL")
    assert q and "AAPL" in q, "a generic name must be disambiguated by its ticker"
    assert build_query("Shell plc", None) is None, "no ticker, no safe query"


def test_the_stored_rows_are_about_their_company(db):
    """The filter is applied at write time; this checks the table agrees."""
    cur = db.cursor()
    cur.execute("SELECT to_regclass('public.company_news')")
    if not cur.fetchone()[0]:
        pytest.skip("company_news not migrated")
    cur.execute("""SELECT n.headline, e.common_name, li.ticker
                   FROM company_news n
                   JOIN entity e ON e.id = n.entity_id
                   LEFT JOIN entity_listing li ON li.entity_id = e.id AND li.is_primary
                   LIMIT 400""")
    rows = cur.fetchall()
    if not rows:
        pytest.skip("no headlines ingested yet")
    off = [(h, who) for h, who, tick in rows if not about(h, who, tick)]
    assert not off, f"{len(off)} stored headlines are not about their company: {off[:3]}"
