# HYP-01 Inference Feasibility — Synthetic Validation Report v1.0 (DRAFT)

> **Synthetic data only. No method is approved. No dated amendment is created.**
> `GST_HYP01_ANALYSIS_LOCK_v1.0` remains the operative lock; the proposed v1.1 remains `PROPOSED_PENDING_HUMAN_AND_METHODOLOGIST_APPROVAL`, unchanged by this study. **F5 remains OPEN.**

**No repository observation, event, attention, price, return, outcome, panel, screening or market dataset was loaded.** No real ticker appears in any fixture — cluster labels are `CLUSTER_001`…`CLUSTER_0NN`. No network request was made and no package was installed. The runner installs a hard socket block before importing any numerical library.

Companion artifacts: [`GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json`](GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json) · [`GST_HYP01_AUTHORIZER_DECISION_MATRIX_v1.0_DRAFT.md`](GST_HYP01_AUTHORIZER_DECISION_MATRIX_v1.0_DRAFT.md)

---

## 1. The headline result

**Only one of the four candidate methods can be validated in this environment today.**

| Method | Executable here | Status |
|---|---|---|
| **CR1** — conventional cluster-robust + finite-sample correction | **Yes** | **`IMPLEMENTATION_VALIDATED`** |
| **CR2/BRL + Satterthwaite** | No | **`IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE`** |
| **CR3 / cluster jackknife** | No | **`IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE`** |
| **Restricted wild cluster bootstrap-t** | No | **`IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE`** |

The merged proposal names **CR2 + Satterthwaite** as its provisional recommendation. **That method cannot be validated in this repository as it stands.** This report does not treat that as a reason to prefer CR1; it is a dependency finding to put in front of the authorizer.

## 2. Why three methods are blocked

**There is no R runtime on this machine.** `R` and `Rscript` are not on `PATH`, and a filesystem search of the standard install locations found nothing. `clubSandwich`, `sandwich`, `lmtest` and `fwildclusterboot` are therefore **absent, not merely unconfigured**. On the Python side, `linearmodels`, `wildboottest` and `pyfixest` are all absent as well.

Working Python implementations of CR2, CR3, the Satterthwaite degrees of freedom and the restricted wild bootstrap were written for this study and run deterministically. **They are not validated, and are not labelled as such**, because the validation hierarchy requires agreement with an *independently maintained* implementation. Comparing code to itself proves only that it is self-consistent.

**Nothing was installed to close this gap.** The exact dependency and the exact validation procedure are recorded in the inventory so the authorizer can decide whether to acquire them.

## 3. What CR1 validation actually establishes

The hand-coded CR1 was compared against **statsmodels 0.14.6** — an independently maintained, already-installed implementation that was not written for this study.

**Tolerances were preregistered before any comparison was run and were not revised afterwards:**

| Quantity | rtol | atol |
|---|---|---|
| covariance matrix | 1e-10 | 1e-12 |
| standard error | 1e-10 | 1e-12 |
| t statistic | 1e-9 | 1e-11 |
| p value | 1e-9 | 1e-12 |
| inference degrees of freedom | exact integer equality | |

**Result: 11 of 14 fixtures matched on every quantity. 2 were skipped by design. 1 is a documented refusal case.**

### A correction made during the study

An initial pass reported a degrees-of-freedom mismatch on **every** fixture. That was a defect in the comparison, not in either implementation: **statsmodels keeps `results.df_resid = n − k` and exposes the inference degrees of freedom separately as `results.df_resid_inference = G − 1`**, which is what its p-values use. Reading the wrong attribute produced a spurious mismatch. The comparison target was corrected — **the preregistered tolerances were not touched** — and the mismatch disappeared. Any future implementation must read `df_resid_inference`.

## 4. Fixture matrix

| Fixture | Design | Outcome |
|---|---|---|
| `F01_balanced_24c_72n` | 24 balanced clusters, 72 obs | matched |
| `F02_unbalanced_24c_60n` | 24 highly unbalanced clusters, 60 obs | matched |
| `F03_several_singletons` | several singleton clusters | matched |
| `F04_one_dominant_cluster` | one dominant cluster | matched |
| `F05_near_collinear` | near-collinear regressors | **skipped — rank-deficient by design** |
| `F06_zero_variance_predictor` | zero-variance predictor | matched; both implementations return a non-finite statistic |
| `F07_perfect_fit` | perfect fit | **numerically unidentified — refusal case** |
| `F08_missing_value` | missing value present | **skipped — must be refused, not row-dropped** |
| `F09` / `F10` | permuted rows; relabelled clusters | invariance verified on every runnable fixture |
| `F11_sign_reversed` | negative hypothetical effect | matched |
| `F12_null_effect` | null-effect data | matched |
| `F13_positive_hypothetical` | positive hypothetical effect | matched |
| `F14_heavy_tailed` | heavy-tailed (t₃) errors | matched |
| `F15_cluster_heteroskedastic` | cluster-level heteroskedasticity | matched |
| `F16` / `F17` | same bootstrap seed; different bootstrap seed | same seed reproduces exactly; different seed differs |
| `F18_below_design_6c` | 6 clusters, below the anticipated design | matched (failure-behaviour probe only) |

Row-permutation and cluster-relabelling invariance held on **all 12 runnable fixtures**.

## 5. The refusal conditions this study found

These matter more than the validation result, because they are places a naive implementation would silently produce a number.

**Perfect or near-perfect fit is the sharp one.** On `F07`, the two implementations agreed on the covariance matrix to **2.6 × 10⁻³²** and on standard errors to **8.4 × 10⁻¹⁷** — and still reported t-statistics differing by a factor of about **1.7** (≈1.31 × 10¹⁶ versus ≈7.52 × 10¹⁵). With residual sum of squares at 3.7 × 10⁻²⁹, the standard errors sit at the floating-point noise floor, where a 10⁻¹⁶ absolute difference is a **75% relative** difference. The ratio β/se is not numerically identifiable. **Both implementations are correct; the statistic is meaningless.** A production implementation must refuse, not report.

**Missing values** must be refused rather than silently row-dropped — dropping rows would change the sample without any record of it, which the locked design forbids.

**Rank-deficient designs** are silently absorbed by a pseudo-inverse, which returns a generalised solution rather than failing. That must be detected and refused.

**Zero-variance predictors** produce a non-finite statistic in both implementations, consistently.

None of these has a rule in the operative lock or the proposed amendment. Each is a decision in the matrix.

## 6. Hypothetical design-sensitivity grid

> **HYPOTHETICAL ENGINEERING FIXTURE — NOT A GST POWER CLAIM.**
> Effects were chosen **before** simulation, are generic standardized effects on a synthetic predictor, and correspond to nothing measured in this project. **No repository effect estimate was used, and none exists.** These numbers must not be converted into a statement about expected GST power, and must not be used to invent a minimum-cluster threshold.

Rejection rates at nominal two-sided 5%, 300 replications per cell:

| Clusters | Shape | Hypothetical effect | CR1 + t(G−1) | CR2 + t(G−1) | CR2 + Satterthwaite | mean ν |
|---|---|---|---|---|---|---|
| 24 | balanced | 0.0 (null) | 0.090 | 0.087 | **0.073** | 11.5 |
| 24 | balanced | 0.2 | 0.263 | 0.233 | 0.203 | 11.4 |
| 24 | balanced | 0.5 | 0.857 | 0.833 | 0.810 | 11.5 |
| 24 | **unbalanced** | 0.0 (null) | 0.110 | 0.097 | **0.050** | 7.5 |
| 24 | **unbalanced** | 0.2 | 0.320 | 0.263 | 0.210 | 7.3 |
| 24 | **unbalanced** | 0.5 | 0.870 | 0.827 | 0.737 | 7.3 |
| 12 | balanced | 0.0 (null) | 0.063 | 0.060 | 0.040 | 6.9 |
| 12 | balanced | 0.5 | 0.753 | 0.707 | 0.653 | 6.7 |
| 6 | balanced | 0.0 (null) | 0.090 | 0.043 | 0.030 | 3.7 |
| 6 | balanced | 0.5 | 0.563 | 0.513 | 0.423 | 3.7 |

Three observations, all engineering rather than scientific:

1. **Under the null, CR1 over-rejects in every cell** — 0.090 to 0.110 against a nominal 0.050. The direction is the dangerous one.
2. **Imbalance is the dominant risk factor.** At 24 clusters the Satterthwaite degrees of freedom fall from ≈11.5 balanced to ≈7.5 unbalanced.
3. **Nominal cluster count overstates the information available**, consistently, across every configuration tested.

**No minimum-cluster threshold is proposed.** The grid does not support one, and the placeholder stands.

## 7. Reproducibility

Fixed seeds throughout. The wild bootstrap reproduces **exactly** under the same seed and differs under a different seed — verified on two fixtures. **Seed reproducibility is not statistical validation**, and is not counted as such anywhere in this study.

## 8. What this study does not do

It does not approve or activate a method · does not create the dated amendment · does not complete any signoff field · does not modify the active or proposed lock · does not resolve C6, C7, E3, E8, A9 or F5 · does not install anything · does not use any real or prospective observation.

**Every decision remains the authorizer's.** They are enumerated in the decision matrix.
