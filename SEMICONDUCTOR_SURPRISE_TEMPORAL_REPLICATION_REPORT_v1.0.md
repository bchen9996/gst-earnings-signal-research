# Terminal Temporal Replication — Semiconductor Surprise Absorption (2010–2017)

`EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY` · `is_gst_test: false` ·
`VENDOR_DEFINED_REPORTED_EPS_SURPRISE` · `POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED`

**Question.** Does vendor-defined earnings surprise improve chronological out-of-sample prediction of
the first full-session SMH-adjusted price reaction for the same ten semiconductor companies during
**2010–2017**?

This is a **retrospective temporal replication** motivated by PR #34's suggestive but gate-failing
result. It is **not a prospectively registered independent replication** and **not preregistered
evidence**. It is the **terminal** replication for this hypothesis.

## Decision

# `TEMPORAL_REPLICATION_FAILS`

**Two of the four replication gates fail.** The research path stops here: no information–price gap,
no Stage 2, no trading, no new specification, and **no third replication is proposed.**

## 1. Sample and exclusions

| | |
|---|---|
| Provider records 2004–2017 | 531 |
| SEC Item 2.02 events 2004–2017 | 522 |
| Excluded — no exact-date match | 68 |
| Excluded — ambiguous | **1** |
| **Uniquely matched** | **462** |
| Tickers with events | **9 of 10** |
| **OOS events 2010–2017** | **283** |
| Duplicate identities | **0** |
| Train/test identity overlap | **0** |

Timing: **456** accepted ≥16:00 ET → next session; **6** accepted <09:30 ET → same session;
**0** intraday. No event was dropped for missing prices.

**AVGO is excluded, not replaced.** Its current CIK (1730168, Broadcom Inc., former name
"Broadcom Ltd") carries **no pre-2018 filing history** and lists **no archived submission files**;
the historical issuer is a predecessor entity not reachable from the authoritative ticker→CIK map.
Under the frozen rule the affected records are excluded and the sample gate applies. No substitute
ticker was introduced. Nine tickers still clear the ≥8 requirement.

2004 contributes only 10 events because **SEC Item 2.02 came into force on 2004-08-23**; earlier
releases carry a different item number and cannot match. This was recorded *in advance* and falls
entirely inside the training window.

**Split audit.** Exactly one absolute daily move ≥40% was found: **AMD 2016-04-22, +52.3%**, with a
following-session return of −13.5%. Diagnosed as a **genuine move**, not an adjustment failure, and
**reported rather than deleted**.

Events by ticker: MU 53, TXN 53, AMD 52, QCOM 52, NVDA 51, INTC 51, AMAT 51, KLAC 50, LRCX 49,
AVGO 0. Every replication year holds 34–37 OOS events.

## 2. Stage 1 — Model B vs Model C

Model B = intercept + ticker indicators. Model C = B + transformed vendor-defined surprise.
Metric: MAE of the initial abnormal reaction, pooled over eight expanding chronological folds
(train 2004–2009 → test 2010 … train 2004–2016 → test 2017). **n = 283.**

| | Model B | Model C |
|---|---|---|
| MAE | 0.044226 | **0.043246** |
| RMSE | 0.068302 | 0.066776 |
| **MAE improvement** | | **+2.216%** |
| OOS R² (Model C) | | 0.0351 |

Pooled OOS Spearman (surprise vs initial reaction) = **+0.2169**, **p = 0.000236**. Mean coefficient
on transformed surprise = **+0.0122**. Alphas drawn only from the frozen grid.

## 3. Exact bootstrap interval

2,000 moving-block draws · 28-calendar-day blocks · **92 blocks** · seed **20260817** ·
statistic `MAE_B − MAE_C`:

> mean **+0.000981**, 95% interval **[−0.0000561, +0.0021342]**

The interval **contains zero**, by a very narrow margin at the lower bound.

## 4. All four replication gates

| # | Gate | Result | |
|---|---|---|---|
| 1 | pooled MAE improvement ≥ 1.0% | **+2.216%** | **pass** |
| 2 | 95% bootstrap interval entirely above zero | **[−0.0000561, +0.0021342]** | **FAIL** |
| 3 | Model C beats Model B in ≥ ⌈2×8/3⌉ = **6** of 8 years | **5 of 8** | **FAIL** |
| 4 | expected positive sign | **+0.2169** (p = 0.000236) | **pass** |

## 5. Annual and ticker stability

| Year | n | MAE B | MAE C | Improvement | C better |
|---|---|---|---|---|---|
| 2010 | 35 | 0.033309 | 0.032044 | **+3.80%** | yes |
| 2011 | 35 | 0.045103 | 0.041977 | **+6.93%** | yes |
| 2012 | 36 | 0.028540 | 0.026866 | **+5.87%** | yes |
| 2013 | 34 | 0.038273 | 0.038701 | −1.12% | no |
| 2014 | 35 | 0.048191 | 0.048786 | −1.23% | no |
| 2015 | 37 | 0.049350 | 0.049325 | +0.05% | yes |
| 2016 | 35 | 0.065080 | 0.065377 | −0.46% | no |
| 2017 | 36 | 0.045900 | 0.042895 | **+6.55%** | yes |

The pattern is **front-loaded and unstable**: strong in 2010–2012, absent or negative through
2013–2016, strong again in 2017.

| Ticker | n | Improvement % | Spearman |
|---|---|---|---|
| MU | 31 | +6.07 | +0.409 |
| AMD | 31 | +4.96 | +0.288 |
| LRCX | 31 | +4.69 | +0.353 |
| QCOM | 32 | +1.37 | +0.271 |
| NVDA | 31 | −0.32 | +0.150 |
| INTC | 31 | −0.40 | +0.118 |
| TXN | 32 | −0.42 | +0.151 |
| KLAC | 32 | −1.37 | +0.030 |
| AMAT | 32 | −3.47 | +0.002 |

Model C helps only **4 of 9** tickers, yet **every one of the nine** Spearman correlations is
positive. Excluding fiscal-year-end quarters (72 events) leaves n = 211, improvement +2.35%,
Spearman +0.260 — descriptive only, and it does not replace the primary gate.

SEC-validated overlap is **NOT_APPLICABLE**: those parser values exist only for 2018–2025 and none
overlaps this window. The twenty-session return is **NOT_REPORTED** because Stage 2 was never
permitted.

## 6. Stage 2 and trading

**Stage 2 was not permitted and did not run. Trading did not run.** The gap was never constructed,
Models D/E were never fitted, no CR2/BRL or Satterthwaite inference on a gap was computed, and no
trade was simulated.

## 7. Comparison with PR #34 — secondary, never pooled

Produced **after** the replication result was finalized. The samples are **never pooled**, and this
comparison **cannot rescue the failed gate**.

| | PR #34 (2023–2025) | Replication (2010–2017) |
|---|---|---|
| OOS n | 116 | **283** |
| MAE improvement | +2.482% | **+2.216%** |
| Spearman | +0.135 (p = 0.148) | **+0.217 (p = 0.000236)** |
| Bootstrap 95% CI | [−0.000727, +0.003170] | **[−0.0000561, +0.0021342]** |
| Stage 1 passed | **no** | **no** |

**The point estimates agree in sign** — both the MAE improvement and the Spearman correlation are
positive in both windows. **Both windows nevertheless fail the same unchanged gate.** Two
independent-in-time failures of the same gate are not converted into a pass by combining them, and
no such combination was performed.

## 8. Strongest findings in both directions

**Strongest supporting finding.** Over 283 out-of-sample events spanning eight years, the
surprise/reaction Spearman correlation is **+0.217 with p = 0.000236** — a genuinely significant
monotonic association, roughly 1.6× the magnitude seen in 2023–2025 and on a sample 2.4× larger.
**All nine tickers show a positive Spearman.** Pooled MAE improvement is +2.22%, and the association
holds in the same direction in both temporal windows.

**Strongest falsifying finding.** That association does **not** convert into a robust predictive
improvement. Model C beats Model B in only **5 of 8 years** against 6 required, is **negative in
2013, 2014 and 2016**, and helps only **4 of 9 tickers** — AMAT −3.5% and KLAC −1.4% among the
losers. The bootstrap interval **includes zero**. A correlation that is statistically real but
delivers no stable out-of-sample error reduction is exactly what a weak, regime-dependent effect
looks like, and it is not a tradable signal.

## 9. Limitations

- **Vendor-defined, restated EPS.** Not GAAP, not SEC-validated. `surprisePercentage` neutralizes
  *split* restatement but **not** estimate-vintage revision.
- **`POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED`.** If historical `estimatedEPS` was revised
  after the announcement, the predictor is contaminated in an unknown direction. This is the single
  largest threat to interpreting even the significant Spearman result, and it is unresolved.
- **Nine tickers, not ten**, because AVGO's pre-2018 issuer identity is not mechanically resolvable.
- **Retrospective.** Motivated by an earlier suggestive result on the same hypothesis and the same
  universe; not an independent registered replication.

## 10. Integrity confirmation

**Nothing was changed after outcomes were viewed.** No gate, threshold, horizon, cost, model family,
feature, universe or fold definition was altered at any point after the design commit `6361111`,
which preceded any pre-2018 price or return observation. Every model, transform, grid, selection
rule, tie-break, bootstrap and gate was **imported and executed unmodified** from PR #34's runner;
that file's source was not edited.

Two amendments were made **before any outcome was opened** and both are recorded in the design block:
the `FOLDS`/`PRICE_CACHE` rebinding, and a **calendar-bounds** fix — the repository's XNYS instance
begins 2006-08-17 and raised `DateOutOfBounds` for 2004–2006 acceptance dates, so the same package
and same XNYS calendar were re-instantiated from 2003-01-01. No repository module was edited, and no
price cache existed when that fix was made.

**No third replication is proposed.** This hypothesis path is closed.

Reproduce: `python tools/run_semiconductor_surprise_temporal_replication.py`
Verify: `python test_market_response_semiconductor_surprise_temporal_replication.py`
