"""Upsert stored embeddings into the local Chroma collection."""

from __future__ import annotations

import json
from pathlib import Path

from src.config import AppConfig
from src.paths import page_file

METADATA_KEYS = (
    "source_url",
    "page_title",
    "section",
    "scheme_name",
    "amc",
    "fetched_at",
    "chunk_index",
    "fallback",
)


class StoreError(Exception):
    """The vector collection cannot be updated safely."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")


class StoredEmbeddings:
    """Marker so Chroma does not download or run its own embedding model."""

    @staticmethod
    def name() -> str:
        return "stored"

    def __call__(self, input):
        raise StoreError("vectorstore", "embeddings are already stored; pass them to upsert or query")

    def embed_query(self, input):
        return self(input)

    @staticmethod
    def default_space() -> str:
        return "cosine"

    @staticmethod
    def supported_spaces() -> list[str]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> "StoredEmbeddings":
        return StoredEmbeddings()


def index_embeddings(config: AppConfig, rebuild: bool = False) -> dict:
    rows = _rows(config)
    if not rows:
        raise StoreError("embeddings", "no embedding files found; run python -m src.cli embed first")
    import chromadb

    client = chromadb.PersistentClient(path=str(config.vector_path))
    collection = _collection(client, config, rebuild)
    ids = [row["id"] for row in rows]
    for start in range(0, len(rows), 64):
        batch = rows[start : start + 64]
        collection.upsert(
            ids=[row["id"] for row in batch],
            embeddings=[row["vector"] for row in batch],
            documents=[row["document"] for row in batch],
            metadatas=[row["metadata"] for row in batch],
        )
    _delete_stale(collection, set(ids))
    return {
        "collection": config.collection,
        "path": str(config.vector_path),
        "embedding_model": config.embedding_model,
        "count": collection.count(),
    }


def verify_index(config: AppConfig) -> dict:
    import chromadb

    client = chromadb.PersistentClient(path=str(config.vector_path))
    try:
        collection = client.get_collection(config.collection, embedding_function=StoredEmbeddings())
    except Exception as exc:
        raise StoreError("vectorstore", "run python -m src.cli index first") from exc
    sample = collection.get(limit=3, include=["metadatas", "documents"])
    rows = []
    metadatas = sample.get("metadatas") or []
    documents = sample.get("documents") or []
    for index, chunk_id in enumerate(sample.get("ids") or []):
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        rows.append(
            {
                "chunk_id": chunk_id,
                "section": metadata.get("section"),
                "source_url": metadata.get("source_url"),
                "document": documents[index] if index < len(documents) else None,
            }
        )
    recorded = (collection.metadata or {}).get("embedding_model")
    return {
        "collection": collection.name,
        "path": str(config.vector_path),
        "embedding_model": recorded,
        "count": collection.count(),
        "sample": rows,
    }


def _collection(client, config: AppConfig, rebuild: bool):
    names = _collection_names(client)
    if config.collection in names:
        if rebuild:
            client.delete_collection(config.collection)
        else:
            collection = client.get_collection(config.collection, embedding_function=StoredEmbeddings())
            recorded = (collection.metadata or {}).get("embedding_model")
            if recorded != config.embedding_model:
                raise StoreError(
                    "vectorstore.embedding_model",
                    f"collection was built with {recorded!r}; re-run with --rebuild to replace it with {config.embedding_model!r}",
                )
            return collection
    return client.create_collection(
        name=config.collection,
        metadata={"embedding_model": config.embedding_model, "hnsw:space": "cosine"},
        embedding_function=StoredEmbeddings(),
    )


def _collection_names(client) -> set[str]:
    names: set[str] = set()
    for item in client.list_collections():
        names.add(item.name if hasattr(item, "name") else str(item))
    return names


def _delete_stale(collection, keep: set[str]) -> None:
    existing = collection.get(include=[])["ids"]
    stale = [chunk_id for chunk_id in existing if chunk_id not in keep]
    for start in range(0, len(stale), 64):
        collection.delete(ids=stale[start : start + 64])


def _rows(config: AppConfig) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for page in config.corpus:
        payload = _read(page_file(config.embedding_dir, page.slug))
        if not isinstance(payload, dict):
            continue
        recorded = payload.get("model")
        if recorded != config.embedding_model:
            raise StoreError(
                "embedding.model",
                f"{page.slug} was embedded with {recorded!r}; expected {config.embedding_model!r}",
            )
        chunks = payload.get("chunks")
        if not isinstance(chunks, list):
            continue
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            chunk_id = chunk.get("chunk_id")
            vector = chunk.get("vector")
            metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            text = metadata.get("text")
            if not isinstance(chunk_id, str) or chunk_id in seen:
                continue
            if not isinstance(vector, list) or not vector or not isinstance(text, str):
                continue
            seen.add(chunk_id)
            rows.append(
                {
                    "id": chunk_id,
                    "vector": vector,
                    "document": text,
                    "metadata": _metadata(metadata),
                }
            )
    return rows


def _metadata(source: dict) -> dict:
    clean: dict = {}
    for key in METADATA_KEYS:
        value = source.get(key)
        if isinstance(value, bool) or isinstance(value, (str, int, float)) and value is not None:
            if isinstance(value, float) and not value == value:
                continue
            clean[key] = value
    return clean


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
