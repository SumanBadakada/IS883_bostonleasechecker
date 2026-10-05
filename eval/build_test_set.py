# --- Owner: (assign, see docs/TEAM_SPLIT.md) | builds the synthetic test leases and their expected results ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Write eval/test_set/: 20 synthetic leases (DOCX and PDF) plus awkward inputs, and gold.json with the
expected result for every input. Deterministic (fixed seed): re-running gives the same leases and labels.

    python -m eval.build_test_set

Consented real leases go in eval/test_set/private/ (git-ignored) with their own entries in
eval/test_set/private/gold.json, labelled by two team members before any run.
"""
from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

from eval.clause_bank import LAWFUL, UNLAWFUL, UNUSUAL, money_clauses

OUT = Path(__file__).resolve().parent / "test_set"
SEED = 883

ADDRESSES = ["12 Commonwealth Ave, Apt 3", "45 Gardner St, Unit 2", "200 Bay State Rd, Apt 5B",
             "8 Linden St, Apt 1", "77 Brighton Ave, Unit 4", "31 Park Dr, Apt 12",
             "150 Harvard Ave, Unit 6", "9 Egmont St, Apt 2R", "64 Strathmore Rd, Unit 3",
             "18 Mission Hill Ave, Apt 1"]
LANDLORDS = ["Charles River Holdings LLC", "Allston Realty Trust", "Fenway Residential LLC", "Kenmore Properties Inc."]
MONEY_KEYS = ["m_ok", "m_deposit_high", "m_pet_fee", "m_app_fee", "m_pet_deposit", "m_lock", "m_broker", "m_last_high"]


def build_leases(n: int = 20) -> list[dict]:
    rng = random.Random(SEED)
    leases = []
    for i in range(n):
        rent = rng.choice(range(1650, 3450, 50))
        clean = i == 0  # lease 1 is a clean lease: nothing planted, lawful payments
        money_key = "m_ok" if clean else MONEY_KEYS[i % len(MONEY_KEYS)]
        planted_unlawful = [] if clean else rng.sample(UNLAWFUL, rng.randint(1, 3))
        planted_unusual = [] if clean else rng.sample(UNUSUAL, rng.randint(0, 2))
        filler = rng.sample(LAWFUL, 9 if clean else 7)
        # Never put the lawful and unlawful versions of the same topic in one lease.
        planted_keys = {k for k, *_ in planted_unlawful}
        if "entry_any" in planted_keys:
            filler = [c for c in filler if c[0] != "entry_ok"]
        if "all_repairs" in planted_keys or "heat" in planted_keys or "pests" in planted_keys:
            filler = [c for c in filler if c[0] != "repairs_ok"]
        if "no_interest" in planted_keys:
            filler = [c for c in filler if c[0] not in ("return_ok", "account_ok")]

        money_text, money_label, money_cite, charges = money_clauses(rent)[money_key]
        body = filler + planted_unlawful + planted_unusual
        rng.shuffle(body)
        clauses = [
            ("term", "TERM. The term of this lease is twelve months, beginning September 1, 2026 and ending August 31, 2027.", "lawful", []),
            ("rent", f"RENT. Tenant shall pay rent of ${rent:,} per month, due on the first day of each month.", "lawful", []),
            (money_key, money_text, money_label, money_cite),
        ] + body

        landlord = rng.choice(LANDLORDS)
        address = ADDRESSES[i % len(ADDRESSES)]
        preamble = (f"This Residential Lease is made between {landlord} (\"Landlord\") and the student named below "
                    f"(\"Tenant\") for the apartment at {address}, Boston, Massachusetts (the \"premises\").")
        leases.append({
            "id": f"lease_{i + 1:02d}",
            "format": "docx" if i % 2 == 0 else "pdf",
            "rent": rent,
            "preamble": preamble,
            "clauses": [{"key": k, "text": t, "label": l, "cite": c} for k, t, l, c in clauses],
            "charges": charges,
        })
    return leases


def lease_lines(lease: dict) -> list[str]:
    lines = ["RESIDENTIAL LEASE AGREEMENT", lease["preamble"]]
    lines += [f"{n}. {c['text']}" for n, c in enumerate(lease["clauses"], start=1)]
    return lines


def write_docx(path: Path, lines: list[str]) -> None:
    import docx

    document = docx.Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(path)


def write_pdf(path: Path, lines: list[str]) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    story = []
    for line in lines:
        story += [Paragraph(line.replace("&", "&amp;"), styles["Normal"]), Spacer(1, 6)]
    SimpleDocTemplate(str(path), pagesize=letter).build(story)


def write_scanned_pdf(path: Path) -> None:
    """A PDF with no text layer, like a phone scan: only drawn shapes."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for page in range(2):
        for y in range(700, 100, -18):
            c.rect(72, y, 440 - (y % 90), 8, fill=1, stroke=0)  # grey bars where text lines would be
        c.showPage()
    c.save()


NON_LEASE_TEXT = [
    "IS883 STUDY GROUP NOTES",
    "Week 5: tools and retrieval. Bring laptops with the Gemini key configured.",
    "1. Review the ReAct loop from the session notebook.",
    "2. Try cosine similarity on the sample paragraphs.",
    "3. Each person drafts two test inputs for the project.",
    "Next meeting: Thursday 6 pm in the library, second floor.",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    leases = build_leases()
    gold = {"created": date.today().isoformat(),
            "note": "Expected results written before any run. Do not edit after running the app on these files.",
            "inputs": []}
    for lease in leases:
        filename = f"{lease['id']}.{lease['format']}"
        lines = lease_lines(lease)
        (write_docx if lease["format"] == "docx" else write_pdf)(OUT / filename, lines)
        gold["inputs"].append({
            "file": filename, "kind": "lease", "expect": "analyzed",
            "clauses": [{"text": "\n".join(lines[:2]), "label": "lawful", "cite": [], "key": "preamble"}]
                       + lease["clauses"],
            "charges": lease["charges"],
        })

    write_scanned_pdf(OUT / "awkward_scanned.pdf")
    gold["inputs"].append({"file": "awkward_scanned.pdf", "kind": "awkward", "expect": "rejected:scanned"})
    write_docx(OUT / "awkward_not_a_lease.docx", NON_LEASE_TEXT)
    gold["inputs"].append({"file": "awkward_not_a_lease.docx", "kind": "awkward", "expect": "rejected:not_a_lease"})
    write_docx(OUT / "awkward_empty.docx", [])
    gold["inputs"].append({"file": "awkward_empty.docx", "kind": "awkward", "expect": "rejected:empty"})

    (OUT / "gold.json").write_text(json.dumps(gold, indent=2), encoding="utf-8")
    n_unlawful = sum(1 for g in gold["inputs"] for c in g.get("clauses", []) if c["label"] == "possibly_unlawful")
    n_clauses = sum(len(g.get("clauses", [])) for g in gold["inputs"])
    print(f"Wrote {len(gold['inputs'])} inputs, {n_clauses} labelled clauses "
          f"({n_unlawful} possibly_unlawful) to {OUT}")


if __name__ == "__main__":
    main()
