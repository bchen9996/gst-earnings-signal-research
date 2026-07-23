# Candidate B v1 — Forward-Only Locked Protocol

**Timestamp: 2026-07-19T23:19:32Z. Written BEFORE any forward result under
this protocol exists.** No position has been opened, no z≥10 crossing has
been classified, and no pipeline-validation-phase event has been observed
under these rules at the time this file was written.

---

## 0. Why forward-only, and why this supersedes every prior Candidate B attempt

The historical point-in-time audit (documented in this project's prior
forensic-audit exchange) found that every historical GST z-score in this
project — including both earlier Candidate B pre-registrations
(`CandidateB_PreRegistration.md`) — was computed via a RETROSPECTIVE
pytrends query: querying today for a window ending years in the past.
That is internally reproducible but not provably identical to what a live
observer would have seen in real time, since Google Trends' recent data
can be revised. That gate failed and was not waivable with available
data.

**This document does not attempt to fix that gate — it routes around it.**
Every value used to evaluate this protocol will come from
`gst-multiticker-forward-log`'s daily archive
(`Live Signal Engine/MultiTicker_Forward_Log.csv`), where the z-score is
computed the moment it's observable, going forward, with its exact
retrieval timestamp and query window already recorded. **No historical
backtest data is used to define, tune, or calibrate any rule in this
document** — every threshold below is either already-fixed project
convention (the z≥5/z≥10 tiers, the ATM-strike/nearest-expiry contract
rule, the $10k flat sizing) or a disclosed, non-tuned default (the
control-group entry rule, the fill-penalty assumption) chosen without
reference to how it would have performed on any historical data.

This document **supersedes both prior Candidate B documents**
(`CandidateB_PreRegistration.md` and the informal first read,
`CandidateA_RealQuote_TierTest.csv`'s companion analysis) as the only
currently-live protocol for testing this mechanism. Those remain on disk
as historical record, not as active tests.

## 1. Signal

- z-score: computed **fresh, daily**, by `GST_MultiTicker_Forward_Log.py`
  (running in `gst-multiticker-forward-log` via GitHub Actions), using
  the exact same `fetch_ticker_series` + `compute_latest_zscore`
  functions as the main project's live signal engine — not
  retrospectively reconstructed, not backtested.
- A ticker "signals" on a given day if, on that day: `gst_zscore >= 5`
  AND `within_earnings_window` is True (0-5 days to earnings, matching
  this project's existing `EARNINGS_WINDOW_DAYS=5` convention).
- Tiers: **z≥10** and **5≤z<10**, split at the already-established
  `HIGH_CONFIDENCE_STRONG_EARNINGS` threshold (`CHANGELOG.md`,
  2026-07-19).

## 2. Contract selection

Unchanged from every prior real-quote pull in this project: nearest
listed expiration on/after the earnings date, closest listed strike to
the underlying's price at entry (ATM). Selected once, at entry, and held
fixed through exit (the same contract's exit-day quote is what's pulled
at exit, not a re-selected one).

## 3. Entry and exit rules — all three groups (see §5) use the same exit rule; entry differs by group

- **Signal groups (z≥10, 5≤z<10): entry = real quoted ASK, on the first
  day within the 5-day earnings window that the ticker's z-score first
  crosses the group's threshold** (i.e., the day the signal is actually
  observed in that day's forward-log run — not a day chosen after the
  fact).
- **Control group: entry = real quoted ASK, on the first day the ticker
  enters the 5-day earnings window** (`days_to_earnings` first reads 5),
  **regardless of whether a signal later fires.** This is a disclosed,
  non-tuned choice, not derived from historical performance (see §7 for
  the asymmetry this creates and why it isn't corrected here).
- **All three groups: exit = real quoted BID, at the last trading day
  before the earnings announcement** (the trading day immediately
  preceding the fetched earnings date) — **never held through earnings.**
  This aligns exactly with `gst-multiticker-forward-log`'s existing daily
  3:30pm ET snapshot cadence, so no new pull timing is needed — the
  regularly-scheduled run on that specific day serves as the exit
  snapshot.

## 4. Costs

- Real quoted ask (buy) minus real quoted bid (sell) already captures
  the full bid-ask spread — no separate spread assumption needed.
- **Commission: $0.65/contract × 4 legs** (buy call+put at entry, sell
  call+put at exit) — same assumption used in every real-quote pull this
  project has run.
- **Fill-penalty (new, disclosed): entry cost inflated 2%, exit value
  reduced 2%.** These are PAPER positions — no real order is ever placed,
  so there is no real fill to observe. This penalty is a conservative,
  disclosed stand-in for the slippage a genuine order would likely incur
  between observing a quote and actually filling at it. Not derived from
  any historical fill data (none exists in this project) — a judgment
  call, disclosed as such.

## 5. Position sizing

**Flat $10,000 fixed premium allocation per event**, identical to every
other simulation in this project.

## 6. Three concurrent paper-tracked groups

1. **z≥10** — the primary hypothesis under forward test.
2. **5≤z<10** — comparison tier, same mechanism, weaker signal.
3. **Control** — matched non-GST earnings events for the SAME 29
   tickers: any ticker's earnings cycle where NO z≥5 signal ever fires
   during its 5-day window. Isolates whether Candidate B's timing adds
   value beyond options' ordinary tendency to gain implied volatility
   approaching any earnings date, signaled or not.

Every one of the 29 tickers' earnings cycles is classified into EXACTLY
one of these three groups, determined by the first z≥5 crossing observed
during that cycle's 5-day window (or the absence of one, resolved once
the window closes without a crossing — see §7 for how this is
mechanically implemented on top of the daily archive).

## 7. Disclosed limitation: control-group entry timing is not symmetric with signal-group entry timing

Signal-group positions enter on whichever day within the 5-day window the
signal happens to cross (day 0 through day 5 — often later, since a
crossing can happen anytime). Control-group positions always enter on
day 5 (the window's first day), since that's the only point at which
every ticker's cycle can be given an entry without already knowing
whether it will end up being a signal cycle. **This means control
positions may systematically hold longer, with more exposure to
pre-earnings IV build, than the average signal position.** Correcting
this would require calibrating control entry timing to the historical
distribution of signal entry-lead-times — which this protocol explicitly
does not do, since no historical data is used to define or tune any rule
here. This asymmetry is a known, accepted limitation of v1, not a bug —
worth addressing in a v2 with its own forward-test clock if v1's results
warrant a follow-up.

## 8. Success criteria (stated in advance, binding)

Requires **BOTH**:
1. Mean dollar return (per $10k fixed premium) for the **z≥10** group is
   **positive**, AND
2. The **difference** in mean dollar return, **z≥10 minus 5≤z<10**, is
   **positive**.

Both evaluated **only** at whatever sample size is reached per §9 —
**not event-by-event, and not restated after seeing early results.**
Uncertainty on both quantities is **clustered by ticker** (block
bootstrap resampling whole tickers, not individual events — several
tickers will contribute multiple events, and treating those as
independent would understate true uncertainty) — reported as a 95% CI
alongside the point estimate for context, not itself an additional binary
gate beyond the two conditions above.

## 9. Sample size — determined adaptively, not fixed in advance

**No fixed number (e.g., "30 events") is set now.** Instead:
- The **first phase** of forward observations (an initial run of events —
  exact count not fixed, continues until the pipeline has demonstrably
  worked correctly: positions opened, tracked, and closed without a
  mechanical failure, across all three groups at least once) is
  explicitly a **pipeline-validation phase, testing whether the
  infrastructure works, not whether the strategy works.** Results from
  this phase are not used to evaluate §8's success criteria.
- Once the pipeline-validation phase is complete, the **observed standard
  deviation of dollar returns** from those events (not from any
  historical backtest) will be used to compute the forward sample size
  needed for adequate statistical power to detect a meaningful
  difference under §8 — this calculation will be done and documented
  transparently at that time, not pre-committed to a specific formula
  now, since there is currently zero forward-observed variance to base
  one on.

## 10. Governance (binding, same pattern as `STRATEGY_SPEC_v1.0`)

**No rule in this document changes once forward data starts arriving.**
Any modification — to the signal definition, entry/exit timing, contract
selection, costs, sizing, group definitions, success criteria, or sample-
size methodology — creates a new version (`CandidateB_v1.1_...md` or
similar) and starts a **new forward-test clock** from the date of that
change. Results already recorded under v1 are never retroactively
restated under a later version's rules, and a later version's results are
never retroactively merged into v1's track record. This file is not
edited in place.

---

*End of locked protocol. The mechanical implementation
(`GST_CandidateB_v1_ForwardTracker.py`) that opens, tracks, and closes
positions under these exact rules is deployed alongside this document,
not built from a different, undocumented understanding of it.*
