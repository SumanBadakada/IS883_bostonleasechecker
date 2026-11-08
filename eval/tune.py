# --- Erdan: one-change-at-a-time tuning on the five real leases ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Change one thing at a time against the app's settings and measure recall and precision on the five real
leases, each version run with seeds 1..N.

    export GEMINI_API_KEY=...
    python -m eval.tune run --seeds 5     # resumes: runs already saved are skipped
    python -m eval.tune report            # writes tune_summary.json (no lease text, safe to commit)

The baseline is exactly the app (prompt v2, temperature 0.1, top-k 3, structured output, few-shot, no
written reasoning). Every other version differs from it in one setting. Raw runs hold the leases' text and
go to the git-ignored results/v2/<model>/tune/.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from eval.metrics import summarise
from eval.run_v2 import OUT, EvalLLM, clause_rows, load_inputs, run_input
from leasecheck import analyzer, config, prompts
from leasecheck.analyzer import ChargesResult
from leasecheck.llm import LLMError
from leasecheck.prompts import PromptVersion
from leasecheck.retrieval import SourceIndex
from leasecheck.schemas import Label, parse_batch

TUNE = OUT / "tune"
LEASES = ["real_01_gh_addendum.pdf", "real_02_st_paul_brookline.pdf", "real_03_104_academy.pdf",
          "real_04_residential_lease_2025_noimages.pdf", "real_05_graduate_residence_license.pdf"]

# --- Erdan: prompt v2 cut into its eight elements, and the chain-of-thought prompt and schema ---
# Each piece is (element, text). Joined in order they give back prompt v2 exactly (checked below), so removing
# one element removes only that element's words. "keep" pieces are the clauses themselves and the headings.

_SYSTEM_PIECES = [
    ("persona", "You are a careful Massachusetts tenant-rights reviewer. "),
    ("context", "Your reader is a graduate student\nabout to sign their first Boston apartment lease. "
                "They are not a lawyer.\n\n"),
    ("instruction", """For every clause you are given, decide ONE label:
- "possibly_unlawful": the clause conflicts with a Massachusetts law in the SOURCE PASSAGES, or asks the
  tenant to give up a right the passages say cannot be waived.
- "unusual": legal as far as the passages show, but uncommon or unfavourable enough that the tenant
  should ask about it before signing (e.g. a very short notice period, broad fees for damage).
- "lawful": ordinary lease language, or a clause the passages do not touch and that is not unusual.

Work through each clause in this order:
1. Say to yourself what the clause requires of the tenant or the landlord.
2. Look for a SOURCE PASSAGE that addresses it."""),
    ("constraints", " Use only the passages provided, never your memory of the law."),
    ("instruction", "\n3. If a passage says the clause is not allowed, label it possibly_unlawful and cite that passage.\n"),
    ("constraints", "4. If no passage addresses it, the label is lawful or unusual, never possibly_unlawful.\n"),
    ("keep", "\nRules:\n"),
    ("constraints", "- source_ids must contain only IDs that appear in square brackets in SOURCE PASSAGES.\n"),
    ("format", "- citation is the legal citation shown next to that ID. Leave both empty when no passage applies.\n"),
    ("tone", "- explanation is one or two plain sentences addressed to the tenant (\"you\"). No legal jargon.\n"
             "- Say \"may\" and \"possibly\". You are flagging for review, not giving legal advice.\n"),
    ("format", "- Return exactly one finding per clause, with the clause_id you were given."),
]

_V2_TASK = prompts.PROMPTS["v2"].task
_TASK_PIECES = [
    ("data", "SOURCE PASSAGES\n{passages}\n\n"),
    ("exemplar", _V2_TASK[_V2_TASK.index("EXAMPLES"):_V2_TASK.index("CLAUSES TO REVIEW")]),
    ("keep", "CLAUSES TO REVIEW\n{clauses}\n\n"),
    ("format", "Return one finding per clause."),
]

assert "".join(t for _, t in _SYSTEM_PIECES) == prompts.PROMPTS["v2"].system
assert "".join(t for _, t in _TASK_PIECES) == _V2_TASK

ELEMENTS = ("persona", "context", "instruction", "exemplar", "format", "constraints", "tone", "data")


def without(element: Optional[str]) -> PromptVersion:
    """Prompt v2 with one element's words removed (None = v2 unchanged)."""
    system = "".join(t for e, t in _SYSTEM_PIECES if e != element)
    if element == "instruction":  # the two constraints left from the numbered steps become plain sentences
        system = system.replace("\n\n Use only", "\n\nUse only").replace("law.4. If no", "law.\nIf no")
    task = "".join(t for e, t in _TASK_PIECES if e != element).rstrip("\n")
    return PromptVersion(system=system.strip(), task=task)


_COT_OLD = "Work through each clause in this order:\n1. Say to yourself what"
_COT_NEW = ("Work through each clause in this order, and write these steps in the reasoning field before you "
            "choose the label:\n1. Write down what")


def cot_prompt() -> PromptVersion:
    v2 = prompts.PROMPTS["v2"]
    assert _COT_OLD in v2.system
    return PromptVersion(system=v2.system.replace(_COT_OLD, _COT_NEW), task=v2.task)


class ClauseFindingCoT(BaseModel):
    """ClauseFinding with a reasoning field first, so the model writes its steps before it picks a label."""

    clause_id: int = Field(description="The clause number exactly as given in the prompt.")
    reasoning: str = Field(description="Steps 1-3 for this clause, in two to four short sentences.")
    topic: str = Field(description="Short topic, e.g. 'security deposit', 'late fee', 'repairs'.")
    label: Label
    explanation: str = Field(description="One or two plain-English sentences for a tenant.")
    source_ids: list[str] = Field(default_factory=list, description="IDs of the provided source passages "
                                  "that support the label. Empty if none apply.")
    citation: str = Field(default="", description="Human-readable legal citation. Empty if none applies.")


class BatchFindingsCoT(BaseModel):
    findings: list[ClauseFindingCoT]


# --- Erdan: the 16 versions (each differs from the baseline in one setting) and how they are applied ---

VARIANTS: dict[str, dict] = {
    "baseline": {},
    "temperature_0.0": {"temperature": 0.0},
    "temperature_0.3": {"temperature": 0.3},
    "chain_of_thought": {"prompt": "tune-cot", "schema": "cot"},
    "top_k_1": {"top_k": 1},
    "top_k_5": {"top_k": 5},
    "top_k_10": {"top_k": 10},
    **{f"no_{e}": {"prompt": f"tune-no-{e}", **({"retrieval": False} if e == "data" else {})} for e in ELEMENTS},
    "no_schema": {"schema": "none"},
    # No passages, and the prompt run_v2 uses for the comparison: v2 with "the passages" replaced by
    # "Massachusetts law as you know it" (no_data keeps v2, which forbids flagging without a passage).
    "own_knowledge": {"prompt": "v2-memory", "retrieval": False},
}
# zero-shot is "no_exemplar"; few-shot (three examples) is the baseline.

prompts.PROMPTS["tune-cot"] = cot_prompt()  # registered for this process only; the app never sees them
for _e in ELEMENTS:
    prompts.PROMPTS[f"tune-no-{_e}"] = without(_e)


class TuneLLM(EvalLLM):
    """EvalLLM that can swap the response schema (CoT) or drop structured output altogether."""

    schema_mode = "schema"

    def generate_json(self, system, prompt, schema):
        if self.schema_mode == "schema":
            return super().generate_json(system, prompt, schema)
        self.stage = "classify"
        if self.schema_mode == "cot":
            raw = super(EvalLLM, self).generate_json(system, prompt, BatchFindingsCoT)
        else:  # the same prompt, no response_schema and no JSON mode: what the course's cell 6 shows breaking
            response = self._with_retries(lambda model: self.client.models.generate_content(
                model=model, contents=prompt, config=self._config(model, system)))
            self.usage.add(response)
            raw = response.text or ""
        self.parse_log.append(parse_batch(raw) is not None)
        return raw


def apply(variant: dict, llm: TuneLLM) -> None:
    config.TEMPERATURE = variant.get("temperature", 0.1)
    config.TOP_K_PER_CLAUSE = variant.get("top_k", 3)
    llm.schema_mode = variant.get("schema", "schema")


# --- Erdan: running every version on seeds 1..N, resuming after quota stops ---

def _count_passages(log: list[int]):
    original = analyzer._batch_passages

    def counted(per_clause):
        out = original(per_clause)
        log.append(len(out))
        return out
    return counted


def run(llm: TuneLLM, index: SourceIndex, seeds: range, only: Optional[list[str]] = None) -> None:
    inputs = {Path(i["file"]).name: i for i in load_inputs()[0]}
    leases = [inputs[name] for name in LEASES]
    TUNE.mkdir(parents=True, exist_ok=True)
    analyzer.check_charges = lambda llm_, clauses: ChargesResult("Not checked in tuning.", [])  # same in every version
    passages_log: list[int] = []
    analyzer._batch_passages = _count_passages(passages_log)
    for seed in seeds:  # seeds outermost, so a quota stop leaves every version with the same number of runs
        for name, variant in VARIANTS.items():
            if only and name not in only:
                continue
            path = TUNE / f"{name}_seed{seed:02d}.json"
            if path.exists():
                continue
            config.SEED = seed
            apply(variant, llm)
            print(f"=== {name}, seed {seed} ===", flush=True)
            reused = _reuse_compare(name, seed)
            records = []
            for item in leases:
                if Path(item["file"]).name in reused:
                    records.append(reused[Path(item["file"]).name])
                    continue
                passages_log.clear()
                record = run_input(llm, index if variant.get("retrieval", True) else None, item,
                                   variant.get("prompt", "v2"))
                record.pop("_result", None)
                record["rows"] = clause_rows(item, record)
                record["passages_per_batch"] = list(passages_log)
                records.append(record)
            apply({}, llm)
            # A lease cut off part-way by an API error (r["errors"]) is as unusable as one that never started.
            if any(r["outcome"].startswith("api_error") or r.get("errors") for r in records):
                print("API error in this run; not saved. Rerun later.", flush=True)
                if any("daily quota" in r["outcome"] + " ".join(r.get("errors", [])) for r in records):
                    raise QuotaExhausted
                continue
            path.write_text(json.dumps({"variant": name, "settings": variant, "seed": seed, "inputs": records},
                                       indent=1))


def _reuse_compare(name: str, seed: int) -> dict:
    """The baseline and own_knowledge are the same configurations as the comparison's 'retrieval' and 'memory'
    runs, so real_01 and real_02 from those runs (same seed) are reused rather than spending quota on them again."""
    version = {"baseline": "retrieval", "own_knowledge": "memory"}.get(name)
    path = TUNE.parent / "compare" / f"{version}_seed{seed:02d}.json"
    if version is None or not path.exists():
        return {}
    out = {}
    for r in json.loads(path.read_text())["inputs"]:
        if Path(r["file"]).name in LEASES:
            out[Path(r["file"]).name] = {**r, "reused_from": path.name}
    return out


class QuotaExhausted(Exception):
    pass


# --- Erdan: summary: mean, spread, tokens, cost, and the seed-by-seed comparison with the baseline ---

def summary() -> dict:
    out = {}
    for name, variant in VARIANTS.items():
        runs = [json.loads(p.read_text()) for p in sorted(TUNE.glob(f"{name}_seed*.json"))]
        if not runs:
            continue
        per_seed = []
        for run_ in runs:
            rows = [row for r in run_["inputs"] for row in r["rows"]]
            s = summarise(rows)
            calls = [c for r in run_["inputs"] for c in r["calls"] if c["stage"] == "classify"]
            parsed = [ok for r in run_["inputs"] for ok in r["raw_parsed"]]
            per_seed.append({
                "seed": run_["seed"], "recall": s["recall_possibly_unlawful"],
                "precision": s["precision_possibly_unlawful"], "agreement": s["agreement"],
                "correct_citation": s["correct_citation_on_true_flags"],
                "flagged": sum(row["pred"] == "possibly_unlawful" for row in rows),
                "not_checked": sum(row["pred"] in ("not_checked", "missing") for row in rows),
                "requests": len(calls), "answers_parsed": sum(parsed), "answers": len(parsed),
                "input_tokens": sum(c["input"] for c in calls),
                "output_tokens": sum(c["output"] + c["thinking"] for c in calls),
                "leases": len(run_["inputs"]),
                "per_lease_recall": {Path(r["file"]).name[:7]: summarise(r["rows"])["recall_possibly_unlawful"]
                                     for r in run_["inputs"] if r["rows"]},
            })

        def stats(key):
            vals = [p[key] for p in per_seed if p[key] is not None]
            if not vals:
                return None
            return {"mean": statistics.mean(vals), "min": min(vals), "max": max(vals),
                    "sd": statistics.pstdev(vals), "n": len(vals)}

        tin = statistics.mean(p["input_tokens"] / p["leases"] for p in per_seed)
        tout = statistics.mean(p["output_tokens"] / p["leases"] for p in per_seed)
        passages = [n for run_ in runs for r in run_["inputs"] for n in r.get("passages_per_batch", [])]
        out[name] = {
            "settings": variant, "runs": len(runs), "recall": stats("recall"), "precision": stats("precision"),
            "agreement": stats("agreement"), "correct_citation": stats("correct_citation"),
            "flagged_per_run": statistics.mean(p["flagged"] for p in per_seed),
            "not_checked_per_run": statistics.mean(p["not_checked"] for p in per_seed),
            "answers_parsed": sum(p["answers_parsed"] for p in per_seed),
            "answers": sum(p["answers"] for p in per_seed),
            "input_tokens_per_lease": tin, "output_tokens_per_lease": tout,
            "cost_per_1000_leases_usd": (tin * config.PRICE_INPUT_PER_M + tout * config.PRICE_OUTPUT_PER_M) / 1e3,
            "mean_passages_per_batch": statistics.mean(passages) if passages else None,
            "per_seed": per_seed,
        }
    # Paired by seed: every version ran on the baseline's seeds, so compare run with run, not mean with mean.
    base = {p["seed"]: p for p in out.get("baseline", {}).get("per_seed", [])}
    for name, v in out.items():
        diffs = [p["recall"] - base[p["seed"]]["recall"] for p in v["per_seed"] if p["seed"] in base]
        if name != "baseline" and diffs:
            v["recall_vs_baseline"] = {"mean_diff": statistics.mean(diffs), "sd_diff": statistics.pstdev(diffs),
                                       "lower_in": sum(d < 0 for d in diffs), "higher_in": sum(d > 0 for d in diffs),
                                       "runs": len(diffs)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["run", "report"])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--wait-for-quota", action="store_true",
                    help="when the daily quota runs out, sleep until it resets (midnight Pacific) and go on")
    ap.add_argument("--model", default=config.MODEL,
                    help="another Gemini model, e.g. gemini-3.1-flash-lite; its runs go to results/v2/<model>/tune/")
    args = ap.parse_args()
    global TUNE
    TUNE = OUT.parent / args.model / "tune"
    if args.what == "run":
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise SystemExit("Set GEMINI_API_KEY in your environment first.")
        llm = TuneLLM(api_key, model=args.model)
        index = SourceIndex.build(llm)
        while True:
            try:
                run(llm, index, range(1, args.seeds + 1), args.only)
                break
            except QuotaExhausted:
                if not args.wait_for_quota:
                    print("Daily quota used up; rerun after midnight Pacific.", flush=True)
                    break
                wait = _seconds_to_quota_reset()
                print(f"Daily quota used up; sleeping {wait / 3600:.1f} h until it resets.", flush=True)
                time.sleep(wait)
    (TUNE.parent / "tune_summary.json").write_text(json.dumps(summary(), indent=1))
    print(f"Wrote {TUNE.parent / 'tune_summary.json'}")


def _seconds_to_quota_reset() -> float:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    reset = (now + timedelta(days=1)).replace(hour=0, minute=10, second=0, microsecond=0)
    return (reset - now).total_seconds()


if __name__ == "__main__":
    try:
        main()
    except LLMError as exc:
        raise SystemExit(str(exc))
