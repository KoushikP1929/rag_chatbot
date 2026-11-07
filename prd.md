# PRD: HDFC Mutual Fund Facts Assistant

**Status:** Draft  
**Date:** 6 November 2026  
**Source:** `doc/Problem Statement`

## 1. Summary

Build a small retrieval-augmented FAQ assistant that answers factual questions about HDFC Mutual Fund schemes using only five official public Groww pages. Every answer cites one source link. The assistant gives no investment advice, stores no personal data, and does not compute or compare returns.

This is a RAG demo. Each pipeline stage writes its output to disk so a reviewer can inspect raw pages, chunks, embeddings, the vector index, and the retrieval trace for a question.

## 2. Users

| User | Need |
| --- | --- |
| Retail investor comparing schemes | Look up a single fact (expense ratio, exit load, minimum SIP, lock-in, riskometer, benchmark) without reading the full page |
| Support or content team | Answer the same factual questions repeatedly, with a link they can send |

## 3. Goals

1. Answer the supported fact types from the scraped corpus, with one citation on every answer.
2. Refuse opinion, portfolio, and buy/sell questions with a short facts-only message and one educational link.
3. Keep the full RAG path visible: fetch, load documents, chunk, embed, index, retrieve, generate.
4. Make the embedding model, vector store, LLM provider, and model id changeable from config and `.env` without code edits.

## 4. Non-goals

- Investment advice, scheme ranking, portfolio construction, or “should I buy/sell?”.
- Return calculations, trailing-return comparisons, or any performance claim. If asked, point to the official factsheet and do not compute a number.
- Scraping pages other than the five listed below, including links found on those pages.
- Screenshots of any app back-end, or third-party blogs as sources.
- Accepting or storing PAN, Aadhaar, account numbers, OTPs, email addresses, or phone numbers.
- User accounts, chat history persistence, or a production support integration.

## 5. Corpus

Scrape and store only these pages. Do not follow links inside them.

| # | Page | URL |
| --- | --- | --- |
| 1 | AMC overview — HDFC Mutual Fund | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| 2 | Large Cap — HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 3 | Flexi Cap — HDFC Flexi Cap Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 4 | ELSS — HDFC ELSS Tax Saver Fund Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | Mid Cap — HDFC Mid Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

The assignment template asks for a source list of 15–25 URLs. This build uses the five pages above, because the problem statement forbids scraping anything else. The source-list deliverable lists these five URLs and states that limit. Factsheet links, if shown for a returns question, are named as external pointers and are not added to the corpus.

## 6. What the assistant answers

Supported factual intents, each grounded in a retrieved chunk:

- Expense ratio
- Exit load
- Minimum SIP
- Lock-in (ELSS)
- Riskometer
- Benchmark
- How to download a capital-gains or account statement, when that text exists on the scraped pages

If the corpus does not contain the fact, the assistant says it does not have that fact in the indexed pages and still shows the most relevant source link. It does not fill the gap from model memory.

### Refusal

Opinionated or portfolio questions (“Should I buy this?”, “Which fund is better?”, “Is this good for me?”) get:

- A polite refusal in at most three sentences
- A facts-only framing
- One relevant educational link from the corpus (the matching scheme page, or the AMC overview if no scheme is named)

### Answer format

- At most three sentences.
- Exactly one source link, shown as a clear citation.
- A line: `Last updated from sources: <ISO date of the last successful scrape>`.
- UI always shows: `Facts-only. No investment advice.`

## 7. Pipeline

Stages run in order. Each stage reads the previous stage’s files and writes its own directory. Re-running a stage from a given point does not require repeating earlier stages if their outputs are still present.

### 7.1 Fetch

- Fetch the five URLs over HTTP.
- Store the raw response and the extracted main text for each page.
- Record `url`, `fetched_at`, HTTP status, and a content hash.
- Fail that page visibly if the fetch fails. Do not invent page text.

**Artifact:** `data/raw/<slug>.json` (url, fetched_at, status, hash, text).

### 7.2 Load documents

- Read the raw files from 7.1. Do not fetch again.
- Emit one document per successful page. `page_content` is the extracted text. Metadata carries the URL, title, scheme or AMC name, fetch time, and content hash.
- Skip a failed or empty page. Do not write a placeholder document.

**Artifact:** `data/documents/<slug>.json`.

### 7.3 Chunking

Pages are fact sheets, so chunks follow sections rather than a fixed token window that can split a label from its value.

- Detect headings and labeled rows (expense ratio, exit load, minimum SIP, lock-in, riskometer, benchmark, and peer sections on the same page).
- One chunk per section. A chunk includes the section heading and its full body.
- If a page has no usable headings, fall back to recursive character splitting with overlap, and record that fallback on the chunk.
- Every chunk carries metadata: `source_url`, `page_title`, `scheme_name` (or `amc` for the overview), `section`, `chunk_index`, `fetched_at`.

**Artifact:** `data/chunks/<slug>.json`.

### 7.4 Embedding

- Model: `sentence-transformers/all-MiniLM-L6-v2`.
- The model id is read from config so it can be swapped. Ingestion and retrieval must use the same id. A mismatch blocks retrieval and tells the operator to re-embed.
- Store the vector next to the chunk id and metadata.

**Artifact:** `data/embeddings/<slug>.json` (chunk id, vector, model id, metadata).

### 7.5 Vector database

- Engine: ChromaDB, persisted on disk.
- Collection name and persist path come from config.
- Upsert uses a stable chunk id so a re-index replaces rows instead of duplicating them.
- The collection records the embedding model id used to build it.

**Artifact:** `data/chroma/` (or the path set in config).

### 7.6 Retrieval and answer

For each user question, persist a trace:

1. Embed the question with the ingestion embedding model.
2. Query the same Chroma collection.
3. Keep the top chunks, their scores, section names, and source URLs.
4. Decide answer vs refuse from the question and the retrieved text.
5. Call the configured LLM with the question, the retrieved chunks, and the answer rules in section 6.
6. Attach one citation URL taken from the chosen chunk, not from the model.

**Artifact:** `data/traces/<query-id>.json` (question, retrieved chunks, scores, prompt, raw model output, final answer, citation, timestamp).

## 8. Configuration

Non-secret settings live in a config file (YAML or JSON). Secrets live only in `.env`, which is not committed.

| Setting | Default | Where |
| --- | --- | --- |
| Corpus URL list | The five Groww URLs in section 5 | Config |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` | Config |
| Vector DB | ChromaDB | Config |
| Chroma persist path and collection | Local `data/chroma`, one collection | Config |
| LLM provider | `groq` | Config. Allowed: `groq`, `gemini`, `openai`, `anthropic`, `mistral` |
| Model id | Read from `.env` | `.env` (`LLM_MODEL`) |
| Provider API key | — | `.env` (`GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`) |

Retrieval uses the same embedding model and the same vector database as ingestion. Changing the embedding model requires re-running embed and index.

The problem statement names `qwen/qwen3.8-27b` as the Groq model. That id is stored as the `.env.example` placeholder and must be checked against Groq’s current model list before the demo. The running app never hardcodes the model id.

## 9. Interface

A single small page:

- Welcome line naming the assistant and the five HDFC pages it covers.
- Three example questions a user can click, covering a scheme fact, the ELSS lock-in, and a refusal case.
- Text input and a submit control.
- The answer, one citation link, and the last-updated line.
- Standing note: `Facts-only. No investment advice.`
- Optional demo panel that shows the trace for the last question: retrieved sections, scores, and the citation URL. This panel exists so the RAG stages are visible without opening the data folders.

PII in the question (PAN, Aadhaar, account number, OTP, email, phone) is not sent to the LLM and is not written to traces. The UI asks the user to remove it and resubmit.

## 10. Deliverables

| Item | Contents |
| --- | --- |
| Working prototype | Local app that runs load → chunk → embed → index → ask. A demo video of at most 3 minutes only if it cannot be hosted. |
| Source list | `doc/sources.md` (or CSV) with the five URLs, fetch date, and the note that internal links were not scraped. |
| README | Setup, `.env` keys, how to run each phase, scope (HDFC AMC + four schemes), and known limits. |
| Sample Q&A | 5–10 queries with the assistant’s answers and links, including at least one refusal and one “not in corpus” case. |
| Disclaimer | The exact UI string: `Facts-only. No investment advice.` |

## 11. Acceptance

- Asking for expense ratio, exit load, minimum SIP, lock-in, riskometer, or benchmark on one of the four schemes returns that fact, one Groww link from the corpus, and the last-updated line, in at most three sentences.
- A buy/sell or “which is better?” question is refused and does not recommend a scheme.
- A returns question does not state or calculate a return.
- An answer’s citation URL is one of the five corpus URLs and matches the chunk that supported the fact.
- `data/raw`, `data/documents`, `data/chunks`, `data/embeddings`, the Chroma directory, and a retrieval trace all exist after a full run and can be opened without re-running the app.
- Switching `LLM_MODEL` or the provider in config changes the model used on the next question.
- The embedding model used at query time matches the model recorded on the collection.

## 12. Known limits

- Facts go stale when Groww updates a page. Freshness is the last successful scrape, printed on every answer.
- Statement-download steps appear only if they are present on the five pages. Otherwise the assistant says the indexed pages do not contain that procedure.
- The assistant covers one AMC and four schemes. It does not generalize to other AMCs.
- Chunk quality depends on how Groww marks up the page on the scrape date. The chunk files are the place to check a bad answer.
