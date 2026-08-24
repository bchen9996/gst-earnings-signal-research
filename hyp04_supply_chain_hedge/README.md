# `hyp04_supply_chain_hedge/` — HYP-04 Phase 0

**Phase 0 feasibility only. Placeholder linkage. No real-capital logic. No hedging edge is claimed anywhere.**

## What this is

The Phase 0 build of the HYP-04 Supply-Chain Hedge-Lag Model: given a confirmed anchor earnings shock, does a peer's volatility move, how many trading days does the reaction take to show up, and — separately, by rules rather than by a fitted model — what protective structure would that imply.

Phase 0 answers only *can this be computed at all, and is the sample large enough to be worth continuing*. It produces no finding.

### Placeholder linkage

Peers are assigned to anchors by **list position** — `peers[i*k:(i+1)*k]` in `fixtures.py`. The sector column is never read for pairing, so the placeholder is **positional-synthetic**, which is weaker than same-sector.

*(This paragraph previously said "same-sector tickers". That wording described `GST_Task2_PeerDivergence.py`'s approach, not this package's; the correction was made in `__init__.py` on 2026-08-18 and missed here until 2026-08-22.)*

Hand curation of a real map began 2026-08-22, so the map is no longer empty — but it is nowhere near sufficient, **no analysis path in this package runs on curated data**, and Phase 1 remains blocked. **No output from this package is evidence about supply-chain transmission.**

## Authoritative documents

Read these before changing anything here:

1. `Live Signal Engine/HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md` — **the plan.** Self-contained and authoritative on its own as of 2026-08-19. Read this one.
2. `Live Signal Engine/CLAUDE_CODE_BUILD_PROMPT_HYP04_v8.md`
3. `Live Signal Engine/HYP04_OPERATOR_RUNBOOK_2026-08-23.md` — **how the
   modules compose**, end to end: resolving a response session, computing which
   closes to collect, loading them, resolving pairs, and computing a target.
   Read it before touching any of that path. It also states plainly what
   completing every step does *not* give you, which is a finding.

Superseded, retained as historical records — **do not implement from either**: `HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.1_DRAFT.md` and `HYP04_PLAN_ROUND2_EDITS.md`. Their 16 patches are merged into v0.2, whose §0 maps each patch to where it landed. The old "read both and apply the marker convention" rule is retired: v0.2 needs no companion doc.

## Setup

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python.exe -m pip install -r requirements-hyp04.txt
```

The package is not installed, so `PYTHONPATH` must point at the repo root:

```bash
PYTHONPATH=. python -m hyp04_supply_chain_hedge.fixtures
```

`yfinance` is **not** in `requirements-hyp04.txt` on purpose. It is needed only by the live audit runners, which make real provider calls. Install it separately when running an authorized audit.

## Tests

This repository uses **no pytest**. Every test file is a hand-rolled `check()`/`skip()` harness run directly, matching `test_market_response_*.py`. Skips are reported separately and never counted as passes.

```bash
PYTHONPATH=. python test_hyp04_supply_chain_hedge_target.py
```

```bash
PYTHONPATH=. python test_hyp04_supply_chain_hedge_inference.py
```

```bash
PYTHONPATH=. python test_hyp04_supply_chain_hedge_smoke.py
```

CI (`.github/workflows/hyp04-supply-chain-hedge-tests.yml`) globs `test_hyp04_supply_chain_hedge*.py` and runs each directly, failing loudly if discovery finds nothing.

## Modules

| Module | Role |
|---|---|
| `constants.py` | Every preregistered value, each traced to a numbered patch |
| `fixtures.py` | Synthetic panels with known injected lag/effect/cluster structure |
| `target.py` | `log(RVar(h)) − log(RVar_ref)` plus earnings-cycle residualization |
| `audit.py` | Options-coverage audit; refuses to run without an owner-supplied budget |
| `clustered_se.py` | CR2 covariance, Satterthwaite dof, ICC (**copied** from the HYP-01 bridge with provenance) |
| `inference.py` | Local projections, max-T permutation, prewhitened CCF, ridge, LOOCV, placebo |
| `gate.py` | `N_eff` sample-size gate |
| `stage2.py` | Hedge-structure decision table |
| `run_canary_audit.py` / `run_full_audit.py` | **Live runners. Real provider calls. Owner consent required.** |

## Things that are easy to get wrong here

Each of these was a real defect at some point in this build, and each is now pinned by a test.

**The target is a normalized log-variance ratio.** `RVar(h) = (1/h)·Σr²` — a mean, not a sum, and not square-rooted. The rejected `RV(h) = √(Σr²)` carries a deterministic `√h` trend with no volatility content: giving it 26× more data leaves its cross-horizon range unchanged (2.80 → 2.83 vol units), while the corrected definition's shrinks like 1/√N (0.065 → 0.015). `test_..._target.py::test_3` asserts that contrast, not an absolute tolerance, because a tolerance could be satisfied by tuning.

**Onset ≠ peak.** With an expanding-window target, `argmax|t_h|` lands on `L+W-1` — the **end** of the reaction window — while the first horizon clearing significance lands on `L`, the **onset**. Confirmed across six `(L, W)` combinations. **Stage 2 sizes tenor off the onset.** Using the peak buys `(W−1)` days too much tenor and arrives late. Onset detection is itself late-biased (the affected fraction at horizon `L` is only `1/L`), so it is reported with that caveat rather than as a point estimate.

**The prewhitening filter is fit to the peer-vol series, never the anchor shock.** Measured: AR(5) on peer-vol gives Σ|φ| = 1.093; on the anchor shock series, 0.048 — the shock series is already near-white, so filtering with it would be a no-op leaving the peer's vol clustering untouched. One filter, applied to both series; no double-prewhitening fork, because different filters break proportionality to the impulse-response weights and bias the lag.

**Significance is permutation-based, never Bartlett or Bonferroni.** Adjacent `β_h` are correlated by construction (expanding window), so Bonferroni is badly over-conservative; max-T permutation measures the real penalty. Measured effective independent tests: **6.34** of 20 horizons, implying a target N ≈ 195.

**The gate measures sample size, not effect size.** A zero-effect fixture with ample N must **pass** (a well-powered null is a legitimate result); an insufficient-N fixture must **fail** regardless of how large an effect is injected. Both directions are asserted.

**ICC is floored at 0 for `DEFF` only.** Negative ICC estimates are a real small-sample artifact; unfloored they push `DEFF` below 1 and make `N_eff` exceed `N_pairs`, which is backwards. The raw estimate is still reported.

**Under-populated buckets are excluded, not imputed** — and the buckets are not widened nor the threshold lowered to recover sample size (Patch 12). The excluded fraction is reported separately from the retained-history fraction; they measure different things.

## Stated limitations

- **One-way clustering only** (anchor event). Two-way (anchor × calendar period) is not implemented: no multiway CR2 exists in this repository, validated or otherwise. One-way understates SEs in the direction that makes marginal results look significant. See `clustered_se.TWO_WAY_LIMITATION_NOTE`.
- **h = 1–2 are statistically pathological** (`log(RVar(1)) = log(r₁²)`, a log-χ²₁). This does not bias `β_h` — each horizon has its own intercept — but those estimates are very noisy.
- **Retained history has a structural ceiling near 0.28** for quarterly anchors: excluding ±E sessions removes about `(2E+1)/63` of a peer's calendar. The threshold is set below that ceiling by arithmetic, not tuned.
- **The coverage audit measures current chains only.** yfinance has no historical endpoint, so 100% coverage does **not** establish that IV is viable as a Stage 1 target. Realized volatility remains the default.

## Live audit consent

`run_canary_audit.py` and `run_full_audit.py` make **real provider calls** and require the repo owner's staged go-ahead (Patch 13): a hard-capped canary batch first to establish observed cost-per-call, then a full-run cap extrapolated from those real numbers. `audit.py` refuses to make its first call without an owner-supplied budget — there is no default and no fallback.

Both stages were granted and executed on 2026-08-17: 27/27 placeholder-universe peers, 54 calls, 2 calls/ticker constant, 100% current-chain coverage, 0 transport failures, $0.00.
