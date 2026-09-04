# HYP-04 — the code was not clustering where the lock says, and two things depended on that

**Date:** 2026-09-03
**Status:** measured. Records a preregistration divergence, its repair, and two
consequences the repair exposed. **Adopts nothing on its own** and resolves no
open decision.

---

## 1. The divergence

`GST_HYP04_ANALYSIS_LOCK_v1.0.md` is **SIGNED 2026-08-20, IN FORCE**. **D1**:

> **One-way, clustered on `calendar_period`.**
> Not `event_id` (the Phase 0 default) and not `anchor`.

The code clustered on `event_id` in three places:

| Site | What it did |
|---|---|
| `inference.py:149` | `fit_local_projections(cluster_key="event_id")` as the default |
| `inference.py:199` | `_max_abs_t_for_shuffle` **hardcoded** `event_id`; `cluster_key` could not reach it |
| `gate.py:208` | `evaluate_gate` read `table["event_id"]` for ICC, DEFF and `N_eff` |

`local_projection_analysis` — the entry point everything else calls — accepted
no `cluster_key` at all, so every caller silently got `event_id` however the fit
beneath it was configured. The permutation null was therefore clustered on a
different dimension from the statistic it was calibrating.

**Why the direction matters.** One-way clustering on too fine a dimension
**understates** standard errors. An understated SE is anticonservative for
rejecting a null *and* for declaring an equivalence — there is no reading under
which the `event_id` default was the safe one. D2 records the lock's own
measurement of the price it accepted: **8 clusters, Satterthwaite df ≈ 5.7**,
against **24.5** under `event_id`.

## 2. What was repaired

`LOCKED_CLUSTER_KEY = "calendar_period"` now lives in `constants.py` and is the
default for `fit_local_projections`, `local_projection_analysis`,
`max_t_permutation` and `evaluate_gate`. `local_projection_analysis` accepts and
**forwards** it to both the fit and the null.

**The permutation is now shape-aware.** Shocks are permuted across anchor events
*of the same `calendar_period`*, never freely. Permuting across periods
decouples shock from period and strips period-level confounding out of the null
while leaving it in the observed statistic — a null narrower than the truth.
That is precisely the error the function's own docstring already guarded against
one level up, on the peer dimension. An event's cluster is **verified constant
within the event** rather than assumed by taking a silent first value.

The mode follows the cluster shape, and is reported rather than left for the
reader to infer:

| cluster shape | permutation | why |
|---|---|---|
| clusters hold many events (`calendar_period`: 14 groups, 224 movable) | **restricted within cluster** | the clustering asserts dependence inside a cluster, so it must survive under the null |
| every cluster is one event (`event_id`: 224 groups, 0 movable) | **unrestricted** | no within-cluster structure exists to preserve, and the clustering asserts independence across clusters |

The unrestricted branch is the correct null for `event_id`, not a fallback — it
keeps the sensitivity fit runnable rather than refusing it.

**Operational cost, recorded because it is large.** Under `calendar_period` the
CR2 adjustment does ~14 eigendecompositions of ~130×130 rather than ~224 of
6×6. Measured: **20 permutations in 6.3 s**, so the production default of 2,000
is roughly **10 minutes per analysis**. Not prohibitive, but it makes any
simulation study over this estimator a design problem rather than a loop.

## 3. Consequence one — `peak_horizon` was only reliable under the violation

`peak_horizon` is computed as `argmax |t|`. Measured across 15 (lag, window)
combinations on synthetic fixtures with a known injected truth, peak expected at
`L + W − 1`:

| clustering | `argmax abs(beta)` | `argmax abs(t)` = `peak_horizon` |
|---|---|---|
| `event_id` (forbidden by D1) | 15 / 15 | **15 / 15** |
| `calendar_period` (**D1**) | **15 / 15** | **9 / 15** |

Worst miss: injected peak at horizon 6, reported at **15**.

`argmax abs(beta)` recovers the injected horizon **perfectly under both**
dimensions — as a location estimate must, since clustering changes only the
variance estimate and never the point estimate. `peak_horizon` looked robust
only because the code was clustering on the dimension the lock forbids.

**What this does and does not touch.** **D8** is explicit that `peak_horizon`
"never reaches tenor sizing" — Stage 2 sizes off `onset − 2`. So **no decision
input moved.** The locked reported quantity is `onset_horizon`, and its two
invariants (`onset >= L`, and `L <= onset <= L+2`) **both still hold** under D1.
What degrades is D8's secondary use: *"combined with onset it gives the window
width W."* Under D1, `peak_horizon` does not reliably give W.

**This is left open, not fixed.** Redefining `peak_horizon` as `argmax abs(beta)`
is a methodology change to a reported quantity and belongs to the repo owner,
not to whichever choice makes a test pass. The evidence is recorded here so the
decision is made on measurement rather than on convenience.

## 4. Consequence two — the assumed effect size holds only at the forbidden df

`required_n_for_k_tests` solves for N given Cohen's d under a **normal**
approximation. Its exact algebraic inverse (`mde_cohens_d`, added, round-trip
exact to machine precision for every (N, k) tested) answers the question a fixed
sample actually poses. At the registered floor:

```
N = 193, k_eff = 5.6, power = 0.80
  normal approximation                     MDE d = 0.497   ( = ASSUMED_COHENS_D )
```

But the normal approximation is only accurate at large df, and under D1 the df
are single-digit. Redone with the **noncentral t** (`mde_cohens_d_nct`):

| Satterthwaite df | t critical | z used instead | **MDE d** | |
|---|---|---|---|---|
| **5.7** | 3.871 | 2.608 | **0.714** | **D2, at the gate threshold** |
| 13.3 | 3.049 | 2.608 | 0.571 | measured, main fixture |
| 24.5 | 2.832 | 2.608 | 0.534 | `event_id` — forbidden by D1 |
| 124.4 | 2.649 | 2.608 | 0.503 | `event_id`, main fixture |

**At the df D1 actually produces, the design detects d ≈ 0.71, not the assumed
0.5 — an effect roughly 43% larger.** And `ASSUMED_COHENS_D = 0.5` is recovered
almost exactly only at the inflated df the **forbidden** clustering produces.
The 193 floor was calibrated against a dimension the lock rules out.

**Outcome-free by construction, which is what makes it permitted.** The inputs
are N, alpha, the effective test count, the power target and the df. No target
value, no residual, no fitted coefficient. `satterthwaite_df(X, g, c)` takes the
design matrix and cluster labels and **no `y`**; the CR2 adjustment matrices are
`y`-free too. This is the design-only sensitivity that
`GST_HYP01_STATISTICAL_METHOD_REVIEW_PACKET_v1.0_DRAFT.md` §11 lists as
permitted, and it is not the project-derived power calculation the display-gate
document forbids.

**The 193 floor is NOT moved here.** `required_n_for_k_tests` is untouched —
it produces the number gate condition C2 reads, and changing it is a dated
amendment, not a refactor. Both numbers are reported, labelled.

## 5. What is NOT settled

**The `N_eff` question is still open, and the fixtures cannot close it.**
Measured on a 195-event zero-effect panel:

| clustering | clusters | m̄ | DEFF | `N_eff` |
|---|---|---|---|---|
| `event_id` | 195 | 5.29 | 1.000 | 1031.0 |
| `calendar_period` | 15 | 68.73 | 1.066 | 967.5 |

DEFF barely moves — **but only because `make_panel` assigns `calendar_period` as
a bare quarter index and models no market-wide period factor.** The period-level
ICC is therefore near zero *by construction*, and this measurement is a smoke
test of the plumbing, not evidence about real data. Real peer volatility is
correlated within a quarter. `DEFF = 1 + (m̄ − 1)·ICC` with m̄ ≈ 69 means an ICC
of only 0.05 would give DEFF ≈ 4.4. **What D1 costs `N_eff` cannot be known
until Phase 1 has real peers**, and it is now measurable the moment it does.

Also open: the **anchor-recurrence** dimension remains uncovered by any one-way
clustering, per D2's standing limitation. Two-way CR2 is **not** built and
should not be: D1 already chose one-way, the intersection of anchor event and
calendar period is a single cluster spanning the panel, and no external
reference implementation of multiway CR2 exists to validate against
(`clubSandwich` is one-way; `sandwich::vcovCL` is multiway but CR0/CR1, which D4
excludes).

## 6. What this does not do

No target value, no `beta_h`, no peer response, no horizon and no direction has
been computed from real data. Everything above is either a property of the
**design** or a measurement on **synthetic fixtures with a known injected
truth**. The display gate is **CLOSED**, C4 MET, four denials, eligible event
count **zero**, and nothing here moves any of that.

---

*Nothing in this document is evidence about supply-chain transmission. No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.*

*Nothing in this document constitutes investment advice, a solicitation, or a
representation that any approach is profitable.*
