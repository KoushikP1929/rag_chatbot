import json
from dataclasses import replace
from pathlib import Path

from src.config import PROJECT_ROOT, load_config
from src.documents import load_documents
from src.fetch import FetchError, extract_text, scrape
from src.paths import page_file

ENV = {"GROQ_API_KEY": "gsk-test-key-1234", "LLM_MODEL": "qwen/qwen3.8-27b"}


def _config(tmp_path: Path):
    loaded = load_config(PROJECT_ROOT / "config.yaml", ENV)
    return replace(
        loaded,
        raw_dir=tmp_path / "raw",
        document_dir=tmp_path / "documents",
    )


def _scheme_html() -> str:
    payload = {
        "props": {
            "pageProps": {
                "mfServerSideData": {
                    "scheme_name": "HDFC Large Cap Fund Direct Growth",
                    "fund_house": "HDFC Mutual Fund",
                    "category": "Equity",
                    "sub_category": "Large Cap",
                    "expense_ratio": "1.01",
                    "exit_load": "Exit load of 1% if redeemed within 1 year",
                    "min_sip_investment": 100,
                    "lock_in": {"years": 0, "months": 0, "days": 0},
                    "nfo_risk": "Moderately High Riskometer",
                    "benchmark": "NIFTY 100 TRI",
                    "description": "Long-term capital appreciation from large-cap companies. " * 8,
                    "logo_url": "https://evil.example/logo.png",
                    "sid_url": "https://www.hdfcfund.com/factsheet",
                    "simple_return": {"return1y": 99.5},
                    "peerComparison": [
                        {"scheme_name": "Other Fund", "search_id": "other-fund"}
                    ],
                }
            }
        }
    }
    blob = json.dumps(payload)
    return (
        "<html><body><a href=\"https://evil.example/other-fund\">Other</a>"
        f'<script id="__NEXT_DATA__" type="application/json">{blob}</script>'
        "</body></html>"
    )


def _amc_html() -> str:
    paragraph = (
        "<p>HDFC Asset Management Company Ltd. manages the HDFC Mutual Fund schemes. "
        "Investors can read the scheme page for expense ratio, exit load, and minimum SIP.</p>"
    ) * 4
    payload = {
        "props": {
            "pageProps": {
                "amcMainPageData": [
                    {
                        "amcs": [
                            {
                                "name": "Some Other AMC",
                                "deep_link": "https://evil.example/other-amc",
                            }
                        ]
                    },
                    {
                        "key_information": {
                            "fund_house": "HDFC Mutual Fund",
                            "address": "Churchgate, Mumbai",
                            "phone": "9999999999",
                            "email": "secret@example.com",
                        },
                        "contentList": [
                            {"title": "About HDFC Mutual Fund", "content": paragraph}
                        ],
                    },
                ]
            }
        }
    }
    blob = json.dumps(payload)
    return f'<html><script id="__NEXT_DATA__" type="application/json">{blob}</script></html>'


def test_extract_keeps_facts_and_drops_other_links():
    text = extract_text(_scheme_html(), "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth")
    assert "Expense ratio: 1.01" in text
    assert "Exit load: Exit load of 1% if redeemed within 1 year" in text
    assert "Minimum SIP (INR): 100" in text
    assert "Lock-in: None" in text
    assert "Benchmark: NIFTY 100 TRI" in text
    assert "evil.example" not in text
    assert "other-fund" not in text
    assert "99.5" not in text
    assert "hdfcfund.com" not in text


def test_extract_amc_skips_other_amc_links_and_contact_numbers():
    text = extract_text(_amc_html(), "https://groww.in/mutual-funds/amc/hdfc-mutual-funds")
    assert "HDFC Mutual Fund" in text
    assert "About HDFC Mutual Fund" in text
    assert "evil.example" not in text
    assert "9999999999" not in text
    assert "secret@example.com" not in text


def test_scrape_requests_only_the_five_pages(tmp_path: Path):
    config = _config(tmp_path)
    seen: list[str] = []

    def getter(url: str) -> tuple[int, str]:
        seen.append(url)
        if url not in {page.url for page in config.corpus}:
            raise AssertionError(f"fetched a page outside the five links: {url}")
        if "/amc/" in url:
            return 200, _amc_html()
        return 200, _scheme_html()

    results = scrape(config, getter)
    assert seen == [page.url for page in config.corpus]
    assert all(item.ok for item in results)
    assert not page_file(config.document_dir, config.corpus[1].slug).exists()
    raw = json.loads(page_file(config.raw_dir, config.corpus[1].slug).read_text(encoding="utf-8"))
    assert "Expense ratio: 1.01" in raw["text"]
    assert "evil.example" not in raw["text"]


def test_failed_page_has_no_text_and_drops_a_stale_document(tmp_path: Path):
    config = _config(tmp_path)
    config.document_dir.mkdir(parents=True)
    stale = page_file(config.document_dir, config.corpus[0].slug)
    stale.write_text('{"page_content":"stale"}', encoding="utf-8")

    def getter(url: str) -> tuple[int, str]:
        if url == config.corpus[0].url:
            raise FetchError("timed out")
        if "/amc/" in url:
            return 200, _amc_html()
        return 200, _scheme_html()

    results = scrape(config, getter)
    assert results[0].ok is False
    raw = json.loads(page_file(config.raw_dir, config.corpus[0].slug).read_text(encoding="utf-8"))
    assert raw["ok"] is False
    assert "text" not in raw
    assert stale.exists()
    index = load_documents(config)
    assert not stale.exists()
    assert config.corpus[0].slug in index["skipped_slugs"]
    assert index["document_count"] == 4


def test_second_scrape_overwrites_the_same_file(tmp_path: Path):
    config = _config(tmp_path)

    def getter(_url: str) -> tuple[int, str]:
        return 200, _scheme_html() if "/amc/" not in _url else _amc_html()

    scrape(config, getter)
    first = page_file(config.raw_dir, config.corpus[1].slug).read_text(encoding="utf-8")
    scrape(config, getter)
    second = page_file(config.raw_dir, config.corpus[1].slug).read_text(encoding="utf-8")
    assert json.loads(first)["hash"] == json.loads(second)["hash"]
    assert json.loads(first)["text"] == json.loads(second)["text"]
    load_documents(config)
    names = {path.name for path in config.document_dir.glob("*.json")}
    assert names == {f"{page.slug}.json" for page in config.corpus} | {"_index.json"}
