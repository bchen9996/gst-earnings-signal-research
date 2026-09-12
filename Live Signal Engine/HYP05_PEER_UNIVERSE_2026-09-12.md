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
