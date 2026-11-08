# --- Erdan: offline tests for the tuning harness ---
# AI-assisted: Claude Code, see AI_DISCLOSURE.md
import json

from eval import tune
from eval.run_v2 import OUT, main_summary
from leasecheck import prompts
from leasecheck.schemas import parse_batch


def test_every_variant_changes_one_setting_from_the_app():
    assert tune.VARIANTS["baseline"] == {}
    for name, settings in tune.VARIANTS.items():
        if name == "no_data":
            assert settings == {"prompt": "tune-no-data", "retrieval": False}
        elif name == "chain_of_thought":
            assert settings == {"prompt": "tune-cot", "schema": "cot"}
        elif name == "own_knowledge":  # passages swapped for the model's memory: the comparison's 'memory' version
            assert settings == {"prompt": "v2-memory", "retrieval": False}
            assert "v2-memory" in prompts.PROMPTS
        else:
            assert len(settings) <= 1, name


def test_removing_an_element_removes_only_its_words():
    v2 = prompts.PROMPTS["v2"]
    for element in tune.ELEMENTS:
        p = prompts.PROMPTS[f"tune-no-{element}"]
        assert "{clauses}" in p.task
        assert len(p.system) + len(p.task) < len(v2.system) + len(v2.task), element
    assert "You are a careful" not in prompts.PROMPTS["tune-no-persona"].system
    assert "graduate student" not in prompts.PROMPTS["tune-no-context"].system
    assert "EXAMPLES" not in prompts.PROMPTS["tune-no-exemplar"].task
    assert "{passages}" not in prompts.PROMPTS["tune-no-data"].task
    assert "decide ONE label" not in prompts.PROMPTS["tune-no-instruction"].system
    assert "jargon" not in prompts.PROMPTS["tune-no-tone"].system
    assert "never possibly_unlawful" not in prompts.PROMPTS["tune-no-constraints"].system
    assert "Return exactly one finding" not in prompts.PROMPTS["tune-no-format"].system


def test_chain_of_thought_answers_still_parse_for_the_app():
    raw = json.dumps({"findings": [{"clause_id": 1, "reasoning": "It sets a late fee after 5 days.",
                                    "topic": "late fee", "label": "possibly_unlawful", "explanation": "x",
                                    "source_ids": ["c186-15B-1c"], "citation": ""}]})
    assert parse_batch(raw).findings[0].label == "possibly_unlawful"
    assert list(tune.ClauseFindingCoT.model_fields)[:2] == ["clause_id", "reasoning"]


def test_main_summary_recomputes_the_saved_run():
    path = OUT / "main.json"
    if not path.exists():  # raw results are private and git-ignored
        return
    saved = json.loads(path.read_text())
    if any(r.get("added_later") for r in saved["inputs"]):
        return
    again = main_summary(saved["summary"]["model"], saved["inputs"], saved["chat"])
    assert again["real_leases"]["recall_possibly_unlawful"] == saved["summary"]["real_leases"]["recall_possibly_unlawful"]
    assert again["checks_passed"] == saved["summary"]["checks_passed"]
