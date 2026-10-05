# --- Owner: (assign, see docs/TEAM_SPLIT.md) | offline tests: parsing, tool, schema, retrieval, pipeline, metrics ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
import io
import json

import docx
import pytest

from eval.metrics import score_charges, score_lease, summarise
from leasecheck.analyzer import analyze
from leasecheck.charges import check_move_in_charges
from leasecheck.parsing import InputRejected, load_clauses, split_clauses
from leasecheck.retrieval import SourceIndex, load_chunks
from leasecheck.schemas import parse_batch
from tests.fakes import FakeLLM

LEASE = """RESIDENTIAL LEASE AGREEMENT
This lease is between Landlord and Tenant for the premises at 1 Main St, Boston.
1. TERM. The term of this lease is twelve months starting September 1.
2. RENT. Tenant shall pay rent of $2,000 per month on the first day of each month.
3. PAYMENTS. At signing Tenant shall pay first month's rent of $2,000 and a security deposit of $3,000.
4. LATE PAYMENT. Tenant shall pay a late charge of $50 if rent is late by five days.
5. ACCESS. Landlord may enter at any time for any purpose.
6. TRASH. Tenant shall keep the apartment clean and dispose of trash properly.
"""


def docx_bytes(lines):
    d = docx.Document()
    for line in lines:
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ---------- parsing ----------

def test_split_numbered_clauses():
    clauses = split_clauses(LEASE)
    assert len(clauses) == 7  # preamble + 6
    assert clauses[1].text.startswith("1. TERM")
    assert "LATE PAYMENT" in clauses[4].text


def test_docx_round_trip():
    clauses = load_clauses(docx_bytes(LEASE.splitlines()), "lease.docx")
    assert len(clauses) == 7


@pytest.mark.parametrize("data,name,reason", [
    (b"", "x.pdf", "empty"),
    (b"hello", "x.png", "unsupported"),
    (b"not a pdf at all", "x.pdf", "unreadable"),
])
def test_rejections(data, name, reason):
    with pytest.raises(InputRejected) as exc:
        load_clauses(data, name)
    assert exc.value.reason == reason


def test_not_a_lease_rejected():
    with pytest.raises(InputRejected) as exc:
        load_clauses(docx_bytes(["Shopping list", "1. Milk and eggs", "2. Bread", "3. Apples"]), "list.docx")
    assert exc.value.reason == "not_a_lease"


# ---------- the tool ----------

def test_charges_lawful():
    r = check_move_in_charges(2000, first_month_rent=2000, last_month_rent=2000, security_deposit=2000)
    assert r["problems_found"] == 0


def test_charges_deposit_over_cap_and_fees():
    r = check_move_in_charges(2000, first_month_rent=2000, security_deposit=2000,
                              other_fees=[{"name": "Pet deposit", "amount": 500},
                                          {"name": "Application fee", "amount": 50}])
    statuses = {i["charge"]: i["status"] for i in r["items"]}
    assert r["problems_found"] == 2  # combined deposit > rent, and the application fee
    assert statuses["Application fee"] == "not_allowed"


def test_charges_broker_and_lock_need_checking():
    r = check_move_in_charges(2000, lock_and_key_fee=85, other_fees=[{"name": "Broker fee", "amount": 2000}])
    assert r["problems_found"] == 0 and r["needs_checking"] == 2


def test_charges_bad_rent():
    assert "error" in check_move_in_charges(0)


# ---------- structured output ----------

def test_parse_batch_variants():
    good = {"findings": [{"clause_id": 1, "topic": "t", "label": "lawful", "explanation": "e"}]}
    assert parse_batch(json.dumps(good)).findings[0].label == "lawful"
    assert parse_batch("```json\n" + json.dumps(good) + "\n```") is not None
    assert parse_batch(json.dumps(good["findings"])) is not None
    assert parse_batch("not json") is None
    assert parse_batch(json.dumps({"findings": [{"clause_id": 1, "label": "illegal"}]})) is None


# ---------- retrieval ----------

def test_sources_load_and_have_unique_ids():
    chunks = load_chunks()
    ids = [c.chunk_id for c in chunks]
    assert len(chunks) > 20 and len(ids) == len(set(ids))


def test_retrieval_finds_late_fee_passage():
    llm = FakeLLM()
    index = SourceIndex.build(llm, cache_path=None)
    hits = index.search_many(llm, ["late fee interest penalty failure to pay rent thirty days"], k=3)[0]
    assert "c186-15B-1c" in [c.chunk_id for c, _ in hits]


# ---------- the whole pipeline ----------

def test_analyze_end_to_end():
    llm = FakeLLM()
    index = SourceIndex.build(llm, cache_path=None)
    result = analyze(LEASE.encode(), "lease.txt", llm, index)
    labels = {r.clause.clause_id: r.label for r in result.clauses}
    assert labels[5] == "possibly_unlawful" and labels[6] == "possibly_unlawful" and labels[7] == "lawful"
    # invented source ids are stripped; only retrieved ones remain
    for r in result.clauses:
        if r.finding:
            assert "made-up-id" not in r.finding.source_ids
    check = result.charges.check
    assert check and check["problems_found"] == 1  # $3,000 deposit on $2,000 rent
    assert result.usage.calls > 0


def test_unparseable_output_takes_failure_path():
    llm = FakeLLM(json_responses=["oops", "still not json"])
    result = analyze(LEASE.encode(), "lease.txt", llm, None)
    assert result.parse_failures == 1  # 7 clauses = 1 batch, which failed, was retried, and failed again
    assert all(r.label == "not_checked" for r in result.clauses)


# ---------- metrics ----------

def test_metrics():
    gold = {"clauses": [{"text": "late fee after five days", "label": "possibly_unlawful", "cite": ["c186-15B-1c"]},
                        {"text": "keep the apartment clean", "label": "lawful", "cite": []}]}
    pred = [{"text": "Late fee after five days.", "label": "possibly_unlawful", "source_ids": ["c186-15B-1c"]},
            {"text": "keep the apartment clean", "label": "possibly_unlawful", "source_ids": []}]
    s = summarise(score_lease(gold, pred)["rows"])
    assert s["recall_possibly_unlawful"] == 1.0 and s["agreement"] == 0.5
    assert s["correct_citation_on_true_flags"] == 1.0 and s["flags_with_citation"] == 0.5
    c = score_charges({"monthly_rent": 2000, "security_deposit": 2000, "problems_found": 0},
                      [{"name": "check_move_in_charges", "args": {"monthly_rent": 2000, "security_deposit": 2000},
                        "result": {"problems_found": 0}}])
    assert all(c.values())
