# HYP-04 anchor-event source — 8-K Item 2.02 (2026-08-23)

**Artifact:** [`HYP04_ANCHOR_EVENT_CANDIDATES_2026-08-23.csv`](HYP04_ANCHOR_EVENT_CANDIDATES_2026-08-23.csv)
**Producer:** `hyp04_supply_chain_hedge/earnings_events.py`
**Run:** `--ticker MCK --since MCK:2013-05-07 --ticker PKG --since PKG:2016-02-26`

> **These are CANDIDATES, not eligible events.** They have not been screened
> against HYP-01's rules, `eligible_event_counts` is unchanged, and no
> display-gate condition moved. The gate reads **CLOSED, C4 MET, 4 denials**
> before and after.

---

## 1. What the source is

Item 2.02 of Form 8-K — *Results of Operations and Financial Condition* — is
the filing obligation a company discharges when it releases earnings. Walking
it gives the dates on which an anchor actually reported, with SEC's own
acceptance timestamp attached.

The `--since` dates are the curated edges' `as_of_date`s. Peer-eligibility
condition **P3** counts an edge only for anchor events *strictly after* it, so
releases before those dates would only produce rows the analysis must discard.

## 2. The finding that changes the answer: `filingDate` is not the release date

SEC stamps a submission accepted after **17:30 ET** with the *next business
day* as its `filingDate`. `reportDate` is the day the results were released.

Measured across the full walk:

| | accepted | `reportDate` == `filingDate` |
|---|---|---|
| **MCK** | 16:05–16:07 ET | **54 of 55** |
| **PKG** | 17:48–18:18 ET | **5 of 42** |

PKG's five exceptions were accepted **17:09–17:27 ET** — just inside the
cutoff. The mechanism is exact, not approximate.

**An implementation reaching for `filingDate` would be perfect on MCK and one
day late on 37 of 42 PKG events.** After the AMC next-session rule that is one
*session* late, which extends the reference window past the news — the
look-ahead direction. `test_3` pins a PKG-shaped record to the report date;
the mutation fails 7 checks.

## 3. How BMO/AMC is derived

`acceptanceDateTime` is UTC, converted to `America/New_York` (both EST and EDT
occur in the real data, so a fixed offset is wrong half the year):

| acceptance, ET, on the release date | verdict |
|---|---|
| ≥ 16:00 | **AMC** |
| < 09:30 | **BMO** |
| 09:30 – 16:00 | **UNKNOWN** |
| a different calendar day | **UNKNOWN** |

Acceptance time is when the 8-K reached EDGAR, not when the wire went out. For
Item 2.02 the two are close — Reg FD pushes companies to furnish at release —
but *close* is not *equal*, so the bands are wide and the middle of the day
refuses rather than guesses. Every verdict carries the timestamp it came from.

**Result: 78 AMC, 17 BMO, 2 UNKNOWN.**

MCK's split is genuine, not noise. Its BMO releases were all accepted
**07:04–08:11 ET** and cluster in 2013–2021; it settled into AMC around 2022.
Assuming "MCK is always AMC" would mis-date **17 of 55** events.

## 4. The two unresolved events, and why they are not guessed

| | `reportDate` | items | accepted |
|---|---|---|---|
| MCK | 2023-10-27 | 2.02,**5.02**,7.01,9.01 | 2023-11-01 16:05 EDT |
| PKG | 2020-07-24 | 2.02,**2.06**,9.01 | 2020-07-28 17:29 EDT |

`reportDate` is the date of the *earliest* event reported, and an 8-K may
report several. Both of these bundle an earnings release with an unrelated
earlier item — 5.02 is a director/officer change, 2.06 a material impairment —
so `reportDate` belongs to the other item and the release is the acceptance
date.

Both already resolve to UNKNOWN, because acceptance falls on a different day
than `reportDate`, and both carry `non_standard_items`. The shape routes itself
to a human. Deciding which of several bundled items a `reportDate` refers to is
not something the module can do correctly, and a wrong guess is a mis-dated
anchor event — the exact failure it exists to prevent.

**Action required:** resolve these two by hand, or drop them. 95 of 97 need
nothing.

## 5. Item 2.02 is a floor, not a census — one confirmed miss

A company can file its earnings release without tagging Item 2.02, and MCK did:

| | |
|---|---|
| Accession | `0000927653-20-000013` |
| Filed | 2020-02-04, accepted **07:10 ET → BMO** |
| Items | **`9.01` only** — no Item 2.02 |
| Document | `mck8-k12312019.htm`, with a 1 MB press-release exhibit |
| SGML header | `ITEM INFORMATION: Financial Statements and Exhibits` |

That is McKesson's Q3 FY2020 earnings release — quarter ending 2019-12-31 —
and the Item 2.02 filter cannot see it. **An absent candidate is therefore not
evidence the company did not report.**

`find_cadence_gaps()` was added because of this. It reports any interval
between consecutive releases longer than 130 days, which is what a missed
release looks like:

```
MCK  GAP 2019-10-30 -> 2020-05-20 (203 days)
PKG  none
```

It deliberately does **not** fill them. The only reliable signal that a
9.01-only filing is an earnings release is the filer's document-naming
convention, which varies by filer and would silently mis-tag some other filing
as an anchor event. Detect, and route to a human.

An empty gap list means the cadence is unbroken, **not** that coverage is
complete — a miss at either end of the range leaves no gap to find.

**Action required:** MCK 2020-02-04 (BMO) is verified and can be added by hand.
It is not written into the CSV here, because that file is generated and a
hand-inserted row would be indistinguishable from a derived one on the next
regeneration.

## 6. What this does and does not get you

| | |
|---|---|
| Candidate releases | **97** — MCK 55 (2013-07-25 … 2026-08-05), PKG 42 (2016-04-20 … 2026-07-22) |
| C2's floor | **193 eligible anchor events** |

Even if every candidate screened as eligible — and none has been screened —
**97 is about half the floor**, from the only two anchors the curated map
contains. Closing C2 is a HYP-01 collection problem across a wider universe,
not something two anchors can reach.

Nothing here is evidence about supply-chain transmission.
