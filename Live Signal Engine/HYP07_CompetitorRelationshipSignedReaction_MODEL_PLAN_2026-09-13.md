# HYP-07: Competitor-Relationship Signed Reaction — Build Plan (2026-09-13)

**Status:** proposal / not yet preregistered. Written to define what this
hypothesis is, why it is a genuinely different mechanism from HYP-04/05/06
rather than another rescale of the same one, and what is and is not
already decided, consistent with this project's HYP-01/HYP-04/HYP-05/
HYP-06 discipline.

## 1. Where this comes from

HYP-04, HYP-05, and HYP-06 all tested the same mechanism — delayed
transmission of earnings-surprise information from a large "anchor" to a
smaller supply-chain-linked "peer" (customer/supplier relationships),
using a direction-agnostic residualized log realized-variance-ratio
target (`target.py`). All three came back null, most recently HYP-06
(2026-09-13): 778 real, hand-verified pairs, peak t=1.30 vs a critical
value of 2.70 (p=0.62).

Rather than rescale the same mechanism again, the owner chose a genuinely
different one: **competitor relationships**, where the predicted reaction
is the OPPOSITE sign (a rival's bad quarter should be good news for you),
not just "did volatility spike." Because the prediction is directional,
reusing HYP-04/05/06's magnitude-only target would only test "did the
competitor react at all" — so this pass built a new signed target,
`target_signed.py`, as part of the same push that built the discovery
pipeline.

Discovery followed the same proven pivot that rescued customer/supplier
discovery in round 4: reverse EDGAR full-text search, rather than forward
extraction (a filer's own 10-K naming its "most prominent" rivals, which
was tried first and diagnosed as structurally biased toward large,
ineligible names — see
`HYP07_DISCOVERY_AND_TARGET_METHODOLOGY_2026-09-13.md`, "Step 0"). The
reverse search was first run against 27 hand-curated anchors, then scaled
to the full 788-anchor Russell1000Proxy universe this session, mirroring
round 6's own scaling move. The scaled run found, and a human read in
full, **371 confirmed competitor-relationship leads (370 kept, 1
rejected)**, yielding a real, fail-closed, point-in-time-correct universe:
**195 qualifying (peer, anchor_event) pairs, 6 distinct peer tickers**
(`HYP07_PEER_UNIVERSE_REVERSE_SEARCH_SCALED_2026-09-13.json`).

## 2. What's new here, and what's reused

Unlike HYP-06 (which reused HYP-05's target/outcome definition and
clustering choice verbatim, because it was testing the identical
question), HYP-07 is a different question with a different formula. Two
of the four decisions a fresh hypothesis owes are genuinely new; two are
reused unchanged because they are project-wide conventions, not
mechanism-specific choices:

**Genuinely new:**

- **Target/outcome definition.** `target_signed.py`'s signed cumulative
  abnormal return — `signed_car(h) = Σ(benchmark-adjusted peer log
  returns over the post-event window) − h × (peer's own pre-event
  20-session reference-window mean)` — fixed beta=1.0 against SPY (same
  convention `anchor_shock.py`'s AS-2 already uses, applied peer-side),
  log returns throughout. First use of a SIGNED target in this project;
  HYP-04/05/06 all used the magnitude-only residualized log
  realized-variance ratio. Written and offline-tested
  (`test_hyp04_supply_chain_hedge_target_signed.py`) before any outcome
  value was computed for any real HYP-07 pair — no computation of any
  kind has been performed against the actual 195-pair universe as of this
  writing, only market cap, disclosure dates, and relationship direction.
  **Not yet Phase-2-locked** — to be pinned by sha256 at HYP-07's own
  Phase 2 lock, the same step every prior hypothesis's spec was pinned
  at.
- **The anchor/peer universe.** Not chosen by looking at which peers
  "look promising" — exactly, and only, the output of
  `derive_peer_universe()`'s real, fail-closed PS-1..PS-4 run recorded in
  `HYP07_PEER_UNIVERSE_REVERSE_SEARCH_SCALED_2026-09-13.json`. Every
  qualifying pair in that artifact is in HYP-07's universe; no pair is
  added, removed, or re-weighted by hand.

**Reused verbatim, because these are project-wide method conventions, not
universe- or target-contingent:**

- **Coverage/liquidity threshold.** `MARKET_CAP_THRESHOLD_USD =
  2,000,000,000`, RATIFIED in `peer_selection.py` 2026-09-12, unchanged.
- **Clustering.** `event_id` primary (anchor_ticker + anchor_event_date),
  `calendar_period` as a one-way robustness lens reported alongside it,
  never a two-way estimator — the same convention HYP-05/06 already
  re-decided on, away from HYP-04's D1-locked `calendar_period`-only
  choice.
- **Point-in-time discipline.** `peer_selection.py`'s PS-4 (as_of_date
  strictly precedes anchor_event_date), the same fixed rule HYP-06
  inherited.

## 3. What this means for the four decisions a fresh hypothesis owes

1. **The liquidity/coverage cutoff.** RESOLVED — reused unchanged (§2).
2. **The target anchor/peer universe.** RESOLVED — the round-7 scaled
   discovery output, in full (§2).
3. **The target/outcome definition.** RESOLVED — `target_signed.py`, new
   and not yet locked (§2).
4. **Clustering.** RESOLVED — reused unchanged (§2).

Nothing here is decided by looking at the outcome any observation would
produce: no target value (signed CAR, beta, t-stat) has been computed for
any HYP-07 pair as of this writing — only market cap, disclosure dates,
and relationship direction, all `NEVER_CONDITIONS`-clean inputs fixed
before this plan.

## 4. Sample-size gate — clears the floor, but exactly, not comfortably

`HYP07_SAMPLE_SIZE_GATE_2026-09-13.md` reuses HYP-05's own provisional
floor (195 pairs, borrowed from HYP-04's measured k range 6.05–6.34) — the
same number HYP-06 also reused. **This is a weaker borrow than HYP-06's
own reuse of the same numbers**: HYP-06 at least shared HYP-05's identical
target formula, so the correlation structure the original k range was
measured against was, at minimum, the same formula on a different
universe. HYP-07's target (`target_signed.py`) is a genuinely different
formula — a cumulative sum that plateaus across horizons, not the
diluting-mean ratio the original k range was measured against — so this
borrow is used only because no HYP-07-shaped measurement exists yet, not
because the analogy is expected to hold tightly.

**The real universe (195 of 625 evaluated candidates) clears this floor
at exactly 195 — not comfortably above it the way HYP-06's 778 cleared
the identical floor by nearly 4x.** This is disclosed deliberately, not
rounded away: see `HYP07_SAMPLE_SIZE_GATE_2026-09-13.md` for the full
number. `fixtures_signed.py` (built this session, offline-tested) makes a
real max-T permutation measurement against a synthetic fixture shaped
like HYP-07's actual design possible in principle; it is not performed in
this pass.

A separate, real caveat about the two lowest-market-cap peers (GLUC,
SCSC — market caps running into the low hundreds-of-thousands to
single-digit-millions range) is disclosed in
`HYP07_DISCOVERY_AND_TARGET_METHODOLOGY_2026-09-13.md` — a genuine
liquidity/data-quality concern, not a rule violation (the $2B threshold
has never had a lower bound by original v1.8 design).

## 5. What is explicitly NOT decided by this document

- **No freeze, lock, or Phase 1-3 machinery.** This document only states
  the hypothesis and its four resolved decisions. Registration, Phase 2
  locking, and Phase 3 authorization are separate, later, separately
  authorized steps — same discipline as every prior hypothesis.
- **No claim of significance, direction, or of any result at all.** No
  target value has been computed for any pair in this universe. This
  document is not evidence about competitor-relationship earnings-
  information transmission, in either direction (displacement or
  comovement).
- **No re-measurement of the sample-size gate.** Flagged in §4 as the
  natural next refinement, explicitly out of scope here, though
  `fixtures_signed.py` makes it more reachable than it was for HYP-05/06
  at their own registrations.
