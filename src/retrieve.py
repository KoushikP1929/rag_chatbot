"""Query the Chroma collection for the chunks most relevant to a question."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import AppConfig


@dataclass
class Retrieved:
    chunk_id: str
    text: str
    score: float
    section: str
    source_url: str
    scheme_name: str | None
    amc: str | None
    slug: str


class RetrievalError(Exception):
    """The collection is missing, empty, or built with a different model."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")


def retrieve(
    config: AppConfig,
    question: str,
    embed=None,
    collection=None,
    where: dict | None = None,
) -> list[Retrieved]:
    """Return the top-k chunks for a question, using the ingestion embedding model.

    `where` is an optional Chroma metadata filter. The answer layer passes
    `{"section": {"$in": [...]}}` built from the chunk files, because short
    `label: value` rows rank below longer generic sections in cosine space.
    """
    if collection is None:
        collection = _open_collection(config)
    _check_model_parity(collection, config)
    if embed is None:
        from src.embed import load_encoder

        embed = load_encoder(config.embedding_model)
    vectors = embed([question])
    if len(vectors) != 1:
        raise RetrievalError("retrieval", f"expected one question vector, got {len(vectors)}")
    results = collection.query(
        query_embeddings=[vectors[0]],
        n_results=config.top_k,
        include=["documents", "metadatas", "distances"],
        where=where,
    )
    return _rows(results)



def _rows(results: dict) -> list[Retrieved]:
    rows: list[Retrieved] = []
    ids = results.get("ids") or []
    first = ids[0] if ids else []
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    for index, chunk_id in enumerate(first):
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        text = documents[index] if index < len(documents) else ""
        if not isinstance(text, str) or not text:
            continue
        distance = distances[index] if index < len(distances) and distances[index] is not None else 1.0
        score = max(0.0, min(1.0, 1.0 - float(distance)))
        rows.append(
            Retrieved(
                chunk_id=chunk_id,
                text=text,
                score=score,
                section=str(metadata.get("section") or ""),
                source_url=str(metadata.get("source_url") or ""),
                scheme_name=metadata.get("scheme_name"),
                amc=metadata.get("amc"),
                slug=str(metadata.get("slug") or ""),
            )
        )
    return rows


def _open_collection(config: AppConfig):
    import chromadb

    from src.index import StoredEmbeddings

    client = chromadb.PersistentClient(path=str(config.vector_path))
    try:
        return client.get_collection(config.collection, embedding_function=StoredEmbeddings())
    except Exception as exc:
        raise RetrievalError(
            "vectorstore",
            f"collection {config.collection!r} not found; run python -m src.cli index first",
        ) from exc


def _check_model_parity(collection, config: AppConfig) -> None:
    recorded = (collection.metadata or {}).get("embedding_model")
    if recorded != config.embedding_model:
        raise RetrievalError(
            "vectorstore.embedding_model",
            f"the collection was built with {recorded!r}; re-run "
            f"python -m src.cli embed --force and index to use {config.embedding_model!r}",
        )
