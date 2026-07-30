# GST "Attention-Risk Monitoring" Product — Feasibility Scoping

**Status: scoping only. Not a pitch, not a build plan, not a recommendation to proceed.**
No code, workflows, CSVs, the Phase 2 spec, or CHANGELOG.md were touched to produce
this document — it is pure research and writing, done in parallel with (and without
altering) the separate, in-progress Phase 2 run-3 / GitHub Actions work.

This document was written without access to a prior brainstorm doc referencing the
Google Trends API alpha — a search of this repo (including `Live Signal Engine/`)
turned up no such file. Everything below is either freshly researched (search
performed at write time, not recalled from training data — Google's Trends API
alpha and its terms could plausibly have changed) or derived from this project's
own already-verified engineering history. Anywhere a claim can't be traced to one
of those two sources, it's flagged as unverified.

---

## 0. The product idea, stated plainly

"Attention-risk monitoring" as a B2B product would mean: sell subscribers a signal
that flags elevated public attention (search interest, possibly other sources) on
a company, disambiguated by *what kind* of attention it is (earnings-related vs.
layoffs-related vs. litigation-related vs. ordinary brand interest), as a leading
indicator of risk. That disambiguation — "query-family separation" — is the part
that turns "we track one GST z-score per ticker" into "we track a company's
*reputation surface*," and it's the part this document spends the most time on,
because it's the part most likely to be underestimated.

## 1. What query-family separation actually requires

### 1.1 What exists today

Every GST-pulling script in this project (`GST_Phase2_DailyPanel.py`,
`GST_MultiTicker_Forward_Log.py`, `GST_MSFT_Forward_Quote_Log.py`,
`GST_Live_Signal_Engine.py`) does the same thing per ticker per day: **one**
`pytrends` `build_payload()` + `interest_over_time()` call, using the bare ticker
symbol as the search term, over a fixed 300-day lookback window. That single raw
0-100 series is then turned into a z-score via a 12-period rolling window
(`ROLLING_WINDOW=12`, `MIN_PERIODS=8`, `STD_EPSILON_FLOOR=1.0`). One term, one
query, one series, per ticker, per day. There is no query-family concept
anywhere in the current codebase.

### 1.2 What "MSFT earnings" vs. "MSFT layoffs" actually means technically

Google Trends' `interest_over_time()` returns values **normalized to the maximum
within that specific request** — not an absolute count. Two consequences that
matter here:

- To get a genuinely independent, day-over-day-comparable historical z-score for
  each family term (the same guarantee the current single-term series has), each
  term needs **its own independent query with its own 300-day lookback**, run and
  renormalized every single day — the same shape as today's per-ticker query, just
  duplicated per family term. You cannot get this by batching up to 5 terms into
  one `build_payload()` call and reading off relative proportions: that batch's
  0-100 scale is relative to whichever term in *that specific request* peaked
  highest, which is a different, incomparable scale from any other day's batch
  (especially once the batch membership or window shifts even slightly) — the
  exact class of subtle normalization dependency this project already had to
  reason carefully about once, in the CandidateB/MultiTicker column-order and
  MSFT-divergence work.
- So: N query-family terms per ticker ≈ **N× the daily pytrends query volume**
  for that ticker, not a comparison-request trick that avoids multiplying calls.

### 1.3 Why this multiplies a problem that isn't solved yet

At 24 tickers, **one** query each, inside a single ~1-hour collection window, this
project has already measured real 429 rate-limiting pressure — not a hypothetical.
The sibling forward-log pipeline (same `pytrends` access pattern, 29 tickers, one
query each) logged 12/29 and 14/29 zero-week GST fetch failures on two separate
days before a fix was shipped (2026-07-29) to stop mislabeling those failures as
"insufficient history." That fix makes the failure *visible and categorized* — it
does not make the underlying rate-limiting go away, and post-fix runs still show
non-zero 429 counts. **The 429 problem at 1 query/ticker is understood and now
honestly reported, but not eliminated.**

A query-family design with even a modest family size (say, 3 terms per ticker: the
base ticker term plus two attention-type qualifiers) at the same 24-ticker universe
means roughly **3× today's query volume inside the same narrow same-day-comparable
collection window** — the exact conditions already producing double-digit percent
failure rates at 1×. A richer family (5+ terms, to meaningfully cover
earnings/layoffs/litigation/M&A/product-recall-style categories) could mean 5-8×.
Nothing about the current pytrends-based architecture suggests this scales by
just running the existing script more times; it's a rate-limit regime change, and
the honest expectation is *materially worse* completeness before any other work,
not "roughly the same, more data."

### 1.4 The parts of this that are genuinely new engineering, not scaling

- **Term selection is a research task, not a config change.** Someone has to
  decide, per company (or per sector, if terms are meant to generalize), what
  search-term family actually separates "earnings attention" from "layoffs
  attention" from background brand noise — and then validate that the terms
  chosen actually carry that signal against real historical events, the same way
  this project's existing hypotheses were pre-registered and tested. That's weeks
  of methodology work per category of attention the product claims to detect, not
  an afternoon of picking synonyms.
- **The z-score methodology isn't proven to transfer.** `ROLLING_WINDOW=12`,
  `MIN_PERIODS=8`, and `STD_EPSILON_FLOOR=1.0` were tuned against the behavior of
  a single ticker-name search term, which is relatively high-volume and rarely
  near-zero. A term like "MSFT layoffs" is very plausibly much sparser and
  noisier — more weeks near the Trends floor, more reliance on
  `STD_EPSILON_FLOOR` clipping, a real chance the same formula produces junk
  z-scores on the low-volume family terms specifically. This needs its own
  validation pass; assuming the existing formula "just works" on new term types
  is exactly the kind of optimistic assumption this document is trying not to make.
- **None of this touches the Wikipedia-pageview or price/volume/IV legs** already
  in the Phase 2 schema — those stay single-series per ticker regardless. Only
  the GST leg multiplies.

**Bottom line on section 1:** query-family separation is a rate-limit-regime
change, a term-selection research task, and a methodology-validation task, stacked
on top of a rate-limit problem that is *currently* only partially mitigated at 1
query/ticker. Calling it "a small add-on" would be wrong; it's comparable in scope
to standing up a second data-collection pipeline with its own validation cycle.

## 2. Legal / access reality check (researched at write time, not recalled)

### 2.1 Google's general API Terms of Service

Fetched directly from `developers.google.com/terms/` at write time. The relevant
clauses (quoted, not paraphrased):

> "Copy, translate, modify, create a derivative work of, sell, lease, lend,
> convey, distribute, publicly display, or sublicense to any third party" —
> listed as a prohibited use of content/data obtained via a Google API.

> "Scrape, build databases, or otherwise create permanent copies of such content,
> or keep cached copies longer than permitted by the cache header."

> "You will only access (or attempt to access) an API by the means described in
> the documentation of that API."

**This is a real problem for the current architecture before any B2B question
even comes up.** `pytrends` is an unofficial library that scrapes the public
Google Trends *website's* internal endpoints — it is not "the means described in
the documentation" of any Google API, because there was no documented, sanctioned
API for this until very recently (see 2.2). Everything this project has built to
date, including the already-fixed forward logs and Phase 2 panel, runs on that
same unofficial access pattern. That's a defensible-enough position for private,
non-redistributed research use, but it is a materially different (and weaker)
legal footing than a contracted relationship with Google — and the general ToS
language above is squarely about *not* redistributing or selling API-derived data
to third parties, which is the core mechanic of the proposed product.

### 2.2 The official Google Trends API (alpha) — does it change this?

Google announced an official **Google Trends API (alpha)** on 2025-07-24
(`developers.google.com/search/blog/2025/07/trends-api`), with a live application
page at `developers.google.com/search/apis/trends`. Confirmed directly from that
page and Google's own announcement coverage:

- Provides "access to a rolling window of the last 5 years of data," with
  daily/weekly/monthly/yearly aggregation and country/sub-region breakdowns.
- Explicitly offers **consistent scaling across requests** — data from multiple
  requests can be joined/compared/merged, which is a direct fix for exactly the
  normalization-instability problem described in section 1.2. If this project
  ever gets access, it is the correct long-term foundation for query-family work,
  not pytrends.
- Access is alpha-gated: "available only to a very limited number of testers,"
  application-form-only, with Google stating it prioritizes "developers that know
  what they want to do, that can start doing it soon, and that are willing to
  provide feedback." A public Google Search Central Community thread titled
  "Google Trends API alpha access application — no response received" indicates
  applying does not reliably or quickly result in access — treat "we'll get in"
  as unconfirmed, not a planning assumption.
- **Could not find, in any page reachable during this research pass, alpha-specific
  terms that explicitly permit (or forbid) commercial redistribution of derived
  data to paying customers.** Absent an explicit carve-out, the general Google
  APIs ToS language in 2.1 is the default that applies. This is a genuinely open
  legal question, not a solved one — it would need direct clarification from
  Google (as part of, or before, requesting alpha access) or actual legal review
  before any commercial commitment, not an assumption in either direction.

### 2.3 Google Trends' own attribution guidance

From `support.google.com/trends/answer/4365538` (the official "export, embed, and
cite" help page): "You can use any information from Google Trends, subject to the
Google Terms of Service. If you reuse Trends data, attribute the information to
Google with a citation." This confirms reuse-with-attribution is fine for the
kind of citation this project already does internally — it does not address
resale, and doesn't override the general ToS restrictions in 2.1.

**Bottom line on section 2:** the current data-collection method (pytrends) is on
weaker legal footing than a commercial product should be built on. The official
alpha API is the right long-term answer technically (it fixes the normalization
problem too), but access is unconfirmed, slow or unresponsive by at least one
public report, and its commercial-redistribution terms are not publicly resolved
as of this research. Any commercialization plan needs this resolved as an
explicit, dated decision — not inherited silently from the current research setup.

## 3. Brutally honest gap list: today vs. the described MVP

| | **Exists today** | **MVP as described** |
|---|---|---|
| Universe | 24 tickers, locked, chosen from tickers with prior clean real-quote history in *this* research project — not a general-purpose "any company" selection process | 25-50 companies — plausibly a different, unvetted set; no process yet for choosing/onboarding an arbitrary company |
| Data collection | One manually-verified script (`GST_Phase2_DailyPanel.py`); as of this writing, 2 manual test runs completed and committed, a 3rd run/backoff-hardening pass in progress separately (not evaluated further here, per this task's scope) | Reliable, unattended, daily collection across a larger universe |
| Automation | Not yet proven: no GitHub Actions workflow exists for this panel as of this writing; the *separate* forward-log repos in this project only recently (2026-07-29) got their own automation reliability fixes, and those cover a different ticker set and different fields | Fully unattended daily operation, implicitly for paying customers who notice outages |
| Query scope per company | 1 query/day/ticker (raw ticker symbol) | Query-family attribution (multiple queries per company, see section 1) — not designed, not term-validated, not rate-limit-tested |
| Reporting | Raw CSV rows, no report generation, no customer-facing artifact of any kind | Daily reports — a templating/generation/delivery layer that doesn't exist |
| Customer validation | None conducted as part of this project | Customer interviews — a go-to-market activity fully outside this project's engineering work to date |
| Legal footing | Research-only use on an unofficial scraping library, not evaluated for commercial risk before now | A paying product reselling derived Trends data — see section 2's open legal question |

**Honest time/effort read:** this is not "finish Phase 2, then layer features on
top for a few weeks." Reliably standing up unattended collection at the *current*
24-ticker, 1-query-per-ticker scope is itself the immediate, not-yet-done
prerequisite (section 4). Query-family separation on top of that is closer to a
second research-and-build cycle of its own — term selection and validation,
methodology revalidation for sparser series, and a rate-limit regime that gets
harder, not easier, as coverage grows (section 1.3) — plausibly comparable in
duration to the work already invested in this project's existing GST
infrastructure to date, not a bolt-on measured in days. Report generation,
customer interviews, and the legal resolution in section 2 are additional,
largely disjoint tracks on top of that. Stating a single confident number here
would be a false precision this document is explicitly trying to avoid; the
honest statement is "substantially longer than the MVP description implies, with
real open risks (legal, rate-limit, methodology) that could each independently
block it," not a schedule.

## 4. What this document is not saying

This is not a recommendation to build the query-family system, apply for Trends
API alpha access, or start customer interviews. None of that is well-founded
until a more basic question is answered with real evidence, and it isn't yet:

**The actual prerequisite is that the Phase 2 daily information-arrival panel
runs reliably, unattended, on its current locked 24-ticker/single-query scope —
proven over real time, not a single clean manual run — before any part of this
product direction is worth pursuing further.**
