# Changelog

## 2026-08-03 — Correction: cache-hash discrepancy reconciled (report-only, no cache/code change)

**What was flagged.** The prior report for the subchunk-recovery pass recorded the operational cache's SHA-256 as `e3ebecd2...` at Lane B preflight, then `29d072f2...` "immediately before the deterministic suite" a few steps later, without explaining the difference. This entry reconciles it.

**Finding.** Both hashes were computed identically — same absolute path (`Live Signal Engine/Phase2_Wikipedia_Cache.csv` under this repo root), same tool (`sha256sum`, which hashes raw bytes with no line-ending normalization), same algorithm. This is not a hashing-procedure or path artifact: the file's content genuinely changed between the two checkpoints, from 8,162 to 8,163 data rows (net +1).

**Root cause.** Between preflight and the "before suite" checkpoint, an initial regression-check pass mistakenly included `test_phase2_wikipedia_equivalence.py` — a live-network test (distinct from `test_phase2_wikipedia_equivalence_deterministic.py`) that never overrides `CACHE_PATH` and therefore reads/writes the real operational cache by design. It fetched fresh AAPL/AMZN Wikipedia data to compare direct-vs-chunked equivalence; AMZN came back INCONCLUSIVE (nothing written), AAPL succeeded. `write_chunk_to_cache()` first removes any existing rows for the same `(ticker, chunk_start, chunk_end)` key before appending — AAPL's existing 1-row group for chunk `(2026-08-01, 2026-08-03)` (from the earlier 24-ticker regression, watermark then at 2026-08-01) was replaced by a fresh 2-row group (`20260801`, `20260802`; watermark had since advanced to 2026-08-02), both `last_verified_utc=2026-08-03T20:35:45+00:00`, matching the file's own recorded mtime exactly. Net effect: −1 row, +2 rows = +1, fully accounted for.

**Legitimacy.** Both changed rows carry `http_status=200` and a genuine `wikimedia.org` per-article URL, written through the same production `get_ticker_wikipedia_daily()` → `validate_snapshot()` → `write_chunk_to_cache()` path used everywhere else in this module — not a bug, not corruption, not a test artifact bypassing validation. The gap was in test-run *hygiene* (a live test was run during a "confirm no regressions" pass that should have been deterministic-only) and in *reporting* (the subsequent "byte-identical before/after the deterministic suite" claim was true for that specific window but did not disclose that the cache had already changed once, earlier, for an unrelated reason).

**No correction to the subchunk-recovery mechanism, its tests, or the operational cache was needed or made.** The cache was not modified, restored, or normalized as part of producing this note — it was only inspected.

## 2026-08-03 — Phase 2: bounded closed-month Wikipedia subchunk recovery

**Why this changed.** The 2026-08-03 CTSH/GME PARTIAL regression traced to two mid-history full-month chunks returning HTTP 404 on both the first attempt and the bounded second pass, while a read-only diagnostic (`Live Signal Engine/Phase2 Failure Evidence/2026-08-03_CTSH_GME_Historical_Endpoint_PARTIAL/`) later showed the exact same requests succeeded cleanly on retry, as did every fixed 7-day subrange of each — consistent with transient/rate-limited server behavior on a per-request-shape basis, not a genuine data-availability gap. This adds a third, strictly bounded, last-resort recovery mechanism for exactly that failure pattern.

**What changed** (additive only -- no change to data selection, z-score methodology, cache acceptance rules, the earnings leg, the six locked research fields, or the locked 24-ticker universe):

- `week_aligned_subchunks()`, `attempt_closed_month_subchunk_recovery()`, `run_bounded_subchunk_recovery()` (new, `GST_Phase2_Wikipedia_Transport.py`): a fixed, calendar-aligned 7-day partition of a closed month that already failed both the first pass and the bounded second pass, one attempt per subchunk (never recursive, never bisected further), production-appropriate pacing (`SUBCHUNK_PACING_RANGE_S = (2.0, 5.0)`, matching the existing second pass), and independent per-month `SUBCHUNK_MAX_REQUESTS_PER_MONTH = 6` / `SUBCHUNK_MAX_WALL_CLOCK_S = 120.0` budgets on top of the run-level clock. Applies ONLY to closed months (`is_open_chunk()` gates it out for the open/current chunk, which remains `apply_recent_cache_fallback()`'s exclusive domain). Every subchunk response is validated through the SAME shared `validate_snapshot()` gate used everywhere else in this module (identity, duplicate dates, invalid pageviews, date-outside-range, content-hash, exact coverage through `required_data_end()` -- which structurally excludes any post-watermark observation). A subchunk that validates is cached immediately through the existing `write_chunk_to_cache()` path, keyed by its own boundaries -- never a synthesized whole-month entry, so a genuine partial recovery survives even when the overall month does not end up fully recovered. The overall recovery succeeds only when the union of successful subchunks exactly equals the full expected date set, with no duplicate/conflicting observation across subchunks; even one missing date fails the whole attempt closed.
- `_wiki_source_provenance()` (`GST_Phase2_DailyPanel.py`): additively recognizes a new `source="subchunk_salvage"` chunk-result tag, producing `wiki_source_mode="subchunk_salvage_only"` when it is the sole contributor (falls into the existing `"mixed"` bucket alongside any other source otherwise, unchanged logic).
- `GST_Phase2_DailyPanel.py` `main()`: wires `run_bounded_subchunk_recovery()` in as a third stage, running after the bounded second pass AND the recent-cache fallback, on whatever remains failed. Two new additive `COLUMN_ORDER` fields, `wiki_subchunk_recovery_attempted` / `wiki_subchunk_recovery_provenance_json`, record the full per-subchunk provenance (original failed interval, subchunk boundaries, response status, elapsed time, content hashes, retrieval timestamps, expected/observed date counts, recovery status, and budgets consumed) on every row where this mechanism was invoked, whether or not it ultimately succeeded -- `None`/`null` on every row where it never ran.

**Tests**: `test_phase2_wiki_subchunk_recovery.py` (new) -- complete recovery, one missing date, one failed subchunk, duplicate/conflicting dates across subchunks, invalid identity/hash detection, invalid pageview values, post-watermark observation rejection, open-month non-use, request-count exhaustion, wall-clock-budget exhaustion, 429/404 behavior, no recursive descent, correct cache writes (including no cache write on incomplete union), provenance/source-mode correctness, and a final byte-identical check on the real operational cache. Full deterministic Phase 2 suite (10 files) re-run in full: all passing, operational cache verified byte-identical before and after.

Only deterministic tests were run. No live network access, no operational-cache mutation, and the 24-ticker panel itself was not rerun.

## 2026-08-02 — Phase 2: preserve wiki source provenance end-to-end, fix article-identity gap in cache-union

**Why this changed.** The cache-union implementation above (fa172a1) computed detailed, per-chunk provenance (`attempt_cache_union_reconstruction()`'s return value) but it never reached the finalized panel row: `process_ticker()` logged only `source`/`status` per chunk and discarded the rest; `wiki_pending` (the struct carried into the second pass) didn't retain `chunk_results` at all; and `_finalize_wiki_row()` unconditionally wrote `wiki_source_mode="fresh"` regardless of what actually happened. A ticker fully recovered via cache-union reconstruction, or via a mix of cache/fetch/union, would show up in the panel output indistinguishable from a genuinely fresh network fetch.

**What changed** (additive only -- no change to data selection, z-score methodology, cache acceptance rules, retry behavior, budgets, or the six locked research fields):

- `_wiki_source_provenance()` (new, `GST_Phase2_DailyPanel.py`): derives final source provenance from the chunks that **actually contributed** rows (`status="ok"` and `source` in `{cache, fetch, cache_union_reconstruction}`) -- never hardcoded. Produces `wiki_source_mode` (`fresh_only` / `exact_cache_only` / `cache_union_only` / `mixed`, or `None` if nothing contributed -- never invented), `wiki_cache_union_used`, `wiki_cache_union_chunk_count`, and two deterministic (`sort_keys=True`, over already-sorted inputs) JSON fields: `wiki_source_components_json` and `wiki_cache_union_provenance_json` (contributing chunk keys, content hashes, and retrieval timestamps for every union-recovered chunk).
- `_finalize_wiki_row()` now takes a **required** `chunk_results` parameter (no default -- matches the existing `watermark_date` fail-closed pattern) and calls `_wiki_source_provenance()` instead of hardcoding `"fresh"`.
- `wiki_pending` now retains first-pass `chunk_results` (previously discarded), and `main()`'s second-pass loop merges them with a normalized view of the ticker's second-pass results (`source="fetch"` added -- second pass is always a live retry, never a cache/union hit) before finalizing, so provenance survives a chunk being queued, retried, and recovered.
- The existing `recent_last_known_good` fallback's own provenance (`wiki_status`, `wiki_source_mode`, and its other fields) is completely untouched -- still applied via the same `row.update(fallback_info["provenance"])` override, unchanged. Purely additively, `"recent_last_known_good"` is merged into `wiki_source_components_json` afterward, so a ticker recovered by the fallback still shows any OTHER chunks that contributed normally, without ever overriding the fallback's own authoritative labels.
- Fixed a related identity gap in `attempt_cache_union_reconstruction()`'s per-group hash-reverification: the full-group re-lookup used for recomputing a candidate group's stored hash filtered on `(ticker, chunk_start, chunk_end)` but **not** `configured_article_title` -- two different article mappings for the same ticker sharing an identical chunk-boundary key could have their rows silently mixed together during hash recomputation. Now filtered on all four fields.
- 9 required deterministic scenarios / 35 assertions added (`test_phase2_wiki_source_provenance.py`): union-only never labeled fresh, provenance survives CSV/DataFrame round-trip, mixed-source labeling with all components present, provenance survives a later successful second pass, `recent_last_known_good` unchanged, two genuinely separate cached chunk groups jointly reconstructing one interval with both represented in provenance, wall-clock independence with nondegenerate non-null z-scores, exact-snapshot vs. union-snapshot producing equal non-null z-scores (not merely equal daily rows), and differing article titles sharing a ticker/chunk boundary provably unable to interfere.
- `test_phase2_wiki_zscore_anchor.py` updated for `_finalize_wiki_row()`'s new required `chunk_results` parameter (mechanical signature update only, no behavioral change to that file's own assertions).

**Caught and fixed during test development, before this commit:** an early version of the new second-pass test called the real `run_bounded_second_pass()` with a fetch stub that returned a successful result, which -- exactly as the real code is supposed to -- triggered `write_chunk_to_cache()` against the real, global `wiki_transport.CACHE_PATH`, appending 30 fabricated rows to the actual operational `Live Signal Engine/Phase2_Wikipedia_Cache.csv`. Caught immediately via a before/after cache-hash mismatch; the 30 synthetic rows were identified precisely (a clean append at the file's tail, confirmed by the exact row-count delta -- no pre-existing row was overwritten) and removed, restoring the cache to its exact prior SHA-256. The test itself was then fixed to redirect `CACHE_PATH` to a temp file for its duration (the same pattern already used elsewhere in this suite), and the full suite was re-run to reconfirm a byte-identical cache hash before and after.

**Full deterministic suite: 291 assertions passing** (up from 256), across all 9 test files. No live-network test, no 24-ticker panel run in this pass. Operational cache confirmed byte-identical before/after the final suite run.

## 2026-08-02 — Phase 2: fix pull_start watermark propagation, add closed-interval cache-union reconstruction

**Why this changed.** Two follow-ups to the same-day anchor fix above, found while re-verifying the watermark's propagation end-to-end.

**1. `pull_start` was still wall-clock-derived.** `process_ticker()` computed `pull_start = anchor_date - timedelta(days=PULL_LOOKBACK_DAYS)` using `anchor_date = run_ts.date()` (wall-clock), not `watermark_date` -- the same class of bug just fixed for the z-score anchor itself. Since the effective data end is truncated to the watermark regardless, a wall-clock-derived `pull_start` silently shortens the effective lookback by exactly the watermark's lag whenever it lags wall-clock time. Fix: `pull_start = watermark_date - timedelta(days=PULL_LOOKBACK_DAYS)`. The request horizon/end-date passed to the transport (`anchor_date`, still wall-clock) is deliberately unchanged -- `get_ticker_wikipedia_daily()`/`required_data_end()` already truncate any chunk beyond the watermark, so this is harmless and out of scope. 4 required lag scenarios (0/1/2/3 days) added, 23 assertions total, in `test_phase2_wiki_pull_start.py` -- proves `pull_start` is fixed relative to `watermark_date` regardless of wall-clock date, the request horizon still varies with wall-clock (confirming it was deliberately left alone), a post-watermark observation has zero effect on the resulting z-score, and a missing/errored watermark still fails closed (zero network calls attempted).

**2. Closed-historical-interval cache-union reconstruction (new capability, not a bug fix).** The 2026-08-02 endpoint-failure diagnostis found that most of the 8 "genuine failure" tickers' failed chunks (see `COMPOSITE_SNAPSHOT_DESIGN_PROPOSAL_NOT_IMPLEMENTED.md`) were re-fetching calendar dates already fully, validly cached under a *different* rolling-window chunk-boundary key -- `cached_daily_rows_for_chunk()`/`validated_cache_hit()` key on an exact `(chunk_start, chunk_end)` match, so this coverage was invisible to the lookup that mattered. Implemented the proposal exactly as designed, conservatively:

- `attempt_cache_union_reconstruction()` (new, `GST_Phase2_Wikipedia_Transport.py`): on an exact-key cache miss for a **closed historical interval only** (never the open/current chunk -- gated by `is_open_chunk()` at the call site, live-first + the existing `recent_last_known_good` fallback there is completely unchanged), attempts a day-level union of already-validated cache rows for the same ticker + configured article, tried *before* any network request.
- Fails closed unless: every calendar date in the requested interval is present (no partial-coverage union ever accepted); every contributing row has `http_status == 200`, a genuinely nonnegative-integer `pageviews` value, and belongs to a chunk-group whose stored `content_hash` matches a hash recomputed from that group's own full row set (the same check `verify_cache_integrity()` runs, applied per candidate group -- a tampered/inconsistent group contributes nothing); two cached rows disagreeing on the same date's `pageviews` rejects the *whole* reconstruction (never averaged, never picked); every contributing date is independently re-checked against the watermark.
- Never writes the synthetic union back to the cache as though it were a real network response -- read-only.
- Explicit `cache_union_reconstruction` provenance recorded per recovered chunk: contributing `(chunk_start, chunk_end)` keys, contributing `content_hash` values, contributing `last_verified_utc` timestamps, reconstruction timestamp.
- 8 required scenarios / 19 assertions added in `test_phase2_wiki_cache_union.py`: complete-union acceptance, one-date-missing rejection, conflicting-value rejection, identity/hash rejection (three sub-cases: tampered hash, wrong article, non-200), watermark exclusion, current/open-month non-use (proven even when full day-level coverage exists under another key), zero-network-call recovery, and byte-identical daily values vs. an exact-boundary snapshot for the same interval.

**Full deterministic suite: 256 assertions passing** (up from 214), across all 8 test files. No live-network test, no 24-ticker panel run in this pass. Operational cache confirmed byte-identical before/after the full suite run.

## 2026-08-02 — Phase 2: anchor the wiki z-score on the measured watermark, not wall-clock time

**Why this changed.** A bounded 24-ticker regression on 2026-08-02 (commit
`50c4916`) came back PARTIAL with `wiki_zscore` 0/24, even though the
watermark mechanism (`e2d7d80`) and the completion gate (`50c4916`) both
worked correctly this run (watermark `status=ok`, `lag_days=1`; every row
`earnings_status=ok`). Root cause, confirmed via each affected row's
`wiki_note`: `_finalize_wiki_row()` in `GST_Phase2_DailyPanel.py` anchored
`compute_zscore_at_anchor()` on `pd.Timestamp(run_ts.date())` — the
script's real wall-clock run date — instead of the measured watermark
date. Since Wikipedia data is genuinely truncated at the watermark
(`required_data_end = min(chunk_end, watermark)`), anchoring one day past
it manufactured a 7-day gap to the nearest available week for 16/24
tickers, one day past the existing 6-day alignment tolerance in
`compute_zscore_at_anchor()` (unchanged, not touched by this fix).
Evidence preserved in `Live Signal Engine/Phase2 Failure Evidence/
2026-08-02_WatermarkAnchor_And_Endpoint_PARTIAL/`.

**What changed** (the anchor computation only; chunk boundaries, budgets,
retry counts, source hierarchy, the six locked research fields, and the
core z-score formula in `GST_FixedWindow_PerEvent_Canonical.py` are all
untouched):

- `_finalize_wiki_row(row, article, daily_rows, watermark_date)` — the
  `run_ts: datetime` parameter is replaced by a required `watermark_date:
  date` parameter (no default; matches this project's established
  "no implicit today" pattern). The function now raises `ValueError` if
  `watermark_date` is `None` — fail-closed, no wall-clock fallback.
- Added a defense-in-depth filter inside `_finalize_wiki_row()`: any
  `daily_rows` entry dated after `watermark_date` is excluded before the
  weekly series is assembled, independent of whatever upstream chunk
  truncation already did.
- Two new provenance columns: `wiki_zscore_anchor_date` (always equal to
  the watermark date on a finalized row) and `wiki_zscore_anchor_source`
  (currently always `"measured_watermark"`).
- All three call sites (`process_ticker()`'s first pass, and both
  finalization branches in `main()`'s second-pass/fallback loop) updated
  to pass `watermark_info["watermark_date"]` instead of a wall-clock
  timestamp.
- Added `test_phase2_wiki_zscore_anchor.py`: 8 required scenarios / 14
  assertions, covering the exact within-tolerance/over-tolerance
  boundary, wall-clock independence, post-watermark exclusion, and
  fail-closed behavior on a missing/errored watermark.
- Full deterministic suite re-run after this change: **214 assertions**
  passing across `test_phase2_wikipedia_transport.py` (79),
  `test_phase2_dailypanel_gate.py` (24),
  `test_phase2_wikipedia_recent_cache_fallback.py` (26),
  `test_phase2_wikipedia_watermark.py` (48),
  `test_phase2_wikipedia_equivalence_deterministic.py` (23), and the new
  `test_phase2_wiki_zscore_anchor.py` (14).

**Separately investigated, not fixed:** the same regression's 8/24
"genuine endpoint failure" tickers (ADBE, AMZN, BKR, CTSH, GME, LDOS,
NCLH, TSLA) were diagnosed read-only. No narrow implementation bug was
found — the existing `recent_last_known_good` fallback is correctly
scoped to the open month only and correctly does not apply to the
closed-month chunks that failed (October 2025, January 2026, July 2026),
and the open-month failures for CTSH/GME/NCLH have zero cached history to
fall back to. A forward-looking design proposal for reconstructing a
complete chunk from a day-level union of overlapping cached fetches
(rather than requiring an exact chunk-boundary cache key match) is
documented, **not implemented**, in
`COMPOSITE_SNAPSHOT_DESIGN_PROPOSAL_NOT_IMPLEMENTED.md` alongside the
evidence. No fallback logic was changed in this pass.

## 2026-08-01 — Phase 2: align completion gate with six-field contract

**Why this changed.** GitHub review of the watermark commits (`7fa1762`,
`e2d7d80`) found a real logic bug in the completion gate. The locked six
research fields are `gst_zscore`, `wiki_zscore`, `implied_volatility`,
`realized_vol`, `price`, `volume`; `days_to_nearest_earnings` is contextual
metadata, not one of them. `all_six_fields_clean` had drifted to require
all six fields **and** `days_to_nearest_earnings` non-null, and
`is_run_complete()` required `all_six_fields_clean=True` for every row.
Under that logic, the successful `46aec15` baseline -- which had all six
research fields 24/24 but legitimately found no upcoming earnings date for
four tickers (`earnings_status="ok"`, `days_to_nearest_earnings=None`) --
would have been incorrectly classified PARTIAL. A genuinely successful
"no earnings found" result is not a failure and must not block COMPLETE.

**What changed** (completion-gate logic only; watermark algorithm,
Wikipedia transport, z-score formulas, ticker universe, retry policy,
budgets, option selection, and historical data are all untouched):

- `all_six_fields_clean` (both computation sites: `process_ticker()` and
  the post-second-pass/fallback finalization loop in `main()`) now covers
  **only** the six locked research fields.
- `is_run_complete()` separately and independently requires
  `earnings_status == "ok"` for every row -- fail-closed: `"error"` or
  `"timeout"` still block COMPLETE, but a null `days_to_nearest_earnings`
  alongside `earnings_status="ok"` does not. No earnings date is ever
  fabricated.
- `write_completion_marker()` gains two additive observability fields,
  `earnings_lookup_ok_count` and `days_to_nearest_earnings_nonnull_count`,
  so a successful-null-earnings run is visibly distinguishable from an
  earnings-lookup failure. No existing marker field was removed or renamed.
- Corrected the RUN SUMMARY log line, which previously read "Clean (all 6
  fields + earnings)" -- now "Clean (six locked research fields only)"
  with a separate "Earnings lookup ok (date may still be null)" count.
- Added 7 new deterministic assertions to
  `test_phase2_dailypanel_gate.py` (`earnings-a` through `earnings-d`,
  `marker-e` x3) proving: six fields clean + `earnings_status="ok"` +
  null date is COMPLETE-eligible; `earnings_status="error"` or `"timeout"`
  forces PARTIAL even with six clean fields; a missing core field still
  forces PARTIAL independent of earnings status; and the new marker
  counters correctly distinguish a successful-null-earnings row from a
  lookup-failure row.
- Full deterministic suite re-run after this change: 200 assertions
  passing across `test_phase2_wikipedia_transport.py` (79),
  `test_phase2_dailypanel_gate.py` (24),
  `test_phase2_wikipedia_recent_cache_fallback.py` (26),
  `test_phase2_wikipedia_watermark.py` (48), and
  `test_phase2_wikipedia_equivalence_deterministic.py` (23). No live
  network test was run in this pass; the 24-ticker panel was not run.

## 2026-08-01 — Phase 2: measure and enforce a Wikimedia publication watermark

**Why this changed.** The 2026-08-01 24-ticker regression (the PR's
operational merge gate) came back PARTIAL: `wiki_zscore` 0/24. Root cause,
independently confirmed via direct probe of both the per-article and the
site-wide aggregate Wikipedia endpoints: this run landed ~3.5 hours into
August 1, immediately after July closed, and Wikipedia had not yet
published July 31 for any article. The fixed "coverage through `today-1`"
assumption -- previously baked into `effective_open_chunk_data_end()` and
applied only to the calendar-open month -- was proven false on a real,
measured day, and it never protected CLOSED months at all (a closed
month's own last day can be just as unpublished). Evidence preserved in
`Live Signal Engine/Phase2 Failure Evidence/2026-08-01_Wikipedia_SourceWatermark_Lag2/`.

**Phase B feasibility probe** (read-only, before any implementation):
tested the site-wide aggregate pageviews endpoint
(`.../pageviews/aggregate/en.wikipedia.org/all-access/user/daily/{start}/{end}`,
requiring `YYYYMMDD` + a trailing `"00"` hour component -- a different
format than the per-article endpoint) for July 31 and July 30
individually. Result: clean, non-flaky, reproducible --  July 30 returned
HTTP 200 consistently, July 31 returned HTTP 404 consistently (confirmed
twice, 2 seconds apart), and a 3-day range query correctly omitted the
unavailable trailing date rather than erroring the whole range. This
endpoint does NOT exhibit the per-article/per-request-shape flakiness
documented elsewhere in this investigation, making it a reliable
foundation for a watermark. Evidence:
`aggregate_endpoint_probe_evidence.csv`.

**What changed** (none of it touches the Wikipedia z-score formula, GST
methodology, the ticker universe, any option/price/volume field, the six
required research-field meanings, historical datasets, or existing
PARTIAL evidence):

- **`resolve_wiki_data_watermark()`** (new): resolves the SINGLE run-level
  Wikipedia data watermark exactly once, at run start, before any ticker
  is processed. Probes candidates `anchor_date-1` through `anchor_date-3`
  (`MAX_ACCEPTABLE_WIKI_LAG_DAYS`, locked) newest-to-oldest against the
  aggregate endpoint. A 404 gets exactly one bounded confirmation re-probe
  before moving to the next-older candidate. A 429 honors a bounded
  `Retry-After` and retries the SAME candidate (never walks back on a rate
  limit). Any other ambiguous outcome (exception, non-404/429 HTTP status,
  malformed response) FAILS THE WATERMARK CLOSED immediately -- never
  interpreted as "unpublished". No watermark within the lag budget leaves
  the run's Wikipedia leg entirely unresolved (PARTIAL), never guessed.
- **`required_data_end(chunk_end, watermark) = min(chunk_end, watermark)`**
  replaces `effective_open_chunk_data_end()` and is now applied UNIFORMLY
  to every chunk, open or closed alike -- the exact fix for the incident,
  since the old code only ever capped the open month.
- **`today` removed from the transport module's public API entirely**,
  replaced by `watermark` throughout: `validate_snapshot()`,
  `validated_cache_hit()`, `get_ticker_wikipedia_daily()`,
  `run_bounded_second_pass()` (now a required parameter, no silent
  default), `evaluate_recent_cache_fallback()`/`apply_recent_cache_fallback()`
  (the fallback's "current chunk" gate is now `is_open_chunk(chunk_start,
  chunk_end, watermark)` -- the watermark, not the calendar, defines the
  frontier). A fresh fetch now requests ONLY `chunk_start..required_data_end`
  -- never a date beyond the measured watermark, and never the chunk's
  full nominal end.
- **Rollover behavior now generalizes correctly**: a cache snapshot valid
  against an earlier, smaller watermark is rejected (`incomplete_coverage`)
  and refetched once the watermark advances -- for BOTH open and closed
  chunks, closing the exact gap that caused the 2026-08-01 PARTIAL (23 of
  24 tickers' cached July snapshots, valid through July 30, will now be
  accepted directly once the watermark reaches July 30, and correctly
  refreshed once it reaches July 31).
- **7 new additive, run-level provenance columns** (identical across every
  row of a run, never recomputed per ticker): `wiki_data_watermark_date`,
  `wiki_data_lag_days`, `wiki_watermark_status`,
  `wiki_watermark_retrieved_at_utc`, `wiki_watermark_source_url`,
  `wiki_watermark_http_status`, `wiki_required_data_end`. The same
  metadata is added to the completion marker
  (`wiki_data_watermark` object).
- **`is_run_complete()`** now requires `watermark_status == "ok"` in
  addition to its existing checks -- a run cannot be COMPLETE without a
  valid measured watermark, and a lag exceeding `MAX_ACCEPTABLE_WIKI_LAG_DAYS`
  structurally can never reach `watermark_status == "ok"` in the first
  place, so it can never produce COMPLETE either.
- `GST_Phase2_DailyPanel.py`'s `main()` resolves the watermark once,
  before the ticker loop; if resolution fails, every ticker's wiki leg is
  marked `incomplete_watermark_unavailable` and skipped entirely (fail
  closed, no network request, no guess) while the other five fields still
  process normally.

**Tests**: 5 files updated for the `today` -> `watermark` API change (all
prior tests re-verified passing under the new semantics, several fixed
where their setup's premise no longer applied under the unified
watermark-driven model -- e.g. a cache exactly satisfying the current
watermark is now legitimately reused rather than always refetched). New
coverage: `test_phase2_wikipedia_watermark.py` (48 assertions, tests 1-12:
lag 1/2/3 resolution, no-data-within-max-lag, 429/Retry-After, fail-closed
on ambiguous errors, request truncated exactly to the watermark, no
request for chunks entirely beyond it, July-rollover cache valid/rejected
across a watermark advance, exact coverage enforcement, identical
provenance across rows); `test_phase2_wikipedia_equivalence_deterministic.py`
gains a watermark-truncation test (13: a manually-truncated frozen fixture
exactly matches the pipeline's own truncation); `test_phase2_dailypanel_gate.py`
gains tests 15/16 (no COMPLETE without a valid watermark; lag > max cannot
produce COMPLETE). Total deterministic suite: 193 assertions across 5
files, all passing; operational cache confirmed byte-identical before and
after.

**Live diagnostic** (the only live check run before this commit, per
instruction -- no full panel): `diagnose_wiki_watermark_only.py` exercises
only `resolve_wiki_data_watermark()` against the real aggregate endpoint.
Result at commit time: `status=ok`, `watermark_date=2026-07-31`,
`lag_days=1` -- Wikipedia's publication lag had already recovered to 1 day
by the time of this commit (confirming the earlier 2-day lag was
genuinely transient, exactly as classified throughout this investigation).

**Remaining limitations, disclosed:** the watermark is resolved from the
SITE-WIDE aggregate endpoint, which is a proxy for per-article
availability, not a per-article guarantee -- an individual article could
theoretically still lag behind the aggregate signal (not observed in this
investigation). `MAX_ACCEPTABLE_WIKI_LAG_DAYS=3` is a locked policy
constant, not derived; a genuinely longer Wikipedia-side outage would
still correctly produce PARTIAL rather than an incorrect COMPLETE, but
requires a deliberate policy change (not an automatic escalation) to
extend. No new 24-ticker regression has been run under this watermark
implementation -- per instruction, none was authorized this pass.

## 2026-07-31 — Phase 2 follow-up: close test-isolation and edge-case validation gaps

Four further review findings closed on top of the prior corrective commit:

1. **Real no-observations-yet orchestration.** The real Wikipedia worker
   returns `status="empty"` (not `"ok"`) for a zero-item HTTP-200 response
   -- so the prior fix (which only classified `no_observations_expected_yet`
   AFTER a fetch, and only when `status=="ok"`) could still queue the very
   first day of a new open month as a genuine failure forever, since that
   day's request will always come back "empty". Fixed prospectively:
   `get_ticker_wikipedia_daily()` now checks, BEFORE making any request for
   an open chunk, whether `effective_data_end < chunk_start` (nothing in
   range could possibly be published yet); if so, no network call is made,
   `chunk_results` gets `source="not_requested"` /
   `status="no_observations_expected_yet"` with zero network/sleep time,
   nothing is cached, and no failed chunk is produced. Verified with an
   orchestration-level test using a `fetch_fn` that raises if called at
   all, plus a run-completeness test showing the run can still be COMPLETE
   using the preceding available dates.
2. **Deterministic equivalence test isolated from the operational cache.**
   `test_phase2_wikipedia_equivalence_deterministic.py`'s fixture-backed
   chunks still called the real `write_chunk_to_cache()` against the
   module-global `CACHE_PATH` -- using the real ticker symbols AAPL/AMZN,
   an unredirected run could pollute the actual operational
   `Phase2_Wikipedia_Cache.csv`. Fixed: `CACHE_PATH` is now redirected to a
   temporary file for the test's duration, restored in `finally`, and the
   run explicitly verifies the operational cache is byte-identical before
   and after (or confirms none was created if it didn't exist). No
   deterministic test may mutate operational data.
3. **Unambiguous live-smoke-test exit codes.** `test_phase2_wikipedia_equivalence.py`
   (the optional live diagnostic) now exits 0 only if every tested ticker
   PASSes, 1 if any ticker FAILs, 2 if none FAIL but at least one is
   INCONCLUSIVE -- extracted into a pure `decide_exit_code()` function,
   directly unit-tested with zero network calls. Final PASS/INCONCLUSIVE/
   FAIL counts are printed. Explicitly documented as an optional live
   diagnostic, not a deterministic CI gate.
4. **Genuinely integral pageviews.** `validate_snapshot()` used
   `int(value)`, which silently truncates `1.5` to `1` and silently
   accepts `True` as `1`. New `_is_valid_nonnegative_integer_pageviews()`
   accepts real integers and integer-valued numeric representations (`5.0`,
   `"5"`, `"5.0"`), and rejects fractional values, NaN, +/-infinity,
   booleans, and negatives outright -- never silently coerced. Tested for
   every accepted and rejected case.

None of this touches request behavior, retries, budgets, chunk boundaries,
fallback rules, z-score methodology, field definitions, ticker universe,
or completeness policy. Full existing deterministic suite (133 assertions
across 4 files) passes; operational cache confirmed byte-identical before
and after the full suite run; no orphan process from any test (two
unrelated `llm_pull.py` processes observed on the machine were
independently confirmed, by command line and parent PID, to belong to a
different script entirely).

## 2026-07-31 — Phase 2 corrective commit: cache completeness, identity, equivalence, and deadline gates

Following a GitHub review of the two prior commits, five correctness gaps
were closed. None of it touches request behavior, retries, budgets, chunk
boundaries, fallback rules, z-score methodology, field definitions, ticker
universe, or completeness policy -- confirmed by the full existing
deterministic suite passing unchanged, plus new tests for each fix.

1. **Shared validation for every fresh response and every cache hit.**
   New `validate_snapshot()` is now the SINGLE gate used before (a) writing
   a fresh HTTP-200 response to cache, (b) treating a fresh response as
   successful, (c) reusing any closed-month cache entry (via new
   `validated_cache_hit()`), and (d) accepting the open-month
   RECENT_LAST_KNOWN_GOOD fallback (`evaluate_recent_cache_fallback()` now
   delegates to it instead of duplicating checks). Enforces: configured
   ticker/article identity, one content hash per snapshot with successful
   recomputation, no duplicate dates, parseable dates, non-negative integer
   pageviews, no dates outside the requested range, and EXACT expected
   date coverage (closed chunk: every date through chunk_end; open chunk:
   every date through `min(chunk_end, today-1)`). A nonempty HTTP 200 with
   missing required dates is classified `incomplete_coverage`, never
   cached, never treated as success, and enters the bounded second pass
   like any other failure -- no zero-filling, ever. If today is the very
   start of a new open month (no date could legitimately be published
   yet), an empty response is explicitly classified
   `no_observations_expected_yet`, not fabricated and not an error.
   **Rollover case fixed and tested**: a month fetched while still open
   (e.g. July 31, covering only through July 30) is correctly rejected as
   `incomplete_coverage` once that month closes and requires its own final
   day too -- it is never silently reused as a complete closed month; the
   orchestration falls through to a fresh fetch instead. `verify_cache_integrity()`
   -- previously exercised only by tests, never called from production --
   is now also invoked once per `get_ticker_wikipedia_daily()` call as a
   whole-cache sanity pass, on top of `validate_snapshot()`'s own per-read
   hash re-verification, so schema-valid-but-corrupted cache content can
   no longer bypass validation.
2. **Split the scientific-equivalence gate.** The prior single test
   checked only overlapping values (so it could pass even with different
   date sets between the two routes) and treated `probe_inconclusive` as
   acceptable -- not equivalence. Now two separate files:
   - `test_phase2_wikipedia_equivalence_deterministic.py` (Section A,
     mandatory): frozen, provenance-documented fixtures for AAPL and AMZN
     (`Live Signal Engine/Phase2_Wikipedia_Equivalence_Fixtures/`, captured
     once from the real direct-response route with exact dates, values,
     retrieval timestamp, article identity, source URL, and content hash
     recorded and self-verified). Requires EXACT date-set equality (not
     overlap), exact value equality for every date, and z-score match
     within 1e-9. No live-network dependency at test-run time. No
     unavailable/inconclusive outcome is possible -- this test only ever
     PASSES or FAILS.
   - `test_phase2_wikipedia_equivalence.py` (Section B, optional,
     observational): live smoke test against the real direct route, now
     reporting one of exactly three verdicts per ticker -- PASS (identical
     date sets, exact values, z-score within tolerance), INCONCLUSIVE
     (source unavailable or date sets differ -- never counted as PASS,
     regardless of how an independent re-probe classifies the gap), or
     FAIL (a true value mismatch on a date both routes returned complete
     data for). Exit code reflects only true FAILUREs; INCONCLUSIVE never
     blocks anything. Explicitly documented as not substituting for
     Section A.
3. **Cache-identity honesty.** The production cache-write path has never
   independently resolved or verified a canonical article title or
   Wikipedia page ID -- no identity registry exists for the 24-ticker
   universe, and `canonical_title`/`page_id` are always written blank.
   Prior docstring wording that implied stronger verification was
   happening has been corrected: `evaluate_recent_cache_fallback()` now
   states plainly that only ticker + configured article title are actually
   enforced (via `validate_snapshot()`), and that `canonical_title`/
   `page_id` are optional, best-effort checks that only fire if a caller
   explicitly supplies them AND a stored value happens to be non-blank
   (which production never populates today). The schema columns remain,
   for a future registry, but nothing claims they're checked when they
   aren't.
4. **Genuinely bounded time budget.** `run_bounded_second_pass()`
   previously checked remaining budget only BEFORE the jitter/Retry-After
   wait, then could launch a full-`chunk_timeout_s` request regardless of
   how little budget the wait itself had consumed. Now: remaining budget
   is recomputed AFTER any wait; a request is never launched once usable
   budget (<1s) is gone; the subprocess timeout passed to `fetch_fn` is
   capped to whatever budget actually remains, never the full
   `chunk_timeout_s`. The same discipline now applies BETWEEN first-pass
   chunks too: `get_ticker_wikipedia_daily()` accepts an optional
   `remaining_budget_s`, and `GST_Phase2_DailyPanel.py`'s ticker loop
   computes and passes the actual remaining total-run budget before each
   ticker's Wikipedia leg starts, so one late ticker's first pass cannot
   materially eat into the deadline meant for the tickers after it.
   Verified with deterministic mock-based tests (budget capping and
   exhaustion, both between second-pass items and between first-pass
   chunks) AND one real-subprocess test (a genuinely-hanging worker under
   a tiny real budget, proving the capped value -- not just any timeout
   value -- actually bounds execution end-to-end, with no orphan process
   left behind).
5. **Corrected cache-persistence wording.** `Phase2_Wikipedia_Cache.csv`
   was described as "repository-committed" while actually being untracked
   and deliberately excluded from both prior commits. Corrected: it is
   persistent ACROSS LOCAL RUNS on the same machine (atomic writes,
   accumulates over time), not currently repository-committed; a future
   unattended workflow (e.g. GitHub Actions) must explicitly persist it
   itself; the first cache intended for repository commit is the one
   produced by a validated COMPLETE 24/24 regression, reserved for
   Commit 3; automation is not ready until persistence on a clean runner
   is actually verified, not merely designed for. The volatile
   partial-run cache accumulated locally during this branch's testing is
   still not committed by this corrective commit either.

**Tests**: full existing 26-test deterministic suite (13 transport + 2
completeness-gate + 11 fallback) still passes unchanged after every fix
above, plus new coverage: 1 rollover-case test, 1
no-observations-expected-yet test, 2 tiny-budget tests (mock-based, second
pass and first pass), 1 real-subprocess tiny-budget test (proves no
overshoot, no orphan process), and the 2-ticker deterministic
scientific-equivalence test (Section A). Total: 33 assertions-worth of new
coverage across `test_phase2_wikipedia_transport.py`, plus 3 existing
fallback-test assertions updated to match `validate_snapshot()`'s
consolidated rejection-reason categories (no behavior change, only
matching the now-shared error-category names).

**Not run as part of this commit's test gate** (by instruction): another
24-ticker panel, or anything depending on current Wikipedia availability
(Section B, the live smoke test, is optional/observational and was not
executed as a precondition for this commit).

## 2026-07-31 — Phase 2 Wikipedia transport rewrite: deterministic chunking, persistent cache, bounded retry, process isolation, recent-cache fallback

**Why this changed.** The 2026-07-30 run-3 safeguards (below) bounded the
Wikipedia leg per-ticker but did not fix its underlying transport. A
subsequent investigation (preserved in `Live Signal Engine/Phase2 Failure
Evidence/2026-07-30_AMZN_Wikipedia_180s/`) found AMZN repeatedly timing out
under the old recursive-bisection design. Direct evidence: real network
time across an entire failed 180s attempt was under 3 seconds; the rest was
the old code's own mandatory 10s+20s+30s=60s retry-wait schedule, paid once
per HTTP 404 encountered, with no caching, so successful sub-ranges were
re-fetched from scratch on every run. A separate deterministic test also
proved the existing daemon-thread timeout wrapper (`run_bounded()`) returns
control to the caller while the timed-out call keeps running in the
background -- "fail-closed" described the orchestration's exit, not a
guarantee the underlying worker actually stopped.

**What changed** (new module `GST_Phase2_Wikipedia_Transport.py`, isolated
from the shared `GST_Wikipedia_Pageviews_Pull.py` used elsewhere --
confirmed unmodified). None of it touches the Wikipedia z-score formula,
any of the six locked scientific field definitions, the 24-ticker universe,
GST collection, option selection, implied volatility, realized volatility,
price, volume, or earnings-date methodology -- confirmed by diff review and
by a dedicated scientific-equivalence test (below):

- **Deterministic calendar-month chunking** (`calendar_month_chunks()`)
  replacing recursive, data-dependent bisection. The exact requested
  start/end dates are preserved; interior chunks run full calendar months.
  Deterministic boundaries make chunks reliably cacheable, unlike
  recursively-computed bisection midpoints.
- **Persistent, repository-committed, human-auditable CSV cache**
  (`Live Signal Engine/Phase2_Wikipedia_Cache.csv`, 14 columns: ticker,
  configured/canonical article title, page ID, chunk bounds, date,
  pageviews, source URL, HTTP status, first-retrieved/last-verified UTC
  timestamps, schema version, content hash). Closed months are cached and
  reused; the open/current month is always refreshed. Atomic writes
  (temp file + `os.replace`). HTTP 404 is never cached as a legitimate
  zero-view period; missing dates stay explicitly missing, never
  zero-filled. Cache corruption (missing columns, schema mismatch, hash
  mismatch) is detected and treated as a source failure, never silently
  coerced.
- **Bounded second-pass retry queue**: one attempt per chunk during normal
  processing; failures queue instead of sleeping inline; after all 24
  tickers' first passes finish, each failed chunk gets exactly one bounded
  retry with short jitter (2-5s) for ordinary failures, honoring a real
  `Retry-After` header (capped at 30s) for 429s. No recursive splitting of
  a still-failing chunk. Explicitly NOT the old 10s+20s+30s schedule.
- **Genuinely killable subprocess isolation** for the Wikipedia leg
  (`run_process_bounded()`, Windows-safe `multiprocessing` spawn context):
  on timeout, terminate() then kill() if needed, then join() to actually
  reap the child before the parent continues. Proven by a deterministic
  test that spawns a real, deliberately-hanging worker and verifies via
  `os.kill(pid, 0)` that no process with that PID survives. **Scope
  disclosure**: this isolation applies to the Wikipedia leg only -- GST,
  earnings, price-history, and IV still use the older daemon-thread
  `run_bounded()` wrapper, which does not guarantee a timed-out call
  actually stops. Converting every leg would be a substantially larger
  rewrite than this pass covers.
- **Run-level fail-closed completeness**: a failed/isolated ticker no
  longer discards other tickers' rows. `is_run_complete()` (pulled out as
  a directly unit-tested pure function) requires the loop itself reported
  COMPLETE, exactly the expected unique ticker count, every row's six
  required fields complete, and every timestamp parseable -- a PARTIAL run
  can never be mistaken for COMPLETE.
- **RECENT_LAST_KNOWN_GOOD fallback** (approved as a narrow, strictly-bounded
  addition, not a general staleness tolerance): for the current/open month
  ONLY, after both the fresh attempt and the one bounded second-pass
  attempt have failed, a persisted cache snapshot may stand in if -- and
  only if -- it originated from a real HTTP 200, its content hash verifies,
  its configured article title matches, it has no duplicate dates, it
  covers every date through a lag-adjusted effective data-end date (capped
  at yesterday, since Wikipedia's own same-day pageview count is never
  complete yet regardless of any transient failure), and it was verified
  within the last 24 hours. Read-only evaluation -- never writes to cache,
  so a failed refresh can never overwrite a valid prior snapshot, and using
  the fallback never resets that snapshot's own age. Provenance fields
  (`wiki_source_mode`, `wiki_fresh_request_failed`,
  `wiki_fresh_failure_http_status`, `wiki_fallback_retrieved_at_utc`,
  `wiki_cache_age_hours`, `wiki_effective_data_end`,
  `wiki_cache_content_hash`) preserve the ORIGINAL retrieval timestamp --
  a fallback-served value is never mislabeled as freshly retrieved.
- **Observational HTTP-status/Retry-After logging** (2026-07-31, purely
  additive): chunk-level diagnostic log lines and `chunk_results` now
  surface the raw numeric HTTP status and `Retry-After` header for both
  the fresh attempt and the bounded second-pass attempt. No request,
  retry, timing, budget, chunk-boundary, fallback, or completeness
  behavior changed -- confirmed by a dedicated test
  (`test_http_status_retry_after_logging_is_purely_additive`) and by the
  full existing suite (26 prior tests) passing unchanged before and after.

**Tests** (all passing, run directly, no external framework): 13
deterministic transport-module tests (`test_phase2_wikipedia_transport.py`,
covering full success, 404-then-recovery, repeated 404, 429/Retry-After,
timeout, real process termination, malformed response, cache corruption,
atomic-write interruption, cache resume, open-month refresh, no
zero-filling, duplicate-date prevention) plus the purely-additive logging
test; 2 run-level completeness-gate tests
(`test_phase2_dailypanel_gate.py`, tests 14-15: the final gate, and PARTIAL
never nameable COMPLETE); 11 RECENT_LAST_KNOWN_GOOD fallback tests
(`test_phase2_wikipedia_recent_cache_fallback.py`: fresh-preferred, valid
fallback used, stale/incomplete/mismatched/corrupt/duplicate cache
rejected, no recursive re-use resetting the clock, failed refresh never
overwrites cache, provenance/timestamp preserved, fallback z-score exactly
matches the original successful response's).

**Scientific-equivalence test** (`test_phase2_wikipedia_equivalence.py`,
AAPL and AMZN): direct full-window response vs. monthly-chunk-assembled
response (including the fallback where applicable) -- every overlapping
date/pageview value matched exactly (300/300 both tickers), and the wiki
z-score field agreed within tolerance for both.

**AMZN-only validation** (`validate_amzn_wiki_only.py`): under live source
conditions where AMZN's July 2026 chunk 404'd on both fresh attempts, the
RECENT_LAST_KNOWN_GOOD fallback correctly used an 11.2-hour-old, fully
gated snapshot; all 300 observations assembled; the resulting field matched
the direct-response calculation exactly; status was correctly
`complete_recent_cache_fallback`, not `fresh`; no child process remained.

**24-ticker regression (2026-07-31): PARTIAL, not COMPLETE.** 2634.8s
(43.9 min), exit code 1, no automatic restart. 24/24 unique tickers, every
non-wiki required field 100% complete (0 nulls across `gst_zscore`,
`implied_volatility`, `realized_vol`, `price`, `volume`). The `wiki_zscore`
field completed for only 12/24 tickers -- 25 calendar-month chunks across
12 tickers failed both the fresh attempt and the bounded second pass.
Evidence preserved in `Live Signal Engine/Phase2 Failure Evidence/
2026-07-31_TransportRewrite_12of24_Regression/` (full failure matrix,
root-cause analysis, preserved checkpoint/marker/logs).

The evidence strongly supports transient, query-specific Wikipedia API
failures, not a defect in this rewrite: failures were scattered across 9
calendar months with no concentration near the most recent data (11/12
affected tickers' open/current month succeeded); a live re-probe of 6
sampled failures recovered 5 within minutes; a minimal single-day
availability probe (AMZN vs. AAPL, a control that fully succeeded in this
same run) showed non-monotonic success/failure on adjacent individual
days for both articles, not a clean recency cutoff. CDN or edge-cache
inconsistency is a possible mechanism for this transience -- it is **not**
confirmed; no lower-level Wikimedia-side diagnostic evidence was available
to verify it. The RECENT_LAST_KNOWN_GOOD fallback correctly stayed out of
scope for the 24 closed-month failures (by design) and correctly rejected
the one open-month failure it did evaluate (NCLH, no prior snapshot
existed).

**This PARTIAL regression validates the fail-closed transport behavior --
not 24/24 dataset completeness. No trading or substantive research
conclusion may use this PARTIAL output.** A disclosed logging gap (the 25
failures were recorded by status category, not raw numeric HTTP code, for
that specific run) is closed prospectively by the observational logging
addition above; it does not retroactively change the classification of
that run's failures, independently confirmed HTTP 404 via a sampled spot
re-probe.

**Remaining limitations, disclosed:** GST/earnings/price-history/IV legs
still use the older daemon-thread mechanism, not process isolation. The
RECENT_LAST_KNOWN_GOOD fallback only ever applies to the current/open
month -- closed-month failures under elevated source instability have no
recovery path in this design. The fallback's effective-data-end check
assumes a fixed 1-day Wikipedia publish lag and requires an exact match;
on a day where the true lag is 2+ days, an otherwise-valid snapshot could
be spuriously rejected -- not observed in the 2026-07-31 regression (whose
one open-month failure was rejected for an unrelated reason), but a
plausible edge case, not fixed in this pass. Commit 3 (a new COMPLETE
24/24 regression) is reserved for a future run under calmer source
conditions.

## 2026-07-30 — Phase 2 run-3: duration correction, operational safeguards, and a passing bounded run

No CHANGELOG.md existed in this repo before this entry.

**Correction to an earlier (informal) hypothesis:** after run 3's first
attempt (2026-07-27) ran for `real 365m3.843s` and produced a completely
empty `phase2_run3.log`, an unbounded yfinance hang was floated as the likely
cause. That was wrong to assert without doing the arithmetic first, and the
arithmetic was done before writing any code this pass, not after:

- **GST leg** (this script's scoped 429 backoff): `TrendReq`'s own
  `timeout=(30, 60)` bounds each of 5 attempts at ~90s before erroring, then
  sleeps up to `backoff+jitter` (28/48/78/108/138s across attempts 1-5).
  Fully-adversarial worst case: `sum(90+28, 90+48, 90+78, 90+108, 90+138) =
  850s` (14.2 min) per ticker -- bounded, and not smaller than the *old*
  flat-60s schedule's own worst case (750s) once the request-timeout
  dimension is included on every attempt.
- **Wikipedia leg** (`GST_Wikipedia_Pageviews_Pull.py`, not modified by this
  entry): `_fetch_chunk()` retries 429/404 up to 4 attempts (10/20/30s waits,
  ~30s timeout each -> up to 180s per chunk), and `_fetch_with_bisection()`
  recurses to `MIN_BISECT_DAYS=45`. For this script's single 300-day pull,
  the bisection tree (300→150→75→~37) makes up to `1+2+4+8 = 15` chunk calls
  if every one fails: **2700s (45 minutes) worst case for a single ticker's
  Wikipedia leg alone** -- true before today, unrelated to the GST change,
  and large enough on its own to matter.
- **yfinance 1.5.1** (installed version, read directly, not assumed):
  `yfinance/data.py`'s `_make_request()` defaults to `timeout=30` per
  underlying HTTP call, and `YfConfig.network.retries` defaults to `0` (no
  internal retry-multiplication). Calls were already bounded by yfinance's
  own defaults -- an initial assumption that they had no timeout at all was
  incorrect.
- Summing a fully-adversarial per-ticker worst case (GST 850s + Wiki 2700s +
  ~270s for earnings/price/IV) × 24 tickers ≈ **1528 minutes (~25.5 hours)**.
  The observed 365-minute duration is only ~24% of that ceiling --
  comfortably explainable by ordinary (if unlucky) bounded retry/bisection
  behavior, especially via the Wikipedia leg. An unbounded hang is not
  required to explain it, and was not assumed going forward.

**What was added** (none of it touches the six field definitions, the
24-ticker universe, any z-score methodology, or the option-contract-selection
rule -- confirmed by diff review before and after):

- Line-buffered, explicitly-flushed stdout (`sys.stdout.reconfigure(...,
  line_buffering=True)` + a `log()` helper using `print(..., flush=True)`) --
  the empty 2026-07-27 log was itself caused by fully-buffered output on a
  redirected, non-TTY stdout combined with a process that never reached a
  normal exit to flush it.
- Explicit START/DONE logging for every source leg (earnings, price
  history, realized vol, IV/options, GST, Wikipedia), every ticker.
- `run_bounded()`: a reusable wrapper that runs any call in a thread and
  waits at most a configured timeout, independent of whether the callee (or
  any library it uses) honors its own `timeout=` parameter.
  **Caught a real bug via the mandated pre-run test, not assumed to work**:
  the first version used `concurrent.futures.ThreadPoolExecutor`, which
  returned promptly from `run_bounded()` on a timeout, but
  `concurrent.futures.thread` registers a process-wide `atexit` hook that
  joins *every* worker thread any `ThreadPoolExecutor` ever created --
  including abandoned ones -- so the whole process would hang at exit
  waiting for a genuinely-stuck call, exactly the failure mode this
  safeguard exists to prevent. Fixed by switching to a plain daemon
  `threading.Thread` (daemon threads are never joined at interpreter exit).
  Verified with two tests before trusting it: (1) `run_bounded()` in
  isolation against an injected 9999s sleep with a 2s budget -- returned in
  2.02s both before and after the fix, but the *process* only exited
  cleanly after the fix (before the fix, the process hung until an outer
  `timeout` wrapper killed it); (2) a full `process_ticker("AAPL")` call
  with a 9999s delay injected into the `price_history` leg specifically
  (via `GST_PHASE2_INJECT_SLOW_TICKER`/`GST_PHASE2_INJECT_SLOW_LEG` env
  vars) -- `price_history_status` correctly recorded `"timeout"` after
  ~45s, the other four legs completed normally with real values (including
  a real GST 429 retry that resolved on its own), and the process exited
  with code 0 on its own.
- `GST_TICKER_BUDGET_S=480s` and `WIKI_TICKER_BUDGET_S=90s`: documented
  cumulative caps per ticker, on top of (not replacing) each leg's existing
  per-attempt timeout/retry/bisection limits. Verified live during the real
  run below: BKR and GME both hit real Wikipedia bisection (visible in
  `phase2_run3.log` as `"...failed -- bisecting at..."`, from the
  unmodified Wikipedia module), taking 61.7s and 61.5s respectively --
  comfortably under the 90s cap, both resolved successfully.
- `PER_TICKER_WALL_BUDGET_S=900s` and `TOTAL_RUN_BUDGET_S=2700s` (45 min):
  checked between tickers; on exhaustion the checkpoint already written is
  preserved, the next (not-yet-started) ticker is recorded as active, and
  the process exits with code 1 without restarting. Verified with a
  monkeypatched 5-second total budget against 3 real tickers: exited code 1
  after 2 tickers, checkpoint file contained exactly those 2 rows, no file
  was written under the completed-run naming convention, and the
  completion marker correctly read `"status": "PARTIAL"`,
  `"active_ticker_when_stopped": "ADBE"`.
- An atomic (write-temp-then-`os.replace`) checkpoint file after every
  ticker, named
  `GST_Phase2_DailyPanel_TestRun_<date>_run3_CHECKPOINT_PARTIAL.csv` --
  deliberately never reused as the final filename, so a partial file can
  never be mistaken for a completed panel.
- A JSON completion marker
  (`GST_Phase2_DailyPanel_TestRun_<date>_run3_COMPLETION_MARKER.json`) with
  row/unique-ticker counts, per-field completeness, per-source failure
  counts, elapsed time, and `COMPLETE`/`PARTIAL` status.
- Per-source `{leg}_status`/`{leg}_error`/`{leg}_elapsed_s` columns
  (additive; the six locked research fields and
  `days_to_nearest_earnings` keep their existing names/meanings), plus
  `gst_retry_count`/`gst_rate_limit_events`/`gst_budget_exhausted`, all
  under an explicit fixed `COLUMN_ORDER` (pre-filled per row, same
  discipline as `GST_MultiTicker_Forward_Log.py`'s own column-order guard).
- Per-ticker exception isolation at the `main()` loop level (in addition to
  the existing per-leg `try`/`except`s inside `process_ticker()`), so one
  ticker's unhandled failure cannot destroy already-collected rows for the
  others.

**Run 3 result (2026-07-30, bounded, unbuffered, hard 45-minute outer
`timeout` wrapper, no auto-restart):** exited code 0 (`COMPLETE`) in
**16m 1.4s** (`real` per `phase2_run3_time.log`; 959.5s per the completion
marker) -- squarely inside the established 15-17 minute baseline.

- 24 rows, 24 unique tickers, 0 duplicates, universe exactly matches the
  locked 24-ticker list.
- All six required fields (`gst_zscore`, `wiki_zscore`,
  `implied_volatility`, `realized_vol`, `price`, `volume`): **0 nulls / 24**
  -- 100% complete, matching runs 1 and 2.
- `days_to_nearest_earnings` is null for 4 tickers (CTSH, MSFT, QCOM,
  SBUX) -- `earnings_status="ok"` for all four (a genuine "no upcoming
  earnings date found" result, not a fetch failure), plausibly explained by
  MSFT's earnings landing 2026-07-29, the day before this run, shifting
  what "next" earnings resolves to. This is why
  `all_six_fields_clean_count=20` rather than 24, even though the six core
  research fields are fully complete.
- `retrieval_timestamp_utc` parses cleanly for all rows and is
  monotonically increasing (tickers processed in the intended
  priority-then-list order); single consistent `run_date`.
- `option_expiry` present for all 24 rows and strictly later than
  `run_date` for all 24 -- the contract-selection rule
  (`get_nearest_post_earnings_expiry`, imported unchanged) is intact.
  Observed one pre-existing, disclosed-in-code data quality pattern, not a
  new bug: ADBE's nearest listed expiry was 1 day out (2026-07-31),
  producing a near-degenerate `implied_volatility=0.00001` on both legs --
  the same class of issue this script's header already flagged from the
  original AAPL smoke test (a very-near-term expiry can have effectively no
  time value), just one day further out than the literal same-day case
  that fix already excludes.
- GST leg vs. runs 1/2: `gst_status="ok"` for 24/24 (no `attempts_exhausted`
  or `budget_exhausted`). Total retry attempts 41 (mean 1.71/ticker), 17
  rate-limit events across 9/24 tickers -- comparable to run 1's disclosed
  9/24 tickers hitting a 429, somewhat more than run 2's 7/24. Total GST
  time 690.0s (mean 28.8s, max 145.2s), sitting between run 1 (815.3s
  total, max 183.6s) and run 2 (658.8s total, max 182.9s) -- not a clear
  win or loss on total time, but run 3's single worst ticker (145.2s) was
  faster than both prior runs' worst ticker, directionally consistent with
  the escalating/shorter-first-retry schedule's intent. One run is not
  enough to call this a proven improvement either way.
- IV and Wikipedia legs: IV timing in line with runs 1/2 (mean 0.29s vs.
  0.37s/0.42s). Wikipedia timing shows real variance runs 1/2 didn't
  exhibit (mean 5.54s, max 61.71s vs. ~0.3-0.6s in both prior runs) --
  explained above by BKR/GME's real bisection, not a regression, and
  correctly bounded by the new per-ticker Wikipedia budget rather than
  running unbounded.

**Verified before committing:** implementation tests (above) passed before
this run was attempted, and the run itself completed 24/24 with the checks
this entry documents. GitHub Actions is deliberately NOT wired up by this
entry -- this remains a manual test-run script.
