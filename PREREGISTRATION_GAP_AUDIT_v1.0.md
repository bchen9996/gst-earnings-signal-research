# Preregistration Gap Audit — v1.0

**Status:** Audit only. **No methodology is changed and no missing value is invented.** Where a scientific decision is unresolved, it is marked as requiring human or external methodological review — filling it in from this document would be exactly the failure the audit exists to catch.

**Audited against** the repository at `main` = `133ee473918b3922f4040031aee8c8eb3c20992f`.

**Deadline convention.** *Before first observation* = before the first prospective pre-event capture. *Before freeze* = before the 60th eligible event fixes the sample and the analysis commit. *Before analysis* = before the primary model is run once.

**Severity.** **Critical** = an unresolved value could change the confirmatory conclusion. **High** = affects interpretation or a secondary claim. **Medium** = affects reporting or reproducibility. **Low** = documentation.

---

## A. Sample definition

| # | Element | Repository source | Status | Locked value | Gap | Sev. | Changes methodology? | Human decision | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| A1 | Universe | `gst_market_response/constants.py` → `LOCKED_24_TICKER_UNIVERSE`; cohort protocol v1.1 | **LOCKED** | 24 tickers, read from the production constant | — | — | no | none | — |
| A2 | Event eligibility | cohort protocol v1.1 INC-1…INC-10 | **LOCKED** | regular quarterly/annual earnings; official IR/SEC source; explicit date; timing classifiable without inference | — | — | no | none | — |
| A3 | Inclusion / exclusion | cohort protocol v1.1 §5, §7.1 | **LOCKED** | 12 dispositions; explicit list of reasons an event may **never** be excluded | — | — | no | none | — |
| A4 | Registration lead time | cohort protocol v1.1 | **LOCKED** | **5 XNYS trading sessions** before the derived anchor | — | — | no | none | — |
| A5 | Collection window | cohort protocol v1.1 | **LOCKED** | **2026-09-01 → 2027-05-31**, applied to the derived anchor | — | — | no | none | — |
| A6 | HYP-01 sample conditions | HYP-01 lock S-1…S-8 | **LOCKED** | cohort-enrolled · core-class eligible · strict v0.2 core · D1 passed · `gst_zscore` with successful GST provenance · `abs_overnight_gap` non-null · `BMO`/`AMC` | — | — | no | none | — |
| A7 | Event ordering | HYP-01 lock `sample.ordering` | **LOCKED** | derived response-session date ascending, tie-broken by `event_id` ascending | — | — | no | none | — |
| A8 | Sample size | HYP-01 lock; hypothesis registry | **LOCKED** | **n = 60** (HYP-02 60, HYP-03 40) | thresholds are governance floors, **not** power calculations | Low | no | none | — |
| A9 | Statistical power | — | **ABSENT BY DESIGN** | — | no power analysis exists; none may use observed project results | Medium | **would** if used to change n | **Yes — external methodologist.** A pre-data power analysis is legitimate; a post-hoc one is not | before freeze |

## B. Timestamps and provenance

| # | Element | Source | Status | Locked value | Gap | Sev. | Changes methodology? | Human decision | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| B1 | Timestamps | pre-event capture provenance (15 fields) | **LOCKED** | retrieval timestamps, `run_date`, `price_asof_date`, panel CSV/marker SHA-256, commit SHA, methodology version | — | — | no | none | — |
| B2 | Anchor derivation | `operations_plan.build_operations_plan`; XNYS calendar | **LOCKED** | `sessions.pre_event_anchor.session_date`; never recomputed by hand | — | — | no | none | — |
| B3 | Point-in-time validity (historical) | status doc §1a | **KNOWN FAILURE** | — | historical z-scores are a reconstruction; check treated as **failed**, no waiver | **Critical** (historical only) | no — prospective path already fixes it forward | **Yes** — decide whether any retrospective figure may appear in a paper, and with what caveat | before publication |
| B4 | Code / version provenance | analysis-lock `environment_freeze` | **PARTIALLY LOCKED** | fields exist; all `TO_BE_FROZEN_AT_EVENT_60` | package, version, cluster-covariance option string and seed are **unset** | High | no — recording, not choosing | **Yes** — must be recorded at freeze | at freeze |

## C. Hypothesis and outcome

| # | Element | Source | Status | Locked value | Gap | Sev. | Changes methodology? | Human decision | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| C1 | Primary hypothesis | HYP-01 lock | **LOCKED** | "Does higher abnormal pre-earnings Google-search attention associate with a greater absolute overnight earnings response?" | — | — | no | none | — |
| C2 | Primary predictor | HYP-01 lock | **LOCKED** | `gst_zscore`, continuous, unthresholded, at the pre-event anchor | — | — | no | none | — |
| C3 | Primary outcome | HYP-01 lock | **LOCKED** | `abs_overnight_gap` = `abs(next_session_open / previous_close - 1)` | — | — | no | none | — |
| C4 | Model formula | HYP-01 lock | **LOCKED** | `abs_overnight_gap ~ gst_zscore`, OLS, single RHS term | — | — | no | none | — |
| C5 | Alpha | HYP-01 lock; registry governance | **LOCKED** | **0.05**, two-sided | — | — | no | none | — |
| C6 | Covariance / error structure | HYP-01 lock | **LOCKED** | cluster-robust on `ticker` | exact estimator variant (CR0/CR1/CR2/CR3) **unspecified** | **Critical** | **yes** | **Yes — external econometrics review.** Do not pick one to make this table complete | before freeze |
| C7 | Finite-sample correction | HYP-01 lock | **LOCKED (flag)** | enabled | which correction, given ~24 clusters, is unspecified; the small-cluster problem is real at 24 | **Critical** | **yes** | **Yes — same review as C6** | before freeze |
| C8 | Covariates | HYP-01 lock | **LOCKED** | none; no data-driven covariate selection | — | — | no | none | — |
| C9 | Adjusted sensitivity model | HYP-01 lock §6 | **LOCKED as secondary** | `+ realized_volatility + release_session_BMO + sector fixed effects`; cannot overturn or rescue the primary | sector fixed-effect **encoding** unspecified | High | yes, for the secondary | **Yes** | before analysis |

## D. Data handling

| # | Element | Source | Status | Locked value | Gap | Sev. | Changes methodology? | Human decision | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| D1 | Missing-data handling | HYP-01 lock; counting rule CNT-4 | **LOCKED** | no imputation, no zero-fill, no winsorization, no outlier deletion | — | — | no | none | — |
| D2 | Abstention rules | market-response state machine | **LOCKED** | `PARTIAL` and `ABSTAIN_DATA_QUALITY` are terminal; a stage-specific `failure_stage` is persisted | — | — | no | none | — |
| D3 | Options unavailability | SPEC v0.2; cohort protocol; registry | **LOCKED** | lowers tier to `core_only_no_option_benchmark`; **never** removes an event from the core cohort; never becomes zero; no indicative substitution | — | — | no | none | — |
| D4 | Data-source failure handling | HYP-01 lock; round-1 correction overlay | **LOCKED** | a provider/schema failure is a **documented missing observation**; retrieval failure is never recorded as issuer-confirmed absence | — | — | no | none | — |
| D5 | Frozen event IDs | HYP-01 lock; freeze rules | **LOCKED (procedure)** | freeze the exact 60 IDs, then the environment, then verify gates, then run once | the ID set is **empty** — it does not exist until event 60 | — (expected) | no | none | at freeze |

## E. Multiplicity, stopping, and scope

| # | Element | Source | Status | Locked value | Gap | Sev. | Changes methodology? | Human decision | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| E1 | Secondary outcomes | HYP-01 lock §7; registry | **LOCKED** | `wiki_zscore` substitution, `abs_open_to_30m`, `abs_open_to_close`, `full_session_range`, sector-relative variants, rank-based GST — all non-confirmatory | some are `SPECIFIED_NOT_YET_EMITTED` | Medium | no | none | before analysis |
| E2 | Exploratory outcomes | registry; North Star §7 | **LOCKED as exploratory** | HYP-03 and the localization framework | HYP-03's measurement does not exist | High | no | none | — |
| E3 | Multiple-testing treatment | registry governance | **UNRESOLVED** | — | explicitly marked `PENDING_SEPARATE_ANALYSIS_LOCK`; no adjustment is specified across the three families | **Critical** | **yes** | **Yes — external methodologist.** One confirmatory hypothesis may need no adjustment, but that must be *decided*, not assumed | before freeze |
| E4 | Interim-analysis dates | display gates | **LOCKED — none permitted** | nothing may be displayed before the threshold: no estimate, direction, plot, interim p-value or CI | — | — | no | none | — |
| E5 | Stopping rule | HYP-01 lock; CNT-8 | **LOCKED** | **no optional stopping**; threshold is not re-checked for significance; collection is neither stopped early nor extended because of results | — | — | no | none | — |
| E6 | Extension cohort | CNT-9; freeze rules | **LOCKED** | post-freeze events are separately labelled and never enlarge the frozen set | — | — | no | none | — |
| E7 | Model-change rules | HYP-01 lock; governance | **LOCKED** | **no model change after the event set is frozen**; promotion to confirmatory may never be based on observed results | — | — | no | none | — |
| E8 | Development / holdout boundary | freeze procedure; North Star §10 | **PARTIALLY LOCKED** | freeze separates development from holdout | which **retrospective** artifacts may inform development is **implicit, not written** | High | possibly — if a past choice was informed by data now inside the holdout | **Yes** | before freeze |
| E9 | Analysis authorization | display gates; freeze rules | **LOCKED** | run the primary model **once**, after freeze + environment freeze + gate verification | who authorizes the run is not named | Medium | no | **Yes** — name the authorizing human | before analysis |

## F. Cross-cutting

| # | Element | Source | Status | Gap | Sev. | Human decision | Deadline |
|---|---|---|---|---|---|---|---|
| F1 | Exposure definition variants | HYP-01 lock unresolved list | **UNRESOLVED** | continuous form is locked; whether any transform (e.g. rank) is confirmatory is not | High | **Yes** | before freeze |
| F2 | HYP-02 divergence measure | registry unresolved list | **UNRESOLVED** | no authoritative definition of GST↔Wikipedia divergence; difference, ratio, rank gap and residual would give different answers | High | **Yes** | before HYP-02 activation |
| F3 | HYP-02 surprise field | registry | **UNRESOLVED** | EPS vs revenue not designated; sign handling unspecified | High | **Yes** | before HYP-02 activation |
| F4 | HYP-03 half-life definition | registry unresolved list | **UNRESOLVED** | source series, window, estimator, and behaviour on non-decaying series all undefined | High | **Yes** | before HYP-03 activation |
| F5 | Search-construct validity | — | **NOT AUDITED** | ticker→query mapping not formally justified; homonym risk unreviewed | High | **Yes** | before first observation |

---

## Summary

**Locked and sufficient: 28 elements.** The sample definition, primary hypothesis, predictor, outcome, model formula, alpha, missing-data handling, abstention, options treatment, stopping rule, interim-analysis prohibition and model-change rules are all fixed and reproducible from the repository.

**Requiring a human or external methodological decision: 11.**

| Blocking the **freeze** | Blocking **activation / publication** |
|---|---|
| C6 cluster-covariance estimator variant | F2 HYP-02 divergence measure |
| C7 finite-sample correction, at ~24 clusters | F3 HYP-02 primary surprise field |
| E3 multiple-testing treatment | F4 HYP-03 half-life definition |
| E8 development/holdout boundary, written down | F5 search-construct validity audit |
| F1 whether any predictor transform is confirmatory | B3 how retrospective figures may be cited |
| A9 whether a pre-data power analysis is performed | C9 sector fixed-effect encoding |
| B4 environment values (recorded at freeze, not chosen) | E9 named analysis authorizer |

**None of these is filled in by this document.** Three of them — C6, C7 and E3 — could each change whether HYP-01 is reported as significant. That is exactly why they must be resolved by a qualified human, in a dated lock, **before** the freeze, and never after seeing the data.
