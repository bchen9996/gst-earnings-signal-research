# Changelog — measurement/data-quality findings

This file logs data-measurement and calculation-fidelity findings that do
**not** change any STRONG_EARNINGS strategy rule (query, threshold,
window, entry/exit timing, pricing, sizing, cost assumptions — see
`STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md`, which is never edited in
place). Entries here explain what was found, what was and wasn't changed,
and what it implies for confidence in existing numbers. This is
distinct from `STRATEGY_SPEC_v1.0_TERMINOLOGY.md` (precise definitions of
existing figures) — this file is specifically for data/calculation
findings discovered after the v1.0 freeze.

> **POINTER (2026-07-19):** this log is append-only and preserved exactly
> as written below — entries citing "n=147" or "n=148" reflect what was
> understood at the time and are NOT rewritten here. The current
> authoritative population (n=152), the superseded status of 147/148, the
> real-quote validation sample reconciliation, and the current
> trading-readiness position (paper-trade only, v1 economics rejected)
> are all consolidated in
> `STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` — read that file for
> the current state; read this file for the historical trail of how it
> was reached.

---

## 2026-07-18 — GST window-normalization discrepancy (live engine vs. historical backtest)

**Finding:** the live signal engine (`GST_Live_Signal_Engine.py`) computes
z-scores from a single continuous ~300-day Google Trends pull. The
historical backtest that produced the validated 147-event population
(`GST Weekly Data Gathering (...).py` scripts) was built from
**per-calendar-year chunked pulls**, concatenated. Google Trends
renormalizes its 0-100 scale to the peak *within each queried window*
(confirmed against Google's own Trends Help documentation — see
sources in-conversation). Per-year chunking means each year's values are
anchored to a different, independent peak; a single continuous pull has
one peak anchor across its entire window. **The chunked method used to
build the historical backtest carries a real, Google-documented
rescaling-discontinuity risk that the live engine's continuous-pull
method does not have.**

**Action taken: NONE to the live engine.** The live engine already uses
the more sound method — there is nothing to fix there. No code was
changed as a result of this finding.

**Verification performed:** recomputed all 15 of MSFT's archived
STRONG_EARNINGS events using the live engine's continuous-window method.
2 of 15 (2023-07-23, 2024-10-27 — both originally wins) flip below z=5
under the corrected measurement. Recomputed subset: **n=13, 9 wins,
69.2% win rate** (vs. the archived 73.3%, 11/15). Detail:
`Live Signal Engine/MSFT_ContinuousWindow_Recompute.csv`.

**Disclosed gap:** this check only re-scored the 15 dates already known
to qualify under the old method. It did not scan MSFT's full weekly
history for previously-sub-5 weeks that might newly cross 5 under the
continuous method, which could partially offset the two that dropped
out. **69.2% is a lower-bound-style revision, not a confirmed final
number** — a full resolution requires rescanning MSFT's entire weekly
series, which was out of scope for this pass.

**Governance:** classified as a **data-measurement finding, not a
strategy rule change.** The z≥5 threshold and the 12-week/min_periods=8
rolling formula are unchanged; only the fidelity of the underlying pull
methodology is in question. Per the same reasoning applied to the
year-boundary NaN-drop bug and the SPY benchmark bug (both logged
without triggering v1.1), this does not require a new
`STRATEGY_SPEC_v1.1` governance track. It is logged here, distinctly
from those two, because — unlike a bug that fixes obviously-missing
data — this one moves a real, previously-cited number (73.3%→69.2% for
MSFT) rather than correcting an unambiguous data gap, and is flagged as
the closer call of the three.

**Open follow-up, not yet done:** the full 147-event historical backtest
was built with the same per-year-chunked method and has the same latent
exposure. A complete correction would mean re-pulling the entire
2021–2025 GST history per ticker as continuous multi-year queries
(instead of chunked-by-year) and rebuilding the z-score series and
STRONG_EARNINGS population from that corrected data. That is a
significant undertaking, not performed here — flagged as a real
candidate for follow-up work, separate from and larger than this
MSFT-specific check.

## 2026-07-18 (later same day) — full-population continuous-window recompute (the follow-up above, done)

**What was done:** the MSFT-only follow-up above was completed for the
full 28-ticker / 147-event population. Discovered that a single pytrends
query longer than ~5 years silently falls back from weekly to MONTHLY
granularity (a 2020-10-to-2025-12 pull returned 63 monthly points, not
~273 weekly ones) — worked around by pulling exactly `2021-01-01` to
`2025-12-31` (5 years flat) per ticker, one continuous call each (28
total calls instead of the ~7,280 a naive per-week rescan would have
needed), confirmed to return the expected 262 weekly points. Re-ran the
full original pipeline (spike detection at z>=2, 21-day dedup, symmetric
+/-5-day near-earnings check, Black-Scholes pricing) against this
corrected input, for every ticker's entire weekly history — the "fuller
scan" the MSFT-only entry above disclosed as missing.

**Population comparison:** of the original 147 events, **22 dropped**
(no longer clear z>=5 under the continuous method — notably including a
few with substantial original z-scores, e.g. COHR 2024-02-04 at z=9.23
and NVDA 2024-02-18 at z=9.71, not just borderline ones) and **27
newly qualify** (previously below z>=5, now clear it, after excluding 1
corrupted reading — see bug below). Net: **~33% of the population
turned over** (49/147 events changed status). Full detail:
`Live Signal Engine/FullPopulation_ContinuousWindow_Recompute.csv`.

**New, separate bug found and NOT fixed:** the z-score formula
(`(gst - rolling_mean) / rolling_std`) has no floor on `rolling_std`. Two
GME readings came back at z~2,019,407 and z~2,137,083 — a rolling
window where GME's GST value was apparently flat for a stretch,
collapsing the standard deviation toward zero and blowing up the
division. Both excluded from all reported statistics below (treated as
indeterminate, not as evidence of a real spike). This is a distinct
robustness gap from the windowing/rescaling issue above — worth a
`rolling_std` epsilon guard eventually, not addressed here.

**Aggregate result (n=149, corrupted GME readings excluded):**

| | n | Win rate | Median P&L | Sharpe | Max DD |
|---|---|---|---|---|---|
| Original (chunked) | 147 | 76.2% | +130.0% | 2.33 | -3.3% |
| Recomputed (continuous, clean) | 149 | 76.5% | +145.8% | 2.23 | -4.1% |

**Conclusion: despite ~33% event-level turnover, the aggregate strategy
edge is not materially changed** — win rate and median P&L hold or
improve slightly, Sharpe and max drawdown move slightly in the
unfavorable direction but stay strong. Individual "did this exact
historical date qualify" is measurement-sensitive; the strategy's
aggregate edge is not.

**Governance:** same classification as the MSFT-only entry above — a
data-measurement correction to the SAME rule (z>=5, 12-week/
min_periods=8 formula, symmetric +/-5-day earnings window), not a rule
change. No `STRATEGY_SPEC_v1.1` track triggered.

**Not done / still open:** the archived `group_a_z4_earnings_adjacent.csv`
and all downstream files that cite "n=147" have NOT been regenerated or
replaced — this recompute lives in its own output file
(`FullPopulation_ContinuousWindow_Recompute.csv`) alongside, not instead
of, the original. Deciding whether to formally supersede the archived
147-event population with this 149-event one is a separate decision,
not made here.

## 2026-07-18 (later same day) — rolling_std epsilon-floor fix + full 28-ticker rescan

**Fix applied:** `STD_EPSILON_FLOOR = 1.0` added to the z-score formula's
denominator (`roll_std.clip(lower=1.0)` before dividing), in **both**
`GST_Live_Signal_Engine.py` (`compute_latest_zscore`, the actual
production code that runs the MSFT check) and
`GST_FullPopulation_ContinuousWindow_Recompute.py` (`compute_zscore`).
Epsilon chosen to match `gst`'s integer 0-100 resolution — the smallest
std that could reflect genuine non-zero variation on that scale. This
does not change the z-score formula's shape or the z>=5 threshold for
any well-behaved input; it only bounds the output when the trailing
window's variance is degenerate. Not a rule change.

**Full rescan result (all 28 tickers, complete weekly history,
2021-2025):** 197 total weeks where the floor activated (raw std <
1.0). **189 of these are GME** — this is not a couple of isolated bad
data points, it's structural: GME's weekly search interest sits at 1-2
(on the 0-100 scale) for long stretches, so its rolling std is
chronically near-zero throughout large parts of its history, not just
at the two dates originally found. NFLX had 6 activations (std 0.65-0.97,
not degenerate) and NVDA had 2; neither changed any event's qualification
status after flooring — the floor only trimmed their z magnitude
slightly, all still landed the same side of the z>=5 line as before.

**Correction to the same-day entry above:** that entry reported GME
2023-03-19 (continuous z=6.08, unfloored) as "clean... confirmed
retained, reliable." **This was wrong** — this full rescan shows that
event's raw std was already low (0.452, just not obviously absurd like
the million-scale readings), and its properly-floored z-score is
**2.75**, well below threshold. It should not have been counted as
retained.

**GME's two previously-unresolved events, now resolved with the fixed
formula:**
- 2025-09-07: floored z = **1.00** — does not clear z>=5.
- 2024-03-24 (candidate): floored z = **1.00** — does not clear z>=5,
  was never a real new candidate.

**Combined effect: GME contributes ZERO legitimate STRONG_EARNINGS
events** under the corrected calculation, not 2 as archived. Both of its
original wins (+386.9% on 2023-03-19, +10.4% on 2025-09-07) were
std-collapse artifacts, not genuine relative search-interest spikes.

**Updated aggregate (final, floor-corrected):**

| | n | Win rate | Median P&L | Sharpe | Max DD |
|---|---|---|---|---|---|
| Original (chunked) | 147 | 76.2% | +130.0% | 2.33 | -3.3% |
| Continuous recompute, pre-floor-correction | 149 | 76.5% | +145.8% | 2.23 | -4.1% |
| **Continuous recompute, floor-corrected (final)** | **148** | **76.4%** | **+145.5%** | **2.22** | **-2.6%** |

Dropped from original 147: 24 (22 found previously + GME's 2). Removing
GME's one large winner barely moves the aggregate; the strategy's
edge remains stable despite the correction.

**Governance:** same classification as both entries above — numerical-
stability guard on an unchanged formula/threshold, not a rule change. No
`STRATEGY_SPEC_v1.1` track triggered.

**Still open:** whether to formally supersede the archived 147-event
population with the 148-event corrected one is a separate decision, not
made here. GME's broader suitability for this signal methodology (given
189/262 weeks show near-zero variance) is also worth a dedicated look
beyond just flooring its z-score — flooring prevents nonsense output,
it doesn't make GME's underlying search-volume data any more informative.

## 2026-07-18 (later still) — look-ahead bias found in the full-population recompute (148-event set now provisional)

**Finding:** `GST_FullPopulation_ContinuousWindow_Recompute.py` pulled
each ticker's entire 2021-2025 history in ONE query, for efficiency (28
calls instead of thousands). Google Trends rescales its integer 0-100
output to the peak *within the queried window* — a single 5-year query
means every week, including early-2021 ones, is normalized against
whatever the eventual 5-year peak turns out to be, even when that peak
lands years later. A pure linear rescale wouldn't distort a z-score
(scale-invariant), but **rounding to an integer on top of the rescale
does**: an event normalized against a distant, larger future peak gets
compressed into a narrower integer range, which mechanically produces
more tied/repeated values and artificially collapses rolling variance —
the same root mechanism as the std-floor bug (GME's 189 collapses)
found earlier, not a separate coincidence.

**This does NOT affect:** the MSFT 15-event recompute
(`MSFT_ContinuousWindow_Recompute.csv`) or the 10-event reproducibility
audit — both used per-event pulls ending shortly after each specific
date, never extending into that event's future. Those remain
look-ahead-safe.

**This DOES affect:** the 148-event full-population recompute, and
everything built on it since (`EventReconciliation_Ledger.csv`,
`MembershipGroup_Breakdown.csv`).

**Quantified (re-pulled all 28 tickers, found each one's actual
2021-2025 peak date, flagged every considered event whose date precedes
its ticker's peak):** **93 of 175 considered events (53%) flagged at
risk.** By ledger category:

| Category | n | At risk | % |
|---|---|---|---|
| retained_confirmed | 123 | 62 | 50% |
| dropped_original_only | 22 | 11 | 50% |
| **newly_qualifying_confirmed** | 25 | **18** | **72%** |

The newly-qualifying group — the events the "correction" added — is the
**most** contaminated, not the least. Detail:
`Live Signal Engine/LookAhead_Audit_Results.csv`.

**Verdict: the 148-event population, the reconciliation ledger, and the
membership-group breakdown are PROVISIONAL, not authoritative.** They
should not be cited as "what the live engine would have shown at the
time" without redoing the scan with per-event pulls (window ending
shortly after each date, not extending to 2025) for at least the 93
flagged events, ideally all 175 for consistency. Not done here — a
real, scoped follow-up, not a quiet patch.

**Governance:** this is a data-measurement finding about MY OWN
recompute methodology in this investigation, not about the live engine
or the original archived backtest — it doesn't change any strategy rule
and doesn't trigger `STRATEGY_SPEC_v1.1`. It does mean the 148-event
figure should not yet be treated as a validated replacement for the
archived 147.

## 2026-07-19 — signal-tiering enhancement: HIGH_CONFIDENCE_STRONG_EARNINGS

**What changed:** `GST_Live_Signal_Engine.py` and
`GST_EarningsFirst_Scanner.py` now split the existing STRONG_EARNINGS tier
into two labels: **HIGH_CONFIDENCE_STRONG_EARNINGS** (z>=10, same
earnings-proximity check as before) and **STRONG_EARNINGS** (z=5-9.99,
unchanged otherwise). This is a classification layer only — the z-score
formula, the z>=5 qualifying threshold, and the earnings-window logic
(`EARNINGS_WINDOW_DAYS=5`) are all byte-for-byte unchanged. Every event
that would have been labeled STRONG_EARNINGS before this change still
clears the same bar; it just now carries a more specific label above
z=10.

**Evidence basis (verified before making this change, not taken on
faith):** re-derived directly from
`Live Signal Engine/MatchedControlGroup_Results.csv` (event-level rows,
n=147):

| Group | n | Win rate | Median matched-control excess |
|---|---|---|---|
| z>=10 | 33 | 93.9% | +186.9 pts |
| z=5-9.99 | 114 | 71.1% | +38.6 pts |

**Important disclosed gap:** this evidence comes from the **archived
147-event population ("GST-Legacy-v1", the original per-calendar-year
chunked method)** — it has not yet been re-derived against the new
canonical fixed-window population
(`Live Signal Engine/FixedWindow_PerEvent_Canonical.csv`, n=152), which
supersedes the archived 147 per the 2026-07-19 canonical-baseline entry
above. The z>=10/z=5-9.99 split used to justify this tiering enhancement
has not been reconfirmed under that corrected methodology. This is a
real limitation on the evidence behind the new label, not a hidden one —
a follow-up recompute of this same split against the canonical 152-event
set would strengthen (or could revise) the specific win-rate/excess-return
figures cited above, though it would not change the mechanics of the
tiering itself.

**Governance:** purely an additive reporting/monitoring label on top of
the existing validated STRONG_EARNINGS tier — no threshold, formula, or
entry/exit/pricing rule changed, so this does not trigger
`STRATEGY_SPEC_v1.1`. Both tiers continue to be treated identically for
any actual trading decision described in `STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md`;
HIGH_CONFIDENCE_STRONG_EARNINGS is a monitoring/analysis distinction, not
(yet) a differently-sized or differently-executed position.

## 2026-07-19 (later same day) — z>=10 vs z=5-9.99 split reconfirmed against the canonical population (with a revision)

**What was done:** the disclosed gap in the entry above (the tiering
evidence came from the archived 147-event population, not the canonical
152-event one) is now closed. Built
`GST_MatchedControlGroup_CanonicalRecompute.py`: same matching methodology
as the original (`GST_MatchedControlGroup.py` — same-ticker-different-quarter
first, cross-ticker/sector/cap fallback, same BMO/AMC + trailing-vol-band
filters, same Black-Scholes control pricing), but the SIGNAL side now
reuses `FixedWindow_PerEvent_Canonical.csv`'s own entry/exit/pnl_pct/win
directly (single source of truth) rather than re-pricing it — only the
matched CONTROL side is newly priced. Detail:
`Live Signal Engine/MatchedControlGroup_CanonicalRecompute.csv`, summary:
`Live Signal Engine/MatchedControlGroup_CanonicalRecompute_Summary.csv`.

**Result: the qualitative pattern holds — z>=10 still meaningfully
outperforms z=5-9.99 on every measure — but the magnitude is smaller than
the archived-population figures cited in the entry above:**

| | n (matched+priced) | Win rate | Median P&L | Median matched-control excess | 95% CI | % outperform control |
|---|---|---|---|---|---|---|
| z>=10 (archived 147, prior entry) | 33 | 93.9% | — | +186.9pt | not computed at the time | — |
| z>=10 (canonical 152, this recompute) | 40 | 92.5% | +214.9% | **+72.3pt** | [+0.0, +189.0] | 62.5% |
| z=5-9.99 (archived 147, prior entry) | 114 | 71.1% | — | +38.6pt | not computed at the time | — |
| z=5-9.99 (canonical 152, this recompute) | 93 | 69.9% | +130.0% | **+11.6pt** | [+0.0, +84.7] | 53.8% |

Win rates and median P&L are close to the archived figures (both within
~2 points). **Matched-control excess return roughly halved for z>=10 and
roughly a third of its prior size for z=5-9.99** — both group's 95% CIs
now touch $0 at the lower bound, meaning the "beats a matched control"
claim is now the weaker part of the finding, not the win-rate/P&L
difference between the two tiers (which remains clear and unchanged in
direction).

**Broader context, not just the tier split:** the aggregate matched-
control excess (all matched+priced events pooled, not split by z) also
weakened versus the archived-population run: n=127→133,
median diff +75.24pt→+35.7pt, 95% CI [+19.72,+106.89]→[+0.0,+91.4] (no
longer clearly excludes zero), % outperforming control 65.4%→56.4%. This
is a real, disclosed softening of the matched-control-excess evidence
under the corrected methodology — it does not reverse the core win-rate/
P&L finding, but it means "beats a matched control by a wide margin" is a
noticeably less certain claim than it was under the archived 147-event
population.

**Attrition:** 152→133 usable (19 events had a match found but were
unpriceable, 0 had no match at all).

**Conclusion for the tiering enhancement above:** the HIGH_CONFIDENCE_STRONG_EARNINGS
split remains justified — z>=10 events are still a meaningfully
higher-quality subset by win rate and P&L under the canonical
methodology — but the matched-control-excess magnitudes originally cited
should be treated as directionally confirmed, not precisely reconfirmed;
the canonical, weaker-but-still-positive figures above (+72.3pt / +11.6pt)
are now the current best estimate and should be cited in preference to
the archived-population figures (+186.9pt / +38.6pt) going forward.

**Governance:** same classification as the entry above — this is
re-verification of the EVIDENCE behind an already-made classification
change, not a further rule change. No threshold, formula, or entry/exit/
pricing rule is touched. No `STRATEGY_SPEC_v1.1` track triggered.

## 2026-07-19 (later still) — IV markup recalibration against real QC option quotes (MAJOR FINDING — flips backtest economics)

**What was done:** the first-ever check of `NEAR_EARNINGS_IV_MARKUP=1.2398`
(originally derived from `iv_calibration_buckets.csv`, a purely
historical-return-based source, never against a real quoted option price)
against genuine market data — the 37 clean, non-corrupted events from the
QuantConnect AlgoSeek validation (NFLX 2025-01-19 excluded as corrupted,
see the validation entries above). Built
`GST_Recalibrate_IV_Markup.py`:

1. Split the 37 events into a **calibration subset (n=25) and holdout
   subset (n=12)**, fixed `seed=42`, to guard against overfitting a
   correction to the same data it's tested on.
2. On the CALIBRATION subset only: `correction_factor =
   mean(real_cost_pct_of_spot) / mean(model_implied_cost_pct) = 2.9453`.
   `new_markup = 1.2398 x 2.9453 = 3.6516`.
3. **Validated out-of-sample on the untouched HOLDOUT subset** (approximating
   the new model cost as `old_model_cost x correction_factor`, since an
   ATM straddle's price is close to linear in implied vol at these short
   [4-6 day] tenors — the Brenner-Subrahmanyam approximation; the exported
   validation file only contains the already-computed model cost, not each
   event's underlying T/sigma, so an exact per-event Black-Scholes
   re-inversion wasn't possible from this data):

   | | Median abs pricing error | Mean abs pricing error | Mean signed bias |
   |---|---|---|---|
   | OLD markup (1.2398) | 3.378 | 4.021 | -4.021 |
   | NEW markup (3.6516) | 1.344 | 1.743 | -0.296 |

   **10 of 12 holdout events improved.** The new markup is clearly better
   calibrated out-of-sample — not just fit to the calibration data — and
   the mean bias collapses from a heavy, consistent underestimate (-4.02)
   to near zero (-0.30).

4. Only because step 3 validated: re-ran the full 152-event canonical
   backtest's pricing (`price_event()`, exact recomputation with each
   event's own real T/sigma from local daily-return data — not the linear
   approximation used for holdout validation) with the new markup. Detail:
   `Live Signal Engine/FixedWindow_PerEvent_RecalibratedPricing.csv`.

**Result — this is a major, not marginal, finding:**

| | n | Win rate | Median P&L | Sharpe | Max DD |
|---|---|---|---|---|---|
| ORIGINAL (markup=1.2398) | 152 | 76.3% | +145.5% | 2.222 | -3.6% |
| **RECALIBRATED (markup=3.6516)** | 152 | **39.5%** | **-16.6%** | **-0.298** | **-85.72%** |

**The corrected markup does not merely shrink the edge — it reverses it.**
56 of 152 events (37%) flip their win/loss classification. Under a markup
calibrated to match real market-quoted option costs, this strategy is a
net LOSER on the same 152-event population that showed a strong positive
edge under the original (uncalibrated) synthetic pricing.

**Why this happened, mechanically:** `pnl_pct = (intrinsic - cost) / cost
x 100`. `intrinsic` (the realized market move) doesn't depend on the
markup at all — only `cost` does. The original markup priced straddles at
roughly 1/3 of what real market quotes show they actually cost, so nearly
every event's realized move looked cheap relative to an artificially low
cost basis. Correcting the cost basis to match reality means the same
realized moves are no longer large enough, on net, to clear a realistic
cost.

**Important scope caveat, disclosed not hidden:** this recalibration
corrects the ENTRY-COST side of the model only (`real_cost_pct_of_spot`
is the real quoted ASK price at entry) — per the exact framing requested.
It does NOT independently re-verify the EXIT/payout side (the model's
synthetic "intrinsic realized move" vs. a real quoted EXIT BID), which
could carry its own separate miscalibration not addressed here. It's also
worth noting `real_cost_pct_of_spot` reflects the full retail ASK price
(bid-ask spread included), so part of this correction factor reflects
genuine execution-cost reality (crossing the spread), not purely an
implied-volatility assumption error — both are real costs a live trader
would actually pay, but they are conceptually distinct, and this
recalibration does not separate them.

**THIS IS A FIRST-PASS ESTIMATE ON A SMALL SAMPLE (n=37, holdout n=12),
NOT A FINAL CALIBRATION.** A correction factor this large (2.95x), derived
from 12 out-of-sample holdout points, warrants a larger real-data
validation (the originally-planned 30-50-event QC pull, once the
remaining events beyond the 37 clean ones are priced, and ideally the
excluded/failed events investigated too) before being treated as
conclusive. The direction (original pricing understates true cost) is
credible and holdout-validated; the exact magnitude (3.65 vs. some other
value in a plausible range) is not yet pinned down with confidence.

**Governance:** this is the single most consequential finding logged in
this file to date — it bears directly on whether the STRONG_EARNINGS
edge, AS PRICED in every backtest in this project
(`STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md`'s synthetic S=K=100 Black-Scholes
model), reflects a real, tradeable edge or an artifact of underpriced
execution cost. This does NOT itself trigger `STRATEGY_SPEC_v1.1` (no
z-threshold, window, or timing rule changed) — but it is a direct,
material challenge to the ECONOMIC validity of every P&L figure in this
project's entire history, pending a larger real-data recalibration. Do
not treat the original 76.3%-win/+145.5%-median figures as the
best-available economic estimate going forward without weighing this
finding.

## 2026-07-19 (later still) — IV markup recalibration v2: 76-event real-quote sample (up from 37) — first-pass finding holds

**What was done:** the real-quote validation sample was expanded from 37 to
**76 clean events** (a ticker-proportional stratified random sample, n=90
sampled, 14 auto-excluded by the new corruption filter or otherwise
unpriceable — see the QuantConnect validation entries — leaving 76
clean, not top-winner/loser-biased). Built `GST_Recalibrate_IV_Markup_v2.py`,
same method as the v1 script, re-parameterized for the larger sample:

1. Split into calibration (n=55) / holdout (n=21), same `seed=42`.
2. `correction_factor = mean(real_cost_pct_of_spot) /
   mean(model_implied_cost_pct)` on the calibration subset =
   **2.7503** (v1 was 2.9453). `new_markup = 1.2398 x 2.7503 =
   **3.4098**` (v1 was 3.6516).
3. Holdout validation (n=21, larger than v1's n=12):

   | | Median abs pricing error | Mean abs pricing error | Mean signed bias |
   |---|---|---|---|
   | OLD markup (1.2398) | 4.114 | 4.743 | -4.555 |
   | NEW markup (3.4098) | 1.726 | 2.821 | +0.394 |

   **18 of 21 holdout events improved** (v1 was 10/12) — the correction
   validates even more strongly with the larger sample.

**The estimate is STABLE, not swinging wildly, with ~2x the data:**
markup moved from 3.6516 -> 3.4098, a **-6.6% change**. This is a real,
meaningful, but modest revision — not a sign the first-pass estimate was
noise. Detail: `Live Signal Engine/FixedWindow_PerEvent_RecalibratedPricing_v2.csv`
(includes ORIGINAL, v1, and v2 pricing side by side for every event).

**Three-way comparison, full 152-event canonical backtest:**

| | Win rate | Median P&L | Sharpe | Max DD |
|---|---|---|---|---|
| ORIGINAL (markup=1.2398, uncorrected) | 76.3% | +145.5% | 2.222 | -3.6% |
| V1 RECALIBRATED (markup=3.6516, n=37) | 39.5% | -16.6% | -0.298 | -85.73% |
| **V2 RECALIBRATED (markup=3.4098, n=76)** | **43.4%** | **-10.7%** | **+0.273** | **-46.37%** |

**The core finding from the first pass holds up: this is not noise from
a small sample.** The strategy's edge, once priced against real market
option costs, remains materially weaker than the original synthetic
pricing showed — win rate well below 50%, median P&L negative, Sharpe
near zero. The v2 numbers are somewhat LESS severe than v1 (Sharpe
recovers from -0.298 to a marginal +0.273, max drawdown improves from
-85.73% to -46.37%), consistent with the markup itself moving down
modestly (-6.6%) — but the qualitative conclusion is unchanged: the
uncorrected 76.3%-win/+145.5%-median figures do not survive contact with
real market-quoted option costs.

**Still a first-pass-caliber estimate, now on firmer footing:** the
sample doubled and the estimate moved only ~7%, which is a meaningfully
stronger footing than v1's n=37, but still not a large-sample
calibration. The same scope caveat as v1 applies — this corrects the
ENTRY-COST side only (real ASK price vs. modeled cost), not the
EXIT/payout side independently. Further expansion of the real-quote
sample (the remaining ~76 canonical events not yet pulled) would further
narrow the estimate.

**Governance:** same classification as the v1 entry above — this is
FURTHER EVIDENCE on the same finding, not a new one, and does not itself
trigger `STRATEGY_SPEC_v1.1`. The v1 entry's conclusion — do not treat the
original uncorrected figures as the best-available economic estimate — is
reaffirmed, not superseded; use the v2 figures above as the current best
estimate in preference to both the original and the v1 recalibration.

## 2026-07-19 — fixed-window per-event recompute (resolves the look-ahead finding; new canonical baseline)

**What was done:** built `GST_FixedWindow_PerEvent_Canonical.py`, which
replaces both prior measurement methods rather than patching either one.
For each of the 175 candidate `(ticker, spike_week)` pairs ever
considered in this audit trail (the union of the original 147 archived
events and the 28 raw newly-qualifying candidates from the continuous-
window scan, taken directly from `EventReconciliation_Ledger.csv`), the
script issues one **independent** pytrends query per event: a
300-day window ending 7 days after that event's own spike week. This
structurally avoids both prior flaws at once — one query means one
internal peak-anchor (no cross-year-chunk discontinuity), and the
window never extends past the event's own date (no look-ahead
contamination, since the 5-year-all-history peak that caused the prior
finding simply isn't in view for events where that peak lies in a later
year). Same z-score formula as always (12-week rolling, min_periods=8,
`STD_EPSILON_FLOOR=1.0`), same Black-Scholes pricing as both prior
recomputes (entry=anchor+2, exit=anchor+6, calibrated near-earnings IV
markup, `COST_LOADING=1.05`).

**Note on window length:** the original request for this task suggested
a 12-14 week lookback (to mirror the 12-week rolling formula directly).
That does not work — pytrends silently returns **daily**, not weekly,
granularity for single queries under ~269 days (confirmed empirically
earlier in this project; see the reproducibility-audit work). A 12-14
week pull would silently break the weekly rolling formula with no error
raised. Used the same 300-day lookback the live engine itself already
uses (`PULL_LOOKBACK_DAYS=300`), anchored per-event instead of at
"today" — the same approach already validated look-ahead-safe on the
MSFT 15-event recompute and the 10-event reproducibility audit.

**Result: 153 of 175 candidates clear z≥5 under this method; 152 priced
successfully** (1 — `LDOS 2021-02-21` — qualifies but has no daily
excess-return history early enough to price, same as under the
continuous method). Full per-event detail, including every candidate
that did *not* qualify and why:
`Live Signal Engine/FixedWindow_PerEvent_Canonical.csv`.

| | n | Win rate | Median P&L | Sharpe | Max DD |
|---|---|---|---|---|---|
| GST-Legacy-v1 (original, chunked) | 147 | 76.2% | +130.0% | 2.33 | -3.3% |
| Quarantined continuous-window reconstruction | 148 | 76.4% | +145.5% | 2.22 | -2.6% |
| **Fixed-window per-event canonical (this recompute)** | **152** | **76.3%** | **+145.5%** | **2.222** | **-3.6%** |

**Resolves the prior look-ahead finding.** By construction, none of
these 152 events can suffer the contamination flagged in the entry
above — no query in this recompute ever reaches past its own event's
date, so there is no future peak for any window to be rescaled against.

**Notable: GME's three previously-excluded events now resolve cleanly.**
Both GME events dropped for numerical corruption
(`gme_corrupted_z_gt_1e6`) and the one dropped for a low floored z
(`gme_floor_confirmed_low_z_2.75`, GME 2023-03-19) all clear z≥5 under
the fixed-window method (z=8.54, 5.77, 5.58) and price to sane,
non-corrupted values (+386.89%, +454.94%, +10.40%). This is consistent
with — not a contradiction of — the std-floor finding: GME's std
collapse was a full-history artifact (189/262 weeks affected by one
dominant all-time peak); a 300-day window ending at each event never
sees that distant peak, so the collapse doesn't occur. GME now
contributes 3 legitimate events to this canonical set, not the 0 found
under the corrected continuous method.

**Category cross-check against the prior ledger** (for context, not as
a rule — this recompute's own z≥5 gate is what determines membership):
`retained_confirmed` 117/123 still qualify, `dropped_original_only`
13/22 now qualify (most of what the continuous method dropped comes
back under the cleaner per-event method), `newly_qualifying_confirmed`
19/25 still qualify, plus the 3 previously-excluded GME events above.

**Governance / supersession:** this is the same class of finding as
every entry above — a data-measurement/methodology correction, not a
strategy rule change (z≥5 threshold, 12-week/min_periods=8 formula,
entry/exit timing, and pricing model are all unchanged). No
`STRATEGY_SPEC_v1.1` track triggered. **This fixed-window per-event
result (n=152) is now the canonical baseline for the STRONG_EARNINGS
signal's historical population, superseding both:**
- **the original 147-event archive ("GST-Legacy-v1"**, per-calendar-year
  chunked method — known cross-year discontinuity risk), and
- **the quarantined 148-event continuous-window reconstruction**
  (known, quantified look-ahead contamination, 93/175 events at risk).

Both superseded files remain on disk for audit-trail purposes and are
not deleted; neither should be cited going forward as the current
best estimate of the historical population. `EventReconciliation_Ledger.csv`
and `MembershipGroup_Breakdown.csv` (built on the quarantined 148-event
set) are likewise superseded and should not be used for new analysis —
`FixedWindow_PerEvent_Canonical.csv` is the reference file going
forward.

---

## BACKFILL NOTICE (added 2026-07-20T03:37:00Z)

**The nine entries below were added retroactively, in one batch, on
2026-07-20.** The work they describe happened progressively through the
rest of 2026-07-19's session, after the "IV markup recalibration v2"
entry above — but was never logged at the time. This notice and the
entries below are the correction, prompted by an explicit consistency
audit. Nothing above this notice was altered.

## 2026-07-19 (later still) — volatility-surprise check (real quotes vs. real moves, 76-event sample)

**What was done:** using the 76-event real-quote validation sample
(`QC_Validation_CleanSample_v2_76Events.csv`), computed "volatility
surprise" per event: `|realized stock move| - implied move` (the real
quoted ATM straddle ask cost, as % of spot — the market's own priced-in
expectation), where realized move was reconstructed from local daily
price data (not the option's own exit quote, to avoid entangling
remaining time value). Detail: `Live Signal Engine/VolatilitySurprise_Analysis.csv`.

**Result:** only **42.1%** of events showed a positive surprise (realized
> implied); median surprise **-0.52 percentage points** — slightly
negative, not positive. z-score correlated almost identically with raw
realized-move size (Pearson r=0.443) as with surprise specifically
(r=0.407) — meaning the signal predicts move *magnitude*, not
specifically *mispriced* magnitude. **No evidence the GST signal flags
moves the options market fails to price in.** Independent confirmation,
from a different angle, of the IV-recalibration finding above.

**Governance:** data-measurement finding, no rule changed, no
`STRATEGY_SPEC_v1.1` triggered.

## 2026-07-19 (later still) — directional-bias check (152-event canonical population)

**What was done:** for all 152 canonical events, computed the SIGNED
realized move (entry_date to exit_date) to test whether GST spikes carry
any directional lean, split by z-tier, sector, and ticker. Detail:
`Live Signal Engine/DirectionalBias_Analysis.csv`.

**Result:** **46.1% positive / 53.9% negative overall (n=152), binomial
p=0.372 — not distinguishable from a coin flip.** z≥10 leaned slightly
more negative than 5-9.99 (40.0% vs. 48.6% positive) but neither reached
significance (p=0.233, p=0.847). The two largest sector cuts (Technology
n=66, Consumer Cyclical n=38) both leaned mildly negative; smaller
sectors were pure small-sample noise. **The one striking pattern was
ticker-level, not GST-related**: INTC 0% positive (0/6) vs. TTWO 85.7%
(6/7) — flagged at the time as *possibly* a real per-ticker tendency,
*or* small-sample clustering, explicitly not yet resolved.

**Conclusion: GST spikes carry no aggregate directional information —
the signal is about magnitude, not direction.**

## 2026-07-19 (later still) — pre-earnings attention-pressure test (152-event canonical population)

**What was done:** tested whether a GST spike precedes a sector-relative
"pressure" run-up before earnings (stock return minus sector SPDR ETF
return, same window, entry_date to the trading day before earnings), and
whether that pressure predicts a reversal on the earnings-day move
itself. Fresh yfinance pull for 8 sector ETFs (XLK, XLY, XLC, XLV, XLI,
XLP, XLE, XLF). Detail: `Live Signal Engine/PreEarningsPressure_Analysis.csv`.

**Result: clean null.** Mean/median pressure return -0.10pp / -0.30pp,
46.7% positive (coin-flip). z-score vs. pressure return: essentially
zero correlation (r=-0.015). Reversal test (pressure return vs.
earnings-day move): r=0.101 — weak, and if anything points toward mild
continuation, not reversal, though not distinguishable from noise. No
support for a pre-earnings attention-pressure mechanism.

## 2026-07-19 (later still) — Candidate A: pre-registered z≥10-vs-5≤z<10 real-quote test

**What was done:** an informal first read (`GST_CandidateA_RealQuote_TierTest.py`,
`Live Signal Engine/CandidateA_RealQuote_TierTest.csv` — this one IS
independently computed and confirmed) found z≥10's apparent edge
concentrated in one event (53.1% of profit from a single trade, 178.6%
from the top 20%) on the 76-event sample, not pre-registered for that
specific question. A genuinely clean, pre-registered test followed:
`Live Signal Engine/CandidateA_PreRegistration.md` (locked 2026-07-19,
n=34: all 10 untouched z≥10 events + 24 proportionally-sampled 5≤z<10,
seed=99, drawn from the 46 events untouched by either prior QC pull),
with a binding decision rule (mean return>0 AND top-20%-concentration
<100%) and `QC_CandidateA_PreRegistered_Pull.py` to execute it.

**Status: the pre-registered pull's numerical result was never
independently confirmed in this project's records.** A figure (91.8%
comparison-tier concentration) was referenced in a later correction
request, but no `CandidateA...Results.csv` or verified console output
ever existed to confirm it — this was flagged explicitly at the time and
the number was never supplied. **Separately and more importantly**, the
point-in-time forensic audit below subsequently found that the
retrospective z-scores underlying this entire test are not provably
point-in-time valid — meaning even a fully confirmed result would not
have constituted a valid confirmatory test. **Correct characterization:
Candidate A's pre-registered test was never completed with a confirmed
result, and was independently superseded by the point-in-time gate
failure before one was ever recorded** — not "passed" or "failed."

## 2026-07-19 (later still) — Candidate B: pre-registered pre-earnings-IV-expansion test

**What was done:** `Live Signal Engine/CandidateB_PreRegistration.md`
(locked 2026-07-19, n=59: all 35 available z≥10 events untouched by
Candidate A + 24 proportionally-sampled 5≤z<10, seed=123) tested a
DIFFERENT mechanism than every other test that night — entering at the
GST signal and exiting BEFORE earnings, never holding through the
announcement, betting on pre-earnings IV expansion rather than the
earnings reaction itself. `QC_CandidateB_PreRegistered_Pull.py` executed
the pull (the first pull in this project to use a pre-earnings, rather
than post-earnings, exit timestamp).

**Status: identical to Candidate A above.** The pre-registered pull's
result (`+8.71%` mean return, `236.7%` concentration, cited in a later
message) was never independently confirmed — no results file exists, and
a follow-up request for the exact split came back with unfilled template
placeholders instead of real numbers. **Correct characterization:
Candidate B's pre-registered test was never completed with a confirmed
result, and was independently superseded by the point-in-time gate
failure below before one was ever recorded** — not "failed." (An earlier
correction request asked to reclassify a stated "failed" result as
"unvalidated/inconclusive"; that request was declined at the time as an
improper post-hoc reinterpretation of a binding pre-registered rule. This
entry supersedes that exchange with the more precise finding: the
question of "failed vs. inconclusive" is moot, because a confirmed result
never existed and the test was independently invalidated regardless.)

## 2026-07-19 (later still) — point-in-time forensic audit: EVERY historical GST z-score in this project is retrospectively reconstructed, not provably point-in-time valid

**THE MOST CONSEQUENTIAL FINDING OF THE NIGHT.** Requested as a forensic
audit of Candidate B's data specifically; the finding turned out to be
project-wide. Every historical GST z-score in this project — including
the 152-event canonical baseline
(`FixedWindow_PerEvent_Canonical.csv`), both Candidate A/B pre-
registrations above, the IV recalibration, and the volatility-surprise/
directional-bias/pre-earnings-pressure checks above — was computed by
querying pytrends **today**, for a window ending years in the past. This
is internally reproducible (confirmed by `GST_Reproducibility_Audit.py`
much earlier: 10 events, 10 repeated pulls each, zero variance) — but
reproducibility only proves today's retrospective computation is
self-consistent. **It does not prove that computation matches what a
real observer would have seen on Google Trends in real time, on that
historical date.** Google's own documentation states recent/provisional
Trends data can be revised; this project has never had, and does not
have access to, an independent archived snapshot of what Google Trends
actually displayed on any historical date. **Verdict: this check does
not pass, and — per the standard that an unverifiable claim does not
clear a hard gate — is treated as failed.**

**Consequence:** neither Candidate A nor B's retrospective pre-registered
tests could have constituted valid point-in-time confirmatory tests
regardless of their (unconfirmed) numerical results. More broadly, every
historical figure in this project (the 152-event canonical baseline
included) should be understood as a **validated methodology applied
to reconstructed historical data**, not a **proven point-in-time live
track record** — a materially different, weaker claim than this
project's documentation had stated up to this point.

**Governance:** this does not retroactively invalidate the canonical
baseline's status as the best-available reconstruction, nor does it
trigger `STRATEGY_SPEC_v1.1` (no rule changed). It is a first-class
epistemic caveat on everything reconstructed from historical Google
Trends queries, logged here and elevated into
`STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` directly (not buried),
per the 2026-07-20 backfill to that file.

## 2026-07-19 (later still) — forward-only pivot: multi-ticker forward logger + Candidate B v1 locked protocol deployed

**Response to the point-in-time finding above: instead of trying to fix
retrospective reconstruction, route around it.** Two pieces of new,
genuinely point-in-time-clean infrastructure were built and deployed to
a new GitHub Actions repo (`gst-multiticker-forward-log`, running daily,
19:30 UTC / 3:30pm ET, Mon-Fri):

1. `GST_MultiTicker_Forward_Log.py` — expands the MSFT-only forward
   logger to 29 tickers (the 27 canonical tickers with a qualifying
   event, plus MCHP and EBAY). Every trading day, every ticker: raw GST
   value, retrieval timestamp, **exact query start/end date window**
   (the specific field that makes the point-in-time claim checkable, not
   just asserted), z-score, underlying price, days to next earnings; full
   real option chain for any ticker within 5 days of earnings.
2. `Live Signal Engine/CandidateB_v1_FORWARD_LOCKED.md` (locked
   2026-07-19T23:19:32Z) — a NEW, forward-only version of the pre-
   earnings-IV-expansion hypothesis, explicitly built on the running
   logger's data, with **no historical backtest data used to define or
   tune any rule**. Three concurrent paper-tracked groups (z≥10, 5≤z<10,
   and a matched non-GST-earnings control group per ticker), same
   binding success criteria as Candidate B's retrospective version, an
   adaptive (not fixed) sample-size rule, and the same frozen-spec-style
   governance (no rule changes once forward data starts arriving).
   `GST_CandidateB_v1_ForwardTracker.py` implements the actual mechanics
   (opening, reclassifying, and closing paper positions daily) on top of
   the logger's data — deployed to the same repo, running as a second
   step in the same daily job. Two real bugs were caught and fixed during
   smoke-testing before deployment (a target-exit-date miscalculation,
   and a same-day-duplicate-row edge case) — neither ever reached a real
   run.

**This explicitly supersedes both retrospective Candidate B documents**
(`CandidateB_PreRegistration.md` and the informal first read) as the only
currently-live test of this mechanism. No forward data has been collected
against it yet as of this entry.

**Governance:** infrastructure deployment + a new, clean forward-test
protocol — does not modify any existing rule, does not trigger
`STRATEGY_SPEC_v1.1` on its own (`CandidateB_v1_FORWARD_LOCKED.md` has
its own independent governance clause for its own future changes).

## 2026-07-19 (later still) — short-vol defensive-filter test: SELLING the straddle reverses under a GST filter, with real-price confirmation partial and pending

**What was done:** tested whether GST can serve as a defensive filter for
a SHORT-ATM-straddle strategy (opposite side of every long simulation in
this project) — does avoiding high-GST earnings dates improve risk
profile, even if mean return doesn't change much. Baseline redefined
(per explicit decision) as `MatchedControlGroup_CanonicalRecompute.csv`'s
133 usable matched pairs: 133 signal (z≥5) events + 133 matched non-
signal control events = 266 "sell every earnings date" baseline. Compared
against excluding all z≥5 (133 control-only) and excluding only z≥10 (226
events). Detail: `Live Signal Engine/ShortVol_DefensiveFilter_Test.csv`.

**Result — avoiding high-GST events substantially improves the short-
vol strategy's risk profile, and mean return too:**

| | Baseline (n=266) | Excl. z≥5 (n=133) | Excl. z≥10 only (n=226) |
|---|---|---|---|
| Mean $ return / $10k | $3,563 | $7,404 | $4,511 |
| Sharpe | 2.223 | 2.180 | 2.289 |
| Max drawdown | -11.1% | -1.1% | -5.4% |
| Expected shortfall (worst 10%) | -$11,325 | +$1,169 | -$9,264 |
| Worst single trade | -$26,133 (-261%) | -$4,143 (-41%) | -$26,133 (-261%) |

**Two disclosed limitations, not yet resolved:**
1. 80 of 266 events' short-side P&L is approximated as `-long_pnl_pct`
   (real quote data existed for the long side only) — this UNDERSTATES
   true short-side cost, since a real short trades the opposite legs
   (sells at entry bid, buys back at exit ask) from what was captured.
   All 133 control events are modeled-only (recalibrated markup=3.4098,
   not the original uncorrected 1.2398) — no real quote has ever been
   pulled for a non-signal control date before this test.
2. **A follow-up real-quote pull to fix limitation 1 was built and handed
   off** (`QC_ShortVol_ControlSample_Pull.py`, n=39 stratified control
   events, seed=256, pricing the short side directly and correctly —
   entry bid received, exit ask paid, not a negation) **but results have
   not been returned or incorporated as of this entry.** The table above
   should be treated as provisional pending that data.

**Governance:** a new strategy-design finding (short, not long, side),
not a rule change to the existing long-side STRATEGY_SPEC — does not
trigger `STRATEGY_SPEC_v1.1`. Flagged in
`STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` as a distinct,
partially-open thread, not folded into the long-side "rejected" verdict.

## 2026-07-19 (later still) — ticker-specific earnings-reaction persistence: null result on proper power

**What was done:** the directional-bias entry above flagged a striking
ticker-level pattern (INTC 0/6 positive, TTWO 6/7) on a small, GST-
flagged-only subsample. Tested properly: full 2021-2025 earnings history
(20 quarters each, independent of GST entirely) for INTC, TTWO, SBUX
(named explicitly) plus NKE, QCOM, ADBE (every other ticker from the
small-sample check with a lean ≥20 points from 50%, a disclosed
consistent threshold). Detail:
`Live Signal Engine/TickerEarningsPersistence_Test.csv` /
`..._Summary.csv`.

**Result: every one of the six small-sample "leans" reverses or
collapses to neutral.** INTC: 0% (0/6) small-sample -> **60% (12/20)**
full-sample (opposite direction). TTWO: 85.7% (6/7) -> **50.0% (10/20)**
(exactly neutral). None of the six tickers reach significance (binomial
p between 0.26 and 1.0); only INTC's direction is stable across both
halves of the period, and even that is not significant on its own.
**Confirms the small-sample-noise interpretation flagged as a possibility
in the directional-bias entry above — no evidence of real, tradeable
ticker-specific earnings-reaction persistence in this data.**

## 2026-07-25 — Hypothesis #5 (volatility mispricing) out-of-sample test: DEAD, did not replicate

**What was done:** the original volatility-surprise finding (z-score vs.
`volatility_surprise_pct = realized_move_pct - implied_move_pct`, Pearson
r=0.407, n=76, see the "volatility-surprise check" entry above) was
pre-registered for out-of-sample replication
(`Live Signal Engine/H5_OutOfSample_PreRegistration.md`, locked before any
fresh data was touched) against a disjoint sample drawn from the 152-event
canonical population, hard-excluding the original 76 events by their own
`(ticker, spike_week)` keys. The original n=45 draw returned only 29
clean-and-priced events after the unmodified 25%-of-spot corruption
filter; a supplemental draw of the entire remaining eligible pool (n=31,
no seed applicable — the full remainder, not a subsample) added 20 more,
for a combined **n=49**, clearing the pre-registration's n≥40 target.
`implied_move_pct` came from real QuantConnect/AlgoSeek quotes (entry-only
ATM straddle ask cost); `realized_move_pct` was computed from the same
local daily excess-return data and the same helper functions
(`load_daily_excess`/`nearest_trading_day_on_or_before`/`cumulative_return`)
as the original test — confirmed identical, not just similarly named,
before the correlation was computed.

**Result: Hypothesis #5 is dead. Out-of-sample test: n=49, r=0.1065,
p=0.4664 — not statistically distinguishable from zero.** Same fate as
Attention Spread's reversal: a promising-looking original-sample
correlation (r=0.407, n=76) did not replicate on fresh data.

**Governance note on the decision rule:** the pre-registered binding rule
(PASS: r≥0.25 & p<0.05 same-signed; WEAK: r in [0.10,0.25) & p<0.05;
FAIL: r<0.10 or wrong-signed) did not cleanly cover this specific result
as originally worded — r=0.1065 narrowly missed the FAIL threshold
(r<0.10) while p=0.4664 badly missed WEAK's significance requirement,
leaving it technically unclassified. Resolved via a dated, appended
amendment to the pre-registration (not a silent edit): FAIL is clarified
to mean any result that clears neither the PASS nor WEAK bar, in addition
to the originally-stated cases. This amendment was logged after seeing
the n=49 result but moves the bar stricter, not looser — it classifies
this specific marginal result as FAIL rather than leaving it unclassified,
so it cannot be read as rescuing the hypothesis.

**Limitation, carried over from the pre-registration's own appended
note:** the 49-event sample has zero representation from NFLX (0/16
attempted), NVDA (0/6), COHR (0/2), and DELL (0/1) — all excluded by the
unmodified corruption filter (implausible pricing for the first three
tickers' pattern, no listed option chain for COHR). This DEAD conclusion
should not be read as generalizing to those four tickers specifically;
it is a about the pooled cross-sectional relationship among the other 23
tickers in this sample.

**Governance:** per the pre-registration's own consequence for FAIL, no
new monetization hypothesis is spawned from this result, and no
retroactive explanation for the null is used to save the hypothesis —
any observation that might explain *why* it failed is a note for a
future, separately-designed test, not a reclassification of this one.

## 2026-07-25 (later) — CORRECTION: hypothesis #11b ("Attention Spread out-of-sample reversal") was never substantiated

**CORRECTION** — hypothesis #11b ("Attention Spread out-of-sample
reversal") as described in the 2026-07-25 master handoff document was
never actually substantiated. No raw results file or executed pull
exists for this claim as of 2026-07-25. The claim of a "clean rejection"
/ "reversal" should be treated as unverified, not fact, until real
out-of-sample data is pulled and analyzed under a locked
pre-registration.

**What actually exists, confirmed directly against the filesystem and
git history, not assumed:** `Live Signal Engine/AttentionSpread_OOS_LockedSample.csv`
(n=45, seed=314) and `QC_AttentionSpread_OOS_Pull.py` were built and
committed (`a2587c6`) as preparation for an out-of-sample confirmatory
test. Neither the pull nor any correlation/tercile analysis on it has
ever been executed — no `AttentionSpread_OOS_RawResults.csv`, no pasted
`results_df` output, no console log for this specific pull exists
anywhere in this project. This same gap was already noted in
`STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` section 9 (added
2026-07-25, same day, earlier), which states the confirmatory pull "was
built and locked but never executed" — this CHANGELOG entry makes the
same correction explicit here, in this project's append-only historical
log, not only in the current-status file.

**Separately, and also corrected here:** no dedicated pre-registration
document exists for Attention Spread's out-of-sample test — unlike
Hypothesis #5, which had its tercile-independent binding rule
(`H5_OutOfSample_PreRegistration.md`) locked before any fresh data was
touched, the Attention Spread OOS sample and pull script were built
without an equivalent locked-rule document specifying, in advance, the
tercile cutpoints to apply and the pass/fail criteria. This gap is being
closed separately (see this file's next relevant entry, once written) —
it is a second, independent finding from the same handoff-doc
verification pass, not part of hypothesis #11b's original claim.

## 2026-07-26 — Attention Spread out-of-sample test: genuinely executed and resolved. Hypothesis #11b confirmed FAIL

**This entry resolves the gap flagged in the 2026-07-25 "CORRECTION"
entry above** (`f53f2e0`): a pre-registration
(`Live Signal Engine/AttentionSpread_OutOfSample_PreRegistration.md`)
was locked, the already-built pull script (`QC_AttentionSpread_OOS_Pull.py`,
`a2587c6`) was run on QuantConnect, and the result has now been
independently verified against the actual pulled data — not asserted
from a summary.

**Sample**: n=45 drawn, 6 auto-flagged implausible pricing, 8 missing
quote data, **n=31 clean-and-priced**. Raw output saved verbatim:
`Live Signal Engine/QC_AttentionSpread_OOS_RawResults.csv`. Counts
verified against the file itself before proceeding, not trusted from
the reported summary alone.

**Tercile split, locked cutpoints from the original 76-event sample
(low ≤0.968673, mid ≤1.344624, high above), applied unchanged:**

| Tercile | n | Win rate | Median real_pnl_pct |
|---|---|---|---|
| Low | 10 | 60.0% | +21.48% |
| Mid | 11 | 54.5% | +2.48% |
| High | 10 | 40.0% | -27.43% |

Mann-Whitney (high vs. low): **p=0.7337**.

**Result: DIRECTION REVERSED from the original in-sample finding.** The
original 76-event split had the high tercile outperforming the low
(56.0% win / +7.89% median vs. 30.8% / -32.70%, p=0.039). Here, the low
tercile outperforms the high tercile on both win rate and median return
— the opposite pattern.

**Classified FAIL under the locked binding rule
(`AttentionSpread_OutOfSample_PreRegistration.md` §5), applied exactly
as written, with no gap to resolve this time** (unlike Hypothesis #5's
rule, which needed an amendment): FAIL's stated condition — "direction
does not match on both win rate and median return... or p≥0.20" — is
triggered independently by BOTH clauses here (direction is reversed, not
just non-matching; p=0.7337 is far past the 0.20 threshold). No
reinterpretation was needed or applied. No event was excluded as an
outlier; all 31 clean events are included in the stats above exactly as
pulled.

**On the relationship to the prior CORRECTION entry — precision matters
here:** the 2026-07-25 correction stated that hypothesis #11b's claimed
"reversal" was unverified, not that it was false. **It is now
independently confirmed true, by an actual executed test under a locked
pre-registration — which is a different thing from having been true (or
verifiable) at the time the original, unsubstantiated claim was made.**
The original claim was correct by coincidence, not by evidence; this
entry is the evidence. Both the correction and this entry stand — the
correction was accurate about the state of proof as of 2026-07-25
morning, this entry is accurate about the state of proof as of
2026-07-26.

**Governance:** per this project's established practice for a confirmed
FAIL, no new monetization hypothesis is spawned from this result. This
now closes hypothesis #11b's status alongside Hypothesis #5's (§ this
file, 2026-07-25 entry) — both a promising in-sample correlation and a
promising in-sample tercile split failed to replicate out-of-sample in
this project, on largely overlapping (27 of 45 events) but independently
pre-registered samples.

## 2026-07-25 — C5 (post-earnings continuation/reversal): near-miss, does not clear the bar [BACKFILLED 2026-07-26 — every other named hypothesis result in this project had a CHANGELOG entry except this one, until now]

**Dated to the day this test was actually run and committed**
(`f27e439`, 2026-07-25 03:00:06), not to today — this entry is a
retroactive backfill of a real gap, not a new result. Written
2026-07-26, one day after the fact, because no CHANGELOG entry for this
result existed anywhere despite the test being fully run, its
pre-registration locked, and its status already documented in
`STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` §8 — this project's
append-only historical log had simply never recorded it.

**What was done:** tested whether continuous GST z-score predicts
post-earnings continuation/reversal (the C5 metric: sign(gap) ×
sector-adjusted stock return from 9:45am ET Day 0 to Day 5 close),
pre-registered in `Live Signal Engine/C5_PostEarnings_PreRegistration.md`
before any 9:45am-anchored price was pulled. Sample: n=235 (151
canonical signal events + 84 unique matched non-GST controls, each with
its own continuous z-score rather than an assumed z=0 for controls),
pulled via QuantConnect/AlgoSeek minute-resolution equity data (the only
source this project has found that reaches this population's full
2021-2025 date range at intraday resolution — yfinance cannot).
Controls: gap magnitude, ticker, BMO/AMC timing, VIX, sector return,
calendar year; ticker-clustered SEs and a 10,000-replicate ticker-cluster
block bootstrap.

**Result: the project's strongest near-miss.** Day 5 (the sole primary
horizon): β=+0.00095, clustered SE=0.00049, **p=0.0512** — a hair over
the 0.05 line — clustered 95% CI [-0.00000, +0.00190], bootstrap 95% CI
[-0.00002, +0.00204]. **Sign stayed positive across all 32 leave-one-
ticker-out/leave-one-year-out refits** (range [+0.00048, +0.00125]) — not
an artifact of any single ticker or year, just short of the pre-
registered significance bar. Under the binding decision rule (requiring
significance under both the clustered SE and the bootstrap CI), this
does **not** clear the bar — reported exactly as a near-miss, not rounded
into a pass or a clean fail either direction.

**Status: unresolved, not tradeable, not dead.** Unlike Hypothesis #5 and
Attention Spread's OOS test (both classified FAIL above), C5 was never
classified FAIL — a p=0.0512 near-miss with fully stable sign across
every robustness refit does not meet this project's bar for declaring a
hypothesis dead the way a clean, wrong-signed, or badly-insignificant
result would. It also does not meet the bar for PASS. It sits exactly
where its own numbers put it: unresolved.

**Follow-up, same day as this backfill (2026-07-26):** the four
robustness-horizon coefficients (same-day, Day 2, Day 5, Day 20) that
were always part of this test's design were reformatted as an explicit
decay curve — not a new test, no new sample, no new significance
threshold — appended to
`Live Signal Engine/C5_PostEarnings_PreRegistration.md` as a dated
addendum. Shape: builds from same-day (+0.000222) through Day 2
(+0.000282) to the Day 5 peak above, then flips sign by Day 20
(-0.000208, itself not significant, p=0.7788 — a point-estimate sign
change, not a confirmed reversal). Full detail:
`Live Signal Engine/C5_DecayCurve_Data.csv`.
