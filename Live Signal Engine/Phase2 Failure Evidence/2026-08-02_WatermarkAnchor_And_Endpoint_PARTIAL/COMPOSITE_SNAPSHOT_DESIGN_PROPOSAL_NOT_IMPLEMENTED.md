# Composite daily-cache-union snapshot — design proposal (NOT IMPLEMENTED)

**Status: proposal only. No code in this task implements any part of this
document. Stop for review, per explicit instruction.**

## Why this exists

The read-only diagnostic of the 8 endpoint-failure tickers
(`endpoint_failure_8_tickers.csv`, `ROOT_CAUSE_CLASSIFICATION.md`) found
**no narrow implementation bug** in the existing `recent_last_known_good`
fallback — every one of the 14 still-failed chunks either (a) falls
outside that fallback's documented open-month-only scope (the October
2025 / January 2026 / July 2026 closed-month chunks), or (b) has
genuinely zero cached history to fall back to (the brand-new August 1-2
open-month requests for CTSH/GME/NCLH). Fixing either of those would mean
*changing what the fallback is allowed to do*, not fixing a bug in what it
already does — exactly the "new methodological design" this task is
scoped to document, not implement.

What the diagnostic *did* find: for the October-2025 case specifically
(all 8 tickers) and the two 30/31-day July cases (CTSH, TSLA), the exact
calendar dates required are **already sitting in the cache**, just under a
different `(chunk_start, chunk_end)` key from an earlier run's rolling
lookback window. `cached_daily_rows_for_chunk()` in
`GST_Phase2_Wikipedia_Transport.py` looks up rows by an **exact**
`(ticker, chunk_start, chunk_end)` match, not by individual `date` across
all of a ticker's cached rows — so this coverage is invisible to the
lookup that matters, and a live re-fetch is attempted every day for what
is, for October 2025, a permanently-closed, unchanging historical month.

## Exact proposed algorithm

Add a **day-level union read**, used only as a fallback when the existing
exact-chunk-key cache lookup misses and a fresh fetch then fails:

1. On a chunk-fetch failure (first pass or second pass) for
   `(ticker, chunk_start, chunk_end)`, before falling through to
   `pending_second_pass`/`incomplete_after_second_pass`/the existing
   open-month-only `recent_last_known_good` fallback, query the cache for
   **all** rows matching `ticker` (any `chunk_start`/`chunk_end`) whose
   `date` falls within `[chunk_start, chunk_end]`.
2. Group the matched rows by `date`. For each date, if all matching rows
   agree on `pageviews` (see conflict handling below), keep one row; if
   they disagree, treat that date as unresolved (do not guess).
3. If the union of agreed-upon dates covers `[chunk_start, chunk_end]`
   **completely** (every calendar date present, no gaps), treat the union
   as a valid synthetic snapshot for this chunk: it may be used exactly
   like a normal `validated_cache_hit()` result.
4. If the union does **not** fully cover the interval, this fallback does
   not apply — the chunk remains `incomplete_after_second_pass` (or falls
   through to the existing narrower fallback if it's the open month),
   exactly as today. **No partial-coverage union is ever accepted as a
   complete chunk** — this preserves the existing "no zero-filling, no
   partial-data masquerading as complete" policy.
5. Record explicit new provenance on any row recovered this way (naming
   deliberately distinct from the existing `recent_last_known_good`
   fields, since the *mechanism* is different — this reconstructs from
   fragments of the SAME cache rather than reusing one aged, complete
   prior snapshot): e.g. `wiki_source_mode = "cache_union_reconstruction"`,
   plus which `(chunk_start, chunk_end)` keys contributed each date, so a
   reviewer can audit exactly how the interval was assembled.

## Required validity conditions

- The union must be **complete** — every single calendar date in
  `[chunk_start, chunk_end]` present — partial coverage never qualifies.
- Every contributing date must independently pass the same per-row
  validation `validate_snapshot()` already applies (non-negative integer
  pageviews, HTTP-200 provenance, date within its own original chunk's
  bounds).
- No contributing date may be later than the run's measured watermark —
  the union must respect `required_data_end` exactly like a normal fetch.
- This is a **read-only reconstruction of already-validated data** — it
  must never trigger a new network request itself (that's what the
  existing fetch/second-pass/open-month-fallback machinery already does);
  it only changes *what counts as a cache hit* before falling through to
  those.

## Conflict handling

If two cached rows for the same `(ticker, date)` disagree on `pageviews`
(not observed in this run's cache — the integrity scan found zero such
conflicts across all 8,137 rows — but must be handled for correctness):
- The date is treated as **unresolved**, not averaged, not defaulted to
  the more recent fetch, not defaulted to the more common value. This
  matches the project's existing "no inference" policy.
- An unresolved date breaks completeness for that chunk (per validity
  condition 1 above), so the whole union fails closed for that interval.
- The conflict itself should be logged/surfaced (e.g., a new
  `cache_identity_conflict` diagnostic counter) since it would indicate
  something has gone wrong upstream that deserves separate investigation,
  not silent resolution.

## Point-in-time implications

This changes what "the cache has this chunk" means: today, a chunk is
"cached" only if it was fetched and validated as a single, exact-boundary
request. Under this proposal, a chunk could become servable from cache
purely because **enough other, differently-bounded requests over time**
happened to cover every date in it — even if no single request ever
targeted that exact `(chunk_start, chunk_end)` pair. This is scientifically
sound (each individual date's value is still independently validated,
never fabricated or interpolated) but is a real behavioral shift worth
flagging explicitly: the "chunk" becomes a derived view over day-level
truth rather than the primary unit of trust. Any provenance/audit tooling
that currently assumes one chunk = one fetch event would need updating.

## Advantages

- Would very likely resolve the October-2025 (all 8 tickers) and the two
  July 30/31-day cases entirely, since the diagnostic already confirmed
  full/near-full coverage exists — no new network requests needed at all
  for those, eliminating repeated daily 404/429 hits against a
  historically-static month.
- Reduces load against the already-documented flaky per-article endpoint.
- Strictly additive and fail-closed: never weakens the "complete coverage
  or nothing" rule, never fabricates a value.

## Risks

- Implicitly assumes a Wikipedia pageviews value for a fixed historical
  date never legitimately changes between two different fetches (i.e.,
  Wikipedia never retroactively revises a published daily pageview count).
  The zero-conflict scan on today's cache is consistent with this
  assumption but does not prove it holds forever — a real, disagreeing
  future case would need to be handled by the conflict-resolution rule
  above, not silently ignored.
- Adds real complexity to the cache-read path (a second, more expensive
  lookup strategy that must be reasoned about alongside the existing exact
  match) — increases surface area for future bugs in exactly the kind of
  identity/completeness logic this project has already had to correct
  multiple times.
- Does **not** help the genuinely-never-fetched cases (CTSH/GME/NCLH's
  August 1-2 open-month rows, GME's entire January 2026) — those still
  need a real successful fetch or remain unresolved; this proposal is not
  a general fix for endpoint flakiness, only for the specific "we already
  have this, just under a different key" situation.
- Changes what "cached" means for provenance/audit purposes (see
  Point-in-time implications above) — downstream consumers of
  `wiki_source_mode` would need to learn a new value.

## Tests that would be required before implementation

1. Complete day-level union across two non-overlapping prior chunk keys
   exactly covers a requested interval -> synthetic snapshot accepted.
2. Union missing even a single date anywhere in the interval -> rejected,
   falls through to existing behavior unchanged.
3. Two cached rows for the same `(ticker, date)` with disagreeing
   `pageviews` -> that date treated as unresolved, completeness check
   fails, chunk not recovered via this path.
4. A contributing date later than the run's measured watermark -> excluded
   from the union (mirrors the existing `_finalize_wiki_row` defense-in-
   depth filter added in this task).
5. No network request is made when the union-fallback path is exercised
   (a mock/counter asserting `fetch` was never called for that chunk).
6. Provenance fields correctly name every contributing `(chunk_start,
   chunk_end)` key per recovered date, auditable end-to-end.
7. Equivalence test: a chunk recovered via union reconstruction produces
   byte-for-byte identical daily values (and therefore an identical
   z-score) to what a single, exact-boundary fetch of the same interval
   would have produced, using the existing frozen AAPL/AMZN fixtures as a
   base case if extendable, or a new synthetic fixture otherwise.

Stopping here per instruction — no implementation, no fallback-logic
change made in this task beyond the anchor fix, which is unrelated to this
proposal.
