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
#
# CACHE PERSISTENCE -- CORRECTED WORDING (2026-07-31): CACHE_PATH's CSV is
# persistent ACROSS LOCAL RUNS on the same machine (atomic writes, survives
# between invocations, accumulates over time) -- it is NOT currently
# repository-committed; it is deliberately untracked/excluded from git in
# this branch's commits so far (a partial run's accumulated cache is not a
# curated artifact). A future unattended workflow (e.g. GitHub Actions on a
# clean runner) must explicitly persist this file itself (checkout/restore
# it, or commit it as part of a scheduled job) -- nothing here does that
# automatically. The first cache seed intended for repository commit is the
# one produced by a validated COMPLETE 24/24 regression, reserved for
# Commit 3. Automation is not ready until cache persistence on a clean
# GitHub runner has actually been verified, not merely designed for.
#
# CORRECTIVE COMMIT (2026-07-31, following GitHub review of the prior two
# commits) -- five gaps closed, none touching request behavior, retries,
# budgets, chunk boundaries, fallback rules, z-score methodology, field
# definitions, ticker universe, or completeness policy:
#   1. validate_snapshot() is now the SINGLE shared validator used before
#      (a) writing a fresh HTTP-200 response to cache, (b) treating a fresh
#      response as successful, (c) reusing any closed-month cache entry
#      (via validated_cache_hit()), and (d) accepting the open-month
#      RECENT_LAST_KNOWN_GOOD fallback (evaluate_recent_cache_fallback()
#      now delegates to it). Previously each of these four sites had its
#      own ad hoc checks (or, for closed-month cache reuse, NO checks at
#      all beyond "the row exists") -- now they cannot silently drift
#      apart, and a closed-month cache entry that was valid when it was
#      still an OPEN month (e.g. fetched on the last day of that month,
#      covering only through the day before) is correctly rejected as
#      incomplete_coverage once that month closes and requires its final
#      day too, falling through to a fresh fetch rather than being reused
#      silently. verify_cache_integrity() -- previously exercised only by
#      tests, never called from production -- is now also invoked once per
#      get_ticker_wikipedia_daily() call as a whole-cache sanity pass, in
#      addition to validate_snapshot()'s own per-chunk hash re-verification
#      on every read.
#   2. get_ticker_wikipedia_daily() and run_bounded_second_pass() both now
#      accept/respect a wall-clock budget: run_bounded_second_pass()
#      recomputes remaining budget AFTER any wait (not just before), never
#      launches a request once usable budget is gone, and caps the
#      subprocess timeout to whatever budget actually remains rather than
#      always requesting the full chunk_timeout_s. get_ticker_wikipedia_daily()
#      accepts an optional remaining_budget_s and applies the same
#      discipline across a single ticker's first-pass chunk loop, so one
#      ticker's Wikipedia leg cannot materially eat into the total-run
#      deadline meant for the tickers after it.
#   3. Cache-identity honesty: canonical_title/page_id are NOT independently
#      resolved or verified anywhere in this codebase (no canonical-title
#      registry exists for the 24-ticker universe) -- only ticker +
#      configured_article_title are actually enforced on cache reuse/
#      fallback. Prior wording that implied canonical-title/page-ID
#      verification was happening has been corrected; the fields remain in
#      the cache schema (for a future registry) but are not currently a
#      checked gate.
#   4. Fixed above (budget capping) -- see item 2.
#   5. Fixed above (cache-persistence wording) -- see the CACHE PERSISTENCE
#      note directly above this one.

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
# Below this much usable time, a request can't meaningfully complete --
# don't launch it. Applies both between second-pass items (after any wait)
# and between first-pass chunks, so a caller-supplied remaining_budget_s
# genuinely bounds wall time rather than being checked once and ignored.
MIN_USABLE_CHUNK_BUDGET_S = 1.0

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


def validate_snapshot(ticker: str, article: str, chunk_start: date, chunk_end: date,
                       rows: list[dict], today: date,
                       stored_configured_article_title: str | None = None,
                       stored_content_hash: str | None = None) -> dict:
    """THE single shared validator for a (ticker, chunk) snapshot -- rows
    freshly fetched OR rows read from cache. Used before all four of:
    (1) writing a fresh HTTP-200 response to cache, (2) treating a fresh
    response as successful, (3) reusing any closed-month cache entry
    (via validated_cache_hit()), (4) accepting the open-month
    RECENT_LAST_KNOWN_GOOD fallback (evaluate_recent_cache_fallback()
    delegates here). One function so these four call sites cannot silently
    drift apart.

    Checks, in order (first failure wins):
      1. identity: stored_configured_article_title (if given) == article
      2. no duplicate dates
      3. every date parses as YYYYMMDD
      4. every pageviews value is a non-negative integer
      5. no date falls outside [chunk_start, chunk_end]
      6. content_hash recomputes cleanly; if stored_content_hash is given,
         it must match (a mismatch means tampered/corrupted cache data --
         this is the per-read integrity gate that makes corrupted,
         schema-valid cache data unable to bypass validation; see
         verify_cache_integrity() for the whole-cache-scan equivalent,
         also invoked in production now, not only in tests)
      7. exact expected date coverage:
         - closed chunk: every date chunk_start..chunk_end
         - open chunk: every date chunk_start..min(chunk_end, today-1)
         - special case: if the open chunk's coverage window hasn't
           started yet (today is at/near chunk_start, so today-1 <
           chunk_start -- e.g. the very first day of a new month), an
           EMPTY, non-error response is valid and classified
           "no_observations_expected_yet", never "incomplete_coverage"
           and never fabricated

    Returns {"valid": bool, "category": str, "reason": str,
    "content_hash": str|None, "expected_dates": set[str]}."""
    if stored_configured_article_title is not None and stored_configured_article_title != article:
        return {"valid": False, "category": "identity_mismatch",
                "reason": f"stored configured_article_title={stored_configured_article_title!r} "
                          f"!= currently configured {article!r} for {ticker}",
                "content_hash": None, "expected_dates": set()}

    dates = [r["date"] for r in rows]
    if len(dates) != len(set(dates)):
        return {"valid": False, "category": "duplicate_dates",
                "reason": "duplicate dates present in snapshot", "content_hash": None, "expected_dates": set()}

    parsed: dict = {}
    for d in dates:
        try:
            parsed[d] = datetime.strptime(str(d), "%Y%m%d").date()
        except (TypeError, ValueError):
            return {"valid": False, "category": "unparseable_date",
                    "reason": f"unparseable date {d!r}", "content_hash": None, "expected_dates": set()}

    for r in rows:
        try:
            pv = int(r["pageviews"])
        except (TypeError, ValueError):
            return {"valid": False, "category": "invalid_pageviews",
                    "reason": f"non-integer pageviews {r.get('pageviews')!r} for date {r.get('date')!r}",
                    "content_hash": None, "expected_dates": set()}
        if pv < 0:
            return {"valid": False, "category": "invalid_pageviews",
                    "reason": f"negative pageviews {pv} for date {r.get('date')!r}",
                    "content_hash": None, "expected_dates": set()}

    for d, dt in parsed.items():
        if dt < chunk_start or dt > chunk_end:
            return {"valid": False, "category": "date_outside_requested_range",
                    "reason": f"date {d} outside requested range "
                              f"{chunk_start.isoformat()}..{chunk_end.isoformat()}",
                    "content_hash": None, "expected_dates": set()}

    content_hash = compute_chunk_hash(rows)
    if stored_content_hash is not None and content_hash != stored_content_hash:
        return {"valid": False, "category": "content_hash_mismatch",
                "reason": f"stored={stored_content_hash} recomputed={content_hash} -- "
                          f"cache data tampered/corrupted",
                "content_hash": content_hash, "expected_dates": set()}

    closed = not is_open_chunk(chunk_start, chunk_end, today)
    coverage_end = chunk_end if closed else effective_open_chunk_data_end(chunk_end, today)

    if coverage_end < chunk_start:
        if rows:
            return {"valid": False, "category": "unexpected_data_before_coverage_start",
                    "reason": f"open chunk has {len(rows)} row(s) but no date could legitimately be "
                              f"published yet (coverage_end {coverage_end.isoformat()} < chunk_start "
                              f"{chunk_start.isoformat()})",
                    "content_hash": content_hash, "expected_dates": set()}
        return {"valid": True, "category": "no_observations_expected_yet",
                "reason": "open chunk, no date in range has a published pageview count yet "
                          "(today is at/near the start of this calendar month)",
                "content_hash": content_hash, "expected_dates": set()}

    expected_dates = set()
    cursor = chunk_start
    while cursor <= coverage_end:
        expected_dates.add(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)
    actual_dates = set(dates)
    if actual_dates != expected_dates:
        missing = sorted(expected_dates - actual_dates)
        extra = sorted(actual_dates - expected_dates)
        return {"valid": False, "category": "incomplete_coverage",
                "reason": f"missing={missing[:5]}{'...' if len(missing) > 5 else ''} "
                          f"extra={extra[:5]}{'...' if len(extra) > 5 else ''} "
                          f"(of {len(expected_dates)} expected dates through {coverage_end.isoformat()})",
                "content_hash": content_hash, "expected_dates": expected_dates}

    return {"valid": True, "category": "ok", "reason": "", "content_hash": content_hash,
            "expected_dates": expected_dates}


def validated_cache_hit(cache_df: pd.DataFrame, ticker: str, article: str,
                         chunk_start: date, chunk_end: date, today: date) -> dict:
    """THE single gate for reusing ANY closed-month cache entry -- delegates
    to validate_snapshot() for identity/hash/duplicate/pageview/coverage
    checks. A cache group that is schema-consistent but whose CONTENT has
    been tampered with, or that was a valid snapshot on a PRIOR day but no
    longer covers what TODAY requires (the open-to-closed rollover case: a
    month fetched while still open only has data through the day before
    it was fetched; once that month closes, it needs its own final day
    too), is correctly treated as a cache MISS here, never a corrupted or
    stale HIT -- the caller falls through to a fresh fetch either way.

    Returns {"hit": bool, "rows": [...], "validation": {...}}."""
    if cache_df.empty:
        return {"hit": False, "rows": [], "validation": {"category": "not_cached", "reason": "empty cache"}}
    mask = (
        (cache_df["ticker"] == ticker)
        & (cache_df["chunk_start"] == chunk_start.isoformat())
        & (cache_df["chunk_end"] == chunk_end.isoformat())
    )
    group = cache_df[mask]
    if group.empty:
        return {"hit": False, "rows": [], "validation": {"category": "not_cached", "reason": "no cached snapshot"}}

    titles = set(group["configured_article_title"])
    hashes = group["content_hash"].unique()
    if len(hashes) != 1:
        return {"hit": False, "rows": [], "validation": {
            "category": "inconsistent_content_hash_within_snapshot",
            "reason": f"cached group has {len(hashes)} distinct content_hash values"}}
    if len(titles) != 1:
        return {"hit": False, "rows": [], "validation": {
            "category": "inconsistent_configured_article_title_within_snapshot",
            "reason": f"cached group has {len(titles)} distinct configured_article_title values"}}

    rows = group[["date", "pageviews"]].to_dict("records")
    validation = validate_snapshot(ticker, article, chunk_start, chunk_end, rows, today,
                                    stored_configured_article_title=next(iter(titles)),
                                    stored_content_hash=hashes[0])
    if not validation["valid"]:
        return {"hit": False, "rows": [], "validation": validation}
    return {"hit": True, "rows": rows, "validation": validation}


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


def fetch_chunk_isolated(article: str, start: date, end: date, timeout_s: float = CHUNK_TIMEOUT_S,
                          worker=None) -> dict:
    """Runs _fetch_chunk_worker in a separate PROCESS via run_process_bounded()
    -- Windows-safe, genuinely killable, unlike the old daemon-thread
    wrapper. IPC via an atomic temp result file, not a Queue -- avoids any
    pickling edge cases and matches this project's existing atomic-write
    convention.

    worker: injectable override for _fetch_chunk_worker, defaulting to the
    real one. Exists ONLY so tests can prove genuine real-subprocess timeout
    enforcement (e.g. a deliberately-hanging worker under a tiny caller-
    supplied budget) without depending on live Wikipedia network calls --
    see test_phase2_wikipedia_transport.py. Production code never passes
    this."""
    worker = worker or _fetch_chunk_worker
    fd, result_path = tempfile.mkstemp(suffix=".json", prefix="wiki_chunk_")
    os.close(fd)
    os.remove(result_path)  # worker creates it fresh, atomically; must not pre-exist as an empty file

    run_result = run_process_bounded(
        worker, (article, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), result_path), timeout_s
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
                                fetch_fn=None, remaining_budget_s: float | None = None) -> dict:
    """First pass only -- no inline retry. For each calendar-month chunk:
    use the cache if it's a closed month with a VALIDATED cached entry
    (validated_cache_hit() -- identity, hash, and exact-coverage all
    re-checked on every read, so a corrupted or now-stale-relative-to-today
    cache row can never silently pass as a hit), else fetch once via
    fetch_chunk_isolated(). A fresh HTTP-200 response is itself validated
    (validate_snapshot()) before being trusted or cached -- an incomplete
    or malformed 200 is never cached and never treated as success. Failures
    are collected into a queue for the bounded second pass, NOT retried
    inline (this is the direct fix for the old code's mandatory
    60s-per-404 tax).

    fetch_fn: injectable override for fetch_chunk_isolated, defaulting to
    the real one. Exists ONLY so tests can deterministically simulate
    success/404/timeout/malformed responses without a real network call or
    a real subprocess spawn per case -- see
    test_phase2_wikipedia_transport.py. Production code never passes this.

    remaining_budget_s: optional wall-clock budget for THIS ticker's first
    pass. When given, each chunk's fetch timeout is capped to whatever
    budget actually remains, and once usable budget runs out, every
    remaining chunk is recorded as failed ("first_pass_budget_exhausted",
    queued for the run-level bounded second pass) without launching further
    requests -- so one ticker's Wikipedia leg cannot materially eat into
    the total-run deadline meant for the tickers after it. None (default)
    means unbounded, matching prior behavior exactly.

    Returns {"daily_rows": [...], "chunk_results": [...], "failed_chunks": [...],
    "cache_integrity_problems": [...]}. cache_integrity_problems is a
    whole-cache verify_cache_integrity() scan, informational (validated_cache_hit()
    is the authoritative per-chunk gate regardless). chunk_results carries
    per-chunk network_elapsed_s and sleep_s (always 0 in this first pass)
    for logging, separately from each other -- see the RETRY POLICY
    requirement to log network vs. sleep time separately."""
    fetch_fn = fetch_fn or fetch_chunk_isolated
    chunks = calendar_month_chunks(start, end)
    daily_rows: list[dict] = []
    chunk_results: list[dict] = []
    failed_chunks: list[dict] = []
    cache_integrity_problems = verify_cache_integrity(cache_df) if not cache_df.empty else []

    loop_start = time.time()
    for chunk_start, chunk_end in chunks:
        if remaining_budget_s is not None:
            budget_left = remaining_budget_s - (time.time() - loop_start)
            if budget_left < MIN_USABLE_CHUNK_BUDGET_S:
                failed_chunks.append({
                    "ticker": ticker, "article": article, "chunk_start": chunk_start, "chunk_end": chunk_end,
                    "last_status": "first_pass_budget_exhausted", "retry_after": None, "last_http_status": None,
                })
                chunk_results.append({
                    "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
                    "source": "skipped", "status": "first_pass_budget_exhausted",
                    "network_elapsed_s": 0.0, "sleep_s": 0.0,
                })
                continue
            effective_chunk_timeout = min(chunk_timeout_s, budget_left)
        else:
            effective_chunk_timeout = chunk_timeout_s

        closed = not is_open_chunk(chunk_start, chunk_end, today)
        if closed:
            hit = validated_cache_hit(cache_df, ticker, article, chunk_start, chunk_end, today)
            if hit["hit"]:
                daily_rows.extend(hit["rows"])
                chunk_results.append({
                    "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
                    "source": "cache", "status": "ok", "network_elapsed_s": 0.0, "sleep_s": 0.0,
                })
                continue
            # Cache MISS -- never cached, OR cached-but-failed-validation
            # (e.g. the open-to-closed rollover case: a snapshot that was
            # complete while this chunk was still open no longer covers
            # what a now-closed month requires). Either way, fall through
            # to a fresh fetch.

        result = fetch_fn(article, chunk_start, chunk_end, timeout_s=effective_chunk_timeout)
        base_chunk_result = {
            "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
            "source": "fetch", "network_elapsed_s": result.get("network_elapsed_s") or 0.0,
            "sleep_s": 0.0, "http_status": result.get("http_status"), "terminated": result.get("terminated"),
            "retry_after": result.get("retry_after"),
        }

        if result["status"] == "ok":
            validation = validate_snapshot(ticker, article, chunk_start, chunk_end, result["items"], today)
            if validation["category"] == "no_observations_expected_yet":
                chunk_results.append({**base_chunk_result, "status": "no_observations_expected_yet"})
                continue
            if validation["valid"]:
                now_utc = datetime.now(timezone.utc).isoformat()
                write_chunk_to_cache(ticker, article, None, None, chunk_start, chunk_end, result["items"],
                                      result.get("url", ""), result.get("http_status"), now_utc)
                daily_rows.extend(result["items"])
                chunk_results.append({**base_chunk_result, "status": "ok"})
                continue
            # A nonempty HTTP 200 that fails validation (e.g. incomplete
            # coverage) is NEVER cached and NEVER treated as success --
            # queued for the bounded second pass like any other failure.
            chunk_results.append({**base_chunk_result, "status": validation["category"]})
            failed_chunks.append({
                "ticker": ticker, "article": article, "chunk_start": chunk_start, "chunk_end": chunk_end,
                "last_status": f"validation:{validation['category']}", "retry_after": result.get("retry_after"),
                "last_http_status": result.get("http_status"),
            })
            continue

        chunk_results.append({**base_chunk_result, "status": result["status"]})
        failed_chunks.append({
            "ticker": ticker, "article": article, "chunk_start": chunk_start, "chunk_end": chunk_end,
            "last_status": result["status"], "retry_after": result.get("retry_after"),
            "last_http_status": result.get("http_status"),
        })

    return {"daily_rows": daily_rows, "chunk_results": chunk_results, "failed_chunks": failed_chunks,
            "cache_integrity_problems": cache_integrity_problems}


def run_bounded_second_pass(failed_queue: list[dict], remaining_budget_s: float,
                             chunk_timeout_s: float = CHUNK_TIMEOUT_S, fetch_fn=None,
                             today: date | None = None) -> dict:
    """Exactly one retry attempt per queued chunk, after normal ticker
    processing has finished for every ticker -- not per-ticker, not inline,
    not recursive. Short bounded jitter for ordinary failures; honors a real
    Retry-After header if it fits within remaining_budget_s and the
    SECOND_PASS_MAX_WAIT_FOR_RETRY_AFTER_S cap. No recursive splitting of a
    still-failing chunk -- it simply remains failed and is reported as such.

    Genuinely bounded (2026-07-31 correction): remaining budget is
    recomputed AFTER any wait, not just before it -- a request is never
    launched once usable budget is gone, and the subprocess timeout passed
    to fetch_fn is capped to whatever budget actually remains (never the
    full chunk_timeout_s regardless of how little time is left).

    fetch_fn: same injectable override as get_ticker_wikipedia_daily(), for
    deterministic testing only.

    today: date used for validate_snapshot()'s coverage check on a
    recovered response. Defaults to the real current UTC date if omitted
    (matches prior behavior for existing callers that don't pass it).

    Returns {"recovered": {ticker: [daily_rows...]}, "still_failed": [...],
    "chunk_results": [...]}."""
    fetch_fn = fetch_fn or fetch_chunk_isolated
    effective_today = today if today is not None else datetime.now(timezone.utc).date()
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
        # Never sleep past the remaining budget either.
        wait_s = max(0.0, min(wait_s, max(0.0, remaining_budget_s - elapsed_so_far)))
        if wait_s > 0:
            time.sleep(wait_s)

        # Recompute remaining budget AFTER the wait. Do not launch a
        # request if no usable budget remains, and cap the subprocess
        # timeout to whatever budget actually remains.
        remaining_after_wait = remaining_budget_s - (time.time() - budget_start)
        if remaining_after_wait < MIN_USABLE_CHUNK_BUDGET_S:
            still_failed.append({**item, "reason": "second_pass_budget_exhausted_after_wait"})
            continue
        capped_timeout = min(chunk_timeout_s, remaining_after_wait)

        result = fetch_fn(item["article"], item["chunk_start"], item["chunk_end"],
                           timeout_s=capped_timeout)
        chunk_results.append({
            "ticker": item["ticker"], "chunk_start": item["chunk_start"].isoformat(),
            "chunk_end": item["chunk_end"].isoformat(), "status": result["status"],
            "network_elapsed_s": result.get("network_elapsed_s") or 0.0, "sleep_s": wait_s,
            "http_status": result.get("http_status"), "retry_after": result.get("retry_after"),
            "timeout_s_used": capped_timeout,
        })
        if result["status"] == "ok":
            validation = validate_snapshot(item["ticker"], item["article"], item["chunk_start"],
                                            item["chunk_end"], result["items"], effective_today)
            if validation["category"] == "no_observations_expected_yet":
                continue   # nothing to recover, but not a failure either
            if validation["valid"]:
                now_utc = datetime.now(timezone.utc).isoformat()
                write_chunk_to_cache(item["ticker"], item["article"], None, None, item["chunk_start"],
                                      item["chunk_end"], result["items"], result.get("url", ""),
                                      result.get("http_status"), now_utc)
                recovered.setdefault(item["ticker"], []).extend(result["items"])
            else:
                still_failed.append({**item, "reason": f"second_pass_also_failed:validation:{validation['category']}",
                                      "last_status": f"validation:{validation['category']}",
                                      "last_http_status": result.get("http_status")})
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
    strictly-bounded fallback -- not a general staleness tolerance.
    Delegates identity/hash/duplicate/pageview-validity/exact-coverage
    checks to validate_snapshot() (the same shared gate used for fresh
    writes and closed-month cache reuse, so this fallback cannot silently
    apply a looser standard) and layers its own two fallback-specific
    checks on top:

      - HTTP-200 provenance: every row in the snapshot must carry
        http_status == 200 (structurally already guaranteed by
        write_chunk_to_cache() only ever being called on a genuine
        success, but re-checked here defensively)
      - recency: its last_verified_utc must be no more than
        RECENT_CACHE_FALLBACK_MAX_AGE_HOURS old relative to now_utc

    canonical_title/page_id: OPTIONAL, best-effort cross-checks only. This
    codebase does NOT independently resolve or verify a canonical article
    title or Wikipedia page ID for any of the 24 Phase 2 tickers -- no
    identity registry exists. These parameters only have any effect when a
    caller explicitly supplies them AND the cache row happens to have a
    non-blank stored value for that field (which production writes never
    populate today -- see write_chunk_to_cache()'s canonical_title/page_id
    always being None in every production call site). The only identity
    check actually enforced in production is ticker + configured article
    title, via validate_snapshot(). Documented here plainly rather than
    implying stronger verification than exists.

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

    titles = set(group["configured_article_title"])
    hashes = group["content_hash"].unique()
    if len(hashes) != 1:
        return {"eligible": False, "reason": "inconsistent_content_hash_within_snapshot", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}
    if len(titles) != 1:
        return {"eligible": False, "reason": "inconsistent_configured_article_title_within_snapshot", "rows": [],
                "retrieved_at_utc": None, "age_hours": None, "content_hash": None,
                "effective_data_end": effective_data_end}

    rows = group[["date", "pageviews"]].to_dict("records")
    validation = validate_snapshot(ticker, article, chunk_start, chunk_end, rows, today,
                                    stored_configured_article_title=next(iter(titles)),
                                    stored_content_hash=hashes[0])
    if not validation["valid"]:
        return {"eligible": False, "reason": f"validation_failed:{validation['category']}:{validation['reason']}",
                "rows": [], "retrieved_at_utc": None, "age_hours": None,
                "content_hash": validation.get("content_hash"), "effective_data_end": effective_data_end}

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
            "content_hash": validation["content_hash"], "effective_data_end": effective_data_end}


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
