# 2026-08-05 — anchor-month availability-only live gate: 22/24, failed closed

**No panel was run. The operational Wikipedia cache was not mutated.** This was
a cache-isolated, availability-only gate of the Stage-1 mechanism introduced in
commit `21d9419` — Stage 1 and Stage 2 only, no ticker loop, no z-score, no
panel output.

| | |
|---|---|
| Branch / commit under test | `phase2-wikipedia-reliability` @ `21d9419b7f543c72efd0268c94e017f9710e5cdc` |
| Anchor date (UTC) | `2026-08-05` |
| Aggregate watermark | `2026-08-04` (lag 1, HTTP 200) |
| Anchor month | `2026-08` |
| **Request boundaries (identical for all 24)** | **`2026-08-01 .. 2026-08-04`** |
| Result | **`failed_closed`, 22/24 usable** |
| Requests issued | 26 (24 tickers + 2 bounded 429 retries) |
| Wall clock | 135.8 s |
| Total pacing wait | 75.6 s |
| Operational cache | `2cc29dde…ad93d` before and after, **mtime unchanged** |

## What this gate proved works

The pacing defect that made `9990c39` release-blocking is **fixed**:

- **Zero unhandled HTTP 429s.** Two tickers (GME, STZ) hit a transient 429 and
  both recovered on their single bounded retry — `attempts=2`, final status 200.
- All 26 requests passed through the one shared limiter at a 3.5 s minimum
  interval.
- Every request used the identical anchor-month boundaries; none extended past
  the aggregate watermark or to wall-clock today.

## What failed

Two tickers returned HTTP **404** on the exact anchor-month request:

| Ticker | Article | Request | Attempts | HTTP | Retry-After | Classification |
|---|---|---|---|---|---|---|
| GPN | Global Payments | `2026-08-01..2026-08-04` | 1 | 404 | — | transient CDN transport |
| TTWO | Take-Two Interactive | `2026-08-01..2026-08-04` | 1 | 404 | — | transient CDN transport |

Neither is an availability or identity problem:

- Both articles are in the locked mapping and have been identity-validated in
  prior runs.
- The **set of 404-ing articles changes between runs**: ADBE and GOOGL 404'd
  earlier the same day on a different range shape and both returned 200 here;
  CTSH, INTC and SYK — the three previously "unresolved" blockers — all
  returned clean 200s in this gate.
- Both failed on their **first and only** attempt; the design at `21d9419`
  applied no retry to a 404.

This is consistent with the URL-keyed CDN response caching characterised in
`../2026-08-05_EffectiveWatermark_Probe_Design_Failure/ROOT_CAUSE.md`.

## Watermark outcome

Stage 1 failed closed, so **no effective panel watermark was produced** — a
minimum over 22 of 24 is not a panel watermark and the aggregate watermark is
never substituted.

Had all 24 measured, the candidate effective panel watermark would have been
**`2026-08-03`** (`aggregate_vs_panel_lag_days = 1`):

| Latest observed | Count | Tickers |
|---|---|---|
| `2026-08-03` | 15 | AAPL, ABBV, ADBE, AMZN, BKR, BRK-B, CTSH, DELL, GOOGL, LDOS, MSFT, NCLH, NKE, QCOM, UAL |
| `2026-08-04` | 7 | DVN, GME, INTC, SBUX, STZ, SYK, TSLA |
| unmeasured | 2 | GPN, TTWO |

That 15/7 split is exactly the trailing-publication-lag condition the two-stage
design exists to handle, and it is being measured from the same response
production would reuse.

## Files

| File | Contents |
|---|---|
| `live_availability_gate_result.json` | Full raw gate output |
| `per_ticker_request_outcomes.csv` | All 24 tickers: boundaries, attempts, HTTP status, Retry-After, observed count, latest date |
| `gate_summary.csv` | Aggregate/candidate watermarks, pacing, runtime, cache proof |
| `raw_artifact_hash_verification.csv` | SHA-256 of the preserved JSON |

## Consequence

The remaining blocker is a **transient transport** condition, not missing data
and not a design fault. It is addressed by a bounded identical-request retry on
404 in Stage 1 only — same URL, same boundaries, at most three total attempts —
which is implemented in the commit that follows this evidence.
