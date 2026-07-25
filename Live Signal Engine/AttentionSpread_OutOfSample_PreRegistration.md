# Attention Spread — Out-of-Sample Replication Pre-Registration

**Timestamp: 2026-07-25. Written BEFORE any fresh event's real quote has
been pulled.** No `real_cost_pct_of_spot`, no `Attention Spread` value,
and no tercile assignment exists for any event in this document's sample
at the time this file is written.

**Why this document exists now, not earlier — a corrected gap, not a
routine addition:** the sample and pull script referenced below
(`Live Signal Engine/AttentionSpread_OOS_LockedSample.csv`,
`QC_AttentionSpread_OOS_Pull.py`, both committed `a2587c6`) were built
without an equivalent document at the time — unlike Hypothesis #5, whose
binding rule (`H5_OutOfSample_PreRegistration.md`) was locked before any
fresh data was touched. That gap let a later handoff document
mischaracterize an out-of-sample "reversal" as a confirmed result when no
pull had ever been executed (corrected in `CHANGELOG.md`, 2026-07-25,
"CORRECTION" entry). This document closes that gap retroactively, before
the already-built pull script is ever run — the tercile cutpoints and
decision rule below are locked from the ORIGINAL 76-event sample now,
prior to execution, exactly as they should have been from the start.

## 1. Original finding, cited to its exact source

**76-event real-quote sample**
(`Live Signal Engine/QC_Validation_CleanSample_v2_76Events.csv`),
`Attention Spread := fixed_window_zscore / real_cost_pct_of_spot`
(z-score joined from `FixedWindow_PerEvent_Canonical.csv` on `(ticker,
spike_week)`, since the validation sample itself has no z-score column —
same join already used for Hypothesis #5's original test).

- **Script**: `GST_AttentionSpread_Analysis.py`
- **Output**: `Live Signal Engine/AttentionSpread_Analysis.csv`

**Two distinct results from that script, both part of "the original
finding" and both in scope for this replication:**
1. **Linear/regression tests say the ratio is redundant with its own
   ingredients.** Raw z-score alone correlates with `real_pnl_pct` more
   strongly (Pearson r=+0.284) than Attention Spread does (r=+0.244); in
   a regression with both z-score and `real_cost_pct_of_spot` already
   included (R²=0.0898), adding Attention Spread gains R²=+0.0006 with a
   non-significant coefficient (p=0.825).
2. **A tercile split shows the opposite, unresolved by (1):** high
   tercile 56.0% win rate / +7.89% median `real_pnl_pct` (n=25) vs. low
   tercile 30.8% / -32.70% (n=26) — Mann-Whitney p=0.039 — a **cleaner**
   separation than the identical split done on raw z-score terciles
   (p=0.296, not significant).

**This out-of-sample test targets finding (2) specifically** — the
tercile-split claim — since that is the one with a concrete, lockable
rule (fixed cutpoints + a group comparison), matching what
`AttentionSpread_OOS_LockedSample.csv` and `QC_AttentionSpread_OOS_Pull.py`
were already built to test. Finding (1) is not re-tested here; it was
already a within-sample regression result, not a claim this specific
pull design can confirm or refute.

## 2. Locked tercile cutpoints — from the original sample, applied unchanged

Computed directly from `Live Signal Engine/AttentionSpread_Analysis.csv`
(verified again just before writing this document, not assumed from
memory):

- **Low**: Attention Spread ≤ **0.968673**
- **Mid**: 0.968673 < Attention Spread ≤ **1.344624**
- **High**: Attention Spread > 1.344624

**These cutpoints are fixed inputs to this test, not recomputed on the
fresh sample.** A fresh event is sorted into low/mid/high using these
exact numbers — the whole point of a locked cutpoint is that the test
asks "does the ORIGINAL boundary still separate outcomes on new data,"
not "do new terciles, computed on new data, separate outcomes" (the
latter would not be a replication test at all, just a redescription of
whatever the new data happens to look like).

## 3. Fresh sample — already drawn, re-verified here before locking

**Exclusion set**: every `(ticker, spike_week)` pair in
`QC_Validation_CleanSample_v2_76Events.csv` (n=76), the same sample
Attention Spread's original finding was computed on.

**Population**: `FixedWindow_PerEvent_Canonical.csv`,
`qualifies_z5==True & pnl_pct.notna()` (n=152, this project's sole
authoritative population).

**Eligible pool: n=76** (152 − 76). **Sample already drawn: n=45**,
ticker-proportional stratified random, `seed=314` — locked in
`Live Signal Engine/AttentionSpread_OOS_LockedSample.csv`. Re-verified
directly before writing this document: 0 overlap with the original
76-event sample, 0 keys outside the 152-event canonical population, 23
of 27 canonical tickers represented.

**Not disjoint from every other real-quote pull this project has run**
(the 152-event population is fully saturated by the union of all prior
pulls — see `H5_OutOfSample_PreRegistration.md` §2 for the same finding
applied to Hypothesis #5) — this sample overlaps with several other
tests' samples, including 27 of 45 events shared with
`H5_OutOfSample_LockedSample.csv`. Disclosed, not hidden: this test and
Hypothesis #5's out-of-sample test are not fully independent
replications of each other.

## 4. Methodology — the QC pull, reused, not redefined

`QC_AttentionSpread_OOS_Pull.py` (already built, committed `a2587c6`):
same contract-selection methodology as
`QC_Options_Validation_Script_v2_Expanded.py` (first listed expiration
on/after `exit_date`, ATM strike closest to entry-day close, real quoted
ask at entry / bid at exit, $0.65×4-leg fee, 25%-of-spot automated
corruption filter — **not relaxed for this test**, same as every other
pull this project has run). Produces `real_cost_pct_of_spot` and
`real_pnl_pct` per event; `Attention Spread` and tercile assignment are
computed locally afterward from `fixed_window_zscore / real_cost_pct_of_spot`
using the cutpoints in §2.

## 5. Binding decision rule (modeled on Hypothesis #5's structure, stated before execution)

**PASS**: the high-tercile group (Attention Spread > 1.344624, per the
locked cutpoint) shows both a higher win rate **and** a higher median
`real_pnl_pct` than the low-tercile group (Attention Spread ≤ 0.968673),
**and** a Mann-Whitney test between the two groups' `real_pnl_pct`
reaches p<0.05.

**WEAK**: the direction matches (high tercile better on both win rate and
median return) but p is in [0.05, 0.20) — log as "not tradeable," do not
spawn a new monetization hypothesis from it.

**FAIL**: the direction does not match on both win rate and median return
(including a tie or split direction), **or** p≥0.20, **or** either
tercile group has fewer than 8 usable events after real-quote attrition
(too thin to trust a rank-sum test) → the tercile-split finding does not
replicate. Given this project's own precedent
(`H5_OutOfSample_PreRegistration.md`§4's amendment), any result that
clears neither PASS nor WEAK is FAIL by elimination — stated here in
advance, not amended after the fact this time.

**No new metric, cutpoint, or threshold will be introduced after results
are observed.** Consistent with finding (1) in §1 already showing the
ratio is redundant with its own ingredients under a linear test, a PASS
or WEAK result here would specifically support the *rank/tercile*
mechanism, not overturn (1) — and a FAIL would mean neither the linear
nor the rank-based version of this metric has survived out-of-sample
testing.

## 6. Execution plan

1. **DONE.** Sample drawn and locked (§3), pull script written (§4;
   `a2587c6`) — both predate this document, re-verified here rather than
   retroactively trusted.
2. **DONE, this document.** Cutpoints (§2) and binding rule (§5) locked
   before the already-built pull script is ever executed.
3. **NOT YET RUN.** `QC_AttentionSpread_OOS_Pull.py` must be pasted into
   a QuantConnect Research notebook and run there — this environment
   cannot execute QuantConnect Research cells.
4. **NOT STARTED — cannot be run against real data yet.** Local
   computation of Attention Spread and tercile assignment using the
   locked cutpoints, followed by the binding decision rule in §5 exactly
   as written.

---

*End of pre-registration. The already-built pull script's execution
follows this file's commit, not the other way around — no results exist
yet for any event in this sample.*
