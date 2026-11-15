# --- Shared test setup ---
# AI-assisted: Claude Code, see AI_DISCLOSURE.md
import pytest

from leasecheck import config, llm


@pytest.fixture(autouse=True)
def no_embedding_pacing(monkeypatch):
    """The free-tier pacing really sleeps, so it is off in tests; the tests of the pacing switch it back on."""
    monkeypatch.setattr(config, "EMBED_TEXTS_PER_MINUTE", 0)
    llm._EMBED_SENT.clear()
