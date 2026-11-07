"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys

from src.answer import ask as answer_question, last_updated_from
from src.chunk import chunk_documents
from src.config import ConfigError, load_config, mask_secret
from src.documents import load_documents
from src.embed import EmbedError, embed_documents
from src.fetch import FetchError, scrape
from src.index import StoreError, index_embeddings, verify_index
from src.paths import ensure_artifact_dirs, page_file
from src.retrieve import RetrievalError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config-check", help="Validate config.yaml and .env, then print a summary")
    sub.add_parser("scrape", help="Fetch the five configured pages into data/raw")
    sub.add_parser("load", help="Build one document per successful raw page")
    sub.add_parser("chunk", help="Split loaded documents into fact sections")
    embed_parser = sub.add_parser("embed", help="Embed chunks with the configured model")
    embed_parser.add_argument("--force", action="store_true", help="Replace embeddings from a different model")
    index_parser = sub.add_parser("index", help="Upsert embeddings into Chroma")
    index_parser.add_argument("--rebuild", action="store_true", help="Drop the collection and write it again")
    index_parser.add_argument("--verify", action="store_true", help="Print the collection count and a sample")
    ask_parser = sub.add_parser("ask", help="Answer one question; writes a trace to data/traces")
    ask_parser.add_argument("question", help="The question to answer")
    all_parser = sub.add_parser("all", help="Run scrape → load → chunk → embed → index in order")
    all_parser.add_argument("--keep-going", action="store_true", help="Continue after a failed stage")
    args = parser.parse_args(argv)
    if args.command == "config-check":
        return config_check()
    if args.command == "scrape":
        return scrape_command()
    if args.command == "load":
        return load_command()
    if args.command == "chunk":
        return chunk_command()
    if args.command == "embed":
        return embed_command(force=args.force)
    if args.command == "index":
        return index_command(rebuild=args.rebuild, verify=args.verify)
    if args.command == "ask":
        return ask_command(args.question)
    if args.command == "all":
        return all_command(keep_going=args.keep_going)
    print(f"unknown command: {args.command}", file=sys.stderr)
    return 2


def config_check() -> int:
    try:
        config = load_config()
        ensure_artifact_dirs(config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    print("Corpus:")
    for page in config.corpus:
        print(f"  {page.slug}  {page.url}")
    print(f"Embedding: {config.embedding_model}")
    print(f"Vector store: {config.vector_engine}  {config.vector_path}  {config.collection}")
    print(f"LLM provider: {config.provider}")
    print(f"LLM model: {config.llm_model}")
    print(f"{config.api_key_name}: {mask_secret(config.api_key)}")
    print("Config OK")
    return 0


def scrape_command() -> int:
    try:
        config = load_config()
        ensure_artifact_dirs(config)
        results = scrape(config)
    except (ConfigError, FetchError) as exc:
        print(exc, file=sys.stderr)
        return 1
    failed = [item for item in results if not item.ok]
    for item in results:
        if item.ok:
            print(f"ok      {item.slug}  {item.chars} chars")
        else:
            print(f"FAILED  {item.slug}  {item.error}", file=sys.stderr)
    print(f"Raw pages saved: {len(results) - len(failed)}")
    return 1 if failed else 0


def load_command() -> int:
    try:
        config = load_config()
        ensure_artifact_dirs(config)
        index = load_documents(config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    for slug in index["documents"]:
        path = page_file(config.document_dir, slug)
        print(f"loaded  {slug}  {path.stat().st_size} bytes")
    for slug in index["skipped_slugs"]:
        print(f"skipped {slug}", file=sys.stderr)
    print(f"Documents: {index['document_count']}")
    if index["last_successful_scrape"]:
        print(f"Last updated from sources: {index['last_successful_scrape']}")
    return 0 if index["document_count"] else 1


def chunk_command() -> int:
    try:
        config = load_config()
        ensure_artifact_dirs(config)
        summary = chunk_documents(config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    for slug in summary["documents"]:
        payload = json_chunks(page_file(config.chunk_dir, slug))
        sections = ", ".join(chunk["section"] for chunk in payload["chunks"][:8])
        extra = "" if len(payload["chunks"]) <= 8 else ", …"
        print(f"chunked {slug}  {len(payload['chunks'])} sections  {sections}{extra}")
    for slug in summary["skipped_slugs"]:
        print(f"skipped {slug}", file=sys.stderr)
    print(f"Chunk files: {summary['document_count']}")
    return 0 if summary["document_count"] else 1


def embed_command(force: bool = False) -> int:
    try:
        config = load_config()
        ensure_artifact_dirs(config)
        print(f"Embedding with {config.embedding_model}")
        summary = embed_documents(config, force=force)
    except (ConfigError, EmbedError) as exc:
        print(exc, file=sys.stderr)
        return 1
    for slug in summary["documents"]:
        payload = json_chunks(page_file(config.embedding_dir, slug))
        print(f"embedded {slug}  {len(payload['chunks'])} vectors")
    for slug in summary["skipped_slugs"]:
        print(f"skipped {slug}", file=sys.stderr)
    print(f"Model: {summary['model']}")
    print(f"Dimension: {summary['dimension']}")
    print(f"Embedding files: {summary['document_count']}")
    return 0 if summary["document_count"] else 1


def index_command(rebuild: bool = False, verify: bool = False) -> int:
    try:
        config = load_config()
        ensure_artifact_dirs(config)
        if verify and not rebuild:
            summary = verify_index(config)
        else:
            summary = index_embeddings(config, rebuild=rebuild)
            if verify:
                summary = verify_index(config)
    except (ConfigError, StoreError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Collection: {summary['collection']}")
    print(f"Path: {summary['path']}")
    print(f"Embedding model: {summary['embedding_model']}")
    print(f"Count: {summary['count']}")
    for row in summary.get("sample") or []:
        print(f"  {row['chunk_id']}  {row['section']}  {row['source_url']}")
    return 0


def ask_command(question: str) -> int:
    try:
        config = load_config()
        ensure_artifact_dirs(config)
        result = answer_question(question, config=config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    except RetrievalError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Mode: {result.mode}")
    print(f"Answer: {result.answer}")
    if result.citation:
        print(f"Citation: {result.citation}")
    if result.last_updated:
        print(f"Last updated from sources: {result.last_updated}")
    print(f"Trace: {page_file(config.trace_dir, result.query_id)}")
    return 0


def all_command(keep_going: bool = False) -> int:
    """Run the full ingestion pipeline: scrape → load → chunk → embed → index."""
    stages = (
        ("scrape", scrape_command),
        ("load", load_command),
        ("chunk", chunk_command),
        ("embed", embed_command),
        ("index", index_command),
    )
    failed: list[str] = []
    for name, run in stages:
        print(f"== {name} ==")
        code = run()
        if code == 0:
            continue
        print(f"stage {name} failed (exit {code})", file=sys.stderr)
        if not keep_going:
            return code
        failed.append(name)
    if failed:
        print(f"completed with failed stages: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def json_chunks(path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
