"""Build one document per successful raw page. Does not fetch the network."""

from __future__ import annotations

import json
from pathlib import Path

from src.config import AppConfig
from src.paths import page_file, safe_write


def load_documents(config: AppConfig) -> dict:
    config.document_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[str] = []
    for page in config.corpus:
        raw_path = page_file(config.raw_dir, page.slug)
        document_path = page_file(config.document_dir, page.slug)
        raw = _read(raw_path)
        text = raw.get("text") if isinstance(raw, dict) else None
        if not isinstance(raw, dict) or not raw.get("ok") or not isinstance(text, str) or not text.strip():
            skipped.append(page.slug)
            if document_path.is_file():
                document_path.unlink()
            continue
        safe_write(document_path, _dumps(_document(raw, text)))
        written.append(page.slug)
    run_path = config.raw_dir / "_run.json"
    run = _read(run_path)
    last = run.get("last_successful_scrape") if isinstance(run, dict) else None
    index = {
        "document_count": len(written),
        "documents": written,
        "skipped_slugs": skipped,
        "last_successful_scrape": last if isinstance(last, str) else None,
    }
    safe_write(config.document_dir / "_index.json", _dumps(index))
    return index


def _document(raw: dict, text: str) -> dict:
    slug = raw["slug"]
    body = {
        "document_id": f"doc::{slug}",
        "slug": slug,
        "source_url": raw["url"],
        "page_title": raw.get("title"),
        "kind": raw.get("kind"),
        "fetched_at": raw.get("fetched_at"),
        "content_hash": raw.get("hash"),
        "page_content": text,
    }
    if raw.get("kind") == "scheme":
        body["scheme_name"] = raw.get("scheme_name")
    else:
        body["amc"] = raw.get("amc") or "HDFC Mutual Fund"
    return body


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
