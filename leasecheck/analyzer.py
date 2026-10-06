# --- Owner: (assign, see docs/TEAM_SPLIT.md) | the pipeline: clauses -> retrieval -> classify -> charges ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Runs one lease through the whole app. Used by both app.py and eval/run_eval.py, so the eval measures
exactly what users get.

    upload -> parsing.load_clauses (code)
           -> retrieval: top passages per clause (embeddings + cosine similarity)
           -> classify each batch of clauses (structured output, versioned prompt)
                 failure path: unparseable JSON -> one retry -> clauses marked "not_checked"
           -> move-in charges (model decides to call check_move_in_charges)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import config, prompts
from .charges import CHECK_MOVE_IN_CHARGES_DECLARATION, TOOLS
from .llm import ToolCall, Usage
from .parsing import Clause, load_clauses
from .retrieval import Chunk, SourceIndex, format_passages
from .schemas import BatchFindings, ClauseFinding, parse_batch


@dataclass
class ClauseResult:
    clause: Clause
    finding: Optional[ClauseFinding]  # None = the model's output for this clause could not be used
    retrieved_ids: list[str] = field(default_factory=list)
    cited: list[Chunk] = field(default_factory=list)  # the source passages the finding cites, shown to the user

    @property
    def label(self) -> str:
        return self.finding.label if self.finding else "not_checked"


@dataclass
class ChargesResult:
    summary: str
    tool_calls: list[ToolCall]

    @property
    def check(self) -> Optional[dict]:
        for call in self.tool_calls:
            if call.name == "check_move_in_charges" and "items" in call.result:
                return call.result
        return None


@dataclass
class AnalysisResult:
    clauses: list[ClauseResult]
    charges: ChargesResult
    usage: Usage
    prompt_version: str
    used_retrieval: bool
    parse_failures: int = 0
    errors: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.clauses:
            out[r.label] = out.get(r.label, 0) + 1
        return out


MONEY = re.compile(r"\$\s?\d|\bdeposit\b|\bfee\b|\bfirst month|\blast month|\block\b", re.IGNORECASE)


def analyze(
    data: bytes,
    filename: str,
    llm,
    index: Optional[SourceIndex],
    prompt_version: str = prompts.ACTIVE_VERSION,
    progress: Callable[[str, float], None] = lambda msg, frac: None,
) -> AnalysisResult:
    """Raises parsing.InputRejected for bad inputs and llm.LLMError if the API fails outright."""
    start_usage = Usage(llm.usage.calls, llm.usage.input_tokens, llm.usage.output_tokens)
    clauses = load_clauses(data, filename)
    prompt = prompts.PROMPTS[prompt_version]

    # Retrieval: one embedding request for all clauses.
    progress("Finding the relevant Massachusetts law for each clause", 0.1)
    retrieved: list[list[Chunk]] = [[] for _ in clauses]
    if index is not None:
        hits = index.search_many(llm, [c.text for c in clauses], k=config.TOP_K_PER_CLAUSE)
        retrieved = [[chunk for chunk, _score in row] for row in hits]

    results: list[ClauseResult] = []
    parse_failures = 0
    batches = [clauses[i:i + config.CLAUSES_PER_BATCH] for i in range(0, len(clauses), config.CLAUSES_PER_BATCH)]
    for b, batch in enumerate(batches):
        progress(f"Reviewing clauses {batch[0].clause_id}-{batch[-1].clause_id} of {len(clauses)}",
                 0.15 + 0.7 * b / len(batches))
        passages = _batch_passages([retrieved[c.clause_id - 1] for c in batch])
        task = prompt.task.format(
            passages=format_passages(passages) if passages else "(no passages retrieved)",
            clauses=prompts.format_clauses(batch),
        )
        parsed = _classify_with_retry(llm, prompt.system, task)
        if parsed is None:
            parse_failures += 1
        by_id = {f.clause_id: f for f in parsed.findings} if parsed else {}
        allowed = {p.chunk_id: p for p in passages}
        for clause in batch:
            finding = by_id.get(clause.clause_id)
            cited: list[Chunk] = []
            if finding is not None:
                # Drop any source id the model invented; the citation must point at a passage we gave it.
                finding.source_ids = [s for s in finding.source_ids if s in allowed]
                cited = [allowed[s] for s in finding.source_ids]
            results.append(ClauseResult(clause, finding, [c.chunk_id for c in retrieved[clause.clause_id - 1]], cited))

    progress("Checking move-in charges", 0.9)
    charges = check_charges(llm, clauses)

    usage = Usage(llm.usage.calls - start_usage.calls,
                  llm.usage.input_tokens - start_usage.input_tokens,
                  llm.usage.output_tokens - start_usage.output_tokens)
    progress("Done", 1.0)
    return AnalysisResult(results, charges, usage, prompt_version, index is not None, parse_failures)


def _batch_passages(per_clause: list[list[Chunk]]) -> list[Chunk]:
    """Union of each clause's passages, best-ranked first, capped so prompts stay small."""
    seen: dict[str, Chunk] = {}
    for rank in range(config.TOP_K_PER_CLAUSE):
        for chunks in per_clause:
            if rank < len(chunks) and chunks[rank].chunk_id not in seen:
                seen[chunks[rank].chunk_id] = chunks[rank]
    return list(seen.values())[: config.MAX_CHUNKS_PER_BATCH]


def _classify_with_retry(llm, system: str, task: str) -> Optional[BatchFindings]:
    raw = llm.generate_json(system, task, BatchFindings)
    parsed = parse_batch(raw)
    if parsed is None:
        raw = llm.generate_json(
            system, task + "\n\nYour previous answer was not valid JSON for the schema. Return only the JSON object.",
            BatchFindings,
        )
        parsed = parse_batch(raw)
    return parsed


def check_charges(llm, clauses: list[Clause]) -> ChargesResult:
    excerpts = [c for c in clauses if MONEY.search(c.text)]
    if not excerpts:
        return ChargesResult("No move-in charges were found in this lease.", [])
    task = prompts.CHARGES_TASK.format(excerpts=prompts.format_clauses(excerpts))
    run = llm.run_with_tools(prompts.CHARGES_SYSTEM, task, [CHECK_MOVE_IN_CHARGES_DECLARATION], TOOLS)
    summary = run.text.strip()
    if not run.tool_calls or "NO_CHARGES_FOUND" in summary:
        summary = "No move-in charges were found in this lease."
    return ChargesResult(summary, run.tool_calls)


def findings_digest(result: AnalysisResult) -> str:
    """Compact text of the findings, used as context for the follow-up chat."""
    lines = []
    for r in result.clauses:
        if r.finding:
            lines.append(f"Clause {r.clause.clause_id} [{r.label}] {r.finding.topic}: {r.finding.explanation} "
                         f"{('(' + r.finding.citation + ')') if r.finding.citation else ''}")
    if result.charges.check:
        for item in result.charges.check["items"]:
            lines.append(f"Move-in charge: {item['charge']} ${item['amount']:,.2f} -> {item['status']}: {item['reason']}")
    return "\n".join(lines)
