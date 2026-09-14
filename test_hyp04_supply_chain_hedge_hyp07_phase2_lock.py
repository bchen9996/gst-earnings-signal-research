#!/usr/bin/env python3
"""make_hyp07_phase2_lock.py tests -- offline, hermetic, no network, no
git. `build_draft` itself calls `_commit_sha` (requires a clean working
tree) and reads the real committed artifacts, so it is not exercised
end-to-end here -- same reason HYP-05's/HYP-06's own phase2-lock test
files skip it. What IS fully offline-testable is `_locked_events`/
`_all_shock_rows`: the pure derivation, given synthetic fixtures.

  ONLY QUALIFYING ROWS SURVIVE, ACROSS MULTIPLE ANCHOR-SHOCKS CSVS
  (test_1) -- HYP-07's real 195-pair universe spans 3 separate
  anchor-shocks files, same shape as HYP-06's own multi-file case.

  EACH LOCKED EVENT CARRIES excess_return ALONGSIDE shock (test_1) --
  new relative to HYP-06's own test: HYP-07's target reads the SIGNED
  value, not just the magnitude.

  A DUPLICATE (anchor, release_date) KEY ACROSS TWO CSVS REFUSES (test_2).

  DRIFT BETWEEN THE UNIVERSE AND EVERY SHOCKS FILE REFUSES (test_3).

  THE REAL COMMITTED ARTIFACTS DERIVE EXACTLY 195 (test_4, a control) --
  proves the module's own EXPECTED_N_EVENTS assumption against the
  actual files on disk.

Run directly: python test_hyp04_supply_chain_hedge_hyp07_phase2_lock.py
"""
from __future__ import annotations

import json
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

from hyp04_supply_chain_hedge.make_hyp07_phase2_lock import (  # noqa: E402
    EXPECTED_N_EVENTS, Phase2LockError, _all_shock_rows, _locked_events,
)

FAILURES: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="hyp07_phase2_lock_test_"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _qual(ticker: str, anchor: str, event_date: str, qualifies: bool,
         rel_type: str = "sector_competitor", as_of: str = "2010-01-01") -> dict:
    return {
        "ticker": ticker,
        "qualifies": qualifies,
        "evidence": {"candidate": {
            "anchor_ticker": anchor, "anchor_event_date": event_date,
            "relationship_type": rel_type, "as_of_date": as_of}},
    }


def _shock_row(anchor: str, release_date: str, event_id: str,
              attributed: str, shock: str, excess_return: str,
              status: str = "shock_computed") -> dict:
    return {"event_id": event_id, "anchor_ticker": anchor,
            "release_date": release_date, "attributed_session": attributed,
            "shock": shock, "excess_return": excess_return, "status": status}


def _write_universe(qualifications: list[dict]) -> Path:
    p = TMP / f"universe_{id(qualifications)}.json"
    p.write_text(json.dumps({"qualifications": qualifications}), encoding="utf-8")
    return p


def _write_shocks(name: str, rows: list[dict]) -> Path:
    import csv
    p = TMP / f"{name}.csv"
    fields = ["event_id", "anchor_ticker", "release_date",
              "attributed_session", "shock", "excess_return", "status"]
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return p


def test_1_qualifying_rows_resolve_across_multiple_csvs_with_excess_return() -> None:
    universe = _write_universe([
        _qual("PEER1", "ABT", "2017-04-19", True),
        _qual("PEER2", "CLX", "2020-01-01", True),   # in a DIFFERENT csv
        _qual("PEER3", "ABT", "2018-11-10", False),   # not qualifying
    ])
    csv_a = _write_shocks("shocks_a", [
        _shock_row("ABT", "2017-04-19", "ABT-2017-04-19", "2017-04-19",
                   "0.15", "-0.15"),
        _shock_row("ABT", "2018-11-10", "ABT-2018-11-10", "2018-11-12",
                   "0.26", "0.26"),
    ])
    csv_b = _write_shocks("shocks_b", [
        _shock_row("CLX", "2020-01-01", "CLX-2020-01-01", "2020-01-02",
                   "0.05", "0.05"),
    ])
    events = _locked_events(universe, (csv_a, csv_b))
    check("1a. exactly two events survive (the non-qualifying row is "
          "excluded)", len(events) == 2, str(events))
    ids = {e["event_id"] for e in events}
    check("1b. the ABT event (csv_a) and the CLX event (csv_b) both "
          "resolve, from different files",
          ids == {"ABT-2017-04-19", "CLX-2020-01-01"}, str(ids))
    check("1c. relationship_type and as_of_date are carried onto the event",
          all("relationship_type" in e and "as_of_date" in e for e in events))
    abt_ev = next(e for e in events if e["event_id"] == "ABT-2017-04-19")
    check("1d. excess_return is carried, SIGNED, distinct from shock's "
          "magnitude -- the value HYP-07's regressor actually reads",
          abt_ev["excess_return"] == -0.15 and abt_ev["shock"] == 0.15,
          str(abt_ev))


def test_2_duplicate_key_across_two_csvs_refuses() -> None:
    csv_a = _write_shocks("dup_a", [
        _shock_row("ABT", "2017-04-19", "ABT-2017-04-19", "2017-04-19",
                   "0.15", "0.15"),
    ])
    csv_b = _write_shocks("dup_b", [
        _shock_row("ABT", "2017-04-19", "ABT-2017-04-19-DUP", "2017-04-19",
                   "0.99", "0.99"),
    ])
    try:
        _all_shock_rows((csv_a, csv_b))
        check("2a. an (anchor, release_date) key in two CSVs refuses", False)
    except Phase2LockError as e:
        check("2a. an (anchor, release_date) key in two CSVs refuses", True)
        check("2b. the refusal names the anchor", "ABT" in str(e), str(e))


def test_3_drift_between_universe_and_every_shocks_file_refuses() -> None:
    universe = _write_universe([
        _qual("PEER1", "ABT", "2099-01-01", True),   # no matching shock row anywhere
    ])
    csv_a = _write_shocks("drift_a", [
        _shock_row("ABT", "2017-04-19", "ABT-2017-04-19", "2017-04-19",
                   "0.15", "0.15"),
    ])
    try:
        _locked_events(universe, (csv_a,))
        check("3a. drift between universe and every shocks file refuses", False)
    except Phase2LockError as e:
        check("3a. drift between universe and every shocks file refuses", True)
        check("3b. the refusal names the orphaned date",
              "2099-01-01" in str(e), str(e))


def test_4_the_real_committed_artifacts_derive_exactly_195() -> None:
    """CONTROL: proves EXPECTED_N_EVENTS against the real files on disk."""
    from hyp04_supply_chain_hedge.make_hyp07_phase2_lock import (
        ANCHOR_SHOCKS_CSVS, PEER_UNIVERSE_JSON,
    )
    missing = [p for p in (PEER_UNIVERSE_JSON, *ANCHOR_SHOCKS_CSVS)
              if not p.is_file()]
    if missing:
        check("4a. real source artifacts are present on disk", False,
              str(missing))
        return
    events = _locked_events(PEER_UNIVERSE_JSON, ANCHOR_SHOCKS_CSVS)
    check(f"4a. the real committed artifacts derive exactly "
          f"{EXPECTED_N_EVENTS} event(s)",
          len(events) == EXPECTED_N_EVENTS, str(len(events)))
    check("4b. every derived event carries a non-empty peer and anchor ticker",
          all(e["peer_ticker"] and e["anchor_ticker"] for e in events))
    check("4c. every derived event carries a real, finite excess_return",
          all(isinstance(e["excess_return"], float) for e in events))
    check("4d. the 6 real qualifying peers/anchors are exactly what round "
          "7's own hand review found",
          {e["peer_ticker"] for e in events}
          == {"BHE", "GLUC", "OMCL", "SCSC", "TOMZ", "TRS"}
          and {e["anchor_ticker"] for e in events}
          == {"ABT", "CLX", "HWM", "JBL", "MCK", "SNX"})


def test_5_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("5a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("5a. network blocked", True)


if __name__ == "__main__":
    test_1_qualifying_rows_resolve_across_multiple_csvs_with_excess_return()
    test_2_duplicate_key_across_two_csvs_refuses()
    test_3_drift_between_universe_and_every_shocks_file_refuses()
    test_4_the_real_committed_artifacts_derive_exactly_195()
    test_5_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP07_PHASE2_LOCK TESTS PASSED")
    sys.exit(0)
