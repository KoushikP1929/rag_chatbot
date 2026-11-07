"""Grounded answers and refusals. The citation always comes from a retrieved chunk."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from src.config import AppConfig, Page, load_config
from src.guard import (
    GuardError,
    INTENT_SECTIONS,
    guarded_classify,
    pii_message,
)
from src.llm import LLMError, build_client
from src.paths import page_file, safe_write
from src.retrieve import Retrieved

MAX_SENTENCES = 3
MISSING_FACT = "I don't have that fact in the indexed pages. You can check the sourced page below."
LLM_DOWN = "I could not verify that fact right now. Please try again, or check the sourced page below."
LIKELY_URL = re.compile(r"https?://\S+")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
BANNED_PHRASE = re.compile(
    r"\b(?:you should (?:buy|sell|invest|hold)|i recommend|my recommendation|"
    r"better fund|go for the|worth investing)\b",
    re.IGNORECASE,
)
RETURN_NUMBER = re.compile(r"\b(?:return|returns|cagr|xirr|performance|profit)\b", re.IGNORECASE)
SYSTEM_PROMPT = """You answer questions about HDFC Mutual Fund schemes using only the numbered facts provided.
Rules:
- Answer in at most 3 sentences.
- Use only the numbered facts. If none contains the answer, say you do not have it.
- Never give investment advice, rankings, or buy/sell suggestions.
- Never state or calculate returns or performance numbers.
- Never invent URLs, links, or citations; the system adds the link."""


@dataclass
class AskResult:
    query_id: str
    mode: str
    answer: str
    citation: str | None
    last_updated: str | None
    disclaimer: str
    trace: dict = field(repr=False)


def ask(
    question: str,
    config: AppConfig | None = None,
    client=None,
    retriever: Callable[[str], list[Retrieved]] | None = None,
    query_id: str | None = None,
) -> AskResult:
    """Answer one question: guard first, then retrieval, generation, and a trace."""
    config = config or load_config()
    query_id = query_id or uuid.uuid4().hex[:12]
    last_updated = last_updated_from(config)
    pages = {page.slug: page for page in config.corpus}
    amc = next(page for page in config.corpus if page.kind == "amc")

    try:
        guarded = guarded_classify(question)
    except GuardError as exc:
        return _record(
            config,
            query_id,
            mode="pii",
            question=None,
            answer=pii_message(exc.kinds),
            citation=None,
            last_updated=last_updated,
            trace_extra={"pii_kinds": exc.kinds},
        )

    if guarded.mode != "fact":
        answer, citation = _refusal_answer(guarded.mode)
        link = _link_for(guarded.scheme_slug, pages, amc)
        return _record(
            config,
            query_id,
            mode=guarded.mode,
            question=question,
            answer=answer,
            citation=link,
            last_updated=last_updated,
        )

    if guarded.intent is None:
        return _record(
            config,
            query_id,
            mode="fact",
            question=question,
            answer=MISSING_FACT,
            citation=_link_for(guarded.scheme_slug, pages, amc),
            last_updated=last_updated,
            warnings=["no supported intent in the question"],
        )

    if retriever is None:
        retriever = _default_retriever(config, guarded.intent, guarded.scheme_slug)
    chunks = retriever(question)
    retrieved = [asdict(chunk) for chunk in chunks]
    grounded = _grounded_chunk(chunks, guarded.intent, guarded.scheme_slug, pages)
    if grounded is None:
        return _record(
            config,
            query_id,
            mode="fact",
            question=question,
            answer=MISSING_FACT,
            citation=_link_for(guarded.scheme_slug, pages, amc, fallback=chunks),
            last_updated=last_updated,
            retrieved=retrieved,
            warnings=["no chunk matched the intent and scheme"],
        )

    prompt = _prompt(question, grounded, chunks)
    if client is None:
        client = build_client(config)
    try:
        raw_output = client.complete(prompt["system"], prompt["user"])
    except LLMError as exc:
        return _record(
            config,
            query_id,
            mode="fact",
            question=question,
            answer=LLM_DOWN,
            citation=_validated(grounded.source_url, amc, pages),
            last_updated=last_updated,
            prompt=prompt,
            raw_output=f"LLMError: {exc}",
            retrieved=retrieved,
            warnings=["llm call failed; used the safe fallback"],
        )

    violation = _violation(raw_output)
    text = finalize(raw_output)
    if violation is not None or text is None:
        warning = f"model output violated a rule: {violation}" if violation else "model output was unusable"
        return _record(
            config,
            query_id,
            mode="fact",
            question=question,
            answer=MISSING_FACT,
            citation=_link_for(guarded.scheme_slug, pages, amc, fallback=[grounded]),
            last_updated=last_updated,
            prompt=prompt,
            raw_output=raw_output,
            retrieved=retrieved,
            warnings=[warning],
        )
    return _record(
        config,
        query_id,
        mode="fact",
        question=question,
        answer=text,
        citation=_validated(grounded.source_url, amc, pages),
        last_updated=last_updated,
        prompt=prompt,
        raw_output=raw_output,
        retrieved=retrieved,
    )


def finalize(text: str) -> str | None:
    """Strip URLs, enforce the sentence cap, and drop unusable output."""
    if not isinstance(text, str) or not text.strip():
        return None
    stripped = LIKELY_URL.sub("", text)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    sentences = SENTENCE_SPLIT.split(stripped)
    capped = " ".join(sentences[:MAX_SENTENCES]).strip()
    if not capped or not capped.rstrip(".!?"):
        return None
    return capped if capped.endswith((".", "!", "?")) else capped + "."


def _violation(text: str) -> str | None:
    """Return the rule the model output broke, or None when output is usable.

    A percent figure is legitimate for facts like exit load or expense ratio;
    it is only a violation when it sits in a sentence that talks returns.
    """
    if BANNED_PHRASE.search(text):
        return "advice-like phrase"
    for sentence in SENTENCE_SPLIT.split(text):
        if "%" in sentence and RETURN_NUMBER.search(sentence):
            return "stated a return number"
    return None


def _grounded_chunk(
    chunks: list[Retrieved],
    intent: str,
    scheme_slug: str | None,
    pages: dict[str, Page],
) -> Retrieved | None:
    fragments = INTENT_SECTIONS[intent]
    for chunk in chunks:
        section = chunk.section.lower()
        if not any(fragment in section for fragment in fragments):
            continue
        slug = _slug_of(chunk, pages)
        if scheme_slug is None or slug == scheme_slug:
            return chunk
    return None


def _slug_of(chunk: Retrieved, pages: dict[str, Page]) -> str | None:
    """The chunk metadata carries no slug key; the source URL identifies the page."""
    for slug, page in pages.items():
        if page.url == chunk.source_url:
            return slug
    return None


def _refusal_answer(mode: str) -> tuple[str, str]:
    if mode == "advice":
        return (
            "I cannot advise on whether to buy, sell, or switch between schemes. "
            "I can look up facts like the expense ratio, exit load, minimum SIP, "
            "lock-in, riskometer, or benchmark instead.",
            "",
        )
    if mode == "returns":
        return (
            "I do not provide return numbers or calculate performance. "
            "Please check the official HDFC Mutual Fund factsheet. "
            "I can answer facts like the expense ratio, exit load, minimum SIP, "
            "lock-in, riskometer, or benchmark from the page below.",
            "",
        )
    return (
        "I cover facts from the five indexed HDFC Mutual Fund pages only. "
        "Try asking about the expense ratio, exit load, minimum SIP, lock-in, "
        "riskometer, or benchmark for one of the four schemes.",
        "",
    )


def _link_for(
    scheme_slug: str | None,
    pages: dict[str, Page],
    amc: Page,
    fallback: Iterable[Retrieved] | None = None,
) -> str:
    allowed = {page.url for page in pages.values()}
    if scheme_slug in pages:
        return pages[scheme_slug].url
    if fallback is not None:
        for chunk in fallback:
            if chunk.source_url in allowed:
                return chunk.source_url
    return amc.url


def _validated(citation: str | None, amc: Page, pages: dict[str, Page]) -> str | None:
    allowed = {page.url for page in pages.values()}
    if citation in allowed:
        return citation
    return amc.url


def _prompt(question: str, grounded: Retrieved, chunks: list[Retrieved]) -> dict[str, str]:
    lines: list[str] = [f"Question: {question}", "", "Facts:"]
    for index, chunk in enumerate(chunks, start=1):
        mark = " [answer]" if chunk.chunk_id == grounded.chunk_id else ""
        owner = chunk.scheme_name or chunk.amc or ""
        lines.append(f"Fact [{index}]{mark} (section: {chunk.section}; page: {owner}):")
        lines.append(chunk.text.strip())
    return {"system": SYSTEM_PROMPT, "user": "\n".join(lines)}


def _default_retriever(
    config: AppConfig,
    intent: str | None = None,
    scheme_slug: str | None = None,
) -> Callable[[str], list[Retrieved]]:
    """The production retriever: query Chroma filtered to the wanted sections.

    The exact section names come from the chunk files on disk, so the filter
    matches the same markup that produced them. When no chunk file holds a
    section for that intent, the retriever returns nothing and ask() answers
    "not in corpus" without touching the vector store.
    """
    from src.retrieve import retrieve

    sections = _intent_sections(config, intent, scheme_slug)
    if not sections:
        return lambda _question: []
    scheme_page = None
    for page in config.corpus:
        if page.slug == scheme_slug:
            scheme_page = page
    conditions = [{"section": {"$in": sections}}]
    if scheme_page is not None:
        conditions.append({"source_url": {"$eq": scheme_page.url}})
    where = conditions[0] if len(conditions) == 1 else {"$and": conditions}

    def retriever(question: str) -> list[Retrieved]:
        return retrieve(config, question, where=where)

    return retriever


def _intent_sections(config: AppConfig, intent: str | None, scheme_slug: str | None) -> list[str]:
    if intent is None:
        return []
    fragments = INTENT_SECTIONS[intent]
    slugs = [scheme_slug] if scheme_slug else [page.slug for page in config.corpus]
    names: list[str] = []
    for slug in slugs:
        payload = _read(page_file(config.chunk_dir, slug))
        if not isinstance(payload, dict):
            continue
        for chunk in payload.get("chunks") or []:
            if not isinstance(chunk, dict):
                continue
            section = str(chunk.get("section") or "")
            lowered = section.lower()
            if section and section not in names and any(fragment in lowered for fragment in fragments):
                names.append(section)
    return names


def last_updated_from(config: AppConfig) -> str | None:
    """The last successful scrape date, from the load index or the run summary."""
    for candidate in (config.document_dir / "_index.json", config.raw_dir / "_run.json"):
        payload = _read(candidate)
        if isinstance(payload, dict):
            last = payload.get("last_successful_scrape")
            if isinstance(last, str) and last:
                return last
    return None


def _record(
    config: AppConfig,
    query_id: str,
    mode: str,
    question: str | None,
    answer: str,
    citation: str | None,
    last_updated: str | None,
    prompt: dict | None = None,
    raw_output: str | None = None,
    retrieved: list[dict] | None = None,
    warnings: list[str] | None = None,
    trace_extra: dict | None = None,
) -> AskResult:
    trace = {
        "query_id": query_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "question": question,
        "mode": mode,
        "embedding_model": config.embedding_model,
        "llm": {"provider": config.provider, "model": config.llm_model},
        "retrieved": retrieved or [],
        "prompt": prompt,
        "raw_output": raw_output,
        "final_answer": answer,
        "citation": citation,
        "last_updated": last_updated,
        "disclaimer": config.disclaimer,
        "warnings": warnings or [],
        **(trace_extra or {}),
    }
    safe_write(
        page_file(config.trace_dir, query_id),
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
    )
    return AskResult(
        query_id=query_id,
        mode=mode,
        answer=answer,
        citation=citation,
        last_updated=last_updated,
        disclaimer=config.disclaimer,
        trace=trace,
    )


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
