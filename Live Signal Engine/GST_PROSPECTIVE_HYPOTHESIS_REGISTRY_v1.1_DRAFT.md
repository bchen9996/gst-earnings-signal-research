# GST Prospective Hypothesis Registry — v1.1 (DRAFT)

**Authored:** 2026-08-18
**Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json` / `_v1.0_DRAFT.md`
**Machine-readable companion:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json)

> **v1.0 is not edited.** It stays on disk byte-for-byte, and its own governance tests continue to run against it unchanged. This version is **additive**: it registers HYP-04 and alters nothing about HYP-01, HYP-02 or HYP-03.

## What changed

**One thing:** HYP-04 is registered as a preregistered **exploratory** hypothesis.

Nothing else. No existing hypothesis is modified, reclassified, promoted, demoted or re-thresholded. The options-eligibility position is unchanged and still carries no registered hypothesis.

## The registered hypotheses

| ID | Question | Class | n ≥ | Status |
|---|---|---|---|---|
| **HYP-01** | Pre-earnings attention and market repricing | primary confirmatory observational | 60 | `ACTIVE_COLLECTING` |
| **HYP-02** | Cross-source attention divergence and earnings surprise | preregistered secondary | 60 | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` |
| **HYP-03** | Post-earnings attention decay and continued repricing | preregistered exploratory | 40 | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` |
| **HYP-04** | **Supply-chain peer volatility transmission and lag** | **preregistered exploratory** | **193** | **`PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`** |

HYP-01/02/03 are defined in v1.0 and are **not restated** in v1.1's JSON — restating governed text creates two mutable copies of it and invites exactly the drift this project's tamper tests exist to catch. v1.0 remains authoritative for all three.

---

## HYP-04 — Supply-chain peer volatility transmission and lag

> **Supply-chain/competitor peer volatility transmission and lag following anchor earnings shocks**

**Classification:** preregistered exploratory · **not** confirmatory, **not** secondary
**Threshold:** 193 eligible anchor events
**Status:** `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`
**Eligible events accrued:** 0

### Why the status is `NOT_IMPLEMENTED`

Three required measurements have no production capture path:

1. **The linkage map does not exist in any form.** Phase 0 ran entirely on a *same-sector placeholder*, carrying the same limitation as `GST_Task2_PeerDivergence.py`. Sector membership is not a supply-chain relationship.
2. **No production capture path exists for peer price or volatility series.** No module ingests peer returns for a registered event.
3. **No production join** maps a market-response `event_id` to any peer observation.

Phase 0 analysis code exists and is tested (`hyp04_supply_chain_hedge/`, 159 passing checks). **Working analysis code running on synthetic fixtures is not a production capture path**, and this registry does not treat it as one.

### On the status vocabulary

The status enum is **unchanged** from v1.0. A candidate value was considered during authoring — `PREREGISTERED_MEASUREMENT_IMPLEMENTED_PENDING_LINKAGE` — and **rejected**. It is not part of this enum and was not added.

The reasoning: inventing a status to describe a partially-built hypothesis would weaken the single distinction this enum exists to enforce — *does a production capture path exist at all*. HYP-04's analysis code existing does not make its measurement reachable, and the vocabulary should keep saying so plainly rather than softening to accommodate a hypothesis that happens to have code first and data never.

### The 193 threshold — what it is, and what it is not

**It is a governance eligibility floor**, in exactly the sense HYP-01/02/03's 60/60/40 are: the minimum evidence required before any result may be looked at. **It is not a claim of guaranteed statistical power, and not an estimate of detectable effect size.** The registry's `power_statement` governs it unchanged.

**Unit: anchor events** — the same unit as every other threshold here, and deliberately *not* (anchor × peer) pairs. The pair-level reading of the same derivation is a far weaker bar; with ~5–10 peers per anchor it could be satisfied by a small fraction of the event count. Leaving that unit ambiguous is the specific defect Patch 2 of `HYP04_PLAN_ROUND2_EDITS.md` exists to eliminate, and it is not reintroduced here.

**Where 193 comes from.** Phase 0 derived an effective-sample-size target of `N_eff ≈ 193`, where `N_eff = N_pairs / DEFF` and `DEFF = 1 + (m̄ − 1)·ICC`. The figure recorded here is the **conservative ICC = 1 endpoint**, at which `N_eff` collapses to the anchor-event count — so the event-unit floor and the effective-observation target coincide. At any empirically observed ICC below 1, `N_eff` is reached with *fewer* than 193 anchor events, never more. The floor is therefore conservative in the direction that demands more evidence.

Inputs, recorded so the number can be audited rather than trusted:

| Input | Value |
|---|---|
| Assumed effect size | Cohen's *d* = 0.5 — **hypothetical, externally chosen, not from any observed project result** |
| Family-wise α | 0.05 |
| Power | 0.80 |
| Multiplicity | Šidák over the *effective* number of independent horizon tests, measured empirically at **k = 6.05–6.34** across a 20-horizon grid by max-T permutation on synthetic fixtures |
| Naive single-test baseline | 126 — **labelled baseline only, never the operative floor** |

**Why this does not violate the `power_statement`.** That statement forbids a power calculation performed *using observed project results*. This derivation used a hypothetical effect size chosen before any data, on synthetic fixtures with known injected ground truth. No project data entered it. The output is recorded as a governance floor, not a power guarantee.

Full derivation: `HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md` (§6) · `HYP04_PHASE0_FEASIBILITY_STATUS_2026-08-18.md` (§5). *(Pointer updated 2026-08-19: the derivation was originally specified in `HYP04_PLAN_ROUND2_EDITS.md` Patch 2, which has since been merged into plan v0.2 and demoted to a historical record. The registered threshold of 193 is unchanged — this updates where the derivation is documented, not the value.)*

**Revisable only** by a further dated registry version written *before* the results that would motivate the revision are seen — the same discipline the promotion rule imposes.

### Required external measurement

The supply-chain / competitor / customer **linkage map**, per anchor ticker:

| Column | Required |
|---|---|
| `anchor_ticker` | yes |
| `peer_ticker` | yes |
| `relationship_type` | yes |
| `confidence` | yes |
| **`first_known_or_established_as_of_date`** | **yes — not optional** |

**The as-of date is required, not a nicety.** A map built today encodes relationships known *today*; applying it to historical anchor events without knowing when each relationship was first publicly established is look-ahead bias — the same class of defect this project's own forensic audit already found in the reconstructed GST z-score history. **A map delivered without this column is a blocking data-quality failure, not a partial delivery.**

### Never substituted

- Sector membership as a stand-in for a supply-chain relationship
- Return or volatility correlation as a stand-in for an established business relationship
- Any linkage map lacking a first-known date, applied to historical events

If linkage for a pair is unavailable or undated, that pair **does not count** toward HYP-04. A missing linkage is never inferred from price behaviour.

### Eligibility class

`core_attention_vs_equity_response` — **anchor side only**. An anchor event must itself be core-eligible for its earnings shock to be usable.

The **peer-side measurement has no eligibility class at all** in `gst_market_response.completeness.HYPOTHESIS_CLASSES`. That is part of why this hypothesis is `NOT_IMPLEMENTED`. No existing class is stretched to cover it, and **no new class is created by this registry version**.

### Unresolved, and never guessed

| Decision | State |
|---|---|
| Two-way clustering (anchor event × calendar period) — Phase 0 ships one-way only, as no multiway CR2/Satterthwaite implementation exists in this repo | `PENDING_SEPARATE_ANALYSIS_LOCK` |
| Whether implied volatility is ever promoted from secondary/robustness to primary target — the Phase 0 audit measured **current** chains only; no historical options source has been obtained | `PENDING_SEPARATE_ANALYSIS_LOCK` |
| Uncertainty treatment for the reported lag — `onset_horizon` is late-biased by construction under an expanding-window target | `PENDING_SEPARATE_ANALYSIS_LOCK` |
| Ticker-cluster estimator | `PENDING_SEPARATE_ANALYSIS_LOCK` |

### The options tension, recorded deliberately

HYP-04's **Stage 2 constructs options-adjacent hedge recommendations** — protective put, put spread, collar, sector-ETF proxy. Phase 0 **sizes nothing and executes nothing**: it emits recommendation objects against an *assumed* long-equity holding, with no real position, no order construction and no capital logic.

**Formal options eligibility is out of scope for this entry.** This version does **not** register HYP-04, or any hypothesis, against `options_implied_move` or `joint_attention_plus_options`. Those classes continue to carry `DENY_NO_REGISTERED_HYPOTHESIS`, unchanged.

Deferred to **Phase 4**, where Stage 2 would need options eligibility to mean something operationally. Resolving it then requires its own dated registry decision, exactly as the options rule already specifies.

It is recorded now so the tension is **visible at registration rather than discovered at Phase 4**. Registering an exploratory equity-volatility hypothesis whose downstream stage is options-shaped is a deliberate, bounded decision — not an oversight.

### Display rule

> No result, direction, effect estimate, plot, p-value or confidence interval may be displayed before **193 eligible events**. The hypothesis accrues **no eligible events at all** while its status is `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`. **No result computed on the Phase 0 placeholder (same-sector) linkage may be displayed as a HYP-04 result under any circumstances, at any event count.**

---

## Governance

- **HYP-01 remains the sole primary confirmatory hypothesis.** HYP-02 is secondary; HYP-03 and HYP-04 are exploratory and carry no confirmatory claim.
- **HYP-02, HYP-03 and HYP-04 may never be promoted to confirmatory on the basis of observed results.** Promotion requires a new dated registry version written *before* the results that would motivate it are seen.
- **Adding a hypothesis** enters this registry only via a new dated version, authored before any observation or result for it exists. v1.1 qualifies: zero HYP-04 eligible events, no linkage map, no HYP-04 result produced or looked at.
- **Cross-family multiplicity** across the now-four hypotheses remains `PENDING_SEPARATE_ANALYSIS_LOCK` and is **not** resolved here. HYP-04's max-T horizon correction is *within*-hypothesis and is not a cross-family adjustment.
- **Counting rules CNT-1 … CNT-10** from v1.0 apply unchanged to HYP-04.
- **No model may be changed** after an eligible event set is frozen.

### On the `authored_before_any_candidate_screening_or_observation` flag

v1.0 carries this as `true`. **v1.1 carries it as `false`**, stated plainly rather than inherited.

Round-1 cohort screening has occurred and one event (`EVT-DELL-FY27Q2-ERN`) has been registered since v1.0 was authored, so the unqualified claim would be false here. The scoped claim that *is* true, and is recorded in the JSON: this version was authored before any HYP-04 observation exists, before any peer linkage map exists, and before any HYP-04 result has been produced or looked at.

---

## Eligible event counts

| Hypothesis | Count |
|---|---|
| HYP-01 | 0 |
| HYP-02 | 0 |
| HYP-03 | 0 |
| **HYP-04** | **0** |

Zero for every hypothesis. No candidate has been screened for HYP-04, no peer linkage map exists, no prospective HYP-04 event has been observed, and no result exists. These are structural placeholders.

**Results: none.** No result, direction, effect estimate, plot, p-value or confidence interval exists for any hypothesis. HYP-04's Phase 0 feasibility work produced diagnostics on synthetic fixtures and a placeholder linkage; **none of it is a result about this hypothesis and none of it may be reported as one.**
