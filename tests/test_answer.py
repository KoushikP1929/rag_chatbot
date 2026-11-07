import json
from dataclasses import replace
from pathlib import Path

from src.config import PROJECT_ROOT, load_config
from src.answer import MISSING_FACT, ask, finalize
from src.paths import page_file
from src.retrieve import Retrieved

ENV = {"GROQ_API_KEY": "gsk-test-key-1234", "LLM_MODEL": "qwen/qwen3.8-27b"}
LARGE_CAP_URL = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
AMC_URL = "https://groww.in/mutual-funds/amc/hdfc-mutual-funds"


def _config(tmp_path: Path):
    loaded = load_config(PROJECT_ROOT / "config.yaml", ENV)
    return replace(
        loaded,
        trace_dir=tmp_path / "traces",
        document_dir=tmp_path / "documents",
        raw_dir=tmp_path / "raw",
    )


def _chunk(slug: str, section: str, url: str = LARGE_CAP_URL) -> Retrieved:
    return Retrieved(
        chunk_id=f"{slug}::0::abc",
        text=f"{section}: 1.01",
        score=0.81,
        section=section,
        source_url=url,
        scheme_name="HDFC Large Cap Fund Direct Growth",
        amc=None,
        slug=slug,
    )


class StubClient:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[dict] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        return self.answer


def test_fact_answer_is_capped_and_cites_the_chunk(tmp_path: Path):
    config = _config(tmp_path)
    client = StubClient("The exit load is 1%. It applies within one year. Extra sentence beyond the cap.")
    trace_file = page_file(config.trace_dir, "abc")
    assert not trace_file.exists()
    result = ask(
        "What is the expense ratio of HDFC Large Cap Fund?",
        config=config,
        client=client,
        retriever=lambda _q: [_chunk(config.corpus[1].slug, "Expense ratio")],
        query_id="abc",
    )
    assert result.mode == "fact"
    parts = [part for part in result.answer.split(". ") if part]
    assert len(parts) <= 3
    assert result.citation == LARGE_CAP_URL
    assert client.calls, "the fact path must call the configured LLM"
    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    assert trace["question"].startswith("What is the expense ratio")
    assert trace["llm"]["model"] == "qwen/qwen3.8-27b"
    assert trace["retrieved"][0]["section"] == "Expense ratio"
    assert trace["citation"] == LARGE_CAP_URL


def test_fact_without_matching_section_says_not_in_corpus(tmp_path: Path):
    config = _config(tmp_path)
    client = StubClient("should never be called")
    result = ask(
        "What is the lock-in for HDFC Large Cap Fund?",
        config=config,
        client=client,
        retriever=lambda _q: [_chunk(config.corpus[1].slug, "Fund managers")],
        query_id="abc",
    )
    assert result.answer == MISSING_FACT
    assert result.citation == LARGE_CAP_URL
    assert not client.calls, "an ungrounded fact must not reach the LLM"


def test_advice_is_refused_without_an_llm_call(tmp_path: Path):
    config = _config(tmp_path)
    client = StubClient("Buy it, it is the best fund!")
    result = ask(
        "Should I buy HDFC Mid Cap Fund?",
        config=config,
        client=client,
        retriever=lambda _q: [],
        query_id="abc",
    )
    assert result.mode == "advice"
    assert "cannot advise" in result.answer
    assert result.citation == "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
    assert not client.calls
    trace = json.loads(page_file(config.trace_dir, "abc").read_text(encoding="utf-8"))
    assert trace["prompt"] is None


def test_returns_question_gives_no_number(tmp_path: Path):
    config = _config(tmp_path)
    stub = StubClient("The 3-year return is 22%!")
    result = ask(
        "What returns will HDFC Flexi Cap give?",
        config=config,
        client=stub,
        retriever=lambda _q: [],
        query_id="abc",
    )
    assert result.mode == "returns"
    assert "%" not in result.answer and "22" not in result.answer
    assert result.citation == "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth"
    assert not stub.calls


def test_banned_phrase_and_model_url_fall_back_to_safe_answer(tmp_path: Path):
    config = _config(tmp_path)
    stub = StubClient(
        "You should buy this fund now. It is a great choice. See https://model-invented.example.com"
    )
    result = ask(
        "What is the exit load on HDFC Large Cap Fund?",
        config=config,
        client=stub,
        retriever=lambda _q: [_chunk(config.corpus[1].slug, "Exit load")],
        query_id="abc",
    )
    assert result.answer == MISSING_FACT
    assert result.citation == LARGE_CAP_URL
    trace = json.loads(page_file(config.trace_dir, "abc").read_text(encoding="utf-8"))
    assert "violated a rule" in trace["warnings"][0]


def test_pii_never_reaches_the_llm_or_the_trace(tmp_path: Path):
    config = _config(tmp_path)
    stub = StubClient("never called")
    result = ask(
        "What is the exit load? My PAN is ABCDE1234F",
        config=config,
        client=stub,
        retriever=lambda _q: [],
        query_id="abc",
    )
    assert result.mode == "pii"
    assert "Remove personal details" in result.answer or "resubmit" in result.answer
    assert not stub.calls
    trace = json.loads(page_file(config.trace_dir, "abc").read_text(encoding="utf-8"))
    assert trace["question"] is None
    assert trace["pii_kinds"] == ["pan"]
    assert "ABCDE1234F" not in json.dumps(trace)


def test_finalize_caps_sentences_and_strips_urls():
    assert finalize("One. Two. Three. Four. Five.") == "One. Two. Three."
    cleaned = finalize("The ratio is 1.01.Visit https://extra.example.com for more.")
    assert "example.com" not in cleaned
    assert finalize("   ") is None
    assert finalize(None) is None
