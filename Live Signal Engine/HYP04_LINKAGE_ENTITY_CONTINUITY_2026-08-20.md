# HYP-04 linkage entity continuity — decision record (2026-08-20)

**Decision:** where a counterparty is disclosed under successive *renamings* of the same corporate entity, the disclosures are treated as **one continuous relationship**, and the edge's `as_of_date` is the earliest filing in the chain.

**Decided by:** repo owner, 2026-08-20. **Status:** determination recorded. **No linkage row is curated by this document.**

---

## Why this needed a human

`run_linkage_history.py` reports counterparties by the exact string a filing used. It does **not** merge similar names, and its test suite pins that behaviour deliberately (`3f`). Fusing on a substring would also fuse genuinely different companies that share a word, and prose-matching is what produced the false edges in both EDGAR extractors — the failure `HYP04_LINKAGE_SOURCE_DECISION_2026-08-18.md` records.

But the opposite error is just as real, and it is the one that showed up here: **naive string matching fragments one true relationship into several**, and reports the newest fragment's date. That understates coverage rather than inventing it, so it fails quietly.

Deciding that two names denote one entity is a judgment about corporate identity. It belongs in a dated record a human signed, not in a regex.

## Determinations

### MCK → CVS — continuous, `as_of_date` **2013-05-07**

Disclosed in **every** McKesson 10-K from 2013 to 2026, under three successive names:

| Filings | Name as disclosed |
|---|---|
| 2013-05-07 → 2015-05-12 | `CVS Caremark Corporation` (and bare `CVS`) |
| 2016-05-05 → 2019-05-15 | `CVS Health` |
| 2020-05-22 → 2026-05-08 | `CVS Health Corporation` |

Unbroken, 14 consecutive annual filings, no gap year.

**Operative as_of_date: `2013-05-07`**, accession `0001561787-13-000010`.

The candidate extractor had recorded `2026-05-08`, because it reads only the newest 10-K. Under the peer-eligibility rule an edge counts only for anchor events strictly after its as_of date, so this determination moves the edge from covering *almost no* anchor events to covering **thirteen years** of them.

### PKG → ODP — continuous, `as_of_date` **2016-02-26**

| Filings | Name as disclosed |
|---|---|
| 2016-02-26 → 2022-02-24 | `Office Depot` |
| 2023-02-23 → 2026-02-26 | `ODP` |

Unbroken, 11 consecutive annual filings. Office Depot, Inc. became The ODP Corporation; same counterparty.

**Operative as_of_date: `2016-02-26`**, accession `0000075677-16-000030`.

Filings back to 2000 were examined and **none before 2016 names it**, so 2016 is the floor for this edge on this source.

## NOT decided — two things this record deliberately does not cover

### `Caremark RX` (2006-05-16, 2007-05-09) — a merger, not a rename

McKesson's 2006 and 2007 10-Ks name **Caremark RX** as a major customer. Caremark Rx, Inc. was a **separate public company** that combined with CVS Corporation in 2007 to form CVS Caremark.

That is not the "slight name change" this record covers. Whether the pre-merger Caremark relationship is *the same relationship* as the post-merger CVS one is a different and harder question: in 2006 the customer was a standalone pharmacy-benefit manager that was not yet part of CVS.

Accepting it would move the as_of date to **2006-05-16**, seven years earlier again. **It is left open.** Nothing here authorises it.

### `Rite Aid Corporation` (2001-06-01 → 2005-05-13) — a different customer

Named in five consecutive McKesson 10-Ks. This is **not** early CVS; it is a separate candidate edge, `MCK → RAD`, and would need its own row.

Practical caveat for whoever curates it: Rite Aid has since been through bankruptcy, so peer return history — eligibility condition **P5** — may not be available across the window.

## Known limit on the MCK floor

The history walk examined **26 of 29** McKesson 10-Ks. It stopped on a `404` for a 2000-era document (`.../000092962400000832/0001.txt`, the old EDGAR document-naming convention). The three unexamined filings are the **oldest** ones.

So **2013-05-07 is the earliest disclosure *found*, not proven to be the floor.** Filings from 2008–2012 name no counterparty at all, which makes an earlier CVS disclosure unlikely — but it has not been checked, and this record should not be read as if it had.

## What an as_of_date claims

The earliest filing that **discloses** the relationship. It is not evidence the relationship *began* then — only that it was publicly known by then, which is the claim the field makes and the only one a filing supports. An earlier start date requires a different source.

## Status

No row is curated. The two determinations above fix the `as_of_date` and `source_citation` for two future rows; every other required field — `confidence`, `relationship_type`, `date_confidence`, `review_status` — still needs a curator. Both edges are `direct_customer` from the anchor's perspective, but that too is the curator's call to record.

---

*Nothing in this document constitutes investment advice, a solicitation, or a representation that any approach is profitable. No hedging edge has been demonstrated, and Phase 0 established nothing about supply-chain transmission.*
