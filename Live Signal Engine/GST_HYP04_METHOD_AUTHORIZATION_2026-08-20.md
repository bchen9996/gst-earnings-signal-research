# HYP-04 Analysis-Lock Authorization — 2026-08-20

> **Dated authorizer signature for the HYP-04 analysis lock, decisions D1–D10.
> No outcome was inspected, the display gate remains CLOSED on all five
> conditions, and the linkage map still does not exist at zero curated rows.**

Companion to [`GST_HYP04_ANALYSIS_LOCK_v1.0.md`](GST_HYP04_ANALYSIS_LOCK_v1.0.md)
and its JSON. Modelled on
[`GST_HYP01_METHOD_AUTHORIZATION_2026-08-16.md`](GST_HYP01_METHOD_AUTHORIZATION_2026-08-16.md),
which is the pattern this project already uses for exactly this act.

**This authorization is append-only.** It rewrites, deletes, renames and
activates nothing.

---

## The authorization

> **"I authorize the HYP-04 analysis-lock decisions D1–D10 as specified in
> `GST_HYP04_ANALYSIS_LOCK_v1.0`, on August 20, 2026. These decisions are fixed
> before any HYP-04 outcome exists to see. I authorize no result, no method
> approval, and no display of any finding."**

| | |
|---|---|
| **Authorizer role** | Project authorizer / repository owner |
| **Declared authorization date** | `2026-08-20` |
| **Date basis** | user-declared UTC calendar date |
| **Recorded at** | `2026-08-20T18:12:21Z` |
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
`PENDING_SEPARATE_ANALYSIS_LOCK` entries registry v1.1 records against HYP-04.

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

Each of the following held at the moment of authorization:

- [x] `results` is null for HYP-04
- [x] zero real eligible anchor events exist
- [x] no event-set freeze record exists
- [x] the linkage map does not exist; zero rows are curated
- [x] the result-display gate is CLOSED on all five conditions
- [x] no effect estimate, direction, p-value, interim result or plot existed to
      inspect, and none was inspected

**Verified mechanically before signing**, rather than asserted. Run at
`2026-08-20T18:12:21Z`:

```
gate: CLOSED
    NOT MET C1_status
    NOT MET C2_threshold
    NOT MET C3_frozen
    NOT MET C4_decisions_resolved
    NOT MET C5_not_placeholder

results is null            : True
eligible event counts      : {'HYP-01': 0, 'HYP-02': 0, 'HYP-03': 0, 'HYP-04': 0}
freeze record exists       : False
```

Reproduce with:

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

Every condition must read `NOT MET` and the gate must read `CLOSED`. If any
condition reads `MET`, stop — something changed, and this authorization's
premise no longer holds.

**Which clause actually rests on a person's word.** Five of the six conditions
above are machine-checkable and were checked. Only the sixth — that nothing was
*inspected* — is an attestation about the authorizer's own conduct, and in this
instance it is close to trivially satisfiable: no effect estimate, direction,
p-value, interim result or plot existed anywhere in the repository to inspect.
That is the point of signing now rather than later.

## What signing does not do

Signing resolves nothing on its own. **Gate condition C4 reads registry v1.1,
not this file or the lock.** Clearing C4 additionally requires authoring
registry **v1.2** per the lock's §11 — v1.1 is never edited in place — and
repointing the five code locations that pin the v1.1 filename.

Even after both acts, the gate remains **CLOSED**: C4 clears; C1, C2, C3 and C5
do not. No HYP-04 finding becomes displayable.

## Signature

| Field | Value |
|---|---|
| Authorizer | `Project authorizer / repository owner` |
| Declared date | `2026-08-20` |
| Lock artifact authorized | `GST_HYP04_ANALYSIS_LOCK_v1.0.json` |
| Lock artifact SHA-256 at signing | `5b98557b769bee062d32f679b5670d2b1804e877614af8dcb5a6b0d5581cd703` |
| Registry version in force at signing | `v1.1` |
| Registry version that will record resolution | `v1.2` (not yet authored) |

Recording the lock's hash at signing is what makes later drift detectable,
matching how HYP-01's amendment records the hashes of the artifacts it leaves
untouched.

---

*Nothing in this document constitutes investment advice, a solicitation, or a
representation that any approach is profitable. No hedging edge has been
demonstrated, and Phase 0 established nothing about supply-chain transmission.*
