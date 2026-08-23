# HYP-04 peer-side return capture — decision record (2026-08-22)

**Decision:** the peer-side return-series capture path is built as `hyp04_supply_chain_hedge/peer_returns.py`, **operator-fed and provider-free**, with the trading-session index **injected** rather than imported.

**Status:** capture path built and tested (69 checks). **It does not close registry gap (2)** — that is a registry statement and only a governed version bump can make it. The display gate is unchanged: **CLOSED, C4 MET, exactly 4 denials.**

---

## What prompted it

Registry v1.2 records three missing capture paths in HYP-04's `status_basis`:

> "(1) The supply-chain/competitor LINKAGE MAP does not exist in any form … (2) There is no production capture path for PEER-side price or volatility series; no module ingests peer returns for a registered event. (3) There is no production join mapping a market-response event_id to any peer observation."

Gap (3) was addressed by `linkage_resolution.py`. Gap (1) is a curation question and is now partly overtaken by events — two edges are curated, which is why the registry's `availability: does_not_exist` is itself stale and awaiting a governed correction. Gap (2) was the last of the three that could be *built* without first resolving a registry question, so it was taken next.

## What was built

A validating ingestion path from operator-supplied closing prices to per-peer daily log returns aligned to a shared session index, plus a derived answer to the question `pair_eligibility` condition **P5** asks.

## The four constraints, and where each comes from

### 1. It never touches a provider

Same rule `gst_market_response.pre_event_capture` states for itself: no network client, no credential read, no price lookup. Closes are handed in; this module validates them.

A future fetcher can feed this module. This module cannot summon a fetcher — which is what stops a live call from ever happening implicitly. It is the same reasoning `requirements-hyp04.txt` gives for excluding `yfinance`: make the unwanted path fail at the boundary rather than succeed quietly.

### 2. It never imports the exchange calendar

`gst_market_response.exchange_calendar` is the authoritative XNYS session source, and it imports `exchange_calendars` — which **`requirements-hyp04.txt` deliberately does not install**, because HYP-04's CI job is scoped to its own dependency file.

Importing it would break that job at import time. So **the session index is injected**: callers pass the ordered sessions they want returns aligned to. Anything running under the full `requirements.txt` can pass the authoritative calendar's sessions in and get authoritative alignment; HYP-04's own tests pass an explicit list. The module gets calendar correctness without taking a calendar dependency.

This is enforced, not documented: the suite parses the module's own AST and asserts its only non-stdlib import is in-package, and separately asserts no heavy dependency appears in `sys.modules`. That second check passes **while `exchange_calendars` is installed in the local venv**, so it is testing the module's behaviour rather than the environment's contents.

### 3. Coverage is derived, never asserted

This is the same safety property `LinkageProvenance` applies to `uses_placeholder_linkage`, applied to the other end of the pair.

P5 asks whether a peer has usable return history around an event, and denies when the answer is unknown. Today the answer is supplied by the caller — and a caller that can simply assert `True` makes P5 an honour system in exactly the way an assertable `uses_placeholder_linkage` would have made C5 one.

So **nothing in this module accepts an availability flag.** `coverage_for_event()` computes it from the series: whether the reference window and the full horizon grid are populated with finite returns.

### 4. Gaps are never bridged

A missing close kills the return on **both** adjacent sessions. A return spanning a gap is not a one-session return, and admitting it would inflate realized variance exactly where the data is worst — the direction that manufactures a signal rather than hiding one.

Missing is `None`, never `0.0`. A zero return is a real observation (a halt, a flat close) and must not be confused with absent data.

## The window rule, and why it is asserted against `target.py`

Coverage windows mirror `target.raw_log_ratio_target` exactly:

| Window | Span |
|---|---|
| reference | the 20 sessions ending **at** the anchor day |
| post-event | `[anchor_day + 1, anchor_day + 20]` |

Every return in **both** must be finite. A partially-populated reference window is not a shorter reference window: `RVar_ref` is a mean over a fixed count, and averaging over fewer days silently changes the estimator.

The suite asserts agreement with `raw_log_ratio_target` at **every** day index, not at sampled ones. If the two ever disagree, pairs get counted eligible whose target then evaluates to `NaN` — inflating the eligible-pair count with observations that silently vanish later, which is the worst of the available failure modes.

**Writing that test surfaced a real distinction.** The first version encoded missing returns as `0.0` to hand them to the target function, and it disagreed at exactly one day. The disagreement was correct: index 0 can never carry a return, because no prior close exists inside the index — and the `0.0` substitution had fabricated the very observation the module refuses to invent. The fix was to encode missing as `NaN`. The module was right; the test had been lying to it.

## The per-peer unit is lossy, and resolves conservatively

Coverage is really a property of a **(peer, event) pair** — a peer listed since 2015 has coverage for a 2020 event and none for a 2010 one.

`resolve_from_curated_map` takes **one bool per peer**. `peer_history_map()` therefore marks a peer available only if it covers **every** event it appears in. That **undercounts**, which is the safe direction and the one this package already takes on every unknown. `coverage_for_event()` remains available for the precise per-pair answer, and is what a Phase 1 sample construction should use.

This is recorded as a known limitation rather than silently absorbed.

## What this does NOT do

- **It does not close registry gap (2).** A module existing and a registry acknowledging it are two different facts. The registry is append-only; only a governed bump by the repo owner can record the change.
- **It opens no gate.** C1–C5 are untouched; the gate stays CLOSED with the same four denials. Peer returns are not linkage, so C5 denies exactly as before — asserted directly by the suite.
- **It curates no data and fetches nothing.** No network call is made or made possible.
- **It changes no existing file.** The change is two new files; `git status` showed only untracked entries.

## Verification

- `test_hyp04_supply_chain_hedge_peer_returns.py` — 69 checks, 0 skips
- Full sweep: **1293 pass / 0 skip / 0 failing** across 16 suites, including `test_market_response_cohort_protocol.py` (128), the control proving no eligibility class was added
- Gate after the change: **CLOSED, C4 MET, exactly 4 denials** — unchanged

**Mutation-tested**, because a suite that cannot fail proves nothing. Three deliberate defects were injected and each was caught:

| Mutation | Caught by |
|---|---|
| coverage always sufficient (hardcoded-open) | 10 checks, incl. every P4/P5 denial and the `target.py` agreement |
| coverage never sufficient (hardcoded-closed) | 7 checks, incl. the positive controls |
| gaps bridged by carrying the last close forward | `2b` — the mutation that would manufacture signal |

A fourth attempt (removing the gap guard outright) crashed instead of failing a check; it was discarded as an invalid mutation rather than counted as a caught one.

The module was restored from a byte-level backup afterwards and confirmed by SHA-256 to be identical.

## Open, and deliberately not decided here

- **Registry v1.3.** Two facts in v1.2 are now stale — linkage `availability: does_not_exist`, and gap (2)'s "no module ingests peer returns". Both need the owner's governed correction, including the vocabulary question of whether two curated edges are `exists` or something like `exists_partial`.
- **Where the closes come from.** This path validates operator-supplied prices. Choosing a provider, and whether that provider's history is point-in-time honest, is a separate decision with the same look-ahead exposure the linkage as-of dates carry.
- **Whether P5 should become per-pair.** The lossy per-peer unit is safe but wasteful. Changing it touches `resolve_from_curated_map`'s signature, which is in flight.
