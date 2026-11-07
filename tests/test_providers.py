import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.config import PROJECT_ROOT, load_config
from src.llm import LLMError, build_client
from src.retrieve import RetrievalError, retrieve

ENV = {"GROQ_API_KEY": "gsk-test-key-1234", "LLM_MODEL": "qwen/qwen3.8-27b"}


def _config(tmp_path: Path, **overrides):
    loaded = load_config(PROJECT_ROOT / "config.yaml", ENV)
    return replace(loaded, vector_path=tmp_path / "chroma", **overrides)


def test_groq_adapter_completes_chat_completions(tmp_path: Path):
    payloads = []

    def post(url, headers, body):
        payloads.append((url, json.loads(body)))
        return 200, json.dumps({"choices": [{"message": {"content": "The load is 1%."}}]})

    client = build_client(_config(tmp_path), post=post)
    result = client.complete("be factual", "What is the exit load?")
    assert result == "The load is 1%."
    url, payload = payloads[0]
    assert "groq" in url
    assert payload["model"] == "qwen/qwen3.8-27b"
    assert payload["messages"][0]["role"] == "system"


def test_gemini_adapter_completes_generate_content(tmp_path: Path):
    def post(url, headers, body):
        body = json.loads(body)
        assert "system_instruction" in body
        return 200, json.dumps(
            {"candidates": [{"content": {"parts": [{"text": "1% ", }, {"text": "one year"}]}}]}
        )

    config = _config(tmp_path, provider="gemini", api_key="gem-key", api_key_name="GEMINI_API_KEY")
    client = build_client(config, post=post)
    assert client.complete("sys", "user") == "1% one year"


def test_openai_and_mistral_pick_their_own_endpoints(tmp_path: Path):
    seen = []

    def post(url, headers, body):
        seen.append(url)
        return 200, json.dumps({"choices": [{"message": {"content": "ok"}}]})

    for provider, token_name in (("openai", "OPENAI_API_KEY"), ("mistral", "MISTRAL_API_KEY")):
        config = _config(tmp_path, provider=provider, api_key="k", api_key_name=token_name)
        client = build_client(config, post=post)
        client.complete("s", "u")
    assert any("openai" in url for url in seen) and any("mistral" in url for url in seen)


def test_retries_once_on_500_then_succeeds(tmp_path: Path):
    calls = []

    def post(url, headers, body):
        calls.append(1)
        if len(calls) == 1:
            return 500, "boom"
        return 200, json.dumps({"choices": [{"message": {"content": "fine"}}]})

    client = build_client(_config(tmp_path), post=post)
    assert client.complete("s", "u") == "fine"
    assert len(calls) == 2


def test_persistent_5xx_names_the_status_without_the_key(tmp_path: Path):
    def post(url, headers, body):
        headers = dict(headers)
        return 503, f"down (attempts to look like {headers.get('Authorization', '')})"

    client = build_client(_config(tmp_path), post=post)
    with pytest.raises(LLMError) as exc:
        client.complete("s", "u")
    assert exc.value.field == "llm"
    assert "HTTP 503" in str(exc.value)
    assert "gsk-test-key-1234" not in str(exc.value)


def test_anthropic_is_documented_but_not_wired(tmp_path: Path):
    config = _config(tmp_path, provider="anthropic", api_key="k", api_key_name="ANTHROPIC_API_KEY")
    with pytest.raises(LLMError) as exc:
        build_client(config, post=lambda *a: (200, "{}"))
    assert "anthropic" in str(exc.value)


class FakeCollection:
    def __init__(self, metadata: dict, rows: dict | None = None):
        self.metadata = metadata
        self._rows = rows
        self.last_where = "unused"

    def query(self, query_embeddings, n_results, include, where=None):
        self.last_where = where
        assert n_results == 5
        return self._rows or {
            "ids": [["slug::0::abc"]],
            "documents": [["Benchmark: Nifty 500 TRI. The fund tracks the index."]],
            "metadatas": [[{
                "section": "Benchmark",
                "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
                "scheme_name": "HDFC Large Cap Fund Direct Growth",
                "slug": "hdfc-large-cap-fund-direct-growth",
                "amc": None,
            }]],
            "distances": [[0.2]],
        }


def test_retrieve_maps_rows_and_converts_distances():
    config = _config(Path("."))
    chunks = retrieve(
        config,
        "What is the benchmark?",
        embed=lambda texts: [[1.0, 0.0] for _text in texts],
        collection=FakeCollection({"embedding_model": config.embedding_model}),
    )
    assert len(chunks) == 1
    row = chunks[0]
    assert row.section == "Benchmark"
    assert row.score == pytest.approx(0.8)
    assert row.scheme_name.startswith("HDFC")
    assert row.source_url.endswith("hdfc-large-cap-fund-direct-growth")


def test_retrieve_blocks_a_collection_from_a_different_model():
    config = _config(Path("."))
    with pytest.raises(RetrievalError) as exc:
        retrieve(
            config,
            "Any question?",
            embed=lambda texts: [[1.0]],
            collection=FakeCollection({"embedding_model": "other-model"}),
        )
    assert exc.value.field == "vectorstore.embedding_model"


def test_retrieve_forwards_the_section_filter():
    config = _config(Path("."))
    fake = FakeCollection({"embedding_model": config.embedding_model})
    where = {"section": {"$in": ["Expense ratio"]}}
    retrieve(config, "What is the expense ratio?", embed=lambda texts: [[1.0]], collection=fake, where=where)
    assert fake.last_where == where


def test_retrieve_without_a_filter_passes_none():
    config = _config(Path("."))
    fake = FakeCollection({"embedding_model": config.embedding_model})
    retrieve(config, "Any question?", embed=lambda texts: [[1.0]], collection=fake)
    assert fake.last_where is None
