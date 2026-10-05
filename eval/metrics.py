# --- Owner: (assign, see docs/TEAM_SPLIT.md) | scoring: success metric and deterministic checks ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Pure scoring functions (no API calls), so they can be unit-tested.

Headline metric: recall on clauses labelled possibly_unlawful = of the clauses we labelled possibly
unlawful in advance, the share the app also labelled possibly unlawful. Overall agreement is reported
alongside, because most clauses are lawful and agreement alone would look inflated.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

LABELS = ["lawful", "unusual", "possibly_unlawful", "not_checked", "missing"]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def align(gold_clauses: list[dict], predicted: list[dict], threshold: float = 0.6) -> list[dict | None]:
    """Match each gold clause to the predicted clause with the most similar text (or None).

    Splitting may not reproduce our clause boundaries exactly, so we match on text, not position.
    """
    pred_norm = [_norm(p["text"]) for p in predicted]
    matches: list[dict | None] = []
    for g in gold_clauses:
        gn = _norm(g["text"])
        best, best_score = None, 0.0
        for p, pn in zip(predicted, pred_norm):
            if gn in pn or pn in gn:
                score = min(len(gn), len(pn)) / max(len(gn), len(pn), 1) * 0.5 + 0.5
            else:
                score = SequenceMatcher(None, gn, pn).ratio()
            if score > best_score:
                best, best_score = p, score
        matches.append(best if best_score >= threshold else None)
    return matches


def score_lease(gold: dict, predicted: list[dict]) -> dict:
    """predicted: [{"text", "label", "source_ids", "citation"}] for one lease."""
    matches = align(gold["clauses"], predicted)
    rows = []
    for g, p in zip(gold["clauses"], matches):
        pred_label = p["label"] if p else "missing"
        cited_ok = None
        if g["label"] == "possibly_unlawful" and pred_label == "possibly_unlawful":
            cited_ok = bool(set(p.get("source_ids") or []) & set(g["cite"]))
        rows.append({"key": g.get("key"), "gold": g["label"], "pred": pred_label,
                     "has_citation": bool(p and p.get("source_ids")) if pred_label == "possibly_unlawful" else None,
                     "citation_correct": cited_ok})
    return {"rows": rows}


def summarise(rows: list[dict]) -> dict:
    total = len(rows)
    agree = sum(r["gold"] == r["pred"] for r in rows)
    gold_u = [r for r in rows if r["gold"] == "possibly_unlawful"]
    pred_u = [r for r in rows if r["pred"] == "possibly_unlawful"]
    tp = sum(r["pred"] == "possibly_unlawful" for r in gold_u)
    flagged = [r for r in rows if r["has_citation"] is not None]
    cited = [r for r in rows if r["citation_correct"] is not None]
    confusion = {g: {p: 0 for p in LABELS} for g in LABELS[:3]}
    for r in rows:
        confusion[r["gold"]][r["pred"]] += 1
    return {
        "clauses": total,
        "recall_possibly_unlawful": tp / len(gold_u) if gold_u else None,
        "precision_possibly_unlawful": tp / len(pred_u) if pred_u else None,
        "agreement": agree / total if total else None,
        "flags_with_citation": sum(r["has_citation"] for r in flagged) / len(flagged) if flagged else None,
        "correct_citation_on_true_flags": sum(r["citation_correct"] for r in cited) / len(cited) if cited else None,
        "confusion": confusion,
    }


def score_charges(expected: dict, tool_calls: list[dict]) -> dict:
    """Deterministic check on the tool: was it called, and with the right numbers?"""
    call = next((c for c in tool_calls if c["name"] == "check_move_in_charges"), None)
    if call is None:
        return {"called": False, "rent_ok": False, "deposit_ok": False, "problems_ok": False}
    args, result = call["args"], call["result"]
    deposit = float(args.get("security_deposit") or 0)
    return {
        "called": True,
        "rent_ok": abs(float(args.get("monthly_rent") or 0) - expected["monthly_rent"]) < 0.01,
        "deposit_ok": abs(deposit - expected["security_deposit"]) < 0.01,
        "problems_ok": result.get("problems_found") == expected["problems_found"],
    }
