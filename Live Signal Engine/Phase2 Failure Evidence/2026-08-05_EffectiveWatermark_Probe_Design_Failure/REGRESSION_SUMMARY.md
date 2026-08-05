# 2026-08-05 — read-only diagnostic: effective-watermark probe design failure

> **CORRECTED — see [`CORRECTION.md`](CORRECTION.md).** This document's SYK finding is
> wrong: production already truncates its request to the watermark, so all three prior
> blockers are transient failures now resolved, and the `:752` comment was not falsified.
> The two release-blocking defects in `9990c39` are unaffected and still stand.

**This is a regression report against commit `9990c39`, caught before it ever ran
a panel.** The commit is on PR #1 (draft, unmerged). PR #1's merge gate remains
unsatisfied.

| | |
|---|---|
| Branch | `phase2-wikipedia-reliability` |
| Commit under diagnosis | `9990c391e4f6a064aeee945b6015b965bcc09d77` |
| Kind of work | read-only live diagnostic — **no panel run, no source change, no cache mutation** |
| Anchor date (UTC) | `2026-08-05` |
| Aggregate watermark | `2026-08-04` (lag 1, HTTP 200) |
| Live requests issued | 62 (24 unpaced + 29 paced + 9 controlled matrix) |
| Operational cache | **byte-identical across all three passes** |

## Verdict

`9990c39` is release-blocking on two independent counts. See `ROOT_CAUSE.md`.

1. **Unpaced probe loop → 429 storm.** 24 requests at ~0.7 req/s; Wikimedia
   throttles from request 11. `measured=9/24` → `failed_closed` → every run
   PARTIAL.
2. **Request-shape-dependent availability.** The same date is present in one
   range's response and absent from another's, for the same article, seconds
   apart. A separate fixed-14-day probe therefore cannot certify what the
   production calendar-chunk request returns — the design premise is unsound,
   not merely mistuned.

## Diagnostic passes

| Pass | What ran | Result |
|---|---|---|
| 1 | `resolve_effective_panel_watermark()` verbatim, all 24 tickers, production pacing (i.e. none) | `failed_closed`, 9/24 measured, 14 × HTTP 429 |
| 2 | Same function, same request construction, **paced** 2–5 s (labelled diagnostic variation) | `failed_closed`, 22/24 measured; ADBE + GOOGL deterministic 404 on the probe window. Then Diagnostic B over the three blocker intervals. |
| 3 | Controlled range matrix varying only the requested range for ADBE / GOOGL / SYK | Same date present in one range, absent in another, within seconds |

Had the two probe-window 404s not occurred, the effective watermark in pass 2
would have been `2026-08-04` with `aggregate_vs_panel_lag_days = 0` — all 22
measured tickers reported `2026-08-04`, n=14.

## Prior blockers, re-probed once each through the production path

| Blocker | Outcome | Classification |
|---|---|---|
| CTSH `2026-07-08..07-14` | 200, exact 7/7 | Transient full-range failure, **now resolved** |
| INTC August interval | 200, exact 4/4 | Transient full-range failure, **now resolved** |
| SYK August interval | 404 with request end `..08-05`; 200 exact 4/4 with end `..08-04` | **Recoverable by correcting the request end** |

Leaf recovery is **not** justified — SYK is a request-construction defect, not a
partition-size one.

## Safety properties of this diagnostic

- Every fetch went through the real `fetch_chunk_isolated`; the injected
  `fetch_fn` only observed and delegated, never altering a request.
- `CACHE_PATH` was redirected to a temp file for the whole of every pass, and no
  `write_chunk_to_cache()` call site is reachable from any function called.
- Operational cache SHA-256 `2cc29dde…ad93d`, 2,286,153 bytes, mtime unchanged
  at `2026-08-04 21:32:49` across all three passes — see
  `cache_before_after_hashes.csv`. An unchanged mtime is independent proof that
  no write occurred, not merely that content happened to match.
- One attempt per (interval, shape) in Diagnostic B. Pass 3 deliberately repeats
  one range to test determinism; that is its purpose and it is labelled as such.
- No zero-fill, interpolation, inference, or reuse of differently-dated
  observations anywhere.

## Files

| File | Contents |
|---|---|
| `diagnostic_result.json` | Pass 1 — unpaced 24-ticker run, full per-request record |
| `diagnostic2_result.json` | Pass 2 — paced 24-ticker run + Diagnostic B intervals |
| `diagnostic3_result.json` | Pass 3 — controlled range-shape matrix |
| `unpaced_24ticker_429_sequence.csv` | The 429 onset, request-by-request with `Retry-After` |
| `request_matrix_ADBE_GOOGL_CTSH_INTC_SYK.csv` | Every request issued against the five articles of interest, across all passes |
| `cache_before_after_hashes.csv` | Before/after hashes and isolated-cache-written flag per pass |
| `raw_artifact_hash_verification.csv` | SHA-256 of each preserved JSON |
| `ROOT_CAUSE.md` | Full analysis and corrective direction |

## Remaining blockers for PR #1

1. **`9990c39` must be corrected before any regression run.** Superseded by the
   two-stage anchor-month design: measure availability from the *same* response
   production will use, pace globally, never request past the aggregate
   watermark.
2. **Interior historical gaps remain a separate class.** CTSH and INTC are now
   clean, but nothing here changes the rule that an interior gap fails — the
   common watermark may only remove trailing unpublished dates.
