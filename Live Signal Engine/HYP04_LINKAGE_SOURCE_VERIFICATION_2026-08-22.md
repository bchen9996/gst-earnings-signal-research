# HYP-04 linkage source verification — record (2026-08-22)

**Decisions taken (repo owner, 2026-08-22):**

1. **Caremark RX lineage REJECTED** for `MCK → CVS`. `as_of_date` stays **2013-05-07**.
2. **PKG `source_type` CONFIRMED** as `10-K Customer Concentration Note`; the *Competition section* concern is resolved as a false alarm.

**Status:** two open caveats on the curated map are closed, and the MCK earliest-disclosure gap is closed. **No `as_of_date` moved. No edge was added or removed. The gate is unchanged: CLOSED, C4 MET, exactly 4 denials.**

---

## 1. MCK — the three unexamined filings

`HYP04_EDGAR_LINKAGE_HISTORY.json` recorded `filings_examined: 26` of `filings_on_record: 29`, having stopped on:

```
HTTPError: 404 ... /Archives/edgar/data/927653/000092962400000832/0001.txt
```

The three unexamined filings were the **oldest**, which is the direction that could have moved `as_of_date` earlier — so the gap mattered.

**Cause of the 404:** pre-2001 EDGAR accessions do not expose the modern `primaryDocument` layout the walk assumes. The **full-submission `.txt`** path exists for every accession regardless of era:

```
https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{acc_with_dashes}.txt
```

All three retrieved cleanly on that path.

| Filed | Accession | Largest-customer disclosure |
|---|---|---|
| 1996-06-19 | `0000898430-96-002749` | **Wal-Mart Stores, Inc.** — 11% of consolidated revenues FY1996, 10% FY1995 |
| 1997-06-19 | `0000929624-97-000781` | none named; Note 5 states credit risk is "spread over a large number of geographically dispersed customers" |
| 2000-06-13 | `0000929624-00-000832` | **Rite Aid Corporation** — 15% of FY2000 revenues; ten largest = 52% |

**MCK's earliest-disclosure floor is therefore established, not merely "found".** All 29 filings have been examined.

### The CVS mention in the FY2000 filing, and why it was rejected

`CVS` does appear once in the 2000 filing. It is **not** a customer disclosure. It sits inside an **exhibit** — a receivables-sales facility agreement — in the definition of *Special Obligor*:

> "**Special Obligor**" means Rite Aid, Osco Drug (American Stores), CVS Corp., Wal-Mart, and such other Special Obligors as may be designated by the Managing Agents from time to time.

That is a **credit-facility concentration-limit definition**. It names no percentage, makes no statement about the size or nature of any customer relationship, and appears in an exhibit rather than in Item 1 or the concentration note.

Rejected as a source for three reasons, in order of weight:

1. It does not support the row's `source_type` (`10-K Customer Concentration Note`) or its `date_confidence: high`. Using it would have made the row's `source_citation` and `as_of_date` describe different documents of very different evidentiary weight.
2. The **same filing's actual customer disclosure names Rite Aid**, not CVS. So the positive evidence is that CVS was *not* a concentration counterparty for McKesson in 2000.
3. `as_of_date` is load-bearing for peer eligibility: condition **P3** counts an edge only for anchor events strictly after it. Moving a date earlier on weak evidence admits observations the evidence does not support — the one direction that manufactures sample rather than losing it.

**This is not merely the conservative choice; it is the choice the evidence supports.** Keeping 2013-05-07 is what the filings say.

### Caremark RX — rejected

`HYP04_EDGAR_LINKAGE_HISTORY.json` records `Caremark RX` disclosed 2006-05-16 and 2007-05-09. Accepting that lineage would move `as_of_date` back to **2006-05-16**, gaining roughly seven years of eligible anchor events.

**Rejected.** CVS acquired Caremark RX in 2007: that is a **merger, not a rename**. The pre-2007 counterparty was a different company, and an edge asserting `MCK → CVS` in 2006 would assert a relationship with an entity that was not then CVS.

This is the opposite disposition from the one recorded in `HYP04_LINKAGE_ENTITY_CONTINUITY_2026-08-20.md` for `CVS Caremark Corporation → CVS Health → CVS Health Corporation`, and deliberately so: **those are renamings of one continuous registrant; this is an acquisition of a separate one.** The distinction is the whole content of the rule.

## 2. PKG — `source_type` confirmed, and a lineage question found

The row's caveat flagged that the ODP disclosure "sits next to the Competition heading", so `10-K Competition section` might be the accurate value.

**Resolved: it is not.** Accession `0000075677-16-000030`, document `pkg1231201510k.htm`, was retrieved and the text inspected. The disclosure sits under the **`Customers` subsection of Item 1 Business**. The `Competition` heading begins *immediately after* it — the earlier concern was a **proximity artifact** of reading nearby text.

> **Customers** — We have over 200 customers in approximately 500 locations. … **Office Depot, Inc. is our largest customer in the Paper segment.** We have an agreement with Office Depot in which we will supply at least 50% of Office Depot's requirements for commodity office papers through December 2017 … In 2015, our sales revenue to Office Depot represented **45% of our Paper segment sales revenue**. **Competition** The markets in which our Paper segment competes …

Naming the largest customer with a revenue share is substantively a customer-concentration statement, so `10-K Customer Concentration Note` **stands**.

One caveat is recorded rather than absorbed: the closed vocabulary is **coarse**. This text is in Item 1 Business, not in the notes to the consolidated financial statements, and "Note" implies the latter. The value is the best available and is not misleading; the vocabulary could later distinguish the two locations.

### OfficeMax — the same merger question, same answer

The same filing states:

> "Office Depot became our largest customer **when it acquired OfficeMax Incorporated late in 2013**. We previously had a long standing contractual relationship with OfficeMax Incorporated."

So PKG had a supply relationship with **OfficeMax** before 2016, and the 10-K history walk — which examined **all 27** PKG filings — finds no filing before 2016-02-26 naming Office Depot.

**Lineage not extended, for the same reason Caremark RX was rejected**: an acquisition makes the earlier counterparty a different company. `as_of_date` stays **2016-02-26**.

That the two anchors produced the identical question independently, and take the identical answer, is the rule behaving consistently rather than being applied case by case.

## What was NOT done

- **No `as_of_date` moved**, in either direction, on either row.
- **`HYP04_EDGAR_LINKAGE_HISTORY.json` was not regenerated.** It is the output of a 59-request walk and remains an accurate record of *that run*, including its early stop. This document supersedes its `stopped_early_reason` for MCK; re-running it to close a field would cost ~60 SEC requests to change one string.
- **`review_status` stays `draft`** on both rows. Closing the caveats a draft names does not promote it — that is the owner's act.
- **No registry field was touched.**

## Verification cost

11 SEC requests total, read-only, via the repo's rate-limited `EdgarClient` with the owner-supplied contact. No credential, no write, no third-party service.
