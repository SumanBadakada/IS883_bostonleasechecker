# --- Owner: Suman | tests for the workshop-feedback fixes (citations, duplicate questions, overload) ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
import pytest

from leasecheck import config
from leasecheck.analyzer import ChargesResult, analyze
from leasecheck.charges import CITE_BROKER, check_move_in_charges
from leasecheck.llm import LLMError, ToolCall
from leasecheck.report import next_steps
from leasecheck.retrieval import SourceIndex, load_chunks
from tests.fakes import FakeLLM
from tests.test_pipeline import LEASE

PET_LEASE = LEASE.replace("and a security deposit of $3,000.",
                          "a security deposit of $2,000, and a non-refundable pet fee of $300.")


def _with_pet_fee_charge(result):
    check = check_move_in_charges(2000, first_month_rent=2000, security_deposit=2000,
                                  other_fees=[{"name": "Non-refundable pet fee", "amount": 300}])
    result.charges = ChargesResult("", [ToolCall("check_move_in_charges", {}, check)])
    return result


def test_pet_fee_is_asked_about_once():
    result = analyze(PET_LEASE.encode(), "lease.txt", FakeLLM(flag_words=("pet fee",)), None)
    payments = next(r for r in result.clauses if "PAYMENTS" in r.clause.text)
    payments.finding.source_ids = ["c186-15B-1b"]  # flagged on move-in grounds, like the real run
    steps = next_steps(_with_pet_fee_charge(result))
    pet = [s for s in steps if "pet fee" in s.title.lower() or "clause 3" in s.title.lower()]
    assert len(pet) == 1, [s.title for s in steps]
    assert "in clause 3" in pet[0].title  # the merged question still says where it is


def test_clause_flagged_for_another_reason_is_still_asked():
    result = analyze(PET_LEASE.encode(), "lease.txt", FakeLLM(flag_words=("pet fee",)), None)
    payments = next(r for r in result.clauses if "PAYMENTS" in r.clause.text)
    payments.finding.source_ids = ["c186-15B-4"]  # e.g. a deposit-return problem in the same clause
    titles = [s.title for s in next_steps(_with_pet_fee_charge(result))]
    assert any("rewrite clause 3" in t for t in titles)


def test_shown_citation_comes_from_the_cited_passage():
    llm = FakeLLM()  # the fake model always writes the citation "cite"
    result = analyze(LEASE.encode(), "lease.txt", llm, SourceIndex.build(llm, cache_path=None))
    by_id = {c.chunk_id: c.citation for c in load_chunks()}
    flagged = [r for r in result.clauses if r.label == "possibly_unlawful"]
    assert flagged
    for r in flagged:
        assert r.finding.citation == "; ".join(by_id[i] for i in r.finding.source_ids)
        assert r.finding.citation != "cite"


def test_corrected_citations():
    assert "verify" not in CITE_BROKER.lower()
    chunks = {c.chunk_id: c for c in load_chunks()}
    assert "15F" in chunks["ag-eviction"].citation and "c. 184 §18" in chunks["ag-eviction"].citation
    assert "verify" not in chunks["ag-broker-fees"].text.lower()


class FlakyLLM(FakeLLM):
    """Fails on the n-th clause-review request, or on the move-in charge step."""

    def __init__(self, fail_on_call=None, fail_charges=False, **kw):
        super().__init__(**kw)
        self.json_calls, self.fail_on_call, self.fail_charges = 0, fail_on_call, fail_charges

    def generate_json(self, system, prompt, schema):
        self.json_calls += 1
        if self.json_calls == self.fail_on_call:
            raise LLMError("Google's Gemini service is overloaded right now.")
        return super().generate_json(system, prompt, schema)

    def run_with_tools(self, *a, **kw):
        if self.fail_charges:
            raise LLMError("Google's Gemini service is overloaded right now.")
        return super().run_with_tools(*a, **kw)


def test_overload_midway_keeps_the_clauses_already_checked(monkeypatch):
    monkeypatch.setattr(config, "CLAUSES_PER_BATCH", 3)
    result = analyze(LEASE.encode(), "lease.txt", FlakyLLM(fail_on_call=2), None)
    labels = [r.label for r in result.clauses]
    assert labels[:3] != ["not_checked"] * 3 and all(l == "not_checked" for l in labels[3:])
    assert result.errors and "could not be checked" in result.errors[0]


def test_overload_on_the_first_request_is_reported():
    with pytest.raises(LLMError, match="overloaded"):
        analyze(LEASE.encode(), "lease.txt", FlakyLLM(fail_on_call=1), None)


def test_overload_on_the_charge_step_keeps_the_clause_review():
    result = analyze(LEASE.encode(), "lease.txt", FlakyLLM(fail_charges=True), None)
    assert all(r.label != "not_checked" for r in result.clauses)
    assert result.charges.check is None and "move-in charges could not be checked" in result.errors[0]
