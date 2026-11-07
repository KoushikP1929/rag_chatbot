"""Split loaded documents into fact sections. Does not read raw pages or the network."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from src.config import AppConfig
from src.paths import page_file, safe_write

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
LABEL = re.compile(r"^([^:\n]{1,80}):\s*(.*)$")
BULLET_GROUPS = {"Exit load history", "Fund managers"}


def chunk_documents(config: AppConfig) -> dict:
    config.chunk_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[str] = []
    for page in config.corpus:
        document_path = page_file(config.document_dir, page.slug)
        chunk_path = page_file(config.chunk_dir, page.slug)
        document = _read(document_path)
        if document is None or not isinstance(document.get("page_content"), str):
            skipped.append(page.slug)
            if chunk_path.is_file():
                chunk_path.unlink()
            continue
        chunks = chunk_document(document)
        safe_write(chunk_path, _dumps({"slug": page.slug, "chunks": chunks}))
        written.append(page.slug)
    summary = {"document_count": len(written), "documents": written, "skipped_slugs": skipped}
    safe_write(config.chunk_dir / "_index.json", _dumps(summary))
    return summary


def chunk_document(document: dict) -> list[dict]:
    text = document["page_content"].strip()
    sections = _sections(text)
    fallback = not _has_structure(sections)
    if fallback:
        parts = [(f"Part {index + 1}", part, True) for index, part in enumerate(_windows(text))]
    else:
        parts = []
        for section, body in sections:
            pieces = _windows(body) if len(body) > CHUNK_SIZE else [body]
            for piece in pieces:
                if piece != body and not piece.startswith(section):
                    piece = f"{section}\n{piece}"
                parts.append((section, piece, False))
    chunks: list[dict] = []
    for index, (section, body, is_fallback) in enumerate(parts):
        chunk = {
            "chunk_id": _chunk_id(document["slug"], index, section, body),
            "text": body,
            "source_url": document["source_url"],
            "page_title": document.get("page_title"),
            "section": section,
            "chunk_index": index,
            "fetched_at": document.get("fetched_at"),
            "fallback": is_fallback,
        }
        if document.get("kind") == "scheme":
            chunk["scheme_name"] = document.get("scheme_name")
        else:
            chunk["amc"] = document.get("amc") or "HDFC Mutual Fund"
        chunks.append(chunk)
    return chunks


def _sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        label = _label(line)
        if label is not None and label[0] in BULLET_GROUPS:
            name, _value = label
            block = [line]
            index += 1
            while index < len(lines) and lines[index].strip().startswith("- "):
                block.append(lines[index].strip())
                index += 1
            sections.append((name, "\n".join(block)))
            continue
        if label is not None:
            name, value = label
            index += 1
            if value:
                sections.append((name, line))
            continue
        heading = line
        block = [line]
        index += 1
        while index < len(lines):
            current = lines[index].strip()
            if not current:
                nxt = _next_content(lines, index + 1)
                if nxt is None or _label(nxt) is not None or _is_heading(nxt):
                    break
                block.append("")
                index += 1
                continue
            if _label(current) is not None or _is_heading(current):
                break
            block.append(current)
            index += 1
        body = "\n".join(block).strip()
        if body:
            sections.append((_section_name(heading, body), body))
    return sections


def _has_structure(sections: list[tuple[str, str]]) -> bool:
    if len(sections) >= 2:
        return True
    names = {name.lower() for name, _body in sections}
    return bool(names & {"expense ratio", "exit load", "lock-in", "benchmark", "riskometer"})


def _section_name(heading: str, body: str) -> str:
    lowered = body.lower()
    if "capital gain" in lowered or ("statement" in lowered and "download" in lowered):
        return "Statement download"
    return heading[:80]


def _label(line: str) -> tuple[str, str] | None:
    match = LABEL.match(line.strip())
    if match is None:
        return None
    name = match.group(1).strip()
    if len(name.split()) > 8:
        return None
    return name, match.group(2).strip()


def _is_heading(line: str) -> bool:
    if _label(line) is not None:
        return False
    return line.endswith("?") or (len(line) <= 80 and len(line.split()) <= 12)


def _next_content(lines: list[str], start: int) -> str | None:
    for line in lines[start:]:
        if line.strip():
            return line.strip()
    return None


def _windows(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text] if text else []
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            break_at = max(text.rfind("\n", start, end), text.rfind(" ", start, end))
            if break_at > start + CHUNK_OVERLAP:
                end = break_at
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        next_start = end - CHUNK_OVERLAP
        start = next_start if next_start > start else end
    return pieces


def _chunk_id(slug: str, index: int, section: str, text: str) -> str:
    digest = hashlib.sha256(f"{section}\n{text}".encode("utf-8")).hexdigest()[:12]
    return f"{slug}::{index}::{digest}"


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
