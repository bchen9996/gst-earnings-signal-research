#!/usr/bin/env python3
"""run_hyp07_existing_competitor_edges_name_search.py tests -- offline,
hermetic, no network. Named off the `test_*` discovery pattern so CI never
executes the live search path.

  THE MERGE FILTERS TO COMPETITOR-DIRECTION EDGES ONLY, ACROSS MULTIPLE
  INPUT FILES (test_1) -- a customer/supplier edge in the same file is
  excluded; a name recurring across two files keeps the EARLIEST as_of_date
  and records every anchor/source/input file it appeared under.

  main() NEVER OVERWRITES A DATED ARTIFACT, AND REFUSES ON A MISSING INPUT
  (test_2).

  main() NEVER GOES LIVE WITHOUT THE FLAG (test_3).

  NO HARDCODED GATE-STATE VERDICT (test_4).

Run directly: python test_hyp04_supply_chain_hedge_hyp07_existing_competitor_edges_name_search.py
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

from hyp04_supply_chain_hedge import (  # noqa: E402
    run_hyp07_existing_competitor_edges_name_search as R,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _edge(anchor: str, name: str, direction: str, as_of: str,
         source: str = "EDGAR_10K_COMPETITION_SECTION_PROSE") -> dict:
    return {"reporting_company": anchor, "reporting_cik": "0000000001",
            "named_counterparty": name, "counterparty_is_named": True,
            "direction": direction, "concentration_pct": None,
            "as_of_date": as_of, "accession": "x", "form": "10-K",
            "source": source, "pattern": "we_compete_with", "context": ""}


def _write_linkage(path: Path, edges: list[dict]) -> None:
    path.write_text(json.dumps({"edges": edges}), encoding="utf-8")


def test_1_merge_filters_to_competitor_direction_across_files() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f1 = tmp / "a.json"
        f2 = tmp / "b.json"
        _write_linkage(f1, [
            _edge("INTC", "AMD", "competitor", "2026-01-23"),
            _edge("MCK", "CVS Health Corporation", "customer", "2020-01-01"),
        ])
        _write_linkage(f2, [
            _edge("ADBE", "AMD", "competitor", "2015-01-01"),  # recurs, earlier date
            _edge("BKR", "Siemens Energy", "competitor", "2026-02-05"),
        ])
        rows = R._candidates((f1, f2))
        by_name = {r["counterparty"]: r for r in rows}

        check("1a. only competitor-direction edges survive (2 distinct "
              "names, not 3)", set(by_name) == {"AMD", "Siemens Energy"},
              str(set(by_name)))
        check("1b. AMD's as_of_date is the EARLIEST across both files",
              by_name["AMD"]["as_of_date"] == "2015-01-01",
              by_name["AMD"]["as_of_date"])
        check("1c. AMD's all_anchors lists both anchors",
              by_name["AMD"]["all_anchors"] == ["ADBE", "INTC"],
              str(by_name["AMD"]))
        check("1d. AMD's input_files names both source files",
              by_name["AMD"]["input_files"] == sorted([f1.name, f2.name]),
              str(by_name["AMD"]["input_files"]))
        check("1e. rows are sorted by counterparty name",
              [r["counterparty"] for r in rows] == sorted(by_name), str(rows))


def _run_main(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = R.main(list(args))
    return code, out.getvalue(), err.getvalue()


def test_2_main_refuses_on_missing_input_and_existing_output() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        missing = tmp / "nope.json"
        out = tmp / "out.json"
        code, out_txt, err = _run_main(
            "--in-json", str(missing), "--out", str(out))
        check("2a. refuses with a non-zero exit on a missing input file",
              code != 0, str(code))
        check("2b. says why, on stderr", "missing input" in err, err[:160])

        f1 = tmp / "a.json"
        _write_linkage(f1, [_edge("INTC", "AMD", "competitor", "2026-01-23")])
        existing_out = tmp / "existing.json"
        existing_out.write_text("{}", encoding="utf-8")
        code2, out2, err2 = _run_main(
            "--in-json", str(f1), "--out", str(existing_out))
        check("2c. refuses with a non-zero exit when --out already exists",
              code2 != 0, str(code2))
        check("2d. says why, on stderr", "already exists" in err2, err2[:160])


def test_3_dry_run_never_goes_live() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        f1 = tmp / "a.json"
        _write_linkage(f1, [
            _edge("INTC", "AMD", "competitor", "2026-01-23"),
            _edge("BKR", "Siemens Energy", "competitor", "2026-02-05"),
        ])
        out = tmp / "out.json"
        code, stdout, err = _run_main("--in-json", str(f1), "--out", str(out))
        check("3a. exits 0", code == 0, str(code))
        check("3b. names both candidates", "AMD" in stdout and "Siemens Energy" in stdout,
              stdout[:300])
        check("3c. says DRY RUN and names the flag to proceed",
              "DRY RUN" in stdout and "--yes-run-live" in stdout)
        check("3d. nothing was written", not out.exists())
        check("3e. no error output on the successful dry-run path",
              err == "", err[:160])


def test_4_no_hardcoded_gate_state_verdict() -> None:
    import re
    src = (Path(__file__).resolve().parent / "hyp04_supply_chain_hedge"
           / "run_hyp07_existing_competitor_edges_name_search.py"
           ).read_text(encoding="utf-8")
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
    test_1_merge_filters_to_competitor_direction_across_files()
    test_2_main_refuses_on_missing_input_and_existing_output()
    test_3_dry_run_never_goes_live()
    test_4_no_hardcoded_gate_state_verdict()
    test_5_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP07_EXISTING_COMPETITOR_EDGES_NAME_SEARCH TESTS PASSED")
    sys.exit(0)
