#!/usr/bin/env python3
# TASK 1 deterministic tests: HumanVerifiedEventRegistryProvider. Synthetic
# fixtures only -- no real upcoming event is populated anywhere here.
#
# Run directly: python test_market_response_event_registry.py

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.event_registry import (
    EventRegistryError,
    HumanVerifiedEventRegistry,
    RegistryBackedEventTimingProvider,
    is_trading_day_v0_1,
)
from gst_market_response.identity import EventIdentityError

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="mrd_registry_test_"))


UTC = timezone.utc


def test_bmo_amc_never_inferred_only_explicit_confirmed_value_accepted():
    root = temp_dir()
    try:
        registry = HumanVerifiedEventRegistry(root)
        try:
            registry.register_verified_event(
                ticker="MSFT", fiscal_period="FY27Q1", earnings_date=date(2026, 10, 27),
                earnings_datetime_utc=None, release_market_session="MAYBE_AMC",  # invalid label
                source_url="https://example.com/ir", source_title="Q1 press release",
                source_type="company_ir_press_release", source_retrieved_at_utc=datetime.now(UTC),
                verified_at_utc=datetime.now(UTC), verified_by="analyst_a", verification_status="verified",
            )
            ok = False
        except EventIdentityError:
            ok = True
        check("1a. An unrecognized release_market_session label is rejected, never coerced", ok)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_date_without_verified_timing_cannot_reach_registered():
    root = temp_dir()
    try:
        registry = HumanVerifiedEventRegistry(root)
        row = registry.register_verified_event(
            ticker="AAPL", fiscal_period="FY27Q1", earnings_date=date(2026, 10, 29),
            earnings_datetime_utc=None, release_market_session="AMC",
            source_url="https://example.com/ir", source_title="draft, not yet confirmed",
            source_type="company_ir_press_release", source_retrieved_at_utc=datetime.now(UTC),
            verified_at_utc=datetime.now(UTC), verified_by="analyst_b", verification_status="pending",
        )
        check("2a. A 'pending' row can be registered in the log itself (it's a real row, just not usable yet)", row.verification_status == "pending")

        try:
            registry.to_event_identity(row.event_id, company="Apple Inc.")
            ok = False
        except EventIdentityError:
            ok = True
        check("2b. to_event_identity() refuses (cannot reach REGISTERED) while verification_status is 'pending'", ok)

        provider = RegistryBackedEventTimingProvider(registry)
        timing = provider.get_event_timing("AAPL", "FY27Q1")
        check("2c. EventTimingProvider interface also returns all-None timing for an unverified row (fails closed)", timing.release_market_session is None and timing.earnings_datetime_utc is None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_expected_response_session_derived_mechanically():
    root = temp_dir()
    try:
        registry = HumanVerifiedEventRegistry(root)
        # BMO on an ordinary Tuesday -> same-day response session.
        row_bmo = registry.register_verified_event(
            ticker="MSFT", fiscal_period="FY27Q1", earnings_date=date(2026, 10, 27),  # Tuesday
            earnings_datetime_utc=None, release_market_session="BMO",
            source_url="https://example.com/ir", source_title="verified BMO release",
            source_type="exchange_notice", source_retrieved_at_utc=datetime.now(UTC),
            verified_at_utc=datetime.now(UTC), verified_by="analyst_c", verification_status="verified",
        )
        check("3a. BMO expected_response_session mechanically equals earnings_date itself", row_bmo.expected_response_session == "2026-10-27")

        # AMC on a Friday -> response session is the following Monday.
        row_amc = registry.register_verified_event(
            ticker="AAPL", fiscal_period="FY27Q1", earnings_date=date(2026, 10, 30),  # Friday
            earnings_datetime_utc=None, release_market_session="AMC",
            source_url="https://example.com/ir", source_title="verified AMC release",
            source_type="sec_filing", source_retrieved_at_utc=datetime.now(UTC),
            verified_at_utc=datetime.now(UTC), verified_by="analyst_c", verification_status="verified",
        )
        check("3b. AMC on a Friday mechanically maps to the following Monday", row_amc.expected_response_session == "2026-11-02")

        # Weekend/holiday: a verified BMO event dated on a documented holiday
        # (e.g. Thanksgiving 2026-11-26) must roll to the next trading day.
        row_holiday = registry.register_verified_event(
            ticker="GOOGL", fiscal_period="FY27Q1", earnings_date=date(2026, 11, 26),
            earnings_datetime_utc=None, release_market_session="BMO",
            source_url="https://example.com/ir", source_title="edge-case fixture, not a real filing date",
            source_type="exchange_notice", source_retrieved_at_utc=datetime.now(UTC),
            verified_at_utc=datetime.now(UTC), verified_by="analyst_c", verification_status="verified",
        )
        check("3c. Locked-specification holiday handling: BMO on a documented holiday rolls to the next trading day", row_holiday.expected_response_session == "2026-11-27")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_verified_event_reaches_registered_identity():
    root = temp_dir()
    try:
        registry = HumanVerifiedEventRegistry(root)
        row = registry.register_verified_event(
            ticker="TSLA", fiscal_period="FY26Q3", earnings_date=date(2026, 10, 21),
            earnings_datetime_utc=datetime(2026, 10, 21, 20, 5, tzinfo=UTC), release_market_session="AMC",
            source_url="https://example.com/ir/tsla-q3", source_title="TSLA Q3 FY26 shareholder deck",
            source_type="company_ir_press_release", source_retrieved_at_utc=datetime.now(UTC),
            verified_at_utc=datetime.now(UTC), verified_by="analyst_d", verification_status="verified",
        )
        identity = registry.to_event_identity(row.event_id, company="Tesla, Inc.")
        check("4a. A verified row successfully builds an EventIdentity", identity.ticker == "TSLA")
        check("4b. EventIdentity's release_market_session matches the verified value, not a guess", identity.release_market_session == "AMC")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_correction_requires_amendment_never_overwrites():
    root = temp_dir()
    try:
        registry = HumanVerifiedEventRegistry(root)
        row = registry.register_verified_event(
            ticker="NKE", fiscal_period="FY27Q1", earnings_date=date(2026, 9, 24),
            earnings_datetime_utc=None, release_market_session="AMC",
            source_url="https://example.com/ir/nke", source_title="NKE Q1 FY27 press release (draft time)",
            source_type="company_ir_press_release", source_retrieved_at_utc=datetime.now(UTC),
            verified_at_utc=datetime.now(UTC), verified_by="analyst_e", verification_status="verified",
        )
        registry_path = registry._log_path()
        before_bytes = registry_path.read_bytes()

        # A later, more authoritative source shows it was actually BMO, not AMC.
        amendment = registry.amend_event(
            amends_row_id=row.row_id,
            corrected_fields={"release_market_session": "BMO", "source_type": "exchange_notice",
                               "source_url": "https://example.com/exchange-notice/nke", "source_title": "NYSE notice, corrects release timing"},
            verified_at_utc=datetime.now(UTC), verified_by="analyst_f",
            notes="Original IR press release timestamp was ambiguous; exchange notice confirms BMO.",
        )
        after_bytes = registry_path.read_bytes()

        check("5a. Amendment row references the original by row_id", amendment.amends_row_id == row.row_id)
        check("5b. Amendment is a distinct row (different row_id)", amendment.row_id != row.row_id)
        check("5c. Original registry bytes are an untouched prefix after the amendment", after_bytes.startswith(before_bytes))

        rows = registry.read_all()
        original_still_says_amc = next(r for r in rows if r["row_id"] == row.row_id)["release_market_session"]
        check("5d. The original row's own release_market_session is still literally AMC on disk, never edited", original_still_says_amc == "AMC")

        effective = registry.effective_row(row.event_id)
        check("5e. effective_row() reflects the CORRECTED value (BMO) for readers who want the current view", effective["release_market_session"] == "BMO")
        check("5f. Amendment recomputed expected_response_session mechanically for the corrected session", effective["expected_response_session"] == "2026-09-24")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_real_upcoming_event_populated():
    root = temp_dir()
    try:
        registry = HumanVerifiedEventRegistry(root)
        check("6a. A freshly-constructed registry starts with zero rows (no real upcoming event pre-populated)", registry.read_all() == [])
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    test_bmo_amc_never_inferred_only_explicit_confirmed_value_accepted()
    test_date_without_verified_timing_cannot_reach_registered()
    test_expected_response_session_derived_mechanically()
    test_verified_event_reaches_registered_identity()
    test_correction_requires_amendment_never_overwrites()
    test_no_real_upcoming_event_populated()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL EVENT REGISTRY TESTS PASSED")
        sys.exit(0)
