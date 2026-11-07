"""Artifact paths and atomic writes."""

from __future__ import annotations

import os
from pathlib import Path

from src.config import AppConfig


def artifact_dirs(config: AppConfig) -> tuple[Path, ...]:
    return (
        config.raw_dir,
        config.document_dir,
        config.chunk_dir,
        config.embedding_dir,
        config.vector_path,
        config.trace_dir,
    )


def ensure_artifact_dirs(config: AppConfig) -> None:
    for directory in artifact_dirs(config):
        directory.mkdir(parents=True, exist_ok=True)


def page_file(directory: Path, slug: str) -> Path:
    if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
        raise ValueError(f"unsafe slug: {slug!r}")
    return directory / f"{slug}.json"


def safe_write(path: Path, text: str) -> None:
    """Write text by replacing the destination, so a crash cannot leave a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
