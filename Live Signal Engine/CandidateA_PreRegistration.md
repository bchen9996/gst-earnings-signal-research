# Candidate A Pre-Registration — z≥10 vs 5≤z<10, real-quote clean test

**Timestamp: 2026-07-19T20:55:48Z. Written BEFORE any real quote data for
this specific sample was pulled or observed.** No `real_pnl_pct`,
`real_cost_pct_of_spot`, or any other real-quote-derived value for the
events listed in §3 exists anywhere at the time this file was written.
This is a genuine pre-registration, not a post-hoc rationalization of a
result already seen.

---

## 1. Why this test is clean (unlike the two samples run earlier tonight)

The two prior QC real-quote pulls tonight (37/42-event and 76/90-event
samples) were both stratified by *ticker*, not by z-tier, and neither was
designed to test the z≥10 hypothesis specifically — that hypothesis (and
the informal first read on it, `CandidateA_RealQuote_TierTest.py`,
`Live Signal Engine/CandidateA_RealQuote_TierTest.csv`) was only posed
*after* those samples already existed. Reusing them to test a
z-tier hypothesis is not a clean confirmatory test — it's exactly the
kind of "test devised after seeing the data" this file exists to avoid
repeating.

**Untouched-pool identification:** all 152 canonical events, minus the
union of every event that appeared in either prior QC sample (42-event
sample ∪ 90-event sample = 106 distinct events, 26 overlapping between
the two), leaves **46 untouched canonical events** — of which 10 are
z≥10 and 36 are 5≤z<10. This test uses only events from that untouched
46.

## 2. Signal definition

- z-score: `fixed_window_zscore` from `FixedWindow_PerEvent_Canonical.csv`
  (the established canonical population, already fixed before tonight —
  using it to select events is not a new/untested measurement, only the
  real-quote pricing that follows is new).
- Tiers: **z≥10** vs **5≤z<10**. Same split as
  `GST_CandidateA_RealQuote_TierTest.py` and the HIGH_CONFIDENCE_STRONG_EARNINGS
  tiering (`CHANGELOG.md`, 2026-07-19).

## 3. Sample (locked, enumerated — not just a selection rule)

**All 10 untouched z≥10 events included** (rare tier, no sampling).
**24 of the 36 untouched 5≤z<10 events**, randomly selected
(`np.random.RandomState(seed=99)`, a seed not used in any prior sample
tonight) — sized proportionally to the FULL canonical population's own
z≥10:5-9.99 ratio (45:107 ≈ 1:2.378), i.e. `round(10 × 2.378) = 24`, so the
comparison group's relative size mirrors the population's natural tier
balance rather than an arbitrarily chosen number.

**Total n = 34.** Full list (ticker, spike_week, z-score, entry_date,
exit_date — entry/exit already fixed from the canonical file, anchor+2/
anchor+6, nearest trading day rule, unchanged):

| Ticker | Spike week | z-score | Tier |
|---|---|---|---|
| DELL | 2021-08-22 | 10.68 | z≥10 |
| NFLX | 2021-04-18 | 13.97 | z≥10 |
| NKE | 2022-06-26 | 13.44 | z≥10 |
| NKE | 2022-09-25 | 22.53 | z≥10 |
| NKE | 2023-03-19 | 12.22 | z≥10 |
| TTWO | 2023-11-05 | 27.45 | z≥10 |
| NFLX | 2024-01-21 | 26.79 | z≥10 |
| ADBE | 2024-12-08 | 14.67 | z≥10 |
| SBUX | 2025-07-27 | 13.24 | z≥10 |
| ADBE | 2025-09-07 | 16.93 | z≥10 |
| AAPL | 2023-01-29 | 6.61 | 5≤z<10 |
| ADBE | 2022-03-20 | 6.99 | 5≤z<10 |
| AMZN | 2021-07-25 | 5.52 | 5≤z<10 |
| AMZN | 2024-01-28 | 7.24 | 5≤z<10 |
| AMZN | 2025-10-26 | 8.79 | 5≤z<10 |
| COHR | 2024-08-11 | 5.41 | 5≤z<10 |
| CTSH | 2023-07-30 | 5.59 | 5≤z<10 |
| GME | 2023-03-19 | 8.54 | 5≤z<10 |
| GOOGL | 2022-10-23 | 5.18 | 5≤z<10 |
| GOOGL | 2023-10-22 | 7.05 | 5≤z<10 |
| GPN | 2022-10-30 | 5.84 | 5≤z<10 |
| INTC | 2021-10-17 | 5.77 | 5≤z<10 |
| NFLX | 2023-04-16 | 7.51 | 5≤z<10 |
| NFLX | 2025-07-13 | 5.45 | 5≤z<10 |
| NFLX | 2025-10-19 | 8.99 | 5≤z<10 |
| NVDA | 2023-11-19 | 5.50 | 5≤z<10 |
| NVDA | 2024-02-18 | 7.16 | 5≤z<10 |
| QCOM | 2021-07-25 | 5.87 | 5≤z<10 |
| QCOM | 2022-10-30 | 6.57 | 5≤z<10 |
| SBUX | 2021-07-25 | 5.65 | 5≤z<10 |
| STZ | 2023-12-31 | 6.93 | 5≤z<10 |
| SYK | 2025-01-26 | 8.29 | 5≤z<10 |
| TSLA | 2024-01-21 | 7.51 | 5≤z<10 |
| TTWO | 2025-02-02 | 9.42 | 5≤z<10 |

## 4. Contract selection methodology (identical to prior pulls — not re-litigated)

- **Expiration:** first listed expiration on/after `exit_date`.
- **Strike:** closest listed strike to the underlying's entry-day closing
  price (ATM).
- Same automated corruption filter as the second pull
  (`real_cost_pct_of_spot > 25% of spot` → flagged and excluded, not
  silently dropped).

## 5. Entry / exit rule

- **Entry:** real quoted ASK price (call ask + put ask), first tradable
  timestamp at/after `entry_date` (`anchor + 2` trading days — unchanged
  from the canonical backtest's own entry rule).
- **Exit:** real quoted BID price (call bid + put bid), fixed at
  `exit_date` (`anchor + 6` trading days, nearest trading day on/before —
  this project's existing, already-validated exit rule; "fixed time next
  trading day" in the sense that it's a pre-determined date derived from
  the anchor, not a discretionary or outcome-dependent exit).
- Fee assumption: same disclosed `$0.65/contract × 4 legs` as both prior
  pulls.

## 6. Metrics (locked in advance)

**Primary metric — the only one that determines the pass/fail decision
rule in §7:**
- Mean dollar return per $10,000 fixed premium, per tier (**not** win
  rate, **not** median).

**Secondary metrics (reported for context, not part of the decision
rule):**
- Max drawdown across the tier's own chronological event sequence.
- Expected shortfall: mean $ loss in the worst 10% and worst 20% of
  outcomes.
- Worst single trade ($ and %).
- % of tier's total net $ profit contributed by the top 20% of events by
  P&L — an explicit, built-in overfitting/concentration check, included
  specifically because the informal first read
  (`CandidateA_RealQuote_TierTest.csv`) showed the z≥10 tier's apparent
  edge concentrated in one event (53.1% of profit from a single trade,
  178.6% from the top 20%).

## 7. Decision rule (stated in advance, binding)

**z≥10 is considered to show real edge on this test if and only if
BOTH of the following hold:**
1. Mean dollar return per $10k fixed premium is **positive**.
2. % of tier profit from the top 20% of events is **under 100%**
   (i.e., the tier's profit is not entirely — or more than entirely —
   dependent on its best few outlier trades).

If either condition fails, this test does **not** show real edge for
z≥10, regardless of how the other metrics look. No new metric, threshold,
or reinterpretation will be introduced after results are observed — the
report following the real-quote pull will state pass/fail against
exactly these two conditions, first, before any other discussion.

---

*End of pre-registration. The real-quote pull for the 34 events listed
in §3 follows this file's creation, not the other way around.*
