#!/usr/bin/env python3
"""HYP-04 dashboard -- a suite that could not run has not failed.

Why this suite exists. The dashboard's whole job is to state the project's
status honestly, and it had one way to be wrong about itself: any suite whose
process exited non-zero was reported FAIL. Running the dashboard from an
interpreter without `numpy` therefore produced a page announcing eighteen
FAILING suites when not a single check had failed -- they had not run. That
page was generated for real on 2026-09-09 before this was fixed.

The distinction is the same one the repository already draws elsewhere and
states on the page itself: skips are counted separately and never as passes,
and discovery finding nothing must not render as success. Not running is not
passing, and it is not failing either. Three states, not two.

What is asserted: the classifier reads a real ModuleNotFoundError traceback
and does NOT read a genuine harness failure as one; `all_green` stays strict
so an unrunnable environment never renders green; and the headline word the
reader actually sees changes accordingly.

None of this touches the display gate. The dashboard reports the gate; it has
never been able to move it.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_dashboard.py
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

from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import dashboard as D  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


# The two real shapes, copied from actual output rather than invented.
IMPORT_ERROR = (
    "Traceback (most recent call last):\n"
    '  File "C:\\Users\\bchen\\Quant_Research_Project'
    '\\test_hyp04_supply_chain_hedge_target.py", line 33, in <module>\n'
    "    import numpy as np  # noqa: E402\n"
    "    ^^^^^^^^^^^^^^^^^^\n"
    "ModuleNotFoundError: No module named 'numpy'\n"
)
WRAPPED_REFUSAL = (
    "Traceback (most recent call last):\n"
    '  File "test_hyp04_supply_chain_hedge_registry_v1_11.py", line 153\n'
    "    again, _ = build_v1_11()\n"
    "hyp04_supply_chain_hedge.make_registry_v1_6.RefusedError: the repository "
    "does not implement what v1.11 would declare: cannot build the session "
    "index: No module named 'exchange_calendars'\n"
)
HARNESS_FAILURE_STDOUT = (
    "PASS: 1a. something true\n"
    "FAIL: 1b. something false\n"
    "\n"
    "1 FAILURE(S): ['1b. something false']\n"
)


class _Proc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _run_with(outcomes: dict[str, _Proc]):
    """Drive run_test_suites over fabricated process results.

    The fake is on `subprocess.run` rather than on the classifier, so what is
    exercised is the code path the dashboard actually takes. It must never
    shell out: this suite is itself discovered by the dashboard's glob, and a
    real call here would run all forty-odd suites inside one of them.
    """
    names = list(outcomes)
    real_run, real_suites = D.subprocess.run, D.TEST_SUITES

    def fake_run(cmd, *a, **k):
        return outcomes[Path(cmd[1]).name]

    D.subprocess.run = fake_run
    D.TEST_SUITES = names
    try:
        return D.run_test_suites()
    finally:
        D.subprocess.run, D.TEST_SUITES = real_run, real_suites


def _by(res: dict, suite: str) -> dict:
    return next(r for r in res["suites"] if r["suite"] == suite)


def test_0_the_fake_reaches_the_real_code_path() -> None:
    """Negative control. If the fake were not wired in, everything below is
    vacuous -- so first show the fabricated result actually lands."""
    res = _run_with({"test_hyp04_supply_chain_hedge_dashboard.py":
                     _Proc(0, "PASS: a\nPASS: b\n")})
    check("0a. the fabricated process result is what got counted",
          res["available"] is True and res["total_passed"] == 2,
          str(res.get("total_passed")))
    check("0b. and TEST_SUITES was restored afterwards",
          len(D.TEST_SUITES) > 1)


def test_1_the_classifier_reads_the_reason() -> None:
    check("1a. a ModuleNotFoundError traceback yields the module name",
          D._missing_module(IMPORT_ERROR) == "numpy",
          repr(D._missing_module(IMPORT_ERROR)))
    check("1b. a genuine harness failure is NOT read as a missing module",
          D._missing_module(HARNESS_FAILURE_STDOUT) is None)
    check("1c. and neither is empty stderr", D._missing_module("") is None)
    check("1d. an unrelated traceback is not read as one either",
          D._missing_module("Traceback...\nValueError: nope\n") is None)
    check("1e. a WRAPPED absence is still an absence -- v1.11's generator "
          "re-raises it as a RefusedError",
          D._missing_module(WRAPPED_REFUSAL) == "exchange_calendars",
          repr(D._missing_module(WRAPPED_REFUSAL)))


def test_2_not_running_is_not_failing() -> None:
    """The bug, stated as a test: exit 1 for want of numpy is not a failure."""
    res = _run_with({
        "test_hyp04_supply_chain_hedge_target.py": _Proc(1, "", IMPORT_ERROR),
        "test_hyp04_supply_chain_hedge_dashboard.py":
            _Proc(1, HARNESS_FAILURE_STDOUT),
    })
    unrun = _by(res, "test_hyp04_supply_chain_hedge_target.py")
    real = _by(res, "test_hyp04_supply_chain_hedge_dashboard.py")
    check("2a. the unimportable suite reads NOT RUN, not FAIL",
          unrun["status"] == "NOT RUN", unrun["status"])
    check("2b. it names what was missing, so the reader can act",
          unrun["missing_module"] == "numpy")
    check("2c. the genuinely failing suite still reads FAIL",
          real["status"] == "FAIL", real["status"])
    check("2d. and is not mislabelled as a dependency problem",
          real["missing_module"] is None)
    check("2e. the checks that did not run are absent from the count, not "
          "counted false", unrun["passed"] == 0 and res["total_passed"] == 1)
    check("2f. both are surfaced at the top level",
          res["unrunnable"] == ["test_hyp04_supply_chain_hedge_target.py"]
          and res["missing_modules"] == ["numpy"], str(res["missing_modules"]))

    # The wrapped shape, which the first version of this classifier missed and
    # reported as the one FAILING suite on a page where nothing had failed.
    wrapped = _run_with({"test_hyp04_supply_chain_hedge_registry_v1_11.py":
                         _Proc(1, "PASS: A1. it is version 1.11\n",
                               WRAPPED_REFUSAL)})
    w = _by(wrapped, "test_hyp04_supply_chain_hedge_registry_v1_11.py")
    check("2g. a refusal that wraps a missing module reads NOT RUN",
          w["status"] == "NOT RUN" and w["missing_module"] == "exchange_calendars",
          f"{w['status']} / {w['missing_module']}")
    check("2h. the checks it DID print before dying are still counted",
          w["passed"] == 1)

    # The safety property that makes the widening above defensible. Stderr can
    # mention a missing module for any reason; a suite that reported a check
    # FALSE has failed, and must never be reclassified into silence.
    both = _run_with({"test_hyp04_supply_chain_hedge_dashboard.py":
                      _Proc(1, HARNESS_FAILURE_STDOUT, WRAPPED_REFUSAL)})
    b = _by(both, "test_hyp04_supply_chain_hedge_dashboard.py")
    check("2i. a suite that printed FAIL: stays FAIL even with a missing "
          "module on stderr -- a reported failure is never hidden",
          b["status"] == "FAIL" and b["missing_module"] is None,
          f"{b['status']} / {b['missing_module']}")
    check("2j. and it is not listed as unrunnable", both["unrunnable"] == [])


def test_3_all_green_stays_strict() -> None:
    """Softening `all_green` would be the wrong fix -- it would report an
    unrunnable environment as a healthy one."""
    res = _run_with({"test_hyp04_supply_chain_hedge_target.py":
                     _Proc(1, "", IMPORT_ERROR)})
    check("3a. nothing failed", not any(r["status"] == "FAIL"
                                        for r in res["suites"]))
    check("3b. and it is still NOT all green", res["all_green"] is False)

    ok = _run_with({"test_hyp04_supply_chain_hedge_dashboard.py":
                    _Proc(0, "PASS: a\n")})
    check("3c. the control: everything passing IS all green",
          ok["all_green"] is True and ok["unrunnable"] == []
          and ok["missing_modules"] == [])


def test_4_the_headline_word_changes() -> None:
    """What a reader actually sees. Asserted against rendered HTML, because
    the value being fixed is the one printed on the page."""
    audit, registry = D.read_audit(), D.read_registry()
    decision = D.current_decision()

    def page(res: dict) -> str:
        return D.render(res, audit, registry, decision)

    unrun = page(_run_with({"test_hyp04_supply_chain_hedge_target.py":
                            _Proc(1, "", IMPORT_ERROR)}))
    failing = page(_run_with({"test_hyp04_supply_chain_hedge_dashboard.py":
                              _Proc(1, HARNESS_FAILURE_STDOUT)}))
    green = page(_run_with({"test_hyp04_supply_chain_hedge_dashboard.py":
                            _Proc(0, "PASS: a\n")}))

    check("4a. nothing ran -> the page says NOT RUN, not FAILING",
          "NOT RUN" in unrun and "FAILING" not in unrun)
    check("4b. something failed -> the page still says FAILING",
          "FAILING" in failing)
    check("4c. all passed -> ALL GREEN",
          "ALL GREEN" in green and "NOT RUN" not in green)
    flat = " ".join(unrun.replace("<strong>", "").replace("</strong>", "").split())
    check("4d. the unrunnable page says how many, in words, not just a badge",
          "1 suite(s) did not run" in flat, flat[flat.find("suite(s)") - 40:][:120])
    check("4e. it names numpy and points at the requirements file",
          "numpy" in unrun and "requirements-hyp04.txt" in unrun)
    check("4f. and it does not claim those checks were counted false",
          "counted false" in unrun)

    # A suite whose FILE has gone is not a dependency gap, and the softest of
    # the three words must not be where an unanticipated status lands.
    gone = _run_with({"test_hyp04_supply_chain_hedge_no_such_suite.py":
                      _Proc(0, "PASS: never reached\n")})
    check("4g. a MISSING suite is classified MISSING",
          _by(gone, "test_hyp04_supply_chain_hedge_no_such_suite.py")["status"]
          == "MISSING")
    page_gone = page(gone)
    check("4h. and the page reads FAILING for it, not NOT RUN",
          "FAILING" in page_gone and "NOT RUN" not in page_gone)


def test_5_the_gate_is_reported_not_moved() -> None:
    """The dashboard reads the gate. It has never been able to change it, and
    a change to its test reporting must not have given it that power."""
    before = D.current_decision()
    _run_with({"test_hyp04_supply_chain_hedge_target.py":
               _Proc(1, "", IMPORT_ERROR)})
    after = D.current_decision()
    check("5a. the gate decision is unchanged by rendering",
          (before.open, len(before.denials))
          == (after.open, len(after.denials)))
    check("5b. and it is the real one, read from committed artifacts",
          after.status in ("OPEN", "CLOSED"), after.status)


if __name__ == "__main__":
    test_0_the_fake_reaches_the_real_code_path()
    test_1_the_classifier_reads_the_reason()
    test_2_not_running_is_not_failing()
    test_3_all_green_stays_strict()
    test_4_the_headline_word_changes()
    test_5_the_gate_is_reported_not_moved()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 DASHBOARD TESTS PASSED")
    sys.exit(0)
