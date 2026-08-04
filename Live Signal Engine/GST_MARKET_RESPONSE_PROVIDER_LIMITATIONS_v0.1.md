# Market Response — Development Provider Limitations (v0.1)

**YFinance remains a development provider.** Nothing in this document, or anywhere else in this module, claims
exchange-grade, NBBO, or institutional execution quality for any data sourced through `yfinance`.

## Bounded live diagnostic (2026-08-04)

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
