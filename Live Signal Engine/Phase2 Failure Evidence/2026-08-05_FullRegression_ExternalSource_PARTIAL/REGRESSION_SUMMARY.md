# 2026-08-05 — full end-to-end PR #1 merge-gate regression: PARTIAL

**Failure classification: (b) correctly handled external-source unavailability.**
No implementation defect was found. Two independent external sources degraded
during the run; both were handled fail-closed exactly as designed.

| | |
|---|---|
| Branch / commit | `phase2-wikipedia-reliability` @ `90a2ba8ad2c615c118e4fde2e76737f9d797b4f1` |
| RUN_DATE (UTC) | `2026-08-05` |
| Started / ended | `16:26:19Z` → `17:06:52Z` |
| Runtime | **2433 s (40.6 min)** |
| Exit code | **1** |
| Internal budget | `TOTAL_RUN_BUDGET_S = 2700 s` — not reached |
| Outer backstop | `timeout -k 30 3000` — not reached |
| Status | **PARTIAL** |
| Runs executed | Exactly one. No pre-probe, no restart, no manual retry, no source change. |

## Gate arithmetic

| Criterion | Observed | Pass |
|---|---|---|
| 24 unique locked tickers | 24 / 24, exact set match | ✅ |
| Duplicates | 0 | ✅ |
| `gst_zscore` | **21 / 24** | ❌ |
| `wiki_zscore` | **0 / 24** | ❌ |
| `implied_volatility` | 24 / 24 | ✅ |
| `realized_vol` | 24 / 24 | ✅ |
| `price` | 24 / 24 | ✅ |
| `volume` | 24 / 24 | ✅ |
| **`all_six_fields_clean`** | **0** | ❌ |
| `earnings_status == "ok"` | 24 / 24 | ✅ |

No final CSV was written — correct, since `FINAL_OUT_PATH` is only written on
clean 24/24.

## Cause 1 — Wikimedia per-article 404s (5 of 24)

Aggregate watermark resolved cleanly: `2026-08-04`, lag 1, HTTP 200.

Stage 1 issued the identical request `2026-08-01..2026-08-04` for every ticker
through the shared 3.5 s limiter (34 requests, 364.7 s pacing, **zero HTTP
429s**). 19 tickers returned HTTP 200 on attempt 1, every one reporting
`latest_available_date = 2026-08-04`.

Five tickers exhausted the bounded identical-request retry with three
consecutive 404s:

| Ticker | Attempts | Statuses | Retry waits (s) |
|---|---|---|---|
| BKR | 3 | `404, 404, 404` | 21.7 / 40.1 |
| CTSH | 3 | `404, 404, 404` | 21.6 / 40.6 |
| INTC | 3 | `404, 404, 404` | 21.9 / 40.3 |
| STZ | 3 | `404, 404, 404` | 21.5 / 40.6 |
| UAL | 3 | `404, 404, 404` | 21.7 / 40.1 |

Stage 1 therefore failed closed at **19/24**, no effective panel watermark was
established, and the Wikipedia leg was skipped for **all 24** tickers —
`wiki_status = incomplete_effective_watermark_unavailable` on every row. The
aggregate watermark was **not** substituted, no date was invented, and no
alternate request shape was attempted.

**Why this is external, not a defect.** The failing set rotates completely
between runs against the same code and the same request:

| Run (2026-08-05) | Failed Stage-1 tickers |
|---|---|
| 02:35 gate | ADBE, GOOGL (14-day probe shape) |
| 02:56 gate | GPN, TTWO |
| 16:26 full run | **BKR, CTSH, INTC, STZ, UAL** |

GPN and TTWO — the two failures that motivated the bounded retry — both
returned HTTP 200 on attempt 1 in this run. CTSH and INTC, clean in the
previous gate, failed here. No ticker is persistently unavailable; the
condition follows the URL-keyed CDN behaviour documented in
`../2026-08-05_EffectiveWatermark_Probe_Design_Failure/ROOT_CAUSE.md`.

**Recovered transient 404s this run: 0.** None of the five 404s cleared inside
the ~62 s bounded window. The retry mechanism is not thereby disproven — it
demonstrably recovered GPN in the preceding gate — but it did not help here.

## Cause 2 — Google Trends 429 exhaustion (3 of 24)

Independent of Wikipedia, three tickers exhausted the **pre-existing,
unmodified** GST backoff (5 attempts, escalating 20/40/70/100/130 s + jitter):

| Ticker | `gst_status` | Rate-limit events | Leg elapsed |
|---|---|---|---|
| AAPL | `attempts_exhausted` | 5 | 383.4 s |
| ABBV | `attempts_exhausted` | 5 | 386.6 s |
| SYK | `attempts_exhausted` | 5 | 398.1 s |

Every attempt returned HTTP 429. This is unchanged behaviour from before this
branch and is not related to any Wikipedia work.

## Full verification (all 20 points)

| # | Check | Result |
|---|---|---|
| 1 | Exit code / status / runtime | 1 / PARTIAL / 2433 s; neither budget reached |
| 2 | 24-ticker coverage | 24 / 24, exact locked set |
| 3 | Duplicates | 0 |
| 4 | Six locked fields | gst 21, wiki 0, iv/rv/price/volume 24 each |
| 5 | `all_six_fields_clean` | 0 (recomputed independently; matches marker) |
| 6 | `earnings_status` | `ok` × 24 (`days_to_nearest_earnings` non-null on 23 — an honest "none found", not a failure) |
| 7 | Watermarks | aggregate `2026-08-04` on all rows; effective panel watermark **not established** |
| 8 | Anchor-month attempts | 19 × (1 attempt, 200); 5 × (3 attempts, 404) — full per-ticker record in `stage1_anchor_month_attempts.csv` |
| 9 | Recovered transient 404s | 0 |
| 10 | Unresolved failures | 5 Wikipedia (Stage 1) + 3 GST (429) |
| 11 | Wiki source-mode / provenance | `wiki_source_mode` null × 24; `wiki_status` = `incomplete_effective_watermark_unavailable` × 24; `wiki_zscore_anchor_date` null × 24 |
| 12 | Cache-union / subchunk recovery | Neither invoked — the wiki leg never ran (0 `wiki chunk` lines, 0 second passes) |
| 13 | Timestamps | All 24 parseable, `16:33:41Z`–`17:06:21Z`, inside the run window |
| 14 | Option expiries | 24 / 24 non-null, all ≥ run date (`2026-08-07`, `2026-08-21`) |
| 15 | Cache before/after | `2cc29dde…ad93d` → `2cc29dde…ad93d`; 8238 rows / 329 chunks unchanged; **mtime unchanged** |
| 16 | Cache integrity | `verify_cache_integrity()` — **0 problems** across all 329 groups |
| 17 | Mutation → HTTP-200 mapping | **Zero mutations occurred**; requirement vacuously satisfied. Stage-1 responses are in-memory only and never cached. |
| 18 | Child processes | None remain (no panel, no `multiprocessing` spawn children) |
| 19 | Git status | HEAD `90a2ba8`, zero tracked modifications |
| 20 | Preserved artifacts | All prior untracked artifacts byte-identical; tracked evidence tree digest unchanged at `ba849aca…d9a5` |

Nothing was classified as zero. No missing observation was zero-filled,
interpolated, inferred, or substituted anywhere.

## Merge readiness — assessed separately from research eligibility

**Research run: PARTIAL and ineligible.** `all_six_fields_clean = 0`. The
COMPLETE criterion is unchanged and unmet. This run produces no usable panel.

**Software: assessed merge-ready**, on these grounds:

| Criterion | Status |
|---|---|
| All deterministic tests pass | ✅ 12 files, 617 assertions, 0 failures at this commit |
| Valid observations uncorrupted | ✅ Cache byte-identical, mtime unchanged, integrity clean; the 19 valid Stage-1 responses were correctly discarded rather than partially applied |
| Provenance complete | ✅ Attempt count, per-attempt statuses, retry waits, recovery flag and final HTTP status recorded for all 24 tickers, on rows and in the marker |
| Failure correctly fail-closed | ✅ No aggregate-watermark substitution, no invented dates, no alternate request shape, no zero-fill, no partial-panel emission |

The software behaved correctly under a genuinely degraded external source. The
blocker is source availability, not code.

## What was NOT done

Per instruction: no longer retries, no alternate request ranges, no
cache-busting parameters, no new fallbacks, no lowered completeness threshold.
No source change was made before, during, or after the run. The run was not
repeated.

## Files

| File | Contents |
|---|---|
| `CHECKPOINT_PARTIAL_24rows.csv` | The 24-row PARTIAL panel |
| `COMPLETION_MARKER_PARTIAL.json` | Marker incl. full anchor-month request/observed/reuse provenance |
| `phase2_regression_20260805T162601Z_90a2ba8_PARTIAL.log` | Full run log |
| `phase2_regression_20260805T162601Z_90a2ba8_time_PARTIAL.log` | Start/end/elapsed/exit code |
| `stage1_anchor_month_attempts.csv` | Per-ticker attempt sequence, waits, statuses, observed dates |
| `per_ticker_failure_classification.csv` | Per-ticker failure source and classification |
| `cache_before_after.csv` | Hashes, row/chunk counts, mutation counts, integrity result |
| `raw_artifact_hash_verification.csv` | Source→copy SHA-256 verification |
