# --- Owner: (assign, see docs/TEAM_SPLIT.md) | tests for rate-limit, quota and timeout handling ---
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


@pytest.fixture
def llm(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm_module.time, "sleep", sleeps.append)
    client = GeminiLLM("fake-key")
    client.sleeps = sleeps
    client.messages = []
    client.on_wait = client.messages.append
    return client


def flaky(*failures, result="ok"):
    queue = list(failures)

    def fn():
        if queue:
            raise queue.pop(0)
        return result
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
