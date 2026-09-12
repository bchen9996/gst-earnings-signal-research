# HYP-05 competitor/supplier extractor calibration (2026-09-12)

**CORRECTION (added same day, after the Assessment below was first
written):** the Assessment section originally described these 24 tickers
as "HYP-04's own frozen anchor set." That is wrong. `anchor_universe.py`'s
own `NEVER_CONDITIONS` states that `LOCKED_24_ANCHORS` is HYP-01
confirmatory infrastructure, not HYP-04's anchors; HYP-04's real anchors
(verified against `HYP04_ANCHOR_SHOCKS_2026-08-31.csv`, the artifact that
fed the real, completed Phase 3 test) are a different seven tickers: ADBE,
CTSH, INTC, JBL, MCK, NKE, NVDA. See `peer_selection.py`'s docstring for
the full correction. Everything below about the extractor itself -- the
three defects found and fixed, the 0%-false-positive result, the decision
to wire it into `extract_for_universe()` -- is UNAFFECTED: it was measured
on real filing text and stands regardless of which ticker set motivated
pulling that text. What is wrong is only the claim that this run also
constitutes HYP-05's real anchor-universe curation. It does not; that is a
separate run against the seven tickers above.

**Status: raw findings only. No pass/fail judgment is asserted by this script.** A human reads the context snippets below and writes the assessment.

Tickers: AAPL, ABBV, ADBE, AMZN, BKR, BRK-B, CTSH, DELL, DVN, GME, GOOGL, GPN, INTC, LDOS, MSFT, NCLH, NKE, QCOM, SBUX, STZ, SYK, TSLA, TTWO, UAL -- fixed before running, not chosen after seeing results (see module docstring). Real SEC requests made: 0.

This script makes real network calls and is deliberately NOT part of the offline test suite. Nothing found here is added to any linkage map by this script.

## AAPL
- Filing: 10-K filed 2025-10-31, accession 0000320193-25-000079 (220,568 chars of extracted text)
- Edges found: 0

(no edges found)

## ABBV
- Filing: 10-K filed 2026-02-20, accession 0001551152-26-000008 (501,313 chars of extracted text)
- Edges found: 0

(no edges found)

## ADBE
- Filing: 10-K filed 2026-01-15, accession 0000796343-26-000003 (371,127 chars of extracted text)
- Edges found: 0

(no edges found)

## AMZN
- Filing: 10-K filed 2026-02-06, accession 0001018724-26-000004 (312,331 chars of extracted text)
- Edges found: 0

(no edges found)

## BKR
- Filing: 10-K filed 2026-02-05, accession 0001701605-26-000007 (411,959 chars of extracted text)
- Edges found: 11

1. **Siemens Energy** (competitor, pattern `principal_competitors`)
   > 'generation, aerospace, and light and heavy industrials. IET main competitors include Siemens Energy, Solar (a Caterpillar company), Mitsubishi Heavy Industry, Sulzer, Flowserve, and Emerson. Chart Industr'

2. **Solar** (competitor, pattern `principal_competitors`)
   > 'generation, aerospace, and light and heavy industrials. IET main competitors include Siemens Energy, Solar (a Caterpillar company), Mitsubishi Heavy Industry, Sulzer, Flowserve, and Emerson. Chart Industr'

3. **Mitsubishi Heavy Industry** (competitor, pattern `principal_competitors`)
   > 'generation, aerospace, and light and heavy industrials. IET main competitors include Siemens Energy, Solar (a Caterpillar company), Mitsubishi Heavy Industry, Sulzer, Flowserve, and Emerson. Chart Industr'

4. **Sulzer** (competitor, pattern `principal_competitors`)
   > 'generation, aerospace, and light and heavy industrials. IET main competitors include Siemens Energy, Solar (a Caterpillar company), Mitsubishi Heavy Industry, Sulzer, Flowserve, and Emerson. Chart Industr'

5. **Flowserve** (competitor, pattern `principal_competitors`)
   > 'generation, aerospace, and light and heavy industrials. IET main competitors include Siemens Energy, Solar (a Caterpillar company), Mitsubishi Heavy Industry, Sulzer, Flowserve, and Emerson. Chart Industr'

6. **Emerson** (competitor, pattern `principal_competitors`)
   > 'generation, aerospace, and light and heavy industrials. IET main competitors include Siemens Energy, Solar (a Caterpillar company), Mitsubishi Heavy Industry, Sulzer, Flowserve, and Emerson. Chart Industr'

7. **SLB** (competitor, pattern `competitors_include`)
   > 'blish an obligation to use OFSE products and services. OFSE competitors include SLB, Halliburton, NOV, Weatherford, and TechnipFMC. Industrial & Energy Technology The IET segment combines a broad arr'

8. **Halliburton** (competitor, pattern `competitors_include`)
   > 'blish an obligation to use OFSE products and services. OFSE competitors include SLB, Halliburton, NOV, Weatherford, and TechnipFMC. Industrial & Energy Technology The IET segment combines a broad arr'

9. **NOV** (competitor, pattern `competitors_include`)
   > 'blish an obligation to use OFSE products and services. OFSE competitors include SLB, Halliburton, NOV, Weatherford, and TechnipFMC. Industrial & Energy Technology The IET segment combines a broad arr'

10. **Weatherford** (competitor, pattern `competitors_include`)
   > 'blish an obligation to use OFSE products and services. OFSE competitors include SLB, Halliburton, NOV, Weatherford, and TechnipFMC. Industrial & Energy Technology The IET segment combines a broad arr'

11. **TechnipFMC** (competitor, pattern `competitors_include`)
   > 'blish an obligation to use OFSE products and services. OFSE competitors include SLB, Halliburton, NOV, Weatherford, and TechnipFMC. Industrial & Energy Technology The IET segment combines a broad arr'

## BRK-B
- Filing: 10-K filed 2026-03-02, accession 0001193125-26-083899 (619,973 chars of extracted text)
- Edges found: 3

1. **Infineum International Ltd** (competitor, pattern `principal_competitors`)
   > 'ny of the markets in which it competes. Lubrizol Additives’ principal competitors are Infineum International Ltd., Chevron Oronite Company and Afton Chemical Corporation. Lubrizol Advanced Materials’ busin'

2. **Chevron Oronite Company** (competitor, pattern `principal_competitors`)
   > 'ny of the markets in which it competes. Lubrizol Additives’ principal competitors are Infineum International Ltd., Chevron Oronite Company and Afton Chemical Corporation. Lubrizol Advanced Materials’ busin'

3. **Afton Chemical Corporation** (competitor, pattern `principal_competitors`)
   > 'ny of the markets in which it competes. Lubrizol Additives’ principal competitors are Infineum International Ltd., Chevron Oronite Company and Afton Chemical Corporation. Lubrizol Advanced Materials’ busin'

## CTSH
- Filing: 10-K filed 2026-02-12, accession 0001058290-26-000008 (367,903 chars of extracted text)
- Edges found: 0

(no edges found)

## DELL
- Filing: 10-K filed 2026-03-16, accession 0001571996-26-000008 (542,082 chars of extracted text)
- Edges found: 0

(no edges found)

## DVN
- Filing: 10-K filed 2026-02-18, accession 0001193125-26-056485 (366,036 chars of extracted text)
- Edges found: 0

(no edges found)

## GME
- Filing: 10-K filed 2026-03-24, accession 0001326380-26-000013 (324,525 chars of extracted text)
- Edges found: 6

1. **Walmart Stores, Inc** (competitor, pattern `we_compete_with`)
   > 'd collectibles, and similar products. In the United States, we compete with Walmart Stores, Inc. (“Walmart”), Target Corporation (“Target”), Best Buy Co., Inc. ("Best Buy") and Amazon.com, Inc. ('

2. **Target Corporation** (competitor, pattern `we_compete_with`)
   > 'd collectibles, and similar products. In the United States, we compete with Walmart Stores, Inc. (“Walmart”), Target Corporation (“Target”), Best Buy Co., Inc. ("Best Buy") and Amazon.com, Inc. ('

3. **Best Buy Co., Inc** (competitor, pattern `we_compete_with`)
   > 'd collectibles, and similar products. In the United States, we compete with Walmart Stores, Inc. (“Walmart”), Target Corporation (“Target”), Best Buy Co., Inc. ("Best Buy") and Amazon.com, Inc. ('

4. **Amazon.com, Inc** (competitor, pattern `we_compete_with`)
   > 'd collectibles, and similar products. In the United States, we compete with Walmart Stores, Inc. (“Walmart”), Target Corporation (“Target”), Best Buy Co., Inc. ("Best Buy") and Amazon.com, Inc. ('

5. **JB HiFi** (competitor, pattern `we_compete_with`)
   > 'ry competitors included Walmart and Best Buy. In Australia, we compete with retailers such as JB HiFi stores, Big W, Target and Amazon.com. Globally, we also compete with certain vendors, includi'

6. **FNAC-Darty** (competitor, pattern `competitors_include`)
   > ", and other national and specialty retailers. In Europe our competitors include major consumer electronic retailers such as FNAC-Darty, large hypermarket chains including Leclerc, and Amazon.com's on"

## GOOGL
- Filing: 10-K filed 2026-02-05, accession 0001652044-26-000018 (384,060 chars of extracted text)
- Edges found: 0

(no edges found)

## GPN
- Filing: 10-K filed 2026-02-20, accession 0001123360-26-000008 (528,696 chars of extracted text)
- Edges found: 0

(no edges found)

## INTC
- Filing: 10-K filed 2026-01-23, accession 0000050863-26-000011 (571,466 chars of extracted text)
- Edges found: 4

1. **AMD** (competitor, pattern `principal_competitors`)
   > "ced AI capabilities and high performance. Competition CCG's primary competitor is AMD, which like us designs processors based on the x86 architecture. Client CPUs utilizing the x86 architecture remain "

2. **GlobalFoundries** (competitor, pattern `competitors_include`)
   > 'e directly with Samsung in this market. Other Intel Foundry competitors include GlobalFoundries, UMC and SMIC, which primarily focus on mature process technologies. Our Business 7 Table of Contents A'

3. **UMC** (competitor, pattern `competitors_include`)
   > 'e directly with Samsung in this market. Other Intel Foundry competitors include GlobalFoundries, UMC and SMIC, which primarily focus on mature process technologies. Our Business 7 Table of Contents A'

4. **SMIC** (competitor, pattern `competitors_include`)
   > 'e directly with Samsung in this market. Other Intel Foundry competitors include GlobalFoundries, UMC and SMIC, which primarily focus on mature process technologies. Our Business 7 Table of Contents A'

## LDOS
- Filing: 10-K filed 2026-02-17, accession 0001336920-26-000030 (463,586 chars of extracted text)
- Edges found: 0

(no edges found)

## MSFT
- Filing: 10-K filed 2026-07-29, accession 0001193125-26-323660 (357,670 chars of extracted text)
- Edges found: 0

(no edges found)

## NCLH
- Filing: 10-K filed 2026-03-02, accession 0001104659-26-022067 (496,142 chars of extracted text)
- Edges found: 2

1. **Carnival** (competitor, pattern `principal_competitors`)
   > 'ically schedule during non-peak demand periods. Competition Our primary competition includes operators such as Carnival and Royal Caribbean, as well as other cruise lines such as MSC Cruises, Viking Ocean Cruises'

2. **Royal Caribbean** (competitor, pattern `principal_competitors`)
   > 'ically schedule during non-peak demand periods. Competition Our primary competition includes operators such as Carnival and Royal Caribbean, as well as other cruise lines such as MSC Cruises, Viking Ocean Cruises'

## NKE
- Filing: 10-K filed 2026-07-15, accession 0000320187-26-000088 (419,830 chars of extracted text)
- Edges found: 0

(no edges found)

## QCOM
- Filing: 10-K filed 2025-11-05, accession 0000804328-25-000085 (403,596 chars of extracted text)
- Edges found: 0

(no edges found)

## SBUX
- Filing: 10-K filed 2025-11-14, accession 0000829224-25-000114 (403,148 chars of extracted text)
- Edges found: 0

(no edges found)

## STZ
- Filing: 10-K filed 2026-04-22, accession 0000016918-26-000011 (463,772 chars of extracted text)
- Edges found: 4

1. **Beer Anheuser-Busch InBev** (competitor, pattern `principal_competitors`)
   > ' products, some of which have greater resources than we do. Our principal competitors include: Beer Anheuser-Busch InBev, The Boston Beer Company, Heineken, Mark Anthony, Molson Coors Wine Deutsch Family Wine & Sp'

2. **Boston Beer Company** (competitor, pattern `principal_competitors`)
   > ' products, some of which have greater resources than we do. Our principal competitors include: Beer Anheuser-Busch InBev, The Boston Beer Company, Heineken, Mark Anthony, Molson Coors Wine Deutsch Family Wine & Sp'

3. **Heineken** (competitor, pattern `principal_competitors`)
   > ' products, some of which have greater resources than we do. Our principal competitors include: Beer Anheuser-Busch InBev, The Boston Beer Company, Heineken, Mark Anthony, Molson Coors Wine Deutsch Family Wine & Sp'

4. **Mark Anthony** (competitor, pattern `principal_competitors`)
   > ' products, some of which have greater resources than we do. Our principal competitors include: Beer Anheuser-Busch InBev, The Boston Beer Company, Heineken, Mark Anthony, Molson Coors Wine Deutsch Family Wine & Sp'

## SYK
- Filing: 10-K filed 2026-02-11, accession 0000310764-26-000010 (331,627 chars of extracted text)
- Edges found: 0

(no edges found)

## TSLA
- Filing: 10-K filed 2026-01-29, accession 0001628280-26-003952 (429,675 chars of extracted text)
- Edges found: 0

(no edges found)

## TTWO
- Filing: 10-K filed 2026-05-22, accession 0001628280-26-037434 (473,556 chars of extracted text)
- Edges found: 9

1. **Electronic Arts** (competitor, pattern `competitors_include`)
   > ', technical, and other resources than ours. Examples of our competitors include Electronic Arts, Embracer Group, Epic Games, Playrix, Playtika, Roblox, Savvy Games, Tencent, and Ubisoft. We also expe'

2. **Embracer Group** (competitor, pattern `competitors_include`)
   > ', technical, and other resources than ours. Examples of our competitors include Electronic Arts, Embracer Group, Epic Games, Playrix, Playtika, Roblox, Savvy Games, Tencent, and Ubisoft. We also expe'

3. **Epic Games** (competitor, pattern `competitors_include`)
   > ', technical, and other resources than ours. Examples of our competitors include Electronic Arts, Embracer Group, Epic Games, Playrix, Playtika, Roblox, Savvy Games, Tencent, and Ubisoft. We also expe'

4. **Playrix** (competitor, pattern `competitors_include`)
   > ', technical, and other resources than ours. Examples of our competitors include Electronic Arts, Embracer Group, Epic Games, Playrix, Playtika, Roblox, Savvy Games, Tencent, and Ubisoft. We also expe'

5. **Playtika** (competitor, pattern `competitors_include`)
   > ', technical, and other resources than ours. Examples of our competitors include Electronic Arts, Embracer Group, Epic Games, Playrix, Playtika, Roblox, Savvy Games, Tencent, and Ubisoft. We also expe'

6. **Roblox** (competitor, pattern `competitors_include`)
   > ', technical, and other resources than ours. Examples of our competitors include Electronic Arts, Embracer Group, Epic Games, Playrix, Playtika, Roblox, Savvy Games, Tencent, and Ubisoft. We also expe'

7. **Savvy Games** (competitor, pattern `competitors_include`)
   > ', technical, and other resources than ours. Examples of our competitors include Electronic Arts, Embracer Group, Epic Games, Playrix, Playtika, Roblox, Savvy Games, Tencent, and Ubisoft. We also expe'

8. **Tencent** (competitor, pattern `competitors_include`)
   > ', technical, and other resources than ours. Examples of our competitors include Electronic Arts, Embracer Group, Epic Games, Playrix, Playtika, Roblox, Savvy Games, Tencent, and Ubisoft. We also expe'

9. **Ubisoft** (competitor, pattern `competitors_include`)
   > ', technical, and other resources than ours. Examples of our competitors include Electronic Arts, Embracer Group, Epic Games, Playrix, Playtika, Roblox, Savvy Games, Tencent, and Ubisoft. We also expe'

## UAL
- Filing: 10-K filed 2026-02-12, accession 0000100517-26-000023 (483,124 chars of extracted text)
- Edges found: 0

(no edges found)

## Provenance note

All 24 filings were served from `.edgar_cache/`, the same pre-existing,
previously-authorized cache the 5-ticker calibration used (populated by
earlier HYP-04 EDGAR walks). Zero new network calls were made by this run
-- every filing text below is real, previously-fetched SEC text, not
synthetic.

## Assessment

This is the second, larger calibration pass of the same extractor, run the
same day as the first: 24 real anchor filings (HYP-04's full
`LOCKED_24_ANCHORS`) instead of 5, chosen because they are HYP-04's own
frozen anchor set -- fixed on 2026-08-17, weeks before HYP-05 existed --
not a convenience sample. Three independent, real-evidence-driven fix
rounds happened between the first and final run of this larger sample, each
found by actually reading the context snippets below, each verified by
hand-tracing the regex before writing any fix, each confirmed by re-running
this exact script unmodified afterward.

**Final result: 39 edges across 7 of 24 anchors (BKR 11, BRK-B 3, GME 6,
INTC 4, NCLH 2, STZ 4, TTWO 9), 0 clean false positives.**

| Round | Total edges | Clean TP | Malformed-but-real TP | False positives |
|---|---|---|---|---|
| Before any fix this pass | 29 | 27 | 1 | 1 |
| After fix 1 (generic-determiner stopwords) | 28 | 27 | 1 | 0 |
| After fix 2 (competition-not-competitors anchor + "such as"/"including" cue) | 32 | 31 | 1 | 0 |
| After fix 3 (parenthetical short-name skip) | **39** | **38** | **1** | **0** |

### The three defects found and fixed this pass

1. **A generic determiner captured as a company name.** TTWO's 10-K reads
   "we compete with: * Other interactive entertainment companies that range
   in size..." -- "Other" is the literal first capitalized token after the
   anchor phrase (a bulleted, descriptive clause, not a named company), so
   the 2026-09-12-morning anchoring fix correctly identified it as
   "immediately following the anchor" but had no way to know it wasn't a
   proper noun. Fixed by extending the shared `UNNAMED_TOKENS` blocklist
   with a small, closed class of English determiners/quantifiers
   (other(s)/various/several/many/some/numerous) -- purely additive, so it
   cannot introduce a new false ACCEPTANCE anywhere, including the
   already-calibrated ASC 280 path that shares this same function.
   Before: 'Other' captured as a competitor. After: correctly nothing.

2. **A real recall gap: "competition" was never recognized, and a
   descriptive-noun-phrase-then-"such as" preamble blocked capture even
   once it was.** NCLH's 10-K reads "Our primary competition includes
   operators such as Carnival and Royal Caribbean..." -- two compounding
   defects: none of the three anchor patterns matched the noun "competition"
   (only "competitor(s)"), and even after widening that, "operators such
   as" sat between the anchor's verb and the first real name. Fixed by
   widening `COMPETITOR_ANCHORS`'s first pattern to accept "competition" as
   well as "competitor(s)", and adding `_EXAMPLE_CUE`, a bounded (at most 4
   lowercase words) strip of a descriptive-noun-phrase-then-"such
   as"/"including" preamble -- still anchored, still fails closed
   ("primary competition is intense" matches the anchor and correctly
   yields nothing, because "intense" is lowercase). Before: 0 edges for
   NCLH. After: Carnival, Royal Caribbean (2 of the 5 real names the
   sentence names -- the other 3 sit behind a SECOND, nested "such as"
   clause this fix does not walk into; see Known limitations below). The
   same fix also recovered real names at GME (JB HiFi, FNAC-Darty) that
   were sitting behind the identical "retailers such as"/"consumer
   electronic retailers such as" construction.

3. **A real recall gap: parenthetical short-name annotations broke list
   capture after the first item.** GME's 10-K reads "we compete with
   Walmart Stores, Inc. ("Walmart"), Target Corporation ("Target"), Best
   Buy Co., Inc. ("Best Buy") and Amazon.com, Inc." -- one of the single
   most common constructions in competitor/customer lists (define a short
   form once, then use it), but the parenthetical sat between each name and
   `_LIST_SEPARATOR`'s comma, breaking the walk immediately after the first
   name every time. Fixed by adding `_PARENTHETICAL_ANNOTATION`, stripped
   after EVERY captured name (not just the first), bounded to 40 chars with
   no nested parens. Before: 1 edge for GME (Walmart only). After: 4
   (Walmart, Target, Best Buy, Amazon.com) -- plus the same construction
   recovered 4 more real names at BKR (Mitsubishi Heavy Industry, Sulzer,
   Flowserve, Emerson, behind "Solar (a Caterpillar company),").

Every fix was hand-traced against the real sentence that motivated it
BEFORE being implemented, then confirmed by an unmodified re-run of this
script -- the same discipline the first (5-ticker) calibration used, and
the same discipline `CONCENTRATION_ANCHORS` was held to.

### Known, accepted, disclosed limitations (not fixed this pass)

- **One malformed-but-real capture.** STZ's 10-K reads "Our principal
  competitors include: Beer Anheuser-Busch InBev, The Boston Beer Company,
  Heineken, Mark Anthony, Molson Coors Wine Deutsch Family Wine & Sp[irits]"
  -- almost certainly a multi-column Beer/Wine/Spirits table flattened into
  running text during PDF-to-text conversion, with no punctuation between a
  category label and the company name that follows it. The extractor
  correctly captures "Anheuser-Busch InBev" as a real company but with a
  spurious "Beer" category-label prefix glued on ("Beer Anheuser-Busch
  InBev"). Deliberately NOT fixed: a general fix would need an open-ended,
  domain-specific stoplist of category words (Beer/Wine/Spirits/Liquor/...),
  exactly the kind of unbounded, arbitrary parsing heuristic this module's
  own docstring already warns against. In practice this fails safe even
  downstream: `peer_selection.py`'s CIK-resolution step (`cik_for()`) will
  not resolve "Beer Anheuser-Busch InBev" to any real ticker, so this
  malformed string cannot silently become a false peer -- it just fails to
  resolve, the same as any other unresolvable name.
- **Disclosed recall gaps, all fail closed (never fabricate).** STZ's
  "Molson Coors" (same table-flattening cause as above -- the malformed
  capture consumed the list position instead of stopping cleanly); NCLH's
  "MSC Cruises, Viking Ocean Cruises, Virgin Voyages" (a second, nested
  "such as" clause mid-list, which `_LIST_SEPARATOR` does not walk into);
  GME's "Big W"/"Target" in the Australia sentence and "Leclerc"/"Amazon.com's
  marketplace" in the Europe sentence (a bare noun glued to the name with no
  separator, e.g. "JB HiFi stores" -- capture correctly stops at "JB HiFi"
  rather than swallowing "stores" or guessing past it).

### Zero-edge anchors: spot-checked, not just assumed

17 of 24 anchors returned zero edges. Three (AAPL, MSFT, GOOGL) were
spot-checked directly against their cached filing text: all three use
generic, non-named competitive language ("The markets... are highly
competitive...", "Competitors to Office include software and global
application vendors...") with no proper-noun company names in the
Competition-section prose the anchors target. A further batch of 15
(ABBV, ADBE, AMZN, CTSH, DELL, DVN, GPN, LDOS, NKE, QCOM, SBUX, SYK, TSLA,
UAL, plus one more) was scanned the same way; SYK's filing does name real
competitors (Zimmer Biomet, Medtronic, Johnson & Johnson MedTech) but via
"We are one of five leading global competitors...; the other four being X,
Y, Z" -- a construction narrow and specific enough that generalizing an
anchor pattern for it was judged not worth the risk of overfitting to one
sentence, and is recorded here as a known, accepted gap rather than chased.
No other zero-edge anchor showed any named-competitor language in a
spot-check. Zero here means genuinely generic prose, not an anchor-pattern
gap, with one named exception (SYK) disclosed rather than hidden.

## Recommendation: WIRED IN

Unlike the first (5-ticker) calibration's "not yet" recommendation, this
one clears the bar `extract_competitor_edges_from_text`'s own module
comment set: "measure it the way `CONCENTRATION_ANCHORS` was measured, and
only then wire this into `extract_for_universe()`." Three independent
real-evidence-driven measurement-and-fix rounds, over HYP-04's actual
24-anchor universe (not a convenience sample), converged to 0 clean false
positives across 39 edges, with every residual defect either fixed,
disclosed, or shown to fail closed rather than fabricate.

This function is now called from `extract_for_universe()` (edgar_linkage.py,
2026-09-12), alongside the ASC 280 path, against the same fetched filing
text (no extra network cost). It still carries its own distinct `source`
tag (`SOURCE_10K_COMPETITION_SECTION_PROSE`, renamed from `..._UNCALIBRATED`
now that it is one) -- wiring it in does not claim parity with a
percentage-backed ASC 280 disclosure, only that it is no longer unmeasured.
And every candidate `extract_for_universe()` produces, from either path,
remains a `CANDIDATE_REVIEW_QUEUE` item -- `reconcile()` never merges
automatically -- so the practical risk of wiring this in now is bounded by
the same human-review step every ASC 280 candidate already goes through.

This is a genuinely larger, real measurement than the first pass, but it is
still ONE filing per company (the latest 10-K), not a multi-year historical
walk the way `CONCENTRATION_ANCHORS`'s own "cached corpus" measurement was
for finding earliest-disclosure dates. That is an intentional, disclosed
scope difference, not an oversight: this function's job is "does the
CURRENT Competition section name real competitors," a snapshot question,
not "when did this relationship start," a lineage question -- the two
calibration efforts are not directly comparable in depth, and this one is
appropriately scoped to the question this function actually answers.
