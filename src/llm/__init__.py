"""LLM provider adapters behind one interface.

The provider comes from config.yaml; the model id and the key come from the
environment. Nothing here hardcodes a model id.
"""

from __future__ import annotations

import json
import re

from src.config import AppConfig

TIMEOUT = 30.0
MAX_TOKENS = 300

ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
}

_URL_IN_TEXT = re.compile(r"https?://\S+")
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}


class LLMError(Exception):
    """The provider call failed. The message never contains the key."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")


def build_client(config: AppConfig, post=None):
    """Map provider → adapter. Raises LLMError for a provider without an adapter."""
    if post is None:
        post = _post
    if config.provider in OPENAI_COMPATIBLE:
        return OpenAICompatibleClient(
            provider=config.provider,
            endpoint=ENDPOINTS[config.provider],
            api_key=config.api_key,
            model=config.llm_model,
            post=post,
        )
    if config.provider == "gemini":
        return GeminiClient(api_key=config.api_key, model=config.llm_model, post=post)
    raise LLMError("llm.provider", f"no adapter wired for provider {config.provider!r}")


OPENAI_COMPATIBLE = frozenset({"groq", "openai", "mistral"})


class OpenAICompatibleClient:
    """Groq, OpenAI, and Mistral reuse the chat-completions shape."""

    def __init__(self, provider: str, endpoint: str, api_key: str, model: str, post) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self._post = post

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
        }
        response = _call(
            self._post,
            self.endpoint,
            {"Authorization": f"Bearer {self.api_key}"},
            json.dumps(payload),
            attempts=2,
        )
        try:
            choices = response["choices"]
            text = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("llm", f"{self.provider} returned an unexpected body") from exc
        if not isinstance(text, str):
            raise LLMError("llm", f"{self.provider} returned no text")
        return text


class GeminiClient:
    def __init__(self, api_key: str, model: str, post) -> None:
        self.provider = "gemini"
        self.api_key = api_key
        self.model = model
        self._post = post

    def complete(self, system: str, user: str) -> str:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generation_config": {"temperature": 0, "max_output_tokens": MAX_TOKENS},
        }
        response = _call(
            self._post,
            f"{endpoint}?key={self.api_key}",
            {},
            json.dumps(payload),
            attempts=2,
        )
        try:
            parts = response["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("llm", "gemini returned an unexpected body") from exc
        if not text:
            raise LLMError("llm", "gemini returned no text")
        return text


def _call(post, url: str, headers: dict, body: str, attempts: int) -> dict:
    status, text = 0, ""
    for attempt in range(attempts):
        try:
            status, text = post(url, headers, body)
        except Exception as exc:
            raise LLMError("llm", f"provider request failed: {exc}") from exc
        if int(status) < 400:
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise LLMError("llm", "provider returned a non-JSON body") from exc
        if int(status) in _RETRY_STATUS and attempt + 1 < attempts:
            continue
        raise LLMError("llm", f"provider returned HTTP {int(status)}")
    raise LLMError("llm", f"provider returned HTTP {status}")


def _post(url: str, headers: dict, body: str) -> tuple[int, str]:
    """POST with the stdlib instead of httpx.

    httpx ConnectError errno 16 (EBUSY) on some serverless sandboxes; urllib
    connects fine there, and locally both behave the same.
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "rag-bot/1.0", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as error:
        raise RuntimeError(f"provider request failed: {error.reason}") from error
