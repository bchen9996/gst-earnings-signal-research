# Round-2 Renderer Runbook — Monday 09:00 America/Chicago

**Do not execute this during the audit pass.** It runs at the cadence fixed by cohort protocol v1.1: **Monday 09:00 America/Chicago**, or on the next available calendar day if a documented technical failure blocks it, with the delay and its cause recorded. Running it early would be an unscheduled re-screen, which the protocol forbids.

Scope is fixed **in advance** by `ROUND1_CORRECTION_OVERLAY_v1.json`. Round 2 visits the URLs listed there and nothing else.

---

## 1. Target list — exactly these, nothing else

### 1.1 Browser rendering required (static HTML insufficient) — 9 tickers, 11 URLs

| Ticker | URL |
|---|---|
| AMZN | `https://ir.aboutamazon.com/events/default.aspx` |
| BKR | `https://investors.bakerhughes.com/events-presentations` |
| CTSH | `https://news.cognizant.com/events` |
| GOOGL | `https://abc.xyz/investor/events/` |
| MSFT | `https://www.microsoft.com/en-us/investor/events/default.aspx` |
| NKE | `https://investors.nike.com/investors/news-events-and-reports/default.aspx` |
| NKE | `https://investors.nike.com/investors/news-events-and-reports/default.aspx?toggle=news` |
| NKE | `https://investors.nike.com/investors/news-events-and-reports/?toggle=earnings` |
| QCOM | `https://investor.qualcomm.com/news-events/events` |
| SBUX | `https://investor.starbucks.com/events-presentations/default.aspx` |
| SYK | `https://investors.stryker.com/events-and-presentations` |

### 1.2 Retry, then locate the real calendar — 8 access-failure tickers

`ABBV`, `BRK-B`, `DVN`, `GME`, `LDOS`, `TSLA`, `TTWO`, `UAL`. Retry the recorded URL once; if it still fails, navigate from the **issuer's own** site to its events calendar. **Classify by page role, not by URL spelling** — round 1 accepted a spill-prevention page because "pr‑event‑ion" contains "event".

### 1.3 Locate the events calendar — 2 discovery-gap tickers

`AAPL`, `ADBE`. Round 1 only ever read an IR landing page. Find the actual events calendar from the issuer's own navigation.

### 1.4 Confirm only — 4 issuer-stated-absence tickers

`GPN`, `INTC`, `NCLH`, `STZ`. Re-read the same page and record whether the "no upcoming events" statement still holds. Nothing else.

### 1.5 DELL — recheck only

`https://investors.delltechnologies.com/news-events/upcoming-events`. **Date and time consistency only.** The registration is not to be altered. If an official source **contradicts** the registered timing, **stop before writing anything** and report it.

## 2. Retrieval rules

- **Browser rendering only for §1.1** — pages whose static HTML was demonstrably insufficient. Everything else uses ordinary retrieval first.
- **No search engines, no snippets, no third-party calendars.** No YCharts, Nasdaq, Yahoo, MarketWatch, Seeking Alpha, broker calendars or aggregators — not as evidence, not as navigation.
- **Block or ignore** third-party analytics, market-data widgets, advertisements, trackers and unrelated outbound requests. If the renderer cannot suppress them, record that and continue without treating any of it as evidence.
- **Do not click** earnings-results links, presentations, transcripts, analyst materials, or historical-result pages. The target is the *upcoming-event listing*, nothing adjacent to it.

## 3. What may be extracted

Only:

- upcoming-event title
- fiscal-period label **as displayed**
- date **as displayed**
- time **as displayed**
- the URL
- the exact displayed text, verbatim

Nothing is normalised, completed or inferred. A missing fiscal period stays missing; a missing time stays missing.

For **any proposed candidate**, capture both:

1. a **screenshot**, and
2. a **DOM text hash**

so the observation is reproducible and auditable.

## 4. What may not be extracted

No attention, price, return, volume, volatility, options, earnings surprise, analyst estimate, news tone or prior outcome — no field of that kind may be read, stored or inferred, and none may appear in any round-2 artifact.

**Stop immediately** if a page displays prohibited attention, price, surprise, options or outcome data in a way that cannot be isolated from the event listing. Record the stop and the reason; do not work around it.

## 5. Outcomes

- An **inaccessible** page remains a documented **access failure**. It is never described as issuer-confirmed absence, and no third-party source is substituted.
- A page that **states** no upcoming events is recorded as **issuer-stated absence** — a distinct outcome.
- A candidate with an explicit date **and** explicit timing enters the **human-review queue**.
- **No registry row and no canonical `ENROLLED` screening row may be written until a named human verifies the official source.** The agent's retrieval is never recorded as human verification, and authorisation to run the sweep is not verification.
- A canonical `PENDING_OFFICIAL_DATE_UNAVAILABLE` row may be written **only** when a real candidate identity exists (ticker **and** fiscal period) so the screening-log schema is satisfied without inventing a label. Otherwise the item stays in the round-2 manifest with the reconnaissance status `NO_ENROLLMENT_DECISION_REACHED`.

## 6. Artifacts to produce

`SWEEP_MANIFEST_ROUND2.json` (every ticker exactly once, including failures), `HUMAN_REVIEW_REQUIRED_ROUND2.json`, screenshots and DOM hashes for any candidate, and a round-2 entry in `CHANGELOG.md`. Round-1 artifacts and the correction overlay are **not** modified — round 2 adds, it never rewrites.

Do not store recent-8-K metadata unless a specific candidate filing was actually opened.
