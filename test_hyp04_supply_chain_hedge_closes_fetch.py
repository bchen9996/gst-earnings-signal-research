#!/usr/bin/env python3
"""Tests for the Yahoo closes fetcher -- HYP-04.

The module under test makes real provider calls. NOTHING HERE DOES. `yfinance`
is never imported: the only function that touches it is `fetch_closes`, and
every test below drives `fill_request` with a dict the test supplies. That is
deliberate -- the fetcher's risky part is not the download, it is what it does
with a provider response that disagrees with the request.

Three properties carry the weight:

  1. IT FILLS A REQUEST, IT DOES NOT INVENT ONE (test_2, test_3). The request
     file names the exact XNYS sessions. A session the provider omitted is left
     EMPTY; a session the provider returned that was never requested is dropped
     and reported. If the fetcher chose its own dates it would be substituting
     Yahoo's calendar for XNYS's, and the mismatch would surface much later in
     peer_returns as `off_calendar_dates` -- a long way from its cause.

  2. MISSING IS EMPTY, NEVER ZERO (test_3). A zero return is a real
     observation -- a halt, a flat close. An empty cell is the absence of one.
     Substituting 0.0 fabricates exactly the observation peer_returns refuses
     to invent, and realized variance sums SQUARED returns, so a fabricated
     jump is not a small error.

  3. BAD VALUES ARE TREATED AS ABSENT, NOT PASSED THROUGH (test_4). NaN, inf
     and non-positive closes make log(p_t / p_{t-1}) undefined. They are
     recorded as rejected AND counted as missing, so the operator sees both
     that the provider returned something and that it was unusable.

Offline. No network. Nothing is written outside a temp directory.

Run directly: python test_hyp04_supply_chain_hedge_closes_fetch.py
"""
from __future__ import annotations

import csv
import socket
import sys
import tempfile
from datetime import date
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.run_peer_closes_fetch import (  # noqa: E402
    ADJUST_SPLIT_AND_DIVIDEND,
    ADJUST_SPLIT_ONLY,
    YFINANCE_REQUIRED_MESSAGE,
    fill_request,
    read_request,
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


SESSIONS = [date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6),
            date(2020, 1, 7), date(2020, 1, 8)]


def _request(tmp: Path, sessions=SESSIONS, ticker="CVS") -> Path:
    p = tmp / f"{ticker}_closes_REQUEST.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "session_date", "close"])
        for d in sessions:
            w.writerow([ticker, d.isoformat(), ""])
    return p


def _rows(p: Path) -> list[dict]:
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_1_read_request_validates_its_input():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tk, sess = read_request(_request(tmp))
        check("1a. the ticker is read", tk == "CVS", tk)
        check("1b. sessions are read in order", sess == SESSIONS, str(sess))

        # A mixed-ticker file is a malformed request, not something to guess at.
        mixed = tmp / "mixed.csv"
        with mixed.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ticker", "session_date", "close"])
            w.writerow(["CVS", "2020-01-02", ""])
            w.writerow(["ODP", "2020-01-03", ""])
        raised = False
        try:
            read_request(mixed)
        except ValueError as e:
            raised = "one peer" in str(e)
        check("1c. a mixed-ticker request is refused", raised)

        dup = tmp / "dup.csv"
        with dup.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ticker", "session_date", "close"])
            w.writerow(["CVS", "2020-01-02", ""])
            w.writerow(["CVS", "2020-01-02", ""])
        raised2 = False
        try:
            read_request(dup)
        except ValueError as e:
            raised2 = "duplicate" in str(e)
        check("1d. duplicate sessions are refused", raised2)

        unordered = tmp / "unordered.csv"
        with unordered.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ticker", "session_date", "close"])
            w.writerow(["CVS", "2020-01-03", ""])
            w.writerow(["CVS", "2020-01-02", ""])
        raised3 = False
        try:
            read_request(unordered)
        except ValueError as e:
            raised3 = "ascending" in str(e)
        check("1e. out-of-order sessions are refused", raised3)


def test_2_a_complete_response_fills_every_row():
    with tempfile.TemporaryDirectory() as td:
        p = _request(Path(td))
        closes = {d: 100.0 + i for i, d in enumerate(SESSIONS)}
        res = fill_request(p, closes, adjustment=ADJUST_SPLIT_AND_DIVIDEND)

        check("2a. every requested row is filled",
              res.filled == res.requested == len(SESSIONS), str(res.as_dict()))
        check("2b. nothing is missing", not res.missing, str(res.missing))
        check("2c. it reports complete", res.complete)
        check("2d. the adjustment basis is recorded",
              res.adjustment == ADJUST_SPLIT_AND_DIVIDEND, res.adjustment)

        rows = _rows(p)
        check("2e. the file still has exactly the requested sessions",
              [r["session_date"] for r in rows]
              == [d.isoformat() for d in SESSIONS])
        check("2f. and every close is populated",
              all(r["close"] for r in rows), str(rows))


def test_3_the_request_is_the_specification():
    """A provider disagreeing with the request must not change the request."""
    with tempfile.TemporaryDirectory() as td:
        p = _request(Path(td))
        closes = {
            SESSIONS[0]: 100.0,
            # SESSIONS[1] deliberately absent -- provider gap
            SESSIONS[2]: 102.0,
            SESSIONS[3]: 103.0,
            SESSIONS[4]: 104.0,
            date(2020, 1, 4): 999.0,   # a Saturday -- never requested
            date(2020, 1, 5): 998.0,   # a Sunday  -- never requested
        }
        res = fill_request(p, closes, adjustment=ADJUST_SPLIT_ONLY)

        check("3a. the missing session is reported",
              res.missing == [SESSIONS[1].isoformat()], str(res.missing))
        check("3b. it is NOT filled", res.filled == 4, str(res.filled))
        check("3c. and the file is not complete", not res.complete)

        rows = _rows(p)
        gap = [r for r in rows if r["session_date"] == SESSIONS[1].isoformat()]
        check("3d. the gap row still EXISTS in the file", len(gap) == 1)
        check("3e. with an EMPTY close, not a zero",
              gap and gap[0]["close"] == "",
              f"got {gap[0]['close']!r}" if gap else "row absent")

        check("3f. unrequested provider dates are reported",
              set(res.unrequested_dropped) == {"2020-01-04", "2020-01-05"},
              str(res.unrequested_dropped))
        check("3g. and do NOT appear in the file",
              not any(r["session_date"] in ("2020-01-04", "2020-01-05")
                      for r in rows))
        check("3h. the row count still equals the request",
              len(rows) == len(SESSIONS), str(len(rows)))


def test_4_unusable_values_are_absent_not_passed_through():
    with tempfile.TemporaryDirectory() as td:
        p = _request(Path(td))
        closes = {
            SESSIONS[0]: float("nan"),
            SESSIONS[1]: float("inf"),
            SESSIONS[2]: 0.0,
            SESSIONS[3]: -5.0,
            SESSIONS[4]: 104.0,
        }
        res = fill_request(p, closes, adjustment=ADJUST_SPLIT_AND_DIVIDEND)

        check("4a. only the one usable close is filled", res.filled == 1,
              str(res.filled))
        check("4b. all four bad values are recorded as rejected",
              len(res.rejected_values) == 4, str(res.rejected_values))
        check("4c. and ALSO counted as missing",
              len(res.missing) == 4, str(res.missing))

        rows = _rows(p)
        blanks = [r["close"] for r in rows[:4]]
        check("4d. every rejected value writes an EMPTY cell",
              blanks == ["", "", "", ""], str(blanks))
        check("4e. zero is rejected, not accepted as a price",
              SESSIONS[2].isoformat() in res.missing,
              "a zero close makes the log return undefined")


def test_5_out_of_place_writing_leaves_the_request_intact():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p = _request(tmp)
        out = tmp / "filled" / "CVS_closes_REQUEST.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        fill_request(p, {d: 100.0 for d in SESSIONS},
                     adjustment=ADJUST_SPLIT_ONLY, out_path=out)

        check("5a. the copy is filled", all(r["close"] for r in _rows(out)))
        check("5b. and the original request is untouched",
              all(r["close"] == "" for r in _rows(p)))


def test_6_the_module_never_imports_yfinance_at_module_scope():
    """The exclusion of yfinance is a safety property; keep it enforceable."""
    import ast

    import hyp04_supply_chain_hedge.run_peer_closes_fetch as m

    src = Path(m.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    top_level: set[str] = set()
    for node in tree.body:                      # MODULE SCOPE only
        if isinstance(node, ast.Import):
            top_level.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            top_level.add(node.module.split(".")[0])
    check("6a. yfinance is not imported at module scope",
          "yfinance" not in top_level, str(sorted(top_level)))
    check("6b. and is not in sys.modules after importing this module",
          "yfinance" not in sys.modules)
    check("6c. the refusal message names the deliberate omission",
          "DELIBERATELY absent" in YFINANCE_REQUIRED_MESSAGE)
    check("6d. and tells the operator how to install it",
          "pip install yfinance" in YFINANCE_REQUIRED_MESSAGE)

    flat = " ".join(src.split())
    check("6e. the adjustment choice is documented as a real choice",
          "DIVIDENDS ARE A JUDGEMENT CALL" in flat)
    check("6f. and disclaims being registered anywhere",
          "NOT registered anywhere" in flat)
    check("6g. the module states it makes real provider calls",
          "MAKES REAL PROVIDER CALLS" in flat)
    check("6h. and is named off the test_* discovery pattern",
          not Path(m.__file__).name.startswith("test_"),
          Path(m.__file__).name)


def test_7_offline():
    check("7a. network is blocked in this suite", True)
    try:
        socket.getaddrinfo("finance.yahoo.com", 443)
        check("7b. a network call raises", False, "it did not")
    except NetworkBlocked:
        check("7b. a network call raises", True)


if __name__ == "__main__":
    test_1_read_request_validates_its_input()
    test_2_a_complete_response_fills_every_row()
    test_3_the_request_is_the_specification()
    test_4_unusable_values_are_absent_not_passed_through()
    test_5_out_of_place_writing_leaves_the_request_intact()
    test_6_the_module_never_imports_yfinance_at_module_scope()
    test_7_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 CLOSES-FETCH TESTS PASSED")
    sys.exit(0)
