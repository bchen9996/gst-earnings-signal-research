#!/usr/bin/env python3
"""ratify_hyp08.py tests -- offline except LOCAL git subprocess calls (no
network), same pattern every prior per-hypothesis ratify test file uses.

Nothing here calls either function with the real repo's own lock or the
real affirmation text in a way that would actually declare/authorize
anything real -- every fixture lock/authorization/closes/earnings file
below is synthetic, in a throwaway tempdir.

  DECLARE PHASE2 REFUSES EVERY JUDGEMENT (test_1). DECLARE PHASE2 WRITES
  ONLY THE OWNER FIELDS (test_2).

  DECLARE PHASE3 REFUSES EVERY JUDGEMENT (test_3) -- wrong affirmation, an
  undeclared Phase 2 lock, missing peer-closes/earnings files, an existing
  authorization, and an existing result all refuse.

  DECLARE PHASE3 WRITES A CORRECTLY PINNED AUTHORIZATION (test_4).

  THE TEMPLATES ARE PASTEABLE (test_5).

Run directly: python test_hyp04_supply_chain_hedge_ratify_hyp08.py
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
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from contextlib import redirect_stdout  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import ratify_hyp08 as R  # noqa: E402
from hyp04_supply_chain_hedge.ratify import RatifyError  # noqa: E402
from hyp04_supply_chain_hedge.make_freeze_draft import _sha256  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

def _draft_lock(tmp: Path) -> Path:
    """A syntactically-valid, undeclared HYP-08 Phase 2 lock draft."""
    p = tmp / "HYP08_PHASE2_LOCK_2026-09-14.json"
    p.write_text(json.dumps({
        "artifact": p.name,
        "locked_peers": ["BHE", "GLUC", "OMCL", "ICUI", "NGS"],
        "locked_anchors": ["ABT", "DVN", "MCK", "SNX"],
        "n_locked_events": 973,
        "n_locked_events_customer_supplier": 778,
        "n_locked_events_competitor": 195,
        "locked_events": [{"event_id": f"X-2016-0{i}-01"} for i in range(1, 3)],
        "model_spec": {"primary_cluster_key": "event_id", "residualize": False,
                       "test_family": {"k": 2}},
        "pins": {"target_same_session_py_sha256": "x", "inference_py_sha256": "y",
                "clustered_se_py_sha256": "z", "anchor_shock_py_sha256": "w",
                "sample_size_gate_py_sha256": "v",
                "hyp06_phase2_lock_sha256": "u", "hyp07_phase2_lock_sha256": "t"},
        "declared": False, "declared_by": "", "declared_date": "",
        "status": "DRAFT -- inert until declared",
    }, indent=1), encoding="utf-8")
    return p


def _git_repo(tmp: Path) -> Path:
    for cmd in (("init", "-q"), ("config", "user.email", "t@t"),
               ("config", "user.name", "t")):
        subprocess.run(("git", *cmd), cwd=str(tmp), capture_output=True)
    (tmp / "README").write_text("fixture\n", encoding="utf-8")
    _commit_all(tmp)
    return tmp


def _commit_all(tmp: Path) -> None:
    subprocess.run(("git", "add", "-A"), cwd=str(tmp), capture_output=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture step"), cwd=str(tmp),
                   capture_output=True)


def _peer_data(tmp: Path) -> tuple[Path, Path]:
    closes = tmp / "closes.csv"
    earnings = tmp / "earnings.json"
    closes.write_text(
        "ticker,session_date,close\nBHE,2016-01-04,10.0\nSPY,2016-01-04,200.0\n",
        encoding="utf-8")
    earnings.write_text(json.dumps({"per_peer_earnings_releases": {}}),
                        encoding="utf-8")
    return closes, earnings


# --------------------------------------------------------------------------
# phase2
# --------------------------------------------------------------------------

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
                                  affirmation=R.HYP08_PHASE2_AFFIRMATION)
            check("1b. blank-placeholder declared-by refuses", False)
        except RatifyError:
            check("1b. blank-placeholder declared-by refuses", True)

        out = R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                                    affirmation=R.HYP08_PHASE2_AFFIRMATION)
        check("1c. a correct declaration succeeds",
              out["declared_by"] == "bchen9996", str(out))
        check("1d. locked_peers/locked_anchors are carried through the "
              "return value",
              out["locked_peers"] == ["BHE", "GLUC", "OMCL", "ICUI", "NGS"]
              and out["locked_anchors"] == ["ABT", "DVN", "MCK", "SNX"], str(out))

        try:
            R.declare_phase2_lock(lock_path=lock, declared_by="someone else",
                                  affirmation=R.HYP08_PHASE2_AFFIRMATION)
            check("1e. re-declaring an already-declared lock refuses", False)
        except RatifyError:
            check("1e. re-declaring an already-declared lock refuses", True)


def test_2_declare_phase2_writes_only_owner_fields() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        lock = _draft_lock(tmp)
        before = json.loads(lock.read_text())

        R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                              affirmation=R.HYP08_PHASE2_AFFIRMATION)
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


# --------------------------------------------------------------------------
# phase3
# --------------------------------------------------------------------------

def test_3_declare_phase3_refuses_every_judgement() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = _git_repo(Path(td))
        lock = _draft_lock(tmp)
        closes, earnings = _peer_data(tmp)

        try:
            R.declare_phase3_authorization(
                out_path=tmp / "auth.json", phase2_lock_path=lock,
                peer_closes_path=closes, peer_earnings_path=earnings,
                declared_by="bchen9996", affirmation=R.HYP08_PHASE3_AFFIRMATION,
                repo=tmp)
            check("3a. undeclared Phase 2 lock refuses", False)
        except RatifyError:
            check("3a. undeclared Phase 2 lock refuses", True)

        R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                              affirmation=R.HYP08_PHASE2_AFFIRMATION)
        _commit_all(tmp)

        try:
            R.declare_phase3_authorization(
                out_path=tmp / "auth_missing.json", phase2_lock_path=lock,
                peer_closes_path=tmp / "nope.csv", peer_earnings_path=earnings,
                declared_by="bchen9996", affirmation=R.HYP08_PHASE3_AFFIRMATION,
                repo=tmp)
            check("3b. missing peer-closes file refuses", False)
        except RatifyError as e:
            check("3b. missing peer-closes file refuses",
                  "peer closes" in str(e), str(e))

        try:
            R.declare_phase3_authorization(
                out_path=tmp / "auth2.json", phase2_lock_path=lock,
                peer_closes_path=closes, peer_earnings_path=earnings,
                declared_by="bchen9996", affirmation="not it", repo=tmp)
            check("3c. wrong affirmation refuses", False)
        except RatifyError:
            check("3c. wrong affirmation refuses", True)
        check("3c-untouched. nothing written on refusal",
              not (tmp / "auth2.json").exists())

        auth = tmp / "HYP08_PHASE3_AUTHORIZATION_2026-09-14.json"
        R.declare_phase3_authorization(
            out_path=auth, phase2_lock_path=lock, peer_closes_path=closes,
            peer_earnings_path=earnings, declared_by="bchen9996",
            affirmation=R.HYP08_PHASE3_AFFIRMATION, repo=tmp)

        try:
            R.declare_phase3_authorization(
                out_path=tmp / "HYP08_PHASE3_AUTHORIZATION_2026-09-15.json",
                phase2_lock_path=lock, peer_closes_path=closes,
                peer_earnings_path=earnings, declared_by="bchen9996",
                affirmation=R.HYP08_PHASE3_AFFIRMATION, repo=tmp)
            check("3d. a second authorization file refuses", False)
        except RatifyError:
            check("3d. a second authorization file refuses", True)

        (tmp / "HYP08_PHASE3_RESULT_2026-09-15.json").write_text("{}")
        auth.unlink()
        try:
            R.declare_phase3_authorization(
                out_path=auth, phase2_lock_path=lock, peer_closes_path=closes,
                peer_earnings_path=earnings, declared_by="bchen9996",
                affirmation=R.HYP08_PHASE3_AFFIRMATION, repo=tmp)
            check("3e. an existing result refuses a fresh authorization", False)
        except RatifyError:
            check("3e. an existing result refuses a fresh authorization", True)


def test_4_declare_phase3_writes_correct_pins() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = _git_repo(Path(td))
        lock = _draft_lock(tmp)
        closes, earnings = _peer_data(tmp)
        R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                              affirmation=R.HYP08_PHASE2_AFFIRMATION)
        _commit_all(tmp)

        auth = tmp / "HYP08_PHASE3_AUTHORIZATION_2026-09-14.json"
        out = R.declare_phase3_authorization(
            out_path=auth, phase2_lock_path=lock, peer_closes_path=closes,
            peer_earnings_path=earnings, declared_by="bchen9996",
            affirmation=R.HYP08_PHASE3_AFFIRMATION, repo=tmp)

        doc = json.loads(auth.read_text())
        check("4a. declared is true", doc["declared"] is True)
        check("4b. consumed starts false", doc["consumed"] is False)
        check("4c. pinned commit sha is a real 40-char sha",
              len(doc["pinned_commit_sha"]) == 40, doc["pinned_commit_sha"])
        check("4d. pinned lock hash matches the lock on disk",
              doc["pinned_phase2_lock_sha256"] == _sha256(lock))
        check("4e. pinned peer-closes hash matches the file on disk",
              doc["pinned_peer_closes_sha256"] == _sha256(closes))
        check("4f. pinned peer-earnings hash matches the file on disk",
              doc["pinned_peer_earnings_sha256"] == _sha256(earnings))
        check("4g. attestation text is the real affirmation",
              doc["attestation_text"] == R.HYP08_PHASE3_AFFIRMATION)
        check("4h. return value echoes the pinned commit",
              out["pinned_commit_sha"] == doc["pinned_commit_sha"])


# --------------------------------------------------------------------------
# templates
# --------------------------------------------------------------------------

def test_5_templates_are_pasteable() -> None:
    for name, fn, affirm in (
        ("phase2", R._print_phase2_template, R.HYP08_PHASE2_AFFIRMATION),
        ("phase3", R._print_phase3_template, R.HYP08_PHASE3_AFFIRMATION),
    ):
        out = io.StringIO()
        with redirect_stdout(out):
            fn()
        text = out.getvalue()
        check(f"5a. {name} template reproduces the affirmation verbatim",
              affirm in text)
        check(f"5b. {name} template names its own module",
              "ratify_hyp08" in text, text[:200])
        check(f"5c. {name} template leaves no <your name> unresolved "
              "as the command to run",
              '--declared-by "<your name>"' in text, text[:200])


def test_6_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("6a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("6a. network blocked", True)


if __name__ == "__main__":
    test_1_declare_phase2_refuses_every_judgement()
    test_2_declare_phase2_writes_only_owner_fields()
    test_3_declare_phase3_refuses_every_judgement()
    test_4_declare_phase3_writes_correct_pins()
    test_5_templates_are_pasteable()
    test_6_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL RATIFY_HYP08 TESTS PASSED")
    sys.exit(0)
