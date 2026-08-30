# HYP-04 anchor-event calendar — the feasibility question, measured

**Dated finding, 2026-08-29.** Append-only. Supersedes no artifact; corrects two
figures this session produced, both of which were estimates.

**Artifacts:**
[`HYP04_ANCHOR_EVENT_CALENDAR_2026-08-29.json`](HYP04_ANCHOR_EVENT_CALENDAR_2026-08-29.json) ·
[`HYP04_ANCHOR_EVENT_CALENDAR_2026-08-29.csv`](HYP04_ANCHOR_EVENT_CALENDAR_2026-08-29.csv)

> **Nothing here is evidence about supply-chain transmission, and nothing here
> moves the display gate.** The gate is **CLOSED, C4 MET, four denials**, and
> the eligible-event count for HYP-04 is still **zero**.

---

## 1. The question

Registry v1.9 leaves one question open by name:

> *"It does not decide feasibility. Whether enough eligible anchor events can
> exist is a separate question this version does not touch and does not
> answer."*

Every figure this project has had for it was an **estimate** — member-years
multiplied by an assumed 4.25 releases a year. Two such estimates were produced
earlier in this same session (~217 events under registry v1.7's universe, ~382
under v1.8's). Neither was derived, and both are now superseded by a count.

The two ingredients existed and had never been crossed:

- the point-in-time anchor universe — **11 membership intervals over 8 tickers**,
  derived from the pinned linkage history
- candidate anchor events — derived from 8-K item tagging

## 2. The answer

**321 distinct candidate anchor events fall inside a span during which their
filer was a registered HYP-04 anchor.** Of those, **306 have a resolved release
session** (BMO or AMC), which is the tighter ceiling because AS-1 cannot be
satisfied without one.

The registered threshold is **193 anchor events**. The strict calendar clears it
by **128**, or **1.66×**; the session-resolved subset clears it by **113**.

| interval | candidate events |
|---|---|
| INTC 2005-02-22 → 2025-01-31 | 85 |
| JBL 2001-11-28 → 2025-10-17 | 87 |
| MCK 2013-05-07 → *(open)* | 56 |
| NVDA 2002-05-14 → 2012-03-13 | 33 |
| ADBE 2008-01-24 → 2015-01-20 | 30 |
| MCK 2000-06-13 → 2008-05-07 | 16 |
| NVDA 2016-03-17 → 2018-02-28 | 8 |
| NVDA 2020-02-20 → 2021-02-26 | 4 |
| CTSH 2004-03-12 → 2005-03-16 | 2 |
| AAPL 2000-12-14 → 2002-12-19 | 0 |
| NKE 2002-08-14 → 2004-07-30 | 0 |

**This does not mean C2 can be met.** A candidate is an 8-K; an eligible anchor
event is a candidate that survives `HYP04-ANCHOR-SHOCK-RULE-v1`, which needs the
anchor's and the benchmark's closes for the attributed session. **No price
source has been decided for HYP-04**, no shock has been computed from production
data, and the eligible count is zero. What changed is that the ceiling is now
known to be above the floor. Whether the floor is reachable underneath it is
still open.

## 3. A defect found by making a false claim

I asserted that this derivation needed no SEC requests, having verified by hash
that every submissions block for all eight members was already in the on-disk
cache. The run then reported **`requests_made = 20`**.

`earnings_events.all_item_202_records` called `EdgarClient._get` — the **raw
transport**, which sits *below* the on-disk cache and *below* the `offline=True`
guard. So an `EdgarClient` constructed as offline reached `data.sec.gov` anyway,
while the cache reported zero hits because it was never consulted.

`OfflineCacheMiss` exists in this repo for exactly this, and says so:

> *"Deliberately fatal. The alternative — quietly reaching the network from a run
> the caller asked to be offline — is how a 'no requests made' claim becomes
> false without anyone noticing."*

It could not fire, because nothing on that path ever asked it to. **Fixed**
(`_get` → `_get_json`, two lines), with a regression test whose stub `_get`
raises, plus a control proving the trap is armed and a check that a real offline
client over an empty cache raises `OfflineCacheMiss` rather than attempting a
request. After the fix the same derivation reports **0 live requests and 21
cache hits**, with numbers identical to the live run.

The 20 requests were real, paced, and within fair access. The problem is not
their cost; it is that a guarantee this repo relies on was not in force.

## 4. Two ways the raw count was wrong

### 4.1 The same release filed twice — 18 cases

Of 339 results filings inside membership spans, **18 release dates carried two
8-Ks**. The shape is identical every time: one accepted on the release day just
after the 16:00 close through a filing agent, and a second carrying the **same
`reportDate`** accepted days later at an intraday hour. INTC does this every
quarter from 2009-10 to 2013-10 — same-day through agent CIK `0001157523`, then
a re-filing under Intel's own CIK `0000050863`.

Counting both is wrong twice over. It double-counts one release, and because the
re-filing lands intraday it resolves to **UNKNOWN** — so the duplicate also drags
an unusable session into the set. **17 of the 32 UNKNOWN sessions in the raw
calendar were re-filings of a release whose same-day filing is cleanly AMC.**

**Rule adopted:** one anchor event per `(anchor_ticker, release_date)`; **earliest
acceptance wins**, ties broken on accession. Earliest acceptance because that is
when the news reached the market — the quantity both the session attribution and
the shock depend on — and a later re-filing of the same results cannot make the
release later. Every displaced filing is recorded in `superseded` with the
accession that displaced it; nothing is dropped silently.

Effect: 339 → **321**, and UNKNOWN sessions 32 → **15**.

### 4.2 The item code is an artefact of its era

`earnings_events` selects on **Item 2.02**. Measured across all eight members,
the earliest Item 2.02 in the data is **2004-09-20**, and seven of the eight fall
in September–October 2004. That is not a change in corporate behaviour:

| era | code for a results release |
|---|---|
| before **2003-03-28** | none exists — Item 5 or Item 7, same as every unrelated 8-K |
| **2003-03-28 … 2004-08-22** | **Item 12** |
| from **2004-08-23** | **Item 2.02** |

Item 12 was created by the Regulation G release; SEC Release 33-8400 renumbered
it to 2.02 effective 2004-08-23.

**NKE is the clean case.** Inside its 2002-08-14 → 2004-07-30 span it has **zero**
Item 2.02 filings and **six** Item 12 filings. Its zero is the renumbering, and
nothing else. AAPL's zero is different and worse: its whole span predates Item 12,
so no index-level rule can see its releases at all.

This is the principle already settled twice here — **data availability must not
decide membership**, and **a filer changing print format is not a changed
relationship**. A regulator renumbering a form item is not a filer that stopped
reporting earnings.

**But adopting Item 12 is a specification change, so it is NOT the default.**
`accept_legacy_item_12` defaults to `False`, reproducing the existing rule
exactly. Both totals are derived and published side by side:

| rule | candidates | session resolved |
|---|---|---|
| **Item 2.02 only (unchanged, primary)** | **321** | **306** |
| Item 12 recovered (measured, not adopted) | 342 | 324 |

Measuring a change is not making it. **This is a decision for the repo owner**
(§7).

A *modern* code before the renumbering date is a data anomaly, not a licence: it
is counted under the strict rule and **flagged**. Exactly one exists — NKE
2001-12-16 — and it falls outside NKE's membership span, so it enters no total.

## 5. What is still invisible

**7.6 member-years fall entirely before 2003-03-28**, when no earnings-specific
item code existed. Those years hold roughly 30 quarterly releases that **no
index-level rule can recover** — reaching them means reading filing text, which
is a different and much more expensive walk.

Recorded as measured under-inclusion. It is not a reason to doubt the 321; it is
a reason the true ceiling is higher than 321 and the gap is quantified rather
than hand-waved.

## 6. What this does not do

- **It measures no transmission.** No return, no shock, no peer response, no
  effect estimate, no p-value.
- **It creates no eligible anchor event.** C2 counts eligible events. It still
  counts zero.
- **It moves no gate.** C1 (status), C3 (freeze) and C5 (linkage, 2 curated
  draft rows) deny exactly as before, and C4 stays MET. **CLOSED, four denials.**
- **It does not decide the peer side.** A calendar of anchor events says nothing
  about whether peer closes can be obtained for them.
- **It changes no registry version.** v1.9 stands unedited.

## 7. Open, for the owner

1. **Adopt Item 12 for its own era?** Recommended: yes — the argument is the
   same one already accepted for print format, and it is the difference between
   NKE contributing 0 events and 6. It is a specification change, so it belongs
   in a registry version with the exception named, not in a quiet default flip.
2. **The day-0 reference window**, still open from the shock memo §6.2 and
   v1.9's `known_limitations`. Unaffected by this finding, and now more
   consequential, since there are 321 events for it to apply to.
3. **The peer price source**, now the binding constraint on the anchor side as
   well: without closes there is no shock, and without a shock a candidate
   cannot become eligible.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
