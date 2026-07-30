# Changelog

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
