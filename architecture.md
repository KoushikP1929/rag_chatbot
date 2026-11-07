# Architecture: HDFC Mutual Fund Facts Assistant

**Status:** Draft
**Date:** 6 November 2026
**Source:** `prd.md`

## 1. Purpose

This document describes how the RAG demo in `prd.md` is built: the components, the data that flows between them, the on-disk artifacts, the configuration surface, and the rules that keep answers facts-only and grounded in the five Groww pages.

Design principles carried straight from the PRD:

1. **The pipeline is the product.** Fetch → load documents → chunk → embed → index → retrieve → generate, with every stage writing inspectable files to disk.
2. **Retrieval decides the truth.** The LLM receives only retrieved chunk text. Citations come from chunk metadata, never from the model.
3. **Stages are independently runnable.** Each stage reads the previous stage's artifacts and writes its own directory; a later stage can be re-run without repeating earlier ones.
4. **Configuration over code.** Embedding model, vector store settings, LLM provider, and model id are config/env values.
5. **No personal data, no advice, no performance claims.** Enforced in the input guard, the prompt, and the output formatter.

## 2. System Context

```
                 ┌──────────────────────────────┐
                 │  Local operator (CLI)         │
                 │  run fetch/load/chunk/embed/index │
                 └──────────────┬───────────────┘
                                │
                 ┌──────────────▼───────────────┐
   Groww pages → │  Ingestion pipeline           │ → data/raw, data/documents,
   (5 URLs)      │  fetch → load → chunk →       │   data/chunks, data/embeddings,
                 │  embed → index                │   data/chroma
                 └──────────────────────────────┘
                                │
                 ┌──────────────▼───────────────┐
                 │  Query service                │
                 │  guard → retrieve → answer    │ → data/traces
                 └──────────────┬───────────────┘
                                │
                 ┌──────────────▼───────────────┐
                 │  Local web UI (single page)   │
                 └──────────────────────────────┘
```

Everything runs locally. The only outbound calls are the five HTTP fetches at ingestion time and the LLM API at query time. No database server is needed beyond the embedded Chroma persistence.

## 3. Technology Choices

| Concern | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.11+ | Matches the embedding/Chroma ecosystem |
| HTTP fetch | `httpx` (or `requests`) | Plain GET with timeout and User-Agent |
| HTML→text extraction | `trafilatura` with a `BeautifulSoup`/`lxml` fallback | Keep raw HTML alongside extracted text |
| Text processing | Heading/label-aware parser | See chunking strategy |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2` default) | Model id from config |
| Vector store | ChromaDB, `PersistentClient` | Local path from config |
| LLM access | Thin provider adapter interface | Groq default; Gemini, OpenAI, Anthropic, Mistral allowed |
| Config | YAML (or JSON) + `.env` via `python-dotenv` | Secrets only in `.env` |
| Web UI | Small server-rendered or lightweight local app (FastAPI + single HTML page) | One page per PRD §9 |
| Testing | `pytest` | Unit tests for guard, chunker, citation selection, provider switch |

Provider access is behind one interface so a provider/model change is a config edit, not a code edit:

```python
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...
```

A factory maps `llm.provider` + `LLM_MODEL` to the concrete client and raises a clear startup error for an unknown provider or missing key.

## 4. Repository Layout

```
rag_bot/
├── architecture.md
├── prd.md
├── README.md
├── config.yaml
├── .env.example
├── src/
│   ├── config.py            # load + validate config and env
│   ├── paths.py             # artifact paths, slugs
│   ├── fetch.py             # §7.1 scrape raw pages
│   ├── documents.py         # §7.2 load one document per page
│   ├── chunk.py             # §7.3 chunking
│   ├── embed.py             # §7.4 embeddings
│   ├── index.py             # §7.5 Chroma upsert
│   ├── retrieve.py          # §7.6 query + trace
│   ├── answer.py            # prompt assembly, refusal, citation, formatting
│   ├── guard.py             # PII + advice/returns detection
│   ├── llm/                 # provider adapters + factory
│   ├── cli.py               # stage commands
│   └── app.py               # local web UI / API
├── data/
│   ├── raw/<slug>.json
│   ├── documents/<slug>.json
│   ├── chunks/<slug>.json
│   ├── embeddings/<slug>.json
│   ├── chroma/
│   └── traces/<query-id>.json
├── doc/
│   └── sources.md
└── tests/
```

`data/` is disposable and regenerable; it is git-ignored except for a `.gitkeep`. `doc/sources.md` and the sample Q&A are committed deliverables.

## 5. Configuration Model

### 5.1 `config.yaml` (non-secret)

```yaml
corpus:
  - slug: amc-hdfc-mutual-funds
    title: HDFC Mutual Fund — AMC overview
    url: https://groww.in/mutual-funds/amc/hdfc-mutual-funds
    kind: amc
  - slug: hdfc-large-cap-fund-direct-growth
    title: HDFC Large Cap Fund — Direct Growth
    url: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth
    kind: scheme
    scheme_name: HDFC Large Cap Fund — Direct Growth
  # flexi cap, ELSS, mid cap follow the same shape

embedding:
  model: sentence-transformers/all-MiniLM-L6-v2

vectorstore:
  engine: chroma
  persist_path: data/chroma
  collection: hdfc_facts

llm:
  provider: groq            # groq | gemini | openai | anthropic | mistral

retrieval:
  top_k: 5

artifacts:
  raw_dir: data/raw
  document_dir: data/documents
  chunk_dir: data/chunks
  embedding_dir: data/embeddings
  trace_dir: data/traces

ui:
  disclaimer: "Facts-only. No investment advice."
```

### 5.2 `.env` (secrets and the model id)

```dotenv
GROQ_API_KEY=...
LLM_MODEL=qwen/qwen3.8-27b   # placeholder; verify against provider's model list
```

- `.env` is never committed; `.env.example` carries the keys as placeholders.
- `config.py` validates at startup: every configured corpus URL is one of the five allowed URLs; the provider is in the allowed set; the key for the selected provider exists; `LLM_MODEL` is non-empty.
- The app never hardcodes a model id. Switching `LLM_MODEL` or `llm.provider` is picked up on the next question.

### 5.3 Embedding model consistency guard

The Chroma collection stores the embedding model id in metadata. Query time asserts:

```
collection_metadata["embedding_model"] == config.embedding.model
```

On mismatch, retrieval is **blocked** with an operator-facing message telling them to re-run `embed` and `index`. This directly satisfies PRD §7.4 and §11.

## 6. Pipeline Stages

Each stage is a CLI command (`python -m src.cli fetch|load|chunk|embed|index|ask ...`), is idempotent for a given input, and writes only its own artifact directory.

### 6.1 Fetch (`src/fetch.py`)

**Input:** `config.yaml` corpus list.
**Output:** `data/raw/<slug>.json`.

For each URL:

1. GET with timeout, redirects, and a descriptive User-Agent.
2. Persist `url`, `fetched_at` (UTC ISO-8601), `status`, `hash` (SHA-256 of the extracted text), `text` (extracted main content), and `html` (raw response, or a separate blob reference).
3. On failure, record `status` and error and mark the page failed. **No placeholder text is written.**

Failure semantics: a failed page is reported loudly and excluded from downstream stages. The run does not silently continue with an empty document. `data/raw/_run.json` records per-URL outcome, overall status, and the latest successful fetch timestamp used for the UI's "Last updated from sources" line.

### 6.2 Load documents (`src/documents.py`)

**Input:** `data/raw/<slug>.json`.
**Output:** `data/documents/<slug>.json` and `data/documents/_index.json`.

No network call. One document per successful page:

1. Skip a raw file whose status failed or whose text is empty. Do not write a placeholder document.
2. `page_content` is the extracted text. Metadata: `document_id` (`doc::<slug>`), `slug`, `source_url`, `page_title`, `scheme_name` (or `amc`), `kind`, `fetched_at`, `content_hash`.
3. Overwrite the same slug on re-run. Delete the document file if that raw page is now failed.
4. `_index.json` records the document count, skipped slugs, and `last_successful_scrape` from `data/raw/_run.json`.

### 6.3 Chunk (`src/chunk.py`)

**Input:** `data/documents/<slug>.json`. Chunking does not open `data/raw/`.
**Output:** `data/chunks/<slug>.json`.

Strategy: section-based chunking because the sources are fact sheets.

1. Parse headings and labeled key/value rows.
2. Target sections (per page, as present): expense ratio, exit load, minimum SIP, lock-in, riskometer, benchmark, statement download, peers.
3. One chunk per section: heading + full body. A label is never separated from its value.
4. If a page yields no usable headings, fall back to recursive character splitting with overlap and set `fallback: true` on each affected chunk.
5. Stable chunk id: `<slug>::<chunk_index>::<hash(section + body)[:12]>`. Stability matters for upsert deduplication.
6. Metadata on every chunk: `source_url`, `page_title`, `scheme_name` (or `amc`), `section`, `chunk_index`, `fetched_at`.

### 6.4 Embed (`src/embed.py`)

**Input:** `data/chunks/`.
**Output:** `data/embeddings/<slug>.json`.

- Load the configured sentence-transformers model once, embed each chunk's `heading + body` text, L2-normalized.
- Write `chunk_id`, `vector` (list of floats), `model` (`config.embedding.model`), and the full chunk metadata for each row.
- Refuse to overwrite embeddings produced by a different model id without `--force`, since mixing vectors from two models is invalid.

### 6.5 Index (`src/index.py`)

**Input:** `data/embeddings/`.
**Output:** `data/chroma/`.

- `chromadb.PersistentClient(path=config.vectorstore.persist_path)`.
- `get_or_create_collection(name=..., metadata={"embedding_model": ..., "built_at": ...})`.
- `upsert(ids=chunk_id, embeddings=vector, metadocuments, metadatas=...)` — stable ids mean re-index replaces rows rather than duplicating them.
- Assert or update the collection's embedding-model metadata; refuse mixed-model collections.
- Verify counts after upsert and print a per-slug summary.

### 6.6 Retrieve and answer (`src/retrieve.py`, `src/answer.py`, `src/guard.py`)

Entry point: `ask(question, query_id)`.

Order of operations for every question:

1. **Input guard** (before any LLM or trace write). Detect PAN, Aadhaar, account number, OTP, email, phone. If present: do not call the LLM, do not persist the raw text; return a message asking the user to remove it and resubmit. Trace (if written at all) stores only a redacted flag and no matched value.
2. **Mode decision.** Classify the question as one of: `fact`, `advice`, `returns`, `out_of_scope`. Advice and returns take the refusal path; both still retrieve so a relevant corpus link can be attached.
3. **Embedding consistency check** (collection model vs config).
4. **Embed the question** with the ingestion model and **query** the same Chroma collection.
5. **Retrieve top-k** chunks with scores, section names, source URLs.
6. **Grounding check.** For fact questions, verify a retrieved chunk plausibly covers the requested fact type/scheme; if not, use the "not in corpus" path (state the fact is not in the indexed pages, still cite the most relevant source link). Never fill gaps from model memory.
7. **Generate.**
   - Fact: call the configured LLM with a system prompt containing the answer rules (≤3 sentences, facts only, no advice, no computed returns, use only the provided chunks) and the user message containing the question + numbered chunks.
   - Refusal: a short templated facts-only refusal (≤3 sentences) plus an educational link — the matching scheme page if a scheme was named, else the AMC overview. No investment recommendation.
   - Returns: state that returns are not provided; point to the official factsheet as an external pointer, without calculating or stating a number.
8. **Post-process / validate output.**
   - Enforce ≤3 sentences (truncate at sentence boundary, never mid-sentence).
   - Extract the citation **from the chosen chunk's `source_url`**, not from model text. If the model emitted a URL, discard it.
   - Assert the citation is one of the five corpus URLs.
   - Append `Last updated from sources: <ISO date of last successful scrape>`.
   - Prepend/attach the disclaimer string from config.
9. **Write trace** to `data/traces/<query-id>.json`: question (redacted), mode, retrieved chunks + scores + sections + URLs, prompt sent, raw model output, final answer, citation, timestamps, model/provider/embedding ids.

Malformed or hallucinated model output is handled by the formatter: if it cannot produce a `fact` answer with a valid corpus citation, fall back to a deterministic "I don't have that fact in the indexed pages" response with the best retrieved link. The trace records both the raw and final output.

### 6.7 Orchestration

`python -m src.cli all` runs fetch → load → chunk → embed → index in order and stops on a failed required page. Individual stages are runnable alone and skip upstream work when their inputs already exist (optionally with `--force`). Query time (`ask` / the UI) never re-ingests.

## 7. Answer Contract

| Rule | Implementation |
| --- | --- |
| ≤3 sentences | Post-processing sentence splitter, hard cap |
| Exactly one citation | Attached from `chunk["source_url"]` after generation |
| Citation in corpus | Validated against the config URL allow-list |
| Last-updated line | `Last updated from sources: <ISO date>` from `_run.json` |
| Standing disclaimer | Config string rendered by the UI and appended to answers |
| No advice / no ranking | Mode classifier + prompt rules + post-check for banned recommendation phrases |
| No performance numbers | Returns mode refuses; post-check rejects numeric return patterns in fact answers |
| No model-memory fill | Grounding check; fallback to "not in corpus" |

The same formatter is used by the CLI and the UI, so acceptance checks hold for both.

## 8. Data Model and Artifacts

### Raw — `data/raw/<slug>.json`

```json
{
  "slug": "hdfc-large-cap-fund-direct-growth",
  "url": "https://groww.in/...",
  "title": "HDFC Large Cap Fund — Direct Growth",
  "kind": "scheme",
  "scheme_name": "HDFC Large Cap Fund — Direct Growth",
  "status": 200,
  "fetched_at": "2026-11-06T09:12:44Z",
  "hash": "sha256:…",
  "text": "…extracted main text…"
}
```

### Document — `data/documents/<slug>.json`

```json
{
  "document_id": "doc::hdfc-large-cap-fund-direct-growth",
  "slug": "hdfc-large-cap-fund-direct-growth",
  "source_url": "https://groww.in/...",
  "page_title": "HDFC Large Cap Fund — Direct Growth",
  "kind": "scheme",
  "scheme_name": "HDFC Large Cap Fund — Direct Growth",
  "fetched_at": "2026-11-06T09:12:44Z",
  "content_hash": "sha256:…",
  "page_content": "…extracted main text…"
}
```

### Chunk — `data/chunks/<slug>.json`

```json
{
  "source_url": "https://groww.in/...",
  "page_title": "…",
  "scheme_name": "…",
  "section": "Exit Load",
  "chunk_index": 4,
  "fetched_at": "2026-11-06T09:12:44Z",
  "fallback": false,
  "chunk_id": "hdfc-large-cap-fund-direct-growth::4::a1b2c3d4e5f6",
  "text": "Exit Load\n…value…"
}
```

### Embedding — `data/embeddings/<slug>.json`

```json
{
  "model": "sentence-transformers/all-MiniLM-L6-v2",
  "chunks": [
    { "chunk_id": "…", "vector": [0.013, -0.042, "…"], "metadata": { "…chunk metadata…" } }
  ]
}
```

### Trace — `data/traces/<query-id>.json`

```json
{
  "query_id": "…",
  "timestamp": "2026-11-06T09:30:00Z",
  "question": "What is the exit load on HDFC Large Cap Fund?",
  "mode": "fact",
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "llm": { "provider": "groq", "model": "…" },
  "retrieved": [
    { "chunk_id": "…", "score": 0.81, "section": "Exit Load", "source_url": "https://groww.in/…" }
  ],
  "prompt": { "system": "…", "user": "…" },
  "raw_output": "…",
  "final_answer": "…",
  "citation": "https://groww.in/…",
  "last_updated": "2026-11-06"
}
```

Artifacts are plain JSON and openable without the app, satisfying PRD §11.

## 9. UI Architecture

- FastAPI (or equivalent) serves one HTML page and a `POST /ask` endpoint.
- Page contains: welcome line naming the assistant and covered pages; three clickable example questions (a scheme fact, ELSS lock-in, a refusal case); text input + submit; answer with one citation and the last-updated line; standing disclaimer; optional trace panel for the last question (retrieved sections, scores, citation URL).
- The UI is a thin client over the same `ask()` path the CLI uses; no business logic is duplicated in the browser.
- PII guard runs server-side. On detection the UI shows the removal/resubmit message and no LLM call occurs.
- The trace panel is read from the just-written trace object, so the demo shows the RAG stages without opening `data/`.

## 10. Security, Privacy, and Scope Controls

| Control | Where |
| --- | --- |
| Secrets only in `.env`, not committed | `.env.example` + `.gitignore` |
| PII rejected before LLM and not written to traces | `guard.py`, trace writer |
| Corpus locked to five URLs; links inside pages not followed | `config.py` validation, fetcher does not crawl |
| Citation cannot be model-invented | Citation selection from chunk metadata |
| No advice/returns in output | Mode classifier + prompt + post-checks |
| Provider/model change without code edits | Provider factory + config/env |
| Embedding/collection model parity | Collection metadata check blocks mismatched retrieval |

## 11. Failure Modes and Handling

| Failure | Behavior |
| --- | --- |
| A page fetch fails | Record status/error; mark that page failed; stop a full `all` run (or continue with `--keep-going`), never fabricate text |
| Extraction yields no usable headings | Recursive split with overlap; `fallback: true` recorded on chunks |
| Embedding model changed after ingest | Embed refuses without `--force`; retrieval blocked until re-embed + re-index |
| Collection built with a different model | Retrieval blocked with re-embed instruction |
| Provider key missing / unknown provider | Startup validation error naming the key/config field |
| LLM returns prose with a URL or >3 sentences | Formatter strips model URLs, enforces sentence cap, attaches chunk citation |
| LLM answer not grounded | Fallback to "not in indexed pages" with best retrieved link; both outputs in trace |
| PII in question | No LLM call, no raw persistence, ask to remove and resubmit |
| Chroma path missing/empty | Clear error telling the operator to run `index` |

## 12. Testing Strategy

- **Unit:** PII detection patterns; advice/returns classifier; sentence cap; citation selection and allow-list validation; chunk id stability; config validation (bad URL, bad provider).
- **Stage tests:** one raw page → one document; one document → deterministic chunks; embedding dims and normalization; upsert replaces not duplicates.
- **Integration:** full pipeline on cached fixtures, then a small set of golden questions per fact type plus refusal and not-in-corpus cases; assert ≤3 sentences, exactly one citation, citation ∈ corpus, last-updated line present.
- **Provider switch test:** point the factory at a stub client for each provider name and verify selection from config/env.

## 13. Acceptance Mapping

| PRD acceptance item | Architecture element |
| --- | --- |
| Fact answers with one corpus link + last-updated line | §6.5 steps 6–8, §7 |
| Buy/sell or "which is better" refused, no recommendation | Mode classifier + refusal path + post-check |
| Returns question states no number | Returns mode + numeric-returns post-check |
| Citation matches supporting chunk | Citation from chunk metadata + allow-list |
| All artifact directories exist after a run | Stage outputs in §6, §8 |
| `LLM_MODEL`/provider change applies next question | Provider factory + config/env, §5 |
| Query-time embedding model matches collection | Collection metadata check, §5.3 |

## 14. Deployment and Operations

- Local-only. Setup: create venv, install requirements, copy `.env.example` → `.env`, fill the selected provider key, run `python -m src.cli all`, then start the UI.
- The README documents each phase command, env keys, scope (HDFC AMC + four schemes), and known limits from PRD §12.
- Re-ingestion is the freshness mechanism; the last successful scrape date is surfaced on every answer.
- No user accounts, no chat persistence beyond traces, no production support integration.

## 15. Known Limits (inherited)

- Facts go stale when Groww changes a page; freshness is the last successful scrape.
- Statement-download steps exist only if present on the five pages.
- One AMC and four schemes only; no generalization to other AMCs.
- Chunk quality depends on Groww's markup on the scrape date; `data/chunks/` is the first place to inspect a bad answer.
