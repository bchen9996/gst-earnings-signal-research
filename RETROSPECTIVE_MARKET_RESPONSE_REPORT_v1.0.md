# Retrospective Market-Response Decomposition — Results

`RETROSPECTIVE_DEVELOPMENT_ONLY`. Confirms nothing about HYP-01, changes no locked methodology, uses
no gated prospective outcome. 285 usable earnings events, 28 tickers, 2021-03-24 → 2025-12-19.

## Strategy scorecard

Costs: **10 bps** round trip single-leg, **20 bps** two-leg. Fixed before computing; not tuned.

| Strategy | Trades | Mean gross | Median | Mean **net** | Hit rate | t (net) | Max DD | Trades/yr | Older | Newer | Same-ticker paired | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A.** Opening-range breakout | — | — | — | — | — | — | — | — | — | — | — | **NOT_TESTABLE** |
| **B.** Gap continuation | 152 | 0.573% | 0.640% | **0.473%** | 57.2% | 1.59 | −18.8% | 32.2 | 0.444% | 0.504% | −0.390% (t=−1.01) | **WEAK/UNSTABLE** |
| **C.** Gap reversal | 152 | −0.573% | −0.640% | **−0.673%** | 42.8% | −2.27 | −71.8% | 32.2 | −0.644% | −0.704% | +0.390% (t=1.01) | **FAILS_AFTER_COSTS** |
| **D.** Attention–price divergence | 60 vs 92 | quiet 7.43% vs loud 8.18% abs | — | — | — | −0.76 | — | — | — | — | — | **WEAK/UNSTABLE** |
| **E.** Benchmark-neutral continuation T→T+3 | 152 | 1.054% | 0.725% | **0.854%** | 63.2% | **3.03** | −10.4% | 32.2 | 0.691% | 1.031% | +0.116% (t=0.27) | **SURVIVES_BASIC_DEVELOPMENT_CHECKS** |

### The comparators that decide it

| Benchmark | Trades | Mean net |
|---|---|---|
| No trade | 0 | 0.000% |
| Unfiltered — **all** earnings events, strategy E | 285 | **+0.858%** |
| **Control** (low-attention) events only, strategy E | 133 | **+0.861%** |
| High-GST events, strategy E | 152 | +0.854% |
| Unfiltered all-earnings long-only, day T | 285 | −1.216% |
| High-GST long-only, day T | 152 | −1.173% |

**The GST filter contributes nothing to E.** Low-attention controls score marginally *higher* than
high-attention events, and the matched within-pair difference is +0.116% (t=0.27).

## The six questions, numerically

| # | Question | Answer |
|---|---|---|
| 1 | Does high abnormal attention predict a larger absolute move? | **Yes.** 7.89% vs 6.45%, **+1.44 pp**, t=2.14 |
| 2 | Where does the movement occur? | **Overnight.** Mean abs gap 7.00% vs open→close 2.76% — **71.7%** of the move |
| 3 | Is it already complete overnight? | **Largely yes** — it is in the price before any post-announcement trade is possible |
| 4 | Does the post-open move continue or reverse? | **Neither significantly.** Gap-direction open→close +0.573%, t=1.93; corr(gap, open→close) = **−0.003** |
| 5 | Does it survive benchmark subtraction? | **Yes.** Mean abs 7.89% → 7.62% excess, **96.6% retained** — it is stock-specific, not market beta |
| 6 | Does the attention effect survive robustness? | **The magnitude effect does; the tradable edge does not** (below) |

### Q6 detail — the magnitude effect is real

| Test | Difference | t |
|---|---|---|
| Matched pairs | +1.66 pp | **2.58** |
| Same-ticker pairs only (132) | +1.62 pp | **2.495** |
| Ticker fixed effects (demeaned) | +1.50 pp | **2.57** |
| Older half (69 pairs) | +2.18 pp | — |
| Newer half (64 pairs) | +1.11 pp | — |

High abnormal GST predicts a bigger absolute earnings move **even within the same ticker**. It
weakens in the newer half (2.18 → 1.11 pp) but does not vanish.

## What this means

**Initially, strategy E looked promising: benchmark-neutral continuation returned +0.854% net per
trade over 152 high-GST events, t = 3.03, 63% hit rate, −10.4% max drawdown, and it got *stronger*
in the recent half (+1.031% vs +0.691%). After comparing it against the unfiltered and
low-attention control sets, it became clear the attention filter contributes nothing: all earnings
events return +0.858% and low-attention controls +0.861% on the identical rule, with a matched
within-pair difference of +0.116% (t = 0.27). E is post-earnings drift; GST is not what makes it
work.**

The attention signal that *is* real — a +1.66 pp larger absolute move, surviving same-ticker pairing
at t=2.495 — is a **magnitude** effect, and **71.7% of it lands in the overnight gap**, before any
post-announcement stock trade can be placed. A directional stock strategy cannot capture it: the
correlation between the gap and the subsequent open→close move is **−0.003**, i.e. the gap carries no
information about what happens next.

## Answers to the six required outputs

1. **Strongest apparent result** — Strategy E, +0.854% net/trade, t=3.03, 63.2% hit rate, −10.4% DD.
2. **Hardest robustness test it survives** — fixed costs *and* the newer-period split (it improves:
   +0.691% older → +1.031% newer), plus benchmark neutrality by construction.
3. **Most convincing result that weakened or disappeared** — the GST filter's contribution to E.
   Against the unfiltered and control comparators it is indistinguishable from zero (+0.116%,
   t=0.27). Strategy B is worse: low-attention controls (+0.840%) *beat* high-attention (+0.473%).
4. **Anything economically interesting after costs?** — Post-earnings drift is (E, +0.854% net), but
   it is **not a GST result**. There is **no attention-conditioned stock edge** after costs.
5. **Next single strategy worth prospective testing** — **None stock-based.** The only surviving
   attention effect is magnitude, not direction, and it is realized overnight; capturing it requires
   a volatility/options structure, which is outside this sprint's stock-only scope and would need
   the gated prospective process.
6. **Verdict: NO STRATEGY.** No GST-conditioned stock strategy qualifies for prospective testing.

## Not testable, and why

| Item | Status |
|---|---|
| open → +30 min component | **NOT TESTABLE** — no intraday bars exist in this repository |
| +30 min → close component | **NOT TESTABLE** — same |
| **Strategy A** (opening-range breakout) | **NOT TESTABLE** — requires intraday bars; no substitute invented |
| Sector-ETF hedge leg for E | **Limited** — no SPY open price exists, so the hedge cannot be applied intraday. E is evaluated close(T)→close(T+3), which SPY supports. A broad benchmark is used because no sector-ETF mapping is present in the repository. |

19 of 304 population events dropped: earnings date beyond the 2021-01-04 → 2025-12-31 price coverage.
No event was dropped for any other reason.

## Frozen definitions

Event day T: AMC → next trading day; BMO → the earnings date. High GST = `role=signal` in the C5
matched population (all z ≥ 5.0); controls are its matched same-ticker/nearby non-spike events.
Pre-drift close(T−6)→close(T−1); gap close(T−1)→open(T); open→close on T; post close(T)→close(T+3).
Quiet price for D: |pre-drift| ≤ 2.0%. Benchmark: SPY daily close-to-close. No window, threshold,
holding period or cost was searched over after seeing results.

Inputs: `Live Signal Engine/C5_PostEarnings_Population.csv`,
`Daily OHLC Data (2021-2025 Opening Gap Test)/`, `Daily Excess Return Data*/`.
Regenerate: `python tools/run_retrospective_market_response_decomposition.py`
