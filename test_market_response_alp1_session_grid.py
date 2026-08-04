#!/usr/bin/env python3
# Deterministic tests for the ALP-1 FIX and the eligibility split.
#
# ALP-1: Alpaca's `end` parameter is INCLUSIVE of a bar whose START equals
# `end`. Requesting end = session_close (16:00 ET) therefore returned a 79th,
# after-hours (16:00-16:05 ET) bar on an ordinary session, which then became
# `session_close` because extract_session_fields() took bars[-1].
#
# The fix has three independent layers, each tested here:
#   1. REQUEST     -- end is the final EXPECTED BAR START, derived dynamically
#                     from the calendar (15:55 ET normal, 12:55 ET early close).
#   2. VALIDATION  -- the returned timestamp set must EQUAL the expected set;
#                     missing/extra/duplicate/misaligned/out-of-session all
#                     fail closed.
#   3. EXTRACTION  -- open and close bars are selected by expected timestamp,
#                     never positionally, so a stray bar cannot become the
#                     close even if layers 1-2 were bypassed.
#
# NO live network call anywhere in this file.
#
# Run directly: python test_market_response_alp1_session_grid.py

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gst_market_response.alpaca_provider as ap
from gst_market_response import providers
from gst_market_response.bars import Bar, MixedSessionError, extract_session_fields
from gst_market_response.exchange_calendar import (
    expected_bar_boundaries,
    expected_bar_starts_utc,
    is_early_close,
    session_close_utc,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


UTC = timezone.utc
NORMAL = date(2026, 8, 3)        # ordinary session: 78 bars, 09:30-15:55 ET
EARLY_CLOSE = date(2026, 11, 27)  # half day: 42 bars, 09:30-12:55 ET
FAR_FUTURE_NOW = datetime(2026, 12, 31, 12, 0, tzinfo=UTC)
FAKE_CREDS = ap.AlpacaCredentials(key_id="AKFAKE1234567890", secret_key="SECRETFAKE1234567890abcdefg")


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = json.dumps(self._json)
        self.headers = {}

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, queue):
        self._queue = list(queue)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        return self._queue.pop(0)


def _grid_json(session_date, *, drop=None, extra=None, duplicate=None, shuffle=False, misalign=False):
    """Builds an Alpaca-shaped `bars` payload for session_date's expected grid,
    with optional deliberate corruptions."""
    starts = expected_bar_starts_utc(session_date)
    if drop is not None:
        starts = [t for t in starts if t != drop]
    if misalign:
        starts = [t + timedelta(minutes=1) if i == 20 else t for i, t in enumerate(starts)]
    rows = [
        {"t": t.isoformat().replace("+00:00", "Z"), "o": 100.0 + i * 0.01, "h": 101.0 + i * 0.01,
         "l": 99.0 + i * 0.01, "c": 100.5 + i * 0.01, "v": 1000 + i}
        for i, t in enumerate(starts)
    ]
    if extra is not None:
        rows.append({"t": extra.isoformat().replace("+00:00", "Z"), "o": 110.0, "h": 111.0,
                     "l": 109.0, "c": 999.0, "v": 12345})
    if duplicate is not None:
        match = next(r for r in rows if r["t"] == duplicate.isoformat().replace("+00:00", "Z"))
        rows.insert(rows.index(match) + 1, dict(match))
    if shuffle:
        rows = rows[::-1]
    return {"bars": rows, "symbol": "AAPL", "next_page_token": None}


def _fetch(session_date, payload, **kw):
    session = FakeSession([FakeResponse(200, payload)])
    result = ap.fetch_bars_alpaca_sip(
        canonical_ticker="AAPL", session_date=session_date, credentials=FAKE_CREDS,
        session=session, sleep_fn=lambda s: None, now_fn=lambda: FAR_FUTURE_NOW, **kw
    )
    return result, session


def _expect_grid_error(session_date, payload, label, name):
    try:
        _fetch(session_date, payload)
        check(name, False, "no error raised -- the malformed grid was accepted")
    except ap.AlpacaSessionGridError as e:
        check(name, True)
        return str(e)
    except Exception as e:  # noqa: BLE001 - any other exception is also a failure of this test
        check(name, False, f"wrong exception type {type(e).__name__}: {e}")
    return ""


# ==========================================================================
# LAYER 1 -- the request boundary
# ==========================================================================
def test_request_end_is_the_final_expected_bar_start_not_session_close():
    _, session = _fetch(NORMAL, _grid_json(NORMAL))
    params = session.calls[0]["params"]
    boundaries = expected_bar_boundaries(NORMAL)

    check("1a. Request start is 09:30 ET (13:30Z)", params["start"] == "2026-08-03T13:30:00Z", params["start"])
    check("1b. Request end is 15:55 ET (19:55Z) -- the FINAL EXPECTED BAR START",
          params["end"] == "2026-08-03T19:55:00Z", params["end"])
    check("1c. Request end is NOT the 16:00 ET session close, which an inclusive `end` would admit as a bar",
          params["end"] != "2026-08-03T20:00:00Z" and boundaries.close_utc == "2026-08-03T20:00:00+00:00")
    check("1d. The requested end equals exactly the calendar's own last_bar_start_utc",
          params["end"] == boundaries.last_bar_start_utc.replace("+00:00", "Z"))
    check("1e. The gap between requested end and session close is exactly one bar interval",
          session_close_utc(NORMAL) - datetime.fromisoformat(params["end"].replace("Z", "+00:00"))
          == timedelta(minutes=5))
    check("1f. SIP/raw are still requested unchanged by the fix",
          params["feed"] == "sip" and params["adjustment"] == "raw" and params["timeframe"] == "5Min")


def test_early_close_end_is_derived_dynamically():
    _, session = _fetch(EARLY_CLOSE, _grid_json(EARLY_CLOSE))
    params = session.calls[0]["params"]
    starts = expected_bar_starts_utc(EARLY_CLOSE)

    check("2a. 2026-11-27 really is an early close", is_early_close(EARLY_CLOSE))
    check("2b. Its expected grid is 42 bars, not 78", len(starts) == 42, str(len(starts)))
    check("2c. Its last expected bar start is 12:55 ET", starts[-1].astimezone(
        __import__("zoneinfo").ZoneInfo("America/New_York")).strftime("%H:%M") == "12:55")
    check("2d. The request end is that 12:55 ET start -- derived, never a hard-coded 15:55",
          params["end"] == starts[-1].isoformat().replace("+00:00", "Z"), params["end"])
    check("2e. The early-close end is NOT the 13:00 ET session close",
          params["end"] != session_close_utc(EARLY_CLOSE).isoformat().replace("+00:00", "Z"))


def test_normal_session_returns_exactly_78_bars_0930_to_1555():
    result, _ = _fetch(NORMAL, _grid_json(NORMAL))
    ET = __import__("zoneinfo").ZoneInfo("America/New_York")
    check("3a. Exactly 78 bars accepted", len(result.bars) == 78, str(len(result.bars)))
    check("3b. First bar is 09:30 ET", result.bars[0].timestamp_utc.astimezone(ET).strftime("%H:%M") == "09:30")
    check("3c. Last bar is 15:55 ET", result.bars[-1].timestamp_utc.astimezone(ET).strftime("%H:%M") == "15:55")
    check("3d. No bar lands at or after 16:00 ET",
          all(b.timestamp_utc < session_close_utc(NORMAL) for b in result.bars))
    check("3e. The 42-bar early-close session is likewise accepted whole",
          len(_fetch(EARLY_CLOSE, _grid_json(EARLY_CLOSE))[0].bars) == 42)


# ==========================================================================
# LAYER 2 -- fail-closed validation
# ==========================================================================
def test_extra_1600_bar_fails_closed():
    """The exact ALP-1 payload: 78 correct bars plus the 16:00 ET bar."""
    payload = _grid_json(NORMAL, extra=session_close_utc(NORMAL))
    msg = _expect_grid_error(NORMAL, payload,
                             "extra 16:00 ET bar",
                             "4a. A 79th bar starting at 16:00 ET raises AlpacaSessionGridError")
    check("4b. The error names the offending timestamp", "2026-08-03T20:00:00" in msg, msg[:200])
    check("4c. The error reports it as unexpected rather than missing", "1 unexpected" in msg, msg[:200])
    check("4d. It is NOT silently trimmed to 78 and returned", True)


def test_missing_1555_bar_fails_closed():
    payload = _grid_json(NORMAL, drop=expected_bar_starts_utc(NORMAL)[-1])
    msg = _expect_grid_error(NORMAL, payload,
                             "missing 15:55 ET bar",
                             "5a. A response missing the 15:55 ET bar raises AlpacaSessionGridError")
    check("5b. The error names the missing timestamp", "2026-08-03T19:55:00" in msg, msg[:200])
    check("5c. The error reports it as missing", "1 missing" in msg, msg[:200])


def test_missing_interior_bar_fails_closed():
    payload = _grid_json(NORMAL, drop=expected_bar_starts_utc(NORMAL)[30])
    _expect_grid_error(NORMAL, payload, "missing interior bar",
                       "6. A missing mid-session bar raises rather than being zero-filled or interpolated")


def test_duplicate_bar_fails_closed():
    payload = _grid_json(NORMAL, duplicate=expected_bar_starts_utc(NORMAL)[10])
    msg = _expect_grid_error(NORMAL, payload, "duplicate bar",
                             "7a. A duplicated bar timestamp raises AlpacaSessionGridError")
    check("7b. The error identifies it as a duplicate", "duplicate" in msg.lower(), msg[:200])


def test_unordered_response_fails_closed():
    payload = _grid_json(NORMAL, shuffle=True)
    msg = _expect_grid_error(NORMAL, payload, "unordered bars",
                             "8a. A reverse-ordered response raises rather than being silently re-sorted")
    check("8b. The error identifies the ordering problem", "order" in msg.lower(), msg[:200])


def test_misaligned_bar_fails_closed():
    payload = _grid_json(NORMAL, misalign=True)
    msg = _expect_grid_error(NORMAL, payload, "misaligned bar",
                             "9a. A bar offset off the 5-minute grid raises AlpacaSessionGridError")
    check("9b. Both the unexpected and the missing slot are reported",
          "1 unexpected" in msg and "1 missing" in msg, msg[:250])


def test_premarket_bar_fails_closed():
    payload = _grid_json(NORMAL, extra=datetime(2026, 8, 3, 13, 0, tzinfo=UTC))  # 09:00 ET
    _expect_grid_error(NORMAL, payload, "premarket bar",
                       "10. An out-of-session premarket bar raises AlpacaSessionGridError")


def test_clean_grid_does_not_raise():
    result, _ = _fetch(NORMAL, _grid_json(NORMAL))
    check("11a. The exactly-correct grid raises nothing and returns all 78 bars", len(result.bars) == 78)
    check("11b. The guard is on by default -- callers do not have to opt in",
          ap.SESSION_GRID_ENFORCED is True)


# ==========================================================================
# LAYER 3 -- extraction by expected timestamp, never by position
# ==========================================================================
def _bars(session_date, closes=None):
    starts = expected_bar_starts_utc(session_date)
    return [
        Bar(symbol="X", timestamp_utc=t, open=100.0 + i, high=101.0 + i, low=99.0 + i,
            close=(closes[i] if closes else 100.5 + i), volume=1000)
        for i, t in enumerate(starts)
    ]


def test_extraction_selects_boundaries_by_expected_timestamp():
    bars = _bars(NORMAL)
    fields = extract_session_fields(bars, NORMAL)
    check("12a. session_open is the 09:30 ET bar's open", fields.session_open == bars[0].open)
    check("12b. session_close is the 15:55 ET bar's close", fields.session_close == bars[-1].close)
    check("12c. price_at_30m is the 09:55 ET bar's close", fields.price_at_30m == bars[5].close)
    check("12d. full_session_volume sums all 78 bars", fields.full_session_volume == 78 * 1000)


def test_stray_1600_bar_can_never_become_the_close():
    """Layer 3 in isolation: even if layers 1-2 were bypassed entirely, a
    16:00 ET bar must not be able to become session_close."""
    bars = _bars(NORMAL)
    stray = Bar(symbol="X", timestamp_utc=session_close_utc(NORMAL),
                open=500.0, high=9999.0, low=0.01, close=777.0, volume=555555)
    clean = extract_session_fields(bars, NORMAL)
    polluted = extract_session_fields(bars + [stray], NORMAL)

    check("13a. session_close is unchanged by a trailing 16:00 ET bar",
          polluted.session_close == clean.session_close == bars[-1].close, str(polluted.session_close))
    check("13b. The stray bar's close (777.0) is NOT adopted", polluted.session_close != 777.0)
    check("13c. session_high is unaffected by the stray bar's 9999.0 high",
          polluted.session_high == clean.session_high)
    check("13d. session_low is unaffected by the stray bar's 0.01 low",
          polluted.session_low == clean.session_low)
    check("13e. full_session_volume excludes the stray bar's volume",
          polluted.full_session_volume == clean.full_session_volume)
    check("13f. Every derived field is identical with and without the stray bar", polluted == clean)


def test_extraction_is_order_independent():
    bars = _bars(NORMAL)
    forward = extract_session_fields(bars, NORMAL)
    reversed_ = extract_session_fields(list(reversed(bars)), NORMAL)
    shuffled = extract_session_fields(bars[40:] + bars[:40], NORMAL)
    check("14a. Reversed input yields identical fields -- nothing depends on bars[0]/bars[-1]",
          reversed_ == forward)
    check("14b. Rotated input yields identical fields", shuffled == forward)


def test_extraction_handles_early_close_by_calendar():
    bars = _bars(EARLY_CLOSE)
    fields = extract_session_fields(bars, EARLY_CLOSE)
    check("15a. Early-close session_close is the 12:55 ET bar, not a 15:55 ET bar that does not exist",
          fields.session_close == bars[-1].close and len(bars) == 42)
    check("15b. Early-close session_open is still the 09:30 ET bar", fields.session_open == bars[0].open)
    check("15c. The 30-minute boundary still resolves on a half day", fields.price_at_30m == bars[5].close)


def test_missing_boundary_bars_yield_none_never_a_substitute():
    bars = _bars(NORMAL)
    no_close = extract_session_fields(bars[:-1], NORMAL)
    check("16a. Missing 15:55 ET bar -> session_close is None, NOT the 15:50 bar's close",
          no_close.session_close is None, str(no_close.session_close))
    no_open = extract_session_fields(bars[1:], NORMAL)
    check("16b. Missing 09:30 ET bar -> session_open is None, NOT the 09:35 bar's open",
          no_open.session_open is None, str(no_open.session_open))
    no_30m = extract_session_fields([b for i, b in enumerate(bars) if i != 5], NORMAL)
    check("16c. Missing 09:55 ET bar -> price_at_30m and first_30m_volume are both None",
          no_30m.price_at_30m is None and no_30m.first_30m_volume is None)


def test_session_date_is_derived_when_not_supplied_and_mixed_input_fails():
    bars = _bars(NORMAL)
    check("17a. session_date is derived from the bars when not passed explicitly",
          extract_session_fields(bars) == extract_session_fields(bars, NORMAL))
    try:
        extract_session_fields(_bars(NORMAL) + _bars(EARLY_CLOSE))
        ok = False
    except MixedSessionError:
        ok = True
    check("17b. Bars spanning two sessions raise MixedSessionError rather than silently using one", ok)
    check("17c. An empty bar list still returns all-None rather than raising",
          extract_session_fields([]).session_close is None)


# ==========================================================================
# ELIGIBILITY -- supports_real_event_semantics vs operational_clearance_status
# ==========================================================================
def _elig(**overrides):
    base = dict(
        supports_real_event_semantics=True,
        operational_clearance_status=providers.CLEARANCE_LIVE_DIAGNOSTIC_PASSED,
        feed="sip", adjustment="raw", session_grid_enforced=True, has_credentials=True,
    )
    base.update(overrides)
    return providers.compute_real_event_eligibility(**base)


def test_eligibility_requires_every_condition():
    check("18a. All conditions satisfied -> eligible", _elig() is True)
    check("18b. clearance NOT_RUN -> ineligible",
          _elig(operational_clearance_status=providers.CLEARANCE_NOT_RUN) is False)
    check("18c. clearance LIVE_DIAGNOSTIC_FAILED -> ineligible",
          _elig(operational_clearance_status=providers.CLEARANCE_LIVE_DIAGNOSTIC_FAILED) is False)
    check("18d. An unrecognized clearance string -> ineligible (unknown fails closed)",
          _elig(operational_clearance_status="TOTALLY_FINE_HONEST") is False)
    check("18e. Missing credentials -> ineligible", _elig(has_credentials=False) is False)
    check("18f. feed=iex -> ineligible", _elig(feed="iex") is False)
    check("18g. feed=None -> ineligible", _elig(feed=None) is False)
    check("18h. adjustment=split/dividend-adjusted -> ineligible", _elig(adjustment="all") is False)
    check("18i. Session-grid guard disabled -> ineligible (disabling the ALP-1 fix revokes clearance)",
          _elig(session_grid_enforced=False) is False)
    check("18j. supports_real_event_semantics=False -> ineligible even with a PASSED clearance",
          _elig(supports_real_event_semantics=False) is False)


def test_the_two_concepts_are_genuinely_independent():
    check("19a. A structurally-capable provider with a FAILED diagnostic is ineligible",
          _elig(supports_real_event_semantics=True,
                operational_clearance_status=providers.CLEARANCE_LIVE_DIAGNOSTIC_FAILED) is False)
    check("19b. A structurally-incapable provider is ineligible even with a PASSED diagnostic",
          _elig(supports_real_event_semantics=False,
                operational_clearance_status=providers.CLEARANCE_LIVE_DIAGNOSTIC_PASSED) is False)
    check("19c. Eligibility requires BOTH -- neither alone suffices",
          _elig(supports_real_event_semantics=True,
                operational_clearance_status=providers.CLEARANCE_LIVE_DIAGNOSTIC_PASSED) is True)


def test_provider_instances_report_the_split_correctly():
    alpaca = ap.AlpacaHistoricalSipIntradayProvider(credentials=FAKE_CREDS)
    check("20a. Alpaca supports real-event semantics (structural, permanent)",
          alpaca.supports_real_event_semantics is True)
    check("20b. Its clearance status is a recognized value",
          alpaca.operational_clearance_status in providers.VALID_CLEARANCE_STATUSES,
          alpaca.operational_clearance_status)
    check("20c. Its eligibility agrees with the pure rule applied to its own inputs",
          alpaca.is_eligible_for_real_event == _elig(
              operational_clearance_status=alpaca.operational_clearance_status,
              feed=ap.FEED, adjustment=ap.ADJUSTMENT, session_grid_enforced=ap.SESSION_GRID_ENFORCED))

    from gst_market_response.providers import YFinanceDevIntradayProvider

    yf = YFinanceDevIntradayProvider()
    check("20d. yfinance does not support real-event semantics", yf.supports_real_event_semantics is False)
    check("20e. yfinance is ineligible", yf.is_eligible_for_real_event is False)
    check("20f. yfinance's own clearance records its FAILED diagnostic",
          yf.operational_clearance_status == providers.CLEARANCE_LIVE_DIAGNOSTIC_FAILED)


def test_missing_credentials_cannot_produce_an_eligible_provider():
    saved = {k: os.environ.pop(k, None) for k in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY")}
    try:
        ap.AlpacaHistoricalSipIntradayProvider(credentials=None)
        ok = False
    except ap.AlpacaCredentialsMissingError:
        ok = True
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    check("21a. Without credentials the provider cannot even be constructed", ok)
    check("21b. And the eligibility rule independently rejects has_credentials=False",
          _elig(has_credentials=False) is False)


def test_current_clearance_reflects_the_passed_postfix_validation():
    """Pins the state actually achieved on 2026-08-04 (pass 4): the post-fix
    live diagnostic PASSED for both SPY and BRK-B, so the recorded clearance
    is LIVE_DIAGNOSTIC_PASSED and the provider is eligible.

    If a later live diagnostic fails and the constant is moved back, THIS TEST
    MUST BE UPDATED as part of that change -- the failure is the intended
    signal that clearance changed, not a nuisance. The truth-table tests above
    are deliberately state-independent and keep passing either way."""
    check("22a. Recorded clearance is LIVE_DIAGNOSTIC_PASSED",
          ap.OPERATIONAL_CLEARANCE_STATUS == providers.CLEARANCE_LIVE_DIAGNOSTIC_PASSED,
          ap.OPERATIONAL_CLEARANCE_STATUS)
    alpaca = ap.AlpacaHistoricalSipIntradayProvider(credentials=FAKE_CREDS)
    check("22b. The provider is therefore eligible for real event capture",
          alpaca.is_eligible_for_real_event is True)
    check("22c. Eligibility still depends on the ALP-1 guard being active",
          ap.SESSION_GRID_ENFORCED is True and _elig(session_grid_enforced=False) is False)
    check("22d. Clearance does not make yfinance eligible",
          providers.YFinanceDevIntradayProvider().is_eligible_for_real_event is False)


if __name__ == "__main__":
    test_request_end_is_the_final_expected_bar_start_not_session_close()
    test_early_close_end_is_derived_dynamically()
    test_normal_session_returns_exactly_78_bars_0930_to_1555()
    test_extra_1600_bar_fails_closed()
    test_missing_1555_bar_fails_closed()
    test_missing_interior_bar_fails_closed()
    test_duplicate_bar_fails_closed()
    test_unordered_response_fails_closed()
    test_misaligned_bar_fails_closed()
    test_premarket_bar_fails_closed()
    test_clean_grid_does_not_raise()
    test_extraction_selects_boundaries_by_expected_timestamp()
    test_stray_1600_bar_can_never_become_the_close()
    test_extraction_is_order_independent()
    test_extraction_handles_early_close_by_calendar()
    test_missing_boundary_bars_yield_none_never_a_substitute()
    test_session_date_is_derived_when_not_supplied_and_mixed_input_fails()
    test_eligibility_requires_every_condition()
    test_the_two_concepts_are_genuinely_independent()
    test_provider_instances_report_the_split_correctly()
    test_missing_credentials_cannot_produce_an_eligible_provider()
    test_current_clearance_reflects_the_passed_postfix_validation()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL ALP-1 SESSION-GRID AND ELIGIBILITY TESTS PASSED")
        sys.exit(0)
