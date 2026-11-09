"""Embed chunk text with the configured sentence-transformers model."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.config import AppConfig
from src.paths import page_file, safe_write

Encode = Callable[[list[str]], list[list[float]]]


class EmbedError(Exception):
    """Existing embeddings were built with a different model."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")


def embed_documents(config: AppConfig, encode: Encode | None = None, force: bool = False) -> dict:
    config.embedding_dir.mkdir(parents=True, exist_ok=True)
    _refuse_model_mismatch(config, force)
    if encode is None:
        encode = load_encoder(config.embedding_model)
    written: list[str] = []
    skipped: list[str] = []
    dimension: int | None = None
    embedded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for page in config.corpus:
        chunk_path = page_file(config.chunk_dir, page.slug)
        embedding_path = page_file(config.embedding_dir, page.slug)
        payload = _read(chunk_path)
        chunks = payload.get("chunks") if isinstance(payload, dict) else None
        if not isinstance(chunks, list):
            skipped.append(page.slug)
            if embedding_path.is_file():
                embedding_path.unlink()
            continue
        usable = [
            chunk
            for chunk in chunks
            if isinstance(chunk, dict) and isinstance(chunk.get("chunk_id"), str) and isinstance(chunk.get("text"), str)
        ]
        texts = [chunk["text"] for chunk in usable]
        vectors = [_normalize(vector) for vector in encode(texts)] if texts else []
        if len(vectors) != len(texts):
            raise EmbedError("embedding", f"{page.slug} returned {len(vectors)} vectors for {len(texts)} chunks")
        if vectors:
            page_dimension = len(vectors[0])
            if any(len(vector) != page_dimension for vector in vectors):
                raise EmbedError("embedding", f"{page.slug} vectors do not share one dimension")
            if dimension is None:
                dimension = page_dimension
            elif page_dimension != dimension:
                raise EmbedError("embedding", f"{page.slug} dimension {page_dimension} does not match {dimension}")
        rows = []
        for chunk, vector in zip(usable, vectors):
            metadata = {key: value for key, value in chunk.items() if key != "chunk_id"}
            rows.append({"chunk_id": chunk["chunk_id"], "vector": vector, "metadata": metadata})
        safe_write(
            embedding_path,
            _dumps(
                {
                    "slug": page.slug,
                    "model": config.embedding_model,
                    "embedded_at": embedded_at,
                    "dimension": dimension or 0,
                    "chunks": rows,
                }
            ),
        )
        written.append(page.slug)
    summary = {
        "model": config.embedding_model,
        "dimension": dimension or 0,
        "document_count": len(written),
        "documents": written,
        "skipped_slugs": skipped,
    }
    safe_write(config.embedding_dir / "_index.json", _dumps(summary))
    return summary


_ENCODER_CACHE: dict[str, "Encode"] = {}


def load_encoder(model_name: str) -> Encode:
    """One encoder per process: loading the model on every ask is wasted work."""
    key = ("local", model_name)
    cached = _ENCODER_CACHE.get(key)
    if cached is not None:
        return cached
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)

    def encode(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        matrix = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        return [row.tolist() for row in matrix]

    _ENCODER_CACHE[key] = encode
    return encode


def load_remote_encoder(model_name: str, endpoint: str | None = None, token: str | None = None) -> Encode:
    """Question embeddings over the HF Inference API with the SAME model id as
    ingestion, so serverless functions never have to load torch. The caller
    normalizes vectors, exactly like the local encoder does."""
    default = "https://router.huggingface.co/hf-inference/models/{model}"
    url = (endpoint or default).format(model=model_name)
    key = ("hf-inference", url, bool(token))
    cached = _ENCODER_CACHE.get(key)
    if cached is not None:
        return cached
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    def encode(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = _hf_post(url, headers, texts)
        if response.status_code != 200:
            raise EmbedError(
                "embedding.hf", f"inference endpoint returned HTTP {response.status_code}"
            )
        try:
            vectors = response.json()
        except ValueError as exc:
            raise EmbedError("embedding.hf", "inference endpoint returned a non-JSON body") from exc
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbedError("embedding.hf", f"expected {len(texts)} vectors from the endpoint")
        return vectors

    _ENCODER_CACHE[key] = encode
    return encode


def _hf_post(url: str, headers: dict, texts: list[str]):
    """POST with the stdlib instead of httpx.

    httpx ConnectError errno 16 (EBUSY) on some serverless sandboxes; urllib
    connects fine there, and locally both behave the same.
    """
    import json as _json
    import urllib.request

    request = urllib.request.Request(
        url,
        data=_json.dumps({"inputs": texts, "options": {"wait_for_model": True}}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "rag-bot/1.0", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return _HTTPResponse(response.status, response.read())
    except urllib.error.HTTPError as error:
        return _HTTPResponse(error.code, error.read())


def load_gemini_encoder(model_name: str, token: str | None = None, task_type: str = "RETRIEVAL_QUERY") -> Encode:
    """Embeddings via the Gemini embedContent API (generativelanguage host).

    The Vercel sandbox cannot load local sentence-transformers weights (the HF
    CDN that serves them is blocked) and HF Inference reserves embeddings for
    paid accounts, so Gemini's free-tier embeddings API is the serverless path.
    Ingestion and questions must use the SAME model and dimensionality;
    task_type selects Google's RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY heads,
    which stay in one vector space. The caller normalizes vectors, like every
    other encoder."""
    url = _gemini_url(model_name)
    key = ("gemini", url, task_type, _GEMINI_DIM, bool(token))
    cached = _ENCODER_CACHE.get(key)
    if cached is not None:
        return cached
    headers = {"x-goog-api-key": token or ""}

    def encode(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = _gemini_post(url, headers, texts, task_type, _GEMINI_DIM)
        if response.status_code != 200:
            raise EmbedError(
                "embedding.gemini", f"embeddings endpoint returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbedError("embedding.gemini", "embeddings endpoint returned a non-JSON body") from exc
        rows = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise EmbedError("embedding.gemini", f"expected {len(texts)} embeddings from the endpoint")
        vectors: list[list[float]] = []
        for row in rows:
            values = row.get("values") if isinstance(row, dict) else None
            if not isinstance(values, list) or not all(isinstance(v, (int, float)) for v in values):
                raise EmbedError("embedding.gemini", "an embedding row was missing its values")
            if len(values) != _GEMINI_DIM:
                raise EmbedError(
                    "embedding.gemini", f"expected {_GEMINI_DIM}-dim vectors, got {len(values)}"
                )
            vectors.append([float(v) for v in values])
        return vectors

    _ENCODER_CACHE[key] = encode
    return encode


_GEMINI_DIM = 768


def _gemini_url(model_name: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:batchEmbedContents"


def _gemini_post(url: str, headers: dict, texts: list[str], task_type: str, dims: int):
    """batchEmbedContents POST using the stdlib transport (see _hf_post)."""
    import json as _json
    import urllib.request

    model = url.rsplit("/", 1)[1].split(":", 1)[0]
    payload = {
        "requests": [
            {
                "model": "models/" + model,
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
                "outputDimensionality": dims,
            }
            for text in texts
        ]
    }
    request = urllib.request.Request(
        url,
        data=_json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "rag-bot/1.0", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return _HTTPResponse(response.status, response.read())
    except urllib.error.HTTPError as error:
        return _HTTPResponse(error.code, error.read())


class _HTTPResponse:
    """The small shape (status_code + json) the encoder code expects."""

    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict | list:
        import json as _json

        return _json.loads(self._body.decode("utf-8"))


_ENCODER_CACHE: dict[tuple, Encode] = {}


def _refuse_model_mismatch(config: AppConfig, force: bool) -> None:
    if force:
        return
    for page in config.corpus:
        existing = _read(page_file(config.embedding_dir, page.slug))
        if not isinstance(existing, dict):
            continue
        recorded = existing.get("model")
        if isinstance(recorded, str) and recorded != config.embedding_model:
            raise EmbedError(
                "embedding.model",
                f"existing embeddings used {recorded!r}; re-run with --force to replace them with {config.embedding_model!r}",
            )


def _normalize(vector: list[float]) -> list[float]:
    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0:
        return list(vector)
    return [value / norm for value in vector]


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"
