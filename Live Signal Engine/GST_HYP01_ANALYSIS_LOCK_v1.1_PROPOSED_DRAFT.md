# HYP-01 Analysis Lock — v1.1 **PROPOSED**

> ## `PROPOSED_PENDING_HUMAN_AND_METHODOLOGIST_APPROVAL`
>
> **This file is a proposal. It is not active, not registered, not approved, not frozen, and not authoritative.**
>
> **[`GST_HYP01_ANALYSIS_LOCK_v1.0`](GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md) remains the sole authoritative HYP-01 analysis lock.** Nothing in this document governs any analysis unless and until a qualified methodologist and Harshith Akurati record approval on the [signoff form](GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md), and a separate dated commit activates it.

Companion to the machine-readable [`GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json`](GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json). Where the two differ, **neither is authoritative** — v1.0 is.

**Authored by** Claude (Anthropic), at the direction of Harshith Akurati. **The author is not a methodologist and may not supply any approval this proposal requires.**

**No outcome was inspected.** Zero prospective observations exist: `results: null`, `frozen_event_ids: []`, eligible-event counts 0/0/0. Every choice below was made from published statistical literature and the locked design, never from data.

---

## Why this proposal exists

The v1.0 lock fixes the science: predictor, outcome, model formula, sidedness, alpha, clustering variable, sample eligibility, ordering, n = 60, no interim analysis, no optional stopping. It leaves four things unspecified and contains one structural inversion.

| | Gap | v1.0 state |
|---|---|---|
| **C6** | Which cluster-robust covariance estimator | variant not named |
| **C7** | Which finite-sample correction and reference distribution | a boolean, `finite_sample_correction: true` |
| **E3** | Multiplicity treatment | `PENDING_SEPARATE_ANALYSIS_LOCK` |
| **C9** | Sector fixed-effect encoding (secondary model) | `PENDING_SEPARATE_ANALYSIS_LOCK` |
| **NEW-1** | What if too few effective clusters? | **no rule exists** |
| **NEW-2** | Rule-versus-record inversion | the estimator's *option string* is deferred to event 60, so the estimator would be chosen implicitly by whoever types it |

The reasoning, the compared alternatives, and the sources are in the [method review packet](GST_HYP01_STATISTICAL_METHOD_REVIEW_PACKET_v1.0_DRAFT.md). This file records only what is proposed.

## Unchanged from v1.0

Everything not listed under *Proposed changes* is carried forward **verbatim** and is not reopened: the study question · `gst_zscore` continuous, natural-scale, unthresholded · `abs_overnight_gap` · `abs_overnight_gap ~ gst_zscore` OLS · no covariates · `beta_gst = 0` · two-sided · α = 0.05 · clustering on `ticker` · S-1…S-8 · response-session-date ordering tie-broken by `event_id` · n = 60 · `BMO`/`AMC` eligible, `INTRADAY` ineligible · no imputation or zero-fill or winsorization or outlier deletion · no interim analysis · no optional stopping · no model change after freeze · one run · display gates · cohort protocol · v0.2 thresholds and interval formulas · HYP-02 and HYP-03.

**The estimand is unchanged.** Every alternative considered estimates the same OLS coefficient on `gst_zscore`. This proposal changes *how uncertainty around that coefficient is quantified*, never what is being estimated.

## Proposed changes — all `PROPOSED_NOT_APPROVED`

### C6 — covariance estimator

**Proposed: CV2**, bias-reduced linearization (Bell & McCaffrey 2002), clustered on `ticker`. The residual block `u_g` is replaced by `A_g u_g` with `A_g = (I − H_gg)^{−1/2}`, `H_gg = X_g (X'X)⁻¹ X_g'`. Exactly unbiased under a homoskedastic-independent working model.

*A reviewer may reasonably prefer **CV3 + t(G−1)*** — comparable published performance, simpler and more reproducible df rule. Question 2 on the signoff form asks this directly.

### C7 — finite-sample inference

**Proposed:** reference distribution `t(ν)` with `ν` from the **Satterthwaite / Bell–McCaffrey** approximation computed from the realized design matrix. α = 0.05 two-sided, unchanged.

`ν` cannot be computed in advance — only the *rule* can be fixed in advance.

**Also proposed:** report the realized `ν`, the effective cluster count `G*`, and the CV1 standard error as a comparability reference, alongside the coefficient, 95% CI and p-value. A very small `ν` is a finding about evidential strength and must not be hidden.

### E3 — multiplicity

**Proposed: no adjustment for the single HYP-01 primary confirmatory test.** One primary hypothesis, one predictor, one outcome, one test, all fixed before data exists.

HYP-02, HYP-03 and all registered secondary/exploratory analyses report with a **predeclared non-confirmatory treatment**: no confirmatory claim, cannot change the HYP-01 conclusion, not pooled with it into a single tested family. The existing promotion rule is unchanged — promotion to confirmatory may never be based on observed results.

### C9 — sector fixed effects (secondary model only)

**Proposed: sum (effects) coding**, sectors from the existing frozen `GST_Sector_ETF_Mapping_v0.1.json` (unchanged here). No reference sector is scientifically privileged among the locked 24 tickers.

**The `gst_zscore` estimate and standard error are identical under treatment or sum coding** — the codings span the same column space. Only the interpretation of the intercept and sector terms differs.

**Sparse-sector rule: `PLACEHOLDER_PENDING_METHODOLOGIST`.** With ≤ 24 tickers over 60 events some sectors may contribute one event or none. That rule must be predeclared; none is invented here.

### D — wild cluster bootstrap

**Proposed: labelled sensitivity analysis only.** Predeclared, **always reported** whatever it shows, and **explicitly barred from rescuing or overturning the primary result.**

Variant, restricted-vs-unrestricted, and replication count are `PLACEHOLDER_PENDING_METHODOLOGIST`. A fixed seed must be recorded at the freeze — a stochastic procedure without a recorded seed is not reproducible.

### NEW-2 — separating the rule from the record

| Fixed **before the first prospective observation** | Recorded **at the event-60 freeze** |
|---|---|
| Covariance estimator family (C6) | Language version |
| Degrees-of-freedom rule (C7) | Statistics package and version |
| Alpha and sidedness *(already locked)* | The literal option string implementing the fixed estimator |
| Multiplicity treatment (E3) | Random seed, wild-bootstrap seed |
| Minimum-cluster / effective-df policy (NEW-1) | Analysis-code commit SHA |
| Wild-bootstrap role, variant, replications, weights | The exact 60 event IDs |
| Sector coding (C9) | |

**A rule is chosen by a human on scientific grounds. A record is transcribed from the environment. Recording a value is not deciding one.**

## Unresolved — deliberately left open

### NEW-1 · minimum effective clusters / effective degrees of freedom

**No threshold is proposed. `PLACEHOLDER_PENDING_METHODOLOGIST`.**

If eligible events concentrate in a few tickers, CV2 + Satterthwaite will return a small `ν` and a wide interval — the procedure working correctly. The open question is governance: is there a floor below which no confirmatory conclusion should be drawn; what is the trigger (effective df, `G*`, tickers contributing ≥ 1 event, maximum single-ticker share); and what is the consequence (abstain / report as inconclusive with the interval / proceed with a predeclared caveat)?

**Inventing a number here would be exactly the failure the [gap audit](../PREREGISTRATION_GAP_AUDIT_v1.0.md) exists to prevent** — a value that looks locked because it appears in a file, chosen by an author with no standing to choose it.

One constraint is *not* open: whatever the rule, it is fixed **before the first prospective observation** and **never evaluated after seeing the coefficient**.

### Also unresolved

- **C6-alt** — CV3 + t(G−1) instead?
- **A9** — pre-data design-sensitivity analysis, and on what externally justified effect sizes? *(None was performed.)*
- **Per-ticker cap** — would change the **sample definition**, a currently locked element, and needs its own amendment.
- **Sparse-sector rule.**
- **Implementation path** — CV2 + Satterthwaite is **not available in `statsmodels` 0.14.6**, this project's regression library. Add an R/`clubSandwich` dependency, or implement and validate CV2 in Python against a published reference? Either is work that must complete **before** the first observation.

## Confirmatory-cohort boundary

Carried from [North Star §10](../PROJECT_NORTH_STAR_v1.0_DRAFT.md) as merged on main.

1. **Development material** — synthetic fixtures and explicitly labelled historical/reconstructed artifacts. **No prospective outcomes, ever.** May inform methodology. Not a holdout.
2. **Confirmatory evaluation cohort** — the first 60 eligible prospective events, governed from **event 1** by the pre-data lock. **Never development data at any point.** Outcomes gated and unexamined until the full set and the analysis environment are frozen.
3. **Event-60 freeze** — fixes event IDs, analysis commit, environment, reproducibility metadata. Does **not** retroactively convert development material into holdout data. Does **not** authorize changing the statistical rule.
4. **Extension cohort** — separately labelled; never enlarges the frozen set; **not automatically a formal holdout test**. It becomes one only under a new dated protocol written before those outcomes are examined.

## What must happen before this file has any standing

1. A named, qualified methodologist records decisions on **C6, C7 and E3**.
2. The methodologist **sets or explicitly declines** the NEW-1 minimum-cluster / effective-df rule.
3. **Harshith Akurati** records approval.
4. A **separate dated commit** activates the approved version and states plainly what changed from v1.0 and why.

**All four must complete before the first HYP-01-eligible prospective pre-event capture — not at the event-60 freeze.** Claude may not supply any of these approvals.

## Current state

`results: null` · `frozen_event_ids: []` · `eligible_events_now: 0` · registry still points at **v1.0** and is unmodified by this proposal.

---

**This file must never be described as active, registered, approved, frozen, authoritative, adopted, in force, or "the current lock." Until signoff, v1.0 is the lock.**
