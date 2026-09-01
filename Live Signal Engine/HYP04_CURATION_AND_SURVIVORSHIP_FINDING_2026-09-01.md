# Five draft edges, and four companies that are gone

**Dated finding, 2026-09-01.** Append-only.

**Artifacts:**
[`HYP04_LINKAGE_ROWS_DRAFT_2026-08-31.csv`](HYP04_LINKAGE_ROWS_DRAFT_2026-08-31.csv) ·
[`HYP04_PEER_NAME_SEARCH_2026-09-01.json`](HYP04_PEER_NAME_SEARCH_2026-09-01.json)

> **Gate CLOSED, C4 MET, four denials, eligible-event count zero.** Nothing here
> is evidence about supply-chain transmission. No edge has been curated.

---

## 1. Owner decisions, 2026-09-01

Three decisions were taken, with the framing that the price source is **not on
the critical path**: the curated map caps the sample at 54 events against a
floor of 193, so a source chosen today would be exercised on a sample that
cannot meet C2 regardless.

1. **The peer price source is DEFERRED** until curation lifts the ceiling. No
   registry v1.11. The measured bias (109 of 270 incremental events behind
   unreachable names) stays on record for when the decision is taken.
2. **Draft rows prepared for owner review**, with the judgement fields blank.
3. **The unreachable names searched against SEC's fuller record.**

## 2. Five draft edges, and why they cannot do anything

`HYP04_LINKAGE_ROWS_DRAFT_2026-08-31.csv` holds five candidate edges — JBL→CSCO,
JBL→AAPL, JBL→BB, NVDA→MSFT, INTC→HPQ — the ticker-resolved candidates that
passed the lineage audit and are not already in the map. Curating all five would
take reach from 54 to 215.

Every field derivable from the filings is filled: relationship type from the
disclosure's own `direction`, the accession, the concentration percentage and
its basis, the EDGAR URL, the earliest disclosing filing date. Five fields are
**blank** — `confidence`, `date_confidence`, `curated_by`, `curated_date`,
`review_status` — because no derivation can supply them.

**That is the safety property, and it is the loader's, not a convention.** All
five are in `curated_linkage.REQUIRED_FIELDS`. Measured against the real file
through the real loader:

```
header_matched=True  rows_seen=5  rows_rejected=5  edges_usable=0
uses_placeholder_linkage=True     <- C5 stays shut
```

The header is accepted on purpose, so a completed row can be pasted into the
map. Every row is then rejected for the blanks. The suite asserts this against
the generated file and carries the control: the same row **with** the five
fields filled loads as one edge, so the rejection is the blanks and not a
malformed row.

Two MCK→CVS candidates were **not** drafted. Both sit at as-of dates later than
the existing curated edge, so they add nothing, and the loader rejects duplicate
anchor-peer pairs anyway.

## 3. The missing registrants were found. None of them trades.

`resolve_counterparty` matches SEC's list of companies filing today, so 27
counterparty names could not resolve at all. EDGAR's **company search** sees
former names that list drops — "Dell Computer" returns the registrant now named
DELL INC, carrying `DELL COMPUTER CORP` until 2003-07-22.

24 names searched, one request each. The search only **nominates**: acceptance
is `peer_lineage.assess` against the registrant's own submissions record, the
same test that rejected INGM.

| outcome | names |
|---|---|
| registrant identified, **no current ticker** | **5** (4 distinct) |
| hits found, none filing under that name then | 8 |
| no registrant matched | 11 |
| **newly tradeable** | **0** |

The identified registrants: **DELL INC** (CIK 826083), **INGRAM MICRO INC**
(CIK 1018003), **TECH DATA CORP** (CIK 790703), **FOOT LOCKER INC**
(CIK 850209). **145 anchor events sit behind them.**

Not one still trades. The survivorship gap is no longer an inference about the
method — it is a list of named, confirmed companies that are gone.

## 4. The Ingram Micro loop closes

Three findings now meet on one name:

- Exact matching resolved ADBE's 2006 "Ingram Micro" onto **INGM** — because
  the normaliser stripped "Holding". Fixed 2026-08-31.
- The lineage control proved INGM's registrant (CIK **1897762**) first filed
  **2022-04-13**, sixteen years after the disclosure.
- The name search now identifies the registrant ADBE actually named: CIK
  **1018003**, filing in 2006 as `INGRAM MICRO INC` — **and it has no current
  ticker.**

The wrong answer was caught, the right one was found, and the right one is
untradeable. That is the whole survivorship problem in a single counterparty.

## 5. A defect in this work, found and fixed before publishing

The first live run lost **8 of 24 names** to HTTP 503s and read timeouts from
`browse-edgar`, and recorded every one as `no_registrant_matched` — reporting an
endpoint outage as a finding about those companies, across 249 events of sample.
That is data availability deciding a result.

Fixed: `STATUS_SEARCH_FAILED` is now a distinct outcome checked **before** the
no-hits branch (a failed search also has zero candidates, which is exactly how
it fell through), searches retry three times with backoff at 1s spacing, and the
artifact counts unanswered names separately and excludes them from every
conclusion. The re-run answered all 24 with **zero** errors.

The test carries the control: the same inputs without the failure flag must
still produce the negative, so the two are genuinely distinguished.

## 6. What this does NOT do

- **It curates nothing.** Five draft rows exist and all five are inert.
- **It selects no price source**, by decision.
- **It does not move C2 or C3**, which move together or not at all.
- **215 is a ceiling on an uncurated queue**, not a met threshold.
- **It measures no transmission.**

## 7. Still open

- **The five draft rows**, awaiting the five owner fields.
- **The peer price source**, deferred by decision until the ceiling clears 193.
- **145 events** behind identified-but-untradeable registrants, and 11 names no
  search could match. Both are now documented rather than inferred.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
