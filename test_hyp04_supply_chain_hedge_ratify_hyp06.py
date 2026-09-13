#!/usr/bin/env python3
"""ratify_hyp06.py tests -- offline, hermetic, no network, no git (unlike
ratify_hyp05.py's phase3 tests, declare_phase2_lock never reaches
_commit_sha, so no real git fixture is needed here either).

Also asserts the STRUCTURAL boundary this module exists to enforce: there
is no phase3 subcommand at all, not merely an unfinished one.

Run directly: python test_hyp04_supply_chain_hedge_ratify_hyp06.py
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

import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import ratify_hyp06 as R  # noqa: E402
from hyp04_supply_chain_hedge.ratify import RatifyError  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _draft_lock(tmp: Path) -> Path:
    """A syntactically-valid, undeclared HYP-06 Phase 2 lock draft."""
    p = tmp / "HYP06_PHASE2_LOCK_2026-09-13.json"
    p.write_text(json.dumps({
        "artifact": p.name,
        "locked_peers": ["CKX", "KTCC"],
        "locked_anchors": ["EOG", "CLX"],
        "n_locked_events": 778,
        "locked_events": [{"event_id": f"X-2016-0{i}-01"} for i in range(1, 3)],
        "model_spec": {"primary_cluster_key": "event_id", "residualize": True,
                       "n_permutations": 2000, "random_seed": 42},
        "pins": {"target_py_sha256": "x", "constants_py_sha256": "y",
                "clustered_se_py_sha256": "z"},
        "declared": False, "declared_by": "", "declared_date": "",
        "status": "DRAFT -- inert until declared",
    }, indent=1), encoding="utf-8")
    return p


def test_1_declare_phase2_refuses_every_judgement() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        lock = _draft_lock(tmp)

        try:
            R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                                  affirmation="close but not it")
            check("1a. wrong affirmation refuses", False, "it did not raise")
        except RatifyError:
            check("1a. wrong affirmation refuses", True)
        check("1a-untouched. nothing written on refusal",
              json.loads(lock.read_text())["declared"] is False)

        try:
            R.declare_phase2_lock(lock_path=lock, declared_by="<your name>",
                                  affirmation=R.HYP06_PHASE2_AFFIRMATION)
            check("1b. blank-placeholder declared-by refuses", False)
        except RatifyError:
            check("1b. blank-placeholder declared-by refuses", True)

        out = R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                                    affirmation=R.HYP06_PHASE2_AFFIRMATION)
        check("1c. a correct declaration succeeds",
              out["declared_by"] == "bchen9996", str(out))
        check("1d. locked_peers/locked_anchors are carried through the "
              "return value", out["locked_peers"] == ["CKX", "KTCC"]
              and out["locked_anchors"] == ["EOG", "CLX"], str(out))

        try:
            R.declare_phase2_lock(lock_path=lock, declared_by="someone else",
                                  affirmation=R.HYP06_PHASE2_AFFIRMATION)
            check("1e. re-declaring an already-declared lock refuses", False)
        except RatifyError:
            check("1e. re-declaring an already-declared lock refuses", True)


def test_2_declare_phase2_writes_only_owner_fields() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        lock = _draft_lock(tmp)
        before = json.loads(lock.read_text())

        R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                              affirmation=R.HYP06_PHASE2_AFFIRMATION)
        after = json.loads(lock.read_text())

        moved = sorted(k for k in set(before) | set(after)
                       if before.get(k) != after.get(k))
        check("2a. only declared/declared_by/declared_date/status/"
              "attestation_text moved",
              set(moved) == {"declared", "declared_by", "declared_date",
                            "status", "attestation_text"}, str(moved))
        check("2b. every other field is byte-identical",
              all(before[k] == after[k] for k in before
                  if k not in moved), "mismatch")


def test_3_there_is_no_phase3_subcommand() -> None:
    """The structural boundary this module exists to enforce -- see
    module docstring. Not an oversight; asserted directly so a future
    edit that quietly adds one is caught here, not discovered live."""
    import io
    from contextlib import redirect_stderr

    err = io.StringIO()
    try:
        with redirect_stderr(err):
            R.main(["phase3"])
        check("3a. 'phase3' is not a recognized subcommand", False,
              "argparse accepted it")
    except SystemExit as e:
        check("3a. 'phase3' is not a recognized subcommand", e.code != 0,
              str(e.code))
        check("3b. argparse's own error names it as invalid",
              "invalid choice" in err.getvalue().lower(), err.getvalue())


def test_4_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("4a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("4a. network blocked", True)


if __name__ == "__main__":
    test_1_declare_phase2_refuses_every_judgement()
    test_2_declare_phase2_writes_only_owner_fields()
    test_3_there_is_no_phase3_subcommand()
    test_4_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL RATIFY_HYP06 TESTS PASSED")
    sys.exit(0)
