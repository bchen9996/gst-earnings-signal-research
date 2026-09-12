#!/usr/bin/env python3
"""Tests for run_hyp05_peer_returns_fetch.py -- offline, hermetic, no network.

Mirrors test_hyp04_supply_chain_hedge_peer_earnings_fetch.py's own shape for
the analogous HYP-04 module: named off the `test_*` discovery pattern so CI
never executes the live path, and nothing here calls it.

  THE PEER IS EXACTLY AMBA, FIXED (test_1) -- HYP-05's one real, verified,
  sub-$2B qualifying peer (see HYP05_PEER_UNIVERSE_HAND_CURATED_2026-09-12
  .json), not derived or discoverable from this suite.

  main() NEVER OVERWRITES A DATED ARTIFACT (test_2) -- checked for BOTH
  output files independently, since this module writes two, not one.

  main() NEVER GOES LIVE WITHOUT THE FLAG (test_3) -- verified by absence of
  both output files, not by trusting stdout.

  NO HARDCODED GATE-STATE VERDICT (test_4) -- the same defect class found and
  fixed across seven HYP-04 artifacts on 2026-09-09; this module is new and
  must not add a site for it.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_hyp05_peer_returns_fetch.py
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
import tempfile  # noqa: E402
from contextlib import redirect_stderr, redirect_stdout  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import run_hyp05_peer_returns_fetch as R  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_the_peer_is_fixed() -> None:
    check("1a. the peer is AMBA", R.PEER_TICKER == "AMBA", R.PEER_TICKER)
    check("1b. the closes fetch starts well before Ambarella's real "
          "2012-10-05 IPO", R.CLOSES_START < date(2012, 10, 5),
          str(R.CLOSES_START))


def _run_main(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = R.main(list(args))
    return code, out.getvalue(), err.getvalue()


def test_2_main_never_overwrites_a_dated_artifact() -> None:
    """Both output files are checked independently -- this module writes
    two, and a bug that only guarded one would silently clobber the other."""
    with tempfile.TemporaryDirectory() as td:
        closes_existing = Path(td) / "closes_existing.csv"
        earnings_fresh = Path(td) / "earnings_fresh.json"
        closes_existing.write_text("ticker,session_date,close\n", encoding="utf-8")
        code, out, err = _run_main(
            "--closes-out", str(closes_existing),
            "--earnings-out", str(earnings_fresh))
        check("2a. refuses with a non-zero exit when closes-out exists",
              code != 0, str(code))
        check("2b. says why, on stderr", "already exists" in err, err[:160])
        check("2c. never reaches the plan-printing path",
              "peer:" not in out, out[:160])
        check("2d. the earnings file is untouched",
              not earnings_fresh.exists())

        earnings_existing = Path(td) / "earnings_existing.json"
        closes_fresh = Path(td) / "closes_fresh.csv"
        earnings_existing.write_text("{}", encoding="utf-8")
        code, out, err = _run_main(
            "--closes-out", str(closes_fresh),
            "--earnings-out", str(earnings_existing))
        check("2e. refuses with a non-zero exit when earnings-out exists",
              code != 0, str(code))
        check("2f. the closes file is untouched", not closes_fresh.exists())


def test_3_dry_run_never_goes_live() -> None:
    with tempfile.TemporaryDirectory() as td:
        closes_out = Path(td) / "closes.csv"
        earnings_out = Path(td) / "earnings.json"
        code, out, err = _run_main(
            "--closes-out", str(closes_out), "--earnings-out", str(earnings_out))
        check("3a. exits 0", code == 0, str(code))
        check("3b. names the peer", "AMBA" in out, out[:200])
        check("3c. says DRY RUN and names the flag to proceed",
              "DRY RUN" in out and "--yes-run-live" in out)
        check("3d. nothing was written",
              not closes_out.exists() and not earnings_out.exists())
        check("3e. no error output on the successful dry-run path",
              err == "", err[:160])


def test_4_no_hardcoded_gate_state_verdict() -> None:
    """Same defect class found and fixed across seven HYP-04 artifacts on
    2026-09-09 -- a hardcoded gate STATE baked into a dated file. This
    module is new; it must not add a site for it."""
    import re
    src = (Path(__file__).resolve().parent / "hyp04_supply_chain_hedge"
           / "run_hyp05_peer_returns_fetch.py").read_text(encoding="utf-8")
    verdict = re.compile(
        r"(display )?[Gg]ate (is|stays) CLOSED|Gate CLOSED"
        r"|CLOSED with (C4 MET and )?four denials|CLOSED, C4 MET, four denials")
    hits = [ln for ln in src.splitlines()
            if not ln.strip().startswith("#") and verdict.search(ln)]
    check("4a. no hardcoded gate-state verdict in this module", hits == [],
          str(hits[:2]))


def test_5_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("5a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("5a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_the_peer_is_fixed()
    test_2_main_never_overwrites_a_dated_artifact()
    test_3_dry_run_never_goes_live()
    test_4_no_hardcoded_gate_state_verdict()
    test_5_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP05_PEER_RETURNS_FETCH TESTS PASSED")
    sys.exit(0)
