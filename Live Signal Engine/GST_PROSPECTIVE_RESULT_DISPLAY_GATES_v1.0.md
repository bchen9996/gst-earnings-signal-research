# GST Prospective Result-Display Gates — v1.0

Companion to `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0_DRAFT.md` and its canonical JSON.

This document states **what may be shown, to whom, and when**. It supersedes nothing: the cohort protocol's `display_gate` (default `DENY`, status `NOT_YET_REGISTERED`) pointed here, and these are the numbers it was waiting for.

**Every gate below is currently CLOSED.** No hypothesis has any eligible events.

---

## 1. The gate

For each hypothesis, a result may be displayed **only** when **all** of the following hold:

1. the hypothesis status is `ACTIVE_COLLECTING`;
2. the count of **eligible** events (counting rules CNT-1…CNT-10) is **≥ its registered threshold**;
3. the eligible event-ID set has been **frozen**, together with the analysis-code commit, **before** any result was calculated;
4. every `PENDING_SEPARATE_ANALYSIS_LOCK` decision for that hypothesis has been resolved in a **dated analysis lock written before the freeze**.

Failing any one of these, the gate is **CLOSED**. A closed gate is not a soft warning: the result must not be computed for casual inspection, previewed, plotted, described in prose, summarised as a direction, or mentioned as "looking promising".

## 2. Current status

| Hypothesis | Threshold | Eligible now | Status | Gate |
|---|---|---|---|---|
| HYP-01 | 60 | 0 | `ACTIVE_COLLECTING` | **CLOSED** |
| HYP-02 | 60 | 0 | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` | **CLOSED** |
| HYP-03 | 40 | 0 | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` | **CLOSED** |
| `options_implied_move` (class) | — | — | no registered hypothesis | **`DENY_NO_REGISTERED_HYPOTHESIS`** |
| `joint_attention_plus_options` (class) | — | — | no registered hypothesis | **`DENY_NO_REGISTERED_HYPOTHESIS`** |

## 3. What "display" covers

All of the following are displays and are equally gated:

- a p-value, test statistic, confidence interval or effect estimate;
- a direction ("higher attention appears to precede larger moves");
- a plot, chart, scatter, table of group means, or dashboard tile;
- a correlation, regression coefficient, or model summary;
- a count-with-implication ("18 of 22 moved in the expected direction");
- a verbal summary in a report, commit message, PR body, changelog, or conversation.

The **eligible event count itself is not a result** and may be displayed at any time. So may the registry, the thresholds, the statuses, and the list of unresolved decisions. Progress is public; findings are gated.

## 4. Fail-closed defaults

| Condition | Gate |
|---|---|
| Hypothesis not registered | **DENY** |
| Registered but status is `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` | **DENY** |
| Registered, `ACTIVE_COLLECTING`, below threshold | **DENY** |
| At threshold, event set not frozen | **DENY** |
| At threshold, frozen, but a `PENDING_SEPARATE_ANALYSIS_LOCK` decision is unresolved | **DENY** |
| Eligible count unknown or not mechanically derivable | **DENY** |

Absence of a rule is never read as permission.

## 5. Freeze procedure

When a hypothesis first reaches its threshold:

1. enumerate the eligible `event_id` set mechanically from the gates, and record it;
2. record the analysis-code commit SHA;
3. record the resolved analysis lock (every `PENDING_SEPARATE_ANALYSIS_LOCK` decision, dated, written before this step);
4. hash and append all three, immutably — **then** compute results.

Any event that qualifies afterwards belongs to the **extension cohort** (CNT-9) and is reported separately. The frozen set is never retroactively enlarged, and the model is never changed after the freeze (§5 of the registry).

## 6. What these numbers are not

**60 / 60 / 40 are governance eligibility floors, not power calculations.** They state the minimum evidence required before anyone is allowed to look. They are not claims of statistical power, not minimum detectable effect sizes, and not guarantees that a result at that n will be meaningful. No power calculation was performed, and none may be performed using observed project results.

Reaching a threshold licenses **looking**, not **concluding**.

## 7. No trading interpretation

Nothing in this registry or these gates produces, evaluates or implies a trading rule, return forecast, signal ranking, or buy/sell recommendation. A gate opening means a measurement may be reported — never that a strategy is validated.
