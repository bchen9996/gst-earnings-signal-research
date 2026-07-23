# Candidate B Pre-Registration — Pre-Earnings IV Expansion Trade

**Timestamp: 2026-07-19T21:41:08Z. Written BEFORE any real quote data for
this specific sample was pulled or observed.** No entry-ask or
pre-earnings-exit-bid price for any event listed in §4 exists anywhere at
the time this file was written. No pre-earnings option quote has ever
been pulled for ANY event in this project before this test — this is a
genuinely new kind of real-world observation, not a re-analysis of
already-known outcomes.

---

## 1. The mechanism under test — different from every prior test tonight

Every real-quote test run tonight (the 37/76-event validations, Candidate
A) held through the earnings announcement, betting on the REALIZED price
move exceeding the straddle's cost. Candidate B tests a different
mechanism entirely: **enter at the GST signal, exit BEFORE the earnings
announcement, and never observe the earnings reaction at all.** This
isolates whether GST-signaled attention/uncertainty causes ATM straddle
prices to inflate (implied-volatility expansion) between signal and
earnings — independent of, and untestable by, anything examined so far.
If this shows an edge, it is a genuinely distinct strategy from anything
tested tonight, not a variant of the same one.

## 2. Sample selection — reasoning disclosed in full

**Excludes only Candidate A's 34 events, not the earlier two QC pulls
(106 events).** This is deliberate, not an oversight: the earlier two
pulls only ever observed POST-earnings exit prices. No event in this
project has ever had a pre-earnings exit price pulled before now, so
reusing a ticker/date from those pulls does not leak any information
about *this* test's outcome — the specific real-world data point this
test measures (a pre-earnings-eve option quote) has never been observed
for any event, touched or not.

**Why not exclude the full union (both pulls + Candidate A) instead:**
checked directly before designing this sample —  doing so leaves a pool
of 12 events with **zero** z≥10 events (every z≥10 event not already
"untouched" for Candidate A was consumed by the earlier two ticker-
stratified pulls). Since oversampling z≥10 is a requirement of this test,
excluding only Candidate A is the only interpretation under which this
test is executable at all.

**Available pool after excluding Candidate A's 34: n=118** (35 z≥10, 83
5≤z<10).

**Comparison-group sizing — a disclosed judgment call:** applying
Candidate A's exact ratio-based formula (comparison size = z≥10 count ×
population ratio 2.378) to 35 available z≥10 events calls for ~83
comparison events — which is effectively the *entire* remaining 5≤z<10
pool, leaving no room for genuine random selection. Instead, this test
matches Candidate A's **absolute** comparison-group size (24), not its
ratio, so that (a) all 35 available z≥10 events are still included in
full (full oversampling of the rare tier, same principle as Candidate
A), and (b) the comparison group is a genuine random subsample (24 of 83
available), consistent with the instruction to use a fresh random seed.
This keeps the total pull (59 events) closer in scale to the prior pulls
tonight rather than ballooning to 118.

**Random seed: `np.random.RandomState(123)`** — applied only to the
5≤z<10 comparison-group draw (24 of 83 available). Not reused from any
prior sample tonight (42-sample: seed 42; 90-sample: seed 7; Candidate A:
seed 99).

**Final sample: n=59** (35 z≥10 — all available — + 24 randomly-selected
5≤z<10).

## 3. Contract, entry, and exit rules

- **Contract:** same as every prior pull — first listed expiration
  on/after the (original, post-earnings) `exit_date`, closest ATM strike
  to the underlying's entry-day close. Not re-selected for this test;
  using the same contract keeps this comparable to Candidate A on
  everything except the exit timing.
- **Entry:** real quoted ASK price (call ask + put ask), at `entry_date`
  (`anchor + 2` trading days) — **identical to every prior test.**
- **Exit — the mechanical difference this test isolates:** real quoted
  BID price (call bid + put bid), at `pre_earnings_exit_date` — **the
  trading day immediately BEFORE** the original post-earnings `exit_date`
  used in every prior test. Concretely: since `exit_date` (anchor+6,
  nearest trading day on/before) is this project's own established
  "next trading day's close after the earnings announcement," the
  trading day immediately preceding it is the last trading day before
  that announcement — i.e., the earnings-eve close. Computed per-event
  from each ticker's own local daily trading calendar (not assumed to be
  a fixed offset from the anchor, since trading-day spacing varies with
  weekends/holidays).
- Same automated corruption filter as prior pulls
  (`real_cost_pct_of_spot > 25%` of spot → flagged/excluded).
- Same fee assumption: `$0.65/contract × 4 legs`.

## 4. Sample (locked, enumerated)

n=59: 35 z≥10 (all available) + 24 randomly-selected 5≤z<10 (seed=123).

Table generated programmatically from the same selection code that
produces `QC_CandidateB_PreRegistered_Pull.py`'s `EMBEDDED_SAMPLE` (not
retyped by hand — an earlier draft of this table had two transcription
errors, caught and corrected before finalizing this file, precisely
*because* it wasn't generated this way originally; this version is).

| Ticker | Spike week | z-score | Tier | Entry date | Pre-earnings exit date |
|---|---|---|---|---|---|
| AAPL | 2023-04-30 | 7.28 | 5≤z<10 | 2023-05-02 | 2023-05-04 |
| ABBV | 2024-10-27 | 6.69 | 5≤z<10 | 2024-10-29 | 2024-10-31 |
| ADBE | 2022-09-11 | 24.11 | z≥10 | 2022-09-13 | 2022-09-15 |
| ADBE | 2023-03-12 | 6.10 | 5≤z<10 | 2023-03-14 | 2023-03-16 |
| ADBE | 2023-12-10 | 15.66 | z≥10 | 2023-12-12 | 2023-12-14 |
| ADBE | 2024-03-10 | 8.79 | 5≤z<10 | 2024-03-12 | 2024-03-14 |
| AMZN | 2025-07-27 | 5.11 | 5≤z<10 | 2025-07-29 | 2025-07-31 |
| BKR | 2025-07-20 | 11.45 | z≥10 | 2025-07-22 | 2025-07-24 |
| COHR | 2024-02-04 | 11.44 | z≥10 | 2024-02-06 | 2024-02-08 |
| CTSH | 2022-10-30 | 7.88 | 5≤z<10 | 2022-11-01 | 2022-11-03 |
| DELL | 2025-11-30 | 5.80 | 5≤z<10 | 2025-12-02 | 2025-12-04 |
| DVN | 2023-02-12 | 10.28 | z≥10 | 2023-02-14 | 2023-02-16 |
| GPN | 2021-08-01 | 13.57 | z≥10 | 2021-08-03 | 2021-08-05 |
| GPN | 2024-08-04 | 5.20 | 5≤z<10 | 2024-08-06 | 2024-08-08 |
| INTC | 2023-01-22 | 8.87 | 5≤z<10 | 2023-01-24 | 2023-01-26 |
| LDOS | 2023-10-29 | 5.55 | 5≤z<10 | 2023-10-31 | 2023-11-02 |
| MSFT | 2022-01-23 | 13.48 | z≥10 | 2022-01-25 | 2022-01-27 |
| MSFT | 2022-10-23 | 13.11 | z≥10 | 2022-10-25 | 2022-10-27 |
| MSFT | 2023-01-22 | 11.78 | z≥10 | 2023-01-24 | 2023-01-26 |
| MSFT | 2023-04-23 | 7.38 | 5≤z<10 | 2023-04-25 | 2023-04-27 |
| MSFT | 2023-10-22 | 8.27 | 5≤z<10 | 2023-10-24 | 2023-10-26 |
| MSFT | 2025-01-26 | 11.45 | z≥10 | 2025-01-28 | 2025-01-30 |
| MSFT | 2025-07-27 | 13.38 | z≥10 | 2025-07-29 | 2025-07-31 |
| NFLX | 2021-07-18 | 10.28 | z≥10 | 2021-07-20 | 2021-07-22 |
| NFLX | 2021-10-17 | 15.27 | z≥10 | 2021-10-19 | 2021-10-21 |
| NFLX | 2022-01-16 | 31.10 | z≥10 | 2022-01-18 | 2022-01-20 |
| NFLX | 2022-04-17 | 13.63 | z≥10 | 2022-04-19 | 2022-04-21 |
| NFLX | 2022-10-16 | 16.46 | z≥10 | 2022-10-18 | 2022-10-20 |
| NFLX | 2023-07-16 | 15.81 | z≥10 | 2023-07-18 | 2023-07-20 |
| NFLX | 2024-07-14 | 13.66 | z≥10 | 2024-07-16 | 2024-07-18 |
| NFLX | 2024-10-13 | 17.08 | z≥10 | 2024-10-15 | 2024-10-17 |
| NFLX | 2025-01-19 | 12.79 | z≥10 | 2025-01-21 | 2025-01-23 |
| NKE | 2021-06-20 | 11.91 | z≥10 | 2021-06-22 | 2021-06-24 |
| NKE | 2022-03-20 | 10.45 | z≥10 | 2022-03-22 | 2022-03-24 |
| NKE | 2023-06-25 | 11.30 | z≥10 | 2023-06-27 | 2023-06-29 |
| NKE | 2024-03-17 | 10.78 | z≥10 | 2024-03-19 | 2024-03-21 |
| NKE | 2024-06-23 | 22.47 | z≥10 | 2024-06-25 | 2024-06-27 |
| NVDA | 2023-05-21 | 17.19 | z≥10 | 2023-05-23 | 2023-05-25 |
| NVDA | 2023-08-20 | 9.44 | 5≤z<10 | 2023-08-22 | 2023-08-24 |
| QCOM | 2021-10-31 | 18.68 | z≥10 | 2021-11-02 | 2021-11-04 |
| QCOM | 2023-04-30 | 10.57 | z≥10 | 2023-05-02 | 2023-05-04 |
| QCOM | 2024-01-28 | 7.07 | 5≤z<10 | 2024-01-30 | 2024-02-01 |
| QCOM | 2025-07-27 | 12.31 | z≥10 | 2025-07-29 | 2025-07-31 |
| SBUX | 2023-04-30 | 12.31 | z≥10 | 2023-05-02 | 2023-05-04 |
| SBUX | 2024-04-28 | 26.77 | z≥10 | 2024-04-30 | 2024-05-02 |
| SBUX | 2025-01-26 | 13.65 | z≥10 | 2025-01-28 | 2025-01-30 |
| SBUX | 2025-04-27 | 5.57 | 5≤z<10 | 2025-04-29 | 2025-05-01 |
| STZ | 2023-01-01 | 5.90 | 5≤z<10 | 2022-12-30 | 2023-01-05 |
| STZ | 2024-04-07 | 10.20 | z≥10 | 2024-04-09 | 2024-04-11 |
| STZ | 2025-01-05 | 11.78 | z≥10 | 2025-01-07 | 2025-01-08 |
| SYK | 2023-01-29 | 7.26 | 5≤z<10 | 2023-01-31 | 2023-02-02 |
| SYK | 2024-01-28 | 8.62 | 5≤z<10 | 2024-01-30 | 2024-02-01 |
| SYK | 2025-07-27 | 5.23 | 5≤z<10 | 2025-07-29 | 2025-07-31 |
| TSLA | 2024-04-21 | 5.60 | 5≤z<10 | 2024-04-23 | 2024-04-25 |
| TTWO | 2021-05-16 | 8.32 | 5≤z<10 | 2021-05-18 | 2021-05-20 |
| TTWO | 2022-11-06 | 8.08 | 5≤z<10 | 2022-11-08 | 2022-11-10 |
| TTWO | 2023-05-14 | 12.57 | z≥10 | 2023-05-16 | 2023-05-18 |
| TTWO | 2024-05-12 | 8.53 | 5≤z<10 | 2024-05-14 | 2024-05-16 |
| UAL | 2021-07-18 | 5.53 | 5≤z<10 | 2021-07-20 | 2021-07-22 |

## 5. Metrics (identical structure to Candidate A)

**Primary metric:** mean dollar return per $10,000 fixed premium, per
tier (not win rate, not median).

**Secondary metrics:** max drawdown across the tier's own chronological
sequence (ordered by `pre_earnings_exit_date`), expected shortfall (worst
10% and worst 20%), worst single trade, % of tier's total net profit from
the top 20% of events (the same built-in concentration/overfitting
check used in Candidate A, included after Candidate A's z≥10 read showed
its apparent edge concentrated in one event).

## 6. Decision rule (stated in advance, binding)

**z≥10 shows real edge on this test if and only if:**
1. Mean dollar return per $10k fixed premium is **positive**, AND
2. % of tier profit from the top 20% of events is **under 100%**.

Same rule structure as Candidate A, applied independently to this
different mechanism. If either condition fails, this test does not show
real edge for z≥10 under the pre-earnings-IV-expansion mechanism,
regardless of the other metrics. No new metric or threshold will be
introduced after results are observed.

---

*End of pre-registration. The real-quote pull for the 59 events follows
this file's creation, not the other way around.*
