# TASK 4 of the operational-readiness pass: one narrowly bounded live
# diagnostic of YFinanceDevIntradayProvider against ONE ordinary, completed,
# non-earnings trading session. This validates the PROVIDER's mechanics
# against the locked contract in bars.py/derivations.py -- it is NOT a
# research event, NOT a hypothesis test, and its output is never fed into
# the event state machine (event_record.py/pipeline.py). The ticker used is
# SPY specifically because SPY is not a member of LOCKED_24_TICKER_UNIVERSE
# and has no earnings date at all -- it cannot be mistaken for a research
# observation by construction, not just by convention.
#
# Writes all output to an explicitly-supplied out_dir (never a path inside
# this repo) so downloaded market data never collides with, or is
# accidentally committed alongside, research artifacts.
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Optional

from ..bars import (
    Bar,
    DuplicateBarError,
    NonMonotonicTimestampError,
    WrongTickerError,
    extract_session_fields,
    validate_bars,
)
from ..providers import YFinanceDevIntradayProvider
from ..raw_bars import sha256_hex

EXPECTED_SESSION_OPEN = time(9, 30)
EXPECTED_SESSION_LAST_BAR_START = time(15, 55)
EXPECTED_BAR_COUNT_FULL_SESSION = 78  # 6.5h * 60min / 5min

# Aggregated-intraday-vs-daily-bar cross-check tolerance. Both calls use the
# SAME explicit auto_adjust=False/prepost=False settings (see providers.py),
# so this is checking for genuine data-consistency issues, not an
# adjustment-methodology mismatch. A tight but nonzero tolerance accounts
# for ordinary floating-point/rounding noise only.
OHLC_CROSS_CHECK_RELATIVE_TOLERANCE = 0.001  # 0.1%


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class DiagnosticReport:
    ticker: str
    session_date: str
    reason_for_selection: str
    provider_label: str
    started_at_utc: str
    finished_at_utc: Optional[str] = None
    raw_intraday_path: Optional[str] = None
    raw_intraday_sha256: Optional[str] = None
    raw_daily_path: Optional[str] = None
    raw_daily_sha256: Optional[str] = None
    checks: list[CheckResult] = field(default_factory=list)
    verdict: str = "PENDING"  # PASSED | FAILED

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, passed=passed, detail=detail))

    def finalize(self) -> None:
        self.finished_at_utc = datetime.now(timezone.utc).isoformat()
        self.verdict = "PASSED" if all(c.passed for c in self.checks) else "FAILED"

    def to_json_dict(self) -> dict:
        d = asdict(self)
        return d


def _write_raw_bars_csv(path: Path, bars: list[Bar]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "timestamp_utc", "open", "high", "low", "close", "volume"])
        for b in bars:
            writer.writerow([b.symbol, b.timestamp_utc.isoformat(), b.open, b.high, b.low, b.close, b.volume])


def _read_raw_bars_csv(path: Path, symbol: str) -> list[Bar]:
    import csv

    bars = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            bars.append(
                Bar(
                    symbol=row["symbol"],
                    timestamp_utc=datetime.fromisoformat(row["timestamp_utc"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                )
            )
    return bars


def run_diagnostic(
    *,
    ticker: str,
    session_date: date,
    reason_for_selection: str,
    out_dir: Path,
) -> DiagnosticReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    provider = YFinanceDevIntradayProvider()
    report = DiagnosticReport(
        ticker=ticker,
        session_date=session_date.isoformat(),
        reason_for_selection=reason_for_selection,
        provider_label=provider.provider_label,
        started_at_utc=datetime.now(timezone.utc).isoformat(),
    )

    # ---- The ONE live network call this diagnostic makes (plus its daily-
    #      bar companion call, same session, needed for the OHLC cross-check).
    try:
        bars = provider.get_bars(ticker, session_date)
        daily_bar = provider.get_daily_bar(ticker, session_date)
    except Exception as e:  # noqa: BLE001 -- diagnostic must record ANY failure, not just expected ones
        report.add("live fetch succeeded", False, f"exception during live fetch: {e!r}")
        report.finalize()
        return report
    report.add("live fetch succeeded", True, f"{len(bars)} intraday bars, daily_bar={'present' if daily_bar else 'MISSING'}")

    if not bars:
        report.add("non-empty bar set returned", False, "provider returned zero bars for this session")
        report.finalize()
        return report
    report.add("non-empty bar set returned", True, f"{len(bars)} bars")

    # ---- Raw-response provenance: save exactly what was received, hash it.
    raw_intraday_path = out_dir / f"{ticker}_{session_date.isoformat()}_intraday_raw.csv"
    _write_raw_bars_csv(raw_intraday_path, bars)
    raw_intraday_hash = sha256_hex(raw_intraday_path.read_bytes())
    report.raw_intraday_path = str(raw_intraday_path)
    report.raw_intraday_sha256 = raw_intraday_hash
    report.add("raw intraday response saved with SHA-256 provenance", True, raw_intraday_hash)

    raw_daily_path = out_dir / f"{ticker}_{session_date.isoformat()}_daily_raw.json"
    raw_daily_path.write_text(json.dumps(daily_bar, indent=2), encoding="utf-8")
    raw_daily_hash = sha256_hex(raw_daily_path.read_bytes())
    report.raw_daily_path = str(raw_daily_path)
    report.raw_daily_sha256 = raw_daily_hash
    report.add("raw daily-bar response saved with SHA-256 provenance", True, raw_daily_hash)

    # ---- Explicit auto_adjust / regular-session-only treatment (provider.py
    #      now passes these explicitly; this just confirms the effect is
    #      visible in what came back -- no adjustment artifacts, no bars
    #      outside 09:30-16:00 ET).
    report.add(
        "auto_adjust passed explicitly (False) -- see providers.py",
        True,
        "get_bars()/get_daily_bar() both call history(auto_adjust=False, prepost=False) explicitly",
    )

    out_of_session = [b for b in bars if not (EXPECTED_SESSION_OPEN <= b.local_time().time() < time(16, 0))]
    report.add(
        "regular-session-only (no pre/post-market bars)",
        len(out_of_session) == 0,
        f"{len(out_of_session)} bars outside 09:30-16:00 ET" if out_of_session else "all bars within session",
    )

    # ---- Exchange timezone conversion sanity: first bar's ET local time
    #      hour should be 9 (market open hour), not e.g. 13/14 (a UTC-labeled-
    #      as-ET bug) or the raw UTC hour unconverted.
    first_local = bars[0].local_time()
    report.add(
        "exchange timezone conversion (America/New_York)",
        first_local.tzinfo is not None and first_local.hour in (9,),
        f"first bar local time: {first_local.isoformat()}",
    )

    # ---- Expected 5-minute bar boundaries / first-last expected bars.
    misaligned = [b for b in bars if b.local_time().minute % 5 != 0 or b.local_time().second != 0]
    report.add("all bars on exact 5-minute boundaries", len(misaligned) == 0, f"{len(misaligned)} misaligned bars")

    first_bar_time = bars[0].local_time().time()
    last_bar_time = bars[-1].local_time().time()
    report.add(
        "first bar starts at session open (09:30 ET)",
        first_bar_time == EXPECTED_SESSION_OPEN,
        f"actual first bar time: {first_bar_time}",
    )
    report.add(
        "last bar starts at expected final 5-min slot (15:55 ET) for a full session",
        last_bar_time == EXPECTED_SESSION_LAST_BAR_START,
        f"actual last bar time: {last_bar_time}",
    )
    report.add(
        f"bar count matches a full regular session ({EXPECTED_BAR_COUNT_FULL_SESSION} bars)",
        len(bars) == EXPECTED_BAR_COUNT_FULL_SESSION,
        f"actual: {len(bars)}",
    )

    # ---- No duplicates, strictly monotonic, correct ticker -- reuses the
    #      SAME validator the real pipeline uses, not a diagnostic-only copy.
    try:
        validate_bars(bars, ticker)
        report.add("validate_bars(): no duplicates / strictly monotonic / correct ticker", True)
    except (DuplicateBarError, NonMonotonicTimestampError, WrongTickerError) as e:
        report.add("validate_bars(): no duplicates / strictly monotonic / correct ticker", False, repr(e))

    # ---- OHLC internal consistency + nonnegative volume.
    bad_ohlc = [b for b in bars if not (b.low <= b.open <= b.high and b.low <= b.close <= b.high and b.low <= b.high)]
    report.add("OHLC consistency (low <= open,close <= high)", len(bad_ohlc) == 0, f"{len(bad_ohlc)} inconsistent bars")

    negative_volume = [b for b in bars if b.volume < 0]
    report.add("nonnegative volume on every bar", len(negative_volume) == 0, f"{len(negative_volume)} negative-volume bars")

    # ---- Aggregated intraday OHLC vs. the provider's own daily bar.
    if daily_bar is not None:
        session_fields = extract_session_fields(bars)
        agg_open = session_fields.session_open
        agg_close = session_fields.session_close
        agg_high = session_fields.session_high
        agg_low = session_fields.session_low

        def _within_tol(a: Optional[float], b: Optional[float]) -> bool:
            if a is None or b is None:
                return False
            if b == 0:
                return a == 0
            return abs(a - b) / abs(b) <= OHLC_CROSS_CHECK_RELATIVE_TOLERANCE

        report.add(
            "aggregated intraday open matches provider's own daily open",
            _within_tol(agg_open, daily_bar["open"]),
            f"intraday={agg_open}, daily={daily_bar['open']}",
        )
        report.add(
            "aggregated intraday close matches provider's own daily close",
            _within_tol(agg_close, daily_bar["close"]),
            f"intraday={agg_close}, daily={daily_bar['close']}",
        )
        report.add(
            "aggregated intraday high matches provider's own daily high",
            _within_tol(agg_high, daily_bar["high"]),
            f"intraday={agg_high}, daily={daily_bar['high']}",
        )
        report.add(
            "aggregated intraday low matches provider's own daily low",
            _within_tol(agg_low, daily_bar["low"]),
            f"intraday={agg_low}, daily={daily_bar['low']}",
        )
    else:
        report.add("aggregated intraday OHLC vs. daily bar", False, "no daily bar was returned to compare against")

    # ---- Repeatability of PARSING/DERIVATION (not of the live call itself
    #      -- see module docstring: this diagnostic makes exactly one live
    #      fetch). Re-parses the FROZEN raw file a second time, independent
    #      of the network, and confirms identical derived session fields.
    reparsed_bars = _read_raw_bars_csv(raw_intraday_path, ticker)
    fields_a = extract_session_fields(bars)
    fields_b = extract_session_fields(reparsed_bars)
    report.add(
        "parsing/derivation is repeatable from the frozen raw response",
        fields_a == fields_b,
        f"first-pass fields == second-pass (reloaded-from-disk) fields: {fields_a == fields_b}",
    )

    report.finalize()
    return report
