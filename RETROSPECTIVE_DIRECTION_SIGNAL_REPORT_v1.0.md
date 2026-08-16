# Independent Pre-Earnings Direction Model — Results

`RETROSPECTIVE_DEVELOPMENT_ONLY`. Confirms nothing about HYP-01, uses no gated prospective outcome.
**GST is never an input to the direction model** — it is applied only after every out-of-sample
prediction exists, as a magnitude/event-selection filter.

## Conclusion

# `NEITHER_ADDS_VALUE`

Neither the independent direction model nor the GST filter adds value. No stage of the two-stage
design survives.

## Out-of-sample model performance

144 out-of-sample events, 27–28 tickers, chronological expanding window. 77 positive / 67 negative.

| Model | Accuracy | Balanced acc. | AUC | **Brier** | Beats baselines? |
|---|---|---|---|---|---|
| Always-positive baseline | **0.5347** | 0.5000 | 0.500 | 0.46528 | — |
| Momentum-sign baseline | 0.4792 | 0.4752 | 0.4752 | 0.32292 | — |
| **Logistic (L2, C=1.0)** — *selected* | 0.4792 | 0.4849 | **0.4654** | **0.27110** | Brier yes; **accuracy no**, **AUC < 0.5** |
| Shallow GBT (depth 2, 100 trees, lr 0.05) | 0.4931 | 0.5056 | 0.4757 | 0.28710 | Brier yes; accuracy no |

Selection was by **pooled out-of-sample Brier score** (AUC secondary), fixed before fitting and never
based on trading returns. That rule picks the logistic model — but the choice is hollow: **its
accuracy (47.9%) is below the always-positive baseline (53.5%), and its AUC is 0.465, i.e. below
chance.** The Brier advantage comes from predicting close to 0.5 (being unconfident), not from
discriminating. **No model here has directional skill.**

### By test year — logistic

| Test year | n | Accuracy | AUC | Brier |
|---|---|---|---|---|
| 2023 | 47 | 0.4468 | 0.4330 | 0.27277 |
| 2024 | 49 | 0.5714 | 0.5368 | 0.25638 |
| 2025 | 48 | 0.4167 | 0.3767 | 0.28448 |

Two of three years are below chance. There is no chronological stability to build on.

### Calibration — logistic

| Predicted bin | n | Mean predicted | Observed positive rate |
|---|---|---|---|
| [0.0, 0.4) | 41 | 0.3416 | **0.5854** |
| [0.4, 0.5) | 43 | 0.4409 | 0.5116 |
| [0.5, 0.6) | 38 | 0.5514 | 0.6053 |
| [0.6, 1.0) | 22 | 0.6435 | **0.3636** |

Calibration is **inverted at both ends**: where the model is most confident of a down gap it is right
41% of the time, and where it is most confident of an up gap it is right 36% of the time.

### Folds

| Test year | Train n | Test n |
|---|---|---|
| 2023 | 73 | 47 |
| 2024 | 120 | 49 |
| 2025 | 169 | 48 |

Expanding window, never random. Standardization fit inside each training fold only.

## Combined strategy

Enter at close(T−1), exit at open(T); long if p > 0.5, short if p < 0.5; **10 bps round-trip cost**,
fixed and disclosed before any return was computed.

| Evaluation | Direction only | Direction + GST filter |
|---|---:|---:|
| Trades | 144 | 90 |
| Mean net return | **−0.7027%** | **−0.8865%** |
| Median net return | −0.5406% | −0.6018% |
| Hit rate | 47.92% | 47.78% |
| Maximum drawdown | −81.66% | −78.90% |
| Annualized trade frequency | 48.79 | 30.72 |
| Worst test year | 2023: −2.3316% | 2023: −2.5048% |

Contemporaneous unfiltered comparator — **low-attention events only**: 54 trades, **−0.3962%** mean
net, 48.15% hit rate, −26.27% max drawdown. The GST filter selects the *worse* half.

**Decisive statistic — incremental GST effect**, `strategy_return ~ high_GST + ticker fixed effects`,
ticker-clustered CR2/BRL with coefficient-specific Satterthwaite df (27 clusters), reusing
`tools/hyp01_inference_feasibility.py` unchanged:

> **−1.0404 pp**, CR2 SE 1.8752, df 18.1, t = −0.555, **p = 0.5858**, 95% CI **[−4.978, +2.897]**

Negative point estimate, not statistically supported. GST does not improve the independent direction
model. This coefficient — not the filtered strategy's standalone mean — is the test.

**Secondary** (one fixed conventional threshold, not searched): confidence filter at p ≥ 0.60 or
≤ 0.40 gives 63 trades, **−1.8891%** mean net, 39.68% hit rate. Worse again, consistent with the
inverted calibration.

## A leak was found and removed — this changed the answer

The event population reuses matched controls, so the same `(ticker, event_day)` identity appears
several times — **68 duplicate rows out of 285; one event appears 7 times**. Left in place this both
double-counted the evaluation sample and **leaked the outcome**: a duplicate's `prior_gap_dir`
feature read *the same event's* gap sign.

With duplicates present the logistic model scored **63.6% accuracy, AUC 0.6395, Brier 0.23824**, and
the direction-only strategy returned **+0.60% net**. After deduplicating to **217 unique event
identities** and requiring `prior_gap_dir` to use a **strictly earlier** event date, the same model
scores **47.9% accuracy, AUC 0.4654**, and the strategy returns **−0.70% net**. The apparent skill was
the leak.

## Frozen definitions

Outcome `y = 1[open(T)/close(T−1) − 1 > 0]`, AMC → next session, BMO → announcement session.
Features, frozen before fitting, all from information at or before close(T−1): 5-day and 20-day stock
return, 20-day realized volatility, 5-day and 20-day SPY return, stock-minus-SPY 20-day momentum,
prior earnings-gap direction (strictly earlier events only), calendar quarter. **No feature was
omitted** — all eight were constructible point-in-time. Models were fixed in advance; no feature
search, no hyperparameter optimization, no threshold search, no alternative holding periods.

Inputs: `Live Signal Engine/retrospective_event_components.csv`,
`Daily OHLC Data (2021-2025 Opening Gap Test)/`, `Daily Excess Return Data*/`.
Regenerate: `python tools/run_retrospective_direction_signal.py`

## Scope

This tests one direction model family on one event population. It does not establish that earnings
gap direction is unpredictable in general — only that these four fixed models, on these features and
this sample, have no out-of-sample directional skill, and that GST filtering does not improve them.
