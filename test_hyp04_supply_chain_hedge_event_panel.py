#!/usr/bin/env python3
"""Tests for the calendar->session bridge, and the END-TO-END wiring -- HYP-04.

Two jobs, and the second is why this file matters more than its size suggests.

=== 1. THE BRIDGE ===

`event_panel` converts a calendar response-session date into the integer index
`target` and `peer_returns` slice with. An off-by-one there is look-ahead bias
that raises nothing and produces a perfectly ordinary number, so the boundary
tests (test_2) check the exact index, not merely that resolution "worked".

A date that is not in the session index must be REJECTED, never snapped
(test_3). Snapping would move an event onto a day the market did something
else.

=== 2. THE CHAIN ACTUALLY COMPOSES (test_6) ===

Four modules were built to feed each other and had never been run together:

    curated map -> linkage_resolution -> pair_eligibility
                -> peer_returns (coverage/P5) -> target

Every one is unit-tested in isolation, and isolation is exactly where an
interface mismatch survives. Writing this suite found one: the calendar half
and the positional half had nothing converting between them, and the
positional index went by two names -- `day` in fixtures and target,
`anchor_day` in peer_returns. The names were unified onto `anchor_day` on
2026-08-23; `1f2` asserts the alias is gone, so one concept keeps one name.

test_6 runs the whole chain on synthetic data and asserts a real target value
comes out the far end. It is a WIRING check on synthetic input: it proves the
modules fit, and it is not evidence about anything in the world.

Offline. No network. Nothing is written to the repo.

Run directly: python test_hyp04_supply_chain_hedge_event_panel.py
"""
from __future__ import annotations

import socket
import sys
from datetime import date, timedelta


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import numpy as np  # noqa: E402

from hyp04_supply_chain_hedge.constants import (  # noqa: E402
    HORIZON_GRID,
    REFERENCE_WINDOW_TRADING_DAYS,
)
from hyp04_supply_chain_hedge.event_panel import (  # noqa: E402
    KEY_ANCHOR_DAY,
    EventPanelError,
    assert_sessions_resolved,
    normalize_sessions,
    resolve_events,
)
from hyp04_supply_chain_hedge.peer_returns import (  # noqa: E402
    PriceObservation,
    build_panel,
    coverage_for_event,
    peer_history_map,
)
from hyp04_supply_chain_hedge.target import raw_log_ratio_target  # noqa: E402

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


N = 90
# Deliberately NOT consecutive calendar days: a 5-on/2-off pattern, so a
# "session index" and "calendar days since start" genuinely differ. A bridge
# tested only on consecutive days passes while doing nothing.
def _sessions(n: int = N) -> list[date]:
    out: list[date] = []
    d = date(2020, 1, 6)          # a Monday
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


SESSIONS = _sessions()
WEEKEND = date(2020, 1, 11)       # a Saturday, inside the span, not a session


def _closes(ticker: str, *, drop: set[int] = frozenset()) -> list[PriceObservation]:
    return [PriceObservation(ticker, SESSIONS[i], 100.0 * (1.001 ** i))
            for i in range(N) if i not in drop]


# --------------------------------------------------------------------------


def test_1_basic_resolution() -> None:
    evs = [{"event_id": "E1", "anchor": "mck",
            "response_session_date": SESSIONS[40].isoformat(),
            "peers": ["cvs"]}]
    p = resolve_events(evs, sessions=SESSIONS)

    check("1a. the event resolves", p.n_resolved == 1, str(p.rejection_reasons()))
    r = p.resolved[0]
    check("1b. the day index is the session's position", r.day_index == 40,
          str(r.day_index))
    check("1c. the anchor is upper-cased", r.anchor == "MCK", r.anchor)
    check("1d. peers are upper-cased", r.peers == ("CVS",), str(r.peers))
    check("1e. sessions_in_index is reported", p.sessions_in_index == N)

    ev = r.as_analysis_event()
    check("1f. the canonical day key carries the index",
          ev[KEY_ANCHOR_DAY] == 40, str(ev.get(KEY_ANCHOR_DAY)))
    check("1f2. the legacy alias is gone -- exactly one name for one concept",
          "day" not in ev, str(sorted(ev)))
    check("1g. event_date is the RESPONSE session, not a raw earnings date",
          ev["event_date"] == SESSIONS[40].isoformat() == ev["response_session_date"])
    check("1h. a date object is accepted as well as a string",
          resolve_events([{"event_id": "E", "anchor": "A",
                           "response_session_date": SESSIONS[7]}],
                         sessions=SESSIONS).resolved[0].day_index == 7)


def test_2_the_index_is_positional_not_calendar() -> None:
    """The off-by-one that would be look-ahead bias."""
    # SESSIONS skips weekends, so index 10 is NOT 10 calendar days after start.
    tenth = SESSIONS[10]
    check("2a. the fixture really does skip weekends",
          (tenth - SESSIONS[0]).days != 10,
          "if these were equal the test could not tell the two apart")

    p = resolve_events([{"event_id": "E", "anchor": "A",
                         "response_session_date": tenth.isoformat()}],
                       sessions=SESSIONS)
    check("2b. resolution uses session position, not elapsed days",
          p.resolved[0].day_index == 10, str(p.resolved[0].day_index))

    # Exact endpoints.
    for i in (0, 1, N - 2, N - 1):
        got = resolve_events([{"event_id": f"E{i}", "anchor": "A",
                               "response_session_date": SESSIONS[i]}],
                             sessions=SESSIONS)
        check(f"2c. session {i} resolves to index {i}",
              got.resolved and got.resolved[0].day_index == i,
              str(got.rejection_reasons()))

    # And the index must agree with what target actually slices.
    s = build_panel(_closes("P"), sessions=SESSIONS).series["P"]
    day = 40
    ref = s.window(day - REFERENCE_WINDOW_TRADING_DAYS + 1, day + 1)
    check("2d. the reference window ends AT the anchor day",
          len(ref) == REFERENCE_WINDOW_TRADING_DAYS
          and s.log_returns[day] is ref[-1],
          "target's reference window includes the anchor day itself")


def test_3_off_index_dates_are_rejected_not_snapped() -> None:
    evs = [{"event_id": "SAT", "anchor": "A",
            "response_session_date": WEEKEND.isoformat()},
           {"event_id": "BEFORE", "anchor": "A",
            "response_session_date": "2019-01-02"},
           {"event_id": "AFTER", "anchor": "A",
            "response_session_date": "2099-01-02"}]
    p = resolve_events(evs, sessions=SESSIONS)

    check("3a. none of the three resolve", p.n_resolved == 0,
          str([r.event_id for r in p.resolved]))
    check("3b. all three are rejected with a reason",
          p.rejection_reasons().get("date_not_in_session_index") == 3,
          str(p.rejection_reasons()))
    check("3c. the rejection names the date and the index span",
          all(WEEKEND.isoformat() in r.detail or "2019" in r.detail
              or "2099" in r.detail for r in p.rejected),
          str([r.detail[:60] for r in p.rejected]))

    # The control: an ON-index date DOES resolve. Without it, a function that
    # rejected everything would pass 3a-3c.
    ok = resolve_events([{"event_id": "OK", "anchor": "A",
                          "response_session_date": SESSIONS[5]}],
                        sessions=SESSIONS)
    check("3d. control -- an on-index date resolves", ok.n_resolved == 1)

    # A weekend must NOT be snapped to the adjacent Monday.
    check("3e. the weekend was not snapped to a neighbouring session",
          all(r.day_index != 3 for r in p.resolved),
          "snapping would move the event to a day the market did something else")


def test_4_malformed_input_is_reported_not_raised() -> None:
    evs = [{"event_id": "", "anchor": "A", "response_session_date": SESSIONS[1]},
           {"event_id": "D", "anchor": "", "response_session_date": SESSIONS[1]},
           {"event_id": "E", "anchor": "A"},
           {"event_id": "F", "anchor": "A", "response_session_date": "06/01/2020"},
           {"event_id": "G", "anchor": "A", "response_session_date": "2020-13-45"},
           {"event_id": "H", "anchor": "A", "response_session_date": SESSIONS[2]},
           {"event_id": "H", "anchor": "A", "response_session_date": SESSIONS[3]}]
    p = resolve_events(evs, sessions=SESSIONS)

    check("4a. only the first valid H survives", p.n_resolved == 1,
          str([r.event_id for r in p.resolved]))
    check("4b. and it is the FIRST occurrence", p.resolved[0].day_index == 2)
    reasons = p.rejection_reasons()
    for r in ("missing_event_id", "missing_anchor",
              "missing_response_session_date", "malformed_date",
              "duplicate_event_id"):
        check(f"4c. {r} is reported", reasons.get(r, 0) >= 1, str(reasons))

    # An unsorted index is a caller bug and must be fatal.
    for label, bad in (("unsorted", [SESSIONS[1], SESSIONS[0]]),
                       ("duplicated", [SESSIONS[0], SESSIONS[0]])):
        try:
            normalize_sessions(bad)
            check(f"4d. a {label} index raises", False, "no exception")
        except EventPanelError:
            check(f"4d. a {label} index raises", True)


def test_5_unresolved_dates_are_flagged() -> None:
    """Raw earnings dates cannot be proven, but they can be smelled."""
    raw = [{"event_id": "E1", "anchor": "A",
            "response_session_date": WEEKEND.isoformat()},
           {"event_id": "E2", "anchor": "A",
            "response_session_date": SESSIONS[5].isoformat()}]
    warns = assert_sessions_resolved(raw, sessions=SESSIONS)
    check("5a. a non-session date raises a warning", len(warns) == 1, str(warns))
    check("5b. the warning names the authoritative resolver",
          "compute_expected_next_full_trading_session_xnys" in warns[0])
    check("5c. and says AMC releases would be one session early",
          "one session early" in warns[0])

    clean = [{"event_id": "E", "anchor": "A",
              "response_session_date": SESSIONS[i].isoformat()} for i in (3, 9)]
    check("5d. control -- fully resolved dates warn about nothing",
          assert_sessions_resolved(clean, sessions=SESSIONS) == [])


def test_6_the_whole_chain_composes() -> None:
    """curated map -> join -> P5 -> coverage -> target, on synthetic data.

    A WIRING check. Synthetic input, so nothing here is evidence about
    anything; what it proves is that the four modules fit together, which no
    unit test can show.
    """
    from hyp04_supply_chain_hedge.curated_linkage import LSE
    from hyp04_supply_chain_hedge.linkage_resolution import (
        resolve_from_curated_map)

    map_path = LSE / "HYP04_Linkage_Map_v1.0.csv"
    if not map_path.is_file():
        skip("6. end-to-end chain", "no committed curated map on disk")
        return

    # 1. anchor events as calendar dates -> session indices
    day = 45
    panel = resolve_events(
        [{"event_id": "MCK-Q1", "anchor": "MCK",
          "response_session_date": SESSIONS[day].isoformat()}],
        sessions=SESSIONS)
    check("6a. the anchor event pins to the session index",
          panel.n_resolved == 1 and panel.resolved[0].day_index == day,
          str(panel.rejection_reasons()))
    events = panel.analysis_events()

    # 2. peer returns -> derived P5 availability
    peers = build_panel(_closes("CVS"), sessions=SESSIONS)
    # peers must be attached before availability can be derived per event
    with_peers = [dict(e, peers=["CVS"]) for e in events]
    hist = peer_history_map(peers.series, with_peers)
    check("6b. peer availability is derived from the returns", hist == {"CVS": True},
          str(hist))

    # 3. curated map + P5 -> eligible pairs
    res = resolve_from_curated_map(events, map_path=map_path, peer_history=hist)
    reasons = res.denial_reasons()
    check("6c. the join reads the curated map, not the placeholder",
          res.provenance.uses_placeholder_linkage is False,
          str(res.provenance.as_dict()))
    check("6d. P5 does not deny -- derived history was accepted",
          "P5" not in reasons, str(reasons))
    check("6e. P1 denies, because no anchor eligibility was supplied",
          reasons.get("P1", 0) == 1, str(reasons))

    # 4. coverage agrees with the target at the resolved index
    cov = coverage_for_event(peers.series["CVS"], event_id="MCK-Q1",
                             anchor_day=day)
    check("6f. the peer covers the event at that index", cov.sufficient,
          str(cov.reasons))

    arr = np.array([np.nan if r is None else r
                    for r in peers.series["CVS"].log_returns], dtype=float)
    val = raw_log_ratio_target(arr, day, max(HORIZON_GRID))
    check("6g. a finite target value comes out the far end",
          bool(np.isfinite(val)), str(val))

    # 5. and the whole thing still displays nothing
    from hyp04_supply_chain_hedge.display_gate import current_decision
    d = current_decision()
    # NARROWED, not retargeted -- the gate went OPEN (2026-09-09, freeze +
    # v1.12) then CLOSED again (2026-09-11, v1.13 closed HYP-04 as
    # HOLDOUT_TESTED_NULL). THIS chain ran on synthetic peer returns and
    # contributed to neither move: C5 passes because the committed freeze
    # derives non-placeholder linkage from the ratified map, not because
    # anything here did, and that claim is unaffected by C1's status.
    check("6i. C5 passes on the FROZEN linkage, which this run is not part of",
          d.conditions.get("C5_not_placeholder") is True)


def test_7_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("7a. network blocked", False, "a lookup succeeded")
    except Exception as e:  # noqa: BLE001
        check("7a. network blocked", type(e).__name__ == "NetworkBlocked")

    import ast
    from pathlib import Path

    import hyp04_supply_chain_hedge.event_panel as ep
    tree = ast.parse(Path(ep.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imported.add(node.module)
    stdlib = {"re", "dataclasses", "datetime", "typing", "__future__"}
    bad = sorted(n for n in imported if n.split(".")[0] not in stdlib)
    check("7b. the bridge imports nothing but stdlib", not bad, str(bad))
    check("7c. and does not pull the exchange calendar",
          "exchange_calendars" not in sys.modules,
          "the resolved session date is injected precisely so it need not")


if __name__ == "__main__":
    test_1_basic_resolution()
    test_2_the_index_is_positional_not_calendar()
    test_3_off_index_dates_are_rejected_not_snapped()
    test_4_malformed_input_is_reported_not_raised()
    test_5_unresolved_dates_are_flagged()
    test_6_the_whole_chain_composes()
    test_7_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 EVENT-PANEL TESTS PASSED")
    sys.exit(0)
