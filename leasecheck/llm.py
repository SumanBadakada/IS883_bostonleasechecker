# --- Owner: (assign, see docs/TEAM_SPLIT.md) | Gemini client: retries, token counting, tool loop ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Every call to Gemini goes through this file.

Keeping it in one place means: (1) retries and error handling are written once, (2) token usage is
recorded for every call, which is the measured cost per interaction the financial model needs (§5.6),
and (3) tests can swap in a fake with the same four methods.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from . import config


class LLMError(Exception):
    """An API failure after retries. The message is safe to show to the user."""


REQUEST_TIMEOUT_MS = 90_000  # without a timeout a stuck request leaves the app waiting forever
MAX_WAIT_SECONDS = 60


def retry_delay_seconds(exc: Exception) -> float | None:
    """The wait Google asks for in a 429 response (RetryInfo retryDelay, e.g. "37s"), if any."""
    match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(getattr(exc, "details", "")))
    return float(match.group(1)) if match else None


def is_daily_quota(exc: Exception) -> bool:
    """A per-day quota will not reset in a minute, so retrying is pointless."""
    return "PerDay" in str(getattr(exc, "details", ""))


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, response: Any) -> None:
        self.calls += 1
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            self.input_tokens += getattr(meta, "prompt_token_count", 0) or 0
            # Thinking tokens are billed as output.
            self.output_tokens += (getattr(meta, "candidates_token_count", 0) or 0) + (
                getattr(meta, "thoughts_token_count", 0) or 0
            )

    def merge(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * config.PRICE_INPUT_PER_M + self.output_tokens * config.PRICE_OUTPUT_PER_M) / 1e6


@dataclass
class ToolCall:
    name: str
    args: dict
    result: dict


@dataclass
class ToolRunResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class GeminiLLM:
    def __init__(self, api_key: str, model: str = config.MODEL, embed_model: str = config.EMBED_MODEL):
        from google import genai
        from google.genai import types

        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
        self.model = model
        self.embed_model = embed_model
        self.usage = Usage()
        # Called with a message whenever we pause before a retry, so the UI can say why it is waiting.
        self.on_wait: Callable[[str], None] = lambda message: None

    # ---------- shared plumbing ----------

    def _config(self, system: str | None, **extra):
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=config.TEMPERATURE,
            seed=config.SEED,
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_level="MINIMAL", include_thoughts=False),
            **extra,
        )

    def _with_retries(self, fn: Callable[[], Any]) -> Any:
        """Retry rate limits, server errors and timeouts; turn anything else into LLMError."""
        import httpx
        from google.genai import errors

        delay = 5.0
        for attempt in range(4):
            last = attempt == 3
            try:
                return fn()
            except errors.ClientError as exc:
                if exc.code != 429:
                    raise LLMError(f"The model request was rejected ({exc.code} {exc.status}).") from exc
                if is_daily_quota(exc):
                    raise LLMError("This app has used its free daily quota. Please try again tomorrow.") from exc
                if last:
                    raise LLMError("The free-tier rate limit was reached. Please wait a minute and try again.") from exc
                wait = min(retry_delay_seconds(exc) or delay, MAX_WAIT_SECONDS)
                self.on_wait(f"Free-tier rate limit reached, waiting {wait:.0f} seconds before continuing...")
            except errors.ServerError as exc:
                if last:
                    raise LLMError("The model service is having problems right now. Please try again shortly.") from exc
                wait = delay
                self.on_wait(f"The model service is busy, retrying in {wait:.0f} seconds...")
            except httpx.TimeoutException as exc:
                if attempt >= 1:
                    raise LLMError("The model took too long to respond. Please try again.") from exc
                wait = 1.0
                self.on_wait("The model is slow to respond, retrying...")
            except Exception as exc:  # network failures and the like
                raise LLMError("Could not reach the model service. Please try again.") from exc
            time.sleep(wait)
            delay *= 2

    # ---------- the four operations the app uses ----------

    def generate_json(self, system: str, prompt: str, schema: Any) -> str:
        """Structured output: ask for JSON matching `schema`. Returns raw text; the caller parses it."""
        cfg = self._config(system, response_mime_type="application/json", response_schema=schema)
        response = self._with_retries(
            lambda: self.client.models.generate_content(model=self.model, contents=prompt, config=cfg)
        )
        self.usage.add(response)
        return response.text or ""

    def run_with_tools(self, system: str, prompt: str, declarations: list, functions: dict[str, Callable],
                       max_rounds: int = 3) -> ToolRunResult:
        """Tool calling with a manual loop, so we can record exactly which tool was called with what.

        The model decides whether to call a tool. If it does, we run our Python function and send the
        result back, and the model writes its answer using that result.
        """
        from google.genai import types

        cfg = self._config(
            system,
            tools=[types.Tool(function_declarations=declarations)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents: list = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        calls: list[ToolCall] = []
        for _ in range(max_rounds):
            response = self._with_retries(
                lambda: self.client.models.generate_content(model=self.model, contents=contents, config=cfg)
            )
            self.usage.add(response)
            function_calls = response.function_calls or []
            if not function_calls:
                return ToolRunResult(text=response.text or "", tool_calls=calls)
            # Keep the model's turn as-is (it carries thought signatures Gemini 3 needs back).
            contents.append(response.candidates[0].content)
            parts = []
            for fc in function_calls:
                args = dict(fc.args or {})
                fn = functions.get(fc.name)
                try:
                    result = fn(**args) if fn else {"error": f"Unknown tool {fc.name}"}
                except (TypeError, ValueError) as exc:
                    result = {"error": f"Bad arguments: {exc}"}
                calls.append(ToolCall(name=fc.name, args=args, result=result))
                parts.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
            contents.append(types.Content(role="user", parts=parts))
        return ToolRunResult(text="", tool_calls=calls)

    def chat(self, system: str, history: list[dict], message: str) -> str:
        """One conversational turn. `history` is [{"role": "user"|"assistant", "content": str}, ...]."""
        from google.genai import types

        contents = [
            types.Content(role="model" if h["role"] == "assistant" else "user",
                          parts=[types.Part.from_text(text=h["content"])])
            for h in history
        ]
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
        cfg = self._config(system)
        response = self._with_retries(
            lambda: self.client.models.generate_content(model=self.model, contents=contents, config=cfg)
        )
        self.usage.add(response)
        return response.text or ""

    def embed(self, texts: list[str], task_type: str) -> np.ndarray:
        """Embeddings, L2-normalised so a dot product is cosine similarity."""
        from google.genai import types

        vectors = []
        for start in range(0, len(texts), 100):  # API batch limit
            batch = texts[start:start + 100]
            response = self._with_retries(
                lambda: self.client.models.embed_content(
                    model=self.embed_model, contents=batch,
                    config=types.EmbedContentConfig(task_type=task_type),
                )
            )
            self.usage.calls += 1
            vectors.extend(e.values for e in response.embeddings)
        matrix = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.where(norms == 0, 1, norms)
