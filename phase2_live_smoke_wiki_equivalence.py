#!/usr/bin/env python3
# OPTIONAL LIVE SOURCE SMOKE TEST (2026-07-31 corrective commit, Section B
# of the split equivalence gate -- see
# test_phase2_wikipedia_equivalence_deterministic.py for Section A, the
# MANDATORY, no-live-network, frozen-fixture test that this one does NOT
# substitute for).
#
# 2026-08-03 SAFETY CORRECTION: this file was previously named
# test_phase2_wikipedia_equivalence.py and was silently swept up by any
# "run every test_*.py" loop or discovery tool -- including this project's
# own CI-style regression checks -- even though it makes REAL network calls
# and, without this correction, wrote directly to the REAL operational
# Phase2_Wikipedia_Cache.csv. Renamed off the test_*.py pattern specifically
# so ordinary deterministic test discovery can never pick it up by
# accident, and gated behind an explicit environment variable (below) so it
# can never run -- let alone touch the network or the operational cache --
# without a human deliberately opting in for this one invocation. See
# CHANGELOG.md's 2026-08-03 "cache-hash discrepancy" entry for the incident
# that motivated this.
#
# For AAPL and AMZN: fetches the SAME 300-day production window two ways --
# DIRECT (fetch_daily_pageviews(), the existing, unmodified shared helper)
# and CHUNKED (get_ticker_wikipedia_daily() + bounded second pass +
# RECENT_LAST_KNOWN_GOOD fallback, the actual current production pipeline)
# -- and reports, per ticker, one of exactly three verdicts:
#
#   PASS         -- the two routes' date sets are IDENTICAL, every value
#                   matches exactly, and the z-score matches within
#                   tolerance.
#   INCONCLUSIVE -- source unavailable (either route returned no data) or
#                   the two routes' date SETS differ (a coverage gap on
#                   either side, live source instability by nature) --
#                   NEVER counted as a pass, regardless of how a live
#                   re-probe of the gap classifies it.
#   FAIL         -- a true value mismatch on a date BOTH routes returned
#                   (both "complete" for that date) -- a real defect,
#                   never explained away as transience.
#
# This is the fix for the prior version of this file, which checked only
# OVERLAPPING values (so it could pass even when the two routes had
# different date sets) and folded "probe_inconclusive" into an acceptance
# check. That was not equivalence. This version can no longer do either.
#
# Makes REAL network calls (and, for the chunked path, real subprocess
# spawns) for two tickers -- NOT part of the deterministic suites run
# before committing, and NOT a deterministic CI gate: this is an OPTIONAL,
# OBSERVATIONAL live diagnostic. Its outcome depends on real-time Wikipedia
# availability and must never be required for a commit/merge/regression
# decision -- test_phase2_wikipedia_equivalence_deterministic.py is the
# actual gate.
#
# Run directly (only with the explicit opt-in below):
#   RUN_PHASE2_LIVE_WIKI_SMOKE=1 python phase2_live_smoke_wiki_equivalence.py
# Exit code (see decide_exit_code(), directly unit-tested without any
# network call in test_phase2_wikipedia_equivalence_deterministic.py):
#   0 -- every tested ticker PASSED
#   1 -- at least one ticker FAILed (a true value mismatch -- investigate)
#   2 -- no FAILures, but at least one ticker was INCONCLUSIVE (source
#        unavailable or a coverage gap right now -- not a defect, but not
#        a clean pass either)

from __future__ import annotations
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import urllib.error
import urllib.parse
import urllib.request

from GST_Wikipedia_Pageviews_Pull import fetch_daily_pageviews, to_weekly, TICKER_TO_WIKI_ARTICLE
import GST_Phase2_Wikipedia_Transport as wiki_transport
import GST_FixedWindow_PerEvent_Canonical as canonical

TOLERANCE = 1e-6
TICKERS_UNDER_TEST = ["AAPL", "AMZN"]

# Explicit opt-in required for this file to make any network call or touch
# GST_Phase2_Wikipedia_Transport.CACHE_PATH at all. Unset (the default in
# every normal invocation, including any "run every test file" loop) means
# this file does nothing but print a skip notice and return -- no import-
# time side effect, no network access, no cache access.
LIVE_SMOKE_ENV_VAR = "RUN_PHASE2_LIVE_WIKI_SMOKE"

VERDICTS: dict[str, str] = {}   # ticker -> "PASS" / "INCONCLUSIVE" / "FAIL"
FAILURES: list[str] = []        # true defects only -- reported in the summary


def _hash_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class _TempCacheRedirect:
    """Context manager: swaps GST_Phase2_Wikipedia_Transport.CACHE_PATH to
    a fresh, empty temp file for its entire duration, unconditionally
    restoring the original CACHE_PATH and deleting the temp directory on
    the way out -- including when the body raises (the restore happens in
    __exit__, which always runs). This is its own small, independently
    testable unit specifically so deterministic tests can prove the
    isolation and cleanup-on-exception behavior without invoking any live
    network code (see test_phase2_live_wiki_smoke_gating.py)."""

    def __enter__(self) -> Path:
        self._original_cache_path = wiki_transport.CACHE_PATH
        self._tmp_dir = tempfile.mkdtemp(prefix="phase2_live_smoke_cache_")
        wiki_transport.CACHE_PATH = Path(self._tmp_dir) / "live_smoke_isolated_cache.csv"
        return wiki_transport.CACHE_PATH

    def __exit__(self, exc_type, exc, tb) -> bool:
        wiki_transport.CACHE_PATH = self._original_cache_path
        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        return False  # never swallow an exception


def decide_exit_code(verdicts: dict[str, str]) -> int:
    """Pure mapping from per-ticker verdicts to the process exit code --
    extracted specifically so it can be tested deterministically, without
    any network call, in test_phase2_wikipedia_equivalence_deterministic.py.
    0 = all PASS, 1 = any FAIL (checked first -- a FAIL always wins over
    any INCONCLUSIVE present), 2 = no FAIL but at least one INCONCLUSIVE.
    An empty verdicts dict is treated as all-PASS (vacuously 0) -- callers
    always populate it from TICKERS_UNDER_TEST before calling this."""
    values = list(verdicts.values())
    if any(v == "FAIL" for v in values):
        return 1
    if any(v == "INCONCLUSIVE" for v in values):
        return 2
    return 0


def note(name: str, condition: bool, detail: str = "") -> None:
    """Sub-check logging only -- does NOT by itself decide a ticker's
    verdict (see _run_for_ticker's explicit verdict assignment at the end).
    Kept separate from FAILURES so an INCONCLUSIVE ticker's sub-checks
    don't silently become exit-code failures."""
    tag = "OK" if condition else "NOTE"
    print(f"    [{tag}] {name}" + (f" -- {detail}" if detail else ""))


def _direct_daily(article: str, start: date, end: date) -> pd.DataFrame:
    df = fetch_daily_pageviews(article, pd.Timestamp(start), pd.Timestamp(end))
    return df.sort_values("date").reset_index(drop=True)


def _chunked_daily(ticker: str, article: str, start: date, end: date, watermark: date) -> pd.DataFrame:
    cache_df = wiki_transport.load_cache()
    result = wiki_transport.get_ticker_wikipedia_daily(
        ticker, article, start, end, watermark=watermark, cache_df=cache_df,
    )
    daily_rows = result["daily_rows"]
    still_failed = []
    if result["failed_chunks"]:
        print(f"    [{ticker}] {len(result['failed_chunks'])} chunk(s) failed first pass -- running bounded second pass")
        second = wiki_transport.run_bounded_second_pass(result["failed_chunks"], remaining_budget_s=180,
                                                          watermark=watermark)
        daily_rows = daily_rows + second["recovered"].get(ticker, [])
        still_failed = second["still_failed"]
        if still_failed:
            print(f"    [{ticker}] STILL FAILED after second pass: {still_failed}")
    if still_failed:
        # RECENT_LAST_KNOWN_GOOD fallback is part of the actual production
        # pipeline -- exercising it here means this smoke test reflects
        # what production actually does, not a stale two-pass-only version.
        fallback = wiki_transport.apply_recent_cache_fallback(
            still_failed, wiki_transport.load_cache(), watermark=watermark, now_utc=datetime.now(timezone.utc))
        fb = fallback["fallback_recovered"].get(ticker)
        if fb is not None:
            print(f"    [{ticker}] RECENT_LAST_KNOWN_GOOD fallback used for the remaining gap: {fb['provenance']}")
            daily_rows = daily_rows + fb["rows"]
        for rej in fallback["still_failed"]:
            print(f"    [{ticker}] fallback NOT used ({rej.get('fallback_rejected_reason')}) -- "
                  f"chunk {rej['chunk_start']}..{rej['chunk_end']} remains genuinely unresolved")
    daily_df = wiki_transport.assemble_daily_series(daily_rows)
    return daily_df.sort_values("date").reset_index(drop=True)


def _independently_reprobe_month(article: str, month_start: date) -> str:
    """A direct, standalone HTTP re-probe of a single calendar month --
    independent of both routes under test -- purely DIAGNOSTIC context
    printed alongside an INCONCLUSIVE verdict. Never used to upgrade a
    date-set mismatch into a PASS, and never used to downgrade one into a
    FAIL either -- see the module docstring for why."""
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    month_end = next_month - timedelta(days=1)
    encoded = urllib.parse.quote(article.replace(" ", "_"), safe="")
    url = wiki_transport.WIKI_API.format(
        article=encoded, start=month_start.strftime("%Y%m%d"), end=month_end.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; GST project)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.load(resp)
            return "actually_available_now" if body.get("items") else "confirmed_unavailable"
    except urllib.error.HTTPError as e:
        return "confirmed_unavailable" if e.code == 404 else "probe_inconclusive"
    except Exception:
        return "probe_inconclusive"


def _run_for_ticker(ticker: str, watermark: date) -> str:
    """Returns exactly one of 'PASS' / 'INCONCLUSIVE' / 'FAIL'."""
    article = TICKER_TO_WIKI_ARTICLE[ticker]
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=canonical.PULL_LOOKBACK_DAYS)

    print(f"\n=== {ticker} ({article}): direct vs chunked-assembled (live), {start}..{today}, "
          f"watermark={watermark} ===")

    direct_df = _direct_daily(article, start, today)
    chunked_df = _chunked_daily(ticker, article, start, today, watermark)
    note(f"{ticker}: direct route returned data", len(direct_df) > 0, f"{len(direct_df)} rows")
    note(f"{ticker}: chunked route returned data", len(chunked_df) > 0, f"{len(chunked_df)} rows")

    if direct_df.empty or chunked_df.empty:
        print(f"    VERDICT ({ticker}): INCONCLUSIVE -- one or both routes returned no data right now "
              f"(source unavailable), not evaluable as PASS or FAIL")
        return "INCONCLUSIVE"

    direct_idx = direct_df.set_index(direct_df["date"].dt.date)["views"]
    chunked_idx = chunked_df.set_index(chunked_df["date"].dt.date)["views"]
    direct_dates = set(direct_idx.index)
    chunked_dates = set(chunked_idx.index)
    common_dates = sorted(direct_dates & chunked_dates)

    # A true mismatch is only meaningful on a date BOTH routes actually
    # returned -- "both responses complete" for that date. This can FAIL
    # regardless of what happens with the date-set comparison below.
    mismatches = [(d, int(direct_idx[d]), int(chunked_idx[d])) for d in common_dates
                  if int(direct_idx[d]) != int(chunked_idx[d])]
    note(f"{ticker}: value agreement on the {len(common_dates)} common date(s)",
         mismatches == [], mismatches[:10])
    if mismatches:
        print(f"    VERDICT ({ticker}): FAIL -- {len(mismatches)} true value mismatch(es) on dates both "
              f"routes returned complete data for")
        return "FAIL"

    if direct_dates != chunked_dates:
        only_direct = sorted(direct_dates - chunked_dates)
        only_chunked = sorted(chunked_dates - direct_dates)
        if only_direct:
            gap_months = sorted({date(d.year, d.month, 1) for d in only_direct})
            classifications = {m: _independently_reprobe_month(article, m) for m in gap_months}
            for m, cls in classifications.items():
                print(f"    RE-PROBE ({ticker}) {m.isoformat()}: {cls} (diagnostic only -- does not "
                      f"change the verdict)")
        note(f"{ticker}: date sets differ ({len(only_direct)} only-direct, {len(only_chunked)} only-chunked)",
             False, f"only_direct={only_direct[:5]} only_chunked={only_chunked[:5]}")
        print(f"    VERDICT ({ticker}): INCONCLUSIVE -- date sets differ between routes (live source "
              f"coverage gap on one side) -- never counted as PASS")
        return "INCONCLUSIVE"

    anchor = pd.Timestamp(today)
    _, direct_z, direct_note_ = canonical.compute_zscore_at_anchor(to_weekly(direct_df), anchor)
    _, chunked_z, chunked_note_ = canonical.compute_zscore_at_anchor(to_weekly(chunked_df), anchor)
    if direct_z is None or chunked_z is None:
        note(f"{ticker}: z-score computable via both routes", False,
             f"direct={direct_z} ({direct_note_!r}) chunked={chunked_z} ({chunked_note_!r})")
        print(f"    VERDICT ({ticker}): INCONCLUSIVE -- z-score not computable from identical date sets "
              f"(insufficient rolling-window history at this anchor), not a value defect")
        return "INCONCLUSIVE"

    z_match = abs(direct_z - chunked_z) <= TOLERANCE
    note(f"{ticker}: z-score matches within tolerance ({TOLERANCE})", z_match,
         f"direct={direct_z} chunked={chunked_z} diff={abs(direct_z - chunked_z)}")
    if not z_match:
        print(f"    VERDICT ({ticker}): FAIL -- identical date sets and values, but z-score disagrees "
              f"beyond tolerance (unexpected -- investigate compute path)")
        return "FAIL"

    print(f"    VERDICT ({ticker}): PASS -- identical date sets, exact value match, z-score within tolerance")
    return "PASS"


def _print_summary(verdicts: dict[str, str], failures: list[str]) -> int:
    counts = {"PASS": 0, "INCONCLUSIVE": 0, "FAIL": 0}
    for v in verdicts.values():
        counts[v] += 1

    print(f"\n=== SUMMARY -- OPTIONAL LIVE DIAGNOSTIC, NOT a deterministic CI gate "
          f"(does not substitute for test_phase2_wikipedia_equivalence_deterministic.py) ===")
    for t, v in verdicts.items():
        print(f"  {t}: {v}")
    print(f"Counts: PASS={counts['PASS']} INCONCLUSIVE={counts['INCONCLUSIVE']} FAIL={counts['FAIL']}")

    exit_code = decide_exit_code(verdicts)
    if exit_code == 0:
        print("\nExit 0: every tested ticker PASSED.")
    elif exit_code == 1:
        print(f"\nExit 1: {counts['FAIL']} true FAILURE(S) found: {failures} -- a real value mismatch. "
              "This DOES matter and should be investigated.")
    else:
        print(f"\nExit 2: no failures, but {counts['INCONCLUSIVE']} ticker(s) INCONCLUSIVE (source "
              "unavailable, a coverage gap right now, or this live probe was skipped) -- not a "
              "defect, but not a clean pass either.")
    return exit_code


def _run_live_smoke() -> int:
    """The actual live-network smoke run. Only ever called when
    LIVE_SMOKE_ENV_VAR is explicitly set (see main()) -- never at import
    time, never as a side effect of any other function in this module.

    Redirects GST_Phase2_Wikipedia_Transport.CACHE_PATH to an isolated temp
    file for the ENTIRE run via _TempCacheRedirect (restored unconditionally
    on the way out, including on an exception), then independently
    hash-verifies the REAL operational cache file is byte-identical before
    and after -- defense in depth on top of the redirect itself, in case
    any code path were ever to reference the real path directly."""
    real_cache_path = wiki_transport.CACHE_PATH
    real_hash_before = _hash_or_none(real_cache_path)

    with _TempCacheRedirect() as tmp_cache_path:
        print(f"Operational cache isolated for this run: CACHE_PATH -> {tmp_cache_path} "
              f"(real path {real_cache_path} is not read or written by this run)")

        # Resolved ONCE for this diagnostic run, exactly as production
        # main() does -- never recomputed per ticker.
        watermark_info = wiki_transport.resolve_wiki_data_watermark(anchor_date=datetime.now(timezone.utc).date())
        print(f"Watermark: status={watermark_info['status']} watermark_date={watermark_info['watermark_date']} "
              f"lag_days={watermark_info['lag_days']}\n")

        if watermark_info["status"] != "ok":
            print("No valid watermark could be established -- marking all tickers INCONCLUSIVE "
                  "(source unavailable), not FAIL.")
            for t in TICKERS_UNDER_TEST:
                VERDICTS[t] = "INCONCLUSIVE"
        else:
            for t in TICKERS_UNDER_TEST:
                verdict = _run_for_ticker(t, watermark_info["watermark_date"])
                VERDICTS[t] = verdict
                if verdict == "FAIL":
                    FAILURES.append(t)

        exit_code = _print_summary(VERDICTS, FAILURES)

    real_hash_after = _hash_or_none(real_cache_path)
    if real_hash_before != real_hash_after:
        # Should be structurally impossible given the redirect above --
        # printed loudly and forced to a hard failure if it ever happens,
        # rather than silently accepted.
        print(f"\n*** ALARM: the REAL operational cache changed during this run despite CACHE_PATH "
              f"isolation (before={real_hash_before} after={real_hash_after}). This should never "
              f"happen -- treat as a defect in the isolation mechanism, not in Wikipedia data. ***")
        return 1
    print(f"\nOperational cache verified byte-identical before and after this run "
          f"(sha256={real_hash_before}).")
    return exit_code


def main() -> int:
    """Entry point. Without LIVE_SMOKE_ENV_VAR=1 set, this makes NO network
    call and NEVER touches GST_Phase2_Wikipedia_Transport.CACHE_PATH (real
    or otherwise) -- every ticker is reported INCONCLUSIVE with a skip
    reason, reusing the existing three-state PASS/INCONCLUSIVE/FAIL
    contract and its exit codes (0/1/2) rather than inventing a fourth
    state, exactly as intended when INCONCLUSIVE was designed to mean
    "not evaluable right now, not a defect.\""""
    if os.environ.get(LIVE_SMOKE_ENV_VAR) != "1":
        print(f"SKIPPED: {LIVE_SMOKE_ENV_VAR}=1 is not set. This is an OPTIONAL live-network smoke "
              f"test that is never run by default, by any deterministic test suite, or by any "
              f"ordinary test_*.py discovery loop -- it makes real HTTP requests and must be a "
              f"deliberate, explicit, single invocation. No network request was made and the "
              f"operational cache was not accessed.\n"
              f"To run it deliberately: {LIVE_SMOKE_ENV_VAR}=1 python {Path(__file__).name}")
        for t in TICKERS_UNDER_TEST:
            VERDICTS[t] = "INCONCLUSIVE"
        return _print_summary(VERDICTS, FAILURES)
    return _run_live_smoke()


if __name__ == "__main__":
    sys.exit(main())
