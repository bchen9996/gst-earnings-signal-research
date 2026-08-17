# Semiconductor EPS–Price Absorption — Extraction Phase Result

`EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY` · `sector: SEMICONDUCTORS` ·
`google_trends_used: false` · `analyst_consensus_used: false` ·
`later_xbrl_used_for_prediction: false`

## Decision

# `EXTRACTION_NOT_RELIABLE`

The question — whether a mismatch between standardized unexpected GAAP diluted EPS and the market's
first full-session reaction predicts subsequent semiconductor drift — **was not tested.** Extraction
stopped at the Phase-1 gate. **No return was inspected**, no SUE was constructed, no gap was formed,
no model was fitted, no bootstrap was drawn and no trade was simulated.

## Universe and design

Ten frozen tickers in fixed order — NVDA, AMD, INTC, QCOM, AVGO, MU, TXN, AMAT, LRCX, KLAC —
benchmark SMH, 8-K Item 2.02 events 2018–2025, outer test years 2023/2024/2025. The complete design
is in the `FROZEN_DESIGN` block at the top of `tools/run_semiconductor_eps_absorption.py`. Because
the extraction gate failed, that block was never promoted to an outcome commit.

## 1. Extraction counts

| Quantity | Value |
|---|---|
| Item 2.02 8-K events, 2018–2025 | 306 |
| Located earnings-release exhibits | 250 |
| GAAP diluted EPS extracted | **123** |
| Validated against later 10-Q XBRL | **92** |
| Contradicted by later XBRL | **0** |
| No reference available in window | **31** |
| Duplicate event identities refused | 0 |

## 2. The three gate quantities

| Gate | Value | Required | |
|---|---|---|---|
| `reference_coverage` = (validated + contradicted) / extracted | **0.7480** | ≥ 0.80 | **fail** |
| `conditional_precision` = validated / (validated + contradicted) | **1.0000** | ≥ 0.95 | **pass** |
| `usable_event_coverage` = usable / located exhibits | **0.2440** | ≥ 0.60 | **fail** |
| Tickers with usable events | **4** | ≥ 8 | **fail** |
| Usable events | **61** | ≥ 160 | **fail** |
| OOS events | **32** | ≥ 90 | **fail** |
| OOS per year (2023 / 2024 / 2025) | **12 / 10 / 10** | ≥ 25 each | **fail** |
| Later-XBRL values used as predictive inputs | **0** | 0 | **pass** |

## 3. Manual structural spot audit — fixed development sample

Author-side structural record for the outcome-blind sample (ascending SHA-256 of
`SEMICONDUCTOR_EPS_PARSER_DEV|ticker|fiscal_period_end|accession`, 2 per ticker where available):
**17 events across 9 tickers**. This is the author's own record and is **not** an independent human
review.

| Status | Count |
|---|---|
| Validated (exact statement, row, column, value agree with later XBRL within $0.01) | **4** |
| Parsed but no later-XBRL reference in window | **4** |
| Not extracted (parser refused) | **9** |
| Contradicted | **0** |

Per-event selections are recorded in `extraction_validation_v1.0.json` under
`structural_spot_audit`, each with the selected table index, row index, row label, column label,
parsed value and reference. Examples: AMD `Diluted earnings per share` /
`Three Months Ended June 28,2025` → 0.54, reference 0.54; KLAC `Diluted` → 4.28, reference 4.28.

## 4. What actually failed

**The failure is recall, not accuracy.** Every extracted value that had a later-XBRL reference matched
it — 92 of 92, zero contradictions, conditional precision **1.0000**. Five of ten filers yield
**nothing at all**:

| Ticker | Extracted | | Ticker | Extracted |
|---|---|---|---|---|
| AMD | 31 | | NVDA | **0** |
| AMAT | 30 | | INTC | **0** |
| LRCX | 30 | | AVGO | **0** |
| KLAC | 23 | | MU | **0** |
| QCOM | 9 | | TXN | **0** |

Only four tickers survive to a usable panel, against a required eight. Three structural defects were
found and fixed on the development sample during the budget — a date regex that could not read
`June 29,2024` written without a space; year-only header rows being misclassified as data, which
stripped the year off every column heading; and financial statements filed in a sibling exhibit
rather than 99.1. Each fix raised recall (33 → 123 extracted). The five remaining filers use a
consolidated statement layout the structural acceptance test still refuses, and identifying those
layouts was not achievable inside the 60-minute budget.

## 5. What was not run

Because the gate failed: no `FROZEN_DESIGN` outcome commit, no SUE, no `eps_price_gap`, no Model B or
Model C, no calendar-block bootstrap, no five-day or twenty-day evaluation, no SPY sensitivity, no
trading test. Fitting a ridge on 61 events across 4 tickers with 10–12 events per test year would
have produced numbers with no evidential value.

Consequently items 5–8 of the requested reporting — Model B vs C MAE, bootstrap interval, IC,
twenty-day and SPY sensitivities, gap coefficient sign and stability, trading results — **have no
values, by design.**

## 6. Discipline held

Gates were not loosened after the aggregate rates were seen. No extracted value was hand-corrected.
No return was used to choose a parsing rule, and no post-entry return was computed at any point.
Parser debugging happened only on the fixed development sample. The later 10-Q XBRL served purely as
an audit reference: it never selected, replaced or altered an Exhibit value and never entered a
feature.

SUE is defined here as a **seasonal historical-expectation** surprise built from the company's own
previously announced GAAP diluted EPS. Nothing in this branch is called an analyst surprise,
consensus miss, fair value, intrinsic value, proven mispricing or causal underreaction.

## 7. Most important limitation

**Semiconductor earnings releases are not structurally uniform enough for a single conservative table
parser, and the binding constraint is coverage rather than correctness.** Because conditional
precision is already 1.0000, the correct successor is per-filer structural templates for the five
refused layouts — not looser row or table matching, which would trade away the one property that is
currently perfect. Until at least eight of the ten filers parse, this hypothesis cannot be tested on
this universe, and no claim about semiconductor EPS absorption follows from this branch in either
direction.

Reproduce: `python tools/run_semiconductor_eps_absorption.py`
