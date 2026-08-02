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
import math
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
# ONLY to the chunk currently at the frontier of measured data
# availability (see is_open_chunk(..., watermark) usage below), and ONLY
# after a fresh attempt AND the one bounded second-pass attempt have both
# already failed. See evaluate_recent_cache_fallback()'s docstring for the
# full gate list.
RECENT_CACHE_FALLBACK_MAX_AGE_HOURS = 24.0

# --- MEASURED WIKIPEDIA DATA WATERMARK (2026-08-01) -----------------------
#
# WHY THIS REPLACES THE FIXED today-1 ASSUMPTION: the 2026-08-01 24-ticker
# regression (run within ~3.5 hours of July closing) came back PARTIAL,
# wiki_zscore 0/24 -- every ticker's now-closed July chunk required all 31
# days, but Wikipedia had not yet published July 31 for ANY article at the
# time of that run (independently confirmed via direct probe, both
# per-article and aggregate endpoints -- see
# Live Signal Engine/Phase2 Failure Evidence/2026-08-01_Wikipedia_SourceWatermark_Lag2/).
# A fixed "yesterday is always published" assumption is simply false on a
# real, measured, 2-day-lag day. This is not a workaround or a staleness
# waiver -- it establishes EXACTLY what information was available at the
# retrieval timestamp, once, at run start, and enforces exact coverage
# through that measured boundary for every chunk, open or closed alike (a
# "closed" calendar month's own last day can be just as unpublished as an
# "open" month's).
#
# The watermark is resolved ONCE per run (resolve_wiki_data_watermark()),
# frozen, and threaded through every consumer: fresh-response validation,
# closed/open cache validation, the bounded second pass, the recent-cache
# fallback, deterministic equivalence testing, and completion gating. It is
# measured against the SITE-WIDE AGGREGATE pageviews endpoint (not a
# per-article one) specifically because per-article, per-request-shape
# flakiness is independently documented throughout this investigation (a
# single-day per-article probe can 404 even when a wider range covering
# the same date succeeds) -- the aggregate endpoint gave a clean,
# non-flaky, reproducible signal in the Phase B feasibility probe.
WIKI_AGGREGATE_API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/"
                      "en.wikipedia.org/all-access/user/daily/{start}/{end}")
# Locked per the approved design -- do not raise without a fresh review.
# A watermark that can't be resolved within this many days back leaves the
# run's Wikipedia leg entirely unresolved (PARTIAL), not guessed.
MAX_ACCEPTABLE_WIKI_LAG_DAYS = 3
# A 404 gets exactly ONE bounded confirmation re-probe (a single retry,
# short fixed wait) before the watermark resolver moves to the next-older
# candidate -- guards against one transient blip being mistaken for
# genuine unavailability, without resurrecting the old unbounded
# retry-forever behavior.
WATERMARK_404_CONFIRM_WAIT_S = 2.0
WATERMARK_MAX_RETRY_AFTER_WAIT_S = 30.0


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


def is_open_chunk(chunk_start: date, chunk_end: date, reference_date: date) -> bool:
    """Whether `reference_date` falls inside [chunk_start, chunk_end] --
    i.e. this chunk is currently AT THE FRONTIER relative to whatever
    `reference_date` represents. Historically called with the real
    calendar "today" (the chunk containing today is still accumulating
    data); now called with the measured watermark instead (see
    apply_recent_cache_fallback()) -- the watermark, not the calendar, is
    what actually determines whether a chunk's boundary is still "live"."""
    return chunk_start <= reference_date <= chunk_end


def required_data_end(chunk_end: date, watermark: date) -> date:
    """The measured completeness bar for ANY chunk -- open or closed
    alike. Replaces the old fixed today-1 assumption: never request or
    expect data beyond the run-level measured watermark, regardless of how
    far in the future chunk_end nominally extends, and regardless of
    whether the chunk is the calendar-current month or a fully historical
    one -- a "closed" month's own last day can be just as unpublished as
    an "open" month's (see the 2026-08-01 rollover PARTIAL, root-caused to
    exactly this)."""
    return min(chunk_end, watermark)


def _fetch_aggregate_day(candidate: date) -> dict:
    """Real network call (default, overridable for tests): single-day
    probe of the SITE-WIDE aggregate pageviews endpoint (NOT a per-article
    one -- avoids the per-article/per-request-shape flakiness documented
    throughout this investigation; a single-day per-article probe can 404
    even when a wider range covering the same date succeeds, confirmed
    directly during the Phase B feasibility probe). Requires the
    timestamp format this endpoint actually expects: YYYYMMDD + "00" (an
    hour component) -- NOT the plain YYYYMMDD the per-article endpoint
    uses; confirmed empirically before relying on it.

    Returns {"status": "ok"/"http_error"/"malformed"/"exception",
    "http_status": int|None, "views": int|None, "url": str,
    "retry_after": str|None, "network_elapsed_s": float|None}."""
    ymd = candidate.strftime("%Y%m%d") + "00"
    url = WIKI_AGGREGATE_API.format(start=ymd, end=ymd)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; GST project)"})
    result = {"status": "error", "http_status": None, "views": None, "url": url,
              "retry_after": None, "network_elapsed_s": None}
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.load(resp)
            result["network_elapsed_s"] = time.time() - t0
            result["http_status"] = resp.status
            items = body.get("items", [])
            match = next((it for it in items if it.get("timestamp") == ymd), None)
            if match is not None and _is_valid_nonnegative_integer_pageviews(match.get("views")):
                result["status"] = "ok"
                result["views"] = int(float(match["views"]))
            else:
                result["status"] = "malformed"
    except urllib.error.HTTPError as e:
        result["network_elapsed_s"] = time.time() - t0
        result["http_status"] = e.code
        result["retry_after"] = e.headers.get("Retry-After")
        result["status"] = "http_error"
    except Exception as e:
        result["network_elapsed_s"] = time.time() - t0
        result["status"] = "exception"
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def resolve_wiki_data_watermark(anchor_date: date, fetch_fn=None, now_utc: datetime | None = None) -> dict:
    """Resolves the SINGLE run-level Wikipedia data watermark, ONCE, at
    run start, before any ticker is processed. This is not a waiver or a
    stale-data workaround -- it establishes exactly what information was
    genuinely available (per the site-wide aggregate endpoint) at the
    retrieval timestamp.

    Probes candidate dates anchor_date-1, anchor_date-2, anchor_date-3
    (newest to oldest, capped at MAX_ACCEPTABLE_WIKI_LAG_DAYS). The first
    candidate that returns a genuine HTTP-200 with the exact expected
    timestamp and a valid non-negative integer view count becomes the
    frozen watermark.

    - A 404 gets exactly ONE bounded confirmation re-probe (short fixed
      wait) before moving to the next-older candidate.
    - A 429 honors a bounded Retry-After (capped) and retries the SAME
      candidate once -- a rate limit says nothing about data availability,
      so it must never be treated as "move to an older date".
    - Any OTHER unresolved outcome (network exception, non-404/429 HTTP
      status, malformed response, or a repeat failure after the 429 retry)
      FAILS THE WATERMARK CLOSED immediately -- never interpreted as "this
      date is simply unpublished". An ambiguous failure must not silently
      walk the watermark backward.
    - If no candidate within MAX_ACCEPTABLE_WIKI_LAG_DAYS resolves (every
      one confirmed 404), the watermark fails with status
      "no_data_within_max_lag" -- the run's Wikipedia leg is entirely
      unresolved this run (PARTIAL), never guessed.

    fetch_fn: injectable override for _fetch_aggregate_day, for
    deterministic testing only. Production never passes this.

    Returns {"status": "ok"/"no_data_within_max_lag"/"failed_closed",
    "watermark_date": date|None, "lag_days": int|None,
    "retrieved_at_utc": str, "source_url": str|None, "http_status": int|None,
    "probe_log": [...]}. This exact dict (or watermark_date/lag_days from
    it) is what every consumer downstream must be given -- never
    recomputed per ticker."""
    fetch_fn = fetch_fn or _fetch_aggregate_day
    now_utc = now_utc or datetime.now(timezone.utc)
    probe_log = []

    def _log(candidate, lag, attempt, result):
        probe_log.append({"candidate": candidate.isoformat(), "lag_days": lag, "attempt": attempt,
                           "status": result.get("status"), "http_status": result.get("http_status"),
                           "retry_after": result.get("retry_after"),
                           "network_elapsed_s": result.get("network_elapsed_s"), "url": result.get("url")})

    for lag in range(1, MAX_ACCEPTABLE_WIKI_LAG_DAYS + 1):
        candidate = anchor_date - timedelta(days=lag)
        result = fetch_fn(candidate)
        _log(candidate, lag, "first", result)

        if result["status"] == "http_error" and result.get("http_status") == 429:
            try:
                wait_s = (min(float(result["retry_after"]), WATERMARK_MAX_RETRY_AFTER_WAIT_S)
                          if result.get("retry_after") else WATERMARK_MAX_RETRY_AFTER_WAIT_S)
            except (TypeError, ValueError):
                wait_s = WATERMARK_MAX_RETRY_AFTER_WAIT_S
            if wait_s > 0:
                time.sleep(wait_s)
            result = fetch_fn(candidate)
            _log(candidate, lag, "after_retry_after", result)

        if result["status"] == "http_error" and result.get("http_status") == 404:
            time.sleep(WATERMARK_404_CONFIRM_WAIT_S)
            result = fetch_fn(candidate)
            _log(candidate, lag, "confirmation", result)

        if result["status"] == "ok":
            return {"status": "ok", "watermark_date": candidate, "lag_days": lag,
                    "retrieved_at_utc": now_utc.isoformat(), "source_url": result.get("url"),
                    "http_status": result.get("http_status"), "probe_log": probe_log}

        if result["status"] == "http_error" and result.get("http_status") == 404:
            # Confirmed unavailable after one bounded re-probe -- move to
            # the next-older candidate.
            continue

        # Anything else (exception, malformed, non-404/429 HTTP status, or
        # a repeat failure after honoring Retry-After) is an AMBIGUOUS
        # failure -- fail the watermark closed immediately rather than
        # guessing this date is simply unpublished.
        return {"status": "failed_closed", "watermark_date": None, "lag_days": None,
                "retrieved_at_utc": now_utc.isoformat(), "source_url": result.get("url"),
                "http_status": result.get("http_status"), "probe_log": probe_log,
                "failure_reason": result["status"]}

    return {"status": "no_data_within_max_lag", "watermark_date": None, "lag_days": None,
            "retrieved_at_utc": now_utc.isoformat(), "source_url": None, "http_status": None,
            "probe_log": probe_log}


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


def _is_valid_nonnegative_integer_pageviews(value) -> bool:
    """Accepts genuinely integer-valued pageview counts: real ints,
    integer-valued floats (5.0), and integer-valued numeric strings ("5",
    "5.0") -- rejects fractional values (1.5, "1.5"), NaN, +/-infinity,
    booleans, and negatives. Plain `int(value)` is NOT enough: it silently
    truncates 1.5 to 1 and silently accepts True as 1 -- both wrong for a
    pageview count that must be an honest integer, never coerced."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 0
    if isinstance(value, float):
        return math.isfinite(value) and value.is_integer() and value >= 0
    if isinstance(value, str):
        try:
            f = float(value.strip())
        except (TypeError, ValueError):
            return False
        return math.isfinite(f) and f.is_integer() and f >= 0
    return False


def validate_snapshot(ticker: str, article: str, chunk_start: date, chunk_end: date,
                       rows: list[dict], watermark: date,
                       stored_configured_article_title: str | None = None,
                       stored_content_hash: str | None = None) -> dict:
    """THE single shared validator for a (ticker, chunk) snapshot -- rows
    freshly fetched OR rows read from cache. Used before all four of:
    (1) writing a fresh HTTP-200 response to cache, (2) treating a fresh
    response as successful, (3) reusing any closed-month cache entry
    (via validated_cache_hit()), (4) accepting the recent-cache fallback
    (evaluate_recent_cache_fallback() delegates here). One function so
    these four call sites cannot silently drift apart.

    Checks, in order (first failure wins):
      1. identity: stored_configured_article_title (if given) == article
      2. no duplicate dates
      3. every date parses as YYYYMMDD
      4. every pageviews value is a genuinely non-negative integer -- see
         _is_valid_nonnegative_integer_pageviews(): integer-valued floats
         (5.0) and integer-valued numeric strings ("5") are accepted,
         fractional values (1.5, "1.5"), NaN, +/-infinity, booleans, and
         negatives are rejected, never silently coerced (plain int(value)
         would silently truncate 1.5 to 1 and accept True as 1 -- both
         wrong)
      5. no date falls outside [chunk_start, chunk_end]
      6. content_hash recomputes cleanly; if stored_content_hash is given,
         it must match (a mismatch means tampered/corrupted cache data --
         this is the per-read integrity gate that makes corrupted,
         schema-valid cache data unable to bypass validation; see
         verify_cache_integrity() for the whole-cache-scan equivalent,
         also invoked in production now, not only in tests)
      7. exact expected date coverage through `required_data_end(chunk_end,
         watermark)` -- applied UNIFORMLY to every chunk, open or closed
         (2026-08-01 correction: a fixed "closed chunks always need their
         own chunk_end" assumption is exactly what caused the 2026-08-01
         PARTIAL -- a closed month's own last day can be just as
         unpublished as an open month's; the measured watermark is now the
         single source of truth for both). Special case: if the required
         coverage window hasn't started yet (required_data_end <
         chunk_start -- e.g. the watermark hasn't reached this chunk at
         all), an EMPTY, non-error response is valid and classified
         "no_observations_expected_yet", never "incomplete_coverage" and
         never fabricated.

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
        if not _is_valid_nonnegative_integer_pageviews(r.get("pageviews")):
            return {"valid": False, "category": "invalid_pageviews",
                    "reason": f"pageviews value {r.get('pageviews')!r} for date {r.get('date')!r} is not "
                              f"a genuinely non-negative integer -- fractional, NaN, infinite, boolean, "
                              f"and negative values are rejected, never silently coerced",
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

    coverage_end = required_data_end(chunk_end, watermark)

    if coverage_end < chunk_start:
        if rows:
            return {"valid": False, "category": "unexpected_data_before_coverage_start",
                    "reason": f"chunk has {len(rows)} row(s) but the measured watermark "
                              f"({watermark.isoformat()}) hasn't reached this chunk yet "
                              f"(coverage_end {coverage_end.isoformat()} < chunk_start "
                              f"{chunk_start.isoformat()})",
                    "content_hash": content_hash, "expected_dates": set()}
        return {"valid": True, "category": "no_observations_expected_yet",
                "reason": f"no date in range has a published pageview count yet as of the measured "
                          f"watermark ({watermark.isoformat()})",
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
                         chunk_start: date, chunk_end: date, watermark: date) -> dict:
    """THE single gate for reusing ANY cache entry -- delegates to
    validate_snapshot() for identity/hash/duplicate/pageview/coverage
    checks, against the SAME frozen run-level watermark used everywhere
    else. A cache group that is schema-consistent but whose CONTENT has
    been tampered with, or that was a valid snapshot against an EARLIER
    watermark but no longer covers what the CURRENT watermark requires
    (the rollover case: a month fetched when the watermark only reached
    day N doesn't cover day N+1 once the watermark advances there), is
    correctly treated as a cache MISS here, never a corrupted or stale
    HIT -- the caller falls through to a fresh fetch either way.

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
    validation = validate_snapshot(ticker, article, chunk_start, chunk_end, rows, watermark,
                                    stored_configured_article_title=next(iter(titles)),
                                    stored_content_hash=hashes[0])
    if not validation["valid"]:
        return {"hit": False, "rows": [], "validation": validation}
    return {"hit": True, "rows": rows, "validation": validation}


def attempt_cache_union_reconstruction(cache_df: pd.DataFrame, ticker: str, article: str,
                                        chunk_start: date, req_end: date, watermark: date) -> dict:
    """Conservative, read-only fallback for a CLOSED historical interval
    whose exact (ticker, chunk_start, chunk_end) cache key misses,
    attempted BEFORE any network request -- the caller must never invoke
    this for the open/current chunk (see is_open_chunk() gating at the
    call site in get_ticker_wikipedia_daily()); that path is unchanged:
    live-first, then the existing recent_last_known_good fallback only
    after both a fresh fetch and the bounded second pass have failed.

    Motivating case (2026-08-02): a ticker's oldest rolling-lookback chunk
    shifts its chunk_start forward by one day on every run, so it can
    never hit the exact-key cache even though the underlying calendar
    dates were already fetched and validated under yesterday's (or an
    earlier) chunk boundary -- forcing a daily re-fetch against a
    documented-flaky per-article endpoint for data that, for a closed
    historical month, will never change again.

    Reconstructs the required date range from a day-level UNION of
    already-validated cache rows for the same ticker+configured article,
    regardless of which (chunk_start, chunk_end) key they were originally
    fetched under. Fails closed (returns hit=False) unless ALL of:
      1. Every calendar date in [chunk_start, req_end] is present in the
         union -- no partial-coverage union is ever accepted.
      2. Every contributing row carries http_status == 200, a non-null
         content_hash, and a genuinely nonnegative-integer pageviews value
         (_is_valid_nonnegative_integer_pageviews()).
      3. If more than one cached row exists for the same date, they must
         agree EXACTLY on pageviews -- any disagreement fails the WHOLE
         reconstruction closed for this interval, never averaged or
         arbitrarily picked.
      4. No contributing date is later than `watermark` (defensive -- by
         construction req_end <= watermark already, via required_data_end()
         at the call site, but checked again here independently).

    Never writes anything back to the cache -- this is a read-only,
    derived view over already-validated data, not a new network
    observation, and must never be persisted as though it were one (see
    the call site: no write_chunk_to_cache() call follows a union hit).

    Returns {"hit": bool, "rows": [...], "provenance": {...} | None}. On a
    hit, provenance carries wiki_source_mode="cache_union_reconstruction",
    every contributing (chunk_start, chunk_end) key, every distinct
    contributing content_hash, and every distinct contributing
    last_verified_utc timestamp, so a recovered chunk is fully auditable."""
    if cache_df.empty:
        return {"hit": False, "rows": [], "provenance": None}

    needed_dates: list[date] = []
    d = chunk_start
    while d <= req_end:
        needed_dates.append(d)
        d += timedelta(days=1)
    needed_date_strs = {d.strftime("%Y%m%d") for d in needed_dates}
    if not needed_date_strs:
        return {"hit": False, "rows": [], "provenance": None}

    candidates = cache_df[
        (cache_df["ticker"] == ticker)
        & (cache_df["configured_article_title"] == article)
        & (cache_df["http_status"] == 200)
        & (cache_df["date"].isin(needed_date_strs))
    ]
    if candidates.empty:
        return {"hit": False, "rows": [], "provenance": None}

    # Belt-and-suspenders watermark exclusion, independent of the fact
    # that needed_dates itself never extends past req_end (<= watermark
    # by construction at the call site) -- never trust a single boundary
    # check alone for "no post-watermark observation may enter."
    candidates = candidates[candidates["date"].apply(
        lambda s: datetime.strptime(str(s), "%Y%m%d").date() <= watermark)]
    if candidates.empty:
        return {"hit": False, "rows": [], "provenance": None}

    # "Retain valid ... hash" means each contributing row's PARENT chunk
    # group must itself be internally hash-consistent -- the same
    # recompute-and-compare check verify_cache_integrity() runs over the
    # whole cache, applied here per candidate group. A group whose stored
    # hash doesn't match a hash recomputed from its OWN full row set is
    # excluded entirely (its rows never contribute), not silently trusted
    # just because one field happens to be non-null.
    candidate_groups = {(r["chunk_start"], r["chunk_end"]) for _, r in candidates.iterrows()}
    hash_valid_groups = set()
    for cs, ce in candidate_groups:
        full_group = cache_df[
            (cache_df["ticker"] == ticker) & (cache_df["chunk_start"] == cs) & (cache_df["chunk_end"] == ce)
        ]
        stored_hashes = full_group["content_hash"].unique()
        if len(stored_hashes) != 1 or not stored_hashes[0]:
            continue
        recomputed = compute_chunk_hash(full_group[["date", "pageviews"]].to_dict("records"))
        if recomputed == stored_hashes[0]:
            hash_valid_groups.add((cs, ce))
    candidates = candidates[candidates.apply(
        lambda r: (r["chunk_start"], r["chunk_end"]) in hash_valid_groups, axis=1)]
    if candidates.empty:
        return {"hit": False, "rows": [], "provenance": None}

    resolved_rows: dict[str, dict] = {}
    for _, r in candidates.iterrows():
        if not _is_valid_nonnegative_integer_pageviews(r.get("pageviews")):
            continue
        if not r.get("content_hash"):
            continue
        date_str = str(r["date"])
        pv = int(float(r["pageviews"]))
        existing = resolved_rows.get(date_str)
        if existing is not None:
            if existing["pageviews"] != pv:
                # Disagreement across contributing snapshots -- fail the
                # WHOLE reconstruction closed, not just this one date.
                return {"hit": False, "rows": [], "provenance": {
                    "rejected_reason": "conflicting_pageviews_across_cached_chunks",
                    "conflict_date": date_str,
                }}
            continue
        resolved_rows[date_str] = {
            "date": date_str, "pageviews": pv,
            "chunk_start": r["chunk_start"], "chunk_end": r["chunk_end"],
            "content_hash": r["content_hash"], "last_verified_utc": r.get("last_verified_utc"),
        }

    if not needed_date_strs.issubset(resolved_rows.keys()):
        missing = sorted(needed_date_strs - resolved_rows.keys())
        return {"hit": False, "rows": [], "provenance": {
            "rejected_reason": "incomplete_union_coverage",
            "missing_dates": missing,
        }}

    ordered_dates = sorted(needed_date_strs)
    rows = [{"date": ds, "pageviews": resolved_rows[ds]["pageviews"]} for ds in ordered_dates]
    contributing_keys = sorted({(resolved_rows[ds]["chunk_start"], resolved_rows[ds]["chunk_end"])
                                 for ds in ordered_dates})
    contributing_hashes = sorted({resolved_rows[ds]["content_hash"] for ds in ordered_dates})
    contributing_timestamps = sorted({resolved_rows[ds]["last_verified_utc"] for ds in ordered_dates
                                       if resolved_rows[ds]["last_verified_utc"]})
    provenance = {
        "wiki_source_mode": "cache_union_reconstruction",
        "contributing_chunk_keys": contributing_keys,
        "contributing_content_hashes": contributing_hashes,
        "contributing_retrieval_timestamps": contributing_timestamps,
        "reconstructed_at_utc": datetime.now(timezone.utc).isoformat(),
        "date_count": len(rows),
    }
    return {"hit": True, "rows": rows, "provenance": provenance}


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

def get_ticker_wikipedia_daily(ticker: str, article: str, start: date, end: date, watermark: date,
                                cache_df: pd.DataFrame, chunk_timeout_s: float = CHUNK_TIMEOUT_S,
                                fetch_fn=None, remaining_budget_s: float | None = None) -> dict:
    """First pass only -- no inline retry. For each calendar-month chunk,
    the completeness bar is `required_data_end(chunk_end, watermark)` --
    the SAME frozen, run-level watermark passed to every other consumer,
    applied uniformly whether the chunk is calendar-open or calendar-closed
    (2026-08-01 correction: a "closed" chunk's own last day can be just as
    unpublished as an "open" chunk's -- see resolve_wiki_data_watermark()'s
    module-level docstring for the incident this replaces).

    For each chunk: if the watermark hasn't reached chunk_start yet, no
    request is made at all (no_observations_expected_yet). Otherwise, try
    a VALIDATED cache hit (validated_cache_hit() -- identity, hash, and
    exact-coverage against the CURRENT watermark all re-checked on every
    read, so a snapshot valid against an earlier watermark can never
    silently pass once the watermark has advanced). On a cache miss, fetch
    ONLY chunk_start..required_data_end -- NEVER request dates beyond the
    measured watermark. A fresh HTTP-200 response is itself validated
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
        req_end = required_data_end(chunk_end, watermark)

        # PROSPECTIVE no_observations_expected_yet check: if the measured
        # watermark hasn't reached this chunk at all, no request is made
        # -- zero cost, no cache write, no failed chunk, independent of
        # any remaining_budget_s (it costs nothing either way).
        if req_end < chunk_start:
            chunk_results.append({
                "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
                "source": "not_requested", "status": "no_observations_expected_yet",
                "network_elapsed_s": 0.0, "sleep_s": 0.0,
            })
            continue

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

        hit = validated_cache_hit(cache_df, ticker, article, chunk_start, chunk_end, watermark)
        if hit["hit"]:
            daily_rows.extend(hit["rows"])
            chunk_results.append({
                "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
                "source": "cache", "status": "ok", "network_elapsed_s": 0.0, "sleep_s": 0.0,
            })
            continue
        # Cache MISS -- never cached, OR cached-but-failed-validation
        # against the current watermark (the rollover case: a snapshot
        # valid against an earlier, smaller watermark no longer covers
        # what the current, advanced watermark requires). Either way, fall
        # through to a fresh fetch, requesting ONLY chunk_start..req_end --
        # never beyond the measured watermark.

        # CLOSED-HISTORICAL-INTERVAL cache-union reconstruction (2026-08-02
        # addition): tried only for a chunk that is NOT the open/current
        # one, and only before the network request below -- never for the
        # open chunk, whose behavior is deliberately unchanged (live-first,
        # then the existing recent_last_known_good fallback later). See
        # attempt_cache_union_reconstruction() for the full acceptance
        # rules (exact coverage, HTTP-200/identity/hash/pageview validity
        # per contributing row, conflict-fails-closed, watermark exclusion).
        # Never writes to the cache -- a read-only reconstruction only.
        if not is_open_chunk(chunk_start, chunk_end, watermark):
            union = attempt_cache_union_reconstruction(cache_df, ticker, article, chunk_start, req_end, watermark)
            if union["hit"]:
                daily_rows.extend(union["rows"])
                chunk_results.append({
                    "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
                    "source": "cache_union_reconstruction", "status": "ok",
                    "network_elapsed_s": 0.0, "sleep_s": 0.0,
                    "cache_union_provenance": union["provenance"],
                })
                continue

        result = fetch_fn(article, chunk_start, req_end, timeout_s=effective_chunk_timeout)
        base_chunk_result = {
            "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
            "source": "fetch", "network_elapsed_s": result.get("network_elapsed_s") or 0.0,
            "sleep_s": 0.0, "http_status": result.get("http_status"), "terminated": result.get("terminated"),
            "retry_after": result.get("retry_after"),
        }

        if result["status"] == "ok":
            validation = validate_snapshot(ticker, article, chunk_start, chunk_end, result["items"], watermark)
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


def run_bounded_second_pass(failed_queue: list[dict], remaining_budget_s: float, watermark: date,
                             chunk_timeout_s: float = CHUNK_TIMEOUT_S, fetch_fn=None) -> dict:
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

    watermark: the SAME frozen run-level watermark used everywhere else --
    REQUIRED, no default. A retry here must never request or validate
    against a different completeness bar than the first pass used; each
    queued item's original chunk_end is re-truncated to
    required_data_end(chunk_end, watermark) before the retry request is
    made, exactly as the first pass did.

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

        req_end = required_data_end(item["chunk_end"], watermark)
        result = fetch_fn(item["article"], item["chunk_start"], req_end,
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
                                            item["chunk_end"], result["items"], watermark)
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


def evaluate_recent_cache_fallback(cache_df: pd.DataFrame, ticker: str, article: str,
                                    chunk_start: date, chunk_end: date, watermark: date,
                                    now_utc: datetime, canonical_title: str | None = None,
                                    page_id: str | None = None) -> dict:
    """Evaluates whether a persisted cache snapshot for the chunk currently
    AT THE FRONTIER of measured data availability (see
    apply_recent_cache_fallback()'s is_open_chunk(..., watermark) gating)
    may stand in as a RECENT_LAST_KNOWN_GOOD result after a fresh attempt
    AND the one bounded second-pass attempt have both already failed. This
    is a narrow, strictly-bounded fallback -- not a general staleness
    tolerance. Delegates identity/hash/duplicate/pageview-validity/
    exact-coverage checks to validate_snapshot() (the same shared gate
    used for fresh writes and cache reuse, against the SAME frozen
    watermark, so this fallback cannot silently apply a looser standard)
    and layers its own two fallback-specific checks on top:

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
    effective_data_end = required_data_end(chunk_end, watermark)

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
    validation = validate_snapshot(ticker, article, chunk_start, chunk_end, rows, watermark,
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
                                 watermark: date, now_utc: datetime) -> dict:
    """Runs AFTER the bounded second pass, on whatever remains in
    `still_failed`. Only ever considers items whose chunk currently
    CONTAINS the frozen watermark (is_open_chunk(chunk_start, chunk_end,
    watermark) -- the watermark, not the calendar, is what determines
    which chunk is "at the frontier" now) -- a chunk fully behind or fully
    ahead of the watermark is never eligible for this fallback and is left
    in still_failed unchanged. Never writes to the cache (a failed refresh
    must never overwrite a valid prior snapshot, and a fallback usage must
    never reset that snapshot's own age/provenance -- both are
    structurally guaranteed by this function performing a pure read-only
    evaluation).

    Returns {"fallback_recovered": {ticker: {"rows": [...],
    "provenance": {...}}}, "still_failed": [...]} -- `still_failed` here
    contains every item NOT resolved by the fallback (chunks outside the
    watermark's frontier unchanged, plus any frontier-chunk failures that
    didn't pass every gate, each annotated with "fallback_rejected_reason"
    for honest reporting)."""
    fallback_recovered: dict[str, dict] = {}
    remaining_failed = []

    for item in still_failed:
        if not is_open_chunk(item["chunk_start"], item["chunk_end"], watermark):
            remaining_failed.append(item)
            continue

        evaluation = evaluate_recent_cache_fallback(
            cache_df, item["ticker"], item["article"], item["chunk_start"], item["chunk_end"],
            watermark, now_utc,
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
