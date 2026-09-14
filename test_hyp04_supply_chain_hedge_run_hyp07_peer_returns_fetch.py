#!/usr/bin/env python3
"""Tests for run_hyp07_peer_returns_fetch.py -- offline, hermetic, no network.

Mirrors test_hyp04_supply_chain_hedge_run_hyp06_peer_returns_fetch.py's own
shape: named off the `test_*` discovery pattern so CI never executes the
live path, and nothing here calls it.

  PEERS ARE READ FROM A SIGNED LOCK, NOT HARDCODED (test_1).

  main() NEVER OVERWRITES A DATED ARTIFACT (test_2).

  main() NEVER GOES LIVE WITHOUT THE FLAG (test_3) -- also checks the
  benchmark ticker (SPY) is named in the printed plan, distinct from
  HYP-06's own test since HYP-07 fetches one extra ticker.

  NO HARDCODED GATE-STATE VERDICT (test_4).

Run directly: python test_hyp04_supply_chain_hedge_run_hyp07_peer_returns_fetch.py
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

from hyp04_supply_chain_hedge import run_hyp07_peer_returns_fetch as R  # noqa: E402
from hyp04_supply_chain_hedge.anchor_shock import BENCHMARK_TICKER  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _write_lock(path: Path, *, declared: bool = True,
                peers: list[str] | None = None) -> None:
    doc = {
        "artifact": path.name, "declared": declared,
        "locked_peers": peers if peers is not None
        else ["BHE", "GLUC", "OMCL", "SCSC", "TOMZ", "TRS"],
    }
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_1_peers_come_from_a_signed_lock() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        missing = tmp / "nope.json"
        try:
            R._load_locked_peers(missing)
            check("1a. no lock on disk refuses", False)
        except RuntimeError as e:
            check("1a. no lock on disk refuses", "no signed" in str(e))

        draft = tmp / "draft.json"
        _write_lock(draft, declared=False)
        try:
            R._load_locked_peers(draft)
            check("1b. an undeclared draft refuses", False)
        except RuntimeError as e:
            check("1b. an undeclared draft refuses", "not a SIGNED lock" in str(e))

        signed = tmp / "signed.json"
        _write_lock(signed, declared=True, peers=["TOMZ", "BHE", "GLUC"])
        peers = R._load_locked_peers(signed)
        check("1c. locked_peers is read back, sorted",
              peers == ["BHE", "GLUC", "TOMZ"], str(peers))

        empty = tmp / "empty.json"
        _write_lock(empty, declared=True, peers=[])
        try:
            R._load_locked_peers(empty)
            check("1d. an empty locked_peers list refuses", False)
        except RuntimeError as e:
            check("1d. an empty locked_peers list refuses", "no locked_peers" in str(e))


def _run_main(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = R.main(list(args))
    return code, out.getvalue(), err.getvalue()


def test_2_main_never_overwrites_a_dated_artifact() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        lock = tmp / "lock.json"
        _write_lock(lock)

        closes_existing = tmp / "closes_existing.csv"
        earnings_fresh = tmp / "earnings_fresh.json"
        closes_existing.write_text("ticker,session_date,close\n", encoding="utf-8")
        code, out, err = _run_main(
            "--phase2-lock", str(lock),
            "--closes-out", str(closes_existing),
            "--earnings-out", str(earnings_fresh))
        check("2a. refuses with a non-zero exit when closes-out exists",
              code != 0, str(code))
        check("2b. says why, on stderr", "already exists" in err, err[:160])
        check("2c. never reaches the plan-printing path",
              "peers (" not in out, out[:160])
        check("2d. the earnings file is untouched",
              not earnings_fresh.exists())

        earnings_existing = tmp / "earnings_existing.json"
        closes_fresh = tmp / "closes_fresh.csv"
        earnings_existing.write_text("{}", encoding="utf-8")
        code, out, err = _run_main(
            "--phase2-lock", str(lock),
            "--closes-out", str(closes_fresh),
            "--earnings-out", str(earnings_existing))
        check("2e. refuses with a non-zero exit when earnings-out exists",
              code != 0, str(code))
        check("2f. the closes file is untouched", not closes_fresh.exists())


def test_3_dry_run_never_goes_live() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        lock = tmp / "lock.json"
        _write_lock(lock, peers=["BHE", "GLUC", "TOMZ"])
        closes_out = tmp / "closes.csv"
        earnings_out = tmp / "earnings.json"
        code, out, err = _run_main(
            "--phase2-lock", str(lock),
            "--closes-out", str(closes_out), "--earnings-out", str(earnings_out))
        check("3a. exits 0", code == 0, str(code))
        check("3b. names all three peers", all(p in out for p in ("BHE", "GLUC", "TOMZ")), out[:200])
        check("3c. also names the benchmark ticker -- the one real "
              "difference from HYP-06's own fetch module",
              BENCHMARK_TICKER in out, out[:200])
        check("3d. says DRY RUN and names the flag to proceed",
              "DRY RUN" in out and "--yes-run-live" in out)
        check("3e. nothing was written",
              not closes_out.exists() and not earnings_out.exists())
        check("3f. no error output on the successful dry-run path",
              err == "", err[:160])


def test_4_no_hardcoded_gate_state_verdict() -> None:
    import re
    src = (Path(__file__).resolve().parent / "hyp04_supply_chain_hedge"
           / "run_hyp07_peer_returns_fetch.py").read_text(encoding="utf-8")
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
    test_1_peers_come_from_a_signed_lock()
    test_2_main_never_overwrites_a_dated_artifact()
    test_3_dry_run_never_goes_live()
    test_4_no_hardcoded_gate_state_verdict()
    test_5_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP07_PEER_RETURNS_FETCH TESTS PASSED")
    sys.exit(0)
