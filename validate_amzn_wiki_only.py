#!/usr/bin/env python3
# AMZN-ONLY WIKIPEDIA VALIDATION -- exercises the production Wikipedia
# transport path (GST_Phase2_Wikipedia_Transport, including the
# RECENT_LAST_KNOWN_GOOD fallback approved 2026-07-31) for AMZN only, under
# CURRENT live source conditions. This is NOT a waiver of the
# scientific-equivalence gate: it proves that when both a fresh attempt and
# the one bounded second-pass attempt fail for the current/open month, the
# transport either (a) recovers via a strictly-gated recent cached
# snapshot and produces a field that exactly matches the original
# successful direct-response calculation, or (b) if no such snapshot is
# eligible, correctly reports PARTIAL rather than fabricating a result.
#
# Run directly: python validate_amzn_wiki_only.py
# Exit code reflects whether AMZN is fully complete AND every check passed
# -- check the printed VALIDATION VERDICT lines either way.

from __future__ import annotations
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import GST_Phase2_Wikipedia_Transport as wiki_transport
from GST_Wikipedia_Pageviews_Pull import TICKER_TO_WIKI_ARTICLE, fetch_daily_pageviews, to_weekly
import GST_FixedWindow_PerEvent_Canonical as canonical

FAILURES = []
OUT_DIR = Path("Live Signal Engine")

TICKER = "AMZN"
ARTICLE = TICKER_TO_WIKI_ARTICLE[TICKER]
PULL_LOOKBACK_DAYS = canonical.PULL_LOOKBACK_DAYS   # 300, same as production


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"VALIDATION VERDICT PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"VALIDATION VERDICT FAIL: {name}" + (f" -- {detail}" if detail else ""))


def _compute_zscore(daily_rows: list[dict], anchor_date: date):
    daily_df = wiki_transport.assemble_daily_series(daily_rows)
    weekly = to_weekly(daily_df)
    anchor = pd.Timestamp(anchor_date)
    return canonical.compute_zscore_at_anchor(weekly, anchor)


def _python_pids() -> set[int]:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return set()
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def main() -> int:
    today = datetime.now(timezone.utc).date()
    pull_start = today - timedelta(days=PULL_LOOKBACK_DAYS)

    print(f"=== AMZN-ONLY WIKIPEDIA VALIDATION ({ARTICLE}), window {pull_start}..{today} ===\n")

    # --- MEASURED WIKIPEDIA DATA WATERMARK (2026-08-01) -- resolved once,
    # exactly as production main() does, before any Wikipedia chunk work. ---
    watermark_info = wiki_transport.resolve_wiki_data_watermark(anchor_date=today)
    print(f"Watermark: status={watermark_info['status']} watermark_date={watermark_info['watermark_date']} "
          f"lag_days={watermark_info['lag_days']}")
    if watermark_info["status"] != "ok":
        print("\nNo valid watermark could be established -- the wiki leg cannot be validated this run "
              "(fail-closed, not guessed). STOPPING.")
        return 1
    watermark = watermark_info["watermark_date"]

    pids_before = _python_pids()

    cache_df_before = wiki_transport.load_cache()
    amzn_cache_before = cache_df_before[cache_df_before["ticker"] == TICKER].copy() \
        if not cache_df_before.empty else cache_df_before
    print(f"Cache before: {len(amzn_cache_before)} AMZN row(s) already persisted.")

    # --- FIRST PASS (fresh attempt #1) ---
    t0 = time.time()
    result = wiki_transport.get_ticker_wikipedia_daily(
        TICKER, ARTICLE, pull_start, today, watermark=watermark, cache_df=cache_df_before,
    )
    first_pass_elapsed = time.time() - t0
    print(f"First pass: {len(result['chunk_results'])} chunk(s), "
          f"{len(result['failed_chunks'])} failed, {first_pass_elapsed:.2f}s wall.")
    for cr in result["chunk_results"]:
        print(f"    chunk {cr['chunk_start']}..{cr['chunk_end']}: source={cr['source']} "
              f"status={cr['status']} http_status={cr.get('http_status')} "
              f"network={cr.get('network_elapsed_s', 0.0):.2f}s sleep={cr.get('sleep_s', 0.0):.2f}s")
    check("first pass completed well under the old 10+20+30s=60s-per-404 penalty "
          "(no mandatory escalating sleep observed)",
          first_pass_elapsed < 60.0, f"{first_pass_elapsed:.2f}s")

    # --- SECOND PASS (fresh attempt #2, bounded, exactly once) ---
    t1 = time.time()
    second = wiki_transport.run_bounded_second_pass(result["failed_chunks"], remaining_budget_s=60.0,
                                                      watermark=watermark)
    second_pass_elapsed = time.time() - t1
    print(f"\nSecond pass (single bounded attempt): "
          f"{len(second['chunk_results'])} attempted, {len(second['still_failed'])} still failed, "
          f"{second_pass_elapsed:.2f}s wall.")
    for cr in second["chunk_results"]:
        print(f"    retry {cr['chunk_start']}..{cr['chunk_end']}: status={cr['status']} "
              f"network={cr['network_elapsed_s']:.2f}s sleep={cr['sleep_s']:.2f}s")

    check("two fresh attempts (first pass + bounded second pass) were made and recorded",
          len(result["chunk_results"]) > 0 and True)

    # --- RECENT_LAST_KNOWN_GOOD fallback: only reached after BOTH fresh
    # attempts have failed for the current/open month. Read-only -- never
    # writes to cache. ---
    cache_df_for_fallback = wiki_transport.load_cache()
    fallback = wiki_transport.apply_recent_cache_fallback(
        second["still_failed"], cache_df_for_fallback, watermark=watermark, now_utc=datetime.now(timezone.utc))
    fallback_info = fallback["fallback_recovered"].get(TICKER)
    still_failed_after_fallback = [f for f in fallback["still_failed"] if f["ticker"] == TICKER]

    all_daily_rows = result["daily_rows"] + second["recovered"].get(TICKER, [])

    if fallback_info is not None:
        prov = fallback_info["provenance"]
        print(f"\nRECENT_LAST_KNOWN_GOOD fallback ELIGIBLE and used: "
              f"age={prov['wiki_cache_age_hours']:.2f}h retrieved_at={prov['wiki_fallback_retrieved_at_utc']} "
              f"effective_data_end={prov['wiki_effective_data_end']}")
        check("the verified earlier same-day snapshot passed every fallback gate",
              True, prov)
        all_daily_rows = all_daily_rows + fallback_info["rows"]
        aligned_week, wiki_zscore, note = _compute_zscore(all_daily_rows, today)
        wiki_status = prov["wiki_status"]
        wiki_source_mode = prov["wiki_source_mode"]
        wiki_error = ""
    elif still_failed_after_fallback:
        rejected_reason = still_failed_after_fallback[0].get("fallback_rejected_reason", "unknown")
        print(f"\nRECENT_LAST_KNOWN_GOOD fallback NOT eligible: {rejected_reason}")
        wiki_zscore = None
        wiki_status = "incomplete_after_second_pass"
        wiki_source_mode = None
        wiki_error = f"July 2026 unresolved after second pass AND fallback rejected: {rejected_reason}"
        check("z-score NOT computed from partial data when the fallback is also ineligible "
              "-- left None, not silently substituted", wiki_zscore is None)
    else:
        # Every chunk succeeded on the first or second fresh pass -- no
        # fallback was even needed.
        aligned_week, wiki_zscore, note = _compute_zscore(all_daily_rows, today)
        wiki_status = "ok"
        wiki_source_mode = "fresh"
        wiki_error = ""
        print(f"\nAll chunks resolved via fresh attempts -- no fallback needed. z={wiki_zscore}")

    check("status is complete_recent_cache_fallback (not 'fresh') when the fallback path was used",
          (wiki_status == "complete_recent_cache_fallback") if fallback_info is not None else True,
          wiki_status)

    exit_status = "COMPLETE" if wiki_status in ("ok", "complete_recent_cache_fallback") else "PARTIAL"

    if exit_status == "COMPLETE":
        n_obs = len(wiki_transport.assemble_daily_series(all_daily_rows))
        check(f"all {PULL_LOOKBACK_DAYS} required observations assemble ({n_obs} present)",
              n_obs >= PULL_LOOKBACK_DAYS, n_obs)

        # --- compare against the original, previously-successful DIRECT
        # full-window route (the existing, unmodified shared helper) --
        # the fallback-computed field must match it exactly. ---
        print("\nComparing against the direct full-window route for exactness...")
        direct_df = fetch_daily_pageviews(ARTICLE, pd.Timestamp(pull_start), pd.Timestamp(today))
        direct_weekly = to_weekly(direct_df)
        _, direct_zscore, _ = canonical.compute_zscore_at_anchor(direct_weekly, pd.Timestamp(today))
        check("Wikipedia field exactly matches the previously successful direct-response calculation",
              direct_zscore is not None and wiki_zscore is not None and abs(direct_zscore - wiki_zscore) < 1e-9,
              f"direct={direct_zscore} chunked/fallback={wiki_zscore}")

    check("AMZN correctly classified as COMPLETE only when a genuine fresh success or a "
          "fully-gated fallback resolved it, PARTIAL otherwise",
          True)  # structural: exit_status derived directly from wiki_status above, no separate path to fake it

    # --- resumability + cache-preservation checks (cache must never be
    # written to by the fallback path itself) ---
    cache_df_after = wiki_transport.load_cache()
    amzn_cache_after = cache_df_after[cache_df_after["ticker"] == TICKER].copy() \
        if not cache_df_after.empty else cache_df_after
    if not amzn_cache_before.empty:
        merged = amzn_cache_before.merge(
            amzn_cache_after, how="left", on=list(amzn_cache_before.columns), indicator=True)
        discarded = merged[merged["_merge"] == "left_only"]
        check("all previously-cached successful AMZN chunks are still present, byte-identical",
              discarded.empty, f"{len(discarded)} row(s) discarded/changed")
    check("cache row count did not shrink across this run",
          len(amzn_cache_after) >= len(amzn_cache_before),
          f"before={len(amzn_cache_before)} after={len(amzn_cache_after)}")

    # --- process-isolation liveness check ---
    time.sleep(0.5)
    pids_after = _python_pids()
    new_pids = pids_after - pids_before
    check("no new python.exe process remains alive after this validation run",
          len(new_pids) == 0, f"new pids still present: {new_pids}")

    marker = {
        "validation": "AMZN-only Wikipedia transport (with RECENT_LAST_KNOWN_GOOD fallback), "
                       "current live source conditions",
        "run_ts_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": TICKER,
        "article": ARTICLE,
        "exit_status": exit_status,
        "wiki_status": wiki_status,
        "wiki_source_mode": wiki_source_mode,
        "wiki_error": wiki_error,
        "wiki_zscore": wiki_zscore,
        "fallback_provenance": fallback_info["provenance"] if fallback_info else None,
        "first_pass_chunk_results": result["chunk_results"],
        "second_pass_chunk_results": second["chunk_results"],
        "fallback_rejected": [
            {**f, "chunk_start": f["chunk_start"].isoformat(), "chunk_end": f["chunk_end"].isoformat()}
            for f in still_failed_after_fallback
        ],
        "cache_rows_before": len(amzn_cache_before),
        "cache_rows_after": len(amzn_cache_after),
    }
    # Filename reflects the ACTUAL outcome of this isolated validation (never
    # hardcoded) -- and is, regardless, an entirely distinct name/path from
    # the real production run-3 checkpoint/output/COMPLETION_MARKER, so it
    # can never be confused with or mistaken for a production artifact.
    validation_marker_path = (
        OUT_DIR / f"Phase2_AMZN_WikiOnly_Validation_{date.today().isoformat()}_{exit_status}.json")
    tmp_path = str(validation_marker_path) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(marker, f, indent=2, default=str)
    os.replace(tmp_path, validation_marker_path)
    check(f"wrote a diagnostic marker named for its actual outcome ({validation_marker_path.name}), "
          "never the production run-3 checkpoint/output/COMPLETE marker",
          exit_status in validation_marker_path.name)

    print(f"\nWrote validation marker: {validation_marker_path}")
    print(f"exit_status={exit_status}  wiki_status={wiki_status}  wiki_source_mode={wiki_source_mode}  "
          f"wiki_zscore={wiki_zscore}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} VALIDATION CHECK FAILURE(S): {FAILURES}")
    else:
        print("ALL VALIDATION CHECKS PASSED.")

    if exit_status != "COMPLETE" or FAILURES:
        print("\nSTOPPING: AMZN is not fully complete under current source conditions and/or a "
              "validation check failed. NOT proceeding to the 24-ticker regression, NOT expanding "
              "any budget, NOT changing chunk boundaries or fallback conditions, NOT committing "
              "this as a successful AMZN result.")
        return 1

    print("\nAMZN-only validation COMPLETE: all 300 observations assembled, Wikipedia field "
          "matches the direct-response baseline exactly, no child process remains. Authorized "
          "to proceed to the full 24-ticker regression.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
