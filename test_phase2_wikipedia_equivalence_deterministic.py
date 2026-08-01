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
# TEST ISOLATION (2026-07-31 follow-up): a successful fixture-backed chunk
# still goes through the real write_chunk_to_cache(), which writes through
# the module-global wiki_transport.CACHE_PATH -- with the REAL ticker
# symbols "AAPL"/"AMZN", an unredirected run of this test would write into
# (and could corrupt/pollute) the actual operational
# Live Signal Engine/Phase2_Wikipedia_Cache.csv. This is a DETERMINISTIC
# test and must never mutate operational data, so CACHE_PATH is redirected
# to a temporary, test-only file for the duration of the run, restored
# afterward no matter what, and the operational cache's untouched state is
# explicitly verified (byte-identical if it existed, still absent if it
# didn't) before reporting results.
#
# Run directly: python test_phase2_wikipedia_equivalence_deterministic.py

from __future__ import annotations
from datetime import date
from pathlib import Path
import json
import os
import shutil
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from GST_Wikipedia_Pageviews_Pull import to_weekly
import GST_Phase2_Wikipedia_Transport as wiki_transport
import GST_FixedWindow_PerEvent_Canonical as canonical

FAILURES = []
TOLERANCE = 1e-9
FIXTURE_DIR = Path("Live Signal Engine") / "Phase2_Wikipedia_Equivalence_Fixtures"
TICKERS_UNDER_TEST = ["AAPL", "AMZN"]

_ORIGINAL_CACHE_PATH = wiki_transport.CACHE_PATH


def _use_temp_cache() -> str:
    tmp_dir = tempfile.mkdtemp(prefix="wiki_equivalence_test_")
    wiki_transport.CACHE_PATH = Path(tmp_dir) / "test_cache.csv"
    return tmp_dir


def _restore_cache_path(tmp_dir: str) -> None:
    wiki_transport.CACHE_PATH = _ORIGINAL_CACHE_PATH
    shutil.rmtree(tmp_dir, ignore_errors=True)


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
    # The watermark must reflect what the fixture ACTUALLY contains, not
    # its aspirational "requested_end" -- the fixture was captured via the
    # direct route, which (like everything else in this investigation) can
    # itself lag behind the nominal request end by a day or more. Deriving
    # the watermark from the fixture's own real last date means this test
    # verifies exact reproduction of what was genuinely captured, not
    # whether the pipeline can conjure data beyond what was ever fetched.
    fixture_last_date = max(date.fromisoformat(r["date"][:4] + "-" + r["date"][4:6] + "-" + r["date"][6:])
                             for r in fixture["daily_rows"])
    watermark = min(end, fixture_last_date)

    print(f"\n=== {ticker} ({article}): deterministic equivalence against frozen fixture "
          f"(captured {fixture['retrieval_timestamp_utc']}, {fixture['n_observations']} observations, "
          f"watermark={watermark.isoformat()}) ===")

    fetch_fn = _frozen_fetch_fn(fixture)
    cache_df = pd.DataFrame(columns=wiki_transport.CACHE_COLUMNS)   # empty -- every chunk must be "fetched"
    result = wiki_transport.get_ticker_wikipedia_daily(
        ticker, article, start, end, watermark=watermark, cache_df=cache_df, fetch_fn=fetch_fn,
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


# === Watermark truncation test 13 (2026-08-01): a deterministic fixture
# z-score, computed via the chunked pipeline with a watermark set EARLIER
# than the fixture's own natural end, must exactly equal the z-score
# computed from a MANUALLY watermark-truncated copy of the same frozen
# fixture -- proving the truncation logic itself is correct, not just that
# an already-complete fixture round-trips. ===
def test_watermark_truncation_matches_manually_truncated_fixture():
    for ticker in TICKERS_UNDER_TEST:
        fixture = _load_fixture(ticker)
        article = fixture["configured_article_title"]
        start = date.fromisoformat(fixture["requested_start"])
        end = date.fromisoformat(fixture["requested_end"])

        # Deliberately set the watermark 5 days earlier than the fixture's
        # own last real date -- forces the chunked pipeline to truncate.
        fixture_last_date = max(date.fromisoformat(r["date"][:4] + "-" + r["date"][4:6] + "-" + r["date"][6:])
                                 for r in fixture["daily_rows"])
        early_watermark = fixture_last_date - pd.Timedelta(days=5)
        early_watermark = date(early_watermark.year, early_watermark.month, early_watermark.day)

        fetch_fn = _frozen_fetch_fn(fixture)
        cache_df = pd.DataFrame(columns=wiki_transport.CACHE_COLUMNS)
        result = wiki_transport.get_ticker_wikipedia_daily(
            ticker, article, start, end, watermark=early_watermark, cache_df=cache_df, fetch_fn=fetch_fn,
        )
        check(f"{ticker}: no failed chunks when truncating to an earlier watermark",
              result["failed_chunks"] == [], result["failed_chunks"])

        # Manual truncation: filter the frozen fixture's own rows to dates
        # <= early_watermark -- this is the independently-computed "expected"
        # answer the pipeline's own truncation must match exactly.
        manually_truncated = [r for r in fixture["daily_rows"]
                               if date.fromisoformat(r["date"][:4] + "-" + r["date"][4:6] + "-" + r["date"][6:])
                               <= early_watermark]
        assembled_dates = {r["date"] for r in result["daily_rows"]}
        manual_dates = {r["date"] for r in manually_truncated}
        check(f"{ticker}: watermark-truncated chunked assembly matches the manually-truncated "
              f"fixture's date set exactly", assembled_dates == manual_dates,
              f"missing={sorted(manual_dates - assembled_dates)[:5]} "
              f"extra={sorted(assembled_dates - manual_dates)[:5]}")

        manual_df = wiki_transport.assemble_daily_series(manually_truncated)
        assembled_df = wiki_transport.assemble_daily_series(result["daily_rows"])
        # Anchor at the (early) watermark itself, not the original `end` --
        # this test isolates truncation-arithmetic correctness from the
        # separate anchor-alignment-window question (already exercised by
        # _run_for_ticker's full, untruncated comparison above).
        anchor = pd.Timestamp(early_watermark)
        _, manual_z, _ = canonical.compute_zscore_at_anchor(to_weekly(manual_df), anchor)
        _, assembled_z, _ = canonical.compute_zscore_at_anchor(to_weekly(assembled_df), anchor)
        if manual_z is None or assembled_z is None:
            check(f"{ticker}: z-score computable from both the manual truncation and the "
                  f"pipeline's own truncation", False, f"manual={manual_z} assembled={assembled_z}")
        else:
            check(f"{ticker}: watermark-truncated z-score exactly equals the manually-truncated "
                  f"fixture's z-score", manual_z == assembled_z, f"manual={manual_z} assembled={assembled_z}")


# === Live smoke test exit-code mapping (2026-07-31 follow-up): a pure
# function, tested here with zero network calls -- importing
# test_phase2_wikipedia_equivalence only executes its live network code
# inside `if __name__ == "__main__":`, which this import never triggers. ===
def test_live_smoke_verdict_exit_code_mapping():
    import test_phase2_wikipedia_equivalence as live_smoke

    check("exit-code mapping: all PASS -> 0",
          live_smoke.decide_exit_code({"AAPL": "PASS", "AMZN": "PASS"}) == 0)
    check("exit-code mapping: any FAIL -> 1, even alongside a PASS",
          live_smoke.decide_exit_code({"AAPL": "PASS", "AMZN": "FAIL"}) == 1)
    check("exit-code mapping: any FAIL -> 1, even alongside an INCONCLUSIVE (FAIL always wins)",
          live_smoke.decide_exit_code({"AAPL": "INCONCLUSIVE", "AMZN": "FAIL"}) == 1)
    check("exit-code mapping: no FAIL but some INCONCLUSIVE -> 2",
          live_smoke.decide_exit_code({"AAPL": "PASS", "AMZN": "INCONCLUSIVE"}) == 2)
    check("exit-code mapping: all INCONCLUSIVE -> 2",
          live_smoke.decide_exit_code({"AAPL": "INCONCLUSIVE", "AMZN": "INCONCLUSIVE"}) == 2)
    check("exit-code mapping: all FAIL -> 1",
          live_smoke.decide_exit_code({"AAPL": "FAIL", "AMZN": "FAIL"}) == 1)


if __name__ == "__main__":
    operational_cache_existed_before = _ORIGINAL_CACHE_PATH.exists()
    operational_cache_bytes_before = (
        _ORIGINAL_CACHE_PATH.read_bytes() if operational_cache_existed_before else None)

    tmp = _use_temp_cache()
    try:
        for t in TICKERS_UNDER_TEST:
            _run_for_ticker(t)
        test_watermark_truncation_matches_manually_truncated_fixture()
    finally:
        _restore_cache_path(tmp)

    test_live_smoke_verdict_exit_code_mapping()

    operational_cache_exists_after = _ORIGINAL_CACHE_PATH.exists()
    if operational_cache_existed_before:
        unchanged = (operational_cache_exists_after
                     and _ORIGINAL_CACHE_PATH.read_bytes() == operational_cache_bytes_before)
        check("operational cache: pre-existing Phase2_Wikipedia_Cache.csv is byte-identical "
              "before and after this deterministic test", unchanged)
    else:
        check("operational cache: no Phase2_Wikipedia_Cache.csv was created by this deterministic "
              "test (it did not exist before and must not exist after)",
              not operational_cache_exists_after)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("DETERMINISTIC SCIENTIFIC-EQUIVALENCE TEST PASSED FOR ALL TICKERS -- exact date-set and "
              "value equality against frozen, provenance-documented fixtures, no live-network dependency, "
              "and the operational cache was verified untouched.")
        sys.exit(0)
