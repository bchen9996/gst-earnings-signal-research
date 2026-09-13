#!/usr/bin/env python3
"""run_hyp05_additional_anchor_shocks.py tests -- the pure-logic dedup
helper plus build()'s pre-flight overwrite guard. The LIVE pipeline beyond
that guard (candidate_events_for_ticker, the closes fetch inside build())
is NOT exercised here, same discipline as every other live-fetch script's
test file in this repo.

Fully offline, synthetic fixtures written to a temp dir. Sockets blocked
before import.

Run directly: python test_hyp04_supply_chain_hedge_additional_anchor_shocks.py
"""
from __future__ import annotations

import socket
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge import (  # noqa: E402
    run_hyp05_additional_anchor_shocks as M,
)
from hyp04_supply_chain_hedge.earnings_events import CandidateEvent  # noqa: E402

FAILURES: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="hyp05_addl_shocks_test_"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _ev(ticker: str, release_date: str, accession: str,
        acceptance_utc: str = "2020-01-01T20:05:00.000Z") -> CandidateEvent:
    return CandidateEvent(
        event_id=f"{ticker}-{release_date}", anchor_ticker=ticker,
        release_date=release_date, release_session="AMC",
        session_basis="test fixture", filing_date=release_date,
        acceptance_utc=acceptance_utc, acceptance_et="", items="2.02",
        accession=accession, flags=())


def test_1_dedup_keeps_earliest_acceptance() -> None:
    early = _ev("DELL", "2022-01-01", "0000000001-22-000001",
               acceptance_utc="2022-01-01T20:05:00.000Z")
    late = _ev("DELL", "2022-01-01", "0000000001-22-000002",
              acceptance_utc="2022-01-05T13:00:00.000Z")
    kept, dropped = M._dedup_events([late, early])
    check("1a. exactly one event survives for the duplicated release",
          len(kept) == 1, str(kept))
    check("1b. the EARLIEST-accepted filing is kept",
          kept[0].accession == early.accession, str(kept))
    check("1c. exactly one drop is recorded, naming the superseded accession",
          len(dropped) == 1 and dropped[0]["superseded_accession"] == late.accession,
          str(dropped))
    check("1d. the drop names the rule, for the audit trail",
          dropped[0]["reason"] == M.DEDUP_RULE)


def test_2_dedup_ties_break_on_accession() -> None:
    a = _ev("DVN", "2010-01-01", "0000000002-10-000002")
    b = _ev("DVN", "2010-01-01", "0000000001-10-000001")
    kept, _dropped = M._dedup_events([a, b])
    check("2a. a tie on acceptance breaks on the lower accession string",
          kept[0].accession == "0000000001-10-000001", str(kept))


def test_3_dedup_is_a_no_op_across_different_keys() -> None:
    events = [_ev("DELL", "2022-01-01", "acc-1"),
             _ev("DELL", "2022-04-01", "acc-2"),
             _ev("GOOGL", "2022-01-01", "acc-3")]
    kept, dropped = M._dedup_events(events)
    check("3a. three distinct (ticker, release_date) keys all survive",
          len(kept) == 3 and not dropped, str((kept, dropped)))


def test_3b_build_refuses_on_a_ticker_missing_a_lineage_note() -> None:
    """Added when the module generalized beyond exactly 3 hardcoded
    tickers: adding a ticker to a run must never outrun checking its
    formerNames lineage first."""
    out_json = TMP / "lineage_missing.json"
    out_csv = TMP / "lineage_missing.csv"
    refusals = M.build(tickers=("DELL", "NOTREALLYATICKER"),
                       out_json=out_json, out_csv=out_csv)
    check("3b-a. refuses, naming the ticker with no LINEAGE_NOTES entry",
          any("NOTREALLYATICKER" in r for r in refusals), str(refusals))
    check("3b-b. a ticker that DOES have a note is not itself named as "
          "missing", not any(r.startswith("DELL") for r in refusals),
          str(refusals))
    check("3b-c. refusing here never reaches the network (no output "
          "written, nothing to clean up)",
          not out_json.exists() and not out_csv.exists())


def test_4_build_refuses_to_overwrite_existing_artifacts() -> None:
    out_json = TMP / "existing.json"
    out_csv = TMP / "existing.csv"
    out_json.write_text("{}", encoding="utf-8")
    out_csv.write_text("x\n", encoding="utf-8")

    refusals = M.build(out_json=out_json, out_csv=out_csv)
    check("4a. build() refuses when out_json already exists",
          any("existing.json" in r and "already exists" in r for r in refusals),
          str(refusals))
    check("4b. build() refuses when out_csv already exists",
          any("existing.csv" in r and "already exists" in r for r in refusals),
          str(refusals))
    check("4c. the existing files are untouched",
          out_json.read_text(encoding="utf-8") == "{}"
          and out_csv.read_text(encoding="utf-8") == "x\n")


def test_4b_default_tickers_all_have_lineage_notes() -> None:
    check("4b-a. every ticker in ADDITIONAL_ANCHOR_TICKERS has a "
          "LINEAGE_NOTES entry -- the default set can never itself "
          "trigger the refusal it enforces on others",
          all(t in M.LINEAGE_NOTES for t in M.ADDITIONAL_ANCHOR_TICKERS),
          str([t for t in M.ADDITIONAL_ANCHOR_TICKERS
              if t not in M.LINEAGE_NOTES]))


def test_5_shock_csv_fields_match_make_anchor_shocks_schema() -> None:
    from hyp04_supply_chain_hedge.make_anchor_shocks import (
        SHOCK_CSV_FIELDS as HYP04_FIELDS,
    )
    check("5a. this module writes the SAME row schema as HYP-04's own "
          "anchor-shocks artifact, so the two files are structurally "
          "interchangeable to any reader",
          M.SHOCK_CSV_FIELDS == HYP04_FIELDS, str(M.SHOCK_CSV_FIELDS))


def test_6_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("6a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("6a. network blocked", True)


if __name__ == "__main__":
    test_1_dedup_keeps_earliest_acceptance()
    test_2_dedup_ties_break_on_accession()
    test_3_dedup_is_a_no_op_across_different_keys()
    test_3b_build_refuses_on_a_ticker_missing_a_lineage_note()
    test_4_build_refuses_to_overwrite_existing_artifacts()
    test_4b_default_tickers_all_have_lineage_notes()
    test_5_shock_csv_fields_match_make_anchor_shocks_schema()
    test_6_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP05_ADDITIONAL_ANCHOR_SHOCKS TESTS PASSED")
    sys.exit(0)
