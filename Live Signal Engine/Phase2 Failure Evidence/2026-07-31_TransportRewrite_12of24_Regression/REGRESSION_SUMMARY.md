# Phase 2 Wikipedia transport rewrite — 24-ticker regression evidence

Covers the single bounded 24-ticker regression run 2026-07-31, on branch
`phase2-wikipedia-reliability`, using the deterministic calendar-month
chunking / persistent cache / bounded second-pass / process-isolated
transport (`GST_Phase2_Wikipedia_Transport.py`) plus the RECENT_LAST_KNOWN_GOOD
open-month fallback. This directory preserves that run's evidence under a
failure-specific name — it does not replace or overwrite the successful
run-3 baseline artifacts from commit `46aec15`.

## Result

**Status: PARTIAL. Exit code 1.** 24/24 unique tickers processed in
2634.8s (43.9 min), inside the 45-minute total-run budget, no automatic
restart. All 24 rows have valid timestamps; every non-wiki required field
(`gst_zscore`, `implied_volatility`, `realized_vol`, `price`, `volume`) is
100% complete (0 nulls). The `wiki_zscore` field is complete for only
**12/24 tickers** — the other 12 have one or more calendar-month chunks
that failed both the fresh attempt and the one bounded second-pass attempt,
and were correctly left `incomplete_after_second_pass` rather than
computed from partial data.

**This PARTIAL regression validates the fail-closed transport behavior
(deterministic chunking, persistent caching, bounded retry, process
isolation, and honest PARTIAL classification all functioned correctly
under real adversarial source conditions) — it does NOT validate 24/24
dataset completeness. No trading or substantive research conclusion may
be drawn from this PARTIAL output.**

## Failure matrix

See `failed_chunk_manifest.csv` for all 25 failed (ticker, calendar-month)
chunks: ticker, exact requested chunk start/end, first-pass and
second-pass status, whether the chunk was the open/current month, whether
the RECENT_LAST_KNOWN_GOOD fallback was evaluated, and the exact
acceptance/rejection outcome.

- 25 failed chunks across 12 tickers (ADBE, BKR, CTSH, GME, GOOGL, GPN,
  INTC, LDOS, MSFT, NCLH, SYK, UAL), 1–4 chunks each.
- Spread across 9 different calendar months (Oct 2025 – Jul 2026), heaviest
  in Jan 2026 (5) and Oct 2025 (4) — the oldest/middle part of the window,
  not the newest.
- Only 1 of 25 (NCLH, July) touches the current/open month. 11 of the 12
  affected tickers' open-month chunk succeeded — the most recent data was
  fine for nearly all affected tickers.
- The RECENT_LAST_KNOWN_GOOD fallback was evaluated exactly once (NCLH's
  July chunk, the only open-month failure) and correctly rejected:
  `no_cached_snapshot_for_this_chunk` — NCLH had never been fetched
  successfully before, so there was no prior snapshot to fall back to.
  This is the designed, honest behavior, not a defect. The fallback never
  triggered for the other 24 failures because they were closed months,
  out of the fallback's scope by design.

## Root cause

**The evidence strongly supports transient, query-specific Wikipedia API
failures**, not a defect in this transport rewrite:

- Failures are scattered across 9 calendar months and 12 tickers with no
  concentration near the most recent data.
- Independent same-day re-probes of 6 sampled failed (article, month)
  pairs recovered 5 of 6 within minutes.
- A minimal single-day waterline probe (AMZN vs. AAPL, a fully-successful
  control in this same run) for the 7 most recent days showed
  **non-monotonic** success/failure on adjacent individual days for
  *both* articles — not a clean "data not yet published" cutoff.
- Every failure was categorized `http_error`; a sample was independently
  confirmed HTTP 404 via direct and spot re-probes. **CDN or edge-cache
  inconsistency is a possible mechanism for this transience — it is not
  confirmed.** No lower-level Wikimedia-side diagnostic evidence was
  available to verify it.
- **Disclosed logging gap:** the 25 regression failures were recorded and
  classified as `http_error` (a status category); the raw numeric HTTP
  status was independently confirmed 404 for a spot-checked sample via
  separate direct probes, but was NOT captured in this run's own log for
  each of the 25 failed chunks individually. This gap is closed
  prospectively (not retroactively, and not for this run) by the
  http_status/retry_after fields added to `chunk_results` in this same
  commit.

## Not applicable / not observed

- No timeouts, no malformed responses, no cache corruption, no atomic-write
  failures anywhere in this run.
- No `Retry-After` header observed on any of the 25 failures or the
  waterline probe.
- No child process remained alive after the run completed.
- Cache integrity: all previously-cached data survived; nothing was
  overwritten by a failed refresh; no 404 was cached as legitimate data.

## Disposition

Preserved here under a failure-specific name because it is a **PARTIAL**
regression result, not a completed 24/24 panel. The original checkpoint,
completion marker, and run log are preserved in this directory
(`CHECKPOINT_PARTIAL_24rows.csv`, `COMPLETION_MARKER_PARTIAL.json`,
`phase2_run3_wikireliability_2026-07-31_PARTIAL.log`,
`phase2_run3_wikireliability_2026-07-31_time_PARTIAL.log`); their original
top-level/`Live Signal Engine` copies were removed after verifying these
preserved copies are byte-identical, so this PARTIAL result cannot be
confused with or accidentally overwrite the successful run-3 baseline
(`GST_Phase2_DailyPanel_TestRun_2026-07-30_run3.csv`, unaffected, dated the
day before this run and never touched by it).

Commit 3 (a new COMPLETE 24/24 regression) is reserved for a future run
under calmer source conditions and has not been created.
