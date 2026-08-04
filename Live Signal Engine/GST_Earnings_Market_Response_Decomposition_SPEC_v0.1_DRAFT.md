# Earnings Market-Response Decomposition — SPEC v0.1 (DRAFT, LOCKED SCOPE)

**Status: locked draft, not yet implemented as of this document's creation. This document is written before the code that implements it, and the implementation must not silently diverge from it.**

**Branch:** `phase2-market-response`
**Base:** `origin/phase2-wikipedia-reliability` @ `b400af239d89b313f7705e941ddfa7b4c2beb76b` (this is a **stacked branch** — it depends on PR #1 (`phase2-wikipedia-reliability` → its own base) and must be reviewed/merged only after PR #1, never independently ahead of it).

---

## 1. Purpose

**This is a measurement module, not a trading strategy.**

It determines *where and when* earnings-related market movement occurs, relative to a pre-event public-attention observation (GST z-score, Wikipedia z-score). It decomposes the market's reaction into named time intervals (overnight gap, first 30 minutes, rest of session, subsequent days) so that a later, separately-specified and separately-pre-registered research program can ask *whether* attention is associated with *where* movement concentrates.

This module does not:
- Test, optimize, select, or report a trading strategy.
- Compute or imply profitability, expected return, or edge of any kind.
- Choose winners between overnight/open/intraday/multi-day windows. It records all of them, undifferentiated in status, and leaves interpretation to later, explicitly-scoped research work.

Everything this module produces is raw or mechanically-derived observational data. No field in this module's schema represents a trading decision, a P&L outcome, or a ranked/scored opportunity.

---

## 2. Locked universe

Reused **verbatim, unchanged**, from `GST_Phase2_DailyPanel.py:229-233` (module-level `TICKERS` constant), which is itself the same universe mirrored in the Event Dossier Protocol's `locked_universe_v0.1.json`:

```
AAPL, ABBV, ADBE, AMZN, BKR, BRK-B, CTSH, DELL, DVN, GME,
GOOGL, GPN, INTC, LDOS, MSFT, NCLH, NKE, QCOM, SBUX, STZ,
SYK, TSLA, TTWO, UAL
```

No additions, no exclusions, no dynamic liquidity filtering. This module has no code path that can add or remove a ticker from this list — the list is imported/copied as a constant, not recomputed.

---

## 3. Event identity

### 3.1 `event_id` format

Reused from the Event Dossier Protocol (`Event_Dossier_Protocol/validator/validate_event_dossier.py:58`), unchanged:

```
EVT-{TICKER}-FY{yy}Q{n}-{EVENT_TYPE}
```

e.g. `EVT-MSFT-FY26Q4-ERN`. `EVENT_TYPE` is `ERN` only in v0.1 scope (matches the protocol's own v0.1 scope). This lets a market-response record for a given earnings event join directly to that event's Event Dossier record on `event_id`, without inventing a parallel ID scheme.

### 3.2 Required event-identity fields

Every registered event carries:

| Field | Type | Notes |
|---|---|---|
| `event_id` | string | `EVT-{TICKER}-FY{yy}Q{n}-ERN`, regex-validated |
| `ticker` | string | Must be a member of the locked 24-ticker universe |
| `company` | string | Manually curated (no reliable programmatic company-name source exists in this codebase — see §Reused Components) |
| `fiscal_period` | string | `FYyyQn` format |
| `earnings_date` | date (ISO 8601) | Calendar date of the release |
| `earnings_datetime_utc` | datetime (ISO 8601, UTC) | Best-known timestamp of the release, when available; null if only the date is known |
| `release_market_session` | enum: `BMO` \| `AMC` \| `INTRADAY` | See §3.3 |
| `event_time_source` | string | Where the timing claim came from (e.g. `"yfinance get_earnings_dates"`, `"company IR press release"`, `"manually verified"`) |
| `event_time_retrieved_at_utc` | datetime (ISO 8601, UTC) | When the timing claim was retrieved/verified |
| `expected_next_full_trading_session` | date (ISO 8601) | The trading session this module treats as "D1" — see §9 state machine and the Event Dossier Protocol's D1/D5 day-count rule (`EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md` §3): BMO → same session is D1; AMC or a release landing on a weekend/holiday → the next open session is D1; INTRADAY → the *next* full session is D1 (the interrupted current session is excluded from D1). |

### 3.3 BMO/AMC/INTRADAY determination — fail closed

**`release_market_session` must never be inferred from price movement, volume, or any post-hoc market behavior.** It is only ever set from an explicit timing source (a calendar API's own before/after-market flag, an IR press release timestamp, or manual verification against the company's own release).

If `release_market_session` cannot be determined from a genuine timing source, the event's `event_state` (§9) must be set to `ABSTAIN_DATA_QUALITY` and `expected_next_full_trading_session` must be left null. **No default value, no majority-class guess, and no "infer from whether price gapped" logic exists anywhere in this module.** An event that fails this gate produces no pre-event snapshot, no market-response intervals, and no option benchmark — it stops at registration.

---

## 4. Pre-event snapshot

Captured at a single, **locked, documented pre-event time** — the most recent daily close strictly before `earnings_date` (or before the release timestamp, for INTRADAY events where the release lands mid-session; in that case the pre-event snapshot is still anchored to the prior session's close, never to an intraday price after the session has begun moving on same-day rumor/news). The exact anchor timestamp used is itself recorded (`pre_event_snapshot_asof_utc`), not just implied by convention.

| Field | Type | Notes |
|---|---|---|
| `gst_zscore` | float, nullable | Existing GST z-score methodology, **unchanged** (`GST_Live_Signal_Engine.py:390-420` formula, `ROLLING_WINDOW=12`, `MIN_PERIODS=8`, `STD_EPSILON_FLOOR=1.0`) |
| `gst_level` | float, nullable | The raw (non-standardized) GST value feeding the z-score computation |
| `gst_slope` | float, nullable | **New, development-only feature — see §4.1. Not part of the existing GST methodology.** |
| `gst_persistence` | float, nullable | **New, development-only feature — see §4.1. Not part of the existing GST methodology.** |
| `wiki_zscore` | float, nullable | Existing Wikipedia z-score methodology, **unchanged** |
| `previous_close` | float, nullable | Prior session's closing price |
| `realized_volatility` | float, nullable | Trailing realized vol, same convention as the existing six-field contract's `realized_vol` |
| `days_to_earnings` | int, nullable | Signed; matches the existing panel's `days_to_nearest_earnings` convention |
| `pre_event_snapshot_asof_utc` | datetime, nullable | The exact timestamp this snapshot is anchored to |
| `source_status_gst` | enum: `ok` \| `partial` \| `missing` \| `error` | |
| `source_status_wiki` | enum: `ok` \| `partial` \| `missing` \| `error` | |
| `source_status_price` | enum: `ok` \| `partial` \| `missing` \| `error` | |
| `retrieved_at_utc_gst` | datetime, nullable | |
| `retrieved_at_utc_wiki` | datetime, nullable | |
| `retrieved_at_utc_price` | datetime, nullable | |

**The existing GST formula is not modified anywhere in this module.** `gst_zscore` is either pulled from the existing panel/cache verbatim or recomputed with the exact same formula and constants — never a variant formula.

### 4.1 `gst_slope` and `gst_persistence` — versioned, development-only definitions

No locked definition for either exists anywhere in the codebase (confirmed by repo-wide search — see Preflight report). This spec defines development versions, explicitly versioned separately from the core GST methodology so a future change to either does not require touching the core z-score formula or its existing consumers:

- **`gst_slope_v0.1`**: the signed slope (least-squares fit, or simple first-difference — implementation picks one and documents which; see field dictionary) of the raw GST level over the trailing `ROLLING_WINDOW` (12) observations ending at the pre-event snapshot. Units: GST-level-per-observation-period. A rising, elevated GST level produces positive slope; a decaying spike produces negative slope even if the current z-score is still high.
- **`gst_persistence_v0.1`**: the count (or fraction — implementation picks one and documents which) of the trailing `ROLLING_WINDOW` (12) observations for which the raw GST z-score exceeded a documented threshold (reusing `Z_THRESHOLD=2.0` from `GST_Live_Signal_Engine.py`), i.e. how many recent periods were already "elevated" going into this event, distinguishing a single-period spike from a sustained elevation.

Both are labeled `_v0.1` in the field dictionary and schema comments specifically so that if either definition changes later, old records remain interpretable under their original definition rather than silently reinterpreted.

---

## 5. Earnings-specific option benchmark

**This is deliberately not the Phase 2 panel's generic nearest-expiry-after-today IV field.** The Phase 2 panel's `implied_volatility` (via `get_option_snapshot()` + `get_nearest_post_earnings_expiry(tk, today)`) answers "what's the IV right now," reusing "nearest expiry after today" as a free special case. This module needs "what did the market think the earnings move would cost, priced off an expiry that actually spans the event" — a different question, anchored at the **verified earnings event date**, not at today.

### 5.1 Expiration selection

Reuses `get_nearest_post_earnings_expiry(tk, anchor_date)` from `GST_MultiTicker_Forward_Log.py:86` **called with the verified `earnings_date`, not today's date** — the function is already generically parameterized ("nearest expiry strictly after X"); only the anchor argument changes. Expirations on or before the earnings date are rejected outright (see Testing §17).

### 5.2 Quote capture, at a single locked quote timestamp

| Field | Type | Notes |
|---|---|---|
| `underlying_price` | float, nullable | Spot at the quote timestamp |
| `expiration` | date, nullable | Selected per §5.1 |
| `atm_strike_selection_rule` | string | Fixed, documented rule (e.g. "strike minimizing \|strike − spot\|", matching the existing `get_option_snapshot()` convention) |
| `call_bid` / `call_ask` / `call_mid` | float, nullable | `call_mid = (call_bid + call_ask) / 2` only when both are present and positive; never backfilled from `lastPrice` in this module (unlike `mid_price()`'s fallback in `GST_Live_Straddle_Logger.py`, which this module does **not** reuse for that reason) |
| `put_bid` / `put_ask` / `put_mid` | float, nullable | Same rule |
| `quote_timestamp_utc` | datetime, nullable | |
| `open_interest_call` / `open_interest_put` | int, nullable | Optional liquidity fields — see §10 completeness policy |
| `volume_call` / `volume_put` | int, nullable | Optional liquidity fields |
| `straddle_bid` | float, nullable | `call_bid + put_bid` |
| `straddle_ask` | float, nullable | `call_ask + put_ask` |
| `straddle_mid` | float, nullable | `call_mid + put_mid` |
| `midpoint_implied_move` | float, nullable | `straddle_mid / underlying_price` |
| `long_executable_implied_move_cost` | float, nullable | `straddle_ask / underlying_price` — **the cost a real buyer would actually pay, never conflated with the midpoint figure** |
| `short_executable_proceeds_proxy` | float, nullable | `straddle_bid / underlying_price` |
| `contract_selection_status` | enum: `ok` \| `partial` \| `missing` \| `rejected_expiry_not_after_event` \| `rejected_bid_gt_ask` \| `rejected_incompatible_timestamps` | |
| `data_quality_status` | enum: `ok` \| `partial` \| `missing` \| `error` | |

**Hard rules, mechanically enforced (see Testing §16–18):**
- An expiration on or before the verified `earnings_date` is rejected — the record's `contract_selection_status` becomes `rejected_expiry_not_after_event`, not silently substituted with the next-best expiry.
- `bid > ask` on either leg is rejected (`rejected_bid_gt_ask`); no field is populated from a crossed quote.
- Call and put legs (or either leg vs. `underlying_price`) retrieved at *materially different* timestamps (threshold documented in the field dictionary) are either rejected (`rejected_incompatible_timestamps`) or explicitly flagged unusable — never silently combined into one "as of" quote.
- `midpoint_implied_move` is never substituted for `long_executable_implied_move_cost` or vice versa anywhere downstream. They are computed and stored as distinct fields specifically so a later consumer cannot mistake a theoretical midpoint for a real cost.

**Full option-chain snapshots (all strikes) are out of scope for v0.1** — `get_option_snapshot()`, reused here, captures only the single ATM strike per side, consistent with its existing behavior across the codebase. This is documented as a known limitation, not silently worked around.

---

## 6. Market-response intervals

All intervals are computed from OHLCV bars only — never estimated, interpolated, or backfilled from a coarser bar. Every formula below is fixed in this spec; **none of the thresholds or windows here are optimized, fit, or backtested** — they are structural definitions of "where did the move happen," not a trading rule.

| Field | Formula |
|---|---|
| `overnight_gap` | `next_session_open / previous_close - 1` |
| `open_to_30m` | `price_at_30m / session_open - 1` |
| `thirty_min_to_close` | `session_close / price_at_30m - 1` |
| `open_to_close` | `session_close / session_open - 1` |
| `close_T1_to_close_T2` | `close(T2) / close(T1) - 1` |
| `close_T1_to_close_T3` | `close(T3) / close(T1) - 1` |
| `full_session_range` | `(session_high - session_low) / session_open` |
| `first_30m_volume` | Sum of bar volume from session open through the 30-minute boundary bar, inclusive |
| `full_session_volume` | Sum of bar volume for the full regular session |
| `first_30m_volume_share` | `first_30m_volume / full_session_volume` |
| `abs_overnight_gap`, `abs_open_to_30m`, `abs_thirty_min_to_close`, `abs_open_to_close`, `abs_close_T1_to_close_T2`, `abs_close_T1_to_close_T3` | `abs()` of the corresponding signed return, stored alongside it (never replacing it) |

### 6.1 Bar boundary, timezone, and calendar treatment

- **Timezone**: all intraday bars are captured and stored in **exchange-local time (America/New_York)** for boundary logic (session open/close, 30-minute mark), then the record's own timestamp fields are stored in UTC. The 30-minute boundary is the bar whose interval covers `09:30–10:00 America/New_York` inclusive of `09:30`, using 5-minute bars per §8 (i.e., the 6th 5-minute bar after open).
- **Market calendar**: NYSE/Nasdaq regular sessions only. `T1`/`T2`/`T3` in the multi-day fields are **trading sessions**, not calendar days — a Friday `T1` has its `T2` on the following Monday (or later, across a holiday).
- **Missing-bar behavior**: if the specific boundary bar required by a formula (session open, the 30-minute bar, session close) is missing from the raw bar set, that formula's output is `null` and the event's applicable state-machine gate fails closed (§9, §10) — it is never estimated from adjacent bars.
- **Half-day handling**: on a documented early-close session (e.g., day after Thanksgiving, July 3rd when applicable), `session_close` is the actual early-close bar and `full_session_volume`/`full_session_range` are computed over the shortened session as-is; the record carries no separate "half day" flag in v0.1 beyond what the raw bar timestamps themselves already show, but the field dictionary documents that half-day sessions are not normalized/annualized to a full session.

---

## 7. Relative-return controls

### 7.1 Locked ticker-to-sector-ETF mapping (new — nothing existed to reuse)

A versioned mapping file, `Live Signal Engine/GST_Sector_ETF_Mapping_v0.1.json`, assigns each of the 24 locked tickers to one sector ETF (GICS-sector-consistent, e.g. `XLK`, `XLV`, `XLE`, `XLY`, `XLP`, `XLI`, `XLF`, `XLU`, `XLB`, `XLRE`, `XLC`). The mapping is locked at v0.1 and versioned — a later change requires a new version, not an in-place edit, consistent with the append-only philosophy of the rest of this module.

### 7.2 Computed fields, per matching interval

For each interval in §6 that has a defined return (`overnight_gap`, `open_to_30m`, `thirty_min_to_close`, `open_to_close`, `close_T1_to_close_T2`, `close_T1_to_close_T3`), the same formula is computed for:
- the stock
- its mapped sector ETF
- `SPY`

and stored as parallel fields (e.g. `open_to_close_stock`, `open_to_close_sector_etf`, `open_to_close_spy`), plus:

- `{interval}_minus_sector` = stock return − sector ETF return
- `{interval}_minus_spy` = stock return − SPY return

**These difference fields are never labeled "abnormal return" or "alpha" anywhere in this module's schema, code, or documentation.** That terminology is reserved for a separately-specified statistical model (with its own assumptions about expected return) that does not exist in v0.1. Calling a raw arithmetic difference "abnormal" without such a model would overstate what's actually being measured.

---

## 8. Raw observations

Raw 5-minute OHLCV bars are captured and stored for the stock, its mapped sector ETF, and SPY, for the trading-session window each event needs (pre-event session through D3, per the event's actual required window — see §9/§10).

- **Storage separation**: raw bars live in their own immutable files (`raw_bars/{event_id}/{symbol}_{session_date}.csv`), physically separate from the derived event-level record (§4–§7 fields). A derived-field file never embeds raw bar rows; it only references the raw file's path and hash.
- **Provenance**: every raw bar file has a `SHA-256` hash recorded in a manifest at write time (`raw_bars/{event_id}/MANIFEST.json`) and a `retrieval_provenance` block: `{source, retrieved_at_utc, symbol, session_date, bar_interval}`.
- **Immutability**: once written, a raw bar file is never edited or overwritten. A correction produces a new, separately-named file plus an amendment record (§9) — the original file and its hash remain on disk and referenced.

---

## 9. State machine

Append-only, forward-only event states:

```
REGISTERED
    → PRE_EVENT_PENDING
    → PRE_EVENT_CAPTURED
    → D1_PENDING
    → D1_COMPLETE
    → D3_PENDING
    → COMPLETE

(any state) → PARTIAL
(any state) → ABSTAIN_DATA_QUALITY
```

- **`REGISTERED`**: event identity (§3) recorded and validated. Nothing else captured yet.
- **`PRE_EVENT_PENDING`**: registered, pre-event snapshot capture attempted but not yet resolved.
- **`PRE_EVENT_CAPTURED`**: §4 pre-event snapshot and §5 option benchmark both resolved to at least the "valid pre-event observation" / "valid option benchmark" completeness bar (§10).
- **`D1_PENDING`**: D1 session has not yet closed, or its capture is in flight.
- **`D1_COMPLETE`**: §6/§7 D1-relevant intervals (`overnight_gap`, `open_to_30m`, `thirty_min_to_close`, `open_to_close`, plus their sector/SPY-relative fields) meet the "valid D1 decomposition" completeness bar (§10).
- **`D3_PENDING`**: awaiting T2/T3 closes.
- **`COMPLETE`**: `close_T1_to_close_T2` and `close_T1_to_close_T3` (plus relative-return fields) meet the "valid D3 completion" completeness bar (§10).
- **`PARTIAL`**: reachable from any state when a required gate for the *current* stage fails but earlier stages remain valid — e.g., D1 captured cleanly but the D3 sector ETF feed came back missing. A `PARTIAL` record is never silently promoted to `COMPLETE` later by overwriting; see §10 and Testing §12.
- **`ABSTAIN_DATA_QUALITY`**: reachable from any state (most commonly from `REGISTERED`, per §3.3) when a required gate cannot be resolved at all (e.g., event timing can't be verified). An `ABSTAIN_DATA_QUALITY` event carries no derived fields beyond whatever was validated before the abstain.

**An event never moves backward.** `COMPLETE` never reverts to `D1_COMPLETE`; `PARTIAL` does not un-become `PARTIAL` by silently filling the gap in the same record. **Corrections are amendment records** — a new, separately-timestamped record referencing the original `event_id` and the specific field(s) corrected, with the original observation preserved on disk, unedited (see Testing §14).

---

## 10. Completeness policy

**Missing data is `null`, never `0`, anywhere in this module's schema — this is mechanically enforced, not a convention left to implementers.** A `null` field means "not observed"; a `0` field means "observed and the value was zero." No derivation function in this module is allowed to coalesce a missing input into a zero output.

### 10.1 Required fields per validity tier

- **Valid pre-event observation** requires (non-null): `gst_zscore` OR explicit `source_status_gst = missing/error` recorded (i.e., the tier is satisfied by an honest missing-status, not by a silently-guessed value), `previous_close`, `pre_event_snapshot_asof_utc`. `gst_slope`/`gst_persistence` are **not** required for this tier (development-only features, §4.1) — their absence does not block `PRE_EVENT_CAPTURED`.
- **Valid option benchmark** requires: `expiration` (post-event, per §5.1), `underlying_price`, `quote_timestamp_utc`, and at least one of (`straddle_mid`, `long_executable_implied_move_cost`) non-null with `contract_selection_status = ok`.
- **Valid D1 decomposition** requires: `overnight_gap`, `open_to_30m`, `thirty_min_to_close`, `open_to_close` all non-null, each backed by a present session-open, 30-minute-boundary, and session-close bar (§6.1).
- **Valid D3 completion** requires: `close_T1_to_close_T2` and `close_T1_to_close_T3` non-null, each backed by present T1/T2/T3 session-close bars.

### 10.2 Optional vs. required fields are explicitly distinguished

A missing **optional** field (`open_interest_call`, `volume_call`, `open_interest_put`, `volume_put` — liquidity context, not required for a valid option benchmark) **must not** be treated the same as a missing **required** price bar. The completeness gate checks only the required-field list for its tier; optional-field absence is recorded in `source_status`/`data_quality_status` but never blocks a state transition. Every such decision — which fields are required per tier, which are optional — is enumerated explicitly in the field dictionary (deliverable, §Documentation) so it is mechanically testable rather than left to implicit judgment in code.

---

## Reused components (summary — see Preflight report for full detail)

| Capability | Reused from | Caveat |
|---|---|---|
| Earnings-date lookup | `fetch_next_earnings_date()` (`GST_MultiTicker_Forward_Log.py:145`) / `fetch_earnings_dates()` (`GST_Build_Foundation_AllTickers.py:61`) | Both are forward-looking only; this module's "as-of" filtering for point-in-time correctness is new code, not reused |
| Option-expiration selection | `get_nearest_post_earnings_expiry(tk, anchor_date)` (`GST_MultiTicker_Forward_Log.py:86`) | Reused with `earnings_date` as the anchor instead of today; `pick_expiration()` in `GST_Live_Straddle_Logger.py` is explicitly **not** reused (different, DTE-floor-based semantics) |
| Option-chain ATM quote | `get_option_snapshot()` (`GST_MultiTicker_Forward_Log.py:97`) | ATM-only, not full chain; no mid-price field — `call_mid`/`put_mid`/straddle fields are new computation in this module, without the `lastPrice`-fallback behavior of `mid_price()` in `GST_Live_Straddle_Logger.py` |
| Daily price history | `tk.history()` pattern (`GST_Phase2_DailyPanel.py`) | Daily-bar pattern only; intraday 5-minute bars are new — nothing in the repo currently pulls intraday bars |
| GST z-score | `compute_latest_zscore()` / `compute_zscore_at_anchor()` | **Unchanged**, formula and constants reused exactly |
| 24-ticker universe | `GST_Phase2_DailyPanel.py:229-233` | **Unchanged** |
| `event_id` scheme | `Event_Dossier_Protocol/validator/validate_event_dossier.py` | Reused exactly so records join to the Event Dossier Protocol without a parallel ID scheme |
| Sector-ETF mapping | none existed | New in this module, versioned and locked |
| `gst_slope` / `gst_persistence` | none existed | New, development-only, versioned separately from core GST methodology |
| Intraday OHLCV retrieval | none existed | New provider interface, see implementation |
| BMO/AMC/D1 day-count rule | Event Dossier Protocol §3 (written rule, no existing implementation) | New code implementing an existing written spec |

---

## Operational-readiness addendum (2026-08-04)

This addendum documents the operational-readiness pass that implemented the pieces needed to eventually register a
real event, WITHOUT registering one and without changing any locked definition above. Nothing in sections 1-10
above was modified by this pass.

- **`gst_market_response/event_registry.py`** implements `HumanVerifiedEventRegistryProvider` (via
  `RegistryBackedEventTimingProvider`, adapting `HumanVerifiedEventRegistry` to the `EventTimingProvider` interface
  from section "Reused components"). It does NOT scrape or infer timing -- every row requires a human-supplied
  primary source (`source_url`/`source_title`/`source_type`/`verified_by`). `to_event_identity()` raises unless
  `verification_status == "verified"`, which is the mechanical enforcement of "a date without verified release
  timing cannot reach REGISTERED." `expected_response_session` is never accepted as an input parameter -- it is
  always computed from `compute_expected_next_full_trading_session()` (unchanged, section 3.3/9). Corrections are
  `AMENDMENT` rows (`amend_event()`), never in-place edits -- same append-only discipline as section 9's event
  state machine.
- **`gst_market_response/phase2_adapter.py`** implements the narrow, explicit-path-only Phase 2 pre-event import
  described in this addendum's TASK 2. It never discovers "the latest file," hashes both inputs, cross-verifies the
  completion marker's claimed counts against the CSV's actual content (rejecting on any mismatch), and never reads
  the panel's `implied_volatility` column into anything resembling `earnings_implied_move` (see section 5's own
  "Never substitute midpoint for executable cost" rule -- this is the same discipline applied to a different
  import path).
- **`gst_market_response/sector_mapping.py`** gained `validate_sector_mapping()` and
  `assert_usable_for_real_event()`. `GST_Sector_ETF_Mapping_v0.1.json` now carries `review_status` (currently
  `DRAFT`), `reviewed_by`, `reviewed_at_utc`, and per-ticker `sector` names alongside `sector_etf`. A DRAFT mapping
  remains usable in deterministic fixtures but `assert_usable_for_real_event(is_demo=False)` raises for it -- a
  real event cannot reach `COMPLETE` on an unapproved mapping.
- **One bounded live diagnostic** of `YFinanceDevIntradayProvider` was performed against SPY (not a member of the
  locked 24-ticker universe, no earnings date -- structurally not a research event) for the 2026-08-03 regular
  session. **Result: FAILED** -- the provider returned zero bars. See
  `GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md` for the full result and root-cause investigation. No
  workaround was applied and no substitute provider was used, per instruction.
- **`gst_market_response/event_record.py`**'s amendment semantics (section 9) were further tested (not changed) to
  prove a `PARTIAL` record's later recovery is recorded as a distinct, linked `AMENDMENT` -- never a mutation of
  the original -- and that an amendment "counts" toward a completeness tier only if it is independently checked
  against that tier's gate, never merely by virtue of being an amendment.

**No real event has been registered.** `HumanVerifiedEventRegistry` in every test and in this pass's actual usage
starts empty; nothing populates a real upcoming ticker/date.

## Operational-data addendum (2026-08-04, second pass)

This addendum documents replacing the development-only building blocks from the first operational-readiness pass
with operationally-eligible ones, still without registering a real event. Nothing in sections 1-10 above changed.

- **`gst_market_response/alpaca_provider.py`** implements `AlpacaHistoricalSipIntradayProvider`, calling Alpaca's
  documented `GET /v2/stocks/{symbol}/bars` endpoint directly (`timeframe=5Min`, `feed=sip`, `adjustment=raw`,
  `sort=asc`, bounded pagination via `next_page_token`). Credentials come only from `APCA_API_KEY_ID`/
  `APCA_API_SECRET_KEY`; 401/403 fail immediately (never retried); 429/5xx retry up to `MAX_ATTEMPTS=5` honoring
  `Retry-After` (capped at `MAX_RETRY_AFTER_S=30`); a `MAX_WALL_CLOCK_S=60` budget and `MAX_PAGES=20` bound the
  whole call. **Never falls back to IEX, yfinance, an undocumented endpoint, another vendor, or synthetic bars** --
  a failure is `AlpacaProviderError` (or a subclass), full stop. Requires the requested session's close to be at
  least `MIN_END_AGE_MINUTES=15` old before making any request (checked before the HTTP call, not after).
  `is_eligible_for_real_event = True`, versus `YFinanceDevIntradayProvider.is_eligible_for_real_event = False`
  (explicit, unchanged from the first pass). Canonical-to-provider symbol translation
  (`CANONICAL_TO_ALPACA_SYMBOL`) maps `BRK-B -> BRK.B`; both identifiers are always recorded in
  `AlpacaProvenance.canonical_ticker`/`provider_symbol`. **This mapping is not yet live-verified** (no credentials
  were available in this pass) -- see `GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md`.
- **`gst_market_response/exchange_calendar.py`** replaces the hand-maintained partial holiday list
  (`event_registry.is_trading_day_v0_1`/`_SUPERSEDED_*`, kept only for auditability, no longer used as any
  function's default) with the `exchange_calendars` package's real XNYS calendar. `is_trading_day()`,
  `previous_session()`/`next_session()`, `session_open_utc()`/`session_close_utc()`, `is_early_close()`, and
  `expected_bar_boundaries()` (which correctly shrinks the expected 5-minute-bar count on an early-close session,
  e.g. 42 bars instead of 78 on the day after Thanksgiving) are all derived from it. `event_registry.py`'s
  `register_verified_event()`/`amend_event()` now default to this calendar; `EXCHANGE_CALENDAR_ID` recorded in new
  registry rows is `XNYS_exchange_calendars_v4.13.2`.
- **`gst_market_response/bars.py`** gained `validate_ohlc_and_volume()` (raises `InvalidOHLCError`/
  `NegativeVolumeError`) -- a single shared check used by both the yfinance and Alpaca diagnostics rather than each
  reimplementing its own tolerance.
- **`GST_Sector_ETF_Mapping_v0.1.json`** (`mapping_version` bumped 0.1 -> 0.2) was individually reviewed against
  each candidate sector ETF's actual current holdings (or GICS sector classification where fund-holdings data was
  incomplete). **GPN corrected from XLK to XLF** -- confirmed absent from XLK's holdings and present in XLF's
  (0.24% weight), consistent with the 2023 GICS reclassification of payment processors into Financials. **GME's
  fund-constituency in XLY could not be confirmed** and is left visibly documented as an open question (GICS
  sector itself is confirmed Consumer Discretionary, the same rule used for every other ticker). `review_status`
  promoted to `APPROVED` on this basis -- every one of the 24 entries carries its own sourced or documented-rule
  `review` block; see the file itself and `GST_MARKET_RESPONSE_OPERATIONAL_READINESS_CHECKLIST_v0.1.md`.
- **`requirements.txt`** (new) pins `exchange_calendars==4.13.2` and documents (without pinning the rest of this
  research repository's dependencies, out of scope) `requests`, `yfinance`, `pandas` for `gst_market_response/`.
- **Phase 2 adapter dry run**: `import_pre_event_fields_for_ticker()` was run read-only against a real preserved
  panel run (`GST_Phase2_DailyPanel_TestRun_2026-07-30_run3.csv` + its `COMPLETION_MARKER.json`, from the
  `phase2-wikipedia-reliability` worktree) -- 24/24 tickers imported cleanly, `panel_status="COMPLETE"` preserved
  exactly, all 24 rows eligible for `PRE_EVENT_CAPTURED`, both input files verified byte-identical before and
  after. **The adapter is confirmed operationally compatible with a real Phase 2 panel run.**
- **No live Alpaca diagnostic was run.** `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` were absent from the environment
  at preflight -- per instruction, the pass stopped before any live Alpaca call. `alpaca_intraday_diagnostic.py`
  (the harness for when credentials become available) was written and its imports verified, but never executed.

**Still true**: no real event has been registered. No trading strategy is selected. No profitability claim exists.

## Explicitly out of scope for v0.1

- Real-time news sentiment
- Peer/cross-company spillover effects
- Order-book imbalance
- Spread forecasting
- Any trading rule, strategy selection, backtest, or P&L computation
- Full option-chain (all-strikes) capture
- Radar/frontend integration
- Live event registration or any live network call (this spec and its implementation are validated with synthetic fixtures only in v0.1)

Extension points for the above are documented in the field dictionary but not implemented.
