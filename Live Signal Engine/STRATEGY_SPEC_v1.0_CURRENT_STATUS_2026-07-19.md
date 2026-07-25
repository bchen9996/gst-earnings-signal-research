# Current Status — Authoritative Population, Superseded Figures, and Trading Readiness

**Last updated: 2026-07-19. Updated again (backfilled) on 2026-07-20T03:37:00Z.**
This is the single, current-state reference for: (1) which event
population is authoritative, and its point-in-time limitations, (2)
exactly how the two real-quote validation samples shrank from their
sampled size to their clean size, (3) whether any ticker is currently
cleared to trade with real capital, and (4) the status of the Candidate
A/B tests and the short-vol defensive-filter finding. Read this file
before citing any event count or acting on any trading recommendation
found elsewhere in this project.

> **BACKFILL NOTICE:** sections 1a, 5, and the short-vol item in section
> 3 were added on 2026-07-20, after the fact, following a consistency
> audit that found this file had gone stale for roughly the back half of
> the 2026-07-19 session. See `CHANGELOG.md`'s matching "BACKFILL NOTICE"
> entry for the full underlying findings — this file summarizes their
> consequences for current status only.

This file does not modify `STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md` (which
remains untouched, per its own governance clause) or rewrite any
`CHANGELOG.md` entry (which remains an append-only historical log). It
supersedes their population-count figures and trading-readiness framing
going forward, without altering the historical record of how those
figures were arrived at.

---

## 1. The ONE authoritative event population: n=152

**`Live Signal Engine/FixedWindow_PerEvent_Canonical.csv` (n=152) is the
sole authoritative STRONG_EARNINGS event universe for this project, as of
2026-07-19.** Every reference to "n=147" or "n=148" anywhere in this
project's documentation or scripts — including within
`STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md`, `STRATEGY_SPEC_v1.0_TERMINOLOGY.md`,
`SPY_Benchmark_Audit.md`, and every dated entry in `CHANGELOG.md` prior to
the "fixed-window per-event recompute" entry — refers to a population
that is now **superseded and historical**, preserved for audit-trail
purposes only. Neither should be treated as a live, current alternative
to the 152-event canonical set.

| Population | n | Method | Status |
|---|---|---|---|
| "GST-Legacy-v1" (the original archive) | 147 | Per-calendar-year chunked GST pulls | **SUPERSEDED / HISTORICAL.** Known cross-year rescaling-discontinuity risk (each year independently normalized to its own peak). |
| Quarantined continuous-window reconstruction | 148 | Single continuous 5-year GST pull per ticker | **SUPERSEDED / HISTORICAL — additionally QUARANTINED.** Confirmed, quantified look-ahead contamination (93/175 considered events flagged at risk; CHANGELOG.md, 2026-07-18 "look-ahead bias" entry). Never should have been cited as validated in the first place. |
| **Fixed-window per-event canonical** | **152** | Independent ~300-day GST pull per event, ending at that event's own date (never extending past it, never stitched across years) | **AUTHORITATIVE. Use this and only this going forward.** |

If any document not listed above is found still presenting 147 or 148 as
a live, current option alongside 152, treat that as a documentation bug —
152 is the only correct answer to "how many STRONG_EARNINGS events does
this project have."

---

## 1a. Point-in-time limitation on the n=152 baseline (added 2026-07-20 — read this before treating "152" as a live track record)

**The n=152 canonical baseline is the best-available RECONSTRUCTION of
this project's historical population — it is not a proven point-in-time
live track record, and this is a real, unresolved limitation, not a
technicality.** Every z-score behind every one of the 152 events (and
every figure built on it: the IV recalibration, the matched-control
comparisons, the volatility-surprise/directional-bias/pre-earnings-
pressure checks) was computed by querying Google Trends **today**, for a
window ending years in the past — not observed live at the time. A
forensic audit (`CHANGELOG.md`, "point-in-time forensic audit" entry,
2026-07-19) confirmed this is internally *reproducible* (the same query
run twice today gives the same answer) but explicitly **not provably
identical to what a real observer would have seen on Google Trends in
real time** on any of those historical dates — Google's own
documentation states recent/provisional Trends data can be revised, and
this project has no independent archived snapshot of historical Trends
values to check against. No waiver was found; the check is treated as
failed.

**What this does and doesn't change:** the 152-event population remains
the correct answer to "what does this project's validated methodology,
applied to reconstructed historical data, produce" — nothing in section
1 above is wrong on those terms. What it can no longer support is a
claim that this reconstruction proves what a live trader would actually
have observed and acted on historically. **The only genuinely point-in-
time-clean data this project produces going forward comes from
`gst-multiticker-forward-log`** (see §5) — GST values captured the
moment they're observable, with exact retrieval timestamp and query
window recorded, no retrospective reconstruction involved.

---

## 2. Real-quote validation sample attrition, reconciled

Two independent samples of the 152-event canonical population have been
pulled against real historical option quotes via QuantConnect. Both
shrank between "events sampled" and "events usable" — here is the exact
breakdown for each, in one place.

### Pass 1: 42 sampled → 37 clean

| Stage | n | Notes |
|---|---|---|
| Sampled (stratified: 10 top modeled winners, 10 top modeled losers, 10 random [seed=42], all 15 MSFT events, de-duplicated) | 42 | See `QC_Options_Validation_Script.py` |
| Failed to price at all (missing option chain, missing quotes, or other pull failure) | **4** *(inferred — see caveat below)* | Never produced a `real_pnl_pct` value |
| Successfully priced, pre-exclusion | 38 | |
| Excluded as corrupted (NFLX, spike_week=2025-01-19, `real_cost_pct_of_spot`=719% — broken strike/expiry match) | 1 | Manually spotted, not caught automatically (this gap is why pass 2 added an automated filter) |
| **Clean, usable** | **37** | `QC_Validation_CleanSample_37Events.csv` |

**Caveat on the "4 failed to price" figure:** this is *inferred*, not
directly observed — it was never independently confirmed against your
notebook's console output. It follows from stated arithmetic in this
conversation ("recompute stats on the remaining 37 events" after
excluding 1 corrupted event implies the pre-exclusion successfully-priced
count was 38, and 42 sampled − 38 = 4). If your notebook's actual console
output showed a different pre-exclusion count, this number should be
corrected.

### Pass 2: 90 sampled → 76 clean

| Stage | n | Notes |
|---|---|---|
| Sampled (ticker-proportional stratified random, seed=7, all 27 tickers with qualifying events represented) | 90 | See `QC_Options_Validation_Script_v2_Expanded.py` |
| Dropped (corrupted + failed-to-price combined) | 14 | **Sub-split NOT YET RECONCILED — see open item below** |
| **Clean, usable** | **76** | `QC_Validation_CleanSample_v2_76Events.csv` |

**OPEN ITEM, not yet resolved:** unlike pass 1, this project does not
have the exact corrupted-vs-failed-to-price split for the 14 dropped
events in pass 2. The v2 script prints both counts explicitly
(`Auto-flagged as corrupted: X`, `Failed/incomplete (other reasons): Y`)
when run, but that console output was never reported back and no export
of the full (not just clean) results table exists locally. **This table
is incomplete until that split is supplied** — the two counts are known
to sum to 14, not individually.

---

## 3. Current trading-readiness position

**Signal: validated. v1 straddle economics: rejected. Every ticker,
including MSFT: paper-trade only.**

- **The GST z-score → earnings-adjacent price-move relationship is
  validated evidence** (Cohen's d=1.294, p<0.0001 on raw realized price
  moves, independent of any options-pricing model — see
  `STRATEGY_SPEC_v1.0_TERMINOLOGY.md` §3). This finding is about price
  moves, not straddle P&L, and is unaffected by anything in this section.
- **The v1 straddle economics — the synthetic S=K=100 Black-Scholes
  pricing model documented in `STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md`
  §8, with `NEAR_EARNINGS_IV_MARKUP=1.2398` — are REJECTED.** Recalibrating
  that markup against real QuantConnect-quoted option costs (not the
  original project's own synthetic pricing) reverses the backtest's
  economics on the full 152-event canonical population:

  | | Win rate | Median P&L | Sharpe | Max DD |
  |---|---|---|---|---|
  | Original (uncorrected, markup=1.2398) | 76.3% | +145.5% | 2.222 | -3.6% |
  | Recalibrated v1 (n=37 real quotes, markup=3.6516) | 39.5% | -16.6% | -0.298 | -85.73% |
  | Recalibrated v2 (n=76 real quotes, markup=3.4098) | 43.4% | -10.7% | +0.273 | -46.37% |

  The estimate stabilized (not swung wildly) between v1 and v2 — this is
  not noise from a small sample. See `CHANGELOG.md`, both "IV markup
  recalibration" entries, for full methodology.

- **Therefore: no ticker, including MSFT, should be traded with real
  capital under the v1 pricing/sizing rules as currently specified.**
  `STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md`'s framing of "the MSFT trade
  planned for 2026-07-29" (§ header) predates this finding and should be
  read as **paper-trade only** — record signal detections, entries,
  exits, and (if obtainable) real quoted prices for comparison, but do
  not risk real capital on the v1 economics as documented.
- **What would change this:** either a larger real-quote recalibration
  sample that meaningfully revises the markup back toward profitability
  (unlikely given how stable v1→v2 was), or a redesigned pricing/sizing
  approach that is itself validated against real quotes before being
  traded — i.e., a genuine v1.1 forward-test track, not a patch to v1.0's
  frozen numbers.

- **Distinct, still-partially-open thread, added 2026-07-20 — does NOT
  change the "paper-trade only" verdict above:** a SHORT-side (sell the
  straddle, opposite of everything above) variant, tested against a GST
  defensive filter, showed a substantially *better* risk profile when
  high-GST dates were avoided — max drawdown -11.1%→-1.1%, expected
  shortfall flipping from negative to positive, worst trade -261%→-41%
  (`CHANGELOG.md`, "short-vol defensive-filter test" entry;
  `Live Signal Engine/ShortVol_DefensiveFilter_Test.csv`). **This is not
  a green light for real capital either** — 80 of 266 events approximate
  the short side as a negation of long-side data (understates true
  short-side risk), all 133 control events are modeled-only, and a
  follow-up real-quote pull built to fix this
  (`QC_ShortVol_ControlSample_Pull.py`, n=39) has not yet returned
  results. Treat as a promising but unconfirmed direction, not a
  strategy ready for paper- or real-money testing yet.

---

## 5. Candidate A/B tests: precise status (added 2026-07-20)

Both Candidate A (z≥10 vs. 5≤z<10 real-quote tier test) and Candidate B
(pre-earnings IV-expansion mechanism) were formally pre-registered
(`CandidateA_PreRegistration.md`, `CandidateB_PreRegistration.md`) with
binding decision rules, then pulled against real QuantConnect quotes.
**Neither reached a confirmed numerical result in this project's
records** — figures were referenced in conversation but never
independently verified against a results file or console output, despite
being asked for. **Separately and more importantly, both were
subsequently invalidated by the point-in-time finding in §1a before a
confirmed result would have mattered anyway.**

**Correct characterization for both: "never completed with a confirmed
result, and independently superseded by the point-in-time gate failure"
— not "passed" and not "failed."** An earlier request to reclassify a
stated Candidate B "failed" result as "unvalidated/inconclusive" was
declined at the time as an improper post-hoc reinterpretation of a
binding pre-registered rule; this section supersedes that exchange —
the failed/inconclusive distinction turned out to be moot, since no
confirmed result ever existed to classify either way.

**Candidate B's hypothesis is still live, just relocated**: a forward-
only version (`CandidateB_v1_FORWARD_LOCKED.md`, locked
2026-07-19T23:19:32Z) replaces the retrospective test, using
`gst-multiticker-forward-log`'s genuinely point-in-time-clean daily data
(§1a) rather than reconstructed historical z-scores, with its own
independent governance track. No forward data has been collected against
it yet. Candidate A's hypothesis has no forward-only successor as of
this entry.

---

## 7. Hypothesis #5 (volatility mispricing): out-of-sample result — DEAD (added 2026-07-25)

The volatility-surprise finding (z-score vs. `realized_move_pct −
implied_move_pct`, `CHANGELOG.md`'s "volatility-surprise check" entry,
Pearson r=0.407, n=76) was pre-registered for out-of-sample replication
(`Live Signal Engine/H5_OutOfSample_PreRegistration.md`) against a fresh,
disjoint sample (n=49, hard-excluded by event ID from the original 76).

**Result: DEAD. r=0.1065, p=0.4664 (n=49) — not statistically
distinguishable from zero.** Classified FAIL under the pre-registration's
binding decision rule (amended, after seeing this result, to close a gap
where r=0.1065/p=0.4664 satisfied none of the three originally-stated
conditions — the amendment moved the bar stricter, not looser; full
detail and the amendment text itself are in the pre-registration file,
appended not edited). Same fate as Attention Spread's tercile finding: a
promising original-sample correlation did not survive out-of-sample
replication. Full writeup: `CHANGELOG.md`, "2026-07-25 — Hypothesis #5
(volatility mispricing) out-of-sample test" entry.

**Limitation carried forward:** the 49-event replication sample has zero
representation from NFLX, NVDA, COHR, and DELL (all excluded by the
unmodified real-quote corruption filter) — this DEAD verdict is about the
pooled relationship among the other 23 tickers, not a claim that
generalizes to those four specifically.

**No further monetization hypothesis should be built on this
correlation.** This does not affect the separately-validated finding in
§3 (GST z-score → realized price-move magnitude, Cohen's d=1.294) — that
finding is about move *size*, not about whether the options market
mispriced that move, which is what Hypothesis #5 specifically tested and
which did not replicate.

---

## 8. C5 (post-earnings continuation/reversal): near-miss, does not clear the bar (added 2026-07-25)

Tests whether GST z-score predicts continuation vs. reversal of the
earnings-day gap over the following 5 trading days (day-5 primary
horizon), controlling for gap magnitude, ticker, BMO/AMC timing, market
volatility, sector return, and calendar year. Pre-registered:
`Live Signal Engine/C5_PostEarnings_PreRegistration.md`. Sample: n=235
(151 canonical signal events + 84 unique matched non-GST controls, each
with its own continuous z-score, not an assumed z=0).

**Result: does not clear the binding decision rule, but by a narrow
margin.** Ticker-clustered regression: β1(z)=+0.00095, SE=0.00049,
**p=0.0512** (clustered 95% CI [-0.00000, +0.00190]); ticker-cluster
block bootstrap (N=10,000): 95% CI [-0.00002, +0.00204] — both intervals
touch zero at the lower bound. The decision rule required significance
under **both** the clustered SE **and** the bootstrap CI; neither
technically clears p<0.05. **Sign stability held across all 32
leave-one-ticker-out/leave-one-year-out refits** (β1 stayed positive
throughout, range [+0.00048, +0.00125]) — the result is not an artifact
of any single ticker or year, it simply isn't statistically significant
at the pre-registered threshold. Secondary diagnostics (same-day, day-2,
day-20) showed no effect at day-0/day-2 and a sign flip by day-20 —
consistent with a real-but-weak, slow-building effect rather than noise
concentrated at one arbitrary horizon (descriptive framing only, not
part of the binding rule). Full detail: `GST_C5_PostEarnings_Analysis.py`
console output, `Live Signal Engine/C5_PostEarnings_Analysis_Results.csv`.

**Status: neither PASS nor a clean FAIL — a near-miss, reported as such,
not rounded in either direction.** No trading or monetization decision
should be built on this result as it stands.

---

## 9. Attention Spread: original finding is an unresolved linear-vs-rank tension, not a confirmed edge (added 2026-07-25)

Tests `Attention Spread := zscore / real_cost_pct_of_spot` on the
76-event real-quote sample (`Live Signal Engine/AttentionSpread_Analysis.csv`,
`GST_AttentionSpread_Analysis.py`) — same population Hypothesis #5 (§7)
draws its original-sample finding from.

**Linear tests say the ratio is redundant with its own ingredients:**
raw z-score alone correlates with `real_pnl_pct` more strongly (r=+0.284)
than Attention Spread does (r=+0.244); in a regression with both z-score
and `real_cost_pct_of_spot` already included (R²=0.0898), adding
Attention Spread gains R²=+0.0006 and its own coefficient is not
significant (p=0.825). Not circular in the sense of just tracking cost
(Attention Spread correlates more with its own numerator, z-score,
ρ=+0.721, than its denominator, cost, ρ=-0.513) — but redundant with the
two ingredients taken together.

**A rank-based test shows the opposite, unresolved by the above:**
splitting into terciles, the high tercile shows 56.0% win rate / +7.89%
median return vs. the low tercile's 30.8% / -32.70% (Mann-Whitney
p=0.039) — a **cleaner** separation than the same tercile split done on
raw z-score alone (p=0.296, not significant). This is flagged explicitly
as an unresolved linear-vs-nonlinear tension, not forced into one
verdict, and not corrected for running three tests on the same 76 points
without a multiple-comparisons adjustment.

**Out-of-sample confirmatory test: designed and locked, but NEVER
EXECUTED — no "reversal" has actually been confirmed against real data.**
A fresh n=45 sample (seed=314, disjoint from the original 76) was drawn
and `QC_AttentionSpread_OOS_Pull.py` was built
(`Live Signal Engine/AttentionSpread_OOS_LockedSample.csv`), but this
environment cannot run QuantConnect Research cells, and no results file
or pasted output for this specific pull exists anywhere in this
project as of this entry — confirmed by direct filesystem search before
writing this section, not assumed. **Any reference elsewhere to an
Attention Spread "reversal" refers to the in-sample linear-vs-rank
tension above, not a completed, confirmed out-of-sample replication —
that test remains pending.**

---

## 6. Where corrections were and were not made

Per this project's established governance (frozen documents and
append-only logs are not rewritten in place), this status file is the
correction — not edits to the underlying documents' historical numbers.
Specifically:
- `STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md`: unchanged except for a short
  dated pointer banner at the top directing readers here, given the
  real-capital stakes of leaving stale "the MSFT trade" language
  unqualified.
- `STRATEGY_SPEC_v1.0_TERMINOLOGY.md`: unchanged except for a short
  pointer added to §1 noting 147 is superseded by 152 (the precise
  147/112/35 breakdown itself remains historically accurate and is not
  deleted).
- `CHANGELOG.md`: unchanged (append-only log preserved exactly as
  written); a short pointer banner added at the very top of the file
  only. **Update, 2026-07-20:** nine entries backfilled at the end,
  covering everything from the point-in-time audit through the
  ticker-persistence test — see its own "BACKFILL NOTICE" for exactly
  what was added and why.
- `SPY_Benchmark_Audit.md`: unchanged except for a short pointer footnote.
- **This file itself, 2026-07-20:** sections 1a and 5 added, and the
  short-vol item added to section 3 — all new content, addressing a
  consistency-audit finding that this file had gone stale for roughly
  the back half of the 2026-07-19 session (missing the point-in-time
  finding entirely, and silent on Candidate A/B and the short-vol test).
  No existing sentence in sections 1-4 was altered.
- **This file itself, 2026-07-25:** section 7 added, marking Hypothesis
  #5 (volatility mispricing) dead after its out-of-sample replication
  failed (`CHANGELOG.md`, "2026-07-25" entry;
  `Live Signal Engine/H5_OutOfSample_PreRegistration.md` for the full
  pre-registration, supplemental-draw, and decision-rule-amendment
  trail). No existing sentence in sections 1-6 was altered.
- **This file itself, 2026-07-25 (later same day):** sections 8 and 9
  added, closing a gap found during an independent verification pass —
  a handoff doc had claimed this file was updated to cover the C5
  near-miss and the Attention Spread finding/reversal, but neither term
  had any real presence in this file before this edit (confirmed by
  direct grep, not assumed from section numbering). Section 8 reports
  C5's near-miss result (p=0.0512, does not clear the pre-registered
  bar) precisely, without rounding it into a pass or a clean fail.
  Section 9 corrects an overclaim risk head-on: it documents the
  Attention Spread finding as an unresolved linear-vs-rank tension and
  states explicitly that no out-of-sample "reversal" has actually been
  run or confirmed against real data — the confirmatory pull was built
  and locked but never executed, verified by direct filesystem search
  before writing this section. No existing sentence in sections 1-7 was
  altered.
