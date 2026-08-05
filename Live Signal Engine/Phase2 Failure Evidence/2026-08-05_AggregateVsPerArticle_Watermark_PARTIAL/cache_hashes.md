# Operational cache — before/after hashes (2026-08-05 run)

| | SHA-256 | Data rows (excl. header) | Bytes | Write-groups |
|---|---|---|---|---|
| Pre-run (recorded at preflight, before launch) | `29d072f24d25a60a9011a3596588f32c39278c9eab22e4989a170226587a6f19` | 8163 | 2,265,877 | 319 |
| Post-run (this evidence capture) | `2cc29ddeb3f8dcc7c3f1075a3a5813ff90a292341e734cf9de2255d0801ad93d` | 8238 | 2,286,153 | 329 |
| Net change | changed (expected — run performed live fetches) | **+75 rows** | +20,276 | **+10 groups** |

The operational cache is **not** committed with this evidence directory. It is
volatile run state, unchanged from the standing policy for the earlier
evidence captures in this folder.

## Exact diff, not a heuristic

Earlier captures in this folder identified "touched" rows by
`last_verified_utc` window. This capture instead diffs the byte-identical
pre-run snapshot against the post-run file on the full natural key
`(ticker, chunk_start, chunk_end, date)`:

| Diff class | Count |
|---|---|
| Rows added | 75 |
| Rows removed | **0** |
| Pre-existing rows changed in place (any of `pageviews`, `source_url`, `http_status`, `first_retrieved_utc`, `last_verified_utc`, `content_hash`, `cache_schema_version`, `configured_article_title`) | **0** |

No previously-cached observation was rewritten, revalidated in place, or
dropped. The run was purely additive.

## Proof the 75 added rows are legitimate HTTP-200 observations

`cache_mutation_manifest.csv` lists all 75 added rows verbatim. Every one
carries `http_status=200`. They resolve to exactly **10** distinct
`(ticker, chunk_start, chunk_end)` write-groups — one
`write_chunk_to_cache()` call each.

`cache_mutation_to_http200_mapping.csv` maps each of the 10 groups to its
originating log evidence. Breakdown by write mechanism:

- **6 groups — first-pass fetch.** DVN / GPN / SBUX / STZ / TSLA
  `2026-08-01..2026-08-05` (4 rows each: `20260801`–`20260804`) and GME
  `2026-01-01..2026-01-31` (31 rows). Each has a matching
  `source=fetch status=ok http_status=200` line in the run log.
- **4 groups — closed-month subchunk recovery.** CTSH `2026-07-01..07`,
  `2026-07-15..21`, `2026-07-22..28`, `2026-07-29..31` (24 rows total). The
  transport logs subchunk recovery as a single per-chunk summary line
  (`requests_used=5 wall_clock_s=25.8`), so the per-subchunk HTTP status is
  not separately printed; the mapping row records that summary line. The
  HTTP-200 provenance for these four groups rests on two independent facts
  rather than a log line: every persisted row carries `http_status=200`, and
  `write_chunk_to_cache()` is reachable from the recovery path
  (`GST_Phase2_Wikipedia_Transport.py` line 1656) only after
  `result["status"] == "ok"` and per-subchunk `validate_snapshot()` success.

All three `write_chunk_to_cache()` call sites (lines 1145, 1252, 1656) were
read and confirmed to be gated on `result["status"] == "ok"` **and**
`validate_snapshot()` validity.

## Nothing failed was persisted

The 20 chunks that failed this run wrote **zero** rows:

- 17 × `2026-08-01..2026-08-05` — HTTP **200** but rejected by
  `validate_snapshot()` as `incomplete_coverage`, on both the first pass and
  the second pass.
- 3 × HTTP **404** — INTC and SYK `2026-08-01..2026-08-05`, CTSH
  `2026-07-01..2026-07-31`.

This is the point worth recording: a **200 response is not sufficient** to
enter the cache. Seventeen well-formed 200s were discarded because they did
not cover every expected date. Per `write_chunk_to_cache()`'s contract
("Only ever called for a SUCCESSFUL fetch with real items — a 404 or empty
result is never written here"), the absence of rows for those ranges is the
intended "missing" signal — never zero-filled, never fabricated.

CTSH's `2026-07-08..2026-07-14` subchunk also failed inside the recovery
attempt and, correctly, wrote nothing; the union therefore stayed
incomplete (`missing 7 of 31 date(s)`) and recovery reported
`recovered=False`.

## Cache-integrity scan

Ran the codebase's own authoritative `verify_cache_integrity()`
(`GST_Phase2_Wikipedia_Transport.py` lines 447–464 — per-group content-hash
recomputation and comparison) against the full post-run cache, loaded
through `load_cache()` so the schema-version gate applied:
**0 problems across all 329 groups.**

The cache SHA-256 was re-measured after every read-only verification step
and still matched `2cc29dde…ad93d`, confirming the verification itself
mutated nothing.

## Raw-artifact handling

The checkpoint, completion marker, run log and timing log were copied into
this directory and each copy was **SHA-256-verified byte-identical to its
source before the source was removed** from its original location — see
`raw_artifact_hash_verification.csv`. The operational cache was neither
copied here nor modified.

This repository runs with `core.autocrlf=true`, which normalises CRLF→LF on
commit and LF→CRLF on checkout. Left alone, that would mean a fresh clone
could not reproduce the SHA-256 values recorded here or in
`raw_artifact_hash_verification.csv` — three of the four preserved artifacts
hashed differently as blobs than on disk. A directory-scoped
`.gitattributes` (`* -text`) disables EOL conversion for this evidence
folder, and every committed blob was then confirmed byte-identical to the
file that was hashed. Earlier evidence directories in this folder predate
that guard and were committed under the normalising default.
