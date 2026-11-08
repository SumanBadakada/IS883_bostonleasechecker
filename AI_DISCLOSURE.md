# Generative AI disclosure (IS883 §9)

This is the one place the repository describes its use of generative AI. Every code file points here
instead of repeating it.

## Tool

- **Claude Code** (Anthropic), used through claude.ai cloud sessions and connected to this repository.
- Some teammate sections were drafted with **Claude** (the chat assistant) on Oct 15, 2026, and then
  committed by the teammate.

## How it was used

- **Code:** most of `app.py`, `leasecheck/`, `scripts/`, `tests/` and the first evaluation harness
  (`eval/run_eval.py`, `metrics.py`, `build_test_set.py`, `clause_bank.py`, `format_robustness.py`) was
  written with Claude Code, then run, tested and changed by the team. Commits made from Claude Code
  sessions show the author "Claude".
- **Debugging and explanation:** finding and fixing failures (for example the google-genai 3.0
  dependency crash), and explaining the code and course concepts to the team.
- **Not used for:** the report or the slides. Under §9 every word of those is written by the team.

## How to read the tags in the code

| Tag | Where | Meaning |
| --- | --- | --- |
| `# AI-assisted: Claude Code, see AI_DISCLOSURE.md` | line 2 of a file | The file was written with Claude Code (see above). |
| `# [AI] ...` | above a block | That block was written with Claude or Claude Code; the rest of the line explains why the block exists. |
| `# --- Name: what the code does ---` | above a section | That teammate wrote this section themselves (it may also carry an AI tag if they used Claude for it). |

Each person's own use of these tools, with links or screenshots of the exchanges, is listed in the
report's Generative AI appendix.
