# MF FAQ Assistant for Groww — Facts-Only Q&A (RAG with Citations)

A small FAQ assistant that answers **facts** about mutual fund schemes — expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, and how to download statements — using **only official public pages** (HDFC AMC / SEBI / AMFI / Groww). Every answer contains **exactly one source link** and the line `Last updated from sources: <date>`. Answers are ≤ 3 sentences.

> ⚠️ **Facts-only. No investment advice.**

- 🔗 **Prototype:** `__ADD-LINK__` (app/demo)
- 🎬 **Demo video (≤3 min):** `__ADD-LINK__` *(only if app not hosted)*

---

## 1. Scope

| Item | Selection |
|---|---|
| **Product platform** | **Groww** (groww.in — official help/FAQ pages used for product how-to answers) |
| **AMC chosen** | **HDFC Asset Management Company** (hdfcfund.com) |
| **Scheme 1 — Large-cap** | HDFC Bluechip Fund |
| **Scheme 2 — Flexi-cap** | HDFC Flexi Cap Fund |
| **Scheme 3 — ELSS** | HDFC ELSS Tax Saver Fund |

**Why this scope:** all three schemes under one AMC have complete, stable, official public documentation (KIM/SID, factsheets, scheme FAQs, riskometer & benchmark pages), which makes citations accurate and easy to verify. One large-cap + one flexi-cap + one ELSS covers the key FAQ categories: TER/exit load/minimum SIP (large & flexi), lock-in (ELSS), riskometer, benchmark, and statement download (Groww help).

---

## 2. Setup

```bash
git clone __ADD-LINK__ .   # your repo URL (if someone clones fresh)
pip install -r requirements.txt
python app.py
```

- **Stack:** Python + [RAG/retrieval layer — small keyword/embedding index over the 20 collected source pages]
- No login, no database: the assistant stores **no personal data** of any kind.

---

## 3. How to Use

The on-screen UI shows a welcome line, **3 example questions**, and the permanent disclaimer:

> **Facts-only. No investment advice.**

**Example questions rendered in the UI:**

1. What is the expense ratio of HDFC Bluechip Fund?
2. What is the lock-in period for HDFC ELSS Tax Saver Fund?
3. How do I download my capital gains statement on Groww?

**Refusal behaviour:** for opinionated/portfolio questions ("Which fund should I buy?", "Should I sell?"), the assistant replies with a **polite facts-only message + educational link** (Section 5, Q8).

---

## 4. Source List (15–25 official public pages only)

| # | Source | What it's used for |
|---|--------|--------------------|
| 1 | Key Information Memorandum (KIM) — HDFC Bluechip Fund | TER, exit load, min SIP, benchmark, riskometer |
| 2 | Scheme Information Document (SID) — HDFC Bluechip Fund | Full scheme terms |
| 3 | Factsheet — HDFC Bluechip Fund | Latest TER %, benchmark, riskometer |
| 4 | KIM — HDFC Flexi Cap Fund | TER, exit load, min SIP, benchmark, riskometer |
| 5 | SID — HDFC Flexi Cap Fund | Full scheme terms |
| 6 | Factsheet — HDFC Flexi Cap Fund | Latest TER %, benchmark, riskometer |
| 7 | KIM — HDFC ELSS Tax Saver Fund | 3-yr lock-in, min SIP, benchmark, riskometer |
| 8 | SID — HDFC ELSS Tax Saver Fund | Full scheme terms incl. lock-in provisions |
| 9 | Factsheet — HDFC ELSS Tax Saver Fund | Latest TER %, benchmark, riskometer |
| 10 | Scheme FAQs — HDFC AMC | Exit load & lock-in confirmations |
| 11 | Fees / charges page — HDFC AMC | TER / stamp duty facts |
| 12 | Riskometer & benchmark methodology notes — HDFC AMC | Riskometer categories |
| 13 | Statement / tax-doc download guide — HDFC AMC (or Groww help) | Capital gains statement steps |
| 14 | Groww help — download capital gains statement | Product how-to |
| 15 | Groww help — download consolidated account statement | Product how-to |
| 16 | SEBI — Mutual Funds investor page | Baseline facts & lock-in regulation |
| 17 | AMFI — Investor education page | ELSS / SIP educational link (used in refusals) |
| 18 | SEBI master circular on mutual funds | Lock-in (ELSS = 3 years) authority |
| 19 | HDFC AMC — scheme returns/factsheet download page | Redirect target for "performance" questions |
| 20 | Groww scheme page — HDFC Bluechip Fund | Cross-check of TER/load |

📄 **Full list with URLs:** see `sources.csv` in this repo. *(URLs intentionally left as `__ADD-LINK__` placeholders — fill before submitting.)*

---

## 5. Sample Q&A (see `sample_qa.md` for the full 8)

**Q1 — "What is the expense ratio of HDFC Bluechip Fund?"**
> The direct plan TER of HDFC Bluechip Fund is 0.32% (as of the latest factsheet); the regular plan TER is 0.63%. Expense ratios change periodically, so verify against the current factsheet. Last updated from sources: `<date>`.
> 📎 Source: `__ADD-LINK__` (factsheet)

**Q8 — "Which fund should I buy — Bluechip or Flexi Cap?"** *(refusal)*
> I can't recommend which scheme to buy or sell — I share facts only from official sources, not investment advice. For education on how to evaluate schemes, see AMFI's investor education page. 📎 `__ADD-LINK__`

---

## 6. Disclaimer Snippet (exact text shown in UI)

> **Facts-only. No investment advice.** This assistant answers factual questions about mutual fund schemes using official public pages (AMC/SEBI/AMFI) and always shows one source link. It does not recommend schemes, predict returns, or compare performance, and it stores no personal information. Last updated from sources: `<date>`.

---

## 7. Constraints Followed

- ✅ Public sources only (HDFC AMC / SEBI / AMFI / Groww official pages) — no blogs, no back-end screenshots.
- ✅ **No PII:** the assistant never accepts or stores PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers.
- ✅ **No performance/return claims:** return questions are politely refused and redirected to the official factsheet (see Q7 in `sample_qa.md`).
- ✅ Every answer ≤ 3 sentences, with **exactly one** citation link and a `Last updated from sources:` date.

---

## 8. Known Limits

- Small corpus (~20 pages): only the 3 selected HDFC AMC schemes are in scope; other AMCs/products are refused.
- TER and load figures change frequently — dates shown are the last source-fetch dates; check the live factsheet for current values.
- Retrieval is keyword/embedding based on a tiny index; phrased differently, some questions may need rewording to match (W3 limitation).
- Performance, tax-advice, and "which is better" questions are out of scope by design.
