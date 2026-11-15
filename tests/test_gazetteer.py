"""The measurement that decides which names the extractor can match.

A dictionary cannot tell "Applied Materials" from "financial institutions" -
both are ordinary English. The corpus can: a company name is written
capitalised nearly every time it appears, and a generic phrase is not.

This is the filter that, when it was lexical instead of measured, deleted 6,493
real company names. Worth pinning down.

Pure - no database.
"""
import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
dfg = pytest.importorskip("df_gazetteer")

verdict = dfg.verdict


# -------------------------------------------------- real numbers from the corpus

@pytest.mark.parametrize("name,cap,low,df,expected", [
    # measured, from eval/gazetteer_df.tsv
    ("APPLIED MATERIALS",      28,   2, 0.036, "keep"),
    ("BOEING",                119,   8, 0.049, "keep"),
    ("STELLANTIS",             61,   0, 0.044, "keep"),
    ("FEDEX",                  85,   1, 0.013, "keep"),
    ("FINANCIAL INSTITUTIONS",  3, 623, 0.009, "prose"),
    ("WEARABLE DEVICES",        0,  12, 0.000, "prose"),
    ("COATS",                   2,   3, 0.004, "prose"),
    ("COMMODITIES",             8, 315, 0.022, "prose"),
    ("NASDAQ",               2228,  36, 0.533, "category"),
    ("OXLEY",                 600,   0, 0.587, "category"),
])
def test_the_real_cases_are_decided_correctly(name, cap, low, df, expected):
    assert verdict(cap, low, df) == expected, name


# ------------------------------------------------------------- the boundaries

def test_a_name_never_seen_is_left_alone():
    """Judging a name on no evidence would suppress most of the gazetteer."""
    assert verdict(0, 0, 0.0) == "keep"


def test_always_capitalised_and_rare_is_kept():
    assert verdict(50, 0, 0.01) == "keep"


def test_always_lower_case_is_prose():
    assert verdict(0, 50, 0.01) == "prose"


def test_the_prose_threshold_is_where_it_says_it_is():
    lo = dfg.CAP_RATIO - 0.01
    hi = dfg.CAP_RATIO + 0.01
    assert verdict(int(1000 * lo), 1000 - int(1000 * lo), 0.0) == "prose"
    assert verdict(int(1000 * hi), 1000 - int(1000 * hi), 0.0) == "keep"


def test_the_category_threshold_is_where_it_says_it_is():
    assert verdict(100, 0, dfg.DF_FRAC + 0.01) == "category"
    assert verdict(100, 0, dfg.DF_FRAC - 0.01) == "keep"


def test_prose_is_reported_before_category():
    """A phrase that is both lower-case and everywhere is prose: that is the
    more useful reason to show a reviewer."""
    assert verdict(1, 99, 0.9) == "prose"


def test_a_ubiquitous_but_properly_capitalised_name_is_a_category_not_prose():
    assert verdict(1000, 0, 0.9) == "category"


def test_the_thresholds_are_in_a_defensible_range():
    """Both are chosen constants, not fitted. They should at least be sane."""
    assert 0.5 <= dfg.CAP_RATIO <= 0.9, "too strict and real names are lost"
    assert 0.05 <= dfg.DF_FRAC <= 0.4


def test_aebi_schmidt_survives_the_threshold_we_chose():
    """The case that made us lower CAP_RATIO from 0.75 to 0.65: a real company
    written lower-case in table text often enough to score 0.728."""
    assert verdict(147, 55, 0.004) == "keep"


# ------------------------------------------- the rule this filter had to replace

def test_a_two_word_name_of_ordinary_words_is_judged_on_evidence_not_vocabulary():
    """The lexical rule suppressed any two-word name whose words were both in a
    dictionary. 'Applied Materials' and 'Construction Partners' are both exactly
    that; the corpus separates them and a dictionary cannot."""
    assert verdict(28, 2, 0.036) == "keep"     # Applied Materials
    assert verdict(0, 3, 0.000) == "prose"     # Construction Partners


def test_the_lexical_rule_is_gone_from_the_old_filter():
    src = open(os.path.join(ROOT, "scripts", "fix_gazetteer.py")).read()
    assert "all(t in ENGLISH or t in EXTRA for t in toks) and len(toks) <= 2" not in src


# ------------------------------------------- counting depends on the same _proper

def test_it_uses_the_extractor_s_own_notion_of_a_proper_noun():
    """If the filter counted capitalisation differently from the matcher, it
    would be measuring something the extractor never sees."""
    import extract
    assert dfg._proper is extract._proper
    assert dfg.TOKEN is extract.TOKEN


def test_the_audit_file_is_ordered_so_two_runs_can_be_diffed():
    """Ties in the count made the line order wobble between runs, so a diff of
    two audit files was full of noise and a real change could hide in it."""
    src = open(os.path.join(ROOT, "scripts", "df_gazetteer.py")).read()
    assert "(-(cap[k] + low[k]), k)" in src, "the sort has no tie-break"


def test_the_audit_file_records_the_evidence_not_just_the_verdict():
    """A suppression nobody can check is a suppression nobody can reverse."""
    path = os.path.join(ROOT, "eval", "gazetteer_df.tsv")
    if not os.path.exists(path):
        pytest.skip("no audit file; run make gazetteer-df")
    header = open(path).readline().strip().split("\t")
    assert header == ["alias_norm", "cap", "low", "cap_ratio", "doc_freq", "verdict"]


def test_every_line_of_the_audit_file_agrees_with_the_rule():
    """The file is what a reviewer reads. If it ever disagreed with the code,
    the reviewer would be auditing fiction."""
    path = os.path.join(ROOT, "eval", "gazetteer_df.tsv")
    if not os.path.exists(path):
        pytest.skip("no audit file; run make gazetteer-df")
    bad = []
    with open(path) as fh:
        next(fh)
        for line in fh:
            key, cap, low, _ratio, df, why = line.rstrip("\n").split("\t")
            if verdict(int(cap), int(low), float(df)) != why:
                bad.append(key)
    assert not bad, f"{len(bad)} rows disagree with verdict(), e.g. {bad[:3]}"
