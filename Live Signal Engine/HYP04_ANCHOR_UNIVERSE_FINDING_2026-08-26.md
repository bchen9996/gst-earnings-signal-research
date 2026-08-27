# HYP-04 finding — the curated map's anchors are outside the locked universe (2026-08-26)

**Status: FINDING, not a fix.** Nothing was changed in response to it. No gate
moved; the display gate reads **CLOSED, C4 MET, 4 denials** before and after.

---

## 1. The observation

None of the four companies in HYP-04's curated linkage map appear in the
project's locked ticker universe.

| | in `locked_universe_v0.1.json` |
|---|---|
| **MCK** — curated `anchor_ticker` | **no** |
| **PKG** — curated `anchor_ticker` | **no** |
| **CVS** — curated `peer_ticker` | **no** |
| **ODP** — curated `peer_ticker` | **no** |

The canonical universe is 24 tickers: AAPL, ABBV, ADBE, AMZN, BKR, BRK-B, CTSH,
DELL, DVN, GME, GOOGL, GPN, INTC, LDOS, MSFT, NCLH, NKE, QCOM, SBUX, STZ, SYK,
TSLA, TTWO, UAL.

`gst_market_response/constants.py` mirrors it under
`LOCKED_24_TICKER_UNIVERSE`, states *"No code path in this package may add,
remove, or reorder this list"*, and `test_market_response_canonical_drift.py`
compares the mirror against the canonical JSON element by element.

MCK and PKG are in `run_canary_audit.candidate_peer_universe()` — the Phase 0
**peer** universe. CVS and ODP are in neither list.

## 2. Why it matters

Registry v1.4 records HYP-04's `required_eligibility_class` as
`core_attention_vs_equity_response`, with the note:

> This is the ANCHOR-side requirement only: an anchor event must itself be
> core-eligible for its earnings shock to be usable.

Core-eligibility is decided by
`gst_market_response.completeness.is_eligible_for_hypothesis`, which reads
`ModuleEligibility.core_pre_event_eligible` — a per-event record. Those records
come from the capture pipeline, and that pipeline runs over the locked
universe.

So an MCK earnings event has no route to becoming a **core-eligible anchor
event** while MCK is outside that universe. The 98 candidate anchor events
derived on 2026-08-24 (MCK 56, PKG 42) are real, correctly dated releases —
and none of them can currently count toward **C2**, which requires 193
*eligible* anchor events.

## 3. What is NOT claimed

**This is not asserted to be a bug.** Three things cut against that reading:

- `curated_linkage.known_universe()` is documented as *"for the ticker WARNING
  only ... it never constrains what a curated map may contain"*. An
  out-of-universe anchor is explicitly permitted by the loader, by design.
- `is_eligible_for_hypothesis` contains no ticker or universe logic at all. It
  reads a boolean off a record. Nothing structurally forbids an MCK record.
- HYP-04 is `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`. An unimplemented
  measurement having an unresolved universe question is a normal state, not a
  defect.

What *is* claimed is narrower and checkable: **as the code stands, the curated
map's anchors cannot produce eligible anchor events.** Either the universe
changes, or the anchors do, or eligibility records reach these tickers by some
route that does not exist today.

## 4. The compounding measurement

Extraction over 51 tickers on 2026-08-26 (`edgar_linkage`, latest 10-K,
customer-concentration disclosure) found **2 companies with a named
counterparty: MCK and PKG** — the two already curated.

Among the **locked 24 specifically, it found zero.**

The first run appeared to find three more — INTC, LDOS, NKE — all of which are
locked-24 members. All three were false positives:

| Extracted | Actual filing text | What it is |
|---|---|---|
| `INTC → "U.S"` 70% | "sales **outside the U.S.** accounted for 70% of our revenue" | geography |
| `NKE → "United States"` 44% | "sales **in the United States** accounted for ~44% of total revenues" | geography |
| `LDOS → "Digital"` 44% | "National Security & **Digital** represented 44% of total revenues" | own segment |
| `LDOS → "Defense Systems"` 13% | "**Defense Systems** represented 13% of total revenues" | own segment |

They are now rejected by two attribution gates, with all four kept as
regression fixtures in `test_hyp04_supply_chain_hedge_edgar.py::test_6e` using
verbatim filing text. See §6.

**So the two facts together are the finding:** the anchors that have linkage
edges are outside the locked universe, and the anchors inside the locked
universe have no linkage edges.

## 5. Options, none taken

1. **Extend the locked universe** to include MCK and PKG. This is a
   preregistration-level change to a list the code says no path may modify,
   guarded by a drift test against a canonical JSON, and shared with HYP-01.
   It is not a HYP-04 decision.
2. **Curate linkage edges among the locked 24.** Measured yield from 10-K
   customer concentration: zero. ASC 280 requires disclosure only at ≥10% of
   revenue, and most filings name no counterparty. A different source —
   supplier agreements, segment disclosure, trade press — would be needed, and
   each carries its own provenance question.
3. **Record that HYP-04's anchor universe differs from HYP-01's**, deliberately,
   in a registry version — making the 98 candidates meaningful under a stated
   HYP-04-specific rule rather than the locked universe.
4. **Leave it.** HYP-04 is not implemented and displays nothing. This
   costs nothing today and is discovered again by whoever tries to make C2 move.

## 6. Changed by this investigation

Only the extractor, and only to stop it fabricating:

- `GEOGRAPHIC_PARTY` — a bare place name is never a counterparty.
  `NON_CUSTOMER_SUBJECT` already blocked the *words* "geographic", "region" and
  "country"; none of the false-positive sentences contains one.
- A name is kept only if the **sentence itself** establishes a counterparty, or
  the name carries a **legal** entity suffix. `CORP_SUFFIX` could not serve
  here: it includes "Systems", "Technologies" and "Group", which is also how
  filers name their own segments — "Defense Systems" among them.

The ±400-character topic window was **not** narrowed. It exists so a role word
in a neighbouring footnote sentence still counts, and the regression test pins
that case: *"Concentration of credit risk. … Apple Inc. accounted for 22% … No
other customer exceeded 10%"* is still captured.

Nothing in this document is evidence about supply-chain transmission.
