# Suggested ownership split

The first version of this code was drafted with Claude Code. Under the course rules (§6.4, §8.2 item 8,
§9) each part needs a named owner who **reviews it, improves it, commits that work from their own
GitHub account, and can explain every line in Q&A**. Replace each file's
`# --- Owner: (assign, see docs/TEAM_SPLIT.md)` header with your name once you own it. Keep the
`# AI-assisted` line, and list the Claude Code use in the report's Generative AI appendix.

This is a starting suggestion; agree on it as a team and mirror it on the project board.

| Area | Files | Capability | Suggested owner | Work still to do |
| --- | --- | --- | --- | --- |
| App, deployment, usage cap, secrets, UI | `app.py`, `.streamlit/`, `requirements.txt`, `leasecheck/report.py`, `samples/` | baseline | Suman | Deploy to Streamlit Cloud with the key in Secrets; cold-start test in a private window; UI polish |
| Upload and clause splitting | `leasecheck/parsing.py` | (code, not LLM) | Suman | Test on real lease formats (landlord templates, Greater Boston REALTORS form); tune the splitter |
| Legal sources and retrieval | `sources/`, `leasecheck/retrieval.py`, `scripts/fetch_sources.py` | 3 | Erdan | **Replace the paraphrased notes with verified official text**; test chunk sizes; commit `sources/index.npz` |
| Prompts and structured output | `leasecheck/prompts.py`, `leasecheck/schemas.py`, `leasecheck/analyzer.py` | 1, 4 | Janice | Iterate prompt versions against the eval; batch size; label calibration |
| Move-in charge tool | `leasecheck/charges.py`, `leasecheck/llm.py` | 2 | Munkhzaya | Verify the rules (broker-fee law citation); add edge cases (prorated first month, utilities at signing) |
| Evaluation | `eval/`, `tests/` | §5.5 | Munkhzaya + Janice | Double-label the clause bank; collect consented leases; run v1 vs v2; find the failure the metric misses |
| Cost model | (report) | §5.6 | Erdan | Use `avg_*_tokens_per_lease` from `eval/results/` and current Gemini prices |
