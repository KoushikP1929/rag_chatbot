"""Local web UI: one page over the same ask() path the CLI uses.

UI design source of truth: `stitch_hdfc_fund_facts_assistant/`
(see `architecture.md` §9). The template below is the canonical Stitch
desktop screen (`hdfc_fund_facts_assistant`) ported to real `/ask` data
with the design tokens from `clear_trustworthy_fintech/DESIGN.md` inlined.
"""

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


def _friendly_error(message: str) -> str:
    """Never surface transport internals (errno strings, URLError text) in the UI."""
    lowered = message.lower()
    if "errno 16" in lowered or "urlopen error" in lowered or "connect" in lowered:
        return "The assistant could not reach the fact service just now. Please try again in a few seconds."
    return message


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
        return {"error": _friendly_error(str(exc))}
    except Exception as exc:  # noqa: BLE001 - the UI never shows a stack trace
        # TEMP DIAGNOSTIC: surfaced for the serverless rollout; revert to the
        # plain message once the deployment issue is identified.
        import traceback

        traceback.print_exc()
        return {"error_type": type(exc).__name__, "error": _friendly_error(str(exc))}
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


@app.get("/net-probe")
def net_probe() -> dict:
    """TEMP: outbound reachability matrix from this sandbox."""
    import urllib.error
    import urllib.request

    results = {}
    for name, url in (
        ("hf-hub-api", "https://huggingface.co/api/models/all-MiniLM-L6-v2"),
        ("hf-cdn-lfs", "https://cdn-lfs.huggingface.co/"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/models"),
        ("groq", "https://api.groq.com/openai/v1/models"),
    ):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "rag-bot-net-probe/1.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                results[name] = {"status": response.status}
        except urllib.error.HTTPError as error:
            results[name] = {"status": error.code, "note": "connected OK, got HTTP error"}
        except Exception as error:
            results[name] = {"status": "fail", "error_type": type(error).__name__, "error": str(error)}
    return {"results": results}


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
<title>HDFC Fund Facts Assistant</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  /* Design tokens: stitch_hdfc_fund_facts_assistant/clear_trustworthy_fintech/DESIGN.md */
  :root {
    --surface: #F6F7F9;          /* canvas base (Level 0) */
    --surface-card: #FFFFFF;     /* cards, inputs (Level 1) */
    --border: #E6E8EC;           /* structural partition */
    --ink: #44475B;              /* primary text (dark slate) */
    --ink-2: #6E7485;            /* secondary text */
    --primary: #00B386;          /* Groww green: CTAs, links, focus */
    --primary-hover: #00A37A;
    --primary-tint: rgba(0, 179, 134, 0.08);
    --alert: #EB5350;            /* refusal accent only */
    --radius-card: 12px;
    --radius-pill: 9999px;
    --shadow-l1: 0 1px 3px 0 rgba(68, 71, 91, .04), 0 1px 2px -1px rgba(68, 71, 91, .04);
    --shadow-l2: 0 4px 12px 0 rgba(68, 71, 91, .08);
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: var(--surface);
    color: var(--ink);
    font-family: Inter, "Segoe UI", system-ui, -apple-system, sans-serif;
    font-size: 14px; line-height: 22px; /* body-md */
    min-height: 100vh;
    display: flex; flex-direction: column;
  }
  a { color: var(--primary); text-decoration: none; }
  a:hover { color: var(--primary-hover); }
  button, input { font-family: inherit; }

  /* ---- Top bar (Stitch: sticky white header) ---- */
  .topbar {
    position: sticky; top: 0; z-index: 40;
    background: rgba(255, 255, 255, .95);
    border-bottom: 1px solid var(--border);
    backdrop-filter: blur(8px);
  }
  .topbar-in {
    max-width: 1080px; margin: 0 auto; padding: 0 24px;
    height: 56px; display: flex; align-items: center; justify-content: space-between;
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .brand-mark {
    width: 26px; height: 26px; border-radius: 8px; background: var(--primary);
    color: #fff; display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 600;
  }
  .brand-title { font-size: 15px; font-weight: 600; letter-spacing: -.01em; }
  .brand-sub { font-size: 11px; font-weight: 600; color: var(--ink-2);
    letter-spacing: .04em; text-transform: uppercase; }
  .index-badge { display: flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 600; letter-spacing: .04em;
    color: var(--ink-2); background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-pill); padding: 4px 12px; }
  .index-badge .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--primary); }

  /* ---- Conversation shell ---- */
  .shell { width: 100%; max-width: 768px; margin: 0 auto; padding: 24px 20px 8px; flex: 1; }
  .ghost { overflow: hidden; clip: rect(0 0 0 0); height: 0; width: 0; }
  .session-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
  .session-label { display: flex; align-items: center; gap: 8px;
    font-size: 11px; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; color: var(--ink-2); }
  .pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--primary);
    animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
  .sync-label { display: flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 600; letter-spacing: .04em; color: var(--ink-2); }
  .sync-label svg { color: var(--primary); }

  .stream { display: flex; flex-direction: column; gap: 24px; margin-bottom: 24px; }
  .turn { display: flex; flex-direction: column; gap: 12px; }
  .q-row { display: flex; justify-content: flex-end; }
  .q-bubble {
    background: var(--surface-card); color: var(--ink);
    max-width: 560px; border: 1px solid var(--border);
    border-radius: 16px 4px 16px 16px; padding: 10px 18px;
    box-shadow: var(--shadow-l1); overflow-wrap: anywhere;
  }

  /* ---- Assistant answer card (Stitch: Fact & Response Card) ---- */
  .acard-wrap { display: flex; justify-content: flex-start; }
  .acard {
    position: relative; overflow: hidden;
    background: var(--surface-card); border: 1px solid var(--border);
    border-radius: var(--radius-card); padding: 20px;
    box-shadow: var(--shadow-l1); max-width: 100%;
    display: flex; flex-direction: column; gap: 12px;
  }
  .acard.rail-red::before {
    content: ""; position: absolute; left: 0; top: 0; bottom: 0;
    width: 4px; background: var(--alert); /* Advisory refusal mandate */
  }
  .acard.rail-neutral::before {
    content: ""; position: absolute; left: 0; top: 0; bottom: 0;
    width: 4px; background: var(--border);
  }
  .acard-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .acard-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500; }
  .acard-title .mini {
    width: 20px; height: 20px; border-radius: 50%;
    background: var(--primary-tint); color: var(--primary);
    display: flex; align-items: center; justify-content: center; flex: none;
  }
  .acard.refused .acard-title .mini { background: rgba(235, 83, 80, .08); color: var(--alert); }
  .pill { font-size: 11px; font-weight: 600; letter-spacing: .04em;
    border-radius: var(--radius-pill); padding: 2px 10px; white-space: nowrap; }
  .pill.ok { color: var(--primary); background: var(--primary-tint); }
  .pill.warn { color: var(--alert); background: rgba(235, 83, 80, .07); }
  .pill.muted { color: var(--ink-2); background: var(--surface); border: 1px solid var(--border); }
  .answer { margin: 0; color: var(--ink); overflow-wrap: anywhere; }
  .answer .disclaimer-inline { color: var(--ink-2); }

  /* ---- Source citation chip (Stitch: source chip + open_in_new) ---- */
  .chip-row { display: flex; flex-wrap: wrap; gap: 8px; }
  .cite-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--surface-card); border: 1px solid var(--border);
    border-radius: 8px; padding: 6px 12px;
    color: var(--ink-2); font-size: 13px; font-weight: 500;
    transition: color .15s, border-color .15s, box-shadow .15s;
    overflow-wrap: anywhere;
  }
  .cite-chip:hover {
    color: var(--primary); border-color: var(--primary);
    box-shadow: var(--shadow-l2);
  }
  .cite-chip svg { flex: none; }

  /* ---- Trace panel (per PRD §9) ---- */
  .trace { border-top: 1px solid var(--border); padding-top: 10px; font-size: 12px; }
  .trace summary { cursor: pointer; color: var(--ink-2); font-weight: 500; }
  .trace summary:hover { color: var(--primary); }
  .trace table { border-collapse: collapse; width: 100%; margin-top: 8px; }
  .trace th { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
    color: var(--ink-2); background: var(--surface); text-align: left;
    padding: 6px 8px; border-bottom: 1px solid var(--border); }
  .trace td { padding: 6px 8px; border-bottom: 1px solid var(--border);
    color: var(--ink); font-feature-settings: "tnum" 1; overflow-wrap: anywhere; }

  .meta-row { display: flex; align-items: center; justify-content: space-between;
    gap: 8px; padding-top: 10px; border-top: 1px solid var(--border);
    font-size: 12px; color: var(--ink-2); }
  .meta-row .id { font-size: 11px; font-weight: 600; color: var(--ink-2);
    font-feature-settings: "tnum" 1; }

  /* ---- Error card ---- */
  .ecard { border: 1px solid rgba(195, 26, 26, .25); background: #fff;
    border-radius: var(--radius-card); padding: 14px 18px; color: #93000A; }

  /* ---- Thinking placeholder ---- */
  .thinking { display: flex; align-items: center; gap: 10px; color: var(--ink-2); padding: 4px 0 4px 6px; }
  .thinking .pulse { width: 6px; height: 6px; }

  /* ---- Suggested question chips (Stitch: quick suggestion cards) ---- */
  .suggest { margin-bottom: 16px; }
  .suggest-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .suggest-label { font-size: 11px; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; color: var(--ink-2); }
  .suggest-note { font-size: 11px; color: var(--ink-2); }
  .suggest-grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
  @media (min-width: 720px) { .suggest-grid { grid-template-columns: repeat(3, 1fr); } }
  .sugg-btn {
    text-align: left; background: var(--surface-card); border: 1px solid var(--border);
    border-radius: var(--radius-card); padding: 14px; cursor: pointer;
    box-shadow: var(--shadow-l1); display: flex; flex-direction: column; gap: 8px;
    transition: background .15s, border-color .15s, box-shadow .15s;
  }
  .sugg-btn:hover { background: var(--surface); box-shadow: var(--shadow-l2);
    border-color: var(--primary); }
  .sugg-btn .q { color: var(--ink); font-weight: 500; }
  .sugg-btn:hover .q { color: var(--primary); }
  .sugg-btn .go { display: flex; align-items: center; gap: 4px;
    font-size: 11px; font-weight: 500; color: var(--ink-2); }
  .sugg-btn:hover .go { color: var(--primary); }

  .disclaimer-line {
    text-align: center; padding: 6px 0 18px;
    font-size: 11px; font-weight: 600; letter-spacing: .08em;
    text-transform: uppercase; color: var(--ink-2);
  }

  /* ---- Sticky input bar (Stitch: prompt pill + green send) ---- */
  .inputbar {
    position: sticky; bottom: 0; z-index: 40;
    background: rgba(246, 247, 249, .92); backdrop-filter: blur(8px);
    padding: 12px 20px 24px;
  }
  .input-pill {
    max-width: 728px; margin: 0 auto;
    display: flex; align-items: center; gap: 12px;
    background: var(--surface-card); border: 1px solid var(--border);
    border-radius: var(--radius-pill); padding: 8px 8px 8px 18px;
    box-shadow: var(--shadow-l2);
    transition: border-color .15s, box-shadow .15s;
  }
  .input-pill:focus-within { border-color: var(--primary);
    box-shadow: 0 0 0 2px rgba(0, 179, 134, .15); }
  .input-pill svg { color: var(--ink-2); flex: none; }
  .input-pill input {
    flex: 1; border: 0; outline: none; background: transparent;
    color: var(--ink); font-size: 14px; padding: 6px 0; min-width: 0;
  }
  .input-pill input::placeholder { color: var(--ink-2); }
  .send-btn {
    width: 40px; height: 40px; border-radius: 50%;
    background: var(--primary); color: #fff; border: 0; cursor: pointer;
    display: flex; align-items: center; justify-content: center; flex: none;
    transition: background .15s, opacity .15s;
  }
  .send-btn:hover { background: var(--primary-hover); }
  .send-btn:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
  .send-btn[disabled] { opacity: .5; cursor: default; }

  /* ---- Footer (Stitch: slim product footer) ---- */
  .page-footer {
    background: var(--surface-card); border-top: 1px solid var(--border);
    font-size: 12px; color: var(--ink-2);
  }
  .page-footer .in {
    max-width: 1080px; margin: 0 auto; padding: 14px 24px;
    display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center;
    justify-content: space-between;
  }
</style>
</head>
<body>
<svg class="ghost" xmlns="http://www.w3.org/2000/svg">
  <symbol id="i-arrow-up" viewBox="0 0 24 24"><path fill="currentColor" d="M12 5l-7 7 1.4 1.4L11 8.8V19h2V8.8l4.6 4.6L19 12z"/></symbol>
  <symbol id="i-search" viewBox="0 0 24 24"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 4.99L20.49 19zm-6 0A4.5 4.5 0 1 1 14 9.5A4.5 4.5 0 0 1 9.5 14"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path fill="currentColor" d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></symbol>
  <symbol id="i-open" viewBox="0 0 24 24"><path fill="currentColor" d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3z"/></symbol>
  <symbol id="i-info" viewBox="0 0 24 24"><path fill="currentColor" d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9a10 10 0 1 0 0 20a10 10 0 0 0 0-20"/></symbol>
  <symbol id="i-arrow-right" viewBox="0 0 24 24"><path fill="currentColor" d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"/></symbol>
</svg>

<header class="topbar">
  <div class="topbar-in">
    <div class="brand">
      <span class="brand-mark">H</span>
      <span>
        <span class="brand-title">HDFC Fund Facts Assistant</span><br>
        <span class="brand-sub">Groww pages only</span>
      </span>
    </div>
    <span class="index-badge"><span class="dot"></span><span id="index-badge-text">Index loading…</span></span>
  </div>
</header>

<main class="shell">
  <div class="session-row">
    <span class="session-label"><span class="pulse"></span>HDFC AMC facts session</span>
    <span class="sync-label"><svg width="14" height="14"><use href="#i-check"/></svg><span id="sync-text">Sources synced</span></span>
  </div>

  <div class="stream" id="chat-stream" aria-live="polite">
    <!-- Welcome turn (scope note, from PRD §9) -->
    <div class="turn">
      <div class="acard-wrap">
        <article class="acard rail-neutral">
          <div class="acard-head">
            <span class="acard-title">
              <span class="mini"><svg width="12" height="12"><use href="#i-info"/></svg></span>
              What this assistant covers
            </span>
            <span class="pill muted">Scope</span>
          </div>
          <p class="answer">Answers come from five indexed Groww pages: the HDFC AMC overview and four direct
            plans — Large Cap, Flexi Cap, ELSS Tax Saver, and Mid Cap. Every answer cites one of those
            pages. <span class="disclaimer-inline">Facts-only. No investment advice.</span></p>
        </article>
      </div>
    </div>
  </div>

  <section class="suggest" aria-label="Suggested questions">
    <div class="suggest-row">
      <span class="suggest-label">Explore key fund facts</span>
      <span class="suggest-note">Click a prompt to ask it</span>
    </div>
    <div class="suggest-grid">
      <button class="sugg-btn" type="button" data-q="What is the expense ratio of HDFC Large Cap Fund?">
        <span class="q">What is the expense ratio of HDFC Large Cap Fund?</span>
        <span class="go">Scheme fact <svg width="12" height="12"><use href="#i-arrow-right"/></svg></span>
      </button>
      <button class="sugg-btn" type="button" data-q="What is the lock-in period for HDFC ELSS Tax Saver Fund?">
        <span class="q">What is the lock-in period for HDFC ELSS Tax Saver Fund?</span>
        <span class="go">ELSS lock-in <svg width="12" height="12"><use href="#i-arrow-right"/></svg></span>
      </button>
      <button class="sugg-btn" type="button" data-q="Should I buy HDFC Mid Cap Fund?">
        <span class="q">Should I buy HDFC Mid Cap Fund?</span>
        <span class="go">Refusal case <svg width="12" height="12"><use href="#i-arrow-right"/></svg></span>
      </button>
    </div>
  </section>

  <div class="disclaimer-line" id="disclaimer">Facts-only. No investment advice.</div>
</main>

<div class="inputbar">
  <form class="input-pill" id="ask-form">
    <svg width="20" height="20"><use href="#i-search"/></svg>
    <input id="question" type="text" autocomplete="off" autofocus
           placeholder="Ask about expense ratio, exit load, minimum SIP, lock-in, riskometer…">
    <button class="send-btn" id="submit" type="submit" aria-label="Send query">
      <svg width="20" height="20"><use href="#i-arrow-up"/></svg>
    </button>
  </form>
</div>

<footer class="page-footer">
  <div class="in">
    <span><b style="color: var(--ink); font-weight: 600;">HDFC Fund Facts Assistant</b> — facts-only chat over five Groww pages</span>
    <span id="footer-last-updated"></span>
  </div>
</footer>

<script>
const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const submit = document.getElementById("submit");
const stream = document.getElementById("chat-stream");

const svg = (id, size) => {
  const span = document.createElement("span");
  span.innerHTML = '<svg width="' + size + '" height="' + size + '"><use href="#' + id + '"/></svg>';
  return span.firstChild;
};

const MODE_STYLES = {
  fact: { rail: "", title: "Answer from indexed pages",
          icon: "i-info", iconColor: "primary", pill: ["ok", "Fact"] },
  advice: { rail: "rail-red", title: "Advisory query detected",
            icon: "i-info", iconColor: "alert", pill: ["warn", "No advice"] },
  returns: { rail: "rail-red", title: "Returns are not provided",
             icon: "i-info", iconColor: "alert", pill: ["warn", "No numbers"] },
  out_of_scope: { rail: "rail-neutral", title: "Outside the indexed pages",
                  icon: "i-info", iconColor: "primary", pill: ["muted", "Browse"] },
};

function sourceLabel(url) {
  try {
    const u = new URL(url);
    const seg = u.pathname.split("/").filter(Boolean).pop() || "";
    return u.hostname + " — " + seg.replace(/-/g, " ");
  } catch { return url; }
}

function addTurn() {
  const turn = document.createElement("div");
  turn.className = "turn";
  stream.appendChild(turn);
  return turn;
}

function addUserBubble(turn, text) {
  const row = document.createElement("div");
  row.className = "q-row";
  const bubble = document.createElement("div");
  bubble.className = "q-bubble";
  bubble.textContent = text;
  row.appendChild(bubble);
  turn.appendChild(row);
}

function addRefusalCard(turn, payload) {
  const style = MODE_STYLES[payload.mode] || MODE_STYLES.out_of_scope;
  const wrap = document.createElement("div");
  wrap.className = "acard-wrap";
  const card = document.createElement("article");
  card.className = "acard " + (style.rail || "");

  const head = document.createElement("div");
  head.className = "acard-head";
  const title = document.createElement("span");
  title.className = "acard-title";
  const mini = document.createElement("span");
  mini.className = "mini";
  mini.appendChild(svg(style.icon, 12));
  title.appendChild(mini);
  title.appendChild(document.createTextNode(style.title));
  const pill = document.createElement("span");
  pill.className = "pill " + style.pill[0];
  pill.textContent = style.pill[1];
  head.appendChild(title); head.appendChild(pill);
  card.appendChild(head);

  const body = document.createElement("p");
  body.className = "answer";
  body.textContent = payload.answer + " " + (payload.disclaimer || "");
  card.appendChild(body);

  if (payload.citation) {
    const chipRow = document.createElement("div");
    chipRow.className = "chip-row";
    const chip = document.createElement("a");
    chip.className = "cite-chip";
    chip.href = payload.citation;
    chip.target = "_blank";
    chip.rel = "noopener noreferrer";
    chip.appendChild(svg("i-open", 15));
    chip.appendChild(document.createTextNode("Source: " + sourceLabel(payload.citation)));
    chipRow.appendChild(chip);
    card.appendChild(chipRow);
  }

  const meta = document.createElement("div");
  meta.className = "meta-row";
  const left = document.createElement("span");
  left.textContent = "Last updated from sources: " + (payload.last_updated || "—");
  const right = document.createElement("span");
  right.className = "id";
  right.textContent = "Ref: " + payload.query_id;
  meta.appendChild(left); meta.appendChild(right);
  card.appendChild(meta);

  wrap.appendChild(card);
  turn.appendChild(wrap);
}

function scrollDown() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function ask(question) {
  const q = (question || input.value).trim();
  if (!q) return;

  const turn = addTurn();
  addUserBubble(turn, q);
  input.value = "";
  submit.disabled = true;

  const thinking = document.createElement("div");
  thinking.className = "thinking";
  const dot = document.createElement("span");
  dot.className = "pulse";
  thinking.appendChild(dot);
  thinking.appendChild(document.createTextNode("Retrieving from the five indexed pages…"));
  turn.appendChild(thinking);
  scrollDown();

  fetch("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: q })
  }).then(async (response) => {
    turn.removeChild(thinking);
    const payload = await response.json();

    if (payload.error) {
      const wrap = document.createElement("div");
      wrap.className = "acard-wrap";
      const card = document.createElement("div");
      card.className = "ecard";
      card.textContent = payload.error;
      wrap.appendChild(card);
      turn.appendChild(wrap);
      scrollDown();
      return;
    }

    addRefusalCard(turn, payload);
    scrollDown();
  }).catch(() => {
    if (thinking.parentNode) thinking.parentNode.removeChild(thinking);
    const err = document.createElement("div");
    err.className = "ecard";
    err.textContent = "The assistant is unreachable. Is uvicorn running?";
    turn.appendChild(err);
  }).finally(() => {
    submit.disabled = false;
    input.focus();
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask();
});

document.querySelectorAll(".sugg-btn").forEach((button) =>
  button.addEventListener("click", () => ask(button.dataset.q)));

// Index badge from /health (chunk count + last scrape date).
fetch("/health").then((r) => r.json()).then((h) => {
  if (h && typeof h.indexed_chunks === "number") {
    document.getElementById("index-badge-text").textContent =
      h.indexed_chunks > 0
        ? "Index: " + h.indexed_chunks + " chunks · " + h.corpus.length + " pages"
        : "Index warming up — ask a question to build it";
  } else {
    document.getElementById("index-badge-text").textContent = "Index not built — run src.cli index";
  }
  if (h && h.last_updated) {
    document.getElementById("sync-text").textContent = "Last updated: " + h.last_updated;
    document.getElementById("footer-last-updated").textContent =
      "Last updated from sources: " + h.last_updated;
  }
}).catch(() => {
  document.getElementById("index-badge-text").textContent = "Index status unknown";
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
