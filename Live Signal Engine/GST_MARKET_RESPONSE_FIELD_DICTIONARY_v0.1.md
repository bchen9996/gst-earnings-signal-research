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

## Provider labeling

`providers.YFinanceDevIntradayProvider.provider_label == "yfinance-development"` — recorded on every raw-bar
manifest entry produced by it. This is explicitly **not** claimed to be exchange-grade, NBBO, or institutional
execution quality anywhere in this module. `IntradayOHLCVProvider`/`EventTimingProvider` are abstract interfaces
specifically so a higher-quality provider can be substituted later without touching any derived-field definition
in `bars.py`/`derivations.py`.
