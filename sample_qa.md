# Sample Q&A — HDFC Fund Facts Assistant (Groww corpus)

These are the answers the prototype returns for the current 5-page corpus (scraped `2026-11-07T06:30:25Z`). Answers stay within 3 sentences; the citation is the single Groww page shown in the source chip; the card meta row shows `Last updated from sources: 2026-11-07`.

---

**Q1. What is the expense ratio of HDFC Large Cap Fund?**
> The direct plan expense ratio of HDFC Large Cap Fund is 1.01%. Last updated from sources: 2026-11-07.
> 📎 Source: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth
> *Mode: fact · Citation from retrieved chunk*

---

**Q2. What is the expense ratio of HDFC Flexi Cap Fund?**
> The direct plan expense ratio of HDFC Flexi Cap Fund is 0.75%. Last updated from sources: 2026-11-07.
> 📎 Source: https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth

---

**Q3. What is the exit load on HDFC Mid Cap Fund?**
> HDFC Mid Cap Fund charges an exit load of 1% if units are redeemed within 1 year. Last updated from sources: 2026-11-07.
> 📎 Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth

---

**Q4. What is the minimum SIP for HDFC ELSS Tax Saver Fund?**
> The minimum SIP for HDFC ELSS Tax Saver Fund is ₹500 per instalment. Last updated from sources: 2026-11-07.
> 📎 Source: https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth

---

**Q5. What is the lock-in period for HDFC ELSS Tax Saver Fund?**
> HDFC ELSS Tax Saver Fund has a lock-in of 3 years. Last updated from sources: 2026-11-07.
> 📎 Source: https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth

---

**Q6. What is the riskometer level of HDFC Large Cap Fund?**
> HDFC Large Cap Fund is classified as "Moderately High" risk on the riskometer. Last updated from sources: 2026-11-07.
> 📎 Source: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth

---

**Q7. What is the benchmark of HDFC Flexi Cap Fund?**
> The benchmark for HDFC Flexi Cap Fund is the NIFTY 500 Total Return Index (NIFTY 500 TRI). Last updated from sources: 2026-11-07.
> 📎 Source: https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth

---

**Q8. How do I download my capital gains statement?** *(known corpus gap)*
> I don't have that fact in the indexed pages. You can check the sourced page below. Last updated from sources: 2026-11-07.
> 📎 Source: https://groww.in/mutual-funds/amc/hdfc-mutual-funds
> *Mode: fact · Intent recognised, but no statement section exists in the 5-page corpus*

---

**Q9. Should I buy HDFC Mid Cap Fund?** *(advice refusal)*
> I cannot advise on whether to buy, sell, or switch between schemes. I can look up facts like the expense ratio, exit load, minimum SIP, lock-in, riskometer, or benchmark instead.
> 📎 Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth
> *Mode: advice · Fixed refusal text, no LLM call*

---

**Q10. Which fund gave the best returns?** *(returns refusal)*
> I do not provide return numbers or calculate performance. Please check the official HDFC Mutual Fund factsheet. I can answer facts like the expense ratio, exit load, minimum SIP, lock-in, riskometer, or benchmark from the page below.
> 📎 Source: https://groww.in/mutual-funds/amc/hdfc-mutual-funds
> *Mode: returns · No performance data is generated or compared*

---

**Q11. "My email is abc@example.com — what is the exit load?"** *(PII rejection)*
> Your question appears to contain an email address. Please remove personal details and resubmit your question.
> *HTTP 400 · mode: pii · no citation, no retrieval, nothing stored*

---

## Disclaimer shown in the UI

> **Facts-only. No investment advice.**

Answer cards also state that answers come from five indexed Groww pages and cite one of them.

*`Last updated from sources: 2026-11-07` (from `data/documents/_index.json`).*
