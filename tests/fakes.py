# --- Owner: (assign, see docs/TEAM_SPLIT.md) | a fake model for offline tests ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Stands in for GeminiLLM so tests run without an API key or network."""
from __future__ import annotations

import hashlib
import json
import re

import numpy as np

from leasecheck.charges import check_move_in_charges
from leasecheck.llm import ToolCall, ToolRunResult, Usage


def _bag_of_words(text: str, dim: int = 256) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    for word in re.findall(r"[a-z]+", text.lower()):
        v[int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1
    n = np.linalg.norm(v)
    return v / n if n else v


class FakeLLM:
    embed_model = "fake-embed"

    def __init__(self, json_responses=None, flag_words=("late charge", "any time", "negligence")):
        self.usage = Usage()
        self.json_responses = list(json_responses or [])  # queued raw responses; else heuristic
        self.flag_words = flag_words
        self.prompts: list[str] = []

    def embed(self, texts, task_type):
        self.usage.calls += 1
        return np.stack([_bag_of_words(t) for t in texts])

    def generate_json(self, system, prompt, schema):
        self.usage.calls += 1
        self.usage.input_tokens += len(prompt) // 4
        self.usage.output_tokens += 50
        self.prompts.append(prompt)
        if self.json_responses:
            return self.json_responses.pop(0)
        head, _, clause_part = prompt.rpartition("CLAUSES TO REVIEW") if "CLAUSES TO REVIEW" in prompt \
            else prompt.rpartition("Clauses:")
        ids = re.findall(r"\[([a-z0-9.\-]+)\]", head)
        findings = []
        for cid, text in re.findall(r'Clause (\d+): "(.*?)"(?=\n\nClause \d+:|\n\nReturn|$)', clause_part, re.S):
            bad = any(w in text.lower() for w in self.flag_words)
            findings.append({"clause_id": int(cid), "topic": "test", "label": "possibly_unlawful" if bad else "lawful",
                             "explanation": "x", "source_ids": (ids[:1] + ["made-up-id"]) if bad else [],
                             "citation": "cite" if bad else ""})
        return json.dumps({"findings": findings})

    def run_with_tools(self, system, prompt, declarations, functions, max_rounds=3):
        self.usage.calls += 2
        amounts = [float(a.replace(",", "")) for a in re.findall(r"\$([\d,]+)", prompt)]
        if not amounts:
            return ToolRunResult(text="NO_CHARGES_FOUND")
        args = {"monthly_rent": amounts[0], "first_month_rent": amounts[0], "security_deposit": max(amounts)}
        result = check_move_in_charges(**args)
        return ToolRunResult(text="Summary.", tool_calls=[ToolCall("check_move_in_charges", args, result)])

    def chat(self, system, history, message):
        self.usage.calls += 1
        return "answer"
