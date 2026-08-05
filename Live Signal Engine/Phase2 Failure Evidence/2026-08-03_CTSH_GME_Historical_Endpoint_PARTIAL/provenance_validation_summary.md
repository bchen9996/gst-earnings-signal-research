# Provenance-validation summary — 2026-08-03 run (`a067531`)

Full independent re-derivation from `CHECKPOINT_PARTIAL_24rows.csv`, cross-checked
against the run log. All 21 post-run verification items from the prior report
are re-confirmed here for the evidence record.

| # | Item | Result |
|---|---|---|
| 1 | Exit code / status / runtime | `exit_code=1`, script-reported `status=PARTIAL`, elapsed 241s wrapper / 235.8s internal |
| 2 | Universe vs. locked 24, duplicates | 24/24 unique, exact match to `TICKERS` in `GST_Phase2_DailyPanel.py`, 0 duplicates |
| 3 | Six-field completeness | gst_zscore 100%, iv 100%, realized_vol 100%, price 100%, volume 100%, **wiki_zscore 91.67% (22/24)** |
| 4 | `all_six_fields_clean` | 22 (CSV flag and independent recount agree) |
| 5 | `earnings_status` counts | 24/24 `ok` |
| 6 | Non-ok source statuses | only `wiki_status`: 2× `incomplete_after_second_pass` (CTSH, GME); all other legs 24/24 `ok` |
| 7 | Watermark cross-row consistency | single tuple across all 24 rows: date=2026-08-01, lag=2d, status=ok, http_status=200 |
| 8 | Source-mode counts | `mixed`=22, blank=2 (CTSH/GME); `wiki_cache_union_used`: True=1 (AAPL), False=21, blank=2 |
| 9 | JSON provenance parse | every `wiki_source_components_json` / `wiki_cache_union_provenance_json` parses cleanly — 0 failures |
| 10 | wiki_zscore/source_mode null consistency | no non-null `wiki_zscore` has a null `wiki_source_mode` |
| 11 | cache_union_used=True row detail (AAPL) | chunk_count=1>0, provenance-entry count=1 matches, entry has requested boundaries + contributing chunk keys/hashes/timestamps, components include `cache_union_reconstruction` |
| 12 | Source-mode/component consistency | every `mixed`-mode row has ≥2 distinct components |
| 13 | Timestamp validity/monotonicity | all `retrieval_timestamp_utc` parse; monotonic non-decreasing row order (AAPL 00:21:52 → UAL 00:25:32) |
| 14 | Option expiry vs. run_date | 0 violations, all strictly later than 2026-08-03 |
| 15 | Failed-chunk/second-pass recovery | 2 chunks failed second pass (CTSH, GME), 0 recovered — both genuine HTTP 404 on both attempts |
| 16 | Cache-integrity scan | `verify_cache_integrity()` (codebase's own function): 0 problems |
| 17 | Cache SHA/row count before/after | see `cache_hashes.md` — +26 rows, all traced to HTTP-200 activity |
| 18 | Child process check | confirmed clean — see below |
| 19 | Git status / new-modified files | 4 new untracked artifacts (checkpoint, marker, log, timelog); 0 tracked-file changes |
| 20 | Earlier baseline artifacts unchanged | all 9 pre-existing untracked evidence files hash-match their preflight-recorded values |
| 21 | Decision rule | **PARTIAL** (not softened) — 22/24 six-field-clean blocks COMPLETE |

## Child-process check (re-verified for this evidence capture)

At the time of this evidence capture, the only `python.exe`/`python3.exe`
processes running on the machine are an unrelated `extract_parallel.py` job
and its multiprocessing-fork children — none reference
`GST_Phase2_DailyPanel.py`, `GST_Phase2_Wikipedia_Transport.py`, or any wiki
chunk worker. No process from the 2026-08-03 regression remains.

## Scope note

This document is a static evidence artifact describing the 2026-08-03 run
that already completed. It does not itself constitute a new validation run
and made no network calls, no cache writes, and no panel invocation.
