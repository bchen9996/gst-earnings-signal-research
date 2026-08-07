#!/usr/bin/env python3
# Deterministic tests for the session-vocabulary boundary between
# gst_market_response and the Event Dossier Protocol.
#
# Uses only synthetic in-memory / temp-directory fixtures. Never registers a
# real event, never creates a real dossier, never touches the network.
#
# Run directly: python test_market_response_protocol_boundary.py

from __future__ import annotations

import csv
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.identity import VALID_RELEASE_SESSIONS
from gst_market_response.protocol_boundary import (
    MARKET_RESPONSE_TO_PROTOCOL_SESSION,
    SessionVocabularyError,
    load_validator_module,
    to_market_response_release_session,
    to_protocol_release_session,
)

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


def expect_raises(label: str, fn, *args) -> None:
    try:
        fn(*args)
    except SessionVocabularyError:
        print(f"PASS: {label}")
    except Exception as exc:  # wrong exception type is a failure
        print(f"FAIL: {label} (raised {type(exc).__name__}, expected SessionVocabularyError)")
        FAILURES.append(label)
    else:
        print(f"FAIL: {label} (did not raise)")
        FAILURES.append(label)


def test_all_three_valid_mappings():
    check("1a. BMO -> before_open", to_protocol_release_session("BMO") == "before_open")
    check("1b. INTRADAY -> during_session", to_protocol_release_session("INTRADAY") == "during_session")
    check("1c. AMC -> after_close", to_protocol_release_session("AMC") == "after_close")
    check(
        "1d. every VALID_RELEASE_SESSIONS member translates (exhaustive, no gaps)",
        all(to_protocol_release_session(s) for s in VALID_RELEASE_SESSIONS),
    )
    check(
        "1e. mapping covers exactly the three sessions, no extras",
        len(MARKET_RESPONSE_TO_PROTOCOL_SESSION) == 3,
    )


def test_round_trip_is_lossless():
    for s in VALID_RELEASE_SESSIONS:
        rt = to_market_response_release_session(to_protocol_release_session(s))
        check(f"2. {s} survives a round trip unchanged", rt == s)


def test_invalid_values_fail_closed():
    expect_raises("3a. None raises SessionVocabularyError", to_protocol_release_session, None)
    expect_raises("3b. empty string raises", to_protocol_release_session, "")
    expect_raises("3c. whitespace-only raises", to_protocol_release_session, "   ")
    expect_raises("3d. unknown token raises", to_protocol_release_session, "PREMARKET")
    expect_raises("3e. lowercase 'amc' raises (exact match only)", to_protocol_release_session, "amc")
    expect_raises("3f. padded ' AMC ' raises (no silent trim-and-accept)", to_protocol_release_session, " AMC ")
    expect_raises("3g. a protocol-side value raises on the MR->protocol path", to_protocol_release_session, "after_close")
    expect_raises("3h. non-string (int) raises", to_protocol_release_session, 3)
    expect_raises("3i. non-string (list) raises", to_protocol_release_session, ["AMC"])


def test_no_inference_from_time():
    """The boundary must not accept a timestamp as a substitute for a declared
    session -- that would manufacture a protocol field from a clock reading."""
    expect_raises(
        "4a. an ISO timestamp is not accepted as a session",
        to_protocol_release_session,
        "2026-07-29T20:05:00+00:00",
    )
    expect_raises("4b. a bare hour is not accepted as a session", to_protocol_release_session, "20:05")


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def test_converted_identity_is_accepted_by_the_real_validator():
    """Build a minimal synthetic Layer A events.csv whose
    release_market_session came from the translation layer, and prove the
    SHIPPED validator accepts it -- and rejects the untranslated value."""
    validator = load_validator_module()

    header = [
        "event_id", "ticker", "company_name", "fiscal_period", "event_type",
        "earnings_date", "release_market_session", "event_datetime_utc", "niche",
        "protocol_version", "event_disposition",
        "blinding_compromised_for_confirmatory_use", "created_by", "created_at_utc",
    ]

    def row_with(session: str) -> list[str]:
        return [
            "EVT-AAPL-FY26Q3-ERN", "AAPL", "Apple Inc.", "FY26Q3", "ERN",
            "2026-07-30", session, "2026-07-30T20:05:00+00:00",
            "fixed_24_ticker_earnings_panel", "0.1", "confirmatory", "false", "ai",
            "2026-08-02T00:00:00+00:00",
        ]

    translated = to_protocol_release_session("AMC")

    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "good"
        good.mkdir()
        _write_csv(good / "events.csv", header, [row_with(translated)])
        _ok, findings = validator.validate(good, mode="draft")
        session_findings = [
            f for f in findings
            if "release_market_session" in f.message and "events.csv" in f.message
        ]
        check(
            "5a. a translated session ('after_close') raises no release_market_session finding",
            not session_findings,
        )

    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad"
        bad.mkdir()
        _write_csv(bad / "events.csv", header, [row_with("AMC")])
        _ok, findings = validator.validate(bad, mode="draft")
        session_findings = [
            f for f in findings
            if "release_market_session" in f.message and "AMC" in f.message
        ]
        check(
            "5b. the UNtranslated market-response value 'AMC' is rejected by the validator's "
            "enum gate -- proving the translation is load-bearing",
            bool(session_findings),
        )

    check(
        "5c. the validator's enum gate itself is untouched (still the three protocol values)",
        validator.RELEASE_MARKET_SESSIONS == {"before_open", "during_session", "after_close"},
    )
    check(
        "5d. the market-response enum itself is untouched (still the three MR values)",
        tuple(VALID_RELEASE_SESSIONS) == ("BMO", "AMC", "INTRADAY"),
    )


if __name__ == "__main__":
    test_all_three_valid_mappings()
    test_round_trip_is_lossless()
    test_invalid_values_fail_closed()
    test_no_inference_from_time()
    test_converted_identity_is_accepted_by_the_real_validator()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL PROTOCOL BOUNDARY TESTS PASSED")
    sys.exit(0)
