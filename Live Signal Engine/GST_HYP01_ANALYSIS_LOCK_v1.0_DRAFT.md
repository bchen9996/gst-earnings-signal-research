# HYP-01 Primary Analysis Lock — v1.0 (DRAFT)

**Status:** Draft preregistration, written **before any candidate screening and before any prospective observation**. Authored 2026-08-09 (UTC).
**Canonical machine-readable form:** `GST_HYP01_ANALYSIS_LOCK_v1.0.json` — a mechanical test enforces agreement.
**Companions:** `GST_HYP01_ELIGIBILITY_AND_FREEZE_RULES_v1.0.md` · `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0_DRAFT.md` · `GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0_DRAFT.md`

**No model was implemented and none was run.** No coefficient, confidence interval, p-value, direction, plot or informal description exists for HYP-01. Eligible events: **0**.

---

## 1. Study question

> Does higher abnormal pre-earnings Google-search attention associate with a greater absolute overnight earnings response?

## 2. Sample

An event enters the **primary** HYP-01 analysis only if **all** hold:

| # | Condition | Mechanised by |
|---|---|---|
| S-1 | enrolled under the prospective cohort protocol v1.0 | cohort protocol |
| S-2 | eligible for `core_attention_vs_equity_response` | `completeness.is_eligible_for_hypothesis` |
| S-3 | strict v0.2 core passed | `completeness.evaluate_strict_core_v0_2` |
| S-4 | D1 capture passed | `completeness.is_valid_d1_decomposition` |
| S-5 | `gst_zscore` non-null with a successful GST source status (`ok` / `ok_recent_cache_fallback`) | `source_status_gst` |
| S-6 | `abs_overnight_gap` non-null with valid market-data provenance | §4 |
| S-7 | release session is **`BMO`** or **`AMC`** | `identity.determine_release_market_session` |
| S-8 | among the **first 60** eligible events in the deterministic order below | §2.2 |

### 2.1 `INTRADAY` — measurement incompatibility, not exclusion

`INTRADAY` releases **remain enrolled in the overall cohort**. They are ineligible for *this* primary analysis only, because the overnight-gap outcome is not temporally aligned with a release that occurs during the session it would be measured across — the "overnight" window would straddle, rather than follow, the information event.

This rule is fixed **now, before any data exists**. It is a measurement incompatibility, not a post-hoc exclusion, and it implies nothing about those events. They remain fully eligible for the cohort and for any analysis whose outcome *is* aligned with an intraday release.

### 2.2 Deterministic ordering for "first 60"

1. **primary key** — mechanically derived response-session date, ascending (`exchange_calendar.compute_expected_next_full_trading_session_xnys`);
2. **tie-breaker** — `event_id`, ascending.

Both keys are fixed before any event exists and neither depends on an observed value, so **the identity of the first 60 cannot be influenced by results**.

## 3. Predictor

**`gst_zscore`**, measured at the pre-event anchor.

- **continuous**, entered on its natural scale;
- **unthresholded** — no high/low attention binning;
- **no data-driven cutoff**;
- **no winsorization**;
- **no outcome-informed transformation**.

**Wikipedia is not a co-primary predictor.** Any `wiki_zscore` analysis is secondary and **cannot change the HYP-01 confirmatory conclusion**.

## 4. Primary outcome — `abs_overnight_gap`

`abs_overnight_gap = abs(overnight_gap)`, where `overnight_gap = next_session_open / previous_close − 1`.

**No new return formula is created.** Both are already authoritative: the signed interval is defined in SPEC v0.1 and implemented as `derivations.overnight_gap`; the `abs_*` counterpart is defined in SPEC v0.1 ("`abs()` of the corresponding signed return, stored alongside it, never replacing it") and in field dictionary v0.1, with `derivations.abs_or_none` as the implemented helper.

### 4.1 Persistence gap — stated plainly

**`abs_overnight_gap` is specified but not yet emitted.** `completeness.D1_REQUIRED_FIELDS` lists only the four *signed* intervals, and no module currently writes an `abs_*` key into a D1 record. The formula is fixed and authoritative; what does not yet exist is the capture path that persists it.

Emitting it is a **separate build task, not performed here**. This lock names the specified field rather than inventing one or substituting a different return, and records the gap as **blocking for freeze**: event 60 cannot be frozen until `abs_overnight_gap` is actually persisted with valid provenance.

## 5. Primary model — locked

```
abs_overnight_gap ~ gst_zscore
```

| | |
|---|---|
| Estimator | ordinary least squares |
| Coefficient of interest | `gst_zscore` |
| Null | `β_gst = 0`, **two-sided** |
| α | **0.05** |
| Covariance | **cluster-robust, clustered on `ticker`**, **finite-sample correction enabled** |
| Effect reported as | change in absolute overnight return per one-unit increase in GST z-score |
| Reported quantities | coefficient · 95% confidence interval · p-value · eligible-event count · unique-ticker count |

The primary model has **exactly one right-hand-side term**. No covariate may be added, removed or selected on the basis of observed data.

### 5.1 Environment freeze

The exact language version, statistics package and version, cluster-covariance option string, finite-sample-correction option, any random seed, and the analysis-code commit SHA **must be frozen in the analysis artifact before results run**. They are deliberately unset today because no analysis code exists — leaving them unset is what forces the freeze step to record them rather than letting the environment drift silently.

**No analysis runner is implemented in this task, and the model is not run.**

## 6. Prespecified adjusted sensitivity model — secondary only

```
abs_overnight_gap ~ gst_zscore + realized_volatility + release_session_BMO + sector fixed effects
```

- **not co-primary**;
- **cannot overturn** a primary null result and **cannot rescue** one;
- uses the existing pre-event `realized_volatility` field (a strict-core member);
- uses the existing release-session classification and the existing `sector_mapping` module;
- **`panel_implied_volatility` must not be used** as an implied-move benchmark or a substitute for one — SPEC v0.1 §5's prohibition is unchanged;
- same ticker-clustered, finite-sample-corrected covariance.

## 7. Other secondary / exploratory analyses

Registered as **non-confirmatory**. None receives an independent confirmatory claim, and none may redefine the primary outcome.

| Analysis | Label | Note |
|---|---|---|
| `wiki_zscore` replacing GST | secondary | |
| `abs_open_to_30m` as outcome | secondary | specified, not yet emitted |
| `abs_open_to_close` as outcome | secondary | specified, not yet emitted |
| `full_session_range` as outcome | secondary | `derivations.full_session_range` implemented |
| sector-relative response fields | secondary | `derivations.relative_return` implemented; SPEC v0.1 lists these as **optional** for the D1/D3 gates and no capture path emits them yet |
| rank-based GST sensitivity | exploratory | rank transform definition still `PENDING_SEPARATE_ANALYSIS_LOCK` |

## 8. Missingness and exclusions

- **No imputation. No zero-fill. No winsorization. No outlier deletion.**
- No removal based on effect direction, magnitude, earnings surprise, news, options availability, or a value appearing to be an outlier.
- A provider or schema failure remains a **documented missing observation** — never imputed, never silently dropped.
- An event that fails HYP-01 eligibility **remains in the enrollment audit** even though it is ineligible for this analysis.
- One `event_id` counts **once**; duplicate ticker/fiscal-quarter records never count twice.
- **DELL receives no exemption** — `EVT-DELL-FY27Q2-ERN` is subject to every rule here identically.

## 9. Freeze and display

**Before 60 eligible events:** display the **count** and **status** only. No effect estimate, direction, plot, interim p-value, confidence interval or informal description.

**When event 60 becomes eligible:**

1. freeze the exact 60 event IDs;
2. freeze the analysis-code commit and environment;
3. verify all gates;
4. run the primary model **once**.

Later events enter a **separately labelled extension cohort**; they never enlarge the frozen set and never re-open the primary analysis. **No optional stopping. No repeated testing. No model change after the freeze.**

## 10. What this lock does not touch

HYP-02 and HYP-03 keep their thresholds (60, 40), their `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` statuses, their missing-measurement classifications and their unresolved analysis choices. The cohort protocol, the v0.2 completeness gates and every interval formula are unchanged.

## 11. Still pending

| Decision | State |
|---|---|
| exact statistics package, version and cluster-covariance option string | `TO_BE_FROZEN_AT_EVENT_60` |
| sector fixed-effect encoding for the adjusted model | `PENDING_SEPARATE_ANALYSIS_LOCK` |
| rank transform definition for the rank-based sensitivity | `PENDING_SEPARATE_ANALYSIS_LOCK` |
| **`abs_overnight_gap` persistence into the D1 record** | **blocking for freeze — separate build task** |
