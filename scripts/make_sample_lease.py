# --- Owner: Suman | builds the sample leases offered in the app ("Try a sample lease") ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Write the fictional sample leases in samples/, so visitors without a lease can try the app (§5.4 asks
for a few ready-made example inputs). They are NOT part of the eval test set. Each sample is built from
eval/clause_bank.py, whose clauses carry the label we expect, so what each sample should show is known:

  sample_lease.docx         Boston apartment, common problems: 4 possibly unlawful (pet fee, late fee after
                            5 days, entry at any time, no interest on the deposit), 1 unusual (carpets)
  sample_fair_lease.docx    A fair lease: no possibly-unlawful clauses, 1 unusual (no nails in the walls)
  sample_shared_house.docx  Shared house, harsher terms: 7 possibly unlawful (1.5-month deposit, lockout for
                            non-payment, tenant does all repairs, no heat Nov-Apr limits, flat water charge,
                            liability waiver, deposit forfeited on early exit), 3 unusual

    python scripts/make_sample_lease.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.build_test_set import write_docx  # noqa: E402
from eval.clause_bank import LAWFUL, UNLAWFUL, UNUSUAL, money_clauses  # noqa: E402


def pick(bank, keys):
    """The (key, text) of each clause in `bank` whose key is in `keys`, in the bank's own order."""
    missing = set(keys) - {c[0] for c in bank}
    assert not missing, f"not in the clause bank: {missing}"
    return [c[:2] for c in bank if c[0] in keys]


def lease(title, parties, rent, term, clauses):
    lines = [title, f"SAMPLE LEASE FOR DEMONSTRATION ONLY. All names and terms are fictional. {parties}"]
    body = [("term", term), ("rent", f"RENT. Tenant shall pay rent of ${rent:,} per month, due on the first day "
                                     "of each month.")] + clauses
    return lines + [f"{n}. {text}" for n, (_key, text) in enumerate(body, start=1)]


SAMPLES = {
    "sample_lease.docx": lease(
        "RESIDENTIAL LEASE AGREEMENT",
        "This lease is made between Back Bay Example Properties LLC (\"Landlord\") and Jordan Example "
        "(\"Tenant\") for the apartment at 100 Example Street, Apt 2, Boston, Massachusetts (the \"premises\").",
        2450, "TERM. The term of this lease is twelve months, beginning September 1, 2026 and ending August 31, 2027.",
        [("m_pet_fee", money_clauses(2450)["m_pet_fee"][0])]
        + pick(LAWFUL, ["use", "sublet", "electric", "contact", "account_ok", "smoking"])
        + pick(UNLAWFUL, ["late_fee", "entry_any", "no_interest"])
        + pick(UNUSUAL, ["carpet"])
        + pick(LAWFUL, ["keys", "insurance"])),
    "sample_fair_lease.docx": lease(
        "RESIDENTIAL LEASE AGREEMENT",
        "This lease is made between Riverside Example Homes LLC (\"Landlord\") and Alex Example (\"Tenant\") for "
        "the apartment at 25 Sample Road, Unit 4, Cambridge, Massachusetts (the \"premises\").",
        2100, "TERM. The term of this lease is twelve months, beginning September 1, 2026 and ending August 31, 2027.",
        [("m_ok", money_clauses(2100)["m_ok"][0])]
        + pick(LAWFUL, ["use", "occupancy", "trash", "noise", "smoking", "electric", "entry_ok", "repairs_ok",
                        "damage", "account_ok", "condition_ok", "lead_ok", "return_ok", "pets_consent",
                        "laundry", "insurance", "keys"])
        + pick(UNUSUAL, ["nails"])),
    "sample_shared_house.docx": lease(
        "ROOM RENTAL AGREEMENT - SHARED HOUSE",
        "This agreement is made between Allston Example Rentals (\"Landlord\") and Sam Example (\"Tenant\") for a "
        "bedroom and shared common areas at 7 Example Avenue, Boston, Massachusetts (the \"premises\").",
        1400, "TERM. The term of this agreement is twelve months, beginning June 1, 2026 and ending May 31, 2027.",
        [("m_deposit_high", money_clauses(1400)["m_deposit_high"][0])]
        + pick(LAWFUL, ["occupancy", "trash", "pets_consent", "parking"])
        + pick(UNLAWFUL, ["water", "heat", "all_repairs", "lock_out", "liability", "forfeit"])
        + pick(UNUSUAL, ["guests", "lockout_fee", "auto_renew"])
        + pick(LAWFUL, ["keys"])),
}

if __name__ == "__main__":
    for name, lines in SAMPLES.items():
        out = ROOT / "samples" / name
        write_docx(out, lines)
        print(f"wrote {out} ({len(lines) - 2} clauses)")
