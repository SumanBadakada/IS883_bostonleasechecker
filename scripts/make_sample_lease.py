# --- Owner: (assign, see docs/TEAM_SPLIT.md) | builds the "Try a sample lease" file shown in the app ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Write samples/sample_lease.docx: a fictional Boston lease with a few planted problems, so visitors
without a lease can try the app. It is NOT part of the eval test set.

    python scripts/make_sample_lease.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.build_test_set import write_docx  # noqa: E402
from eval.clause_bank import LAWFUL, UNLAWFUL, UNUSUAL, money_clauses  # noqa: E402

RENT = 2450
pick = lambda bank, keys: [c for c in bank if c[0] in keys]  # noqa: E731

clauses = (
    [("term", "TERM. The term of this lease is twelve months, beginning September 1, 2026 and ending August 31, 2027.")]
    + [("rent", f"RENT. Tenant shall pay rent of ${RENT:,} per month, due on the first day of each month.")]
    + [("m_pet_fee", money_clauses(RENT)["m_pet_fee"][0])]
    + [c[:2] for c in pick(LAWFUL, {"use", "sublet", "electric", "contact", "account_ok", "smoking"})]
    + [c[:2] for c in pick(UNLAWFUL, {"late_fee", "entry_any", "no_interest"})]
    + [c[:2] for c in pick(UNUSUAL, {"carpet"})]
    + [c[:2] for c in pick(LAWFUL, {"keys", "insurance"})]
)

lines = ["RESIDENTIAL LEASE AGREEMENT",
         "SAMPLE LEASE FOR DEMONSTRATION ONLY. All names and terms are fictional. This lease is made between "
         "Back Bay Example Properties LLC (\"Landlord\") and Jordan Example (\"Tenant\") for the apartment at "
         "100 Example Street, Apt 2, Boston, Massachusetts (the \"premises\")."]
lines += [f"{n}. {text}" for n, (_key, text) in enumerate(clauses, start=1)]

out = ROOT / "samples" / "sample_lease.docx"
write_docx(out, lines)
print(f"wrote {out} ({len(clauses)} clauses)")
