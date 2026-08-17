# Structured Earnings Data — Feasibility Probe (Alpha Vantage `EARNINGS`)

`DATA_AUDIT_NOT_OUTCOME_STUDY` · `sector: SEMICONDUCTORS` · `modeling_authorized: false`

**No return, price, price reaction, volume, option, strategy or trading outcome was read or
computed at any point in this pass.** No SUE, no information–price gap, no post-earnings drift, no
bootstrap, no coefficient, no portfolio return, no trade.

## Decision

# `STRUCTURED_EARNINGS_COVERAGE_INSUFFICIENT`

Seven of the eight prespecified feasibility gates pass. The crosswalk gate fails at **0.6719**
against a required **0.90**, and — as in the extraction phase it was meant to replace — the binding
constraint turns out to be **the SEC index's own parse coverage, not the provider's data**.

## 1. What was retrieved

All ten tickers, complete retrieval, no ticker left throttled.

| | |
|---|---|
| Tickers requested / retrieved | 10 / **10** |
| Raw quarterly records returned | 1153 |
| Records inside 2018-01-01 … 2025-12-31 (by `reportedDate`) | **320** |
| Complete records (`reportedEPS`, `estimatedEPS`, `surprise` all numeric) | **320** |
| Malformed records refused | 0 |
| Duplicate identities refused | 0 |

The first attempt returned only 5 of 10 tickers. Those five responses were 369-byte
**rate-limit notices**, not empty data. A throttle notice is a transport failure, so it is never
counted as a coverage finding: the retrieval path now retries with backoff, refuses to cache any
body that fails the provider-error check, and the run reports `DATA_ACCESS_BLOCKED` rather than a
coverage verdict if any ticker is still throttled at the end. The poisoned cache entries were
discarded and re-fetched.

### Completeness by year and ticker

| Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| Complete records | 40 | 40 | 39 | 41 | 40 | **40** | **40** | **40** |

Every one of the ten tickers returns exactly **32** complete records (8 years × 4 quarters):
NVDA, AMD, INTC, QCOM, AVGO, MU, TXN, AMAT, LRCX, KLAC. Coverage is uniform and has no gaps.

## 2. Every prespecified gate

| Gate | Value | Required | |
|---|---|---|---|
| g1 tickers with complete records | 10 | ≥ 8 | pass |
| g2 unique complete records 2018–2025 | 320 | ≥ 200 | pass |
| g3 complete records 2023–2025 | 120 | ≥ 90 | pass |
| g4 complete records in each of 2023 / 2024 / 2025 | 40 / 40 / 40 | ≥ 25 each | pass |
| **g5 uniquely crosswalked share of complete records** | **0.6719** | **≥ 0.90** | **fail** |
| g6 internal surprise-arithmetic agreement | **1.0000** (320/320) | ≥ 0.99 | pass |
| g7 unresolved duplicate identities | 0 | = 0 | pass |
| g8 terminology distinguishes vendor EPS from SEC GAAP diluted EPS | true | true | pass |

No gate was lowered, reinterpreted, recomputed differently or marked passed. The `$0.01` tolerance
is the frozen one and no other tolerance was tried.

## 3. Internal arithmetic: the provider is self-consistent

`reportedEPS − estimatedEPS ≈ surprise` holds within `$0.01` on **320 of 320** records — **100.00%**,
with zero failures. Whatever the provider's EPS *means*, its three numeric fields are mutually
consistent.

## 4. Why the crosswalk gate fails — and what it is really measuring

The frozen crosswalk requires **both** a fiscal-period match (±5 days) **and** a report-date match
(±3 days) against the SEC Item 2.02 event index, with equidistant ties refused rather than guessed.

| | |
|---|---|
| Complete provider records | 320 |
| Uniquely crosswalked | 215 (all direct; 0 needed the tie-breaker) |
| Ambiguous, refused | **0** |
| No candidate in window | 105 |
| **Crosswalk rate** | **0.6719** |

The SEC index holds **306** Item 2.02 events, but `fiscal_period_end` is populated for only **267**
of them — it exists only where the hand-built parser successfully *dated* the filing. Because the
frozen rule requires a fiscal-period match, it inherits that parser's coverage:

> **Structural ceiling on the frozen crosswalk rate = 267/320 = 0.8344**, below the required 0.90.

So g5 was **unreachable on this index before the first provider record was examined** — the same
class of defect the extraction phase found in its own reference design, and for the same reason: a
matching key that only exists where the parser already succeeded.

### Diagnostic — explicitly *not* the gate

Matching on **report date alone** (±3 days) against the **full 306-event** index:

| | |
|---|---|
| Uniquely matched | **300 of 320** |
| Ambiguous | **0** |
| No candidate | 20 |
| Rate | **0.9375** |

**This diagnostic is recorded, not substituted.** It is not a gate, it did not become the decision,
and g5 stands as computed at 0.6719. It is reported because it separates two very different claims:
the provider's records *do* correspond to real Item 2.02 events at 93.75% with zero ambiguity; what
fails is the frozen rule's dependence on a parser-derived fiscal date.

## 5. Alpha Vantage versus SEC-validated EPS

Compared on the **139** events that uniquely crosswalk to an SEC event whose `audit_status` is
`validated`:

| | |
|---|---|
| Overlapping events | **139** |
| Match within `$0.01` | **8** (**5.76%**) |
| Median absolute difference | **$0.26** |
| Largest discrepancy | LRCX 2022-09-30: provider **1.04** vs SEC **10.39** |

**The differences are not random error.** They decompose cleanly into two mechanisms:

**(a) Retroactive split restatement.** Every ticker that later executed a 10-for-1 split carries its
whole history on the *post-split* share basis, while the SEC exhibit carries the as-announced
figure. Median provider/SEC ratio by ticker:

| LRCX | KLAC | NVDA | AVGO | | AMAT | TXN | MU | QCOM | AMD |
|---|---|---|---|---|---|---|---|---|---|
| **0.1033** | **0.1074** | **0.1645** | **0.2877** | | 1.0414 | 1.0357 | 1.0719 | 1.3793 | 1.6364 |

28 pairs sit in the split signature band [0.085, 0.115].

**(b) GAAP versus adjusted.** Among the 45 near-parity pairs (ratio in [0.85, 1.15]) only 8 match
within `$0.01`; median absolute difference **$0.05**, and there is one outright **sign
disagreement** — a GAAP loss reported by the provider as a profit. That is the signature of an
adjusted / non-GAAP figure, not a parsing error on either side.

Neither source was corrected by the other, and later XBRL was **not** used to overwrite either.
Per the frozen design, EPS agreement is **descriptive and never a gate**.

## 6. What the provider actually represents

**Vendor-defined, restated `reportedEPS` — not SEC-validated GAAP diluted EPS.** Any surprise
construct built on this source must be called

# `VENDOR_DEFINED_REPORTED_EPS_SURPRISE`

and never a GAAP surprise, analyst surprise, consensus miss, fair value or proven mispricing.

## 7. Point-in-time provenance

# `POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED`

Alpha Vantage's documentation describes the `EARNINGS` fields but publishes **no** guarantee that
historical `estimatedEPS` is the contemporaneous consensus preserved as of the announcement — no
point-in-time, as-of-announcement or non-restatement claim appears for that endpoint.

The audit also found **empirical counter-evidence**: historical `reportedEPS` is demonstrably
*restated* rather than preserved as announced, since the split-adjusted histories above could only
have been produced after the splits occurred. That does not by itself prove `estimatedEPS` is
restated too, but it removes any basis for assuming the series is point-in-time.

**This limitation is recorded, not concealed and not resolved by assumption.**

## 8. Reading of the result

The provider is *strong* exactly where the hand-built parser was weak — uniform 32-quarter coverage
for all ten tickers, 40 records per year, zero duplicates, zero malformed records, and 100%
internal arithmetic consistency. It is *weak* exactly where this study needs discipline: its EPS is
vendor-defined and restated, and its estimate series carries no point-in-time guarantee.

The failing gate does **not** show the provider's coverage is inadequate; under the frozen rule it
could not have exceeded 0.8344 regardless of the provider. The honest statement is that
**this crosswalk design cannot certify this source**, and the frozen rule returns
`STRUCTURED_EARNINGS_COVERAGE_INSUFFICIENT`.

A future pass wanting to certify the source would need to freeze a crosswalk that does not depend on
a parser-derived fiscal date — *before* looking at its results. That is a separate task and is not
authorized here.

## 9. Confirmation

- **No return** and **no price**, price reaction, volume, option, model or trading result was read
  or computed at any point in this pass.
- No prohibited outcome column exists in the sanitized panel; only the seven permitted fields.
- The API key was read only from `ALPHAVANTAGE_API_KEY` and never printed, logged, serialized,
  committed or placed in a recorded URL. Every recorded URL is redacted.
- Raw provider bodies are cached **repository-external** and are not committed. Each is recorded
  with retrieval timestamp, byte count, SHA-256, HTTP status and redacted URL.
- **Passing feasibility does not authorize modeling — and this pass did not pass.** The next task
  would freeze any outcome design separately.

Reproduce: `python tools/run_structured_earnings_feasibility.py`
Verify: `python test_structured_earnings_feasibility.py`
