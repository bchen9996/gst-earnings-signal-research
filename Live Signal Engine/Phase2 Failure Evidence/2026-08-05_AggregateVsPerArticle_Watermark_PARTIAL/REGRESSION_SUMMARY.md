# 2026-08-05 Phase 2 merge-gate regression — PARTIAL

PR #1 merge gate: **NOT satisfied.** Single run, no retry, no restart.

| | |
|---|---|
| Branch | `phase2-wikipedia-reliability` |
| Commit under test | `b400af239d89b313f7705e941ddfa7b4c2beb76b` (local = origin at launch) |
| RUN_DATE (UTC, as the script computes it) | `2026-08-05` |
| Started / ended (UTC) | `02:14:36` → `02:32:50` |
| Elapsed | **1094 s** (18.2 min) |
| Exit code | **1** |
| Internal budget | `TOTAL_RUN_BUDGET_S = 2700 s` (unmodified) — not reached |
| Outer bound | `timeout -k 30 3000` — not reached |
| Status | **PARTIAL** |

Neither timeout fired; the run terminated on its own completeness policy.
No `GST_PHASE2_INJECT_*` env vars were set, so the slow-call test hook was
inert.

## Gate arithmetic

The COMPLETE rule requires 24/24 unique locked tickers, zero duplicates, all
six locked fields present for all 24, `all_six_fields_clean = 24`, and
`earnings_status = ok` for all 24.

| Criterion | Observed | Pass |
|---|---|---|
| Locked 24-ticker coverage, unique | 24 / 24, exact set match, no extras | ✅ |
| Duplicates | 0 | ✅ |
| `gst_zscore` complete | 24 / 24 | ✅ |
| **`wiki_zscore` complete** | **5 / 24** | ❌ |
| `implied_volatility` complete | 24 / 24 | ✅ |
| `realized_vol` complete | 24 / 24 | ✅ |
| `price` complete | 24 / 24 | ✅ |
| `volume` complete | 24 / 24 | ✅ |
| **`all_six_fields_clean`** | **5** | ❌ |
| `earnings_status = ok` | 24 / 24 | ✅ |

`all_six_fields_clean = 5` was recomputed independently from the checkpoint
CSV and agrees with the completion marker. Clean tickers: **DVN, GPN, SBUX,
STZ, TSLA**. The other 19 are incomplete on `wiki_zscore` alone.

No final CSV was written — correct, since `FINAL_OUT_PATH` is only written
on clean 24/24.

## Source-status breakdown

Full per-chunk detail in `source_status_breakdown.csv`; per-ticker detail in
`per_ticker_status_breakdown.csv`.

| Chunk | Source | Status | HTTP | Count |
|---|---|---|---|---|
| `2025-10-08..2025-10-31` | `cache_union_reconstruction` | ok | — | 24 |
| `2025-11` … `2026-06` (8 months) | `cache` | ok | — | 24 each |
| `2026-01-01..2026-01-31` | `cache` / `fetch` | ok / ok | — / 200 | 23 / 1 |
| `2026-07-01..2026-07-31` | `cache` | ok | — | 23 |
| `2026-07-01..2026-07-31` | `fetch` | **http_error** | **404** | 1 (CTSH) |
| `2026-08-01..2026-08-05` | `fetch` | ok | 200 | 5 |
| `2026-08-01..2026-08-05` | `fetch` | **incomplete_coverage** | **200** | **17** |
| `2026-08-01..2026-08-05` | `fetch` | **http_error** | **404** | 2 (INTC, SYK) |

Every historical month resolved from cache without a network call. All 20
failures are concentrated in two ranges.

Wikipedia leg outcome per ticker: `wiki_status = ok` for 5,
`incomplete_after_second_pass` for 19. `wiki_source_mode = mixed` on the 5
clean rows, null on the 19. The aggregate watermark was recorded identically
on all 24 rows (`2026-08-04`, HTTP 200, retrieved `02:14:38.607859Z`).

## Failure detail

Second pass re-attempted all 20 failed chunks (`failed_chunk_manifest.csv`):

- **17 × `2026-08-01..2026-08-05`** — HTTP 200 again, rejected
  `incomplete_coverage` again → `second_pass_also_failed:validation:incomplete_coverage`.
  Recent-cache fallback declined for all
  (`no_cached_snapshot_for_this_chunk`) — no stale value was substituted.
- **3 × HTTP 404** — CTSH `2026-07`, INTC and SYK `2026-08` →
  `second_pass_also_failed:http_error`.
- **CTSH closed-month subchunk recovery** — `recovered=False`,
  `incomplete_union: missing 7 of 31 date(s) (20260708–20260714)`,
  `requests_used=5`, `wall_clock_s=25.8`, `budget_exhausted=False`. Four of
  five week-aligned subchunks recovered and were cached; the fifth failed and
  was correctly left unrecovered rather than split further or retried.

## Root cause

The binding watermark was measured from the Wikimedia **aggregate**
endpoint but enforced against the **per-article** endpoints. At 02:14Z the
aggregate had published `2026-08-04`; only 5 of 24 articles had. See
`ROOT_CAUSE.md` for the full mechanism, the cross-run lag correlation, and
why CTSH/INTC/SYK are a separate defect class that a watermark change must
not mask.

## Integrity of this capture

- **Cache**: `29d072f2…6f19` → `2cc29dde…ad93d`, 8163 → 8238 rows, 319 → 329
  write-groups. Diff on the full natural key: **75 added, 0 removed, 0
  in-place changes**. All 75 added rows carry `http_status=200` and map to 10
  write-groups with logged HTTP-200 provenance. `verify_cache_integrity()`
  reported **0 problems** across all 329 groups. Full detail in
  `cache_hashes.md`. The operational cache is deliberately **not** committed.
- **Raw artifacts**: checkpoint, marker, run log and timing log were copied
  here and each copy SHA-256-verified byte-identical to its source *before*
  the source was removed from its original location —
  `raw_artifact_hash_verification.csv`.
- **Prior evidence**: all 16 pre-existing preserved artifacts were re-hashed
  after the run and are byte-identical to their pre-run baselines. Nothing
  was overwritten.
- **Process hygiene**: no child process remained; no stray `.tmp` files;
  `git status` showed zero tracked modifications and HEAD unchanged at
  `b400af2` throughout the run and verification.

## Files in this directory

| File | Contents |
|---|---|
| `CHECKPOINT_PARTIAL_24rows.csv` | The 24-row PARTIAL panel as written by the run |
| `COMPLETION_MARKER_PARTIAL.json` | Completion marker (`status: PARTIAL`) |
| `phase2_regression_20260805T021419Z_b400af2_PARTIAL.log` | Full run log |
| `phase2_regression_20260805T021419Z_b400af2_time_PARTIAL.log` | Start/end/elapsed/exit code |
| `raw_artifact_hash_verification.csv` | Source→copy SHA-256 verification for the four raw artifacts |
| `cache_hashes.md` | Cache before/after hashes, counts, diff classes, integrity scan |
| `cache_mutation_manifest.csv` | All 75 added cache rows, verbatim |
| `cache_mutation_to_http200_mapping.csv` | Each of the 10 write-groups → its HTTP-200 evidence |
| `failed_chunk_manifest.csv` | All 63 failure/recovery log lines |
| `source_status_breakdown.csv` | Per-chunk `(source, status, http_status)` counts |
| `per_ticker_status_breakdown.csv` | Per-ticker wiki status, source mode, clean flag, earnings status |
| `ROOT_CAUSE.md` | Root-cause analysis and fix direction |

## Blocker

PR #1 cannot merge until a run reaches `all_six_fields_clean = 24`. Two
independent blockers stand between here and that:

1. **Trailing per-article publication lag** — addressed by the effective
   panel watermark described in `ROOT_CAUSE.md`.
2. **Internal historical gaps / persistent 404s** — CTSH `2026-07-08..14`,
   INTC and SYK `2026-08`. Not a lag problem; not fixed by any watermark
   change. Must continue to produce PARTIAL until legitimately recovered.
