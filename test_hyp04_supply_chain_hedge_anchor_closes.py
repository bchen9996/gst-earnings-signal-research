#!/usr/bin/env python3
"""HYP-04 anchor-side closes tests. FULLY OFFLINE.

The anchor side is the one path to C2 that waits on neither the linkage map nor
a survivorship-clean peer source, so the ways of getting it wrong all end in a
number that looks like progress:

  * resolving an AMC release to its OWN session -- one session early, which is
    look-ahead, and which raises nothing
  * accepting an UNRESOLVED session rather than denying it
  * requesting the attributed session but not the close BEFORE it, so every
    return is uncomputable for a reason pointing somewhere else
  * reading a missing benchmark close as zero
  * mixing return bases between the two legs

Nothing here fetches. `numpy` is deliberately not imported: this suite must run
on a machine where Application Control blocks numpy.random.

Run directly: python test_hyp04_supply_chain_hedge_anchor_closes.py
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

from hyp04_supply_chain_hedge.anchor_closes import (  # noqa: E402
    ANCHOR_CLOSES_RULE_ID,
    CLOSES_PER_TICKER_PER_EVENT,
    build_request,
    resolve_attributed_session,
    shocks_for_request,
    survivorship_exposure,
    write_request_csvs,
)
from hyp04_supply_chain_hedge.anchor_shock import (  # noqa: E402
    BENCHMARK_TICKER,
    RETURN_BASIS,
)

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


# Weekdays of 2013-07, minus 2013-07-04 (Independence Day). A real holiday, so
# the "next session" rule is exercised across one.
SESSIONS = [d for d in (date(2013, 7, 1) + timedelta(days=i) for i in range(31))
            if d.weekday() < 5 and d != date(2013, 7, 4)]


def _row(eid, tk, rd, rs):
    return {"event_id": eid, "anchor_ticker": tk, "release_date": rd,
            "release_session": rs}


def test_1_the_session_rule() -> None:
    print("\n--- 1: BMO lands today, AMC lands tomorrow ---")
    a, p, why = resolve_attributed_session("2013-07-10", "BMO", SESSIONS)
    check("1a. BMO resolves to the release session itself",
          a == date(2013, 7, 10), str(a))
    check("1b. and the prior session is the one before it",
          p == date(2013, 7, 9), str(p))

    a, p, _ = resolve_attributed_session("2013-07-10", "AMC", SESSIONS)
    check("1c. AMC resolves to the NEXT session", a == date(2013, 7, 11), str(a))
    check("1d. whose prior session is the release date itself",
          p == date(2013, 7, 10), str(p))

    # THE ERROR THAT RAISES NOTHING. An AMC release resolved to its own session
    # measures the shock on a session that closed BEFORE the news.
    check("1e. AMC does NOT resolve to its own session",
          resolve_attributed_session("2013-07-10", "AMC", SESSIONS)[0]
          != date(2013, 7, 10))

    # Across a real holiday: 2013-07-03 AMC -> 07-04 is closed -> 07-05.
    a, p, _ = resolve_attributed_session("2013-07-03", "AMC", SESSIONS)
    check("1f. AMC skips a market holiday", a == date(2013, 7, 5), str(a))
    check("1g. and the prior session skips it too", p == date(2013, 7, 3), str(p))

    # A BMO release on a non-session cannot land on that day.
    a, _, _ = resolve_attributed_session("2013-07-06", "BMO", SESSIONS)
    check("1h. BMO on a Saturday moves to the next session",
          a == date(2013, 7, 8), str(a))


def test_2_unresolved_denies() -> None:
    print("\n--- 2: an unresolved session is refused, not guessed ---")
    for s in ("UNKNOWN", "", None, "amc-ish", "PRE"):
        a, p, why = resolve_attributed_session("2013-07-10", s, SESSIONS)
        check(f"2a. release session {s!r} denies", a is None and p is None)
        check(f"2b. and says AS-1 needs it: {s!r}",
              "AS-1" in why and "refuses to guess" in why, why[:80])
    a, _, why = resolve_attributed_session("10/07/2013", "BMO", SESSIONS)
    check("2c. a non-ISO release date denies", a is None and "ISO" in why, why)
    # The first session in the index has no prior close, so it cannot carry a
    # return. Clipping instead of denying would produce a return from nothing.
    a, p, why = resolve_attributed_session(
        SESSIONS[0].isoformat(), "BMO", SESSIONS)
    check("2d. the FIRST session in the index denies -- no prior close",
          a is None and "FIRST" in why, why[:80])
    a, _, why = resolve_attributed_session("2013-08-30", "AMC", SESSIONS)
    check("2e. a release past the end of the index denies rather than clips",
          a is None and "extend it" in why, why[:80])


def test_3_the_request_covers_both_legs() -> None:
    print("\n--- 3: what to collect ---")
    rows = [_row("E1", "MCK", "2013-07-10", "AMC"),
            _row("E2", "MCK", "2013-07-24", "BMO"),
            _row("E3", "INTC", "2013-07-10", "AMC"),
            _row("E4", "NKE", "2013-07-15", "UNKNOWN")]
    req = build_request(rows, sessions=SESSIONS)

    check("3a. resolved events exclude the unresolved one",
          len(req.resolved) == 3 and len(req.denied) == 1,
          f"{len(req.resolved)}/{len(req.denied)}")
    check("3b. the denial names the event, not just a count",
          req.denied[0].event_id == "E4", str(req.denied[0].as_dict())[:80])

    # THE BENCHMARK IS NOT OPTIONAL. AS-3 denies without it and never reads a
    # missing benchmark as zero, so it must be requested on the same sessions.
    check("3c. the benchmark is requested too",
          BENCHMARK_TICKER in req.sessions_by_ticker,
          str(req.tickers))
    check("3d. on the union of every event's sessions",
          set(req.sessions_by_ticker[BENCHMARK_TICKER])
          == {"2013-07-10", "2013-07-11", "2013-07-23", "2013-07-24"},
          str(req.sessions_by_ticker[BENCHMARK_TICKER]))

    # TWO closes per (ticker, event): a daily return needs the prior close.
    check("3e. two closes per ticker per event", CLOSES_PER_TICKER_PER_EVENT == 2)
    check("3f. MCK's two events need four sessions",
          len(req.sessions_by_ticker["MCK"]) == 4,
          str(req.sessions_by_ticker["MCK"]))
    check("3g. sessions are DEDUPLICATED across events -- INTC and MCK share a "
          "release date and the benchmark is not requested twice for it",
          len(req.sessions_by_ticker[BENCHMARK_TICKER]) == 4,
          str(len(req.sessions_by_ticker[BENCHMARK_TICKER])))
    check("3h. the rule id is carried", req.rule_id == ANCHOR_CLOSES_RULE_ID)
    check("3i. and the declared return basis travels with the request",
          req.return_basis == RETURN_BASIS == "log")
    check("3j. the request claims nothing about eligibility",
          "no shock has been computed" in req.as_dict()["measurement_status"])


def test_4_the_request_file_is_a_column_to_fill() -> None:
    print("\n--- 4: the emitted files ---")
    import csv
    import tempfile
    from pathlib import Path

    req = build_request([_row("E1", "MCK", "2013-07-10", "AMC")],
                        sessions=SESSIONS)
    with tempfile.TemporaryDirectory() as tmp:
        written = write_request_csvs(req, Path(tmp))
        check("4a. one file per ticker, anchor and benchmark",
              len(written) == 2, str([p.name for p, _ in written]))
        path = next(p for p, _ in written if p.name.startswith("MCK"))
        rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
        check("4b. every requested session is a row", len(rows) == 2, str(rows))
        check("4c. the ticker column is filled",
              all(r["ticker"] == "MCK" for r in rows))
        # EMPTY, never zero. A zero close is not an observation; a zero RETURN
        # is. Conflating them turns a halt into a flat session.
        check("4d. the close column is EMPTY, not zero",
              all(r["close"] == "" for r in rows), str(rows))
        check("4e. sessions are the attributed one and the one before it",
              sorted(r["session_date"] for r in rows)
              == ["2013-07-10", "2013-07-11"],
              str([r["session_date"] for r in rows]))


def test_5_shocks_are_computed_or_denied_never_defaulted() -> None:
    print("\n--- 5: from closes to shocks ---")
    import math

    req = build_request([_row("E1", "MCK", "2013-07-10", "AMC")],
                        sessions=SESSIONS)
    closes = {"MCK": {"2013-07-10": 100.0, "2013-07-11": 92.0},
              BENCHMARK_TICKER: {"2013-07-10": 160.0, "2013-07-11": 161.0}}
    shocks, denials = shocks_for_request(req, closes)
    check("5a. one shock is produced", len(shocks) == 1 and not denials,
          str(denials))
    if shocks:
        s = shocks[0]
        want = abs(math.log(92.0 / 100.0) - math.log(161.0 / 160.0))
        check("5b. it is |log anchor return - log benchmark return|",
              abs(s.shock - want) < 1e-12, f"{s.shock} vs {want}")
        check("5c. measured on the ATTRIBUTED session, not the release date",
              s.session == "2013-07-11", s.session)

    # THE DANGEROUS ONE. A missing benchmark must deny, never be read as zero:
    # that would silently promote a raw return to an excess return.
    for missing in ({"MCK": closes["MCK"]},
                    {"MCK": closes["MCK"], BENCHMARK_TICKER: {"2013-07-10": 160.0}}):
        sh, dn = shocks_for_request(req, missing)
        check("5d. a missing benchmark close denies", not sh and len(dn) == 1,
              str(dn)[:90])
        check("5e. and says it is absent, not zero",
              any("not zero" in r for r in dn[0]["reasons"]), str(dn)[:110])

    # A non-positive close makes log undefined; substituting anything invents a
    # return no trade produced.
    bad = {"MCK": {"2013-07-10": 0.0, "2013-07-11": 92.0},
           BENCHMARK_TICKER: closes[BENCHMARK_TICKER]}
    sh, dn = shocks_for_request(req, bad)
    check("5f. a non-positive close denies rather than being substituted",
          not sh and any("undefined" in r for r in dn[0]["reasons"]),
          str(dn)[:110])

    # CONTROL -- a genuinely flat session is a real observation and must PASS.
    flat = {"MCK": {"2013-07-10": 100.0, "2013-07-11": 100.0},
            BENCHMARK_TICKER: {"2013-07-10": 160.0, "2013-07-11": 160.0}}
    sh, dn = shocks_for_request(req, flat)
    check("5g. CONTROL -- a flat session yields a shock of 0.0, not a denial",
          len(sh) == 1 and sh[0].shock == 0.0, str(dn))


def test_6_survivorship_is_reported_not_assumed() -> None:
    print("\n--- 6: the anchor side's survivorship position ---")
    members = ["AAPL", "ADBE", "CTSH", "INTC", "JBL", "MCK", "NKE", "NVDA"]
    clean = survivorship_exposure(members, members + ["SPY"])
    check("6a. a fully listed universe reports clean",
          clean["anchor_side_survivorship_clean"] is True)
    check("6b. and says so is an observation, not a property of the rule",
          "not a property of the rule" in str(clean).lower()
          or "observation about today" in clean["not_a_property_of_the_rule"])
    # CONTROL -- a delisted member must be NAMED, so the day it happens is
    # visible rather than inferred from silence.
    dirty = survivorship_exposure(members + ["ODP"], members)
    check("6c. CONTROL -- a delisted member is named",
          dirty["tickers_not_currently_listed"] == ["ODP"]
          and dirty["anchor_side_survivorship_clean"] is False,
          str(dirty["tickers_not_currently_listed"]))
    check("6d. and it does not claim to amend the PEER policy",
          "peer_price_data_policy" in clean["why_this_is_not_the_peer_side_policy"])


def test_7_nothing_here_fetches() -> None:
    print("\n--- 7: no provider is reachable from this module ---")
    import ast
    import inspect

    from hyp04_supply_chain_hedge import anchor_closes as ac

    tree = ast.parse(inspect.getsource(ac))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    for banned in ("yfinance", "requests", "urllib", "http", "socket"):
        check(f"7a. {banned} is not imported", banned not in imported,
              str(sorted(imported)))
    check("7b. and it does not import numpy either, so it runs where "
          "Application Control blocks numpy.random",
          "numpy" not in imported, str(sorted(imported)))
    try:
        socket.getaddrinfo("query1.finance.yahoo.com", 443)
        check("7c. network blocked in this suite", False, "a lookup succeeded")
    except Exception as e:
        check("7c. network blocked in this suite",
              type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_the_session_rule()
    test_2_unresolved_denies()
    test_3_the_request_covers_both_legs()
    test_4_the_request_file_is_a_column_to_fill()
    test_5_shocks_are_computed_or_denied_never_defaulted()
    test_6_survivorship_is_reported_not_assumed()
    test_7_nothing_here_fetches()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 ANCHOR CLOSES TESTS PASSED")
