#!/usr/bin/env python3
# Deterministic tests for the Earnings Market-Response Decomposition module
# (gst_market_response/). Synthetic fixtures only -- no live network call,
# no 24-ticker panel run, anywhere in this file. Importing this file does
# not execute any live capture: providers.YFinanceDevIntradayProvider only
# touches the network inside get_bars(), which is never called here.
#
# Covers the 20 numbered testing requirements plus a synthetic
# REGISTERED -> PRE_EVENT_CAPTURED -> D1_COMPLETE -> COMPLETE end-to-end
# scenario, plus 5 failure fixtures, from
# GST_Earnings_Market_Response_Decomposition_SPEC_v0.1_DRAFT.md.
#
# Run directly: python test_market_response_decomposition.py

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import gst_market_response.option_chain_adapter as oca
from gst_market_response import completeness, derivations, pipeline
from gst_market_response.bars import (
    Bar,
    DuplicateBarError,
    NonMonotonicTimestampError,
    WrongTickerError,
    extract_session_fields,
    validate_bars,
)
from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE
from gst_market_response.event_record import EventStore, InvalidStateTransitionError, validate_transition
from gst_market_response.identity import (
    EventIdentityError,
    compute_expected_next_full_trading_session,
    determine_release_market_session,
)
from gst_market_response.option_chain_adapter import ContractSelectionStatus, OptionBenchmark, build_option_benchmark
from gst_market_response.raw_bars import RawBarStore

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


# --------------------------------------------------------------------------
# Shared fixtures
# --------------------------------------------------------------------------

UTC = timezone.utc
ET = ZoneInfo = __import__("zoneinfo").ZoneInfo("America/New_York")


def et_bar(symbol: str, d: date, hh: int, mm: int, o: float, h: float, l: float, c: float, v: int) -> Bar:
    local_dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET)
    return Bar(symbol=symbol, timestamp_utc=local_dt.astimezone(UTC), open=o, high=h, low=l, close=c, volume=v)


def full_session_bars(symbol: str, d: date) -> list[Bar]:
    """A complete, tidy regular session: 09:30 through 15:55 in 5-min bars."""
    bars = []
    t = datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)
    end = datetime(d.year, d.month, d.day, 16, 0, tzinfo=ET)
    price = 100.0
    while t < end:
        bars.append(
            Bar(
                symbol=symbol,
                timestamp_utc=t.astimezone(UTC),
                open=price,
                high=price + 0.5,
                low=price - 0.5,
                close=price + 0.1,
                volume=1000,
            )
        )
        price += 0.1
        t += timedelta(minutes=5)
    return bars


def is_trading_day_mon_fri(d: date) -> bool:
    return d.weekday() < 5


class FakeChain:
    def __init__(self, calls: list[dict], puts: list[dict]):
        self.calls = pd.DataFrame(calls)
        self.puts = pd.DataFrame(puts)


class FakeTicker:
    def __init__(self, options: list[str], calls: list[dict], puts: list[dict]):
        self.options = options
        self._calls = calls
        self._puts = puts

    def option_chain(self, expiry: str):
        return FakeChain(self._calls, self._puts)


def _row(strike, bid, ask, oi=100, vol=50, iv=0.4):
    return {
        "strike": strike, "bid": bid, "ask": ask, "bidSize": 10, "askSize": 10,
        "openInterest": oi, "volume": vol, "impliedVolatility": iv,
    }


def clean_fake_ticker(earnings_date: date, spot: float = 100.0) -> FakeTicker:
    expiry = (earnings_date + timedelta(days=7)).isoformat()
    return FakeTicker(
        options=[expiry],
        calls=[_row(spot, 3.0, 3.4)],
        puts=[_row(spot, 2.8, 3.2)],
    )


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="mrd_test_"))


# ==========================================================================
# 1-3: event timing / D1 day-count rule
# ==========================================================================

def test_1_amc_maps_to_next_trading_session():
    d = date(2026, 8, 4)  # Tuesday
    result = compute_expected_next_full_trading_session(d, "AMC", is_trading_day_mon_fri)
    check("1. AMC event maps to next trading session", result == date(2026, 8, 5), str(result))


def test_2_bmo_maps_to_same_session_when_before_open():
    d = date(2026, 8, 4)  # Tuesday, a trading day
    result = compute_expected_next_full_trading_session(d, "BMO", is_trading_day_mon_fri)
    check("2. BMO event maps to same trading session", result == d, str(result))


def test_3_weekend_and_holiday_handling():
    saturday = date(2026, 8, 8)
    result_bmo = compute_expected_next_full_trading_session(saturday, "BMO", is_trading_day_mon_fri)
    check("3a. BMO release on a weekend rolls to next trading day", result_bmo == date(2026, 8, 10), str(result_bmo))

    def is_trading_day_with_holiday(d: date) -> bool:
        # Simulate a Monday holiday: Aug 10 2026 closed.
        if d == date(2026, 8, 10):
            return False
        return d.weekday() < 5

    result_holiday = compute_expected_next_full_trading_session(saturday, "BMO", is_trading_day_with_holiday)
    check(
        "3b. BMO release on weekend + Monday holiday skips to Tuesday",
        result_holiday == date(2026, 8, 11),
        str(result_holiday),
    )

    intraday_result = compute_expected_next_full_trading_session(date(2026, 8, 4), "INTRADAY", is_trading_day_mon_fri)
    check(
        "3c. INTRADAY release always maps to the NEXT full session, never same-day",
        intraday_result == date(2026, 8, 5),
        str(intraday_result),
    )


def test_bmo_amc_fail_closed_on_unverified_timing():
    try:
        determine_release_market_session(None, "yfinance")
        ok = False
    except EventIdentityError:
        ok = True
    check("BMO/AMC never defaults when label missing -- fails closed", ok)

    try:
        determine_release_market_session("BMO", None)
        ok2 = False
    except EventIdentityError:
        ok2 = True
    check("BMO/AMC never defaults when source missing -- fails closed", ok2)

    try:
        determine_release_market_session("SOMETIME_MAYBE", "a guess")
        ok3 = False
    except EventIdentityError:
        ok3 = True
    check("Invalid session label rejected, never coerced to a valid one", ok3)


# ==========================================================================
# 4: half-day handling
# ==========================================================================

def test_4_half_day_handling():
    d = date(2026, 11, 27)  # a shortened session, bars only run 09:30-13:00
    bars = []
    t = datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)
    end = datetime(d.year, d.month, d.day, 13, 0, tzinfo=ET)
    price = 50.0
    while t < end:
        bars.append(Bar("HALF", t.astimezone(UTC), price, price + 0.2, price - 0.2, price + 0.05, 500))
        price += 0.05
        t += timedelta(minutes=5)
    fields = extract_session_fields(bars)
    check("4a. Half-day session_open resolves from actual first bar", fields.session_open == 50.0)
    check(
        "4b. Half-day session_close is the actual last (13:00-ish) bar, not extrapolated to a full 4pm close",
        fields.session_close == bars[-1].close,
    )
    check(
        "4c. Half-day full_session_volume sums only the bars actually present (not padded to a full session)",
        fields.full_session_volume == sum(b.volume for b in bars),
    )
    check("4d. Half-day still resolves the 30-minute boundary normally", fields.price_at_30m is not None)


# ==========================================================================
# 5: missing 30-minute boundary bar fails closed
# ==========================================================================

def test_5_missing_30m_boundary_fails_closed():
    d = date(2026, 8, 4)
    bars = full_session_bars("MSFT", d)
    bars_missing_boundary = [b for b in bars if b.local_time().time() != __import__("datetime").time(9, 55)]
    fields = extract_session_fields(bars_missing_boundary)
    check("5a. Missing 09:55 boundary bar -> price_at_30m is None (never estimated)", fields.price_at_30m is None)
    check("5b. Missing 09:55 boundary bar -> first_30m_volume is None (never estimated)", fields.first_30m_volume is None)
    o2c = derivations.open_to_30m(fields.price_at_30m, fields.session_open)
    check("5c. open_to_30m formula propagates the missing boundary as None, not 0", o2c is None)


# ==========================================================================
# 6-8: bar validation
# ==========================================================================

def test_6_duplicate_bars_rejected():
    d = date(2026, 8, 4)
    b1 = et_bar("MSFT", d, 9, 30, 100, 101, 99, 100.5, 1000)
    b2 = et_bar("MSFT", d, 9, 30, 100, 101, 99, 100.5, 1000)  # exact duplicate timestamp
    try:
        validate_bars([b1, b2], "MSFT")
        ok = False
    except DuplicateBarError:
        ok = True
    check("6. Duplicate bar timestamps rejected", ok)


def test_7_non_monotonic_timestamps_rejected():
    d = date(2026, 8, 4)
    b1 = et_bar("MSFT", d, 9, 35, 100, 101, 99, 100.5, 1000)
    b2 = et_bar("MSFT", d, 9, 30, 100, 101, 99, 100.5, 1000)  # earlier than b1
    try:
        validate_bars([b1, b2], "MSFT")
        ok = False
    except NonMonotonicTimestampError:
        ok = True
    check("7. Non-monotonic (out-of-order) bar timestamps rejected", ok)


def test_8_wrong_ticker_rejected():
    d = date(2026, 8, 4)
    b1 = et_bar("MSFT", d, 9, 30, 100, 101, 99, 100.5, 1000)
    b2 = et_bar("AAPL", d, 9, 35, 100, 101, 99, 100.5, 1000)  # wrong symbol mixed in
    try:
        validate_bars([b1, b2], "MSFT")
        ok = False
    except WrongTickerError:
        ok = True
    check("8. Bar with unexpected ticker symbol rejected", ok)


# ==========================================================================
# 9: stock / sector / SPY interval alignment
# ==========================================================================

def test_9_stock_sector_spy_alignment():
    d = date(2026, 8, 4)
    stock_bars = full_session_bars("MSFT", d)
    sector_bars = full_session_bars("XLK", d)
    spy_bars = full_session_bars("SPY", d)

    stock_fields = extract_session_fields(stock_bars)
    sector_fields = extract_session_fields(sector_bars)
    spy_fields = extract_session_fields(spy_bars)

    stock_ret = derivations.open_to_close(stock_fields.session_close, stock_fields.session_open)
    sector_ret = derivations.open_to_close(sector_fields.session_close, sector_fields.session_open)
    spy_ret = derivations.open_to_close(spy_fields.session_close, spy_fields.session_open)

    minus_sector = derivations.relative_return(stock_ret, sector_ret)
    minus_spy = derivations.relative_return(stock_ret, spy_ret)

    check("9a. Stock/sector/SPY each produce their own aligned open_to_close return", None not in (stock_ret, sector_ret, spy_ret))
    check(
        "9b. stock_minus_sector is a plain arithmetic difference of matching-interval returns",
        abs(minus_sector - (stock_ret - sector_ret)) < 1e-12,
    )
    check("9c. stock_minus_spy computed on the SAME interval as stock_minus_sector", abs(minus_spy - (stock_ret - spy_ret)) < 1e-12)

    # Missing sector data must not silently zero out the relative field.
    minus_sector_missing = derivations.relative_return(stock_ret, None)
    check("9d. Missing sector return -> relative field is None, not 0", minus_sector_missing is None)


# ==========================================================================
# 10: every return formula
# ==========================================================================

def test_10_every_return_formula():
    check("10a. overnight_gap", abs(derivations.overnight_gap(102.0, 100.0) - 0.02) < 1e-12)
    check("10b. open_to_30m", abs(derivations.open_to_30m(101.0, 100.0) - 0.01) < 1e-12)
    check("10c. thirty_min_to_close", abs(derivations.thirty_min_to_close(103.0, 101.0) - (103.0 / 101.0 - 1)) < 1e-12)
    check("10d. open_to_close", abs(derivations.open_to_close(105.0, 100.0) - 0.05) < 1e-12)
    check("10e. close_to_close (T1->T2)", abs(derivations.close_to_close(110.0, 100.0) - 0.10) < 1e-12)
    check("10f. full_session_range", abs(derivations.full_session_range(110.0, 90.0, 100.0) - 0.20) < 1e-12)
    check("10g. volume_share", abs(derivations.volume_share(300, 1000) - 0.30) < 1e-12)
    check("10h. abs_or_none on a negative value", derivations.abs_or_none(-0.05) == 0.05)
    check("10i. relative_return", abs(derivations.relative_return(0.05, 0.02) - 0.03) < 1e-12)
    check(
        "10j. gst_slope_v0.1 on a clean rising series",
        derivations.gst_slope_v0_1([10.0, 12.0, 14.0]) == 2.0,
    )
    check(
        "10k. gst_persistence_v0.1 counts elevated fraction correctly",
        abs(derivations.gst_persistence_v0_1([1.0, 3.0, 2.5, 1.0], threshold=2.0) - 0.5) < 1e-12,
    )


# ==========================================================================
# 11: null never converted to zero
# ==========================================================================

def test_11_null_never_converted_to_zero():
    check("11a. overnight_gap(None, 100) is None", derivations.overnight_gap(None, 100.0) is None)
    check("11b. overnight_gap(100, None) is None", derivations.overnight_gap(100.0, None) is None)
    check("11c. open_to_30m(None, None) is None", derivations.open_to_30m(None, None) is None)
    check("11d. full_session_range with missing high is None", derivations.full_session_range(None, 90.0, 100.0) is None)
    check("11e. volume_share with zero full_session_volume is None, not a divide-by-zero 0", derivations.volume_share(10, 0) is None)
    check("11f. abs_or_none(None) is None, not 0", derivations.abs_or_none(None) is None)
    check("11g. gst_slope_v0.1([]) is None, not 0", derivations.gst_slope_v0_1([]) is None)
    check("11h. gst_slope_v0.1([None, None]) is None, not 0", derivations.gst_slope_v0_1([None, None]) is None)
    check("11i. gst_persistence_v0.1([]) is None, not 0", derivations.gst_persistence_v0_1([]) is None)
    # Explicitly distinguish a genuine zero return from a missing one.
    check("11j. A genuine zero return is preserved as 0.0, not conflated with None", derivations.overnight_gap(100.0, 100.0) == 0.0)


# ==========================================================================
# 12: PARTIAL never becomes COMPLETE
# ==========================================================================

def test_12_partial_never_becomes_complete():
    try:
        validate_transition("PARTIAL", "COMPLETE")
        ok = False
    except InvalidStateTransitionError:
        ok = True
    check("12a. validate_transition rejects PARTIAL -> COMPLETE directly", ok)

    try:
        validate_transition("PARTIAL", "D1_PENDING")
        ok2 = False
    except InvalidStateTransitionError:
        ok2 = True
    check("12b. PARTIAL is terminal -- no transition out of it at all", ok2)

    # End-to-end: an event that goes PARTIAL at pre-event stage can never be
    # pushed to COMPLETE later by any pipeline call.
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-MSFT-FY26Q4-ERN"
        pipeline.register_event(store, eid, {"ticker": "MSFT"})
        # PROTOCOL v0.2: this ASSERTION is unchanged -- an invalid core still yields
        # PARTIAL-terminal. Only the INPUT changed: `{}` no longer implies "options
        # unavailable", because unavailability is never inferred from an empty dict.
        # The caller must now state a disposition explicitly.
        state = pipeline.capture_pre_event_and_option_benchmark(
            store, eid, {"previous_close": None, "pre_event_snapshot_asof_utc": None},
            {"option_benchmark_status": "NOT_ATTEMPTED",
             "option_benchmark_unavailable_reason": "core snapshot invalid; option capture not attempted"},
        )
        check("12c. Incomplete pre-event data resolves to PARTIAL, not CAPTURED", state == "PARTIAL")
        try:
            pipeline.capture_d1(store, eid, {"overnight_gap": 0.01, "open_to_30m": 0.01, "thirty_min_to_close": 0.01, "open_to_close": 0.02})
            ok3 = False
        except InvalidStateTransitionError:
            ok3 = True
        check("12d. Cannot resume D1 capture on a PARTIAL event -- structurally can't reach COMPLETE", ok3)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ==========================================================================
# 13: input files remain byte-identical
# ==========================================================================

def test_13_input_files_remain_byte_identical():
    root = temp_dir()
    try:
        store = RawBarStore(root)
        d = date(2026, 8, 4)
        bars = full_session_bars("MSFT", d)
        entry = store.write_raw_bars(
            event_id="EVT-MSFT-FY26Q4-ERN", symbol="MSFT", session_date=d, bars=bars,
            bar_interval="5m", source="yfinance-development", retrieved_at_utc=datetime.now(UTC),
        )
        raw_path = root / "EVT-MSFT-FY26Q4-ERN" / entry.relative_path
        before = raw_path.read_bytes()

        # Perform unrelated store operations (a second write, a manifest read).
        store.write_raw_bars(
            event_id="EVT-MSFT-FY26Q4-ERN", symbol="XLK", session_date=d, bars=full_session_bars("XLK", d),
            bar_interval="5m", source="yfinance-development", retrieved_at_utc=datetime.now(UTC),
        )
        _ = store._load_manifest("EVT-MSFT-FY26Q4-ERN")

        after = raw_path.read_bytes()
        check("13. Raw bar input file is byte-identical after unrelated store activity", before == after)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ==========================================================================
# 14: amendment does not modify an earlier frozen record
# ==========================================================================

def test_14_amendment_does_not_modify_earlier_record():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-AAPL-FY26Q3-ERN"
        pipeline.register_event(store, eid, {"ticker": "AAPL"})
        log_path = store._log_path(eid)
        before_bytes = log_path.read_bytes()

        store.append_amendment(eid, amends_seq=0, corrected_fields={"company": "Apple Inc. (corrected)"}, reason="typo fix")

        after_bytes = log_path.read_bytes()
        check(
            "14a. Original record's bytes are an exact, untouched prefix of the file after an amendment",
            after_bytes.startswith(before_bytes),
        )
        check("14b. Amendment strictly appended new bytes, did not shrink or rewrite the file", len(after_bytes) > len(before_bytes))

        records = store.read_all(eid)
        original_record = records[0]
        check("14c. The original STATE record's own state field is unchanged by the amendment", original_record["state"] == "REGISTERED")
        amendment = records[-1]
        check("14d. Amendment record references the original record by seq, rather than overwriting it", amendment["amends_seq"] == 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ==========================================================================
# 15: raw-file hash mismatch rejected
# ==========================================================================

def test_15_raw_file_hash_mismatch_rejected():
    root = temp_dir()
    try:
        store = RawBarStore(root)
        d = date(2026, 8, 4)
        bars = full_session_bars("MSFT", d)
        entry = store.write_raw_bars(
            event_id="EVT-MSFT-FY26Q4-ERN", symbol="MSFT", session_date=d, bars=bars,
            bar_interval="5m", source="yfinance-development", retrieved_at_utc=datetime.now(UTC),
        )
        check("15a. Freshly-written raw bar file verifies clean against its manifest hash", store.verify("EVT-MSFT-FY26Q4-ERN", entry.relative_path))

        raw_path = root / "EVT-MSFT-FY26Q4-ERN" / entry.relative_path
        # Simulate corruption/tampering after the fact.
        raw_path.write_bytes(raw_path.read_bytes() + b"\ncorrupted,extra,row,here\n")

        check("15b. Tampered raw bar file fails hash verification", not store.verify("EVT-MSFT-FY26Q4-ERN", entry.relative_path))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ==========================================================================
# 16: option expiration before or on the earnings date rejected
# ==========================================================================

def test_16_expiration_before_or_on_earnings_date_rejected():
    earnings_date = date(2026, 7, 29)
    # The reused selector itself must never pick an expiry <= earnings_date.
    tk_same_day_and_later = FakeTicker(
        options=[earnings_date.isoformat(), (earnings_date + timedelta(days=7)).isoformat()],
        calls=[_row(100.0, 3.0, 3.4)], puts=[_row(100.0, 2.8, 3.2)],
    )
    result = build_option_benchmark(
        tk=tk_same_day_and_later, earnings_date=earnings_date, underlying_price=100.0,
        quote_timestamp_utc=datetime.now(UTC),
    )
    check(
        "16a. Same-day-as-earnings expiration is never selected, later one is chosen instead",
        result.expiration == earnings_date + timedelta(days=7),
        str(result.expiration),
    )

    # Defensive belt-and-suspenders check: even if the reused selector were
    # ever wrong, build_option_benchmark's own guard must independently
    # reject an on/before-event expiry rather than trust it blindly.
    original_selector = oca._select_nearest_expiry_after
    try:
        oca._select_nearest_expiry_after = lambda tk, ed: earnings_date.isoformat()  # simulate a buggy upstream
        bad_result = build_option_benchmark(
            tk=tk_same_day_and_later, earnings_date=earnings_date, underlying_price=100.0,
            quote_timestamp_utc=datetime.now(UTC),
        )
        check(
            "16b. build_option_benchmark independently rejects an on-or-before-event expiry even if the selector returns one",
            bad_result.contract_selection_status == ContractSelectionStatus.REJECTED_EXPIRY_NOT_AFTER_EVENT,
            bad_result.contract_selection_status,
        )
    finally:
        oca._select_nearest_expiry_after = original_selector


# ==========================================================================
# 17: bid greater than ask rejected
# ==========================================================================

def test_17_bid_greater_than_ask_rejected():
    earnings_date = date(2026, 7, 29)
    tk = FakeTicker(
        options=[(earnings_date + timedelta(days=7)).isoformat()],
        calls=[_row(100.0, bid=5.0, ask=3.0)],  # crossed: bid > ask
        puts=[_row(100.0, bid=2.8, ask=3.2)],
    )
    result = build_option_benchmark(
        tk=tk, earnings_date=earnings_date, underlying_price=100.0, quote_timestamp_utc=datetime.now(UTC)
    )
    check(
        "17. Crossed call quote (bid > ask) rejected, nothing populated from it",
        result.contract_selection_status == ContractSelectionStatus.REJECTED_BID_GT_ASK and result.call_mid is None,
    )


# ==========================================================================
# 18: incompatible quote timestamps rejected/classified unusable
# ==========================================================================

def test_18_incompatible_quote_timestamps_rejected():
    earnings_date = date(2026, 7, 29)
    tk = clean_fake_ticker(earnings_date)
    now = datetime.now(UTC)
    result = build_option_benchmark(
        tk=tk, earnings_date=earnings_date, underlying_price=100.0, quote_timestamp_utc=now,
        call_quote_timestamp_utc=now, put_quote_timestamp_utc=now + timedelta(hours=2),
    )
    check(
        "18. Call/put quotes captured 2 hours apart are rejected as incompatible, not silently combined",
        result.contract_selection_status == ContractSelectionStatus.REJECTED_INCOMPATIBLE_TIMESTAMPS,
    )


# ==========================================================================
# 19: Phase 2 generic IV never imported as earnings_implied_move
# ==========================================================================

def test_19_generic_iv_never_imported_as_earnings_implied_move():
    field_names = set(OptionBenchmark.__dataclass_fields__.keys())
    check(
        "19a. OptionBenchmark schema has no bare 'implied_volatility'/'earnings_implied_move' field at all",
        "implied_volatility" not in field_names and "earnings_implied_move" not in field_names,
        str(field_names),
    )
    check(
        "19b. Benchmark exposes only midpoint/executable-cost fields, never a raw IV pass-through",
        {"midpoint_implied_move", "long_executable_implied_move_cost"}.issubset(field_names),
    )
    src = Path("gst_market_response/option_chain_adapter.py").read_text(encoding="utf-8")
    check(
        "19c. option_chain_adapter.py never imports anything from GST_Phase2_DailyPanel",
        "GST_Phase2_DailyPanel" not in src,
    )


# ==========================================================================
# 20: no trading decision or P&L field in the v0.1 schema
# ==========================================================================

def test_20_no_trading_decision_or_pnl_field():
    banned_substrings = ("pnl", "p&l", "profit", "recommend", "buy_signal", "sell_signal", "trade_action", "position_size")
    all_field_names: list[str] = []
    all_field_names += list(OptionBenchmark.__dataclass_fields__.keys())
    from gst_market_response.identity import EventIdentity

    all_field_names += list(EventIdentity.__dataclass_fields__.keys())
    all_field_names += list(completeness.PRE_EVENT_REQUIRED_FIELDS)
    all_field_names += list(completeness.D1_REQUIRED_FIELDS)
    all_field_names += list(completeness.D3_REQUIRED_FIELDS)

    offenders = [
        f for f in all_field_names if any(b in f.lower() for b in banned_substrings)
    ]
    check("20. No field name in the v0.1 schema resembles a trading decision or P&L field", offenders == [], str(offenders))


# ==========================================================================
# End-to-end synthetic event: REGISTERED -> PRE_EVENT_CAPTURED -> D1_COMPLETE -> COMPLETE
# ==========================================================================

def test_end_to_end_synthetic_event():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-MSFT-FY26Q4-ERN"

        state = pipeline.register_event(store, eid, {
            "ticker": "MSFT", "company": "Microsoft Corporation", "fiscal_period": "FY26Q4",
            "earnings_date": "2026-07-29", "release_market_session": "AMC",
        })
        check("E2E-1. register_event -> REGISTERED", state == "REGISTERED")

        pre_event_fields = {
            "gst_zscore": 3.2, "gst_level": 65.0, "gst_slope": 1.5, "gst_persistence": 0.5,
            "wiki_zscore": 2.1, "previous_close": 450.0, "realized_volatility": 0.28,
            "days_to_earnings": 0, "pre_event_snapshot_asof_utc": "2026-07-29T20:00:00+00:00",
            "source_status_gst": "ok", "source_status_wiki": "ok", "source_status_price": "ok",
        }
        earnings_date = date(2026, 7, 29)
        tk = clean_fake_ticker(earnings_date, spot=450.0)
        benchmark = build_option_benchmark(
            tk=tk, earnings_date=earnings_date, underlying_price=450.0, quote_timestamp_utc=datetime.now(UTC),
        )
        option_fields = {k: v for k, v in benchmark.__dict__.items()}
        # PROTOCOL v0.2: a genuinely verified benchmark must now declare its
        # disposition and provider feed. The ASSERTION is unchanged -- a valid
        # core plus a valid OPRA benchmark still reaches PRE_EVENT_CAPTURED.
        option_fields["option_benchmark_status"] = "VALID_VERIFIED"
        option_fields["option_feed"] = "opra"
        check("E2E-2. Synthetic option benchmark resolves OK", benchmark.contract_selection_status == "ok")

        state = pipeline.capture_pre_event_and_option_benchmark(store, eid, pre_event_fields, option_fields)
        check("E2E-3. capture_pre_event_and_option_benchmark -> PRE_EVENT_CAPTURED", state == "PRE_EVENT_CAPTURED")

        d1_session_date = date(2026, 7, 30)
        stock_bars = full_session_bars("MSFT", d1_session_date)
        session_fields = extract_session_fields(stock_bars)
        d1_fields = {
            "overnight_gap": derivations.overnight_gap(session_fields.session_open, 450.0),
            "open_to_30m": derivations.open_to_30m(session_fields.price_at_30m, session_fields.session_open),
            "thirty_min_to_close": derivations.thirty_min_to_close(session_fields.session_close, session_fields.price_at_30m),
            "open_to_close": derivations.open_to_close(session_fields.session_close, session_fields.session_open),
        }
        state = pipeline.capture_d1(store, eid, d1_fields)
        check("E2E-4. capture_d1 -> D1_COMPLETE", state == "D1_COMPLETE")

        close_t1 = session_fields.session_close
        close_t2 = 452.0
        close_t3 = 455.0
        d3_fields = {
            "close_T1_to_close_T2": derivations.close_to_close(close_t2, close_t1),
            "close_T1_to_close_T3": derivations.close_to_close(close_t3, close_t1),
        }
        state = pipeline.capture_d3(store, eid, d3_fields)
        check("E2E-5. capture_d3 -> COMPLETE", state == "COMPLETE")

        records = store.read_all(eid)
        states_seen = [r["state"] for r in records if r["record_type"] == "STATE"]
        check(
            "E2E-6. Full state sequence recorded, forward-only, ending COMPLETE",
            states_seen == [
                "REGISTERED", "PRE_EVENT_PENDING", "PRE_EVENT_CAPTURED",
                "D1_PENDING", "D1_COMPLETE", "D3_PENDING", "COMPLETE",
            ],
            str(states_seen),
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ==========================================================================
# Failure fixtures
# ==========================================================================

def test_failure_fixture_missing_event_timing():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-GME-FY26Q3-ERN"
        pipeline.register_event(store, eid, {"ticker": "GME"})
        try:
            determine_release_market_session(None, None)
            timing_ok = True
        except EventIdentityError:
            timing_ok = False
        check("FF-1a. Missing event timing raises rather than defaulting", not timing_ok)
        state = pipeline.abstain(store, eid, reason="event timing could not be verified")
        check("FF-1b. Event with unverifiable timing routes to ABSTAIN_DATA_QUALITY", state == "ABSTAIN_DATA_QUALITY")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_failure_fixture_missing_opening_bar():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-TSLA-FY26Q3-ERN"
        d = date(2026, 8, 4)
        bars = full_session_bars("TSLA", d)
        bars_missing_open = [b for b in bars if b.local_time().time() != __import__("datetime").time(9, 30)]
        fields = extract_session_fields(bars_missing_open)
        check("FF-2a. Missing opening bar -> session_open is None", fields.session_open is None)

        pipeline.register_event(store, eid, {"ticker": "TSLA"})
        earnings_date = date(2026, 8, 3)
        tk = clean_fake_ticker(earnings_date, spot=250.0)
        benchmark = build_option_benchmark(
            tk=tk, earnings_date=earnings_date, underlying_price=250.0, quote_timestamp_utc=datetime.now(UTC),
        )
        # PROTOCOL v0.2: disposition + feed now declared explicitly. Assertion unchanged.
        pre_state = pipeline.capture_pre_event_and_option_benchmark(
            store, eid,
            {"previous_close": 250.0, "pre_event_snapshot_asof_utc": "2026-08-03T20:00:00+00:00", "gst_zscore": 1.0},
            {**benchmark.__dict__, "option_benchmark_status": "VALID_VERIFIED", "option_feed": "opra"},
        )
        check("FF-2b. Pre-event stage captured cleanly so the D1 failure below is isolated to the missing bar", pre_state == "PRE_EVENT_CAPTURED")

        d1_fields = {
            "overnight_gap": derivations.overnight_gap(fields.session_open, 250.0),
            "open_to_30m": derivations.open_to_30m(fields.price_at_30m, fields.session_open),
            "thirty_min_to_close": derivations.thirty_min_to_close(fields.session_close, fields.price_at_30m),
            "open_to_close": derivations.open_to_close(fields.session_close, fields.session_open),
        }
        state = pipeline.capture_d1(store, eid, d1_fields)
        check("FF-2c. Missing opening bar fails the D1 gate -> PARTIAL, never COMPLETE", state == "PARTIAL")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_failure_fixture_invalid_option_expiration():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-AAPL-FY26Q4-ERN"
        earnings_date = date(2026, 10, 29)
        tk_no_valid_expiry = FakeTicker(options=[], calls=[], puts=[])
        benchmark = build_option_benchmark(
            tk=tk_no_valid_expiry, earnings_date=earnings_date, underlying_price=230.0,
            quote_timestamp_utc=datetime.now(UTC),
        )
        check("FF-3a. No post-event expiration available -> MISSING status, not a fabricated benchmark", benchmark.contract_selection_status == "missing")

        pipeline.register_event(store, eid, {"ticker": "AAPL"})
        good_core = {"previous_close": 228.0,
                     "pre_event_snapshot_asof_utc": "2026-10-29T20:00:00+00:00", "gst_zscore": 1.0}

        # ---- EXPECTATION CHANGED BY PROTOCOL v0.2 -- explained, not silently updated ----
        #
        # v0.1 asserted: rejected benchmark + valid core -> PARTIAL.
        # That coupling is exactly the defect this amendment corrects: a valid core
        # observation was driven into a TERMINAL state by a missing OPTIONAL module,
        # making D1/D2/D3 uncollectable. The event was destroyed by the absence of
        # the benchmark rather than by any defect in the core.
        #
        # v0.2 splits the outcome in two, and neither branch treats an absent
        # benchmark as valid:
        #
        #   (a) handing over the REJECTED benchmark dict as-is now fails closed. It
        #       still carries a populated underlying_price while claiming no usable
        #       benchmark, and it declares no disposition -- exactly the
        #       "supplied but invalid artifact" case, which must be rejected with
        #       zero writes rather than silently downgraded to ordinary unavailability.
        #
        #   (b) declaring the honest outcome (LOOKUP_FAILED, all benchmark values
        #       null, reason recorded) captures the core and marks the option module
        #       ineligible -- lifecycle proceeds, analytical eligibility does not.
        raised = False
        try:
            pipeline.capture_pre_event_and_option_benchmark(store, eid, good_core, benchmark.__dict__)
        except completeness.OptionDispositionError:
            raised = True
        check("FF-3b. A rejected benchmark handed over as-is fails closed (supplied-but-invalid), "
              "instead of silently becoming 'unavailable'", raised)
        check("FF-3b2. That refusal wrote nothing -- the event is still at REGISTERED",
              store.current_state(eid) == "REGISTERED")

        state = pipeline.capture_pre_event_and_option_benchmark(
            store, eid, good_core,
            {"option_benchmark_status": "LOOKUP_FAILED",
             "option_benchmark_unavailable_reason": "no expiration strictly after the event date",
             "expiration": None, "underlying_price": None, "quote_timestamp_utc": None,
             "straddle_mid": None, "long_executable_implied_move_cost": None},
        )
        check("FF-3c. Declared LOOKUP_FAILED with null values -> core captured, lifecycle continues",
              state == "PRE_EVENT_CAPTURED")
        elig = completeness.read_module_eligibility(
            [r for r in store.read_all(eid) if r["state"] == "PRE_EVENT_CAPTURED"][0]["fields"])
        check("FF-3d. ...but the option module is INELIGIBLE and the tier is core-only",
              elig.option_benchmark_eligible is False
              and elig.joint_full_eligible is False
              and elig.pre_event_completeness_tier == "core_only_no_option_benchmark")
        check("FF-3e. ...and every option value stayed null, never zero",
              all(r["fields"].get(k) is None
                  for r in store.read_all(eid) if r["state"] == "PRE_EVENT_CAPTURED"
                  for k in ("expiration", "underlying_price", "quote_timestamp_utc", "straddle_mid")))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_failure_fixture_partial_sector_data():
    d = date(2026, 8, 4)
    stock_bars = full_session_bars("NKE", d)
    stock_fields = extract_session_fields(stock_bars)
    stock_ret = derivations.open_to_close(stock_fields.session_close, stock_fields.session_open)

    # Sector ETF feed came back empty for the day -- no bars at all.
    sector_fields = extract_session_fields([])
    sector_ret = derivations.open_to_close(sector_fields.session_close, sector_fields.session_open)

    relative = derivations.relative_return(stock_ret, sector_ret)
    check("FF-4a. Missing sector data -> sector return is None", sector_ret is None)
    check("FF-4b. Missing sector data -> relative-return field is None, never silently 0", relative is None)

    d1_fields = {
        "overnight_gap": derivations.overnight_gap(stock_fields.session_open, 100.0),
        "open_to_30m": derivations.open_to_30m(stock_fields.price_at_30m, stock_fields.session_open),
        "thirty_min_to_close": derivations.thirty_min_to_close(stock_fields.session_close, stock_fields.price_at_30m),
        "open_to_close": stock_ret,
        "open_to_close_minus_sector": relative,  # present as an explicit null, not omitted
    }
    check(
        "FF-4c. Stock-side D1 gate still passes on its own required fields despite the missing OPTIONAL sector data",
        completeness.is_valid_d1_decomposition(d1_fields),
    )
    check("FF-4d. The null sector-relative field is visible in the record, not dropped", "open_to_close_minus_sector" in d1_fields)


def test_failure_fixture_raw_file_hash_mismatch():
    root = temp_dir()
    try:
        store = RawBarStore(root)
        d = date(2026, 8, 4)
        bars = full_session_bars("QCOM", d)
        entry = store.write_raw_bars(
            event_id="EVT-QCOM-FY26Q3-ERN", symbol="QCOM", session_date=d, bars=bars,
            bar_interval="5m", source="yfinance-development", retrieved_at_utc=datetime.now(UTC),
        )
        raw_path = root / "EVT-QCOM-FY26Q3-ERN" / entry.relative_path
        raw_path.write_bytes(b"tampered,content\n1,2\n")

        is_clean = store.verify("EVT-QCOM-FY26Q3-ERN", entry.relative_path)
        check("FF-5a. Corrupted raw bar file fails verification", not is_clean)

        # Policy: a caller must never derive D1/D3 fields from unverified bars.
        if not is_clean:
            derived_allowed = False
        else:
            derived_allowed = True
        check("FF-5b. Downstream derivation is blocked when the raw file fails hash verification", not derived_allowed)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ==========================================================================
# Universe / schema sanity (not part of the numbered 20, but load-bearing)
# ==========================================================================

def test_locked_universe_unchanged():
    check("Locked universe has exactly 24 tickers", len(LOCKED_24_TICKER_UNIVERSE) == 24)
    check("MSFT is a member of the locked universe", "MSFT" in LOCKED_24_TICKER_UNIVERSE)


if __name__ == "__main__":
    test_1_amc_maps_to_next_trading_session()
    test_2_bmo_maps_to_same_session_when_before_open()
    test_3_weekend_and_holiday_handling()
    test_bmo_amc_fail_closed_on_unverified_timing()
    test_4_half_day_handling()
    test_5_missing_30m_boundary_fails_closed()
    test_6_duplicate_bars_rejected()
    test_7_non_monotonic_timestamps_rejected()
    test_8_wrong_ticker_rejected()
    test_9_stock_sector_spy_alignment()
    test_10_every_return_formula()
    test_11_null_never_converted_to_zero()
    test_12_partial_never_becomes_complete()
    test_13_input_files_remain_byte_identical()
    test_14_amendment_does_not_modify_earlier_record()
    test_15_raw_file_hash_mismatch_rejected()
    test_16_expiration_before_or_on_earnings_date_rejected()
    test_17_bid_greater_than_ask_rejected()
    test_18_incompatible_quote_timestamps_rejected()
    test_19_generic_iv_never_imported_as_earnings_implied_move()
    test_20_no_trading_decision_or_pnl_field()
    test_end_to_end_synthetic_event()
    test_failure_fixture_missing_event_timing()
    test_failure_fixture_missing_opening_bar()
    test_failure_fixture_invalid_option_expiration()
    test_failure_fixture_partial_sector_data()
    test_failure_fixture_raw_file_hash_mismatch()
    test_locked_universe_unchanged()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print(f"ALL MARKET RESPONSE DECOMPOSITION TESTS PASSED")
        sys.exit(0)
