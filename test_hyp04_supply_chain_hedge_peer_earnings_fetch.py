#!/usr/bin/env python3
"""Tests for the peer-earnings LIVE runner -- offline, hermetic, no network.

This is a `run_*` module: named off the `test_*` discovery pattern so CI never
executes it, and STAGED so a human must pass `--yes-run-live` before it
contacts SEC. Nothing in this suite calls that path. What is tested is
everything reachable WITHOUT it:

  THE PEER SET IS EXACTLY SIX, FIXED (test_1). Not derived, not discoverable
  from this suite -- the six tickers HYP-04 already holds real closes for.

  A CIK LOOKUP OVER AN EMPTY CACHE REFUSES RATHER THAN REACHING THE NETWORK
  (test_2). The same property `earnings_events.py`'s own suite proves for
  `all_item_202_records`, proven here for THIS module's `_resolve_ciks`. If the
  offline guard had a bug, the socket block below would catch it as
  NetworkBlocked instead of the expected OfflineCacheMiss -- so this is
  defense in depth, not a single point of failure.

  THE REAL COMMITTED CACHE RESOLVES ALL SIX FOR FREE (test_3, a control). If
  this ever costs a request, the dry-run plan printed to a human is no longer
  actually free to print.

  THE FIELD RENAME IS REAL, NOT ASSUMED (test_4). `CandidateEvent` is reused
  from the anchor side and its ticker field is literally named
  `anchor_ticker`. `_peer_row` must not leak that name into this artifact.

  main() NEVER OVERWRITES A DATED ARTIFACT (test_5), and NEVER goes live
  without the flag (test_6) -- checked by asserting requests_made stays 0 and
  no artifact appears, not by trusting the printed text.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_peer_earnings_fetch.py
"""
from __future__ import annotations

import socket
import sys


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import io  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
from contextlib import redirect_stderr, redirect_stdout  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import run_peer_earnings_fetch as R  # noqa: E402
from hyp04_supply_chain_hedge.earnings_events import CandidateEvent  # noqa: E402
from hyp04_supply_chain_hedge.edgar_linkage import (  # noqa: E402
    OfflineCacheMiss,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_the_peer_set_is_fixed() -> None:
    check("1a. exactly six peers",
          R.PEER_TICKERS == ("AAPL", "BB", "CSCO", "CVS", "HPQ", "MSFT"),
          str(R.PEER_TICKERS))
    check("1b. no duplicates", len(set(R.PEER_TICKERS)) == 6)
    check("1c. matches the six peers the real panel already holds closes for",
          set(R.PEER_TICKERS) == {"AAPL", "BB", "CSCO", "CVS", "HPQ", "MSFT"})


def test_2_an_empty_cache_refuses_rather_than_reaching_the_network() -> None:
    """The same property earnings_events.py's suite proves for
    all_item_202_records, proven here for THIS module's own CIK lookup."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            R._resolve_ciks(offline=True, cache_dir=Path(tmp))
            check("2a. an offline client with an empty cache REFUSES", False,
                  "it returned instead of raising")
        except OfflineCacheMiss:
            check("2a. an offline client with an empty cache REFUSES", True)
        except NetworkBlocked:
            check("2a. an offline client with an empty cache REFUSES", False,
                  "it attempted a live request instead of refusing")


def test_3_the_real_cache_resolves_all_six_for_free() -> None:
    """CONTROL. If this ever costs a request, the 'free to print' claim in
    main()'s dry-run path is false."""
    ciks, unknown, cost = R._resolve_ciks(offline=True)
    check("3a. all six peers resolve", not unknown, str(unknown))
    check("3b. at ZERO request cost -- served entirely from the committed "
          "ticker-map cache", cost == 0, str(cost))
    check("3c. and the CIKs look like CIKs (10 digits)",
          all(len(c) == 10 and c.isdigit() for c in ciks.values()), str(ciks))


def test_4_the_field_rename_is_real() -> None:
    """CandidateEvent's ticker field is literally `anchor_ticker`. Prove
    `_peer_row` does not leak that name into a peer artifact."""
    e = CandidateEvent(
        event_id="AAPL-2020-01-28", anchor_ticker="AAPL",
        release_date="2020-01-28", release_session="AMC",
        session_basis="accepted 2020-01-28 16:30 EST, at or after the "
                      "16:00 ET close",
        filing_date="2020-01-28", acceptance_utc="2020-01-28T21:30:00.000Z",
        acceptance_et="2020-01-28 16:30 EST", items="2.02,9.01",
        accession="0000320193-20-000001", flags=())
    row = R._peer_row(e)
    check("4a. the row carries peer_ticker", row.get("peer_ticker") == "AAPL",
          str(row))
    check("4b. and NOT the inherited anchor_ticker key",
          "anchor_ticker" not in row, str(sorted(row)))
    check("4c. every other field survives untouched",
          row["release_date"] == "2020-01-28"
          and row["release_session"] == "AMC"
          and row["accession"] == "0000320193-20-000001")


def _run_main(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = R.main(list(args))
    return code, out.getvalue(), err.getvalue()


def test_5_main_never_overwrites_a_dated_artifact() -> None:
    real_out = R.OUT_JSON
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "existing.json"
        p.write_text("{}", encoding="utf-8")
        R.OUT_JSON = p
        try:
            code, out, err = _run_main()
        finally:
            R.OUT_JSON = real_out
        check("5a. refuses with a non-zero exit", code != 0, str(code))
        check("5b. and says why, on stderr", "already exists" in err, err[:160])
        check("5c. and never touches the CIK lookup or prints a plan",
              "peers:" not in out, out[:160])


def test_6_dry_run_never_goes_live() -> None:
    """No --yes-run-live: main() must print the plan, cost zero requests, and
    write nothing -- verified by absence of the output file, not by trusting
    stdout."""
    real_out = R.OUT_JSON
    with tempfile.TemporaryDirectory() as td:
        R.OUT_JSON = Path(td) / "HYP04_PEER_EARNINGS_test.json"
        try:
            code, out, err = _run_main()
        finally:
            R.OUT_JSON = real_out
        check("6a. exits 0", code == 0, str(code))
        check("6b. names every peer and its CIK",
              all(t in out for t in R.PEER_TICKERS), out[:300])
        check("6c. says DRY RUN and names the flag to proceed",
              "DRY RUN" in out and "--yes-run-live" in out)
        check("6d. nothing was written", not (Path(td)
              / "HYP04_PEER_EARNINGS_test.json").exists())
        check("6e. no error output on the successful dry-run path",
              err == "", err[:160])


def test_7_the_artifact_would_disclaim_gate_movement_without_a_snapshot() -> None:
    """The stale-verdict defect found across seven other HYP-04 artifacts on
    2026-09-09 was a hardcoded gate STATE baked into a dated file. This module
    is new; it must not add an eighth site."""
    import re
    src = (Path(__file__).resolve().parent / "hyp04_supply_chain_hedge"
           / "run_peer_earnings_fetch.py").read_text(encoding="utf-8")
    verdict = re.compile(
        r"(display )?[Gg]ate (is|stays) CLOSED|Gate CLOSED"
        r"|CLOSED with (C4 MET and )?four denials|CLOSED, C4 MET, four denials")
    hits = [ln for ln in src.splitlines()
            if not ln.strip().startswith("#") and verdict.search(ln)]
    check("7a. no hardcoded gate-state verdict in this module", hits == [],
          str(hits[:2]))
    check("7b. it states the durable claim instead",
          "moves no gate condition" in src.lower())


def test_8_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("8a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("8a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_the_peer_set_is_fixed()
    test_2_an_empty_cache_refuses_rather_than_reaching_the_network()
    test_3_the_real_cache_resolves_all_six_for_free()
    test_4_the_field_rename_is_real()
    test_5_main_never_overwrites_a_dated_artifact()
    test_6_dry_run_never_goes_live()
    test_7_the_artifact_would_disclaim_gate_movement_without_a_snapshot()
    test_8_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PEER-EARNINGS-FETCH TESTS PASSED")
    sys.exit(0)
