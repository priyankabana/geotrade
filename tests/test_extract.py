"""Regression tests for stage two, built from the audit.

Every case here is a real sentence from a real filing that the extractor once
got wrong, with the verdict we reached by reading it. They exist because each
of these fixes was expensive to find and would be cheap to undo.

Run: make test   (or: python3 -I -m pytest -q tests)
"""
import os, re, sys, pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import extract as ex


def _norm(n):
    """alias_norm as the database stores it: upper case, punctuation to spaces."""
    return " ".join(re.sub(r"[^A-Za-z0-9& ]", " ", n).upper().split())


def gaz(*names):
    """A gazetteer keyed the way extract.main builds it: alias_norm -> (id, ntokens)."""
    return {_norm(n): (f"id-{i}", len(_norm(n).split())) for i, n in enumerate(names)}


def run(sent, *names, filer=()):
    return ex.extract_sentence(sent, {f.upper() for f in filer}, gaz(*names))


def one(sent, *names, filer=()):
    out = run(sent, *names, filer=filer)
    assert len(out) == 1, f"expected exactly one claim, got {len(out)}: {out}"
    return out[0]


# ---------------------------------------------------------------- case matters

def test_lowercase_generic_phrase_is_not_a_company():
    """'financial institutions' in prose must not match Financial Institutions."""
    assert run("We provide services to financial institutions and our customers.",
               "Financial Institutions") == []


def test_capitalised_name_still_matches():
    c = one("Our largest customers are Applied Materials and others.", "Applied Materials")
    assert c["counterparty_entity_id"] == "id-0"


def test_sentence_initial_capital_is_not_proof_of_a_name():
    assert run("Coats protect the surface from corrosion for our customers.", "Coats") == []


def test_acronym_plural_is_not_a_company():
    """'ASICs' is an acronym. 'ASICS' is a shoe company."""
    assert run("Customers use our IP to design ASICs for AI workloads.", "Asics") == []


def test_all_caps_acronym_company_still_matches():
    c = one("Our brand partners include ASICS and New Balance among our customers.", "Asics")
    assert c["direction"] == "downstream"


def test_ampersand_does_not_break_a_name():
    """'&' carries no case information and must not veto the match."""
    c = one("Our customers include Deere & Company in North America.", "Deere & Company")
    assert c["counterparty_text"].lower().startswith("deere")


# ------------------------------------------------------------------- direction

def test_supplier_to_means_they_are_the_customer():
    """Adient is a supplier TO Mercedes, so Mercedes is the customer."""
    c = one("Adient is a supplier to premier automotive manufacturers, "
            "including Mercedes-Benz Group and others.", "Mercedes-Benz Group")
    assert c["direction"] == "downstream"
    assert c["relationship_class"] == "customer"


def test_our_suppliers_include_means_they_are_the_supplier():
    c = one("Our Company's key suppliers include Glencore International AG.", "Glencore")
    assert c["direction"] == "upstream"
    assert c["relationship_class"] == "supplier"


def test_customers_of_our_product_are_still_customers():
    """Regression: 'the principal customers OF OUR engines' must not invert."""
    c = one("The principal customers of our light-duty automotive engines are Stellantis.",
            "Stellantis")
    assert c["direction"] == "downstream"


def test_we_are_a_customer_of_them_does_invert():
    c = one("We are a customer of Taiwan Semiconductor for leading-edge nodes.",
            "Taiwan Semiconductor")
    assert c["direction"] == "upstream"


def test_tier_one_suppliers_are_buyers_for_a_component_vendor():
    c = one("We also partner with leading tier-one suppliers including Aptiv and others.",
            "Aptiv")
    assert c["direction"] == "downstream"


# --------------------------------------------------------------- not a mention

def test_negated_cue_is_not_a_cue():
    """'No supplier accounted for 10% or more' names nobody."""
    out = run("No supplier was individually significant, and Daimler AG "
              "accounted for 18 % of net sales.", "Daimler AG")
    assert out, "the customer disclosure itself must survive"
    assert all(c["relationship_class"] != "supplier" for c in out), out


def test_cue_used_as_a_modifier_is_not_a_cue():
    assert run("We actively manage the timing of our supplier payments to "
               "Verizon Communications Inc.", "Verizon Communications") == []


def test_executive_biography_is_not_a_dependency():
    assert run("Prior to this role, Mr. Nolan served as President of the Materials "
               "Group for Avery Dennison Corporation and our customers.",
               "Avery Dennison Corporation") == []


def test_social_media_is_not_a_dependency():
    assert run("We maintain Facebook and Instagram accounts where information "
               "relevant to customers is disseminated.", "Meta Platforms") == []


def test_share_buyback_is_not_a_dependency():
    assert run("Charter purchased from Liberty Broadband 3.8 million shares of "
               "Charter Class A common stock from our suppliers.",
               "Liberty Broadband") == []


def test_own_plant_is_not_a_counterparty():
    assert run("We produce caprolactam at our Hopewell plant for our customers.",
               "Hopewell Holdings") == []


def test_own_product_brand_is_not_a_counterparty():
    assert run("Net revenues from sales of Metro® vehicles to our customers grew.",
               "Metro") == []


def test_the_filer_is_never_its_own_counterparty():
    assert run("Our customers include Boeing.", "Boeing", filer=("Boeing",)) == []


# ----------------------------------------------------------------- percentages

def test_simple_percentage_is_attributed():
    c = one("Sales to General Motors Company (GM) were approximately 44 % of our "
            "consolidated net sales in 2025.", "General Motors Company")
    assert c["materiality_pct"] == 44.0
    assert "consolidated net sales" in (c["materiality_text"] or "")


def test_aggregate_total_is_not_attributed_to_one_member():
    """'top five customers collectively accounted for 57%' says nothing about one."""
    c = one("Our top five customers (including SoftBank Group) collectively accounted "
            "for approximately 57% of our total revenue.", "SoftBank Group")
    assert c["materiality_pct"] is None


def test_others_and_represented_is_an_aggregate():
    c = one("Our customers include Stellantis and many others and represented "
            "approximately 50% of our revenue in fiscal year 2025.", "Stellantis")
    assert c["materiality_pct"] is None


def test_figure_following_the_name_beats_one_preceding_it():
    """In 'Daimler 18% PACCAR 11%', PACCAR's number is 11."""
    out = run("Our significant customers: Daimler AG 18 % PACCAR Inc. 11 % of net sales.",
              "Daimler AG", "PACCAR Inc")
    got = {c["counterparty_text"].lower(): c["materiality_pct"] for c in out}
    assert got.get("paccar inc") == 11.0


def test_another_company_between_name_and_figure_blocks_attribution():
    out = run("Customers: Viasat represented the following percentages: Boeing 7.3 % "
              "of accounts receivable.", "Viasat", "Boeing")
    byname = {c["counterparty_text"].lower(): c["materiality_pct"] for c in out}
    assert byname.get("viasat") is None


def test_equity_stake_is_not_a_revenue_share():
    c = one("Our customer SAFRAN Group owns a 10% noncontrolling interest in the venture.",
            "SAFRAN Group")
    assert c["materiality_pct"] is None


def test_respectively_with_an_unresolvable_pair_withholds_rather_than_guesses():
    """Apple is absent from the gazetteer, so we cannot line the list up. Say nothing."""
    c = one("Direct sales to Apple and Qualcomm accounted for 29.8% and 11.1% of our "
            "net sales, respectively.", "Qualcomm")
    assert c["materiality_pct"] is None


def test_respectively_pairs_by_position_when_both_resolve():
    out = run("Thor Industries and Forest River accounted for approximately 58.4% and "
              "34.4%, respectively, of our new RV inventory.",
              "Thor Industries", "Forest River")
    got = {c["counterparty_text"].lower(): c["materiality_pct"] for c in out}
    assert got.get("thor industries") == 58.4
    assert got.get("forest river") == 34.4


def test_a_share_of_what_we_buy_points_upstream():
    out = run("Thor Industries and Forest River accounted for approximately 58.4% and "
              "34.4%, respectively, of our new RV inventory.",
              "Thor Industries", "Forest River")
    assert all(c["direction"] == "upstream" for c in out), out


# ------------------------------------------------------------------- integrity

def test_claims_never_carry_a_score_from_a_model():
    """Confidence is deterministic. Same sentence in, same number out, always."""
    s = "Sales to Ford Motor Company were approximately 15 % of our net sales."
    a = one(s, "Ford Motor Company")
    b = one(s, "Ford Motor Company")
    assert a["confidence"] == b["confidence"]
    assert 0.0 < a["confidence"] <= 0.97


def test_a_sentence_with_no_cue_yields_nothing():
    assert run("Boeing is headquartered in Arlington, Virginia.", "Boeing") == []
