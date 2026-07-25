# Hypothesis #5 (Volatility Mispricing) — Out-of-Sample Replication Pre-Registration

**Timestamp: 2026-07-25. Written BEFORE any fresh event's real quote has
been pulled.** No `real_cost_pct_of_spot`, no `realized_move_pct`, no
correlation coefficient exists anywhere for any event in this
pre-registration's sample at the time this file is written.

## 1. Original finding, cited to its exact source

**r = 0.407, n = 76**, Pearson correlation between continuous GST z-score
and "volatility surprise" (`realized_move_pct − implied_move_pct`).

- **Script**: `GST_VolatilitySurprise_Analysis.py`
- **Source data**: `Live Signal Engine/QC_Validation_CleanSample_v2_76Events.csv`
  (76-event real-quote sample — `implied_move_pct := real_cost_pct_of_spot`,
  the real quoted ATM straddle ask cost as % of spot) joined to
  `Live Signal Engine/FixedWindow_PerEvent_Canonical.csv` on
  `(ticker, spike_week)` for the continuous z-score.
  `realized_move_pct := |cumulative stock return, entry_date → exit_date| × 100`,
  reconstructed from LOCAL daily excess-return data (`anchor+2`/`anchor+6`,
  nearest-trading-day-on-or-before rule — same convention used throughout
  this project), NOT from the option's own exit quote.
- **Output**: `Live Signal Engine/VolatilitySurprise_Analysis.csv`
- **Exact citation**: `CHANGELOG.md`, "2026-07-19 (later still) — volatility-surprise
  check (real quotes vs. real moves, 76-event sample)": *"z-score correlated
  almost identically with raw realized-move size (Pearson r=0.443) as with
  surprise specifically (r=0.407) — meaning the signal predicts move
  magnitude, not specifically mispriced magnitude. No evidence the GST
  signal flags moves the options market fails to price in."*

**This hypothesis gets no benefit of the doubt.** Attention Spread
(`Live Signal Engine/AttentionSpread_Analysis.csv`,
`GST_AttentionSpread_Analysis.py`) was built on the same underlying logic
— a ratio/difference between a GST-attention quantity and a real,
market-priced cost quantity, tested for predictive power on the same
76-event sample — and its apparent tercile-split edge did not hold up to
scrutiny even in-sample (redundant with its own ingredients under the
linear/regression test, and the tercile result that did survive is
currently unconfirmed out-of-sample as of this writing). H5 is judged
against the same binding, no-leniency standard, not a looser one because
it "already showed r=0.407 once."

## 2. Fresh sample — hard exclusion by event ID, not by year or count

**Exclusion set**: every `(ticker, spike_week)` pair present in
`QC_Validation_CleanSample_v2_76Events.csv` (n=76 keys), read directly
from that file, not approximated.

**Population**: `FixedWindow_PerEvent_Canonical.csv`, `qualifies_z5==True
& pnl_pct.notna()` (n=152, this project's sole authoritative
STRONG_EARNINGS population per
`STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` §1).

**Eligible pool after hard exclusion: n=76** (152 − 76, since the original
76-event sample is itself a subset of the 152). This clears the
`n≥40` target with room to spare — **the n<30 stop condition is not
triggered**, checked explicitly before sampling, not assumed.

**Sample drawn: n=45**, ticker-proportional stratified random,
`seed=811` — a fresh seed, not reused from any prior sample in this
project (`42`, `7`, `99`, `123`, `256`, `314` are all already spoken for
by earlier pulls). 23 of the 27 canonical tickers represented.
Locked, enumerated: `Live Signal Engine/H5_OutOfSample_LockedSample.csv`.

**Disclosed, not hidden: 27 of these 45 events overlap with the
separately-drawn Attention Spread out-of-sample confirmatory sample**
(`Live Signal Engine/AttentionSpread_OOS_LockedSample.csv`, also n=45,
seed=314, drawn independently from the same 76-event eligible pool).
This is the expected overlap by chance for two independent 45-of-76 draws
(45×45/76 ≈ 27) — not a sampling bug, but it means these two out-of-sample
tests (H5 and Attention Spread) are **not fully independent replications
of each other**; a systematic issue affecting this shared 27-event
subset's real quotes would show up in both. Both tests still stand on
their own terms (different metrics, different decision rules), but this
correlation between the two "fresh" samples should be kept in mind when
weighing how much independent confirmation two OOS passes/fails actually
provide.

## 3. Methodology — reused exactly, not redefined

`realized_move_pct` and `implied_move_pct` computed identically to
`GST_VolatilitySurprise_Analysis.py`:
- `implied_move_pct := real_cost_pct_of_spot` — real quoted ATM straddle
  (first listed expiration on/after `exit_date`, strike closest to
  entry-day close) ask cost as % of spot, at `entry_date`
  (`anchor+2`, nearest trading day on/before). Pulled fresh via
  QuantConnect/AlgoSeek for these 45 events (never pulled before — outside
  the original 76-event QC pull). **No exit-side quote is needed for this
  metric** — `implied_move_pct` is an entry-only quantity, so this pull is
  narrower than a full round-trip P&L pull (no exit ask/bid required).
- `realized_move_pct := |cumulative stock return, entry_date → exit_date| × 100`,
  from LOCAL daily excess-return data — same helper functions
  (`load_daily_excess`, `nearest_trading_day_on_or_before`,
  `cumulative_return`) imported directly from
  `GST_FixedWindow_PerEvent_Canonical.py`, not reimplemented.
- `volatility_surprise_pct := realized_move_pct − implied_move_pct`.
- z-score: `fixed_window_zscore`, joined from `FixedWindow_PerEvent_Canonical.csv`
  on `(ticker, spike_week)` — already present for every event in this
  sample (it's a subset of the canonical 152).
- **Correlation tested: Pearson r, z-score vs. volatility_surprise_pct**
  — the exact statistic the original r=0.407 refers to, not
  `realized_move_pct` alone (which the original test explicitly
  distinguished as a *different*, not-under-test quantity).

## 4. Binding decision rule (stated in advance, not revisited after seeing results)

- **PASS**: r ≥ 0.25 **AND** p < 0.05 on the fresh sample, **same sign as
  the original (positive)**.
- **WEAK**: r in [0.10, 0.25) with p < 0.05 → log as "not tradeable," do
  **not** spawn a new monetization hypothesis from it.
- **FAIL**: r < 0.10, **or** wrong-signed (negative), regardless of
  p-value → **Hypothesis #5 is dead**, marked explicitly dead in
  `CHANGELOG.md`, the same status given to Attention Spread's reversal.

No new metric, threshold, or reinterpretation will be introduced after
the fresh-sample result is observed. A FAIL is not eligible for a
retroactive explanation that saves the hypothesis — any observation that
might explain *why* it failed is logged as a note for a future,
separately-designed test, not used to reclassify this result.

## 5. Execution plan

1. **DONE.** Fresh sample built and locked (§2), this document written
   and committed to version control before any new data is touched.
2. **WRITTEN, NOT YET RUN.** `QC_H5_OutOfSample_Pull.py` — pulls real
   entry-only ATM straddle ask quotes for the 45 locked events via
   QuantConnect/AlgoSeek (same contract-selection methodology as
   `QC_Options_Validation_Script_v2_Expanded.py`, narrowed to
   entry-side-only since that's all this metric needs). Must be pasted
   into a QuantConnect Research notebook and run there — this environment
   cannot execute QuantConnect Research cells.
3. **NOT STARTED — cannot be run against real data yet.** Local
   computation of `realized_move_pct`/`volatility_surprise_pct` and the
   Pearson correlation, applied to whatever real quotes come back,
   followed by the binding decision rule in §4 exactly as written.

---

*End of pre-registration. Real quote pulls for these 45 events follow
this file's commit, not the other way around.*
