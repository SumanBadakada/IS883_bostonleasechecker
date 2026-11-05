# --- Owner: (assign, see docs/TEAM_SPLIT.md) | runs the §5.5 test set and the repeated comparison ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Run the app's own pipeline (leasecheck.analyzer.analyze and the chat prompt) on test set v2.

    export GEMINI_API_KEY=...
    python -m eval.run_v2 main        # every input once, every deterministic check
    python -m eval.run_v2 compare     # retrieval vs the model's own knowledge, seeds 1..10
    python -m eval.run_v2 report      # rebuild eval/results/v2/SUMMARY.md from saved runs

Results go to eval/results/v2/. Runs already saved are skipped, so a run stopped by the free-tier daily
quota resumes where it stopped. Expected results were committed before the first run (see
eval/build_test_set_v2.py); nothing here edits them.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from eval import checks_v2 as chk
from eval.metrics import score_lease, summarise
from leasecheck import analyzer, config, prompts
from leasecheck.analyzer import ChargesResult, analyze, findings_digest
from leasecheck.llm import GeminiLLM, LLMError
from leasecheck.parsing import InputRejected
from leasecheck.prompts import PromptVersion
from leasecheck.retrieval import SourceIndex, format_passages
from leasecheck.schemas import parse_batch

HERE = Path(__file__).resolve().parent
V2 = HERE / "test_set_v2"
PRIVATE = HERE / "test_set" / "private"
OUT = HERE / "results" / "v2"
SEEDS = range(1, 11)
COMPARE_INPUTS = ["real_01_gh_addendum.pdf", "real_02_st_paul_brookline.pdf", "alt_late_fee_31_days.pdf",
                  "alt_late_fee_5_days.pdf", "alt_deposit_1_5_months.pdf", "alt_broker_tenant_hired.pdf"]

# ---------- the "model's own knowledge" prompt: v2 with every reference to the passages removed ----------

_MEMORY_EDITS = [
    ("conflicts with a Massachusetts law in the SOURCE PASSAGES, or asks the\n  tenant to give up a right the "
     "passages say cannot be waived.",
     "conflicts with Massachusetts law as you know it, or asks the\n  tenant to give up a right Massachusetts "
     "law says cannot be waived."),
    ("legal as far as the passages show", "legal as far as you know"),
    ("a clause the passages do not touch", "a clause no Massachusetts law addresses"),
    ("2. Look for a SOURCE PASSAGE that addresses it. Use only the passages provided, never your memory of the law.",
     "2. Recall the Massachusetts statute or regulation that addresses it."),
    ("3. If a passage says the clause is not allowed, label it possibly_unlawful and cite that passage.",
     "3. If that law says the clause is not allowed, label it possibly_unlawful and name that law."),
    ("4. If no passage addresses it, the label is lawful or unusual, never possibly_unlawful.",
     "4. If no Massachusetts law addresses it, the label is lawful or unusual, never possibly_unlawful."),
    ("- source_ids must contain only IDs that appear in square brackets in SOURCE PASSAGES.\n- citation is the "
     "legal citation shown next to that ID. Leave both empty when no passage applies.",
     "- Leave source_ids empty.\n- citation is the Massachusetts statute or regulation you relied on. Leave it "
     "empty when no law applies."),
]


def memory_prompt() -> PromptVersion:
    system = prompts.PROMPTS["v2"].system
    for old, new in _MEMORY_EDITS:
        assert old in system, old
        system = system.replace(old, new)
    task = prompts.PROMPTS["v2"].task
    assert task.startswith("SOURCE PASSAGES\n{passages}\n\n")
    task = task.removeprefix("SOURCE PASSAGES\n{passages}\n\n").replace("citation from the passage on late fees",
                                                                         "citation to the late-fee law")
    return PromptVersion(system=system, task=task)


prompts.PROMPTS["v2-memory"] = memory_prompt()  # registered for this process only; the app never sees it


# ---------- a GeminiLLM that logs every request and retries Google's passing overloads ----------

class EvalLLM(GeminiLLM):
    RETRIES, WAIT = 5, 60

    def __init__(self, api_key: str, model: str = config.MODEL):
        super().__init__(api_key, model=model, fallback_models=())  # one model per run
        self.stage, self.call_log, self.parse_log = "other", [], []
        self._embed_cache: dict[tuple[str, str], np.ndarray] = {}
        generate = self.client.models.generate_content

        def logged(**kwargs):
            response = generate(**kwargs)
            meta = getattr(response, "usage_metadata", None)
            get = lambda k: (getattr(meta, k, 0) or 0) if meta else 0  # noqa: E731
            self.call_log.append({"stage": self.stage, "input": get("prompt_token_count"),
                                  "output": get("candidates_token_count"), "thinking": get("thoughts_token_count")})
            return response

        self.client.models.generate_content = logged

    def _with_retries(self, fn, models=None):
        for attempt in range(self.RETRIES + 1):
            try:
                return super()._with_retries(fn, models)
            except LLMError as exc:
                if not any(t in str(exc) for t in ("overloaded", "Could not reach")) or attempt == self.RETRIES:
                    raise
            print(f"  Gemini overloaded or unreachable, retrying this request in {self.WAIT}s", flush=True)
            time.sleep(self.WAIT)

    def generate_json(self, system, prompt, schema):
        self.stage = "classify"
        raw = super().generate_json(system, prompt, schema)
        self.parse_log.append(parse_batch(raw) is not None)
        return raw

    def run_with_tools(self, *args, **kwargs):
        self.stage = "charges"
        return super().run_with_tools(*args, **kwargs)

    def chat(self, *args, **kwargs):
        self.stage = "chat"
        return super().chat(*args, **kwargs)

    def embed(self, texts, task_type):
        missing = [t for t in dict.fromkeys(texts) if (task_type, t) not in self._embed_cache]
        if missing:
            self.call_log.append({"stage": "embed", "input": 0, "output": 0, "thinking": 0})
            for text, vector in zip(missing, super().embed(missing, task_type)):
                self._embed_cache[(task_type, text)] = vector
        return np.stack([self._embed_cache[(task_type, t)] for t in texts])


# ---------- inputs ----------

def load_inputs() -> tuple[list[dict], list[dict]]:
    gold = json.loads((V2 / "gold.json").read_text())
    inputs = []
    private_gold = PRIVATE / "gold.json"
    if private_gold.exists():
        for item in json.loads(private_gold.read_text())["inputs"]:
            inputs.append({**item, "file": f"private/{item['file']}"})
    inputs += gold["inputs"]
    for item in inputs:
        item["path"] = str((HERE / "test_set" / item["file"]) if item["file"].startswith("private/")
                           else (V2 / item["file"]))
    return inputs, gold["chat"]


def run_input(llm: EvalLLM, index, item: dict, prompt_version: str = "v2") -> dict:
    record = {"file": item["file"], "expect": item["expect"]}
    calls_before, parse_before = len(llm.call_log), len(llm.parse_log)
    try:
        result = analyze(Path(item["path"]).read_bytes(), Path(item["file"]).name, llm, index,
                         prompt_version=prompt_version)
        record.update(outcome="analyzed", warnings=result.warnings, errors=result.errors,
                      parse_failures=result.parse_failures, charges_summary=result.charges.summary,
                      tool_calls=[asdict(c) for c in result.charges.tool_calls],
                      predicted=[{"text": r.clause.text, "label": r.label,
                                  "source_ids": r.finding.source_ids if r.finding else [],
                                  "citation": r.finding.citation if r.finding else "",
                                  "explanation": r.finding.explanation if r.finding else ""} for r in result.clauses])
        record["_result"] = result
    except InputRejected as exc:
        record["outcome"] = f"rejected:{exc.reason}"
    except LLMError as exc:
        record["outcome"] = f"api_error:{exc}"
    record["calls"] = llm.call_log[calls_before:]
    record["raw_parsed"] = llm.parse_log[parse_before:]
    return record


def score_input(item: dict, record: dict, base: dict | None) -> list[dict]:
    checks = [chk.outcome(item["expect"], record["outcome"])]
    if record["outcome"] != "analyzed":
        return checks
    predicted = record["predicted"]
    checks += chk.warnings_raised(item.get("expect_warnings", []), record["warnings"])
    if item.get("charges"):
        checks += chk.charges(item["charges"], record["tool_calls"])
    if item.get("tool_rejects_rent"):
        checks.append(chk.tool_rejects_bad_rent(record["tool_calls"]))
    if item.get("same_labels_as") and base:
        checks.append(chk.same_labels(base["predicted"], predicted, item["clauses"][0]["text"]))
    if item.get("explanations_exclude"):
        checks.append(chk.text_excludes("abuse:not_repeated", [p["explanation"] for p in predicted],
                                        item["explanations_exclude"]))
    if item.get("source") == "derived" and item["clauses"]:
        rider = chk.rider_label(item["clauses"][0], predicted)
        if rider:
            checks.append(rider)
    return checks


def clause_rows(item: dict, record: dict) -> list[dict]:
    """Rows for recall and precision: every clause of a real lease, plus the added clause of an altered one."""
    if record["outcome"] != "analyzed" or not item.get("clauses"):
        return []
    gold = [c for c in item["clauses"] if c["label"] in ("lawful", "unusual", "possibly_unlawful")]
    return score_lease({"clauses": gold}, record["predicted"])["rows"] if gold else []


def tokens_by_stage(calls: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for c in calls:
        row = out.setdefault(c["stage"], {"requests": 0, "input": 0, "output": 0, "thinking": 0})
        row["requests"] += 1
        for k in ("input", "output", "thinking"):
            row[k] += c[k]
    for row in out.values():
        row["cost_usd"] = (row["input"] * config.PRICE_INPUT_PER_M
                           + (row["output"] + row["thinking"]) * config.PRICE_OUTPUT_PER_M) / 1e6
    return out


# ---------- main run: every input once ----------

def run_main(llm: EvalLLM, index) -> dict:
    inputs, chat = load_inputs()
    records, all_rows, real_rows = [], [], []
    base = None
    for n, item in enumerate(inputs, 1):
        print(f"[{n}/{len(inputs)}] {item['file']}", flush=True)
        record = run_input(llm, index, item)
        if Path(item["file"]).name == "real_02_st_paul_brookline.pdf":
            base = record
        record["checks"] = score_input(item, record, base)
        rows = clause_rows(item, record)
        record["rows"] = rows
        all_rows += rows
        if item.get("source") == "real":
            real_rows += rows
        records.append(record)

    chat_records = []
    if base and base["outcome"] == "analyzed":
        result = base["_result"]
        for q in chat:
            print(f"[chat] {q['id']}", flush=True)
            calls_before = len(llm.call_log)
            hits = index.search_many(llm, [q["question"]], k=4)[0]
            system = prompts.CHAT_SYSTEM.format(findings=findings_digest(result),
                                                passages=format_passages([c for c, _ in hits]) or "(none)")
            try:
                answer = llm.chat(system, [], q["question"])
            except LLMError as exc:
                answer = f"api_error:{exc}"
            exp = q["expect"]
            checks = []
            if exp.get("exclude"):
                checks.append(chk.text_excludes("chat:excludes", [answer], exp["exclude"]))
            if exp.get("include_any"):
                checks.append(chk.text_includes_any("chat:cites", answer, exp["include_any"]))
            chat_records.append({**q, "answer": answer, "checks": checks, "calls": llm.call_log[calls_before:]})

    for r in records:
        r.pop("_result", None)
    raw = [ok for r in records for ok in r["raw_parsed"]]
    calls = [c for r in records for c in r["calls"]] + [c for r in chat_records for c in r["calls"]]
    every_check = [c for r in records for c in r["checks"]] + [c for r in chat_records for c in r["checks"]]
    analyzed = [r for r in records if r["outcome"] == "analyzed"]
    summary = {
        "model": llm.model, "temperature": config.TEMPERATURE, "seed": config.SEED,
        "real_leases": summarise(real_rows) if real_rows else {},
        "real_and_altered": summarise(all_rows) if all_rows else {},
        "raw_answers": len(raw), "raw_answers_parsed": sum(raw),
        "checks_passed": sum(c["pass"] for c in every_check), "checks_total": len(every_check),
        "tokens_by_stage": tokens_by_stage(calls),
        "requests_per_analyzed_input": sum(len(r["calls"]) for r in analyzed) / max(len(analyzed), 1),
    }
    return {"summary": summary, "inputs": records, "chat": chat_records}


# ---------- comparison: retrieval vs the model's own knowledge, ten seeds each ----------

VERSIONS = {"retrieval": "v2", "memory": "v2-memory"}


def run_compare(llm: EvalLLM, index) -> None:
    inputs = {Path(i["file"]).name: i for i in load_inputs()[0]}
    chosen = [inputs[name] for name in COMPARE_INPUTS if name in inputs]
    out = OUT / "compare"
    out.mkdir(parents=True, exist_ok=True)
    # The charge step is the same in both versions, so it is skipped to save free-tier requests.
    analyzer.check_charges = lambda llm_, clauses: ChargesResult("Not checked in the comparison.", [])
    saved_seed = config.SEED
    try:
        for seed in SEEDS:
            for version, prompt_version in VERSIONS.items():
                path = out / f"{version}_seed{seed:02d}.json"
                if path.exists():
                    continue
                config.SEED = seed
                print(f"=== {version}, seed {seed} ===", flush=True)
                records = []
                for item in chosen:
                    record = run_input(llm, index if version == "retrieval" else None, item, prompt_version)
                    record.pop("_result", None)
                    record["rows"] = clause_rows(item, record)
                    records.append(record)
                if any(r["outcome"].startswith("api_error") for r in records):
                    print("API error in this run; not saved. Rerun later.", flush=True)
                    if any("daily quota" in r["outcome"] for r in records):
                        return
                    continue
                path.write_text(json.dumps({"version": version, "seed": seed, "inputs": records}, indent=1))
    finally:
        config.SEED = saved_seed


def compare_summary() -> dict:
    out = {}
    for version in VERSIONS:
        runs = [json.loads(p.read_text()) for p in sorted((OUT / "compare").glob(f"{version}_seed*.json"))]
        if not runs:
            continue
        per_seed = []
        for run in runs:
            rows = [row for r in run["inputs"] for row in r["rows"]]
            s = summarise(rows)
            calls = [c for r in run["inputs"] for c in r["calls"] if c["stage"] == "classify"]
            per_seed.append({"seed": run["seed"], "recall": s["recall_possibly_unlawful"],
                             "precision": s["precision_possibly_unlawful"],
                             "input_tokens": sum(c["input"] for c in calls),
                             "output_tokens": sum(c["output"] + c["thinking"] for c in calls),
                             "leases": len(run["inputs"])})

        def stats(key):
            vals = [p[key] for p in per_seed if p[key] is not None]
            return {"mean": statistics.mean(vals), "min": min(vals), "max": max(vals),
                    "sd": statistics.pstdev(vals)} if vals else None

        tokens_in = statistics.mean(p["input_tokens"] / p["leases"] for p in per_seed)
        tokens_out = statistics.mean(p["output_tokens"] / p["leases"] for p in per_seed)
        # How often each target clause got each label across the seeds: the rate the brief asks for.
        flips: dict[str, dict] = {}
        for run in runs:
            for r in run["inputs"]:
                for row in r["rows"]:
                    if row["gold"] != "lawful" or Path(r["file"]).name.startswith("alt_"):
                        key = f"{Path(r['file']).name}:{row['key']}"
                        flips.setdefault(key, {"gold": row["gold"]}).setdefault(row["pred"], 0)
                        flips[key][row["pred"]] += 1
        out[version] = {"runs": len(runs), "recall": stats("recall"), "precision": stats("precision"),
                        "per_seed": per_seed, "input_tokens_per_lease": tokens_in,
                        "output_tokens_per_lease": tokens_out,
                        "cost_per_1000_leases_usd": (tokens_in * config.PRICE_INPUT_PER_M
                                                     + tokens_out * config.PRICE_OUTPUT_PER_M) / 1e3,
                        "clause_label_counts": flips}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["main", "compare", "report"])
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.what == "report":
        (OUT / "compare_summary.json").write_text(json.dumps(compare_summary(), indent=1))
        print(f"Wrote {OUT / 'compare_summary.json'}")
        return
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY in your environment first.")
    llm = EvalLLM(api_key)
    index = SourceIndex.build(llm)
    if args.what == "main":
        result = run_main(llm, index)
        (OUT / "main.json").write_text(json.dumps(result, indent=1, default=str))
        s = result["summary"]
        print(json.dumps({k: s[k] for k in ("checks_passed", "checks_total", "raw_answers", "raw_answers_parsed")}))
        for part in ("real_leases", "real_and_altered"):
            p = s[part]
            print(part, "recall", p.get("recall_possibly_unlawful"), "precision", p.get("precision_possibly_unlawful"))
    else:
        run_compare(llm, index)
        (OUT / "compare_summary.json").write_text(json.dumps(compare_summary(), indent=1))


if __name__ == "__main__":
    main()
