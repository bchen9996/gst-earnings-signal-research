# Root cause — the separate availability probe cannot certify production retrieval

> **CORRECTED — see [`CORRECTION.md`](CORRECTION.md).** This document's SYK finding is
> wrong: production already truncates its request to the watermark, so all three prior
> blockers are transient failures now resolved, and the `:752` comment was not falsified.
> The two release-blocking defects in `9990c39` are unaffected and still stand.

**This directory documents a regression introduced by commit `9990c39`** ("Phase 2:
common per-article availability watermark for the whole panel"), found by a
read-only live diagnostic before any panel run. No production panel was run and
the operational Wikipedia cache was not mutated at any point — see
`cache_before_after_hashes.csv`.

Two independent defects, both release-blocking.

## Defect 1 — the probe loop is unpaced and trips the rate limiter

`resolve_effective_panel_watermark()` iterates all 24 locked tickers issuing one
availability request each, with **no pacing and no `Retry-After` handling**. Run
exactly as production would (`diagnostic_result.json`,
`unpaced_24ticker_429_sequence.csv`):

| Requests | Outcome |
|---|---|
| 1–10 | 9 × HTTP 200, 1 × HTTP 404 (ADBE) |
| **11–24** | **14 × HTTP 429**, `Retry-After` counting down 39 → 20 s |

Measured burst rate before throttling: 10 requests in 14.4 s (~0.7 req/s).
`measured=9/24` → `failed_closed` → the Wikipedia leg is skipped for every
ticker → guaranteed PARTIAL.

The aggregate-watermark path never exposed this because it issues a single
request. The new per-ticker loop multiplied that by 24 without adding pacing.

**As shipped, `9990c39` makes every run fail — strictly worse than the behaviour
it replaced.**

## Defect 2 — availability is request-shape-dependent, so a separate probe proves nothing

Re-running the same measurement **with** pacing still failed closed at 22/24:
ADBE and GOOGL returned deterministic HTTP 404s on the fixed 14-day probe window
`2026-07-22..2026-08-05` (2/2 attempts each, no `Retry-After`, not throttling).

The controlled range matrix (`diagnostic3_result.json`,
`request_matrix_ADBE_GOOGL_CTSH_INTC_SYK.csv`) isolates why. All requests below
were issued within seconds of each other:

| Article | Requested range | HTTP | n | Latest date returned |
|---|---|---|---|---|
| ADBE | `2026-07-22..2026-08-05` | **404** | 0 | — |
| ADBE | `2026-07-22..2026-08-04` | 200 | 14 | **2026-08-04** |
| ADBE | `2026-08-01..2026-08-04` | 200 | 3 | **2026-08-03** ← 08-04 absent |
| GOOGL | `2026-07-22..2026-08-05` | **404** | 0 | — |
| GOOGL | `2026-07-22..2026-08-04` | 200 | 14 | **2026-08-04** |
| GOOGL | `2026-08-01..2026-08-05` | 200 | 4 | **2026-08-04** |
| GOOGL | `2026-08-01..2026-08-04` | 200 | 3 | **2026-08-03** ← 08-04 absent |
| SYK | `2026-08-01..2026-08-05` | **404** | 0 | — |
| SYK | `2026-08-01..2026-08-04` | 200 | 4 | **2026-08-04** |
| SYK | `2026-07-22..2026-08-04` | 200 | 14 | **2026-08-04** |
| SYK | `2026-07-22..2026-08-05` | 200 | 14 | **2026-08-04** |

`2026-08-04` is **present in one range and absent from another, for the same
article, seconds apart**. This is consistent with URL-keyed CDN response caching:
each distinct range URL is a distinct cache entry with its own age and its own
snapshot of publication state.

The consequence is decisive for the design: **"the latest date article X has
published" is not a property of the article. It is a property of
(article, requested range).** A 14-day probe window therefore cannot certify what
the production calendar-month-chunk request will return.

Concretely, the shipped design would have measured `2026-08-04` for ADBE and
GOOGL from the probe window, published that as the effective panel watermark,
and then failed validation during retrieval because the open-month chunk request
returns only through `2026-08-03` for those same articles. The fix would have
reported a watermark it could not honour — the exact class of failure it was
written to eliminate.

Note also that the comment at `GST_Phase2_DailyPanel.py:752` asserting that
widening the request horizon past the watermark is "harmless" is falsified by
SYK: `..2026-08-05` returns 404 where `..2026-08-04` returns a valid 4/4.

## Consequence for the three prior blockers

Re-probed once each through the exact production request path
(`diagnostic2_result.json`):

| Blocker | Production path result | Classification |
|---|---|---|
| CTSH `2026-07-08..07-14` | HTTP 200, exact 7/7 | **Transient full-range failure, now resolved** |
| INTC `2026-08-01..` (req. through 08-04) | HTTP 200, exact 4/4 | **Transient full-range failure, now resolved** |
| SYK `2026-08-01..` (req. through 08-04) | 404 when the request ends `..08-05`; HTTP 200 exact 4/4 when it ends at the watermark | **Recoverable by correcting the request end, not by finer partitioning** |

No zero-fill, interpolation, or reuse of differently-dated observations was
involved in any acceptance; every one came from `validate_snapshot()` requiring
exact coverage and structurally valid non-negative-integer pageviews.

**Leaf recovery is not justified.** SYK's failure is a request-construction
defect — the request extended past the watermark — not a partition-size problem.
Adding a daily-leaf fallback layer would paper over that.

## Corrective direction

1. Pace the availability measurement through one shared limiter and honour
   `Retry-After`.
2. Never request past the aggregate watermark.
3. **Delete the separate probe entirely.** Availability must be measured from the
   *same response* production will use — an anchor-month calendar-chunk request
   `anchor_month_start .. aggregate_watermark`, whose observations are then
   sliced to the common effective watermark and reused, with no second request.

Item 3 is the substantive one: any design that measures availability with one
request shape and retrieves with another is unsound given the evidence above,
regardless of how carefully the probe is paced.
