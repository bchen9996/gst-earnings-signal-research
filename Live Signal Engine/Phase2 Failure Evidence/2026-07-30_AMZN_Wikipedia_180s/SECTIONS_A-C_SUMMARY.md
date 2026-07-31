# Phase 2 Wikipedia reliability investigation — evidence summary

Covers the read-only investigation performed 2026-07-30/31, prior to the
`phase2-wikipedia-reliability` branch's implementation work. Full detail is
in the conversation record; this is the concise, durable summary.

## Context

Commit `46aec15` (successful 24/24 run, 16m1.381s) was the last committed
state. A follow-on session implemented a `LegTimeoutFailClosed` policy and
ADBE semantic-validation QA columns on top of it (uncommitted), then
attempted two bounded 24-ticker regression reruns to validate them:

- **Attempt 1** (`WIKI_TICKER_BUDGET_S=90`): aborted early — traced to a
  real ~63-minute laptop lid-close suspend (confirmed via Windows
  Kernel-Power event log), not a code defect.
- **Attempt 2** (`WIKI_TICKER_BUDGET_S=90`, clean retry): fail-closed
  correctly triggered on ticker 4/24 (AMZN) — a **genuine, non-injected**
  Wikipedia timeout, proving the fail-closed mechanism works in production,
  not just under synthetic test conditions.
- **Attempt 3** (`WIKI_TICKER_BUDGET_S=180`): AMZN failed again, same
  pattern one bisection level deeper. Raising the budget further was
  explicitly ruled out in favor of investigating the root cause.

## AMZN diagnostic — key findings

- **Title/mapping ruled out**: `Amazon (company)`, page ID 90451, no
  redirect, correct company description — confirmed via direct MediaWiki
  API query.
- **Not a timeout or rate-limit**: every one of 24+ diagnostic HTTP probes
  (see `direct_request_evidence.csv`) completed in under 0.7s, success or
  failure. `Retry-After` never appeared. No 429 or 5xx ever observed —
  every failure was HTTP 404 with body `"...we either do not have data for
  those date(s), or the project you asked for is not loaded yet..."`.
- **Not size-dependent**: ranges from 1 day to 300 days both succeeded and
  failed at various points; no interval size reliably reproduces failure.
- **Partially reproducible, endpoint-specific**: the single query
  `(2025-10-03, 2026-03-02)` — the 150-day first half of the production
  bisection — failed **3 times independently** (both real production
  attempts plus this diagnostic, across two separate days), while its
  complement and most overlapping/sub-decompositions succeeded. A 43-day
  sub-range of an otherwise-successful 75-day parent also failed
  independently, ruling out a clean "one bad interval" explanation.
- **The full 300-day range is NOT reliably bad**: it failed once (2026-07-30
  first probe) then succeeded 3/3 times on 2026-07-31 with the identical
  URL and no client-side change — genuine transience.
- **The retry/bisection implementation amplifies this dramatically**:
  `_fetch_chunk()` retries every 404 up to 4 times with fixed 10s/20s/30s
  waits (60s mandatory sleep per occurrence) regardless of whether the
  condition is transient. Real network time across the entire 180s failed
  attempt: ~2.4 seconds. The rest was scheduled sleep.
- **No caching anywhere**: successful sub-ranges (verified reliable across
  multiple trials: the second half, both quarters) are re-fetched from
  scratch on every run with zero reuse.

## Timeout-isolation finding (separate but related)

A deterministic test proved `run_bounded()`'s daemon-thread timeout wrapper
returns control to the caller while the abandoned thread is still alive and
still executing — demonstrated via genuine timestamped overlap on a shared
mutable object standing in for the real `pt`/`tk` objects. This is why
"fail-closed" in the prior implementation describes the *orchestration's*
exit, not a guarantee that the underlying worker actually stopped.

## Root cause (classification E)

**Combination of genuine Wikipedia-side response instability and an
inefficient recursive retry/bisection implementation.** High confidence on
the mechanism (fully reconstructed and arithmetically consistent with every
observation); moderate confidence on Wikimedia's internal cause (a
stale/inconsistent edge-cache entry for specific query strings is the
best-fitting hypothesis, not confirmed).

## Disposition

This evidence is preserved here, under failure-specific names, precisely
because it describes a **failed attempt**, not the successful run-3
baseline. The successful 24/24 artifacts (marker, logs, CSV) were restored
from commit `46aec15` after this evidence was copied out and verified.
