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
