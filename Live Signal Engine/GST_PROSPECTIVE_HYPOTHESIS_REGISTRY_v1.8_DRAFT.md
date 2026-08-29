# GST Prospective Hypothesis Registry — v1.8 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.8.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.8.json)
**Authored:** 2026-08-29 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.7.json` (sha256 `abe45f4d6ff2a78b…`)
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **The rule does not change, and neither does the evaluation basis.** AU-1…AU-6,
> the 10% threshold and the consolidated-revenue denominator are unchanged and
> remain ASC 280-10-50-42's; membership is still a point-in-time span. What
> changes is what the extractor can **read**. No hypothesis, eligibility class,
> measurement, capture path or decision changes, every eligible-event counter
> stays zero, and the display gate stays **CLOSED, C4 MET, four denials**.

---

## 1. The defect was structural

Every anchor required the percentage and its denominator to be **adjacent in
one match** — `<pct>% of <basis>`. Filings routinely state the denominator
**once**, in a scope clause, and then list parties carrying bare percentages:

| Filing | Text |
|---|---|
| INTC 2018-02-16 | "our three largest customers accounted for 40% of our net revenue, with **Dell Inc. … accounting for 16%**, Lenovo … **13%**, and HP Inc. … **11%**" |
| INTC 2024-01-26 | "the following percentage of our net revenue: … **Dell Inc. `19 %` `19 %` `21 %`**" |
| ADBE 2011-01-27 | "as a percentage of net revenue for fiscal 2010, 2009 and 2008 … `2010 2009 2008` **Ingram Micro `15 %` `15 %` `18 %`**" |
| JBL 2015-10-16 | "…as a percentage of consolidated net revenue … **Apple, Inc. `24 %` `18 %` `20 %` `19 %` `12 %`**" |

**The verb tense and the table layout are incidental.** No widening of the verb
set would have reached one of these — the denominator simply is not repeated
per party.

## 2. Membership: two entries and one extension

| | Ticker | Span | Qualifying disclosure |
|---|---|---|---|
| **IN** | **ADBE** | 2008-01-24 → 2015-01-20 | Ingram Micro, 21% of net revenue (7 filings) |
| **IN** | **JBL** | 2001-11-28 → 2025-10-17 | Dell Computer Corporation, 14% (24 filings) |
| **EXTENDED** | INTC | 2005-02-22 → **2025-01-31** *(was 2017-02-17)* | Dell Inc., 19% (20 filings, was 12) |

Eight members ever, eleven intervals: **AAPL, ADBE, CTSH, INTC, JBL, MCK, NKE,
NVDA**.

All three corrections are the **same** error — **data availability deciding
membership**, which AU-1…AU-6 forbid. INTC's interval closed at 2017-02-17
because Intel *moved the disclosure out of Item 1 prose*, not because Dell fell
below the threshold; ADBE and JBL appeared in no registry version at all.

## 3. This version removes nobody — read §3 before trusting §2

v1.7's companion states the principle plainly: **a version that only ever
*adds* members is indistinguishable from a loosened threshold.** v1.8 removes
nobody. That is the honest shape of this change and it is not hidden.

Three things a loosening could not do stand in place of a removal:

1. **The rule is byte-identical to v1.7** — threshold, denominator, AU-1…AU-6
   and the point-in-time basis, all checked field by field. Relaxing anything
   to admit ADBE or JBL would fail that test.
2. **The correction produces new *exits*.** INTC's membership ends 2025-01-31
   and JBL's 2025-10-17, because in those filings Intel and Jabil
   **anonymized** their customers to "Customer A / B / C". A concentration
   whose counterparty is not named cannot support a bilateral relationship, so
   the rule excludes it. *A loosened threshold carries members toward the
   present; it does not evict them.*
3. **INTC's interval is bounded at both ends, and its old end is explicable** —
   2017-02-17 is a change of prose style, identifiable in the filings.

## 4. The first draft was wrong, and the corpus said so

The scoped-list reader was measured against all 1,250 filings **before it was
believed**. It produced six fabrication routes, all now closed with verbatim
regression fixtures:

| Fabrication | Cause |
|---|---|
| a bare `Inc`, in **26 filings** | the comma in "Apple, Inc." — the defect that had reduced Foot Locker to "Inc" |
| `Hong Kong`, `South Korean`, `European`, `There` | rows read out of a **later sentence** than the scope clause |
| `Constellation Wines` | "reported **within the** … **segment**" |
| `…Company and Lucent` | two names sharing one percentage |
| `Rite Aid` at **49% of revenue** | read off a sentence about **receivables** |

**Spot-checking would not have found these.** The exhaustive enumeration did.

## 5. What the reader refuses

- **Column order is not a convention.** INTC, ADBE, CTSH and JBL list years
  newest-first; **GOOGL lists `2023 2024` — oldest first**, in this same
  corpus. The year header is *read*; an unreadable header, or one that never
  names the reporting year, yields nothing.
- **Two blocks sharing one year row** are read only while the revenue label
  precedes the receivables label — checked, not assumed.
- **A single bare column** must sit in the scope clause's own sentence.
- The **aggregate gate moved to the row**: "our three largest customers
  accounted for 40%" is the legitimate *scope* of a list that names its
  members; "Top ten clients 14.6 %" is a *row* naming nobody.

## 6. Known limitations, stated rather than fixed

- **A metric-labelled block table is refused outright.** Where the party heads
  a block and each row of figures is labelled by *metric* —
  `Reyes Beer Division entities / Net sales 27.5 % / Accounts receivable 22.0 %`
  — the nearest label to every figure is a metric, not a party. **Measured
  cost: STZ discloses Reyes Beer Division entities at 25–27% and Southern
  Glazer's Wine and Spirits at 11–13% of net sales, and STZ is therefore not a
  member.** Missing a real relationship is the safe direction.
- **`and` is not a name continuation**, so a counterparty whose name contains
  it is truncated. Both instances here are receivables-basis; no membership
  moves.
- **ASC 280 is a floor.** An absent member is not evidence of no concentration.
- Every limitation carried over from v1.7 still applies.

## 7. Verification

Re-derived offline from the response cache at **zero SEC requests**.

- 51/51 tickers, **1,250 filings, zero failures** — same corpus coverage as v1.7
- corpus diff against the v1.7 extractor: **86 edges added, zero removed**
- every added named party is a real company — Ingram Micro, Tech Data, Dell,
  HP, Lenovo, Apple, Cisco, Nokia, Royal Philips, Marconi, BlackBerry,
  Hewlett-Packard. **No geography, no segment, no aggregate, no bare suffix.**
- intervals **derived, never typed**: `build_v1_8` has no parameter for them,
  re-derives after building, and refuses on disagreement
- v1.4, v1.5, v1.6 and v1.7 remain byte-identical, all four pinned by hash

## 8. What this does not do

- **It creates no eligible anchor event.** `required_eligibility_class` is
  unchanged; eligibility is decided by `gst_market_response.completeness` from
  per-event capture records; no capture path runs over ADBE, JBL, or the
  extended part of INTC's interval. **C2 still counts zero of 193.**
- **The locked 24-ticker universe is untouched**, as are `gst_market_response/`,
  the cohort protocol and every earlier registry version. v1.7 remains on disk
  unchanged — including the INTC interval this version extends and the absence
  of ADBE and JBL it corrects. A superseded version is allowed to be wrong,
  which is what superseded means.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
