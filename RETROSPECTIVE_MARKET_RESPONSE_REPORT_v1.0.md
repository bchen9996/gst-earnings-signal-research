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
| 1 | Does high abnormal attention predict a larger absolute move? | **Descriptively yes** — 7.89% vs 6.45%, **+1.44 pp** (unclustered t=2.14). Under ticker-clustered CR2 the coefficient is **+1.509 pp, p=0.0662**, CI spanning zero — see below |
| 2 | Where does the movement occur? | **Overnight.** The overnight gap accounts for **71.7% of mean |gap| plus mean |open-to-close| among high-GST events** (7.00% vs 2.76%) |
| 3 | Is it already complete overnight? | **Largely yes** — it is in the price before any post-announcement trade is possible |
| 4 | Does the post-open move continue or reverse? | **Neither significantly.** Gap-direction open→close +0.573%, t=1.93; corr(gap, open→close) = **−0.003** |
| 5 | Does it survive benchmark subtraction? | **Yes.** Mean abs 7.89% → 7.62% excess, **96.6% retained** — it is stock-specific, not market beta |
| 6 | Does the attention effect survive robustness? | **Magnitude: weakens to +1.509 pp, p=0.0662 under ticker-clustered CR2 (CI spans zero); tradable edge: zero (+0.013 pp, p=0.98332)** |

### Q6 detail — unclustered pair statistics (superseded by the CR2 table below)

| Test | Difference | t |
|---|---|---|
| Matched pairs | +1.66 pp | **2.58** |
| Same-ticker pairs only (132) | +1.62 pp | **2.495** |
| Ticker fixed effects (demeaned) | +1.50 pp | **2.57** |
| Older half (69 pairs) | +2.18 pp | — |
| Newer half (64 pairs) | +1.11 pp | — |

These are unclustered pair statistics, retained for continuity of the descriptive record; the
ticker-clustered CR2 estimates in the next section supersede them for inference. The point estimate
weakens in the newer half (+2.18 → +1.11 pp) but does not change sign.

## Clustered inference (corrects the independence assumption)

Events repeat within tickers and matched controls are reused, so ordinary t-statistics that treat
observations as independent overstate precision. Every load-bearing statistic below is re-estimated
with **CR2/BRL and coefficient-specific Satterthwaite df, clustered by ticker (28 clusters)**, reusing
`tools/hyp01_inference_feasibility.py` unchanged — the implementation tied out against an independent
R `clubSandwich` reference on 13 of 13 admissible fixtures. **This is retrospective development
inference, not HYP-01 confirmation.**

| Model (+ ticker fixed effects) | n | Coefficient on high_GST |
|---|---|---|
| **Primary:** abs(day_return) | 285 | **+1.509 pp, CR2 SE 0.766, df 16.3, t=1.969, p=0.0662, 95% CI [-0.113, +3.131]** |
| abs(day_return − SPY) | 285 | **+1.539 pp, CR2 SE 0.678, df 16.3, t=2.270, p=0.0371, 95% CI [+0.104, +2.973]** |
| **Strategy E return** (incremental GST value) | 285 | **+0.013 pp, CR2 SE 0.618, df 16.3, t=0.021, p=0.9833, 95% CI [-1.294, +1.320]** |
| **Strategy B return** (incremental GST value) | 285 | **-0.344 pp, CR2 SE 0.461, df 16.3, t=-0.747, p=0.4658, 95% CI [-1.319, +0.631]** |
| Deduplicated events, abs(day_return) | 237 | **+1.921 pp, CR2 SE 0.539, df 20.3, t=3.561, p=0.0019, 95% CI [+0.797, +3.045]** |

**The primary magnitude coefficient weakens under clustering.** The naive ticker-demeaned t was 2.57;
ticker-clustered CR2 gives **t=1.969, p=0.0662**, and the 95% interval **includes zero**. It is
directionally unchanged (+1.509 pp) but **no longer supported at the 5% level** in the primary
specification. The benchmark-adjusted version (p=0.03707) and the deduplicated version
(p=0.00193) do clear 5%. All three are reported; no model was selected after seeing the answers.

**The incremental GST coefficient for Strategy E is +0.013 pp (p=0.98332) — indistinguishable
from zero.** This coefficient, not E's standalone t-statistic, is the test of whether GST adds value,
and it says GST adds nothing. Strategy B's incremental coefficient is -0.344 pp (p=0.46577).

### Repeated controls

| | |
|---|---|
| Signal rows / unique signal events | 152 / **152** |
| Control rows / **unique** control events | 133 / **85** |
| Duplicated control identities | **24** (max reuse **6×**, 48 extra rows) |
| Deduplicated unique event rows | 237 |
| Deduplicated matched difference | +1.788 pp |
| Same-ticker-only pairs | 132 → +1.617 pp |

Duplicated appearances of the same event are **not** treated as independent. The paired analysis retains repeated events because a control can be matched to more than one signal. Duplicated appearances are therefore not independent observations. Two things are reported: (a) a deduplicated analysis in which each distinct ticker+event-day identity appears exactly once, removing reuse entirely; and (b) CR2 inference clustered on TICKER, which is the defensible unit here because every duplicated control identity, and every repeated event, is nested strictly within one ticker. Clustering on ticker is therefore weakly coarser than clustering on event identity and absorbs both the repeated-event and reused-control dependence, as well as any within-firm correlation across separate earnings dates.

### Release timing

AMC events **249**, all 249 mapped to the next trading session. BMO events **36**,
34 mapped to the announcement-date session; the remaining 2 are a single Berkshire **Saturday**
release whose announcement date is not a trading session, so the next session is used. Mapping
verified correct on both conventions.

## What this means

**Initially, strategy E looked promising: benchmark-neutral continuation returned +0.854% net per
trade over 152 high-GST events, with an ordinary t of 3.03, a 63% hit rate and a −10.4% max
drawdown. After estimating the incremental GST coefficient with ticker-clustered CR2 inference, it
became +0.013 pp with p=0.98332 and a 95% interval of [-1.294, +1.320] pp — indistinguishable
from zero.**
E's standalone profitability is post-earnings drift and is **not** a GST result: the identical rule
returns +0.858% on all earnings events and +0.861% on the low-attention controls.

The attention signal that *is* real — a +1.66 pp larger absolute move, surviving same-ticker pairing
at t=2.495 — is a **magnitude** effect, and the overnight gap accounts for **71.7% of mean |gap| plus mean |open-to-close| among
high-GST events** — i.e. it is already in the price before any post-announcement stock trade
can be placed. A directional stock strategy cannot capture it: the
correlation between the gap and the subsequent open→close move is **−0.003**, i.e. the gap carries no
information about what happens next.

## Answers to the six required outputs

1. **Strongest apparent result** — the magnitude effect. Under ticker-clustered CR2 it is
   **+1.509 pp (p=0.0662, CI includes zero)** in the primary specification,
   **+1.539 pp (p=0.03707)** benchmark-adjusted, and **+1.921 pp (p=0.00193)** deduplicated.
2. **Hardest robustness test it survives** — same-ticker fixed effects with ticker-clustered CR2 and
   full deduplication of reused controls, where it is strongest (p=0.00193).
3. **Most convincing result that weakened or disappeared** — two. (a) The primary magnitude
   coefficient fell from a naive t of 2.57 to **t=1.969, p=0.0662**, with an interval spanning zero.
   (b) The GST filter's contribution to Strategy E is **+0.013 pp, p=0.98332** — flatly zero.
4. **Anything economically interesting after costs?** — Post-earnings drift is (E, +0.854% net), but
   it is **not a GST result**. There is **no attention-conditioned stock edge** after costs.
5. **Next single strategy worth prospective testing** — **None stock-based.** The only attention
   effect with support is magnitude, not direction, and it is realized overnight; capturing it would
   require a volatility structure, outside this sprint's stock-only scope and subject to the gated
   prospective process.
6. **Verdict: NO STRATEGY — reaffirmed and strengthened.** The incremental GST coefficient for the
   only profitable strategy is +0.013 pp with p=0.98332, so GST's incremental effect is neither
   economically meaningful nor statistically supported.

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
