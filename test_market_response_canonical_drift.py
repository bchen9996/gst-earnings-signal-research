#!/usr/bin/env python3
# Deterministic drift guards between gst_market_response and the Event Dossier
# Protocol.
#
# The market-response package keeps its own copies of the locked 24-ticker
# universe and the event_id pattern. Before PR #2 merged, the protocol lived
# on another branch and the copies could not be checked mechanically. Now that
# both live in one tree, these tests compare each copy against the CANONICAL,
# EXECUTABLE definition and fail on any divergence.
#
# Deliberately compares against executable/authoritative sources only:
#   * locked_universe_v0.1.json          (the protocol's own data file)
#   * validate_event_dossier.py          (loaded and executed, not parsed)
#   * market_response_addendum.csv       (the schema file's header)
# Never against prose documentation.
#
# Run directly: python test_market_response_canonical_drift.py

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE
from gst_market_response.identity import EVENT_ID_RE, VALID_RELEASE_SESSIONS
from gst_market_response.protocol_boundary import (
    MARKET_RESPONSE_TO_PROTOCOL_SESSION,
    load_canonical_locked_universe,
    load_validator_module,
)

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


def test_locked_universe_matches_canonical_json():
    canonical = load_canonical_locked_universe()
    check(
        "1a. locked universe has the same 24 tickers as locked_universe_v0.1.json",
        set(LOCKED_24_TICKER_UNIVERSE) == set(canonical),
    )
    check(
        "1b. locked universe count is exactly 24 on both sides",
        len(LOCKED_24_TICKER_UNIVERSE) == 24 == len(canonical),
    )
    check(
        "1c. locked universe order is identical (not merely the same set)",
        tuple(LOCKED_24_TICKER_UNIVERSE) == tuple(canonical),
    )
    check(
        "1d. no duplicate tickers in the market-response copy",
        len(set(LOCKED_24_TICKER_UNIVERSE)) == len(LOCKED_24_TICKER_UNIVERSE),
    )


def test_event_id_pattern_matches_canonical_validator():
    validator = load_validator_module()
    check(
        "2a. EVENT_ID_RE pattern string is identical to the validator's",
        EVENT_ID_RE.pattern == validator.EVENT_ID_RE.pattern,
    )
    check(
        "2b. EVENT_ID_RE flags are identical to the validator's",
        EVENT_ID_RE.flags == validator.EVENT_ID_RE.flags,
    )
    # Behavioural equivalence, not just textual: same verdict on every probe.
    probes = [
        "EVT-AAPL-FY26Q3-ERN",
        "EVT-MSFT-FY26Q4-ERN",
        "EVT-BRK-B-FY26Q1-ERN",
        "EVT-TTWO-FY26Q2-ERN",
        "evt-aapl-fy26q3-ern",
        "EVT-AAPL-FY26Q3",
        "AAPL-FY26Q3-ERN",
        "EVT-AAPL-FY2026Q3-ERN",
        "",
        "EVT--FY26Q3-ERN",
    ]
    agree = all(
        bool(EVENT_ID_RE.match(p)) == bool(validator.EVENT_ID_RE.match(p)) for p in probes
    )
    check("2c. both patterns agree on every probe id (accept and reject alike)", agree)


def test_session_vocabularies_match_both_canonical_definitions():
    validator = load_validator_module()
    check(
        "3a. translation keys are exactly the market-response VALID_RELEASE_SESSIONS",
        set(MARKET_RESPONSE_TO_PROTOCOL_SESSION) == set(VALID_RELEASE_SESSIONS),
    )
    check(
        "3b. translation values are exactly the validator's RELEASE_MARKET_SESSIONS",
        set(MARKET_RESPONSE_TO_PROTOCOL_SESSION.values()) == set(validator.RELEASE_MARKET_SESSIONS),
    )
    check(
        "3c. translation is a bijection (no two sessions collapse to one)",
        len(set(MARKET_RESPONSE_TO_PROTOCOL_SESSION.values()))
        == len(MARKET_RESPONSE_TO_PROTOCOL_SESSION),
    )


def test_layer_b_schema_columns_are_read_from_the_protocol_file():
    from gst_market_response.protocol_boundary import load_layer_b_schema_columns

    cols = load_layer_b_schema_columns()
    validator = load_validator_module()
    required = validator.FIELD_RULES["market_response_addendum"]["required"]
    check(
        "4a. every validator-required addendum column exists in the schema header",
        all(c in cols for c in required),
    )
    check(
        "4b. addendum_id is the first schema column",
        cols[0] == "addendum_id",
    )
    check(
        "4c. the schema header is non-empty and has no blank column names",
        len(cols) > 0 and all(c for c in cols),
    )


def test_no_stale_cross_branch_comment_remains():
    """The stale claim that the protocol is unreachable from here must be
    gone from both files that carried it."""
    for rel in ("gst_market_response/identity.py", "gst_market_response/constants.py"):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        stale = (
            "is not\n# reachable at runtime from here" in text
            or "literally unreachable at runtime from a different git worktree." in text
        )
        # The corrected files may quote the old wording while explaining the
        # correction; what must not survive is an uncorrected claim.
        corrected = "2026-08-06" in text and "no longer" in text.lower()
        check(f"5. {rel} no longer asserts the protocol is unreachable", (not stale) or corrected)


if __name__ == "__main__":
    test_locked_universe_matches_canonical_json()
    test_event_id_pattern_matches_canonical_validator()
    test_session_vocabularies_match_both_canonical_definitions()
    test_layer_b_schema_columns_are_read_from_the_protocol_file()
    test_no_stale_cross_branch_comment_remains()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL CANONICAL DRIFT GUARD TESTS PASSED")
    sys.exit(0)
