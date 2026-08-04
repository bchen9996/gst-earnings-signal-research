# Market Response — Provider Limitations (v0.1)

**YFinance remains a development provider**, ineligible for a real event's `COMPLETE` status
(`YFinanceDevIntradayProvider.is_eligible_for_real_event == False`, explicit and unchanged). Nothing in this
document, or anywhere else in this module, claims exchange-grade, NBBO, or institutional execution quality for any
data sourced through `yfinance`.

**`AlpacaHistoricalSipIntradayProvider` (`gst_market_response.alpaca_provider`) is CLEARED for real event
capture** as of the post-fix validation (2026-08-04, Pass 4, below): `operational_clearance_status ==
LIVE_DIAGNOSTIC_PASSED`, and `is_eligible_for_real_event` -- now a *derived* property -- evaluates True. Defect
ALP-1 is **fixed and closed**. Delayed/historical SIP data via Alpaca's documented REST endpoint, never IEX
real-time, never Alpaca's free indicative options data used as an OPRA benchmark.

**Clearance is not production-readiness.** It means one bounded live diagnostic passed against two benchmark
tickers on one historical session. **One complete prospective earnings event is still required** before this lane
can be called production-ready.

## Eligibility is derived, not declared

Before Pass 4, `is_eligible_for_real_event` was a hard-coded `True` on this provider. That single flag fused two
unrelated ideas, and as a result it read as clearance for real capture while no live diagnostic had ever run --
and kept reading that way after one FAILED. They are now separate:

| Property | Meaning | Alpaca | yfinance |
|---|---|---|---|
| `supports_real_event_semantics` | **Structural**, permanent: does the provider implement the SIP/raw/exact-session contract at all? | `True` | `False` |
| `operational_clearance_status` | **Operational**, changes over time: what a live diagnostic has actually demonstrated | `LIVE_DIAGNOSTIC_PASSED` | `LIVE_DIAGNOSTIC_FAILED` |
| `is_eligible_for_real_event` | **Derived** -- never set directly | `True` | `False` |

`providers.compute_real_event_eligibility()` is the single definition, a pure function requiring *all* of:
`supports_real_event_semantics`, clearance `== LIVE_DIAGNOSTIC_PASSED`, `feed == "sip"`, `adjustment == "raw"`,
the ALP-1 session-grid guard active, and credentials present. `NOT_RUN`, `LIVE_DIAGNOSTIC_FAILED`, an
unrecognized status, `feed="iex"`, a non-raw adjustment, a disabled grid guard, or absent credentials each make it
ineligible on their own. Being pure, the full truth table is deterministically tested without constructing a
provider or touching a network -- including `feed="iex"`, which is exercised as an *input* so no IEX code path
needs to exist.

## Bounded live diagnostics (2026-08-04, four passes)

### Pass 4 (2026-08-04, this document's most recent update): Alpaca post-fix -- RAN, **PASSED**

Run exactly once per ticker after the ALP-1 fix, against the same completed 2026-08-03 XNYS session. Neither
registered a research event. The pass-3 failure evidence is preserved untouched alongside this.

| Evidence | SPY | BRK-B |
|---|---|---|
| Verdict | **PASSED 33/33** | **PASSED 29/29** |
| HTTP status | 200 | 200 |
| Query string on the wire | `adjustment=raw&end=2026-08-03T19:55:00Z&feed=sip&limit=10000&sort=asc&start=2026-08-03T13:30:00Z&timeframe=5Min` | identical |
| `feed` / `timeframe` / `adjustment` | `sip` / `5Min` / `raw` | `sip` / `5Min` / `raw` |
| Alpaca's echoed symbol | `SPY` | **`BRK.B`** |
| Pages / retries | 1 / 0 | 1 / 0 |
| Raw-response SHA-256 | `1313d07b2a5843d89d6e3bd0cc7c4cb3e011482709812cc21cb1132a18aa7af2` | `4d3c6713b6ce1f6b75f9d53dfe73a32c13f569bab18f1e2a36021e9983d0ffd9` |
| **Bars returned** | **78 / 78 expected** | **78 / 78 expected** |
| First bar | **09:30:00 ET** | **09:30:00 ET** |
| Last bar | **15:55:00 ET** | **15:55:00 ET** |
| Off-grid bars | 0 | 0 |
| Missing bars | 0 | 0 |

Note the requested `end` is now `19:55:00Z` (15:55 ET), not `20:00:00Z`. That one change is the fix.

**The daily cross-check independently confirms it.** Aggregating the 78 regular-session bars now reproduces
Alpaca's own 1Day SIP OHLC **exactly** -- and, unlike Pass 3, this is the *uncontaminated* aggregate:

| Field | Aggregated 78 × 5Min | Alpaca 1Day SIP | Relative difference |
|---|---|---|---|
| open | 749.44 | 749.44 | **0.0** |
| high | 758.58 | 758.58 | **0.0** |
| low | 748.80 | 748.80 | **0.0** |
| close | **757.67** | **757.67** | **0.0** |
| volume | 50,712,611 | 60,014,445 | −15.499% *(informational only -- see below)* |

In Pass 3 the contaminated 79-bar aggregate put close at 757.72, 6.6 bp off the daily bar. Post-fix the two
independent Alpaca endpoints agree to the cent on all four OHLC fields.

### Correction: the daily-volume difference has NO established explanation

**Retracted.** The Pass 3 write-up stated the −15.50% daily-vs-aggregate volume gap was *"most likely"* because
Alpaca's 1Day equity bar includes extended-hours volume. **That was an unsupported guess and is withdrawn.** It
was never verified against vendor documentation or a controlled experiment, and it should not have been offered as
a leading explanation.

The difference is now recorded as **`unresolved_provider_aggregation_semantics`**. The aggregation semantics of
Alpaca's 1Day bar relative to its 5Min bars are simply **not established**: which trades each series counts is
unknown. No explanation is offered.

Consequently:

- **Daily OHLC remains a genuine sanity comparison** and *is* gated (check 29, 10 bp tolerance). Both series
  should describe the same regular session, so a material OHLC difference is a real signal -- as Pass 3
  demonstrated when contamination pushed close 6.6 bp off.
- **Daily volume is informational only** (check 30) and is **not an equality gate**. It becomes one only if
  identical aggregation semantics are first proven. Until then, an Alpaca 1Day volume must not be compared
  against, or substituted for, a regular-session volume aggregate.

### The ALP-1 fix, in three independent layers

1. **Request** -- `fetch_bars_alpaca_sip` sets `end` to the **final expected bar start** from
   `exchange_calendar.expected_bar_starts_utc()`, never `session_close_utc`. Derived dynamically, so an early
   close asks through 12:55 ET (42 bars) rather than a hard-coded 15:55.
2. **Validation** -- `_assert_exact_session_grid()` requires the returned timestamp set to **equal** the expected
   set. Missing, extra, duplicate, misaligned and out-of-session bars each raise `AlpacaSessionGridError`.
   Nothing trims, pads, re-sorts or de-duplicates: silently repairing a malformed response is precisely how ALP-1
   stayed invisible.
3. **Extraction** -- `bars.extract_session_fields()` selects the open and close bars **by their expected
   timestamps**, never `bars[0]`/`bars[-1]`. Even with layers 1-2 bypassed entirely, a stray 16:00 ET bar cannot
   become `session_close`, cannot set the session high/low, and cannot inflate volume. Extraction is also now
   order-independent.

Disabling layer 2 (`SESSION_GRID_ENFORCED`) mechanically revokes real-event eligibility, so the fix cannot be
turned off without also removing clearance.

### Pass 3 (2026-08-04): Alpaca pre-fix -- RAN, **FAILED**

*Preserved verbatim as the evidence that produced defect ALP-1. Superseded by Pass 4 above; the
`..._LIVE_DIAGNOSTIC_SPY_2026-08-03.json` / `..._BRK-B_...` reports are likewise preserved unmodified alongside
the new `..._POSTFIX_...` ones. The one edit below is the retraction of the daily-volume explanation, marked
inline.*

**Credentials present** at preflight (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`; presence confirmed, values never
printed, logged, serialized or committed). Two diagnostics were run, **exactly once each**, against the completed
2026-08-03 ordinary XNYS session. Neither registered a research event.

- **Diagnostic A** -- `SPY` (not in `LOCKED_24_TICKER_UNIVERSE`, no earnings date, so it cannot be mistaken for an
  eligible research event by construction). Full 31-check suite plus the aggregated-5Min-vs-1Day cross-check.
  **27/31 passed, verdict FAILED.**
- **Diagnostic B** -- canonical `BRK-B` / provider symbol `BRK.B`, same session, run solely to validate symbol
  translation. 29-check suite (no daily cross-check). **25/29 passed, verdict FAILED**, with the *same four*
  failures as SPY and no additional ones.

**Transport evidence (both diagnostics, first-hand):**

| Evidence | SPY | BRK-B |
|---|---|---|
| HTTP status | 200 | 200 |
| Query string on the wire | `adjustment=raw&end=2026-08-03T20:00:00Z&feed=sip&limit=10000&sort=asc&start=2026-08-03T13:30:00Z&timeframe=5Min` | identical |
| `feed` / `timeframe` / `adjustment` | `sip` / `5Min` / `raw` | `sip` / `5Min` / `raw` |
| Alpaca's echoed symbol | `SPY` | **`BRK.B`** |
| Pages / retries | 1 / 0 | 1 / 0 |
| Raw-response SHA-256 | `e253a7b603bf12e8c3f18b127880cc5a8bc5f52081ca5b1742a253f6310c8c4d` | `9b0bb3aa1edf784f475209b93a5997a6afe2763da1eaa2b94af10b8ef18d6a0f` |
| Bars returned | **79** (expected 78) | **79** (expected 78) |
| First bar | 09:30:00 ET | 09:30:00 ET |
| Last bar | **16:00:00 ET** (expected 15:55) | **16:00:00 ET** (expected 15:55) |

Alpaca's single-symbol `/v2/stocks/{symbol}/bars` response does **not** echo `feed`. The query string above is
therefore the first-hand evidence that `feed=sip` was genuinely requested; it is recorded in provenance
(`AlpacaProvenance.request_query_string`) precisely so this cannot be taken on trust. A SIP request without SIP
entitlement returns 403, so the HTTP 200 is corroborating -- but the query string is the direct evidence.

**What passed (27 checks, SPY):** HTTP 200; `feed=sip`/`timeframe=5Min`/`adjustment=raw` all confirmed on the wire;
IEX never requested; requested window exactly equal to the calendar's XNYS regular session; **zero missing
regular-session bars**; first bar exactly 09:30 ET; unique and strictly monotonically increasing timestamps; every
consecutive gap exactly 5 minutes; valid OHLC on every bar; nonnegative volume on every bar; no zero-fill signature
and in fact no zero-volume bar at all; exactly 6 bars in the first 30 minutes; all five market-response derivations
matching an independent recomputation off the raw bars to within 1e-12; all session-boundary fields resolved;
pagination handled and bounded; provenance complete; canonical **and** provider symbols both preserved; Alpaca's
own response echo matching the translated symbol; the daily cross-check computed and recorded in full; neither
credential anywhere in the report; no raw bar rows in the report.

**What failed (4 checks, identically on both tickers):**

| Check | Result |
|---|---|
| 8. No extended-hours contamination | **FAILED** -- 1 off-grid bar, starting `2026-08-03T20:00:00Z` (16:00:00 ET) |
| 10. Expected bar count matches calendar (78) | **FAILED** -- 79 returned |
| 12. Last bar starts at 15:55 ET | **FAILED** -- last bar starts 16:00 ET |
| 19. Bar count and grid coverage agree | **FAILED** -- consequence of the above |

### Open defect ALP-1 (root cause, confirmed and reproduced)

`fetch_bars_alpaca_sip` requests `end = session_close_utc(session_date)` -- i.e. `20:00:00Z` / 16:00 ET.
**Alpaca's `end` parameter is inclusive of a bar whose START equals `end`.** The regular session's last legitimate
5-minute bar starts at 15:55 ET; a bar starting at 16:00 ET covers 16:00-16:05 and is an **after-hours** bar. Every
request therefore pulls exactly one after-hours bar into what is treated as the regular session.

This is not cosmetic. `bars.extract_session_fields()` takes `session_close` from `bars[-1].close`, so the
after-hours bar silently *became* the session close:

| Quantity | Correct (78 bars) | Contaminated (79 bars) |
|---|---|---|
| SPY `session_close` | 757.67 | 757.72 |
| SPY `open_to_close` | 0.01098153 | 0.01104825 (**+6.7 bp**) |
| SPY full-session volume | 50,712,611 | 52,265,414 (**+3.1%**) |
| BRK-B `session_close` | 513.09 | 513.12 |
| BRK-B `open_to_close` | -0.00357330 | -0.00351504 |

**The daily cross-check independently corroborates the root cause.** Aggregating only the 78 regular-session bars
reproduces Alpaca's own 1Day SIP bar's OHLC *exactly*, to the cent:

| Field | Aggregated 78 × 5Min | Alpaca 1Day SIP | Relative difference |
|---|---|---|---|
| open | 749.44 | 749.44 | **0.0** |
| high | 758.58 | 758.58 | **0.0** |
| low | 748.80 | 748.80 | **0.0** |
| close | 757.67 | 757.67 | **0.0** |
| volume | 50,712,611 | 60,014,445 | **-15.50%** |

Using the contaminated 79-bar aggregate instead, the close diverges by +6.6 bp. Two independent Alpaca endpoints
agreeing exactly on the 78-bar OHLC, and disagreeing under the 79-bar aggregate, is about as direct a confirmation
of ALP-1 as this diagnostic can produce.

**The remaining volume discrepancy (-15.50%) is a genuine, separate finding and is reported, not explained away.**

> **RETRACTED (Pass 4, 2026-08-04).** This paragraph originally continued: *"It is a vendor session-definition
> difference: Alpaca's 1Day equity bar includes extended-hours volume ... recorded as the leading explanation, not
> an established fact."* **That explanation was an unsupported guess and is withdrawn.** It was never verified
> against vendor documentation or a controlled experiment. The difference is now classified
> **`unresolved_provider_aggregation_semantics`**: the aggregation semantics of Alpaca's 1Day bar relative to its
> 5Min bars are not established, and no explanation is offered. The practical consequence is unchanged and stands
> on its own: **an Alpaca 1Day volume must never be compared against, or substituted for, a regular-session volume
> aggregate** in this module. Daily volume is informational only and is not an equality gate; daily OHLC remains a
> genuine sanity comparison. See the Pass 4 correction section above.

**Prescribed fix (not applied in Pass 3; APPLIED AND VALIDATED IN PASS 4).** Request
`end = last_bar_start_utc` (19:55:00Z) so the grid closes at 15:55 ET. It was deliberately not applied in Pass 3
because that pass's governing instruction was to run each diagnostic exactly once and not restart a failed one, so
a fix could not have been live-validated then. It was pinned in the interim by a characterization test
(`test_known_defect_end_boundary_is_inclusive`) asserting the defective boundary and its downstream consequence,
so the fix could not land silently. Pass 4 landed it and, exactly as that test's docstring instructed, replaced
those assertions with ones asserting the *corrected* boundary. See "The ALP-1 fix, in three independent layers"
above.

**The harness's detectors are themselves proven.** `test_market_response_alpaca_diagnostic_harness.py` (47 checks)
reconstructs the exact 79-bar response offline and confirms the harness fails checks 8/10/12/19 and *only* those,
that a clean 78-bar session passes, that a 77-bar session fails differently (missing, not contaminated), that
zero-fill signatures, invalid OHLC and negative volume are each caught, and that a provider error yields FAILED
rather than a vacuous pass. The FAILED verdict above is therefore a measured result, not an artifact.

### Symbol translation: the one thing Diagnostic B set out to test

`BRK-B -> BRK.B` is **live-verified**. Alpaca returned HTTP 200 and echoed `"symbol": "BRK.B"` in the response
body, and the returned bars are real BRK.B tape data (79 bars, valid OHLC, ~2.93M regular-session shares). Both
identifiers are preserved in provenance (`canonical_ticker="BRK-B"`, `provider_symbol="BRK.B"`). This assumption is
no longer an assumption. It was recorded separately from the Pass 3 verdict because it was independently useful:
BRK-B's ineligibility was inherited from ALP-1, which affected all 24 tickers equally, and was **not** a
symbol-translation problem. Pass 4 re-confirmed the same echo on a clean 78-bar response, and BRK-B is now
eligible along with the rest of the universe.

### Data handling for Pass 3

Raw bars (79 rows × 2 tickers) were written **only** to the session scratchpad outside this repository and were not
committed. What is committed is the two sanitized harness reports
(`GST_MARKET_RESPONSE_LIVE_DIAGNOSTIC_SPY_2026-08-03.json`, `..._BRK-B_2026-08-03.json`): check names, pass/fail,
aggregate values, statuses, provenance and content hashes only -- no bar rows, no credentials. A byte-level scan of
all 3,605 tracked and untracked files in the worktree found zero occurrences of either credential.

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
