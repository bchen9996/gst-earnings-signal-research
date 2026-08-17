# Brand Search Demand and Quarterly Revenue Nowcasting — Results

`EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY`. A **fundamentals-nowcasting** study. No stock return,
option, analyst estimate or prospective HYP-01 outcome was retrieved or used. **Ticker GST is not
used** — brand-demand search is a different construct, and only the eight frozen brand queries enter.

> ## POINT-IN-TIME LIMITATION — READ THIS FIRST
> Google Trends series retrieved today are a **retrospective reconstruction**. Google rescales each
> series to the maximum of the requested window and may revise its sampling, so **the identical
> series was not necessarily available in this form when each quarter closed**. This MVP can generate
> a prospective hypothesis; it **cannot** establish that the historical series was available
> contemporaneously. Every number below inherits that caveat.

## Decision

# `INSUFFICIENT_DATA`

**The minimum-sample rule is not met: 38 out-of-sample observations against a required 40.**

| Gate | Required | Observed | Met |
|---|---|---|---|
| Eligible company-quarters | ≥ 60 | **66** | yes |
| Chronological out-of-sample observations | ≥ 40 | **38** | **no** |
| Companies represented out of sample | ≥ 6 | **7** | yes |

The label is set by the gate, not by the numbers. The numbers were computed anyway and are reported
in full below, because they point the same way and hiding them would be worse than reporting them
with their limitation attached.

## What the computed numbers show

| Model | **MAE (pp)** | RMSE (pp) | OOS R² vs Model A |
|---|---|---|---|
| **A.** Expanding company historical mean | 6.3795 | 8.5120 | 0.000 |
| **B.** Fundamental ridge | **6.3679** | 8.0876 | 0.09724 |
| **C.** Fundamental + search demand | **6.8735** | 8.1836 | 0.07568 |

**MAE change B → C: −7.94%** — adding search demand made the primary metric **worse**.

### Decisive paired comparison

`abs_error(B) − abs_error(C)`; positive means search helps.

> mean **−0.5056 pp**, median −0.4116 pp, **Model C wins only 44.74%** of events

Ticker-clustered (CR2/BRL, 7 clusters, Satterthwaite df): **−0.5056 pp, SE 0.97855, t = −0.517,
p = 0.62525, 95% CI [−2.946, +1.935]**. The interval is wide — with 38 observations this sample cannot
resolve a small effect either way, which is exactly why the gate exists.

**Not stable across years:** 2024 **+0.72 pp** (search helped), 2025 **−1.61 pp** (search hurt). A sign
flip across the only two evaluable folds is not a signal.

## By company

| Ticker | n | MAE B | MAE C | Improvement |
|---|---|---|---|---|
| **WING** | 6 | 14.6350 | 11.3751 | **+3.2599** |
| MCD | 6 | 4.8890 | 3.5913 | +1.2977 |
| SBUX | 6 | 7.8833 | 7.3173 | +0.5660 |
| CMG | 6 | 5.1066 | 6.2099 | −1.1032 |
| DPZ | 6 | 2.4591 | 5.3410 | −2.8819 |
| BROS | 6 | 4.2231 | 7.3256 | −3.1025 |
| **CAVA** | 2 | 3.4021 | 7.1163 | **−3.7141** |

Strongest **WING** (+3.26 pp, and the company Model B forecasts worst); weakest **CAVA** (−3.71 pp, but
only 2 observations). Three of seven improve, four worsen.

## Secondary metrics — and why they do not change the answer

Search-demand acceleration-sign accuracy: **C 60.53% vs B 55.26%**. That favours C. So does nothing
else: RMSE is worse for C (8.1836 vs 8.0876) and OOS R² is lower (0.0757 vs 0.0972).

**The fixed primary MAE comparison fails, so this is not reinterpreted as success.** One secondary
metric moving the right way on 38 observations, with an unstable year split, is not evidence.

## Calibration and folds

| Test year | n train | n test | A MAE | B MAE | C MAE |
|---|---|---|---|---|---|
| 2023 | 9 | 18 | — | — | **skipped, training set too small** |
| 2024 | 27 | 18 | 5.3765 | 6.8212 | 6.0994 |
| 2025 | 45 | 20 | 7.2822 | 5.9599 | 7.5702 |

The 2023 fold could not run: only 9 training observations existed before it. That is the direct cause
of the 38 out-of-sample count, and it traces to a data constraint, not a design choice — **Google
serves weekly resolution only for windows up to about five years**. An eight-year request silently
returns *monthly* points, which cannot fill a fiscal-quarter average, so usable weekly history starts
in 2021 and the first two years are consumed by the year-ago revenue base and the four-quarter search
baseline.

## Sample construction

292 raw quarterly revenue facts → 251 company-quarters after deduplication by ticker, fiscal period
and accession → **66 eligible** with every feature present. All eight frozen queries returned usable
data (**none marked unavailable**); **TXRH** dropped out at the feature-completeness stage rather than
the query stage. Companies out of sample: BROS, CAVA, CMG, DPZ, MCD, SBUX, WING.

Revenue concepts used: `Revenues` (SBUX, MCD, CMG, DPZ, WING), `RevenueFromContractWithCustomer‑
ExcludingAssessedTax` (CAVA, BROS), `SalesRevenueNet` (TXRH).

## Discipline

Exactly two search features, both normalized on **earlier quarters only**. The search window is the
company's own fiscal quarter, which ends at quarter end — **strictly before the earnings release**, so
no post-release week can enter a feature. One fixed ridge, alpha 1.0, for both B and C. Chronological
expanding window, scaling fitted inside each training fold. No model search, no alpha tuning, no
feature selection, no trees, no neural networks, no quantum models. The universe and query strings
were frozen before retrieval and were not changed after seeing results.

## Next stage

The next-stage rule is **not** triggered. A later project may test whether a predicted fundamental
surprise helps forecast earnings-gap direction **only if** search demand improves the fixed primary
metric. It did not. **No stock return was tested in this task.**

Reproduce: `python tools/run_search_demand_nowcast_mvp.py`
