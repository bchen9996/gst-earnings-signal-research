# HYP-04 Phase 0 — session handoff

**Written:** 2026-08-17
**Purpose:** let a fresh session resume the HYP-04 Phase 0 build without re-deriving context.
**Status:** build steps 1 and 2 of 5 landed and verified; steps 3, 3b, 4, 5 not started.
**Nothing is committed.** All work below is untracked in the working tree on `main`.

---

## 0. Read these first, in this order

| Order | File | Why |
|---|---|---|
| 1 | `Live Signal Engine/HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.1_DRAFT.md` | The plan |
| 2 | `Live Signal Engine/HYP04_PLAN_ROUND2_EDITS.md` | **Authoritative** wherever it disagrees with the plan |
| 3 | `Live Signal Engine/CLAUDE_CODE_BUILD_PROMPT_HYP04_v6.md` | The build spec being executed |
| 4 | This file | What actually happened |

In doc 2, patches carrying a **"Round 2 correction"** / **"Round 3 correction"** marker or a struck-through **"Superseded by"** note are authoritative; earlier wording in the same patch is kept visible for traceability and must **not** be implemented. Patch 6's first bullet is struck through and superseded by Patch 10.

---

## 1. Why the name is HYP-04, not HYP-02

The plan documents arrived named HYP-02. **That ID was already taken.** The repo's hypothesis registry (see `README.md`) has:

- HYP-01 — pre-earnings attention and market repricing (`ACTIVE_COLLECTING`)
- **HYP-02 — cross-source attention divergence vs. earnings surprise** (`PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`)
- HYP-03 — post-earnings attention decay (`PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`)

The supply-chain hedge-lag model is a different question entirely. Landing it under an in-use ID in a project built on append-only registries and named hypothesis locks would collide with the exact convention that discipline exists to protect. The user approved the rename to **HYP-04**.

The rename was mechanical and verified: zero residual `HYP-02` / `HYP02` / `hyp02` strings in the three renamed docs, and the 6 legitimate `HYP-01` references (reusing HYP-01's CR2/Satterthwaite machinery and lock-doc conventions) were left untouched.

**Still open:** HYP-04 does not yet appear in the repo's hypothesis registry or North Star doc. If this project's convention requires a new hypothesis to be registered before Phase 0 code lands, that is a human decision that has not been made. Flagged to the user; not blocking Phase 0 feasibility work.

---

## 2. Environment — this machine had no scientific Python

There was **no working Python environment** on this machine when the session started: `python` on PATH is the Windows Store stub (exits 49), and the only real interpreter (`C:\Users\bchen\.local\bin\.venv\Scripts\python.exe`, 3.14.7) had nothing but `pip`.

A project-local venv was created and is **gitignored** (`.venv/` added to `.gitignore` this session):

```bash
"C:\Users\bchen\.local\bin\.venv\Scripts\python.exe" -m venv .venv
```

```bash
.\.venv\Scripts\python.exe -m pip install numpy pandas scipy
```

Installed: **numpy 2.5.2, pandas 3.0.5, scipy 1.18.0** on Python 3.14.7. (scipy 1.18.0 on Python 3.14 matches what `tools/requirements-hyp01-feasibility.txt` records the HYP-01 study as having used.)

**Running anything requires `PYTHONPATH`** — the package is not installed:

```bash
$env:PYTHONPATH = "C:\Users\bchen\Quant_Research_Project"; .\.venv\Scripts\python.exe -m hyp04_supply_chain_hedge.fixtures
```

---

## 3. Repo conventions that override the build prompt

Two decisions were made from repo evidence rather than from the prompt's literal wording. Both follow the prompt's own higher-order instruction to match this project's existing rigor and style. **Do not silently reverse them.**

### 3a. This repo does not use pytest

The build prompt says "pytest". **No test in this repo uses pytest.** Every `test_market_response_*.py` and `test_phase2_*.py` file uses a hand-rolled harness:

```python
def check(label: str, ok: bool, detail: str = "") -> None: ...
def skip(label: str, why: str) -> None: ...
FAILURES: list[str] = []
...
if __name__ == "__main__":
    test_1(); test_2(); ...
    if FAILURES: sys.exit(1)
```

CI (`.github/workflows/market-response-tests.yml`) globs `test_market_response*.py` at repo root and loops `python "$f"` — there is no pytest in any requirements file. Tests for HYP-04 should follow the repo pattern, named `test_hyp04_supply_chain_hedge_*.py`, with a **new** workflow (`hyp04-supply-chain-hedge-tests.yml`) modelled on `hyp01-r-reference-validation.yml`.

Note the repo's skip discipline: skips are **counted and reported separately, never as passes**.

### 3b. CR2/Satterthwaite must be copied, not imported — and two-way clustering is a stated limitation

The CR2 and Satterthwaite implementations live in `tools/hyp01_inference_feasibility.py` (`cr_vcov(X, y, g, "CR2")`, `satterthwaite_df(X, g, c)`). Two constraints:

1. That file's header says **"NOT PRODUCTION CODE. NOT AN ANALYSIS ENTRY POINT."** and `test_market_response_hyp01_r_reference_validation.py::test_8_isolation` **actively asserts that no production module imports the bridge**. Follow `gst_market_response/constants.py`'s established pattern instead: **copy with a provenance comment**, never import across that boundary.
2. It is **one-way clustering only**. There is no two-way / Cameron-Gelbach-Miller implementation anywhere in this repo, validated or not.

Phase 0 therefore implements **one-way (anchor-event) clustering and flags two-way as a stated limitation** — which is precisely the fallback the build prompt already authorises for this case (v6 line 44), not a new gap. Given this repo's culture around unvalidated inference machinery (CR2/CR3/bootstrap sat `BLOCKED_PENDING_INDEPENDENT_VALIDATION` until an R cross-check existed), standing up an unvalidated two-way estimator would be out of character and out of scope.

---

## 4. What is built

```
hyp04_supply_chain_hedge/
├── __init__.py       # banner: placeholder linkage, no capital logic, no edge claim
├── constants.py      # every preregistered value, each traced to a numbered patch
├── fixtures.py       # BUILD STEP 1 — done, verified
└── target.py         # BUILD STEP 2 (target half) — done, verified
```

Plus, in `Live Signal Engine/`: the three renamed HYP-04 docs.

### `fixtures.py` — step 1 (complete)

Four fixtures, each carrying the ground truth it was generated from:

| Fixture | Events | Pairs | Purpose |
|---|---|---|---|
| `MAIN_known_lag_5` | 384 | 3072 | lag=5, effect=0.55 — lag recovery + step 3b's max-T run |
| `ZERO_EFFECT_ample_n` | 384 | 3072 | Patch 10 Fixture A — LP peak must be non-significant, **gate must PASS** |
| `INSUFFICIENT_N_large_effect` | 6 | 24 | Patch 10 Fixture B — **gate must FAIL** despite effect=0.80 |
| `CONSTANT_VOL_no_ramp` | 144 | 864 | h-trend regression test for the RV-normalization bug |

Generative model is stated in the module docstring. Peers carry their **own earnings ramp** (vol rises into their own report regardless of any anchor) — this is deliberate, so residualization has a real confound to remove and an absent-residualization bug is detectable.

Seeding uses a SHA-256-derived offset, not `hash()` — same reasoning as `tools/hyp01_inference_feasibility.py:stable_name_offset` (Python randomises str hashing per process).

### `target.py` — step 2, target + residualization half (complete)

Implements the corrected Patch 9 definition:

```
RVar(h)  = (1/h) * sum_{i=1..h} r_i^2          # variance, mean not sum, no sqrt
RVar_ref = (1/20) * sum r_i^2                   # trailing 20 sessions ending at t=0
raw      = log(RVar(h)) - log(RVar_ref)         # log-variance ratio, floored
target   = raw - earnings_cycle_baseline(peer, days_to_own_earnings)
```

Also provides `horizon_trend_diagnostic()` (mean target by h) and a `residualize=False` switch so a test can prove residualization does real work.

---

## 5. Verified result: the RV-normalization fix is confirmed, empirically

This is the most important evidence produced this session and should go in the Phase 0 status doc.

Run on `CONSTANT_VOL_no_ramp` at two sample sizes (144 → 3840 pairs, ~26×):

| Definition | range across h≥3, small N | range across h≥3, large N | Verdict |
|---|---|---|---|
| **Corrected** `log(RVar(h))` | 0.0645 | 0.0148 | shrinks ~4.3× ≈ √26 → **noise** |
| **Rejected** `sqrt(sum r²)` | 2.797 (vol units) | 2.833 (vol units) | **unchanged** → **bias** |

The rejected definition's slope is identical to three decimals at both sample sizes (+0.1599 vs +0.1604). That is a deterministic artifact that no amount of data removes — exactly the failure mode Patch 9's Round 3 correction describes.

**The regression test should assert this contrast**, not an absolute threshold: the corrected target's h-trend must shrink with N, the rejected one's must not. That is far stronger than any fixed tolerance and cannot be passed by tuning.

---

## 6. Open findings — real, not yet resolved

These were discovered by running the code and are genuine Phase 0 output. **Do not tune them away.**

### 6a. Retained-history has a structural ceiling (~0.28), and the first threshold was wrong

Excluding ±E sessions around each anchor removes about `(2E+1)/63` of a peer's calendar when anchors report quarterly. Measured:

| Exclusion | Retained |
|---|---|
| ±10 | 0.704 |
| ±15 | 0.563 |
| ±21 | 0.394 |
| **±25 (current)** | **0.281** |
| ±30 | 0.147 |

`MIN_RETAINED_HISTORY_FRACTION` was initially set to **0.30 — above the structural ceiling**, so it would have flagged every peer in every possible dataset. That is a broken check, not a strict one. It was lowered to **0.10**, justified by the arithmetic above and documented as such in `constants.py`. It was explicitly **not** tuned to sit just under the observed 0.28.

A deeper version of this is worth thinking about before Phase 2: a pseudo-event at day `d` draws from `[d-20, d+h]`, and an anchor's plausible influence spans `[a, a+25]`, so true contamination is **asymmetric** (roughly `a-20 ≤ d ≤ a+45`, width ~66) and **exceeds the 63-day quarterly spacing**. Strictly interpreted, per-peer anchor-free baseline estimation may be infeasible for quarterly anchors, and a cross-sectional baseline (pooling peers whose anchors are quiet in that window) may be the right design. This is a genuine methodological question for the status doc, not a code bug.

### 6b. `min_bucket_count` = 3 against a threshold of 20 — currently failing

A second reliability condition was added (`MIN_BASELINE_OBS_PER_BUCKET = 20`) because retention alone can be cleared while a days-to-own-earnings bucket is nearly empty, in which case `predict()` silently falls back to the global mean and stops residualizing the part of the earnings cycle it exists to remove.

On `CONSTANT_VOL_no_ramp`, **60 of 72 peers are flagged unreliable**, driven by this new condition (min bucket count 3). Diagnosis: the `_dte_bucket` boundaries (`≤2`, `3–5`, `6–10`, `11–21`, `>21`) put ~17% of the calendar into the three narrow near-earnings buckets, and 28% retention leaves those thin.

**This is an unresolved design question, not a bug.** Options: widen the buckets, lower the per-bucket minimum, or accept and report. Whichever is chosen must be justified structurally and recorded, not selected because it makes Phase 0 pass.

### 6c. h = 1–2 are statistically pathological even after the fix

`log(RVar(1)) = log(r₁²)` is the log of a χ²₁ — extreme left tail, huge variance. Observed mean target at h=1 swings from −0.527 (small N) to +0.059 (large N) purely from sampling.

This does **not** bias `β_h`: local projections run a separate regression per horizon, each with its own intercept, so a constant level shift at horizon h is absorbed. But h=1–2 estimates will be very noisy and should carry that caveat in reporting. The grid stays 1…20 per Patch 3 — this is a reporting caveat, not a spec change.

---

## 7. What remains

Build sequence per v6 (**do not skip ahead** — 3b depends on code step 3 builds):

- [x] **Step 1** — synthetic-fixture generator
- [~] **Step 2** — target + residualization **done**; **data-availability audit NOT started**
- [ ] **Step 3** — inference layer
- [ ] **Step 3b** — diagnostic run, finalize N_eff gate
- [ ] **Step 4** — Stage 2 rules engine
- [ ] **Step 5** — smoke test, Colab notebook, VS Code scaffolding, status doc

### Step 2 remainder — options-coverage audit
Per Patch 8: cache all provider responses locally, enforce a **stated maximum API call budget** per run, and **fail loudly** (never silently truncate the universe) if the budget is hit. Default budget is already in `constants.py` (`DEFAULT_AUDIT_CALL_BUDGET = 500`). This is the one Phase 0 step that spends money and can rate-limit — it makes **real calls to the HYP-01 options provider**. Confirm with the user before the first live run.

Default target is **realized volatility** (100% universe coverage). IV is promoted to secondary/robustness **only** for peers with confirmed clean coverage, and the coverage % must be **reported before that call is made** — do not decide first and check second.

### Step 3 — inference layer
- **Local projections**, h = 1…20, residualized target on shock magnitude + controls
- **One-way (anchor-event) clustered SEs** + Satterthwaite dof — copy CR2 math per §3b above, with provenance comment; flag two-way as a stated limitation
- **max-T permutation multiplicity correction** across the grid (not Bonferroni — RVar(h) is an expanding-window mean, so adjacent β_h are correlated by construction and Bonferroni is badly over-conservative). Build it **once** here; step 3b reuses it.
- **Prewhitened CCF cross-check** — filter fit to the **peer-vol series** (never the anchor shock series, which is a sparse quarterly point process already near white noise), **same single filter applied to both series**, **no double-prewhitening fork**. Significance from **circular-shift permutation of anchor event dates**, never Bartlett bands.
- Ridge/lasso Link-Strength model (not tree-based/deep). No sklearn installed — ridge is closed-form in numpy; prefer that over adding a heavy dependency the repo doesn't otherwise use.
- Leave-one-anchor-out CV; placebo test per `GST_Task1_PlaceboPermutationTest.py`'s pattern.

### Step 3b — N_eff gate
```
DEFF  = 1 + (m̄ − 1) · ICC        # ICC floored at 0 before this (constants.ICC_FLOOR)
N_eff = N_pairs / DEFF
```
Gate on `N_eff` against the **fixture-derived** multiplicity target from 3b's permutation run. `190–240` is a **provisional pre-3b placeholder only** — state it as such and supersede it. The naive single-test **126** appears **only** as a labelled baseline, never as the operative gate. Report `N_pairs`, `N_events`, raw ICC (+ cluster count, bootstrap interval if feasible), DEFF, `N_eff`, Satterthwaite dof, implied calendar coverage.

### Step 4 — Stage 2
Rules table / small constrained optimization, **never a trained model**. Protects an **assumed existing long-equity holding in the peer name** (Patch 5) — encode that assumption visibly in code and docstrings. `ASSUMED_PEER_EQUITY_NOTIONAL_USD` is already in `constants.py`.

### Tests still to write
Beyond the h-trend regression test (§5) and the two split negative-control fixtures (Fixture A **passes** the gate, Fixture B **fails** it): residualization-leakage, LP recovers the known injected lag, SEs genuinely clustered, multiplicity correction actually moves the threshold, Satterthwaite dof computed, CCF filter fit to peer-vol and **verifiably not** to anchor-shock, LOOCV split correctness, placebo correctness, Stage 2 edge cases.

---

## 8. Non-negotiables (from v6, restated so they cannot drift)

- No real-capital or live-trading logic anywhere.
- **No claim, anywhere, that a hedging edge has been found.**
- Placeholder linkage (same-sector peers) labelled clearly everywhere; same limitation as `GST_Task2_PeerDivergence.py`.
- Do not silently swap linkage source, model family, lag-detection method, prewhitening target, RV/RVar estimator, or N-gate formulation.
- **Quantum autocorrelation function**: use that exact term, never "quantum-inspired". Isolated, non-load-bearing, feeds no decision. **Skip it and say so** if there is no well-defined citable construction for applying the physics construct to classical return series (there almost certainly isn't). **It is explicitly out of scope for "done"** — do not list it in any Definition of Done, even as "(if built)".
- Phase 0 only. Do not implement Phases 1–4.

---

## 9. Process note carried forward

`HYP04_PLAN_ROUND2_EDITS.md` currently **overrides** the plan doc. That is fine for a build, but a Phase 2 lock referencing two mutually-amending documents is precisely the drift risk this project's tamper tests exist to catch. **Before Phase 2**, merge the patches into a plan v0.2 and demote the edits doc to a dated amendment record.

Separately, `CLAUDE_CODE_BUILD_PROMPT_HYP02_1.md` at the repo root is an **older, unrelated** file that predates this work. It was left untouched and should not be used.
