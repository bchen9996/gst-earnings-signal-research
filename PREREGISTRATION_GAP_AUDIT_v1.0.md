# Preregistration Gap Audit — v1.0

**Status:** Audit only. **No methodology is changed and no missing value is invented.** Where a scientific decision is unresolved, it is marked as requiring human or external methodological review — filling it in from this document would be exactly the failure the audit exists to catch.

**Audited against** the repository at `main` = `133ee473918b3922f4040031aee8c8eb3c20992f`.

---

## How rows are classified

Every row carries a **Class**. The classes are disjoint and every row has exactly one.

| Class | Meaning | Count |
|---|---|---|
| `SCIENTIFIC_DECISION` | An unresolved scientific or publication decision. Requires a qualified human; changes what the study means. | **11** |
| `OPERATIONAL_FREEZE_RECORD` | A value that must be *recorded* at the freeze. Nobody chooses it on scientific grounds. | **1** |
| `OPERATIONAL_ASSIGNMENT` | An administrative assignment. Someone must be named; no scientific content. | **1** |
| `RESOLVED` | Locked and reproducible from a repository artifact. | **28** |
| | **Total rows** | **41** |

**Recording a value is not deciding one.** Earlier drafts of this audit counted the freeze record (B4) and the authorizer assignment (E9) alongside genuine scientific gaps, and separately mis-listed the predictor form (F1) as open when the HYP-01 lock had already fixed it. That inflated the apparent methodological debt. The three classes above keep them apart.

## Deadline vocabulary

| Token | Meaning |
|---|---|
| `BEFORE_PREREG_AND_FIRST_OBSERVATION` | Before an external preregistration is filed **and** before the first HYP-01-eligible prospective observation is captured — whichever comes first. Never resolvable using prospective outcome data. |
| `BEFORE_FIRST_OBSERVATION` | Before the first HYP-01-eligible prospective pre-event capture. |
| `BEFORE_HYP02_ACTIVATION` / `BEFORE_HYP03_ACTIVATION` | Before that hypothesis is activated for collection. |
| `BEFORE_SECONDARY_ANALYSIS` | Before the secondary adjusted model is run. |
| `AT_EVENT_60_FREEZE` | Recorded as part of the freeze step. |
| `BEFORE_ANALYSIS_RUN` | Before the single authorized primary-model run. |
| `BEFORE_PUBLICATION` | Before any external write-up. |

**Severity.** **Critical** = an unresolved value could change the confirmatory conclusion. **High** = affects interpretation or a secondary claim. **Medium** = affects reporting or reproducibility. **Low** = documentation.

---

## A. Sample definition

| # | Element | Source | Status | Class | Locked value | Gap | Sev. | Changes methodology? | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| A1 | Universe | `gst_market_response/constants.py` → `LOCKED_24_TICKER_UNIVERSE`; cohort protocol v1.1 | LOCKED | `RESOLVED` | 24 tickers, read from the production constant | — | — | no | — |
| A2 | Event eligibility | cohort protocol v1.1 INC-1…INC-10 | LOCKED | `RESOLVED` | regular quarterly/annual earnings; official IR/SEC source; explicit date; timing classifiable without inference | — | — | no | — |
| A3 | Inclusion / exclusion | cohort protocol v1.1 §5, §7.1 | LOCKED | `RESOLVED` | 12 dispositions; explicit list of reasons an event may **never** be excluded | — | — | no | — |
| A4 | Registration lead time | cohort protocol v1.1 | LOCKED | `RESOLVED` | **5 XNYS trading sessions** before the derived anchor | — | — | no | — |
| A5 | Collection window | cohort protocol v1.1 | LOCKED | `RESOLVED` | **2026-09-01 → 2027-05-31**, applied to the derived anchor | — | — | no | — |
| A6 | HYP-01 sample conditions | HYP-01 lock S-1…S-8 | LOCKED | `RESOLVED` | cohort-enrolled · core-class eligible · strict v0.2 core · D1 passed · `gst_zscore` with successful GST provenance · `abs_overnight_gap` non-null · `BMO`/`AMC` | — | — | no | — |
| A7 | Event ordering | HYP-01 lock `sample.ordering` | LOCKED | `RESOLVED` | derived response-session date ascending, tie-broken by `event_id` ascending | — | — | no | — |
| A8 | Sample size threshold | HYP-01 lock `sample.target_n`; registry | LOCKED | `RESOLVED` | **n = 60** (HYP-02 60, HYP-03 40) — a governance eligibility floor, explicitly *not* a power claim | — | — | no | — |
| A9 | Design sensitivity / power | registry `statistical_governance.power_statement` | **UNRESOLVED** | `SCIENTIFIC_DECISION` | — | no power or design-sensitivity analysis exists | Medium | **yes**, if it were used to revise n | `BEFORE_FIRST_OBSERVATION` |

**A9 constraints.** Any design-sensitivity or power analysis **must** occur before prospective outcomes exist; **must** use externally justified or clearly hypothetical effect sizes; **must never** use observed prospective project results; and **must not** silently change the locked `n = 60` threshold — a revision would require a new dated lock written before any outcome is seen. The registry already states that thresholds are governance eligibility floors, not power claims. *No power analysis is performed in this pass.*

## B. Timestamps and provenance

| # | Element | Source | Status | Class | Locked value | Gap | Sev. | Changes methodology? | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| B1 | Timestamps | pre-event capture provenance (15 fields) | LOCKED | `RESOLVED` | retrieval timestamps, `run_date`, `price_asof_date`, panel CSV/marker SHA-256, commit SHA, methodology version | — | — | no | — |
| B2 | Anchor derivation | `operations_plan.build_operations_plan`; XNYS calendar | LOCKED | `RESOLVED` | `sessions.pre_event_anchor.session_date`; never recomputed by hand | — | — | no | — |
| B3 | Citation policy for reconstructed retrospective results | status doc §1a; §3 | **UNRESOLVED** | `SCIENTIFIC_DECISION` | — | the retrospective population's point-in-time check is **failed**; no policy states whether, and with what caveat, any retrospective figure may be cited externally | **Critical** (publication) | no — governs citation, not the prospective design | `BEFORE_PUBLICATION` |
| B4 | Analysis environment record | HYP-01 lock `environment_freeze` | fields exist, all `TO_BE_FROZEN_AT_EVENT_60` | `OPERATIONAL_FREEZE_RECORD` | language version, statistics package, package version, cluster-covariance **option string**, finite-sample-correction **option**, random seed, analysis-code commit SHA | unset by design — the lock leaves them unset precisely so the freeze step must record them rather than let the environment drift | High (reproducibility) | **no** — recording, not choosing | `AT_EVENT_60_FREEZE` |

**B4 is not a scientific decision.** It records *which software expresses* a rule that C6 and C7 must already have fixed. If the rule is still open when the option string is recorded, the option string is choosing the statistics — which is why C6 and C7 carry an earlier deadline than B4.

## C. Hypothesis and outcome

| # | Element | Source | Status | Class | Locked value | Gap | Sev. | Changes methodology? | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| C1 | Primary hypothesis | HYP-01 lock `study_question` | LOCKED | `RESOLVED` | "Does higher abnormal pre-earnings Google-search attention associate with a greater absolute overnight earnings response?" | — | — | no | — |
| C2 | Primary predictor | HYP-01 lock `predictor` | LOCKED | `RESOLVED` | `gst_zscore`, continuous, unthresholded, at the pre-event anchor | — | — | no | — |
| C3 | Primary outcome | HYP-01 lock `primary_outcome` | LOCKED | `RESOLVED` | `abs_overnight_gap` = `abs(next_session_open / previous_close - 1)` | — | — | no | — |
| C4 | Model formula | HYP-01 lock `primary_model` | LOCKED | `RESOLVED` | `abs_overnight_gap ~ gst_zscore`, OLS, single RHS term | — | — | no | — |
| C5 | Alpha and sidedness | HYP-01 lock; registry governance | LOCKED | `RESOLVED` | **0.05**, two-sided | — | — | no | — |
| C6 | Ticker-cluster covariance estimator | HYP-01 lock `primary_model.covariance`; registry HYP-01 unresolved list | **UNRESOLVED** | `SCIENTIFIC_DECISION` | cluster-robust on `ticker` | the exact estimator variant (CR0 / CR1 / CR2 / CR3 or equivalent) is unspecified | **Critical** | **yes** | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |
| C7 | Finite-sample correction and inference procedure | HYP-01 lock `primary_model.covariance.finite_sample_correction` | **UNRESOLVED** | `SCIENTIFIC_DECISION` | the flag is enabled | *which* correction, and whether reference-distribution or wild-cluster-bootstrap inference is used, is unspecified; the small-cluster problem is real at ~24 clusters | **Critical** | **yes** | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |
| C8 | Covariates | HYP-01 lock `primary_model.covariates` | LOCKED | `RESOLVED` | none; `data_driven_covariates: false` | — | — | no | — |
| C9 | Sector fixed-effect encoding | HYP-01 lock `remaining_pending_decisions` | **UNRESOLVED** | `SCIENTIFIC_DECISION` | the adjusted sensitivity model is locked as **secondary** and can neither overturn nor rescue the primary | the sector fixed-effect encoding is `PENDING_SEPARATE_ANALYSIS_LOCK` | High | yes, for the secondary model only | `BEFORE_SECONDARY_ANALYSIS` |

## D. Data handling

| # | Element | Source | Status | Class | Locked value | Gap | Sev. | Changes methodology? | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| D1 | Missing-data handling | HYP-01 lock; counting rule CNT-4 | LOCKED | `RESOLVED` | no imputation, no zero-fill, no winsorization, no outlier deletion | — | — | no | — |
| D2 | Abstention rules | market-response state machine | LOCKED | `RESOLVED` | `PARTIAL` and `ABSTAIN_DATA_QUALITY` are terminal; a stage-specific `failure_stage` is persisted | — | — | no | — |
| D3 | Options unavailability | SPEC v0.2; cohort protocol; registry | LOCKED | `RESOLVED` | lowers tier to `core_only_no_option_benchmark`; **never** removes an event from the core cohort; never becomes zero; no indicative substitution | — | — | no | — |
| D4 | Data-source failure handling | HYP-01 lock; round-1 correction overlay | LOCKED | `RESOLVED` | a provider/schema failure is a **documented missing observation**; retrieval failure is never recorded as issuer-confirmed absence | — | — | no | — |
| D5 | Frozen event-ID procedure | HYP-01 lock `freeze_and_display.freeze_sequence` | LOCKED (procedure) | `RESOLVED` | freeze the exact 60 IDs → freeze the analysis commit and environment → verify all gates → run once | the ID set is empty until event 60; that is the procedure working, not a gap | — | no | — |

## E. Multiplicity, stopping, and scope

| # | Element | Source | Status | Class | Locked value | Gap | Sev. | Changes methodology? | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| E1 | Secondary analyses | HYP-01 lock `secondary_analyses` | LOCKED | `RESOLVED` | `wiki_zscore` substitution, `abs_open_to_30m`, `abs_open_to_close`, `full_session_range`, sector-relative variants, rank-based GST — none carries an independent confirmatory claim; none may redefine the primary outcome | some are specified-but-not-yet-emitted | Medium | no | — |
| E2 | Exploratory scope | registry; North Star §7 | LOCKED as exploratory | `RESOLVED` | HYP-03 and the localization framework are exploratory | HYP-03's measurement does not exist — tracked at F4, not here | — | no | — |
| E3 | Multiplicity treatment | registry `statistical_governance.multiplicity_note` | **UNRESOLVED** | `SCIENTIFIC_DECISION` | HYP-01 alone is confirmatory; HYP-02/03 carry no confirmatory claim | any adjustment across families is explicitly `PENDING_SEPARATE_ANALYSIS_LOCK`. One confirmatory hypothesis may well need no adjustment — but that must be **decided and written down**, not assumed by silence | **Critical** | **yes** | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |
| E4 | Interim analyses | HYP-01 lock `freeze_and_display`; display gates | LOCKED — none permitted | `RESOLVED` | before the threshold, only eligible-event count and status may be shown; effect estimate, direction, plot, interim p-value, confidence interval and informal description are all prohibited | — | — | no | — |
| E5 | Stopping rule | HYP-01 lock; CNT-8 | LOCKED | `RESOLVED` | optional stopping **prohibited**; repeated testing **prohibited**; collection is neither stopped early nor extended because of results | — | — | no | — |
| E6 | Extension cohort | HYP-01 lock `extension_cohort_rule`; CNT-9 | LOCKED | `RESOLVED` | events eligible after the freeze are separately labelled, never enlarge the frozen set, and never re-open the primary analysis | — | — | no | — |
| E7 | Model-change rule | HYP-01 lock; registry `promotion_rule` | LOCKED | `RESOLVED` | no model change after the event set is frozen; promotion to confirmatory may never be based on observed results | — | — | no | — |
| E8 | Development / confirmatory-cohort boundary | HYP-01 freeze rules; North Star §10 | **UNRESOLVED** | `SCIENTIFIC_DECISION` | the freeze procedure, extension-cohort rule and no-model-change rule are locked | no dated document states **which retrospective artifacts may inform development** without contaminating the confirmatory cohort. Currently implicit | High | possibly — writing it down may reveal that a past choice was informed by data now inside the cohort | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |
| E9 | Named analysis authorizer | HYP-01 lock `freeze_and_display`; display gates | procedure locked; person unnamed | `OPERATIONAL_ASSIGNMENT` | run the primary model **once**, after freeze + environment freeze + gate verification | no human is named as the authorizer of that single run | Medium | **no** | `BEFORE_ANALYSIS_RUN` |

## F. Cross-cutting

| # | Element | Source | Status | Class | Locked value | Gap | Sev. | Changes methodology? | Deadline |
|---|---|---|---|---|---|---|---|---|---|
| F1 | Predictor form and transforms | HYP-01 lock `predictor`; `secondary_analyses` | **LOCKED / RESOLVED** | `RESOLVED` | `gst_zscore`, **continuous, entered on its natural scale, unthresholded**; no data-driven cutoff, no winsorization, no outcome-informed transformation. **No transform is confirmatory.** A rank-based GST analysis is registered as exploratory/sensitivity only and cannot alter the confirmatory conclusion | none. The registry's earlier "continuous versus threshold form" entry was **superseded** by the HYP-01 lock, which fixed the form. The lock's only remaining rank-related item is the *definition of the rank sensitivity analysis*, which is secondary by construction | — | no | — |
| F2 | HYP-02 divergence measure | registry HYP-02 unresolved list | **UNRESOLVED** | `SCIENTIFIC_DECISION` | — | no authoritative specification defines GST↔Wikipedia divergence; difference, ratio, rank gap and residual would give different answers | High | yes, for HYP-02 | `BEFORE_HYP02_ACTIVATION` |
| F3 | HYP-02 surprise field and sign | registry HYP-02 unresolved list | **UNRESOLVED** | `SCIENTIFIC_DECISION` | a missing surprise is never proxied or zero-filled | which field is primary (EPS or revenue) and how sign is handled are undesignated | High | yes, for HYP-02 | `BEFORE_HYP02_ACTIVATION` |
| F4 | HYP-03 attention-decay definition | registry HYP-03 unresolved list | **UNRESOLVED** | `SCIENTIFIC_DECISION` | — | half-life source series, window, estimator, handling of non-decaying series, and "continued repricing" all undefined | High | yes, for HYP-03 | `BEFORE_HYP03_ACTIVATION` |
| F5 | Search-construct validity | — | **NOT AUDITED** | `SCIENTIFIC_DECISION` | — | no documented ticker→query mapping justification; homonym/ambiguity risk unreviewed (e.g. `GME`, `STZ`, `BKR`); Trends' own revision behaviour undocumented | High | yes — a query-term change changes the signal | `BEFORE_FIRST_OBSERVATION` |

---

## What may be settled late, and what may not

This is the distinction the earlier draft of this audit got wrong.

| | May be fixed at the event-60 freeze | Must be fixed **before** the first prospective observation |
|---|---|---|
| **Statistical decision rule** | — | **C6** estimator variant · **C7** finite-sample correction and inference procedure · **E3** multiplicity treatment · **E8** development boundary |
| **Which events** | the exact 60 event IDs (**D5**) | the eligibility rules that select them (already locked, A2–A7) |
| **Software** | package, version, option strings, seed, analysis-code commit (**B4**) | — |
| **Construct** | — | **F5** search-construct validity |
| **Design sensitivity** | — | **A9**, on externally justified or hypothetical effect sizes only |

**Analysis code may be written after the rule is fixed** — but only if it mechanically implements the already-fixed rule, and only if it is tested exclusively on synthetic fixtures or explicitly permitted historical material. Code is an implementation of a decision, never the place a decision gets made.

**A study cannot call itself preregistered while its primary estimator and inference procedure are still open.** C6, C7, E3 and E8 therefore cannot wait for event 60.

> **Required lock amendment, not made in this pass.** The HYP-01 lock currently schedules `cluster_covariance_option_string` and `finite_sample_correction_option` as `TO_BE_FROZEN_AT_EVENT_60`, and its `remaining_pending_decisions` bundles the option string together with package and version. This audit recommends splitting that bundle: the **statistical rule** (C6, C7) resolves before the first observation; the **software option string that expresses it** (B4) is recorded at the freeze. Making that split requires a new dated lock version authored by a human. **This audit does not make it, and no scientific artifact is modified by this document.**

## Two deadlines, often confused

| | Date | What it is | What it is not |
|---|---|---|---|
| **Next screening sweep** | **Monday 2026-08-10, 09:00 America/Chicago** | The next authorized candidate-screening pass under cohort protocol v1.1 | It analyzes no outcome, and it does **not** discharge any decision in this audit |
| **Statistical-rule deadline** | **Before the first prospective HYP-01 pre-event capture** — the DELL anchor falls in the 2026-09-01 → 2027-05-31 window | The point by which C6, C7, E3, E8, F5 and A9 must be settled for a defensible preregistration | It is not the event-60 freeze, and it is not moved by a screening sweep finding nothing |

A sweep that enrolls a candidate brings the capture deadline closer. It never pushes it back.

---

## Summary

**41 rows. Every row has exactly one class.**

### 11 unresolved scientific / publication decisions

| # | Decision | Deadline |
|---|---|---|
| **A9** | Whether to perform a pre-data power / design-sensitivity analysis | `BEFORE_FIRST_OBSERVATION` |
| **B3** | Policy governing citation of retrospective reconstructed results | `BEFORE_PUBLICATION` |
| **C6** | Exact ticker-cluster covariance estimator | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |
| **C7** | Exact finite-sample correction / inference procedure | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |
| **C9** | Sector fixed-effect encoding for the secondary adjusted model | `BEFORE_SECONDARY_ANALYSIS` |
| **E3** | Multiplicity treatment | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |
| **E8** | Written boundary between development material and the confirmatory cohort | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |
| **F2** | HYP-02 divergence definition | `BEFORE_HYP02_ACTIVATION` |
| **F3** | HYP-02 surprise-field and sign definition | `BEFORE_HYP02_ACTIVATION` |
| **F4** | HYP-03 attention-decay definition | `BEFORE_HYP03_ACTIVATION` |
| **F5** | Search-construct validity audit | `BEFORE_FIRST_OBSERVATION` |

**Three of these — C6, C7 and E3 — could each change whether HYP-01 is reported as significant.** That is why they must be resolved by a qualified human, in a dated lock, before any prospective observation, and never after seeing data.

### Operational freeze fields still to be recorded

**B4**, at the event-60 freeze: language version · statistics package · package version · cluster-covariance option string · finite-sample-correction option · random seed · analysis-code commit SHA. **Recording these is not a scientific decision** — the rule they express must already be fixed by C6 and C7.

### Analysis authorizer still to be assigned

**E9**: one named human must be recorded as authorizing the single primary-model run, before that run. Administrative, not methodological.

### Resolved

**28 rows** are locked and reproducible from repository artifacts — including **F1**, the predictor form, which the HYP-01 lock fixed as continuous, natural-scale and unthresholded, with no confirmatory transform.

---

## Consistency invariant

This document is self-checking. A reader or script may verify:

1. Every row in tables A–F carries exactly one `Class` from the four defined values.
2. `SCIENTIFIC_DECISION` rows number **11**, and their IDs are exactly {A9, B3, C6, C7, C9, E3, E8, F2, F3, F4, F5} — matching the summary table above, row for row.
3. `OPERATIONAL_FREEZE_RECORD` rows number **1** — {B4}.
4. `OPERATIONAL_ASSIGNMENT` rows number **1** — {E9}.
5. `RESOLVED` rows number **28**, and F1 is among them.
6. `11 + 1 + 1 + 28 = 41` = the total row count.
7. C6, C7, E3 and E8 all carry `BEFORE_PREREG_AND_FIRST_OBSERVATION`; F5 and A9 carry `BEFORE_FIRST_OBSERVATION`; B4 carries `AT_EVENT_60_FREEZE`; E9 carries `BEFORE_ANALYSIS_RUN`.
8. No row classed `SCIENTIFIC_DECISION` carries a deadline of `AT_EVENT_60_FREEZE`.

**None of the eleven decisions is filled in by this document.**
