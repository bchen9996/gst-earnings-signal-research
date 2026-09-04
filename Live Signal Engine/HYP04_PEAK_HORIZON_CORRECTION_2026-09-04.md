# HYP-04 — `peak_horizon` now matches the plan that always defined it

**Date:** 2026-09-04
**Status:** correction, applied. Records a code/plan divergence and its repair.
**Adopts nothing new** and resolves no open decision.

---

## 1. This is a correction, not a methodology change

`HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md` §3.5 has always defined the
peak on the coefficient, not the t-ratio:

> Because the target is an expanding-window mean from day 1 to day h, its value
> rises monotonically through a rectangular elevated-response block
> `[L, L+W−1]` … So **`argmax_h β_h`** lands at **h = L+W−1, the end of the
> reaction window**, not at h = L, the onset.

`HYP04_PLAN_ROUND2_EDITS.md` says the same twice — *"`peak_horizon`
(argmax β_h)"*. The code computed `argmax_h |t_h|`. **The code was the
divergence.**

The signed lock's **D8** constrains only what the quantity is *used for* —
"never reaches tenor sizing", and "combined with onset it gives the window
width W" — and **defines no estimator**. Nothing signed is altered here.

## 2. Why it surfaced now

The D1 clustering fix ([HYP04_D1_CLUSTERING_FINDING_2026-09-03.md](HYP04_D1_CLUSTERING_FINDING_2026-09-03.md))
moved standard errors onto `calendar_period`, as the lock requires. Measured
across 15 injected (lag, window) combinations:

| clustering | `argmax│β│` | `argmax│t│` (what the code used) |
|---|---|---|
| `event_id` (forbidden by D1) | 15 / 15 | 15 / 15 |
| `calendar_period` (**D1**) | **15 / 15** | **9 / 15** |

Worst miss: injected peak at horizon 6, reported at 15.

`argmax|β|` is invariant across both dimensions, as a **location** estimate must
be — clustering changes the variance estimate and never the point estimate.
`argmax|t|` only looked correct while the code clustered on the dimension the
lock forbids.

## 3. The hazard the fix had to avoid

`peak_abs_t` was passed to `max_t_permutation` as `observed_max_abs_t`, which
sets `peak_significant`, which gates `onset_horizon`, which Stage 2 reads
(`R3_no_onset_horizon` → `NO_POSITION`).

The permutation null is the distribution of **max over horizons** of |t|. Had
`peak_abs_t` simply been repointed at the β-peak it would no longer be that
maximum. The test would have stayed FWER-valid — comparing a non-maximum to a
max-null is conservative — but it would have been mis-calibrated, mislabelled,
and could have reported **`onset_horizon = None` while a horizon genuinely
cleared the threshold**.

**Resolved by separating the two quantities rather than repurposing one:**

```
max_abs_t     = max_h |t_h|            the max-T test statistic
peak_horizon  = argmax_h |beta_h|      where the response peaks (plan §3.5)
peak_abs_t    = |t| at that horizon    reported alongside the location
```

`max_abs_t` receives exactly the value `peak_abs_t` used to hold and feeds
`observed_max_abs_t` unchanged, so **significance behaviour is bit-identical to
before this change.** Only the reported peak location moved. That is the reason
for the field split.

## 4. What changed, and what did not

**Changed:** `inference.py` (the assignment block, the new `max_abs_t` field,
the module and class docstrings), `stage2.py` and `README.md` docstrings that
restated `argmax|t_h|`, and the inference suite — `3c` is asserted **exactly**
again (it had been narrowed on 2026-09-03 only while the definition was an open
question), and `4c` now compares `max_abs_t` to the critical value, so it tests
the max-vs-critical claim its own label makes.

**Not changed:** Stage 2 reads `peak_horizon` exactly once, into the disclosure
field `peak_horizon_not_used_for_tenor`. It reaches no branch and no number.
D8 holds as written.

## 5. Recorded, not fixed here

`stage2._tenor_from_onset` returns `onset + 5`. **D8 says tenor is sized off the
interval's lower bound, `onset − 2`.** This is a pre-existing code/lock
divergence, orthogonal to this change and living in the same function. Unlike
`peak_horizon`, this one **is** a decision input, so it is flagged for a
separate decision rather than folded into a correction it has nothing to do
with.

---

*Nothing in this document is evidence about supply-chain transmission. No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed. The gate is
CLOSED, C4 MET, four denials, eligible event count zero.*
