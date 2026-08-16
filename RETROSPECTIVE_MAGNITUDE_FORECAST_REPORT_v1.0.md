# Does GST Improve Out-of-Sample Prediction of Absolute Gap Size?

`RETROSPECTIVE_DEVELOPMENT_ONLY`. Confirms nothing about HYP-01. **No directional trading or
profitability is evaluated anywhere in this study.**

## Answer

# `GST_DOES_NOT_IMPROVE_MAGNITUDE_FORECAST`

On the primary metric, adding GST does not reduce out-of-sample error.

| Model | MAE | RMSE | OOS R² vs intercept |
|---|---|---|---|
| **A.** Intercept-only historical mean | 3.6673 pp | 4.7643 pp | 0.000 |
| **B.** Baseline, no GST | **3.6284 pp** | 4.6844 pp | 0.03325 |
| **C.** Baseline + pre-event GST z | **3.6299 pp** | **4.6395 pp** | **0.05167** |

**MAE change B → C: −0.0413%** — i.e. C is *marginally worse* on the primary metric.

### Decisive paired test

Event-level loss difference `abs_error(B) − abs_error(C)`; positive means GST reduces error.
Intercept-only design clustered by **ticker** (26 clusters), CR2/BRL with coefficient-specific
Satterthwaite df, reusing `tools/hyp01_inference_feasibility.py` unchanged:

> **−0.00152 pp**, CR2 SE 0.06902, df 17.2, t = **−0.022**, **p = 0.9827**,
> 95% CI **[−0.14703, +0.14399]**

GST is better on **49.26%** of events — a coin flip. The interval is tight and centred on zero: this
is not an underpowered null, it is a precisely estimated *absence* of improvement. The interval
excludes any improvement larger than about **0.14 pp** against a mean absolute gap of ~6.1 pp.

## The GST feature had to be rebuilt to be point-in-time

The population's own spike z-score **cannot** be used here. It spans a 14-day window anchored at the
spike week, while the maximum anchor-to-event lead in this sample is **5 days**, so its window always
overlaps the announcement — and **9 of 217** anchors fall on or after the event day outright. Using
it would be lookahead.

The GST predictor is therefore rebuilt from raw weekly GST: using only weeks that **close strictly
before** the event day, `gst_z_pre` = (latest closed week − mean of the prior 52 such weeks) / stdev
of those weeks, minimum 20 baseline weeks. The population's spike z-score is retained in the output
for reference only and never enters a model.

## Secondary evidence

**Where C does help.** C beats B on RMSE (4.6395 vs 4.6844) and roughly doubles OOS R² (0.0517 vs
0.0333). Both are squared-error metrics, so this says GST helps slightly on the *largest* moves while
being neutral-to-worse on the typical one — consistent with MAE being flat.

**Top-quintile realized magnitude lift:**

| Model | Top-quintile realized | Overall mean | Lift |
|---|---|---|---|
| B (no GST) | 6.9000 pp | 6.1135 pp | **1.129×** |
| C (+ GST) | 7.7118 pp | 6.1135 pp | **1.261×** |

C's top predicted quintile does contain larger realized moves. This is the one place GST looks
useful, and it is a **secondary** metric.

**Calibration by predicted quintile (C):** predicted 5.07 / 6.18 / 6.76 / 7.41 / 9.26 pp against
realized 4.16 / 4.49 / 7.32 / 6.96 / 7.71 pp. Monotone in the broad sense but over-predicting at the
top and under-predicting in the middle.

**Yearly stability — MAE:**

| Test year | A | B | C |
|---|---|---|---|
| 2023 | **3.5772** | 3.6851 | 3.7200 |
| 2024 | 4.0701 | **3.8086** | 3.8765 |
| 2025 | 3.3347 | 3.3949 | **3.2995** |

No model wins consistently. The intercept-only baseline wins 2023 outright; C wins only 2025.
Fold sizes: 2023 train 53 / test 41; 2024 train 94 / test 48; 2025 train 142 / test 47.

## Sample

285 source rows → **217 unique** `(ticker, event_day)` identities after deduplication → **189** with
complete features → **136** out-of-sample observations across the three folds. The 28 dropped are
events lacking a prior same-ticker earnings gap (the first event per ticker) or sufficient weekly GST
baseline. No event was dropped for any outcome-related reason.

## Frozen before fitting

Outcome `abs(open(T)/close(T−1) − 1)`; AMC → next session, BMO → announcement session. Five baseline
predictors: prior mean |gap| from strictly earlier earnings, 20-day realized volatility, |5-day
return|, 20-day SPY volatility, AMC indicator. One fixed model — ridge, alpha 1.0 — for both B and C,
with standardization and fitting inside each training fold only. Chronological expanding window on
the same 2023/2024/2025 folds as PR #23. **No model search, no threshold search, no hyperparameter
tuning.** Primary metric fixed as MAE before any result was seen.

## Scope

This tests whether **this** pre-event GST z-score improves **this** magnitude model on **this**
population. It does not test other GST constructions, other horizons, or magnitude prediction in
general, and it says nothing about direction or profitability — neither was evaluated.

Regenerate: `python tools/run_retrospective_magnitude_forecast.py`
