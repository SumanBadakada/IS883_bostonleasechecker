# Architecture (§5.2)

How information moves through the app, from what the user uploads to what they see. It is drawn from the
code on `main`; if you change the code, update this file. Every Gemini call is labelled with the prompt it
sends (the full text of every prompt is in `leasecheck/prompts.py`, and goes in the report's appendix).
Amber boxes call Gemini; blue boxes are plain Python; dashed red arrows are failure paths.

```mermaid
flowchart TD
    U["User uploads a PDF or Word lease (max 5 MB)<br/>or picks one of 5 fictional samples"] --> CAP{"Lease checks left this session?<br/>3 per session, st.session_state"}
    CAP -- no --> CAPMSG["Message: no checks left"]
    CAP -- yes --> X

    subgraph PARSE ["Plain code, no AI: leasecheck/parsing.py + checkboxes.py"]
      X["Extract text<br/>PyMuPDF / python-docx, tick boxes put back"] --> CLEAN["Clean: tick boxes to [ticked] markers,<br/>page headers and footers removed"]
      CLEAN --> REJ{"Empty, unsupported, damaged, scanned,<br/>spaces lost, not a lease, over 500 clauses?"}
      REJ -- no --> SPLIT["Split into clauses<br/>numbers and ALL-CAPS headings"]
      SPLIT --> WARN["Warnings, analysis continues:<br/>other state, not residential,<br/>term over 5 years, end before start, unticked boxes"]
    end
    REJ -- yes --> REJMSG["Rejection message, check refunded,<br/>no Gemini call made"]

    WARN --> EMB
    subgraph RAG ["Capability 3, retrieval: leasecheck/retrieval.py"]
      LIB[("sources/*.md: 33 law passages<br/>c.186 §15B, 940 CMR 3.17, AG guide")] --> IDXB["CALL A: embed the library<br/>gemini-embedding-001, RETRIEVAL_DOCUMENT<br/>once per server; skipped if index.npz fingerprint matches"]
      EMB["CALL B: embed every clause, requests of up to 100 clauses / 40,000 characters<br/>gemini-embedding-001, RETRIEVAL_QUERY"] --> SIM["Cosine similarity = dot product of normalised vectors<br/>top 3 passages per clause"]
      IDXB --> SIM
    end

    SIM --> BATCH
    subgraph CLASSIFY ["Capabilities 1 + 4: analyzer.py, prompts.py, schemas.py"]
      BATCH["Batches of 20 clauses; their passages merged,<br/>best first, max 16"] --> GEN["CALL C: gemini-3.5-flash-lite<br/>prompt PROMPTS v2: system + task with 3 examples<br/>JSON mode, schema BatchFindings, temperature 0.1, seed 883"]
      GEN --> PARSEQ{"JSON valid for the schema?"}
      PARSEQ -- no --> RETRY["CALL C again, task + 'return only the JSON object'"] --> PARSE2{"Valid?"}
      PARSEQ -- yes --> GUARD["Delete passage IDs not sent;<br/>citation copied from the real passage"]
      PARSE2 -- yes --> GUARD
    end
    PARSE2 -- no --> NC["Those clauses: 'Could not be checked'"]

    SPLIT --> MONEY
    subgraph TOOL ["Capability 2, tool calling: analyzer.check_charges, llm.run_with_tools, charges.py"]
      MONEY["Clauses with $, deposit, fee,<br/>first or last month, lock"] --> TCALL["CALL D: gemini-3.5-flash-lite<br/>prompt CHARGES_SYSTEM + CHARGES_TASK<br/>tool declaration check_move_in_charges, up to 3 rounds"]
      TCALL -- "asks to call the tool" --> CALC["Python: check_move_in_charges<br/>c.186 §15B(1)(b) limits, broker and utility rules"]
      CALC -- "result sent back" --> TCALL
      TCALL -- "summary" --> CHG["Move-in verdicts + summary"]
    end
    MONEY -- "no money clauses" --> NOCHG["No move-in charges found, no call"]

    GUARD --> RESULT
    NC --> RESULT
    CHG --> RESULT
    NOCHG --> RESULT
    RESULT["AnalysisResult"] --> REPORT["report.py, templates, no AI:<br/>verdict, landlord questions, downloadable HTML report"]
    REPORT --> UI["Streamlit tabs: Overview, Clause review, Full lease,<br/>Move-in costs, Ask a question; disclaimer on every screen"]

    UI --> Q["Chat question: 15 per session, max 2,000 characters"]
    Q --> CHATE["CALL E: embed the question, RETRIEVAL_QUERY, top 4 passages"]
    CHATE --> CHAT["CALL F: gemini-3.5-flash-lite<br/>prompt CHAT_SYSTEM with findings digest + passages<br/>+ last 10 messages"]
    CHAT --> UI

    RETRIES[["Every call A-F goes through llm._with_retries:<br/>429: wait 15, 30, 60, 60, 60 s (longer if Google asks) · daily quota: stop<br/>503: 3 tries, then 3.1-flash-lite, 2.5-flash-lite, 2.5-flash<br/>timeout 90 s: 1 retry · other errors: stop"]]
    RETRIES -. "fails on the first batch" .-> ERR["Error message: check could not finish"]
    RETRIES -. "fails on a later batch" .-> PARTIAL["Keep checked clauses, show which were missed"]
    RETRIES -. "fails on the money step" .-> CHGERR["Clause review shown; money not checked"]
    RETRIES -. "fails in chat" .-> CHATERR["Apology in the chat"]

    classDef ai fill:#FEF3E2,stroke:#B45309,color:#16212E
    classDef code fill:#EAF1F8,stroke:#1F4E79,color:#16212E
    classDef fail fill:#FEF3F2,stroke:#B42318,color:#16212E
    class IDXB,EMB,GEN,RETRY,TCALL,CHATE,CHAT ai
    class X,CLEAN,SPLIT,WARN,SIM,BATCH,GUARD,MONEY,CALC,CHG,RESULT,REPORT,UI,Q,CAP,REJ,PARSEQ,PARSE2 code
    class CAPMSG,REJMSG,NC,ERR,PARTIAL,CHGERR,CHATERR,NOCHG,RETRIES fail
```

The clause review (call C) and the move-in check (call D) are drawn as two branches because both start from
the same list of clauses; in the code they run one after the other in `analyzer.analyze`, clause review first.

## Every model call and the prompt it sends

| Call | Model | Prompt (in `leasecheck/prompts.py`) | Code | Capability |
| --- | --- | --- | --- | --- |
| A. Embed the law library | `gemini-embedding-001`, task `RETRIEVAL_DOCUMENT` | none: each passage's citation + text | `retrieval.SourceIndex.build` → `llm.embed` | 3 |
| B. Embed the lease's clauses | `gemini-embedding-001`, task `RETRIEVAL_QUERY` | none: each clause's text | `retrieval.SourceIndex.search_many` (from `analyzer.analyze`) | 3 |
| C. Label each batch of clauses | `gemini-3.5-flash-lite` | `PROMPTS["v2"].system` + `PROMPTS["v2"].task` (passages, 3 examples, clauses); retry appends "Your previous answer was not valid JSON…" | `analyzer._classify_with_retry` → `llm.generate_json`, schema `schemas.BatchFindings` | 1, 3, 4 |
| D. Move-in charges | `gemini-3.5-flash-lite` | `CHARGES_SYSTEM` + `CHARGES_TASK`, with the tool declaration `charges.CHECK_MOVE_IN_CHARGES_DECLARATION` | `analyzer.check_charges` → `llm.run_with_tools` → `charges.check_move_in_charges` | 2 |
| E. Embed a chat question | `gemini-embedding-001`, task `RETRIEVAL_QUERY` | none: the question | `app.answer_question` → `search_many` (k = `config.CHAT_TOP_K`) | 3 |
| F. Chat answer | `gemini-3.5-flash-lite` | `CHAT_SYSTEM`, filled with `analyzer.findings_digest` and the retrieved passages; history = last 10 messages | `app.answer_question` → `llm.chat` | 3 |

All chat-model calls use `config.TEMPERATURE` (0.1), `config.SEED` (883), `config.MAX_OUTPUT_TOKENS` (8,192)
and minimal thinking (`llm.GeminiLLM._config`). Backup models apply to calls C, D and F only; embeddings
never switch models, because vectors from different models cannot be compared.

## Failure paths

| What goes wrong | Where it is handled | What the user sees |
| --- | --- | --- |
| No checks left this session | `app.run_check` | "You have used all the lease checks for this session" |
| Empty, unsupported, over 5 MB, damaged or password-protected, scanned, spaces lost, not a lease, over 500 clauses | `parsing.InputRejected`, caught in `app.run_check` | A message saying why; the check is refunded; no Gemini call |
| Another state, commercial or parking lease, term over 5 years, end before start, unticked "check one" boxes | `parsing.load_document` warnings | A warning above the results; the analysis still runs |
| Gemini's answer is not valid JSON | `analyzer._classify_with_retry` | One retry; then those clauses show "Could not be checked" |
| Rate limit, overload, timeout, daily quota, bad key | `llm.GeminiLLM._with_retries` | "Waiting…" / "switching to…" notices; then an error if it still fails |
| Gemini fails after some clauses were checked | `analyzer.analyze` | The checked clauses, plus which ones were missed |
| The money step fails | `analyzer.analyze` | The clause review, with a note that money could not be checked |
| The chat fails | `app.answer_question` | "Sorry, I could not answer that…" in the chat |
