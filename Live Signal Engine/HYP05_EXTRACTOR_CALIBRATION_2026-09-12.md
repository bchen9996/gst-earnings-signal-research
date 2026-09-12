# HYP-05 competitor/supplier extractor calibration (2026-09-12)

**Status: raw findings only. No pass/fail judgment is asserted by this script.** A human reads the context snippets below and writes the assessment.

Tickers: INTC, JBL, NVDA, AAPL, MSFT -- fixed before running, not chosen after seeing results (see module docstring). Real SEC requests made: 0.

This script makes real network calls and is deliberately NOT part of the offline test suite. Nothing found here is added to any linkage map by this script.

## INTC
- Filing: 10-K filed 2026-01-23, accession 0000050863-26-000011 (571,466 chars of extracted text)
- Edges found: 3

1. **AMD** (competitor, pattern `principal_competitors`)
   > "ced AI capabilities and high performance. Competition CCG's primary competitor is AMD, which like us designs processors based on the x86 architecture. Client CPUs utilizing the x86 architecture remain "

2. **Asi** (competitor, pattern `competitors_include`)
   > 'ext-generation compute solutions. Competition Intel Foundry competitors include semiconductor foundries that deliver wafers and packaging technologies from fabrication plants located primarily in Asi'

3. **GlobalFoundries** (competitor, pattern `competitors_include`)
   > 'e directly with Samsung in this market. Other Intel Foundry competitors include GlobalFoundries, UMC and SMIC, which primarily focus on mature process technologies. Our Business 7 Table of Contents A'

## JBL
- Filing: 10-K filed 2025-10-17, accession 0001628280-25-045293 (410,905 chars of extracted text)
- Edges found: 1

1. **Israel** (supplier, pattern `we_purchase_from`)
   > 'and price fluctuations of these raw materials. In addition, we source some parts from certain suppliers located in Israel. Although the impact of the Russia/Ukraine conflict and conflicts in the Middle Eas'

## NVDA
- Filing: 10-K filed 2026-02-25, accession 0001045810-26-000021 (360,424 chars of extracted text)
- Edges found: 3

1. **GPUs** (competitor, pattern `competitors_include`)
   > 'easingly competitive environment in the future. Our current competitors include: • suppliers and licensors of hardware and software for discrete and integrated GPUs, custom chips and other accelerate'

2. **Asia** (supplier, pattern `our_supplier_is`)
   > 'l business operations, finished goods inventory and some of our suppliers are located in Asia, making our operations vulnerable to natural disasters such as earthquakes, wildfires or other business'

3. **SK Hynix Inc** (supplier, pattern `we_purchase_from`)
   > 'Co., Ltd., or Samsung, to produce our semiconductor wafers. We purchase memory from SK Hynix Inc., Micron Technology, Inc., and Samsung. We utilize CoWoS technology for semiconductor packaging. We engage'

## AAPL
- Filing: 10-K filed 2025-10-31, accession 0000320193-25-000079 (220,568 chars of extracted text)
- Edges found: 0

(no edges found)

## MSFT
- Filing: 10-K filed 2026-07-29, accession 0001193125-26-323660 (357,670 chars of extracted text)
- Edges found: 0

(no edges found)

## Provenance note on "Real SEC requests made: 0"

All five filings were served from `.edgar_cache/`, populated by earlier
authorized HYP-04 EDGAR walks (1,519 cached responses, oldest dated
2026-08-28) -- this run made zero NEW network calls, but every filing text
below is real, previously-fetched SEC text, not synthetic. INTC/JBL/NVDA
were already cached because they are HYP-04's own curated anchors; AAPL/MSFT
because they recur throughout this project's other HYP-04 work. A fresh run
against tickers not already in the cache would make real, live requests
using the same `EdgarClient`/`CONTACT` path -- nothing about the extraction
logic depends on whether the text came from cache or a live call.

## Assessment

**Not ready to wire into `extract_for_universe()`'s default path.** Of the 7
edges extracted across 5 real filings, 3 are true positives and 4 are false
positives -- a 57% false-positive rate on this small sample:

| Ticker | Party captured | Verdict | Why |
|---|---|---|---|
| INTC | AMD | **true positive** | "CCG's primary competitor is AMD" -- clean, correct |
| INTC | Asi | **false positive** | Truncated capture of "Asia" (a region, mid-sentence: "...primarily in Asia") -- not a company at all |
| INTC | GlobalFoundries | **true positive** (partial) | Correct company, but the same sentence also names UMC and SMIC as competitors and neither was captured |
| JBL | Israel | **false positive** | A country name ("suppliers located in Israel") captured as a supplier's name |
| NVDA | GPUs | **false positive** | A product category ("integrated GPUs") captured as a competitor's name -- the actual sentence describes competitor TYPES, not a named company |
| NVDA | Asia | **false positive** | Same class of defect as INTC's "Asi" -- a region name, not a company |
| NVDA | SK Hynix Inc | **true positive** (partial) | Correct company, but the same sentence also names Micron and Samsung as suppliers and neither was captured |

Two distinct, identifiable defects, not one diffuse "needs work":

1. **Geographic/generic-noun false positives.** `_PARTY_NAME` matches any
   capitalized token(s) in the lookahead window that pass `clean_party()`'s
   corporate-suffix-or-Title-Case shape test -- but "Asia," "Israel," and a
   truncated "Asi" all pass that test, because a bare capitalized place name
   is structurally indistinguishable from a bare capitalized company name
   under that rule alone. A fix needs either a location-name exclusion list
   or a requirement that the matched span carry an actual corporate signal
   (Inc./Corp./Ltd., or a known-entity check against `company_tickers.json`,
   which `edgar_linkage.py` already has via `cik_for`).
2. **Multi-item list truncation.** Both true-positive sentences ("GlobalFoundries,
   UMC and SMIC"; "SK Hynix Inc., Micron Technology, Inc., and Samsung.")
   name three counterparties each; the extractor captured only the first.
   `_PARTY_NAME`'s lookahead stops at the first sentence break or matched
   name and never continues past a comma to a subsequent name, which is a
   real, boundable recall gap distinct from the precision problem above.

Zero edges on AAPL and MSFT are not, by themselves, evidence of anything
wrong -- both companies' Item 1 Business sections are consistent with using
broader, less name-specific competitive language than INTC/NVDA's, and a
sample of two non-findings is too small to separate "the anchors don't fire
on genuinely different prose" from "these two filings happen not to name
competitors densely." Worth re-checking once the two defects above are
fixed and precision is trustworthy enough that a zero-edge result means
something.

**Recommendation.** Fix the false-positive class first (highest-value single
change: it is 4 of 7 errors here) with a location/generic-noun guard, then
re-run this exact calibration script unmodified against the same five
tickers to measure whether precision actually improved rather than assuming
it did. The multi-item-list recall gap is lower priority -- it loses real
edges but never fabricates one, which is the direction of error this
project's own discipline treats as less severe. The module stays unwired
from `extract_for_universe()` until both are addressed and re-measured.
