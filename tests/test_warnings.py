# --- Owner: Suman | tests for the document warnings: not residential, implausible term, backwards dates ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
from pathlib import Path

import pytest

from leasecheck.parsing import load_document, residential_warning, term_warnings

ROOT = Path(__file__).resolve().parent.parent
TEST_SET_V2 = ROOT / "eval" / "test_set_v2"
SAMPLES = ROOT / "samples"

NORMAL_TERM = "1. TERM. The term of this lease is twelve months, beginning September 1, 2026 and ending August 31, 2027."
# The rider clauses of eval/build_test_set_v2.py's invalid-value inputs, verbatim.
RIDER_99_YEARS = ("31. TERM. Notwithstanding anything above, the term of this lease is ninety-nine (99) years, "
                  "beginning August 1, 2025 and terminating July 31, 2124.")
RIDER_BACKWARDS = ("31. TERM. Notwithstanding anything above, the term of this lease begins August 1, 2026 and "
                   "terminates July 31, 2025.")


@pytest.mark.parametrize("name", ["scope_commercial.docx", "scope_parking.docx"])
def test_commercial_and_parking_leases_from_the_eval_get_the_warning(name):
    doc = load_document((TEST_SET_V2 / name).read_bytes(), name)
    assert any("not a residential one" in w for w in doc.warnings)


def test_a_residential_lease_with_a_parking_clause_gets_no_residential_warning():
    text = ("RESIDENTIAL LEASE AGREEMENT\nThis lease is for the apartment at 1 Main St, Boston.\n"
            "5. PARKING. One parking space is included with the apartment.")
    assert residential_warning(text) is None


def test_ninety_nine_year_term_is_flagged_as_too_long():
    warnings = term_warnings(NORMAL_TERM + "\n" + RIDER_99_YEARS)
    assert any("unusually long" in w for w in warnings)
    assert not any("end before it begins" in w for w in warnings)


def test_lease_that_ends_before_it_begins_is_flagged():
    warnings = term_warnings(NORMAL_TERM + "\n" + RIDER_BACKWARDS)
    assert any("end before it begins" in w for w in warnings)


@pytest.mark.parametrize("text", [
    NORMAL_TERM,
    "The tenancy runs from 9/1/2026 through 8/31/2027.",
    "TERM. The term is five (5) years beginning January 1, 2027.",  # 5 years: long, but not over the limit
    "This lease begins on June 1st, 2026 and ends on May 31st, 2027.",
])
def test_ordinary_terms_get_no_term_warning(text):
    assert term_warnings(text) == []


def test_numeric_dates_in_the_wrong_order_are_flagged():
    assert any("end before it begins" in w for w in term_warnings("The lease runs from 9/1/2027 to 8/31/2026."))


@pytest.mark.parametrize("name", ["sample_lease.docx", "sample_fair_lease.docx", "sample_shared_house.docx"])
def test_the_sample_leases_raise_no_warnings(name):
    assert load_document((SAMPLES / name).read_bytes(), name).warnings == []
