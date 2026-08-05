# 2026-08-05 — anchor-month availability gate with bounded 404 retry: 23/24

## Explicit statements

- **No panel ran.** This was Stage 1 + Stage 2 only — availability measurement,
  no ticker loop, no z-score, no panel output.
- **The operational cache was unchanged.** `2cc29dde…ad93d` before and after,
  byte-identical, **mtime unchanged**; the isolated temp cache was never
  written.
- **The retry implementation behaved as designed.** GPN recovered on attempt 2
  — precisely the transient-404 case the mechanism was built for — and zero
  unhandled HTTP 429s occurred across 27 requests.
- **TTWO remained unavailable after the bounded policy.** Three attempts, all
  HTTP 404, spanning ~68 s of backoff.
- **No further fallback was added.** No longer retry horizon, no alternate
  request range, no cache-busting parameter, no lowered completeness
  threshold. Stage 1 failed closed.

| | |
|---|---|
| Branch / commit under test | `phase2-wikipedia-reliability` @ `70a8df78bb120b2a13bbb65a3937b65546bc8ff0` |
| Anchor date (UTC) | `2026-08-05` |
| Aggregate watermark | `2026-08-04` (lag 1, HTTP 200) |
| **Identical request boundaries (all attempts, all tickers)** | **`2026-08-01 .. 2026-08-04`** |
| Stage-1 result | **`failed_closed`, 23/24 usable** |
| Requests issued | 27 (24 tickers + 3 retries) |
| Retry wait total | 93.2 s | 
| Pacing wait total | 134.0 s |
| Wall clock | 181.3 s |
| HTTP 429 | **0** |
| Deterministic suite at this commit | 12 files, **617 assertions, 0 failures** |

## The two retry cases

Every attempt used the byte-identical request — same article title, same
`2026-08-01..2026-08-04` boundaries, same endpoint, access type, agent type and
granularity. Full detail in `retry_behaviour_GPN_TTWO.csv`.

### GPN — recovered (the designed case)

| Attempt | Wait before | Status |
|---|---|---|
| 1 | — | `404` |
| 2 | 24.822 s | **`200_ok`** |

Result: `status=ok`, 4 observations, `latest_available_date = 2026-08-04`,
`anchor_month_recovered_after_transient_404 = True`. The single 404 that failed
this ticker in the previous gate is now absorbed.

### TTWO — exhausted the bounded policy

| Attempt | Wait before | Status |
|---|---|---|
| 1 | — | `404` |
| 2 | 24.576 s | `404` |
| 3 | 43.758 s | `404` |

Result: `status=unusable`, `reason="transport_http_error:404 after 3
attempt(s)"`, `latest_available_date = None`. No date was invented, no
alternate range was tried, and the aggregate watermark was not substituted.

**Classification.** This is *not* unavailable data and *not* an identity or
mapping problem — TTWO ("Take-Two Interactive") returned HTTP 200 for other
ranges earlier the same day, and it is a locked, previously identity-validated
article. It is the same URL-keyed CDN behaviour documented in
`../2026-08-05_EffectiveWatermark_Probe_Design_Failure/ROOT_CAUSE.md`, but with
a cache entry that outlives a ~68 s retry window. At that timescale "transient"
is no longer an accurate description of this particular URL's state, which is a
different condition from the one the bounded retry targets.

## Watermark outcome

Stage 1 failed closed, so **no effective panel watermark was produced** — a
minimum over 23 of 24 is not a panel watermark.

Had all 24 measured, the candidate would have been **`2026-08-03`**
(`aggregate_vs_panel_lag_days = 1`):

| Latest observed | Count |
|---|---|
| `2026-08-03` | 15 |
| `2026-08-04` | 8 |
| unmeasured | 1 (TTWO) |

Full breakdown in `watermark_distribution.csv`.

## Files

| File | Contents |
|---|---|
| `live_availability_gate_result.json` | Full raw gate output |
| `per_ticker_outcomes.csv` | All 24: boundaries, attempt count, attempt statuses, waits, recovery flag, final HTTP status, observed count, latest date |
| `retry_behaviour_GPN_TTWO.csv` | Attempt-by-attempt record for both retry cases |
| `gate_summary.csv` | Watermarks, pacing/retry totals, cache proof, suite result, explicit FALSE flags for panel-run / cache-mutation / source-change / extra-fallback |
| `watermark_distribution.csv` | Latest-observed-date distribution across the panel |
| `raw_artifact_hash_verification.csv` | SHA-256 of the preserved JSON |
