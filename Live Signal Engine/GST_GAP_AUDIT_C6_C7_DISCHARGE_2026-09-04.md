# Gap audit C6 and C7 — discharge record

**Date:** 2026-09-04
**Status:** recognition record. **Decides nothing.** Every decision it cites was
made on 2026-08-16 by the repository owner in a dated amendment.
**Modifies no scientific artifact.**

---

## 1. What this is, and what it deliberately is not

`PREREGISTRATION_GAP_AUDIT_v1.0.md` lists **C6** (ticker-cluster covariance
estimator) and **C7** (finite-sample correction and inference procedure) as
`UNRESOLVED`, severity **Critical**, deadline
`BEFORE_PREREG_AND_FIRST_OBSERVATION`, both flagged as able to *"change whether
HYP-01 is reported as significant."*

**They are already resolved.** They were resolved in
`GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-08-16.json`, a dated amendment authored
by the repository owner before any prospective observation — exactly the
instrument the audit itself demands (*"a new dated lock version authored by a
human"*). The audit reports them open because it reads the **base lock**'s
`primary_model.covariance` block and **registry v1.0**'s
`unresolved_analysis_decisions`, and the amendment is an **append-only overlay**
that rewrites neither in place.

So this document is a **recognition**, not a decision. It records where the
answer already lives. Nothing here may be read as choosing an estimator: that
choice has a date, an author, and an authorization statement, all of 2026-08-16,
and this record does not and cannot move them.

## 2. Where each decision actually lives

| Audit item | Decision | Selected value |
|---|---|---|
| **C6** — estimator variant | `decisions.D1.selected` | `CR2_BIAS_REDUCED_LINEARIZATION` |
| **C6** — cluster variable | base lock `primary_model.covariance.cluster_variable`, held by the resolver's `UNAMENDED_INVARIANTS` | `ticker` |
| **C7** — finite-sample correction | `decisions.D2.selected` | `BRL_ADJUSTMENT_BUILT_INTO_CLUBSANDWICH_CR2`, with `additional_cr1_scaling_applied: false` and `second_correction_applied: false` |
| **C7** — reference distribution | `decisions.D3.selected` | `COEFFICIENT_SPECIFIC_SATTERTHWAITE` |
| **C7** — bootstrap question | `decisions.D4.selected` | `NOT_USED_IN_HYP01` (`is_primary: false`, `is_sensitivity: false`, `may_overturn_primary: false`) |

C7's audit text asks specifically *"whether reference-distribution or
wild-cluster-bootstrap inference is used."* D3 and D4 answer both halves: the
reference distribution is coefficient-specific Satterthwaite, and the wild
cluster bootstrap is **not used in HYP-01** — not as primary, not as
sensitivity, and it may not overturn the primary.

The authoritative calculation is recorded in `decisions.D11`: **R 4.6.1 +
`clubSandwich` 0.7.0**, `vcovCR(fit, cluster = <ticker factor>, type = "CR2")`
and `coef_test(fit, vcov = <CR2>, test = "Satterthwaite")`. Python's role is
`INDEPENDENT_IMPLEMENTATION_CROSS_CHECK`, explicitly
`VALIDATED_CROSS_CHECK_NOT_AUTHORITATIVE`.

## 3. Why no new amendment was written, stated because the absence looks like an omission

`tools/hyp01_effective_lock/resolve_effective_lock.py` discovers amendments by
glob and takes `found[-1]` as **the** operative amendment. A second file dated
2026-09 would sort last and silently displace the 2026-08-16 one, after which
the resolver fails `check_authorization` — the authorization statement and its
date are module constants naming *"D1–D16 … on August 16, 2026"* — and
`check_decisions`, which requires D1 through D16 to be present.

`test_market_response_hyp01_dated_amendment.py` check `19e` asserts this
refusal by construction: it plants a second amendment claiming the same field
and requires the resolver to exit non-zero.

C6's field is `primary_model.covariance.estimator_family` and C7's is
`primary_model.covariance.finite_sample_correction_procedure`. **Both are
already claimed by the 2026-08-16 amendment.** A C6/C7 amendment would therefore
collide head-on with an asserted refusal — and would be claiming to decide
something already decided, three weeks late, in a document that would have to
either restate a verbatim August authorization it did not receive or fail its
own resolver. The correct artifact for an already-made decision is a record
that points at it.

## 4. The caveat that travels with this, carried verbatim

From the amendment's `epistemic_status`:

> `"implementation_validation_is_not_scientific_proof": "PR #18 established
> that the study's CR2/Satterthwaite code computes what clubSandwich computes
> on a synthetic fixture matrix. That is implementation agreement. It is not
> evidence that CR2 is the scientifically correct or optimal estimator for
> HYP-01, and it is not a result about the world."`

And the split-tolerance provenance, which the amendment requires to accompany
every citation of the validation:

```
continuous_df_preregistered_in_pr17: false
continuous_satterthwaite_df: "validated under a separately prespecified PR #18
                              tolerance that was NOT preregistered in PR #17"
covariance_se_t_p:           "validated under the PR #17 preregistered tolerances"
```

`GST_HYP01_R_REFERENCE_VALIDATION_v1.0.json` records
`production_eligibility_status: PENDING_AUTHORIZER_DECISION`,
`production_eligible: false`, `method_approved: false`, `lock_activated: false`,
and `cr3_validated: false`. **Resolving C6/C7 does not make the method
approved.** Those are different acts and this record performs neither.

## 5. What is still open, and what this does not clear

- **The gap audit's other nine `SCIENTIFIC_DECISION` rows** — A9, B3, C9, E3,
  E8, F2, F3, F4, F5 — are untouched. **E3 (multiplicity) in particular remains
  open and carries the same critical deadline as C6 and C7**, so the sentence
  *"a study cannot call itself preregistered while its primary estimator and
  inference procedure are still open"* is answered here only in part.
- **Display gate condition 4 is not cleared by this document.** That condition
  reads the registry, and registry v1.0's `unresolved_analysis_decisions` still
  lists the ticker-cluster estimator. Clearing it requires a new dated registry
  version, which is a separate authored act and is not performed here.
- **B4 remains correctly deferred.** The audit's reasoning holds: B4 records
  *which software expresses* the rule C6/C7 fix, and belongs at the freeze. The
  rule preceded the option string, which is the ordering the audit demanded.

---

*This document changes no methodology, no threshold, no universe and no gate.
It records that two decisions the gap audit lists as open were in fact taken on
2026-08-16, and it points at where. No result, direction, effect estimate,
plot, p-value or confidence interval is created, moved or displayed by it.*
