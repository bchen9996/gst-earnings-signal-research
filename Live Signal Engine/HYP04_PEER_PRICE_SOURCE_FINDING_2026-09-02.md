# HYP-04 peer price source — collected, and the bias measured

**Date:** 2026-09-02
**Status:** measured. Records what was collected and what it costs. Adopts nothing on its own.

---

## 1. What changed

The peer price source has been the binding constraint since 2026-09-01, when
curating five draft rows into `HYP04_Linkage_Map_v1.1.csv` took the peer-side
ceiling from 54 anchor events to 215 against a registered floor of 193. Before
that, curation bound and prices were irrelevant; after it, prices bound and
curation did not.

Prices are now collected, for all six curated peers that carry anchor events.

| peer | sessions | window | events |
|---|---|---|---|
| CSCO | 3716 | 2003-08-20 → 2025-10-23 | 89 |
| CVS | 2200 | 2013-04-09 → 2026-06-08 | 54 |
| AAPL | 2142 | 2012-11-20 → 2025-10-23 | 51 |
| BB | 1974 | 2013-11-18 → 2025-10-23 | 47 |
| MSFT | 1764 | 2004-04-07 → 2021-03-25 | 42 |
| HPQ | 1260 | 2017-03-29 → 2025-03-03 | 30 |
| **total** | **13,056** | | **313 pairs** |

**13,056 of 13,056 requested sessions filled. Zero missing, zero rejected
values, every panel `loads_clean` and `usable`.**

The seventh curated peer, ODP, carries no request: PKG has zero anchor events
in the calendar, so the PKG→ODP edge is inert and ODP's delisting costs
nothing. That is worth stating precisely, because ODP is the `measured_instance`
in `peer_price_data_policy` — the case that motivated the policy. It remains
unobtainable, and it remains irrelevant to this sample.

## 2. The ceiling was honest

Per-pair coverage, computed from the collected closes with
`peer_returns.coverage_for_event`:

```
pairs covered  313
pairs short      1
events with >=1 covered peer   215      registered floor  193
```

The ceiling artifact's "peer prices assumed" hypothetical said 215 events and
313 pairs. The assumption turns out to have been almost exactly right, which is
the outcome a stated hypothetical is supposed to be checkable against.

The single shortfall is **CVS on MCK-2026-08-05**, whose 20-session horizon runs
past today. That is a right-edge truncation — a future-dated event, not a data
gap — and it becomes collectable once those sessions trade. It is reported as
truncated rather than clipped, per `closes_requirements`.

## 3. The per-peer unit would sink the sample

Running the join both ways over identical data:

| unit | events | vs. floor 193 |
|---|---|---|
| per-pair, `coverage_for_event` | **215** | clears by 22 |
| per-peer, `peer_history_map` | **161** | fails by 32 |

`peer_history_map` marks a peer available only if it covers **every** event it
appears in. The one uncollectable CVS event therefore marks CVS unavailable for
all 54 of its events. The function's own docstring calls the unit lossy and says
it "undercounts, which is the safe direction" — and in general it is. Here,
undercounting is the difference between clearing the registered floor and
failing it.

**Consequence:** the real-data panel assembler must consume the per-pair path.
This was already a design preference, recorded open on 2026-08-22 as "whether P5
should become per-pair". It now has a measured cost: **54 events.**

## 4. A discrepancy, recorded and not resolved

Under assumed prices, resolving events through `closes_requirements`
(BMO/AMC resolved to the response session) gives **216** events carrying a peer.
The ceiling artifact, resolving through `events_from_calendar`, gives **215**.

After real coverage removes the truncated CVS pair, this route also gives 215.
The two figures agree numerically but **are not demonstrated to be the same
event set**. Reconciling them belongs to the panel assembler. It is recorded
here rather than assumed away, because two routes agreeing by coincidence is
exactly the kind of thing that reads as confirmation.

## 5. The bias this restriction imports

The source is survivors-only. `peer_price_data_policy` permits that "only if
the restriction and its bias are stated in the registry version that does it",
so the numbers are here and the registry version is v1.11.

```
queue candidates                                36
  resolved to a ticker                           8
  unresolvable                                  28   (27 no exact match, 1 ambiguous)
incremental anchor events behind unresolvable names   106
```

Named among the unreachable: **Dell, Ingram Micro, Tech Data, Foot Locker,
Rite Aid**. All are identified and lineage-confirmed; none can be resolved
against SEC's list of companies that file and trade today.

**Why this biases toward the hypothesis.** The policy's own reasoning applies:
the peers most likely to have disappeared are those acquired or taken private,
and acquisition is frequently *caused* by the commercial relationship under
study. The 106 unreachable events are therefore **not missing at random with
respect to HYP-04**. This is stated in the direction that is inconvenient,
because that is the direction it runs.

**What it does not touch.** All seven curated peers trade today, so the
restriction costs the present 215 events nothing. It bounds *future* curation,
not this sample. The two facts are separate and neither excuses the other.

## 6. The dividend-adjustment basis

Collected on `split_and_dividend (yfinance auto_adjust=True)`, matching the
anchor decision of 2026-08-31.

- **Splits must be adjusted.** An unadjusted 2-for-1 prints roughly −69% on a
  quiet day, and the target's RVar is a sum of squares, so one such day can
  dominate a 41-session window.
- **The dividend choice is a genuine judgment call**, and it changes the target.
  `run_peer_closes_fetch` prints exactly that warning on every run and notes the
  choice is registered nowhere. v1.11 is where it stops being unregistered.

**The split-only variant is declared but NOT collected**, and that distinction
matters. v1.10's day-0-inclusive robustness variant needs no second collection
because `closes_requirements.session_span` deliberately emits the wider span. A
split-only price series is **a different series** and cannot be derived from the
dividend-adjusted one. Declaring it without collecting it would put a robustness
check in the registry that no one can run. It is registered as promised, not
available, and it requires its own fetch of ~13,000 rows.

## 7. What this does not do

Nothing here is a measurement of the hypothesis. No target value, no `beta_h`,
no peer response, no horizon, no direction has been computed from these prices.
What is counted is **data availability** — how many anchor events carry a peer
with sufficient price history — which is publishable under the display-gate
convention. What these prices imply is not.

The display gate is **CLOSED**, C4 MET, four denials, eligible event count
**zero**. Collecting closes moves none of that: C2 counts *eligible* anchor
events, and C2 and C3 move together or not at all.

---

*Nothing in this document is evidence about supply-chain transmission. No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.*

*Nothing in this document constitutes investment advice, a solicitation, or a
representation that any approach is profitable.*
