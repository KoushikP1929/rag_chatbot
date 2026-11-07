import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.config import PROJECT_ROOT, load_config
from src.index import StoreError, index_embeddings, verify_index
from src.paths import page_file, safe_write

ENV = {"GROQ_API_KEY": "gsk-test-key-1234", "LLM_MODEL": "qwen/qwen3.8-27b"}


def _config(tmp_path: Path):
    loaded = load_config(PROJECT_ROOT / "config.yaml", ENV)
    return replace(
        loaded,
        embedding_dir=tmp_path / "embeddings",
        vector_path=tmp_path / "chroma",
        collection="hdfc_facts",
    )


def _write_embeddings(config, slug: str, texts: list[str], model: str | None = None) -> None:
    chunks = []
    for index, text in enumerate(texts):
        chunks.append(
            {
                "chunk_id": f"{slug}::{index}::abc{index}",
                "vector": [1.0, 0.0],
                "metadata": {
                    "text": text,
                    "section": "Expense ratio" if index == 0 else "Lock-in",
                    "source_url": "https://groww.in/example",
                    "page_title": "Example",
                    "scheme_name": "Example Scheme",
                    "fetched_at": "2026-11-06T00:00:00Z",
                    "chunk_index": index,
                    "fallback": False,
                },
            }
        )
    safe_write(
        page_file(config.embedding_dir, slug),
        json.dumps({"slug": slug, "model": model or config.embedding_model, "chunks": chunks}),
    )


def test_upsert_twice_does_not_duplicate_rows(tmp_path: Path):
    config = _config(tmp_path)
    slug = config.corpus[1].slug
    _write_embeddings(config, slug, ["Expense ratio: 1.01", "Lock-in: None"])
    first = index_embeddings(config)
    second = index_embeddings(config)
    assert first["count"] == 2
    assert second["count"] == 2
    checked = verify_index(config)
    assert checked["count"] == 2
    assert checked["embedding_model"] == config.embedding_model
    assert checked["sample"]


def test_rebuild_replaces_a_collection_from_another_model(tmp_path: Path):
    config = _config(tmp_path)
    slug = config.corpus[1].slug
    _write_embeddings(config, slug, ["Expense ratio: 1.01"])
    index_embeddings(config)
    switched = replace(config, embedding_model="other-model")
    _write_embeddings(switched, slug, ["Expense ratio: 1.01"], model="other-model")
    with pytest.raises(StoreError) as exc:
        index_embeddings(switched)
    assert exc.value.field == "vectorstore.embedding_model"
    rebuilt = index_embeddings(switched, rebuild=True)
    assert rebuilt["count"] == 1
    assert verify_index(switched)["embedding_model"] == "other-model"


def test_removed_chunk_is_not_left_in_the_collection(tmp_path: Path):
    config = _config(tmp_path)
    slug = config.corpus[1].slug
    _write_embeddings(config, slug, ["Expense ratio: 1.01", "Lock-in: None"])
    index_embeddings(config)
    _write_embeddings(config, slug, ["Expense ratio: 1.01"])
    assert index_embeddings(config)["count"] == 1
