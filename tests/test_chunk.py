import json
from dataclasses import replace
from pathlib import Path

from src.chunk import chunk_document, chunk_documents
from src.config import PROJECT_ROOT, load_config
from src.paths import page_file, safe_write

ENV = {"GROQ_API_KEY": "gsk-test-key-1234", "LLM_MODEL": "qwen/qwen3.8-27b"}


def _config(tmp_path: Path):
    loaded = load_config(PROJECT_ROOT / "config.yaml", ENV)
    return replace(loaded, document_dir=tmp_path / "documents", chunk_dir=tmp_path / "chunks")


def _write_document(config, slug: str, content: str, **extra) -> None:
    body = {
        "slug": slug,
        "source_url": "https://groww.in/example",
        "page_title": extra.get("page_title", slug),
        "kind": extra.get("kind", "scheme"),
        "scheme_name": extra.get("scheme_name", "Example Scheme"),
        "fetched_at": "2026-11-06T00:00:00Z",
        "page_content": content,
    }
    safe_write(page_file(config.document_dir, slug), json.dumps(body))


def test_label_stays_with_its_value():
    document = {
        "slug": "hdfc-elss-tax-saver-fund-direct-plan-growth",
        "source_url": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
        "page_title": "HDFC ELSS Tax Saver Fund Direct Plan Growth",
        "kind": "scheme",
        "scheme_name": "HDFC ELSS Tax Saver Fund Direct Plan Growth",
        "fetched_at": "2026-11-06T00:00:00Z",
        "page_content": (
            "Expense ratio: 1.2\n"
            "Exit load: Nil\n"
            "Minimum SIP (INR): 500\n"
            "Lock-in: 3 years\n"
            "Riskometer: Moderately High\n"
            "Benchmark: NIFTY 500 TRI\n"
        ),
    }
    chunks = chunk_document(document)
    by_section = {chunk["section"]: chunk for chunk in chunks}
    assert by_section["Lock-in"]["text"] == "Lock-in: 3 years"
    assert by_section["Expense ratio"]["text"] == "Expense ratio: 1.2"
    assert by_section["Lock-in"]["fallback"] is False
    assert all(chunk["scheme_name"] == document["scheme_name"] for chunk in chunks)


def test_same_document_produces_the_same_ids():
    document = {
        "slug": "hdfc-large-cap-fund-direct-growth",
        "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        "page_title": "Large Cap",
        "kind": "scheme",
        "scheme_name": "HDFC Large Cap Fund Direct Growth",
        "fetched_at": "2026-11-06T00:00:00Z",
        "page_content": "Exit load: Exit load of 1% if redeemed within 1 year\nBenchmark: NIFTY 100 TRI\n",
    }
    first = [chunk["chunk_id"] for chunk in chunk_document(document)]
    second = [chunk["chunk_id"] for chunk in chunk_document(document)]
    assert first == second
    assert first[0].startswith("hdfc-large-cap-fund-direct-growth::0::")


def test_headingless_page_uses_fallback():
    document = {
        "slug": "amc-hdfc-mutual-funds",
        "source_url": "https://groww.in/mutual-funds/amc/hdfc-mutual-funds",
        "page_title": "AMC",
        "kind": "amc",
        "amc": "HDFC Mutual Fund",
        "fetched_at": "2026-11-06T00:00:00Z",
        "page_content": "word " * 900,
    }
    chunks = chunk_document(document)
    assert len(chunks) >= 2
    assert all(chunk["fallback"] is True for chunk in chunks)
    assert chunks[0]["amc"] == "HDFC Mutual Fund"


def test_missing_document_drops_a_stale_chunk_file(tmp_path: Path):
    config = _config(tmp_path)
    slug = config.corpus[0].slug
    _write_document(config, slug, "Fund house: HDFC Mutual Fund\nAddress: Mumbai\n")
    chunk_documents(config)
    page_file(config.document_dir, slug).unlink()
    summary = chunk_documents(config)
    assert slug in summary["skipped_slugs"]
    assert not page_file(config.chunk_dir, slug).exists()
