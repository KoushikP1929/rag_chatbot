"""Fetch the five configured Groww pages. Does not follow links on those pages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import httpx
from bs4 import BeautifulSoup

from src.config import ALLOWED_CORPUS, AppConfig, Page
from src.paths import page_file, safe_write

USER_AGENT = "hdfc-facts-assistant/0.1 (public pages only; no crawl)"
TIMEOUT_SECONDS = 30.0
MIN_TEXT_CHARS = 200

Getter = Callable[[str], tuple[int, str]]


class FetchError(Exception):
    pass


@dataclass(frozen=True)
class PageResult:
    slug: str
    url: str
    ok: bool
    status: int | None
    error: str | None
    chars: int


def scrape(config: AppConfig, getter: Getter | None = None) -> list[PageResult]:
    """GET each configured page once and save the raw extract. Does not build documents."""
    urls = [page.url for page in config.corpus]
    if urls != list(dict.fromkeys(urls)):
        raise FetchError("corpus contains a duplicate URL")
    unknown = [url for url in urls if url not in ALLOWED_CORPUS]
    if unknown:
        raise FetchError(f"refusing to fetch a URL outside the five pages: {unknown[0]}")

    config.raw_dir.mkdir(parents=True, exist_ok=True)
    if getter is None:
        with httpx.Client(
            follow_redirects=True,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            results = [_save_page(config, page, lambda url: _http_get(client, url)) for page in config.corpus]
    else:
        results = [_save_page(config, page, getter) for page in config.corpus]
    _write_run(config, results)
    return results


def extract_text(html: str, source_url: str) -> str:
    """Turn one page response into fact text. Does not request any URL inside it."""
    payload = _next_data(html)
    page_props = {}
    if isinstance(payload, dict):
        props = payload.get("props")
        if isinstance(props, dict) and isinstance(props.get("pageProps"), dict):
            page_props = props["pageProps"]
    if isinstance(page_props.get("mfServerSideData"), dict):
        return _scheme_text(page_props["mfServerSideData"], source_url)
    if isinstance(page_props.get("amcMainPageData"), list):
        return _amc_text(page_props["amcMainPageData"], source_url)
    return _visible_text(html)


def _http_get(client: httpx.Client, url: str) -> tuple[int, str]:
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        raise FetchError(str(exc)) from exc
    final = _normalize(str(response.url))
    if final != _normalize(url):
        raise FetchError(f"redirected away from the configured page to {final}")
    return response.status_code, response.text


def _save_page(config: AppConfig, page: Page, getter: Getter) -> PageResult:
    fetched_at = _now()
    try:
        status, html = getter(page.url)
    except FetchError as exc:
        _write_raw(config, page, fetched_at, status=None, error=str(exc), text=None)
        return PageResult(page.slug, page.url, False, None, str(exc), 0)
    if status >= 400:
        error = f"HTTP {status}"
        _write_raw(config, page, fetched_at, status=status, error=error, text=None)
        return PageResult(page.slug, page.url, False, status, error, 0)
    text = extract_text(html, page.url).strip()
    if len(text) < MIN_TEXT_CHARS:
        error = "extracted text was empty or too short"
        _write_raw(config, page, fetched_at, status=status, error=error, text=None)
        return PageResult(page.slug, page.url, False, status, error, 0)
    _write_raw(config, page, fetched_at, status=status, error=None, text=text)
    return PageResult(page.slug, page.url, True, status, None, len(text))


def _write_raw(
    config: AppConfig,
    page: Page,
    fetched_at: str,
    status: int | None,
    error: str | None,
    text: str | None,
) -> None:
    body: dict = {
        "slug": page.slug,
        "url": page.url,
        "title": page.title,
        "kind": page.kind,
        "fetched_at": fetched_at,
        "status": status if status is not None else "failed",
        "ok": text is not None,
        "error": error,
    }
    if page.kind == "scheme":
        body["scheme_name"] = page.scheme_name
    else:
        body["amc"] = "HDFC Mutual Fund"
    if text is not None:
        body["hash"] = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        body["text"] = text
    safe_write(page_file(config.raw_dir, page.slug), _dumps(body))


def _write_run(config: AppConfig, results: list[PageResult]) -> None:
    successes = _success_times(config, results)
    previous = _previous_success(config)
    last_success = successes[-1] if successes else previous
    if any(item.ok for item in results):
        overall = "ok" if all(item.ok for item in results) else "partial"
    else:
        overall = "failed"
    payload = {
        "overall": overall,
        "last_successful_scrape": last_success,
        "pages": [
            {
                "slug": item.slug,
                "url": item.url,
                "ok": item.ok,
                "status": item.status,
                "error": item.error,
                "chars": item.chars,
            }
            for item in results
        ],
    }
    safe_write(config.raw_dir / "_run.json", _dumps(payload))


def _previous_success(config: AppConfig) -> str | None:
    path = config.raw_dir / "_run.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = payload.get("last_successful_scrape")
    return value if isinstance(value, str) and value else None


def _scheme_text(data: dict, source_url: str) -> str:
    lines = [f"Source: {source_url}"]
    name = _plain(data.get("scheme_name"))
    if name:
        lines.append(name)
    for label, key in (
        ("Fund house", "fund_house"),
        ("Category", "category"),
        ("Sub-category", "sub_category"),
        ("Plan", "plan_type"),
        ("Option", "scheme_type"),
        ("Expense ratio", "expense_ratio"),
        ("Base expense ratio", "base_expense_ratio"),
        ("Exit load", "exit_load"),
        ("Minimum SIP (INR)", "min_sip_investment"),
        ("Minimum investment (INR)", "min_investment_amount"),
        ("Additional minimum investment (INR)", "mini_additional_investment"),
        ("Riskometer", "nfo_risk"),
        ("Benchmark", "benchmark"),
        ("Benchmark name", "benchmark_name"),
        ("Launch date", "launch_date"),
        ("Allotment date", "allotment_date"),
        ("Fund manager", "fund_manager"),
        ("AUM (Cr)", "aum"),
        ("Stamp duty", "stamp_duty"),
        ("SIP allowed", "sip_allowed"),
        ("Lumpsum allowed", "lumpsum_allowed"),
        ("Description", "description"),
    ):
        rendered = _field(data.get(key))
        if rendered:
            lines.append(f"{label}: {rendered}")
    lock_in = _lock_in(data.get("lock_in"))
    if lock_in:
        lines.append(f"Lock-in: {lock_in}")
    history = _exit_history(data.get("historic_exit_loads"))
    if history:
        lines.append("Exit load history:")
        lines.extend(history)
    managers = _managers(data.get("fund_manager_details"))
    if managers:
        lines.append("Fund managers:")
        lines.extend(managers)
    category = _category_notes(data.get("category_info"))
    if category:
        lines.append("Category notes:")
        lines.append(category)
    return "\n".join(lines).strip()


def _amc_text(blocks: list, source_url: str) -> str:
    lines = [f"Source: {source_url}", "HDFC Mutual Fund"]
    for block in blocks:
        if not isinstance(block, dict):
            continue
        info = block.get("key_information")
        if isinstance(info, dict):
            for label, key in (
                ("Fund house", "fund_house"),
                ("Asset management company", "asset_management_company"),
                ("Incorporation date", "amc_incorporation_date"),
                ("Sponsor", "sponsor_name"),
                ("Trustee organisation", "trustee_organisation"),
                ("Trustees", "name_of_trustee"),
                ("Managing director", "md"),
                ("Chief executive officer", "ceo"),
                ("Chief investment officer", "cio"),
                ("Total AUM (Cr)", "total_aum"),
                ("Address", "address"),
            ):
                rendered = _field(info.get(key))
                if rendered:
                    lines.append(f"{label}: {rendered}")
        for key in ("contentList", "content_list"):
            prose = _prose_blocks(block.get(key))
            if prose:
                lines.append(prose)
    return "\n".join(lines).strip()


def _prose_blocks(value: object) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = _plain(item.get("title"))
        content = _plain(item.get("content"))
        if title and content:
            parts.append(f"{title}\n{content}")
        elif content:
            parts.append(content)
    return "\n\n".join(parts)


def _category_notes(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    for key in ("definition", "description", "tax_impact"):
        text = _plain(value.get(key))
        if text:
            parts.append(f"{key.replace('_', ' ').capitalize()}: {text}")
    return "\n".join(parts)


def _managers(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = _plain(item)
            if text:
                lines.append(f"- {text}")
            continue
        if not isinstance(item, dict):
            continue
        bits: list[str] = []
        for key in ("name", "person_name", "fund_manager", "designation", "experience", "tenure"):
            text = _plain(item.get(key))
            if text and "http" not in text:
                bits.append(text)
        if bits:
            lines.append("- " + " — ".join(bits))
    return lines


def _exit_history(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value[:8]:
        if isinstance(item, str):
            text = _plain(item)
        elif isinstance(item, dict):
            bits = []
            for key, raw in item.items():
                if "url" in key.lower() or "link" in key.lower():
                    continue
                text_bit = _plain(raw)
                if text_bit and "http://" not in text_bit and "https://" not in text_bit:
                    bits.append(f"{key}: {text_bit}")
            text = "; ".join(bits)
        else:
            text = ""
        if text:
            lines.append(f"- {text}")
    return lines


def _lock_in(value: object) -> str:
    if not isinstance(value, dict):
        return _field(value)
    years = _int(value.get("years"))
    months = _int(value.get("months"))
    days = _int(value.get("days"))
    if years == months == days == 0:
        return "None"
    parts: list[str] = []
    if years:
        parts.append(f"{years} year" if years == 1 else f"{years} years")
    if months:
        parts.append(f"{months} month" if months == 1 else f"{months} months")
    if days:
        parts.append(f"{days} day" if days == 1 else f"{days} days")
    return ", ".join(parts)


def _field(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return _plain(value)
    if isinstance(value, list):
        parts = [_field(item) for item in value]
        return "; ".join(part for part in parts if part)
    return ""


def _plain(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return " ".join(text.split())


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def _next_data(html: str) -> dict | None:
    marker = html.find("__NEXT_DATA__")
    if marker < 0:
        return None
    start = html.find(">", marker)
    end = html.find("</script>", start)
    if start < 0 or end < 0:
        return None
    try:
        payload = json.loads(html[start + 1 : end])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# PageResult needs fetched_at only while writing the run file. Keep the timestamp on the raw JSON.
def _success_times(config: AppConfig, results: list[PageResult]) -> list[str]:
    times: list[str] = []
    for item in results:
        if not item.ok:
            continue
        raw = json.loads(page_file(config.raw_dir, item.slug).read_text(encoding="utf-8"))
        fetched_at = raw.get("fetched_at")
        if isinstance(fetched_at, str):
            times.append(fetched_at)
    return times
