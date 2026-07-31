# Changelog

## 2026-07-31 — Phase 2 Wikipedia transport rewrite: deterministic chunking, persistent cache, bounded retry, process isolation, recent-cache fallback

**Why this changed.** The 2026-07-30 run-3 safeguards (below) bounded the
Wikipedia leg per-ticker but did not fix its underlying transport. A
subsequent investigation (preserved in `Live Signal Engine/Phase2 Failure
Evidence/2026-07-30_AMZN_Wikipedia_180s/`) found AMZN repeatedly timing out
under the old recursive-bisection design. Direct evidence: real network
time across an entire failed 180s attempt was under 3 seconds; the rest was
the old code's own mandatory 10s+20s+30s=60s retry-wait schedule, paid once
per HTTP 404 encountered, with no caching, so successful sub-ranges were
re-fetched from scratch on every run. A separate deterministic test also
proved the existing daemon-thread timeout wrapper (`run_bounded()`) returns
control to the caller while the timed-out call keeps running in the
background -- "fail-closed" described the orchestration's exit, not a
guarantee the underlying worker actually stopped.

**What changed** (new module `GST_Phase2_Wikipedia_Transport.py`, isolated
from the shared `GST_Wikipedia_Pageviews_Pull.py` used elsewhere --
confirmed unmodified). None of it touches the Wikipedia z-score formula,
any of the six locked scientific field definitions, the 24-ticker universe,
GST collection, option selection, implied volatility, realized volatility,
price, volume, or earnings-date methodology -- confirmed by diff review and
by a dedicated scientific-equivalence test (below):

- **Deterministic calendar-month chunking** (`calendar_month_chunks()`)
  replacing recursive, data-dependent bisection. The exact requested
  start/end dates are preserved; interior chunks run full calendar months.
  Deterministic boundaries make chunks reliably cacheable, unlike
  recursively-computed bisection midpoints.
- **Persistent, repository-committed, human-auditable CSV cache**
  (`Live Signal Engine/Phase2_Wikipedia_Cache.csv`, 14 columns: ticker,
  configured/canonical article title, page ID, chunk bounds, date,
  pageviews, source URL, HTTP status, first-retrieved/last-verified UTC
  timestamps, schema version, content hash). Closed months are cached and
  reused; the open/current month is always refreshed. Atomic writes
  (temp file + `os.replace`). HTTP 404 is never cached as a legitimate
  zero-view period; missing dates stay explicitly missing, never
  zero-filled. Cache corruption (missing columns, schema mismatch, hash
  mismatch) is detected and treated as a source failure, never silently
  coerced.
- **Bounded second-pass retry queue**: one attempt per chunk during normal
  processing; failures queue instead of sleeping inline; after all 24
  tickers' first passes finish, each failed chunk gets exactly one bounded
  retry with short jitter (2-5s) for ordinary failures, honoring a real
  `Retry-After` header (capped at 30s) for 429s. No recursive splitting of
  a still-failing chunk. Explicitly NOT the old 10s+20s+30s schedule.
- **Genuinely killable subprocess isolation** for the Wikipedia leg
  (`run_process_bounded()`, Windows-safe `multiprocessing` spawn context):
  on timeout, terminate() then kill() if needed, then join() to actually
  reap the child before the parent continues. Proven by a deterministic
  test that spawns a real, deliberately-hanging worker and verifies via
  `os.kill(pid, 0)` that no process with that PID survives. **Scope
  disclosure**: this isolation applies to the Wikipedia leg only -- GST,
  earnings, price-history, and IV still use the older daemon-thread
  `run_bounded()` wrapper, which does not guarantee a timed-out call
  actually stops. Converting every leg would be a substantially larger
  rewrite than this pass covers.
- **Run-level fail-closed completeness**: a failed/isolated ticker no
  longer discards other tickers' rows. `is_run_complete()` (pulled out as
  a directly unit-tested pure function) requires the loop itself reported
  COMPLETE, exactly the expected unique ticker count, every row's six
  required fields complete, and every timestamp parseable -- a PARTIAL run
  can never be mistaken for COMPLETE.
- **RECENT_LAST_KNOWN_GOOD fallback** (approved as a narrow, strictly-bounded
  addition, not a general staleness tolerance): for the current/open month
  ONLY, after both the fresh attempt and the one bounded second-pass
  attempt have failed, a persisted cache snapshot may stand in if -- and
  only if -- it originated from a real HTTP 200, its content hash verifies,
  its configured article title matches, it has no duplicate dates, it
  covers every date through a lag-adjusted effective data-end date (capped
  at yesterday, since Wikipedia's own same-day pageview count is never
  complete yet regardless of any transient failure), and it was verified
  within the last 24 hours. Read-only evaluation -- never writes to cache,
  so a failed refresh can never overwrite a valid prior snapshot, and using
  the fallback never resets that snapshot's own age. Provenance fields
  (`wiki_source_mode`, `wiki_fresh_request_failed`,
  `wiki_fresh_failure_http_status`, `wiki_fallback_retrieved_at_utc`,
  `wiki_cache_age_hours`, `wiki_effective_data_end`,
  `wiki_cache_content_hash`) preserve the ORIGINAL retrieval timestamp --
  a fallback-served value is never mislabeled as freshly retrieved.
- **Observational HTTP-status/Retry-After logging** (2026-07-31, purely
  additive): chunk-level diagnostic log lines and `chunk_results` now
  surface the raw numeric HTTP status and `Retry-After` header for both
  the fresh attempt and the bounded second-pass attempt. No request,
  retry, timing, budget, chunk-boundary, fallback, or completeness
  behavior changed -- confirmed by a dedicated test
  (`test_http_status_retry_after_logging_is_purely_additive`) and by the
  full existing suite (26 prior tests) passing unchanged before and after.

**Tests** (all passing, run directly, no external framework): 13
deterministic transport-module tests (`test_phase2_wikipedia_transport.py`,
covering full success, 404-then-recovery, repeated 404, 429/Retry-After,
timeout, real process termination, malformed response, cache corruption,
atomic-write interruption, cache resume, open-month refresh, no
zero-filling, duplicate-date prevention) plus the purely-additive logging
test; 2 run-level completeness-gate tests
(`test_phase2_dailypanel_gate.py`, tests 14-15: the final gate, and PARTIAL
never nameable COMPLETE); 11 RECENT_LAST_KNOWN_GOOD fallback tests
(`test_phase2_wikipedia_recent_cache_fallback.py`: fresh-preferred, valid
fallback used, stale/incomplete/mismatched/corrupt/duplicate cache
rejected, no recursive re-use resetting the clock, failed refresh never
overwrites cache, provenance/timestamp preserved, fallback z-score exactly
matches the original successful response's).

**Scientific-equivalence test** (`test_phase2_wikipedia_equivalence.py`,
AAPL and AMZN): direct full-window response vs. monthly-chunk-assembled
response (including the fallback where applicable) -- every overlapping
date/pageview value matched exactly (300/300 both tickers), and the wiki
z-score field agreed within tolerance for both.

**AMZN-only validation** (`validate_amzn_wiki_only.py`): under live source
conditions where AMZN's July 2026 chunk 404'd on both fresh attempts, the
RECENT_LAST_KNOWN_GOOD fallback correctly used an 11.2-hour-old, fully
gated snapshot; all 300 observations assembled; the resulting field matched
the direct-response calculation exactly; status was correctly
`complete_recent_cache_fallback`, not `fresh`; no child process remained.

**24-ticker regression (2026-07-31): PARTIAL, not COMPLETE.** 2634.8s
(43.9 min), exit code 1, no automatic restart. 24/24 unique tickers, every
non-wiki required field 100% complete (0 nulls across `gst_zscore`,
`implied_volatility`, `realized_vol`, `price`, `volume`). The `wiki_zscore`
field completed for only 12/24 tickers -- 25 calendar-month chunks across
12 tickers failed both the fresh attempt and the bounded second pass.
Evidence preserved in `Live Signal Engine/Phase2 Failure Evidence/
2026-07-31_TransportRewrite_12of24_Regression/` (full failure matrix,
root-cause analysis, preserved checkpoint/marker/logs).

The evidence strongly supports transient, query-specific Wikipedia API
failures, not a defect in this rewrite: failures were scattered across 9
calendar months with no concentration near the most recent data (11/12
affected tickers' open/current month succeeded); a live re-probe of 6
sampled failures recovered 5 within minutes; a minimal single-day
availability probe (AMZN vs. AAPL, a control that fully succeeded in this
same run) showed non-monotonic success/failure on adjacent individual
days for both articles, not a clean recency cutoff. CDN or edge-cache
inconsistency is a possible mechanism for this transience -- it is **not**
confirmed; no lower-level Wikimedia-side diagnostic evidence was available
to verify it. The RECENT_LAST_KNOWN_GOOD fallback correctly stayed out of
scope for the 24 closed-month failures (by design) and correctly rejected
the one open-month failure it did evaluate (NCLH, no prior snapshot
existed).

**This PARTIAL regression validates the fail-closed transport behavior --
not 24/24 dataset completeness. No trading or substantive research
conclusion may use this PARTIAL output.** A disclosed logging gap (the 25
failures were recorded by status category, not raw numeric HTTP code, for
that specific run) is closed prospectively by the observational logging
addition above; it does not retroactively change the classification of
that run's failures, independently confirmed HTTP 404 via a sampled spot
re-probe.

**Remaining limitations, disclosed:** GST/earnings/price-history/IV legs
still use the older daemon-thread mechanism, not process isolation. The
RECENT_LAST_KNOWN_GOOD fallback only ever applies to the current/open
month -- closed-month failures under elevated source instability have no
recovery path in this design. The fallback's effective-data-end check
assumes a fixed 1-day Wikipedia publish lag and requires an exact match;
on a day where the true lag is 2+ days, an otherwise-valid snapshot could
be spuriously rejected -- not observed in the 2026-07-31 regression (whose
one open-month failure was rejected for an unrelated reason), but a
plausible edge case, not fixed in this pass. Commit 3 (a new COMPLETE
24/24 regression) is reserved for a future run under calmer source
conditions.

## 2026-07-30 — Phase 2 run-3: duration correction, operational safeguards, and a passing bounded run

No CHANGELOG.md existed in this repo before this entry.

**Correction to an earlier (informal) hypothesis:** after run 3's first
attempt (2026-07-27) ran for `real 365m3.843s` and produced a completely
empty `phase2_run3.log`, an unbounded yfinance hang was floated as the likely
cause. That was wrong to assert without doing the arithmetic first, and the
arithmetic was done before writing any code this pass, not after:

- **GST leg** (this script's scoped 429 backoff): `TrendReq`'s own
  `timeout=(30, 60)` bounds each of 5 attempts at ~90s before erroring, then
  sleeps up to `backoff+jitter` (28/48/78/108/138s across attempts 1-5).
  Fully-adversarial worst case: `sum(90+28, 90+48, 90+78, 90+108, 90+138) =
  850s` (14.2 min) per ticker -- bounded, and not smaller than the *old*
  flat-60s schedule's own worst case (750s) once the request-timeout
  dimension is included on every attempt.
- **Wikipedia leg** (`GST_Wikipedia_Pageviews_Pull.py`, not modified by this
  entry): `_fetch_chunk()` retries 429/404 up to 4 attempts (10/20/30s waits,
  ~30s timeout each -> up to 180s per chunk), and `_fetch_with_bisection()`
  recurses to `MIN_BISECT_DAYS=45`. For this script's single 300-day pull,
  the bisection tree (300→150→75→~37) makes up to `1+2+4+8 = 15` chunk calls
  if every one fails: **2700s (45 minutes) worst case for a single ticker's
  Wikipedia leg alone** -- true before today, unrelated to the GST change,
  and large enough on its own to matter.
- **yfinance 1.5.1** (installed version, read directly, not assumed):
  `yfinance/data.py`'s `_make_request()` defaults to `timeout=30` per
  underlying HTTP call, and `YfConfig.network.retries` defaults to `0` (no
  internal retry-multiplication). Calls were already bounded by yfinance's
  own defaults -- an initial assumption that they had no timeout at all was
  incorrect.
- Summing a fully-adversarial per-ticker worst case (GST 850s + Wiki 2700s +
  ~270s for earnings/price/IV) × 24 tickers ≈ **1528 minutes (~25.5 hours)**.
  The observed 365-minute duration is only ~24% of that ceiling --
  comfortably explainable by ordinary (if unlucky) bounded retry/bisection
  behavior, especially via the Wikipedia leg. An unbounded hang is not
  required to explain it, and was not assumed going forward.

**What was added** (none of it touches the six field definitions, the
24-ticker universe, any z-score methodology, or the option-contract-selection
rule -- confirmed by diff review before and after):

- Line-buffered, explicitly-flushed stdout (`sys.stdout.reconfigure(...,
  line_buffering=True)` + a `log()` helper using `print(..., flush=True)`) --
  the empty 2026-07-27 log was itself caused by fully-buffered output on a
  redirected, non-TTY stdout combined with a process that never reached a
  normal exit to flush it.
- Explicit START/DONE logging for every source leg (earnings, price
  history, realized vol, IV/options, GST, Wikipedia), every ticker.
- `run_bounded()`: a reusable wrapper that runs any call in a thread and
  waits at most a configured timeout, independent of whether the callee (or
  any library it uses) honors its own `timeout=` parameter.
  **Caught a real bug via the mandated pre-run test, not assumed to work**:
  the first version used `concurrent.futures.ThreadPoolExecutor`, which
  returned promptly from `run_bounded()` on a timeout, but
  `concurrent.futures.thread` registers a process-wide `atexit` hook that
  joins *every* worker thread any `ThreadPoolExecutor` ever created --
  including abandoned ones -- so the whole process would hang at exit
  waiting for a genuinely-stuck call, exactly the failure mode this
  safeguard exists to prevent. Fixed by switching to a plain daemon
  `threading.Thread` (daemon threads are never joined at interpreter exit).
  Verified with two tests before trusting it: (1) `run_bounded()` in
  isolation against an injected 9999s sleep with a 2s budget -- returned in
  2.02s both before and after the fix, but the *process* only exited
  cleanly after the fix (before the fix, the process hung until an outer
  `timeout` wrapper killed it); (2) a full `process_ticker("AAPL")` call
  with a 9999s delay injected into the `price_history` leg specifically
  (via `GST_PHASE2_INJECT_SLOW_TICKER`/`GST_PHASE2_INJECT_SLOW_LEG` env
  vars) -- `price_history_status` correctly recorded `"timeout"` after
  ~45s, the other four legs completed normally with real values (including
  a real GST 429 retry that resolved on its own), and the process exited
  with code 0 on its own.
- `GST_TICKER_BUDGET_S=480s` and `WIKI_TICKER_BUDGET_S=90s`: documented
  cumulative caps per ticker, on top of (not replacing) each leg's existing
  per-attempt timeout/retry/bisection limits. Verified live during the real
  run below: BKR and GME both hit real Wikipedia bisection (visible in
  `phase2_run3.log` as `"...failed -- bisecting at..."`, from the
  unmodified Wikipedia module), taking 61.7s and 61.5s respectively --
  comfortably under the 90s cap, both resolved successfully.
- `PER_TICKER_WALL_BUDGET_S=900s` and `TOTAL_RUN_BUDGET_S=2700s` (45 min):
  checked between tickers; on exhaustion the checkpoint already written is
  preserved, the next (not-yet-started) ticker is recorded as active, and
  the process exits with code 1 without restarting. Verified with a
  monkeypatched 5-second total budget against 3 real tickers: exited code 1
  after 2 tickers, checkpoint file contained exactly those 2 rows, no file
  was written under the completed-run naming convention, and the
  completion marker correctly read `"status": "PARTIAL"`,
  `"active_ticker_when_stopped": "ADBE"`.
- An atomic (write-temp-then-`os.replace`) checkpoint file after every
  ticker, named
  `GST_Phase2_DailyPanel_TestRun_<date>_run3_CHECKPOINT_PARTIAL.csv` --
  deliberately never reused as the final filename, so a partial file can
  never be mistaken for a completed panel.
- A JSON completion marker
  (`GST_Phase2_DailyPanel_TestRun_<date>_run3_COMPLETION_MARKER.json`) with
  row/unique-ticker counts, per-field completeness, per-source failure
  counts, elapsed time, and `COMPLETE`/`PARTIAL` status.
- Per-source `{leg}_status`/`{leg}_error`/`{leg}_elapsed_s` columns
  (additive; the six locked research fields and
  `days_to_nearest_earnings` keep their existing names/meanings), plus
  `gst_retry_count`/`gst_rate_limit_events`/`gst_budget_exhausted`, all
  under an explicit fixed `COLUMN_ORDER` (pre-filled per row, same
  discipline as `GST_MultiTicker_Forward_Log.py`'s own column-order guard).
- Per-ticker exception isolation at the `main()` loop level (in addition to
  the existing per-leg `try`/`except`s inside `process_ticker()`), so one
  ticker's unhandled failure cannot destroy already-collected rows for the
  others.

**Run 3 result (2026-07-30, bounded, unbuffered, hard 45-minute outer
`timeout` wrapper, no auto-restart):** exited code 0 (`COMPLETE`) in
**16m 1.4s** (`real` per `phase2_run3_time.log`; 959.5s per the completion
marker) -- squarely inside the established 15-17 minute baseline.

- 24 rows, 24 unique tickers, 0 duplicates, universe exactly matches the
  locked 24-ticker list.
- All six required fields (`gst_zscore`, `wiki_zscore`,
  `implied_volatility`, `realized_vol`, `price`, `volume`): **0 nulls / 24**
  -- 100% complete, matching runs 1 and 2.
- `days_to_nearest_earnings` is null for 4 tickers (CTSH, MSFT, QCOM,
  SBUX) -- `earnings_status="ok"` for all four (a genuine "no upcoming
  earnings date found" result, not a fetch failure), plausibly explained by
  MSFT's earnings landing 2026-07-29, the day before this run, shifting
  what "next" earnings resolves to. This is why
  `all_six_fields_clean_count=20` rather than 24, even though the six core
  research fields are fully complete.
- `retrieval_timestamp_utc` parses cleanly for all rows and is
  monotonically increasing (tickers processed in the intended
  priority-then-list order); single consistent `run_date`.
- `option_expiry` present for all 24 rows and strictly later than
  `run_date` for all 24 -- the contract-selection rule
  (`get_nearest_post_earnings_expiry`, imported unchanged) is intact.
  Observed one pre-existing, disclosed-in-code data quality pattern, not a
  new bug: ADBE's nearest listed expiry was 1 day out (2026-07-31),
  producing a near-degenerate `implied_volatility=0.00001` on both legs --
  the same class of issue this script's header already flagged from the
  original AAPL smoke test (a very-near-term expiry can have effectively no
  time value), just one day further out than the literal same-day case
  that fix already excludes.
- GST leg vs. runs 1/2: `gst_status="ok"` for 24/24 (no `attempts_exhausted`
  or `budget_exhausted`). Total retry attempts 41 (mean 1.71/ticker), 17
  rate-limit events across 9/24 tickers -- comparable to run 1's disclosed
  9/24 tickers hitting a 429, somewhat more than run 2's 7/24. Total GST
  time 690.0s (mean 28.8s, max 145.2s), sitting between run 1 (815.3s
  total, max 183.6s) and run 2 (658.8s total, max 182.9s) -- not a clear
  win or loss on total time, but run 3's single worst ticker (145.2s) was
  faster than both prior runs' worst ticker, directionally consistent with
  the escalating/shorter-first-retry schedule's intent. One run is not
  enough to call this a proven improvement either way.
- IV and Wikipedia legs: IV timing in line with runs 1/2 (mean 0.29s vs.
  0.37s/0.42s). Wikipedia timing shows real variance runs 1/2 didn't
  exhibit (mean 5.54s, max 61.71s vs. ~0.3-0.6s in both prior runs) --
  explained above by BKR/GME's real bisection, not a regression, and
  correctly bounded by the new per-ticker Wikipedia budget rather than
  running unbounded.

**Verified before committing:** implementation tests (above) passed before
this run was attempted, and the run itself completed 24/24 with the checks
this entry documents. GitHub Actions is deliberately NOT wired up by this
entry -- this remains a manual test-run script.
