# GST Prospective Hypothesis Registry — v1.5 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5.json)
**Authored:** 2026-08-27 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.4.json` (sha256 `b7900bcd5c6676da…`)
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **This version declares a universe. It measures nothing and opens nothing.**
> No hypothesis, threshold, eligibility class, measurement, capture path or
> decision changes. Every eligible-event counter stays zero and the display
> gate stays **CLOSED, C4 MET, four denials**.

---

## 1. The problem v1.5 responds to

Recorded 2026-08-26 in [`HYP04_ANCHOR_UNIVERSE_FINDING_2026-08-26.md`](HYP04_ANCHOR_UNIVERSE_FINDING_2026-08-26.md), and unchanged since:

- The two companies in the 51-ticker EDGAR screen that disclose a **named** counterparty concentration — **MCK** and **PKG** — are both **outside** the project's locked 24-ticker universe.
- Among the locked 24 the same screen found **zero** named counterparties.

So the anchors that have linkage edges are outside the locked universe, and the anchors inside the locked universe have no linkage edges.

**The obvious fix is the one that must not be taken.** Adding MCK and PKG to the anchor universe means choosing the universe *because those are the tickers that turned out to have usable edges*. Every edge involved is real and filing-backed, and it would still be selection on the data after seeing it — which is exactly what locking a universe exists to prevent.

## 2. What v1.5 does instead

It registers a **rule**, evaluates it, and records whatever comes out.

| | |
|---|---|
| **Rule** | `HYP04-ANCHOR-UNIVERSE-RULE-v1` |
| **Implemented by** | [`hyp04_supply_chain_hedge/anchor_universe.py`](../hyp04_supply_chain_hedge/anchor_universe.py) |
| **Cutoff** | 2026-08-27 |
| **Frame** | 51 tickers — the locked 24 plus the Phase 0 candidate peer universe |
| **Members derived** | **1 — MCK** |

A ticker qualifies if **all six** conditions hold:

| | Requirement |
|---|---|
| **AU-1** | it is in the declared screening frame |
| **AU-2** | an annual report (10-K) was screened for it, filed on or before the cutoff |
| **AU-3** | that filing **names** a specific counterparty |
| **AU-4** | the concentration is stated against **consolidated revenue** — not a segment, not receivables, not an unrecognised denominator |
| **AU-5** | the concentration is **≥ 10%** of that denominator |
| **AU-6** | the disclosure carries a valid filing date on or before the cutoff |

**The threshold and the denominator are ASC 280-10-50-42's own** — "10 percent or more of an entity's revenues" — not numbers picked to fit an observed set.

### The frame predates the rule, checkably

A rule applied to a hand-picked candidate list is still a hand-picked universe. This frame comes from two lists fixed earlier for unrelated reasons, and the ordering is in git rather than asserted:

| | |
|---|---|
| `AllTickers_Sectors.csv` arrives | `77c18d5`, **2026-07-23** |
| `candidate_peer_universe()` written | `42cc220`, **2026-08-18** |
| first curated linkage edge exists | `9f76358`, **2026-08-22** |

MCK and PKG were inside the frame **more than a month** before any edge involving either of them existed.

## 3. The member list is derived, not typed

`make_registry_v1_5.build_v1_5()` has **no parameter** for the member list and no constant holding one. It runs `anchor_universe.derive_universe()` over a screen pinned by name *and* sha256, writes the result, then **re-derives and refuses** if the two disagree. The conditions and the rejected-conditions list are copied out of the code at generation time, so the document cannot drift from what implements it.

[`test_hyp04_supply_chain_hedge_registry_v1_5.py`](../test_hyp04_supply_chain_hedge_registry_v1_5.py) re-derives the universe on **every run** and fails if the published list stops following from the rule.

## 4. The rule was written after the screen was seen

The screen ran 2026-08-26. The rule was written 2026-08-27. **Claiming otherwise would be false, and this registry does not claim it.** What protects it is not ignorance of the data but two things you can check:

1. **Its parameters are the accounting standard's**, not tuned ones.
2. **Applying it costs a ticker.** PKG is excluded — and PKG is one of only two companies in the screen with a named counterparty, and one of the two curated linkage edges. A rule fitted to the observed set would have kept both.

### The alternative that would have kept PKG, and why it was rejected

Accepting a **segment-level** denominator would admit PKG's *"58% of our Paper segment sales revenue"* and make the universe MCK **and** PKG.

It is rejected for two reasons. First, it is the variant that retains the ticker already known to be there — the definition of fitting a rule to data. Second, it does not survive on its own terms. PKG's 10-K filed 2026-02-26 says, in the **same sentence**:

> In 2025, our sales revenue to ODP represented **58% of our Paper segment sales revenue and 4% of our consolidated sales revenue.**

At the entity level — which is the level at which an earnings shock moves the anchor's equity — the relationship is **4%**, below the standard's own bar. Reversing this requires a further dated registry version, authored before the results that would motivate it are seen.

## 5. What the rule is deliberately not allowed to know

Four conditions were considered and **rejected**, recorded in the artifact so that adding one later is a visible reversal:

| Rejected condition | Why |
|---|---|
| counterparty still exists | Selects on survival. |
| price history obtainable | Imports a provider's survivorship bias into the preregistration. |
| relationship still current | The measurement is point-in-time; a relationship that has since ended was still real for the events it covered. |
| ticker is in the locked 24 | Would make the universe empty — the screen found zero named counterparties there. |

**This is the direct response to the second finding**, [`HYP04_CLOSES_COLLECTION_FINDING_2026-08-26.md`](HYP04_CLOSES_COLLECTION_FINDING_2026-08-26.md). ODP — PKG's disclosed counterparty — ceased to be a public SEC filer after the 2026-02-26 10-K that still named it PKG's largest Paper-segment customer, and the provider used for peer closes returns **zero rows at every window from 2016 to 2026**.

The peers most likely to disappear are those acquired or taken private, and **acquisition is frequently caused by the very relationship under study** — so the missing observations are not missing at random with respect to this hypothesis. v1.5's new top-level `peer_price_data_policy` states the separation plainly: **availability is a measurability question, reported per pair; it is never a membership question.**

Note what this buys. PKG is excluded by its *denominator*, not by ODP's tradability. Had the rule conditioned on obtainable prices, PKG would have been excluded for a reason that is pure survivorship.

## 6. What v1.5 does **not** do

- **It creates no eligible anchor event.** `required_eligibility_class` is unchanged at `core_attention_vs_equity_response`; eligibility is decided by `gst_market_response.completeness` from per-event capture records; no capture path runs over MCK. Declaring who *may* be an anchor produces no such record for anybody.
- **No display-gate condition moves.** C2 counts eligible anchor events, of which there are still zero. The generator refuses outright if `eligible_event_counts` changes.
- **The locked 24-ticker universe is untouched**, as are `gst_market_response/`, the cohort protocol, and every earlier registry version. v1.4 remains byte-identical (`b7900bcd…`), pinned by a test.
- **A survivorship-bias-free peer price source is still required** before any HYP-04 measurement is run. None has been selected. No option was taken.

## 7. Honest limitations of the screen behind this

- **ASC 280 is a floor.** Disclosure is required only at ≥10% of revenue. Real relationships below that, most supplier relationships, and every "Customer A" disclosure are invisible. **An absent edge is not evidence of no relationship.**
- **Elided coordination is missed.** The extractor anchors on a verb; in *"represented 58% of segment revenue **and** 4% of consolidated revenue"* it captures the first figure only. This under-includes — the safe direction for a universe, since it excludes rather than fabricates — but a filing whose consolidated figure appears only in a coordinated clause could be wrongly excluded. Not fixed here; recorded.
- **A universe of one is a universe of one.** It is enough to make the rule real and not enough to make the hypothesis measurable. Widening it means widening the *frame* or finding a source beyond ASC 280 concentration disclosure — either of which is a further dated registry decision, not a silent change.

---

**Nothing in this document is evidence about supply-chain transmission.** No result, direction, effect estimate, plot, p-value or confidence interval exists for HYP-04, and none may be displayed while the gate is closed.
