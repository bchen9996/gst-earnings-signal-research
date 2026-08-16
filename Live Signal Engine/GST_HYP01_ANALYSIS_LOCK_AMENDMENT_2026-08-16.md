# HYP-01 Analysis Lock — Dated Amendment, 2026-08-16

> **Dated authorizer amendment for HYP-01 statistical rules. No prospective outcome was inspected, F5 remains OPEN, and collection remains blocked.**

Human companion to [`GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-08-16.json`](GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-08-16.json), which is the machine-readable authority. Where the two differ, the JSON governs. Authorization provenance is recorded in [`GST_HYP01_METHOD_AUTHORIZATION_2026-08-16.md`](GST_HYP01_METHOD_AUTHORIZATION_2026-08-16.md).

**This amendment is append-only.** It rewrites, deletes, renames and activates nothing. `GST_HYP01_ANALYSIS_LOCK_v1.0.json`, its Markdown companion, the proposed v1.1 pair, the signoff template and the PR #17 / PR #18 validation artifacts are all untouched, and their exact hashes are recorded inside the JSON so drift is detectable.

---

## D1 — Primary covariance estimator

**CR2 / bias-reduced linearization.**

The **official confirmatory implementation** is the pinned R reference path:

```r
vcovCR(fit, cluster = <ticker factor>, type = "CR2")   # R 4.6.1, clubSandwich 0.7.0
```

The study-written Python CR2 is a **validated cross-check, not the authoritative production calculation**.

## D2 — Finite-sample correction

**The BRL adjustment built into clubSandwich's CR2** — and nothing else. CR1 scaling must **not** be applied on top, and no second correction of any kind is permitted.

## D3 — Degrees-of-freedom rule

**Coefficient-specific Satterthwaite approximation:**

```r
coef_test(fit, vcov = <CR2>, test = "Satterthwaite")
```

The realized continuous degrees of freedom are **persisted and reported**.

**Provenance qualification, carried forward permanently.** Implementation agreement for the continuous Satterthwaite df was established under a tolerance **prespecified in PR #18**, which was **not preregistered in PR #17** — PR #17's df rule is exact integer equality, written for CR1's integer *G* − 1.

## D4–D7 — Wild cluster bootstrap

**D4: not used in HYP-01.** It is neither primary nor a sensitivity analysis, and it may not overturn the primary result.

**D5 weights, D6 repetitions, D7 seed: not applicable.** No bootstrap placeholder is retained in an activatable state. Introducing any bootstrap role into HYP-01 requires a **new dated amendment**.

## D8 — Singleton clusters

**Retain singleton ticker clusters.** Singleton presence alone is never an exclusion rule.

Always report: total cluster count · number of singleton clusters · identities of singleton cluster labels *only where the blinded analysis protocol permits* · effective Satterthwaite degrees of freedom.

The D9 numerical refusal rules apply unchanged.

## D9 — Invalid or degenerate fits

**Refuse and abort.** The confirmatory analysis aborts **without producing a confirmatory p-value** if any of these occurs:

non-finite or missing required value · rank-deficient design · zero-variance primary predictor · condition number above the prespecified guard · residual variance below the prespecified relative noise-floor guard · undefined or non-finite covariance · nonpositive or non-finite standard error · nonpositive or non-finite Satterthwaite df · a reference-package warning or error this rule classifies as fatal.

**No new numerical threshold is invented here.** The thresholds are adopted **verbatim** from the committed feasibility runner:

| Threshold | Value |
|---|---|
| `rank_condition_number_max` | 1e10 |
| `zero_variance_column_std_min` | 1e-12 |
| `degenerate_fit_relative_rss_min` | 1e-18 |
| `min_clusters_for_any_output` | 2 |
| `nonfinite_any` | any non-finite value in the design matrix or outcome |

Source: `tools/hyp01_inference_feasibility.py`, symbol `REFUSAL`, SHA-256 recorded in the JSON. **Rationale:** these were prespecified in the PR #17 feasibility runner before its corrected rerun; adopting them verbatim avoids inventing a threshold after seeing anything.

`min_clusters_for_any_output` is an **arithmetic floor** inherited verbatim — it is not an eligibility rule and not a minimum-cluster policy. See D10.

**Four outcomes are distinguished, and a refusal is not a null result:**

| Outcome | Meaning |
|---|---|
| `ANALYSIS_REFUSAL` | a guard fired; no confirmatory p-value is produced |
| `NULL_RESULT` | the analysis ran and did not reject the null |
| `SOFTWARE_FAILURE` | the toolchain failed to execute |
| `DATA_QUALITY_FAILURE` | inputs failed capture or completeness rules |

## D10 — Cluster-count and effective-df policy

**No invented minimum-cluster or effective-df cutoff.**

Always report: number of eligible events · number of ticker clusters · cluster-size distribution · singleton count · realized Satterthwaite df.

The primary result is **not suppressed** merely because a post hoc cluster threshold was crossed. Any future threshold requires a **new dated amendment authored without outcome inspection**.

## D11 — Language, package and version

**Official confirmatory calculation:** R 4.6.1 · clubSandwich 0.7.0 · the exact locked package environment from PR #18 · CR2 covariance and Satterthwaite inference through the documented R calls.

**Python** serves as an **independent implementation cross-check** using the already-validated bridge in `tools/hyp01_r_reference/`. **These roles may not be reversed.**

**Freeze at event 60:** exact analysis-script Git SHA · exact R version · exact package lockfile · exact package versions · operating system and architecture · fixture-validation artifact hash · analysis input manifest · eligible event IDs.

**On disagreement between the official R result and the Python cross-check: stop release and produce a discrepancy report.** It must not be averaged, reconciled manually, or resolved by picking the preferred output.

## D12 — Sector fixed-effect encoding

**Treatment/reference coding**, applying **only to the locked secondary adjusted model** — never to the primary model.

The reference sector is recorded **deterministically before fitting**, by a rule independent of outcomes: **lexicographically first among represented non-OTHER sectors**, unless an existing lock already specifies another rule, in which case that rule governs. The reference category may **never** be selected after examining coefficients or significance.

## D13 — Sparse sectors

**For the secondary sector-adjusted model only.** Sectors represented by **fewer than 3** HYP-01-eligible events are pooled into a single `OTHER` category.

- Pooling is determined from **eligible-event counts only, never outcomes**.
- The pooling map is computed **once** from the frozen 60-event cohort and **persisted** as an exact original-sector → final-category mapping.
- Ticker clusters are **never** pooled, removed or altered.
- The **primary unadjusted model is never altered**.
- If the pooled secondary design remains rank deficient, **refuse the secondary model and report why** — do not adjust the pooling threshold.

**The threshold of 3 is an authorizer-selected governance rule, not a result established by PR #18.** PR #18 established nothing about sector pooling.

## D14 — Per-ticker cap

**No cap.** Every otherwise eligible event among the first 60 eligible events remains included. Repeated ticker observations are handled through **ticker-clustered inference, not selective deletion**.

## D15 — Multiplicity

**No multiplicity adjustment for the single locked HYP-01 primary confirmatory test.**

The protected family contains exactly: **one** primary predictor · **one** primary outcome · **one** primary coefficient test · **two-sided α = 0.05**.

Secondary, sensitivity, descriptive, HYP-02, HYP-03, strategy and product analyses **may not** be used to reinterpret or replace the HYP-01 primary result. They require their own labels and, where confirmatory, their own preregistration.

## D16 — Design-sensitivity policy

**No project-derived power claim.** 60 HYP-01-eligible events is retained as a **governance floor, not a demonstrated power target**.

Prohibited: using retrospective reconstruction effects · using prospective outcomes · revising the sample target after examining results · claiming the study is adequately powered.

Any future power analysis must be anchored to **citable external effect sizes** and requires a **new dated amendment before outcome inspection**.

---

## What this amendment changes, and what it leaves alone

**Amended** (15 fields): the primary model's covariance estimator family, finite-sample correction procedure, degrees-of-freedom rule, refusal rules and reporting requirements; six `environment_freeze` fields; the adjusted sensitivity model's sector encoding and sparse-sector pooling; and two entries in `remaining_pending_decisions`.

**Explicitly unamended, and still operative verbatim:** the primary formula, estimator, coefficient of interest, null hypothesis, sidedness, alpha, covariates and covariate rule; the primary outcome and predictor; the sample inclusion conditions; the missingness and exclusion rules; the freeze-and-display rules including the 60-event threshold and single-run requirement; the eligibility and freeze rules; `results`, `frozen_event_ids` and `eligible_events_now`; the cohort protocol and hypothesis registry.

## Effective-lock resolution

The effective lock is resolved from exactly three inputs — the v1.0 base lock, this dated amendment, and the protected artifact hashes recorded inside it:

```
python tools/hyp01_effective_lock/resolve_effective_lock.py --check
```

Precedence is **base lock v1.0 < dated amendment**. The proposed v1.1 file takes no part. If more than one amendment ever claims authority over the same field, resolution **fails closed** rather than merging them.

## Status after this amendment

| Dimension | Status |
|---|---|
| Statistical package | **AUTHORIZED** |
| Implementation | **VALIDATED** — implementation agreement, not scientific proof |
| F5 construct validity | **OPEN** |
| Prospective collection | **BLOCKED** |
| Scientific result | **NONE** |
| Analysis | **NOT RUN** |

No analysis runner is created or executed by this amendment. It freezes methodology; it does not analyze anything.
