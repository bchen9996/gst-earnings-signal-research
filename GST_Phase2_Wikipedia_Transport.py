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
import threading
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

# --- PER-ARTICLE AVAILABILITY MEASUREMENT (2026-08-05, REDESIGNED same day) --
# The aggregate endpoint answers "has en.wikipedia.org published day D
# site-wide?". It does NOT answer "has THIS article's daily row for day D been
# published?" -- two different publication pipelines. The 2026-08-05 PARTIAL
# proved the gap: the aggregate reported 2026-08-04 while only 5 of the 24
# locked articles contained that date.
#
# The FIRST attempt at closing that gap (commit 9990c39) measured availability
# with a separate fixed-14-day per-article probe. A read-only live diagnostic
# proved that design release-blocking on two counts before it ever ran a panel
# (Live Signal Engine/Phase2 Failure Evidence/
# 2026-08-05_EffectiveWatermark_Probe_Design_Failure/):
#
#   1. 24 unpaced requests reach Wikimedia's rate limiter at request 11
#      (14x HTTP 429, Retry-After counting down 39->20s) -> measured=9/24 ->
#      failed closed -> EVERY run PARTIAL, strictly worse than before.
#   2. Availability is REQUEST-SHAPE-DEPENDENT. The same date is present in one
#      range's response and absent from another's, for the same article,
#      seconds apart (ADBE and GOOGL both return 2026-08-04 for 07-22..08-04
#      but NOT for 08-01..08-04) -- consistent with URL-keyed CDN response
#      caching, each range URL being a separate cache entry with its own age.
#
# Consequence: "the latest date article X has published" is NOT a property of
# the article. It is a property of (article, requested range). A probe using
# one request shape can never certify what a differently-shaped retrieval
# request will return -- no amount of pacing fixes that.
#
# The separate probe is therefore DELETED, not tuned. Availability is now
# measured from the SAME RESPONSE production will actually use: a single
# anchor-month calendar-chunk request per ticker, whose observations are then
# sliced to the common effective watermark and reused in memory. See
# retrieve_anchor_month_availability() and resolve_effective_panel_watermark().

EFFECTIVE_WATERMARK_METHOD = "min_anchor_month_observed_latest_same_response"

# Global pacing for the Stage-1 anchor-month sweep. Evidence from the
# 2026-08-05 diagnostic: 10 requests at ~1.44s spacing (~0.7 req/s) triggered
# 429 at request 11; 38 consecutive requests at ~3.5s spacing produced zero
# 429s. 3.5s is the smallest interval this project has direct evidence for.
AVAILABILITY_MIN_REQUEST_INTERVAL_S = 3.5
# One bounded re-attempt per ticker on 429, after honoring a capped
# Retry-After. A second 429 fails the ticker -- and therefore the panel --
# closed. Never walks the watermark backward to dodge a rate limit.
AVAILABILITY_MAX_429_RETRIES = 1
AVAILABILITY_MAX_RETRY_AFTER_WAIT_S = 60.0


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


class SharedRequestLimiter:
    """The SINGLE pacing gate for the Stage-1 anchor-month sweep.

    Why one shared object rather than a sleep inside the loop: the 2026-08-05
    diagnostic showed the failure mode is a GLOBAL request rate against
    Wikimedia, not a per-ticker one. Any code path that can issue an
    anchor-month request -- the sweep itself and its bounded 429 re-attempt --
    must pass through this same instance, so their combined rate is bounded,
    not each independently.

    Subprocess note: fetch_chunk_isolated() spawns one worker process per
    request and that worker issues EXACTLY ONE HTTP request. The limiter is
    therefore held in the parent and acquired BEFORE the spawn, which bounds
    every request that can reach the network. A worker cannot issue an
    unpaced second request because it never issues a second request at all.

    Thread-safe (Lock) so this property survives if the sweep is ever moved
    off a single thread.
    """

    def __init__(self, min_interval_s: float = AVAILABILITY_MIN_REQUEST_INTERVAL_S,
                 sleep_fn=None, clock_fn=None):
        self.min_interval_s = min_interval_s
        self._sleep = sleep_fn or time.sleep
        self._clock = clock_fn or time.monotonic
        self._lock = threading.Lock()
        self._next_allowed_at = None
        self.request_count = 0
        self.waits: list[dict] = []

    def acquire(self, reason: str = "") -> float:
        """Blocks until the next request is allowed. Returns seconds waited."""
        with self._lock:
            now = self._clock()
            waited = 0.0
            if self._next_allowed_at is not None and now < self._next_allowed_at:
                waited = self._next_allowed_at - now
                self._sleep(waited)
                now = self._clock()
            self.request_count += 1
            self._next_allowed_at = now + self.min_interval_s
            self.waits.append({"request_number": self.request_count,
                               "waited_s": round(waited, 3), "reason": reason})
            return waited

    def note_retry_after(self, retry_after_s) -> float:
        """Honors a server-supplied Retry-After by pushing the shared gate out,
        capped at AVAILABILITY_MAX_RETRY_AFTER_WAIT_S. Applies to EVERY
        subsequent caller, not just the one that was throttled -- a 429 is a
        statement about the whole client, not one request."""
        try:
            wait_s = min(float(retry_after_s), AVAILABILITY_MAX_RETRY_AFTER_WAIT_S)
        except (TypeError, ValueError):
            wait_s = AVAILABILITY_MAX_RETRY_AFTER_WAIT_S
        wait_s = max(0.0, wait_s)
        with self._lock:
            candidate = self._clock() + wait_s
            if self._next_allowed_at is None or candidate > self._next_allowed_at:
                self._next_allowed_at = candidate
        return wait_s


def anchor_month_start(watermark: date) -> date:
    """First day of the calendar month containing the aggregate watermark.
    This is the anchor month -- the month whose publication frontier is what
    trailing availability is actually about."""
    return watermark.replace(day=1)


def validate_anchor_month_response(ticker: str, article: str, month_start: date,
                                    requested_end: date, items: list[dict]) -> dict:
    """Structural usability gate for a Stage-1 anchor-month response.

    DELIBERATELY NOT validate_snapshot(). validate_snapshot() requires exact
    coverage THROUGH a known watermark; that is the wrong question here,
    because a trailing shortfall is precisely the thing being measured. What
    this function requires instead:

      - at least one observation;
      - every pageviews value structurally valid (non-negative integer) --
        the same check validate_snapshot() applies, and the ONLY predicate
        applied to a count anywhere in availability measurement;
      - no date outside [month_start, requested_end] -- a response containing
        a date we did not ask for is not trustworthy;
      - no duplicate dates, and no conflicting values for a repeated date;
      - the sequence BEGINS at month_start -- a response that starts late is
        missing interior history, not merely trailing;
      - the sequence is CONTIGUOUS daily through its own maximum observed
        date -- no interior holes.

    A response may legitimately stop short of requested_end. That trailing
    shortfall is the measurement, not an error (see the module note on
    request-shape-dependent availability). An INTERIOR hole is always an
    error and can never be forgiven by lowering the panel watermark, because
    lowering a trailing edge cannot reach inside the sequence.

    Returns {"usable": bool, "latest_available_date": date|None,
    "observed_count": int, "reason": str, "category": str}."""
    base = {"usable": False, "latest_available_date": None, "observed_count": 0}

    if not items:
        return {**base, "category": "empty", "reason": "no observations in response"}

    seen: dict[date, object] = {}
    for item in items:
        if not isinstance(item, dict):
            return {**base, "category": "malformed", "reason": f"non-dict item: {item!r}"}
        raw_views = item.get("pageviews")
        if not _is_valid_nonnegative_integer_pageviews(raw_views):
            return {**base, "category": "malformed",
                    "reason": f"invalid pageviews value {raw_views!r} for date {item.get('date')!r}"}
        try:
            d = datetime.strptime(str(item.get("date")), "%Y%m%d").date()
        except (TypeError, ValueError):
            return {**base, "category": "malformed",
                    "reason": f"unparseable date {item.get('date')!r}"}
        if d < month_start or d > requested_end:
            return {**base, "category": "out_of_range",
                    "reason": f"date {d.isoformat()} outside requested "
                              f"{month_start.isoformat()}..{requested_end.isoformat()}"}
        if d in seen:
            if seen[d] != raw_views:
                return {**base, "category": "conflicting_duplicate",
                        "reason": f"date {d.isoformat()} repeated with conflicting values "
                                  f"({seen[d]!r} vs {raw_views!r})"}
            return {**base, "category": "duplicate",
                    "reason": f"date {d.isoformat()} appears more than once"}
        seen[d] = raw_views

    observed = sorted(seen)
    if observed[0] != month_start:
        return {**base, "observed_count": len(observed), "category": "does_not_start_at_month_start",
                "reason": f"first observation {observed[0].isoformat()} != anchor month start "
                          f"{month_start.isoformat()} -- interior history missing, not trailing lag"}

    expected_n = (observed[-1] - observed[0]).days + 1
    if len(observed) != expected_n:
        present = set(observed)
        missing = [(observed[0] + timedelta(days=i)).isoformat()
                   for i in range(expected_n)
                   if (observed[0] + timedelta(days=i)) not in present]
        return {**base, "observed_count": len(observed), "category": "internal_gap",
                "reason": f"internal missing date(s) {missing[:5]}"
                          f"{'...' if len(missing) > 5 else ''} within "
                          f"{observed[0].isoformat()}..{observed[-1].isoformat()}"}

    return {"usable": True, "latest_available_date": observed[-1],
            "observed_count": len(observed), "reason": "", "category": "ok"}


def retrieve_anchor_month_availability(tickers: list[str], ticker_to_article: dict,
                                        aggregate_watermark: date, fetch_fn=None,
                                        limiter: "SharedRequestLimiter | None" = None,
                                        timeout_s: float = CHUNK_TIMEOUT_S,
                                        max_429_retries: int = AVAILABILITY_MAX_429_RETRIES) -> dict:
    """STAGE 1. For every locked ticker, issue exactly ONE anchor-month
    calendar-chunk request:

        anchor_month_start(aggregate_watermark) .. aggregate_watermark

    Never through wall-clock today, never past the aggregate watermark. This
    is the same request shape whose observations production then uses -- that
    identity is the whole point of the redesign, so the response that measures
    availability IS the response that supplies the data.

    All requests pass through one shared limiter (see SharedRequestLimiter).
    On HTTP 429 the server's Retry-After is honored (capped) via that same
    shared gate and the request is re-attempted at most max_429_retries times;
    a still-throttled ticker fails closed rather than being skipped or
    downgraded.

    FAILS CLOSED per ticker on: missing article mapping, non-ok transport,
    non-200 HTTP, 404, exhausted 429, empty/malformed payload, or any
    structural problem from validate_anchor_month_response(). The caller must
    treat any failure as "the panel has no honest shared bar this run" -- the
    aggregate watermark is never substituted, no other request shape is
    tried, and no cached magnitude data is consulted.

    Returns {"month_start", "requested_end", "results": [...],
    "responses": {ticker: [rows]}, "usable_count", "expected_count",
    "failures": [...], "request_count", "pacing_waits": [...]}.
    `responses` holds the raw validated rows IN MEMORY for Stage-2 reuse --
    nothing here is written to the cache (see resolve_effective_panel_watermark
    for why caching a trailing-short response would be a lie)."""
    fetch_fn = fetch_fn or fetch_chunk_isolated
    limiter = limiter or SharedRequestLimiter()
    month_start = anchor_month_start(aggregate_watermark)
    requested_end = aggregate_watermark

    results, responses, failures = [], {}, []
    for ticker in sorted(tickers):
        article = ticker_to_article.get(ticker)
        rec = {"ticker": ticker, "article": article,
               "requested_start": month_start, "requested_end": requested_end,
               "status": "unusable", "latest_available_date": None, "reason": "",
               "http_status": None, "retry_after": None, "observed_count": 0,
               "attempts": 0, "network_elapsed_s": None}

        if not article:
            rec["reason"] = "no_article_mapping"
            results.append(rec)
            failures.append({"ticker": ticker, "reason": rec["reason"], "http_status": None})
            continue

        result = None
        for attempt in range(max_429_retries + 1):
            limiter.acquire(reason=f"{ticker}:attempt{attempt + 1}")
            rec["attempts"] = attempt + 1
            result = fetch_fn(article, month_start, requested_end, timeout_s)
            rec["http_status"] = result.get("http_status")
            rec["retry_after"] = result.get("retry_after")
            rec["network_elapsed_s"] = result.get("network_elapsed_s")
            if result.get("http_status") == 429 and attempt < max_429_retries:
                limiter.note_retry_after(result.get("retry_after"))
                continue
            break

        if result.get("status") != "ok":
            rec["reason"] = (f"transport_{result.get('status')}"
                             f"{':' + str(result.get('http_status')) if result.get('http_status') else ''}")
            results.append(rec)
            failures.append({"ticker": ticker, "reason": rec["reason"],
                             "http_status": result.get("http_status")})
            continue
        if result.get("http_status") != 200:
            rec["reason"] = f"http_status_not_200:{result.get('http_status')}"
            results.append(rec)
            failures.append({"ticker": ticker, "reason": rec["reason"],
                             "http_status": result.get("http_status")})
            continue

        validation = validate_anchor_month_response(ticker, article, month_start,
                                                     requested_end, result.get("items") or [])
        if not validation["usable"]:
            rec["reason"] = f"{validation['category']}: {validation['reason']}"
            rec["observed_count"] = validation["observed_count"]
            results.append(rec)
            failures.append({"ticker": ticker, "reason": rec["reason"],
                             "http_status": result.get("http_status")})
            continue

        rec.update({"status": "ok", "latest_available_date": validation["latest_available_date"],
                    "observed_count": validation["observed_count"], "reason": ""})
        results.append(rec)
        responses[ticker] = list(result.get("items") or [])

    return {"month_start": month_start, "requested_end": requested_end,
            "results": results, "responses": responses,
            "usable_count": len(responses), "expected_count": len(tickers),
            "failures": failures, "request_count": limiter.request_count,
            "pacing_waits": limiter.waits}


def slice_rows_to_watermark(rows: list[dict], watermark: date) -> list[dict]:
    """Drops observations dated after `watermark`. Pure filtering: it never
    adds, zero-fills, interpolates, or reorders a value, so a sliced response
    contains only rows the source actually returned."""
    out = []
    for r in rows:
        try:
            d = datetime.strptime(str(r.get("date")), "%Y%m%d").date()
        except (TypeError, ValueError):
            continue
        if d <= watermark:
            out.append(r)
    return out


def resolve_effective_panel_watermark(tickers: list[str], ticker_to_article: dict,
                                       aggregate_watermark_info: dict | None = None,
                                       fetch_fn=None, limiter=None,
                                       timeout_s: float = CHUNK_TIMEOUT_S,
                                       now_utc: datetime | None = None,
                                       stage1: dict | None = None) -> dict:
    """STAGE 2. Computes the single panel-wide effective watermark from the
    Stage-1 anchor-month responses, then slices and REUSES those same
    responses -- no second anchor-month request is ever issued.

        effective_panel_watermark = min(anchor-month latest observed date)
                                    over ALL tickers in the locked universe

    Taking the minimum is what makes one shared date safe: it is, by
    construction, a date every article demonstrably returned IN THE VERY
    RESPONSE production will use. That last clause is what the deleted
    14-day probe could not provide (see the module note) -- measurement and
    retrieval are now the same observation, so they cannot disagree.

    Every ticker in a run then uses this identical date for pull_start,
    expected coverage, z-score anchoring and provenance. Per-ticker watermarks
    are never used: different anchor dates inside one panel would make the
    cross-section incomparable.

    SCOPE, unchanged from the first attempt: this removes only TRAILING
    unpublished dates. Each sliced response must still have EXACT daily
    coverage from anchor_month_start through the effective watermark, and
    every chunk before the anchor month keeps its existing exact-coverage,
    cache-integrity, cache-union and bounded-subchunk rules untouched. An
    interior historical gap sits below the effective watermark, is untouched
    by lowering it, and still produces PARTIAL.

    The aggregate watermark is retained as a source-health / provenance
    observation and as the Stage-1 request bound (an UPPER bound only). It is
    never treated as proof of per-article publication and never raises the
    effective watermark.

    FAILS CLOSED if any ticker's anchor-month response is unusable, or if any
    sliced response lacks exact coverage through the effective watermark. A
    minimum over a subset is not a panel watermark.

    stage1: an already-executed retrieve_anchor_month_availability() result,
    for callers that want to inspect Stage 1 separately. Omitted in normal
    use -- this function runs Stage 1 itself.

    Returns the Stage-1 provenance plus {"status", "effective_panel_watermark_date",
    "method", "aggregate_watermark_date", "aggregate_vs_panel_lag_days",
    "per_ticker_latest", "binding_tickers", "anchor_month_rows", ...}.
    anchor_month_rows holds the SLICED, exactly-validated rows per ticker, kept
    IN MEMORY for reuse by get_ticker_wikipedia_daily(). They are deliberately
    NOT written to the cache: a response that stops short of the aggregate
    watermark, stored under a chunk key ending at that watermark, would assert
    a completeness it does not have."""
    now_utc = now_utc or datetime.now(timezone.utc)
    aggregate_watermark_info = aggregate_watermark_info or {}
    aggregate_date = aggregate_watermark_info.get("watermark_date")

    base = {"method": EFFECTIVE_WATERMARK_METHOD, "aggregate_watermark_date": aggregate_date,
            "resolved_at_utc": now_utc.isoformat(), "expected_count": len(tickers),
            "effective_panel_watermark_date": None, "aggregate_vs_panel_lag_days": None,
            "per_ticker_latest": {}, "binding_tickers": [], "anchor_month_rows": {},
            "anchor_month_start": None, "anchor_month_requested_end": None,
            "stage1_results": [], "measured_count": 0, "unmeasured": [],
            "request_count": 0, "pacing_waits": [], "second_anchor_month_request_issued": False}

    if aggregate_date is None:
        return {**base, "status": "failed_closed",
                "failure_reason": "no aggregate watermark -- Stage-1 request bound is undefined"}

    if stage1 is None:
        stage1 = retrieve_anchor_month_availability(
            tickers, ticker_to_article, aggregate_date, fetch_fn=fetch_fn,
            limiter=limiter, timeout_s=timeout_s)

    base.update({"anchor_month_start": stage1["month_start"],
                 "anchor_month_requested_end": stage1["requested_end"],
                 "stage1_results": stage1["results"],
                 "measured_count": stage1["usable_count"],
                 "unmeasured": stage1["failures"],
                 "request_count": stage1["request_count"],
                 "pacing_waits": stage1["pacing_waits"]})

    if stage1["failures"] or stage1["usable_count"] != len(tickers):
        return {**base, "status": "failed_closed",
                "failure_reason": (f"{len(stage1['failures'])} of {len(tickers)} ticker(s) produced no "
                                    f"usable anchor-month response -- a minimum over a subset is not a "
                                    f"panel watermark")}

    per_ticker_latest = {r["ticker"]: r["latest_available_date"]
                         for r in stage1["results"] if r["status"] == "ok"}
    effective = min(per_ticker_latest.values())

    # Reuse: slice each ALREADY-RETRIEVED response. No new request.
    sliced, coverage_failures = {}, []
    month_start = stage1["month_start"]
    for ticker, rows in stage1["responses"].items():
        kept = slice_rows_to_watermark(rows, effective)
        check = validate_anchor_month_response(ticker, ticker_to_article.get(ticker),
                                                month_start, effective, kept)
        if not check["usable"] or check["latest_available_date"] != effective:
            coverage_failures.append({
                "ticker": ticker,
                "reason": (check["reason"] or
                           f"sliced response ends {check['latest_available_date']}, "
                           f"expected exactly {effective.isoformat()}"),
                "category": check["category"]})
            continue
        sliced[ticker] = kept

    if coverage_failures:
        return {**base, "status": "failed_closed", "per_ticker_latest": per_ticker_latest,
                "unmeasured": base["unmeasured"] + coverage_failures,
                "failure_reason": (f"{len(coverage_failures)} ticker(s) lack exact coverage from "
                                    f"{month_start.isoformat()} through the effective watermark "
                                    f"{effective.isoformat()}")}

    return {**base, "status": "ok",
            "effective_panel_watermark_date": effective,
            "aggregate_vs_panel_lag_days": (aggregate_date - effective).days,
            "per_ticker_latest": per_ticker_latest,
            "binding_tickers": sorted(t for t, d in per_ticker_latest.items() if d == effective),
            "anchor_month_rows": sliced}



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
    #
    # The full-group re-lookup below MUST also filter on
    # configured_article_title, not just (ticker, chunk_start, chunk_end)
    # -- two different article mappings for the SAME ticker (e.g. an older,
    # superseded TICKER_TO_WIKI_ARTICLE entry) can otherwise share an
    # identical chunk-boundary key. Without the article filter here, the
    # "full group" pulled for hash recomputation would silently mix rows
    # from both articles, almost certainly breaking the hash match (or,
    # worse, coincidentally NOT breaking it) -- an identity leak this
    # function must never allow even though `candidates` itself was
    # already filtered to `article` above.
    candidate_groups = {(r["chunk_start"], r["chunk_end"]) for _, r in candidates.iterrows()}
    hash_valid_groups = set()
    for cs, ce in candidate_groups:
        full_group = cache_df[
            (cache_df["ticker"] == ticker)
            & (cache_df["configured_article_title"] == article)
            & (cache_df["chunk_start"] == cs)
            & (cache_df["chunk_end"] == ce)
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
                                fetch_fn=None, remaining_budget_s: float | None = None,
                                prefetched_chunk_rows: dict | None = None) -> dict:
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

    prefetched_chunk_rows (2026-08-05): {(chunk_start, chunk_end): rows}
    already retrieved this run and already validated, supplied IN MEMORY --
    currently the Stage-1 anchor-month response (see
    retrieve_anchor_month_availability()). A matching chunk is satisfied from
    these rows with NO second network request and NO cache write: the rows are
    sliced to the effective panel watermark and so stop short of their chunk's
    nominal end, which is exactly what must never be persisted under a key
    implying coverage through that end. They are still put through
    validate_snapshot() below like any other source -- reuse is not a trust
    shortcut.

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

        prefetched = (prefetched_chunk_rows or {}).get((chunk_start, chunk_end))
        if prefetched is not None:
            reuse_validation = validate_snapshot(ticker, article, chunk_start, chunk_end,
                                                  prefetched, watermark)
            if reuse_validation["valid"]:
                daily_rows.extend(prefetched)
                chunk_results.append({
                    "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
                    "source": "anchor_month_stage1", "status": "ok",
                    "network_elapsed_s": 0.0, "sleep_s": 0.0,
                })
                continue
            failed_chunks.append({
                "ticker": ticker, "article": article, "chunk_start": chunk_start,
                "chunk_end": chunk_end, "last_status": f"prefetched_invalid:{reuse_validation['category']}",
                "retry_after": None, "last_http_status": None,
            })
            chunk_results.append({
                "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
                "source": "anchor_month_stage1", "status": f"invalid:{reuse_validation['category']}",
                "network_elapsed_s": 0.0, "sleep_s": 0.0,
            })
            continue

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


# --- BOUNDED CLOSED-MONTH SUBCHUNK RECOVERY (2026-08-03) -------------------
#
# WHY: the CTSH/GME 2026-08-03 PARTIAL (see Live Signal Engine/Phase2
# Failure Evidence/2026-08-03_CTSH_GME_Historical_Endpoint_PARTIAL/) traced
# to two mid-history full-month chunks returning HTTP 404 on both the first
# attempt and the bounded second pass, while a read-only diagnostic later
# showed the SAME exact request succeeded cleanly on retry, as did every
# fixed 7-day subrange of it -- consistent with transient/rate-limited
# server behavior rather than a genuine data-availability gap. This is a
# THIRD, last-resort recovery stage -- strictly bounded, strictly
# closed-month-only, never recursive -- that gives a failed month one more
# chance at fine-grained partial recovery before it is accepted as
# genuinely incomplete.
#
# Deliberately narrower than the existing recovery mechanisms it sits
# alongside: cache_union_reconstruction (attempt_cache_union_reconstruction)
# reads ONLY what is already cached; recent_last_known_good
# (evaluate_recent_cache_fallback) applies ONLY to the open/current chunk.
# This mechanism is the closed-month counterpart -- it makes NEW network
# requests, but only ever fixed, calendar-aligned, non-overlapping 7-day
# slices of an already-twice-failed month, each attempted exactly once.

SUBCHUNK_INTERVAL_DAYS = 7
# ceil(31/7) = 5 subchunks for the longest possible month; +1 headroom,
# still a tight, fixed ceiling -- never a function of how many actually
# fail.
SUBCHUNK_MAX_REQUESTS_PER_MONTH = 6
# Independent of (and much smaller than) the run-level TOTAL_RUN_BUDGET_S --
# a last-resort mechanism must not be able to materially eat into the
# budget meant for tickers/legs that haven't run yet.
SUBCHUNK_MAX_WALL_CLOCK_S = 120.0
# Same production-appropriate jitter as the existing second pass
# (SECOND_PASS_JITTER_RANGE_S) -- deliberately NOT zero-paced. An earlier
# zero-pacing read-only diagnostic of this exact failure independently
# demonstrated that firing requests back-to-back with no delay trips
# Wikimedia's burst rate limiter on the very next request, where paced
# requests at this same cadence succeeded cleanly across every partition
# size tested.
SUBCHUNK_PACING_RANGE_S = (2.0, 5.0)


def week_aligned_subchunks(start: date, end: date) -> list[tuple[date, date]]:
    """Deterministic, fixed 7-day partition of [start, end] -- the FINAL
    interval only is shortened as necessary to fit `end`. Purely a function
    of (start, end), exactly like calendar_month_chunks(): the same inputs
    always produce the same boundaries, and there is no recursive or
    data-dependent splitting anywhere in this module's subchunk logic."""
    if start > end:
        return []
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=SUBCHUNK_INTERVAL_DAYS - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def attempt_closed_month_subchunk_recovery(item: dict, watermark: date, remaining_budget_s: float,
                                            fetch_fn=None) -> dict:
    """Bounded, last-resort recovery for ONE chunk that already failed both
    the first pass and the bounded second pass. `item` is a `still_failed`
    entry (same shape produced by run_bounded_second_pass()/
    apply_recent_cache_fallback(): ticker, article, chunk_start, chunk_end,
    last_status, retry_after, last_http_status, reason).

    Applies ONLY to a CLOSED chunk -- returns immediately, unattempted, if
    `item`'s chunk currently contains the watermark (is_open_chunk()); the
    open/current chunk is evaluate_recent_cache_fallback()'s exclusive
    domain and this function never touches it, mirroring the same gate used
    at the run_bounded_subchunk_recovery() call site so the property holds
    even if called directly.

    Splits [chunk_start, required_data_end(chunk_end, watermark)] into
    fixed 7-day intervals (week_aligned_subchunks()) and makes EXACTLY ONE
    attempt per subchunk -- no inline retry, no recursive re-splitting of a
    subchunk that itself fails; it simply stays unrecovered. Bounded by
    BOTH SUBCHUNK_MAX_REQUESTS_PER_MONTH and
    min(SUBCHUNK_MAX_WALL_CLOCK_S, remaining_budget_s); once either limit
    is reached, every remaining subchunk is recorded as
    not_attempted_* and left un-fetched -- never zero-filled, never
    fabricated.

    Every subchunk response is validated through THE SAME shared
    validate_snapshot() gate used by every other consumer in this module
    (identity, duplicate dates, invalid pageviews, date-outside-range,
    content-hash, exact coverage through required_data_end -- which also
    structurally guarantees no observation past the watermark ever enters
    the union). A subchunk that individually validates is cached
    IMMEDIATELY through the existing write_chunk_to_cache() path, keyed by
    its OWN (sub_start, sub_end) boundaries -- never a synthesized
    whole-month cache entry -- so a genuine partial recovery is preserved
    even if the overall month does not end up fully recovered.

    The overall recovery is accepted ONLY when the union of every
    successfully fetched subchunk's rows exactly equals the full expected
    date set for [chunk_start, required_data_end(chunk_end, watermark)],
    with no duplicate or conflicting (same date, different pageviews)
    observation across subchunks. If even one required date remains
    unavailable -- a subchunk failed, was skipped for budget reasons, or a
    conflict was detected -- the WHOLE recovery fails closed; the caller's
    `item` stays in still_failed and wiki_zscore is never computed from
    this partial data (the caller only ever folds recovered==True rows into
    a ticker's daily series).

    Returns {"recovered": bool, "rows": [...], "reason": str,
    "subchunk_results": [...], "requests_used": int, "wall_clock_s": float,
    "budget_exhausted": bool}. subchunk_results is the full per-subchunk
    provenance record (requested boundaries, http_status, network elapsed
    time, retrieval timestamp, content hash, expected/observed date counts,
    and outcome status) consumed by the call site to build
    wiki_source_components_json-style provenance."""
    fetch_fn = fetch_fn or fetch_chunk_isolated
    ticker, article = item["ticker"], item["article"]
    chunk_start, chunk_end = item["chunk_start"], item["chunk_end"]

    if is_open_chunk(chunk_start, chunk_end, watermark):
        return {"recovered": False, "rows": [], "reason": "not_eligible_open_chunk",
                "subchunk_results": [], "requests_used": 0, "wall_clock_s": 0.0, "budget_exhausted": False}

    req_end = required_data_end(chunk_end, watermark)
    if req_end < chunk_start:
        return {"recovered": False, "rows": [], "reason": "no_observations_expected_yet",
                "subchunk_results": [], "requests_used": 0, "wall_clock_s": 0.0, "budget_exhausted": False}

    subchunks = week_aligned_subchunks(chunk_start, req_end)
    effective_wall_budget = max(0.0, min(SUBCHUNK_MAX_WALL_CLOCK_S, remaining_budget_s))

    subchunk_results: list[dict] = []
    unioned_rows: list[dict] = []
    seen_dates: dict[str, object] = {}
    budget_start = time.time()
    requests_used = 0
    budget_exhausted = False
    conflict = False

    for sub_start, sub_end in subchunks:
        if requests_used >= SUBCHUNK_MAX_REQUESTS_PER_MONTH:
            budget_exhausted = True
            subchunk_results.append({"requested_start": sub_start.isoformat(), "requested_end": sub_end.isoformat(),
                                      "status": "not_attempted_request_count_exhausted"})
            continue

        elapsed_so_far = time.time() - budget_start
        if elapsed_so_far >= effective_wall_budget:
            budget_exhausted = True
            subchunk_results.append({"requested_start": sub_start.isoformat(), "requested_end": sub_end.isoformat(),
                                      "status": "not_attempted_wall_clock_exhausted"})
            continue

        # Production-appropriate pacing between distinct requests -- never
        # a zero-delay burst (see module comment above).
        wait_s = random.uniform(*SUBCHUNK_PACING_RANGE_S)
        wait_s = max(0.0, min(wait_s, max(0.0, effective_wall_budget - elapsed_so_far)))
        if wait_s > 0:
            time.sleep(wait_s)

        remaining_after_wait = effective_wall_budget - (time.time() - budget_start)
        if remaining_after_wait < MIN_USABLE_CHUNK_BUDGET_S:
            budget_exhausted = True
            subchunk_results.append({"requested_start": sub_start.isoformat(), "requested_end": sub_end.isoformat(),
                                      "status": "not_attempted_wall_clock_exhausted"})
            continue

        capped_timeout = min(CHUNK_TIMEOUT_S, remaining_after_wait)
        result = fetch_fn(article, sub_start, sub_end, timeout_s=capped_timeout)
        requests_used += 1
        retrieved_at = datetime.now(timezone.utc).isoformat()
        entry = {
            "requested_start": sub_start.isoformat(), "requested_end": sub_end.isoformat(),
            "http_status": result.get("http_status"),
            "network_elapsed_s": round(result.get("network_elapsed_s") or 0.0, 4),
            "retrieved_at_utc": retrieved_at,
        }

        if result["status"] != "ok":
            entry["status"] = f"fetch_failed:{result['status']}"
            subchunk_results.append(entry)
            continue

        validation = validate_snapshot(ticker, article, sub_start, sub_end, result["items"], watermark)
        entry["expected_date_count"] = len(validation.get("expected_dates") or set())
        entry["observed_date_count"] = len(result["items"])
        entry["content_hash"] = validation.get("content_hash")

        if validation["category"] == "no_observations_expected_yet":
            entry["status"] = "ok_no_observations_expected_yet"
            subchunk_results.append(entry)
            continue
        if not validation["valid"]:
            entry["status"] = f"validation_failed:{validation['category']}"
            entry["reason"] = validation["reason"]
            subchunk_results.append(entry)
            continue

        # Cross-subchunk conflict/duplicate check. Subchunk date ranges are
        # disjoint by construction (week_aligned_subchunks() never
        # overlaps), so this should never trip in practice -- checked
        # defensively rather than assumed, exactly like every other
        # fail-closed gate in this module.
        subchunk_conflict = False
        for row in result["items"]:
            d = row["date"]
            if d in seen_dates:
                subchunk_conflict = True
                entry["status"] = "conflicting_or_duplicate_date_across_subchunks"
                entry["reason"] = f"date {d} already present from an earlier subchunk this recovery attempt"
                break
            seen_dates[d] = row["pageviews"]
        if subchunk_conflict:
            conflict = True
            subchunk_results.append(entry)
            continue

        entry["status"] = "ok"
        subchunk_results.append(entry)
        unioned_rows.extend(result["items"])
        write_chunk_to_cache(ticker, article, None, None, sub_start, sub_end, result["items"],
                              result.get("url", ""), result.get("http_status"), retrieved_at)

    wall_clock_s = time.time() - budget_start

    if conflict:
        return {"recovered": False, "rows": [], "reason": "conflicting_or_duplicate_dates_across_subchunks",
                "subchunk_results": subchunk_results, "requests_used": requests_used,
                "wall_clock_s": round(wall_clock_s, 4), "budget_exhausted": budget_exhausted}

    expected_dates = set()
    cursor = chunk_start
    while cursor <= req_end:
        expected_dates.add(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)
    actual_dates = {r["date"] for r in unioned_rows}

    if actual_dates != expected_dates:
        missing = sorted(expected_dates - actual_dates)
        return {"recovered": False, "rows": [],
                "reason": f"incomplete_union: missing {len(missing)} of {len(expected_dates)} date(s) "
                          f"(first few: {missing[:5]})",
                "subchunk_results": subchunk_results, "requests_used": requests_used,
                "wall_clock_s": round(wall_clock_s, 4), "budget_exhausted": budget_exhausted}

    return {"recovered": True, "rows": unioned_rows, "reason": "",
            "subchunk_results": subchunk_results, "requests_used": requests_used,
            "wall_clock_s": round(wall_clock_s, 4), "budget_exhausted": budget_exhausted}


def run_bounded_subchunk_recovery(still_failed: list[dict], remaining_budget_s: float, watermark: date,
                                   fetch_fn=None) -> dict:
    """Batch entry point, mirroring run_bounded_second_pass()'s and
    apply_recent_cache_fallback()'s own call shape. Runs AFTER both the
    bounded second pass and the recent-cache fallback, on whatever remains
    in `still_failed`. Only CLOSED chunks are eligible for THIS mechanism --
    an item whose chunk currently contains the watermark (the open/current
    chunk, apply_recent_cache_fallback()'s exclusive domain) is passed
    through unchanged, exactly like apply_recent_cache_fallback() passes
    through closed chunks unchanged for the mechanism before it.

    The outer `remaining_budget_s` (the run-level clock) is still respected
    across items even though each individual item's own recovery attempt
    is additionally capped by SUBCHUNK_MAX_WALL_CLOCK_S -- once outer
    budget is too low to usefully attempt anything, every remaining item is
    left in still_failed rather than launched.

    Returns {"recovered": {ticker: [rows...]}, "still_failed": [...],
    "subchunk_provenance": {ticker: {...}}}. subchunk_provenance carries
    the full per-item recovery record (original failed range, outcome,
    requests/wall-clock consumed, and the per-subchunk detail from
    attempt_closed_month_subchunk_recovery()) for wiki_source_mode /
    wiki_source_components_json / wiki_cache_union_provenance_json-style
    provenance at the call site -- keyed by ticker, since at most one
    closed-chunk failure per ticker is expected to survive to this stage in
    the locked 24-ticker panel's own chunking (one chunk per calendar
    month; a ticker with more than one surviving closed-month failure would
    simply overwrite this key with its last attempt, which does not affect
    correctness of `recovered`/`still_failed` -- only the logged detail for
    that ticker's later failure)."""
    fetch_fn = fetch_fn or fetch_chunk_isolated
    recovered: dict[str, list[dict]] = {}
    subchunk_provenance: dict[str, dict] = {}
    remaining_failed: list[dict] = []
    budget_start = time.time()

    for item in still_failed:
        outer_budget_left = max(0.0, remaining_budget_s - (time.time() - budget_start))
        if outer_budget_left < MIN_USABLE_CHUNK_BUDGET_S:
            remaining_failed.append({**item, "reason": item.get("reason", "") + "|subchunk_recovery_run_budget_exhausted"})
            continue
        if is_open_chunk(item["chunk_start"], item["chunk_end"], watermark):
            remaining_failed.append(item)
            continue

        outcome = attempt_closed_month_subchunk_recovery(
            item, watermark=watermark, remaining_budget_s=outer_budget_left, fetch_fn=fetch_fn,
        )
        subchunk_provenance[item["ticker"]] = {
            "original_chunk_start": item["chunk_start"].isoformat(),
            "original_chunk_end": item["chunk_end"].isoformat(),
            "original_failure_reason": item.get("reason", item.get("last_status", "")),
            "recovered": outcome["recovered"],
            "reason": outcome["reason"],
            "requests_used": outcome["requests_used"],
            "wall_clock_s": outcome["wall_clock_s"],
            "budget_exhausted": outcome["budget_exhausted"],
            "subchunks": outcome["subchunk_results"],
        }
        if outcome["recovered"]:
            recovered.setdefault(item["ticker"], []).extend(outcome["rows"])
        else:
            remaining_failed.append({**item, "reason": f"subchunk_recovery_failed:{outcome['reason']}"})

    return {"recovered": recovered, "still_failed": remaining_failed, "subchunk_provenance": subchunk_provenance}


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
