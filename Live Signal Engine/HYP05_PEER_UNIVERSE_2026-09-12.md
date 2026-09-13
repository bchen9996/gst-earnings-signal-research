# HYP-05 peer universe -- first real curation pass (2026-09-12)

**Result: zero candidates qualify as HYP-05 peers from this pass.** That is
the honest, correctly-derived answer given what this pass actually
covered, not a failure of the tooling -- see below for why, and what a
next pass would need to change.

## What this pass covered

HYP-04's real, verified anchor set (ADBE, CTSH, INTC, JBL, MCK, NKE, NVDA
-- see `peer_selection.py`'s docstring for how this was confirmed, after
an earlier same-day correction), each anchor's LATEST 10-K only (not a
historical walk), run through the wired extractor (both the ASC 280
concentration path and the now-calibrated competitor/supplier-context
path). That produced 9 named edges, 8 distinct candidate names:

| Candidate | Anchor | Direction |
|---|---|---|
| AMD | INTC | competitor |
| CVS Health Corporation | MCK | customer (ASC 280, 24%/21%) |
| GlobalFoundries | INTC | competitor |
| Micron Technology, Inc | NVDA | supplier |
| SK Hynix Inc | NVDA | supplier |
| SMIC | INTC | competitor |
| Samsung | NVDA | supplier |
| UMC | INTC | competitor |

The MCK -> CVS Health Corporation edge, at 24%/21% concentration, matches
HYP-04's own existing curated linkage map exactly (`HYP04_Linkage_Map_v1.3.
csv`) -- strong independent confirmation the corrected anchor set is right.

## Name resolution: mostly real answers, one real gap in the method

Ran `run_hyp05_peer_name_search.py` (HYP-04's own company-search + lineage-
test machinery, reused unchanged) against these 8 names, twice (the first
attempt hit heavy SEC `browse-edgar` 503s -- 6 of 8 unanswered; a second
attempt improved that to 3 unanswered). Not retried a third time, out of
respect for an endpoint that was visibly struggling both times.

Final result, 1 of 8 resolved to a tradeable US ticker:

- **GlobalFoundries -> GFS.** Correct: GlobalFoundries IPO'd in 2021 and
  trades as GFS.
- **AMD, Samsung, SK Hynix, UMC -> "hits found but none matched at the
  disclosure date."** This is a REAL finding, not a tooling failure.
  Samsung Electronics and SK Hynix are South Korean companies with no SEC
  registration at all -- "no continuous US filer under this name" is the
  correct, honest answer for both. AMD and UMC's cases are more likely
  name-search collisions (EDGAR's `browse-edgar` prefix match returning
  unrelated registrants) worth a closer manual look in a future pass, but
  are not evidence either company doesn't exist.
- **CVS Health Corporation, Micron Technology, Inc, SMIC -> unanswered**
  (SEC search endpoint failures across both attempts). Genuinely
  unanswered, not a negative finding -- CVS in particular is almost
  certainly resolvable on a calmer day (it is one of the most liquid,
  actively-filing US companies there is).

## The market-cap computation, and a real bug fixed along the way

`shares_outstanding.py` only read 10-K/10-Q filings for the point-in-time
shares-outstanding fact. GlobalFoundries -- a foreign private issuer --
files Form 20-F instead, so its real, filed share counts (2021-2025) were
being silently excluded, and every one of its 79 real HYP-04 anchor
(INTC) events came back "missing_shares" regardless of date, including
dates long after GFS existed as a public company. Fixed by adding "20-F"
to `QUALIFYING_FORM_PREFIXES` -- safe, because
`dei:EntityCommonStockSharesOutstanding` is a standardized cover-page tag
independent of GAAP/IFRS or form type. After the fix: 11 of GFS's 79
events now compute a real market cap ($25-30 billion range, all in 2022+),
correctly denied on PS-3 (>= $2B); the remaining 68 (pre-2021, before GFS
existed as a public filer) are correctly and honestly denied as
not-computable, not silently treated as zero or skipped.

**Before the fix, 0/79 would have looked like "missing data everywhere."
After the fix, 0/79 means "GlobalFoundries is genuinely too large,
confirmed with a real $25-30B market cap" -- a materially different and
much more trustworthy claim, even though the pass/fail outcome (0
qualifying) didn't change.** This is exactly the kind of distinction this
project's own discipline cares about: the NUMBER staying the same is not
the same as the FINDING staying the same.

## Why the honest answer is "zero, for now" -- and what would change it

Every candidate this pass surfaced skews large: CVS Health, AMD, Samsung,
Micron, GlobalFoundries, SMIC, UMC are all multi-billion-dollar companies.
That is not a coincidence of bad luck -- it is what LATEST-10-K-only
extraction from Competition/customer-concentration sections tends to
surface: a large filer's competitors and customers, when it names them at
all, are usually other large, well-known companies. HYP-05's actual
question (transmission among LOWER-coverage peers) needs a candidate pool
that reaches further than that.

Two concrete next steps, either or both:

1. **A historical multi-year walk per anchor**, not latest-10-K-only --
   matching the depth `CONCENTRATION_ANCHORS` itself was measured to. A
   company's disclosed competitors/customers change over time and across
   filings; a single snapshot understates the real candidate pool.
2. **Hand-curation**, the way HYP-04's own original 6-peer map was built --
   deliberately looking for smaller, less-obvious counterparties rather
   than relying only on what a filer's own prose happens to name.

Neither is started in this pass. This report is the honest record of what
a first, fully-automated, single-snapshot pass actually found: real
tooling, real data, real fixes along the way, and a candidate pool that
(correctly, unsurprisingly) skewed too large to produce a qualifying peer
yet.

---

## Update: the historical walk (same day), and where this leaves HYP-05

Step 1 above was done same day: `run_competitor_history_walk.py` walked
EVERY 10-K on record (not just the latest) for all 7 real anchors,
entirely from the existing `.edgar_cache` (0 new SEC requests). It found
34 distinct (counterparty, direction) pairs -- genuinely smaller,
less-obvious real companies the latest-10-K pass never surfaced: Corel,
Jasc Software, Macromedia, Coremetrics, Nedstat, Quark, Getty Images,
Shutterstock, Foundry, Quixel, Unity, C4D (ADBE's competitors, 2000-2021);
IMFT, an Intel-Micron joint venture (INTC); Unimicron Technology
Corporation, Ibiden Co. Ltd (three string variants across years), Nanya
Technology Corporation, Kinsus Interconnect Technology Corporation (NVDA's
suppliers). Reviewing that raw output for data-quality sanity also
surfaced a real 4th extractor defect (an unbounded corporate-suffix
match swallowing part of the next name in a list -- "Avid, Corel" merging
into a malformed "Avid, Co" and silently dropping three real companies),
fixed the same day.

A fixed, hand-picked allowlist of 20 of those 34 names -- the genuinely
smaller/less-obvious ones, deliberately excluding names already known to
be large (Apple, Microsoft, Google, Samsung, TSMC, Micron, SK Hynix,
GlobalFoundries, SMIC, UMC, AMD, Oracle, IBM) -- went through EDGAR name
resolution, twice (SEC's company-search endpoint was flaky both times;
retried once, not a third time, same discipline as every other name-search
this session).

**Final result across both attempts: zero of the 20 resolved to a
currently-tradeable ticker.** Two resolved to a real, identified,
lineage-confirmed registrant that no longer trades:

- **Corel** -- was a real, publicly traded company (historically Nasdaq:
  CORL) before going private. Correctly identified, correctly excluded --
  no current ticker means no current price, means no computable market
  cap, means it cannot be evaluated against PS-3 either way.
- **Macromedia** -- was acquired by Adobe itself in 2005. Same outcome,
  same reason, and a nice confirmation the lineage test is working as
  intended: it found the real company and correctly reported it as
  untradeable rather than silently dropping it or guessing.

The rest split between genuinely UNANSWERED (SEC 503s, both attempts --
Jasc Software, Nanya Technology Corporation, Quixel, Shutterstock never
got a real answer and remain open questions, not negative findings), and
NO_REGISTRANT_MATCHED (Coremetrics, IMFT, all three Ibiden variants,
Kinsus, Unimicron Technology Corporation, Nedstat -- plausible for a
private/foreign/JV entity that was never independently SEC-registered),
and hits-found-but-lineage-refused (Avid, C4D, Foundry, Getty Images,
Quark, Unity -- Unity's case is worth noting specifically: the disclosure
date, 2020-01-21, predates Unity's actual September 2020 IPO, so "not
filing under this name on that date" is the CORRECT answer, not a search
failure).

### The honest headline: zero real HYP-05 peers qualify yet, after real effort

Across every method tried today -- HYP-04's real anchor set (corrected
mid-session from a wrong premise), the calibrated and now-wired
competitor/supplier extractor, both a latest-10-K pass and a full
historical multi-year walk, real EDGAR name resolution attempted twice --
**no candidate has yet resolved to both a currently-tradeable ticker AND a
market cap under the $2B threshold.** One candidate (GlobalFoundries)
computed a real market cap and was correctly denied for being too large
($25-30B). Two more (Corel, Macromedia) were correctly identified as real
companies that no longer trade at all. Everything else is either a
confirmed-large mega-cap, a genuinely foreign/private/JV entity with no
US listing, or a real SEC endpoint failure still waiting on an answer.

This is not a failure of today's work -- it is what the work actually
found, reported the same way every null result this project produces has
been reported. It does point at something worth naming plainly: **both
extraction methods tried so far (ASC 280 concentration disclosures, and
competitor/supplier Competition-section prose) structurally tend to
surface a filer's most PROMINENT named counterparties**, whether the
filer itself is large or small -- a company names its biggest rival or
customer far more often than an obscure one, in both a single filing and
across two decades of filings. Reaching further back in time (what the
historical walk did) surfaced real, smaller companies, but most of those
turned out to be either defunct/acquired or never independently
SEC-registered in the first place -- not because the method is wrong, but
because genuinely thin, still-independently-trading micro/small-cap peers
are, definitionally, not the kind of company that gets NAMED prominently
by a large anchor's own prose. A different discovery method -- hand
curation informed by domain knowledge, or a structurally different
disclosure source -- is the more promising next step, not a third pass of
the same two extraction paths over a still-longer history.

The 20-name resolution attempt, both rounds, and the reasoning above are
recorded in `HYP05_PEER_NAME_SEARCH_HISTORICAL_WALK_2026-09-12.json`. No
market-cap pass was run against this batch -- with zero tradeable tickers
resolved, there was nothing left to evaluate.

---

## Update: hand curation (same day) -- the first real qualifying HYP-05 peer

The recommended next step above was hand curation: naming a specific
real-world relationship from general knowledge instead of waiting for a
filer's own prose to name it. That is a DIFFERENT KIND of claim than
everything else in this report -- an assertion from training knowledge,
not something extracted from a filing read this session -- so it was
built and gated differently, and only proceeded after checking with the
owner on approach.

### The gate: nothing proposed is trusted until EDGAR confirms it independently

`hand_curated_candidates.py` lists 26 proposed (anchor, counterparty,
direction) triples across all 7 real anchors, deliberately favouring
companies believed smaller than everything the automated passes above
already found. Every entry is labelled a proposal, not a fact, in the
module's own docstring.

`run_hyp05_verify_candidates.py` is the actual gate: for each proposal, it
searches EDGAR's own full-text index (`efts.sec.gov`, reusing
`AgreementSearchClient` from `edgar_agreements.py` unchanged) for the
counterparty's name RESTRICTED to the anchor's own 10-K filings, then
fetches the real document and extracts the actual sentence the name
appears in. A candidate only counts as `filed_mention_confirmed` if BOTH
the search index reports a hit AND this script independently locates and
reads the name inside real filing text -- a raw index hit with no
readable context is tracked separately
(`search_hit_found_but_context_unreadable`) and excluded from the
confirmed set, not counted either way. This distinction was not
theoretical: the first live run confirmed 9 of 26 candidates, but hand-
inspecting the context sentences (the same "read the raw snippet, don't
trust the aggregate" discipline this project has used all session) found
two ADBE hits (Shutterstock, Figma) whose indexed document was an
"unofficial pdf" copy `strip_markup` cannot parse, and one CTSH hit
(Syntel) whose archive URL 404'd (a pre-2001 filing with a non-standard
path) -- all three had empty context and were silently being counted as
confirmed. The script was corrected to require readable context before
confirming anything, and re-run. Final, honest result: **6 of 26
confirmed with readable evidence.**

Of those 6, hand-reading the context mattered again:

| Candidate | Anchor | Context found | Assessment |
|---|---|---|---|
| GoPro | JBL | "our largest customers include Apple, Inc., Cisco Systems, Inc., GoPro, Inc., Hewlett-Packard Company, ..." | Strong -- textbook customer-concentration sentence. |
| Ambarella | NVDA | "...suppliers of SOC products...such as Ambarella, Inc., AMD, Apple, Inc., ...Intel, ...Qualcomm..." | Strong -- Nvidia's own named competitor list. |
| Under Armour | NKE | "Corp., Puma, Li Ning and Under Armour, among others." | Reasonable -- a real competitor-listing sentence. |
| WNS | CTSH | "...added Exlservice Holdings Inc, Genpact Ltd and WNS Holdings LTD in our definition of a peer group company..." | Moderate -- a compensation peer-group disclosure (BPO-industry peer), not a product-market "Competition" section. |
| ExlService | CTSH | (same sentence as WNS) | Moderate, same caveat. |
| Wolverine World Wide | NKE | "...The Dow Jones U.S. Footwear Index consists of NIKE, Stride Rite Corp., Timberland Co., Wolverine World Wide, Inc., and Crocs, Inc..." | Weak -- stock-index co-membership in a performance-graph table, not a competition claim. Kept in the artifact rather than silently dropped, flagged here instead. |

### Name resolution and market cap

Fed through the existing, unchanged pipeline
(`run_hyp05_peer_name_search.py`, `run_hyp05_peer_market_cap.py`,
`--out HYP05_PEER_UNIVERSE_HAND_CURATED_2026-09-12.json` to avoid
overwriting this file's own artifact):

- **Resolved to a tradeable ticker (3 of 6):** Ambarella -> AMBA, GoPro ->
  GPRO, Under Armour -> UA.
- **Hits found but none matched at the disclosure date (2 of 6):** WNS,
  ExlService -- a real, honest name-resolution outcome, not an endpoint
  failure, so not retried.
- **Failed lineage resolution (1 of 6):** Wolverine World Wide -- also the
  one flagged weak on evidence grounds above; consistent finding.

Point-in-time market cap was evaluated against every real anchor event
for each resolved ticker's anchor (45 NVDA events for AMBA, 89 JBL events
for GPRO, 4 NKE events for UA -- NKE genuinely has only 6 total registered
anchor-event rows in `HYP04_ANCHOR_SHOCKS_2026-08-31.csv`, a pre-existing
characteristic of that frozen artifact, not a new bug). UA's 4 events
(2003-2004) predate Under Armour's actual 2005 IPO and correctly failed
with a real `yfinance` "data doesn't exist" error; GPRO's early events
likewise correctly denied on missing pre-IPO price/shares data.

**AMBA (Ambarella) qualifies at 8 of 45 NVDA anchor events -- HYP-05's
first real qualifying peer.** All 8 fall between 2016-05-12 and
2020-08-19, with real, computed point-in-time market caps between $1.14B
and $1.94B, all below the $2B threshold. The rule's own boundary behaviour
confirms this isn't an artifact of the code: the very next adjacent
events it evaluated -- 2016-08-11 ($2.03B) and 2020-11-18 ($2.16B) --
were correctly DENIED for being just above threshold, and 2021-02-24
($4.26B, after Ambarella's post-2020 run-up) was correctly denied by a
wide margin. Pre-IPO dates (2003-2012, before Ambarella's October 2012
IPO) were correctly denied for missing shares/price data rather than
silently treated as zero.

### What this does and does not establish

This confirms AMBA passes HYP-05's own eligibility rule (`peer_selection.
py`'s PS-1..PS-3, `MARKET_CAP_THRESHOLD_USD`) as a real, tradeable,
sub-$2B, EDGAR-named counterparty of NVDA at 8 real anchor-event dates. It
does NOT confirm delayed transmission actually happened at those events --
that is Phase 2/3 machinery, not run here. It also does not independently
verify "competitor" is the right characterization of the NVDA/Ambarella
relationship beyond what the filed sentence itself says (which is
explicit: Nvidia's own 10-K lists Ambarella among named SOC-product
competitors).

Artifacts: `hand_curated_candidates.py` (proposals),
`HYP05_HAND_CURATED_VERIFICATION_2026-09-12.json` (full-text verification,
including the unconfirmed and context-unreadable entries),
`HYP05_CANDIDATE_LINKAGE_HAND_CURATED_2026-09-12.json` (the 6 confirmed
edges), `HYP05_PEER_NAME_SEARCH_HAND_CURATED_2026-09-12.json` (name
resolution), `HYP05_PEER_UNIVERSE_HAND_CURATED_2026-09-12.json` (market
cap + derivation -- kept separate from this file's own
`HYP05_PEER_UNIVERSE_2026-09-12.json` artifact rather than overwriting
it).

### Honest headline, updated

Pass 1 (automated extraction) found zero qualifying peers. Pass 2 (hand
curation, gated by real EDGAR full-text confirmation before anything was
trusted) found one: **AMBA, a real, verified, sub-$2B peer of NVDA, at 8
real anchor events.** The remaining 20 of 26 proposals were either
genuinely unconfirmed by a readable filing (17) or confirmed but did not
resolve to a currently tradeable, eligible ticker (2: WNS, ExlService
unmatched at the disclosure date; Wolverine World Wide failed lineage).
That is a small, real result, not a large one -- eight (peer, event)
pairs across one ticker, out of 138 evaluated -- and it is reported at
exactly that size, not rounded up or generalized beyond what was found.

---

## Update: round 2 -- 42 more proposals, two real tooling fixes, still one qualifying peer

The owner asked for more proposals, with the intent of moving to Phase 2
with a bigger sample if they cleared. `hand_curated_candidates.py` grew
from 26 to 68 entries (42 new, none duplicating round 1). Six of the new
ones were not blind guesses: NVDA's and NKE's own confirmed round-1
context sentences already named other companies in the same list
(Marvell Technology Group, Mobileye, ST Microelectronics; Puma, Li Ning)
that had not been proposed as their own candidates -- added here rather
than left on the table.

### Two more real false-signal patterns caught by hand-reading, both fixed in code

The first live verification run confirmed 20 of 68. Hand-reading every
context sentence (same discipline as round 1, and as every extractor fix
this project made this session) found two RECURRING false-signal
patterns, not one-offs to patch by hand:

1. **Stock-performance-graph benchmark-index tables.** Five NKE
   candidates (Wolverine World Wide, Crocs, Deckers Outdoor, Skechers,
   Steven Madden) all "confirmed" purely because Dow Jones happened to
   bucket them into the same footwear index as NIKE in a proxy-statement
   performance graph -- not because NIKE's own prose named them as
   competitors.
2. **Director/officer biography mentions.** MCK's "confirmed" hit on
   Owens & Minor was actually "Group Vice President and Corporate
   Officer, Owens & Minor (1994 - 1996)." -- a director's PRIOR
   EMPLOYER, not a McKesson business relationship.

Both are now real, tested code: `classify_context()` in
`run_hyp05_verify_candidates.py`, with a dedicated regression test
(`test_hyp04_supply_chain_hedge_verify_candidates.py`) built on the exact
real sentences above, not paraphrases. Re-running with the fix in place
correctly dropped all six: **14 of 68 confirmed** with genuine,
on-topic evidence.

### A live SEC endpoint defect found and worked around

Resolving the 14 confirmed names surfaced a third, unrelated issue: EDGAR's
own `browse-edgar` company search returned a completely empty result for
the exact query "Columbia Sportswear" -- despite Columbia Sportswear
Company being a real, currently-trading company (CIK 0001050797, ticker
COLM). Investigating rather than accepting the negative found that a
broader query ("Columbia") DID return entries, but with the company name
replaced by a literal Perl array-reference dump
(`ARRAY(0x55a888699870)`) instead of an actual name -- a defect on SEC's
own legacy CGI script, reproduced directly against the live endpoint by
hand, not assumed. Manually confirmed Columbia Sportswear's lineage using
its independently-obtained CIK and the project's own `peer_lineage.assess()`
machinery (`continuous_under_this_name`) before building a permanent fix:
`ticker_map_fallback_ciks()`, a fallback in `run_hyp05_peer_name_search.py`
that tries `company_tickers.json` (the same endpoint `edgar_agreements.
AgreementSearchClient.cik_for()` already uses) whenever `browse-edgar`
returns zero candidates for a real, non-failed search -- tested offline
against a synthetic ticker-map fixture
(`test_hyp04_supply_chain_hedge_hyp05_name_search_fallback.py`), then
re-run live. Result: Columbia Sportswear resolves correctly (COLM) via
the fallback path; the fallback is recorded explicitly in the output
(`ticker_map_fallback_used_for`) so it is never confused with an ordinary
browse-edgar hit.

(One further candidate, "ST Microelectronics", still failed to resolve --
this is a genuine data-entry gap in the proposal itself: the real
registrant name has no space, "STMicroelectronics". Confirmed directly
against the live endpoint. Not re-run: NVDA's own 10-K already places it
alongside AMD/Qualcomm/TI-scale competitors, so it was proposed "for
completeness rather than because it's expected to qualify" and is very
unlikely to pass the $2B threshold even if resolved.)

### Name resolution and market cap, round 2

5 of 14 confirmed candidates resolved to a tradeable ticker: Ambarella
(AMBA, same as round 1), **Columbia Sportswear (COLM, new)**, **DocuSign
(DOCU, new)**, GoPro (GPRO, same as round 1), Under Armour (UA, same as
round 1). Evaluated against every real anchor event for each one's anchor
(171 total pairs). COLM's 4 available NKE events (2003-2004) and DOCU's 29
available ADBE events (2008-2014) both predate real, structural facts --
Columbia Sportswear's pre-2009 filings predate when `dei:
EntityCommonStockSharesOutstanding` XBRL tagging became standard (missing
shares data, not a code defect), and DocuSign's actual IPO was 2018, years
after every available ADBE event window closes (correctly denied for
missing price AND shares, with a real `yfinance` "data doesn't exist"
error as independent confirmation). UA repeated round 1's pre-IPO result.

**Result: still exactly one qualifying peer, AMBA, at the same 8 of 45
NVDA events found in round 1.** Round 2 substantially widened the search
(68 proposals vs. 26, 14 confirmed with genuine evidence vs. 6, 5 resolved
tradeable tickers vs. 3) and fixed three real tooling gaps along the way,
but did not surface a second qualifying peer or add to AMBA's own 8-event
sample -- the two new resolved tickers (COLM, DOCU) both had real,
structural reasons their available anchor-event windows couldn't produce
a computable market cap, not a near-miss on the $2B threshold.

Artifacts: `HYP05_HAND_CURATED_VERIFICATION_ROUND2_2026-09-12.json` (all 68,
including the two new rejection categories),
`HYP05_CANDIDATE_LINKAGE_HAND_CURATED_ROUND2_2026-09-12.json` (14 confirmed
edges), `HYP05_PEER_NAME_SEARCH_HAND_CURATED_ROUND2_2026-09-12.json` (name
resolution, including the ticker-map fallback), `HYP05_PEER_UNIVERSE_
HAND_CURATED_ROUND2_2026-09-12.json` (market cap + derivation).

### Honest headline after two rounds

68 hand-curated proposals across both rounds, 14 with genuine filed
evidence after fixing three real false-signal/tooling gaps, 5 resolved to
tradeable tickers, 1 -- AMBA -- actually qualifies, at 8 real NVDA anchor
events. The sample available for a Phase 2 move is the same size it was
after round 1: 8 (peer, event) pairs, one ticker. Widening the proposal
list further is possible (both rounds together have covered a minority of
plausible smaller counterparties for the 7 anchors), but round 2's own
result argues it isn't guaranteed to produce more -- the two new resolved
tickers both failed for structural data-availability reasons specific to
their own histories, not for being close misses on size.

---

## Update: round 3 -- mine real sentences instead of guessing; still one qualifying peer, for a structural reason now made explicit

The owner asked for a differently-targeted round rather than more of round
2's size-matched guessing, given INTC's own 0-of-10 confirmation rate
across both rounds with no rich sentence to mine (deliberately NOT
extended further -- there was no specific citable reason left to try, only
more guessing). Round 3's method: mine round 1-2's OWN already-confirmed
real sentences for additional named companies not yet proposed, plus read
the full MCK receivables-agreement document (the same filing Rite Aid's
evidence came from) rather than only the narrow snippet already captured.
28 new proposals (96 total), every one with a specific, citable reason
(the exact sentence or document it was mined from), not a size-matched
guess.

### The method worked: 24 of 28 confirmed (86%), vs. round 2's much lower rate

NKE alone: 14 of 14 mined from its own "BY WAY OF ILLUSTRATION ONLY,
examples of NIKE competitors include..." sentence and its "Significant
Customers" sentence -- 100%. CTSH, NVDA, JBL, MCK candidates mined from
their own real sentences/documents also confirmed at a high rate. Reading
the real disclosure first and proposing names FROM it, instead of guessing
names and hoping they were in there, is a materially better method --
worth recording plainly since it changes how a future round should be
built.

### Two more things caught by hand-reading, one fixed as a generalized filter, one as a data correction

1. **ADBE/Citrix was a false positive, same FAMILY as round 2's Owens &
   Minor catch but a different phrasing.** The context: "Mr. Demo is a
   member of the Board of Directors of Citrix Systems, Inc. and is the
   Vice Chairman of the national Board of Directors of AeA..." -- an
   Adobe director's OTHER board seat, not an Adobe/Citrix business
   relationship. `classify_context()` gained a third pattern,
   `BOARD_OR_OFFICER_AFFILIATION`, generalized rather than left as a
   Citrix-specific patch (it is the second distinct phrasing of the same
   underlying "governance mention, not a business relationship" problem
   found this session), with its own regression test on this exact real
   sentence. Re-run: Citrix correctly dropped.
2. **NKE/Foot Locker was mis-classified, not a false positive.** Proposed
   as a competitor (it was named in the same "examples of competitors"
   sentence as a parenthetical, "Venator (Footlockers)"), but the REAL,
   stronger evidence the verification step actually found was a
   different sentence entirely -- a genuine ASC-280-style customer-
   concentration disclosure: "Foot Locker, Inc. ... accounted for
   approximately 11 percent of global net sales of NIKE brand products
   during fiscal 2002." Corrected `direction` from "competitor" to
   "customer" in `hand_curated_candidates.py` to match what the filed
   text actually says, with the correction documented in the entry
   itself rather than silently changed.

### Name resolution: real companies, mostly no longer trading -- and why that is the actual finding, not noise

37 confirmed candidates resolved through the same pipeline. Result: **zero
new tradeable tickers.** Every round-3-specific name resolved to one of:
a real registrant with no current ticker (Reebok -> acquired by Adidas
2006; Oakley -> acquired by Luxottica 2007; Saucony -> acquired by Stride
Rite 2005; Freescale Semiconductor -> merged into NXP 2015; Foot Locker --
see below), hits found but none matched at the specific historical
disclosure date (Adidas, Converse, Asics, Callaway Golf, Titleist, Tommy
Hilfiger, Sports Authority, FILA, Puma, Mobileye, Imagination
Technologies), or no registrant matched at all (DKNY, Diamond Cluster,
LM Ericsson, Nokia Networks, Osco Drug, Umbro -- plausibly foreign,
private, or a brand name never independently SEC-registered).

**Foot Locker's own result was investigated by hand rather than accepted
at face value**, since Foot Locker is a well-known, currently-recognizable
retail name and "no current ticker" looked surprising: its CIK
(0000850209) is confirmed real with a filing as recent as 2025-11-13, but
carries no ticker in SEC's current company list -- consistent with Dick's
Sporting Goods' 2025 acquisition of Foot Locker having closed. A real,
measured survivorship loss, not a tooling defect; investigating it
directly (rather than assuming either "bug" or "correct") is the same
discipline every other surprising result this session got.

### The structural reason now made explicit

Across three rounds, the SAME pattern keeps appearing: real, well-
evidenced, genuinely smaller counterparties from 15-25 years ago have
overwhelmingly been ACQUIRED, taken private, merged, or gone bankrupt by
now -- Reebok, Oakley, Converse, Saucony, Tommy Hilfiger, Sports
Authority, Freescale Semiconductor, Marvell Technology Group (via
redomiciliation), iGate, Rite Aid, Foot Locker (most recently). This is
not a coincidence or a tooling gap: a company that STAYED small enough to
clear a $2B threshold for 15+ years, without being acquired, going
bankrupt, or growing past the threshold, is comparatively rare among
real, historically-named competitors and customers of giant anchors --
most real small companies in a given competitive set either get bought
(the successful ones) or fail (the unsuccessful ones) well before a
20-year mark. AMBA (Ambarella) remains the one qualifying peer precisely
because it did neither: it IPO'd in 2012 and has traded independently,
at a genuinely sub-$2B market cap, at multiple real NVDA anchor events
since.

Artifacts: `HYP05_HAND_CURATED_VERIFICATION_ROUND3_2026-09-12.json` (all
96, including the board-affiliation rejection category),
`HYP05_CANDIDATE_LINKAGE_HAND_CURATED_ROUND3_2026-09-12.json` (37
confirmed edges, Foot Locker's direction corrected to "customer").
No new market-cap run was needed -- the 5 resolved tradeable tickers
(AMBA, COLM, DOCU, GPRO, UA) are identical to round 2's, against the same
anchors, so the result is unchanged by construction, not re-verified
redundantly.

### Honest headline after three rounds

96 hand-curated proposals across three rounds (26 + 42 + 28), 37 with
genuine filed evidence, 5 resolved to tradeable tickers, 1 -- AMBA --
actually qualifies, unchanged since round 1: 8 of 45 real NVDA anchor
events, market caps $1.14B-$1.94B. Round 3's much better-targeted method
(mining real sentences: 86% confirmation rate vs. guessing's much lower
rate) still did not add a second qualifying peer, and the reason is now a
structural, explained finding rather than an open question: real,
smaller, historically-named counterparties of giant anchors are
survivorship-selected against staying both small AND independently
tradeable for long. The Phase-2-eligible sample remains 8 (peer, event)
pairs across one ticker.

## Round 4 (2026-09-12): reverse the search direction, not the guessing

Rounds 1-3 all shared one bottleneck: every candidate name had to occur
to Claude first, then EDGAR either confirmed or denied it. That is a hard
recall ceiling regardless of which anchor it is pointed at. At the
owner's direction, round 4 tried a genuinely different mechanism instead
of a fourth round of guessing: `run_hyp05_reverse_concentration_search.py`
searches the WHOLE EDGAR full-text corpus, unscoped by CIK, for [an
anchor's name] AND [a customer-concentration tail-phrase] -- so a SMALL
company's OWN 10-K, disclosing that a large anchor is a material share of
ITS revenue (an ASC 280 disclosure, close to mandatory and formulaic),
surfaces directly. No guessing involved. Anchors covered: the original 7
plus 20 members of HYP-01's `LOCKED_24_ANCHORS` never mined this way (27
total, 34 name variants, 4 tail-phrases, 136 searches, 360 total requests).

**Raw result: 223 distinct (anchor, peer) leads discovered, 17 confirmed**
(real, readable, sentence contains both the anchor's name and a
percent-style figure) -- `HYP05_REVERSE_SEARCH_RAW_HITS_2026-09-12.json`.
That is already more confirmed leads than three rounds of hand curation
produced from 96 proposals, and none of the 17 were ever proposed by
Claude in rounds 1-3 -- direct evidence the mechanism reaches real
companies personal recall does not.

**Hand review, same discipline as every prior round -- read every
sentence before trusting the count.** Two real defects surfaced, neither
patched by editing the raw output (append-only; see
`run_hyp05_reverse_search_handreview.py`'s own docstring for the full
per-entry reasoning):

- **4 of 17 were false positives**, none of which happened to matter
    for eligibility (all 4 CIKs carry no current ticker either way) but
    are still wrong and are documented as such: a bond coupon rate
    ("2.875% Convertible Senior Notes") mistaken for a concentration
    percentage (PDL Biopharma/ABBV); two market-share-among-competitors
    statements mistaken for customer concentration (Movie Gallery/GME,
    Carnival PLC/NCLH); one name collision where the FILER's own name
    ("Global Payments Technology Inc.") contained the short anchor-name
    variant used for GPN (Global Payment Technologies Inc/GPN).
- **10 of the remaining 13 carried the wrong relationship direction.**
    The search module hardcoded `direction: "customer"` for every hit,
    assuming every concentration sentence means the filer sells TO the
    anchor. Two disclosure genres share identical tail-phrases: "our
    sales TO [anchor] ... X% of our net revenue" (the peer is the
    anchor's SUPPLIER) versus "our purchases FROM [anchor]" or "[anchor],
    a supplier, accounted for X% of OUR sales" (the peer is the anchor's
    CUSTOMER, same direction as the Foot Locker/NKE correction in round
    3). Corrected by hand, per sentence, not patched into the search
    module as an untested heuristic.
- One more (Micron Technology/INTC) named a real, well-documented
    relationship (the IMFT/IMFS joint ventures) by OWNERSHIP PERCENTAGE,
    not a customer/supplier/competitor disclosure this schema has a
    category for -- left out rather than miscoded into the nearest label.

**12 genuine, hand-verified relationships survived review** -- a 71% true-
positive rate on this pass, comparable to round 3's 86% on mined
sentences and far above blind guessing. 5 resolved to a currently
tradeable ticker (Micron was the 6th raw "tradeable" but is excluded per
the schema-mismatch above): CNXN (PC Connection, DELL's customer), NGS
(Natural Gas Services Group, DVN's supplier), TTWO (Take-Two Interactive,
GOOGL's supplier), AMAT (Applied Materials, INTC's supplier), and SHOE
(Shoe Carnival -- renamed Shoe Station Group Inc 2026-06-11, confirmed a
plain rename via SEC `formerNames`, not an acquisition -- NKE's
customer).

**Eligibility check: 0 of 83 (peer, event) pairs qualify, for THREE
distinct, explainable reasons, not one structural finding:**

  1. **CNXN/DELL, NGS/DVN, TTWO/GOOGL: zero usable anchor events, full
     stop.** `HYP04_ANCHOR_SHOCKS_2026-08-31.csv` has never had earnings-
     shock computation run for DELL, DVN, or GOOGL -- those three anchors
     were added to round 4's SEARCH list (as sources of peer-discovery
     text) without also extending HYP-04's own anchor-shock pipeline to
     them. This is not a peer-side finding at all; it is a prerequisite
     this pass did not do.
  2. **AMAT/INTC: genuinely, definitively too large throughout.** 61 of
     79 real events resolve a real market cap, all of them $109B-$164B --
     multiple orders of magnitude above the $2B cutoff. The remaining 18
     (2005-2009) predate SEC XBRL shares-outstanding coverage.
  3. **SHOE/NKE: unresolved by data availability, not disqualified by
     size.** NKE's only 4 shock-computed anchor events in the current CSV
     all fall in 2003-2004 -- entirely before `dei:
     EntityCommonStockSharesOutstanding` XBRL tagging existed for most
     filers. Point-in-time market cap is honestly reported as NOT
     COMPUTABLE (PS-2), never guessed at or defaulted through. Shoe
     Carnival may or may not have qualified; the current pipeline simply
     cannot say for these 4 dates.

### Honest headline after round 4

The mechanism is validated: reversing the search direction found 12 real,
hand-verified relationships from one run, where three rounds of guessing
found one. None of this pass's specific candidates cleared eligibility,
but for reasons that are fixable in principle and distinct from rounds
1-3's structural survivorship finding: (a) three anchors need their own
earnings-shock computation before their peers can be evaluated at all,
and (b) one promising candidate (Shoe Carnival/NKE) is blocked by a pre-
XBRL data gap, not by size. The Phase-2-eligible sample remains 8 (peer,
event) pairs across one ticker (AMBA/NVDA) -- unchanged by round 4 -- but
the path to a larger sample now looks like "compute anchor shocks for a
few more anchors and find a pre-XBRL shares-outstanding source," not
"guess harder."
