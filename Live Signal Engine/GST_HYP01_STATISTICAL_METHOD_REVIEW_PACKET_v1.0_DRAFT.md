# HYP-01 Statistical Method Review Packet — v1.0 (DRAFT)

**Status: `PROPOSED_NOT_APPROVED`.** This document requests a methodological decision. It does not make one. Nothing here is active, registered, approved, or authoritative.

**`GST_HYP01_ANALYSIS_LOCK_v1.0` remains the current authoritative lock.** A companion file, `GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json`, expresses what this packet proposes *if* a qualified methodologist and Harshith Akurati approve it. Until both approvals are recorded on `GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md`, v1.1 has no standing.

**The author of this packet is not a methodologist.** It was assembled by Claude (Anthropic) from the primary sources cited in §13, at Harshith Akurati's direction. Its purpose is to make an external reviewer's job small and well-posed, not to substitute for one.

**No outcome was inspected in preparing this.** Zero prospective observations exist. `results: null`, `frozen_event_ids: []`, eligible-event counts 0/0/0. Nothing in §§1–13 was chosen by looking at data, because there is no data to look at.

---

## 1. The currently locked HYP-01 design

Reproduced from `GST_HYP01_ANALYSIS_LOCK_v1.0.json`. **Every item in this section is already fixed and is not up for review.**

| Element | Locked value |
|---|---|
| Study question | *Does higher abnormal pre-earnings Google-search attention associate with a greater absolute overnight earnings response?* |
| Predictor | `gst_zscore` — continuous, entered on its natural scale, unthresholded, at the pre-event anchor session. No data-driven cutoff, no winsorization, no outcome-informed transformation |
| Primary outcome | `abs_overnight_gap` = `abs(overnight_gap)`, where `overnight_gap = next_session_open / previous_close - 1` |
| Primary model | `abs_overnight_gap ~ gst_zscore`, ordinary least squares, single right-hand-side term |
| Covariates | none; `data_driven_covariates: false` |
| Null | `beta_gst = 0` |
| Sidedness | two-sided |
| Alpha | 0.05 |
| Clustering | cluster-robust on `ticker` |
| Finite-sample correction | enabled (flag only — *which* correction is unspecified) |
| Required reported quantities | coefficient · 95% confidence interval · p-value · eligible-event count · unique-ticker count |
| Sample | first **60 eligible** events; conditions S-1…S-8 |
| Ordering | mechanically derived response-session date ascending, tie-broken by `event_id` ascending |
| Release sessions | `BMO`, `AMC` eligible; `INTRADAY` ineligible for this outcome |
| Wikipedia | not co-primary; cannot change the confirmatory conclusion |
| Interim analysis | none permitted |
| Optional stopping | prohibited |
| Model change after freeze | prohibited |
| Current results | `null` · `frozen_event_ids: []` · eligible events `0` |

## 2. Exactly what is unresolved

| ID | Question | Current state in v1.0 |
|---|---|---|
| **C6** | Which cluster-robust covariance estimator? CR0/CV0, CR1/CV1, CR2/CV2, CR3/CV3, or another? | `covariance: {type: cluster_robust, cluster_variable: ticker}` — the variant is not named |
| **C7** | Which finite-sample correction, and which reference distribution and degrees of freedom? | `finite_sample_correction: true` — a boolean with no procedure attached |
| **E3** | Multiplicity treatment across HYP-01 / HYP-02 / HYP-03 | registry: *"Any multiplicity adjustment across families is itself `PENDING_SEPARATE_ANALYSIS_LOCK`"* |
| **C9** | Sector fixed-effect encoding in the secondary adjusted model | `remaining_pending_decisions`: `PENDING_SEPARATE_ANALYSIS_LOCK` |
| **NEW-1** | What happens if the realized number of effective ticker clusters is too small for valid inference? | **No rule exists.** Not previously identified as a gap |
| **NEW-2** | Which decisions are the *statistical rule* (fix now) versus *software metadata* (record at event 60)? | v1.0 bundles the cluster-covariance **option string** with package and version at `TO_BE_FROZEN_AT_EVENT_60` |

**NEW-1 and NEW-2 were surfaced while preparing this packet and are not in the merged gap audit.** NEW-2 in particular is a live inconsistency: v1.0 defers the option string to event 60, but an option string *is* the estimator choice in most software. The gap audit already records that separating them requires a dated lock amendment. This packet is the proposal for that amendment.

## 3. Why ≤ 24 clusters and n = 60 force this to be decided deliberately

The locked universe is 24 tickers, so the **nominal** number of clusters is at most 24 — and only if all 24 contribute at least one eligible event, which is not guaranteed. The target is 60 eligible events, so mean cluster size is ≈ 2.5 observations, and cluster sizes will be **unbalanced**: some tickers may contribute four eligible quarters within the window, others one, others zero.

Three facts from the literature make this a decision rather than a formality.

**(a) Cluster-robust inference is asymptotic in the number of clusters, not observations.** Cameron & Miller (2015) state the requirement plainly: cluster-robust standard errors "do require the additional assumption that the number of clusters, rather than just the number of observations, goes to infinity." Twenty-four is not a large number of clusters.

**(b) The bias goes the wrong way.** The conventional estimator is biased *downward* in small samples, so tests over-reject — the error inflates apparent significance. Pustejovsky & Tipton (2018) describe exactly this: CRVE "can be biased downward when the number of clusters is small, leading to hypothesis tests with rejection rates that are too high." For a confirmatory test this is the dangerous direction of error.

**(c) The *effective* number of clusters is materially smaller than the nominal count.** Carter, Schnepel & Steigerwald (2017), as summarised by MacKinnon, Nielsen & Webb (2022), define an effective cluster count `G*_j` per coefficient; it "is always less than G and it can provide a useful warning when `G*_j` is much smaller than G." Cameron & Miller's published Monte Carlo (their Table 2, columns G = 6, 10, 20, 30, 50) reports Imbens–Kolesár effective degrees of freedom averaging **3.3, 5.6, 9.4, 12.3, 16.9** respectively — at **20 nominal clusters the effective df averages 9.4**, with a 5th percentile of 4.9.

The project should therefore expect an effective degrees-of-freedom figure closer to **10 than to 23**, and lower still if cluster sizes are very unbalanced. §5.1 demonstrates this on synthetic data of the project's shape.

**This is not a reason to abandon clustering.** Ignoring within-ticker dependence would be worse. It is a reason to choose the small-cluster correction deliberately, in advance, and to decide now what happens if the realized design is worse than expected.

## 4. Candidate procedures compared

Notation: `G` = number of ticker clusters; `n` = 60; `k` = 2 (intercept + `gst_zscore`); `u_g`, `X_g` the residual and design blocks for cluster `g`; `H_gg = X_g (X'X)^{-1} X_g'`.

| | **A. CV1 (conventional)** | **B. CV2 + Satterthwaite** | **C. CV3 / cluster jackknife** | **D. Wild cluster bootstrap-t (WCR)** |
|---|---|---|---|---|
| **Estimand** | **unchanged** — OLS `beta_gst` | **unchanged** | **unchanged** | **unchanged** |
| **Covariance correction** | `(X'X)⁻¹ [Σ X_g' u_g u_g' X_g] (X'X)⁻¹` scaled by `c = G/(G−1) · (n−1)/(n−k)` | Replaces `u_g` with `A_g u_g`, where `A_g = (I − H_gg)^{−1/2}`. Exactly unbiased if errors are homoskedastic and independent | Replaces `u_g` with `(I − H_gg)^{−1} u_g`; a jackknife estimator generalising HC3 | None — resamples the t-statistic under an imposed null and takes bootstrap critical values |
| **Degrees of freedom / reference** | `t(G−1)` | `t(ν)` with `ν` from a Satterthwaite approximation computed **from the design matrix**, so it varies with the realized data | `t(G−1)` | empirical bootstrap distribution |
| **Few / unbalanced clusters** | Over-rejects, materially. Cameron & Miller Table 2, nominal 5%: **0.125 / 0.103 / 0.082 / 0.069 / 0.075** at G = 6/10/20/30/50 | Best-behaved in the same table: **0.052 / 0.050 / 0.047 / 0.047 / 0.054**. Handles unbalance via leverage | Also good with `t(G−1)`: **0.048 / 0.050 / 0.050 / 0.052 / 0.061**. Tends to be conservative | Good but not uniformly better at very small G: Rademacher **0.068 / 0.065 / 0.062 / 0.051 / 0.060**; Webb 6-point **0.079 / 0.067 / 0.061 / 0.051 / 0.061** |
| **Software** | `statsmodels` `cov_type="cluster"` with `use_correction=True`, `df_correction=True` — **already available in this project's stack** | **Not in `statsmodels`.** Available in R `clubSandwich` (`vcovCR(type="CR2")`, `coef_test(test="Satterthwaite")`). Python would require implementation + verification | Not in `statsmodels`; R `clubSandwich` `type="CR3"` | R `fwildclusterboot`, Stata `boottest`, Python `wildboottest` — **none installed here** |
| **Reproducibility** | Highest — one call, no randomness | Deterministic given the design; requires either an R dependency or a verified in-house implementation | Deterministic; same dependency question | **Stochastic** — needs a fixed seed, a fixed replication count, and a fixed weight distribution, all recorded, or it is not reproducible |
| **Known limitations** | Understates uncertainty exactly where this study sits | Original BRL undefined for some fixed-effect designs (Pustejovsky & Tipton give the generalisation); `ν` can be very small and must be reported | Can be conservative; more computation | Reproducibility burden; performance depends on weight distribution; a bootstrap that "rescues" a primary result invites method-shopping |
| **Suitability here** | Adequate as a **reported reference number**, not as the primary inferential rule | Candidate **primary** | Candidate primary or sensitivity | Candidate **sensitivity only** |

Rejection rates quoted above are from Cameron & Miller (2015) Table 2 (cross-section, individual-level CPS data, true null, nominal 5%), read directly from the published paper.

### 4.1 Rejected without further consideration

- **CV0 / no correction with normal critical values** — strictly dominated; over-rejects worst in every source consulted.
- **Dropping clustering** — multiple eligible quarters per ticker over a nine-month window are not independent. Not defensible.
- **Random-effects / mixed model instead of clustering** — a different estimand and a different set of assumptions. Changing the estimand is outside the scope of an amendment that is supposed to leave the locked design intact.
- **Choosing among A–D after seeing the data** — prohibited by the lock's own model-change rule, and the reason this packet exists.

## 5. Supporting demonstration

### 5.1 Synthetic, project-shaped

A synthetic demonstration was run **outside the repository** on pseudo-random data with a fixed seed, matching only the *shape* of the HYP-01 design: n = 60 observations, G ∈ {10, 16, 24} clusters, one continuous regressor, a cluster random effect, and a **true null** (the outcome does not depend on the regressor). **No ticker, GST value, market response, or project outcome was used**; nothing was calibrated to project data; no method was selected by p-value. The script was deleted after use.

Rejection rates at nominal two-sided 5%:

| Clusters | Cluster sizes | CV0 + normal | CV1 + t(G−1) | CV2 + t(G−1) | **CV2 + Satterthwaite** | mean ν | ν 5th pct | mean G* |
|---|---|---|---|---|---|---|---|---|
| 10 | balanced | 0.128 | 0.069 | 0.056 | **0.043** | 5.8 | 4.0 | 6.8 |
| 10 | unbalanced | 0.208 | 0.135 | 0.102 | **0.057** | 4.2 | 1.9 | 5.0 |
| 16 | balanced | 0.114 | 0.079 | 0.065 | **0.049** | 8.5 | 5.7 | 9.6 |
| 16 | unbalanced | 0.186 | 0.140 | 0.100 | **0.052** | 5.5 | 2.6 | 6.4 |
| 24 | balanced | 0.101 | 0.077 | 0.072 | **0.057** | 11.4 | 7.6 | 12.5 |
| 24 | unbalanced | 0.154 | 0.127 | 0.094 | **0.054** | 7.3 | 3.7 | 8.2 |

Two things to take from this, both of which corroborate the published sources rather than replacing them:

1. **At 24 clusters and n = 60, the Satterthwaite degrees of freedom averaged 11.4 balanced and 7.3 unbalanced — not 23.** The 5th percentile fell to 3.7 under unbalance. The project's nominal cluster count materially overstates the information available.
2. **Unbalance is the dominant risk factor.** At 24 clusters, CV1 + t(G−1) over-rejected at 0.127 when clusters were unbalanced — more than twice the nominal rate. HYP-01's cohort will be unbalanced.

*Caveat: this is one illustrative data-generating process, not a general result. It is offered to show the mechanism on this design's shape. The published Monte Carlo evidence in §4 is the authority.*

### 5.2 A concrete implementation obstacle

`statsmodels` 0.14.6 is the regression library available in this project's environment. Its `get_robustcov_results` docstring documents `cov_type="cluster"` with `use_correction` (a CV1-type scaling) and `df_correction` (switches inference to `G−1` degrees of freedom). **It offers no CR2, bias-reduced-linearization, or Satterthwaite option** — a string search of the docstring for `CR2`, `bias-reduced`, `Satterthwaite` and `BRL` returns nothing. `clubSandwich` (R), `linearmodels`, and `wildboottest` are **not installed**.

**Adopting option B therefore has a real implementation cost**, and the reviewer should know that before recommending it: either add an R dependency, or implement CV2 and the Satterthwaite df in Python and validate the implementation against a published reference before the first observation. That validation is itself work that must happen **before** collection, not at the freeze.

## 6. Provisional recommendation — `PROPOSED_NOT_APPROVED`

**This is a proposal for a methodologist to accept, modify, or reject. It is not a decision, and it is not adopted by being written here.**

| | Proposal | Why |
|---|---|---|
| **Estimand** | **Unchanged.** OLS `beta_gst` from `abs_overnight_gap ~ gst_zscore` | Every candidate in §4 estimates the same quantity. Nothing here touches the locked design |
| **C6** | **CV2 (bias-reduced linearization), clustered on `ticker`** | Exactly unbiased under its working model; best-behaved in the published Monte Carlo at 20–30 clusters; handles unbalance through leverage |
| **C7** | **Satterthwaite / Bell–McCaffrey degrees of freedom**, computed from the realized design; two-sided α = 0.05 retained | Cameron & Miller's own conclusion from their simulations: *"it is best to use the CR3 bias-correction with T(G−1) critical values and the CR2 bias-correction with T(df) critical values where df is the Imbens and Kolesár calculated degrees of freedom."* Imbens & Kolesár recommend computing the BM adjustment "as a matter of routine" |
| **Reporting** | Report the realized `ν` and `G*` **alongside** the coefficient, CI and p-value, whatever they are | A very small `ν` is itself a finding about evidential strength and must not be hidden |
| **Wild cluster bootstrap** | **Labelled sensitivity analysis only.** Predeclared, reported always, and **explicitly barred from rescuing or overturning the primary result** | MacKinnon, Nielsen & Webb recommend WCR bootstrap "as a matter of routine" — but as corroboration. Letting a second procedure overturn the first is method-shopping with extra steps |
| **CV1** | Report as a **reference number** for comparability with other literature; not the inferential rule | Cheap, familiar, and its gap from CV2 is diagnostic |
| **E3** | **No multiplicity adjustment for the single HYP-01 primary confirmatory test** | Exactly one primary hypothesis, one predictor, one outcome, one test, fixed in advance. Standard practice for a single primary endpoint |
| **E3 (families)** | HYP-02 and HYP-03 report with a **predeclared, explicitly non-confirmatory** treatment; they cannot change the confirmatory conclusion | Already the registry's rule; this makes the reporting treatment explicit rather than implicit |
| **C9** | **Sum (effects) coding** for sector fixed effects in the secondary adjusted model, sectors from the existing frozen `GST_Sector_ETF_Mapping`, with any sector too sparse to estimate pooled by a **predeclared** rule | See §10 |
| **NEW-1** | A minimum effective-cluster / effective-df validity rule **must exist before collection** — but the threshold is the methodologist's to set. **This packet does not propose a number** | See §8 |
| **NEW-2** | Split the statistical rule (fixed now) from software metadata (recorded at event 60) | See §9 |

**Where the evidence pointed away from the suggested starting position.** The task that commissioned this packet listed CV2 + Satterthwaite as a candidate. The sources support it, so it is carried forward — but two qualifications are recorded rather than suppressed:

- **CV3 is a genuine competitor, not an also-ran.** In Cameron & Miller's Table 2, CV3 + t(G−1) achieved 0.048/0.050/0.050/0.052 at G = 6/10/20/30 — as close to nominal as CV2 + IK-df, and with a *simpler* degrees-of-freedom rule that does not depend on a design-matrix computation. MacKinnon, Nielsen & Webb note CV3 is a jackknife estimator generalising HC3. **A reviewer who prefers CV3 + t(G−1) on simplicity and reproducibility grounds would be making a defensible choice, and §7 asks the question explicitly.**
- **The wild cluster bootstrap did *not* dominate CV2 + Satterthwaite** in the published Monte Carlo at small G (Rademacher 0.068 vs 0.052 at G = 6). That is the evidential basis for proposing it as sensitivity rather than primary — not a prior preference.

## 7. Questions requiring methodologist signoff

Each is answerable independently.

1. **C6** — Is **CV2** appropriate as the primary covariance estimator for `beta_gst`, clustered on `ticker`, at G ≤ 24 and n = 60? If not, which, and why?
2. **C6-alt** — Should **CV3 + t(G−1)** be preferred instead, given comparable published performance and a simpler, more reproducible df rule?
3. **C7** — Is the **Satterthwaite/Bell–McCaffrey** df the right reference distribution, or should a fixed `t(G−1)` be used with a bias-corrected estimator?
4. **C7-alt** — Should the realized `ν` be **reported** only, or should it also **gate** the analysis (see Q5)?
5. **NEW-1** — Is there a minimum effective df or minimum `G*` below which this design should not be treated as supporting a confirmatory conclusion? **If yes, what value, and what happens instead** — abstain, report as inconclusive with the interval, or switch to a predeclared alternative? *This packet deliberately proposes no number.*
6. **E3** — Is **no multiplicity adjustment** correct for a single primary confirmatory test, given HYP-02 and HYP-03 exist but are non-confirmatory? If an adjustment is required, which, and over what family?
7. **C9** — Is **sum coding** right for the secondary sector fixed effects, and what is the predeclared rule for sectors with too few events?
8. **D** — Is the wild cluster bootstrap correctly placed as **sensitivity only**, and which variant (Rademacher, Webb 6-point), how many replications, restricted or unrestricted?
9. **Robustness of an unbalanced design** — Does the expected 60-events-over-≤24-tickers structure raise concerns not addressed above? Should a per-ticker cap on eligible events be considered — noting that any such cap changes the **sample definition** and would require a separate amendment to a currently locked element?
10. **A9** — Is a pre-data design-sensitivity analysis worth performing, and on what externally justified effect sizes? (See §11.)
11. **Anything the packet gets wrong.** The author is not a methodologist. A finding that the framing itself is mistaken is a useful review outcome.

## 8. Minimum-cluster / effective-df failure policy — **unresolved by design**

If the realized cohort yields very few effective clusters — say most eligible events concentrate in a handful of tickers — CV2 + Satterthwaite will return a small `ν` and a wide interval. That is the procedure working correctly. The open question is **governance, not arithmetic**:

- Is there a floor below which the study should decline to report a confirmatory conclusion at all?
- If so, is the trigger effective df, `G*`, the number of tickers contributing ≥ 1 eligible event, or maximum single-ticker share?
- And what is the consequence — **abstain**, **report as inconclusive with the interval published**, or **proceed with a predeclared caveat**?

**No threshold is proposed here.** Inventing one would be the exact failure the gap audit was written to prevent: a number that looks locked because it appears in a document, but was chosen by an author with no standing to choose it. The proposed v1.1 lock carries an explicit `PLACEHOLDER_PENDING_METHODOLOGIST` for this field.

One constraint is *not* open: whatever the rule, it must be fixed **before the first prospective observation** and must never be evaluated after seeing the coefficient.

## 9. Statistical rule versus software record

| Fixed **before the first prospective observation** | Recorded **at the event-60 freeze** |
|---|---|
| Covariance estimator family (CV1/CV2/CV3) | Statistics package name |
| Degrees-of-freedom rule (t(G−1) vs Satterthwaite) | Package version |
| Alpha and sidedness *(already locked)* | The literal option string implementing the chosen estimator |
| Multiplicity treatment | Random seed, if any |
| Minimum-cluster / effective-df policy | Analysis-code commit SHA |
| Wild-bootstrap role, variant, replications, weights, seed policy | The exact 60 event IDs |
| Sector coding for the secondary model | Language version |

**The distinction is authorship.** A rule is chosen by a human on scientific grounds. A record is transcribed from the environment. v1.0 currently places `cluster_covariance_option_string` in the *record* column while leaving the *rule* unspecified — which means the rule would be chosen, implicitly, by whoever typed the option string at event 60. Correcting that inversion is the main structural purpose of this amendment.

Analysis code may still be **written** after the rule is fixed, provided it only mechanically implements the fixed rule and is tested exclusively on synthetic fixtures or explicitly permitted historical material.

## 10. Sector fixed-effect encoding (C9) — secondary model only

The adjusted sensitivity model `abs_overnight_gap ~ gst_zscore + realized_volatility + release_session_BMO + sector` is **secondary** and can neither overturn nor rescue the primary result.

With `k` sectors, `k−1` fixed effects are estimable alongside an intercept.

| Coding | Intercept means | Sector coefficient means | Effect on `beta_gst` |
|---|---|---|---|
| **Treatment (dummy/reference)** | expected outcome in the arbitrarily chosen reference sector | difference from that reference | **none** |
| **Sum (effects) coding** | unweighted grand mean across sectors | deviation from the grand mean; last sector implied | **none** |

**The estimate and standard error of `gst_zscore` are identical under either coding** — they span the same column space. The choice affects only how the nuisance intercept and sector terms are *interpreted*, which matters here because no reference sector is scientifically privileged among 24 large-cap tickers.

**Proposal: sum coding**, sectors drawn from the existing frozen `GST_Sector_ETF_Mapping_v0.1.json` (unchanged by this packet), plus a **predeclared rule for sparse sectors** — with ≤ 24 tickers over 60 events, some sectors may contribute one event or none. That rule must be fixed in advance, not improvised at analysis time. Absorbing sector fixed effects also reduces residual within-cluster variation, which is where the Pustejovsky & Tipton generalisation of BRL to arbitrary fixed-effect designs becomes relevant.

## 11. Design sensitivity without prospective outcomes (A9)

The registry states plainly: *"No power calculation was performed, and none may be performed using observed project results. The numeric thresholds are GOVERNANCE ELIGIBILITY FLOORS … not claims of guaranteed statistical power."*

Legitimate options, all of which must precede the first prospective outcome:

1. **None.** Keep n = 60 as a governance floor and state openly that the study is not powered to a specific effect size. Honest and already consistent with the registry.
2. **Minimum detectable effect curve.** Given n = 60, α = 0.05 two-sided, and a *range* of plausible effective df (say 5–15, per §3 and §5.1), report what effect size would be detectable at conventional power. Uses no outcome data — only the design.
3. **Externally-anchored power analysis.** Use effect sizes from *published* attention-and-returns literature, cited, explicitly labelled as external and not from this project.
4. **Simulation-based design sensitivity.** Synthetic data of the project's shape across effective-df scenarios, as in §5.1.

**Prohibited in all cases:** any effect size taken from this project's retrospective reconstruction, any prospective outcome, and any revision of `n = 60` justified by a power calculation performed after outcomes exist. **No power analysis was performed in preparing this packet.**

Option 2 is the cheapest thing with real informational value, and it can be produced before September. **The choice is the reviewer's.**

## 12. Mathematical definitions (implementation-neutral)

Let `y` be the `n`-vector of `abs_overnight_gap`, `X` the `n × 2` design `[1, gst_zscore]`, `G` the number of ticker clusters, and for cluster `g`: `X_g`, `y_g`, `u_g = y_g − X_g β̂`.

**OLS estimator** (unchanged in every option):

    β̂ = (X'X)⁻¹ X'y

**Generic cluster-robust sandwich:**

    V = (X'X)⁻¹ [ Σ_{g=1..G} X_g' Ω̂_g X_g ] (X'X)⁻¹

**CV0:**  `Ω̂_g = u_g u_g'`

**CV1:**  `V_CV1 = c · V_CV0`, with `c = [G/(G−1)] · [(n−1)/(n−k)]`

**CV2 (bias-reduced linearization; Bell & McCaffrey 2002):**

    H_gg = X_g (X'X)⁻¹ X_g'
    A_g  = (I − H_gg)^{−1/2}        (symmetric inverse square root)
    Ω̂_g  = (A_g u_g)(A_g u_g)'

Exactly unbiased for `V` when errors are homoskedastic and independent; reduces to HC2 when every cluster has one observation.

**CV3 (cluster jackknife; generalises HC3):**

    Ω̂_g = [(I − H_gg)⁻¹ u_g][(I − H_gg)⁻¹ u_g]'

**Satterthwaite / Bell–McCaffrey degrees of freedom** for a linear combination `c'β` (here `c = (0,1)'`), under the working model `Ω = I`:

    H  = X (X'X)⁻¹ X'
    G_g = (I − H)_{[·, g]} A_g X_g (X'X)⁻¹ c          (an n-vector per cluster)
    G   = [G_1 … G_G]                                  (n × G)
    ν   = (Σ_i λ_i)² / (Σ_i λ_i²),  λ_i = eigenvalues of G'G

`ν` depends on the realized design matrix, so it cannot be computed in advance — only the **rule** can be fixed in advance. Test `c'β̂ / sqrt(c'Vc)` against `t(ν)`.

**Carter–Schnepel–Steigerwald effective clusters** for coefficient `j`:

    γ_g = [(X'X)⁻¹]_j' X_g' X_g [(X'X)⁻¹]_j
    G*_j = (Σ_g γ_g)² / (Σ_g γ_g²)

**Wild cluster restricted (WCR) bootstrap-t:** impose the null, resample cluster-level residuals with random weights (Rademacher ±1 or Webb 6-point), recompute the t-statistic `B` times, compare the observed statistic to the bootstrap distribution. Requires a fixed seed, a fixed `B`, and a fixed weight distribution to be reproducible.

## 13. Bibliography

All sources are peer-reviewed articles, working papers by their authors, or official package documentation. **No blog, trading site, aggregator, or unsourced summary is cited as authority.** Accessed **2026-08-09** (America/Chicago).

1. **Bell, R. M., & McCaffrey, D. F. (2002).** "Bias Reduction in Standard Errors for Linear Regression with Multi-Stage Samples." *Survey Methodology*, **28**(2), 169–181. Statistics Canada Catalogue No. 12-001-XPB. Robert M. Bell, AT&T Labs–Research; Daniel F. McCaffrey, RAND. https://www150.statcan.gc.ca/n1/pub/12-001-x/2002002/article/9058-eng.pdf — *the original CR2/BRL and Satterthwaite proposal. Abstract, verbatim: "we propose a new method, bias reduced linearization (BRL), based on residuals adjusted to better approximate the covariance of the true errors. When the errors are i.i.d., the BRL estimator is unbiased for the variance… We also propose using a Satterthwaite approximation to determine the degrees of freedom of the reference distribution."*

2. **Imbens, G. W., & Kolesár, M. (2016).** "Robust Standard Errors in Small Samples: Some Practical Advice." *The Review of Economics and Statistics*, **98**(4), 701–712. Working-paper version: NBER Working Paper No. 18478, October 2012. https://www.nber.org/papers/w18478 — *verbatim from the abstract: "We recommend researchers calculate the Bell-McCaffrey degrees-of-freedom adjustment to assess potential problems with conventional robust standard errors and use the modification as a matter of routine."*

3. **Cameron, A. C., & Miller, D. L. (2015).** "A Practitioner's Guide to Cluster-Robust Inference." *Journal of Human Resources*, **50**(2), 317–372. Author-hosted copy: https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf — *source of the Table 2 rejection rates and effective-df figures in §3–§4. Verbatim conclusion: "it appears from rows 6 and 7 that it is best to use the CR3 bias-correction with T(G−1) critical values and the CR2 bias-correction with T(df) critical values where df is the Imbens and Kolesár (2013) calculated degrees of freedom."*

4. **MacKinnon, J. G., Nielsen, M. Ø., & Webb, M. D. (2022/2023).** "Cluster-Robust Inference: A Guide to Empirical Practice." *Journal of Econometrics*. Preprint: https://arxiv.org/pdf/2205.03285 — *James G. MacKinnon (Queen's), Morten Ø. Nielsen (Aarhus), Matthew D. Webb (Carleton). Verbatim: "we therefore do not recommend relying only on CV1 and asymptotic theory"; "we recommend using one or more variants of the wild cluster restricted, or WCR, bootstrap … as a matter of routine." Also the source for the CV2/CV3 definitions and the summary of Carter–Schnepel–Steigerwald effective clusters.*

5. **Pustejovsky, J. E., & Tipton, E. (2018).** "Small-Sample Methods for Cluster-Robust Variance Estimation and Hypothesis Testing in Fixed Effects Models." *Journal of Business & Economic Statistics*, **36**(4), 672–683. Preprint: https://arxiv.org/abs/1601.01981. Corrigendum: *JBES* (2023), https://www.tandfonline.com/doi/full/10.1080/07350015.2023.2174123 — *generalises BRL to arbitrary fixed-effect designs; relevant to the secondary sector-fixed-effect model. Note the corrigendum to Theorem 2 — any implementation must use the corrected result.*

6. **Carter, A. V., Schnepel, K. T., & Steigerwald, D. G. (2017).** "Asymptotic Behavior of a t-Test Robust to Cluster Heterogeneity." *The Review of Economics and Statistics*, **99**(4), 698–709 — *the effective-number-of-clusters `G*` measure, as described in source 4.*

7. **Cameron, A. C., Gelbach, J. B., & Miller, D. L. (2008).** "Bootstrap-Based Improvements for Inference with Clustered Errors." *The Review of Economics and Statistics*, **90**(3), 414–427 — *the wild cluster bootstrap.*

8. **`clubSandwich` R package** — official documentation, maintainer James E. Pustejovsky. https://cran.r-project.org/web/packages/clubSandwich/vignettes/panel-data-CRVE.html — *reference implementation of CR2 with Satterthwaite inference (`vcovCR`, `coef_test(test="Satterthwaite")`). Documentation states CRVE-based tests "can perform quite poorly when based on a limited number of independent clusters," and that the package's CR2 "works even in models with arbitrary sets of fixed effects."*

9. **`statsmodels` (Python), version 0.14.6** — the installed regression library. `RegressionResults.get_robustcov_results` docstring, read directly from the installed package on 2026-08-09: documents `cov_type="cluster"` with `use_correction` and `df_correction`; **no CR2, BRL, or Satterthwaite option exists.** https://www.statsmodels.org/

10. **ICH E9, "Statistical Principles for Clinical Trials"** — international regulatory guideline; the standard reference for the principle that a single, prespecified primary endpoint with one comparison does not require multiplicity adjustment, while secondary and exploratory endpoints carry no confirmatory claim. Cited for the **principle** in §6/E3, from a different field; a reviewer may reasonably prefer an economics-specific multiplicity reference, which is Q6.

### Source-quality note

One widely repeated claim — a "rule of thumb" that cluster-robust asymptotics should not be trusted below roughly 40–42 clusters — was **searched for in the full text of Cameron & Miller (2015) and not found**. It is therefore **not cited here as attributable to them**, and §3 rests instead on quotations and Monte Carlo figures verified directly in the source documents. Statements in this packet are either quoted from a cited source, computed from the synthetic demonstration in §5.1 and labelled as such, or flagged as project-specific judgment.

### What is source-supported versus project judgment

| Claim | Basis |
|---|---|
| CV2 is unbiased under its working model; Satterthwaite df proposed alongside it | Source 1 |
| BM df adjustment should be computed as a matter of routine | Source 2 |
| CV2 + IK df and CV3 + t(G−1) are the best-performing combinations tested | Source 3 |
| Effective df at 20 nominal clusters averages 9.4 | Source 3, Table 2 |
| Do not rely on CV1 + asymptotics alone; use WCR bootstrap routinely | Source 4 |
| CRVE biased downward at small G, inflating rejection rates | Source 5 |
| No CR2 available in `statsmodels` 0.14.6 | Source 9, read from the installed package |
| Sum vs treatment coding leaves `beta_gst` unchanged | Standard linear-algebra fact; verifiable |
| **≤ 24 tickers with 60 events is a small-cluster problem for *this* study** | **Project judgment**, applying sources 1–5 to the locked design |
| **Wild bootstrap belongs as sensitivity, not primary, here** | **Project judgment**, informed by source 3's small-G rejection rates |
| **A minimum effective-df policy is needed** | **Project judgment** — the *threshold* is deliberately left to the reviewer |
| **Sum coding preferred for sector effects** | **Project judgment**; no reference sector is privileged |

---

**Nothing in this packet is approved. `GST_HYP01_ANALYSIS_LOCK_v1.0` remains the authoritative lock until a methodologist and Harshith Akurati record their decisions on the signoff form.**
