import json
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

import src.cli as cli
from src.config import load_config, PROJECT_ROOT
from src.llm import LLMError
from src.retrieve import RetrievalError

ENV = {"GROQ_API_KEY": "gsk-test-key-1234", "LLM_MODEL": "qwen/qwen3.8-27b"}


def test_all_runs_stages_in_order_and_stops_on_first_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "scrape_command", lambda: calls.append(("scrape", 0)) or 0)
    monkeypatch.setattr(cli, "load_command", lambda: calls.append(("load", 0)) or 0)
    monkeypatch.setattr(cli, "chunk_command", lambda: calls.append(("chunk", 0)) or 0)

    def embed():
        calls.append(("embed", 1))
        return 1

    monkeypatch.setattr(cli, "embed_command", embed)
    assert cli.all_command() == 1
    assert [name for name, _code in calls] == ["scrape", "load", "chunk", "embed"]


def test_all_with_keep_going_finishes_the_later_stages(monkeypatch):
    calls = []
    indexes = []

    def embed():
        calls.append("embed")
        return 1

    def index():
        indexes.append("index")
        return 0

    monkeypatch.setattr(cli, "scrape_command", lambda: calls.append("scrape") or 0)
    monkeypatch.setattr(cli, "load_command", lambda: calls.append("load") or 0)
    monkeypatch.setattr(cli, "chunk_command", lambda: calls.append("chunk") or 0)
    monkeypatch.setattr(cli, "embed_command", embed)
    monkeypatch.setattr(cli, "index_command", index)
    assert cli.all_command(keep_going=True) == 1
    assert calls == ["scrape", "load", "chunk", "embed"] and indexes == ["index"]


def test_ask_command_reports_missing_prerequisite(tmp_path: Path, monkeypatch, capsys):
    loaded = load_config(PROJECT_ROOT / "config.yaml", ENV)
    config = replace(loaded, vector_path=tmp_path / "chroma", trace_dir=tmp_path / "traces")

    monkeypatch.setattr(cli, "load_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(cli, "ensure_artifact_dirs", lambda _c: None)

    def raise_missing(*args, **kwargs):
        raise RetrievalError("vectorstore", "run index first")

    monkeypatch.setattr(cli, "answer_question", raise_missing)
    assert cli.ask_command("What is the exit load?") == 1
    assert "run index first" in capsys.readouterr().err


def test_llm_error_is_normalized_not_raised_raw(tmp_path: Path):
    def post(url, headers, body):
        return 429, "rate limited"

    from src.llm import build_client

    config = load_config(PROJECT_ROOT / "config.yaml", ENV)
    client = build_client(config, post=post)
    try:
        client.complete("s", "u")
        raised = False
    except LLMError as exc:
        raised = True
        assert exc.field == "llm" and "HTTP 429" in str(exc)
    assert raised


def test_config_summary_masks_secrets():
    from src.config import mask_secret

    assert mask_secret("verylongsecretkey123") == "very…23"
    assert mask_secret("short") == "****"


def test_trace_payload_has_no_pii(tmp_path: Path):
    from src.answer import ask

    loaded = load_config(PROJECT_ROOT / "config.yaml", ENV)
    config = replace(loaded, trace_dir=tmp_path / "traces", raw_dir=tmp_path / "raw", document_dir=tmp_path / "documents")

    class StubClient:
        def complete(self, system, user):  # pragma: no cover - never called
            raise AssertionError("LLM must not be called for a PII question")

    result = ask("PAN card ABCDE1234F expense ratio?", config=config, client=StubClient(), query_id="p1")
    trace_path = config.trace_dir / "p1.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert "ABCDE1234F" not in json.dumps(payload)
    assert result.mode == "pii"
