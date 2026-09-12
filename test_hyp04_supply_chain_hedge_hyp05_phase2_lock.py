#!/usr/bin/env python3
"""make_hyp05_phase2_lock.py tests -- offline, hermetic, no network, no git.

`build_draft` itself calls `_commit_sha` (requires a clean working tree)
and reads the real committed artifacts, so it is not exercised end-to-end
here -- the same reason HYP-04's own `make_phase2_lock.py` has no offline
test of `build_draft` either. What IS fully offline-testable, and tested
here, is `_locked_events`: the pure derivation of the locked event set
from two input files, given synthetic fixtures shaped like the real
`HYP05_PEER_UNIVERSE_HAND_CURATED_2026-09-12.json` and
`HYP04_ANCHOR_SHOCKS_2026-08-31.csv`.

  ONLY QUALIFYING AMBA/NVDA ROWS SURVIVE (test_1) -- a non-qualifying row,
  a different peer, and a different anchor are all excluded.

  DRIFT BETWEEN THE TWO SOURCE FILES REFUSES (test_2) -- a qualifying date
  with no matching anchor-shocks row must not be silently dropped or
  guessed at.

  THE REAL COMMITTED ARTIFACTS DERIVE EXACTLY 8 (test_3, a control) --
  proves the module's own EXPECTED_N_EVENTS assumption against the actual
  files on disk, not just a synthetic fixture.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_hyp05_phase2_lock.py
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

from hyp04_supply_chain_hedge.make_hyp05_phase2_lock import (  # noqa: E402
    EXPECTED_N_EVENTS, Phase2LockError, _locked_events,
)

FAILURES: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="hyp05_phase2_lock_test_"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _qual(ticker: str, anchor: str, event_date: str, qualifies: bool) -> dict:
    return {
        "ticker": ticker,
        "qualifies": qualifies,
        "evidence": {"candidate": {"anchor_ticker": anchor,
                                    "anchor_event_date": event_date}},
    }


def _shock_row(anchor: str, release_date: str, event_id: str,
              attributed: str, shock: str) -> dict:
    return {"event_id": event_id, "anchor_ticker": anchor,
            "release_date": release_date, "attributed_session": attributed,
            "shock": shock}


def _write_universe(qualifications: list[dict]) -> Path:
    p = TMP / f"universe_{len(qualifications)}_{id(qualifications)}.json"
    p.write_text(json.dumps({"qualifications": qualifications}), encoding="utf-8")
    return p


def _write_shocks(rows: list[dict]) -> Path:
    import csv
    p = TMP / f"shocks_{len(rows)}_{id(rows)}.csv"
    fields = ["event_id", "anchor_ticker", "release_date",
              "attributed_session", "shock"]
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return p


def test_1_only_qualifying_amba_nvda_rows_survive() -> None:
    universe = _write_universe([
        _qual("AMBA", "NVDA", "2016-05-12", True),
        _qual("AMBA", "NVDA", "2016-11-10", False),   # not qualifying
        _qual("GPRO", "JBL", "2017-10-19", True),      # different peer
        _qual("AMBA", "INTC", "2018-01-01", True),     # different anchor
    ])
    shocks = _write_shocks([
        _shock_row("NVDA", "2016-05-12", "NVDA-2016-05-12", "2016-05-13", "0.15"),
        _shock_row("NVDA", "2016-11-10", "NVDA-2016-11-10", "2016-11-11", "0.26"),
        _shock_row("JBL", "2017-10-19", "JBL-2017-10-19", "2017-10-20", "0.05"),
        _shock_row("INTC", "2018-01-01", "INTC-2018-01-01", "2018-01-02", "0.03"),
    ])
    events = _locked_events(universe, shocks)
    check("1a. exactly one event survives", len(events) == 1, str(events))
    check("1b. it is the qualifying AMBA/NVDA row",
          events and events[0]["event_id"] == "NVDA-2016-05-12", str(events))


def test_2_drift_between_source_files_refuses() -> None:
    universe = _write_universe([
        _qual("AMBA", "NVDA", "2099-01-01", True),   # no matching shock row
    ])
    shocks = _write_shocks([
        _shock_row("NVDA", "2016-05-12", "NVDA-2016-05-12", "2016-05-13", "0.15"),
    ])
    try:
        _locked_events(universe, shocks)
        check("2a. drift between the two source files refuses", False,
              "it returned instead of raising")
    except Phase2LockError as e:
        check("2a. drift between the two source files refuses", True)
        check("2b. the refusal names the orphaned date",
              "2099-01-01" in str(e), str(e))


def test_3_the_real_committed_artifacts_derive_exactly_eight() -> None:
    """CONTROL: proves EXPECTED_N_EVENTS against the real files on disk."""
    from hyp04_supply_chain_hedge.make_hyp05_phase2_lock import (
        ANCHOR_SHOCKS_CSV, PEER_UNIVERSE_JSON,
    )
    if not (PEER_UNIVERSE_JSON.is_file() and ANCHOR_SHOCKS_CSV.is_file()):
        check("3a. real source artifacts are present on disk", False,
              f"{PEER_UNIVERSE_JSON} / {ANCHOR_SHOCKS_CSV}")
        return
    events = _locked_events(PEER_UNIVERSE_JSON, ANCHOR_SHOCKS_CSV)
    check(f"3a. the real committed artifacts derive exactly "
          f"{EXPECTED_N_EVENTS} event(s)",
          len(events) == EXPECTED_N_EVENTS, str(len(events)))
    check("3b. every derived event is a real NVDA event_id",
          all(e["event_id"].startswith("NVDA-") for e in events), str(events))


def test_4_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("4a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("4a. network blocked", True)


if __name__ == "__main__":
    test_1_only_qualifying_amba_nvda_rows_survive()
    test_2_drift_between_source_files_refuses()
    test_3_the_real_committed_artifacts_derive_exactly_eight()
    test_4_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP05_PHASE2_LOCK TESTS PASSED")
    sys.exit(0)
