# HYP-04 Phase 0 — Feasibility Status (2026-08-18)

**Verdict: Phase 0 PASSES on plumbing and estimator behaviour. It establishes nothing about supply-chain transmission, and no hedging edge is claimed.**

**Placeholder linkage throughout.** Peers are same-sector tickers, not a real supply-chain map — the same limitation as `GST_Task2_PeerDivergence.py`. The real linkage map does not exist and remains the one hard blocker on Phase 1.

Distinct from `HYP04_PHASE0_BUILD_HANDOFF_2026-08-17.md`, which tracks build-process continuity. This document reports Phase 0's methodological results.

---

## 1. What Phase 0 asked, and what it answers

| Question | Answer |
|---|---|
| Can the target variable actually be computed? | **Yes**, under a corrected definition (§3) |
| Does the pipeline run end-to-end? | **Yes** — smoke test green, wired into CI |
| Does the estimator recover a known lag? | **Yes**, with a caveat that changes Stage 2 (§4) |
| Is the sample large enough to continue? | **Yes on synthetic fixtures.** Not yet answerable on real data — no linkage map exists |
| Is IV viable as a Stage 1 target? | **Unanswered.** Realized volatility remains the default (§2) |

---

## 2. Options-coverage audit

Staged consent per Patch 13. Both stages granted by the repo owner and executed 2026-08-17.

| Stage | Tickers | Calls | Cap | Calls/ticker | Coverage OK | Transport failures | Cost |
|---|---|---|---|---|---|---|---|
| 1 — canary | 10 | 20 | 20 | 2, constant | 10/10 (100%) | 0 | $0.00 |
| 2 — full | 17 | 34 | 34 | 2, constant | 17/17 (100%) | 0 | $0.00 |
| **Combined** | **27** | **54** | — | **2, constant** | **27/27 (100%)** | **0** | **$0.00** |

Stage 2 ran with 1s inter-call pacing. Wall clock ~22s. Reports: `HYP04_PHASE0_COVERAGE_AUDIT_CANARY_2026-08-17.json`, `HYP04_PHASE0_COVERAGE_AUDIT_FULL_2026-08-17.json`.

**The constraint that binds is rate-limiting, not money.** The provider is yfinance against Yahoo's free unauthenticated endpoint — no API key, no metering. Patch 13's original dollar-budget framing did not apply and was corrected in its Round 5 revision. If this audit is ever pointed at a genuinely metered provider, re-derive the constraint rather than carrying either framing forward.

**Target selection — decided by availability, reported before the decision:**

> **Realized volatility remains the Stage 1 target. IV is NOT promoted.**

100% *current*-chain coverage does not establish historical coverage. **yfinance has no historical options endpoint at all**, so the plan's actual question — usable historical chains far enough back — is untouched by this check. This is the same limitation that made realized volatility the default in the first place.

Expiration depth varies by more than an order of magnitude across the universe (NFLX 17 expirations / 189 calls / 179 puts; REG 4 / 5 / 4). Every peer has *a* readable chain, but the thin names — precisely the ones this hypothesis cares most about — have visibly thinner surfaces. Worth carrying into any future historical-coverage check.

---

## 3. Target variable

```
RVar(h)  = (1/h) · Σ r_i²        over [t+1, t+h]   — a mean, not a sum; no square root
RVar_ref = (1/20) · Σ r_i²       trailing 20 sessions ending at t=0
raw      = log(RVar(h)) − log(RVar_ref)            — floored before each log
target   = raw − earnings_cycle_baseline(peer, days_to_own_earnings)
```

Single grid, h = 1…20, used for both target computation and lag detection.

### The bug this replaced, and the evidence it is fixed

The earlier definition `RV(h) = √(Σr_i²)` grows as `σ√h` under constant volatility, so `RV(h) − reference` carried a deterministic `√h`-shaped trend containing **no volatility information** — exactly the shape a lag profile exists to detect.

Demonstrated as **bias vs. noise** by giving both definitions ~26× more data (144 → 3840 pairs), on a constant-vol zero-effect fixture:

| Definition | range across h≥3, small N | large N | Verdict |
|---|---|---|---|
| Corrected `log(RVar(h))` | 0.0645 | 0.0148 | shrinks ≈ √26 → **sampling noise** |
| Rejected `√(Σr²)` | 2.797 | 2.833 | **unchanged** → deterministic **bias** |

The rejected definition's slope is identical to three decimals at both sample sizes (+0.1599 / +0.1604). The regression test asserts **this contrast**, not an absolute tolerance — a tolerance could be satisfied by tuning; the contrast cannot.

### Two exclusion numbers, reported separately (Patch 12)

They measure different things, and conflating them would hide which one binds.

| Quantity | Measured (MAIN fixture) | Threshold | Peers/obs affected |
|---|---|---|---|
| **Retained-history fraction** — anchor-adjacent history removed from baseline *estimation* | min 0.253, mean 0.260 | 0.10 | 0 / 192 peers below |
| **Bucket-population exclusion** — observations dropped for an under-populated days-to-earnings bucket | 32.3% | 20 obs/bucket | 19,860 / 61,440 observations |

**The retained-history threshold is set by arithmetic, not tuned.** Excluding ±E sessions around each anchor removes about `(2E+1)/63` of a peer's calendar when anchors report quarterly, so retention has a **structural ceiling near 0.20–0.30** — measured 0.25–0.28. An initial threshold of 0.30 sat *above* that ceiling and would have flagged every peer in every possible dataset; it was lowered to 0.10 on that reasoning, explicitly not to sit just under the observed value.

**Bucket exclusion is accept-and-report.** Under-populated-bucket observations are dropped from the regression sample, not imputed. Buckets were **not** widened and the threshold was **not** lowered — widening blurs resolution exactly where the pre-earnings ramp is steepest, reintroducing the confound residualization exists to remove.

---

## 4. Lag detection — a specification issue found by running the code

**With an expanding-window target, `argmax|t_h|` is not the lag.**

`RVar(h)` averages over `[1, h]`. With peer vol elevated on days `[L, L+W-1]`, the affected fraction `(h−L+1)/h` is maximized at `h = L+W-1` — the **end** of the reaction window. The **onset** is the first horizon clearing significance.

Confirmed across six (L, W) combinations:

| L | W | argmax | predicted L+W−1 | first significant | truth L |
|---|---|---|---|---|---|
| 3 | 5 | 7 | 7 ✓ | 3 | 3 ✓ |
| 5 | 5 | 9 | 9 ✓ | 5 | 5 ✓ |
| 8 | 5 | 12 | 12 ✓ | 8 | 8 ✓ |
| 5 | 3 | 7 | 7 ✓ | 5 | 5 ✓ |
| 5 | 8 | 12 | 12 ✓ | 5 | 5 ✓ |
| 2 | 4 | 5 | 5 ✓ | 2 | 2 ✓ |

**Consequence:** Stage 2 sizes hedge tenor off the lag. Using the peak buys `(W−1)` days too much tenor and arrives after the move has started. The code exposes `onset_horizon` and `peak_horizon` as two distinct quantities.

### Onset estimation method — as implemented

Patch 15 asks that the onset method be confirmed against the implementation rather than assumed. It is:

> **`onset_horizon` = the first horizon, reading forward from h = 1, whose |t_h| exceeds the max-T permutation critical value (the empirical 95th percentile of the permuted max-|t| distribution).**

This matches the "natural default" Patch 15 proposes, with two specifics that patch does not yet state and which should be recorded with it:

1. **The threshold is the multiplicity-corrected max-T critical value, not a per-horizon one.** The onset therefore inherits the same family-wise false-positive control as the peak. Reading onset off an uncorrected per-horizon t would reintroduce exactly the multiplicity problem the max-T procedure exists to solve, and would bias onset *early* — the more dangerous direction.
2. **Onset is gated on the peak first.** If the overall max-T test does not clear, `onset_horizon` is `None` and no onset is reported at all. There is no path by which an onset is claimed while the profile as a whole is non-significant.

Implementation: `hyp04_supply_chain_hedge/inference.py::local_projection_analysis`. Horizons are evaluated in ascending order (h = 1…20), so "first clearing" is literal.

**Known limitation — onset detection is late-biased.** At the onset horizon only `1/L` of the averaging window is affected, so margin over the threshold thins as the lag deepens. Measured |t| at h=L: 5.58 (L=3), 3.53 (L=5), 3.98 (L=8), 4.69 (L=10) against critical values near 2.6–2.9. One L=8 draw produced |t| = 2.08 and reported onset = 9. The error is **one-sided — late, never early** (h < L carried |t| = 0.71 on that same draw). Late onset means a short tenor, the same direction of practical error as using the peak, just smaller. Report onset with this caveat, not as a point estimate.

### Estimator behaviour

| Fixture | onset | peak | peak \|t\| | max-T crit | p | significant |
|---|---|---|---|---|---|---|
| MAIN (L=5, W=5) | **5** | **9** | 22.96 | 2.65 | 0.0010 | Yes |
| ZERO_EFFECT | none | 3 | 1.38 | 2.72 | 0.63 | No |

Placebo test: MAIN p = 0.003 (real linkage separates from random pairing), ZERO_EFFECT p = 0.91 (does not). Both correct.

### Prewhitened CCF — secondary cross-check

Filter fit to the **peer-volatility** series, one filter applied to both series, significance from circular-shift permutation (never Bartlett bands).

Direct confirmation of the filter direction: AR(5) on peer-vol gives **Σ|φ| = 1.093** (φ₁ = 0.849); on the anchor-shock series, **Σ|φ| = 0.048** — already near-white. Filtering with a shock-fit filter would be a near-no-op, leaving the peer's vol clustering untouched.

On a single peer the CCF is non-significant (peak lag 19, p = 0.25). This is a **power difference, not a disagreement**: one peer sees ~16 anchor events while the LP pools thousands of observations. Logged as the expected asymmetry.

---

## 5. Sample-size gate

```
DEFF  = 1 + (m̄ − 1) · ICC        ICC floored at 0 here only
N_eff = N_pairs / DEFF
```

`N_pairs` (ICC = 0) and `N_events` (ICC = 1) are the two **bounds**; neither is gated on directly. The ICC is used exactly once, to place `N_eff` between them.

### Multiplicity target — derived, not assumed

| Source | k (effective independent tests) | Implied total N |
|---|---|---|
| Naive single-test **baseline** (labelled only, never the gate) | 1 | 126 |
| Patch 2 Round-3 *prediction* | 2–4 | 152–178 |
| **Measured, step 3b permutation** | **6.05–6.34** | **193–195** |
| Fully independent horizons (upper bound) | 20 | 238 |

**Operative target: N ≈ 193.** Patch 2's Round 3 addition predicted k_eff "closer to 2–4," implying a revision toward 150–190. **That prediction was wrong** — the measured value lands at the lower edge of the provisional 190–240 range, so that range is **confirmed rather than narrowed**.

### Gate results

| Fixture | N_pairs | N_events | ICC (raw → floored) | DEFF | N_eff | Target | Verdict |
|---|---|---|---|---|---|---|---|
| **MAIN** | 2,079 | 384 | +0.0506 → 0.0506 | 1.224 | 1,699.2 | 193.3 | **PASS** |
| **Fixture A** (zero effect, ample N) | 2,039 | 384 | −0.0125 → 0.0000 | 1.000 | 2,039.0 | 195.0 | **PASS** ✓ |
| **Fixture B** (insufficient N, effect 0.80) | 19 | 6 | −0.2048 → 0.0000 | 1.000 | 19.0 | 195.0 | **FAIL** ✓ |

Both negative controls behave correctly: **the gate responds to sample size and ignores effect size.** A well-powered null passes; a strong effect cannot buy its way past.

**ICC stability.** MAIN: 384 clusters, bootstrap 95% CI **(0.015, 0.084)** — the interval excludes 0, so the design effect is real but modest. Both null fixtures produced **negative raw ICCs**, a known small-sample artifact; unfloored these would push DEFF below 1 and make `N_eff` exceed `N_pairs`, which is backwards. The floor applies only inside DEFF; raw values are reported.

**Satterthwaite dof = 88.5** at h=5 on MAIN, against `N_eff` = 1,699 and 384 clusters. The two diverge by a wide margin, and **the Satterthwaite dof is the more honest number** — it reflects the clustering structure inference actually used, which DEFF's single clustering dimension does not capture. Read the gate accordingly.

**Estimator mismatch, stated not reconciled.** The power calculation is a two-sample Cohen's-d formula while the analysis is a continuous LP regression. Dichotomizing a continuous predictor costs efficiency, so this is a deliberately **conservative proxy**, not an exact match.

**Implied calendar coverage:** ~96–200 anchor events/year across a 24–50-ticker quarterly universe. At the ICC = 1 endpoint, a 193-event target is roughly **1.0–2.0 years** of coverage; materially less as the empirical ICC comes in below 1.

---

## 6. Stated limitations

- **One-way clustering only** (anchor event). Two-way (anchor × calendar period) is **not implemented**: no multiway CR2 exists in this repository, validated or otherwise, and standing up an unvalidated estimator would contradict this project's own treatment of unvalidated inference machinery. One-way understates SEs in the direction that makes marginal results look significant. Recorded as a Phase 0 limitation, which is the fallback the build prompt authorises.
- **h = 1–2 are statistically pathological.** `log(RVar(1)) = log(r₁²)`, a log-χ²₁; the mean target swings −0.527 → +0.059 purely with sample size. This does **not** bias β_h — each horizon has its own intercept — but those estimates are very noisy.
- **Onset detection is late-biased** for deep lags (§4).
- **Retained history is structurally capped** near 0.28 for quarterly anchors (§3).
- **32.3% of candidate observations** are excluded by bucket population (§3).
- **Current-chain coverage only** — nothing established about historical options data (§2).

---

## 7. Quantum autocorrelation function

**Not built. Skipped, as anticipated.**

The term refers to quantum time-correlation functions from statistical mechanics (⟨A(0)A(t)⟩ for quantum operators, involving commutators and quantum ensembles). No well-defined, citable construction exists for applying that construct to classical financial return series, and no track record exists in finance the way CCF, GARCH, and lag-regression methods have.

Nothing quantum-flavoured was improvised to fill the slot. The module is explicitly out of scope for "done" and feeds no decision, gate, or conclusion.

---

## 8. Build and test status

| Artifact | Status |
|---|---|
| `hyp04_supply_chain_hedge/` (9 modules) | Complete |
| `test_hyp04_supply_chain_hedge_target.py` | **32 checks, all pass** |
| `test_hyp04_supply_chain_hedge_inference.py` | **88 checks, all pass** |
| `test_hyp04_supply_chain_hedge_smoke.py` | **42 checks, all pass** |
| CI workflow | Wired, discovery + live-runner guard simulated green |
| Colab notebook | 26 cells, executes top-to-bottom clean |
| VS Code workspace | `settings.json`, `launch.json`, package `README.md` |

Two real defects were caught by tests rather than by review:

1. **`apply_ar_filter` boundary** — the compact reverse slice `x[t-1:t-p-1:-1]` silently returns an *empty array* when `t == p`, because the stop index wraps.
2. **Audit budget-exhaustion path** — used `tickers.index(t)`, which resolves a repeated ticker to its *first* occurrence and duplicated every entry after it. Caught by the smoke test's duplicate-ticker case.

---

## 9. What Phase 0 does NOT establish

- ❌ **No hedging edge**, of any size, in any direction. None is claimed anywhere.
- ❌ **No supply-chain transmission finding.** The linkage is a same-sector placeholder.
- ❌ **No real-data result.** Every number above comes from synthetic fixtures with known ground truth or from a coverage audit that counted chains.
- ❌ **IV is not viable as a Stage 1 target** on current evidence.

---

## 10. Blockers and open decisions

**Hard blocker on Phase 1:** the real supply-chain linkage map (ticker pairs + relationship type + confidence) — **plus a first-known/established-as-of date per pair**. A map built today encodes relationships known today; applying it to historical anchor events without as-of dates is look-ahead bias, the same class of problem this project's own forensic audit already found in the GST z-score history.

> **Source changed 2026-08-18 — the blocker is unchanged.** The automated teammate mapping was deprioritised; the project switched to **hand curation** against a fixed 15-column template that carries the as-of date natively, so the retrofit risk above is resolved by construction. A validating ingestion path is built and tested (`hyp04_supply_chain_hedge/curated_linkage.py`), but **zero rows are curated**. A loader is not a map. Registry v1.1 still records the required linkage measurement as `does_not_exist`. See [`HYP04_LINKAGE_SOURCE_DECISION_2026-08-18.md`](HYP04_LINKAGE_SOURCE_DECISION_2026-08-18.md).
>
> **Open, and the repo owner's call:** whether the curated map targets HYP-01's frozen 24-ticker universe or a smaller first-pass scope. This drives how long Phase 1 stays blocked and what `N_events` can eventually reach against the 193-event floor.

**Open decisions requiring the repo owner:**

1. **Patch the plan's lag-estimator wording** (§4). The code is correct; the docs would send a fresh implementer to argmax.
2. **HYP-04 is not in the hypothesis registry.** The plan docs arrived as HYP-02, an ID already held by "cross-source attention divergence vs. earnings surprise." Renamed to HYP-04 with owner approval, but HYP-04 still does not appear in `README.md`'s registry or the North Star doc.
3. **Before Phase 2**, merge `HYP04_PLAN_ROUND2_EDITS.md` into a plan v0.2 and demote it to a dated amendment record. A Phase 2 lock referencing two mutually-amending documents is the drift risk this project's tamper tests exist to catch.

---

*Nothing in this document constitutes investment advice, a solicitation, or a representation that any approach is profitable.*
