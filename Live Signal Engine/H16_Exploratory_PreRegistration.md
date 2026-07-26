# Hypothesis #16 — Exploratory Pre-Registration: Does GST Have Incremental Explanatory Power for Realized Volatility Beyond Implied Volatility?

**This analysis uses the fully-saturated 152-event canonical population.
No genuinely held-out data exists. Results are EXPLORATORY ONLY and
cannot be treated as confirmatory evidence under this project's own
governance standard, regardless of effect size or significance. Any
promising result here requires a fresh, independently-pre-registered
confirmatory test on new forward data before being treated as real —
same standard as Candidate A/B and Attention Spread's initial in-sample
results, which both looked real and did not replicate.**

**Timestamp: 2026-07-26. Written BEFORE the regression is run.** No
coefficient, t-stat, p-value, or R² exists for this model at the time
this file is written.

**Why exploratory, stated plainly, not softened:** a scoping check run
immediately before this document (see conversation record; not itself a
separate file) found that all 152 events in
`Live Signal Engine/FixedWindow_PerEvent_Canonical.csv`'s qualifying
population have already been touched by at least one prior test in this
project — Pass 1, Pass 2, Candidate A/B, C5, H5, and Attention Spread's
samples collectively cover the entire population, several times over for
many events. There is no way to draw a sample for this hypothesis that
is independent of every prior hypothesis tested on this data. That is
not a defect in this specific analysis' design — it is a structural fact
about this population at this point in the project's history, and it
means this test's result, however it comes out, sits at the same
evidentiary level as every other in-sample finding this project has
produced: suggestive, not confirmatory, until replicated on data that
did not exist when the analysis was designed.

## 1. Model specification

```
RV_i = β0 + β1·IV_i + β2·GST_zscore_i + β3·log(market_cap_i) + sector_FE_i + ε_i
```

- **RV (dependent variable)**: `realized_move_pct` — **reused, not
  redefined**, from `GST_VolatilitySurprise_Analysis.py`:
  `|cumulative stock return, entry_date → exit_date| × 100`, computed via
  `base.load_daily_excess` / `base.nearest_trading_day_on_or_before` /
  `base.cumulative_return` (imported from
  `GST_FixedWindow_PerEvent_Canonical.py`, same functions, same
  `ENTRY_OFFSET_DAYS=2`/`EXIT_OFFSET_DAYS=6` window used everywhere else
  in this project that computes a realized move).
- **IV (independent variable)**: `real_cost_pct_of_spot` — the real
  quoted ATM straddle ask cost as % of spot at entry, from whichever
  real-quote pull already covers that event. This is a straddle-cost
  proxy for implied volatility (the same proxy `implied_move_pct` used
  throughout the H5 test), not a Black-Scholes-inverted IV number — no
  event in this project's real-quote pulls has ever had a model-inverted
  IV computed from its exit quote, so the proxy already in hand is used
  as-is, not manufactured to look more precise than it is.
- **GST_zscore**: `fixed_window_zscore`, already present for every event
  in the canonical population.
- **market_cap**: not previously captured for these tickers in any
  surviving file (checked directly — `fetch_market_cap()`-style helpers
  exist in several other scripts but none persisted a market-cap CSV for
  this ticker set). Pulled **once**, per unique ticker (not per event),
  via `yfinance` `fast_info`/`info` `marketCap` — a **current** snapshot,
  not point-in-time-at-each-event. Disclosed simplification, same one
  this project's own `GST_MatchedControlGroup_CanonicalRecompute.py`
  already used for cross-sectional market-cap matching. Entered as
  `log(market_cap)` to reduce right-skew.
- **sector**: `Live Signal Engine/AllTickers_Sectors.csv`, one-hot
  encoded (dropping first level), same source used throughout this
  project's sector-based tests.

## 2. Sample — reused, not re-pulled

Union of every event with `real_cost_pct_of_spot` already on file across:
- `Live Signal Engine/QC_Validation_CleanSample_37Events.csv` (Pass 1)
- `Live Signal Engine/QC_Validation_CleanSample_v2_76Events.csv` (Pass 2)
- `Live Signal Engine/QC_H5_OutOfSample_RawResults.csv` +
  `Live Signal Engine/QC_H5_OutOfSample_Supplemental_RawResults.csv`
  (H5 OOS, clean rows only: `corrupted==False` & `real_cost_pct_of_spot`
  not null)
- `Live Signal Engine/QC_AttentionSpread_OOS_RawResults.csv` (Attention
  Spread OOS, clean rows only)

**No new option-quote pull is performed.** Where the same `(ticker,
spike_week)` appears in more than one of these sources (expected, given
the saturation finding above), it is **de-duplicated to a single row**
before regression — kept once, not once per source — to avoid the exact
pseudo-replication problem already caught and fixed once in this
project's C5 pipeline (a single real observation must not vote more than
once in a regression). Exact overlap counts are reported in the results,
not assumed to be zero.

## 3. What is reported — descriptive only, no decision rule

Per explicit instruction, **there is no PASS/WEAK/FAIL bucket for this
analysis and none will be introduced.** There is no clean confirmatory
test to clear a bar against, because there is no held-out data. Reported,
plainly, without upgrading the framing based on how it looks:

- The GST z-score coefficient's **t-statistic and p-value** in the full
  model (IV + GST + log(market cap) + sector).
- The **incremental R²** of adding GST z-score to a model that already
  has IV + log(market cap) + sector — i.e., R²(full model) − R²(model
  without GST).
- Overlap/de-duplication counts across the four source files, and n
  actually used in the regression.

**A large, significant-looking GST coefficient here is not evidence this
project can act on.** It is exactly the situation this document's opening
paragraph describes in advance: a result that looks real and has not
been tested against anything the model didn't already see.

## 4. Execution plan

1. **DONE, this document.** Committed before the regression is built or
   run.
2. **NOT YET RUN.** Build the union dataset (reuse only), pull market cap
   once per unique ticker, compute `realized_move_pct` via the reused
   helper functions, fit the model, report the two statistics in §3 —
   nothing more, nothing reframed after seeing them.

---

*End of pre-registration. The regression follows this file's commit, not
the other way around — no coefficient exists yet for any version of this
model.*
