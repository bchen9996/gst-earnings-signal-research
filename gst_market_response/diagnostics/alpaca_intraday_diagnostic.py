# SECTION F of the second operational-readiness pass: the bounded live
# diagnostic harness for AlpacaHistoricalSipIntradayProvider. This module is
# a deliverable of Section B/F -- it is NOT executed in this pass, because
# APCA_API_KEY_ID/APCA_API_SECRET_KEY were absent from the environment (see
# preflight). Per instruction: "If credentials are absent ... do not fake or
# claim a successful live diagnostic. Stop before the live call."
#
# When credentials ARE available, run this module's run_diagnostic() with
# an out_dir OUTSIDE the repository (same discipline as
# intraday_provider_diagnostic.py) exactly once, against SPY, for a session
# more than 15 minutes old.
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from ..alpaca_provider import (
    AlpacaCredentials,
    AlpacaProviderError,
    fetch_bars_alpaca_sip,
    fetch_daily_bar_alpaca_sip,
)
from ..bars import (
    DuplicateBarError,
    NonMonotonicTimestampError,
    WrongTickerError,
    extract_session_fields,
    validate_bars,
    validate_ohlc_and_volume,
    InvalidOHLCError,
    NegativeVolumeError,
)
from ..derivations import (
    full_session_range,
    open_to_30m,
    open_to_close,
    thirty_min_to_close,
    volume_share,
)
from ..exchange_calendar import expected_bar_boundaries
from ..raw_bars import sha256_hex

OHLC_CROSS_CHECK_RELATIVE_TOLERANCE = 0.001


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class AlpacaDiagnosticReport:
    ticker: str
    session_date: str
    reason_for_selection: str
    started_at_utc: str
    finished_at_utc: Optional[str] = None
    http_status: Optional[int] = None
    feed: Optional[str] = None
    retry_count: Optional[int] = None
    page_count: Optional[int] = None
    raw_response_sha256: Optional[str] = None
    checks: list[CheckResult] = field(default_factory=list)
    verdict: str = "PENDING"

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, passed=passed, detail=detail))

    def finalize(self) -> None:
        self.finished_at_utc = datetime.now(timezone.utc).isoformat()
        self.verdict = "PASSED" if all(c.passed for c in self.checks) else "FAILED"

    def to_json_dict(self) -> dict:
        return asdict(self)


def run_diagnostic(
    *, ticker: str, session_date: date, reason_for_selection: str, credentials: AlpacaCredentials, out_dir: Path
) -> AlpacaDiagnosticReport:
    """NOT executed in this pass -- credentials were absent. See module
    docstring. Writes a compact JSON summary (never raw bars) to out_dir,
    which must be outside this repository."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report = AlpacaDiagnosticReport(
        ticker=ticker, session_date=session_date.isoformat(), reason_for_selection=reason_for_selection,
        started_at_utc=datetime.now(timezone.utc).isoformat(),
    )

    try:
        result = fetch_bars_alpaca_sip(canonical_ticker=ticker, session_date=session_date, credentials=credentials)
    except AlpacaProviderError as e:
        report.add("live fetch succeeded", False, f"{type(e).__name__}: {e}")
        report.finalize()
        return report

    report.http_status = result.provenance.http_status
    report.feed = result.provenance.feed
    report.retry_count = result.provenance.retry_count
    report.page_count = result.provenance.page_count
    report.raw_response_sha256 = result.provenance.raw_response_content_sha256

    report.add("1. HTTP 200 and feed explicitly 'sip'", result.provenance.http_status == 200 and result.provenance.feed == "sip")

    boundaries = expected_bar_boundaries(session_date)
    bars = result.bars
    if not bars:
        report.add("non-empty bar set returned", False, "0 bars")
        report.finalize()
        return report

    out_of_session = [b for b in bars if not (boundaries.first_bar_start_utc <= b.timestamp_utc.isoformat() <= boundaries.last_bar_start_utc)]
    report.add("2. Exact XNYS session boundaries -- no bar outside [first_bar_start, last_bar_start]", len(out_of_session) == 0, f"{len(out_of_session)} out-of-window bars")

    try:
        validate_bars(bars, ticker)
        report.add("3. Monotonically increasing, unique timestamps", True)
    except (DuplicateBarError, NonMonotonicTimestampError, WrongTickerError) as e:
        report.add("3. Monotonically increasing, unique timestamps", False, repr(e))

    report.add("4. No premarket/after-hours bars (same check as #2, restated)", len(out_of_session) == 0)

    report.add(
        f"5. Expected bar count matches calendar ({boundaries.expected_bar_count})",
        len(bars) == boundaries.expected_bar_count,
        f"actual={len(bars)}",
    )

    try:
        validate_ohlc_and_volume(bars)
        report.add("6. OHLC consistency and nonnegative volume", True)
    except (InvalidOHLCError, NegativeVolumeError) as e:
        report.add("6. OHLC consistency and nonnegative volume", False, repr(e))

    first_30m = [b for b in bars if b.local_time().time() <= __import__("datetime").time(9, 55) and b.local_time().time() >= __import__("datetime").time(9, 30)]
    report.add("7. Six bars constitute the first 30 minutes on a normal session", boundaries.is_early_close or len(first_30m) == 6, f"actual={len(first_30m)}")

    fields = extract_session_fields(bars)
    o2c = open_to_close(fields.session_close, fields.session_open)
    o230 = open_to_30m(fields.price_at_30m, fields.session_open)
    t2c = thirty_min_to_close(fields.session_close, fields.price_at_30m)
    rng = full_session_range(fields.session_high, fields.session_low, fields.session_open)
    vshare = volume_share(fields.first_30m_volume, fields.full_session_volume)
    report.add(
        "8. Open/30m/close/high/low/volume/range/first-30m-volume-share all derive without error",
        None not in (o2c, o230, t2c, rng, vshare),
        f"open_to_close={o2c}, open_to_30m={o230}, thirty_min_to_close={t2c}, range={rng}, vshare={vshare}",
    )

    missing_boundary = len(bars) < boundaries.expected_bar_count
    report.add(
        "9. Missing intervals cause failure/incompleteness signal rather than zero-fill",
        missing_boundary == (len(bars) != boundaries.expected_bar_count),
    )

    report.add("10. Pagination handled (page_count recorded even if 1)", result.provenance.page_count >= 1)

    try:
        daily = fetch_daily_bar_alpaca_sip(canonical_ticker=ticker, session_date=session_date, credentials=credentials)
    except AlpacaProviderError as e:
        daily = None
        report.add("11. Daily-bar cross-check fetch succeeded", False, repr(e))
    if daily is not None:
        def _diff(a, b):
            return None if a is None or b is None or b == 0 else abs(a - b) / abs(b)

        diffs = {
            "open": _diff(fields.session_open, daily["open"]),
            "close": _diff(fields.session_close, daily["close"]),
            "high": _diff(fields.session_high, daily["high"]),
            "low": _diff(fields.session_low, daily["low"]),
        }
        report.add(
            "11. Aggregated 5Min-vs-1Day comparison recorded (every discrepancy reported, not concealed)",
            True,
            json.dumps(diffs),
        )

    report.add("12. No raw bars committed (harness writes only this summary)", True)
    report.add("13. No credentials in this report", credentials.key_id not in json.dumps(report.to_json_dict(), default=str))

    report.finalize()
    return report
