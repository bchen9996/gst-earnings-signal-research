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

**Result, from the walk alone: 78 AMC, 17 BMO, 2 UNKNOWN.** Both UNKNOWNs are resolved by the addenda in §5, so the merged set has none.

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

### Both resolved by hand, 2026-08-24

Reading the press-release exhibits settles both. In each case the release is
the **acceptance date**, and both are **AMC**:

**MCK → 2023-11-01, AMC.** Exhibit `mck_exhibit991x9302023.htm` (quarter ending
2023-09-30) is headed *"McKESSON CORPORATION REPORTS FISCAL 2024 SECOND QUARTER
RESULTS"* and says *"a conference call for today, Wednesday, November 1st at
4:30 PM ET"*. Accepted 16:05 ET; the call follows at 16:30. `reportDate`
2023-10-27 belongs to the Item 5.02 officer departure.

**PKG → 2020-07-28, AMC.** Exhibit `pkg-ex991_6.htm` opens *"Lake Forest, IL,
July 28, 2020 — Packaging Corporation of America today reported second quarter
2020 net income"*, with the call *"Wednesday, July 29, 2020 at 9:00 a.m."* —
the next morning, PKG's usual AMC pattern. Accepted 17:29 ET. `reportDate`
2020-07-24 belongs to the Item 2.06 impairment.

Note what this cost: the answer required **reading the press release**. The
acceptance timestamp alone could not distinguish "released that evening" from
"filed days late", which is exactly why the classifier refuses the different-day
case rather than inferring through it.

Both now live in `HYP04_ANCHOR_EVENT_ADDENDA.csv` with these citations, each **superseding** the mis-dated derived row rather than sitting alongside it. See §8.

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

MCK 2020-02-04 (BMO) is verified and now lives in `HYP04_ANCHOR_EVENT_ADDENDA.csv`, where it **adds** an event rather than superseding one. It is not pasted into the generated CSV, because a hand-inserted row there would be indistinguishable from a derived one and would not survive regeneration. With it merged, MCK's cadence has **no remaining gaps**.

## 6. What this does and does not get you

| | |
|---|---|
| Candidate releases | **98** merged — MCK 56, PKG 42, 2013-07-25 … 2026-08-05 |
| C2's floor | **193 eligible anchor events** |

Even if every candidate screened as eligible — and none has been screened —
**98 is about half the floor**, from the only two anchors the curated map
contains. Closing C2 is a HYP-01 collection problem across a wider universe,
not something two anchors can reach.

## 7. What collecting these actually costs

Run end-to-end through response-session resolution and `closes_requirements`
on 2026-08-24:

| | |
|---|---|
| Candidates (merged, incl. addenda) | 98 |
| Session-resolved | **98** — the addenda resolve both former UNKNOWNs |
| Pinned onto the session index | **98, zero rejected** |
| **Rows to collect** | **3,915** — CVS 2,193 · ODP 1,722 |
| Truncated | 1 — `MCK-2026-08-05`, horizon runs past today |
| P3-skipped | 0 (the `--since` filter already excluded them) |

**Overlap dedupe saves 62 rows — 1%.** Quarterly releases sit roughly 63
sessions apart and the window is 41, so windows rarely touch. The job does not
get materially smaller by batching it.

**This total is as-of dated and will drift upward.** `--as-of` defaults to
today, and `MCK-2026-08-05` is truncated only because its horizon has not
finished trading; once it has, it contributes ~41 more rows. Re-run the command
rather than quoting 3,915 — the number is a measurement, not a constant.

Reproduce with:

```
PYTHONPATH=. .venv/Scripts/python.exe -m hyp04_supply_chain_hedge.closes_requirements \
    --events-csv "Live Signal Engine/HYP04_ANCHOR_EVENT_CANDIDATES_2026-08-23.csv"
```

## 8. Three verified events the generated CSV does not contain

All three are confirmed against their filings. None is in
`HYP04_ANCHOR_EVENT_CANDIDATES_2026-08-23.csv`, and none should be pasted in.

| Event | Session | Why the walk misses it | Evidence |
|---|---|---|---|
| MCK **2020-02-04** | BMO | filed with items `9.01` only — no Item 2.02 tag | `0000927653-20-000013`, doc `mck8-k12312019.htm`, accepted 07:10 ET |
| MCK **2023-11-01** | AMC | `reportDate` 2023-10-27 belongs to the Item 5.02 officer departure | `0000927653-23-000081`, press release dated Nov 1, call 16:30 ET |
| PKG **2020-07-28** | AMC | `reportDate` 2020-07-24 belongs to the Item 2.06 impairment | `0001564590-20-033955`, press release dated Jul 28, call 09:00 ET next day |

**Why they are not appended.** The CSV is generated. A hand-inserted row is
indistinguishable from a derived one, survives no regeneration, and silently
reappears as a discrepancy the next time anyone re-runs the walk. That is the
same class of defect as a fact corrected in one place while copies survive
elsewhere — the failure this project has spent most of its guards on.

**Decided 2026-08-24: the addendum file.** They live in
`HYP04_ANCHOR_EVENT_ADDENDA.csv`, with linkage-map provenance
(`source_accession`, `source_citation`, `curated_by`, `curated_date`,
`review_status`), merged at read time and marked
`provenance: curated_addendum` so a curated row is never mistaken for a derived
one. The alternative — widening the walk past the Item 2.02 tag — was rejected:
the only signal separating a 9.01-only earnings release from any other exhibit
filing is the filer's document-naming convention, and a false positive there is
a fabricated anchor event.

### Supersession, and why it is not optional

A curated row and the derived row it corrects do **not** collide on `event_id` —
the id embeds the date, and the date is exactly what is being corrected.
`MCK-2023-11-01` and `MCK-2023-10-27` are one earnings release. Merging both
would count it twice, and a double-count is invisible in a total.

So a curated row names the derived row it replaces, and `merge_addenda` raises
rather than warns when:

- the superseded event **is not in the derived set** — the addendum is stale,
  so the correction may no longer apply
- a curated id **collides** with a derived id — ambiguous; a row either adds an
  event or supersedes one, never shadows

### Effect

| | |
|---|---|
| Derived | 97 |
| Superseded | −2 |
| Curated | +3 |
| **Total** | **98** |
| UNKNOWN release sessions | **0** (was 2) |
| Cadence gaps | **none** (was 1 × 203 days) |
| Rows to collect | 3,792 → **3,915** |

Nothing here is evidence about supply-chain transmission.
