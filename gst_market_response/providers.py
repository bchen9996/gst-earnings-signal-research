# Provider interfaces. Structured so a future, higher-quality data source can
# replace the development yfinance provider without changing any derived-
# field definition in derivations.py/bars.py -- callers depend only on these
# interfaces, never on yfinance types directly.
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Sequence

from .bars import Bar


class IntradayOHLCVProvider(ABC):
    """Retrieves 5-minute OHLCV bars for one symbol/session. Implementations
    must return bars in chronological order; they are NOT responsible for
    validation (see bars.validate_bars) -- callers validate independently."""

    @abstractmethod
    def get_bars(self, symbol: str, session_date: date) -> list[Bar]:
        ...

    @property
    @abstractmethod
    def provider_label(self) -> str:
        """A short, explicit label identifying data-quality tier, e.g.
        'yfinance-development' or 'exchange-grade-nbbo'. Never left implicit
        -- every raw-bar manifest entry records this."""
        ...

    @property
    def is_eligible_for_real_event(self) -> bool:
        """False by default -- a provider must explicitly opt in. Checked
        before any raw-bar capture that would back a real (non-demo)
        event's COMPLETE status; see
        gst_market_response.alpaca_provider.AlpacaHistoricalSipIntradayProvider
        (True) vs. YFinanceDevIntradayProvider (False, unchanged)."""
        return False


@dataclass(frozen=True)
class EventTimingResult:
    earnings_date: Optional[date]
    earnings_datetime_utc: Optional[datetime]
    release_market_session: Optional[str]  # 'BMO' | 'AMC' | 'INTRADAY' | None if unverified
    event_time_source: Optional[str]
    event_time_retrieved_at_utc: datetime


class EventTimingProvider(ABC):
    """Verifies earnings-event timing for a ticker/fiscal-period. Must NEVER
    infer release_market_session from price/volume behavior -- if a genuine
    timing source doesn't confirm it, release_market_session and
    earnings_datetime_utc must come back None so the caller fails closed
    (see identity.determine_release_market_session)."""

    @abstractmethod
    def get_event_timing(self, ticker: str, fiscal_period: str) -> EventTimingResult:
        ...


class YFinanceDevIntradayProvider(IntradayOHLCVProvider):
    """DEVELOPMENT PROVIDER ONLY. Backed by yfinance's free intraday
    endpoint. This is NOT exchange-grade data, NOT NBBO, and NOT
    institutional execution quality -- yfinance intraday bars are known to
    be delayed/adjusted/occasionally gapped relative to a real feed. Used
    here only because it is the only intraday source currently available to
    this project; every raw-bar manifest entry from this provider records
    provider_label='yfinance-development' so downstream consumers can never
    mistake it for a higher-quality source."""

    def __init__(self) -> None:
        import yfinance as yf  # imported lazily so importing this module never requires yfinance to make a network call

        self._yf = yf

    @property
    def provider_label(self) -> str:
        return "yfinance-development"

    @property
    def is_eligible_for_real_event(self) -> bool:
        # Explicit, not just the inherited default -- this provider must
        # never be usable to back a real event's COMPLETE status, only
        # deterministic fixtures and the bounded diagnostic. See
        # GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md.
        return False

    def get_bars(self, symbol: str, session_date: date) -> list[Bar]:
        # NOTE: this method is exercised only by live capture and the single
        # bounded diagnostic in gst_market_response/diagnostics/ -- never by
        # the deterministic test suite (which constructs Bar objects
        # directly). See SPEC "Explicitly out of scope for v0.1".
        #
        # auto_adjust and prepost are passed EXPLICITLY rather than relying
        # on yfinance's own default (which has changed across versions):
        # auto_adjust=False because a single trading day has no split/
        # dividend event to adjust for, and leaving it implicit would make
        # an intraday/daily OHLC cross-check (see the diagnostic) compare
        # two differently-adjusted series; prepost=False because this
        # module's SPEC section 6 is regular-session-only by definition.
        from datetime import timedelta, timezone as _tz

        ticker = self._yf.Ticker(symbol)
        start = session_date
        end = session_date + timedelta(days=1)
        hist = ticker.history(start=start, end=end, interval="5m", auto_adjust=False, prepost=False)
        bars: list[Bar] = []
        for ts, row in hist.iterrows():
            ts_utc = ts.tz_convert("UTC").to_pydatetime() if ts.tzinfo else ts.replace(tzinfo=_tz.utc)
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp_utc=ts_utc,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                )
            )
        return bars

    def get_daily_bar(self, symbol: str, session_date: date) -> Optional[dict]:
        """Fetches the provider's own single daily OHLCV bar for
        session_date, using the SAME explicit auto_adjust/prepost settings
        as get_bars() -- used only by the diagnostic to cross-check
        aggregated intraday OHLC against this independently-computed daily
        bar. Not used anywhere in normal derivation logic."""
        from datetime import timedelta

        ticker = self._yf.Ticker(symbol)
        start = session_date
        end = session_date + timedelta(days=1)
        hist = ticker.history(start=start, end=end, interval="1d", auto_adjust=False, prepost=False)
        if hist.empty:
            return None
        row = hist.iloc[0]
        return {
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        }
