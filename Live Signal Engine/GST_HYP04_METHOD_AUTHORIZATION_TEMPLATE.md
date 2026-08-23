# HYP-04 Analysis-Lock Authorization — TEMPLATE (UNSIGNED)

> **THIS IS A TEMPLATE, NOT AN AUTHORIZATION.** Nothing here is signed, and no
> authorization has occurred. On signing, copy this file to
> `GST_HYP04_METHOD_AUTHORIZATION_<YYYY-MM-DD>.md` using the authorizer's
> declared date, fill every `<...>` placeholder, and delete this banner. The
> template itself is retained unsigned so the next authorization has a pattern
> to follow.

Companion to the analysis lock and its JSON — for v1.0 that is
[`GST_HYP04_ANALYSIS_LOCK_v1.0.md`](GST_HYP04_ANALYSIS_LOCK_v1.0.md), signed
2026-08-20; a future lock would name its own. Modelled on
[`GST_HYP01_METHOD_AUTHORIZATION_2026-08-16.md`](GST_HYP01_METHOD_AUTHORIZATION_2026-08-16.md),
which is the pattern this project already uses for exactly this act.

**This authorization is append-only.** It rewrites, deletes, renames and
activates nothing.

---

## The authorization

> **"<AUTHORIZATION SENTENCE — the authorizer's own words. HYP-01's read:
> 'I authorize the recommended D1–D16 methodological package as specified on
> August 16, 2026.'>"**

| | |
|---|---|
| **Authorizer role** | Project authorizer / repository owner |
| **Declared authorization date** | `<YYYY-MM-DD>` |
| **Date basis** | user-declared UTC calendar date |
| **Recorded at** | `<YYYY-MM-DDTHH:MM:SSZ>` |
| **Scope** | HYP-04 analysis-lock decisions **D1–D10 only** |

**What this authorization is not.** The authorizer is the project owner, not an
independent statistician or methodologist. **No external peer review,
methodological review, institutional approval or reviewer sign-off has
occurred**, and none is claimed. No handwritten signature exists. No reviewer
identity is recorded, because there is no reviewer.

**On the date.** The declared date is a **UTC calendar date supplied by the
authorizer**. This record does not assert that the authorization occurred on
that date in America/Chicago or any other local timezone. The git commit and
push timestamps, preserved separately by version control, record when the lock
entered history.

## What is being authorized

The ten decisions in `GST_HYP04_ANALYSIS_LOCK_v1.0`, resolving the four
`PENDING_SEPARATE_ANALYSIS_LOCK` entries the registry in force records against
HYP-04.

| Decision | Substance |
|---|---|
| D1 | Cluster one-way on `calendar_period` |
| D2 | Anchor recurrence stated as an uncovered residual |
| D3 | CR2 covariance estimator |
| D4 | Bias-reduced linearization only; no second correction |
| D5 | Coefficient-specific Satterthwaite dof, persisted and reported |
| D6 | Retain singletons; no invented minimum-cluster or df cutoff |
| D7 | `onset_horizon` reported as `[onset − 2, onset]`, one-sided, k = 2 |
| D8 | Stage 2 sizes tenor off the interval's lower bound |
| D9 | IV promotion conditional — QuantConnect, ≥ 80% per peer, ≥ 70% of universe, 8 quarters |
| D10 | Python CR2 authoritative for Phases 0–1; R cross-check required before Phase 3 |

**This is not the Phase 2 preregistration lock.** Target definition, feature
set, model specification and validation split remain unfrozen and are Phase 2's
to fix.

## What informed the decision

| Evidence | What it established |
|---|---|
| HYP-01 dated amendment 2026-08-16 | The estimator package D3–D6 adopt: CR2, BRL only, Satterthwaite dof, singleton and cluster-count policy |
| HYP-01 R-reference validation | Implementation agreement between this CR2 arithmetic and clubSandwich under preregistered tolerances |
| Phase 0 fixture measurements | That the two clustering dimensions cross-cut and their join collapses the panel to one cluster; that df ≈ 5.7 at the panel shape the 193 floor implies; that onset error is one-sided late |
| Phase 0 options-coverage audit | Current-chain coverage only — yfinance has no historical endpoint, which is why D9 is conditional rather than resolved outright |
| HYP-01 QuantConnect validation | 24 of 24 frozen anchor tickers returned clean historical option pricing, with events per ticker ranging 1 to 8 |

**Implementation validation is not scientific proof.** The R cross-check showed
the Python code computes what clubSandwich computes on synthetic fixtures. That
is implementation agreement — **not** evidence that CR2 is the scientifically
correct or optimal estimator for HYP-04, and not a result about the world.
`method_approved` remains **false**, inherited from HYP-01, which records the
same.

## No outcome was inspected

At the moment of authorization, attest that each of the following holds:

- [ ] `results` is null for HYP-04
- [ ] zero real eligible anchor events exist
- [ ] no event-set freeze record exists
- [ ] curated linkage edges at signing: **______** (record the number; any value
      is compatible with signing — the gate does not read it)
- [ ] display-gate status at signing: **______** with **____** denial(s), and
      the conditions reading MET are: **______________**
- [ ] no effect estimate, direction, p-value, interim result or plot existed to
      inspect, and none was inspected

> Two of these were previously fixed assertions — "the linkage map does not
> exist; zero rows are curated" and "the gate is CLOSED on all five
> conditions". Both became false (curation began 2026-08-22; C4 has read MET
> since registry v1.2), which would have had a signer attest to something
> untrue. They are now blanks the signer fills in, so this instrument records
> the state at signing instead of asserting a state that expires.

**Verify mechanically before signing**, rather than asserting it:

```bash
cd <repo>
PYTHONPATH=$PWD .venv/Scripts/python.exe -c "
from hyp04_supply_chain_hedge.display_gate import current_decision
d = current_decision()
print('gate:', d.status)
for k, v in d.conditions.items():
    print('  ', 'MET' if v else 'NOT MET', k)
"
```

**The gate must read `CLOSED`.** Record the denial count and which conditions
read `MET`; copy them into the blanks above.

Do NOT treat a `MET` condition as a reason to stop by itself. C4 has read `MET`
since registry v1.2 was authored, which is the intended outcome of the work
described in "What signing does not do" below — an earlier version of this
template said to stop on any `MET` condition, which would have aborted signing
on exactly the state the project set out to reach.

**Stop only if the gate reads `OPEN`.** That, and not the state of any single
condition, is what would mean this authorization's premise no longer holds.

## What signing does not do

Signing resolves nothing on its own. **Gate condition C4 reads the registry
named by `display_gate.REGISTRY_CURRENT`, not this file and not the lock.**
Clearing C4 additionally requires authoring the next registry version per the
lock's §11 — a registry version is never edited in place.

*(Historical note: when this template was written that meant authoring v1.2 and
repointing five code locations that pinned the v1.1 filename. Both were done.
The version-named constant is what made the bump a five-file chore, so it is now
`REGISTRY_CURRENT`; do not reintroduce a version number here.)*

Even after both acts, the gate remains **CLOSED**: C4 clears; C1, C2, C3 and C5
do not. No HYP-04 finding becomes displayable.

## Signature

| Field | Value |
|---|---|
| Authorizer | `<name or role>` |
| Declared date | `<YYYY-MM-DD>` |
| Lock artifact authorized | `GST_HYP04_ANALYSIS_LOCK_v1.0.json` |
| Lock artifact SHA-256 at signing | `<hash>` |
| Registry version in force at signing | `<vX.Y>` |
| Registry version that will record resolution | `<vX.Y>` |

Recording the lock's hash at signing is what makes later drift detectable,
matching how HYP-01's amendment records the hashes of the artifacts it leaves
untouched.

---

*Nothing in this document constitutes investment advice, a solicitation, or a
representation that any approach is profitable.*
