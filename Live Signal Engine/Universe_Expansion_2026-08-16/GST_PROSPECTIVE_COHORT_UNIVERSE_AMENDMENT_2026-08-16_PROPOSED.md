# Proposed Cohort/Universe Amendment — 2026-08-16 (PROPOSED, NOT ACTIVE)

> ## PROPOSAL ONLY · NOT ACTIVE · NOT AN S&P DJI CONSTITUENT FILE
> ## CURRENT 24 REMAIN OPERATIVE · F5 REMAINS OPEN · COLLECTION REMAINS BLOCKED
> ## NO PRODUCTION QUERY CHANGED

**Append-only.** This amendment does not rewrite, delete, rename or supersede
`GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json`, its predecessors, or any historical cohort document.
Those remain byte-identical and operative. This file proposes an addition and nothing more.

---

## Why 24 was the starting scope

The original 24 tickers were an **operational starting scope, not a statistically derived optimum**.
They were inherited verbatim from the Phase 2 daily-panel universe — a list chosen to get a retrieval
pipeline working across a manageable number of issuers, at a time when the binding constraint was
whether attention and market data could be captured reliably at all. No power calculation, no
cluster-count target, and no sampling frame produced the number 24. It was never claimed to be
sufficient; it was claimed to be *tractable*.

## Why expansion happens now

**Because nothing has been observed yet.** At the moment of this proposal: `results` is null,
`frozen_event_ids` is empty, `eligible_events_now` is 0, and `screening_rows` is empty. **Zero
HYP-01-eligible prospective observations exist.**

That is the only honest moment to change a sampling frame. Expanding after any eligible event had
been observed — or after any effect estimate, direction or p-value existed — would make the universe
outcome-dependent, and no amount of documentation could repair that. Expanding now costs nothing in
integrity precisely because there is nothing yet to be influenced by.

## Why 50

50 is a **governance judgment**, offered as such and not as a derived optimum:

- **Recruitment.** HYP-01 needs 60 eligible events. At roughly four earnings events per issuer per
  year, 24 issuers make the arrival rate the binding constraint. Doubling the frame roughly halves
  the expected calendar time to reach the freeze threshold.
- **Cluster diversity.** Inference is clustered on ticker. 24 clusters sits in the range where the
  PR #17 grid showed CR1 over-rejecting in every null cell tested, and where the Satterthwaite df ran
  well below the nominal cluster count. More issuers means more clusters — though **this is a
  structural argument, not a demonstrated power claim**, and D16's prohibition on project-derived
  power claims is unaffected.
- **F5 workload.** Every added ticker needs its own construct-validity assessment. F5 is already
  open for 24. Fifty is roughly twice that workload — large enough to matter, small enough to remain
  auditable by one reviewer.
- **Operational feasibility.** The retrieval, screening and dossier pipelines are exercised at 24.
  50 is an increment those pipelines can plausibly absorb; several hundred is not.

**50 is not claimed to be optimal, sufficient, or empirically justified.** It is a defensible
round number chosen before any outcome existed, and it is recorded as such.

## What this amendment asserts

1. **All original 24 remain.** Not removed, renamed, reordered or replaced. They occupy positions
   1–24 of the proposed universe in their existing order.
2. **The additional 26 were selected without outcome or attention information.** Selection was a
   SHA-256 over a fixed prefix and the ticker, sorted ascending, first 26 taken. No price, return,
   volatility, volume, liquidity, spread, options data, market capitalization, index weight, earnings
   surprise, analyst data, news, sentiment, strategy performance, site accessibility, earnings-date
   availability, expected eligibility, anticipated effect or subjective familiarity entered the
   computation. The selection rule was frozen and hashed **before** the candidate names were known.
3. **No failed ticker will be replaced.** If an added ticker later fails F5, has an ambiguous search
   construct, lacks an accessible issuer page, produces missing data, fails an eligibility gate, or
   contributes no usable event, that outcome is **recorded honestly and the ticker is not swapped
   out**. Backfilling from rank 27 onward is prohibited, because a universe that heals its own
   failures is a universe selected on outcomes.
4. **The first-60-eligible-events rule is unchanged.** The freeze threshold, the single-run
   requirement, the prohibition on optional stopping, and the extension-cohort rule for later events
   are all untouched.
5. **D1–D16 are unchanged.** The dated statistical-method amendment of 2026-08-16 is not amended,
   reinterpreted or reopened by this file.
6. **DELL's registration is unchanged.** `EVT-DELL-FY27Q2-ERN` remains the sole registry row,
   byte-identical, subject to every rule identically.
7. **F5 remains OPEN.** This amendment does not resolve construct validity for the original 24 and
   creates 26 more tickers for which it is equally unresolved.
8. **Collection remains BLOCKED.** Expanding a candidate frame is not authorization to screen,
   enroll, capture or observe anything.
9. **Expansion does not establish construct validity.** Adding tickers says nothing about whether a
   Google Trends series measures attention to the intended company. If anything it enlarges the F5
   problem rather than shrinking it.
10. **External preregistration has not occurred.** No submission to any external timestamped
    registry has been made, and completing internal locks does not substitute for one.

## Source, stated precisely

The candidate pool came from **the dated official iShares OEF holdings snapshot, used as an
identity-only proxy for the S&P 100 investable universe** (as-of Aug 13, 2026). It is **not** the
index provider's canonical constituent list. S&P Dow Jones Indices' own export was unobtainable
because its security controls blocked access; those controls were **not** retried, evaded, proxied
around, or circumvented.

A fund's holdings file may differ from index membership through sampling, timing, corporate actions,
cash positions and derivative overlays. **A reviewer who considers that proxy unacceptable should
reject this proposal on that ground** — it is disclosed here precisely so the choice is reviewable
rather than buried.

## Activation

**This amendment is not active.** Activation would require a separate, explicit authorization after
independent review, and would additionally require changing the production universe constant — which
this proposal deliberately does not touch.
