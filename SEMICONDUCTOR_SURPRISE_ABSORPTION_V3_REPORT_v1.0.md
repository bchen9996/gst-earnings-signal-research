# Semiconductor Information–Price Gap — Outcome Study (v3)

`EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY` · `is_gst_test: false` ·
`surprise_construct: VENDOR_DEFINED_REPORTED_EPS_SURPRISE` ·
`POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED`

**Question.** Among semiconductor earnings announcements, does the discrepancy between a
vendor-defined earnings surprise and the market's initial abnormal reaction predict subsequent
abnormal return?

**Answer: the study stopped at the first mandatory gate.**

## Decision

# `SURPRISE_DOES_NOT_EXPLAIN_INITIAL_REACTION`

The information–price gap was **never constructed**, Stage 2 **never ran**, and **no trading was
simulated**. Under the frozen design a gap is meaningless unless surprise first explains some part
of the initial reaction, and that gate failed.

## 1. What this is, and what it is not

This is **exploratory retrospective development**, **not preregistered** confirmation, not
production-ready, and not investable. It is **not a GST test** — no Google Trends series was read.

The surprise series is `VENDOR_DEFINED_REPORTED_EPS_SURPRISE`. It is **not** a GAAP earnings
surprise, **not** an SEC-validated EPS surprise, and **not** a guaranteed contemporaneous-consensus
vintage.

The predecessor structured-source crosswalk gate **failed at 0.6719 against a required 0.90 and
remains failed**. It was not re-scored, relaxed or retried. This is a *successor* design, created
after inspecting identity and coverage information and **before** inspecting any outcome; the
exact-date crosswalk rule was motivated by the already-recorded identity-only diagnostic, which used
no outcome of any kind.

## 2. Sample

`surprisePercentage` is the primary field because a proportional split restatement scales
`reportedEPS`, `estimatedEPS` and `surprise` together and cancels in the ratio. **Verified
mechanically on all 320 records: 320/320 agree, largest deviation 0.0000 pp, invariance holds.**
Raw `reportedEPS` and `estimatedEPS` are never primary model features.

| | |
|---|---|
| Alpha Vantage records considered | 320 |
| Excluded — no exact-date SEC match | 22 |
| Excluded — ambiguous match | **0** |
| **Uniquely matched events** | **298** |
| Tickers | **10** |
| OOS events 2023–2025 | **116** (39 / 38 / 39) |
| Duplicate identities | **0** |

Every sample-gate component passes (≥8 tickers, ≥240 events, ≥90 OOS, ≥25 per year, zero
duplicates). Events by year: 2018‑29, 2019‑35, 2020‑37, 2021‑41, 2022‑40, 2023‑39, 2024‑38, 2025‑39.

### Timing exclusions

| Category | Count |
|---|---|
| Accepted ≥ 16:00 ET → next session | **296** |
| Accepted < 09:30 ET → same session | **2** |
| Accepted 09:30–16:00 ET → **excluded** | **0** |

No intraday release survived because none occurred — semiconductor releases in this universe are
uniformly after the close. Prices are **split- and dividend-adjusted** closes; the discontinuity
audit found **zero** daily moves ≥ 40% across all 11 series (2,113 sessions each), so no unadjusted
split entered the sample.

## 3. Stage 1 — does surprise explain the initial reaction?

Model B = intercept + ticker indicators. Model C = B + transformed vendor-defined surprise.
Metric: MAE of the initial abnormal reaction, pooled over the three OOS folds (n = 116).

| | Model B | Model C |
|---|---|---|
| MAE | 0.052506 | **0.051203** |
| RMSE | 0.065017 | 0.063565 |
| **MAE improvement** | | **+2.482%** |
| OOS R² (Model C) | | 0.0642 |

| Year | n | MAE B | MAE C | Improvement | C better |
|---|---|---|---|---|---|
| 2023 | 39 | 0.047902 | 0.046594 | +2.731% | yes |
| 2024 | 38 | 0.065591 | 0.065225 | +0.558% | yes |
| 2025 | 39 | 0.044361 | 0.042150 | +4.984% | yes |

Pooled OOS Spearman (transformed surprise vs initial reaction) = **+0.1352** (p = 0.148). Mean
coefficient on transformed surprise = **+0.0114**. Selected ridge alphas came from the frozen grid
only: {0.0, 10.0}.

### Every Stage-1 gate

| # | Gate | Result | |
|---|---|---|---|
| 1 | pooled MAE improvement ≥ 1.0% | **+2.482%** | **pass** |
| 2 | 95% bootstrap interval for (MAE_B − MAE_C) entirely above zero | **[−0.000727, +0.003170]** | **FAIL** |
| 3 | Model C beats Model B in ≥ 2 of 3 OOS years | **3 of 3** | **pass** |
| 4 | OOS relationship has the expected positive sign | **+0.1352** | **pass** |

**Three of four gates pass. The binding failure is the bootstrap interval**, which straddles zero:
2,000 deterministic moving-block draws over 36 four-week calendar blocks, seed 20260817, mean
difference +0.001271.

The honest reading: the surprise term has the **economically expected sign**, improves MAE in
**every one of the three OOS years**, and improves it by 2.48% pooled — but at 116 OOS events that
improvement is **not statistically distinguishable from zero**. The label
`SURPRISE_DOES_NOT_EXPLAIN_INITIAL_REACTION` is the frozen label for a Stage-1 failure; the precise
finding is *not demonstrated*, not *demonstrated absent*.

### Raw results by ticker (frozen sensitivity S5)

| Ticker | n | Improvement % | Spearman | Mean AR0 % |
|---|---|---|---|---|
| INTC | 12 | +11.73 | +0.491 | −3.84 |
| AMD | 12 | +9.07 | +0.365 | −2.46 |
| NVDA | 12 | +5.77 | +0.504 | +3.19 |
| KLAC | 10 | +5.26 | +0.273 | +0.51 |
| QCOM | 12 | +2.85 | +0.189 | −2.69 |
| AMAT | 10 | +0.95 | +0.673 | −2.81 |
| AVGO | 12 | −0.86 | −0.049 | +2.40 |
| LRCX | 12 | −1.93 | −0.168 | +1.62 |
| TXN | 12 | −3.21 | −0.098 | −1.54 |
| MU | 12 | −5.73 | +0.091 | −0.07 |

**Model C helps in only 6 of 10 tickers** and actively hurts in four. Seven of ten Spearman
correlations are positive. No single company or year drives the pooled result — which is precisely
why it is weak rather than concentrated. Per-year Spearman: 2023 +0.220, 2024 +0.056, 2025 +0.141.

## 4. What did not run

| Item | Status |
|---|---|
| Information–price gap | **never constructed** |
| Stage 2 (Models D vs E) | **not run** |
| CR2/BRL inference on the gap | **not run** |
| Trading simulation | **not run** |
| Sensitivities S1–S4 | **unavailable** — all are defined on the gap |
| Sensitivity S5 (by ticker and year) | reported above |

No strategy was manufactured from a failed predictive gate. Sensitivities that cannot exist are
reported as unavailable rather than approximated or gate-lowered.

## 5. Strongest findings in both directions

**Strongest positive finding.** The vendor-defined surprise carries the economically expected
positive sign and reduces out-of-sample MAE of the initial reaction in **all three** OOS years
(+2.73%, +0.56%, +4.98%; pooled +2.48%), with pooled Spearman +0.135 and OOS R² 0.064. Three of the
four Stage-1 gates pass. That is a directionally coherent, non-trivial signal.

**Strongest falsifying finding.** The 95% moving-block bootstrap interval for the MAE gain is
**[−0.000727, +0.003170]** — it contains zero, so the improvement is not distinguishable from noise
at this sample size. Model C **degrades** MAE for 4 of 10 tickers (MU −5.7%, TXN −3.2%, LRCX −1.9%,
AVGO −0.9%), and the pooled Spearman is insignificant (p = 0.148). The 2024 improvement is
+0.56%, well under the 1% threshold on its own.

## 6. Limitations

- **Vendor-defined EPS.** `reportedEPS` from this provider is vendor-defined and demonstrably
  **restated** — it is not SEC-validated GAAP diluted EPS. The predecessor audit found only 8 of 139
  overlapping events matching within $0.01, with differences decomposing into retroactive 10-for-1
  split restatement and a GAAP-versus-adjusted definition gap.
- **Unguaranteed historical estimate vintage.** Alpha Vantage publishes no guarantee that historical
  `estimatedEPS` is the contemporaneous consensus preserved as of the announcement.
  `POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED` is recorded and is **not resolved by
  assumption**. If those estimates were revised after the fact, the surprise is contaminated in an
  unknown direction, and the Stage-1 result cannot be cleanly interpreted as a
  reaction-to-news relationship. Using `surprisePercentage` neutralizes *split* restatement — it
  does **not** neutralize *estimate-vintage* revision.
- **Power.** 116 OOS events across 36 four-week blocks is a small sample for a bootstrap interval on
  an MAE difference. Failing gate 2 is at least as consistent with low power as with no effect.
- **Sector and period.** Ten large-cap semiconductor names, 2018–2025, one benchmark (SMH).

## 7. Integrity confirmation

No gate, model, horizon, cost or feature was changed after outcomes were viewed. The frozen design
was committed at `9a9f642`, **before any price or return file was opened**. One transport amendment
was made *before* any outcome existed and is recorded in the design block: `yfinance` could not
complete a TLS handshake in this environment and Alpaca returned HTTP 401, so the **same Yahoo
adjusted-close series** was retrieved over `urllib` instead — same provider, same adjustment, same
numbers, different HTTP client only.

The `stage1_breakdown` section was added after Stage 1 failed. It is **descriptive reporting**
required by frozen sensitivity S5, defines no gate, and changes no model, horizon, cost or feature.

Reproduce: `python tools/run_semiconductor_surprise_absorption_v3.py`
Verify: `python test_market_response_semiconductor_surprise_absorption_v3.py`
