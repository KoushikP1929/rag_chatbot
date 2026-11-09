"""Load and validate config.yaml plus .env."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_CORPUS: dict[str, dict[str, str]] = {
    "https://groww.in/mutual-funds/amc/hdfc-mutual-funds": {
        "slug": "amc-hdfc-mutual-funds",
        "kind": "amc",
    },
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth": {
        "slug": "hdfc-large-cap-fund-direct-growth",
        "kind": "scheme",
    },
    "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth": {
        "slug": "hdfc-flexi-cap-direct-growth",
        "kind": "scheme",
    },
    "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth": {
        "slug": "hdfc-elss-tax-saver-fund-direct-plan-growth",
        "kind": "scheme",
    },
    "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth": {
        "slug": "hdfc-mid-cap-fund-direct-growth",
        "kind": "scheme",
    },
}

PROVIDERS = ("groq", "gemini", "openai", "anthropic", "mistral")

PROVIDER_KEYS = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


class ConfigError(Exception):
    """A named config or environment field failed validation."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")


def _is_serverless(environ: Mapping[str, str]) -> bool:
    """True on Vercel-like hosts where only the temp directory is writable."""
    return bool(
        (environ.get("VERCEL") or environ.get("VERCEL_ENV") or environ.get("NOW_REGION") or "").strip()
    )


def _serverless_tmp(name: str) -> Path:
    """A writable path under the host's temp dir.

    /tmp is scoped to one function instance, so each instance recreates the
    index there without cross-instance SQLite contention (errno 16 EBUSY).
    """
    return Path(tempfile.gettempdir()) / "rag_bot" / name


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    url: str
    kind: str
    scheme_name: str | None


@dataclass(frozen=True)
class AppConfig:
    corpus: tuple[Page, ...]
    embedding_model: str
    vector_engine: str
    vector_path: Path
    collection: str
    provider: str
    api_key: str
    api_key_name: str
    llm_model: str
    top_k: int
    raw_dir: Path
    document_dir: Path
    chunk_dir: Path
    embedding_dir: Path
    trace_dir: Path
    disclaimer: str
    query_provider: str = "local"
    hf_endpoint: str | None = None
    hf_token: str | None = None
    gemini_token: str | None = None


def load_config(
    config_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    path = config_path or (PROJECT_ROOT / "config.yaml")
    if environ is None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        environ = os.environ
    if not path.is_file():
        raise ConfigError("config.yaml", f"file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError("config.yaml", f"invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config.yaml", "expected a mapping at the top level")
    return _build(raw, environ)


def _build(raw: dict, environ: Mapping[str, str]) -> AppConfig:
    corpus = _pages(raw.get("corpus"))
    embedding = _mapping(raw, "embedding")
    vectorstore = _mapping(raw, "vectorstore")
    llm = _mapping(raw, "llm")
    retrieval = _mapping(raw, "retrieval")
    artifacts = _mapping(raw, "artifacts")
    ui = _mapping(raw, "ui")

    model = _text(embedding, "embedding.model", "model")
    engine = _text(vectorstore, "vectorstore.engine", "engine")
    if engine != "chroma":
        raise ConfigError("vectorstore.engine", "only 'chroma' is supported")
    collection = _text(vectorstore, "vectorstore.collection", "collection")
    provider = _text(llm, "llm.provider", "provider").lower()
    if provider not in PROVIDERS:
        allowed = ", ".join(PROVIDERS)
        raise ConfigError("llm.provider", f"unknown provider {provider!r}; allowed: {allowed}")

    key_name = PROVIDER_KEYS[provider]
    api_key = (environ.get(key_name) or "").strip()
    if not api_key:
        raise ConfigError(key_name, "missing; set it in .env")
    llm_model = (environ.get("LLM_MODEL") or "").strip()
    if not llm_model:
        raise ConfigError("LLM_MODEL", "missing or empty; set it in .env")

    top_k = retrieval.get("top_k")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ConfigError("retrieval.top_k", "expected an integer >= 1")

    disclaimer = _text(ui, "ui.disclaimer", "disclaimer")

    # Environment overrides for serverless deployments. On those hosts (Vercel,
    # etc.) only the temp dir is writable; the bundled repo directory is
    # read-only, so Chroma's SQLite journal and trace writes fail with
    # errno 16 (EBUSY). Explicit env overrides always win; otherwise Vercel
    # defaults both to a per-instance writable temp path, where the cold-start
    # rebuild in retrieve._open_collection builds the index on first question.
    serverless = _is_serverless(environ)
    if environ.get("VECTORSTORE_PATH", "").strip():
        vector_path = Path(environ["VECTORSTORE_PATH"].strip())
    elif serverless:
        vector_path = _serverless_tmp("chroma")
    else:
        vector_path = _path(vectorstore, "vectorstore.persist_path", "persist_path")
    if environ.get("TRACE_DIR", "").strip():
        trace_dir = Path(environ["TRACE_DIR"].strip())
    elif serverless:
        trace_dir = _serverless_tmp("traces")
    else:
        trace_dir = _path(artifacts, "artifacts.trace_dir", "trace_dir")

    embedding_block = embedding
    query_provider = (environ.get("EMBEDDING_QUERY_PROVIDER") or embedding_block.get("query_provider", "local")).strip().lower()
    if query_provider not in ("local", "hf-inference", "gemini"):
        raise ConfigError("embedding.query_provider", "must be 'local', 'hf-inference', or 'gemini'")
    hf_endpoint_default = "https://router.huggingface.co/hf-inference/models/{model}"
    hf_endpoint = embedding_block.get("hf_endpoint", hf_endpoint_default)
    hf_token = (environ.get("HF_API_TOKEN") or "").strip() or None
    if query_provider == "hf-inference" and not hf_token:
        raise ConfigError(
            "HF_API_TOKEN",
            "hf-inference question embeddings need a Hugging Face token; create a free one on huggingface.co/settings/tokens",
        )
    gemini_token = (environ.get("GEMINI_API_KEY") or "").strip() or None
    if query_provider == "gemini" and not gemini_token:
        raise ConfigError(
            "GEMINI_API_KEY",
            "gemini question embeddings need an API key; create a free one on aistudio.google.com/apikey",
        )
    return AppConfig(
        corpus=tuple(corpus),
        embedding_model=model,
        vector_engine=engine,
        vector_path=vector_path,
        collection=collection,
        provider=provider,
        api_key=api_key,
        api_key_name=key_name,
        llm_model=llm_model,
        top_k=top_k,
        raw_dir=_path(artifacts, "artifacts.raw_dir", "raw_dir"),
        document_dir=_path(artifacts, "artifacts.document_dir", "document_dir"),
        chunk_dir=_path(artifacts, "artifacts.chunk_dir", "chunk_dir"),
        embedding_dir=_path(artifacts, "artifacts.embedding_dir", "embedding_dir"),
        trace_dir=trace_dir,
        disclaimer=disclaimer,
        query_provider=query_provider,
        hf_endpoint=hf_endpoint,
        hf_token=hf_token,
        gemini_token=gemini_token,
    )


def _pages(value: object) -> list[Page]:
    if not isinstance(value, list):
        raise ConfigError("corpus", "expected a list of pages")
    if len(value) != len(ALLOWED_CORPUS):
        raise ConfigError(
            "corpus",
            f"expected {len(ALLOWED_CORPUS)} pages, found {len(value)}",
        )
    pages: list[Page] = []
    seen_urls: set[str] = set()
    for index, item in enumerate(value):
        field = f"corpus[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(field, "expected a mapping")
        url = _text(item, f"{field}.url", "url")
        expected = ALLOWED_CORPUS.get(url)
        if expected is None:
            raise ConfigError(f"{field}.url", f"not in the five-page allow-list: {url}")
        if url in seen_urls:
            raise ConfigError(f"{field}.url", f"duplicate URL: {url}")
        seen_urls.add(url)
        slug = _text(item, f"{field}.slug", "slug")
        if slug != expected["slug"]:
            raise ConfigError(f"{field}.slug", f"expected {expected['slug']!r} for this URL")
        kind = _text(item, f"{field}.kind", "kind")
        if kind != expected["kind"]:
            raise ConfigError(f"{field}.kind", f"expected {expected['kind']!r} for this URL")
        title = _text(item, f"{field}.title", "title")
        scheme_name = item.get("scheme_name")
        if kind == "scheme":
            if not isinstance(scheme_name, str) or not scheme_name.strip():
                raise ConfigError(f"{field}.scheme_name", "required for a scheme page")
            scheme_name = scheme_name.strip()
        else:
            scheme_name = None
        pages.append(Page(slug=slug, title=title, url=url, kind=kind, scheme_name=scheme_name))
    missing = set(ALLOWED_CORPUS) - seen_urls
    if missing:
        raise ConfigError("corpus", f"missing allow-listed URL: {sorted(missing)[0]}")
    return pages


def _mapping(raw: dict, key: str) -> dict:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfigError(key, "expected a mapping")
    return value


def _text(block: dict, field: str, key: str) -> str:
    value = block.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(field, "expected non-empty text")
    return value.strip()


def _path(block: dict, field: str, key: str) -> Path:
    text = _text(block, field, key)
    path = Path(text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}…{value[-2:]}"
