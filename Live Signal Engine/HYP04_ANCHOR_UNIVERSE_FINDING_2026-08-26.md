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

---

## AMENDMENT — 2026-08-27: option 3 was taken

**Section 5 above says "Options, none taken". That is no longer true**, and this
amendment records what changed rather than editing the sentence that has since
been superseded.

**Option 3 was taken.** Registry
[`v1.5`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5.json) records that HYP-04's
anchor universe differs from HYP-01's, deliberately, under a stated
HYP-04-specific rule. Options 1, 2 and 4 remain untaken: the locked 24-ticker
universe is unmodified, no linkage edge was curated among the locked 24, and
the question is no longer left open.

Not as a list, though. The finding's own framing of option 3 — "making the 98
candidates meaningful" — would have amounted to naming MCK and PKG into a
universe *because they are the tickers that turned out to have edges*. What
v1.5 registers instead is a **rule** (`HYP04-ANCHOR-UNIVERSE-RULE-v1`,
implemented in `hyp04_supply_chain_hedge/anchor_universe.py`), evaluated over
the 51-ticker frame that already existed, with its threshold and denominator
taken from ASC 280-10-50-42 rather than chosen.

**Applying it yields one member: MCK.**

| | |
|---|---|
| MCK | qualifies — CVS Health Corporation, **24% of consolidated revenue**, 10-K filed 2026-05-08 |
| PKG | **does not qualify** — its 58% is of the **Paper segment**, and the same sentence puts the entity-wide figure at 4% |

That PKG is excluded is the point, not a defect. PKG is one of only two
companies in the screen with a named counterparty and one of the two curated
edges; a rule fitted to the observed set would have kept it. The
segment-inclusive variant that would have retained PKG is recorded in v1.5 as
considered and rejected, with its reason.

### What this amendment does not change

Section 4's measurement stands unaltered: the screen still finds **zero** named
counterparties among the locked 24, and the four false positives are still
rejected by the two attribution gates. Section 3's disclaimer also stands —
this was never asserted to be a bug, and v1.5 does not treat it as one.

**No gate moved.** The display gate reads **CLOSED, C4 MET, 4 denials** before
and after, and C2 still counts zero eligible anchor events: declaring who may
be an anchor creates no eligible anchor event for anybody.

One extractor change was required to make the rule mechanically applicable.
`edgar_linkage` now records each concentration percentage's **denominator**,
verbatim and classified — the anchors had always captured it in a `basis` group
that nothing read. Without it, "58%" and "24%" and "21%" were three different
quantities being compared as if they were one.

---

## AMENDMENT — 2026-08-27: the "zero among the locked 24" measurement was an artifact

**This amendment corrects the central measurement of section 4.** That section
reports, and section 4's closing sentence turns on, the claim that extraction
over 51 tickers found **zero** named counterparties among the locked 24. The
extraction was run correctly and the number was true of what it read. It is not
true of the locked 24.

**It read only each filer's newest 10-K.** `extract_for_universe()` calls
`client.latest_10k()`, so the screen could only see concentrations still
disclosed in 2026. Evaluating the same unchanged rule against every 10-K in
force from 1996 to 2026 — 1,250 filings, all 51 frame members, zero retrieval
failures — finds that **three locked-24 members qualify**:

| Locked-24 member | Span | Disclosure |
|---|---|---|
| **AAPL** | 2000-12-14 → 2002-12-19 | Ingram Micro Inc, 11.5% of net sales |
| **CTSH** | 2004-03-12 → 2005-03-16 | JP Morgan Chase, 10.1% of revenues |
| **INTC** | 2005-02-22 → 2017-02-17 | Dell Inc, 19% of total sales |

So the finding's conclusion — *"the anchors that have linkage edges are outside
the locked universe, and the anchors inside the locked universe have no linkage
edges"* — **does not hold**. Its second half was an artifact of the corpus, not
a property of the locked 24. Apple, Cognizant and Intel each disclosed a named
≥10% customer concentration; all three had simply stopped by 2026.

### What still stands

- **Section 1 stands.** MCK, PKG, CVS and ODP are still absent from
  `locked_universe_v0.1.json`. That was a fact about a list, not about filings.
- **Section 2 stands.** An MCK earnings event still has no route to becoming a
  core-eligible anchor event, because no capture path runs over it. Membership
  is not eligibility, and widening the universe changes no counter.
- **Section 3 stands.** This was never asserted to be a bug, and it still is not.
- **Section 6 stands.** The two attribution gates added on 2026-08-26 were
  correct for the filings they were tested against, and both are still in force.

### Why the error is worth recording rather than quietly fixing

The gates were built against 2026 prose and were right for it. Widening the
corpus by twenty-five years raised the false-positive rate with no code change
at all — the gates did not regress, the corpus outgrew them. Eight fabricated
counterparties were found and rejected across two rounds before the number
above could be trusted, and the first round was a spot check that missed three
of them. **A screen's coverage is part of its result**, and this document
reported a number without reporting what the screen could see.

Recorded in registry v1.6 and in
[`HYP04_ANCHOR_UNIVERSE_POINT_IN_TIME_FINDING_2026-08-27.md`](HYP04_ANCHOR_UNIVERSE_POINT_IN_TIME_FINDING_2026-08-27.md).

**No gate moved:** CLOSED, C4 MET, 4 denials.
