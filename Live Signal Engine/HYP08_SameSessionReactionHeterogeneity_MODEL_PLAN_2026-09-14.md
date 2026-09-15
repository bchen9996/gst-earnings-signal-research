# HYP-08: Same-Session Reaction + Reaction Heterogeneity — Build Plan (2026-09-14)

**Status:** proposal / not yet preregistered. Written to define what this
hypothesis is, why it is genuinely distinct from HYP-04/05/06/07 rather
than another rescale, and what is and is not already decided, consistent
with this project's own discipline.

## 1. Where this comes from

External review of HYP-06's real, reconciled result (see
`HYP06_PHASE3_RESULT_CHARACTERIZATION_2026-09-14.md`) asked for one more
hypothesis, on an explicit condition: it must be genuinely distinct — "whether
EDGAR-identified economic exposure predicts a same-session peer reaction or
reaction heterogeneity after anchor earnings" — and must NOT reuse the
delayed-horizon grid, add filters, or keep expanding the same null test.

HYP-07 (built and run before that feedback arrived) does not meet this bar
on its own: it tests a genuinely different MECHANISM (competitor vs.
supply-chain) and a genuinely different TARGET (signed vs. magnitude), but
it kept the same 1–20 day delayed `HORIZON_GRID` structure every prior
hypothesis used. This plan is the test the feedback actually describes:
same-session (day-of, not day-after) reaction, tested for both an average
effect and heterogeneity between relationship types — the two things the
feedback's own sentence asks for, in one coherent design.

## 2. What's new here, and what's reused

**Genuinely new:**

- **Target/outcome definition.** `target_same_session.py`'s
  `same_session_excess_return = r_peer[attributed_session] − β ×
  r_bench[attributed_session]` — the peer's benchmark-adjusted return on
  the EXACT trading session the anchor's own excess return is attributed
  to. No horizon grid, no cumulation, no reference-window baseline. First
  use of a no-horizon-grid target in this project. Written and
  offline-tested (`test_hyp04_supply_chain_hedge_target_same_session.py`)
  before any outcome value was computed for any real HYP-08 pair.
- **The statistical design.** Two preregistered tests instead of a
  20-horizon max-T search: (1) the plain pooled same-session coefficient
  (`inference.fit_local_projections(table, horizons=(0,))`), (2) the
  `shock:is_competitor` heterogeneity interaction
  (`inference.fit_interaction_model`, new). Significance is judged by a
  closed-form Sidak-corrected critical t-value at k=2 EXACT tests
  (`make_hyp08_sample_size_gate.sidak_critical_t`), not a permutation
  null — the correct tool for a fixed, small test family with no
  horizon-correlation problem to solve, not a lowered bar. A priori,
  economically motivated sign predictions, stated before any fit:
  customer/supplier peers POSITIVE (comovement), competitor peers
  NEGATIVE (displacement, same convention `target_signed.py` already
  uses).
- **The peer universe, as a POOL of two already-discovered sets.** Not a
  new discovery pass. `make_hyp08_phase2_lock.py` reads HYP-06's own
  signed lock (778 customer/supplier pairs) and HYP-07's own signed lock
  (195 competitor pairs) wholesale and pools them — 973 total, 31 distinct
  peer tickers (confirmed zero overlap), 33 distinct anchor tickers
  (4 shared between the two sides). Reusing an already-discovered,
  already-EDGAR-verified universe for a fresh, differently preregistered
  question is the same pattern HYP-06 itself used over HYP-05's own
  discovery — not a new exception.

**Reused verbatim, because these are project-wide method conventions, not
mechanism-specific choices:**

- **Clustering.** `event_id` primary, the same convention every
  hypothesis since HYP-05 has used, not re-decided.
- **Coverage/liquidity threshold.** `MARKET_CAP_THRESHOLD_USD =
  2,000,000,000` — inherited through both source universes; not re-applied
  here since no new peer discovery happens in this pass.
- **Point-in-time discipline.** `peer_selection.py`'s PS-4, inherited
  through both source locks.

## 3. What this means for the four decisions a fresh hypothesis owes

1. **The liquidity/coverage cutoff.** RESOLVED — inherited through both
   source universes (§2).
2. **The target anchor/peer universe.** RESOLVED — the pooled 973-pair set
   from HYP-06's and HYP-07's own already-signed locks, in full (§2).
3. **The target/outcome definition.** RESOLVED — `target_same_session.py`,
   new and not yet locked (§2).
4. **Clustering.** RESOLVED — reused unchanged (§2).

Nothing here is decided by looking at the outcome any observation would
produce: no same-session excess return has been computed for any HYP-08
pair as of this writing.

## 4. Sample-size gate — k is EXACT, and the real pool clears it comfortably

`HYP08_SAMPLE_SIZE_GATE_2026-09-14.md` does NOT borrow HYP-04's own
measured k range (6.05–6.34, itself measured against a 20-horizon
max-T-permutation design). HYP-08 has no horizon grid, so there is no
horizon-correlation structure to measure — its family size is exactly 2
preregistered tests, fixed by this design, giving an EXACT (not
provisional) floor of 152 pairs. **The pooled real universe (973 pairs)
clears this floor by 6.4x** — a materially more comfortable margin than
HYP-07's own exact-195-against-195 clearance, both because the floor
itself is smaller (k=2 vs. k≈6) and because the pooled universe is larger
than either source universe alone.

## 5. What is explicitly NOT decided by this document

- **No freeze, lock, or Phase 1–3 machinery.** This document only states
  the hypothesis and its four resolved decisions. Registration, Phase 2
  locking, and Phase 3 authorization are separate, later, separately
  authorized steps — same discipline as every prior hypothesis.
- **No claim of significance, direction, or of any result at all.** No
  same-session value has been computed for any pair in this universe.
  This document is not evidence about same-session earnings-information
  transmission, in either direction, for either relationship type.
- **No new discovery, no `concentration_pct` extraction.** Both peer
  universes are reused exactly as already discovered and EDGAR-verified.
  A continuous concentration-intensity heterogeneity axis was considered
  and explicitly deferred — it is not machine-extracted for the
  reverse-search-discovered universe (it lives only in free-text
  `evidence_sentence` fields), and building a new extractor now, under
  reviewer pressure, would be exactly the "add a filter" move external
  review's own feedback warned against. `relationship_type` (already a
  real, already-assigned categorical field on both source universes) is
  used instead.
