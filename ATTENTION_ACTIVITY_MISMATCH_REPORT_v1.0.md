# Attention–Activity Mismatch: Does Search Help Only When Trading Activity Says It Hasn't Landed?

`EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY`. Not HYP-01 confirmation, not prospective collection.

> **What was measured.** A **search–trading-activity mismatch proxy** — `search_z`, `volume_z`, and
> their interaction. "Unabsorbed attention" is an **interpretation**, not a measurement. Nothing here
> establishes market absorption, causality, or investability. Google Trends remains a **candidate**
> proxy: F5 construct validity is open, so it is not validated investor attention.
>
> **Point-in-time caveat.** Historical Google Trends downloads are **not point-in-time vintages**.
> Google rescales to the requested window and may revise sampling, so the series used here may differ
> from what was observable at the time.

## Decision

# `RETIRE_GST_AS_TRADING_SIGNAL`

Neither frozen gate passed. **This was the final conditional GST trading test.** The recommendation is
to retire GST as a trading signal rather than launch another adjacent pilot.

## Sample

24 tickers (the full locked universe), **208 panel weeks**, 2022-01-10 → 2025-12-29, **4,992** panel
rows. Out-of-sample: **157 weeks, 3,768 ticker-weeks**. Zero duplicate `(ticker, target_week)` rows.

| Gate | Required | Observed |
|---|---|---|
| Tickers | ≥ 18 | **24** |
| Common OOS weeks | ≥ 100 | **157** |
| OOS ticker-weeks | ≥ 1,800 | **3,768** |

Folds: train ≤2022 → test 2023; train ≤2023 → test 2024; train ≤2024 → test 2025. Never randomly split.

## Primary test — volatility, `log(next-week realized volatility)`

| Model | MAE | RMSE | OOS R² |
|---|---|---|---|
| **B** (no search) | **0.420367** | 0.543607 | 0.23945 |
| **C** (+ `search_z`, `search_z × volume_z`) | 0.420497 | 0.543400 | 0.24003 |

**MAE change B → C: −0.0309%** — C is marginally *worse* on the primary metric.

Paired block bootstrap on `loss_B − loss_C` (2,000 draws, 4-week calendar blocks, all tickers
retained within each sampled week, seed 20260817): mean **−0.00013**, **95% CI [−0.001102,
+0.001084]** — straddles zero.

| Test year | B MAE | C MAE | C better? |
|---|---|---|---|
| 2023 | 0.408323 | 0.406841 | yes |
| 2024 | 0.401273 | 0.401223 | yes |
| 2025 | 0.451872 | 0.453798 | no |

**Gates: 1.0% MAE improvement — FAIL (−0.03%). CI entirely above zero — FAIL. Beats in ≥2 of 3 years —
PASS (2/3).** One of three met; the specification does not pass.

Note the tension worth reporting: C is very slightly better on **RMSE and OOS R²** while losing on
**MAE**, and it wins two of three years by margins in the fourth decimal place. That is what a
null looks like at this sample size, not a suppressed effect.

## Secondary test — return direction, `sign(stock − SPY)`

| Model | Log loss | Brier | AUC | Accuracy |
|---|---|---|---|---|
| **Intercept-only null** (training prevalence) | **0.694786** | **0.250819** | — | 0.4862 |
| **R0** (no search) | 0.704603 | 0.255449 | 0.5032 | 0.5130 |
| **R1** (+ search and its three interactions) | 0.707252 | 0.256625 | 0.5019 | 0.5064 |

**R1 is worse than R0, and both are worse than the intercept-only null.** Paired block bootstrap on
`loss_R0 − loss_R1`: mean **−0.002650**, **95% CI [−0.004151, −0.001369]** — entirely *below* zero,
i.e. adding search reliably *hurt*.

| Test year | R0 log loss | R1 log loss | R1 better? |
|---|---|---|---|
| 2023 | 0.723705 | 0.729480 | no |
| 2024 | 0.699427 | 0.701663 | no |
| 2025 | 0.690776 | 0.690722 | yes |

**Gates: beats on log loss — FAIL. CI above zero — FAIL. AUC > 0.52 — FAIL (0.5019). Beats in ≥2 of 3
years — FAIL (1/3).** All four fail.

**No portfolio simulation was run.** The return gate did not pass, and a strategy is not manufactured
from the volatility result.

## Prespecified interaction terms — signs only, no causal reading

Standardized coefficients, averaged across folds. Descriptive.

| Model | Term | Mean coef | Sign | Same sign in every fold |
|---|---|---|---|---|
| Volatility C | `search_z` | −0.025553 | negative | yes |
| Volatility C | `search_z × volume_z` | +0.020338 | positive | yes |
| Return R1 | `search_z` | −0.043620 | negative | yes |
| Return R1 | `search_z × prior_1w_return` | −0.001724 | negative | **no** |
| Return R1 | `search_z × volume_z` | −0.048835 | negative | yes |
| Return R1 | `search_z × volume_z × prior_1w_return` | −0.052388 | negative | **no** |

The mismatch interaction in the volatility model is positive and sign-stable, which is the direction
the hypothesis anticipated — but it is small and **did not produce out-of-sample gains**. A sign-stable
coefficient inside a model that loses on the prespecified metric is not evidence of a usable signal.
The two return interactions carrying the mismatch idea most directly are **not** sign-stable.

## Sensitivity checks (robustness only, not alternative primaries)

| Check | n | B MAE | C MAE | Improvement | C better? |
|---|---|---|---|---|---|
| Exclude known earnings weeks | 3,647 | 0.418406 | 0.418541 | −0.032% | no |
| Drop 5 most lexically ambiguous queries (`BRK-B, GME, GOOGL, BKR, DELL`) | 2,983 | 0.421234 | 0.422192 | −0.227% | no |
| Winsorize predictors at training 1st/99th pct | 3,768 | 0.417584 | 0.417671 | −0.021% | no |

All three agree with the primary result. The earnings-week exclusion uses the existing frozen C5
population and therefore covers only the tickers in that artifact — 121 rows excluded; partial
coverage is disclosed rather than papered over.

## What this does and does not say

- **Search alone** (`search_z`): no out-of-sample gain on either target.
- **The search–volume interaction**: sign-stable in the volatility model, but with no measurable
  out-of-sample benefit under the frozen gates.
- **Volatility prediction**: the non-search baseline already attains OOS R² ≈ 0.24; search adds
  nothing detectable at this sample size.
- **Return-direction prediction**: nothing beats a training-prevalence intercept; adding search makes
  it reliably worse.
- **Statistical evidence**: intervals are tight and centered on or below zero — this is a bounded null
  for these specifications, not an underpowered result.
- **Economic usefulness**: none demonstrated; no strategy was simulated.

No causality, market absorption, investability, or universal uselessness of Google Trends is claimed.
This tests two prespecified specifications on one locked universe over 2022–2025.

## Recommendation

Under the frozen gates the answer is negative. **GST should now be retired as a trading signal.** The
conditional-mismatch framing was the strongest remaining version of the trading hypothesis, and it did
not survive its own prespecified criteria. Launching another adjacent pilot would be a search over
specifications, not new evidence.

Reproduce: `python tools/run_attention_activity_mismatch.py`
