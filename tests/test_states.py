# --- Tests for deciding which state a lease is for (leasecheck/states.py) ---
# AI-assisted: Claude Code, see AI_DISCLOSURE.md
import pytest

from leasecheck.parsing import InputRejected, check_state, state_warning
from leasecheck.states import MA, STATES, ZIP_STATE, state_verdict

OTHERS = [s for s in STATES.values() if s != MA]
CODE = {name: code for code, name in STATES.items()}
ZIP = {}
for prefix, name in ZIP_STATE.items():
    ZIP.setdefault(name, prefix)


def written_out(state):
    return (f"RESIDENTIAL LEASE. The apartment is at 5 Main St, Springfield, {state} 12345. This lease is governed "
            f"by the laws of {state}. Deposits are held as {state} law requires.")


def abbreviated(state):
    return (f"LEASE. Tenant rents the apartment at 5 Main St, Anytown, {CODE[state]} {ZIP[state]}01. "
            f"Notices to Landlord at 9 Oak Rd, Anytown, {CODE[state]} {ZIP[state]}02.")


@pytest.mark.parametrize("state", OTHERS)
def test_every_other_state_is_recognised_written_out_in_capitals_and_abbreviated(state):
    for text in (written_out(state), written_out(state.upper()), abbreviated(state)):
        verdict = state_verdict(text)
        assert (verdict.status, verdict.state) == ("other", state), text


@pytest.mark.parametrize("text", [
    written_out(MA), written_out(MA.upper()), abbreviated(MA),
    "LEASE. Apartment in Cambridge, Mass. Governed by Mass. Gen. Laws ch. 186.",
    "LEASE. Security deposit held under G.L. c. 186, s. 15B and 940 CMR 3.17.",
    "LEASE. Apartment at 9 Elm St, Brookline. Rent $2,000.",
])
def test_massachusetts_is_recognised_by_name_abbreviation_citation_or_city(text):
    assert state_verdict(text).status == "massachusetts"
    assert state_warning(text) is None
    check_state(text)  # does not raise


@pytest.mark.parametrize("text", [
    "LEASE. Tenant shall pay rent of $2,000 per month.",
    "LEASE. Apartment at 12 Washington Street. Washington Street parking. Mail to 3 Washington Street.",
    "LEASE. Landlord is a Delaware limited liability company. Delaware. Delaware.",
])
def test_street_and_company_names_are_not_states(text):
    assert state_verdict(text).status == "unknown" and "could not confirm" in state_warning(text)


def test_one_out_of_state_office_address_only_warns():
    text = "LEASE. Rent is paid to the office at 1 Main St, Austin, Texas 78701."
    assert state_verdict(text).status == "other_likely" and "appears to be for a property in Texas" in state_warning(text)
    check_state(text)


@pytest.mark.parametrize("text", [
    # the apartment is in Massachusetts; the other state is the landlord's office or bank
    "LEASE. Apartment at 9 Elm St, Allston, MA 02134. Landlord office: 1 Main St, Brooklyn, NY 11201.",
    "RESIDENTIAL LEASE for the premises at 12 Oak St, Boston, Massachusetts 02115. M.G.L. c. 186 s. 15B applies. "
    "Deposit held at East West Bank, Pasadena, CA 91101.",
])
def test_a_massachusetts_lease_with_an_out_of_state_office_is_checked_with_a_warning(text):
    verdict = state_verdict(text)
    assert (verdict.status, verdict.state) == ("mixed", MA)
    assert "also mentions" in state_warning(text)
    check_state(text)


def test_a_massachusetts_form_used_for_a_new_york_apartment_says_where_the_apartment_is():
    text = ("STANDARD FORM APARTMENT LEASE, Greater Boston Real Estate Board. Premises: 5 Court St, Brooklyn, "
            "NY 11201. Security deposit under M.G.L. c. 186 s. 15B.")
    verdict = state_verdict(text)
    assert (verdict.status, verdict.state) == ("mixed", "New York")
    assert "address appears to be in New York" in state_warning(text)


def test_another_states_lease_is_rejected_even_if_the_owner_has_a_boston_office():
    text = ("APARTMENT LEASE CONTRACT. You agree to rent the apartment at 5 Main St, Newark, New Jersey 07102. "
            "N.J.S.A. 46:8-19 applies. New Jersey Truth in Renting Act. Owner's parent company: 1 Federal St, "
            "Boston, MA 02110.")
    with pytest.raises(InputRejected) as err:
        check_state(text)
    assert err.value.reason == "other_state" and "New Jersey" in err.value.message


def test_washington_dc_is_not_washington_state():
    verdict = state_verdict("LEASE. Apartment in Washington, DC 20001. District of Columbia law applies.")
    assert verdict.state == "District of Columbia" and "Washington" not in verdict.evidence


def test_a_zip_code_from_the_wrong_state_weakens_an_address():
    right = state_verdict("Mail to 1 Main St, Austin, TX 78701.").evidence["Texas"].counts["address"]
    wrong = state_verdict("Mail to 1 Main St, Austin, TX 02134.").evidence["Texas"].counts["address"]
    assert right == 1 and wrong < 1
