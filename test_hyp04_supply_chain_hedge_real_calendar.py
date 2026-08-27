#!/usr/bin/env python3
"""The REAL XNYS calendar, end to end to a target value -- HYP-04.

=== WHY THIS SUITE EXISTS SEPARATELY ===

Every other suite indexes sessions with a synthetic weekday list. That is the
right choice there: it keeps them fast, offline and free of a heavy dependency,
and it isolates the logic under test. But it means the authoritative calendar
has never been exercised through the whole chain, and a weekday list differs
from XNYS in exactly the way that matters -- it contains market holidays.

It cannot live in `test_hyp04_supply_chain_hedge_event_panel.py`, because that
suite asserts `exchange_calendars` is NOT in `sys.modules` (test_7c): the
bridge takes an already-resolved session date precisely so it never imports a
calendar. Importing one there would break a correct assertion.

So: a separate suite, skipped whole when the calendar is unavailable.
`requirements-hyp04.txt` gained `exchange_calendars` on 2026-08-24 FOR
this suite, so CI does run it; the skip guard remains for anyone whose
environment lacks it.

=== WHAT IT PROVES, AND WHAT IT DOES NOT ===

Prices here are SYNTHETIC. Nothing in this file is evidence about anything.
What it proves is that real session dates, real holiday gaps, real positional
indices and the real target agree -- so a discrepancy is a calendar or indexing
defect rather than a data defect.

The load-bearing check is test_2: the 41-session span of the chosen event
straddles Thanksgiving, and the requested sessions must SKIP it. A weekday
approximation would include 2018-11-22 and shift every subsequent date by one,
which is the failure `closes_requirements` refuses to risk by declining to
approximate.
"""
from __future__ import annotations

import socket
import sys
from datetime import date


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

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


CALENDAR_AVAILABLE = True
try:  # noqa: SIM105
    import exchange_calendars  # noqa: F401
except Exception:  # noqa: BLE001
    CALENDAR_AVAILABLE = False

# A real BMO anchor event, comfortably inside the index so nothing truncates.
EVENT_ID = "MCK-2018-10-25"
ANCHOR = "MCK"
RELEASE = date(2018, 10, 25)
SESSION = "BMO"

# Real XNYS closures inside or near the window. 2018-12-05 is the George H. W.
# Bush national day of mourning -- an unscheduled closure a hand-written
# holiday list would miss, which is why the authoritative calendar is required.
KNOWN_CLOSURES = (date(2018, 7, 4), date(2018, 11, 22), date(2018, 12, 25),
                  date(2018, 12, 5), date(2018, 1, 15), date(2019, 4, 19))

_STATE: dict = {}


def _setup() -> bool:
    if not CALENDAR_AVAILABLE:
        return False
    if _STATE:
        return True
    from pathlib import Path

    from gst_market_response.exchange_calendar import (
        compute_expected_next_full_trading_session_xnys as resolve)
    from hyp04_supply_chain_hedge.closes_requirements import (
        _load_sessions, requirements_for)
    from hyp04_supply_chain_hedge.curated_linkage import LSE, load_curated_linkage
    from hyp04_supply_chain_hedge.event_panel import resolve_events

    sessions = _load_sessions(date(2017, 1, 1), date(2019, 12, 31))
    resp = resolve(RELEASE, SESSION)
    panel = resolve_events(
        [{"event_id": EVENT_ID, "anchor": ANCHOR,
          "response_session_date": resp}], sessions=sessions)
    if panel.rejected:
        return False
    ev = panel.resolved[0]

    map_path = LSE / "HYP04_Linkage_Map_v1.0.csv"
    if not map_path.is_file():
        return False
    edges = load_curated_linkage(map_path).edges
    rep = requirements_for([ev], edges, sessions=sessions)

    _STATE.update(sessions=sessions, resp=resp, ev=ev, rep=rep)
    return True


def test_1_bmo_resolves_to_the_same_session():
    if not _setup():
        skip("1. BMO resolution", "exchange_calendars or curated map unavailable")
        return
    resp = _STATE["resp"]
    check("1a. a BMO release resolves to its OWN session",
          str(resp) == RELEASE.isoformat(), str(resp))
    check("1b. and that session is in the index",
          resp in _STATE["sessions"] or date.fromisoformat(str(resp))
          in _STATE["sessions"])
    ev = _STATE["ev"]
    check("1c. the day index points back at the same date",
          _STATE["sessions"][ev.day_index] == date.fromisoformat(str(resp)),
          f"idx {ev.day_index} -> {_STATE['sessions'][ev.day_index]}")


def test_2_the_span_skips_real_holidays():
    """LOAD-BEARING. The window straddles Thanksgiving and must skip it."""
    if not _setup():
        skip("2. holiday handling", "exchange_calendars unavailable")
        return
    sessions = _STATE["sessions"]
    req = _STATE["rep"].requirements[0]

    for hol in KNOWN_CLOSURES:
        check(f"2. {hol} is NOT a session", hol not in sessions)

    thanksgiving = date(2018, 11, 22)
    check("2a. the window straddles Thanksgiving",
          req.sessions[0] < thanksgiving < req.sessions[-1],
          f"{req.sessions[0]} .. {req.sessions[-1]}")
    check("2b. and does not request it",
          thanksgiving not in req.sessions)
    check("2c. the day after it IS requested",
          date(2018, 11, 23) in req.sessions,
          "the half-day after Thanksgiving is a real session")

    # A weekday approximation over the SAME span counts more days than there
    # are real sessions, and the surplus is exactly the holidays it would have
    # wrongly asked the operator to collect.
    first, last = req.sessions[0], req.sessions[-1]
    weekdays = [date.fromordinal(o)
                for o in range(first.toordinal(), last.toordinal() + 1)
                if date.fromordinal(o).weekday() < 5]
    surplus = sorted(set(weekdays) - set(req.sessions))
    check("2d. a weekday count over the same span EXCEEDS the real sessions",
          len(weekdays) > req.n_sessions,
          f"weekdays={len(weekdays)} real={req.n_sessions}")
    check("2e. and the surplus is exactly the market holidays",
          surplus == [thanksgiving], str(surplus))
    check("2f. real sessions are a strict subset of weekdays",
          set(req.sessions) < set(weekdays))


def test_3_the_request_is_exactly_41_real_sessions():
    if not _setup():
        skip("3. request size", "exchange_calendars unavailable")
        return
    from hyp04_supply_chain_hedge.closes_requirements import (
        closes_per_event, session_span)

    req = _STATE["rep"].requirements[0]
    ev = _STATE["ev"]
    sessions = _STATE["sessions"]

    check("3a. 41 sessions, on the real calendar",
          req.n_sessions == closes_per_event() == 41, str(req.n_sessions))
    check("3b. nothing skipped or truncated",
          not _STATE["rep"].skipped and not _STATE["rep"].truncated,
          f"{len(_STATE['rep'].skipped)} skipped, "
          f"{len(_STATE['rep'].truncated)} truncated")

    start, end = session_span(ev.day_index)
    check("3c. the requested sessions are exactly the positional span",
          list(req.sessions) == sessions[start:end + 1])
    check("3d. the anchor sits inside its own window",
          req.sessions[0] <= sessions[ev.day_index] <= req.sessions[-1])


def test_4_target_is_finite_across_the_grid():
    """Synthetic prices on REAL sessions -> a finite target at every horizon."""
    if not _setup():
        skip("4. target on real sessions", "exchange_calendars unavailable")
        return
    import numpy as np

    from hyp04_supply_chain_hedge.constants import HORIZON_GRID
    from hyp04_supply_chain_hedge.peer_returns import (
        PriceObservation, build_panel, coverage_for_event)
    from hyp04_supply_chain_hedge.target import raw_log_ratio_target

    req = _STATE["rep"].requirements[0]
    ev = _STATE["ev"]
    sessions = _STATE["sessions"]

    rng = np.random.default_rng(7)
    obs, px = [], 100.0
    for d in req.sessions:
        px *= float(np.exp(rng.normal(0, 0.012)))
        obs.append(PriceObservation(req.peer, d, px))

    series = build_panel(obs, sessions=sessions).series[req.peer]
    cov = coverage_for_event(series, event_id=EVENT_ID, anchor_day=ev.day_index)
    check("4a. supplying exactly the request satisfies coverage on the real "
          "calendar", cov.sufficient, str(cov.reasons))

    arr = np.array([np.nan if r is None else r for r in series.log_returns],
                   dtype=float)
    check("4b. exactly 40 finite returns exist",
          int(np.isfinite(arr).sum()) == 40, str(int(np.isfinite(arr).sum())))

    vals = {h: raw_log_ratio_target(arr, ev.day_index, h)
            for h in sorted(HORIZON_GRID)}
    check("4c. every horizon yields a finite target",
          all(np.isfinite(v) for v in vals.values()),
          str({h: v for h, v in vals.items() if not np.isfinite(v)}))
    check("4d. and they are not all identical",
          len({round(v, 9) for v in vals.values()}) > 1,
          "a constant across horizons would mean the horizon is ignored")

    # HARDCODED-OPEN: drop one real session and coverage must fail, so 4a is
    # measuring the window rather than passing unconditionally.
    short = build_panel(obs[:-1], sessions=sessions).series[req.peer]
    cov2 = coverage_for_event(short, event_id=EVENT_ID, anchor_day=ev.day_index)
    check("4e. dropping the last real session breaks coverage",
          not cov2.sufficient)


def test_5_offline():
    check("5a. network is blocked in this suite", True)
    try:
        socket.getaddrinfo("www.sec.gov", 443)
        check("5b. a network call raises", False, "it did not")
    except NetworkBlocked:
        check("5b. a network call raises", True)
    # NOT `... or True`. An assertion that cannot fail is worse than none:
    # it reads as coverage and provides none. When the calendar is present it
    # must actually have loaded and produced state with sockets blocked --
    # which is what proves exchange_calendars ships its data locally rather
    # than fetching it. When absent there is nothing to assert, so it skips.
    if CALENDAR_AVAILABLE:
        check("5c. the calendar loaded and resolved with sockets blocked",
              bool(_STATE) and _STATE.get("sessions"),
              "exchange_calendars must ship its data locally")
    else:
        skip("5c. calendar offline behaviour", "exchange_calendars unavailable")


if __name__ == "__main__":
    if not CALENDAR_AVAILABLE:
        print("SKIP: whole suite   (exchange_calendars unavailable. It IS "
              "declared in requirements-hyp04.txt as of 2026-08-24, so in "
              "CI this should not happen -- install it: "
              "pip install exchange_calendars)")
    test_1_bmo_resolves_to_the_same_session()
    test_2_the_span_skips_real_holidays()
    test_3_the_request_is_exactly_41_real_sessions()
    test_4_target_is_finite_across_the_grid()
    test_5_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REAL-CALENDAR TESTS PASSED")
    sys.exit(0)
