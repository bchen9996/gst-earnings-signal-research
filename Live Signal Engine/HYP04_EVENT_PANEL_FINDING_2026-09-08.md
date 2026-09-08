# HYP-04 event panel — the eligible count is now mechanically derived

**Date:** 2026-09-08
**Status:** measured. Derives the count C2 asks for. Opens no gate, freezes nothing, adopts nothing.

---

## 1. What was missing, and what changed

Registry v1.11 §10 listed the panel assembler as the top open item:

> **The panel assembler**, which must consume the per-pair coverage path.
> Measured: per-pair gives 215 events, the per-peer unit gives 161 — below the
> floor — because one uncollectable CVS event marks CVS unavailable for all 54
> of its events.

Every input already existed. The anchor calendar carries 342 events with 324
shocks; the curated map reaches seven edges; all 13,056 peer closes are
collected and load clean. **Nothing joined them.** So C2's denial has read
"eligible event count is unknown / **not mechanically derivable**" — a statement
about missing machinery, not about missing data.

`hyp04_supply_chain_hedge/make_event_panel.py` is that machinery.

## 2. The derived count

| unit | anchor events | pairs | vs. floor 193 |
|---|---|---|---|
| **per-pair (registered)** | **214** | **312** | **clears by 21** |
| per-peer, P1+P3-scoped | 161 | 259 | fails by 32 |

Denials under the registered unit: **P3 158, P5 171, P1 18.**

The P1 figure needs care, because it invites a wrong reading. The calendar holds
342 events and 324 shocks, so **18 events** carry no shock — and P1 denies
**18 pairs**. *Those two 18s are a coincidence.* Only **14** of the shockless
events sit on an anchor that has any curated edge at all; they generate 18 pairs
because JBL carries three edges (INTC 6×1, NVDA 5×1, JBL 2×3, MCK 1×1 = 18).
The other four shockless events, on NKE, CTSH and ADBE, produce no pair to deny.
A missing shock is denied and never assumed, which is the correct treatment —
but the denial count is a count of pairs, not of events.

**The unit is worth 53 events.** Registry v1.11 settled which one applies —
*"Peer-side price data availability is a MEASURABILITY question, reported per
pair. It is never a MEMBERSHIP question"* — and settled it on **2026-09-02**,
before this assembler existed and with no knowledge of what it would return.
Both units are published anyway, because a choice worth 53 events should be
visible rather than taken on trust.

## 3. A scoping trap in the per-peer unit, disclosed

`peer_history_map` marks a peer available only if it covers **every event in
the list it is given**, so the list decides the answer:

| scope | events |
|---|---|
| P1+P3 survivors only | **161** |
| all calendar events | 89 |

Ranged over all events, a peer is condemned by events P1 or P3 would deny
anyway — AAPL gets checked against JBL events from 2003, a decade before its
edge's `as_of_date`. That is not the per-peer unit's cost; it is the cost of
asking the question on the wrong set. **The 161 figure is the like-for-like
comparison and it reproduces the 2026-09-02 price finding exactly.** The 89 is
published beside it so the scoping is visible rather than buried in a helper.

## 4. The §4 discrepancy, resolved

The price finding recorded, and did not resolve:

> Under assumed prices, resolving events through `closes_requirements` gives 216
> where the ceiling artifact gives 215. The two figures agree numerically but
> **are not demonstrated to be the same event set**.

Diffed by event id rather than compared by count:

- assumed prices → **215 events / 313 pairs**
- real per-pair coverage → **214 events / 312 pairs**
- **difference: exactly one event — `MCK-2026-08-05`, peer `CVS`.**

Its reference *and* horizon windows are both empty. CVS's collected closes end
**2026-06-08**, two months before the event, so this is not only the right-edge
truncation the price finding described — the reference side is missing too. It
becomes collectable when CVS's file is extended.

Nothing is eligible under real coverage that was not eligible under assumed
prices. That direction is checked explicitly (test 5d): the reverse would mean
coverage had *invented* a pair.

## 5. What this does and does not move

**C2** asked for a mechanically derived eligible-event count. There is now one:
**214**, above the registered floor of 193, derived by running the committed
inputs through `pair_eligibility` with no hand-entered numbers anywhere.

**It does not open the gate.** C3 needs a freeze record naming an analysis lock
and a commit sha, attested as made *before* any result was computed. This
module writes no freeze and has no standing to. C2 and C3 move together or not
at all, and C1 remains `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`.

Verified after this work: the display gate is **CLOSED**, C4 **MET**, **four**
denials, eligible event count **unset**. Test 8 asserts it.

## 6. Two changes to shared code

- `linkage_resolution.resolve_from_curated_map` gained an optional
  `peer_history_by_pair` argument. It is additive, per-pair takes precedence
  over per-peer, and a pair absent from **both** maps is still UNKNOWN and
  still denied by P5. Every existing test passes unchanged.
- A dead guard was found and removed rather than left in place. The assembler
  checked `filled == 0` to catch an uncollected request file — but
  `load_peer_closes` rejects a blank-close row outright, so such a file arrives
  as zero observations and the ticker check always fires first. The reject
  check now runs first and names the uncollected case. A guard that cannot fire
  is worse than no guard: it reads as a check that runs.

## 7. What remains before Phase 0 can close

- **C1** — status is still `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`. A
  registry decision, not a measurement.
- **C3** — the freeze machinery: an analysis lock written *before* the freeze,
  a commit sha, and an attestation. None of it exists yet.
- **C5** — the freeze must derive `uses_placeholder_linkage` from the panel's
  provenance via `freeze_record_fields`, which now has a real curated map to
  read. The material exists; the freeze does not.
- **The curated map's own status.** Five of its seven rows still read
  `DRAFT, UNVALIDATED, MACHINE-PREPARED` and one (`INTC→HPQ`) is
  `review_status: needs revisit` at `date_confidence: low`. The count above is
  derived from those rows. **A mechanically derived count over unratified edges
  is a derived count, not a ratified one**, and that distinction belongs to the
  repo owner, not to this module.

---

*Nothing in this document is evidence about supply-chain transmission. No target
value, `beta_h`, peer response, horizon or direction has been computed. What is
counted is data availability, which is publishable under the display-gate
convention; what it implies is not.*

*Nothing in this document constitutes investment advice, a solicitation, or a
representation that any approach is profitable.*
