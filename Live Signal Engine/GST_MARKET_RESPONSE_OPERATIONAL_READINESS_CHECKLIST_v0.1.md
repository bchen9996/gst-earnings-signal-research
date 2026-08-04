# Market Response — Operational Readiness Checklist (v0.1)

Status as of the 2026-08-04 operational-readiness pass (PR #3, branch `phase2-market-response`, stacked on PR #1).
**No real event has been registered. No trading strategy is selected. No profitability claim exists.**

## Done in this pass

- [x] `HumanVerifiedEventRegistryProvider` (`event_registry.py`) — human-verified-only event timing; a date without
      verified timing cannot reach `REGISTERED`; BMO/AMC/INTRADAY never inferred from price; `expected_response_session`
      always mechanically derived; corrections are amendment rows, originals never overwritten.
- [x] Phase 2 pre-event adapter (`phase2_adapter.py`) — explicit-path-only (no implicit "latest file" discovery),
      both input files hashed, marker cross-verified against the CSV rather than trusted blindly, `COMPLETE`/`PARTIAL`
      and all nulls/source statuses preserved exactly, generic panel IV never imported as `earnings_implied_move`,
      input files left byte-identical, research commit SHA + methodology version recorded.
- [x] Sector-ETF mapping mechanical review gate (`sector_mapping.py`) — exactly the locked 24 tickers, no
      duplicates/extras, valid ETF symbols, `mapping_version`/`review_status`/`reviewed_by`/`reviewed_at_utc` fields;
      `DRAFT` usable in fixtures only, `assert_usable_for_real_event()` blocks real-event use until `APPROVED`.
- [x] One bounded live diagnostic of `YFinanceDevIntradayProvider` (SPY, 2026-08-03) — **classified FAILED**
      (zero bars returned); root cause investigated but not remediated; see
      `GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md`.
- [x] Amendment semantics deterministically proven: a `PARTIAL` record is immutable/terminal; a later recovery is a
      distinct, linked `AMENDMENT`; original bytes/hash unchanged; an amendment reaches a completeness tier only if
      independently checked against that tier's gate; full chronology is reconstructable without the original
      `PARTIAL` record ever appearing to have been upgraded.
- [x] 77 new deterministic checks across 4 new test files (`test_market_response_amendment_semantics.py`: 21,
      `test_market_response_event_registry.py`: 16, `test_market_response_phase2_adapter.py`: 27,
      `test_market_response_sector_mapping_gate.py`: 13), all passing. Full 17-file deterministic suite
      (11 pre-existing Phase 2/Wikipedia files + 6 market-response files) passes with zero regressions.

## NOT done — remaining blockers before the first real event can be registered

1. **`YFinanceDevIntradayProvider` cannot currently retrieve real intraday data in this execution environment**
   (diagnostic FAILED, root cause likely environment-specific but not fixed). Must be resolved, or a different
   provider deliberately evaluated and approved, before any real D1/D3 capture can occur.
2. **No `EventTimingProvider` other than the human-verified registry exists** (by design — this pass deliberately
   did not build an automated timing-scraper). A real event still requires a human to manually verify and enter its
   timing via `HumanVerifiedEventRegistry.register_verified_event()`.
3. **The sector-ETF mapping is still `review_status: "DRAFT"`** — a human reviewer must set it to `APPROVED` (with
   `reviewed_by`/`reviewed_at_utc`) before it can back a `COMPLETE` real event.
4. **`GST_MARKET_RESPONSE_EXCHANGE_CALENDAR` (`NYSE_NASDAQ_MON_FRI_PARTIAL_HOLIDAYS_V0.1`) is an explicitly
   partial, non-exhaustive holiday list** — sufficient for deterministic testing, not yet a verified, authoritative
   multi-decade NYSE calendar.
5. **No live wiring exists between the Phase 2 adapter and an actual, currently-running Phase 2 panel output** —
   this pass only proved the adapter works against synthetic CSV+marker fixtures; it has never been pointed at a
   real panel run.
6. **No Radar integration, no strategy test, no backtest** — all explicitly out of scope for this and every prior
   pass in this lane.
7. **This branch is still stacked on, and must not be merged ahead of, PR #1.**

## Explicit statements (restated per instruction)

- YFinance remains a development provider.
- The event registry requires human-verified primary-source timing.
- No trading strategy is selected.
- No profitability claim exists.
- The first real event has not yet been registered.
