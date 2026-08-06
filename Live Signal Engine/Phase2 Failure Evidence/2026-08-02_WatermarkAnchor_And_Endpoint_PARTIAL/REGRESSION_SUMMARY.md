# 2026-08-02 bounded 24-ticker regression — REGRESSION_SUMMARY

**Commit under test:** `50c49161fb74860f03fa8e9af5d55c7087ffeb7a` ("Phase 2:
align completion gate with six-field contract")
**Run wrapper:** `python -u GST_Phase2_DailyPanel.py`, internal budget
45min, hard outer `timeout 3000s` (50min) backstop.
**Log:** `phase2_regression_20260802T040024Z_50c4916_PARTIAL.log`
**Timing:** `phase2_regression_20260802T040024Z_50c4916_time_PARTIAL.log`
— start `2026-08-02T04:00:24+00:00`, end `2026-08-02T04:13:50+00:00`,
elapsed `806s` (13.4 min), `exit_code=1`.

## Verdict: PARTIAL

| Check | Result |
|---|---|
| Ticker universe | 24/24 exact match, 0 duplicates |
| gst_zscore / implied_volatility / realized_vol / price / volume | 24/24 each |
| **wiki_zscore** | **0/24** <- sole blocker |
| `all_six_fields_clean` | 0/24 |
| earnings_status | ok 24/24 |
| earnings_lookup_ok_count | 24 |
| days_to_nearest_earnings non-null | 24 |
| Wikipedia watermark | status=ok, date=2026-08-01, lag=1d (<= 3d budget), identical across all 24 rows |
| Option expiry | 24/24 strictly later than run date (earliest 2026-08-03) |
| Timestamps | all parseable, consistent |
| Child processes remaining | 0 |
| Cache integrity | clean (see `cache_integrity_summary.md`) |

## Root cause

Two distinct, unrelated causes -- see `ROOT_CAUSE_CLASSIFICATION.md`:
1. **16/24 tickers**: z-score anchor computation uses the script's
   wall-clock run date instead of the measured Wikipedia watermark date,
   pushing the anchor-to-nearest-available-week gap to 7 days -- one day
   past the existing 6-day tolerance.
2. **8/24 tickers**: genuine per-article HTTP endpoint failures (404/429)
   surviving the bounded second pass, on chunks whose exact calendar dates
   are, in most cases, already fully cached under a *different*
   chunk-boundary key from a prior run -- a cache-lookup-key limitation,
   not a data-integrity or fallback-implementation bug (see
   `endpoint_failure_8_tickers.csv`).

## Chunk-level tally (first pass)

- 186 cache hits (status=ok)
- 45 fresh fetches succeeded (status=ok)
- 33 fresh fetches failed (status=http_error), across 16 tickers

## Second pass

`*** WIKIPEDIA SECOND PASS: 33 failed chunk(s) across 16 ticker(s), remaining run budget 2322s ***`
- 19 of 33 chunks recovered (8 tickers fully recovered: BRK-B, GOOGL, GPN,
  MSFT, SBUX, STZ, TTWO, UAL)
- 14 of 33 chunks still failed after second pass (8 tickers left
  `incomplete_after_second_pass`: ADBE, AMZN, BKR, CTSH, GME, LDOS, NCLH,
  TSLA)

## What did NOT fail

Both bugs previously fixed on this branch worked correctly this run:
- The measured watermark itself resolved correctly (`status=ok`,
  `lag_days=1`, well within the 3-day budget), confirming the
  `resolve_wiki_data_watermark()` fix (`e2d7d80`) is functioning as
  designed.
- The completion gate correctly separated the six locked research fields
  from the fail-closed earnings check (`earnings_lookup_ok_count=24/24`,
  all 24 rows genuinely `earnings_status=ok`), confirming the
  completion-gate fix (`50c4916`) is functioning as designed.

## Files in this evidence directory

- `CHECKPOINT_PARTIAL_24rows.csv` -- byte-identical copy of the run's checkpoint
- `COMPLETION_MARKER_PARTIAL.json` -- byte-identical copy of the completion marker
- `phase2_regression_20260802T040024Z_50c4916_PARTIAL.log` -- byte-identical copy of the full run log
- `phase2_regression_20260802T040024Z_50c4916_time_PARTIAL.log` -- byte-identical copy of the timing file
- `failed_chunk_manifest.csv` -- the 14 chunks still failed after second pass
- `anchor_failure_16_tickers.csv` -- the 16 tickers hitting the anchor-gap bug
- `endpoint_failure_8_tickers.csv` -- full per-ticker endpoint-failure diagnostic
- `cache_hashes.md` -- before/after operational cache hashes
- `cache_integrity_summary.md` -- duplicate-key, conflict, and invalid-value scan
- `ROOT_CAUSE_CLASSIFICATION.md` -- the two-cause breakdown above, in detail

The operational cache itself (`Phase2_Wikipedia_Cache.csv`) is **not**
included per this branch's existing cache-persistence policy.
