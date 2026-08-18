# HYP-04 Phase 0 — build handoff (2026-08-17)

**Trigger:** step-3 boundary checkpoint + owner-requested pause.
**Scope:** build-process continuity only. **Not** the Phase 0 feasibility status doc (build-prompt item 5) — that reports methodological results once the pipeline runs end-to-end, and does not exist yet.
**Nothing is committed.** All work is untracked in the working tree on `main`.

## Authoritative docs — read these, don't rely on this file's summaries

1. `Live Signal Engine/HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.1_DRAFT.md`
2. `Live Signal Engine/HYP04_PLAN_ROUND2_EDITS.md` — **authoritative** where it disagrees with the plan. 14 patches. Where a patch carries a "Round N correction" marker or a struck-through "Superseded by" note, that corrected text governs; earlier wording is kept for traceability and must **not** be implemented (Patch 6 bullet 1 superseded by Patch 10).
3. `Live Signal Engine/CLAUDE_CODE_BUILD_PROMPT_HYP04_v8.md`

`HYP04_PHASE0_SESSION_HANDOFF.md` at repo root is an earlier long-form handoff from this session; superseded by this file where they disagree.

---

## 1. THE SINGLE NEXT ACTION

**Owner decision pending first** (see §4a): whether to patch the plan's lag-estimator wording. Then finish **step 3b** — wire the `N_eff` gate itself into a gate module and assert Fixture A passes / Fixture B fails. The 3b *diagnostic* has already run; only the gate wiring remains.

---

## 2. Build-sequence status

| Step | State | Detail |
|---|---|---|
| 1 — synthetic-fixture generator | **complete, verified** | 4 fixtures with attached ground truth |
| 2 — audit + target + residualization | **complete, verified** | both audit consent stages granted and executed |
| 3 — inference layer | **complete, verified** | LP, max-T permutation, CCF, ridge, LOOCV, placebo |
| 3b — diagnostic + N_eff gate | **half done** | diagnostic RUN (k_eff measured); **gate not wired** ← next |
| 4 — Stage 2 rules engine | not started | |
| 5 — smoke test, Colab, VS Code, status doc | not started | |

---

## 3. File / module state

```
hyp04_supply_chain_hedge/
├── __init__.py            FINISHED
├── constants.py           FINISHED  every value traced to a numbered patch
├── fixtures.py            FINISHED  step 1
├── target.py              FINISHED  step 2 target half
├── audit.py               FINISHED  step 2 audit half
├── run_canary_audit.py    FINISHED  stage-1 runner (executed)
├── run_full_audit.py      FINISHED  stage-2 runner (executed)
├── clustered_se.py        FINISHED  CR2 + Satterthwaite + ICC (copied w/ provenance)
└── inference.py           FINISHED  step 3
```

Not yet created: the N_eff gate module, `stage2.py`, any `test_hyp04_*.py`, CI workflow, notebook, VS Code scaffolding, package `README.md`.

**No tests are written yet.** All verification so far has been ad-hoc scratchpad scripts, not committed tests. Everything in §5 and §6 must become real test files before step 5.

---

## 4. OPEN — awaiting the repo owner

### 4a. Lag-estimator wording — NEW, blocking the plan docs (not the code)

The plan says *"the horizon where it peaks and clears significance is the estimated lag."* With an expanding-window target these are **two different horizons**.

`RVar(h)` averages over `[1, h]`. With vol elevated on days `[L, L+W-1]`, the affected fraction `(h−L+1)/h` is maximized at `h = L+W-1`. So **argmax finds the END of the reaction window; first-significant finds the ONSET.** Confirmed 6/6 across (L,W) = (3,5), (5,5), (8,5), (5,3), (5,8), (2,4): argmax matched `L+W-1` every time, first-significant matched `L` every time.

**Consequence for Stage 2:** hedge tenor is sized off the lag, so using the peak buys a tenor `(W−1)` days too long and arrives late.

**Code already handles this** — `LocalProjectionResult` exposes `onset_horizon` and `peak_horizon` separately, with onset judged against the *same max-T critical value* so it inherits the multiplicity correction rather than being read off an uncorrected t. The open item is whether the **plan docs** get a patch, since their current wording would send a fresh implementer to argmax.

### 4b. HYP-04 is not in the hypothesis registry

Plan docs arrived as HYP-02; that ID is taken by "cross-source attention divergence vs. earnings surprise" (`README.md`). Owner approved renaming to HYP-04, applied mechanically (zero residual `HYP-02`/`HYP02`/`hyp02`; the legitimate `HYP-01` references intact). HYP-04 still does **not** appear in the registry or North Star doc. Unmade human decision; not blocking feasibility work.

### 4c. Audit consent — CLOSED, both stages granted and executed

Recorded so it cannot be re-litigated or accidentally re-run:

- **Stage 1 (canary), granted 2026-08-17**: 10 tickers, hard cap. Executed — 20/20 calls, 2 calls/ticker constant, 10/10 coverage, 0 transport failures, $0.00.
- **Stage 2 (full), granted 2026-08-17**: remaining 17 tickers, ~1s pacing. Executed — 34/34 calls, 2 calls/ticker constant, 17/17 coverage, 0 transport failures, $0.00, ~22s wall clock.

Combined: **27/27 placeholder-universe peers, 54 calls, 100% current-chain coverage.** Reports: `HYP04_PHASE0_COVERAGE_AUDIT_CANARY_2026-08-17.json`, `HYP04_PHASE0_COVERAGE_AUDIT_FULL_2026-08-17.json`.

**Critical caveat (Patch 13 Round 5):** yfinance serves *current* chains only — no historical endpoint. 100% coverage does **not** promote IV to a Stage 1 target; **realized volatility remains the default**. If historical coverage is ever checked against a genuinely historical provider, re-run Patch 13's staged consent process fresh — neither the cost nor the rate-limit findings carry over.

---

## 5. Verified results to carry into the status doc

### 5a. RV-normalization fix — confirmed empirically

On `CONSTANT_VOL_no_ramp` at two sample sizes (144 → 3840 pairs, ~26×):

| Definition | range across h≥3, small N | large N | Verdict |
|---|---|---|---|
| Corrected `log(RVar(h))` | 0.0645 | 0.0148 | shrinks ≈ √26 → **noise** |
| Rejected `sqrt(Σr²)` | 2.797 | 2.833 | unchanged → **bias** |

Rejected definition's slope identical to three decimals at both sizes (+0.1599 / +0.1604). **The regression test should assert this contrast**, not an absolute tolerance — it cannot be passed by tuning.

### 5b. Lag recovery and null behaviour

| Fixture | onset | peak | peak \|t\| | max-T crit | p | significant |
|---|---|---|---|---|---|---|
| MAIN (L=5, W=5) | **5** ✓ | **9** ✓ (=L+W−1) | 22.96 | 2.65 | 0.0033 | True |
| ZERO_EFFECT | None ✓ | 3 | 1.38 | 2.72 | 0.63 | False |

Placebo: MAIN p = 0.002 (separates from random), ZERO_EFFECT p = 0.90 (does not). Both correct.

### 5c. Step 3b diagnostic — multiplicity target CONFIRMED, not revised

Measured effective independent tests: **k_eff = 6.34** (MAIN), 7.82 (ZERO_EFFECT), of 20 horizons.

| k_eff | implied total N |
|---|---|
| 2 | 152 |
| 4 | 178 |
| **6.34 (measured)** | **195** |
| 20 | 238 |

Patch 2's Round 3 addition predicted k_eff "closer to 2–4," implying a revision toward 150–190. **That prediction was wrong.** The measured value lands at the lower edge of the provisional 190–240 range, so **keep 190–240** rather than narrowing it. Naive single-test baseline stays 126, labelled as a baseline only.

### 5d. Prewhitening direction — confirmed empirically

AR(5) fit to the **peer-vol** series: Σ|φ| = **1.093** (strong persistence, φ₁ = 0.849).
AR(5) fit to the **anchor-shock** series: Σ|φ| = **0.048** (essentially white).

Direct confirmation of Patch 1: filtering with a shock-series filter would be a near-no-op, leaving the peer's vol clustering — the actual source of spurious cross-correlation — untouched.

CCF on a *single peer* is non-significant (peak lag 19, p = 0.25). This is a **power difference, not a contradiction**: one peer sees ~16 anchor events, while the LP pools thousands of observations. Log it as the expected asymmetry, not a disagreement between methods.

### 5e. Bug fixed during step 3

`apply_ar_filter` used the compact reverse slice `x[t-1 : t-p-1 : -1]`, which silently returns an **empty array** when `t == p` because the stop index wraps to the end. Replaced with `x[t-p:t][::-1]` and commented so it does not regress.

---

## 6. Known caveats

- **h = 1–2 are statistically pathological.** `log(RVar(1)) = log(r₁²)`, a log-χ²₁; mean target swings −0.527 → +0.059 purely with sample size. Does **not** bias β_h (LP runs a separate regression per horizon, each with its own intercept, absorbing level shifts). Grid stays 1…20 per Patch 3 — reporting caveat only.
- **Retained-history ceiling ~0.28.** Excluding ±E sessions around each quarterly anchor removes ~(2E+1)/63 of a peer's calendar. `MIN_RETAINED_HISTORY_FRACTION = 0.10` is set **below that structural ceiling by arithmetic**, not tuned to the observed value. Measured: 0.272 / 0.253, 0 peers below threshold.
- **Bucket-population exclusion is material**: 26.3% (CONSTANT_VOL) / 32.3% (MAIN) of candidate observations dropped under Patch 12's accept-and-report policy. Reported as its own number, separate from retained-history. Buckets are **not** widened and the threshold is **not** lowered.
- **Clustering is one-way (anchor event).** Two-way (anchor × calendar period) is **not** implemented: no multiway CR2 exists in this repo, validated or otherwise. Recorded as a stated Phase 0 limitation, which is the fallback the build prompt authorises. `clustered_se.TWO_WAY_LIMITATION_NOTE` carries the text.

---

## 7. Two convention decisions that must not silently reverse

### 7a. This repo does not use pytest

The build prompt says "pytest". **No test in this repo uses it.** Every `test_market_response_*.py` / `test_phase2_*.py` uses a hand-rolled harness — `check(label, ok, detail)`, `skip(label, why)`, a `FAILURES` list, `sys.exit(1)` — run directly as `python file.py`. CI globs `test_market_response*.py` and loops over them; no requirements file mentions pytest. Skips are counted separately, **never as passes**.

HYP-04 tests should follow that pattern, named `test_hyp04_supply_chain_hedge_*.py`, with a new workflow `hyp04-supply-chain-hedge-tests.yml` modelled on `hyp01-r-reference-validation.yml`.

### 7b. CR2/Satterthwaite copied, not imported

`clustered_se.py` mirrors `cr_vcov` / `satterthwaite_df` from `tools/hyp01_inference_feasibility.py` with a full provenance header, because (1) that module declares itself NOT PRODUCTION CODE and patches `socket` at import, and (2) `test_market_response_hyp01_r_reference_validation.py::test_8_isolation` **actively asserts no production module imports the bridge**. Same pattern `gst_market_response/constants.py` already establishes.

---

## 8. Environment

No scientific Python existed on this machine at session start (`python` on PATH is the Windows Store stub, exits 49). Project-local venv, gitignored:

```bash
"C:\Users\bchen\.local\bin\.venv\Scripts\python.exe" -m venv .venv
```

```bash
.\.venv\Scripts\python.exe -m pip install numpy pandas scipy yfinance
```

numpy 2.5.2 · pandas 3.0.5 · scipy 1.18.0 · yfinance 1.6.0 · Python 3.14.7.

**`PYTHONPATH` is required** — the package is not installed:

```bash
$env:PYTHONPATH = "C:\Users\bchen\Quant_Research_Project"; .\.venv\Scripts\python.exe -m hyp04_supply_chain_hedge.fixtures
```

No sklearn, deliberately — ridge is closed-form in `inference.py::ridge_fit`; adding sklearn would not match repo conventions.

---

## 9. Non-negotiables (restated so they cannot drift)

- No real-capital or live-trading logic. **No claim anywhere that a hedging edge has been found.**
- Placeholder linkage labelled everywhere; same limitation as `GST_Task2_PeerDivergence.py`.
- Do not silently swap linkage source, model family, lag-detection method, prewhitening target, RV/RVar estimator, or N-gate formulation.
- Prewhitening: filter fit to **peer-vol series**, same single filter to both, **no double-prewhitening fork**; significance from circular-shift permutation, never Bartlett.
- max-T permutation across the horizon grid, **not Bonferroni**.
- N-gate: `N_eff = N_pairs / DEFF`, ICC floored at 0 for DEFF while the **raw** (possibly negative) ICC is still reported.
- **Quantum autocorrelation function**: that exact term, never "quantum-inspired". Isolated, non-load-bearing. Skip and say so if no citable construction exists. **Explicitly out of scope for "done"** — never in a Definition of Done, not even as "(if built)".
- Phase 0 only. Do not implement Phases 1–4.

---

## 10. Process notes

`HYP04_PLAN_ROUND2_EDITS.md` currently **overrides** the plan doc. Fine for a build; a Phase 2 lock referencing two mutually-amending documents is the drift risk this project's tamper tests exist to catch. **Before Phase 2**, merge patches into a plan v0.2 and demote the edits doc to a dated amendment record.

Patch 14's earlier reference to `claude/session-handoff-2026-08-17.md` was **resolved by its own Round 4 correction** — that file never existed in this repo, and the style is now described self-contained. No external exemplar needed.

`CLAUDE_CODE_BUILD_PROMPT_HYP02_1.md` at repo root is an older, unrelated file predating this work. Left untouched; do not use.
