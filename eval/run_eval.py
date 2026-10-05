# --- Owner: (assign, see docs/TEAM_SPLIT.md) | runs the app's pipeline on the test set and reports the metric ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Run the real pipeline (leasecheck.analyzer.analyze) on every test input and score it.

    export GEMINI_API_KEY=...            # never commit it
    python -m eval.run_eval                          # active prompt, with retrieval
    python -m eval.run_eval --prompt-version v1      # the "before" number
    python -m eval.run_eval --no-retrieval           # retrieval ablation
    python -m eval.run_eval --limit 2                # develop against two rows first (§5.4)

Writes eval/results/<timestamp>_<version>.json and prints a summary. Measured tokens per lease feed the
cost model (§5.6).
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from eval.metrics import score_charges, score_lease, summarise
from leasecheck import prompts
from leasecheck.analyzer import analyze
from leasecheck.llm import GeminiLLM, LLMError
from leasecheck.parsing import InputRejected
from leasecheck.retrieval import SourceIndex

HERE = Path(__file__).resolve().parent


def load_gold(include_private: bool) -> list[dict]:
    inputs = []
    for folder in [HERE / "test_set"] + ([HERE / "test_set" / "private"] if include_private else []):
        gold_path = folder / "gold.json"
        if gold_path.exists():
            for item in json.loads(gold_path.read_text())["inputs"]:
                item["path"] = str(folder / item["file"])
                inputs.append(item)
    return inputs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-version", default=prompts.ACTIVE_VERSION, choices=list(prompts.PROMPTS))
    ap.add_argument("--no-retrieval", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--private", action="store_true", help="also run consented real leases in test_set/private/")
    ap.add_argument("--pause", type=float, default=5.0, help="seconds between leases, for free-tier rate limits")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY in your environment first.")
    llm = GeminiLLM(api_key)
    index = None if args.no_retrieval else SourceIndex.build(llm)

    gold_inputs = load_gold(args.private)
    if args.limit:
        gold_inputs = gold_inputs[: args.limit]

    all_rows, per_input, charge_checks = [], [], []
    for n, item in enumerate(gold_inputs, start=1):
        print(f"[{n}/{len(gold_inputs)}] {item['file']}", flush=True)
        data = Path(item["path"]).read_bytes()
        record = {"file": item["file"], "expect": item["expect"]}
        try:
            result = analyze(data, item["file"], llm, index, prompt_version=args.prompt_version)
            record["outcome"] = "analyzed"
            record["usage"] = vars(result.usage)
            record["parse_failures"] = result.parse_failures
            predicted = [{"text": r.clause.text, "label": r.label,
                          "source_ids": r.finding.source_ids if r.finding else [],
                          "citation": r.finding.citation if r.finding else ""} for r in result.clauses]
            record["predicted"] = predicted
            record["tool_calls"] = [vars(c) for c in result.charges.tool_calls]
            if item["kind"] == "lease":
                scored = score_lease(item, predicted)
                record["rows"] = scored["rows"]
                all_rows += scored["rows"]
                record["charges"] = score_charges(item["charges"], record["tool_calls"])
                charge_checks.append(record["charges"])
        except InputRejected as exc:
            record["outcome"] = f"rejected:{exc.reason}"
        except LLMError as exc:
            record["outcome"] = f"api_error:{exc}"
        record["handled_as_expected"] = record["outcome"] == item["expect"]
        per_input.append(record)
        if record["outcome"] == "analyzed" and n < len(gold_inputs):
            time.sleep(args.pause)

    summary = summarise(all_rows) if all_rows else {}
    analyzed = [r for r in per_input if r["outcome"] == "analyzed"]
    batches_failed = sum(r.get("parse_failures", 0) for r in analyzed)
    summary.update({
        "prompt_version": args.prompt_version,
        "retrieval": not args.no_retrieval,
        "inputs": len(per_input),
        "inputs_handled_as_expected": sum(r["handled_as_expected"] for r in per_input),
        "batches_failed_to_parse": batches_failed,
        "tool_called_when_expected": _rate(charge_checks, "called"),
        "tool_rent_correct": _rate(charge_checks, "rent_ok"),
        "tool_deposit_correct": _rate(charge_checks, "deposit_ok"),
        "tool_problem_count_correct": _rate(charge_checks, "problems_ok"),
        "avg_input_tokens_per_lease": _avg(analyzed, "input_tokens"),
        "avg_output_tokens_per_lease": _avg(analyzed, "output_tokens"),
        "avg_calls_per_lease": _avg(analyzed, "calls"),
    })

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"{args.prompt_version}{'_noretrieval' if args.no_retrieval else ''}"
    out = out_dir / f"{stamp}_{tag}.json"
    out.write_text(json.dumps({"summary": summary, "inputs": per_input}, indent=2))

    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        if k != "confusion":
            print(f"{k:34} {v:.3f}" if isinstance(v, float) else f"{k:34} {v}")
    print("confusion (rows = expected, cols = predicted):")
    for g, row in summary.get("confusion", {}).items():
        print(f"  {g:18} {row}")
    print(f"\nSaved {out}")


def _rate(items: list[dict], key: str):
    return sum(i[key] for i in items) / len(items) if items else None


def _avg(records: list[dict], key: str):
    return sum(r["usage"][key] for r in records) / len(records) if records else None


if __name__ == "__main__":
    main()
