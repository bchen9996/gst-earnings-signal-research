# Operational cache — before/after hashes (2026-08-03 run)

| | SHA-256 | Data rows (excl. header) |
|---|---|---|
| Pre-run (preflight, recorded before launch) | `f9e89ccf03d66a3064e42b5b2933e80f202e0aba82d14ac897408ed3c73a3c69` | 8136 |
| Post-run (this evidence capture) | `e3ebecd28ae10974f7e07c3e38453621db7bea480d9b07ef0847d7c063e577fa` | 8162 |
| Net change | changed (expected — run performed live fetches) | **+26 rows** |

## Proof the change is entirely legitimate HTTP-200 activity

`cache_mutation_manifest.csv` lists all 55 cache rows whose `last_verified_utc`
falls inside this run's execution window. Those 55 rows resolve to exactly
25 distinct `(ticker, chunk_start, chunk_end)` write-groups (one call to
`write_chunk_to_cache()` per group — see `GST_Phase2_Wikipedia_Transport.py`
lines 816–847, which purges only the exact same `(ticker, chunk_start,
chunk_end)` key before appending, so a successful re-fetch of an
already-covered range shows up as "touched" without changing the net row
count for that group).

`cache_mutation_to_http200_mapping.csv` cross-references each of those 25
groups against the run log and confirms every single one corresponds to a
`source=fetch status=ok http_status=200` line — **zero exceptions, zero
unmapped groups**. 24 of the 25 groups are each ticker's routine
`2026-08-01..2026-08-03` chunk; the 25th is TSLA's `2026-07-01..2026-07-31`
chunk (a re-fetch of a previously-cached month, replacing 31 rows with
freshly-hashed but content-verified rows — net contribution to the +26 row
delta is 1, from the one genuinely new calendar date, `2026-08-03`, not
previously held by any ticker).

The two chunks that **failed** this run (CTSH `2026-07-01..2026-07-31`,
GME `2026-01-01..2026-01-31`) both returned HTTP 404 on both the first
attempt and the second pass. Per `write_chunk_to_cache()`'s own contract
("Only ever called for a SUCCESSFUL fetch with real items — a 404 or empty
result is never written here"), **no row was written for either failed
chunk** — the absence of coverage for those two ranges is exactly the
"missing" signal the design intends, not silently zero-filled or
fabricated.

## Cache-integrity scan

Ran the codebase's own authoritative `verify_cache_integrity()`
(`GST_Phase2_Wikipedia_Transport.py` lines 447–464 — per-`(ticker,
chunk_start, chunk_end)` group content-hash recomputation and comparison)
against the full post-run cache: **0 problems reported**.

A same-`(ticker, date)` value can legitimately appear under more than one
`(ticker, chunk_start, chunk_end)` group when different runs used different
chunk-boundary conventions over time (documented, pre-existing consequence
of the chunking design — `cached_daily_rows_for_chunk()` keys strictly on
`(ticker, chunk_start, chunk_end)`, not on `date` alone). This is not new
corruption from this run; the authoritative per-group hash scan already
accounts for it and found nothing wrong.

No raw source file (the live cache, the run log, the checkpoint, or the
completion marker) was modified or deleted in the course of producing this
evidence directory — only read and copied.
