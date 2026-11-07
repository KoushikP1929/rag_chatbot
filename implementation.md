# Implementation Plan: HDFC Mutual Fund Facts Assistant

**Status:** Draft  
**Date:** 6 November 2026  
**Sources:** `prd.md`, `architecture.md`

Seven steps. Each one writes files you can open. Later steps read the previous step's files and do not repeat earlier work.

| Step | Name | Output |
| --- | --- | --- |
| 1 | Creating directory | Scaffold, `config.yaml`, `.env.example` |
| 2 | Scraping document | `data/raw/` |
| 3 | Loading the document | `data/documents/` |
| 4 | Chunking | `data/chunks/` |
| 5 | Embedding | `data/embeddings/` |
| 6 | Storing data in vector DB | `data/chroma/` |
| 7 | Retrieval logic and UI | `data/traces/`, one local page |
| 8 | Edge case and test case for guardrails | `src/guard.py`, `tests/` |

```bash
python -m src.cli all    # scrape → load → chunk → embed → index
```

---

## 1. Creating directory

Create the repo layout, config, and a check that config is valid.

```
config.yaml          .env.example         .gitignore
requirements.txt     README.md
data/raw/  data/documents/  data/chunks/  data/embeddings/  data/chroma/  data/traces/
src/config.py  src/paths.py  src/fetch.py  src/documents.py
src/chunk.py  src/embed.py  src/index.py
src/guard.py  src/retrieve.py  src/answer.py  src/llm/
src/cli.py  src/app.py
tests/
```

`config.yaml` holds the five Groww URLs, embedding model `sentence-transformers/all-MiniLM-L6-v2`, Chroma path `data/chroma` and collection `hdfc_facts`, LLM provider `groq`, `top_k: 5`, and the disclaimer `Facts-only. No investment advice.`

`.env` holds the provider API key and `LLM_MODEL`. The example value `qwen/qwen3.8-27b` is a placeholder until it is checked against Groq's model list. Allowed providers: Groq, Gemini, OpenAI, Anthropic, Mistral.

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m src.cli config-check
```

Done when `config-check` prints the five URLs and a masked key, and a bad URL, missing key, or unknown provider fails with the field name.

## 2. Scraping document

Fetch only the five configured pages. Do not follow links on them.

1. Save the HTTP result as `data/raw/<slug>.json` (`url`, `title`, `scheme_name` or `amc`, `status`, `fetched_at`, `hash`, `text`). A failed or empty page is recorded and gets no body text.
2. Write `data/raw/_run.json` with the last successful scrape time. That date is the "Last updated from sources" line.

```bash
python -m src.cli scrape
```

Done when each successful page has one raw file, a failed page has no invented text, and a second run overwrites the same files.

## 3. Loading the document

Read `data/raw/` only. Do not fetch the network.

Write one document per successful page, `data/documents/<slug>.json`: `page_content` is the raw text, plus `source_url`, title, scheme or AMC, fetch time, and hash. A failed or empty raw page produces no document, and a document left from an earlier run is deleted. `data/documents/_index.json` lists the documents, the skipped slugs, and the last successful scrape time.

```bash
python -m src.cli load
```

Done when each successful raw page has one document, `page_content` matches the raw text, and a second run overwrites the same files.

## 4. Chunking

Read `data/documents/` only. One chunk per section so a label stays with its value (expense ratio, exit load, minimum SIP, lock-in, riskometer, benchmark, statement download). A page with no headings falls back to ~800-character chunks with overlap, marked `fallback: true`.

Chunk id is `<slug>::<index>::<hash>` so a re-run replaces rows. Metadata on every chunk: `source_url`, `page_title`, `scheme_name` or `amc`, `section`, `fetched_at`.

```bash
python -m src.cli chunk
```

Done when the ELSS page has a lock-in chunk and the same input produces the same chunk ids.

## 5. Embedding

Embed each chunk with the model in config (`sentence-transformers/all-MiniLM-L6-v2`). Write `data/embeddings/<slug>.json` with the model id, chunk id, vector, and chunk metadata. Vectors are L2-normalized.

If existing embeddings were made with a different model, stop unless `--force` is passed.

```bash
python -m src.cli embed
```

Done when every chunk has one vector of the model's dimension, and a model change is refused without `--force`.

## 6. Storing data in vector DB

Upsert embeddings into Chroma at `data/chroma`, collection `hdfc_facts`, keyed by chunk id. Store the embedding model id on the collection. Refuse to mix vectors from two models; `--rebuild` drops the collection and writes it again.

```bash
python -m src.cli index
python -m src.cli index --verify
```

Done when the collection count equals the chunk count and a second run does not add duplicate rows.

## 7. Retrieval logic and UI

`ask(question)`:

1. Reject PII before any model call. Classify the question as fact, advice, returns, or out of scope.
2. Embed the question with the same model used at ingest, and query the same Chroma collection.
3. Answer a grounded fact from the retrieved chunks only (at most 3 sentences). Cite the chunk's `source_url`, which must be one of the five pages.
4. Refuse advice with a short facts-only message and one educational link. Refuse returns with no number and a pointer to the official factsheet. If the fact is not in the chunks, say so and still give the closest corpus link.
5. Save `data/traces/<query-id>.json`: question, retrieved chunks and scores, answer, citation. No PII in the trace.

The provider and `LLM_MODEL` come from config and `.env`. Nothing in code hardcodes the model id.

The UI is one FastAPI page: a welcome line, three example questions (a scheme fact, ELSS lock-in, a refusal), a text box, the answer, one citation, the last-updated line, and `Facts-only. No investment advice.` A trace panel shows the sections and scores for the last question.

```bash
python -m src.cli ask "What is the exit load on HDFC Large Cap Fund?"
uvicorn src.app:app --reload --port 8000
```

Done when a fact question returns a cited answer, advice and returns questions are refused, and the three examples work in the browser.

## 8. Edge case and test case for guardrails

| Case | Behavior |
| --- | --- |
| PAN, Aadhaar, account number, OTP, email, or phone in the question | Stop before the LLM. Do not store the value. Ask the user to remove it. |
| "Should I buy?" or "Which is better?" | Facts-only refusal and one corpus link. No recommendation. |
| Returns or CAGR | No number and no calculation. Point to the factsheet. |
| Fact missing from the five pages | Say it is not in the indexed pages. Link the closest page. |
| Fetch fails or text is empty | Record the failure. Do not invent text. |
| Embedding model or Chroma collection does not match | Block retrieval until embed and index are run again. |
| Model adds its own URL or writes more than 3 sentences | Drop the model URL, cap the sentences, and cite the chunk. |

Tests cover config validation, PII and refusal classification, scrape → document, chunk ids, embedding shape, Chroma upsert without duplicates, citation taken from chunk metadata, and the three UI examples. PII on `POST /ask` returns HTTP 400.

```bash
pytest -q
```

Also write `doc/sources.md` (the five URLs and the note that internal links were not scraped), `doc/sample_qa.md` (5–10 answers, including one refusal and one missing fact), and `README.md` (setup, env keys, the commands above, and known limits).
