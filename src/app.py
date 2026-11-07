"""Local web UI: one page over the same ask() path the CLI uses."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from src.answer import ask as answer_question, last_updated_from
from src.config import AppConfig, load_config, mask_secret
from src.index import verify_index
from src.retrieve import RetrievalError

app = FastAPI(title="HDFC Mutual Fund Facts Assistant")
_state: dict = {"config": None}


def _config() -> AppConfig:
    if _state["config"] is None:
        _state["config"] = load_config()
    return _state["config"]


@app.get("/", response_class=HTMLResponse)
def page() -> HTMLResponse:
    return HTMLResponse(TEMPLATE)


@app.post("/ask")
def ask_route(payload: dict):
    question = (payload or {}).get("question")
    if not isinstance(question, str) or not question.strip():
        return {"error": "Please type a question."}
    try:
        result = answer_question(question.strip(), config=_config())
    except RetrievalError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - the UI never shows a stack trace
        return {"error": str(exc)}
    if result.mode == "pii":
        return JSONResponse(status_code=400, content={"error": result.answer, "mode": "pii"})
    return {
        "answer": result.answer,
        "citation": result.citation,
        "last_updated": result.last_updated,
        "disclaimer": result.disclaimer,
        "mode": result.mode,
        "query_id": result.query_id,
        "trace": result.trace,
    }


@app.get("/health")
def health() -> dict:
    config = _config()
    try:
        store = verify_index(config)
    except Exception:  # noqa: BLE001 - health must not fail when the index is absent
        store = {"count": 0, "embedding_model": None}
    return {
        "corpus": [page.slug for page in config.corpus],
        "embedding_model": config.embedding_model,
        "collection": config.collection,
        "indexed_chunks": store.get("count"),
        "indexed_with": store.get("embedding_model"),
        "provider": config.provider,
        "llm_model": config.llm_model,
        "api_key": mask_secret(config.api_key),
        "last_updated": last_updated_from(config),
    }


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HDFC Mutual Fund Facts Assistant</title>
<style>
  body { font-family: Georgia, serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  h1 { font-size: 1.4rem; } .muted { color: #666; font-size: .9rem; }
  .banner { border-left: 4px solid #b45309; background: #fffbeb; padding: .5rem .75rem; margin: 1rem 0; }
  form { display: flex; gap: .5rem; margin: 1rem 0; }
  input { flex: 1; padding: .6rem; font-size: 1rem; }
  button { padding: .6rem 1.2rem; font-size: 1rem; cursor: pointer; }
  button[disabled] { opacity: .5; cursor: default; }
  .examples button { padding: .25rem .6rem; margin: 0 .3rem .3rem 0; font-size: .85rem; background: #eef; border: 1px solid #99f; }
  .card { border: 1px solid #ccc; border-radius: 6px; padding: 1rem; margin: 1rem 0; }
  .card h2 { font-size: 1rem; margin: 0 0 .5rem; }
  blockquote { border-left: 3px solid #888; margin: .5rem 0; padding-left: .75rem; color: #333; }
  details { margin-top: .75rem; font-size: .85rem; }
  summary { cursor: pointer; color: #036; }
  table { border-collapse: collapse; width: 100%; }
  td, th { border-bottom: 1px solid #ddd; padding: .25rem .4rem; text-align: left; }
  .error { color: #b00; }
  a { color: #036; }
</style>
</head>
<body>
<h1>HDFC Mutual Fund Facts Assistant</h1>
<p class="muted">Answers come from five indexed pages: the HDFC AMC overview on Groww and four direct plans —
Large Cap, Flexi Cap, ELSS Tax Saver, and Mid Cap. Every answer cites one of those pages.</p>
<p class="banner" id="disclaimer">Facts-only. No investment advice.</p>

<div class="examples">
  Example questions:
  <button type="button" data-q="What is the expense ratio of HDFC Large Cap Fund?">Scheme fact</button>
  <button type="button" data-q="What is the lock-in period for HDFC ELSS Tax Saver Fund?">ELSS lock-in</button>
  <button type="button" data-q="Should I buy HDFC Mid Cap Fund?">Refusal case</button>
</div>

<form id="ask-form">
  <input id="question" type="text" placeholder="Ask a fact about one of the five pages" autofocus>
  <button type="submit" id="submit">Ask</button>
</form>

<div id="out" aria-live="polite"></div>

<script>
const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const submit = document.getElementById("submit");
const out = document.getElementById("out");
function renderError(text) {
  out.innerHTML = '<div class="card error">' + text + '</div>';
}
function renderTracePanel(trace) {
  const rows = (trace.retrieved || []).map(item =>
    "<tr><td>" + item.section + "</td><td>" + (item.score !== undefined ? item.score.toFixed(3) : "") +
    "</td><td><a href='" + item.source_url + "'>" + item.source_url + "</a></td></tr>").join("");
  return "<details><summary>Trace for this question (query " + trace.query_id +
    ", mode " + trace.mode + ")</summary><table><tr><th>Retrieved section</th><th>Score</th><th>Source</th></tr>" +
    rows + "</table></details>";
}
async function ask() {
  const question = input.value.trim();
  if (!question) return;
  submit.disabled = true;
  out.innerHTML = '<p class="muted">Looking in the indexed pages…</p>';
  try {
    const response = await fetch("/ask", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: question})
    });
    const payload = await response.json();
    if (payload.error) { renderError(payload.error); return; }
    out.innerHTML =
      '<div class="card"><h2>Answer</h2><p>' + payload.answer + '</p>' +
      (payload.citation ? '<p>Source: <a href="' + payload.citation + '">' + payload.citation + '</a></p>' : '') +
      (payload.last_updated ? '<p class="muted">Last updated from sources: ' + payload.last_updated + '</p>' : '') +
      '<p class="muted">' + payload.disclaimer + '</p></div>' +
      renderTracePanel(payload.trace);
  } catch (err) {
    renderError("The assistant is unreachable. Is uvicorn running?");
  } finally {
    submit.disabled = false;
    input.focus();
  }
}
form.addEventListener("submit", (event) => { event.preventDefault(); ask(); });
document.querySelectorAll(".examples button").forEach((button) =>
  button.addEventListener("click", () => { input.value = button.dataset.q; ask(); }));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
