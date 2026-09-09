# HYP-04 curated-edge verification (2026-09-08)

**Status:** evidence for a ratification decision. It contains no `review_status` and recommends nothing.

Assembled offline from the completed EDGAR 10-K walks in `HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-09-02.json`. No network call was made.

## Why every edge matters equally here

The derived sample is 214 eligible anchor events against a floor of 193 — a margin of 21. The smallest contributing anchor supplies 30 events, so **dropping any single anchor's edges fails the floor.** That is precisely the circumstance in which a recommendation to keep an edge would be worth nothing, which is why there is none below.

## The edges, by events contributed

| edge | events | as_of | walk earliest | walk latest | filings | events after last disclosure |
|---|---|---|---|---|---|---|
| `JBL->CSCO` | 89 | 2002-11-25 | 2002-11-25 | 2012-10-25 | 9 | **51** (57.3%) † |
| `MCK->CVS` | 53 | 2013-05-07 | 2013-05-07 | 2015-05-12 | 3 | **44** (83.0%) † |
| `JBL->AAPL` | 51 | 2012-10-25 | 2012-10-25 | 2024-10-28 | 13 | **4** (7.8%) |
| `JBL->BB` | 47 | 2013-10-28 | 2013-10-28 | 2013-10-28 | 1 | **47** (100.0%) ‡ † |
| `NVDA->MSFT` | 42 | 2004-03-29 | 2004-03-29 | 2005-03-22 | 2 | **38** (90.5%) † |
| `INTC->HPQ` | 30 | 2017-02-17 | 2017-02-17 | 2024-01-26 | 8 | **3** (10.0%) |

`as_of` agrees with the walk's earliest disclosing filing for `JBL->CSCO`, `MCK->CVS`, `JBL->AAPL`, `JBL->BB`, `NVDA->MSFT`, `INTC->HPQ`, `PKG->ODP`.

**‡ — the count is arithmetic, not evidence.** This edge is disclosed in exactly one filing, so `as_of` *is* the last disclosure and P3 admits only events strictly after it. 100% is forced. What the single filing does tell you is that the relationship was never disclosed again, which is a separate thing worth weighing.

**† — this anchor kept naming counterparties after this one's last filing.** Exact-string matching finds only the name in the citation, so an anchor that carried on disclosing under a *different* name reads here as if it stopped. The names are listed per edge below. Whether any of them is the same company is the judgement that rejected Caremark RX and OfficeMax, and it is not made for you:

- `JBL->CSCO` — later on this anchor: **Apple, Inc** (2012-10-25 → 2024-10-28, 13 filing(s)), **BlackBerry Limited** (2013-10-28 → 2013-10-28, 1 filing(s))
- `MCK->CVS` — later on this anchor: **CVS Health Corporation** (2020-05-22 → 2026-05-08, 7 filing(s)), **CVS Health** (2016-05-05 → 2019-05-15, 4 filing(s))
- `JBL->BB` — later on this anchor: **Apple, Inc** (2012-10-25 → 2024-10-28, 13 filing(s))
- `NVDA->MSFT` — later on this anchor: **Dell** (2020-02-20 → 2020-02-20, 1 filing(s)), **ASUSTeK Computer Inc** (2016-03-17 → 2017-03-01, 2 filing(s)), **Quanta Computer Incorporated** (2011-03-16 → 2011-03-16, 1 filing(s)), **Quanta** (2010-03-18 → 2010-03-18, 1 filing(s)), **Hewlett-Packard Company** (2009-03-13 → 2009-03-13, 1 filing(s)), **Asustek Computer** (2008-03-21 → 2008-03-21, 1 filing(s)), **Asustek** (2006-03-16 → 2007-03-16, 2 filing(s))

## What the last column means, and does not

P3 admits a pair when `as_of_date <= event_date`. **Nothing checks the relationship was still disclosed when the event happened.** The rightmost column counts eligible events falling after the last filing that named the counterparty at all.

A high number is not proof the relationship ended — ASC 280 requires disclosure only above a threshold, so a customer can fall from 12% to 9% of revenue and vanish from the filings while the commercial relationship continues. It is *absence of evidence*, and the agreements artifact already uses that exact phrase for the same problem. But it is the axis on which these edges differ most, and it is not visible anywhere in the map.

**Adopting a currency rule is a `SCIENTIFIC_DECISION` and is not proposed here.** It would be made after seeing which edges it cuts, which is what the analysis locks exist to prevent.

## `JBL->CSCO`

- **Counterparty named in the citation:** `Cisco Systems, Inc`
- **Matched in the walk:** True (exact_string_equality)
- **Disclosed in 9 filing(s)**, 2002-11-25 → 2012-10-25
- Earliest accession `0000950144-02-012283`, latest `0001193125-12-435503`
- **`as_of` agrees with the earliest disclosing filing:** True
- Map records `date_confidence: high`, `review_status: draft`

Every counterparty **JBL** ever named in its 10-Ks:

| counterparty | earliest | latest | filings |
|---|---|---|---|
| Apple, Inc | 2012-10-25 | 2024-10-28 | 13 |
| BlackBerry Limited | 2013-10-28 | 2013-10-28 | 1 |
| Cisco Systems, Inc | 2002-11-25 | 2012-10-25 | 9 |
| Nokia Corporation | 2005-10-28 | 2007-10-25 | 3 |
| Royal Philips Electronics | 2003-11-12 | 2007-05-15 | 4 |
| Hewlett-Packard Company | 2003-11-12 | 2005-10-28 | 2 |
| Marconi Communications | 2002-11-25 | 2002-11-25 | 1 |
| Dell Computer Corporation | 2001-11-28 | 2001-11-28 | 1 |

<details><summary>The map's own notes on this edge, verbatim</summary>

> DRAFT, UNVALIDATED, MACHINE-PREPARED. Derived from the EDGAR review queue; no human has reviewed this edge. as_of_date is the EARLIEST filing in the walk that names this counterparty -- found, not proven to be the floor. LINEAGE: SEC's record shows the registrant filing on 2002-11-25 as 'CISCO SYSTEMS INC' (CIK 0000858877, filing since 1995-02-13), which matches the disclosed name -- this removes ONE way of being wrong and does not establish the relationship. A merger that preserved the name and the registrant would look identical here; check it the way Caremark RX and OfficeMax were checked. STAKE: 89 anchor events beyond what the curated map already reaches.

</details>

## `MCK->CVS`

- **Counterparty named in the citation:** `CVS Caremark Corporation`
- **Matched in the walk:** True (exact_string_equality)
- **Disclosed in 3 filing(s)**, 2013-05-07 → 2015-05-12
- Earliest accession `0001561787-13-000010`, latest `0001628280-15-004098`
- **`as_of` agrees with the earliest disclosing filing:** True
- Map records `date_confidence: high`, `review_status: draft`

Every counterparty **MCK** ever named in its 10-Ks:

| counterparty | earliest | latest | filings |
|---|---|---|---|
| CVS Health Corporation | 2020-05-22 | 2026-05-08 | 7 |
| CVS Health | 2016-05-05 | 2019-05-15 | 4 |
| CVS Caremark Corporation | 2013-05-07 | 2015-05-12 | 3 |
| CVS | 2013-05-07 | 2014-05-14 | 2 |
| Caremark RX, Inc | 2006-05-16 | 2007-05-09 | 2 |
| Rite Aid Corporation | 2000-06-13 | 2005-05-13 | 6 |

<details><summary>The map's own notes on this edge, verbatim</summary>

> DRAFT, UNVALIDATED. EARLIEST-DISCLOSURE GAP NOW CLOSED (2026-08-22): all 29 MCK 10-Ks have been examined. The history walk had stopped at 26 on a 404; the 3 oldest (1996-06-19, 1997-06-19, 2000-06-13) were retrieved via the full-submission .txt path and none supports an earlier as_of. FY1996 names Wal-Mart Stores as largest customer (11% of revenues); FY1997 states credit risk is spread over many dispersed customers; FY2000 names Rite Aid Corporation as largest customer (15% of revenues). CVS appears once in the FY2000 filing but only inside an EXHIBIT -- a receivables-sales facility defining 'Special Obligor' as Rite Aid, Osco Drug, CVS Corp. and Wal-Mart -- which is a credit-facility definition, names no percentage, and is NOT a customer-concentration disclosure. It does not support a high-confidence as_of and was rejected as a source. Caremark RX (2006-2007) REJECTED by repo owner 2026-08-22: a merger, not a rename, so the pre-2007 counterparty is a different company. 2013-05-07 stands.

</details>

## `JBL->AAPL`

- **Counterparty named in the citation:** `Apple, Inc`
- **Matched in the walk:** True (exact_string_equality)
- **Disclosed in 13 filing(s)**, 2012-10-25 → 2024-10-28
- Earliest accession `0001193125-12-435503`, latest `0001628280-24-043960`
- **`as_of` agrees with the earliest disclosing filing:** True
- Map records `date_confidence: high`, `review_status: draft`

Every counterparty **JBL** ever named in its 10-Ks:

| counterparty | earliest | latest | filings |
|---|---|---|---|
| Apple, Inc | 2012-10-25 | 2024-10-28 | 13 |
| BlackBerry Limited | 2013-10-28 | 2013-10-28 | 1 |
| Cisco Systems, Inc | 2002-11-25 | 2012-10-25 | 9 |
| Nokia Corporation | 2005-10-28 | 2007-10-25 | 3 |
| Royal Philips Electronics | 2003-11-12 | 2007-05-15 | 4 |
| Hewlett-Packard Company | 2003-11-12 | 2005-10-28 | 2 |
| Marconi Communications | 2002-11-25 | 2002-11-25 | 1 |
| Dell Computer Corporation | 2001-11-28 | 2001-11-28 | 1 |

<details><summary>The map's own notes on this edge, verbatim</summary>

> DRAFT, UNVALIDATED, MACHINE-PREPARED. Derived from the EDGAR review queue; no human has reviewed this edge. as_of_date is the EARLIEST filing in the walk that names this counterparty -- found, not proven to be the floor. LINEAGE: SEC's record shows the registrant filing on 2012-10-25 as 'APPLE INC' (CIK 0000320193, filing since 1994-01-26), which matches the disclosed name -- this removes ONE way of being wrong and does not establish the relationship. A merger that preserved the name and the registrant would look identical here; check it the way Caremark RX and OfficeMax were checked. STAKE: 51 anchor events beyond what the curated map already reaches.

</details>

## `JBL->BB`

- **Counterparty named in the citation:** `BlackBerry Limited`
- **Matched in the walk:** True (exact_string_equality)
- **Disclosed in 1 filing(s)**, 2013-10-28 → 2013-10-28
- Earliest accession `0001193125-13-413660`, latest `0001193125-13-413660`
- **`as_of` agrees with the earliest disclosing filing:** True
- Map records `date_confidence: medium`, `review_status: draft`

Every counterparty **JBL** ever named in its 10-Ks:

| counterparty | earliest | latest | filings |
|---|---|---|---|
| Apple, Inc | 2012-10-25 | 2024-10-28 | 13 |
| BlackBerry Limited | 2013-10-28 | 2013-10-28 | 1 |
| Cisco Systems, Inc | 2002-11-25 | 2012-10-25 | 9 |
| Nokia Corporation | 2005-10-28 | 2007-10-25 | 3 |
| Royal Philips Electronics | 2003-11-12 | 2007-05-15 | 4 |
| Hewlett-Packard Company | 2003-11-12 | 2005-10-28 | 2 |
| Marconi Communications | 2002-11-25 | 2002-11-25 | 1 |
| Dell Computer Corporation | 2001-11-28 | 2001-11-28 | 1 |

<details><summary>The map's own notes on this edge, verbatim</summary>

> DRAFT, UNVALIDATED, MACHINE-PREPARED. Derived from the EDGAR review queue; no human has reviewed this edge. as_of_date is the EARLIEST filing in the walk that names this counterparty -- found, not proven to be the floor. LINEAGE: SEC's record shows the registrant filing on 2013-10-28 as 'BLACKBERRY Ltd' (CIK 0001070235, filing since 1999-07-12), which matches the disclosed name -- this removes ONE way of being wrong and does not establish the relationship. A merger that preserved the name and the registrant would look identical here; check it the way Caremark RX and OfficeMax were checked. STAKE: 47 anchor events beyond what the curated map already reaches.

</details>

## `NVDA->MSFT`

- **Counterparty named in the citation:** `Microsoft`
- **Matched in the walk:** True (exact_string_equality)
- **Disclosed in 2 filing(s)**, 2004-03-29 → 2005-03-22
- Earliest accession `0001045810-04-000007`, latest `0001045810-05-000008`
- **`as_of` agrees with the earliest disclosing filing:** True
- Map records `date_confidence: high`, `review_status: draft`

Every counterparty **NVDA** ever named in its 10-Ks:

| counterparty | earliest | latest | filings |
|---|---|---|---|
| Dell | 2020-02-20 | 2020-02-20 | 1 |
| ASUSTeK Computer Inc | 2016-03-17 | 2017-03-01 | 2 |
| Quanta Computer Incorporated | 2011-03-16 | 2011-03-16 | 1 |
| Quanta | 2010-03-18 | 2010-03-18 | 1 |
| Hewlett-Packard Company | 2009-03-13 | 2009-03-13 | 1 |
| Asustek Computer | 2008-03-21 | 2008-03-21 | 1 |
| Asustek | 2006-03-16 | 2007-03-16 | 2 |
| Microsoft | 2004-03-29 | 2005-03-22 | 2 |
| Micro-Star | 2003-04-25 | 2004-03-29 | 2 |
| Atlantic | 2002-05-14 | 2002-05-14 | 1 |
| Atlantic Semiconductor | 2002-05-14 | 2002-05-14 | 1 |
| Celestica | 2001-04-27 | 2001-04-27 | 1 |

<details><summary>The map's own notes on this edge, verbatim</summary>

> DRAFT, UNVALIDATED, MACHINE-PREPARED. Derived from the EDGAR review queue; no human has reviewed this edge. as_of_date is the EARLIEST filing in the walk that names this counterparty -- found, not proven to be the floor. LINEAGE: SEC's record shows the registrant filing on 2004-03-29 as 'MICROSOFT CORP' (CIK 0000789019, filing since 1994-02-14), which matches the disclosed name -- this removes ONE way of being wrong and does not establish the relationship. A merger that preserved the name and the registrant would look identical here; check it the way Caremark RX and OfficeMax were checked. STAKE: 42 anchor events beyond what the curated map already reaches.

</details>

## `INTC->HPQ`

- **Counterparty named in the citation:** `HP Inc`
- **Matched in the walk:** True (exact_string_equality)
- **Disclosed in 8 filing(s)**, 2017-02-17 → 2024-01-26
- Earliest accession `0000050863-17-000012`, latest `0000050863-24-000010`
- **`as_of` agrees with the earliest disclosing filing:** True
- Map records `date_confidence: low`, `review_status: needs revisit`

Every counterparty **INTC** ever named in its 10-Ks:

| counterparty | earliest | latest | filings |
|---|---|---|---|
| Dell Inc | 2005-02-22 | 2024-01-26 | 20 |
| HP Inc | 2017-02-17 | 2024-01-26 | 8 |
| Lenovo Group Limited | 2013-02-19 | 2024-01-26 | 12 |
| Hewlett-Packard Company | 2013-02-19 | 2015-02-13 | 3 |
| ICG | 2005-02-22 | 2005-02-22 | 1 |

<details><summary>The map's own notes on this edge, verbatim</summary>

> DRAFT, UNVALIDATED, MACHINE-PREPARED. Derived from the EDGAR review queue; no human has reviewed this edge. as_of_date is the EARLIEST filing in the walk that names this counterparty -- found, not proven to be the floor. LINEAGE: SEC's record shows the registrant filing on 2017-02-17 as 'HP INC' (CIK 0000047217, filing since 1994-01-21), which matches the disclosed name -- this removes ONE way of being wrong and does not establish the relationship. A merger that preserved the name and the registrant would look identical here; check it the way Caremark RX and OfficeMax were checked. STAKE: 30 anchor events beyond what the curated map already reaches.

</details>

## `PKG->ODP`  (contributes no eligible events)

- **Counterparty named in the citation:** `Office Depot`
- **Matched in the walk:** True (exact_string_equality)
- **Disclosed in 6 filing(s)**, 2016-02-26 → 2022-02-24
- Earliest accession `0000075677-16-000030`, latest `0000950170-22-001913`
- **`as_of` agrees with the earliest disclosing filing:** True
- Map records `date_confidence: high`, `review_status: draft`

Every counterparty **PKG** ever named in its 10-Ks:

| counterparty | earliest | latest | filings |
|---|---|---|---|
| ODP | 2023-02-23 | 2026-02-26 | 4 |
| Office Depot | 2016-02-26 | 2022-02-24 | 6 |

<details><summary>The map's own notes on this edge, verbatim</summary>

> DRAFT, UNVALIDATED. SOURCE_TYPE CONFIRMED 2026-08-22 by retrieving accession 0000075677-16-000030 (pkg1231201510k.htm). The disclosure sits under the 'Customers' subsection of Item 1 Business -- NOT the Competition section, which begins immediately AFTER it; the earlier concern was a proximity artifact. It reads: 'Office Depot, Inc. is our largest customer in the Paper segment ... In 2015, our sales revenue to Office Depot represented 45% of our Paper segment sales revenue.' That is substantively a customer-concentration statement, so the closed-vocabulary value stands, though it is coarse: the text is in Item 1, not in the notes to the financial statements. LINEAGE NOT EXTENDED: the same filing says 'Office Depot became our largest customer when it acquired OfficeMax Incorporated late in 2013', and PKG's own earlier 10-Ks name OfficeMax rather than Office Depot. That is a merger, not a rename -- the same basis on which Caremark RX was rejected for MCK -- so 2016-02-26 stands. All 27 PKG 10-Ks were examined; none before 2016 names Office Depot.

</details>

---

*Nothing in this document is evidence about supply-chain transmission. No target value, `beta_h`, horizon or direction has been computed, and none may be displayed while the gate is closed.*

*Nothing here constitutes investment advice, a solicitation, or a representation that any approach is profitable.*
