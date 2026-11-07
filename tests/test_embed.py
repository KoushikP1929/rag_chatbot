import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.config import PROJECT_ROOT, load_config
from src.embed import EmbedError, embed_documents
from src.paths import page_file, safe_write

ENV = {"GROQ_API_KEY": "gsk-test-key-1234", "LLM_MODEL": "qwen/qwen3.8-27b"}


def _config(tmp_path: Path):
    loaded = load_config(PROJECT_ROOT / "config.yaml", ENV)
    return replace(loaded, chunk_dir=tmp_path / "chunks", embedding_dir=tmp_path / "embeddings")


def _write_chunks(config, slug: str) -> None:
    payload = {
        "slug": slug,
        "chunks": [
            {
                "chunk_id": f"{slug}::0::abc",
                "text": "Expense ratio: 1.01",
                "source_url": "https://groww.in/example",
                "page_title": "Example",
                "section": "Expense ratio",
                "chunk_index": 0,
                "fetched_at": "2026-11-06T00:00:00Z",
                "fallback": False,
                "scheme_name": "Example Scheme",
            },
            {
                "chunk_id": f"{slug}::1::def",
                "text": "Lock-in: 3 years",
                "source_url": "https://groww.in/example",
                "page_title": "Example",
                "section": "Lock-in",
                "chunk_index": 1,
                "fetched_at": "2026-11-06T00:00:00Z",
                "fallback": False,
                "scheme_name": "Example Scheme",
            },
        ],
    }
    safe_write(page_file(config.chunk_dir, slug), json.dumps(payload))


def _encode(texts: list[str]) -> list[list[float]]:
    return [[3.0, 4.0] for _text in texts]


def test_vectors_match_chunks_and_are_normalized(tmp_path: Path):
    config = _config(tmp_path)
    slug = config.corpus[1].slug
    _write_chunks(config, slug)
    summary = embed_documents(config, encode=_encode)
    saved = json.loads(page_file(config.embedding_dir, slug).read_text(encoding="utf-8"))
    assert summary["dimension"] == 2
    assert saved["model"] == config.embedding_model
    assert len(saved["chunks"]) == 2
    assert saved["chunks"][0]["chunk_id"].endswith("::0::abc")
    assert saved["chunks"][0]["metadata"]["section"] == "Expense ratio"
    assert saved["chunks"][0]["vector"] == pytest.approx([0.6, 0.8])


def test_different_model_is_refused_without_force(tmp_path: Path):
    config = _config(tmp_path)
    slug = config.corpus[1].slug
    _write_chunks(config, slug)
    embed_documents(config, encode=_encode)
    path = page_file(config.embedding_dir, slug)
    original = path.read_text(encoding="utf-8")
    switched = replace(config, embedding_model="other-model")
    with pytest.raises(EmbedError) as exc:
        embed_documents(switched, encode=_encode)
    assert exc.value.field == "embedding.model"
    assert path.read_text(encoding="utf-8") == original
    replaced = embed_documents(switched, encode=_encode, force=True)
    assert replaced["model"] == "other-model"
    assert json.loads(path.read_text(encoding="utf-8"))["model"] == "other-model"
