# Round-1 Evidence Audit

**Offline audit.** No network retrieval, no candidate lookup, no round 2. Protocol v1.1 fixes the next sweep at **Monday 09:00 America/Chicago**, and this audit is deliberately not an unscheduled re-screen.

**Audited at PR #12 head** `12400f8c9394de5741bb37269dbf6e392b9245ad`.
**Authoritative machine-readable form:** `ROUND1_CORRECTION_OVERLAY_v1.json`.

---

## 1. What this audit does and does not do

It **adds a correction layer**. It does not rewrite, delete, squash or amend anything. The original artifacts record what the first retrieval actually did — including its mistakes — and they stay exactly as written:

| Artifact | SHA-256 (LF-normalised) |
|---|---|
| `SWEEP_MANIFEST_ROUND1.json` | `d44e5c539804adc170041d66d140b6c5d2568e9ce95f34a4b379df819b9a4499` |
| `sweep_raw_round1.json` | `63bdb83d1385b4ef848fe8f309d4da1f9b97ee4f1b2b05a476fcc066f4c5fe17` |
| `sweep_raw_round1_pass2.json` | `13b8997883491776458b40f3c9b64b9065fb2dc318eb42affc0f3d04db353875` |
| `HUMAN_REVIEW_REQUIRED_ROUND1.json` | `da85fe04442f2bded639bfede41df311cef01f6a644c61451b99e277be12d599` |
| `sec_cik_map_round1.json` | `f8eebf71ab858aa017b9b0d5debcb5a1eab4eaa94521154f3bfe960258a58b33` |

Where the original and the overlay disagree, **the original records what was done and the overlay records what that evidence may legitimately support.** Both remain visible.

## 2. Correction A — no unsupported canonical disposition

Round 1 wrote `PENDING_OFFICIAL_DATE_UNAVAILABLE` for 23 tickers. That was wrong, and it is superseded.

`PENDING_OFFICIAL_DATE_UNAVAILABLE` is a **canonical protocol disposition**. Using it presupposes a candidate identity — a ticker **and** a fiscal period — so the screening-log schema can be satisfied. Round 1 established no fiscal period for any ticker. Applying a canonical disposition to 23 unnamed fiscal periods asserts a screening decision that was never actually reached.

**Effective correction, for every non-DELL ticker:**

- `proposed_disposition` → **`null`**
- status → **`NO_ENROLLMENT_DECISION_REACHED`**

`NO_ENROLLMENT_DECISION_REACHED` is a **reconnaissance label, not one of the twelve protocol dispositions**. It is deliberately outside that vocabulary so it can never be read as a screening decision. Every such ticker **remains eligible for the next scheduled sweep**. No fiscal period was fabricated to make the schema fit.

24 `UNSUPPORTED_CANONICAL_DISPOSITION` corrections are recorded (23 non-DELL tickers plus DELL's non-protocol marker, which is likewise effectively null with the status `EXISTING_ENROLLED_EVENT_UNCHANGED`).

## 3. Correction B — source-type audit

Every one of the **77** checked URLs was re-classified against the four permitted source types. **18 `SOURCE_TYPE_MISCLASSIFICATION` corrections** were required — I searched the whole evidence set rather than fixing only the known DVN case.

| Effective role | Count | May support a disposition? |
|---|---|---|
| `PERMITTED_SOURCE_OF_RECORD` | 21 | **yes** |
| `RECONNAISSANCE_ONLY` | 26 | no |
| `ACCESS_FAILED` | 18 | no |
| `NAVIGATION_ONLY` | 11 | no |
| `INVALID_OR_UNRELATED` | 1 | no |

### 3.1 The DVN error, and its root cause

`https://www.devonenergy.com/sustainability/environment/spill-prevention` was recorded as `company_ir_events_calendar`. It is **`INVALID_OR_UNRELATED`**: a spill-prevention page is not an investor-relations events calendar and **cannot support any enrollment or "no upcoming event" conclusion**.

Root cause, stated plainly: pass 2's link filter tested `event|investor|calendar|news` as a substring, and **"pr‑event‑ion"** contains "event". A substring filter over issuer navigation is not a source-type judgement. Round 2 must classify by page role, not by URL spelling.

### 3.2 Other misclassifications found by the same search

- **11 company homepages / IR landing roots** (`ABBV`, `BRK-B`, `DELL`, `DVN`, `GME`, `INTC`, `LDOS`, `NCLH`, `NKE`, `SBUX`, `STZ`, `TSLA`, `TTWO`, `UAL` roots) → **`NAVIGATION_ONLY`**. Useful for finding the real calendar; not a source of record.
- **Press-release and news listing indexes** (`INTC`, `NCLH`, `STZ` press-release pages, `BRK-B` news index) → **`RECONNAISSANCE_ONLY`**. A listing is not a specific earnings advisory establishing a date.
- **IR landing pages that are not event calendars** (`AAPL` `/investor-relations/default.aspx`, `ADBE` `/investor-relations.html`) → **`RECONNAISSANCE_ONLY`**. Round 1 never located these issuers' actual events calendars.

## 4. Correction C — the SEC submissions index

`https://data.sec.gov/submissions/CIK{cik}.json` was retrieved for all 24 tickers and recorded as `sec_issuer_filed_submissions_index`.

It is an **official SEC endpoint**, but it is **`RECONNAISSANCE_ONLY`** and **not** a `sec_filing_8k_earnings_date`:

- the index is filing **metadata** — a list, not a filing;
- a specific issuer-filed 8-K becomes a permitted source **only after the exact filing is opened** and is found to state the future earnings date and timing explicitly;
- an accession number, a filing date, or an `Item 2.02` label establishes **no** upcoming candidate;
- **no previous filing metadata may influence enrollment** — that would be reasoning from historical reporting cadence, which the protocol forbids;
- **no filing content was opened in round 1.**

The `recent_8k` metadata is **retained** in the raw artifact (it is part of what round 1 actually did) but is marked **unused** and **prohibited** from the effective round-1 decision. Future sweeps should not store recent-8-K lists when no candidate filing is opened.

## 5. Correction D — the renderer / human-review set, recomputed

The original queue said "ten calendars require rendering" without naming them. Recomputed from the preserved evidence, the real figure is **9 tickers** (11 URLs), and the remaining tickers fall into three genuinely different categories that the original conflated.

### 5.1 Client-rendered official calendars — 9 tickers, 11 URLs

Retrieved HTTP 200 from a permitted events calendar, but the served HTML carried no dated event because the list renders client-side. **Browser rendering or human observation required.**

| Ticker | URL |
|---|---|
| AMZN | `https://ir.aboutamazon.com/events/default.aspx` |
| BKR | `https://investors.bakerhughes.com/events-presentations` |
| CTSH | `https://news.cognizant.com/events` |
| GOOGL | `https://abc.xyz/investor/events/` |
| MSFT | `https://www.microsoft.com/en-us/investor/events/default.aspx` |
| NKE | `https://investors.nike.com/investors/news-events-and-reports/default.aspx` |
| NKE | `…/default.aspx?toggle=news` |
| NKE | `…/?toggle=earnings` |
| QCOM | `https://investor.qualcomm.com/news-events/events` |
| SBUX | `https://investor.starbucks.com/events-presentations/default.aspx` |
| SYK | `https://investors.stryker.com/events-and-presentations` |

### 5.2 Access failures — 8 tickers

**Not** client-rendered, and **not** issuer-confirmed absence. The page could not be read at all.

| Ticker | Result | URL(s) |
|---|---|---|
| ABBV | timeout | `https://investors.abbvie.com/events-and-presentations` |
| BRK-B | HTTP 404 | `https://www.berkshirehathaway.com/news/news.html` |
| DVN | HTTP 404 | `https://investors.devonenergy.com/events-and-presentations` |
| GME | HTTP 404 | `https://investor.gamestop.com/news-events/ir-calendar` |
| LDOS | connection reset | `https://investors.leidos.com/events-and-presentations`, `…/news-events/events` |
| TSLA | HTTP 403 | `https://ir.tesla.com/#quarterly-disclosure`, `https://ir.tesla.com/` |
| TTWO | HTTP 404 | `https://ir.take2games.com/news-events/ir-calendar` |
| UAL | timeout | `https://ir.united.com/news-and-events/events`, `https://ir.united.com/` |

A 404 on a URL **I constructed** is evidence my URL was wrong — not that the issuer publishes nothing.

### 5.3 Issuer explicitly states no upcoming event — 4 tickers

The only category where absence is **issuer evidence** rather than a retrieval gap. Each traces to a genuine permitted events-calendar page.

| Ticker | URL |
|---|---|
| GPN | `https://investors.globalpayments.com/events-and-presentations` |
| INTC | `https://www.intc.com/news-events/ir-calendar` |
| NCLH | `https://www.nclhltd.com/news-media/events` |
| STZ | `https://ir.cbrands.com/news-events/ir-calendar` |

### 5.4 No events calendar ever located — 2 tickers

Pages retrieved fine, but none of them was an events calendar. A **URL-discovery gap** — neither an access failure nor issuer absence.

| Ticker | What was read instead |
|---|---|
| AAPL | `https://investor.apple.com/investor-relations/default.aspx` (IR landing page) |
| ADBE | `https://www.adobe.com/investor-relations.html` (IR landing page) |

### 5.5 DELL — source recheck outstanding

`https://investors.delltechnologies.com/news-events/upcoming-events` and the IR root both timed out. The recheck was **not performed**. `EVT-DELL-FY27Q2-ERN` / `-REG-001` was **not altered, amended or re-verified**, and no contradiction was observed because no source was readable.

**23 non-DELL tickers, bucketed exactly once each: 9 + 8 + 4 + 2 = 23.**

## 6. Correction E — the corrected round-1 conclusion

- **0** enrollable candidates established
- **0** canonical candidate dispositions written
- **0** registry rows written
- **0** human verifications completed
- **1** existing enrolled event — DELL — unchanged
- Round 1 is **reconnaissance evidence**, not a completed canonical screening decision for 23 unnamed fiscal periods
- Unresolved tickers continue to the scheduled **Monday 09:00 America/Chicago** renderer / human sweep

**Retrieval failure is never described as issuer-confirmed absence.** Only the four tickers in §5.3 have issuer-stated absence. The other nineteen have a retrieval limitation, a discovery gap, or an access failure — and the overlay labels each one as what it actually is.

## 7. What did not change

The DELL registry is byte-identical (`71681aa4…f4974`, one verified `REGISTRATION` row). No canonical screening log exists. No registry row, event log, stage marker, dossier or observation was created. The v1.0 protocol files and the v1.1 cadence are untouched, and no unscheduled re-screen was performed.
