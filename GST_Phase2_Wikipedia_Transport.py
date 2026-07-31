#!/usr/bin/env python3
# GST PHASE 2 -- WIKIPEDIA TRANSPORT (deterministic chunking, persistent
# cache, bounded second-pass retry, killable subprocess isolation)
#
# WHY THIS IS A SEPARATE MODULE, NOT A CHANGE TO GST_Wikipedia_Pageviews_Pull.py:
# that module is shared outside Phase 2 (the 152-event canonical-population
# pull uses it directly). This isolates the Phase 2 daily-panel path per
# explicit instruction, rather than risking the shared module's other
# callers. GST_Wikipedia_Pageviews_Pull.py is NOT modified by this file --
# only TICKER_TO_WIKI_ARTICLE (a static dict) is imported from it.
#
# ROOT CAUSE THIS REPLACES (see Live Signal Engine/Phase2 Failure Evidence/
# 2026-07-30_AMZN_Wikipedia_180s/ for the full investigation): AMZN's
# Wikipedia leg repeatedly timed out under the old recursive-bisection
# design. Direct evidence: real network time across the entire failed 180s
# attempt was under 3 seconds; the rest was the old code's own mandatory
# 10s+20s+30s=60s retry-wait schedule, paid once per 404 encountered, with
# no caching so successful sub-ranges were re-fetched from scratch on every
# run. Root cause was classified as a COMBINATION of genuine (if transient)
# Wikipedia-side 404s and an inefficient retry/bisection implementation --
# this module fixes the implementation side: deterministic chunks (stable,
# cacheable keys, unlike recursively-computed bisection midpoints),
# persistent cross-run caching (never re-pay for a chunk that already
# succeeded), a single bounded retry pass instead of inline sleeping, and
# genuinely killable process isolation (the prior daemon-thread wrapper was
# proven, by a deterministic test, to leave the timed-out call running in
# the background after "returning" -- a real process boundary can actually
# be terminated, unlike a thread).
#
# SCOPE DISCLOSURE: this process-isolation mechanism is applied to the
# Wikipedia leg ONLY. The GST, earnings, price-history, and IV legs in
# GST_Phase2_DailyPanel.py still use the older thread-based run_bounded()/
# LegTimeoutFailClosed mechanism, which does NOT guarantee the timed-out
# call actually stops -- converting every leg to process isolation would be
# a substantially larger rewrite than this pass covers. Do not read
# "process isolation exists in this file" as "the whole script is
# isolated" -- it is not.
#
# SCIENTIFIC CHARACTERIZATION OF THE SOURCE INSTABILITY (2026-07-31,
# following a 24-ticker regression that came back PARTIAL, 12/24 wiki
# fields complete -- see Live Signal Engine/Phase2 Failure Evidence/
# 2026-07-31_TransportRewrite_12of24_Regression/ for the full
# investigation). Stated precisely, not overstated:
#   - The evidence strongly supports transient, query-specific Wikipedia
#     API failures: 25 failed chunks were scattered across 9 different
#     calendar months and 12 different tickers, with no concentration near
#     the most recent data (11/12 affected tickers' current/open month
#     succeeded); independent same-day re-probes recovered most of the
#     failed chunks within minutes; single-day probes on both an affected
#     and an unaffected control ticker showed non-monotonic
#     success/failure on adjacent days, not a clean recency cutoff.
#   - CDN or edge-cache inconsistency is a POSSIBLE mechanism for this
#     transience -- it is NOT confirmed. No lower-level evidence (cache
#     headers, server timing, Wikimedia-side diagnostics) was available to
#     verify it; it is the best-fitting hypothesis given the observed
#     pattern, nothing more.
#   - The 25 regression failures were recorded and classified as
#     `http_error` (a status category); exact HTTP 404 was independently
#     confirmed via direct and spot re-probes for a sample of these, but
#     the raw numeric status was NOT captured in that regression's log for
#     each of the 25 chunks individually (a real, disclosed logging gap --
#     see the http_status/retry_after fields added to chunk_results below,
#     which close this gap prospectively, not retroactively).
#   - That PARTIAL regression validates the FAIL-CLOSED TRANSPORT
#     BEHAVIOR (deterministic chunking, caching, bounded retry, process
#     isolation, and honest PARTIAL classification all worked correctly
#     under real adversarial conditions) -- it does NOT validate 24/24
#     dataset completeness, and no trading or substantive research
#     conclusion may be drawn from that PARTIAL output.

from __future__ import annotations
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import multiprocessing
import os
import random
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import pandas as pd

CACHE_PATH = Path("Live Signal Engine") / "Phase2_Wikipedia_Cache.csv"
CACHE_SCHEMA_VERSION = "1"

CACHE_COLUMNS = [
    "ticker", "configured_article_title", "canonical_title", "page_id",
    "chunk_start", "chunk_end", "date", "pageviews", "source_url", "http_status",
    "first_retrieved_utc", "last_verified_utc", "cache_schema_version", "content_hash",
]

WIKI_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{article}/daily/{start}/{end}"

# Per-chunk subprocess timeout: a single attempt, no inline retry. 30s
# matches the underlying urlopen timeout used inside the worker -- this is
# a backstop against the worker itself hanging beyond that, verified by the
# process-isolation test (a genuinely killable bound, unlike the old
# daemon-thread wrapper).
CHUNK_TIMEOUT_S = 35.0

# Bounded second-pass retry: short jitter for ordinary 404/connection
# failures (NOT the old 10s/20s/30s escalating schedule -- direct evidence
# showed real network time was under 3 seconds total across an entire
# failed attempt, so a short bounded jitter is proportionate, not the old
# assume-it's-still-retrying-forever approach).
SECOND_PASS_JITTER_RANGE_S = (2.0, 5.0)
SECOND_PASS_MAX_WAIT_FOR_RETRY_AFTER_S = 30.0   # cap on honoring a real Retry-After header

# --- RECENT_LAST_KNOWN_GOOD fallback (2026-07-31, approved as a narrow,
# strictly-bounded addition -- NOT a general staleness tolerance). Applies
# ONLY to the current/open Wikipedia month, and ONLY after a fresh attempt
# AND the one bounded second-pass attempt have both already failed. See
# evaluate_recent_cache_fallback()'s docstring for the full gate list.
RECENT_CACHE_FALLBACK_MAX_AGE_HOURS = 24.0
# Wikipedia's pageview counts have a genuine same-day processing lag --
# "today"'s own daily total is never fully counted yet, regardless of any
# transient 404 issue. This is a real data-availability fact, not a carve-out
# invented to make a fallback succeed: a fresh request for a range ending
# "today" was never going to return today's row either. The fallback's
# completeness bar is capped at yesterday accordingly.
RECENT_CACHE_FALLBACK_DATA_LAG_DAYS = 1


class CacheCorruptionError(Exception):
    """Raised when the persistent cache file exists but doesn't match the
    expected schema -- treated as a source failure (recompute from scratch),
    never silently patched over."""


def calendar_month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Splits [start, end] into calendar-month-aligned chunks. The exact
    requested start and end dates are preserved -- only the FIRST and LAST
    chunks are clipped to them; interior chunks run the full calendar month.
    Deterministic: the same (start, end) always produces the same chunk
    boundaries, unlike the old recursive bisection's data-dependent midpoints
    -- this determinism is what makes the chunks reliably cacheable."""
    if start > end:
        return []
    chunks = []
    cursor = start
    while cursor <= end:
        if cursor.month == 12:
            next_month_start = date(cursor.year + 1, 1, 1)
        else:
            next_month_start = date(cursor.year, cursor.month + 1, 1)
        month_end = next_month_start - timedelta(days=1)
        chunk_end = min(month_end, end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def is_open_chunk(chunk_start: date, chunk_end: date, today: date) -> bool:
    """The currently open/incomplete month -- the one containing today --
    may be refreshed on every run since it's still accumulating data. Any
    other (fully past) chunk is closed and, once successfully cached, is
    permanently reusable (Wikipedia's historical pageview data for a
    completed period doesn't change)."""
    return chunk_start <= today <= chunk_end


def compute_chunk_hash(daily_rows: list[dict]) -> str:
    """Deterministic integrity hash over a chunk's (date, pageviews) pairs.
    Used to detect cache corruption (a row whose stored hash doesn't match
    a recomputed hash of its own chunk's sibling rows) -- see
    verify_cache_integrity()."""
    payload = json.dumps(sorted([(r["date"], r["pageviews"]) for r in daily_rows]), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_cache() -> pd.DataFrame:
    """Reads the persistent cache. Missing file -> empty (valid) cache.
    Present but schema-mismatched file -> CacheCorruptionError, never
    silently coerced -- corruption is a source failure, not something to
    patch over quietly."""
    if not CACHE_PATH.exists():
        return pd.DataFrame(columns=CACHE_COLUMNS)
    try:
        df = pd.read_csv(CACHE_PATH, dtype={"chunk_start": str, "chunk_end": str, "date": str,
                                             "page_id": str, "cache_schema_version": str})
    except Exception as e:
        raise CacheCorruptionError(f"cache file unreadable: {e}")
    missing_cols = set(CACHE_COLUMNS) - set(df.columns)
    if missing_cols:
        raise CacheCorruptionError(f"cache missing expected columns: {sorted(missing_cols)}")
    bad_version = df[df["cache_schema_version"].astype(str) != CACHE_SCHEMA_VERSION]
    if not bad_version.empty:
        raise CacheCorruptionError(
            f"cache contains {len(bad_version)} row(s) with an unexpected schema version "
            f"(expected {CACHE_SCHEMA_VERSION!r})"
        )
    return df


def verify_cache_integrity(df: pd.DataFrame) -> list[str]:
    """Recomputes each (ticker, chunk_start, chunk_end) group's content hash
    from its own stored rows and compares to the stored hash. Returns a list
    of human-readable problems (empty list = clean). Does not raise -- the
    caller decides whether to treat any given group as unusable."""
    problems = []
    if df.empty:
        return problems
    for (ticker, cs, ce), group in df.groupby(["ticker", "chunk_start", "chunk_end"]):
        stored_hashes = group["content_hash"].unique()
        if len(stored_hashes) != 1:
            problems.append(f"{ticker} {cs}..{ce}: inconsistent content_hash within the group ({stored_hashes})")
            continue
        recomputed = compute_chunk_hash(group[["date", "pageviews"]].to_dict("records"))
        if recomputed != stored_hashes[0]:
            problems.append(f"{ticker} {cs}..{ce}: content_hash mismatch (stored={stored_hashes[0]}, "
                             f"recomputed={recomputed}) -- treat as corrupted")
    return problems


def write_chunk_to_cache(ticker: str, article: str, canonical_title: str | None, page_id: str | None,
                          chunk_start: date, chunk_end: date, daily_rows: list[dict],
                          source_url: str, http_status: int, now_utc: str) -> None:
    """Atomic write (temp file + os.replace, same pattern as the rest of this
    project's checkpointing). Only ever called for a SUCCESSFUL fetch with
    real items -- a 404 or empty result is never written here, so the
    absence of cache rows for a range is itself the "missing" signal; HTTP
    404 is never cached as a legitimate zero-view period, and missing dates
    are never zero-filled (unchanged from the existing, locked z-score
    methodology's own gap-tolerant summation in to_weekly())."""
    if not daily_rows:
        return
    df = load_cache()
    mask = (
        (df["ticker"] == ticker)
        & (df["chunk_start"] == chunk_start.isoformat())
        & (df["chunk_end"] == chunk_end.isoformat())
    )
    df = df[~mask]
    content_hash = compute_chunk_hash(daily_rows)
    new_rows = [{
        "ticker": ticker, "configured_article_title": article, "canonical_title": canonical_title or "",
        "page_id": page_id or "", "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
        "date": r["date"], "pageviews": r["pageviews"], "source_url": source_url,
        "http_status": http_status, "first_retrieved_utc": now_utc, "last_verified_utc": now_utc,
        "cache_schema_version": CACHE_SCHEMA_VERSION, "content_hash": content_hash,
    } for r in daily_rows]
    df = pd.concat([df, pd.DataFrame(new_rows, columns=CACHE_COLUMNS)], ignore_index=True)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, CACHE_PATH)


def cached_daily_rows_for_chunk(df: pd.DataFrame, ticker: str, chunk_start: date, chunk_end: date) -> list[dict]:
    if df.empty:
        return []
    mask = (
        (df["ticker"] == ticker)
        & (df["chunk_start"] == chunk_start.isoformat())
        & (df["chunk_end"] == chunk_end.isoformat())
    )
    sub = df[mask]
    return sub[["date", "pageviews"]].to_dict("records")


# --- Killable subprocess isolation -----------------------------------------
#
# _fetch_chunk_worker MUST be a top-level function (not a closure/lambda):
# Windows' default multiprocessing start method is "spawn", which pickles
# the target by import path (module + qualified name), not by value -- a
# nested function has no stable import path and cannot be spawned. Guarded
# by this module having no top-level side effects on import (safe for the
# spawned child to re-import).

def _fetch_chunk_worker(article: str, start_ymd: str, end_ymd: str, result_path: str) -> None:
    """Runs in a CHILD PROCESS. Writes its outcome to result_path as JSON,
    atomically (temp file + os.replace) so the parent never reads a
    half-written file. A single attempt -- no inline retry here; retries are
    handled by the bounded second pass at the orchestration level, not
    inside the worker.

    start_ymd/end_ymd MUST be YYYYMMDD (no dashes) -- the Wikimedia
    pageviews REST API's path segment requires this exact compact form
    (matching GST_Wikipedia_Pageviews_Pull._fetch_chunk's strftime("%Y%m%d")).
    A dashed ISO date (date.isoformat()) here silently 404s on every single
    request regardless of real data availability -- caught by the
    scientific-equivalence test (AAPL, which has no known Wikipedia-side
    404 history, failed 10/10 chunks identically to AMZN until this was
    fixed)."""
    encoded = urllib.parse.quote(article.replace(" ", "_"), safe="")
    url = WIKI_API.format(article=encoded, start=start_ymd, end=end_ymd)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; GST project)"})
    result = {"status": "error", "http_status": None, "items": [], "error": None,
              "retry_after": None, "url": url, "network_elapsed_s": None}
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
            result["network_elapsed_s"] = time.time() - t0
            result["http_status"] = resp.status
            items = body.get("items", [])
            result["items"] = [{"date": it["timestamp"][:8], "pageviews": it["views"]} for it in items]
            result["status"] = "ok" if items else "empty"
    except urllib.error.HTTPError as e:
        result["network_elapsed_s"] = time.time() - t0
        result["http_status"] = e.code
        result["retry_after"] = e.headers.get("Retry-After")
        result["status"] = "http_error"
        result["error"] = f"HTTP {e.code}"
    except Exception as e:
        result["network_elapsed_s"] = time.time() - t0
        result["status"] = "exception"
        result["error"] = f"{type(e).__name__}: {e}"
    tmp = result_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f)
    os.replace(tmp, result_path)


def run_process_bounded(target, args: tuple, timeout_s: float) -> dict:
    """Generic, directly-testable core of the process-isolation mechanism:
    spawn `target(*args)` in a child process (Windows-safe spawn context),
    wait up to timeout_s, and on timeout terminate() then kill() (if still
    alive) then join() to actually reap it -- never returning while the
    child might still be alive. Separated from fetch_chunk_isolated() so
    this exact mechanism can be exercised directly against a trivial,
    deliberately-slow top-level test function, independent of the real
    Wikipedia-fetching worker -- see
    test_phase2_wikipedia_transport.py: test_process_actually_terminates.

    Returns {"completed": bool, "terminated": bool, "elapsed_s": float,
    "pid": int|None}. "completed"=False means the child was killed/terminated
    (timeout); the caller must not assume any output the child may have
    produced is trustworthy or even present."""
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=target, args=args)
    t0 = time.time()
    proc.start()
    pid = proc.pid
    proc.join(timeout=timeout_s)
    elapsed = time.time() - t0

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=5)
        terminated = not proc.is_alive()
        return {"completed": False, "terminated": terminated, "elapsed_s": elapsed, "pid": pid}
    return {"completed": True, "terminated": False, "elapsed_s": elapsed, "pid": pid}


def fetch_chunk_isolated(article: str, start: date, end: date, timeout_s: float = CHUNK_TIMEOUT_S) -> dict:
    """Runs _fetch_chunk_worker in a separate PROCESS via run_process_bounded()
    -- Windows-safe, genuinely killable, unlike the old daemon-thread
    wrapper. IPC via an atomic temp result file, not a Queue -- avoids any
    pickling edge cases and matches this project's existing atomic-write
    convention."""
    fd, result_path = tempfile.mkstemp(suffix=".json", prefix="wiki_chunk_")
    os.close(fd)
    os.remove(result_path)  # worker creates it fresh, atomically; must not pre-exist as an empty file

    run_result = run_process_bounded(
        _fetch_chunk_worker, (article, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), result_path), timeout_s
    )
    elapsed = run_result["elapsed_s"]

    if not run_result["completed"]:
        terminated = run_result["terminated"]
        try:
            if os.path.exists(result_path):
                os.remove(result_path)
        except OSError:
            pass
        return {"status": "timeout", "terminated": terminated, "elapsed_s": elapsed,
                "http_status": None, "items": [], "error": f"timed out after {timeout_s:.0f}s",
                "retry_after": None, "network_elapsed_s": None}

    if os.path.exists(result_path):
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                result = json.load(f)
        except Exception as e:
            result = {"status": "malformed", "http_status": None, "items": [], "error": str(e),
                      "retry_after": None, "network_elapsed_s": None}
        finally:
            try:
                os.remove(result_path)
            except OSError:
                pass
    else:
        result = {"status": "no_result_file", "http_status": None, "items": [], "error":
                  "worker exited without writing a result", "retry_after": None, "network_elapsed_s": None}
    result["elapsed_s"] = elapsed
    result["terminated"] = False
    return result


# --- Orchestration ----------------------------------------------------------

def get_ticker_wikipedia_daily(ticker: str, article: str, start: date, end: date, today: date,
                                cache_df: pd.DataFrame, chunk_timeout_s: float = CHUNK_TIMEOUT_S,
                                fetch_fn=None) -> dict:
    """First pass only -- no inline retry. For each calendar-month chunk:
    use the cache if it's a closed month with a valid cached entry, else
    fetch once via fetch_chunk_isolated(). Failures are collected into a
    queue for the bounded second pass, NOT retried inline (this is the
    direct fix for the old code's mandatory 60s-per-404 tax).

    fetch_fn: injectable override for fetch_chunk_isolated, defaulting to
    the real one. Exists ONLY so tests can deterministically simulate
    success/404/timeout/malformed responses without a real network call or
    a real subprocess spawn per case -- see
    test_phase2_wikipedia_transport.py. Production code never passes this.

    Returns {"daily_rows": [...], "chunk_results": [...], "failed_chunks": [...]}.
    chunk_results carries per-chunk network_elapsed_s and sleep_s (always 0
    in this first pass) for logging, separately from each other -- see the
    RETRY POLICY requirement to log network vs. sleep time separately."""
    fetch_fn = fetch_fn or fetch_chunk_isolated
    chunks = calendar_month_chunks(start, end)
    daily_rows: list[dict] = []
    chunk_results: list[dict] = []
    failed_chunks: list[dict] = []

    for chunk_start, chunk_end in chunks:
        closed = not is_open_chunk(chunk_start, chunk_end, today)
        if closed:
            cached_rows = cached_daily_rows_for_chunk(cache_df, ticker, chunk_start, chunk_end)
            if cached_rows:
                daily_rows.extend(cached_rows)
                chunk_results.append({
                    "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
                    "source": "cache", "status": "ok", "network_elapsed_s": 0.0, "sleep_s": 0.0,
                })
                continue

        result = fetch_fn(article, chunk_start, chunk_end, timeout_s=chunk_timeout_s)
        chunk_results.append({
            "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
            "source": "fetch", "status": result["status"], "network_elapsed_s": result.get("network_elapsed_s") or 0.0,
            "sleep_s": 0.0, "http_status": result.get("http_status"), "terminated": result.get("terminated"),
            # Purely observational (2026-07-31): raw HTTP status was already
            # captured above; retry_after wasn't previously surfaced to the
            # chunk-level diagnostic log at all. Neither changes request
            # behavior, retries, or classification -- both are already
            # present on `result`, just not previously reported here.
            "retry_after": result.get("retry_after"),
        })
        if result["status"] == "ok" and result["items"]:
            now_utc = datetime.now(timezone.utc).isoformat()
            write_chunk_to_cache(ticker, article, None, None, chunk_start, chunk_end, result["items"],
                                  result.get("url", ""), result.get("http_status"), now_utc)
            daily_rows.extend(result["items"])
        else:
            failed_chunks.append({
                "ticker": ticker, "article": article, "chunk_start": chunk_start, "chunk_end": chunk_end,
                "last_status": result["status"], "retry_after": result.get("retry_after"),
                "last_http_status": result.get("http_status"),
            })

    return {"daily_rows": daily_rows, "chunk_results": chunk_results, "failed_chunks": failed_chunks}


def run_bounded_second_pass(failed_queue: list[dict], remaining_budget_s: float,
                             chunk_timeout_s: float = CHUNK_TIMEOUT_S, fetch_fn=None) -> dict:
    """Exactly one retry attempt per queued chunk, after normal ticker
    processing has finished for every ticker -- not per-ticker, not inline,
    not recursive. Short bounded jitter for ordinary failures; honors a real
    Retry-After header if it fits within remaining_budget_s and the
    SECOND_PASS_MAX_WAIT_FOR_RETRY_AFTER_S cap. No recursive splitting of a
    still-failing chunk -- it simply remains failed and is reported as such.

    fetch_fn: same injectable override as get_ticker_wikipedia_daily(), for
    deterministic testing only.

    Returns {"recovered": {ticker: [daily_rows...]}, "still_failed": [...],
    "chunk_results": [...]}."""
    fetch_fn = fetch_fn or fetch_chunk_isolated
    recovered: dict[str, list[dict]] = {}
    still_failed = []
    chunk_results = []
    budget_start = time.time()

    for item in failed_queue:
        elapsed_so_far = time.time() - budget_start
        if elapsed_so_far >= remaining_budget_s:
            still_failed.append({**item, "reason": "second_pass_budget_exhausted"})
            continue

        wait_s = 0.0
        if item.get("retry_after"):
            try:
                requested_wait = float(item["retry_after"])
                wait_s = min(requested_wait, SECOND_PASS_MAX_WAIT_FOR_RETRY_AFTER_S,
                             max(0.0, remaining_budget_s - elapsed_so_far))
            except (TypeError, ValueError):
                wait_s = random.uniform(*SECOND_PASS_JITTER_RANGE_S)
        else:
            wait_s = random.uniform(*SECOND_PASS_JITTER_RANGE_S)
        if wait_s > 0:
            time.sleep(wait_s)

        result = fetch_fn(item["article"], item["chunk_start"], item["chunk_end"],
                           timeout_s=chunk_timeout_s)
        chunk_results.append({
            "ticker": item["ticker"], "chunk_start": item["chunk_start"].isoformat(),
            "chunk_end": item["chunk_end"].isoformat(), "status": result["status"],
            "network_elapsed_s": result.get("network_elapsed_s") or 0.0, "sleep_s": wait_s,
            # Purely observational (2026-07-31): both already exist on
            # `result` and were already used internally (http_status is
            # written to cache on success; retry_after drives the honor-it
            # branch above) -- this just surfaces them to the diagnostic
            # log too. No retry/timing/classification behavior changes.
            "http_status": result.get("http_status"), "retry_after": result.get("retry_after"),
        })
        if result["status"] == "ok" and result["items"]:
            now_utc = datetime.now(timezone.utc).isoformat()
            write_chunk_to_cache(item["ticker"], item["article"], None, None, item["chunk_start"],
                                  item["chunk_end"], result["items"], result.get("url", ""),
                                  result.get("http_status"), now_utc)
            recovered.setdefault(item["ticker"], []).extend(result["items"])
        else:
            still_failed.append({**item, "reason": f"second_pass_also_failed:{result['status']}",
                                  "last_status": result["status"], "last_http_status": result.get("http_status")})

    return {"recovered": recovered, "still_failed": still_failed, "chunk_results": chunk_results}


def effective_open_chunk_data_end(chunk_end: date, today: date) -> date:
    """The completeness bar for a RECENT_LAST_KNOWN_GOOD fallback candidate,
    for the current/open chunk only. Capped at yesterday relative to
    `today` regardless of how late `chunk_end` (the requested end of the
    window) is -- see RECENT_CACHE_FALLBACK_DATA_LAG_DAYS: Wikipedia's own
    same-day pageview count is never complete yet, so a fresh request
    covering through "today" was never going to return today's row either.
    A completed CLOSED month's chunk_end already fully precedes today and
    is returned unchanged."""
    return min(chunk_end, today - timedelta(days=RECENT_CACHE_FALLBACK_DATA_LAG_DAYS))


def evaluate_recent_cache_fallback(cache_df: pd.DataFrame, ticker: str, article: str,
                                    chunk_start: date, chunk_end: date, today: date,
                                    now_utc: datetime, canonical_title: str | None = None,
                                    page_id: str | None = None) -> dict:
    """Evaluates whether a persisted cache snapshot for the CURRENT/OPEN
    chunk (ticker, chunk_start, chunk_end) may stand in as a
    RECENT_LAST_KNOWN_GOOD result after a fresh attempt AND the one bounded
    second-pass attempt have both already failed. This is a narrow,
    strictly-bounded fallback -- not a general staleness tolerance -- and
    every one of the following must hold, or eligible=False:

      1. a cached snapshot for this exact (ticker, chunk_start, chunk_end)
         key exists at all
      2. every row in it carries http_status == 200 (a real success, never
         an error response, never zero-filled/interpolated data -- those
         are structurally impossible here too, since write_chunk_to_cache()
         is only ever called on a genuine successful fetch with real items)
      3. configured_article_title (and, where independently resolved,
         canonical_title/page_id) matches the currently configured article
         for this ticker -- NOTE: this codebase does not independently
         resolve a canonical title/page ID per request (see module
         docstring), so those two sub-checks only fire when a caller
         explicitly supplies canonical_title/page_id to compare against;
         configured_article_title equality is always enforced and is the
         practically available form of this check today
      4. its content_hash verifies against a fresh recomputation over its
         own stored rows (corruption -> rejected, never silently trusted)
      5. it contains no duplicate dates
      6. every calendar date from chunk_start through the effective,
         lag-adjusted data-end date (see effective_open_chunk_data_end) is
         present -- exactly, not merely "some coverage"
      7. all pageview values are valid (non-negative integers)
      8. its last_verified_utc is no more than RECENT_CACHE_FALLBACK_MAX_AGE_HOURS
         old relative to now_utc

    Returns {"eligible": bool, "reason": str, "rows": [...],
    "retrieved_at_utc": str|None, "age_hours": float|None,
    "content_hash": str|None, "effective_data_end": date}. `rows` and the
    provenance fields are populated only when eligible=True. Never mutates
    cache_df or the on-disk cache -- purely a read-only evaluation."""
    effective_data_end = effective_open_chunk_data_end(chunk_end, today)

    if cache_df.empty:
        return {"eligible": False, "reason": "no_cache_at_all", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}

    mask = (
        (cache_df["ticker"] == ticker)
        & (cache_df["chunk_start"] == chunk_start.isoformat())
        & (cache_df["chunk_end"] == chunk_end.isoformat())
    )
    group = cache_df[mask]
    if group.empty:
        return {"eligible": False, "reason": "no_cached_snapshot_for_this_chunk", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}

    if not (group["http_status"].astype(str) == "200").all():
        return {"eligible": False, "reason": "cached_snapshot_not_from_a_real_http_200", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}

    if not (group["configured_article_title"] == article).all():
        return {"eligible": False, "reason": "configured_article_title_mismatch", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}
    if canonical_title:
        stored_canonical = set(group["canonical_title"].astype(str)) - {""}
        if stored_canonical and stored_canonical != {canonical_title}:
            return {"eligible": False, "reason": "canonical_title_mismatch", "rows": [],
                    "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                    "effective_data_end": effective_data_end}
    if page_id:
        stored_page_id = set(group["page_id"].astype(str)) - {""}
        if stored_page_id and stored_page_id != {str(page_id)}:
            return {"eligible": False, "reason": "page_id_mismatch", "rows": [],
                    "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                    "effective_data_end": effective_data_end}

    dates = list(group["date"])
    if len(dates) != len(set(dates)):
        return {"eligible": False, "reason": "duplicate_dates_in_cached_snapshot", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}

    rows = group[["date", "pageviews"]].to_dict("records")
    stored_hashes = group["content_hash"].unique()
    if len(stored_hashes) != 1:
        return {"eligible": False, "reason": "inconsistent_content_hash_within_snapshot", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}
    recomputed_hash = compute_chunk_hash(rows)
    if recomputed_hash != stored_hashes[0]:
        return {"eligible": False, "reason": "content_hash_verification_failed", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}

    try:
        pageviews_valid = all(int(r["pageviews"]) >= 0 for r in rows)
    except (TypeError, ValueError):
        pageviews_valid = False
    if not pageviews_valid:
        return {"eligible": False, "reason": "invalid_pageview_values", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}

    expected_dates = set()
    cursor = chunk_start
    while cursor <= effective_data_end:
        expected_dates.add(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)
    actual_dates = set(dates)
    if actual_dates != expected_dates:
        missing = sorted(expected_dates - actual_dates)
        extra = sorted(actual_dates - expected_dates)
        return {"eligible": False,
                "reason": f"incomplete_coverage_through_effective_data_end (missing={missing[:5]} extra={extra[:5]})",
                "rows": [], "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}

    verified_ts = group["last_verified_utc"].unique()
    if len(verified_ts) != 1:
        return {"eligible": False, "reason": "inconsistent_last_verified_utc_within_snapshot", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}
    try:
        retrieved_at = datetime.fromisoformat(str(verified_ts[0]))
    except (TypeError, ValueError):
        return {"eligible": False, "reason": "unparseable_last_verified_utc", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}
    age_hours = (now_utc - retrieved_at).total_seconds() / 3600.0
    if age_hours > RECENT_CACHE_FALLBACK_MAX_AGE_HOURS or age_hours < 0:
        return {"eligible": False,
                "reason": f"cache_too_old ({age_hours:.2f}h > {RECENT_CACHE_FALLBACK_MAX_AGE_HOURS}h)",
                "rows": [], "retrieved_at_utc": verified_ts[0], "age_hours": age_hours,
                "content_hash": None, "effective_data_end": effective_data_end}

    return {"eligible": True, "reason": "ok", "rows": rows,
            "retrieved_at_utc": verified_ts[0], "age_hours": age_hours,
            "content_hash": stored_hashes[0], "effective_data_end": effective_data_end}


def apply_recent_cache_fallback(still_failed: list[dict], cache_df: pd.DataFrame,
                                 today: date, now_utc: datetime) -> dict:
    """Runs AFTER the bounded second pass, on whatever remains in
    `still_failed`. Only ever considers items whose chunk IS the current
    open chunk (is_open_chunk) -- a closed month that failed both passes is
    never eligible for this fallback and is left in still_failed unchanged.
    Never writes to the cache (a failed refresh must never overwrite a
    valid prior snapshot, and a fallback usage must never reset that
    snapshot's own age/provenance -- both are structurally guaranteed by
    this function performing a pure read-only evaluation).

    Returns {"fallback_recovered": {ticker: {"rows": [...],
    "provenance": {...}}}, "still_failed": [...]} -- `still_failed` here
    contains every item NOT resolved by the fallback (closed-month failures
    unchanged, plus any open-month failures that didn't pass every gate,
    each annotated with "fallback_rejected_reason" for honest reporting)."""
    fallback_recovered: dict[str, dict] = {}
    remaining_failed = []

    for item in still_failed:
        if not is_open_chunk(item["chunk_start"], item["chunk_end"], today):
            remaining_failed.append(item)
            continue

        evaluation = evaluate_recent_cache_fallback(
            cache_df, item["ticker"], item["article"], item["chunk_start"], item["chunk_end"],
            today, now_utc,
        )
        if evaluation["eligible"]:
            fallback_recovered[item["ticker"]] = {
                "rows": evaluation["rows"],
                "provenance": {
                    "wiki_status": "complete_recent_cache_fallback",
                    "wiki_source_mode": "recent_last_known_good",
                    "wiki_fresh_request_failed": True,
                    "wiki_fresh_failure_category": item.get("last_status"),
                    "wiki_fresh_failure_http_status": item.get("last_http_status"),
                    "wiki_fallback_retrieved_at_utc": evaluation["retrieved_at_utc"],
                    "wiki_cache_age_hours": round(evaluation["age_hours"], 4),
                    "wiki_effective_data_end": evaluation["effective_data_end"].isoformat(),
                    "wiki_cache_content_hash": evaluation["content_hash"],
                },
            }
        else:
            remaining_failed.append({**item, "fallback_rejected_reason": evaluation["reason"]})

    return {"fallback_recovered": fallback_recovered, "still_failed": remaining_failed}


def assemble_daily_series(daily_rows: list[dict]) -> pd.DataFrame:
    """Same shape/semantics as the original fetch_daily_pageviews()'s return
    value: sorted, de-duplicated on date. Missing dates are simply absent
    (never zero-filled) -- unchanged from the existing, locked methodology's
    own gap-tolerant to_weekly() summation."""
    if not daily_rows:
        return pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "views": pd.Series(dtype="int64")})
    df = pd.DataFrame(daily_rows)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.rename(columns={"pageviews": "views"})
    df = df.dropna(subset=["date"]).drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    return df[["date", "views"]]
