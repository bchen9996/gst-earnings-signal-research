# HYP-01 Authorizer Decision Matrix v1.0 (DRAFT)

> **Nothing here is decided. Every checkbox is blank and every authorizer field is `PENDING`.**
> This document presents choices. It does not make them, and merging it approves nothing.
>
> `GST_HYP01_ANALYSIS_LOCK_v1.0` remains operative. The proposed v1.1 remains `PROPOSED_PENDING_HUMAN_AND_METHODOLOGIST_APPROVAL`. **F5 remains OPEN.** No dated amendment is created by this document.

**Authorizer:** `PENDING`  ·  **Decision date:** `PENDING`  ·  **Signature / confirmation:** `PENDING`

Evidence base: [`GST_HYP01_SYNTHETIC_VALIDATION_REPORT_v1.0_DRAFT.md`](GST_HYP01_SYNTHETIC_VALIDATION_REPORT_v1.0_DRAFT.md) · [`GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json`](GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json) · the merged [review packet](GST_HYP01_STATISTICAL_METHOD_REVIEW_PACKET_v1.0_DRAFT.md).

**A note on how to read the "recommended" column.** A recommendation is offered only where the offline evidence actually supports one. Several rows deliberately carry **no recommendation**, because the evidence does not reach that far. Those blanks are findings, not omissions.

---

## The constraint that shapes several of these decisions

**CR2 + Satterthwaite — the merged packet's provisional recommendation — is not executable in the currently tested environment.** No R runtime is present there, so `clubSandwich` cannot be reached; `wildboottest` and `linearmodels` are absent too. An independently maintained reference runtime must be added and pinned before CR2 can be validated. Only **CR1** has an implementation-validated path today.

**This is a dependency problem, not evidence that CR1 is the better method.** At the corrected simulation precision (5,000 replications per null cell), CR1's 95% Wilson interval lies entirely above 0.05 in **all four null cells tested** — so over-rejection is established for CR1 itself. The CR2 columns are **`UNVALIDATED ENGINEERING OUTPUT — NOT METHOD-COMPARISON EVIDENCE`** and cannot be used to argue any method is better. Choosing CR1 because it is the only thing that runs here would be choosing on convenience.

---

## D1 — Primary covariance estimator (gap-audit C6)

**Decision:** which cluster-robust covariance estimator is primary for `beta_gst`?

| Option | Implementation status | Consequence if chosen |
|---|---|---|
| **A. CR1** | **Validated** against statsmodels 0.14.6 (implementation agreement, not statistical endorsement) | Runnable today with no new dependency. At 5,000 replications per cell its Wilson interval lies entirely above 0.05 in all four null cells (0.0796, 0.1180, 0.0854, 0.0912) — over-rejection, in the direction that inflates apparent significance |
| **B. CR2 / BRL** | **Blocked** — no independent reference installed in the tested environment | Favoured in the published literature. Its behaviour in this study's grid is **unvalidated engineering output and is not method-comparison evidence**. Cannot be validated until an independently maintained reference runtime is added and pinned. Collection cannot honestly begin before that |
| **C. CR3 / jackknife** | **Blocked** — same reason | Comparable published performance to CR2 with a simpler `t(G−1)` rule; same dependency gap |

**Recommended:** *none offered.* The methodologically preferred options are exactly the ones that are blocked. This is the authorizer's call, and it is really a call about whether to acquire the dependency.

- [ ] A — CR1
- [ ] B — CR2 / BRL
- [ ] C — CR3
- [ ] Other: ______________

**If left unresolved:** the primary estimator is undefined and the study cannot claim to be preregistered.

## D2 — Finite-sample correction (gap-audit C7, part 1)

| Option | Status | Consequence |
|---|---|---|
| A. `c = [G/(G−1)]·[(n−1)/(n−k)]` (CR1 scaling) | Validated | Standard, familiar, insufficient on its own at this cluster count |
| B. BRL transform built into CR2 | Blocked | Exactly unbiased under a homoskedastic-independent working model |
| C. Jackknife transform (CR3) | Blocked | Tends conservative |

**Recommended:** *none offered* — follows D1.

- [ ] A  - [ ] B  - [ ] C  - [ ] Other: ______________

**If unresolved:** the `finite_sample_correction: true` flag in v1.0 stays a boolean with no procedure attached.

## D3 — Degrees-of-freedom rule (gap-audit C7, part 2)

| Option | Status | Consequence |
|---|---|---|
| A. `t(G−1)` | Validated | Simple, reproducible. In this repository, read `results.df_resid_inference`, **not** `results.df_resid` |
| B. Satterthwaite / Bell–McCaffrey ν | Blocked | Design-dependent. The study grid put ν at 7.248 for 24 unbalanced clusters, but that figure is **unvalidated engineering output, not method-comparison evidence** |

**Recommended:** if D1 selects CR2, then **B**; if D1 selects CR1 or CR3, then **A**. The pairing matters more than either alone.

- [ ] A  - [ ] B  - [ ] Other: ______________

## D4 — Wild bootstrap: primary or sensitivity?

| Option | Status | Consequence |
|---|---|---|
| A. Labelled sensitivity only, barred from overturning the primary | Blocked | Matches the merged packet's proposal; adds corroboration without method-shopping |
| B. Primary inference | Blocked | Published evidence does not show it dominating CR2 + Satterthwaite at small G |
| C. Not used at all | — | Removes a stochastic dependency and a seed-management burden |

**Recommended: A**, on the merged packet's evidence — but note it is **blocked**, so choosing A also incurs the dependency in D11.

- [ ] A  - [ ] B  - [ ] C

## D5 — Bootstrap weight distribution

| Option | Status | Consequence |
|---|---|---|
| A. Rademacher 2-point | Implemented, unvalidated | Only 2^G distinct draws — degenerate at very small G |
| B. Webb 6-point | Implemented, unvalidated | Preferred at very small G in the literature |

**Recommended:** *none offered* — conditional on D4 and on the realized cluster count.

- [ ] A  - [ ] B  - [ ] Not applicable (D4 = C)

## D6 — Bootstrap repetitions · D7 — Random seed

**D6.** 999 was used in this study. Production value: `PENDING`. Fewer repetitions coarsens the attainable p-value grid; more costs only compute.

- [ ] 999  - [ ] 9,999  - [ ] Other: ______  - [ ] Not applicable

**D7.** A fixed seed **must** be recorded, or the procedure is not reproducible. Verified here by recomputation: the same seed reproduces the identical bootstrap draw vector, and a different seed changes it. The test compares a digest of the draw vector rather than the p-value, because the p-value lies on a coarse 1/(B+1) grid where two seeds may legitimately collide.

- [ ] Fixed seed recorded at the event-60 freeze  - [ ] Fixed seed declared now: ______  - [ ] Not applicable

## D8 — Singleton clusters

**No rule exists.** The synthetic fixtures ran with singletons present, but CR2's `A_g` and CR3's `(I − H_gg)^{−1}` degenerate as `I − H_gg` approaches singularity.

| Option | Consequence |
|---|---|
| A. Retain singletons unchanged | Simple; degeneracy risk under CR2/CR3 |
| B. Retain but flag and report the count | Transparent; still needs a numerical guard |
| C. Predeclared merge or exclusion rule | Changes the effective sample — needs its own justification |

**Recommended: B** as a minimum. Silent retention is the one option with no defence.

- [ ] A  - [ ] B  - [ ] C  - [ ] Other: ______________

## D9 — Rank deficiency, missing values, degenerate fit

**This study found five conditions where an implementation would otherwise emit a meaningless number**, each now refused by a distinct prespecified rule: ill-conditioning, exact rank deficiency, zero-variance predictor, degenerate fit and non-finite values.

On the perfect-fit fixture both implementations became numerically unstable near the floating-point noise floor and disagreed materially on the derived statistic. No correctness verdict is asserted for either. The runner now refuses this configuration by a prespecified relative-residual-variance threshold rather than by noticing a disagreement.

| Option | Consequence |
|---|---|
| A. **Refuse and abort** on rank deficiency, ill-conditioning, zero variance, any missing value, and residual variance below a declared floor | Fails loudly. The runner already implements exactly this, with five distinct prespecified reasons |
| B. Refuse on rank deficiency and missing values only | Leaves the degenerate-fit case reporting a meaningless statistic |
| C. No rule | An implementation may silently report a number that is not identified |

**Recommended: A.** This is the one row where the offline evidence is decisive.

- [ ] A  - [ ] B  - [ ] C
- Residual-variance floor, if A: `PENDING` (the runner's study default is relative RSS < 1e-18; adopting it is the authorizer's call)

## D10 — Cluster-count / effective-df warning policy (gap-audit NEW-1)

**No threshold is proposed, and the synthetic grid does not support one.** It shows effective df below the nominal cluster count — 11.42 balanced and 7.248 unbalanced at 24 clusters — but those figures come from **unvalidated CR2/Satterthwaite code**, and a rejection floor is in any case a judgement about evidential sufficiency, not a number a grid can produce.

| Option | Consequence |
|---|---|
| A. Report realized ν and `G*` alongside every result, no threshold | Transparent; leaves interpretation to the reader |
| B. Report, plus a declared floor below which no confirmatory conclusion is drawn | Stronger; the floor must be justified externally |
| C. No reporting | Hides the weakest part of the design |

**Recommended: A or B, never C.** Choosing between them requires a methodologist.

- [ ] A  - [ ] B (floor: ______)  - [ ] C
- **Threshold remains `PLACEHOLDER_PENDING_METHODOLOGIST` unless B is selected and justified.**

## D11 — Implementation language, package and version

| Option | Consequence |
|---|---|
| A. Python + statsmodels 0.14.6 only | Runs today. **Restricts D1 to CR1** — statsmodels provides no CR2, CR3, Satterthwaite or wild bootstrap |
| B. Add an R runtime + `clubSandwich` | Unblocks CR2, CR3 and Satterthwaite and supplies the independent reference needed to validate them |
| C. Add `fwildclusterboot` (R) or `wildboottest` (Python) | Unblocks the wild bootstrap |
| D. Implement in Python and validate against an acquired reference | Most work; keeps a single runtime |

**Recommended:** *none offered* — this is a resourcing decision. **But note the dependency: selecting CR2, CR3 or the wild bootstrap in D1/D4 without also selecting B, C or D leaves the chosen method unvalidated, and collection must not begin in that state.**

- [ ] A  - [ ] B  - [ ] C  - [ ] D  - [ ] Other: ______________

## D12 — Sector fixed-effect encoding (gap-audit C9) · D13 — Sparse sectors · D14 — Per-ticker cap

**D12** — secondary adjusted model only; **the `gst_zscore` estimate and standard error are identical under either coding.**

- [ ] Treatment (reference) coding  - [ ] Sum (effects) coding  - [ ] Other: ______________

**D13** — rule for sectors contributing too few eligible events. Not investigated by this study.

- [ ] Pool below a declared count: ______  - [ ] Drop the sector from the secondary model  - [ ] Other: ______________

**D14** — per-ticker cap on eligible events. **Warning: this changes the *sample definition*, a currently locked element, and needs its own dated amendment beyond the statistical rule.**

- [ ] No cap  - [ ] Cap at: ______  - [ ] Defer

## D15 — Multiplicity treatment (gap-audit E3)

| Option | Consequence |
|---|---|
| A. No adjustment for the single primary confirmatory test | One hypothesis, one predictor, one outcome, one test, all fixed pre-data |
| B. Adjust across the HYP-01 / HYP-02 / HYP-03 families | More conservative; requires defining the family |

**Recommended: A**, per the merged packet — but it must be **decided**, not assumed by silence.

- [ ] A  - [ ] B (method: ______)  - [ ] Other: ______________

## D16 — A9 hypothetical design-sensitivity policy

The grid in this study is **hypothetical engineering output**. It used generic standardized effects chosen before simulation and **no repository effect estimate, because none exists**.

| Option | Consequence |
|---|---|
| A. None; keep n = 60 as a governance floor and say so | Honest; already consistent with the registry |
| B. Publish a minimum-detectable-effect curve from this synthetic grid, labelled hypothetical | Informative; must never be read as expected GST power |
| C. Externally-anchored power analysis using published literature effect sizes | Strongest; requires citable external effects |

**Recommended: A or B.** Under no option may an effect size from this project's retrospective reconstruction or any prospective outcome be used, and `n = 60` may not be silently revised.

- [ ] A  - [ ] B  - [ ] C  - [ ] Other: ______________

---

## Summary — every decision still open

| ID | Decision | Recommendation offered? |
|---|---|---|
| D1 | Primary covariance estimator | No — preferred options are blocked |
| D2 | Finite-sample correction | No — follows D1 |
| D3 | Degrees-of-freedom rule | Conditional on D1 |
| D4 | Wild bootstrap role | Yes — sensitivity only |
| D5 | Bootstrap weights | No |
| D6 | Bootstrap repetitions | No |
| D7 | Random seed | Must be recorded |
| D8 | Singleton clusters | Yes — flag and report, at minimum |
| D9 | Rank deficiency / missing / degenerate fit | **Yes — refuse and abort** |
| D10 | Cluster-count warning policy | Report always; threshold still `PLACEHOLDER_PENDING_METHODOLOGIST` |
| D11 | Implementation language and package | No — resourcing decision |
| D12 | Sector encoding | No |
| D13 | Sparse sectors | No |
| D14 | Per-ticker cap | No — changes the locked sample definition |
| D15 | Multiplicity | Yes — no adjustment for the single primary test |
| D16 | Design-sensitivity policy | A or B, never using project effects |

**Sixteen decisions. Zero made.**

## What must happen after these decisions

1. The authorizer records each decision above, with a date.
2. Any method selected but currently **blocked** is validated against an independently maintained reference **before** collection begins.
3. A **separate dated lock amendment** encodes the approved rule. **This document is not that amendment and does not become one by being merged.**
4. All of it completes **before the first HYP-01-eligible prospective pre-event capture**.

**Authorizer signature:** `PENDING`  ·  **Date:** `PENDING`
