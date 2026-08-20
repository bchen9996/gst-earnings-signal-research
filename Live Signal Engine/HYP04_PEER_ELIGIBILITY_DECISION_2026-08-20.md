# HYP-04 peer-side eligibility — decision record (2026-08-20)

**Decision:** peer-side eligibility is defined at the **(anchor event × peer) pair** level inside `hyp04_supply_chain_hedge/`, **not** as a fourth member of `gst_market_response.completeness.HYPOTHESIS_CLASSES`.

**Status:** rule defined and tested. **No linkage rows are curated.** This record defines a bar; it does not clear one, and it opens no gate.

---

## What prompted it

Registry v1.2 records HYP-04's `required_eligibility_class` as `core_attention_vs_equity_response` — the **anchor-side** requirement — and states that the peer-side measurement has *no* eligibility class in `HYPOTHESIS_CLASSES` **at all**, listing that as one reason HYP-04 is `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`.

It was raised ahead of linkage curation deliberately: curating rows against an undefined eligibility rule is work that may have to be redone, and the rule turns out to constrain *which* rows are worth curating.

## Why not a fourth hypothesis class

The registry's wording — "no eligibility class at all" — invites adding one. That would have been the wrong fix.

`HYPOTHESIS_CLASSES` has three members, and each maps onto exactly one boolean field of `ModuleEligibility`:

| Class | Backing field |
|---|---|
| `core_attention_vs_equity_response` | `core_pre_event_eligible` |
| `options_implied_move` | `option_benchmark_eligible` |
| `joint_attention_plus_options` | `joint_full_eligible` |

Those booleans are properties of **one anchor event record**. They answer *"which evidence modules does this event carry?"*

HYP-04's peer measurement is not a property of an event record. It is a property of a **pair**: this anchor event, this peer, and a linkage edge whose as-of date either does or does not precede the event. **A fourth boolean on a per-event record cannot encode a fact that is not about the event.** This is a unit mismatch, not a missing enum member.

Adding one anyway would have carried real cost for no benefit:

- it would edit `gst_market_response`, which is **HYP-01's confirmatory infrastructure** and is `ACTIVE_COLLECTING`
- `test_market_response_cohort_protocol.py` pins the protocol document's `hypothesis_families` to the production tuple, so it would require **cohort protocol v1.2**
- the new flag could not be computed from an event record, so it would be either dishonest or permanently `False`
- recording it properly would imply **registry v1.3**

**Because no class was created, registry v1.2's statement that "no new class is created by this registry version" remains accurate, and no registry v1.3 is required.**

## The rule

`hyp04_supply_chain_hedge/pair_eligibility.py`. Fail-closed; every unknown denies; each condition denies independently.

| | Condition |
|---|---|
| **P1** | The anchor event is core-eligible. **Delegated** to `is_eligible_for_hypothesis`, never reimplemented — the anchor-side requirement stays where the registry already put it. |
| **P2** | The edge belongs to this anchor; peer is non-blank and is not the anchor |
| **P3** | The edge's `as_of_date` is **strictly before** the event date |
| **P4** | `as_of_date_basis` is not `unknown/uncertain` |
| **P5** | The peer has usable return history in the event window; **unknown denies** |
| **P6** | `relationship_type` is in the closed vocabulary and has a direction |
| **P7** | The pair does not derive from the Phase 0 placeholder linkage |

## Why P3 and P4 are the point

This project's central unresolved finding is a **failed point-in-time validity check**: HYP-01's historical GST z-scores were reconstructed by querying Trends today for windows ending years earlier — reproducible, but not provably what a live observer saw. It is carried as **failed**, not waived. Critically, it was discovered *after* the data was built.

A curated supply-chain map is exposed to the same error and arguably worse, because it is assembled from documents that exist **now** about relationships that began **then**. An edge sourced from a 2026 10-K says nothing about whether a 2022 observer knew the relationship existed. Counting that pair at a 2022 event imports hindsight directly into the sample.

So the rule is strict, in both halves:

- **Strictly before, not on-or-before.** An edge established *on* the event date is refused. Same-day knowledge is not prior knowledge, and the boundary is tested explicitly in both directions.
- **`unknown/uncertain` is never eligible**, at any event, however early and well-formed the date looks. A date nobody can source cannot establish what was knowable.

**This will disqualify real, correctly-curated edges.** That is the intended cost. It is the difference between applying the discipline prospectively and discovering the violation afterwards — which this project has already done once, expensively.

The `unknown/uncertain` basis remains a legal value in the curated schema on purpose. A curator must be able to record honest uncertainty rather than being pushed into inventing a date. It is refused at *eligibility*, not at *curation*.

## What is deliberately not a condition

**Peer options data.** Analysis-lock decision D9 makes implied volatility a **conditional, secondary** target; the primary target is realized volatility, which needs only the peer's own return history.

Requiring peer options here would silently exclude precisely the thin, less-covered peers plan v0.2 §1 says this hypothesis is most interested in — turning a robustness check on the same population into a different question about liquid names. That is the tension D9 records as *stated, not resolved*, and it is an argument for keeping IV permanently secondary, not for narrowing the eligible population.

## What this does not do

- **It opens no gate.** Pair eligibility feeds Phase 1 sample construction. Display-gate condition **C2 counts eligible *anchor events***, a unit registry v1.2 fixes deliberately. C1–C5 are untouched and the gate remains **CLOSED**.
- It changes nothing in `gst_market_response/`, the cohort protocol, or any registry version.
- It curates no rows. **Zero linkage rows exist**, so **zero pairs are eligible today** — asserted as a live check in the suite rather than assumed.
- It is not a Phase 2 preregistration decision. Target, features, model specification and validation split remain unfrozen.

## Consequence for curation

Two properties are now worth knowing before curating at scale:

1. An edge is only usable for events **after** its as-of date, so an edge curated from a recent filing contributes to fewer anchor events than one traceable to an earlier document. **Earlier-sourced edges are worth more.**
2. An edge with `as_of_date_basis: unknown/uncertain` contributes to **nothing**. Curating one is not useless — it records a known relationship — but it will not enter the sample, and that should be understood before the effort is spent.

Neither changes the schema. Both change what a curator should prioritise.

---

*Nothing in this document constitutes investment advice, a solicitation, or a representation that any approach is profitable. No hedging edge has been demonstrated, and Phase 0 established nothing about supply-chain transmission.*
