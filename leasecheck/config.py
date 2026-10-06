# --- Owner: (assign, see docs/TEAM_SPLIT.md) | settings shared by the app and the eval ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).

# Model choices. Flash-lite is the model the course uses on the free tier.
MODEL = "gemini-3.1-flash-lite"
EMBED_MODEL = "gemini-embedding-001"

# Generation parameters. Low temperature because we want the same clause to get the same label
# every time; a fixed seed makes eval runs repeatable.
TEMPERATURE = 0.1
SEED = 883
MAX_OUTPUT_TOKENS = 8192

# How many clauses go into one classification request. Bigger batches use fewer free-tier
# requests (a typical lease is then one request); smaller batches give the model less to keep track of.
CLAUSES_PER_BATCH = 20

# Retrieval: how many source chunks to fetch per clause, and the cap per batch prompt.
TOP_K_PER_CLAUSE = 3
MAX_CHUNKS_PER_BATCH = 16

# Input limits (public app, free tier).
MAX_FILE_MB = 5
MAX_CLAUSES = 80

# Per-session usage cap (IS883 §3.2), held in st.session_state by app.py.
MAX_ANALYSES_PER_SESSION = 3
MAX_CHAT_MESSAGES_PER_SESSION = 15

# Published per-token prices (USD per 1M tokens) used for the cost model (§5.6).
# Check these against Google's current price list before you report them.
PRICE_INPUT_PER_M = 0.10
PRICE_OUTPUT_PER_M = 0.40
