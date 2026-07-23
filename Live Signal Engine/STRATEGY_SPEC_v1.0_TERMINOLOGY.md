# Terminology & Precise Definitions — companion to STRATEGY_SPEC_v1.0

This file is the **canonical reference** for four specific numbers that
have been described imprecisely in informal summaries. It does not modify,
supersede, or reinterpret any rule in `STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md`
— that file remains untouched, exactly as frozen. This is a terminology
clarification, not a strategy change: it does not trigger v1.1.

Unlike the frozen spec, **this file may be amended in place** if further
terminology corrections are identified — precise-language fixes aren't
rule changes and don't need their own version track. Each entry below
notes the source data it was verified against.

---

## 1. The 147/112/35 event/win/loss breakdown

> **SUPERSEDED (2026-07-19):** the 147-event population below is
> historical, not current — the authoritative population is now the
> 152-event `FixedWindow_PerEvent_Canonical.csv`. See
> `STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md`. The precise
> definitions and arithmetic below remain accurate for the 147-event
> population as it existed and are kept for historical/audit reference,
> not deleted.

The canonical STRONG_EARNINGS validated population is **147 signal
events** (z≥5, near_earnings=True, 2021–2025, 51-ticker universe). Of
these:
- **112 are wins** (positive model-priced P&L at exit) — 76.2%.
- **35 are losses** — 23.8%.

**"147 winning trades" is not correct phrasing and should not be used.**
All 147 are signal events; only 112 of them won. Always state win rate
alongside the event count, not the event count alone.

Source: `Earnings-Adjacent Spike vs No-Spike Test/group_a_z4_earnings_adjacent.csv`,
filtered to `zscore>=5 & near_earnings==True`; 112/147 = 76.19% ≈ 76.2%.

## 2. MSFT's precise historical win rate: 73.3% (11/15), not 85%

MSFT has **15 historical STRONG_EARNINGS events** (2021–2025). Of these,
**11 won and 4 lost** — a win rate of **73.3%**, not 85%.

**"Hit rate," defined precisely:** the fraction of events where the
model-priced straddle had positive P&L at exit (`end_of_spike_week_win`)
— i.e. straddle win rate. It does **not** mean how often the GST signal
fires near MSFT's earnings, and it does not mean anything about signal
*detection* frequency versus earnings *proximity* frequency.

An earlier informal "85%" figure appears to have conflated signal-firing
frequency with straddle win rate — those are two different statistics,
and 85% does not match either MSFT's win rate (73.3%) or any other
MSFT-specific cut computed in this project. **That 85% figure should not
be used going forward.** For reference, MSFT's win rate split by z-score
band (both verified subsets of the same 15 events):
- z = 5.00–9.99: 63.6% (7/11)
- z ≥ 10: 100% (4/4 — small sample, treat directionally only)
- All 15 events combined: **73.3% (11/15)**

Source: `Earnings-Adjacent Spike vs No-Spike Test/group_a_z4_earnings_adjacent.csv`,
filtered to `ticker=="MSFT" & zscore>=5 & near_earnings==True`.

## 3. The behavioral mechanism finding: Cohen's d=1.294, p<0.0001

Precise statement (replaces any "essentially zero chance it's random"
phrasing): STRONG_EARNINGS spike weeks show a realized move magnitude of
**mean 7.72%** (n=147) versus **mean 3.72%** for random baseline weeks
(n=1,275) — a difference of **4.0 percentage points**. This holds
independent of the Black-Scholes pricing model entirely (raw realized
move, no options math involved).

- **Effect size: Cohen's d = 1.294** (a large effect by conventional
  benchmarks — d>0.8 is typically called "large").
- **Permutation test p-value: p < 0.0001** (0 of 10,000 permutations
  produced a difference this large or larger under the null of no
  difference between spike and baseline weeks).
- Median comparison, for completeness: spike weeks 6.63% vs. baseline
  3.03%, diff = 3.6 points, same p<0.0001.
- **Gap, disclosed:** no confidence interval is currently computed or
  stored for this Cohen's d or for the mean/median difference. The
  source script reports point estimates and a permutation p-value, not a
  bootstrap CI. If a CI is needed, it has to be computed fresh — it does
  not already exist anywhere in this project's output.

Source: `Live Signal Engine/MechanismStability_Results.csv`, `full_sample`
row (`GST_Task2_MechanismStability.py`).

## 4. The multiverse 81-combination caveat

`GST_Task1_MultiverseAnalysis.py` / `Multiverse_Analysis_Results.csv`
tested 81 combinations of `rolling_window` × `z_threshold` ×
`earnings_window` × `exit_rule`. All 81 combinations show positive
median P&L and win rate >50% — that part of the claim is accurate and
verified.

**The caveat that must accompany this number wherever it's cited:**
these are 81 different *parameter choices* applied to the **same
underlying 2021–2025 GST/price dataset** — this is robustness-to-
parameter-choice evidence, not 81 independent validations. Varying
`rolling_window`, `z_threshold`, `earnings_window`, and `exit_rule` does
not create new data or a new sample; a systematic error in the
underlying data or methodology (a look-ahead bug, a mispriced benchmark,
a survivorship issue) would likely still show up as "profitable" across
all 81 combinations, since they all share the same root data. Do not use
"81/81 profitable" to imply the level of confidence that 81 genuinely
independent out-of-sample tests would provide.

Source: `Live Signal Engine/Multiverse_Analysis_Results.csv` (81 rows).
