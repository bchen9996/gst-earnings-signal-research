# Market Response — Operational Readiness Checklist (v0.1)

Status as of the 2026-08-04 operational-data pass (second operational-readiness pass; PR #3, branch
`phase2-market-response`, stacked on PR #1). **No real event has been registered. No trading strategy is
selected. No profitability claim exists.**

## Done — first pass (2026-08-04)

- [x] `HumanVerifiedEventRegistryProvider` (`event_registry.py`) — human-verified-only event timing; a date without
      verified timing cannot reach `REGISTERED`; BMO/AMC/INTRADAY never inferred from price; `expected_response_session`
      always mechanically derived; corrections are amendment rows, originals never overwritten.
- [x] Phase 2 pre-event adapter (`phase2_adapter.py`) — explicit-path-only (no implicit "latest file" discovery),
      both input files hashed, marker cross-verified against the CSV rather than trusted blindly, `COMPLETE`/`PARTIAL`
      and all nulls/source statuses preserved exactly, generic panel IV never imported as `earnings_implied_move`,
      input files left byte-identical, research commit SHA + methodology version recorded.
- [x] Sector-ETF mapping mechanical review gate (`sector_mapping.py`) — exactly the locked 24 tickers, no
      duplicates/extras, valid ETF symbols, `mapping_version`/`review_status`/`reviewed_by`/`reviewed_at_utc` fields.
- [x] Amendment semantics deterministically proven (21 checks).

## Done — second pass (2026-08-04, this update)

- [x] **`AlpacaHistoricalSipIntradayProvider`** (`alpaca_provider.py`) — official REST endpoint, no SDK; bounded
      retries (429/5xx, `Retry-After` honored, capped), 401/403 never retried, `MAX_WALL_CLOCK_S=60`/`MAX_ATTEMPTS=5`/
      `MAX_PAGES=20` bounds, 15-minute freshness gate checked before any HTTP call, sanitized provenance (10 required
      fields), `BRK-B -> BRK.B` symbol translation with both identifiers always recorded, never falls back to
      IEX/yfinance/undocumented endpoints/synthetic bars, `is_eligible_for_real_event = True` (vs. `False` for
      yfinance, explicit). **43 deterministic checks, all passing. Never exercised against a real Alpaca response —
      credentials absent (see below).**
- [x] **Authoritative XNYS calendar** (`exchange_calendar.py`, `exchange_calendars==4.13.2` pinned in
      `requirements.txt`) — replaces the hand-maintained partial holiday list as the operational default (old list
      kept, unused, for auditability only). Ordinary/weekend/holiday/early-close/DST/AMC/BMO/INTRADAY/bar-boundary
      behavior all deterministically tested (29 checks).
- [x] **Sector-ETF mapping v0.2, `review_status: "APPROVED"`** — all 24 tickers individually reviewed against actual
      current sector-ETF holdings (or sourced GICS classification). **GPN corrected XLK → XLF** (confirmed absent
      from XLK, present in XLF at 0.24% weight; consistent with the 2023 GICS payment-processor reclassification).
      **GME's XLY fund-constituency left explicitly unresolved** (GICS sector confirmed, disclosed-holdings-list
      membership not confirmed) — documented, not guessed.
- [x] **Phase 2 adapter dry run against a real preserved panel** — `GST_Phase2_DailyPanel_TestRun_2026-07-30_run3.csv`
      + its completion marker (24 rows, `COMPLETE`), read-only. **24/24 tickers imported cleanly, `panel_status`
      preserved exactly, 24/24 eligible for `PRE_EVENT_CAPTURED`, both files byte-identical before/after.** Adapter
      confirmed operationally compatible with real panel output.
- [x] 116 new deterministic checks across 2 new test files (`test_market_response_alpaca_provider.py`: 43,
      `test_market_response_exchange_calendar.py`: 29) plus 7 additional checks added to the existing sector-mapping
      test file (13 → 20). Full 19-file deterministic suite (11 pre-existing Phase 2/Wikipedia + 8 market-response)
      passes with zero regressions — **638 total checks, all passing.**
- [ ] **Live Alpaca diagnostic (Section F): NOT RUN.** `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` were absent from the
      environment at preflight (checked via both Bash and PowerShell, values never printed). Per instruction, the
      pass stopped before any live call rather than fake or claim a result.

## NOT done — remaining blockers before the first real event can be registered

1. **The Alpaca provider has never been exercised against a real Alpaca response.** No live diagnostic has run
   (credentials absent in both passes to date). Its `BRK-B -> BRK.B` symbol mapping is an unverified assumption.
   This must happen, and pass, before any real capture.
2. **`YFinanceDevIntradayProvider` remains explicitly ineligible** (`is_eligible_for_real_event = False`) and its
   one live diagnostic to date FAILED (2026-08-04, SPY, root cause likely environment-specific, not remediated).
   Not a blocker for Alpaca-based capture, but yfinance itself is not, and will not become, usable for a real event.
3. **No `EventTimingProvider` other than the human-verified registry exists** (by design). A real event still
   requires a human to manually verify and enter its timing.
4. **GME's sector-ETF assignment carries a documented, unresolved fund-constituency question** — usable (the
   mapping is `APPROVED` overall, per the review's own stated conditions), but this specific entry should be
   revisited if GME is ever the ticker for a real event.
5. **No live wiring exists between the Phase 2 adapter and a currently-running Phase 2 panel process** — the dry
   run proved compatibility with one real, already-completed panel output; it has never been invoked as part of an
   active capture pipeline.
6. **No Radar integration, no strategy test, no backtest** — all explicitly out of scope for this and every prior
   pass in this lane.
7. **This branch is still stacked on, and must not be merged ahead of, PR #1.**

## Explicit statements (restated per instruction)

- YFinance remains a development provider.
- The event registry requires human-verified primary-source timing.
- No trading strategy is selected.
- No profitability claim exists.
- The first real event has not yet been registered.
