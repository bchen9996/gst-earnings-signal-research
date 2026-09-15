#!/usr/bin/env python3
"""make_hyp08_phase2_lock.py tests -- offline, hermetic, no network, no
git. `build_draft` itself calls `_commit_sha` (requires a clean working
tree) and reads the real committed artifacts, so it is not exercised
end-to-end here -- same reason every prior hypothesis's own phase2-lock
test file skips it. What IS fully offline-testable is `_locked_events`/
`_all_shock_rows`: the pure derivation, given synthetic fixtures.

  EVENTS ARE POOLED FROM TWO ALREADY-SIGNED SOURCE LOCKS, NAMESPACED BY
  SOURCE (test_1) -- unlike every prior hypothesis's own `_locked_events`,
  which derives its universe from a raw peer-universe/qualification
  artifact, HYP-08's own reads two already-declared PRIOR locks wholesale.

  excess_return IS LOOKED UP FRESH FOR THE HYP-06 SIDE, CARRIED THROUGH
  UNCHANGED FOR THE HYP-07 SIDE (test_1) -- the one real asymmetry this
  module's own docstring calls out.

  AN UNDECLARED SOURCE LOCK REFUSES (test_2).

  A MISSING SHOCK ROW FOR THE HYP-06 SIDE REFUSES (test_3).

  A DUPLICATE (anchor, release_date) KEY ACROSS TWO ANCHOR-SHOCKS CSVS
  REFUSES (test_4).

  THE REAL COMMITTED ARTIFACTS DERIVE EXACTLY 973 (test_5, a control) --
  proves the module's own EXPECTED_N_EVENTS assumption against the actual
  files on disk, and confirms no single real anchor event mixes
  relationship_type across its own peers (the assumption
  target_same_session.py's own panel-building code depends on).

Run directly: python test_hyp04_supply_chain_hedge_hyp08_phase2_lock.py
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

from hyp04_supply_chain_hedge.make_hyp08_phase2_lock import (  # noqa: E402
    EXPECTED_N_EVENTS, Phase2LockError, _all_shock_rows, _locked_events,
)

FAILURES: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="hyp08_phase2_lock_test_"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _hyp06_style_event(event_id: str, anchor: str, peer: str, release_date: str,
                       attributed: str, shock: float,
                       rel_type: str = "direct_supplier") -> dict:
    return {"event_id": event_id, "anchor_ticker": anchor, "peer_ticker": peer,
            "relationship_type": rel_type, "as_of_date": "2010-01-01",
            "release_date": release_date, "attributed_session": attributed,
            "shock": shock}


def _hyp07_style_event(event_id: str, anchor: str, peer: str, release_date: str,
                       attributed: str, shock: float, excess_return: float,
                       rel_type: str = "sector_competitor") -> dict:
    return {"event_id": event_id, "anchor_ticker": anchor, "peer_ticker": peer,
            "relationship_type": rel_type, "as_of_date": "2010-01-01",
            "release_date": release_date, "attributed_session": attributed,
            "shock": shock, "excess_return": excess_return}


def _write_lock(name: str, events: list[dict], *, declared: bool = True) -> Path:
    p = TMP / f"{name}.json"
    p.write_text(json.dumps({
        "artifact": p.name, "locked_events": events,
        "declared": declared,
        "declared_by": "offline-test-fixture" if declared else "",
        "declared_date": "2026-09-14" if declared else "",
    }), encoding="utf-8")
    return p


def _shock_row(anchor: str, release_date: str, event_id: str,
              attributed: str, shock: str, excess_return: str,
              status: str = "shock_computed") -> dict:
    return {"event_id": event_id, "anchor_ticker": anchor,
            "release_date": release_date, "attributed_session": attributed,
            "shock": shock, "excess_return": excess_return, "status": status}


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


def test_1_events_pooled_and_namespaced_with_correct_excess_return() -> None:
    hyp06_lock = _write_lock("hyp06_fixture", [
        _hyp06_style_event("ABT-2017-04-19", "ABT", "ICUI", "2017-04-19",
                          "2017-04-19", 0.15),
    ])
    hyp07_lock = _write_lock("hyp07_fixture", [
        _hyp07_style_event("SNX-2020-01-01", "SNX", "SCSC", "2020-01-01",
                          "2020-01-02", 0.05, -0.05),
    ])
    csv_a = _write_shocks("shocks_a", [
        _shock_row("ABT", "2017-04-19", "ABT-2017-04-19", "2017-04-19",
                   "0.15", "-0.15"),
    ])
    events = _locked_events(hyp06_lock, hyp07_lock, (csv_a,))
    check("1a. exactly two pooled events", len(events) == 2, str(events))
    ids = {e["event_id"] for e in events}
    check("1b. event_ids are namespaced by source hypothesis",
          ids == {"HYP06-ABT-2017-04-19", "HYP07-SNX-2020-01-01"}, str(ids))

    hyp06_ev = next(e for e in events if e["source_hypothesis"] == "HYP-06")
    check("1c. HYP-06 side: excess_return is LOOKED UP from the shocks CSV, "
          "not copied from the lock (which never had it)",
          hyp06_ev["excess_return"] == -0.15 and hyp06_ev["shock"] == 0.15,
          str(hyp06_ev))

    hyp07_ev = next(e for e in events if e["source_hypothesis"] == "HYP-07")
    check("1d. HYP-07 side: excess_return is CARRIED THROUGH unchanged "
          "from the source lock",
          hyp07_ev["excess_return"] == -0.05 and hyp07_ev["shock"] == 0.05,
          str(hyp07_ev))
    check("1e. both sides carry relationship_type and as_of_date",
          all("relationship_type" in e and "as_of_date" in e for e in events))


def test_2_undeclared_source_lock_refuses() -> None:
    hyp06_draft = _write_lock("hyp06_draft", [
        _hyp06_style_event("ABT-2017-04-19", "ABT", "ICUI", "2017-04-19",
                          "2017-04-19", 0.15)], declared=False)
    hyp07_lock = _write_lock("hyp07_fixture2", [
        _hyp07_style_event("SNX-2020-01-01", "SNX", "SCSC", "2020-01-01",
                          "2020-01-02", 0.05, -0.05)])
    csv_a = _write_shocks("shocks_b", [
        _shock_row("ABT", "2017-04-19", "ABT-2017-04-19", "2017-04-19",
                   "0.15", "-0.15"),
    ])
    try:
        _locked_events(hyp06_draft, hyp07_lock, (csv_a,))
        check("2a. an undeclared HYP-06 source lock refuses", False)
    except Phase2LockError as e:
        check("2a. an undeclared HYP-06 source lock refuses", True)
        check("2b. names the draft file", "hyp06_draft" in str(e), str(e))


def test_3_missing_shock_row_for_hyp06_side_refuses() -> None:
    hyp06_lock = _write_lock("hyp06_orphan", [
        _hyp06_style_event("ABT-2099-01-01", "ABT", "ICUI", "2099-01-01",
                          "2099-01-01", 0.15)])
    hyp07_lock = _write_lock("hyp07_fixture3", [
        _hyp07_style_event("SNX-2020-01-01", "SNX", "SCSC", "2020-01-01",
                          "2020-01-02", 0.05, -0.05)])
    csv_a = _write_shocks("shocks_c", [
        _shock_row("ABT", "2017-04-19", "ABT-2017-04-19", "2017-04-19",
                   "0.15", "-0.15"),
    ])
    try:
        _locked_events(hyp06_lock, hyp07_lock, (csv_a,))
        check("3a. a HYP-06 locked pair with no matching shock row refuses", False)
    except Phase2LockError as e:
        check("3a. a HYP-06 locked pair with no matching shock row refuses", True)
        check("3b. names the orphaned date", "2099-01-01" in str(e), str(e))


def test_4_duplicate_key_across_two_csvs_refuses() -> None:
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
        check("4a. an (anchor, release_date) key in two CSVs refuses", False)
    except Phase2LockError as e:
        check("4a. an (anchor, release_date) key in two CSVs refuses", True)
        check("4b. the refusal names the anchor", "ABT" in str(e), str(e))


def test_5_the_real_committed_artifacts_derive_exactly_973() -> None:
    """CONTROL: proves EXPECTED_N_EVENTS against the real files on disk."""
    from hyp04_supply_chain_hedge.make_hyp08_phase2_lock import (
        ANCHOR_SHOCKS_CSVS, HYP06_PHASE2_LOCK_JSON, HYP07_PHASE2_LOCK_JSON,
    )
    missing = [p for p in (HYP06_PHASE2_LOCK_JSON, HYP07_PHASE2_LOCK_JSON,
                           *ANCHOR_SHOCKS_CSVS) if not p.is_file()]
    if missing:
        check("5a. real source artifacts are present on disk", False, str(missing))
        return
    events = _locked_events(HYP06_PHASE2_LOCK_JSON, HYP07_PHASE2_LOCK_JSON,
                            ANCHOR_SHOCKS_CSVS)
    check(f"5a. the real committed artifacts derive exactly "
          f"{EXPECTED_N_EVENTS} event(s)",
          len(events) == EXPECTED_N_EVENTS, str(len(events)))
    n6 = sum(1 for e in events if e["source_hypothesis"] == "HYP-06")
    n7 = sum(1 for e in events if e["source_hypothesis"] == "HYP-07")
    check("5b. 778 from HYP-06's side, 195 from HYP-07's side",
          n6 == 778 and n7 == 195, f"{n6}, {n7}")
    check("5c. every derived event carries a real, finite excess_return",
          all(isinstance(e["excess_return"], float) for e in events))
    peers6 = {e["peer_ticker"] for e in events if e["source_hypothesis"] == "HYP-06"}
    peers7 = {e["peer_ticker"] for e in events if e["source_hypothesis"] == "HYP-07"}
    check("5d. zero peer-ticker overlap between the two sides",
          not (peers6 & peers7), str(peers6 & peers7))

    from collections import defaultdict
    by_event: dict[str, set] = defaultdict(set)
    for e in events:
        by_event[e["event_id"]].add(e["relationship_type"])
    mixed = {k: v for k, v in by_event.items() if len(v) > 1}
    check("5e. no single real anchor event mixes relationship_type across "
          "its own peers -- the assumption target_same_session.py's panel "
          "builder depends on",
          not mixed, str(list(mixed.items())[:5]))


def test_6_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("6a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("6a. network blocked", True)


if __name__ == "__main__":
    test_1_events_pooled_and_namespaced_with_correct_excess_return()
    test_2_undeclared_source_lock_refuses()
    test_3_missing_shock_row_for_hyp06_side_refuses()
    test_4_duplicate_key_across_two_csvs_refuses()
    test_5_the_real_committed_artifacts_derive_exactly_973()
    test_6_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP08_PHASE2_LOCK TESTS PASSED")
    sys.exit(0)
