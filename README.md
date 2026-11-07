# HDFC Mutual Fund Facts Assistant

Facts-only FAQ for five public HDFC Mutual Fund pages on Groww. Every answer cites one of those pages. The assistant does not give investment advice.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set the API key for the provider in `config.yaml` (`groq` by default) and set `LLM_MODEL`. The value in `.env.example` is a placeholder until it is checked against Groq's model list.

```bash
python -m src.cli config-check
```

`config-check` prints the five URLs and a masked key. A bad URL, an unknown provider, a missing key, or an empty `LLM_MODEL` fails with the field name.

Fetch those five pages into `data/raw/`. The scraper does not open links found on the pages. Loading reads those files and writes one document per successful page. It does not fetch again.

```bash
python -m src.cli scrape
python -m src.cli load
```

## Scope

HDFC Mutual Fund AMC overview, plus HDFC Large Cap, Flexi Cap, ELSS Tax Saver, and Mid Cap direct plans. Internal links on those pages are not scraped.

## This checkout

Phase 1 is the directory layout and config check. Phase 2 scrapes the five pages into `data/raw/`. Phase 3 loads those files into `data/documents/`. Phase 4 splits each document into fact sections in `data/chunks/`. Phase 5 embeds those chunks with `sentence-transformers/all-MiniLM-L6-v2` into `data/embeddings/`. Phase 6 stores them in Chroma at `data/chroma`, collection `hdfc_facts`. The UI is a later phase.

```bash
python -m src.cli chunk
python -m src.cli embed
python -m src.cli index
python -m src.cli all                 # scrape → load → chunk → embed → index in one go
python -m src.cli index --verify
python -m src.cli ask "What is the expense ratio of HDFC Large Cap Fund?"
```

## Asking questions (retrieval phase)

`ask` guards the question first: PAN, Aadhaar, account number, OTP, email, or phone is rejected without an LLM call. Then it classifies the question (fact / advice / returns / out of scope), retrieves the matching fact sections from Chroma, and answers. Buy, sell, "which is better", and returns questions get a facts-only refusal with one corpus link. Answers are at most three sentences, cite exactly one of the five pages, and end with the last successful scrape date. Every question writes `data/traces/<query-id>.json` with the retrieved chunks, scores, prompt, raw model output, and final answer.

Set a real API key in `.env` — the placeholder `GROQ_API_KEY` returns HTTP 401 from Groq — and verify `LLM_MODEL` against Groq's current model list. The web UI serves the same path:

```bash
python -m src.cli ask "Should I buy HDFC Mid Cap Fund?"
uvicorn src.app:app --port 8000     # then open http://127.0.0.1:8000
```
