# Phase2_Wikipedia_Cache.csv — hashes and growth summary (2026-08-01 run)

`Phase2_Wikipedia_Cache.csv` is not committed in this evidence commit —
it is a volatile, local, untracked operational cache per this branch's
existing cache-persistence policy. Recorded here for audit only.

| | SHA-256 |
|---|---|
| Before this run | `6e93b1b3cd56baa99ebf0e85fe3633b2c5219462e9197ed9965e9747d2ab7bf0` |
| After this run | `bbebda7b94f8d12681f3635eef299b8955e73244b394b140c530f627c6b346ec` |

Hash changed (expected): this run wrote 29 fresh-fetch successful chunks
and 8 bounded-second-pass-recovered successful chunks to the cache during
its first and second passes. No 404 or failed/incomplete response was
cached at any point (`incomplete_coverage` results are, by design, never
written — see `validate_snapshot()`). Post-run row count: 7,497.

23 of 24 tickers' July 2026 chunk entries in the cache remain at 30/31
days (missing only July 31, not yet published by Wikipedia at the time of
this run) — these entries are correctly recognized as `incomplete_coverage`
for a now-closed month by `validated_cache_hit()`'s per-read validation,
not silently trusted, and will refresh automatically on the next run once
July 31 becomes available. NCLH has zero cached July rows (outright 404
for the whole month, both passes).
