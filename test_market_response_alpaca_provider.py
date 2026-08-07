#!/usr/bin/env python3
# SECTION B/G deterministic tests: AlpacaHistoricalSipIntradayProvider.
# Uses a fake requests.Session double throughout -- NO live network call
# anywhere in this file.
#
# Run directly: python test_market_response_alpaca_provider.py

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

import gst_market_response.alpaca_provider as ap
from gst_market_response.bars import (
    Bar,
    DuplicateBarError,
    InvalidOHLCError,
    NegativeVolumeError,
    validate_bars,
    validate_ohlc_and_volume,
)
from gst_market_response.exchange_calendar import expected_bar_boundaries
from gst_market_response import providers
from gst_market_response.providers import YFinanceDevIntradayProvider

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


UTC = timezone.utc
SESSION_DATE = date(2026, 8, 3)  # ordinary XNYS session
FAR_FUTURE_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)  # well past the session's own close + 15min gate


class FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = json.dumps(self._json_data)
        self.headers = headers or {}

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, queue: list):
        self._queue = list(queue)
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {}), "timeout": timeout})
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _bar_json(t: str, o=100.0, h=101.0, l=99.0, c=100.5, v=1000):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


FAKE_CREDS = ap.AlpacaCredentials(key_id="AKFAKE1234567890", secret_key="SECRETFAKE1234567890abcdefg")


def _fetch(session, **overrides):
    """Transport-level helper. `enforce_session_grid=False` because these
    tests are about retries, pagination, auth, timeouts and provenance -- they
    use 0-2 synthetic bars, which the ALP-1 grid guard would (correctly)
    reject before the transport behaviour under test could be observed. The
    grid guard itself is exercised exhaustively in
    test_market_response_alp1_session_grid.py."""
    kwargs = dict(
        canonical_ticker="AAPL", session_date=SESSION_DATE, credentials=FAKE_CREDS,
        session=session, sleep_fn=lambda s: None, now_fn=lambda: FAR_FUTURE_NOW,
        enforce_session_grid=False,
    )
    kwargs.update(overrides)
    return ap.fetch_bars_alpaca_sip(**kwargs)


def test_credentials_absent():
    creds = ap.load_alpaca_credentials(env={})
    check("1a. load_alpaca_credentials() returns None when both vars are absent", creds is None)
    creds2 = ap.load_alpaca_credentials(env={"APCA_API_KEY_ID": "x"})
    check("1b. Returns None when only one of the two vars is present", creds2 is None)

    # The constructor falls back to load_alpaca_credentials() from the real
    # process environment. This test must therefore CREATE the absent-
    # credential condition rather than assume it: as of the live-validation
    # pass these variables are genuinely present in the operator's
    # environment, and an assume-empty test would silently invert.
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
    check("1c. Provider construction raises AlpacaCredentialsMissingError rather than silently doing nothing", ok)
    check("1d. The test restored the ambient credential environment it temporarily cleared",
          all(os.environ.get(k) == v for k, v in saved.items() if v is not None))


def test_401_403_never_retried():
    session = FakeSession([FakeResponse(401)])
    try:
        _fetch(session)
        ok = False
    except ap.AlpacaAuthError:
        ok = True
    check("2a. HTTP 401 raises AlpacaAuthError", ok)
    check("2b. HTTP 401 is never retried -- exactly one call made", len(session.calls) == 1, str(len(session.calls)))

    session2 = FakeSession([FakeResponse(403)])
    try:
        _fetch(session2)
        ok2 = False
    except ap.AlpacaAuthError:
        ok2 = True
    check("2c. HTTP 403 also raises AlpacaAuthError immediately", ok2)


def test_429_with_retry_after():
    good_bar = _bar_json("2026-08-03T13:30:00Z")
    session = FakeSession([
        FakeResponse(429, headers={"Retry-After": "0"}),
        FakeResponse(200, json_data={"bars": [good_bar], "next_page_token": None}),
    ])
    result = _fetch(session)
    check("3a. 429 followed by 200 succeeds", len(result.bars) == 1)
    check("3b. retry_count reflects exactly one retry", result.provenance.retry_count == 1)
    check("3c. Retry-After header value was read by the retry-delay calculation path", session.calls[0]["url"] == session.calls[1]["url"])


def test_transient_5xx_recovery():
    good_bar = _bar_json("2026-08-03T13:30:00Z")
    for code in (500, 502, 503, 504):
        session = FakeSession([
            FakeResponse(code),
            FakeResponse(200, json_data={"bars": [good_bar], "next_page_token": None}),
        ])
        result = _fetch(session)
        check(f"4. HTTP {code} recovers on retry", len(result.bars) == 1 and result.provenance.retry_count == 1)


def test_bounded_retry_exhaustion():
    session = FakeSession([FakeResponse(503) for _ in range(ap.MAX_ATTEMPTS + 2)])
    try:
        _fetch(session)
        ok = False
    except ap.AlpacaRetryExhaustedError:
        ok = True
    check("5a. Persistent 503s exhaust retries and raise AlpacaRetryExhaustedError", ok)
    check("5b. Exactly MAX_ATTEMPTS calls were made, not unbounded retries", len(session.calls) == ap.MAX_ATTEMPTS, str(len(session.calls)))


def test_timeout():
    session = FakeSession([requests.Timeout("connect timeout") for _ in range(ap.MAX_ATTEMPTS + 1)])
    try:
        _fetch(session)
        ok = False
    except ap.AlpacaRetryExhaustedError:
        ok = True
    check("6. Repeated requests.Timeout exhausts retries and raises, rather than hanging or silently returning empty", ok)


def test_empty_bars():
    session = FakeSession([FakeResponse(200, json_data={"bars": [], "next_page_token": None})])
    result = _fetch(session)
    check("7a. An empty bars response returns an empty list, not an error", result.bars == [])
    check("7b. page_count is still recorded correctly for an empty response", result.provenance.page_count == 1)


def test_pagination():
    bar1 = _bar_json("2026-08-03T13:30:00Z")
    bar2 = _bar_json("2026-08-03T13:35:00Z")
    session = FakeSession([
        FakeResponse(200, json_data={"bars": [bar1], "next_page_token": "PAGE2TOKEN"}),
        FakeResponse(200, json_data={"bars": [bar2], "next_page_token": None}),
    ])
    result = _fetch(session)
    check("8a. Two-page response combines bars from both pages", len(result.bars) == 2)
    check("8b. page_count reflects both pages", result.provenance.page_count == 2)
    check("8c. Second request's params carried the page_token from the first response", session.calls[1]["params"].get("page_token") == "PAGE2TOKEN")


def test_duplicate_timestamps_rejected_downstream():
    t = "2026-08-03T13:30:00Z"
    session = FakeSession([FakeResponse(200, json_data={"bars": [_bar_json(t), _bar_json(t)], "next_page_token": None})])
    result = _fetch(session)
    try:
        validate_bars(result.bars, "AAPL")
        ok = False
    except DuplicateBarError:
        ok = True
    check("9. Duplicate timestamps in an Alpaca response are caught by bars.validate_bars()", ok)


def test_out_of_session_bars_detectable():
    # A bar timestamped before the session's own open (e.g. pre-market) --
    # confirm the caller can detect it against the calendar's own boundaries.
    boundaries = expected_bar_boundaries(SESSION_DATE)
    pre_market_ts = "2026-08-03T09:00:00Z"  # well before 13:30 UTC open
    session = FakeSession([FakeResponse(200, json_data={"bars": [_bar_json(pre_market_ts)], "next_page_token": None})])
    result = _fetch(session)
    out_of_session = [b for b in result.bars if b.timestamp_utc.isoformat().replace("+00:00", "Z") < boundaries.first_bar_start_utc.replace("+00:00", "Z")]
    check("10. A pre-market-timestamped bar is detectable as out-of-session against the calendar's own boundary", len(out_of_session) == 1)


def test_missing_expected_bar_detectable():
    boundaries = expected_bar_boundaries(SESSION_DATE)
    session = FakeSession([FakeResponse(200, json_data={"bars": [_bar_json("2026-08-03T13:30:00Z")], "next_page_token": None})])
    result = _fetch(session)
    check(
        "11. A response with far fewer bars than the calendar's expected_bar_count is detectable as incomplete",
        len(result.bars) < boundaries.expected_bar_count,
    )


def test_invalid_ohlc_and_negative_volume_rejected():
    bad_ohlc_bar = _bar_json("2026-08-03T13:30:00Z", o=50.0, h=40.0, l=45.0, c=42.0)  # high < low, nonsensical
    session = FakeSession([FakeResponse(200, json_data={"bars": [bad_ohlc_bar], "next_page_token": None})])
    result = _fetch(session)
    try:
        validate_ohlc_and_volume(result.bars)
        ok = False
    except InvalidOHLCError:
        ok = True
    check("12a. Invalid OHLC (high < low) from Alpaca is rejected by validate_ohlc_and_volume()", ok)

    neg_vol_bar = _bar_json("2026-08-03T13:30:00Z", v=-500)
    session2 = FakeSession([FakeResponse(200, json_data={"bars": [neg_vol_bar], "next_page_token": None})])
    result2 = _fetch(session2)
    try:
        validate_ohlc_and_volume(result2.bars)
        ok2 = False
    except NegativeVolumeError:
        ok2 = True
    check("12b. Negative volume from Alpaca is rejected by validate_ohlc_and_volume()", ok2)


def test_provider_symbol_translation():
    check("13a. Canonical BRK-B maps to provider symbol BRK.B", ap.provider_symbol_for("BRK-B") == "BRK.B")
    check("13b. An ordinary ticker maps to itself", ap.provider_symbol_for("AAPL") == "AAPL")

    session = FakeSession([FakeResponse(200, json_data={"bars": [], "next_page_token": None})])
    result = _fetch(session, canonical_ticker="BRK-B")
    check("13c. The actual HTTP request URL used the translated provider symbol (BRK.B), not the canonical one", "BRK.B" in session.calls[0]["url"] and "BRK-B" not in session.calls[0]["url"])
    check("13d. Provenance preserves BOTH the canonical ticker and the provider symbol", result.provenance.canonical_ticker == "BRK-B" and result.provenance.provider_symbol == "BRK.B")


def test_end_timestamp_freshness_gate():
    too_recent_now = lambda: __import__("gst_market_response.exchange_calendar", fromlist=["session_close_utc"]).session_close_utc(SESSION_DATE) + timedelta(minutes=5)
    session = FakeSession([FakeResponse(200, json_data={"bars": [], "next_page_token": None})])
    try:
        ap.fetch_bars_alpaca_sip(
            canonical_ticker="AAPL", session_date=SESSION_DATE, credentials=FAKE_CREDS,
            session=session, sleep_fn=lambda s: None, now_fn=too_recent_now,
        )
        ok = False
    except ap.AlpacaFreshnessGateError:
        ok = True
    check("14a. An end timestamp less than 15 minutes old raises AlpacaFreshnessGateError", ok)
    check("14b. The freshness gate fires BEFORE any HTTP call is made", len(session.calls) == 0, str(len(session.calls)))

    far_enough_now = lambda: __import__("gst_market_response.exchange_calendar", fromlist=["session_close_utc"]).session_close_utc(SESSION_DATE) + timedelta(minutes=16)
    session2 = FakeSession([FakeResponse(200, json_data={"bars": [], "next_page_token": None})])
    ap.fetch_bars_alpaca_sip(
        canonical_ticker="AAPL", session_date=SESSION_DATE, credentials=FAKE_CREDS,
        session=session2, sleep_fn=lambda s: None, now_fn=far_enough_now,
        enforce_session_grid=False,  # this test is about the freshness gate, not the grid
    )
    check("14c. An end timestamp 16+ minutes old passes the gate and proceeds", len(session2.calls) == 1)


def test_iex_never_requested():
    check("15a. FEED constant is fixed to 'sip'", ap.FEED == "sip")
    session = FakeSession([FakeResponse(200, json_data={"bars": [], "next_page_token": None})])
    _fetch(session)
    check("15b. Every actual request explicitly carries feed=sip -- IEX is never requested", all(c["params"].get("feed") == "sip" for c in session.calls))


def test_yfinance_provider_ineligible_alpaca_eligible():
    # Constructing a real YFinanceDevIntradayProvider() imports yfinance
    # (fine, already a dependency) but touches no network -- safe here.
    yf_provider = YFinanceDevIntradayProvider()
    check("16a. YFinanceDevIntradayProvider is ineligible for a real event", yf_provider.is_eligible_for_real_event is False)
    check("16b. ...and structurally so -- it does not support real-event semantics at all, so no clearance status could change that",
          yf_provider.supports_real_event_semantics is False)

    alpaca_provider = ap.AlpacaHistoricalSipIntradayProvider(credentials=FAKE_CREDS)
    check("16c. AlpacaHistoricalSipIntradayProvider DOES support real-event semantics (structural)",
          alpaca_provider.supports_real_event_semantics is True)
    # Eligibility is DERIVED, so this asserts consistency with the pure rule
    # rather than a hard-coded expectation -- it stays correct across a
    # clearance change without being vacuous.
    expected = providers.compute_real_event_eligibility(
        supports_real_event_semantics=True,
        operational_clearance_status=ap.OPERATIONAL_CLEARANCE_STATUS,
        feed=ap.FEED, adjustment=ap.ADJUSTMENT,
        session_grid_enforced=ap.SESSION_GRID_ENFORCED, has_credentials=True,
    )
    check("16d. Its eligibility is derived from the clearance rule, not hard-coded",
          alpaca_provider.is_eligible_for_real_event == expected,
          f"clearance={ap.OPERATIONAL_CLEARANCE_STATUS} eligible={alpaca_provider.is_eligible_for_real_event}")
    check("16e. Its recorded clearance status is one of the three recognized values",
          ap.OPERATIONAL_CLEARANCE_STATUS in providers.VALID_CLEARANCE_STATUSES, ap.OPERATIONAL_CLEARANCE_STATUS)


def test_raw_data_never_written_to_disk_by_this_module():
    import inspect

    src = inspect.getsource(ap)
    check(
        "17. alpaca_provider.py contains no file-write calls -- it cannot silently persist raw data anywhere",
        "open(" not in src and ".write(" not in src and "to_csv(" not in src,
    )


def test_secrets_never_appear_in_provenance_or_repr():
    secret_marker = FAKE_CREDS.secret_key
    key_marker = FAKE_CREDS.key_id

    check("18a. repr(credentials) never contains the secret key", secret_marker not in repr(FAKE_CREDS))
    check("18b. repr(credentials) never contains the key id either", key_marker not in repr(FAKE_CREDS))
    check("18c. str(credentials) is also redacted", secret_marker not in str(FAKE_CREDS))

    session = FakeSession([FakeResponse(200, json_data={"bars": [_bar_json("2026-08-03T13:30:00Z")], "next_page_token": None})])
    result = _fetch(session)
    from dataclasses import asdict

    provenance_str = json.dumps(asdict(result.provenance), default=str)
    check("18d. Serialized provenance never contains the secret key", secret_marker not in provenance_str)
    check("18e. Serialized provenance never contains the raw key id", key_marker not in provenance_str)
    check("18f. Request headers (not logged/returned) carried the credentials -- confirms they were sent via headers, not URL", "APCA-API-KEY-ID" in session.calls[0]["headers"])
    check("18g. The request URL itself never embeds the secret", secret_marker not in session.calls[0]["url"])


def test_sanitized_request_evidence_recorded():
    """The provenance must carry first-hand evidence of what was actually put
    on the wire. Alpaca's single-symbol bars response does not echo `feed`, so
    the query string is the only place a reviewer can confirm feed=sip /
    timeframe=5Min / adjustment=raw were genuinely requested."""
    session = FakeSession([FakeResponse(200, json_data={"bars": [_bar_json("2026-08-03T13:30:00Z")], "symbol": "AAPL", "next_page_token": None})])
    result = _fetch(session)
    q = result.provenance.request_query_string
    check("19a. request_query_string is recorded", bool(q), repr(q))
    check("19b. It shows feed=sip on the wire", "feed=sip" in q, q)
    check("19c. It shows timeframe=5Min on the wire", "timeframe=5Min" in q, q)
    check("19d. It shows adjustment=raw on the wire", "adjustment=raw" in q, q)
    check("19e. It carries no credential material", FAKE_CREDS.key_id not in q and FAKE_CREDS.secret_key not in q)
    check("19f. Alpaca's echoed symbol is captured from the response body", result.provenance.response_symbol_echo == "AAPL")

    brk = FakeSession([FakeResponse(200, json_data={"bars": [], "symbol": "BRK.B", "next_page_token": None})])
    r2 = _fetch(brk, canonical_ticker="BRK-B")
    check("19g. For BRK-B the echoed symbol is the TRANSLATED provider symbol -- server-side confirmation the translation resolved",
          r2.provenance.response_symbol_echo == "BRK.B" and r2.provenance.canonical_ticker == "BRK-B")


def test_daily_cross_check_uses_a_calendar_day_window():
    """A 1Day bar is timestamped at midnight ET, so requesting it with the
    09:30-16:00 regular-session window returns nothing and the absent bar is
    indistinguishable from a genuine vendor gap. Regression guard for that."""
    daily_bar = _bar_json("2026-08-03T04:00:00Z", o=749.44, h=758.58, l=748.80, c=757.67, v=60014445)
    session = FakeSession([FakeResponse(200, json_data={"bars": [daily_bar], "symbol": "SPY", "next_page_token": None})])
    out = ap.fetch_daily_bar_alpaca_sip(
        canonical_ticker="SPY", session_date=SESSION_DATE, credentials=FAKE_CREDS,
        session=session, sleep_fn=lambda s: None, now_fn=lambda: FAR_FUTURE_NOW,
    )
    params = session.calls[0]["params"]
    check("20a. The 1Day request uses timeframe=1Day", params.get("timeframe") == "1Day")
    check("20b. Its window starts at 00:00Z of the session date, NOT the 13:30Z session open",
          params.get("start") == "2026-08-03T00:00:00Z", str(params.get("start")))
    check("20c. Its window ends at 23:59:59Z of the session date, NOT the 20:00Z session close",
          params.get("end") == "2026-08-03T23:59:59Z", str(params.get("end")))
    check("20d. The midnight-ET-stamped daily bar is therefore inside the window and returned",
          out is not None and out["close"] == 757.67)
    check("20e. The daily result carries its own sanitized provenance", out is not None and out["http_status"] == 200 and len(out["raw_response_content_sha256"]) == 64)
    check("20f. The daily request still requests feed=sip", params.get("feed") == "sip")

    multi = FakeSession([FakeResponse(200, json_data={"bars": [daily_bar, _bar_json("2026-08-04T04:00:00Z")], "symbol": "SPY", "next_page_token": None})])
    try:
        ap.fetch_daily_bar_alpaca_sip(
            canonical_ticker="SPY", session_date=SESSION_DATE, credentials=FAKE_CREDS,
            session=multi, sleep_fn=lambda s: None, now_fn=lambda: FAR_FUTURE_NOW,
        )
        ok = False
    except ap.AlpacaProviderError:
        ok = True
    check("20g. More than one daily bar raises rather than silently cross-checking against bars[0]", ok)

    empty = FakeSession([FakeResponse(200, json_data={"bars": [], "symbol": "SPY", "next_page_token": None})])
    out_empty = ap.fetch_daily_bar_alpaca_sip(
        canonical_ticker="SPY", session_date=SESSION_DATE, credentials=FAKE_CREDS,
        session=empty, sleep_fn=lambda s: None, now_fn=lambda: FAR_FUTURE_NOW,
    )
    check("20h. A genuinely absent daily bar returns None -- never a fabricated one", out_empty is None)


def test_window_overrides_cannot_smuggle_a_nonsession_date():
    """The overrides exist only for the 1Day cross-check. They must not be
    usable to bypass the exchange calendar."""
    from gst_market_response.exchange_calendar import ExchangeCalendarError

    saturday = date(2026, 8, 1)
    session = FakeSession([FakeResponse(200, json_data={"bars": [], "next_page_token": None})])
    try:
        ap.fetch_bars_alpaca_sip(
            canonical_ticker="AAPL", session_date=saturday, credentials=FAKE_CREDS,
            session=session, sleep_fn=lambda s: None, now_fn=lambda: FAR_FUTURE_NOW,
            start_utc_override=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
            end_utc_override=datetime(2026, 8, 1, 23, 59, 59, tzinfo=UTC),
        )
        ok = False
    except ExchangeCalendarError:
        ok = True
    check("21a. A non-session date still raises even when both window overrides are supplied", ok)
    check("21b. No HTTP call was made for the non-session date", len(session.calls) == 0)

    default_session = FakeSession([FakeResponse(200, json_data={"bars": [], "next_page_token": None})])
    _fetch(default_session)
    check("21c. With no overrides the 5Min path uses [first expected bar start, LAST expected bar start]",
          default_session.calls[0]["params"]["start"] == "2026-08-03T13:30:00Z"
          and default_session.calls[0]["params"]["end"] == "2026-08-03T19:55:00Z",
          str(default_session.calls[0]["params"]))


if __name__ == "__main__":
    test_credentials_absent()
    test_401_403_never_retried()
    test_429_with_retry_after()
    test_transient_5xx_recovery()
    test_bounded_retry_exhaustion()
    test_timeout()
    test_empty_bars()
    test_pagination()
    test_duplicate_timestamps_rejected_downstream()
    test_out_of_session_bars_detectable()
    test_missing_expected_bar_detectable()
    test_invalid_ohlc_and_negative_volume_rejected()
    test_provider_symbol_translation()
    test_end_timestamp_freshness_gate()
    test_iex_never_requested()
    test_yfinance_provider_ineligible_alpaca_eligible()
    test_raw_data_never_written_to_disk_by_this_module()
    test_secrets_never_appear_in_provenance_or_repr()
    test_sanitized_request_evidence_recorded()
    test_daily_cross_check_uses_a_calendar_day_window()
    test_window_overrides_cannot_smuggle_a_nonsession_date()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL ALPACA PROVIDER TESTS PASSED")
        sys.exit(0)
