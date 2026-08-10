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

### 4.1 Clarification — what "isolated" means (added 2026-08-10, additive)

*This subsection was added after the round-two sweep halted on a genuine conflict between §2 and §4: §4 requires a stop when prohibited data is not isolable, while §2's only remedy — suppressing market-data widgets — is a renderer capability, and §2 routes every set other than §1.1 through ordinary retrieval, which has no suppression mechanism at all. The decisions below were made by Harshith Akurati. They resolve the precedence and add nothing else. **No universe, cadence, eligibility window, source hierarchy, source-authority rule, enrollment criterion, outcome firewall or statistical rule is changed.***

**Precedence.** §4 governs **actual exposure**. §2 supplies the **preventive mechanism**. Where both apply, §4 decides the outcome and §2 decides the method.

**Definition — isolated.** Prohibited data counts as isolated **only if its network requests were blocked before their responses were received and before any value populated the rendered page**. Isolation is a property of what never arrived, not of what was subsequently avoided.

**Insufficient.** Ignoring, cropping, masking, excluding from extraction, or omitting an already-rendered or already-retrieved widget **does not restore blinding**. A value that reached the evidence surface has already been observed for protocol purposes.

**Pre-render request blocking is permitted for every issuer page**, regardless of whether the ticker was originally assigned ordinary retrieval (§1.2, §1.3, §1.4, §1.5) or renderer retrieval (§1.1). Blocking must be installed **before** navigation begins. This is a retrieval-method permission only; it expands no source set and reaches no host the runbook did not already authorise.

**Consequence.** If a prohibited value populates the **DOM, accessibility tree, screenshot, extracted text, console output, or saved evidence**, stop that ticker and classify it **`COMPROMISED_ENROLLMENT_BLINDING` for this screening cycle**.

That disposition is **cycle-specific**. It is *not* a permanent exclusion, *not* a registry amendment, *not* an event-state transition, and *not* a claim that any existing registered event is compromised. The ticker returns to the ordinary cadence next cycle.

**Recording rule.** For a compromised ticker, record **only**: that prohibited market data was displayed, the exposure timestamp, the affected source URL, and the resulting disposition. **The observed price, percentage change, volume or any other prohibited value is never recorded anywhere** — not in an artifact, a log, a commit message, or a report. Evidence bodies containing prohibited values are quarantined outside version control and are never re-inspected.

**Blocking may not be weakened to obtain a listing.** If blocking prevents the event listing from rendering, the source is classified under the existing access-failure or unresolved rule.

**Pre-extraction gate.** Before any event information is extracted from a rendered page, an automated scan must verify that the rendered DOM, accessibility text and saved screenshot contain no populated quote, price, percentage-change, volume, chart-value, options, surprise, analyst or outcome field. **No page may be inspected manually until that scan passes.** If the scan fails, the values are not viewed: the ticker stops and takes the cycle-specific compromised disposition.

## 5. Outcomes

- An **inaccessible** page remains a documented **access failure**. It is never described as issuer-confirmed absence, and no third-party source is substituted.
- A page that **states** no upcoming events is recorded as **issuer-stated absence** — a distinct outcome.
- A candidate with an explicit date **and** explicit timing enters the **human-review queue**.
- **No registry row and no canonical `ENROLLED` screening row may be written until a named human verifies the official source.** The agent's retrieval is never recorded as human verification, and authorisation to run the sweep is not verification.
- A canonical `PENDING_OFFICIAL_DATE_UNAVAILABLE` row may be written **only** when a real candidate identity exists (ticker **and** fiscal period) so the screening-log schema is satisfied without inventing a label. Otherwise the item stays in the round-2 manifest with the reconnaissance status `NO_ENROLLMENT_DECISION_REACHED`.

## 6. Artifacts to produce

`SWEEP_MANIFEST_ROUND2.json` (every ticker exactly once, including failures), `HUMAN_REVIEW_REQUIRED_ROUND2.json`, screenshots and DOM hashes for any candidate, and a round-2 entry in `CHANGELOG.md`. Round-1 artifacts and the correction overlay are **not** modified — round 2 adds, it never rewrites.

Do not store recent-8-K metadata unless a specific candidate filing was actually opened.
