# --- Owner: Erdan | settings shared by the app and the eval ---
# AI-assisted: Claude Code, see AI_DISCLOSURE.md

# --- Model choices and backup models ---
# Model choices. Flash-lite is the model the course uses on the free tier (the course notebook moved its
# default from 3.1 to 3.5 Flash-Lite on Nov 2, 2026; 3.1 stays first in line as a fallback).
MODEL = "gemini-3.5-flash-lite"
EMBED_MODEL = "gemini-embedding-001"

# Used only when Google reports MODEL overloaded (HTTP 503), in this order. Each must be available on your
# key's free tier (check AI Studio); one that is not is skipped automatically.
FALLBACK_MODELS = ("gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash")

# --- Erdan: generation parameters and why the temperature is 0.1 ---
# Generation parameters. Low temperature because we want the same clause to get the same label
# every time; a fixed seed makes eval runs repeatable.
# Tested in eval/tune.py (docs/evaluation.md §5): on gemini-3.5-flash-lite, temperatures 0.0, 0.1 and 0.3
# gave word-for-word identical answers at the same seed (a probe at 1.0 and 2.0 did too); only the seed
# changed the output. So 0.1 is kept: it costs nothing and states the intent if the model is ever changed.
TEMPERATURE = 0.1
SEED = 883
MAX_OUTPUT_TOKENS = 8192

# --- Erdan: batch size and retrieval top-k ---
# How many clauses go into one classification request. Bigger batches use fewer free-tier
# requests (a typical lease is then one request); smaller batches give the model less to keep track of.
CLAUSES_PER_BATCH = 20

# Retrieval: how many source chunks to fetch per clause, and the cap per batch prompt.
TOP_K_PER_CLAUSE = 3
MAX_CHUNKS_PER_BATCH = 16
# Passages retrieved for each follow-up chat question (one more than per clause: a question can span rules).
CHAT_TOP_K = 4

# --- Input limits, usage caps and prices ---
# Input limits (public app, free tier).
MAX_FILE_MB = 5
# Real leases with riders and addenda run long (one reached 86 clauses), so 80 rejected real uploads.
# 150 clauses = 8 review requests; the per-session cap below still bounds the total cost.
MAX_CLAUSES = 150

# Per-session usage cap (IS883 §3.2), held in st.session_state by app.py.
MAX_ANALYSES_PER_SESSION = 3
MAX_CHAT_MESSAGES_PER_SESSION = 15

# Published per-token prices (USD per 1M tokens) used for the cost model (§5.6).
# Check these against Google's current price list before you report them.
PRICE_INPUT_PER_M = 0.10
PRICE_OUTPUT_PER_M = 0.40
