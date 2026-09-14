# HYP-07: competitor-relationship discovery + a new signed target (2026-09-13)

**Result: a real, non-null candidate universe (90 qualifying pairs, 2 peers)
found via reverse search, plus a new, validated signed-return target
methodology. No registration, lock, or Phase 3 authorization exists yet --
this document covers tooling and discovery only, per the approved plan's
own scope.**

## Context

HYP-04, HYP-05, and HYP-06 all tested the same mechanism -- delayed
transmission of earnings-surprise information from a large anchor to a
smaller supply-chain-linked peer (customer/supplier relationships, found
via ASC 280 customer-concentration disclosures) -- using a direction-
agnostic residualized log realized-variance-ratio target. All three came
back null, most recently HYP-06 (778 real pairs, peak t=1.30 vs a critical
value of 2.70, p=0.62).

The owner chose to pivot to a genuinely different mechanism: **competitor
relationships**, where the predicted reaction is the *opposite* sign (a
rival's bad quarter should be good news for you) -- a different economic
claim than "did volatility spike," which is all the RVar-ratio target can
detect. Rather than reuse that target verbatim, the owner explicitly chose
to build a new signed abnormal-return target so the sharper, directional
claim actually gets tested.

## Step 0: the 56 already-extracted competitor edges -- a free sanity check, correctly null

HYP-05's own first pass (2026-09-12) already ran the calibrated, wired-in
`extract_competitor_edges_from_text()` against anchors' OWN filings (latest
10-K and a full historical walk) and diagnosed a real structural bias: it
surfaces only a filer's most PROMINENT named rivals, which then fail the
<$2B market-cap eligibility test. 56 competitor edges from that work sat
unused across three JSON files. Name-resolving all 52 distinct names found
8 tradeable tickers; evaluating the 2 with existing anchor-event coverage
(GlobalFoundries/INTC, Shutterstock/ADBE) against real market cap and
point-in-time eligibility gave **0 of 108 qualifying pairs** -- GFS
confirmed too large ($25-30B, same finding HYP-05 already made), SSTK's
2016 disclosure date postdates every available ADBE anchor event (2008-2014
only), the same "dead end" shape as SHOE/NKE in HYP-05's own round 4-5. The
other 6 resolved tickers (Flowserve, Halliburton, NOV, SLB, TechnipFMC,
Roblox) were not pursued further -- all are well-known large/mega-caps
(SLB alone is a $50B+ company), and spending real provider budget on new
anchor-shock fetches for BKR/TTWO to confirm a near-certain "too large"
outcome was judged not worth it.

This result was predicted, not just found: forward extraction from an
anchor's own filing structurally surfaces prominent names, and prominent
names are large. It confirmed the plan's own stated expectation before
moving to Step 1.

## Step 1-2: reverse search finds real, smaller competitors

The proven fix is the same pivot that rescued customer/supplier discovery
in round 4: search EDGAR's full-text corpus, unscoped by CIK, for [an
anchor's name] AND [a phrase] -- so a SMALL company's OWN 10-K surfaces
directly, rather than depending on the anchor's own filing naming it.
`run_hyp07_reverse_competitor_search.py` swaps the phrase set to literal
instantiations of `edgar_linkage.COMPETITOR_ANCHORS`'s three real,
calibrated regex patterns ("principal competitors include", "we compete
with", etc.), searched against the same 27 anchors round 4 used (for
direct comparability, not the 788-anchor scaled universe -- that remains
an explicit next step).

**276 distinct (anchor, peer_cik) leads discovered, 33 confirmed** (real,
readable sentences matching a calibrated `COMPETITOR_ANCHORS` pattern) --
a 12% confirmation rate, lower than round 4's 71% for customer/supplier
concentration language (expected: competitor mentions carry no equivalent
mandatory disclosure, so more of what full-text search surfaces is noise).

**Every one of the 33 was hand-reviewed, same discipline as every prior
round.** None were rejected as false positives -- the plan's own
anticipated new false-positive genre (market-share/industry-structure
sentences, the Movie Gallery/Carnival PLC shape from HYP-05's hand review)
did not actually recur here; every confirmed sentence directly claims the
filer itself competes with the anchor. Two entries name the anchor via a
subsidiary rather than its core business (Encore Wire vs. Cerrowire, a
Marmon/Berkshire Hathaway company; Omnicell vs. McKesson Automation Inc.)
-- kept, flagged, since the disclosure is real and the relationship's
economic strength is for the statistical test to judge, not curation. One
entry's stored evidence was truncated by a 400-character display limit
before reaching the anchor's name (DJ Orthopedics/SYK) -- verified by
fetching the real filing directly; the full sentence is genuine
("...our competitors include Aircast, I-Flow Corp., Orthofix and Stryker
Corporation").

**A real schema bug found and fixed along the way**: FISERV INC genuinely
recurs as a confirmed competitor under three different anchors (AAPL,
GOOGL, SBUX -- a near-identical "newer competitors include..." sentence
across different fiscal years' filings). Round 4's own `Decision` type,
keyed by `peer_cik` alone, would have silently collapsed these three real,
distinct anchor-pairs into one. Fixed in both the hand-review module and
`run_hyp07_peer_market_cap.py`'s own candidate-resolution join by keying on
`(anchor_ticker, peer_cik)` instead -- the same fix round 6 already made
for the customer/supplier scaled search, rediscovered here independently
because HYP-07's own data exposed it, and regression-tested in both
modules.

## Step 3: real eligibility -- 90 of 274 pairs qualify

Of the 33 hand-reviewed leads, 16 resolved to a tradeable ticker. Of those,
6 anchors had existing shock-computed anchor-event coverage (ADBE, CTSH,
DELL, GOOGL, JBL, MCK); the rest (ABBV, BKR, BRK-B, GPN, LDOS, QCOM, TTWO)
did not and were not pursued this pass, matching Step 0's own scoping
decision.

**Real result: 90 of 274 (peer, anchor_event) pairs qualify, across 2
distinct peer tickers:**

| peer | anchor | qualifying pairs | date range | market cap range |
|---|---|---|---|---|
| BHE (Benchmark Electronics) | JBL | 60 | 2010-09-27 .. 2025-09-25 | $713M - $1.72B |
| OMCL (Omnicell) | MCK | 30 | 2013-05-07 .. 2026-08-05 | $630M - $1.97B |

Both comfortably (BHE) or narrowly (OMCL, approaching the $2B ceiling near
the top of its range) clear the eligibility threshold throughout. OTEX/ADBE
(29 events) and CNDT/CTSH (3 events, one yfinance data gap for 2004-2005
pre-spinoff Conduent) had real anchor-event coverage but did not produce
any qualifying pairs on their own merits.

**90 pairs is short of HYP-06's own 195-pair provisional floor** (46% of
it) -- a real, disclosed limitation, not hidden. It is a substantially
better starting point than HYP-05's own 8-event pilot (24x short), though
not yet at HYP-06's 778-pair, floor-clearing scale. Scaling this same
reverse-search mechanism to the 788-anchor Russell1000Proxy universe
(mirroring round 6) would very plausibly multiply this yield the way it
did for customer/supplier discovery (17 -> 277 confirmed leads, a 16x
increase, when round 4's 27-anchor pilot scaled to round 6's 788) -- named
here as the obvious next step, not attempted in this pass.

## Step 4: a new, validated signed target

`target_signed.py` implements `signed_car(h)` -- a signed cumulative
abnormal return, built from the SAME already-validated event-study
machinery HYP-04/05/06 use (fixed beta=1.0 against SPY, the same
20-session reference window, log returns throughout) but summed rather
than variance-ratio'd, so it preserves direction instead of discarding it.
Deliberately does NOT port `target.py`'s bucketed earnings-cycle
residualizer -- that machinery removes a magnitude confound with no
obvious signed analog; a constant-mean reference-window baseline is the
stated v1 simplification.

Nothing about the sign convention is flipped anywhere -- the anchor's raw
signed `excess_return` (already computed and stored by `anchor_shock.py`,
just never read before now) and the raw signed `signed_car` are used
as-is, and the fitted peak beta's sign is read directly: negative confirms
competitive displacement, positive would indicate comovement instead
(flagged explicitly, never silently relabeled as confirming), not
significant is a null. Proven mechanically inconsequential by a dedicated
algebraic test: flipping every event's shock sign flips only the recovered
beta's sign -- `|beta|`, `se`, `t_stat`, `satterthwaite_dof`, and
`max_t_p_value` are bit-for-bit unchanged.

Validated end-to-end through the REAL, completely unmodified `inference.py`
pipeline (`local_projection_analysis`, `fit_local_projections`, the max-T
permutation null) on synthetic fixtures with a known, injected signed
effect: a negative injected effect recovers a negative, significant peak
beta; a positive injected effect recovers a positive, significant peak
beta (proving the pipeline distinguishes direction, not merely "some
relationship" -- the one thing a sign-agnostic pipeline could get right by
accident); a zero-effect fixture is correctly not significant.

**One real methodological caveat, disclosed in the module's own docstring**:
`peak_horizon` means something different here than for HYP-04/05/06.
RVar(h) is a MEAN over an expanding window that DILUTES with unaffected
days, so its peak necessarily lands at the end of the true reaction window.
`signed_car(h)` is a CUMULATIVE SUM that PLATEAUS instead of diluting. A
future HYP-07 result's `peak_horizon` should be read as "where the
cumulative effect saturates," not compared directly against a HYP-04/05/06
peak as if the two measured the same geometric thing.

## What this pass does NOT do

No registry entry, no Phase 2 lock, no Phase 3 authorization or run, no
sample-size gate, and no 788-anchor scaled search -- all explicitly out of
scope for this pass, named as real next steps rather than attempted here.
The 90-pair universe found in Step 3 has not been locked or tested against
anything; no target/outcome value has been computed for either BHE or OMCL
around any anchor event using either the old RVar-ratio target or the new
signed one.
