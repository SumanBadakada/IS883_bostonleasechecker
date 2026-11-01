# --- Owner: (assign, see docs/TEAM_SPLIT.md) | builds the "Try a sample lease" files shown in the app ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Write samples/sample_lease*.docx: five fictional Boston leases, each telling a different story, so
visitors without a lease of their own can see the range of what the app catches. NOT part of the eval
test set (see eval/build_test_set.py for that).

    python scripts/make_sample_lease.py

`sample_lease.docx` (the original, unchanged mixed-violations lease) is left exactly as it was: its
clause numbering is cited verbatim in README.md's "PROOF OF CONCEPT" test (Input B, clause 13 = the
carpet-cleaning clause), which was already run and its actual output recorded there. Regenerating it
with different content or clause order would silently invalidate that documented, already-run test.
The four new files below are purely additive.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.build_test_set import write_docx  # noqa: E402
from eval.clause_bank import LAWFUL, UNLAWFUL, UNUSUAL, money_clauses  # noqa: E402

RENT = 2450
pick = lambda bank, keys: [c[:2] for c in bank if c[0] in keys]  # noqa: E731

PREAMBLE = ("SAMPLE LEASE FOR DEMONSTRATION ONLY. All names and terms are fictional. This lease is made "
            "between Back Bay Example Properties LLC (\"Landlord\") and Jordan Example (\"Tenant\") for "
            "the apartment at 100 Example Street, Apt 2, Boston, Massachusetts (the \"premises\").")


def write_legacy_sample(out_dir: Path) -> None:
    """Unchanged from the original single-sample version. Do not reorder or re-pick these clauses --
    see the module docstring. (Mixed violations: pet fee, late fee, any-time entry, no deposit
    interest, plus the carpet-cleaning "unusual" clause.)"""
    clauses = (
        [("term", "TERM. The term of this lease is twelve months, beginning September 1, 2026 and ending August 31, 2027.")]
        + [("rent", f"RENT. Tenant shall pay rent of ${RENT:,} per month, due on the first day of each month.")]
        + [("m_pet_fee", money_clauses(RENT)["m_pet_fee"][0])]
        + pick(LAWFUL, {"use", "sublet", "electric", "contact", "account_ok", "smoking"})
        + pick(UNLAWFUL, {"late_fee", "entry_any", "no_interest"})
        + pick(UNUSUAL, {"carpet"})
        + pick(LAWFUL, {"keys", "insurance"})
    )
    lines = ["RESIDENTIAL LEASE AGREEMENT", PREAMBLE]
    lines += [f"{n}. {text}" for n, (_key, text) in enumerate(clauses, start=1)]
    out = out_dir / "sample_lease.docx"
    write_docx(out, lines)
    print(f"wrote {out} ({len(clauses)} clauses) — Mixed violations (original sample, unchanged)")


COMMON_LAWFUL = {"use", "sublet", "smoking", "insurance", "keys"}

# Four additional profiles, each a distinct story, with their own filenames so the original sample's
# clause numbering above is never disturbed. As in build_test_set.py, never mix the lawful and
# unlawful versions of the same topic (entry, repairs) in one lease.
NEW_PROFILES = [
    {
        "id": "clean",
        "label": "Clean lease (no violations)",
        "money_key": "m_ok",
        "lawful": COMMON_LAWFUL | {"electric", "contact", "account_ok", "return_ok", "entry_ok", "repairs_ok"},
        "unlawful": set(),
        "unusual": set(),
    },
    {
        "id": "repairs",
        "label": "Habitability / repairs violation",
        "money_key": "m_ok",
        "lawful": COMMON_LAWFUL | {"electric", "contact", "entry_ok"},
        "unlawful": {"all_repairs", "heat"},
        "unusual": set(),
    },
    {
        "id": "entry",
        "label": "Entry / eviction violation",
        "money_key": "m_ok",
        "lawful": COMMON_LAWFUL | {"electric", "contact", "repairs_ok"},
        "unlawful": {"entry_any", "lock_out"},
        "unusual": set(),
    },
    {
        "id": "unusual",
        "label": "Mostly fine, with a couple of unusual clauses",
        "money_key": "m_ok",
        "lawful": COMMON_LAWFUL | {"electric", "contact", "entry_ok", "repairs_ok", "account_ok"},
        "unlawful": set(),
        "unusual": {"carpet", "guests", "lockout_fee"},
    },
]


def build_lines(profile: dict) -> list[str]:
    money_text, _label, _cite, _charges = money_clauses(RENT)[profile["money_key"]]
    clauses = (
        [("term", "TERM. The term of this lease is twelve months, beginning September 1, 2026 and ending August 31, 2027.")]
        + [("rent", f"RENT. Tenant shall pay rent of ${RENT:,} per month, due on the first day of each month.")]
        + [(profile["money_key"], money_text)]
        + pick(LAWFUL, profile["lawful"])
        + pick(UNLAWFUL, profile["unlawful"])
        + pick(UNUSUAL, profile["unusual"])
    )
    lines = ["RESIDENTIAL LEASE AGREEMENT", PREAMBLE]
    lines += [f"{n}. {text}" for n, (_key, text) in enumerate(clauses, start=1)]
    return lines


def main() -> None:
    out_dir = ROOT / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_legacy_sample(out_dir)
    for profile in NEW_PROFILES:
        lines = build_lines(profile)
        out = out_dir / f"sample_lease_{profile['id']}.docx"
        write_docx(out, lines)
        print(f"wrote {out} ({len(lines) - 2} clauses) — {profile['label']}")


if __name__ == "__main__":
    main()
