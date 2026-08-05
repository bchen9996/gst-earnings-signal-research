# Root-cause classification — 2026-08-02 PARTIAL regression

Exit code 1, status PARTIAL, `all_six_fields_clean = 0/24`, driven entirely
by `wiki_zscore = 0/24`. Two **distinct, unrelated** causes, confirmed from
the checkpoint's `wiki_note` column and the regression log:

## Cause 1 (dominant, 16/24 tickers): z-score anchor uses wall-clock date, not the measured watermark

**Affected:** AAPL, ABBV, BRK-B, DELL, DVN, GOOGL, GPN, INTC, MSFT, NKE,
QCOM, SBUX, STZ, SYK, TTWO, UAL — every one of these has `wiki_status=ok`
(zero chunk failures, including the 8 that only reached `ok` after
successful second-pass recovery) yet `wiki_zscore=None`.

**Mechanism:** `_finalize_wiki_row()` in `GST_Phase2_DailyPanel.py` sets
`anchor = pd.Timestamp(run_ts.date())` — the script's real wall-clock run
date (2026-08-02) — and passes it to
`compute_zscore_at_anchor()` in `GST_FixedWindow_PerEvent_Canonical.py`.
That function requires the nearest available weekly-aggregated data point
to be within 6 days of the anchor (`gap_days > 6` -> `None`). Because the
measured Wikipedia watermark this run was **2026-08-01** (lag=1d,
`wiki_watermark_status=ok`), the daily series is genuinely truncated at
Aug 1, so the most recent fully-formed week starts **2026-07-26**. The gap
between that week and the wall-clock anchor (Aug 2) is **7 days** — one
day past the tolerance. Every affected row's `wiki_note` reads verbatim:
`"nearest pulled week 2026-07-26 is 7d from anchor -- no aligned week"`.

**Why this is new, not a repeat of either previously-fixed bug:** the
watermark mechanism itself worked correctly this run (`status=ok`,
`lag_days=1`, identical across all 24 rows, well within the 3-day budget)
— this is not the "today-1 fixed lag assumption" bug fixed in
`e2d7d80`/`7fa1762`. The completion gate also worked correctly
(`earnings_lookup_ok_count=24/24`, `all_six_fields_clean` correctly
reflects only the six locked fields) — this is not the completion-gate bug
fixed in `50c4916`. The watermark was measured correctly and used
correctly to truncate chunk *fetching*, but was never propagated into the
z-score *anchor* computation, which still independently derives its own
reference date from wall-clock time.

**Classification: implementation gap, code fix required and made in this
task.** See `ANCHOR_FIX_SUMMARY.md` (added alongside the source commit)
for the exact change.

## Cause 2 (secondary, 8/24 tickers): genuine per-article endpoint failures surviving the bounded second pass

**Affected:** ADBE, AMZN, BKR, CTSH, GME, LDOS, NCLH, TSLA — `wiki_status=
incomplete_after_second_pass`, matching `failed_source_counts.wiki=8` in
the completion marker.

**Mechanism:** 14 chunk requests, spread across these 8 tickers, received
genuine HTTP error responses (404 or 429) on both the first pass and the
bounded second-pass retry. See `endpoint_failure_8_tickers.csv` for the
full per-ticker, per-interval breakdown (failed dates, HTTP statuses,
cached-coverage-elsewhere analysis, fallback eligibility, and a 5-way
classification per interval).

**Summary of the per-interval classification** (see the CSV for detail):
- All 8 tickers' **2025-10-06..2025-10-31** failure, plus CTSH's and
  TSLA's July 2026 failures: cache already has complete (Oct) or
  near-complete (July, missing only the legitimately-not-yet-published
  final day) day-level coverage for the exact dates needed, just under a
  **different** `(chunk_start, chunk_end)` key from a prior run's rolling
  window boundary. `cached_daily_rows_for_chunk()` keys on an exact
  `(ticker, chunk_start, chunk_end)` match, so this coverage is invisible
  to today's lookup, forcing a live re-fetch that then hits real
  documented per-article endpoint flakiness. **Classification: category 3
  (cache has exact/near-exact coverage but lacks an accepted snapshot
  representation under today's exact chunk key) — not an implementation
  bug relative to documented intended behavior**, since the existing
  `recent_last_known_good` fallback was explicitly scoped, by design, to
  the open/current month only (per the 2026-08-01 evidence), never to
  arbitrary historical chunk-boundary misses.
- CTSH/GME/NCLH's **2026-08-01..2026-08-02** (open-month) failure, and
  GME's **2026-01-01..2026-01-31** failure: zero cached data exists
  anywhere for these ticker/date combinations. **Classification: category
  5 (still unresolved) / correctly-rejected fallback (category 2)** — there
  is genuinely nothing to fall back to; fail-closed behavior is correct,
  not a bug.

**No category-1 (existing fallback implementation bug violating
already-documented intended behavior) was found.** Recovering the
category-3 cases would require a new methodological capability — unioning
cached daily rows across overlapping chunk-boundary keys instead of
requiring an exact key match — which is a new design, not a narrow bug
fix. Per instruction, this is documented as a proposal for future review,
not implemented in this task.
