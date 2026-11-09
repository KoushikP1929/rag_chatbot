# HDFC Fund Facts Assistant (Groww corpus) — Facts-Only MF FAQ

A small RAG assistant that answers **facts** about four HDFC Mutual Fund schemes — expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark — using **only the five official Groww pages** in its corpus. Every answer carries **exactly one source link**, a `Last updated from sources:` date, and stays within **3 sentences**. Opinionated, returns, out-of-corpus and PII queries are refused by a pre-LLM guard.

> ⚠️ **Facts-only. No investment advice.**

- 🔗 **Prototype / live app:** `__ADD-LINK__`
- 🔗 **GitHub repo:** `__ADD-LINK__`
- 🎬 **Demo video (≤3 min):** `__ADD-LINK__` *(only if the app is not hosted)*

---

## 1. Scope

| Item | Selection |
|---|---|
| **Product platform** | **Groww** — all five indexed pages are public groww.in pages |
| **AMC** | **HDFC Mutual Fund** |
| **Scheme 1** | HDFC Large Cap Fund — Direct Growth |
| **Scheme 2** | HDFC Flexi Cap Fund — Direct Plan Growth |
| **Scheme 3** | HDFC ELSS Tax Saver Fund — Direct Plan Growth |
| **Scheme 4** | HDFC Mid Cap Fund — Direct Growth |
| **AMC page** | HDFC Mutual Fund — AMC overview |

**Corpus size: 5 pages** (1 AMC overview + 4 scheme pages). All five are live, public, and re-scrapable with one command.

> 📌 **Note on page count:** the milestone asks for 15–25 source pages. This prototype currently indexes **5** (the five Groww pages above). Expanding the corpus (KIM/SID, factsheets, SEBI/AMFI pages, statement guides) is listed under *Known limits* and is the next step — the ingestion pipeline (`config.yaml` allow-list → `src.cli all`) is already built to take more pages.

---

## 2. Stack & Architecture

| Layer | Implementation |
|---|---|
| Web UI / API | **FastAPI** (`src/app.py`) — single-page chat UI in Groww design tokens |
| Input guard | `src/guard.py` — PII detection + intent / scheme / advice / returns classification (regex, pre-LLM) |
| Retrieval | **Chroma** vector store, section-filtered top-k (`k = 5`) |
| Embeddings | **`gemini-embedding-001`** (768 dims) |
| Generation | **Groq** LLM (configurable via `config.yaml` + `.env`) |
| Post-checks | `src/answer.py` — strips URLs, enforces ≤ 3 sentences, validates citation against the 5-page allow-list |
| Audit | Every query writes a JSON trace to `data/traces/<query_id>.json` |

**Answer flow:** `question → PII guard → mode (fact / advice / returns / out_of_scope) → intent + scheme detection → Chroma retrieval filtered to the matching section & scheme → grounded prompt → Groq → finalize (≤ 3 sentences, no URLs) → citation from the retrieved chunk → UI card + trace`.

---

## 3. Setup (local)

```bash
# 1. clone
git clone __ADD-LINK__
cd rag_bot

# 2. install
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# 3. keys
copy .env.example .env          # then fill GROQ_API_KEY, GEMINI_API_KEY, LLM_MODEL

# 4. validate config
python -m src.cli config-check

# 5. run the web app
python -m src.app               # → http://127.0.0.1:8000
```

*(Optional)* rebuild the whole index from the five Groww pages:

```bash
python -m src.cli all           # scrape → load → chunk → embed → index
python -m src.cli index --verify
```

**Deploy:** `vercel.json` is included (`app.py` is the ASGI entrypoint, `maxDuration: 60`). Set `GROQ_API_KEY`, `GEMINI_API_KEY`, `LLM_MODEL`, and optionally `EMBEDDING_QUERY_PROVIDER=gemini`.

---

## 4. Using the Prototype

**UI** (`/`): welcome/scope card, **3 example question chips**, sticky input, and the permanent line **“Facts-only. No investment advice.”**

Example chips that ship in the UI:

1. What is the expense ratio of HDFC Large Cap Fund?
2. What is the lock-in period for HDFC ELSS Tax Saver Fund?
3. Should I buy HDFC Mid Cap Fund? *(demonstrates the refusal path)*

**API:**

| Endpoint | Purpose |
|---|---|
| `POST /ask` `{"question": "..."}` | Returns `answer`, `citation`, `last_updated`, `mode`, `query_id`, `trace` |
| `GET /health` | Corpus slugs, chunk count, embedding model, LLM model, last scrape date |

**CLI:**

```bash
python -m src.cli ask "What is the exit load on HDFC Flexi Cap Fund?"
```

---

## 5. Corpus Facts Snapshot (scraped 2026-11-07)

All values are **Direct plan** figures exactly as published on the indexed Groww pages.

| Scheme | Expense ratio | Exit load | Min SIP | Lock-in | Riskometer | Benchmark |
|---|---|---|---|---|---|---|
| HDFC Large Cap Fund | 1.01% | 1% if redeemed within 1 year | ₹100 | None | Moderately High | NIFTY 100 TRI |
| HDFC Flexi Cap Fund | 0.75% | 1% if redeemed within 1 year | ₹100 | None | Moderately High | NIFTY 500 TRI |
| HDFC ELSS Tax Saver Fund | 1.20% | Nil | ₹500 | 3 years | Moderately High | NIFTY 500 TRI |
| HDFC Mid Cap Fund | 0.74% | 1% if redeemed within 1 year | ₹100 | None | Moderately High | NIFTY Midcap 150 TRI |

`Last updated from sources: 2026-11-07T06:30:25Z`

---

## 6. Source List (5 indexed pages)

| # | Page | URL |
|---|---|---|
| 1 | HDFC Mutual Fund — AMC overview | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| 2 | HDFC Large Cap Fund — Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 3 | HDFC Flexi Cap — Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 4 | HDFC ELSS Tax Saver Fund — Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | HDFC Mid Cap Fund — Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

Full machine-readable list: **`sources.csv`**.

---

## 7. Sample Q&A

See **`sample_qa.md`** for the full set (10 queries, including refusals and the PII rejection). Short excerpt:

**Q: What is the expense ratio of HDFC Large Cap Fund?**
> The direct plan expense ratio of HDFC Large Cap Fund is 1.01%. Last updated from sources: 2026-11-07.
> 📎 https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth

**Q: Should I buy HDFC Mid Cap Fund?** *(refusal)*
> I cannot advise on whether to buy, sell, or switch between schemes. I can look up facts like the expense ratio, exit load, minimum SIP, lock-in, riskometer, or benchmark instead.
> 📎 https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth

---

## 8. Disclaimer (exact UI text)

> **Facts-only. No investment advice.**

The answer cards additionally carry: *“Answers come from five indexed Groww pages… Every answer cites one of those pages.”* The long-form version for README/support use:

> **Facts-only. No investment advice.** This assistant answers factual questions about HDFC Mutual Fund schemes using five official public Groww pages and always shows one source link. It does not recommend schemes, predict returns, or compare performance, and it stores no personal information. Last updated from sources: 2026-11-07.

---

## 9. Constraints Compliance

- ✅ **Public sources only** — five public groww.in pages, enforced by a `config.yaml` allow-list (`ALLOWED_CORPUS`); no blogs, no back-end screenshots.
- ✅ **Every answer has exactly one citation** — the URL is taken from the retrieved chunk and validated against the five-page allow-list before display.
- ✅ **≤ 3 sentences** — `src/answer.py::finalize` hard-caps output; model-generated URLs are stripped.
- ✅ **No PII** — the guard detects PAN, Aadhaar, email, phone, OTP and account-number patterns before retrieval/LLM and rejects with a 400 + polite message. Nothing is stored.
- ✅ **No performance claims** — a returns guard refuses return/performance/CAGR questions and points to the AMC page; the prompt also forbids return numbers.
- ✅ **Facts-only refusals** — advice/portfolio/“which fund” questions get a fixed, polite refusal (no LLM involvement).
- ✅ **Transparency** — every query writes a trace (retrieved chunks, prompt, raw output, final answer, citation) to `data/traces/`.

---

## 10. Known Limits

- **Corpus is 5 pages**, below the milestone’s 15–25 target. Missing: KIM/SID, factsheets, fee pages, SEBI/AMFI pages, and a statement-download guide.
- **No statement-download source is indexed.** The guard recognises the intent, but the corpus has no statement section, so the answer falls back to *“I don’t have that fact in the indexed pages”* with the AMC-page link.
- **Only Direct-plan Growth pages** — Regular plan, IDCW and other AMC schemes are out of scope and refused politely.
- **Values are a point-in-time snapshot** (2026-11-07). TER, loads and benchmarks change; re-run `python -m src.cli all` to refresh.
- **Runtime needs network keys** — Groq for answers, Gemini for question embeddings (`EMBEDDING_QUERY_PROVIDER=gemini` on serverless). If either is unavailable the app degrades to a safe fallback message instead of guessing.
- **Retrieval is section-filtered**, so unusual phrasings can miss; the supported intents are expense ratio, exit load, minimum SIP, lock-in, riskometer, benchmark (and statement, when a source exists).
