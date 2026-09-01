# The peer side's blockers were in the wrong order

**Dated finding, 2026-08-31.** Append-only.

**Artifacts:**
[`HYP04_PEER_CEILING_2026-08-31.json`](HYP04_PEER_CEILING_2026-08-31.json) ·
[`HYP04_PEER_CURATION_WORKLIST_2026-08-31.csv`](HYP04_PEER_CURATION_WORKLIST_2026-08-31.csv)

> **The display gate is CLOSED, C4 MET, four denials, and the eligible-event
> count is still zero.** Nothing here is evidence about supply-chain
> transmission. No peer return has been measured. No pair is eligible.

---

## 1. The claim this corrects

Since the anchor side finished, this project has said — in the last finding, in
two dashboard panels, and in its own memory — that **the peer price source was
the sole remaining blocker**. That was an ordering asserted from impression, and
it is wrong.

The correction is a number. Run the real join —
`linkage_resolution.resolve_from_curated_map` over the real 342-event calendar
and the real 324 shocks — with peer price availability supplied as a **stated
hypothetical**, so that P5 stops denying everything and the conditions behind it
become visible:

| | |
|---|---|
| anchor events the curated map could reach | **54** |
| registered floor | **193** |
| shortfall | **139** |
| reached today (measured, prices unknown) | **0** |

**A survivorship-bias-free price source bought tomorrow would not raise that by
one event**, because the ceiling run already assumes one exists. Curation binds
first. Prices bind second.

## 2. The measured price failure sits on an edge that costs nothing

The curated map holds two rows. `peers_never_evaluated` reports that one of
them, **PKG → ODP, is never evaluated at all** — not denied, never asked. PKG is
not in the anchor universe, so no calendar event has PKG as its anchor.

ODP is the **measured instance** behind `peer_price_data_policy`: the provider
returns zero rows for it across its entire history, and that finding is why the
peer source has been described as blocking. It is a real survivorship failure
and the policy that came from it is right. But the edge it sits on **cannot
supply a single pair**, so it was never the thing capping the sample.

What actually caps the sample is the other row, MCK → CVS, at 54 MCK events
after 2013-05-07 that carry a shock. That is the whole hypothesis.

This distinction only exists because the report separates "never evaluated" from
"denied". A denial profile alone would have shown P3 and P1 and said nothing
about ODP, because ODP never reached a condition to fail.

## 3. Both numbers are published, and why the honest one is not enough

**Measured**, exactly as it stands: **0 pairs**, 76 evaluated, denials
`{P5: 76, P3: 21, P1: 1}`. Every pair dies on P5 — no peer price source — so
P5 masks everything behind it. That is the honest state and on its own it is
uninformative: it cannot distinguish a map that would yield 500 events from one
that would yield 54.

**Ceiling**, prices assumed: **54 pairs on 54 events**, denials `{P3: 21,
P1: 1}`. The hypothetical is confined to one argument, and what it produces is
labelled a ceiling everywhere it appears.

A ceiling is a **sample-size feasibility count** — the same category as the 342
anchor events and the options-coverage audit, publishable for the same reason.
It is not eligibility. `CeilingReport` has no `eligible` field and the tests
assert it never gains one: that word belongs to `pair_eligibility`, which is the
only module entitled to use it.

## 4. What would move it, ranked

`HYP04_PEER_CURATION_WORKLIST_2026-08-31.csv` ranks the EDGAR review queue by
how many anchor events each candidate counterparty could add. The count is
**anchor-side only** — this anchor's shock-carrying events strictly after the
earliest filing that disclosed the counterparty — which is why it is derivable
today, with no peer ticker, no prices and no curation.

| | |
|---|---|
| candidate counterparties on the 7 anchor tickers | 35 |
| resolved to a ticker by exact SEC match | 8 |
| left UNRESOLVED for the curator | 27 |
| distinct anchor events spanned by the 8 resolved | **231** |
| distinct anchor events spanned by all 35 | **324** |

**231 > 193.** The material to reach the registered floor already exists on
disk, in a queue built from filings, every row carrying the accession that
disclosed it.

It is a **union, not a sum**. Candidates on one anchor cover overlapping
stretches of the same event list, so adding `max_anchor_events` would
double-count heavily.

And it is a ceiling on a ceiling. Curating a candidate can only lower it: a
rejected as-of date moves later, and a rejected relationship removes the row.

## 5. The two lines this work does not cross

**A resolved name is not a curated edge.** The worklist's columns are provably
disjoint from `curated_linkage.REQUIRED_FIELDS`, so `load_curated_linkage`
rejects the published file **on its header** — asserted against the real
artifact, not a fixture. `refuse_if_curated_schema` enforces the same property
at build time, because the failure it prevents is silent: a map that loads is a
map that runs. Without it, a column rename would turn 35 unreviewed candidates
into a linkage map nobody curated.

**Resolution refuses to guess.** Exact match on the normalised SEC company title
or nothing. Two filers sharing a name come back AMBIGUOUS with both candidates
named, not resolved by coin flip. A self-link comes back with its reason
visible. A near-miss is a non-match, never a nearest neighbour. There is no
score field a caller could act on, and no fuzzy matcher is imported.

**Every resolution carries a lineage hazard, and says so.** SEC's ticker map
describes companies as they are *today*; the names come from filings made years
earlier. Matching them answers "does a company with this name exist now?", never
"is it the same company that was named then?" This project has already refused
that inference twice — **Caremark RX** for MCK and **OfficeMax** for PKG, both
because a merger is not a rename. So every resolved row carries
`requires_lineage_review=yes` and the years elapsed, and no row is promoted
automatically. Several of the 8 are exactly this hazard.

The 27 unresolved names are also informative: they are enriched in delisted,
taken-private and foreign-listed companies — the population
`peer_price_data_policy` warns about. That is a survivorship observation about
the queue, recorded, not acted on.

## 6. A recorded follow-on, closed

`closes_requirements._load_sessions` called
`gst_market_response.exchange_calendar.is_trading_day`, carrying the same
2006-08-31 default bound found on the anchor side. It did not raise — it
returned **False for every earlier date**, so a pre-2006 peer event would have
produced a request that was **short rather than one that refused**.

It now uses `sessions.xnys_sessions`, which reaches back to 1995 and verifies
itself against the authoritative instance across the whole overlap. Out-of-range
dates now raise, and `main` reports them. Measured: 2003 returns **252
sessions**, where the old path returned 0.

## 7. What this does NOT do

- **It does not open the gate, and it does not move C2.**
  `display_gate.current_decision()` passes a literal `eligible_event_count=0`
  and cross-checks it against a freeze record that does not exist. **C2 and C3
  move together or not at all.**
- **231 is not a met threshold, and neither is 324.** Both are unions over
  unreviewed candidates under an assumption about prices. No candidate is
  curated, no as-of is ratified, no resolution has passed lineage review.
- **It curates nothing.** No row was promoted, no counterparty became an edge,
  and no linkage data was invented.
- **It measures no transmission.** No peer return has been computed at all.

## 8. Still open

- **The peer price source.** Still unselected, and still required before any
  measurement — but now correctly ordered *behind* curation.
  `peer_price_data_policy` already states its own escape hatch: restricting to
  survivors is permitted "only if the restriction and its bias are stated in the
  registry version that does it." Taking it would need a new registry version.
- **The C5 linkage map**, still two curated rows — now with a ranked worklist
  in front of it.
- **C2/C3**, separate and separately authorised.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
