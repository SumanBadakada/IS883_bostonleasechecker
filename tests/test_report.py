# --- Owner: (assign, see docs/TEAM_SPLIT.md) | tests for next steps, verdicts and the downloadable report ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
from leasecheck.analyzer import analyze
from leasecheck.parsing import Clause
from leasecheck.report import html_report, next_steps, overall_verdict
from tests.fakes import FakeLLM
from tests.test_pipeline import LEASE


def run(text=LEASE, **fake):
    return analyze(text.encode(), "lease.txt", FakeLLM(**fake), None)


def test_next_steps_put_charge_problems_and_flags_first():
    steps = next_steps(run())
    assert steps and all(s.severity == "high" for s in steps[:3])
    assert "security deposit" in steps[0].title.lower()  # $3,000 deposit on $2,000 rent
    assert any("clause 4" in s.title for s in steps)  # the lease's own number, not our counter


def test_verdict_tones():
    assert overall_verdict(run())[0] == "danger"
    clean = run(flag_words=("zzz",))
    clean.charges.tool_calls = []
    assert overall_verdict(clean)[0] == "success"


def test_report_escapes_lease_text():
    hostile = LEASE.replace("dispose of trash properly", "<script>alert(1)</script> trash")
    page = html_report(run(hostile), "<b>lease</b>.pdf")
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert "<b>lease</b>" not in page


def test_display_names():
    assert Clause(4, "3. PAYMENTS. Pay rent.").display_name == "Clause 3"
    assert Clause(1, "RESIDENTIAL LEASE between...").display_name == "Opening section"
    assert Clause(7, "SECURITY DEPOSIT. The deposit...").display_name == "Part 7"
