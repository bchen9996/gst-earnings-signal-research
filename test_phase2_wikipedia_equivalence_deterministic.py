#!/usr/bin/env python3
# DETERMINISTIC SCIENTIFIC-EQUIVALENCE TEST (2026-07-31 corrective commit,
# Section A of the split equivalence gate -- see
# test_phase2_wikipedia_equivalence.py for Section B, the OPTIONAL live
# smoke test that does NOT substitute for this one).
#
# Uses FROZEN, provenance-documented fixtures captured once from the real
# direct-response route (Live Signal Engine/Phase2_Wikipedia_Equivalence_Fixtures/
# {TICKER}_direct_response_fixture.json -- exact dates, values, retrieval
# timestamp, article identity, source URL, and content hash all recorded).
# The chunked-assembly pipeline is exercised via an injected fetch_fn that
# slices the SAME frozen dataset by requested date range -- deterministic,
# no live-network call, no "unavailable"/"inconclusive" outcome possible.
#
# Requirements enforced (unlike the old, now-replaced permissive check):
#   - the chunked assembly must produce EXACTLY the same date SET as the
#     fixture (not just matching values on whatever happens to overlap)
#   - EXACTLY the same value for every date
#   - the same z-score within the documented numerical tolerance (1e-9)
#   - no live-network dependency
#   - no unavailable/inconclusive condition may count as PASS -- this test
#     only ever PASSES or FAILS
#
# Run directly: python test_phase2_wikipedia_equivalence_deterministic.py

from __future__ import annotations
from datetime import date
from pathlib import Path
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from GST_Wikipedia_Pageviews_Pull import to_weekly
import GST_Phase2_Wikipedia_Transport as wiki_transport
import GST_FixedWindow_PerEvent_Canonical as canonical

FAILURES = []
TOLERANCE = 1e-9
FIXTURE_DIR = Path("Live Signal Engine") / "Phase2_Wikipedia_Equivalence_Fixtures"
TICKERS_UNDER_TEST = ["AAPL", "AMZN"]


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def _load_fixture(ticker: str) -> dict:
    path = FIXTURE_DIR / f"{ticker}_direct_response_fixture.json"
    with open(path, "r", encoding="utf-8") as f:
        fixture = json.load(f)
    # Provenance sanity: the fixture itself must carry everything it claims to.
    for field in ("ticker", "configured_article_title", "requested_start", "requested_end",
                  "source_url", "http_status", "retrieval_timestamp_utc", "content_hash", "daily_rows"):
        assert field in fixture, f"fixture {path} missing required provenance field {field!r}"
    recomputed_hash = wiki_transport.compute_chunk_hash(fixture["daily_rows"])
    assert recomputed_hash == fixture["content_hash"], (
        f"fixture {path} content_hash does not verify -- fixture itself is corrupted "
        f"(stored={fixture['content_hash']} recomputed={recomputed_hash})")
    assert fixture["http_status"] == 200, f"fixture {path} was not captured from a real HTTP 200"
    return fixture


def _frozen_fetch_fn(fixture: dict):
    """Deterministic fetch_fn backed ENTIRELY by the frozen fixture -- slices
    the fixture's own daily_rows by the requested chunk range. No network
    call, ever. This is what makes the chunked-assembly side of the
    comparison deterministic and reproducible."""
    by_date = {r["date"]: r["pageviews"] for r in fixture["daily_rows"]}

    def _fn(article, start: date, end: date, timeout_s=None):
        items = []
        cursor = start
        while cursor <= end:
            key = cursor.strftime("%Y%m%d")
            if key in by_date:
                items.append({"date": key, "pageviews": by_date[key]})
            cursor += pd.Timedelta(days=1)
        return {"status": "ok", "http_status": 200, "items": items, "url": fixture["source_url"],
                "network_elapsed_s": 0.0, "terminated": False, "retry_after": None}

    return _fn


def _run_for_ticker(ticker: str) -> None:
    fixture = _load_fixture(ticker)
    article = fixture["configured_article_title"]
    start = date.fromisoformat(fixture["requested_start"])
    end = date.fromisoformat(fixture["requested_end"])

    print(f"\n=== {ticker} ({article}): deterministic equivalence against frozen fixture "
          f"(captured {fixture['retrieval_timestamp_utc']}, {fixture['n_observations']} observations) ===")

    fetch_fn = _frozen_fetch_fn(fixture)
    cache_df = pd.DataFrame(columns=wiki_transport.CACHE_COLUMNS)   # empty -- every chunk must be "fetched"
    result = wiki_transport.get_ticker_wikipedia_daily(
        ticker, article, start, end, today=end, cache_df=cache_df, fetch_fn=fetch_fn,
    )
    check(f"{ticker}: no failed chunks against the frozen fixture (fully deterministic, no live network)",
          result["failed_chunks"] == [], result["failed_chunks"])

    fixture_dates = {r["date"] for r in fixture["daily_rows"]}
    assembled_dates = {r["date"] for r in result["daily_rows"]}

    check(f"{ticker}: chunked assembly produces EXACTLY the same date SET as the fixture "
          f"(not merely overlapping) -- {len(fixture_dates)} dates",
          assembled_dates == fixture_dates,
          f"missing={sorted(fixture_dates - assembled_dates)[:5]} "
          f"extra={sorted(assembled_dates - fixture_dates)[:5]}")

    fixture_by_date = {r["date"]: r["pageviews"] for r in fixture["daily_rows"]}
    assembled_by_date = {r["date"]: r["pageviews"] for r in result["daily_rows"]}
    mismatches = [(d, fixture_by_date[d], assembled_by_date.get(d))
                  for d in fixture_by_date if assembled_by_date.get(d) != fixture_by_date[d]]
    check(f"{ticker}: EXACTLY the same pageviews value for every date ({len(fixture_by_date)} compared)",
          mismatches == [], mismatches[:10])

    fixture_df = wiki_transport.assemble_daily_series(fixture["daily_rows"])
    assembled_df = wiki_transport.assemble_daily_series(result["daily_rows"])
    anchor = pd.Timestamp(end)
    _, fixture_z, _ = canonical.compute_zscore_at_anchor(to_weekly(fixture_df), anchor)
    _, assembled_z, _ = canonical.compute_zscore_at_anchor(to_weekly(assembled_df), anchor)

    check(f"{ticker}: wiki z-score computable from both the fixture and the chunked assembly",
          fixture_z is not None and assembled_z is not None, f"fixture={fixture_z} assembled={assembled_z}")
    if fixture_z is not None and assembled_z is not None:
        check(f"{ticker}: z-score matches within documented tolerance ({TOLERANCE})",
              abs(fixture_z - assembled_z) <= TOLERANCE,
              f"fixture={fixture_z} assembled={assembled_z} diff={abs(fixture_z - assembled_z)}")


if __name__ == "__main__":
    for t in TICKERS_UNDER_TEST:
        _run_for_ticker(t)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("DETERMINISTIC SCIENTIFIC-EQUIVALENCE TEST PASSED FOR ALL TICKERS -- exact date-set and "
              "value equality against frozen, provenance-documented fixtures, no live-network dependency.")
        sys.exit(0)
