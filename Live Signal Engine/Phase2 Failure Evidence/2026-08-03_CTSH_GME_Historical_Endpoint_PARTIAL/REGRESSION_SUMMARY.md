# 2026-08-03 bounded 24-ticker regression — REGRESSION_SUMMARY

**Commit under test:** `a0675311b932d88e1949352e9163d82fece69b08` ("Wikipedia
source-provenance-preservation fix")
**Run wrapper:** `python -u GST_Phase2_DailyPanel.py`, internal budget
45min, hard outer `timeout 3000s` (50min) backstop.
**Log:** `phase2_regression_20260803T002147Z_a067531_PARTIAL.log`
**Timing:** `phase2_regression_20260803T002147Z_a067531_time_PARTIAL.log`
— start `2026-08-03T00:21:47+00:00`, end `2026-08-03T00:25:48+00:00`,
elapsed `241s` (4.0 min wrapper; 235.8s / 3.93 min internal), `exit_code=1`.

## Verdict: PARTIAL

| Check | Result |
|---|---|
| Ticker universe | 24/24 exact match, 0 duplicates |
| gst_zscore / implied_volatility / realized_vol / price / volume | 24/24 each |
| **wiki_zscore** | **22/24** — CTSH and GME missing |
| `all_six_fields_clean` | 22/24 |
| earnings_status | ok 24/24 |
| earnings_lookup_ok_count | 24 |
| days_to_nearest_earnings non-null | 24 |
| Wikipedia watermark | status=ok, date=2026-08-01, lag=2d, identical across all 24 rows |
| Option expiry | 24/24 strictly later than run date |
| Timestamps | all parseable, consistent, monotonic |
| Child processes remaining | 0 |
| Cache integrity | clean (see `cache_hashes.md`) |

## Root cause

Single cause, isolated to two tickers — see the companion read-only
diagnostic (`../../Phase2_CTSH_GME_Diagnostic_2026-08-03.md` once produced):

- **CTSH**: chunk `2026-07-01..2026-07-31` returned HTTP 404 on both the
  first attempt and the bounded second pass.
- **GME**: chunk `2026-01-01..2026-01-31` returned HTTP 404 on both the
  first attempt and the bounded second pass.

Both are **mid-history** chunks (not the routine `2026-08-01..2026-08-03`
recent-data chunk, which succeeded for every one of the 24 tickers,
including CTSH and GME themselves). No other ticker and no other chunk
failed this run.

## Chunk-level tally

- 24/24 tickers succeeded on their `2026-08-01..2026-08-03` recent chunk
  (all `source=fetch status=ok http_status=200`, or `cache`/`cache_union_reconstruction`
  where already covered)
- AAPL used one `cache_union_reconstruction` chunk (`2025-10-05..2025-10-31`)
  — successful, read-only reconstruction from prior cache fragments, 0 new
  cache writes for that chunk
- TSLA re-fetched `2026-07-01..2026-07-31` fresh (`status=ok http_status=200`)
  in addition to its recent chunk
- 2 chunks failed the first pass: CTSH `2026-07-01..2026-07-31`, GME
  `2026-01-01..2026-01-31` — both `http_error` / `http_status=404`

## Second pass

`*** WIKIPEDIA SECOND PASS: 2 failed chunk(s) across 2 ticker(s), remaining run budget 2475s ***`
- 0 of 2 chunks recovered
- Both tickers left `incomplete_after_second_pass`: CTSH, GME

## What did NOT fail

- The measured watermark resolved correctly (`status=ok`, `lag_days=2`,
  within the 3-day budget) across all 24 rows.
- The completion gate correctly separated the six locked research fields
  from the fail-closed earnings check (`earnings_lookup_ok_count=24/24`).
- The provenance-preservation fix (`a067531`) is functioning as designed:
  every `wiki_source_components_json`/`wiki_cache_union_provenance_json`
  parses cleanly, AAPL's cache-union reconstruction carries full provenance
  (requested boundaries, contributing chunk keys/hashes/timestamps), and no
  non-null `wiki_zscore` row has a null `wiki_source_mode`.
- Cache-integrity scan (`verify_cache_integrity()`) is clean; every one of
  the 55 cache rows touched this run maps to a genuine HTTP-200 fetch (see
  `cache_hashes.md` and `cache_mutation_to_http200_mapping.csv`).

## Files in this evidence directory

- `CHECKPOINT_PARTIAL_24rows.csv` — byte-identical copy of the run's checkpoint
- `COMPLETION_MARKER_PARTIAL.json` — byte-identical copy of the completion marker
- `phase2_regression_20260803T002147Z_a067531_PARTIAL.log` — byte-identical copy of the full run log
- `phase2_regression_20260803T002147Z_a067531_time_PARTIAL.log` — byte-identical copy of the timing file
- `cache_hashes.md` — before/after operational cache hashes + legitimacy proof
- `cache_mutation_manifest.csv` — all 55 cache rows touched during this run
- `cache_mutation_to_http200_mapping.csv` — each of the 25 distinct write-groups mapped to its HTTP-200 log line
- `failed_chunk_manifest.csv` — the CTSH/GME chunks still failed after second pass (first pass + second pass + final disposition, 6 raw log lines)
- `provenance_validation_summary.md` — full 21-item post-run verification re-derivation

The operational cache itself (`Phase2_Wikipedia_Cache.csv`) is **not**
included per this branch's existing cache-persistence policy.

Hash verification: every file above was copied with `shutil.copy2` and its
SHA-256 compared byte-for-byte against the live source immediately after
copying; all copies matched exactly. No raw source file was modified or
deleted.
