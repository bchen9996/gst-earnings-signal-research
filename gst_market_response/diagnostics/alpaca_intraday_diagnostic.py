# SECTION F of the second operational-readiness pass, EXECUTED in the third
# (live-validation) pass: the bounded live diagnostic harness for
# AlpacaHistoricalSipIntradayProvider.
#
# This harness is deliberately assertion-heavy and reports every discrepancy
# it finds. It writes NO raw bars into the repository -- the caller passes an
# out_dir that must live outside the repo (the runner in this pass used the
# session scratchpad), and even there the harness writes only the sanitized
# report. Raw bars are the runner's responsibility, not this module's.
#
# Non-research use only: running this against a ticker does NOT register an
# event, and the report is not an event record.
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as _dtime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..alpaca_provider import (
    ADJUSTMENT,
    FEED,
    TIMEFRAME,
    AlpacaCredentials,
    AlpacaProviderError,
    fetch_bars_alpaca_sip,
    fetch_daily_bar_alpaca_sip,
    provider_symbol_for,
)
from ..bars import (
    ET_ZONE,
    DuplicateBarError,
    InvalidOHLCError,
    NegativeVolumeError,
    NonMonotonicTimestampError,
    WrongTickerError,
    extract_session_fields,
    validate_bars,
    validate_ohlc_and_volume,
)
from ..derivations import (
    full_session_range,
    open_to_30m,
    open_to_close,
    thirty_min_to_close,
    volume_share,
)
from ..exchange_calendar import expected_bar_boundaries, session_close_utc, session_open_utc

BAR_INTERVAL_MINUTES = 5
FIRST_30M_BAR_COUNT = 6
REGULAR_OPEN_ET = _dtime(9, 30)
REGULAR_LAST_BAR_START_ET = _dtime(15, 55)
# Independent-recomputation tolerance. The derivations module and the
# recomputation below are both plain float arithmetic on the same inputs, so
# they should agree to within representation error, not merely "closely".
DERIVATION_EXACTNESS_TOLERANCE = 1e-12

# Tolerance for the OHLC sanity comparison between the aggregated 5-minute
# bars and Alpaca's own 1Day SIP bar. Both should describe the same regular
# session, so this is deliberately tight (10 bp); a difference beyond it is a
# real signal, not rounding.
OHLC_CROSS_CHECK_RELATIVE_TOLERANCE = 0.001

# The aggregation semantics of Alpaca's 1Day equity bar relative to its 5Min
# bars are NOT established. An earlier draft of this module's report asserted
# the daily-vs-aggregate volume gap was "most likely" extended-hours volume;
# that was an unsupported guess and has been retracted. Until identical
# semantics are proven, a volume difference is uninterpretable and is recorded
# as informational only -- never as an equality gate. OHLC is different: both
# series should describe the same regular session, so OHLC remains a genuine
# sanity comparison.
VOLUME_COMPARISON_STATUS = "unresolved_provider_aggregation_semantics"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class AlpacaDiagnosticReport:
    ticker: str
    provider_symbol: str
    session_date: str
    reason_for_selection: str
    started_at_utc: str
    finished_at_utc: Optional[str] = None
    http_status: Optional[int] = None
    feed_requested: Optional[str] = None
    timeframe_requested: Optional[str] = None
    adjustment_requested: Optional[str] = None
    request_query_string: Optional[str] = None
    response_symbol_echo: Optional[str] = None
    retry_count: Optional[int] = None
    page_count: Optional[int] = None
    raw_response_sha256: Optional[str] = None
    bar_count: Optional[int] = None
    expected_bar_count: Optional[int] = None
    first_bar_et: Optional[str] = None
    last_bar_et: Optional[str] = None
    daily_bar_comparison: Optional[dict] = None
    checks: list[CheckResult] = field(default_factory=list)
    verdict: str = "PENDING"

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, passed=passed, detail=detail))

    def finalize(self) -> None:
        self.finished_at_utc = datetime.now(timezone.utc).isoformat()
        self.verdict = "PASSED" if all(c.passed for c in self.checks) else "FAILED"

    def to_json_dict(self) -> dict:
        return asdict(self)

    @property
    def failed_checks(self) -> list[str]:
        return [c.name for c in self.checks if not c.passed]


def _expected_grid_utc(session_date: date) -> list[datetime]:
    """The exact 5-minute bar-START grid the calendar says this session must
    have. Derived from the calendar's own open/close, so an early close
    produces a shorter grid rather than a wrong 78."""
    open_utc = session_open_utc(session_date)
    close_utc = session_close_utc(session_date)
    grid: list[datetime] = []
    t = open_utc
    while t < close_utc:
        grid.append(t)
        t = t + timedelta(minutes=BAR_INTERVAL_MINUTES)
    return grid


def run_diagnostic(
    *,
    ticker: str,
    session_date: date,
    reason_for_selection: str,
    credentials: AlpacaCredentials,
    out_dir: Path,
    cross_check_daily: bool = True,
    raw_sink: Optional[Path] = None,
) -> AlpacaDiagnosticReport:
    """Runs the full live check suite exactly once. `out_dir` must be outside
    the repository. `raw_sink`, if given, must ALSO be outside the repository
    (or inside an ignored directory) -- it receives the raw parsed bars for
    the operator's own inspection and is never committed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report = AlpacaDiagnosticReport(
        ticker=ticker,
        provider_symbol=provider_symbol_for(ticker),
        session_date=session_date.isoformat(),
        reason_for_selection=reason_for_selection,
        started_at_utc=datetime.now(timezone.utc).isoformat(),
    )

    try:
        result = fetch_bars_alpaca_sip(canonical_ticker=ticker, session_date=session_date, credentials=credentials)
    except AlpacaProviderError as e:
        report.add("0. Live fetch completed without a provider error", False, f"{type(e).__name__}: {e}")
        report.finalize()
        _write_report(report, out_dir)
        return report

    prov = result.provenance
    bars = result.bars
    report.http_status = prov.http_status
    report.feed_requested = prov.feed
    report.timeframe_requested = prov.timeframe
    report.adjustment_requested = prov.adjustment
    report.request_query_string = prov.request_query_string
    report.response_symbol_echo = prov.response_symbol_echo
    report.retry_count = prov.retry_count
    report.page_count = prov.page_count
    report.raw_response_sha256 = prov.raw_response_content_sha256
    report.bar_count = len(bars)

    if raw_sink is not None:
        raw_sink.parent.mkdir(parents=True, exist_ok=True)
        with open(raw_sink, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "t": b.timestamp_utc.isoformat(),
                        "t_et": b.local_time().isoformat(),
                        "o": b.open, "h": b.high, "l": b.low, "c": b.close, "v": b.volume,
                    }
                    for b in bars
                ],
                f,
                indent=1,
            )

    report.add("0. Live fetch completed without a provider error", True)

    # --- 1. Transport-level evidence -------------------------------------
    report.add("1. HTTP 200", prov.http_status == 200, f"http_status={prov.http_status}")
    report.add(
        "2. feed=sip requested on the wire (Alpaca's single-symbol bars response does not echo feed; the query string is the first-hand evidence)",
        prov.feed == FEED == "sip" and "feed=sip" in (prov.request_query_string or ""),
        f"query={prov.request_query_string}",
    )
    report.add(
        "3. timeframe=5Min requested on the wire",
        prov.timeframe == TIMEFRAME == "5Min" and "timeframe=5Min" in (prov.request_query_string or ""),
        f"timeframe={prov.timeframe}",
    )
    report.add(
        "4. adjustment=raw requested on the wire",
        prov.adjustment == ADJUSTMENT == "raw" and "adjustment=raw" in (prov.request_query_string or ""),
        f"adjustment={prov.adjustment}",
    )
    report.add(
        "5. IEX was never requested -- no feed other than sip appears in the query string",
        "feed=iex" not in (prov.request_query_string or "") and (prov.request_query_string or "").count("feed=") == 1,
    )

    boundaries = expected_bar_boundaries(session_date)
    report.expected_bar_count = boundaries.expected_bar_count

    if not bars:
        report.add("6. Non-empty bar set returned", False, "0 bars -- nothing further can be checked")
        report.finalize()
        _write_report(report, out_dir)
        return report
    report.add("6. Non-empty bar set returned", True, f"{len(bars)} bars")

    first_bar_et = bars[0].local_time()
    last_bar_et = bars[-1].local_time()
    report.first_bar_et = first_bar_et.isoformat()
    report.last_bar_et = last_bar_et.isoformat()

    # --- 2. Session-window evidence --------------------------------------
    # ALP-1: the requested end must be the FINAL EXPECTED BAR START (15:55 ET
    # on an ordinary session), never the 16:00 session close, because Alpaca's
    # `end` is inclusive of a bar starting exactly at `end`.
    grid = _expected_grid_utc(session_date)
    report.add(
        "7. Requested window is exactly [first expected bar start, LAST expected bar start] -- "
        "not the session close, which an inclusive `end` would turn into an after-hours bar",
        prov.requested_start_utc == boundaries.first_bar_start_utc
        and prov.requested_end_utc == boundaries.last_bar_start_utc
        and prov.requested_end_utc != boundaries.close_utc,
        f"requested=[{prov.requested_start_utc}, {prov.requested_end_utc}] "
        f"expected=[{boundaries.first_bar_start_utc}, {boundaries.last_bar_start_utc}] "
        f"session_close={boundaries.close_utc}",
    )

    grid_set = set(grid)
    # The on-grid subset, ordered by timestamp. Everything downstream that
    # asks "what did this session do" works from this, never from raw list
    # position -- see the note above check 21.
    in_grid = sorted((b for b in bars if b.timestamp_utc in grid_set), key=lambda b: b.timestamp_utc)
    returned_set = {b.timestamp_utc for b in bars}
    extra_ts = sorted(returned_set - grid_set)
    missing_ts = sorted(grid_set - returned_set)
    report.add(
        "8. No extended-hours contamination -- every returned bar start lies on the regular-session grid",
        len(extra_ts) == 0,
        f"{len(extra_ts)} off-grid/out-of-session bars: {[t.isoformat() for t in extra_ts[:5]]}",
    )
    report.add(
        "9. No regular-session bar is missing -- returned set exactly equals the calendar grid",
        len(missing_ts) == 0,
        f"{len(missing_ts)} missing: {[t.isoformat() for t in missing_ts[:5]]}",
    )
    report.add(
        f"10. Expected bar count matches the calendar ({boundaries.expected_bar_count})",
        len(bars) == boundaries.expected_bar_count,
        f"actual={len(bars)}",
    )
    report.add(
        "11. First bar starts at 09:30 ET",
        first_bar_et.time() == REGULAR_OPEN_ET,
        f"first_bar_et={first_bar_et.isoformat()}, is_early_close={boundaries.is_early_close}",
    )
    report.add(
        "12. Last bar starts at 15:55 ET (3:55 pm), i.e. the final 5-minute bar of the regular session",
        last_bar_et.time() == REGULAR_LAST_BAR_START_ET
        and bars[-1].timestamp_utc.isoformat() == boundaries.last_bar_start_utc,
        f"last_bar_et={last_bar_et.isoformat()}",
    )

    # --- 3. Structural integrity -----------------------------------------
    try:
        validate_bars(bars, ticker)
        report.add("13. Unique, strictly monotonically increasing timestamps", True)
    except (DuplicateBarError, NonMonotonicTimestampError, WrongTickerError) as e:
        report.add("13. Unique, strictly monotonically increasing timestamps", False, repr(e))

    spacings = {
        int((bars[i + 1].timestamp_utc - bars[i].timestamp_utc).total_seconds() // 60) for i in range(len(bars) - 1)
    }
    report.add(
        "14. Every consecutive gap is exactly 5 minutes -- no silently-collapsed interval",
        spacings == {BAR_INTERVAL_MINUTES},
        f"observed gaps (minutes)={sorted(spacings)}",
    )

    try:
        validate_ohlc_and_volume(bars)
        report.add("15. Valid OHLC relationships (low <= open/close <= high) on every bar", True)
        report.add("16. Nonnegative volume on every bar", True)
    except InvalidOHLCError as e:
        report.add("15. Valid OHLC relationships (low <= open/close <= high) on every bar", False, repr(e))
        report.add("16. Nonnegative volume on every bar", False, "not reached -- OHLC check raised first")
    except NegativeVolumeError as e:
        report.add("15. Valid OHLC relationships (low <= open/close <= high) on every bar", True)
        report.add("16. Nonnegative volume on every bar", False, repr(e))

    # --- 4. Zero-fill / synthesis detection -------------------------------
    # A zero-filled or synthesized bar is the failure mode that would silently
    # corrupt a market-response measurement, so it gets its own explicit scan
    # rather than being inferred from the count matching.
    flat_zero_volume = [
        b for b in bars if b.volume == 0 and b.open == b.high == b.low == b.close
    ]
    report.add(
        "17. No bar carries the zero-fill signature (zero volume AND a flat O=H=L=C)",
        len(flat_zero_volume) == 0,
        f"{len(flat_zero_volume)} suspect bars: {[b.timestamp_utc.isoformat() for b in flat_zero_volume[:5]]}",
    )
    zero_volume = [b for b in bars if b.volume == 0]
    report.add(
        "18. No zero-volume bar at all in this session (recorded separately -- a real quiet interval is legal, a fabricated one is not)",
        len(zero_volume) == 0,
        f"{len(zero_volume)} zero-volume bars",
    )
    report.add(
        "19. Bar count and grid coverage agree -- an incomplete response would surface as a FAILED check above, never as a filled gap",
        (len(bars) == boundaries.expected_bar_count) == (len(missing_ts) == 0),
    )

    # --- 5. Market-response derivations -----------------------------------
    fields = extract_session_fields(bars, session_date)
    o2c = open_to_close(fields.session_close, fields.session_open)
    o230 = open_to_30m(fields.price_at_30m, fields.session_open)
    t2c = thirty_min_to_close(fields.session_close, fields.price_at_30m)
    rng = full_session_range(fields.session_high, fields.session_low, fields.session_open)
    vshare = volume_share(fields.first_30m_volume, fields.full_session_volume)

    first_30m_bars = [
        b for b in in_grid if REGULAR_OPEN_ET <= b.local_time().time() <= _dtime(9, 55)
    ]
    report.add(
        f"20. Exactly {FIRST_30M_BAR_COUNT} bars constitute the first 30 minutes (09:30-09:55 starts)",
        len(first_30m_bars) == FIRST_30M_BAR_COUNT,
        f"actual={len(first_30m_bars)}",
    )

    # Independent recomputation, NOT reusing the derivations module -- so an
    # error inside derivations cannot validate itself.
    #
    # It runs over the ON-GRID bars, selecting the open/close bars by their
    # expected timestamps rather than positionally. Two reasons: (a) it must
    # cover the same domain as extract_session_fields(), or this becomes a
    # duplicate contamination detector instead of an arithmetic cross-check --
    # grid deviations are already reported by checks 8/9/10/12/19; and (b)
    # positional bars[0]/bars[-1] is exactly the pattern defect ALP-1
    # exploited, so it has no place in the code that verifies the fix.
    by_ts = {b.timestamp_utc: b for b in in_grid}
    open_bar = by_ts.get(grid[0])
    close_bar = by_ts.get(grid[-1])
    if open_bar is None or close_bar is None:
        report.add(
            "21. Market-response derivations match an independent recomputation off the raw bars",
            False,
            f"expected open bar {grid[0].isoformat()} present={open_bar is not None}, "
            f"expected close bar {grid[-1].isoformat()} present={close_bar is not None}",
        )
        report.finalize()
        _write_report(report, out_dir)
        return report

    ind_open = open_bar.open
    ind_close = close_bar.close
    ind_high = max(b.high for b in in_grid)
    ind_low = min(b.low for b in in_grid)
    ind_30m_bar = next((b for b in in_grid if b.local_time().time() == _dtime(9, 55)), None)
    ind_first30_vol = sum(b.volume for b in first_30m_bars)
    ind_total_vol = sum(b.volume for b in in_grid)
    if ind_30m_bar is None:
        report.add(
            "21. Market-response derivations match an independent recomputation off the raw bars",
            False,
            "the 09:55 ET boundary bar is absent -- open_to_30m/thirty_min_to_close cannot be recomputed independently",
        )
        report.finalize()
        _write_report(report, out_dir)
        return report
    ind_30m_close = ind_30m_bar.close

    expectations = {
        "open_to_close": (o2c, ind_close / ind_open - 1.0),
        "open_to_30m": (o230, ind_30m_close / ind_open - 1.0),
        "thirty_min_to_close": (t2c, ind_close / ind_30m_close - 1.0),
        "full_session_range": (rng, (ind_high - ind_low) / ind_open),
        "first_30m_volume_share": (vshare, ind_first30_vol / ind_total_vol),
    }
    mismatches = {
        k: {"derivations": v[0], "independent": v[1]}
        for k, v in expectations.items()
        if v[0] is None or abs(v[0] - v[1]) > DERIVATION_EXACTNESS_TOLERANCE
    }
    report.add(
        "21. Market-response derivations match an independent recomputation off the raw bars",
        len(mismatches) == 0,
        json.dumps(mismatches) if mismatches else json.dumps({k: round(v[1], 8) for k, v in expectations.items()}),
    )
    report.add(
        "22. Session boundary fields all resolved (none fell back to None)",
        None
        not in (
            fields.session_open, fields.price_at_30m, fields.session_close,
            fields.session_high, fields.session_low, fields.first_30m_volume, fields.full_session_volume,
        ),
    )

    # --- 6. Provenance / pagination ---------------------------------------
    report.add(
        "23. Pagination handled and recorded -- page_count >= 1 and within the bound",
        1 <= prov.page_count <= 20,
        f"page_count={prov.page_count}, retry_count={prov.retry_count}",
    )
    provenance_fields = asdict(prov)
    report.add(
        "24. Provenance is complete -- no field left unset",
        all(v is not None and v != "" for k, v in provenance_fields.items() if k != "response_symbol_echo")
        and provenance_fields["response_symbol_echo"] is not None,
        json.dumps({k: v for k, v in provenance_fields.items() if v in (None, "")}),
    )
    report.add(
        "25. Both the canonical ticker and the provider symbol are preserved in provenance",
        prov.canonical_ticker == ticker and prov.provider_symbol == provider_symbol_for(ticker),
        f"canonical={prov.canonical_ticker}, provider={prov.provider_symbol}",
    )
    report.add(
        "26. Alpaca's own response echoes the translated provider symbol -- server-side confirmation the symbol resolved",
        prov.response_symbol_echo == provider_symbol_for(ticker),
        f"echo={prov.response_symbol_echo!r}, expected={provider_symbol_for(ticker)!r}",
    )

    # --- 7. Aggregated 5Min vs Alpaca's own 1Day SIP bar ------------------
    if cross_check_daily:
        try:
            daily = fetch_daily_bar_alpaca_sip(
                canonical_ticker=ticker, session_date=session_date, credentials=credentials
            )
            fetch_ok = True
            fetch_detail = ""
        except AlpacaProviderError as e:
            daily = None
            fetch_ok = False
            fetch_detail = repr(e)
        report.add("27. 1Day SIP cross-check fetch succeeded", fetch_ok and daily is not None, fetch_detail or ("returned no daily bar" if daily is None else ""))

        if daily is not None:
            def _rel(a, b):
                if a is None or b is None or b == 0:
                    return None
                return (a - b) / abs(b)

            comparison = {
                "aggregated_5min": {
                    "open": ind_open, "high": ind_high, "low": ind_low, "close": ind_close, "volume": ind_total_vol,
                },
                "alpaca_1day": {
                    "open": daily["open"], "high": daily["high"], "low": daily["low"],
                    "close": daily["close"], "volume": daily["volume"],
                },
                "relative_difference": {
                    "open": _rel(ind_open, daily["open"]),
                    "high": _rel(ind_high, daily["high"]),
                    "low": _rel(ind_low, daily["low"]),
                    "close": _rel(ind_close, daily["close"]),
                    "volume": _rel(ind_total_vol, daily["volume"]),
                },
                "daily_bar_timestamp_utc": daily.get("bar_timestamp_utc"),
                "daily_request_query_string": daily.get("request_query_string"),
                "daily_http_status": daily.get("http_status"),
                "daily_raw_response_sha256": daily.get("raw_response_content_sha256"),
                "ohlc_role": "sanity_comparison",
                "volume_role": "informational_only",
                "volume_status": VOLUME_COMPARISON_STATUS,
                "volume_caveat": (
                    "The aggregation semantics of Alpaca's 1Day bar relative to its 5Min bars are not "
                    "established: which trades each series counts is unknown and has not been determined "
                    "from vendor documentation or a controlled experiment. A volume difference is therefore "
                    "uninterpretable, and no explanation for one is offered here. It is recorded as "
                    "informational only and is NOT an equality gate; it becomes one only once identical "
                    "aggregation semantics are proven."
                ),
            }
            report.daily_bar_comparison = comparison
            # Recorded, never suppressed. OHLC is a genuine sanity comparison
            # -- both series should describe the same regular session, so a
            # material OHLC difference is a real signal. VOLUME is not: see
            # volume_caveat. Neither is gated here; both are reported as data.
            report.add(
                "28. Aggregated-5Min vs 1Day comparison computed and recorded in full (all five deltas, none suppressed)",
                all(k in comparison["relative_difference"] for k in ("open", "high", "low", "close", "volume")),
                json.dumps(comparison["relative_difference"]),
            )
            ohlc_deltas = {
                k: v for k, v in comparison["relative_difference"].items() if k != "volume" and v is not None
            }
            report.add(
                "29. OHLC sanity comparison: aggregated 5Min OHLC matches Alpaca's own 1Day SIP OHLC",
                all(abs(v) <= OHLC_CROSS_CHECK_RELATIVE_TOLERANCE for v in ohlc_deltas.values()),
                json.dumps(ohlc_deltas),
            )
            report.add(
                f"30. Volume difference recorded as INFORMATIONAL ONLY ({VOLUME_COMPARISON_STATUS}) -- "
                f"not an equality gate, because the vendor's 1Day aggregation semantics are unproven",
                comparison["volume_role"] == "informational_only"
                and comparison["volume_status"] == VOLUME_COMPARISON_STATUS,
                f"observed relative volume difference={comparison['relative_difference']['volume']}",
            )

    # --- 8. Data protection ------------------------------------------------
    serialized = json.dumps(report.to_json_dict(), default=str)
    report.add(
        "31. Neither credential appears anywhere in this report",
        credentials.key_id not in serialized and credentials.secret_key not in serialized,
    )
    # Structural, not textual: assert the report object itself holds no
    # per-bar collection anywhere. A grep-for-a-substring check would pass
    # trivially and prove nothing.
    def _holds_bar_rows(value) -> bool:
        if isinstance(value, list):
            return any(isinstance(v, dict) and {"t", "o", "h", "l", "c", "v"} <= set(v) for v in value) or any(
                _holds_bar_rows(v) for v in value
            )
        if isinstance(value, dict):
            return any(_holds_bar_rows(v) for v in value.values())
        return False

    report.add(
        "32. This report contains no raw bar rows anywhere in its structure -- only aggregates, statuses, and hashes",
        not _holds_bar_rows(report.to_json_dict()) and len(serialized) < 20000,
        f"serialized_report_bytes={len(serialized)}",
    )

    report.finalize()
    _write_report(report, out_dir)
    return report


def _write_report(report: AlpacaDiagnosticReport, out_dir: Path) -> Path:
    path = out_dir / f"alpaca_diagnostic_{report.ticker.replace('.', '_')}_{report.session_date}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_json_dict(), f, indent=2, default=str)
    return path
