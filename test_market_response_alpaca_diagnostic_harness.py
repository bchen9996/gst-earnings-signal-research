#!/usr/bin/env python3
# Deterministic tests for the LIVE-DIAGNOSTIC HARNESS itself
# (gst_market_response/diagnostics/alpaca_intraday_diagnostic.py).
#
# A diagnostic verdict is only worth as much as its detectors. The
# 2026-08-04 live run returned a FAILED verdict for both SPY and BRK-B; these
# tests prove, offline and deterministically, that the harness genuinely
# detects the condition it reported (a 79th bar starting at 16:00 ET) and
# that it does NOT report that failure on a clean 78-bar session.
#
# NO live network call anywhere in this file -- both fetch functions are
# replaced with in-process doubles.
#
# Run directly: python test_market_response_alpaca_diagnostic_harness.py

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gst_market_response.diagnostics.alpaca_intraday_diagnostic as diag
from gst_market_response.alpaca_provider import (
    AlpacaCredentials,
    AlpacaFetchResult,
    AlpacaProvenance,
    provider_symbol_for,
)
from gst_market_response.bars import Bar
from gst_market_response.exchange_calendar import (
    expected_bar_starts_utc,
    session_close_utc,
    session_open_utc,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


UTC = timezone.utc
SESSION = date(2026, 8, 3)  # ordinary full XNYS session, 78 expected bars
CREDS = AlpacaCredentials(key_id="AKTESTKEYID0000000", secret_key="TESTSECRET00000000000000")


def _clean_bars(symbol: str, n: int | None = None) -> list[Bar]:
    start, close = session_open_utc(SESSION), session_close_utc(SESSION)
    out, t, px = [], start, 100.0
    while t < close:
        out.append(Bar(symbol=symbol, timestamp_utc=t, open=px, high=px + 1.0, low=px - 1.0,
                       close=px + 0.5, volume=1000))
        px += 0.1
        t += timedelta(minutes=5)
    return out if n is None else out[:n]


def _after_hours_bar(symbol: str) -> Bar:
    """The exact contaminant the live run hit: a bar STARTING at 16:00 ET,
    i.e. at the session close, covering 16:00-16:05 (after hours)."""
    return Bar(symbol=symbol, timestamp_utc=session_close_utc(SESSION),
               open=110.0, high=110.5, low=109.5, close=110.2, volume=1552803)


def _provenance(symbol_canonical: str) -> AlpacaProvenance:
    ps = provider_symbol_for(symbol_canonical)
    return AlpacaProvenance(
        provider="alpaca-historical-sip",
        api_endpoint=f"https://data.alpaca.markets/v2/stocks/{ps}/bars",
        feed="sip", timeframe="5Min", adjustment="raw",
        # ALP-1 fix: the request ends at the LAST EXPECTED BAR START (15:55 ET),
        # never at the 16:00 session close.
        requested_start_utc=expected_bar_starts_utc(SESSION)[0].isoformat(),
        requested_end_utc=expected_bar_starts_utc(SESSION)[-1].isoformat(),
        retrieved_at_utc=datetime.now(UTC).isoformat(),
        http_status=200, retry_count=0, page_count=1,
        raw_response_content_sha256="a" * 64,
        canonical_ticker=symbol_canonical, provider_symbol=ps,
        request_query_string=(
            "adjustment=raw&end=2026-08-03T20%3A00%3A00Z&feed=sip&limit=10000"
            "&sort=asc&start=2026-08-03T13%3A30%3A00Z&timeframe=5Min"
        ),
        response_symbol_echo=ps,
    )


def _run(bars: list[Bar], *, ticker: str = "SPY", daily: dict | None = None,
         prov: AlpacaProvenance | None = None):
    """Runs the harness against injected bars. Restores the real functions
    afterwards so a later test can never accidentally inherit a double."""
    real_fetch, real_daily = diag.fetch_bars_alpaca_sip, diag.fetch_daily_bar_alpaca_sip
    diag.fetch_bars_alpaca_sip = lambda **kw: AlpacaFetchResult(
        bars=bars, provenance=prov or _provenance(ticker)
    )
    diag.fetch_daily_bar_alpaca_sip = lambda **kw: daily
    try:
        with tempfile.TemporaryDirectory() as td:
            return diag.run_diagnostic(
                ticker=ticker, session_date=SESSION, reason_for_selection="deterministic fixture",
                credentials=CREDS, out_dir=Path(td), cross_check_daily=daily is not None,
            )
    finally:
        diag.fetch_bars_alpaca_sip, diag.fetch_daily_bar_alpaca_sip = real_fetch, real_daily


def _failed(report, prefix: str) -> bool:
    return any(c.name.startswith(prefix) for c in report.checks if not c.passed)


# --------------------------------------------------------------------------
def test_clean_78_bar_session_passes():
    report = _run(_clean_bars("SPY"))
    check("1a. A clean 78-bar regular session yields verdict PASSED", report.verdict == "PASSED",
          str(report.failed_checks))
    check("1b. Bar count is reported as 78/78", report.bar_count == 78 and report.expected_bar_count == 78)
    check("1c. First bar reported at 09:30 ET", report.first_bar_et.endswith("09:30:00-04:00"), report.first_bar_et)
    check("1d. Last bar reported at 15:55 ET", report.last_bar_et.endswith("15:55:00-04:00"), report.last_bar_et)
    check("1e. Every check evaluated -- the suite is not silently short-circuiting", len(report.checks) >= 29,
          str(len(report.checks)))


def test_the_live_failure_signature_is_genuinely_detected():
    """The 2026-08-04 live run failed checks 8, 10, 12 and 19 on a 79-bar
    response. Reproduce that response exactly and confirm the harness fails
    the same four checks -- and only those."""
    report = _run(_clean_bars("SPY") + [_after_hours_bar("SPY")])
    check("2a. A 79th bar starting at 16:00 ET yields verdict FAILED", report.verdict == "FAILED")
    check("2b. Check 8 (extended-hours contamination) fails", _failed(report, "8."))
    check("2c. Check 10 (expected bar count) fails", _failed(report, "10."))
    check("2d. Check 12 (last bar at 15:55 ET) fails", _failed(report, "12."))
    check("2e. Check 19 (count/grid agreement) fails", _failed(report, "19."))
    check("2f. Exactly those four checks fail -- the harness is specific, not blanket-failing",
          len(report.failed_checks) == 4, str(report.failed_checks))
    check("2g. Check 9 (no MISSING bar) still PASSES -- the response was over-complete, not incomplete",
          not _failed(report, "9."))
    check("2h. Check 11 (first bar 09:30 ET) still PASSES", not _failed(report, "11."))
    check("2i. The contaminating timestamp is named in the failure detail",
          any("20:00:00" in c.detail for c in report.checks if not c.passed), str(report.failed_checks))


def test_missing_bar_is_detected_and_never_filled():
    report = _run(_clean_bars("SPY", 77))
    check("3a. A 77-bar response yields verdict FAILED", report.verdict == "FAILED")
    check("3b. Check 9 (no missing regular-session bar) fails", _failed(report, "9."))
    check("3c. Check 10 (expected bar count) fails", _failed(report, "10."))
    check("3d. The harness reports 77, not a zero-filled 78", report.bar_count == 77)
    check("3e. Check 8 (contamination) still PASSES -- an incomplete set is not an off-grid set",
          not _failed(report, "8."))


def test_zero_fill_signature_is_detected():
    bars = _clean_bars("SPY")
    bars[40] = Bar(symbol="SPY", timestamp_utc=bars[40].timestamp_utc,
                   open=104.0, high=104.0, low=104.0, close=104.0, volume=0)
    report = _run(bars)
    check("4a. A zero-volume flat O=H=L=C bar is flagged", _failed(report, "17."))
    check("4b. The zero-volume observation is also recorded separately", _failed(report, "18."))
    check("4c. Bar count itself still matches -- proving the scan is independent of the count",
          report.bar_count == 78 and not _failed(report, "10."))


def test_invalid_ohlc_and_negative_volume_detected():
    bars = _clean_bars("SPY")
    bars[10] = Bar(symbol="SPY", timestamp_utc=bars[10].timestamp_utc,
                   open=50.0, high=40.0, low=45.0, close=42.0, volume=100)
    check("5a. An impossible OHLC bar fails check 15", _failed(_run(bars), "15."))

    bars2 = _clean_bars("SPY")
    bars2[10] = Bar(symbol="SPY", timestamp_utc=bars2[10].timestamp_utc,
                    open=100.0, high=101.0, low=99.0, close=100.5, volume=-5)
    check("5b. A negative-volume bar fails check 16", _failed(_run(bars2), "16."))


def test_derivations_are_checked_against_an_independent_recomputation():
    report = _run(_clean_bars("SPY"))
    d21 = next(c for c in report.checks if c.name.startswith("21."))
    check("6a. Check 21 passes on clean bars", d21.passed)
    payload = json.loads(d21.detail)
    check("6b. All five derived quantities are reported numerically",
          set(payload) == {"open_to_close", "open_to_30m", "thirty_min_to_close",
                           "full_session_range", "first_30m_volume_share"}, str(payload))
    check("6c. Exactly six bars are recognised as the first 30 minutes",
          not _failed(report, "20."))


def test_symbol_translation_is_checked_against_alpacas_own_echo():
    report = _run(_clean_bars("BRK-B"), ticker="BRK-B")
    check("7a. BRK-B runs clean end to end", report.verdict == "PASSED", str(report.failed_checks))
    check("7b. The report preserves BOTH the canonical and provider symbols",
          report.ticker == "BRK-B" and report.provider_symbol == "BRK.B")
    check("7c. The report records Alpaca's echoed symbol as BRK.B", report.response_symbol_echo == "BRK.B")

    wrong = _provenance("BRK-B")
    wrong.response_symbol_echo = "BRKB"  # server resolved something else
    report2 = _run(_clean_bars("BRK-B"), ticker="BRK-B", prov=wrong)
    check("7d. A mismatched echo fails check 26 rather than being absorbed", _failed(report2, "26."))


def _daily_for(bars, *, close_mult=1.0, volume_mult=1.0):
    return {
        "open": bars[0].open, "high": max(b.high for b in bars), "low": min(b.low for b in bars),
        "close": bars[-1].close * close_mult,
        "volume": int(sum(b.volume for b in bars) * volume_mult),
        "bar_timestamp_utc": "2026-08-03T04:00:00+00:00",
        "request_query_string": "timeframe=1Day&feed=sip", "http_status": 200,
        "raw_response_content_sha256": "b" * 64,
    }


def test_daily_comparison_is_reported_in_full():
    bars = _clean_bars("SPY")
    report = _run(bars, daily=_daily_for(bars))
    comp = report.daily_bar_comparison
    check("8a. The daily comparison block is present", comp is not None)
    check("8b. All five deltas are recorded, none suppressed",
          set(comp["relative_difference"]) == {"open", "high", "low", "close", "volume"})
    check("8c. A matching daily bar yields verdict PASSED", report.verdict == "PASSED",
          str(report.failed_checks))
    check("8d. The daily bar's own provenance is preserved",
          comp["daily_http_status"] == 200 and comp["daily_raw_response_sha256"] == "b" * 64)


def test_daily_volume_difference_is_informational_not_a_gate():
    """CORRECTION (pass 4). The pass-3 report asserted the daily-vs-aggregate
    volume gap was 'most likely' extended-hours volume. That was an
    unsupported guess and is retracted: Alpaca's 1Day aggregation semantics
    are not established. Volume is therefore recorded as informational only
    and must never gate the verdict."""
    bars = _clean_bars("SPY")
    report = _run(bars, daily=_daily_for(bars, volume_mult=1.2))  # +20% volume difference
    comp = report.daily_bar_comparison

    check("9a. A large volume difference is reported, not zeroed out",
          abs(comp["relative_difference"]["volume"] + 0.1666667) < 1e-4,
          str(comp["relative_difference"]["volume"]))
    check("9b. It does NOT fail the run -- volume is not an equality gate",
          report.verdict == "PASSED", str(report.failed_checks))
    check("9c. It is explicitly labelled informational_only",
          comp["volume_role"] == "informational_only")
    check("9d. Its status is unresolved_provider_aggregation_semantics",
          comp["volume_status"] == "unresolved_provider_aggregation_semantics")
    # Scoped to the daily-comparison block: "extended-hours" legitimately
    # appears in check 8's name (the contamination check), which is a
    # different subject entirely.
    daily_blob = json.dumps(comp, default=str).lower()
    check("9e. The retracted extended-hours explanation appears nowhere in the daily-comparison block",
          "extended-hours" not in daily_blob and "extended hours" not in daily_blob, daily_blob[:200])
    check("9g. No explanation of any kind is offered for the volume difference",
          "no explanation for one is offered" in comp["volume_caveat"])
    check("9f. The caveat states the semantics are unknown rather than offering a guess",
          "not established" in comp["volume_caveat"] and "unknown" in comp["volume_caveat"])


def test_daily_ohlc_remains_a_real_sanity_gate():
    """OHLC is different from volume: both series should describe the same
    regular session, so a material OHLC difference IS a signal."""
    bars = _clean_bars("SPY")
    ok = _run(bars, daily=_daily_for(bars))
    check("10a. Matching OHLC passes the sanity check", not _failed(ok, "29."))

    bad = _run(bars, daily=_daily_for(bars, close_mult=1.05))  # 5% close difference
    check("10b. A 5% close difference FAILS the OHLC sanity check", _failed(bad, "29."))
    check("10c. ...and therefore fails the run", bad.verdict == "FAILED")
    check("10d. The volume check is unaffected by an OHLC discrepancy", not _failed(bad, "30."))
    check("10e. OHLC is labelled a sanity comparison, distinct from volume's role",
          bad.daily_bar_comparison["ohlc_role"] == "sanity_comparison")


def test_report_leaks_neither_credentials_nor_raw_bars():
    report = _run(_clean_bars("SPY"))
    blob = json.dumps(report.to_json_dict(), default=str)
    check("11a. The key id appears nowhere in the report", CREDS.key_id not in blob)
    check("11b. The secret key appears nowhere in the report", CREDS.secret_key not in blob)
    check("11c. The no-credential check itself passes", not _failed(report, "31."))
    check("11d. The no-raw-bars check passes", not _failed(report, "32."))
    check("11e. The report holds no per-bar rows -- 78 bars in, no bar rows out",
          '"t_et"' not in blob and blob.count('"volume"') <= 2, str(blob.count('"volume"')))


def test_a_provider_error_is_reported_as_a_failure_not_an_empty_pass():
    from gst_market_response.alpaca_provider import AlpacaRetryExhaustedError

    real = diag.fetch_bars_alpaca_sip

    def boom(**kw):
        raise AlpacaRetryExhaustedError("HTTP 503 persisted")

    diag.fetch_bars_alpaca_sip = boom
    try:
        with tempfile.TemporaryDirectory() as td:
            report = diag.run_diagnostic(
                ticker="SPY", session_date=SESSION, reason_for_selection="fixture",
                credentials=CREDS, out_dir=Path(td),
            )
    finally:
        diag.fetch_bars_alpaca_sip = real
    check("12a. A provider error yields verdict FAILED", report.verdict == "FAILED")
    check("12b. The failure names the underlying error", "AlpacaRetryExhaustedError" in report.checks[0].detail)
    check("12c. No fallback provider was consulted -- the report has exactly one check",
          len(report.checks) == 1, str(len(report.checks)))


def test_empty_bar_set_fails_rather_than_passing_vacuously():
    report = _run([])
    check("13a. A zero-bar response yields verdict FAILED", report.verdict == "FAILED")
    check("13b. It fails the non-empty check specifically", _failed(report, "6."))


if __name__ == "__main__":
    test_clean_78_bar_session_passes()
    test_the_live_failure_signature_is_genuinely_detected()
    test_missing_bar_is_detected_and_never_filled()
    test_zero_fill_signature_is_detected()
    test_invalid_ohlc_and_negative_volume_detected()
    test_derivations_are_checked_against_an_independent_recomputation()
    test_symbol_translation_is_checked_against_alpacas_own_echo()
    test_daily_comparison_is_reported_in_full()
    test_daily_volume_difference_is_informational_not_a_gate()
    test_daily_ohlc_remains_a_real_sanity_gate()
    test_report_leaks_neither_credentials_nor_raw_bars()
    test_a_provider_error_is_reported_as_a_failure_not_an_empty_pass()
    test_empty_bar_set_fails_rather_than_passing_vacuously()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL ALPACA DIAGNOSTIC HARNESS TESTS PASSED")
        sys.exit(0)
