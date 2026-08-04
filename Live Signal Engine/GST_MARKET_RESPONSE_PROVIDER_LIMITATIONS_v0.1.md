# Market Response — Provider Limitations (v0.1)

**YFinance remains a development provider**, ineligible for a real event's `COMPLETE` status
(`YFinanceDevIntradayProvider.is_eligible_for_real_event == False`, explicit and unchanged). Nothing in this
document, or anywhere else in this module, claims exchange-grade, NBBO, or institutional execution quality for any
data sourced through `yfinance`.

**`AlpacaHistoricalSipIntradayProvider` (`gst_market_response.alpaca_provider`) is the eligible provider**
(`is_eligible_for_real_event == True`) for real event capture -- delayed/historical SIP data via Alpaca's
documented REST endpoint, never IEX real-time, never Alpaca's free indicative options data used as an OPRA
benchmark. Its retry/timeout/pagination/freshness-gate contract is fully deterministically tested (43 checks,
`test_market_response_alpaca_provider.py`) but **has never been exercised against a real Alpaca response** --
`APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` were absent from the environment throughout both operational-readiness
passes to date. Its canonical-to-provider symbol mapping (`BRK-B -> BRK.B`) is a documented assumption, not yet
live-verified.

## Bounded live diagnostics (2026-08-04, two passes)

### Pass 2 (2026-08-04, this document's most recent update): Alpaca -- NOT RUN, credentials absent

**Preflight confirmed `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` were both absent** from the process environment
and the user-scope environment (checked via both a Bash shell and PowerShell, values never printed -- only
presence/absence checked). Per instruction, the live diagnostic was not attempted; no fake or claimed result is
recorded here. `gst_market_response/diagnostics/alpaca_intraday_diagnostic.py` (the harness for when credentials
become available) was written, and its imports were verified to load cleanly, but it was never executed.

**Missing environment variables**: `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`.

**What running it later will look like**: exactly one call against SPY (not a locked-universe ticker, no earnings
date), for the most recent fully completed ordinary XNYS session more than 15 minutes old at call time, checking
HTTP 200 + `feed=="sip"`, exact XNYS session boundaries (via `exchange_calendar`), monotonic/unique timestamps, no
premarket/after-hours bars, the calendar-derived expected bar count, OHLC consistency + nonnegative volume, the
first-30-minutes 6-bar count, every derivation formula, missing-interval failure (never zero-fill), pagination
handling, and an aggregated-5Min-vs-Alpaca's-own-1Day cross-check with every discrepancy reported. No raw bars
would be committed; only a compact JSON summary + hashes, exactly like Pass 1 below.

### Pass 1 (2026-08-04): yfinance -- RAN, FAILED

**Scope**: one narrowly bounded live diagnostic of `gst_market_response.providers.YFinanceDevIntradayProvider`,
performed as part of an operational-readiness pass, not a research event and not a hypothesis test.

- **Ticker**: `SPY`. Chosen specifically because SPY is not a member of `LOCKED_24_TICKER_UNIVERSE` and has no
  earnings date at all -- it cannot be mistaken for an eligible research event by construction, not just by
  convention.
- **Session**: 2026-08-03 (an ordinary, regular, non-half-day trading session, the most recent fully completed
  session at diagnostic time).
- **Reason recorded before the diagnostic ran**: benchmark-provider validation only; explicitly confirmed not an
  eligible research event before any network call was made.

### Result: **FAILED**

| Check | Result |
|---|---|
| Live fetch completed without an exception | Passed (call returned, no exception raised) |
| Non-empty bar set returned | **FAILED** -- 0 intraday bars, daily bar also missing |
| All subsequent checks (session-only treatment, timezone conversion, bar boundaries, duplicate/monotonic timestamps, OHLC consistency, nonnegative volume, first/last bar, intraday-vs-daily cross-check, provenance, repeatability) | **Not evaluated** -- there was no data to check against |

Per instruction, the diagnostic was classified **FAILED and stopped** at this point. No tolerance was weakened, and
no alternate provider was substituted to force a passing result.

### Root-cause investigation (diagnostic, not a fix)

A direct, unauthenticated HTTPS request to the exact same Yahoo Finance chart endpoint
(`https://query2.finance.yahoo.com/v8/finance/chart/AAPL?range=5d&interval=1d`) with a plain `curl` call, made
immediately after the failed diagnostic, returned **HTTP 200 with genuine, well-formed OHLCV data**. This rules out
a genuine Yahoo Finance data-availability gap or an outbound-network block in this environment.

Verbose (`DEBUG`) logging of `yfinance`'s own request pipeline showed it entering `_get_crumb_basic()` (its
internal cookie/authentication-crumb negotiation step, built on `curl_cffi`) and then failing with `yfinance`'s
generic `"possibly delisted; no price data found"` message -- the same fallback message `yfinance` produces for
several distinct underlying causes, without further detail in this run.

**Most likely explanation**: an environment-specific defect in `yfinance`'s own cookie/crumb request pipeline (a
different HTTP/TLS code path than a plain `curl` request) in this sandbox -- not a genuine data gap, not a code bug
in `YFinanceDevIntradayProvider`'s own logic, and not evidence that the underlying data doesn't exist. This is
recorded as the most likely explanation, not a confirmed root cause -- no further remediation was attempted in this
pass, consistent with "do not weaken tolerances or substitute another provider automatically."

### What this means operationally

- `YFinanceDevIntradayProvider` cannot currently be relied upon to actually retrieve intraday bars in this specific
  execution environment, even though its code (`get_bars()`/`get_daily_bar()`, both with explicit
  `auto_adjust=False, prepost=False`) is unchanged from the prior pass and passed a full deterministic test suite
  using synthetic fixtures.
- **No real event capture can proceed using this provider from this environment until this is resolved or worked
  around through a deliberate, separately-approved change** (e.g., diagnosing `yfinance`'s cookie/crumb pipeline
  further, pinning a different `yfinance`/`curl_cffi` version, or evaluating a different intraday data source) --
  none of which was done in this pass.
- This diagnostic's raw output (a JSON report + `yfinance`'s own stderr log) was written to a scratch directory
  outside this repository and was **not committed** -- there was no actual market data to curate (the fetch
  returned zero rows), and the general policy (raw live data stays local/untracked unless explicitly curated with
  licensing/redistribution documentation) applies regardless.

## Other standing yfinance limitations (unchanged from the prior pass)

- Not exchange-grade, not NBBO, not institutional execution quality.
- Known to occasionally return delayed, adjusted, or gapped bars relative to a real feed.
- `IntradayOHLCVProvider`/`EventTimingProvider` remain abstract interfaces specifically so a higher-quality
  provider can be substituted later without touching any derived-field definition in `bars.py`/`derivations.py` --
  this diagnostic's failure is exactly the kind of finding that interface boundary exists to make swappable, once a
  substitution is deliberately chosen and approved, not automatically defaulted to.
