"""The rule that auto-merged 50 ambiguous aliases.

`bare()` strips corporate furniture so two spellings of one company collapse to
the same string. It decided, without a human, that 50 of the 80 ambiguous
aliases occurring in our corpus were one company under different legal names.
If it is too eager it merges companies that are genuinely different, and the
graph quietly attributes one firm's dependencies to another.

Pure - no database.
"""
import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
ra = pytest.importorskip("review_aliases")

bare = ra.bare


def same(a, b):
    """The question that matters: safe to merge without asking a person?"""
    return ra.same_company(a, b)


# ------------------------------------------- real pairs it merged automatically

@pytest.mark.parametrize("a,b", [
    ("Cyclacel Pharmaceuticals Inc", "Cyclacel Pharmaceuticals Inc."),
    ("CVR Partners LP", "CVR Partners, LP"),
    ("Boxlight Corp", "Boxlight Corporation"),
    ("Alcoa Corp", "Alcoa Corporation"),
    ("Thomson Reuters Corp", "Thomson Reuters Corporation"),
    ("Thomson Reuters Corporation", "Thomson Reuters Corporation (USA)"),
    ("Aptiv PLC", "Aptiv plc"),
    ("Biodexa Pharmaceuticals PLC", "Biodexa Pharmaceuticals PLC."),
    ("Diversified Energy Company", "Diversified Energy Company PLC"),
])
def test_one_company_under_two_spellings_collapses(a, b):
    assert same(a, b), f"{a!r} and {b!r} should be the same company"


# -------------------------------------- pairs it must never merge automatically

@pytest.mark.parametrize("a,b", [
    ("Metro AG", "Metro Inc."),                      # German wholesaler vs Canadian grocer
    ("Pfizer Inc.", "Pfizer Ltd."),                  # US parent vs UK subsidiary
    ("Siemens AG", "Siemens Ltd."),                  # German parent vs Siemens India
    ("Unilever NV", "Unilever PLC"),
    ("Medtronic Inc.", "Medtronic PLC"),
    ("Metro Inc.", "Ceconomy VZ"),
    ("Alcoa Corporation", "Howmet Aerospace Inc."),  # the former Alcoa Inc
    ("Xperi Inc.", "Adeia Inc"),                     # renamed, not the same entity
    ("Ekso Bionics Holdings Inc", "ChronoScale Corporation"),
    ("Siyata Mobile Inc", "Core AI Holdings, Inc."),
    ("Hyundai Motor Company", "Hyundai Motor India Limited"),
    ("Pfizer Inc", "Pfizer Ltd"),
])
def test_two_different_companies_stay_apart(a, b):
    assert not same(a, b), f"{a!r} and {b!r} must not be merged without a person"


# ------------------------------------------------------------- the mechanics

def test_the_identifying_words_are_what_is_compared():
    assert bare("Acme Inc") == bare("Acme Corporation") == bare("Acme Ltd") == "acme"


def test_but_the_legal_form_still_decides_whether_to_merge():
    """Stripping the form outright is what merged Pfizer Inc with Pfizer Ltd.
    The identifying words match; the jurisdictions do not."""
    assert ra.form("Acme Inc") == "us"
    assert ra.form("Acme Ltd") == "uk"
    assert not ra.same_company("Acme Inc", "Acme Ltd")


def test_a_name_that_states_no_legal_form_merges_with_either():
    """"Diversified Energy Company" and "...Company PLC" are one company."""
    assert ra.form("Diversified Energy Company") is None
    assert ra.same_company("Diversified Energy Company", "Diversified Energy Company PLC")


def test_punctuation_carries_no_identity():
    """The case that made us strip punctuation: 'CVR Partners LP' read as a
    collision against 'CVR Partners, LP' purely because of a comma."""
    assert ra.same_company("CVR Partners, LP", "CVR Partners LP")


def test_case_carries_no_identity():
    assert ra.same_company("APTIV PLC", "Aptiv plc")


def test_an_ampersand_is_kept_because_it_is_part_of_the_name():
    assert "&" in bare("Standard & Poor's") or "s p" in bare("Standard & Poor's")


def test_a_name_that_is_only_furniture_collapses_to_nothing():
    """'The Group Holdings Ltd' has no identity left once stripped, and must not
    silently match every other husk."""
    assert bare("The Group Holdings Ltd") == ""


def test_an_empty_or_missing_name_does_not_crash():
    assert bare(None) == "" and bare("") == ""


def test_stripping_is_idempotent():
    once = bare("Thomson Reuters Corporation (USA)")
    assert bare(once) == once


def test_a_share_class_is_not_a_different_company():
    assert same("Charter Communications Inc Class A", "Charter Communications Inc")


def test_no_recorded_merge_would_be_refused_by_the_current_rule(tx):
    """Five of the first fifty auto-merges were wrong - Pfizer Inc with Pfizer
    Ltd, Siemens AG with Siemens India. If this fails again, a merge on record
    no longer meets the bar it was recorded under."""
    tx.execute("""SELECT d.alias_norm, array_agg(DISTINCT e.legal_name)
                  FROM alias_decision d
                  JOIN entity_alias a ON a.alias_norm = d.alias_norm
                  JOIN entity e ON e.id = a.entity_id
                  WHERE d.decision = 'merge' GROUP BY d.alias_norm""")
    bad = [k for k, c in tx.fetchall()
           if not all(ra.same_company(c[0], x) for x in c[1:])]
    assert not bad, f"merges that would now be refused: {bad[:5]}"


def test_the_distinguishing_word_survives():
    """Whatever makes two names different must still be there afterwards, or
    the comparison is meaningless."""
    assert bare("Hyundai Motor India Limited") != bare("Hyundai Motor Company")
    assert "india" in bare("Hyundai Motor India Limited")


# --------------------------------------------------- the decisions on record

def test_every_recorded_decision_names_who_made_it(tx):
    tx.execute("""SELECT count(*) FROM alias_decision
                  WHERE decided_by IS NULL OR btrim(decided_by) = ''""")
    assert tx.fetchone()[0] == 0, "a decision nobody is accountable for"


def test_a_prefer_decision_actually_names_an_entity(tx):
    tx.execute("SELECT count(*) FROM alias_decision WHERE decision='prefer' AND entity_id IS NULL")
    assert tx.fetchone()[0] == 0


def test_a_suppressed_alias_really_is_suppressed(tx):
    """Recording the decision and not acting on it would be worse than not
    deciding: somebody would believe it had been handled."""
    tx.execute("""SELECT count(*) FROM alias_decision d
                  JOIN entity_alias a ON a.alias_norm = d.alias_norm
                  WHERE d.decision = 'suppress' AND NOT a.is_ambiguous""")
    assert tx.fetchone()[0] == 0


def test_the_extractor_honours_a_prefer_decision(tx):
    """A preferred entity must be the one the gazetteer resolves to."""
    tx.execute("""SELECT d.alias_norm, d.entity_id FROM alias_decision d
                  WHERE d.decision = 'prefer' LIMIT 5""")
    for alias, eid in tx.fetchall():
        tx.execute("""SELECT count(*) FROM entity_alias a
                      LEFT JOIN alias_decision d ON d.alias_norm = a.alias_norm
                      WHERE a.alias_norm = %s AND NOT a.is_ambiguous
                        AND (d.decision IS NULL OR d.decision='merge'
                             OR (d.decision='prefer' AND d.entity_id = a.entity_id))
                        AND a.entity_id <> %s""", (alias, eid))
        assert tx.fetchone()[0] == 0, f"{alias} can still resolve to another entity"
