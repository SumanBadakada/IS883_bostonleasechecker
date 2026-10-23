# --- Owner: (assign, see docs/TEAM_SPLIT.md) | tests for rate-limit, quota, overload and timeout handling ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
import httpx
import pytest
from google.genai import errors

from leasecheck import llm as llm_module
from leasecheck.llm import GeminiLLM, LLMError


def rate_limited(retry="37s", quota_id="GenerateRequestsPerMinutePerProjectPerModel-FreeTier"):
    return errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota_id}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry}]}})


def overloaded():
    return errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE",
                                              "message": "The model is overloaded. Please try again later."}})


def not_found():
    return errors.ClientError(404, {"error": {"code": 404, "status": "NOT_FOUND", "message": "model not found"}})


@pytest.fixture
def llm(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm_module.time, "sleep", sleeps.append)
    client = GeminiLLM("fake-key", model="main", fallback_models=("backup-1", "backup-2"))
    client.sleeps = sleeps
    client.messages = []
    client.on_wait = client.messages.append
    return client


def flaky(*failures, result="ok"):
    """fn(model) that raises the queued failures in order, then returns result; records the models tried."""
    queue = list(failures)

    def fn(model):
        fn.models.append(model)
        if queue:
            raise queue.pop(0)
        return result
    fn.models = []
    return fn


def test_waits_as_long_as_google_asks_then_succeeds(llm):
    assert llm._with_retries(flaky(rate_limited("37s"))) == "ok"
    assert llm.sleeps == [37.0]
    assert "waiting 37 seconds" in llm.messages[0]


def test_wait_is_capped(llm):
    llm._with_retries(flaky(rate_limited("300s")))
    assert llm.sleeps == [llm_module.MAX_WAIT_SECONDS]


def test_daily_quota_fails_fast(llm):
    with pytest.raises(LLMError, match="daily quota"):
        llm._with_retries(flaky(rate_limited(quota_id="GenerateRequestsPerDayPerProjectPerModel-FreeTier")))
    assert llm.sleeps == []


def test_gives_up_after_repeated_rate_limits(llm):
    with pytest.raises(LLMError, match="rate limit"):
        llm._with_retries(flaky(*[rate_limited("1s")] * 4))


def test_timeout_retried_once_then_reported(llm):
    assert llm._with_retries(flaky(httpx.ReadTimeout("slow"))) == "ok"
    with pytest.raises(LLMError, match="too long"):
        llm._with_retries(flaky(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow")))


def test_other_client_errors_are_not_retried(llm):
    bad_key = errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "API key not valid"}})
    with pytest.raises(LLMError, match="400"):
        llm._with_retries(flaky(bad_key))
    assert llm.sleeps == []


def test_overload_retries_then_recovers_on_main_model(llm):
    fn = flaky(overloaded())
    assert llm._with_retries(fn) == "ok"
    assert fn.models == ["main", "main"] and llm.models_used == {"main"}
    assert "overloaded" in llm.messages[0]


def test_persistent_overload_falls_back_to_next_model(llm):
    n = llm_module.OVERLOAD_TRIES_PER_MODEL
    fn = flaky(*[overloaded()] * n)
    assert llm._with_retries(fn) == "ok"
    assert fn.models == ["main"] * n + ["backup-1"]
    assert llm.models_used == {"backup-1"}
    assert any("switching to backup-1" in m for m in llm.messages)


def test_unavailable_fallback_is_skipped(llm):
    n = llm_module.OVERLOAD_TRIES_PER_MODEL
    fn = flaky(*[overloaded()] * n, not_found())
    assert llm._with_retries(fn) == "ok"
    assert fn.models[-2:] == ["backup-1", "backup-2"]


def test_all_models_overloaded_gives_a_clear_message(llm):
    n = llm_module.OVERLOAD_TRIES_PER_MODEL
    with pytest.raises(LLMError, match="overloaded right now"):
        llm._with_retries(flaky(*[overloaded()] * (3 * n)))


def test_embeddings_never_fall_back(llm):
    n = llm_module.OVERLOAD_TRIES_PER_MODEL
    fn = flaky(*[overloaded()] * n)
    with pytest.raises(LLMError):
        llm._with_retries(fn, models=("embed-model",))
    assert set(fn.models) == {"embed-model"}


def test_thinking_config_matches_model_family(llm):
    assert llm._config("gemini-2.5-flash-lite", "s").thinking_config.thinking_budget == 0
    assert llm._config("gemini-3.1-flash-lite", "s").thinking_config.thinking_level is not None
