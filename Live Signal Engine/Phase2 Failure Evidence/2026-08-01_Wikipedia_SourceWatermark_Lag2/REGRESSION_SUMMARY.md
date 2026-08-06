# Phase 2 Wikipedia rollover regression — 2026-08-01 evidence

Covers the single bounded 24-ticker regression run 2026-08-01 (commit
`2279c4d`, branch `phase2-wikipedia-reliability`), executed as the PR's
operational merge gate. Preserved here under a failure-specific name; does
not overwrite or replace the successful run-3 baseline from `46aec15`
(dated 2026-07-30) or the prior `2026-07-31_TransportRewrite_12of24_Regression`
evidence.

## Result

**Status: PARTIAL. Exit code 1.** Runtime 626.1s (10.44 min), well inside
the 45-minute internal budget and the 50-minute hard outer timeout (no
timeout triggered).

- **24/24 tickers processed**, exact match to the locked 24-ticker
  universe, 0 duplicates.
- **Five of six required fields: 24/24 complete** (`gst_zscore`,
  `implied_volatility`, `realized_vol`, `price`, `volume`).
- **`wiki_zscore`: 0/24 complete.** `all_six_fields_clean`: 0/24.
- All other source statuses (`earnings`, `price_history`, `realized_vol`,
  `iv`, `gst`): ok, 24/24.

## Root cause: measured, not assumed

This run landed ~3.5 hours into August 1 (UTC), immediately after July
closed. The fixed "coverage through `today - 1`" assumption used by the
closed-month rollover validation required July 1–31 (all 31 days) for
every ticker's now-closed July chunk. Wikipedia had not yet published
July 31 for any article checked at the time of this run.

- **23 tickers** had a validated, correctly-cached July chunk covering
  **July 1–30 (30/31 days)** — cached while July was still open, and
  correctly re-validated as `incomplete_coverage` once July closed and
  required its 31st day. This is the rollover-detection fix working
  exactly as designed, not a defect.
- **NCLH** lacked the July chunk entirely — its fetch returned an outright
  404 for the whole month on both the fresh attempt and the bounded
  second pass, not merely a missing final day.
- **Source availability was independently confirmed through July 30
  only** — see `direct_probe_evidence.csv`: a same-day, same-article
  request for July 1–31 (30-day range) returns HTTP 200 with 30 items,
  the last dated July 30; a single-day request for July 31 alone returns
  HTTP 404 for both AAPL and AMZN, live, at the time of this run.
- **Caution documented for the next phase**: a single-day per-article
  probe for July 30 ITSELF also returned HTTP 404 for AAPL (while the
  30-day range request covering the same date succeeded) — the same
  per-request-shape/per-article flakiness already documented throughout
  this investigation. Single-day, per-article probing is not a reliable
  signal on its own; this is part of the motivation for resolving any
  future watermark against the site-wide aggregate endpoint rather than
  an individual article.

## This PARTIAL validates fail-closed rollover behavior, not scientific completeness

The correct, designed outcome given a genuine, verified 2-day Wikipedia
publication lag on this specific date is exactly what happened: no
date was fabricated, no incomplete month was cached as complete, no
zero-filling occurred, and the run correctly reported PARTIAL rather than
a false COMPLETE. **No trading or research conclusion may use this
PARTIAL output.**

## Not applicable / not observed

- No cache hash problems, no duplicate dates, no invalid pageviews, no
  identity mismatches (full integrity scan clean).
- No child process remained alive after the run.
- No tracked source or test file was modified by this run (`git diff
  --stat` against HEAD empty).

## Cache growth (not committed in this evidence commit)

`Live Signal Engine/Phase2_Wikipedia_Cache.csv` grew legitimately during
this run (29 fresh + 8 second-pass successful chunk writes). It is NOT
committed here — see `cache_hashes.md` for its before/after SHA-256
hashes and a summary of the change; the cache file itself remains local
and untracked, consistent with this branch's existing cache-persistence
policy.

## Disposition

Preserved here because this is a **PARTIAL** result driven by a real,
measured, currently-confirmed Wikipedia publication lag of 2 days on this
specific date -- not a 1-day lag as the fixed prior assumption required.
This motivates replacing the fixed `today - 1` rule with a measured,
run-level watermark (see the corresponding "measure and enforce Wikimedia
publication watermark" commit). The original checkpoint, completion
marker, and run log are preserved in this directory
(`CHECKPOINT_PARTIAL_24rows.csv`, `COMPLETION_MARKER_PARTIAL.json`,
`phase2_regression_20260801T032815Z_2279c4d_PARTIAL.log`,
`phase2_regression_20260801T032815Z_2279c4d_time_PARTIAL.log`); their
original top-level/`Live Signal Engine` copies remain in place, untouched
and not removed (this evidence commit only ADDS curated copies, per
instruction).
