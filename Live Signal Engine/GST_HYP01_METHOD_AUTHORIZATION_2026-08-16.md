# HYP-01 Statistical-Method Authorization — 2026-08-16

> **Dated authorizer amendment for HYP-01 statistical rules. No prospective outcome was inspected, F5 remains OPEN, and collection remains blocked.**

## The authorization

> **"I authorize the recommended D1–D16 methodological package as specified on August 16, 2026."**

| | |
|---|---|
| **Authorizer role** | Project authorizer / repository owner |
| **Declared authorization date** | 2026-08-16 |
| **Date basis** | user-declared UTC calendar date |
| **Recorded at** | 2026-08-16T03:57:18Z |
| **Scope** | HYP-01 statistical rules D1–D16 only |

**What this authorization is not.** The authorizer is the project owner, not an independent statistician or methodologist. **No external peer review, methodological review, institutional approval or reviewer sign-off has occurred**, and none is claimed. No handwritten signature exists. No reviewer identity is recorded, because there is no reviewer.

**On the date.** 2026-08-16 is a **UTC calendar date supplied by the authorizer**. This record does not assert that the authorization occurred on 2026-08-16 in America/Chicago or any other local timezone — at the recorded UTC instant the local civil date was 2026-08-15. The git commit and push timestamps, preserved separately by version control, record when the amendment entered history.

## What informed the decision

| Evidence | What it established |
|---|---|
| PR #17 feasibility study | Which estimators could be implemented reproducibly; CR1 over-rejects in all four null cells tested; five prespecified refusal thresholds |
| PR #18 R-reference validation | The study's CR2/Satterthwaite code agrees with clubSandwich 0.7.0 on a synthetic fixture matrix |
| Proposed v1.1 (non-authoritative) | A prior proposal, considered as input only |

**Implementation validation is not scientific proof.** PR #18 showed the Python code computes what clubSandwich computes on synthetic fixtures. That is implementation agreement — not evidence that CR2 is the scientifically correct or optimal estimator for HYP-01, and not a result about the world.

**Split tolerance provenance, carried forward.** CR2 covariance, standard error, t-statistic and p-value were validated under the **PR #17** tolerances. The continuous **Satterthwaite degrees of freedom** were validated under a **separately prespecified PR #18 tolerance that was not preregistered in PR #17**. That distinction travels with every citation of the result, including this one.

## No outcome was inspected

At the moment of authorization: `results` is null, `frozen_event_ids` is empty, `eligible_events_now` is 0, and `screening_rows` is empty. **Zero HYP-01-eligible prospective observations existed.** There was no effect estimate, direction, p-value, interim result or plot to inspect, and none was inspected.

## Proposed → authorized → effective

| ID | Proposed input | Authorizer-selected choice | Effective amendment field | Implementation status | Remaining blocker |
|---|---|---|---|---|---|
| D1 | CR2/BRL favoured, blocked at the time | **CR2 bias-reduced linearization**, official path R 4.6.1 + clubSandwich 0.7.0 | `decisions.D1` | Validated (split provenance) | F5; pre-observation gates |
| D2 | BRL built into CR2 | **BRL only** — no CR1 scaling, no second correction | `decisions.D2` | Validated | same |
| D3 | Satterthwaite | **Coefficient-specific Satterthwaite**, realized df persisted | `decisions.D3` | Agreement under the **PR #18** df tolerance | same |
| D4 | Sensitivity-only bootstrap | **Not used in HYP-01** | `decisions.D4` | N/A | — |
| D5–D7 | Weights / repetitions / seed | **Not applicable**, no activatable placeholder retained | `decisions.D5–D7` | N/A | — |
| D8 | Report singletons | **Retain singletons**, report counts and realized df | `decisions.D8` | Rule only | same |
| D9 | Refuse and abort | **Refuse and abort**, thresholds adopted verbatim from the committed runner | `decisions.D9` | Thresholds pre-existing | same |
| D10 | No invented cutoff | **Report without threshold** | `decisions.D10` | Rule only | same |
| D11 | Freeze package/version | **R official, Python cross-check**, freeze eight items at event 60 | `decisions.D11` | Environment pinned | freeze not yet performed |
| D12 | Treatment coding | **Treatment/reference coding**, deterministic reference, secondary model only | `decisions.D12` | Rule only | secondary model unbuilt |
| D13 | Pool sparse sectors | **Pool < 3 eligible events into OTHER**, from counts only | `decisions.D13` | Rule only | cohort not frozen |
| D14 | No cap | **No per-ticker cap** | `decisions.D14` | Rule only | same |
| D15 | Single primary test | **No multiplicity adjustment**, family = 1 predictor / 1 outcome / 1 test / α = 0.05 two-sided | `decisions.D15` | Rule only | same |
| D16 | 60 as floor | **No project-derived power claim**; 60 is a governance floor | `decisions.D16` | Rule only | same |

## Effective state

| Dimension | Status |
|---|---|
| Statistical package | **AUTHORIZED** |
| Implementation | **VALIDATED** (implementation agreement, not scientific proof) |
| F5 construct validity | **STILL OPEN** |
| Prospective collection | **STILL BLOCKED** |
| Scientific result | **NONE** |
| Analysis | **NOT RUN** |
| External preregistration | **NOT PERFORMED** |

**Why collection is still blocked.** Authorizing the statistical package removes one gate. It does not remove the others. Collection may begin only when F5 construct validity is resolved and recorded, every other pre-observation gate in the cohort protocol and eligibility rules is satisfied, and the event-60 environment freeze required by D11 is recorded.

**External preregistration has not occurred.** Completing this internal lock does not make the study externally preregistered — that requires actual submission to an external timestamped registry, which has not happened.

## Authority

The **dated amendment** `GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-08-16.json` is the authoritative statistical-rule overlay once merged. `GST_HYP01_ANALYSIS_LOCK_v1.0.json` remains the base lock and every rule it states that the amendment does not list remains operative verbatim. `GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json` remains a **historical, non-authoritative proposal** and takes no part in resolving the effective lock.

Resolve the effective lock with:

```
python tools/hyp01_effective_lock/resolve_effective_lock.py --check
```

It fails closed and emits nothing if any artifact is missing, any hash drifts, more than one amendment claims a field, an amended field is absent, an unamended field drifts, the authorization statement or date is missing, the authorizer role is misrepresented, F5 is marked closed, bootstrap settings become active, CR3 is selected, CR1 becomes primary, package versions drift, the R/Python roles are reversed, sector pooling reads outcomes, a ticker cap appears, alpha or sidedness changes, or n = 60 is described as empirically powered.
