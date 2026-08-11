# HYP-01 Statistical Method — Decision and Signoff Form (v1.0 TEMPLATE)

> **This is a blank template. Every field below is `PENDING`.**
>
> **No reviewer has been engaged. No review has taken place. No approval exists.** No name on this form has been supplied by its author, and none may be. `GST_HYP01_ANALYSIS_LOCK_v1.0` remains the authoritative lock until this form is completed by a real reviewer and countersigned.
>
> **Claude (Anthropic) authored the review packet and the proposed amendment and may not complete any field on this form.**

Complete this form only after reading:

- [`GST_HYP01_STATISTICAL_METHOD_REVIEW_PACKET_v1.0_DRAFT.md`](GST_HYP01_STATISTICAL_METHOD_REVIEW_PACKET_v1.0_DRAFT.md)
- [`GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED_DRAFT.md`](GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED_DRAFT.md) and its JSON
- [`GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md`](GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md) — the current authoritative lock

---

## 1. Reviewer

| Field | Entry |
|---|---|
| Reviewer name | `PENDING` |
| Affiliation | `PENDING` |
| Position / title | `PENDING` |
| Methodological qualifications relevant to cluster-robust inference | `PENDING` |
| Contact | `PENDING` |
| Review date | `PENDING` |

## 2. Conflict-of-interest statement

| Field | Entry |
|---|---|
| Any financial interest in this project or its outcomes? | `PENDING` |
| Any advisory, supervisory, or personal relationship with the project team? | `PENDING` |
| Any interest in a particular result being obtained? | `PENDING` |
| Statement | `PENDING` |

> A reviewer with no conflict should say so explicitly. Faculty supervision of the project team **is** a relationship and should be disclosed here rather than treated as absence of conflict.

## 3. Documents reviewed

| Document | Version / commit | Reviewed? |
|---|---|---|
| Method review packet | `PENDING` | `PENDING` |
| Proposed v1.1 lock (Markdown) | `PENDING` | `PENDING` |
| Proposed v1.1 lock (JSON) | `PENDING` | `PENDING` |
| Authoritative v1.0 lock | `PENDING` | `PENDING` |
| Hypothesis registry v1.0 | `PENDING` | `PENDING` |
| Eligibility and freeze rules v1.0 | `PENDING` | `PENDING` |
| Result display gates v1.0 | `PENDING` | `PENDING` |
| Preregistration gap audit v1.0 | `PENDING` | `PENDING` |
| Cohort protocol v1.1 | `PENDING` | `PENDING` |
| Other | `PENDING` | `PENDING` |

## 4. C6 — cluster-robust covariance estimator

**Proposed:** CV2 (bias-reduced linearization), clustered on `ticker`.

| Field | Entry |
|---|---|
| Approve as proposed? | `PENDING` |
| Reject? | `PENDING` |
| Approve with modification — specify | `PENDING` |
| If rejected or modified, which estimator, and why | `PENDING` |
| **Q2** — Should CV3 + `t(G−1)` be preferred instead, on simplicity/reproducibility grounds? | `PENDING` |
| Reasoning | `PENDING` |

## 5. C7 — finite-sample correction and reference distribution

**Proposed:** `t(ν)` with Satterthwaite / Bell–McCaffrey degrees of freedom computed from the realized design; α = 0.05 two-sided unchanged; realized `ν`, `G*` and the CV1 reference standard error all reported.

| Field | Entry |
|---|---|
| Approve as proposed? | `PENDING` |
| Reject? | `PENDING` |
| Approve with modification — specify | `PENDING` |
| Alternative df rule, if any | `PENDING` |
| Should realized `ν` be reported only, or also gate the analysis? | `PENDING` |
| Reasoning | `PENDING` |

## 6. E3 — multiplicity treatment

**Proposed:** no adjustment for the single HYP-01 primary confirmatory test; secondary and exploratory families reported with a predeclared non-confirmatory treatment.

| Field | Entry |
|---|---|
| Approve as proposed? | `PENDING` |
| Reject? | `PENDING` |
| Approve with modification — specify | `PENDING` |
| If adjustment required: which method | `PENDING` |
| If adjustment required: over what family | `PENDING` |
| Reasoning | `PENDING` |

## 7. C9 — sector fixed-effect encoding (secondary model) — *recommendation*

**Proposed:** sum (effects) coding; sectors from the existing frozen mapping; sparse-sector rule left open.

| Field | Entry |
|---|---|
| Recommendation | `PENDING` |
| Preferred coding | `PENDING` |
| Predeclared rule for sparse sectors | `PENDING` |
| Reasoning | `PENDING` |

## 8. Minimum-cluster / effective-degrees-of-freedom rule (NEW-1)

> **No threshold was proposed by the packet author, deliberately.** This section exists so a qualified reviewer can set one, or explicitly decline to.

| Field | Entry |
|---|---|
| Is such a rule needed? | `PENDING` |
| Trigger quantity (effective df · `G*` · tickers with ≥ 1 eligible event · max single-ticker share · other) | `PENDING` |
| **Threshold value** | `PENDING` |
| Consequence if breached (abstain · report as inconclusive with interval · proceed with predeclared caveat · other) | `PENDING` |
| Explicitly declining to set a rule? If so, why | `PENDING` |
| Reasoning | `PENDING` |

## 9. Wild cluster bootstrap — role

**Proposed:** labelled sensitivity analysis only; always reported; may not rescue or overturn the primary result.

| Field | Entry |
|---|---|
| Approve this role? | `PENDING` |
| Should it instead be primary? | `PENDING` |
| Variant (Rademacher 2-point · Webb 6-point · other) | `PENDING` |
| Restricted (WCR) or unrestricted | `PENDING` |
| Number of replications | `PENDING` |
| Seed policy | `PENDING` |
| Reasoning | `PENDING` |

## 10. Design sensitivity / power (A9)

> Constraints: must precede any prospective outcome; must use externally justified or clearly hypothetical effect sizes; must never use observed project results; must not silently revise the locked n = 60.

| Field | Entry |
|---|---|
| Recommended option (none · minimum-detectable-effect curve · externally-anchored power analysis · simulation-based · other) | `PENDING` |
| Effect sizes to use, and their external source | `PENDING` |
| Reasoning | `PENDING` |

## 11. Other questions from the packet

| Question | Entry |
|---|---|
| Q9 — concerns about the unbalanced ≤ 24-ticker / 60-event structure | `PENDING` |
| Q9 — should a per-ticker cap be considered? *(changes a locked sample element)* | `PENDING` |
| Implementation path — R/`clubSandwich` dependency vs validated Python CV2 | `PENDING` |
| Q11 — anything the packet gets wrong | `PENDING` |

## 12. Requested revisions

| Field | Entry |
|---|---|
| Revisions required before approval | `PENDING` |
| Revisions suggested but not required | `PENDING` |
| Re-review required after revision? | `PENDING` |

## 13. Final disposition

| Field | Entry |
|---|---|
| Disposition (approved as proposed · approved with the modifications above · rejected · revise and resubmit) | `PENDING` |
| Date | `PENDING` |
| Additional statement | `PENDING` |

## 14. Reviewer confirmation

| Field | Entry |
|---|---|
| Reviewer signature / confirmation | `PENDING` |
| Confirms the disposition in §13 is theirs | `PENDING` |
| Consents to being named in the repository? | `PENDING` |
| Consents to being named in any resulting publication? | `PENDING` |

> Reviewing this proposal implies **no endorsement of the project**, no authorship, and no public association. Naming requires explicit consent recorded above.

## 15. Project approval

| Field | Entry |
|---|---|
| Harshith Akurati — approve activation of the amended lock? | `PENDING` |
| Date | `PENDING` |
| Signature / confirmation | `PENDING` |
| Notes | `PENDING` |

## 16. Commit to be approved

| Field | Entry |
|---|---|
| Repository | `PENDING` |
| Branch | `PENDING` |
| Dated commit SHA containing the version being approved | `PENDING` |
| Proposed-lock JSON SHA-256 at that commit | `PENDING` |
| Proposed-lock Markdown SHA-256 at that commit | `PENDING` |
| Review-packet SHA-256 at that commit | `PENDING` |
| Activation commit SHA (created **after** signoff) | `PENDING` |

---

## Activation checklist — none of these may be ticked yet

- [ ] Methodologist decisions recorded for C6, C7, E3
- [ ] NEW-1 minimum-cluster / effective-df rule set, or explicitly declined
- [ ] C9 recommendation recorded
- [ ] Wild-bootstrap role, variant, replications and seed policy recorded
- [ ] Conflict-of-interest statement completed
- [ ] Reviewer confirmation recorded
- [ ] Harshith Akurati approval recorded
- [ ] Implementation path chosen, and the implementation validated against a published reference on synthetic fixtures only
- [ ] A separate dated commit activates the approved version and states what changed from v1.0 and why
- [ ] Registry updated to point at the activated version
- [ ] **All of the above completed BEFORE the first HYP-01-eligible prospective pre-event capture**

**Until every box is ticked, `GST_HYP01_ANALYSIS_LOCK_v1.0` is the authoritative lock and the proposed v1.1 has no standing.**
