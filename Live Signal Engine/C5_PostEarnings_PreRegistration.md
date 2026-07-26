# Post-Earnings Continuation/Reversal (C5) Pre-Registration

**Timestamp: 2026-07-23 (session continuation). Written BEFORE any C5 value
for any event has been computed.** No 9:45am-anchored price, no gap value,
and no regression coefficient exists anywhere at the time this file is
written. This document, `GST_C5_PostEarnings_BuildPopulation.py` (which
resolves the population and its covariates, but never touches a
9:45am-anchored price), and `QC_C5_PostEarnings_Pull.py` (which will pull
the actual 9:45am/Day2/Day5/Day20 prices) are written in that order,
matching this project's established pre-registration discipline
(`CandidateA_PreRegistration.md`, `CandidateB_PreRegistration.md`,
`CandidateB_v1_FORWARD_LOCKED.md`).

**No prior "locked" spec existed for this test.** A request referenced a
file, `GST_Current_State.md`, containing a locked C5 protocol — that file
does not exist anywhere in this project or its two linked GitHub repos
(confirmed by exhaustive search before writing a single line of this
document). This is a new pre-registration, designed from the methodology
described in that request, not a rediscovery of a pre-existing lock.

---

## 1. Mechanism under test

Every prior real-money-adjacent test in this project either (a) held a
straddle through the earnings announcement itself (the original
STRONG_EARNINGS backtest and all its recalibrations), or (b) tested
pre-earnings IV expansion / pre-earnings sector-relative drift BEFORE the
announcement (Candidate B, `GST_PreEarningsPressure_Analysis.py`,
`GST_PreEarningsPressure_Cointegration_Test.py` — the last of which found
the cointegration precondition itself only holds for 6.6% of the
population). **This test is different again: it asks whether GST attention
intensity (continuous z-score) predicts how the market digests the
earnings surprise AFTER it's already known** — does a bigger GST spike
predict a stock CONTINUING to drift in the direction of its earnings gap
over the following days (post-earnings-announcement-drift-style
continuation), or REVERSING/giving back part of the gap (overreaction
correction)? Both directions are live hypotheses; this test does not
presuppose which.

## 2. Population — 152 GST signal events + 152 matched non-GST controls

**Reuses the existing, already-locked matching, not a new ad hoc scheme.**
The 152 matched signal/control pairs in
`Live Signal Engine/MatchedControlGroup_CanonicalRecompute.csv` are the
population backbone: same-ticker-different-quarter match first (no z≥5
spike within ±10 trading days, same BMO/AMC, trailing-vol band 0.5x–2x,
nearest-vol wins), falling back to cross-ticker/same-sector/market-cap-band
when no same-ticker match exists — the exact methodology documented in
`GST_MatchedControlGroup_CanonicalRecompute.py`'s own header. This is the
single source of truth for "which non-GST earnings date matches which GST
event" in this project; this test does not re-derive or second-guess it.

**304 total role-rows (152 signal + 152 control), each independently
resolved to:**
- its own real earnings announcement date and BMO/AMC timing (nearest real
  earnings date within ±10 calendar days of the matched anchor/control
  date — the anchor/control_date fields are WEEK-level, not necessarily
  the exact earnings date the gap definition needs)
- its own earnings-day gap (§3)
- its own continuous GST z-score (§4 — **not** an artificial z=0 for
  control rows; see the disclosed reasoning there)

Built by `GST_C5_PostEarnings_BuildPopulation.py`, raw output
`Live Signal Engine/C5_PostEarnings_Population.csv` (304 rows, before the
dedup step below). 283 of 304 resolved a real earnings date + gap +
z-score; the remaining 21 failed with "no daily bar on the resolved
earnings date" (isolated per-event gaps, not a systemic pattern — logged
in that file's `note` column, nothing silently dropped).

**Post-hoc finding, disclosed before any C5 value is computed: the
matching in `MatchedControlGroup_CanonicalRecompute.csv` reuses individual
control events across multiple signal events.** Of 132 usable control
rows, only **84 are unique** `(ticker, control_date)` pairs — e.g.
SBUX 2025-01-28 is matched as "the control" for 6 different signal events.
Treating each reuse as an independent row would pseudo-replicate one real
observation up to 6x in the regression — a distinct problem from what
ticker-clustered SEs fix (clustering groups by ticker, not by unique
event; six literal copies of the same SBUX earnings date would still
inflate that one data point's weight on the point estimate itself, not
just understate its SE). **Fix, applied before locking: control rows are
deduplicated to one row per unique `(ticker, control_date)` before this
sample is locked** — signal rows need no such dedup (0 duplicates found,
checked directly). This was not anticipated when this document's §2 was
first drafted; it is disclosed here as a same-session correction, the
same way this project's CHANGELOG discloses findings made after an
initial pass, not silently folded in.

**Separately notable, not a bug: 20 of 132 usable control rows have a
computed z-score ≥ 5** (up to 14.6 for SBUX 2025-01-28), despite being
matched as "non-GST" events. This is a known, already-documented property
of the matching's exclusion pool
(`GST_MatchedControlGroup_CanonicalRecompute.py`'s own header: the
"clean"-date exclusion filter uses the archived z≥4 list, never
re-verified against the current canonical fixed-window method — "a
conservative exclusion filter, not the population under study"). Because
this test pools signal and control rows on their REAL continuous
z-score (§5) rather than an assumed binary label, these rows are not a
contamination risk here — they simply contribute their true z-score to
the regression, which is exactly the point of using a continuous variable
instead of a signal/control indicator.

**FINAL LOCKED SAMPLE: n=235** (151 signal + 84 unique control — 1 signal
event, BRK-B 2024-02-28, dropped for the same "no daily bar" reason as the
21 above). Every row has a resolved sector ETF (`AllTickers_Sectors.csv` +
the same `SECTOR_ETF_MAP` as `GST_PreEarningsPressure_Analysis.py` — 0
rows lost to missing sector mapping in this population, unlike some of
this project's earlier sector-based tests). Locked, enumerated:
`Live Signal Engine/C5_PostEarnings_LockedSample.csv`, and embedded
identically (generated from that same file, not hand-typed) in
`QC_C5_PostEarnings_Pull.py`'s `EMBEDDED_SAMPLE`.

BMO/AMC split of the final 235: **204 AMC / 31 BMO (87%/13%)** — heavily
skewed toward AMC. Flagged here, not after the fact: the β3 (BMO
indicator) coefficient in §5's regression will have much less power than
β1, and any BMO-specific conclusion from this test should be treated as
low-confidence given how few BMO events exist in this population.

## 3. Gap definition

- **AMC** (after market close): `gap = ln(next_trading_day_open / announcement_day_close)`
- **BMO** (before market open): `gap = ln(announcement_day_open / prior_trading_day_close)`
- BMO/AMC classification: identical convention to every other script in
  this project — yfinance `get_earnings_dates()` timestamp, tz-converted to
  `America/New_York`, `hour < 12 => BMO` else `AMC`.
- `gap_magnitude = |gap|` — used as a control variable (§5), not part of
  C5's own sign convention (§4).
- Computed from daily OHLC (yfinance) — daily resolution is adequate here
  since the gap is defined entirely in terms of official open/close prints,
  no intraday timing required for the gap itself.

## 4. The C5 metric

- **Day 0** = the earnings reaction day: for AMC, the next trading day
  after the announcement; for BMO, the announcement day itself (same
  convention as "next-open"/"announcement-open" in §3 — Day 0 is whichever
  day contains the gap's own open print).
- **Entry point: the 9:45am ET price on Day 0** — 15 minutes after the
  open, filtering opening-auction noise, per spec. **This requires true
  intraday (minute-resolution) equity data.** Checked directly before
  writing this document: yfinance — the only automated data source this
  project has ever used — caps 1-minute bars to the last 30 days, 5-minute
  to 60 days, and even 1-hour bars to the last 730 days (back to
  ~2024-07-24 only). The population spans 2021-03 to 2025-12. **yfinance
  cannot supply a real 9:45am ET price for the large majority of this
  population.** Per explicit instruction, this is NOT approximated with
  the daily open — see §6, this routes through QuantConnect/AlgoSeek
  intraday data instead, the same platform already used in this project
  for real option quotes.
- **"Day N"** = the Nth trading day after Day 0 (Day 0 itself is the
  reaction day; Day 5 is 5 trading days later).
- **C5 = sign(gap) × (stock_return[9:45 ET Day0 → close Day5] −
  sector_ETF_return[SAME clock-time window, SAME ticker's own sector ETF])**
  — sector mapping identical to `SECTOR_ETF_MAP` in
  `GST_PreEarningsPressure_Analysis.py` / the cointegration test (8 SPDR
  sector ETFs, not tuned here either). **The sector ETF's own return over
  this window is ALSO measured from its own 9:45am ET Day-0 price, not a
  daily close** — matching the stock's own timing exactly, otherwise the
  "sector-relative" comparison has a half-day timing mismatch baked in.
  Both legs pulled via the same QC/AlgoSeek intraday call (§6).
- **Primary horizon: Day 5, the sole primary metric.** Same-day (Day 0,
  9:45→close), Day 2, and Day 20 are computed and reported as secondary
  diagnostics only — they do NOT feed the binding decision rule (§7).
- **Sign convention, spelled out:** for a positive gap (stock jumped up),
  C5 > 0 means the stock's sector-relative outperformance CONTINUED past
  9:45 through Day 5 (drift/continuation); C5 < 0 means it gave back
  sector-relative outperformance (reversal). Symmetric for a negative gap
  by construction of the `sign(gap)` multiplication — C5 > 0 always means
  "continuation in the direction of the initial reaction," regardless of
  which direction that was.

## 5. Regression specification

```
C5_i = β0 + β1·z_i + β2·|gap_i| + β3·BMO_i + β4·mkt_vol_i + β5·sector_ret_i
       + year_FE + ε_i
```
ticker-clustered standard errors (primary parametric inference).

- **z_i: the continuous GST z-score, pooled across BOTH signal and control
  rows** — this is the central, disclosed design choice this section
  exists to justify. "Compare continuous GST z-score against C5" is read
  literally: z is a continuous regressor across the full 304-row pooled
  sample, not a binary signal-vs-control split with an assumed z=0 for
  every control. Control rows get their own real fixed-window z-score,
  computed via the exact same per-event, point-in-time-clean methodology
  as every signal event's z-score (`GST_FixedWindow_PerEvent_Canonical.py`'s
  `fetch_event_window`/`compute_zscore_at_anchor`, reused byte-for-byte —
  see `GST_C5_PostEarnings_BuildPopulation.py`). Most control z-scores will
  land below 5 (that's what "non-GST earnings event" means by
  construction of the matching in §2), but the actual computed value is
  used, not an assumed floor — some may be negative, some may land
  surprisingly close to 5 without crossing it, and that real variation is
  exactly what makes β1 a genuine continuous-z coefficient rather than a
  relabeled two-group mean-difference test.
- **|gap_i|**: gap magnitude — controls for the mechanical fact that
  bigger surprises likely have more room to continue or revert regardless
  of attention.
- **BMO_i**: binary indicator (1 = BMO, 0 = AMC) — controls for the known
  structural difference in how BMO vs. AMC reactions unfold (BMO gaps face
  a full trading day of price discovery starting at the open; AMC gaps
  face an overnight gap then a full next day).
- **mkt_vol_i**: CBOE VIX close on Day 0 (yfinance `^VIX`) — broad-market
  volatility regime at the time of the reaction, distinct from this
  specific stock's or sector's own move. Documented fallback if a VIX
  close is unavailable for a given date: 20-trading-day trailing realized
  volatility of SPY ending the day before Day 0 (same
  `VOL_LOOKBACK_TRADING_DAYS`-style convention used elsewhere in this
  project, just applied to SPY instead of the individual ticker).
- **sector_ret_i**: the sector ETF's own raw return over the SAME
  evaluation window used inside C5. Not redundant with C5's own
  sector-adjustment: C5 nets out sector return via a naive 1:1 subtraction
  (the same simplification the cointegration test showed is frequently
  wrong for the true stock/sector relationship — see
  `PreEarningsPressure_Cointegration_Test.csv`), so residual sector
  exposure beyond a true 1:1 beta can still leak into C5. Controlling for
  raw `sector_ret_i` directly in this regression absorbs that residual
  linear exposure rather than assuming the 1:1 subtraction fully removed
  it.
- **year_FE**: calendar-year dummy variables (event year, 2021–2025) —
  absorbs any year-level regime shift (rate environment, realized-vol
  regime, etc.) common to all events that year.
- **ticker-clustered SEs**: primary parametric standard error on β1,
  clustering by the ROW's OWN ticker (the company whose price is being
  measured — for a control row this is `control_ticker`, not the signal
  event's own ticker), since a single company's multiple earnings cycles
  are not independent draws.

## 6. Data-source disclosure

| Component | Source | Resolution |
|---|---|---|
| Matched signal/control pairs, BMO/AMC classification, real earnings dates | yfinance (existing infra) | daily |
| Gap (§3) | yfinance daily OHLC (existing infra) | daily |
| Control z-scores (§5) | pytrends, same per-event methodology as every signal z-score (existing infra) | weekly |
| VIX / SPY realized-vol control | yfinance (existing infra) | daily |
| **9:45am ET stock price, sector-ETF price, and Day0/2/5/20 closes for C5 itself** | **QuantConnect Research + AlgoSeek minute-resolution equity data** | **minute** |

The last row is the one genuinely new data dependency this test
introduces. Per explicit decision (this project has used QuantConnect for
real option quotes throughout, e.g. every `QC_*.py` script), this is NOT
approximated with a same-project data source. `QC_C5_PostEarnings_Pull.py`
is written to the same execution pattern as every prior QC pull in this
project: pasted into an empty QuantConnect Research notebook cell and run
there — this environment cannot execute QuantConnect Research cells
directly. Results are pasted back and analyzed locally, same as every
prior real-quote pull tonight.

## 7. Uncertainty and stability checks

- **Primary uncertainty statement: block bootstrap, resampling by
  ticker-cluster** (not i.i.d. row resampling — preserves each ticker's own
  within-ticker time-ordering and avoids treating a company's several
  earnings cycles as independent draws). `N_BOOTSTRAP=10000`,
  `RANDOM_SEED=42` — same convention already established in
  `GST_MatchedControlGroup_CanonicalRecompute.py`. Reports the 95%
  percentile CI for β1.
- **Cross-check: ticker-clustered (Huber-White) SE** from the parametric
  regression itself (§5) — reported alongside the bootstrap CI, not
  instead of it.
- **Leave-one-ticker-out (LOTO):** refit the full regression once per
  unique underlying ticker (27 refits), each time excluding every row
  (signal OR control) whose OWN ticker equals the held-out ticker. Reports
  the full distribution (min/max/range) of β1 across all 27 refits.
- **Leave-one-year-out (LOYO):** refit once per calendar year present in
  the population (2021–2025, 5 refits), excluding all rows from that
  year. Same reporting.
- **Stability verdict:** whether β1's SIGN and statistical significance
  survive every single LOTO/LOYO refit — not just the range of point
  estimates. A finding that flips sign or loses significance when any one
  ticker or year is dropped is not stable, regardless of the full-sample
  point estimate's face value.

## 8. Decision rule (binding, stated in advance)

**GST z-score shows a real, robust relationship with post-earnings
continuation/reversal if and only if:**

1. β1 (the coefficient on z in the fully-controlled regression, §5) is
   statistically distinguishable from zero at the 95% level under **both**
   the ticker-clustered parametric SE **and** the block-bootstrap CI, AND
2. The **sign** of β1 does not flip in **any** of the 27 LOTO or 5 LOYO
   refits (32 total) — same-sign stability across every single-drop
   robustness check.

If either condition fails, this test does not show a real, robust
relationship between GST attention and post-earnings continuation/reversal
under the C5 metric, regardless of the full-sample point estimate's
face-value magnitude or sign. No new metric, control, or threshold will be
introduced after results are observed. Same-day / Day 2 / Day 20 secondary
diagnostics (§4) are reported for context but do not affect this rule.

## 9. Execution plan (three separate, ordered artifacts)

1. **DONE.** `GST_C5_PostEarnings_BuildPopulation.py` — resolved the
   population and every covariate except C5 itself (no 9:45am price
   touched). Raw output `Live Signal Engine/C5_PostEarnings_Population.csv`
   (304 rows); locked, deduplicated final sample
   `Live Signal Engine/C5_PostEarnings_LockedSample.csv` (n=235, §2).
2. **WRITTEN, NOT YET RUN.** `QC_C5_PostEarnings_Pull.py` — its
   `EMBEDDED_SAMPLE` (235 entries) generated directly from
   `C5_PostEarnings_LockedSample.csv`, not hand-typed. Pulls 9:45am ET /
   Day0 / Day2 / Day5 / Day20 prices for both the stock and its sector ETF
   for all 235 rows, and mechanically computes C5 (and the three secondary
   diagnostics) from the locked formula — no regression/bootstrap/LOTO/LOYO
   logic lives in this script. Must be pasted into a QuantConnect Research
   notebook and run there — this environment cannot execute QuantConnect
   Research cells. **This is the current blocking step.**
3. **NOT STARTED — cannot be written against real data yet.** A local
   analysis script (regression + ticker-block bootstrap + LOTO/LOYO), run
   after `QC_C5_PostEarnings_Pull.py`'s results are pasted back.

---

*End of pre-registration. Population construction (step 1) follows this
file's creation, not the other way around.*

---

## Addendum (2026-07-26) — existing C5 data viewed through a decay lens

**This is NOT a new test.** No new sample was drawn, no new significance
threshold was computed, and this addendum is not confirmatory of
anything beyond what was already established when this test was run.
The actual numeric result (β, p, LOTO/LOYO stability) is documented in
`STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` §8 — this pre-
registration's own §7-8 define the uncertainty methodology and the
decision rule, not the computed result itself; that distinction matters
for anyone tracing where a number came from, so it's stated explicitly
here rather than left to be inferred from matching section numbers
across two different files. This addendum reformats the four robustness-
horizon coefficients already computed under this document's locked model
(§5, run by `GST_C5_PostEarnings_Analysis.py`) as an explicit decay
curve — same-day, Day 2, Day 5 (the sole primary horizon), and Day 20
were always part of this pre-registration's design (§4: "same-day/Day
2/Day 20 secondary diagnostics"); this addendum only changes how they're
displayed, not what was tested.

**Numbers re-derived directly from the locked per-event dataset**
(`Live Signal Engine/C5_PostEarnings_Analysis_Results.csv`, n=235),
re-running the exact same `build_design`/`fit_clustered` functions
already in `GST_C5_PostEarnings_Analysis.py` — not retyped from prior
console output or summary prose. Confirmed to match the original run's
reported numbers exactly.

| Horizon | Days | n | β (z coefficient) | Clustered SE | t | p |
|---|---|---|---|---|---|---|
| Same-day | 0 | 235 | +0.000222 | 0.000292 | +0.763 | 0.4457 |
| Day 2 | 2 | 235 | +0.000282 | 0.000427 | +0.660 | 0.5092 |
| **Day 5 (primary)** | **5** | **235** | **+0.000946** | **0.000485** | **+1.950** | **0.0512** |
| Day 20 | 20 | 235 | -0.000208 | 0.000740 | -0.281 | 0.7788 |

Full detail: `Live Signal Engine/C5_DecayCurve_Data.csv`.

**Shape of the curve, described plainly:** the coefficient builds
monotonically in magnitude from same-day (+0.000222) through Day 2
(+0.000282) to a **peak at Day 5** (+0.000946, both the largest magnitude
and the closest to conventional significance of the four horizons — the
same p=0.0512 near-miss already reported in
`STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` §8). By Day 20 the
point estimate has **flipped sign** to -0.000208. This is consistent with
a real-but-weak, slow-building effect that peaks around Day 5 and does
not persist, rather than noise that happened to concentrate at one
arbitrarily-chosen horizon.

**What this does NOT establish, stated as plainly as the shape above:**
the Day 20 sign flip is not itself statistically distinguishable from
zero (p=0.7788, the least significant of the four points) — it is a
change in the point estimate's sign, not evidence of a real reversal.
None of same-day, Day 2, or Day 20 individually clears any bar; only Day
5 came close, and "close" was already reported as not clearing the
locked decision rule (§8 of this document defines that rule; §8 of
`STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` reports the applied
result). Viewing the four points together as a curve makes the
peak-then-fade shape visually clear, but does not upgrade Day 5's
already-reported non-significant result, and does not newly confirm
same-day, Day 2, or Day 20 as significant. This remains descriptive
context on an already-resolved (does-not-clear-the-bar) result, not a
new finding requiring its own decision rule.
