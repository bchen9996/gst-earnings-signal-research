#!/usr/bin/env python3
"""HYP-04 session-index tests. OFFLINE (exchange_calendars ships its own data).

This module exists because a second calendar is a second answer to a question
that already has one, and the failure mode is silent: a session off by one is
look-ahead that raises nothing.

So the load-bearing test is not "the index is wide enough" -- it is that the
wider index AGREES with the authoritative one everywhere they overlap, and that
the refusal fires when it does not (test_2).

Run directly: python test_hyp04_supply_chain_hedge_sessions.py
"""
from __future__ import annotations

import socket
import sys
from datetime import date

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


try:
    import exchange_calendars  # noqa: F401
    HAVE_CALENDAR = True
except Exception:
    HAVE_CALENDAR = False

from hyp04_supply_chain_hedge.sessions import (  # noqa: E402
    CALENDAR_NAME,
    DEFAULT_INDEX_START,
    SessionIndexError,
    calendar_id,
    sessions_for_release_dates,
    verify_agreement,
    xnys_sessions,
)


def test_1_the_wider_index_reaches_the_calendar_it_must() -> None:
    print("\n--- 1: it reaches back far enough to be worth having ---")
    if not HAVE_CALENDAR:
        skip("1. wider index", "exchange_calendars unavailable")
        return

    # The anchor calendar's earliest release is 2003-08-07. The authoritative
    # instance starts about 20 years before TODAY on a rolling window (see
    # test_2d), which is why this module exists at all.
    s = xnys_sessions(date(2003, 1, 1), date(2003, 12, 31))
    check("1a. 2003 is reachable at all", len(s) > 0, str(len(s)))
    check("1b. and holds a full year of sessions", 248 <= len(s) <= 256,
          str(len(s)))
    check("1c. weekends are excluded", all(d.weekday() < 5 for d in s))
    # A real holiday inside the era the authoritative calendar cannot see.
    check("1d. 2003-07-04 is not a session", date(2003, 7, 4) not in s)
    check("1e. 2003-07-03 IS a session", date(2003, 7, 3) in s)
    check("1f. sessions come back ordered", s == sorted(s))
    check("1g. the calendar implementation is recorded, not assumed",
          calendar_id().startswith(CALENDAR_NAME + "_exchange_calendars_v"),
          calendar_id())


def test_2_it_refuses_to_disagree_with_the_authoritative_calendar() -> None:
    """THE LOAD-BEARING ONE. Wider is only safe if it is otherwise identical."""
    print("\n--- 2: agreement with the authoritative instance ---")
    if not HAVE_CALENDAR:
        skip("2. agreement", "exchange_calendars unavailable")
        return

    r = verify_agreement()
    check("2a. the two calendars agree over their whole overlap",
          r["agrees"] is True, str(r["disagreements"]))
    check("2b. and the overlap is large enough for that to mean something",
          r["overlap_sessions"] > 4000, str(r["overlap_sessions"]))
    check("2c. the wider one really does start earlier",
          r["wide_first_session"] < r["authoritative_first_session"],
          f'{r["wide_first_session"]} vs {r["authoritative_first_session"]}')
    # MEASURED 2026-09-01: the bound is not a fixed default, it ROLLS. The
    # authoritative instance spans exactly 21 years ending a year ahead, so its
    # first session is today minus 20 years and MOVES FORWARD ONE DAY PER DAY.
    # It read 2006-08-31 yesterday and 2006-09-01 today, with no code change.
    #
    # This test asserted the literal date and broke overnight. The date was
    # never the point; the property is. And the property is worse than a fixed
    # default: anything resolving sessions through that instance silently loses
    # its oldest day every day, so an event in range today can be out of range
    # tomorrow. That is the strongest form of the reason this module exists.
    today = date.today()
    first = date.fromisoformat(r["authoritative_first_session"])
    age = (today - first).days / 365.25
    check("2d. the authoritative first session is a ROLLING default about 20 "
          "years back -- not a data limit, and not even a fixed one",
          19.0 <= age <= 21.5, f'{r["authoritative_first_session"]} '
          f'({age:.2f}y before {today.isoformat()})')
    check("2d2. and it is far later than HYP-04's fixed start, which is the "
          "whole reason this module exists",
          first > date.fromisoformat(r["wide_first_session"]),
          f'{first} vs {r["wide_first_session"]}')

    # CONTROL -- a guard nobody has seen fail is not known to work. Force a
    # disagreement with a calendar that really is different, and require both
    # the report and the accessor to refuse.
    import exchange_calendars as xcals

    other = xcals.get_calendar("XLON", start="2010-01-01")
    wide = xcals.get_calendar(CALENDAR_NAME, start="2010-01-01")
    bad = verify_agreement(wide=wide, authoritative=other)
    check("2e. CONTROL -- a genuinely different calendar is caught",
          bad["agrees"] is False and bad["disagreements"] > 0,
          str(bad["disagreements"]))
    check("2f. CONTROL -- and the disagreeing dates are NAMED, not just counted",
          bool(bad["only_in_wide"] or bad["only_in_authoritative"]))


def test_3_it_fails_closed_on_a_range_it_cannot_serve() -> None:
    print("\n--- 3: clipping is refused ---")
    if not HAVE_CALENDAR:
        skip("3. bounds", "exchange_calendars unavailable")
        return

    # A clipped index LOOKS complete, which is why this raises instead of
    # trimming -- the same reason closes_requirements reports `truncated`
    # rather than shortening a window.
    try:
        xnys_sessions(date(1970, 1, 1), date(1971, 1, 1))
        check("3a. a range before the index start is refused", False,
              "it returned")
    except SessionIndexError as e:
        check("3a. a range before the index start is refused",
              "before the index start" in str(e), str(e)[:80])

    try:
        xnys_sessions(date(2005, 1, 1), date(2004, 1, 1))
        check("3b. an inverted range is refused", False, "it returned")
    except SessionIndexError as e:
        check("3b. an inverted range is refused", "empty range" in str(e))

    check("3c. CONTROL -- a range inside the index is served",
          len(xnys_sessions(date(2004, 1, 1), date(2004, 3, 31))) > 50)
    check("3d. the start is a STATED choice, not open-ended",
          DEFAULT_INDEX_START == "1995-01-01", DEFAULT_INDEX_START)


def test_4_release_dates_get_a_padded_index_with_provenance() -> None:
    print("\n--- 4: an index built from release dates ---")
    if not HAVE_CALENDAR:
        skip("4. release dates", "exchange_calendars unavailable")
        return

    dates = ["2003-08-07", "2010-04-13", "2026-08-05"]
    sess, prov = sessions_for_release_dates(dates)
    check("4a. it spans every release date", sess[0] < date(2003, 8, 7)
          and sess[-1] > date(2026, 8, 5), f"{sess[0]}..{sess[-1]}")
    # A release on the FIRST date still needs the session before it, and an AMC
    # release on the LAST lands on the session after it.
    check("4b. it is padded on both ends", prov["pad_days"] == 20)
    check("4c. provenance carries the calendar implementation",
          prov["calendar_id"] == calendar_id())
    check("4d. and the agreement result travels with the index",
          prov["agrees"] is True and prov["disagreements"] == 0)
    check("4e. and the release-date range it was built for",
          prov["earliest_release_date"] == "2003-08-07"
          and prov["latest_release_date"] == "2026-08-05")
    check("4f. an empty set is refused rather than yielding an empty index",
          _raises(lambda: sessions_for_release_dates([])))
    check("4g. an unparseable date is refused",
          _raises(lambda: sessions_for_release_dates(["not-a-date"])))


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except SessionIndexError:
        return True


def test_5_the_authoritative_calendar_is_not_modified() -> None:
    """HYP-04 must not widen HYP-01's calendar to suit itself."""
    print("\n--- 5: gst_market_response is left alone ---")
    import ast
    import inspect

    from hyp04_supply_chain_hedge import sessions as mod

    src = inspect.getsource(mod)
    tree = ast.parse(src)
    module_level: set[str] = set()
    for node in tree.body:                      # MODULE level only
        if isinstance(node, ast.Import):
            module_level.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_level.add(node.module.split(".")[0])
    check("5a. gst_market_response is not imported at module scope",
          "gst_market_response" not in module_level, str(sorted(module_level)))
    check("5b. nor is exchange_calendars -- both are deferred, so importing "
          "this module costs nothing",
          "exchange_calendars" not in module_level, str(sorted(module_level)))
    check("5c. and nothing here assigns to the authoritative instance",
          "_calendar =" not in src and "_calendar=" not in src)

    if HAVE_CALENDAR:
        from gst_market_response.exchange_calendar import _calendar
        # NOT a literal date: see 2d. The bound rolls with the current
        # date, so pinning it makes this suite fail on a calendar change
        # nobody made. What must hold is that HYP-04 reaches earlier.
        auth = _calendar.first_session.date()
        check("5d. the authoritative instance is still bounded well after "
              "HYP-04's index start",
              auth > date.fromisoformat(DEFAULT_INDEX_START),
              f"{auth} vs {DEFAULT_INDEX_START}")
        check("5e. and it still cannot serve the anchor calendar's earliest "
              "release (2003-08-07), which is why HYP-04 has its own",
              auth > date(2003, 8, 7), str(auth))


def test_6_offline() -> None:
    print("\n--- 6: no endpoint is reached ---")
    if not HAVE_CALENDAR:
        skip("6. offline", "exchange_calendars unavailable")
        return

    def _no_net(*a, **k):
        raise RuntimeError("network access attempted")

    saved = (socket.socket.connect, socket.create_connection,
             socket.getaddrinfo)
    socket.socket.connect = _no_net
    socket.create_connection = _no_net
    socket.getaddrinfo = _no_net
    try:
        n = len(xnys_sessions(date(2003, 1, 1), date(2003, 3, 31)))
        check("6a. the index resolves with sockets blocked", n > 50, str(n))
    finally:
        (socket.socket.connect, socket.create_connection,
         socket.getaddrinfo) = saved


if __name__ == "__main__":
    test_1_the_wider_index_reaches_the_calendar_it_must()
    test_2_it_refuses_to_disagree_with_the_authoritative_calendar()
    test_3_it_fails_closed_on_a_range_it_cannot_serve()
    test_4_release_dates_get_a_padded_index_with_provenance()
    test_5_the_authoritative_calendar_is_not_modified()
    test_6_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 SESSION-INDEX TESTS PASSED")
