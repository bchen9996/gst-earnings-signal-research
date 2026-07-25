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

---

## Appended note (2026-07-25) — supplemental draw, original 45 fell short

**Not an edit to anything above — append-only, per this project's
established governance for locked/pre-registered documents.**

**What happened:** the original n=45 draw (§2, seed=811) came back with
only **29 clean-and-priced events** after the (unmodified) automated
corruption filter: 15 excluded as implausible pricing (>25% of spot — the
same `MAX_PLAUSIBLE_COST_PCT_OF_SPOT` threshold used throughout this
project, not relaxed here or anywhere else), 1 with no option chain
listed at entry. 29 is below the effective floor for the §2 `n≥40`
target once further attrition in the still-to-come outcome pull is
accounted for — **not itself a stop condition** (the pre-registration's
stop condition is `n<30` on the *eligible pool before sampling*, which
was 76 and never came close to triggering), but a real shortfall that
needs resolving before any correlation is computed.

**Supplemental draw:**
- Remaining untouched eligible pool: **31 events** — the same 76-event
  eligible pool defined in §2 (152 canonical minus the original 76-event
  H5 sample), minus the 45 already drawn. Recomputed directly from the
  actual files (`FixedWindow_PerEvent_Canonical.csv`,
  `QC_Validation_CleanSample_v2_76Events.csv`,
  `H5_OutOfSample_LockedSample.csv`), not assumed from the prior count.
- **All 31 remaining events drawn — not a random subsample, so no seed
  applies.** Reasoning: this is the complete remainder of the *already-
  locked* eligible pool from §2, not a new population definition, so
  using all of it isn't an expansion of scope needing a fresh
  pre-registration decision — it's completing the draw from a set already
  fixed in advance. Since nothing is being left out, there is no
  selection to seed, and holding part of it back for a hypothetical later
  draw would only lower the probability of reaching the `n≥40` combined
  target with no offsetting benefit (there is no further eligible pool to
  draw from afterward under this pre-registration's population
  definition).
- Expected new clean count at the original draw's ~64.4% clean-pass rate
  (29/45): 31 × 0.644 ≈ 20, for a combined expected total of **~49** —
  comfortably above 40 even allowing for realistic pass-rate variance,
  which is the specific reason the full remainder was drawn rather than
  the bare-minimum ~18 events that would only just clear 40 in
  expectation.
- Locked: `Live Signal Engine/H5_OutOfSample_Supplemental_LockedSample.csv`
  (n=31). Confirmed disjoint from the original 45-event draw (0 overlap,
  checked directly) and confirmed a subset of the §2 eligible pool.
- Pull script: `QC_H5_OutOfSample_Supplemental_Pull.py` — same
  entry-only `real_cost_pct_of_spot` methodology, same unmodified 25%
  corruption filter, core pull logic verified byte-identical to the
  original `QC_H5_OutOfSample_Pull.py` (only the header comment, sample
  list, and print label differ). Not yet run.

**Still not done, per explicit instruction:** no correlation has been
computed on the original 29. No outcome/realized-move pull has been run
for either the original or supplemental sample. The binding decision rule
in §4 is unchanged and still applies once a combined clean-and-priced
`n≥40` is confirmed — if the supplemental draw still leaves the combined
total under 30, this note's next update (also appended, not edited) will
report that H5 cannot be tested out-of-sample without a fresh
pre-registration decision to expand the eligible-pool definition itself.

---

## Appended note (2026-07-25, later) — combined n confirmed at 49; ticker-exclusion limitation, verified and broader than first flagged

**Not an edit to anything above — append-only.**

**Verification artifacts created**: the two QC pulls' `results_df` output
was pasted into conversation but the scripts' own CSV exports were never
generated from the notebook. Reconstructed and saved as
`Live Signal Engine/QC_H5_OutOfSample_RawResults.csv` (original 45-event
pull) and `Live Signal Engine/QC_H5_OutOfSample_Supplemental_RawResults.csv`
(supplemental 31-event pull), from the pasted content only — nothing
assumed from memory or from summary stats. **Schema caveat, disclosed:**
the supplemental file has the full column set (the complete `results_df`
table was pasted for that pull). The original 45-event file has a
narrower schema — only `ticker`, `spike_week`, `corrupted`, `note`,
`real_cost_pct_of_spot` — because only the console print log was pasted
for that pull, not the full table; `entry_date`, `exit_date`, `zscore`,
strike, and quote-level fields were never provided for those 45 events
and are not fabricated here. Both files' clean/corrupted/failed counts
were assert-checked in code against each pull's own printed summary line
before saving (original: 15 corrupted / 29 clean / 1 failed; supplemental:
10 corrupted / 20 clean / 1 failed) — both matched exactly.

**Combined clean-and-priced n = 49** (29 + 20), confirmed by filtering
both files independently on `corrupted==False & real_cost_pct_of_spot
notnull` and summing — clears the `n≥40` target from §2.

**Ticker-exclusion limitation, corrected and broadened from the first
report:** of the 76 attempted events (all of the pre-registration's
eligible pool), four tickers ended up with **zero** clean-and-priced
representation in the 49, not two:

| Ticker | Attempted | Clean | Failure mode |
|---|---|---|---|
| NFLX | 16 | 0 | all auto-flagged implausible pricing (>25% of spot) |
| NVDA | 6 | 0 | all auto-flagged implausible pricing |
| COHR | 2 | 0 | both "no option chain listed at entry date" — a different failure mode than the other two |
| DELL | 1 | 0 | auto-flagged implausible pricing |

Every other ticker in the 76-event eligible pool has at least one clean
event in the 49. **The final H5 out-of-sample result will have zero
NFLX, NVDA, COHR, or DELL representation and should not be read as
generalizing to any of those four tickers** — not just the two originally
flagged. NFLX and NVDA's exclusion is the dominant pattern (22 of 76
attempted events, all on the same implausible-pricing failure mode,
worth investigating separately as a possible systematic AlgoSeek/strike-
matching issue for those two tickers specifically, per the same
"broken strike/expiry match" root cause already documented for the
original 76-event sample's one manually-caught corrupted case) — COHR
and DELL's exclusion is much thinner evidence (3 attempts between them)
and is disclosed for completeness, not because it's equally strong
evidence of a ticker-specific pattern.

---

## Appended note (2026-07-25, later still) — Amendment: FAIL condition gap closed

**Not an edit to anything above — append-only.**

**The result:** n=49, Pearson r=0.1065, p=0.4664, positive sign (same
direction as the original r=0.407). Applied against §4's binding rule
exactly as written, this satisfied none of the three literal conditions:
PASS requires r≥0.25 (fails); WEAK requires r in [0.10, 0.25) **with**
p<0.05 (r qualifies, p does not — 0.4664 is nowhere close to 0.05); FAIL
as originally worded requires r<0.10 or wrong-signed (r=0.1065 is not
<0.10 by 0.0065, and the sign is correct). The rule's three conditions
were written assuming effect size and significance would move together;
they did not here, leaving this specific result technically unclassified.

**Amendment — the FAIL condition is clarified to mean: any result that
does not meet the PASS or WEAK bar (by elimination), in addition to the
originally-stated r<0.10 or wrong-signed cases. This amendment is logged
after seeing n=49 results (r=0.1065, p=0.4664) but resolves an omitted
case in the direction of a STRICTER bar for validating the hypothesis,
not a looser one — it cannot be read as rescuing a marginal result,
since it classifies this result as FAIL rather than leaving it
unclassified.**

**Under the amended rule: this result classifies as FAIL. Hypothesis #5
is dead**, per §4's original consequence for FAIL — marked explicitly
dead in `CHANGELOG.md` and `STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md`,
the same status given to Attention Spread's reversal.
