# GST Prospective Hypothesis Registry — v1.2 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.2.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.2.json)
**Authored:** 2026-08-20 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json`
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **This version records one thing: that HYP-04's four analysis decisions were
> resolved in a dated, signed analysis lock.** It registers no hypothesis,
> promotes none, demotes none, re-thresholds none, and reports no result.

---

## 1. What changed from v1.1

| | v1.1 | v1.2 |
|---|---|---|
| HYP-04's four analysis decisions | `PENDING_SEPARATE_ANALYSIS_LOCK` | `RESOLVED_IN_DATED_ANALYSIS_LOCK`, each citing `GST_HYP04_ANALYSIS_LOCK_v1.0.json` |
| HYP-04 status | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` | **unchanged** |
| HYP-04 event floor | 193 anchor events | **unchanged** |
| HYP-01 / HYP-02 / HYP-03 | defined in v1.0, incorporated by reference | **unchanged, still by reference** |
| Options-eligibility position | `DENY_NO_REGISTERED_HYPOTHESIS` | **unchanged** |
| Eligible event counts | all zero | **all zero** |
| `results` | `null` | **`null`** |

**Nothing else moved.** The generator that produced this file records v1.1's
SHA-256 in `supersedes_sha256`, so any later drift in v1.1 is detectable.

## 2. v1.1 is not edited in place

`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json` remains on disk, byte for byte,
and its own governance suite continues to run against it unchanged. That is the
same discipline v1.1 applied to v1.0, and it is why resolution is recorded by
**marking** each decision rather than removing it — an emptied ledger is a
deletion, not a resolution, and the display gate denies it.

HYP-01, HYP-02 and HYP-03 are still defined in v1.0 and incorporated here by
reference. They are deliberately not restated, because two mutable copies of the
same governed text is the drift this project's tamper tests exist to catch.

## 3. What resolving these decisions does — and does not — do

Resolution clears exactly one display-gate condition: **C4**.

| Condition | State | Why |
|---|---|---|
| C1 status | **NOT MET** | HYP-04 is not `ACTIVE_COLLECTING` |
| C2 threshold | **NOT MET** | zero eligible anchor events against a floor of 193 |
| C3 freeze | **NOT MET** | no event-set freeze record exists |
| C4 decisions | **MET** | recorded by this version |
| C5 linkage | **NOT MET** | no real linkage map; the Phase 0 placeholder is positional and is never evidence |

**The gate remains CLOSED.** No HYP-04 finding becomes displayable, and none
exists to display. C4 clearing is the removal of a governance blocker, not
progress toward a result.

## 4. What this version explicitly does not claim

- **No result.** `results` is `null` and every eligible-event count is zero.
- **No method approval.** The analysis lock's D3 and D10 record
  `method_approved: false`, inherited from HYP-01. Implementation agreement with
  clubSandwich under preregistered tolerances is a statement about arithmetic,
  not a statistical endorsement.
- **No linkage map.** Zero rows are curated. The ingestion path is built and
  tested; a loader is not a map.
- **No quantum result is validated.** The quantum-provenance control is
  independent of this version in both directions.
- **No hedging edge.** Phase 0 established nothing about supply-chain
  transmission.

## 5. Provenance

Authored mechanically by
[`hyp04_supply_chain_hedge/make_registry_v1_2.py`](../hyp04_supply_chain_hedge/make_registry_v1_2.py),
which refuses to run unless the analysis lock is signed, in force, names an
authorizer and an operative date, and attests that no outcome was inspected
before signing. It also refuses to overwrite an existing v1.2.

The transform is mechanical rather than hand-authored because v1.1 carries ~26
top-level keys, and resolving four decisions changes four nested `state` fields
and adds four `resolved_by_lock` fields. Everything else must survive intact,
and hand-copying invites a silently dropped key.

| Artifact | Role |
|---|---|
| `GST_HYP04_ANALYSIS_LOCK_v1.0.json` | the signed lock these resolutions cite |
| `GST_HYP04_METHOD_AUTHORIZATION_2026-08-20.md` | the dated authorization record |
| `test_hyp04_supply_chain_hedge_registry_v1_2.py` | governs the generator |
| `test_hyp04_supply_chain_hedge_registry_v1_2_artifact.py` | governs this artifact |

---

*Nothing in this document constitutes investment advice, a solicitation, or a
representation that any approach is profitable. No hedging edge has been
demonstrated, and Phase 0 established nothing about supply-chain transmission.*
