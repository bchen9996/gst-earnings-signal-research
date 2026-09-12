#!/usr/bin/env python3
"""ratify_hyp05.py tests -- offline except for LOCAL git subprocess calls.

`declare_phase3_authorization` calls `make_freeze_draft._commit_sha`, which
shells out to a real, local `git` binary (no network) -- exercised here via
a real, throwaway git repo, the same pattern
`test_hyp04_supply_chain_hedge_freeze_draft.py` already uses for the
identical reason ("so _commit_sha is exercised rather than faked").

  DECLARE PHASE2 REFUSES EVERY JUDGEMENT (test_1) -- wrong affirmation,
  placeholder declared-by (including the angle-bracket partial-substitution
  bug caught 2026-09-10), and a second declaration over an already-declared
  lock all refuse; nothing is written on any refusal path.

  DECLARE PHASE2 WRITES ONLY THE OWNER FIELDS (test_2) -- every other key
  in the draft is byte-identical before and after.

  DECLARE PHASE3 REFUSES EVERY JUDGEMENT (test_3) -- wrong affirmation, an
  undeclared Phase 2 lock, an existing authorization, and an existing
  result all refuse.

  DECLARE PHASE3 WRITES A CORRECTLY PINNED AUTHORIZATION (test_4) -- pins
  the real commit sha and the real lock's sha256, unconsumed.

  THE TEMPLATES ARE PASTEABLE (test_5) -- one line, the exact affirmation
  text reproduced verbatim, no template placeholder left unresolved.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_ratify_hyp05.py
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

from hyp04_supply_chain_hedge import ratify_hyp05 as R  # noqa: E402
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
    """A syntactically-valid, undeclared HYP-05 Phase 2 lock draft."""
    p = tmp / "HYP05_PHASE2_LOCK_2026-09-12.json"
    p.write_text(json.dumps({
        "artifact": p.name,
        "locked_peer": "AMBA",
        "locked_anchor": "NVDA",
        "n_locked_events": 8,
        "locked_events": [{"event_id": f"NVDA-2016-0{i}-01"} for i in range(1, 9)],
        "model_spec": {"primary_cluster_key": "event_id", "residualize": True,
                       "n_permutations": 2000, "random_seed": 42},
        "pins": {"target_py_sha256": "x", "constants_py_sha256": "y",
                "clustered_se_py_sha256": "z"},
        "declared": False, "declared_by": "", "declared_date": "",
        "status": "DRAFT -- inert until declared",
    }, indent=1), encoding="utf-8")
    return p


def _git_repo(tmp: Path) -> Path:
    """A real, clean, throwaway git repo so _commit_sha is exercised for
    real -- same pattern as test_hyp04_supply_chain_hedge_freeze_draft.py."""
    for cmd in (("init", "-q"), ("config", "user.email", "t@t"),
               ("config", "user.name", "t")):
        subprocess.run(("git", *cmd), cwd=str(tmp), capture_output=True)
    (tmp / "README").write_text("fixture\n", encoding="utf-8")
    _commit_all(tmp)
    return tmp


def _commit_all(tmp: Path) -> None:
    """Commit whatever is pending -- _commit_sha requires a CLEAN tree, so
    every fixture step that touches a file inside `tmp` (declaring the
    Phase 2 lock included) must be committed before a call that reaches
    _commit_sha."""
    subprocess.run(("git", "add", "-A"), cwd=str(tmp), capture_output=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture step"), cwd=str(tmp),
                   capture_output=True)


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
                                  affirmation=R.HYP05_PHASE2_AFFIRMATION)
            check("1b. blank-placeholder declared-by refuses", False)
        except RatifyError:
            check("1b. blank-placeholder declared-by refuses", True)

        try:
            R.declare_phase2_lock(lock_path=lock, declared_by="<bchen9996>",
                                  affirmation=R.HYP05_PHASE2_AFFIRMATION)
            check("1c. angle-bracket partial substitution refuses", False)
        except RatifyError as e:
            check("1c. angle-bracket partial substitution refuses", True)
            check("1c-detail. names the surviving brackets",
                  "bracket" in str(e).lower(), str(e))

        out = R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                                    affirmation=R.HYP05_PHASE2_AFFIRMATION)
        check("1d. a correct declaration succeeds",
              out["declared_by"] == "bchen9996", str(out))

        try:
            R.declare_phase2_lock(lock_path=lock, declared_by="someone else",
                                  affirmation=R.HYP05_PHASE2_AFFIRMATION)
            check("1e. re-declaring an already-declared lock refuses", False)
        except RatifyError:
            check("1e. re-declaring an already-declared lock refuses", True)


def test_2_declare_phase2_writes_only_owner_fields() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        lock = _draft_lock(tmp)
        before = json.loads(lock.read_text())

        R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                              affirmation=R.HYP05_PHASE2_AFFIRMATION)
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

        # undeclared lock -> refuses before the affirmation is even checked
        try:
            R.declare_phase3_authorization(
                out_path=tmp / "auth.json", phase2_lock_path=lock,
                declared_by="bchen9996", affirmation=R.HYP05_PHASE3_AFFIRMATION,
                repo=tmp)
            check("3a. undeclared Phase 2 lock refuses", False)
        except RatifyError:
            check("3a. undeclared Phase 2 lock refuses", True)

        R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                              affirmation=R.HYP05_PHASE2_AFFIRMATION)
        _commit_all(tmp)  # _commit_sha requires a clean tree from here on

        try:
            R.declare_phase3_authorization(
                out_path=tmp / "auth2.json", phase2_lock_path=lock,
                declared_by="bchen9996", affirmation="not it", repo=tmp)
            check("3b. wrong affirmation refuses", False)
        except RatifyError:
            check("3b. wrong affirmation refuses", True)
        check("3b-untouched. nothing written on refusal",
              not (tmp / "auth2.json").exists())

        auth = tmp / "HYP05_PHASE3_AUTHORIZATION_2026-09-12.json"
        R.declare_phase3_authorization(
            out_path=auth, phase2_lock_path=lock, declared_by="bchen9996",
            affirmation=R.HYP05_PHASE3_AFFIRMATION, repo=tmp)

        try:
            R.declare_phase3_authorization(
                out_path=tmp / "HYP05_PHASE3_AUTHORIZATION_2026-09-13.json",
                phase2_lock_path=lock, declared_by="bchen9996",
                affirmation=R.HYP05_PHASE3_AFFIRMATION, repo=tmp)
            check("3c. a second authorization file refuses", False)
        except RatifyError:
            check("3c. a second authorization file refuses", True)

        (tmp / "HYP05_PHASE3_RESULT_2026-09-13.json").write_text("{}")
        auth.unlink()
        try:
            R.declare_phase3_authorization(
                out_path=auth, phase2_lock_path=lock, declared_by="bchen9996",
                affirmation=R.HYP05_PHASE3_AFFIRMATION, repo=tmp)
            check("3d. an existing result refuses a fresh authorization", False)
        except RatifyError:
            check("3d. an existing result refuses a fresh authorization", True)


def test_4_declare_phase3_writes_correct_pins() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = _git_repo(Path(td))
        lock = _draft_lock(tmp)
        R.declare_phase2_lock(lock_path=lock, declared_by="bchen9996",
                              affirmation=R.HYP05_PHASE2_AFFIRMATION)
        _commit_all(tmp)  # _commit_sha requires a clean tree from here on

        auth = tmp / "HYP05_PHASE3_AUTHORIZATION_2026-09-12.json"
        out = R.declare_phase3_authorization(
            out_path=auth, phase2_lock_path=lock, declared_by="bchen9996",
            affirmation=R.HYP05_PHASE3_AFFIRMATION, repo=tmp)

        doc = json.loads(auth.read_text())
        check("4a. declared is true", doc["declared"] is True)
        check("4b. consumed starts false", doc["consumed"] is False)
        check("4c. pinned commit sha is a real 40-char sha",
              len(doc["pinned_commit_sha"]) == 40, doc["pinned_commit_sha"])
        check("4d. pinned lock hash matches the lock on disk",
              doc["pinned_phase2_lock_sha256"] == _sha256(lock))
        check("4e. attestation text is the real affirmation",
              doc["attestation_text"] == R.HYP05_PHASE3_AFFIRMATION)
        check("4f. return value echoes the pinned commit",
              out["pinned_commit_sha"] == doc["pinned_commit_sha"])


# --------------------------------------------------------------------------
# templates
# --------------------------------------------------------------------------

def test_5_templates_are_pasteable() -> None:
    for name, fn, affirm in (
        ("phase2", R._print_phase2_template, R.HYP05_PHASE2_AFFIRMATION),
        ("phase3", R._print_phase3_template, R.HYP05_PHASE3_AFFIRMATION),
    ):
        out = io.StringIO()
        with redirect_stdout(out):
            fn()
        text = out.getvalue()
        check(f"5a. {name} template reproduces the affirmation verbatim",
              affirm in text)
        check(f"5b. {name} template names its own module",
              "ratify_hyp05" in text, text[:200])
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
    print("ALL RATIFY_HYP05 TESTS PASSED")
    sys.exit(0)
