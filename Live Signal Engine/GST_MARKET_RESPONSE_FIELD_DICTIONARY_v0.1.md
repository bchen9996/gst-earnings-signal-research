# GST Market Response Field Dictionary — v0.1

Companion to `GST_Earnings_Market_Response_Decomposition_SPEC_v0.1_DRAFT.md` and the implementation in
`gst_market_response/`. This document is the authoritative field-by-field reference for anyone consuming this
module's output.

**Read this before reading anything else here:**

- **Historical GST association is retrospective.** Every existing finding this project has produced about GST
  z-scores and market behavior comes from looking backward at data that already happened. Nothing in this module
  changes that.
- **Prospective predictive value remains under collection.** This module exists to start collecting genuinely
  forward, point-in-time-clean observations. Whether attention data predicts anything is an open question this
  module does not answer — it only measures.
- **This module does not establish profitability.** No field here is a return net of costs against a
  pre-committed strategy. `long_executable_implied_move_cost` and `short_executable_proceeds_proxy` are honestly-
  labeled option-market prices, not a claim that trading against them would be profitable.
- **Options are a benchmark, not the only future instrument.** The option-chain fields in this module exist to
  give the pre-event attention snapshot a market-implied-move yardstick. They are not a statement that options are
  the intended or best instrument for any future strategy work.
- **No equity, opening-range, gap, pair, or risk strategy is selected in v0.1.** This module records where returns
  land across named intervals. It does not rank, score, or recommend any of them.
- **Strategy selection may occur only after the first development earnings cycle is complete.** Not before, and
  not as an implicit byproduct of this module's field names or ordering.

---

## Event identity fields

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `event_id` | string | no | `EVT-{TICKER}-FY{yy}Q{n}-ERN`. Joins to the Event Dossier Protocol's `events.csv` on this exact key. |
| `ticker` | string | no | Must be a member of the locked 24-ticker universe (`gst_market_response.constants.LOCKED_24_TICKER_UNIVERSE`). |
| `company` | string | no | Manually curated — no reliable programmatic company-name source exists in this codebase. |
| `fiscal_period` | string | no | `FYyyQn`. |
| `earnings_date` | date | no | Calendar date of the release. |
| `earnings_datetime_utc` | datetime | yes | Best-known release timestamp. Null if only the date is confirmed. |
| `release_market_session` | enum | no | `BMO` \| `AMC` \| `INTRADAY`. **Never inferred from price/volume** — see `identity.determine_release_market_session()`, which raises rather than defaults if unverifiable. |
| `event_time_source` | string | no | Where the timing claim came from. |
| `event_time_retrieved_at_utc` | datetime | no | |
| `expected_next_full_trading_session` | date | no | The D1 session, per `identity.compute_expected_next_full_trading_session()` — BMO same-day if a trading day, else next trading day; AMC/INTRADAY always the next trading day. |

## Pre-event snapshot fields

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `gst_zscore` | float | yes | Existing GST z-score methodology, **unchanged**. |
| `gst_level` | float | yes | Raw GST value feeding the z-score. |
| `gst_slope_v0.1` | float | yes | **Development-only, versioned separately from core GST methodology.** Mean of consecutive first-differences of the raw GST level over the trailing 12-observation window (`derivations.gst_slope_v0_1`). Requires ≥2 non-null trailing observations; otherwise null — never estimated from 0 or 1 points. |
| `gst_persistence_v0.1` | float | yes | **Development-only, versioned separately.** Fraction of the trailing 12 z-scores at/above `GST_Z_THRESHOLD=2.0` (`derivations.gst_persistence_v0_1`). Requires ≥1 non-null observation. |
| `wiki_zscore` | float | yes | Existing Wikipedia z-score methodology, unchanged. |
| `previous_close` | float | yes | Required for the "valid pre-event observation" completeness tier. |
| `realized_volatility` | float | yes | Trailing realized vol, same convention as the six-field contract's `realized_vol`. |
| `days_to_earnings` | int | yes | Signed. |
| `pre_event_snapshot_asof_utc` | datetime | yes | Required for the "valid pre-event observation" tier. |
| `source_status_gst` / `_wiki` / `_price` | enum | no | `ok` \| `partial` \| `missing` \| `error`. |
| `retrieved_at_utc_gst` / `_wiki` / `_price` | datetime | yes | |

## Option benchmark fields (`gst_market_response.option_chain_adapter.OptionBenchmark`)

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `underlying_price` | float | yes | Spot at quote time. |
| `expiration` | date | yes | Nearest listed expiry **strictly after** `earnings_date` — never on/before. Two independent enforcement layers: the reused selector's own `>` filter, plus `build_option_benchmark()`'s own belt-and-suspenders check (see test 16b). |
| `atm_strike_selection_rule` | string | no | Fixed text describing the rule (min absolute distance to spot). |
| `call_bid`, `call_ask`, `call_mid` | float | yes | `call_mid` only computed when both bid and ask are present and positive — never backfilled from `lastPrice`. |
| `put_bid`, `put_ask`, `put_mid` | float | yes | Same rule. |
| `quote_timestamp_utc` | datetime | yes | |
| `open_interest_call`, `open_interest_put`, `volume_call`, `volume_put` | int | yes | **Optional** liquidity fields — absence never blocks the option-benchmark completeness gate (see `completeness.OPTION_BENCHMARK_OPTIONAL_FIELDS`). |
| `straddle_bid`, `straddle_ask`, `straddle_mid` | float | yes | Sum of the corresponding call/put leg values. |
| `midpoint_implied_move` | float | yes | `straddle_mid / underlying_price`. A theoretical figure — **never substituted for an executable cost.** |
| `long_executable_implied_move_cost` | float | yes | `straddle_ask / underlying_price`. What a real buyer would actually pay. |
| `short_executable_proceeds_proxy` | float | yes | `straddle_bid / underlying_price`. |
| `contract_selection_status` | enum | no | `ok` \| `partial` \| `missing` \| `rejected_expiry_not_after_event` \| `rejected_bid_gt_ask` \| `rejected_incompatible_timestamps`. |
| `data_quality_status` | enum | no | `ok` \| `partial` \| `missing` \| `error`. |

**Compatible-timestamp threshold:** call/put quote timestamps more than `MAX_COMPATIBLE_QUOTE_SKEW_SECONDS = 120`
seconds apart are rejected (`contract_selection_status = rejected_incompatible_timestamps`) rather than combined
into one quote. This constant lives in `option_chain_adapter.py` as the single source of truth.

**This module deliberately does NOT expose a bare `implied_volatility` field or an `earnings_implied_move` alias
for the Phase 2 panel's generic nearest-expiry-after-today IV.** Test 19 in `test_market_response_decomposition.py`
mechanically enforces this — it fails if either name is ever added to `OptionBenchmark`'s schema, and it fails if
`option_chain_adapter.py` ever imports from `GST_Phase2_DailyPanel`.

## Market-response interval fields

| Field | Formula | Null behavior |
|---|---|---|
| `overnight_gap` | `next_session_open / previous_close - 1` | Null if either input is null. |
| `open_to_30m` | `price_at_30m / session_open - 1` | Null if either input is null (including a missing 09:55 ET boundary bar). |
| `thirty_min_to_close` | `session_close / price_at_30m - 1` | Same. |
| `open_to_close` | `session_close / session_open - 1` | Same. |
| `close_T1_to_close_T2`, `close_T1_to_close_T3` | `close(T_n) / close(T1) - 1` | T1/T2/T3 are **trading sessions**, not calendar days. |
| `full_session_range` | `(session_high - session_low) / session_open` | Null if any of the three is null. |
| `first_30m_volume` | Sum of volume for the 6 bars from 09:30 through 09:55 ET, inclusive | **Null (not partial-summed) if either boundary bar (09:30 or 09:55) is absent** — a partial window would understate volume and look like genuine low attention, so it fails closed instead. |
| `full_session_volume` | Sum of volume for all bars present in the session | Reflects whatever bars are actually present — including a genuinely shorter half-day session; never padded to a "normal" session length. |
| `first_30m_volume_share` | `first_30m_volume / full_session_volume` | Null if either input is null or `full_session_volume` is 0. |
| `abs_*` | `abs()` of the corresponding signed field | Stored **alongside**, never replacing, the signed value. |

**Timezone/calendar:** all boundary logic (session open, the 30-minute mark, session close) is evaluated in
America/New_York local time (`gst_market_response.bars.ET_ZONE`); stored timestamps are UTC.
**Half-day sessions are not normalized or annualized** — `full_session_volume`/`full_session_range` reflect the
actual (shorter) session as-is.

## Relative-return fields

| Field | Formula | Notes |
|---|---|---|
| `{interval}_stock`, `{interval}_sector_etf`, `{interval}_spy` | Same interval formula applied to the stock, its mapped sector ETF, and SPY | Sector ETF mapping is locked at `Live Signal Engine/GST_Sector_ETF_Mapping_v0.1.json` — a later remap requires a new versioned file. |
| `{interval}_minus_sector` | `stock_return - sector_etf_return` | Plain arithmetic difference. |
| `{interval}_minus_spy` | `stock_return - spy_return` | Plain arithmetic difference. |

**These difference fields are never called "abnormal return" or "alpha" anywhere in this module** — that
terminology implies a benchmark/expected-return model this module doesn't build. A missing sector-ETF feed leaves
the relative field `null`, and — because these fields are **optional** for the D1/D3 completeness gates — never
blocks `D1_COMPLETE`/`COMPLETE` on its own (see `test_failure_fixture_partial_sector_data`).

## Raw bar storage

Immutable per-session-per-symbol CSV files under `raw_bars/{event_id}/{symbol}_{session_date}.csv`, one
`MANIFEST.json` per event recording, per file: `sha256`, `symbol`, `session_date`, `bar_interval`, `source`,
`retrieved_at_utc`, and (for corrections) `is_amendment`/`amends_relative_path`. Files are never rewritten after
creation (`raw_bars.RawBarAlreadyExistsError` on any attempt) — a correction calls `write_amendment_bars()`, which
writes a new, separately-named file and a new manifest entry pointing back at the original.
`RawBarStore.verify()` recomputes the SHA-256 of the file currently on disk and compares it to the manifest;
a mismatch (corruption, tampering, or a missing manifest entry) returns `False`, and no derived field may be
computed from bars that fail this check.

## Event state machine

`REGISTERED → PRE_EVENT_PENDING → PRE_EVENT_CAPTURED → D1_PENDING → D1_COMPLETE → D3_PENDING → COMPLETE`, with
`PARTIAL` and `ABSTAIN_DATA_QUALITY` reachable from any non-terminal mainline state. **Implementation decision,
stricter than the letter of the spec but the simplest mechanically-enforceable reading of "PARTIAL never becomes
COMPLETE":** both `PARTIAL` and `ABSTAIN_DATA_QUALITY` are treated as fully terminal in
`gst_market_response.event_record.validate_transition()` — no further state append is accepted for an event once
either is reached, at all. This guarantees the "never becomes COMPLETE" requirement by construction rather than by
convention. Corrections to a frozen record are `AMENDMENT`-type entries (`EventStore.append_amendment()`),
referencing the amended record's sequence number; the original record's bytes on disk are never touched (writes
use append-only file mode exclusively — see `atomic_io.append_bytes_never_truncate`).

## Completeness tiers (SPEC section 10.1, mechanically enforced in `completeness.py`)

| Tier | Required fields | Notes |
|---|---|---|
| Valid pre-event observation | `previous_close`, `pre_event_snapshot_asof_utc`, plus (`gst_zscore` present OR `source_status_gst` honestly `missing`/`error`) | `gst_slope`/`gst_persistence` are NOT required — their absence never blocks this tier. |
| Valid option benchmark | `expiration`, `underlying_price`, `quote_timestamp_utc`, `contract_selection_status == 'ok'`, at least one of `straddle_mid`/`long_executable_implied_move_cost` | |
| Valid D1 decomposition | `overnight_gap`, `open_to_30m`, `thirty_min_to_close`, `open_to_close` | |
| Valid D3 completion | `close_T1_to_close_T2`, `close_T1_to_close_T3` | |

Optional fields (`open_interest_call/put`, `volume_call/put`, all `_minus_sector`/`_minus_spy` fields) are never
treated as equivalent to a missing required price bar — see `completeness.OPTION_BENCHMARK_OPTIONAL_FIELDS` and
`test_failure_fixture_partial_sector_data`.

## Human-verified event registry (operational-readiness addendum, 2026-08-04)

`gst_market_response.event_registry.HumanVerifiedEventRegistry` -- append-only, one JSONL row per registration or
amendment. Schema (`registry_version = "0.1"`):

| Field | Meaning |
|---|---|
| `event_id` | Same format as everywhere else in this module. |
| `ticker`, `fiscal_period` | |
| `earnings_date`, `earnings_datetime_utc` | Human-verified, not scraped or inferred. |
| `release_market_session` | `BMO`/`AMC`/`INTRADAY` -- must be independently confirmed; `identity.determine_release_market_session()` (reused unchanged) raises otherwise. |
| `source_url`, `source_title`, `source_type` | Primary-source citation (company IR release, exchange notice, SEC filing, etc.) -- what a human actually verified. |
| `source_retrieved_at_utc`, `verified_at_utc`, `verified_by` | |
| `verification_status` | `verified` \| `pending` \| `rejected`. **Only `verified` rows can reach `to_event_identity()` / `REGISTERED`.** |
| `expected_response_session` | **Never a manual input** -- always computed by `compute_expected_next_full_trading_session()` at write time. |
| `exchange_calendar` | `NYSE_NASDAQ_MON_FRI_PARTIAL_HOLIDAYS_V0.1` -- Mon-Fri plus a small, explicitly versioned, non-exhaustive list of documented US market holidays. **This is disclosed as a partial list, not an authoritative multi-decade NYSE calendar** -- extending it requires a new calendar-ID version, never a silent edit. |
| `registry_version`, `notes` | |
| `row_id`, `row_type` (`REGISTRATION`/`AMENDMENT`), `amends_row_id` | Append-only bookkeeping -- a correction is always a new `AMENDMENT` row; `HumanVerifiedEventRegistry` never rewrites an existing row's bytes (same `atomic_io.append_bytes_never_truncate` discipline as `event_record.py`). |

## Phase 2 pre-event adapter (operational-readiness addendum, 2026-08-04)

`gst_market_response.phase2_adapter.import_pre_event_fields_for_ticker(csv_path, marker_path, ticker,
research_commit_sha, methodology_version)` -- both paths must be given explicitly; there is no discovery of "the
latest panel run." Field mapping from the Phase 2 panel's own columns:

| Phase 2 panel column | Adapter field | Notes |
|---|---|---|
| `gst_zscore` | `gst_zscore` | |
| `wiki_zscore` | `wiki_zscore` | |
| `realized_vol` | `realized_volatility` | |
| `price` | `price` AND `previous_close` | The panel's `price` is already "last close as of retrieval" -- imported into both fields; `previous_close` is what `completeness.is_valid_pre_event_observation()` actually checks. |
| `volume` | `volume` | |
| `days_to_nearest_earnings` | `days_to_earnings` | |
| `retrieval_timestamp_utc` | `pre_event_snapshot_asof_utc`, and mirrored into `retrieved_at_utc_gst`/`_wiki`/`_price` | The panel records one retrieval timestamp per ticker row, not per leg -- this adapter mirrors that single timestamp into all three per-leg fields rather than fabricating distinct ones (disclosed here, not silently done). |
| `gst_status`/`wiki_status`/`price_history_status` | `source_status_gst`/`_wiki`/`_price` | Normalized via `_normalize_leg_status()`: panel's `"ok"` → `ok`; empty/missing → `missing`; anything else (a free-text error string) → `error`. The panel has no native "partial" per-leg status. |
| `implied_volatility` | **never imported anywhere** | See SPEC section 5 -- this field is deliberately excluded; `option_chain_adapter.py` is the only legitimate source for any implied-move-shaped field. |

Every call also verifies (`_cross_verify_marker_against_csv`) that the marker's own `row_count`,
`unique_ticker_count`, and `all_six_fields_clean_count` match what's actually in the CSV, and hashes both files
(`source_csv_sha256`, `source_marker_sha256`) -- the marker is never trusted blindly. `panel_status` (`COMPLETE` /
`PARTIAL`) is preserved exactly as the marker states it. `eligible_for_pre_event_captured` is computed via the same
`completeness.is_valid_pre_event_observation()` gate used everywhere else -- a ticker whose panel data fails that
gate is explicitly flagged ineligible, never silently passed through.

## Sector-ETF mapping review gate (operational-readiness addendum, 2026-08-04)

`gst_market_response.sector_mapping.validate_sector_mapping()` mechanically checks: exactly the locked 24 tickers
(no fewer, no extra), one `sector` name and one `sector_etf` per ticker, `sector_etf` drawn from the 11 SPDR Select
Sector ETF symbols, `mapping_version` present, and `review_status` one of `DRAFT`/`APPROVED`/`REJECTED` (with
`reviewed_by`/`reviewed_at_utc` required when `APPROVED`). `assert_usable_for_real_event(mapping, is_demo=...)`
raises `SectorMappingNotApprovedError` for any non-demo use while `review_status != "APPROVED"` -- a DRAFT mapping
may power deterministic fixtures but cannot produce a `COMPLETE` real event. **The mapping is explicitly documented,
in the JSON file's own `description` field, as a benchmark-design choice for computing a relative-return control --
not an assertion that any given sector ETF is the "correct" peer group in an alpha-generating sense.** As of this
pass, `GST_Sector_ETF_Mapping_v0.1.json` remains `review_status: "DRAFT"` -- it has not been human-reviewed.

## Development-provider diagnostic result (operational-readiness addendum, 2026-08-04)

See `GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md` for the full bounded live diagnostic of
`YFinanceDevIntradayProvider` (ticker SPY, session 2026-08-03) and its result: **FAILED** (zero bars returned).
**YFinance remains a development provider** -- this result is additional, direct evidence for that label, not a
one-off fluke to be waved away. No workaround was applied in this pass.

## Standing disclaimers (restated -- true both before and after this pass)

- **The event registry requires human-verified primary-source timing.** No event can reach `REGISTERED` on
  scraped or inferred timing.
- **No trading strategy is selected** anywhere in this module, this pass, or its documentation.
- **No profitability claim exists** for any field, benchmark, or provider in this module.
- **The first real event has not yet been registered.** `HumanVerifiedEventRegistry` contains zero rows outside of
  test fixtures as of this pass.

## Alpaca REST intraday provider (operational-data addendum, 2026-08-04)

`gst_market_response.alpaca_provider.AlpacaHistoricalSipIntradayProvider` -- the eligible (non-development)
`IntradayOHLCVProvider`. Calls `GET https://data.alpaca.markets/v2/stocks/{provider_symbol}/bars` directly (no
SDK) with `timeframe=5Min, feed=sip, adjustment=raw, sort=asc`.

| Field (`AlpacaProvenance`) | Meaning |
|---|---|
| `provider` | `"alpaca-historical-sip"` |
| `api_endpoint` | Host + path only -- never a query string, never a secret |
| `feed`, `timeframe`, `adjustment` | Echo the exact request parameters used |
| `requested_start_utc`, `requested_end_utc` | RFC-3339, from `exchange_calendar.session_open_utc`/`session_close_utc` |
| `retrieved_at_utc` | |
| `http_status` | Final response's status (200 on success) |
| `retry_count` | Count of 429/5xx/timeout retries actually taken (0 on a clean first try) |
| `page_count` | Number of pages fetched via `next_page_token` |
| `raw_response_content_sha256` | SHA-256 of the concatenated raw response bodies across all pages |
| `canonical_ticker`, `provider_symbol` | Both always recorded -- e.g. `BRK-B` / `BRK.B` |
| `request_query_string` | *(added in the live-validation pass)* The exact query string of the last request. Credentials travel in headers only, so this is safe to record and commit -- and it is the **only** first-hand evidence of what `feed`/`timeframe`/`adjustment`/window were actually requested, because Alpaca's single-symbol bars response does not echo `feed`. |
| `response_symbol_echo` | *(added in the live-validation pass)* The `symbol` Alpaca echoes in the response body. Server-side confirmation that the translated provider symbol resolved to a real tape entry -- the only first-hand check available for `BRK-B -> BRK.B`. |

**Retry/timeout policy**: `CONNECT_TIMEOUT_S=5.0`, `READ_TIMEOUT_S=15.0`, `MAX_ATTEMPTS=5` per page,
`MAX_WALL_CLOCK_S=60.0` for the whole call, `MAX_PAGES=20`. 401/403 raise `AlpacaAuthError` immediately, never
retried. 429/500/502/503/504 retry with `Retry-After` honored when present (capped at `MAX_RETRY_AFTER_S=30.0`),
else exponential backoff with jitter. Exhausting attempts or the wall-clock budget raises
`AlpacaRetryExhaustedError`. **No other failure mode causes a fallback to a different provider or synthetic
data** -- the caller receives an exception and must decide what to do, per the hard-stop list.

**Freshness gate**: `assert_end_is_stale_enough()` raises `AlpacaFreshnessGateError` if the requested session's
close is less than `MIN_END_AGE_MINUTES=15` old, checked **before** any HTTP call -- this provider only ever
requests free historical SIP data, never anything that would require a real-time entitlement.

**Symbol translation**: `CANONICAL_TO_ALPACA_SYMBOL` maps `BRK-B -> BRK.B`; every other locked-universe ticker
maps to itself. **LIVE-VERIFIED 2026-08-04** -- Alpaca returned HTTP 200 and echoed `"symbol": "BRK.B"` in the
response body, with real BRK.B tape data. No longer an assumption.

**Daily cross-check window**: `fetch_daily_bar_alpaca_sip()` requests the **calendar day** (`00:00:00Z` to
`23:59:59Z` of the session date), not the regular-session window. A 1Day bar is timestamped at midnight ET, so the
09:30-16:00 window would exclude it entirely and the absent bar would be indistinguishable from a genuine vendor
gap. It raises rather than silently picking `bars[0]` if more than one daily bar comes back, and returns `None`
only when Alpaca genuinely returns none. The two window-override parameters that make this possible are used
**only** on this 1Day path, never on the 5Min research path, and cannot bypass the exchange calendar (a
non-session date still raises `ExchangeCalendarError`).

**Secrets**: `AlpacaCredentials.__repr__`/`__str__` are redacted (`***`). Credentials travel only in HTTP headers
(`APCA-API-KEY-ID`/`APCA-API-SECRET-KEY`), never in the URL, never in `AlpacaProvenance`, never written to disk by
this module (it contains no file-write calls at all -- mechanically checked by
`test_market_response_alpaca_provider.py`).

## Authoritative XNYS exchange calendar (operational-data addendum, 2026-08-04)

`gst_market_response.exchange_calendar` wraps the `exchange_calendars` package's real XNYS calendar
(`exchange_calendars==4.13.2`, pinned in `requirements.txt`). `EXCHANGE_CALENDAR_ID = "XNYS_exchange_calendars_v4.13.2"`.
Replaces `event_registry`'s hand-maintained partial holiday list as the default for
`register_verified_event()`/`amend_event()` -- that list (`_SUPERSEDED_KNOWN_MARKET_HOLIDAYS_V0_1` etc.) remains in
the source for auditability of earlier rows only, never reintroduced as a live default.

`expected_bar_boundaries(session_date)` derives the expected 5-minute-bar grid from the calendar's own real
open/close, correctly shrinking on an early-close session (e.g. 42 bars, not 78, on the day after Thanksgiving)
rather than assuming a fixed count.

## Sector-BENCHMARK mapping v0.3 (live-validation addendum, 2026-08-04)

Supersedes the v0.2 description below. `GST_Sector_ETF_Mapping_v0.1.json` is now `schema_version: "0.2"`,
`mapping_version: "0.3"`, `review_status: "APPROVED"`.

**The rule**: each ticker is benchmarked against the broad SPDR Select Sector ETF corresponding to its **GICS
sector**. That is the entire basis of the assignment. Whether the fund actually holds the company is a separate,
independently recorded observation that never affects it. **The benchmark methodology itself is unchanged from
v0.2** -- what changed is that the file no longer describes itself in membership terms.

Each entry now carries these fields separately:

| Field | Meaning |
|---|---|
| `gics_sector` | The company's GICS sector. This, and only this, determines `benchmark_etf`. |
| `benchmark_etf` | The broad SPDR Select Sector ETF used as the sector-return benchmark. |
| `benchmark_basis` | Why that ETF was chosen. Constrained to `"gics_sector"`. `"etf_membership"` is **not** an accepted value, so membership can never silently become the justification. |
| `constituent_status` | Independent observation: `confirmed_constituent`, `confirmed_nonconstituent`, or `not_verified`. Never affects `benchmark_etf`. A `confirmed_nonconstituent` is **not** a defect. |
| `constituent_status_source` | Evidence behind `constituent_status`. |
| `classification_source` | Evidence behind `gics_sector`. |
| `retrieval_date` | ISO-8601 date both sources were retrieved. |

**`APPROVED` is mechanically conditional on all 24 having actually been reviewed.** `validate_sector_mapping()`
rejects an APPROVED mapping if any ticker lacks a `classification_source` or `retrieval_date`, or still carries
`constituent_status="not_verified"`. The same entry is perfectly acceptable while the mapping is `DRAFT` -- the
gate is on the approval claim, not on the data.

**GME is the worked example of the rule.** `gics_sector: "Consumer Discretionary"` (authoritatively confirmed by
**S&P Dow Jones Indices**, GICS co-owner, in its own index-announcement press release, corroborated by GME's
current S&P MidCap 400 constituent row), `benchmark_etf: "XLY"`, `benchmark_basis: "gics_sector"`,
`constituent_status: "confirmed_nonconstituent"`. The nonconstituency is structural, not anomalous: XLY tracks the
Consumer Discretionary Select Sector Index, whose eligible universe is the S&P 500, and GME is an S&P MidCap 400
member — ineligible for XLY by index construction. **GME is nowhere represented as an XLY holding**, and
`test_market_response_sector_mapping_gate.py` enforces that no sentence in the file affirmatively claims otherwise.
GPN remains XLF (`gics_sector: "Financials"`, per the 2023 GICS payment-processor reclassification).

**Retracted framing.** v0.2 summarised the mapping as a count of tickers verified to be holdings of their assigned
ETF, with GME flagged as an unresolved ambiguity for failing that check. That was wrong in kind, not just wording:
it treated fund membership as the thing being verified. No count of that form appears anywhere in the file now, and
a test asserts it cannot reappear.

**Source-quality caveat** (disclosed in the file itself): for the 22 tickers whose GICS sector was established via
confirmed Select-Sector-ETF membership, the membership evidence is a third-party aggregator's holdings page
(companiesmarketcap.com), not an issuer-published holdings file. The inference is sound — S&P DJI builds the Select
Sector Indices by partitioning S&P 500 members across the eleven sector indices by GICS sector, so confirmed
membership entails that sector — but the underlying observation is one source tier below ideal.

`reviewed_by` records this was a sourced desk review conducted via live web search/fetch, explicitly not a
domain-expert manual sign-off -- read literally, not as a claim of human financial-analyst review.

## Provider eligibility (post-fix addendum, 2026-08-04)

Three distinct properties on `providers.IntradayOHLCVProvider`. They were previously fused into one hard-coded
flag, which is how a provider whose live diagnostic had never run — and later, had FAILED — advertised itself as
cleared for real capture.

| Property | Kind | Meaning |
|---|---|---|
| `supports_real_event_semantics` | **Structural**, permanent | Does the provider implement the SIP/raw/exact-session contract at all? `True` for Alpaca, `False` for yfinance. No diagnostic result can change it. |
| `operational_clearance_status` | **Operational**, changes over time | What a live diagnostic has actually demonstrated in this environment. One of `NOT_RUN`, `LIVE_DIAGNOSTIC_FAILED`, `LIVE_DIAGNOSTIC_PASSED`. |
| `is_eligible_for_real_event` | **Derived** — never set directly | Computed by `providers.compute_real_event_eligibility()`. |

`compute_real_event_eligibility()` is pure and requires **all** of: `supports_real_event_semantics`, clearance
`== LIVE_DIAGNOSTIC_PASSED`, `feed == "sip"`, `adjustment == "raw"`, `session_grid_enforced` (the ALP-1 guard), and
`has_credentials`. Any of the following is independently disqualifying: `NOT_RUN`, `LIVE_DIAGNOSTIC_FAILED`, an
unrecognized clearance string (unknown fails closed), `feed="iex"`, a non-raw adjustment, a disabled grid guard,
absent credentials. Because it is pure, the whole truth table is deterministically tested without constructing a
provider or touching a network — including `feed="iex"` as an input, so no IEX code path needs to exist.

Current values: **Alpaca `LIVE_DIAGNOSTIC_PASSED` → eligible**; yfinance `LIVE_DIAGNOSTIC_FAILED` and
structurally unsupported → ineligible.

## Session grid: the ALP-1 fix (post-fix addendum, 2026-08-04)

`exchange_calendar.expected_bar_starts_utc(d)` is the authoritative, ordered list of 5-minute bar **start**
timestamps for a session, derived from the calendar's real open/close — 78 entries (09:30…15:55 ET) on an ordinary
session, 42 (09:30…12:55 ET) on a 13:00 early close. Three consumers depend on it:

1. **Request boundary.** `fetch_bars_alpaca_sip` sets `end` to `expected_bar_starts_utc(d)[-1]`, **never**
   `session_close_utc`. Alpaca's `end` is inclusive of a bar starting exactly at `end`, so asking for the 16:00 ET
   close returned the 16:00–16:05 ET after-hours bar as a 79th bar. Derived dynamically, so early closes are
   handled without a special case.
2. **Fail-closed validation.** `_assert_exact_session_grid()` requires the returned timestamp set to **equal** the
   expected set, raising `AlpacaSessionGridError` on missing, extra, duplicate, misaligned or out-of-session bars.
   It never trims, pads, re-sorts or de-duplicates. Bypassed only on the 1Day cross-check path
   (`enforce_session_grid=False`), which does its own "exactly one bar" check instead.
3. **Boundary selection.** `bars.extract_session_fields(bars, session_date=None)` selects the open and close bars
   **by expected timestamp**, never `bars[0]`/`bars[-1]`; aggregates high/low/volume over on-grid bars only; is
   order-independent; returns `None` for any absent boundary bar rather than substituting a neighbour; and raises
   `MixedSessionError` if handed bars from more than one session. `session_date` may be passed explicitly or is
   derived from the bars.

## Daily cross-check semantics (post-fix addendum, 2026-08-04)

| Component | Role | Gated? |
|---|---|---|
| Daily **OHLC** vs aggregated 5Min OHLC | `sanity_comparison` — both should describe the same regular session | **Yes**, 10 bp tolerance |
| Daily **volume** vs aggregated 5Min volume | `informational_only`, status `unresolved_provider_aggregation_semantics` | **No** |

**Retraction.** An earlier report stated the −15.50% daily-vs-aggregate volume difference was "most likely"
extended-hours volume. That was an unsupported guess and is withdrawn: it was never verified against vendor
documentation or a controlled experiment. The aggregation semantics of Alpaca's 1Day bar relative to its 5Min bars
are **not established** — which trades each series counts is unknown — and no explanation is offered. A volume
difference is therefore uninterpretable and must not gate anything; it becomes an equality gate only once
identical aggregation semantics are proven. An Alpaca 1Day volume must never be compared against, or substituted
for, a regular-session volume aggregate.

### Superseded: sector-ETF mapping v0.2 (operational-data addendum, 2026-08-04)

Retained for auditability. v0.2 gave each ticker a single `review` block (`status`, `source`, `retrieved_date`,
`reason`) with `status` one of `confirmed` (22 tickers), `corrected` (GPN, XLK → XLF) or
`unresolved_ambiguity_documented` (GME). Replaced wholesale by the seven separated fields above.

## Phase 2 adapter real-data dry run (operational-data addendum, 2026-08-04)

`import_pre_event_fields_for_ticker()` was run read-only against a real preserved Phase 2 panel run --
`GST_Phase2_DailyPanel_TestRun_2026-07-30_run3.csv` + its `..._COMPLETION_MARKER.json` (24 rows, marker status
`COMPLETE`), from the `phase2-wikipedia-reliability` worktree, explicit paths only. Result: **24/24 tickers
imported without error, `panel_status="COMPLETE"` preserved exactly, all 24 rows eligible for
`PRE_EVENT_CAPTURED`, both input files SHA-256-verified byte-identical before and after.** The adapter is
confirmed operationally compatible with a genuine (not synthetic) Phase 2 panel run.

## Provider labeling

`providers.YFinanceDevIntradayProvider.provider_label == "yfinance-development"` — recorded on every raw-bar
manifest entry produced by it. This is explicitly **not** claimed to be exchange-grade, NBBO, or institutional
execution quality anywhere in this module. `IntradayOHLCVProvider`/`EventTimingProvider` are abstract interfaces
specifically so a higher-quality provider can be substituted later without touching any derived-field definition
in `bars.py`/`derivations.py`.
