# HYP-01 Eligibility and Freeze Rules — v1.0

Operational companion to `GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md`. This is the procedure an operator follows; the lock is the contract it enforces.

**Current state: 0 eligible events. Gate CLOSED. Nothing frozen.**

---

## 1. The eligibility decision, in order

Evaluate each candidate event against S-1…S-8. Every check is mechanical; none consults an observed outcome.

| Step | Check | Pass | Fail → disposition |
|---|---|---|---|
| 1 | enrolled under cohort protocol v1.0 | continue | `NOT_ENROLLED` |
| 2 | `is_eligible_for_hypothesis(core_attention_vs_equity_response, …)` | continue | `CLASS_INELIGIBLE` |
| 3 | `evaluate_strict_core_v0_2(...).passed` | continue | `CORE_GATE_FAILED` |
| 4 | `is_valid_d1_decomposition(...)` | continue | `D1_GATE_FAILED` |
| 5 | `gst_zscore` non-null **and** `source_status_gst` ∈ {`ok`, `ok_recent_cache_fallback`} | continue | `GST_PROVENANCE_FAILED` |
| 6 | `abs_overnight_gap` non-null with valid market-data provenance | continue | `OUTCOME_MISSING` |
| 7 | release session ∈ {`BMO`, `AMC`} | continue | `MEASUREMENT_INCOMPATIBLE_INTRADAY` |
| 8 | rank ≤ 60 in the deterministic order | **ELIGIBLE** | `EXTENSION_COHORT` |

Every disposition is **recorded**. An event that fails any step stays in the enrollment audit trail; nothing is silently dropped.

## 2. Ordering

```
sort key = (response_session_date ASC, event_id ASC)
```

`response_session_date` comes from `exchange_calendar.compute_expected_next_full_trading_session_xnys(earnings_date, release_market_session)` — the production function. It is never recomputed by hand and never adjusted.

Both keys are fixed before any event exists and neither reads an observed value, so **the membership of the first 60 cannot be steered by results**. Two events sharing a response session are ordered by `event_id` byte-wise ascending — deterministic and independent of collection order, machine, or run.

## 3. What may be displayed before the freeze

| Allowed | Prohibited |
|---|---|
| eligible-event count | effect estimate |
| per-event disposition | direction ("looks positive") |
| unique-ticker count | plot or chart |
| which gates a failing event failed | interim p-value |
| the lock and these rules themselves | confidence interval |
| | informal description of any pattern |

**The count is not a result.** Progress is public; findings are gated.

## 4. Blocking prerequisite

`abs_overnight_gap` is specified in SPEC v0.1 but **not yet emitted** by the D1 capture path — `D1_REQUIRED_FIELDS` holds only the four signed intervals. Step 6 therefore cannot pass for any event until that field is persisted with valid provenance.

**Event 60 cannot be frozen until this exists.** Building it is a separate, authorised task. Until then HYP-01 accrues 0 eligible events, and that is the honest state — not a failure to report.

## 5. Freeze procedure

Triggered exactly once, when the 60th event becomes eligible:

1. **Freeze the event set.** Enumerate the 60 `event_id`s mechanically in the §2 order. Write them, with each event's response-session date and ticker, to an immutable artifact. Hash it.
2. **Freeze the environment.** Record the language version, statistics package and version, the exact cluster-covariance option string, the finite-sample-correction option, any random seed, and the analysis-code commit SHA into `GST_HYP01_ANALYSIS_LOCK_v1.0.json`'s `environment_freeze` block. All are `TO_BE_FROZEN_AT_EVENT_60` until this step.
3. **Verify all gates.** Re-run S-1…S-8 for all 60 and confirm each passes. Any failure aborts the freeze; nothing is written and nothing is run.
4. **Run the primary model once.** `abs_overnight_gap ~ gst_zscore`, OLS, ticker-clustered with finite-sample correction, two-sided, α = 0.05. Report coefficient, 95% CI, p-value, eligible-event count and unique-ticker count.

Steps 1–3 complete **before** step 4. The order is the point: the event set and the code are fixed before anyone can see what the answer would be.

## 6. After the freeze

- Events becoming eligible later join a **separately labelled extension cohort**. They never enlarge the frozen 60 and never re-open the primary analysis.
- **No optional stopping.** The threshold is not re-checked for significance; collection is neither stopped early nor extended because of what results look like.
- **No model change after the freeze** — not the estimator, not the covariance, not the covariate set, not the outcome.
- The primary model runs **once**. A re-run is permitted only to reproduce the identical frozen inputs bit-for-bit, and produces the identical output.

## 7. Corrections

If an error is found after the freeze, it is recorded as a **dated amendment alongside** the frozen artifact — never as an edit to it. A corrected analysis is a new, separately labelled result that discloses the original. Frozen bytes are never rewritten.

## 8. DELL

`EVT-DELL-FY27Q2-ERN` passes through §1 identically to every other event. It receives no exemption, no priority, and no special case, and it counts once or not at all.
