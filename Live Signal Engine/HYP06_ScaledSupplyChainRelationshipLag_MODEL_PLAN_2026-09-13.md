# HYP-06: Scaled Supply-Chain Relationship-Lag Model — Build Plan (2026-09-13)

**Status:** proposal / not yet preregistered. Written to define what this
hypothesis is, why it is a fresh hypothesis rather than a reopening of
HYP-05's holdout, and what is and is not already decided, consistent with
this project's HYP-01/HYP-04/HYP-05 discipline.

## 1. Where this comes from

HYP-05 registered (registry v1.14, 2026-09-11) the same underlying
question HYP-04 could not answer: does delayed earnings-information
transmission appear specifically in clearly signed supplier/customer
relationships among lower-coverage, less-liquid peers. HYP-05's Phase 3
ran for real (2026-09-12): **NOT significant**, on an 8-event exploratory
pilot (one anchor, one peer -- AMBA/NVDA, the only candidate three rounds
of hand-guessed peer names produced). Registered as
`EXPLORATORY_PILOT_TESTED_NULL`, explicitly distinct from a floor-clearing
confirmatory result, and its holdout is spent -- nothing here reopens or
revisits `HYP05_PHASE3_RESULT_2026-09-12.json`.

Rounds 4-6 (this session, 2026-09-12/13) built and validated a
fundamentally different peer-discovery mechanism -- reverse EDGAR
full-text search, scaled from 27 hand-curated anchor names to 788 -- and
it found a real, hand-verified, point-in-time-correct universe two orders
of magnitude larger than what hand-guessing ever produced: **778
qualifying (peer, event) pairs, 25 distinct peer tickers, 776 distinct
(anchor, event) clusters** (`HYP05_PEER_UNIVERSE_SCALED_2026-09-13.json`).
That universe cannot be fed into HYP-05's already-spent holdout -- see
round 6's closing section in `HYP05_PEER_UNIVERSE_2026-09-12.md`. HYP-06
is how it gets used: the same scientific question, tested for real, on
its own fresh holdout, against a universe two orders of magnitude larger
than what HYP-05 actually tested.

## 2. This is the SAME question as HYP-05 -- what's actually new is power

HYP-05's construction question was never wrong; it was starved. One
anchor, one peer, 8 events is not a meaningful test of "does this effect
exist among lower-coverage peers" regardless of what it finds. HYP-06
asks the identical question, with a universe systematically discovered
rather than hand-guessed.

**Reused verbatim from HYP-05's own already-settled decisions** -- not
re-decided, because these are method choices, not universe-contingent,
and re-litigating them now (after seeing which peers the universe
contains) would be exactly the outcome-driven redesign this project's
`NEVER_CONDITIONS` pattern exists everywhere to forbid:

- **Target/outcome definition**: `target.py`'s residualized log
  realized-variance ratio, `model_spec.residualize=True`, same horizon
  grid HYP-05's Phase 2 lock used (pinned by `target_py_sha256` in
  `HYP05_PHASE2_LOCK_2026-09-12.json`).
- **Coverage/liquidity threshold**: `MARKET_CAP_THRESHOLD_USD =
  2,000,000,000`, RATIFIED (not provisional) in `peer_selection.py`
  2026-09-12, externally grounded (the conventional small/mid-cap
  boundary), unchanged.
- **Clustering**: `event_id` primary (mirrors `clustered_se.HYP05_TWO_
  WAY_LIMITATION_NOTE`), `calendar_period` as the secondary one-way
  robustness lens reported alongside it, never a two-way estimator --
  identical to HYP-05's own re-decision away from HYP-04's D1-locked
  `calendar_period`-only choice.
- **Point-in-time discipline**: `peer_selection.py`'s PS-4 (as_of_date
  strictly precedes anchor_event_date) -- added THIS session after the
  scaled search surfaced the gap, so HYP-06 inherits the FIXED rule, not
  the gap HYP-05's own original 8-event pilot happened never to trigger.

**The one thing that is genuinely new**: the anchor/peer universe itself.
Not chosen by looking at which peers "look promising" -- it is exactly,
and only, the output of `derive_peer_universe()`'s real, fail-closed,
PS-1..PS-4 run recorded in `HYP05_PEER_UNIVERSE_SCALED_2026-09-13.json`.
Every qualifying (peer, event) pair in that artifact is in HYP-06's
universe; no pair is added, removed, or re-weighted by hand.

## 3. What this means for the four decisions a fresh hypothesis owes

Mirroring exactly how HYP-05's own plan (§5) listed its four open items,
before any of them were resolved:

1. **The liquidity/coverage cutoff.** RESOLVED -- reused from HYP-05
   (§2 above), not re-chosen.
2. **The target anchor/peer universe.** RESOLVED -- the round-6 discovery
   output, in full (§2 above).
3. **The target/outcome definition.** RESOLVED -- reused from HYP-05
   (§2 above).
4. **Clustering.** RESOLVED -- reused from HYP-05 (§2 above).

Unlike HYP-05's own registration (deliberately light, all four still
open), HYP-06 registers with all four already resolved -- the discovery
work that resolves #2 already happened, dated and committed, before this
plan was written. Nothing here is decided by looking at the outcome any
observation would produce, since no outcome (return, shock-response,
target value) has been computed for any HYP-06 pair as of this writing --
only market cap, disclosure dates, and relationship direction, all of
which are `NEVER_CONDITIONS`-clean inputs already fixed before this plan.

## 4. Sample-size gate

**778 qualifying pairs clears any plausible floor by a wide margin.**
HYP-05's own operative floor was PROVISIONAL (195 anchor events, borrowed
from HYP-04's measured k range, since HYP-05 had no locked design yet to
measure a real k for). HYP-06 reuses that SAME provisional floor for the
same reason HYP-05's own gate document gives -- a real max-T permutation
measurement against a synthetic fixture shaped like HYP-06's actual
776-cluster design is the correct eventual step (mirroring how HYP-04's
own provisional "190-240" was later superseded by its measured 193), but
building and validating that measurement correctly is real, separate work,
out of scope for this pass, and is not needed to clear a floor 778 already clears
4x over even at the conservative (195) end. See
`HYP06_SAMPLE_SIZE_GATE_2026-09-13.md`.

## 5. What is explicitly NOT decided by this document

- **No freeze, lock, or Phase 1-3 machinery.** This document only states
  the hypothesis and its four resolved decisions. Registration, Phase 2
  locking, and Phase 3 authorization are separate, later, separately
  authorized steps -- same discipline as every prior hypothesis.
- **No claim of significance, or of any result at all.** No target value
  has been computed for any pair in this universe. This document is not
  evidence about supply-chain earnings-information transmission.
- **No re-measurement of the sample-size gate.** Flagged in §4 as the
  natural next refinement, explicitly out of scope here.
