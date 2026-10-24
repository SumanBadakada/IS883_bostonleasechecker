# --- Owner: Suman | tests for page headers/footers, page-break splits, other-state leases and formats ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
import pytest

from eval.build_test_set import build_leases
from eval.format_robustness import FORMATS, run
from leasecheck.parsing import _strip_page_furniture, split_clauses, state_warning, states_named

TOP = "RESIDENTIAL LEASE\nThis lease is between Landlord and Tenant.\n29. GUESTS. Guests may stay 48 hours.\n"


# ---------- clause 30 from the real lease ----------

def test_footer_inside_a_sentence_does_not_split_the_clause():
    text = TOP + ("30. Between 11P.M. and 9A.M. tenants will lower all musical devices. At no time should that "
                  "level disturb any\nMJMJ 4\nother residents of the building. All complaints to the police are "
                  "grounds for immediate termination of the lease.\n31. KEYS. Tenant shall return all keys.\n")
    clauses = split_clauses(text)
    thirty = next(c for c in clauses if c.text.startswith("30."))
    assert "disturb any other residents of the building" in thirty.text
    assert "termination of the lease" in thirty.text and "MJMJ" not in thirty.text
    assert not any(c.text.startswith("MJMJ") for c in clauses)


def test_heading_at_a_real_clause_boundary_still_splits():
    clauses = split_clauses(TOP + "30. NOISE. Keep it down.\nPARKING\nOne space is included.\n31. KEYS. Return keys.")
    assert any(c.text.startswith("PARKING") for c in clauses)


# ---------- headers and footers on PDF pages ----------

def test_repeated_footer_and_header_removed():
    pages = ["ACME LEASE\n1. TERM. One year.\nMJMJ 1", "ACME LEASE\n2. RENT. $2,000.\nMJMJ 2",
             "ACME LEASE\n3. KEYS. Return.\nMJMJ 3"]
    assert _strip_page_furniture(pages) == ["1. TERM. One year.", "2. RENT. $2,000.", "3. KEYS. Return."]


@pytest.mark.parametrize("line", ["Page 2", "Page 2 of 7", "- 2 -", "2", "2/7", "MJMJ 2",
                                  "Tenant initials: ____", "RESIDENTIAL LEASE AGREEMENT - Page 1"])
def test_page_markers_removed_even_on_one_page(line):
    assert _strip_page_furniture([f"1. TERM. One year.\n2. RENT. Due monthly.\n{line}"]) == \
        ["1. TERM. One year.\n2. RENT. Due monthly."]


def test_repeated_sentence_in_the_body_is_kept():
    body = "Tenant shall keep the premises clean."
    pages = [f"1. A.\nx\n{body}\ny\nz\n2. B.", f"3. C.\nx\n{body}\ny\nz\n4. D."]
    assert all(body in p for p in _strip_page_furniture(pages))


# ---------- other states ----------

@pytest.mark.parametrize("text,expected", [
    ("Premises: 12 Main St, Austin, TX 78701. Governed by the laws of the State of Texas.", {"Texas"}),
    ("45 Washington Street, Boston, MA 02108. Governed by Massachusetts law.", {"Massachusetts"}),
    ("Apartment at 9 Virginia Ave, Brighton. Parking on Washington Street.", set()),
    ("100 Elm St, Boston, MA 02115. GOVERNED BY THE LAWS OF THE STATE OF New York.", {"Massachusetts", "New York"}),
])
def test_states_named(text, expected):
    assert states_named(text) == expected


def test_state_warnings():
    assert "Texas" in state_warning("12 Main St, Austin, TX 78701") and "may not apply" in state_warning(
        "12 Main St, Austin, TX 78701")
    assert "also mentions New York" in state_warning("Boston, MA 02115. Laws of the State of New York.")
    assert state_warning("Boston, MA 02115. M.G.L. c. 186 applies.") is None


# ---------- formats ----------

def test_clause_splitting_survives_every_format():
    totals = run(build_leases()[:4], FORMATS)
    for name, t in totals.items():
        assert t["exact_rate"] == 1.0 and t["leaked_furniture"] == 0 and t["split"] == 0, (name, t)
