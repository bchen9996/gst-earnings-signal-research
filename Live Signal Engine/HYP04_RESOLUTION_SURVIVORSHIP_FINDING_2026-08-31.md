# Two silent defects, and why the worklist can only ever find survivors

**Dated finding, 2026-08-31.** Append-only.

**Artifacts:**
[`HYP04_PEER_CEILING_2026-08-31_v3.json`](HYP04_PEER_CEILING_2026-08-31_v3.json) ·
[`HYP04_PEER_CURATION_WORKLIST_2026-08-31_v3.csv`](HYP04_PEER_CURATION_WORKLIST_2026-08-31_v3.csv)

> **Gate CLOSED, C4 MET, four denials, eligible-event count zero.** Nothing here
> is evidence about supply-chain transmission.

---

## 1. A correction: I fixed one of two call sites

I reported that `closes_requirements` had been moved off the 2006-bounded
calendar. That was true of `_load_sessions` and **false of the module**.
`_events_from_csv` still called
`gst_market_response.exchange_calendar.compute_expected_next_full_trading_session_xnys`.

Running the CLI against the real anchor calendar died on the first event:

```
DateOutOfBounds: Parameter `date` receieved as '2003-08-07' although cannot be
earlier than the first session of calendar 'XNYS' ('2006-08-31').
```

Every pre-2006 event — 57 of 342. The module was unusable on its own primary
input and nothing said so, because nothing had run it end to end.

**Fixed** by reusing `anchor_closes.resolve_attributed_session`, which was
already written for exactly this: it takes the session index as an argument and
returns a *reason* rather than raising. An event the index cannot serve now
joins the `unresolved` list with an explanation — which is what every other
branch of that function already did. The CLI now completes, reporting 18 UNKNOWN
sessions and 20 P3-denied pairs, and emits the 2,200-row CVS request.

`event_panel`'s guidance was the same defect one level up: its warning string
told callers to resolve dates with the bounded function. Corrected to point at
`resolve_attributed_session`, with a note not to use the bounded one.

## 2. Artifact selection was going to break at `_v10`

Four places picked the newest artifact with a lexical filename sort:
`dashboard._newest`, `make_anchor_shocks._newest_calendar`,
`make_peer_ceiling._newest`, `run_peer_lineage_audit._newest`.

Lexical order puts `_v10` **before** `_v2`. Measured on
`_v2`/`_v3`/`_v10`, it picks **`_v3`**.

It does not raise and it does not return empty. It silently reads a superseded
artifact and renders it as current — on a page whose entire job is to state what
is true now, and in builders that re-derive from whatever they are handed.

The counter climbs precisely when corrections are happening: this work alone
produced `_v2` and `_v3` of the peer-ceiling artifacts in a day, and
`HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-08-27_v4.json` already exists. The
worst moment to start reading the superseded copy is the moment you are
superseding things.

New `artifacts.py` sorts on `(base name, revision as an INT)`. The date lives in
the base and ISO dates sort correctly as text, so a later date still beats any
revision of an earlier one. A `_v2` in the *middle* of a name is not a revision,
and neither is the `v1.10` in a registry filename — both asserted.

## 3. The resolver can only ever return survivors

Not a defect. A structural property, and the number the registry decision needs.

`resolve_counterparty` matches against SEC's `company_tickers.json` — a list of
companies that file and trade **today**. A counterparty that was delisted,
merged away, taken private, or never a US filer **cannot resolve at all**. Not
because the matcher is imperfect: because there is nothing to match against.
Widening the matcher cannot fix it. Only a source that includes former
registrants can.

| | |
|---|---|
| incremental events the queue could add | **270** |
| reachable by name resolution | **161** |
| **behind names the method cannot reach** | **109** |

**40% of the queue's reach sits behind names the resolver structurally cannot
see**, and they are exactly the population the policy warns about:

| counterparty | anchor | events |
|---|---|---|
| Dell Computer Corporation | JBL | 89 |
| Marconi Communications | JBL | 89 |
| Hewlett-Packard Company *(pre-split)* | JBL | 88 |
| Royal Philips Electronics | JBL | 88 |
| Nokia Corporation *(ambiguous NOK/NOKBF)* | JBL | 80 |
| Lenovo Group Limited | INTC | 46 |

`peer_price_data_policy`'s own reasoning applies one level earlier than it was
written for. The peers most likely to have disappeared are those acquired or
taken private, and **acquisition is frequently caused by the commercial
relationship under study** — so the unreachable counterparties are not missing at
random with respect to this hypothesis. The bias runs toward the null: the edges
hardest to find are disproportionately the ones where the relationship mattered
most.

**It does not claim every unresolved name is a delisted company.** Some are
ambiguous, some foreign-listed, some brands or subsidiaries that were never
registrants. The point is that the method cannot tell those apart from
survivors, which is why the whole set is the exposure.

## 4. Why this was worth measuring now

`peer_price_data_policy` states its own escape hatch: restricting to survivors is
permitted **"only if the restriction and its bias are stated in the registry
version that does it."**

A statement of bias needs a number. This is that number, for the *curation*
step — and it is separate from, and prior to, the same question about the price
source. Even a perfect survivorship-bias-free price feed would be applied to a
peer set assembled by a survivor-only method.

That is a decision for the repo owner, and it is a registry decision. Nothing
here takes it.

## 5. What this does NOT do

- **It curates nothing and selects no price source.**
- **It does not move C2 or C3**, which move together or not at all.
- **The worklist rows are unchanged from `_v2`** — only the measurement is new.
- **It measures no transmission.**

## 6. Supersession

`_v1` and `_v2` of the ceiling and worklist remain on disk **byte-identical**.
`_v3` records both sets of SHA-256s and the suite asserts all four still match.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
