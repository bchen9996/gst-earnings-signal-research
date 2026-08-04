# SECTION B of the second operational-readiness pass: an official Alpaca
# REST intraday provider, calling Alpaca's documented market-data endpoint
# directly (no SDK). This is the only path this module ever uses for
# eligible (non-development) intraday data -- it NEVER falls back to IEX,
# yfinance, Yahoo's undocumented endpoint, another vendor, or synthetic
# bars. A failure here is reported as a failure, not silently routed
# elsewhere.
from __future__ import annotations

import hashlib
import random
import time as _time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests

from .bars import Bar
from .constants import LOCKED_24_TICKER_UNIVERSE
from .exchange_calendar import session_close_utc, session_open_utc
from .providers import IntradayOHLCVProvider

ALPACA_DATA_HOST = "https://data.alpaca.markets"
ALPACA_BARS_PATH_TEMPLATE = "/v2/stocks/{symbol}/bars"

TIMEFRAME = "5Min"
FEED = "sip"
ADJUSTMENT = "raw"
SORT = "asc"

# --- Bounded retry / timeout / freshness policy -----------------------------
CONNECT_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 15.0
MAX_ATTEMPTS = 5
MAX_WALL_CLOCK_S = 60.0
MAX_PAGES = 20
MAX_RETRY_AFTER_S = 30.0  # cap even an honored Retry-After header, so a misbehaving server can't stall the run indefinitely
BASE_BACKOFF_S = 1.0
RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
DEFAULT_PAGE_LIMIT = 10000

# Alpaca's free/historical SIP entitlement requires the requested window to
# be at least this old -- collecting anything newer would require a paid
# real-time SIP subscription (or fall inside the free IEX real-time tier,
# which this provider deliberately never uses -- see hard-stop list).
MIN_END_AGE_MINUTES = 15


# --- Canonical-to-provider symbol mapping -----------------------------------
# Identity for every ticker except BRK-B, which Alpaca's SIP tape addresses
# with a dot, not a hyphen. NOT yet live-verified against a real Alpaca
# response (credentials were absent for this pass) -- see
# GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md. Both identifiers are
# always recorded in provenance so a wrong assumption here is visible, not
# silently absorbed.
CANONICAL_TO_ALPACA_SYMBOL: dict[str, str] = {t: t for t in LOCKED_24_TICKER_UNIVERSE}
CANONICAL_TO_ALPACA_SYMBOL["BRK-B"] = "BRK.B"
# SPY is used only as a relative-return benchmark (SPEC section 7), not a
# member of the locked universe, but needs the same mapping table.
CANONICAL_TO_ALPACA_SYMBOL["SPY"] = "SPY"


def provider_symbol_for(canonical_ticker: str) -> str:
    return CANONICAL_TO_ALPACA_SYMBOL.get(canonical_ticker, canonical_ticker)


class AlpacaProviderError(RuntimeError):
    pass


class AlpacaCredentialsMissingError(AlpacaProviderError):
    pass


class AlpacaFreshnessGateError(AlpacaProviderError):
    """Raised when the requested end timestamp is not yet 15+ minutes old --
    this provider will not attempt to collect data that would require a
    real-time (non-free, non-historical) SIP entitlement."""


class AlpacaAuthError(AlpacaProviderError):
    """401/403 -- never retried, since retrying a bad credential is pointless
    and risks looking like credential-stuffing against the vendor."""


class AlpacaRetryExhaustedError(AlpacaProviderError):
    pass


@dataclass(frozen=True)
class AlpacaCredentials:
    key_id: str
    secret_key: str

    def __repr__(self) -> str:  # never let a stray print/log leak a secret
        return "AlpacaCredentials(key_id=***, secret_key=***)"

    __str__ = __repr__


def load_alpaca_credentials(env: Optional[dict] = None) -> Optional[AlpacaCredentials]:
    """Reads ONLY APCA_API_KEY_ID / APCA_API_SECRET_KEY. Returns None (never
    raises, never fabricates a placeholder) if either is absent -- callers
    must handle that by stopping before any live call, per instruction."""
    import os

    source = env if env is not None else os.environ
    key_id = source.get("APCA_API_KEY_ID")
    secret_key = source.get("APCA_API_SECRET_KEY")
    if not key_id or not secret_key:
        return None
    return AlpacaCredentials(key_id=key_id, secret_key=secret_key)


def assert_end_is_stale_enough(end_utc: datetime, now_utc: Optional[datetime] = None) -> None:
    now = now_utc or datetime.now(timezone.utc)
    age = now - end_utc
    if age < timedelta(minutes=MIN_END_AGE_MINUTES):
        raise AlpacaFreshnessGateError(
            f"requested end {end_utc.isoformat()} is only {age} old -- must be at least "
            f"{MIN_END_AGE_MINUTES} minutes old for free historical SIP collection"
        )


@dataclass
class AlpacaProvenance:
    provider: str
    api_endpoint: str  # host + path, no query string, no secrets
    feed: str
    timeframe: str
    adjustment: str
    requested_start_utc: str
    requested_end_utc: str
    retrieved_at_utc: str
    http_status: Optional[int]
    retry_count: int
    page_count: int
    raw_response_content_sha256: str
    canonical_ticker: str
    provider_symbol: str


@dataclass
class AlpacaFetchResult:
    bars: list[Bar]
    provenance: AlpacaProvenance


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sleep_for_retry(attempt: int, retry_after_header: Optional[str]) -> float:
    if retry_after_header is not None:
        try:
            wait = min(float(retry_after_header), MAX_RETRY_AFTER_S)
        except ValueError:
            wait = min(BASE_BACKOFF_S * (2 ** attempt), MAX_RETRY_AFTER_S)
    else:
        wait = min(BASE_BACKOFF_S * (2 ** attempt) + random.uniform(0, 0.5), MAX_RETRY_AFTER_S)
    return max(wait, 0.0)


def fetch_bars_alpaca_sip(
    *,
    canonical_ticker: str,
    session_date: date,
    credentials: AlpacaCredentials,
    session: Optional[requests.Session] = None,
    sleep_fn=_time.sleep,
    now_fn=lambda: datetime.now(timezone.utc),
    timeframe: str = TIMEFRAME,
) -> AlpacaFetchResult:
    """The ONE network entry point in this module. Fetches every bar (at
    `timeframe` granularity, 5Min by default) for canonical_ticker's regular
    XNYS session on session_date, handling pagination and bounded retries.
    Raises AlpacaProviderError (or a subclass) on any failure -- never
    returns synthetic/partial-silently bars and never calls a different
    provider itself."""
    provider_symbol = provider_symbol_for(canonical_ticker)
    start_utc = session_open_utc(session_date)
    end_utc = session_close_utc(session_date)

    now = now_fn()
    assert_end_is_stale_enough(end_utc, now)

    http = session or requests.Session()
    endpoint = ALPACA_DATA_HOST + ALPACA_BARS_PATH_TEMPLATE.format(symbol=provider_symbol)
    headers = {
        "APCA-API-KEY-ID": credentials.key_id,
        "APCA-API-SECRET-KEY": credentials.secret_key,
    }

    all_bars_raw: list[dict] = []
    raw_response_texts: list[str] = []
    page_token: Optional[str] = None
    page_count = 0
    retry_count = 0
    attempts_this_page = 0
    last_status: Optional[int] = None
    deadline = _time.monotonic() + MAX_WALL_CLOCK_S

    while True:
        if _time.monotonic() > deadline:
            raise AlpacaRetryExhaustedError(f"wall-clock budget of {MAX_WALL_CLOCK_S}s exceeded")

        params = {
            "timeframe": timeframe,
            "feed": FEED,
            "adjustment": ADJUSTMENT,
            "sort": SORT,
            "start": _rfc3339(start_utc),
            "end": _rfc3339(end_utc),
            "limit": DEFAULT_PAGE_LIMIT,
        }
        if page_token:
            params["page_token"] = page_token

        try:
            resp = http.get(endpoint, params=params, headers=headers, timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S))
        except requests.Timeout as e:
            attempts_this_page += 1
            if attempts_this_page >= MAX_ATTEMPTS:
                raise AlpacaRetryExhaustedError(f"timeout after {attempts_this_page} attempts on page {page_count}") from e
            retry_count += 1
            sleep_fn(_sleep_for_retry(attempts_this_page, None))
            continue

        last_status = resp.status_code

        if resp.status_code in (401, 403):
            raise AlpacaAuthError(f"HTTP {resp.status_code} from Alpaca -- credentials rejected, not retrying")

        if resp.status_code in RETRYABLE_HTTP_STATUSES:
            attempts_this_page += 1
            if attempts_this_page >= MAX_ATTEMPTS:
                raise AlpacaRetryExhaustedError(
                    f"HTTP {resp.status_code} persisted after {attempts_this_page} attempts on page {page_count}"
                )
            retry_count += 1
            sleep_fn(_sleep_for_retry(attempts_this_page, resp.headers.get("Retry-After")))
            continue

        if resp.status_code != 200:
            raise AlpacaProviderError(f"unexpected HTTP {resp.status_code} from Alpaca: {resp.text[:500]!r}")

        attempts_this_page = 0
        page_count += 1
        if page_count > MAX_PAGES:
            raise AlpacaRetryExhaustedError(f"exceeded {MAX_PAGES}-page pagination bound")

        raw_response_texts.append(resp.text)
        payload = resp.json()
        page_bars = payload.get("bars") or []
        all_bars_raw.extend(page_bars)

        page_token = payload.get("next_page_token")
        if not page_token:
            break

    content_hash = _sha256_text("".join(raw_response_texts))

    parsed_bars: list[Bar] = []
    for raw in all_bars_raw:
        ts = datetime.fromisoformat(raw["t"].replace("Z", "+00:00"))
        parsed_bars.append(
            Bar(
                symbol=canonical_ticker,
                timestamp_utc=ts,
                open=float(raw["o"]),
                high=float(raw["h"]),
                low=float(raw["l"]),
                close=float(raw["c"]),
                volume=int(raw["v"]),
            )
        )

    provenance = AlpacaProvenance(
        provider="alpaca-historical-sip",
        api_endpoint=endpoint,
        feed=FEED,
        timeframe=timeframe,
        adjustment=ADJUSTMENT,
        requested_start_utc=start_utc.isoformat(),
        requested_end_utc=end_utc.isoformat(),
        retrieved_at_utc=now.isoformat(),
        http_status=last_status,
        retry_count=retry_count,
        page_count=page_count,
        raw_response_content_sha256=content_hash,
        canonical_ticker=canonical_ticker,
        provider_symbol=provider_symbol,
    )
    return AlpacaFetchResult(bars=parsed_bars, provenance=provenance)


def fetch_daily_bar_alpaca_sip(
    *,
    canonical_ticker: str,
    session_date: date,
    credentials: AlpacaCredentials,
    session: Optional[requests.Session] = None,
    sleep_fn=_time.sleep,
    now_fn=lambda: datetime.now(timezone.utc),
) -> Optional[dict]:
    """Fetches Alpaca's own single 1Day SIP bar for the same session, used
    ONLY by the diagnostic's aggregated-intraday-vs-daily cross-check (SPEC
    section 5 doesn't require this for real event capture -- only the 5Min
    bars are). Same retry/pagination/freshness machinery as
    fetch_bars_alpaca_sip, just a different timeframe."""
    result = fetch_bars_alpaca_sip(
        canonical_ticker=canonical_ticker, session_date=session_date, credentials=credentials,
        session=session, sleep_fn=sleep_fn, now_fn=now_fn, timeframe="1Day",
    )
    if not result.bars:
        return None
    b = result.bars[0]
    return {"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}


class AlpacaHistoricalSipIntradayProvider(IntradayOHLCVProvider):
    """The eligible (non-development) intraday provider. Requires real
    credentials -- construction raises AlpacaCredentialsMissingError if
    load_alpaca_credentials() returns None, so a caller can never silently
    end up with a provider that quietly does nothing."""

    def __init__(self, credentials: Optional[AlpacaCredentials] = None):
        self._credentials = credentials or load_alpaca_credentials()
        if self._credentials is None:
            raise AlpacaCredentialsMissingError(
                "APCA_API_KEY_ID and/or APCA_API_SECRET_KEY are not set -- cannot construct an eligible provider"
            )
        self.last_provenance: Optional[AlpacaProvenance] = None

    @property
    def provider_label(self) -> str:
        return "alpaca-historical-sip"

    @property
    def is_eligible_for_real_event(self) -> bool:
        return True

    def get_bars(self, symbol: str, session_date: date) -> list[Bar]:
        result = fetch_bars_alpaca_sip(canonical_ticker=symbol, session_date=session_date, credentials=self._credentials)
        self.last_provenance = result.provenance
        return result.bars
