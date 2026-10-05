# --- Owner: (assign, see docs/TEAM_SPLIT.md) | structured output schemas (capability 4) ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
from __future__ import annotations

import json
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

Label = Literal["lawful", "unusual", "possibly_unlawful"]
LABELS = ("lawful", "unusual", "possibly_unlawful")


class ClauseFinding(BaseModel):
    """What the model returns for one clause. Every field is read downstream."""

    clause_id: int = Field(description="The clause number exactly as given in the prompt.")
    topic: str = Field(description="Short topic, e.g. 'security deposit', 'late fee', 'repairs'.")
    label: Label
    explanation: str = Field(description="One or two plain-English sentences for a tenant.")
    source_ids: list[str] = Field(
        default_factory=list,
        description="IDs of the provided source passages that support the label. Empty if none apply.",
    )
    citation: str = Field(
        default="",
        description="Human-readable legal citation, e.g. 'M.G.L. c. 186 §15B(1)(c)'. Empty for lawful clauses with no source.",
    )


class BatchFindings(BaseModel):
    findings: list[ClauseFinding]


def parse_batch(raw: Optional[str]) -> Optional[BatchFindings]:
    """Parse the model's JSON. Returns None instead of raising, so the caller can take the failure path."""
    if not raw:
        return None
    text = raw.strip()
    # Tolerate a fenced code block, which models sometimes add despite JSON mode.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return BatchFindings.model_validate_json(text)
    except ValidationError:
        pass
    # Some responses are a bare list of findings.
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return BatchFindings(findings=data)
    except (json.JSONDecodeError, ValidationError):
        pass
    return None
