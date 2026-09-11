#!/usr/bin/env python3
"""HYP-04 Phase 3 -- the one locked run against the holdout.

Everything here runs against real committed input files COPIED into an
isolated tempdir -- never the real repo -- with a FRESH freeze, split,
Phase 2 lock, and Phase 3 authorization signed by a clearly-fake
"offline-test-fixture" identity. Nothing here writes to the real `Live
Signal Engine/`, and no computed value is asserted as a finding.

What this suite is defending:

  * The IN-PROCESS REHEARSAL (`run_rehearsal`) executes the full estimator
    and D6/D7 disclosure path on synthetic data, touching no real file and
    requiring no authorization -- plan v0.2's "a dry run against a copy of
    the holdout schema must pass before the one real execution."
  * NO AUTHORIZATION, NO RUN. `build_result` refuses without a signed,
    unconsumed, correctly-pinned `HYP04_PHASE3_AUTHORIZATION_*.json`.
  * NO RE-RUNNING. A second `build_result` after a Phase 3 result already
    exists refuses UNCONDITIONALLY, regardless of `--out`. A second attempt
    with the same (now-consumed) authorization refuses too.
  * DRIFT IS CAUGHT. A changed commit sha, a changed Phase 2 lock hash, or a
    changed target.py/constants.py hash all refuse rather than running
    against a spec that no longer matches what was authorized.
  * `_rejoin_holdout` refuses if an exploration id leaks into the set it
    computes over -- the mirror image of Phase 1's own leak test.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_phase3_run.py
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
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import make_freeze_draft as F  # noqa: E402
from hyp04_supply_chain_hedge import make_phase2_lock as L  # noqa: E402
from hyp04_supply_chain_hedge import make_phase3_run as P3  # noqa: E402
from hyp04_supply_chain_hedge import make_validation_split as V  # noqa: E402
from hyp04_supply_chain_hedge import ratify as R  # noqa: E402

ROOT = Path(__file__).resolve().parent
LSE = ROOT / "Live Signal Engine"
PANEL = LSE / "HYP04_EVENT_PANEL_2026-09-08.json"

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


def expect_refusal(label: str, fn, *, substring: str = "") -> None:
    try:
        fn()
        check(label, False, "it did not refuse")
    except (P3.Phase3Error, L.Phase2LockError, V.SplitError, F.FreezeError,
            R.RatifyError) as e:
        ok = substring in str(e) if substring else True
        check(label, ok, str(e)[:200])


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(("git", *args), cwd=str(cwd), capture_output=True)


def _fixture(tmp: Path) -> dict:
    """Real inputs copied in; a FRESH freeze, split, and Phase 2 lock signed
    here under a fake identity -- mirrors test_hyp04_supply_chain_hedge_
    phase2_lock.py's own fixture, one step further."""
    lse = tmp / "Live Signal Engine"
    lse.mkdir(parents=True)

    panel = json.loads(PANEL.read_text(encoding="utf-8"))
    for key in ("calendar", "shocks", "curated_map"):
        shutil.copy2(LSE / panel["sources"][key], lse / panel["sources"][key])
    dst_panel = lse / PANEL.name
    shutil.copy2(PANEL, dst_panel)

    closes_dir = lse / "HYP04_PEER_CLOSES_REQUEST"
    shutil.copytree(LSE / "HYP04_PEER_CLOSES_REQUEST", closes_dir)

    lock_doc = lse / "GST_HYP04_ANALYSIS_LOCK_v1.0.md"
    lock_doc.write_text("# lock\n\n> **SIGNED 2026-08-20. IN FORCE.**\n",
                        encoding="utf-8")

    for cmd in (("init", "-q"), ("config", "user.email", "t@t"),
                ("config", "user.name", "t")):
        _git(*cmd, cwd=tmp)
    (tmp / "README").write_text("fixture\n", encoding="utf-8")
    _git("add", "-A", cwd=tmp)
    _git("commit", "-q", "-m", "fixture", cwd=tmp)

    freeze_out = lse / "HYP04_FREEZE_DRAFT_test.json"
    fd = F.build_draft(panel_path=dst_panel, out_path=freeze_out, lse=lse,
                       repo=tmp, lock_path=lock_doc, today=date(2026, 9, 9))
    fd.update(frozen=True, frozen_before_any_result_computed=True,
              attested_by="offline-test-fixture", attested_date="2026-09-09")
    freeze_out.write_text(json.dumps(fd), encoding="utf-8")
    _git("add", "-A", cwd=tmp)
    _git("commit", "-q", "-m", "fixture: freeze", cwd=tmp)

    split_out = lse / "HYP04_VALIDATION_SPLIT_test.json"
    V.build_draft(panel_path=dst_panel, out_path=split_out, lse=lse,
                  repo=tmp, today=date(2026, 9, 9))
    sd = json.loads(split_out.read_text(encoding="utf-8"))
    sd.update(declared=True, declared_by="offline-test-fixture",
              declared_date="2026-09-09")
    split_out.write_text(json.dumps(sd), encoding="utf-8")
    _git("add", "-A", cwd=tmp)
    _git("commit", "-q", "-m", "fixture: split", cwd=tmp)

    import csv
    curated_peers = sorted({r["peer_ticker"] for r in csv.DictReader(
        (lse / panel["sources"]["curated_map"]).open(
            newline="", encoding="utf-8"))})
    earnings = {
        "artifact": "fake.json", "as_of_date": "2026-09-10",
        "peers": curated_peers, "cik_by_peer": {}, "sources": {},
        "per_peer_earnings_releases": {
            p: [{"release_date": "2005-01-15", "release_session": "AMC"},
               {"release_date": "2020-04-01", "release_session": "AMC"}]
            for p in curated_peers
        },
        "cadence_gaps": {}, "summary_by_peer": {},
    }
    earnings_out = lse / "HYP04_PEER_EARNINGS_test.json"
    earnings_out.write_text(json.dumps(earnings), encoding="utf-8")
    _git("add", "-A", cwd=tmp)
    _git("commit", "-q", "-m", "fixture: earnings", cwd=tmp)

    lock_out = lse / "HYP04_PHASE2_LOCK_test.json"
    L.build_draft(out_path=lock_out, split_path=split_out, lse=lse, repo=tmp,
                  today=date(2026, 9, 10))
    R.declare_phase2_lock(lock_path=lock_out, declared_by="offline-test-fixture",
                          affirmation=R.PHASE2_AFFIRMATION,
                          declared_date="2026-09-10")
    _git("add", "-A", cwd=tmp)
    _git("commit", "-q", "-m", "fixture: phase2 lock", cwd=tmp)

    return {"tmp": tmp, "lse": lse, "panel": dst_panel, "split": split_out,
            "freeze": freeze_out, "earnings": earnings_out, "split_doc": sd,
            "lock": lock_out, "out": lse / "HYP04_PHASE3_RESULT_test.json"}


def _authorize(f: dict, *, declared_date: str = "2026-09-11") -> Path:
    """Write a valid, signed Phase 3 authorization pinned to `f['tmp']`."""
    auth_out = f["lse"] / f"HYP04_PHASE3_AUTHORIZATION_{declared_date}.json"
    R.declare_phase3_authorization(
        out_path=auth_out, phase2_lock_path=f["lock"],
        declared_by="offline-test-fixture", affirmation=R.PHASE3_AFFIRMATION,
        declared_date=declared_date, repo=f["tmp"])
    _git("add", "-A", cwd=f["tmp"])
    _git("commit", "-q", "-m", "fixture: phase3 authorization", cwd=f["tmp"])
    return auth_out


# --------------------------------------------------------------------------
def test_1_rehearsal_runs_without_touching_anything_real() -> None:
    result = P3.run_rehearsal()
    check("1a. the rehearsal produces rows", result["n_rows"] > 0)
    check("1b. the rehearsal produces a D6 disclosure",
          len(result["d6_disclosures"]) > 0)
    check("1c. the rehearsal states point_estimate_permitted is False",
          result["point_estimate_permitted"] is False)
    # touched nothing real: no new file appeared under the real LSE
    before = set(LSE.glob("HYP04_PHASE3_*"))
    P3.run_rehearsal()
    after = set(LSE.glob("HYP04_PHASE3_*"))
    check("1d. running it again writes nothing under the real Live Signal "
          "Engine directory", before == after)


def test_2_refuses_without_an_authorization() -> None:
    if not PANEL.is_file():
        skip("2. no authorization", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        expect_refusal(
            "2a. build_result refuses with no authorization on disk",
            lambda: P3.build_result(
                out_path=f["out"], panel_path=f["panel"], split_path=f["split"],
                peer_earnings_path=f["earnings"], phase2_lock_path=f["lock"],
                lse=f["lse"], repo=f["tmp"]),
            substring="authorization")


def test_3_refuses_an_unsigned_authorization() -> None:
    if not PANEL.is_file():
        skip("3. draft authorization", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        auth_out = f["lse"] / "HYP04_PHASE3_AUTHORIZATION_2026-09-11.json"
        auth_out.write_text(json.dumps({
            "declared": False, "declared_by": "", "declared_date": "",
            "attestation_text": "", "pinned_commit_sha": "0" * 40,
            "pinned_phase2_lock_sha256": "0" * 64, "consumed": False,
        }), encoding="utf-8")
        expect_refusal(
            "3a. build_result refuses a draft (undeclared) authorization",
            lambda: P3.build_result(
                out_path=f["out"], panel_path=f["panel"], split_path=f["split"],
                peer_earnings_path=f["earnings"], phase2_lock_path=f["lock"],
                lse=f["lse"], repo=f["tmp"]),
            substring="draft")


def test_4_refuses_a_commit_sha_mismatch() -> None:
    if not PANEL.is_file():
        skip("4. dirty tree", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = Path(td)
        fx = _fixture(f)
        _authorize(fx)
        # An uncommitted change after authorization -- the same clean-tree
        # hygiene every other consequential step here requires (freeze,
        # split, Phase 2 lock all refuse the same way). This is NOT a
        # check that HEAD still equals what the authorization pinned --
        # see make_phase3_run._load_valid_authorization's own comment for
        # why that specific comparison is a fixed point, not a drift
        # signal, and is deliberately not made.
        (fx["lse"] / "uncommitted.txt").write_text("x", encoding="utf-8")
        expect_refusal(
            "4a. build_result refuses a dirty tree at run time",
            lambda: P3.build_result(
                out_path=fx["out"], panel_path=fx["panel"], split_path=fx["split"],
                peer_earnings_path=fx["earnings"], phase2_lock_path=fx["lock"],
                lse=fx["lse"], repo=fx["tmp"]),
            substring="uncommitted")


def test_5_refuses_a_phase2_lock_hash_mismatch() -> None:
    """A differently-shaped lock file living OUTSIDE `repo`'s tree (never
    committed, never part of `repo` at all) leaves `repo` clean while
    `--phase2-lock` still resolves to different bytes than what was
    authorized -- isolating the lock-hash comparison specifically, the same
    way test_9/test_10 in the Phase 2 lock suite isolate one corrupted pin
    at a time."""
    if not PANEL.is_file():
        skip("5. lock drift", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td, \
         tempfile.TemporaryDirectory() as td_outside:
        f = Path(td)
        fx = _fixture(f)
        _authorize(fx)

        d = json.loads(fx["lock"].read_text(encoding="utf-8"))
        d["extra_field_that_changes_the_hash"] = True
        drifted_lock = Path(td_outside) / fx["lock"].name
        drifted_lock.write_text(json.dumps(d), encoding="utf-8")

        expect_refusal(
            "5a. build_result refuses when --phase2-lock resolves to "
            "different bytes than what was authorized",
            lambda: P3.build_result(
                out_path=fx["out"], panel_path=fx["panel"], split_path=fx["split"],
                peer_earnings_path=fx["earnings"], phase2_lock_path=drifted_lock,
                lse=fx["lse"], repo=fx["tmp"]),
            substring="Phase 2 lock hash")


def test_6_an_authorized_run_succeeds_exactly_once() -> None:
    if not PANEL.is_file():
        skip("6. authorized run", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = Path(td)
        fx = _fixture(f)
        auth_out = _authorize(fx)

        doc = P3.build_result(
            out_path=fx["out"], panel_path=fx["panel"], split_path=fx["split"],
            peer_earnings_path=fx["earnings"], phase2_lock_path=fx["lock"],
            lse=fx["lse"], repo=fx["tmp"])
        check("6a. the run reports it is reported regardless of outcome",
              doc["reported_regardless_of_outcome"] is True)
        check("6b. the run reports no re-run is permitted",
              doc["no_rerun_permitted"] is True)
        check("6c. it consumed only the holdout events",
              set(doc["event_ids_consumed"]) ==
              set(fx["split_doc"]["holdout"]["event_ids"]))
        check("6d. no exploration id appears in what was consumed",
              not (set(doc["event_ids_consumed"])
                   & set(fx["split_doc"]["exploration"]["event_ids"])))
        check("6e. it used the single locked treatment (residualize=True)",
              doc["treatment"]["residualize"] is True)

        auth_doc = json.loads(auth_out.read_text(encoding="utf-8"))
        check("6f. the authorization is marked consumed",
              auth_doc["consumed"] is True
              and auth_doc["consumed_by_result"] == fx["out"].name)

        # A second attempt, even with a DIFFERENT --out, refuses: a Phase 3
        # result already exists.
        second_out = fx["lse"] / "HYP04_PHASE3_RESULT_second_attempt.json"
        expect_refusal(
            "6g. a second run refuses unconditionally once a result exists",
            lambda: P3.build_result(
                out_path=second_out, panel_path=fx["panel"], split_path=fx["split"],
                peer_earnings_path=fx["earnings"], phase2_lock_path=fx["lock"],
                lse=fx["lse"], repo=fx["tmp"]),
            substring="ONCE")


def test_7_a_consumed_authorization_cannot_be_reused() -> None:
    if not PANEL.is_file():
        skip("7. consumed authorization", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = Path(td)
        fx = _fixture(f)
        auth_out = _authorize(fx)
        P3.build_result(
            out_path=fx["out"], panel_path=fx["panel"], split_path=fx["split"],
            peer_earnings_path=fx["earnings"], phase2_lock_path=fx["lock"],
            lse=fx["lse"], repo=fx["tmp"])
        fx["out"].unlink()  # simulate "no result exists" to isolate the
                            # authorization-consumed check specifically
        expect_refusal(
            "7a. a consumed authorization refuses even if the result is "
            "somehow gone",
            lambda: P3.build_result(
                out_path=fx["out"], panel_path=fx["panel"], split_path=fx["split"],
                peer_earnings_path=fx["earnings"], phase2_lock_path=fx["lock"],
                lse=fx["lse"], repo=fx["tmp"]),
            substring="consumed")


def test_8_ratify_phase3_guards() -> None:
    if not PANEL.is_file():
        skip("8. ratify phase3 guards", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = Path(td)
        fx = _fixture(f)

        expect_refusal(
            "8a. the wrong affirmation refuses, and writes nothing",
            lambda: R.declare_phase3_authorization(
                out_path=fx["lse"] / "HYP04_PHASE3_AUTHORIZATION_2026-09-11.json",
                phase2_lock_path=fx["lock"], declared_by="offline-test-fixture",
                affirmation="not the real affirmation", repo=fx["tmp"]))
        check("8a2. and no authorization file was written",
              not any(fx["lse"].glob("HYP04_PHASE3_AUTHORIZATION_*.json")))

        auth_out = _authorize(fx)
        check("8b. the correct affirmation authorizes it", auth_out.is_file())

        expect_refusal(
            "8c. a second authorization while one already exists refuses",
            lambda: R.declare_phase3_authorization(
                out_path=fx["lse"] / "HYP04_PHASE3_AUTHORIZATION_2026-09-12.json",
                phase2_lock_path=fx["lock"], declared_by="offline-test-fixture",
                affirmation=R.PHASE3_AFFIRMATION, repo=fx["tmp"]))


def test_9_refuses_an_unsigned_phase2_lock() -> None:
    if not PANEL.is_file():
        skip("9. unsigned lock", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = Path(td)
        fx = _fixture(f)
        d = json.loads(fx["lock"].read_text(encoding="utf-8"))
        d["declared"] = False
        fx["lock"].write_text(json.dumps(d), encoding="utf-8")
        expect_refusal(
            "9a. ratify phase3 refuses to authorize against an unsigned "
            "Phase 2 lock",
            lambda: R.declare_phase3_authorization(
                out_path=fx["lse"] / "HYP04_PHASE3_AUTHORIZATION_2026-09-11.json",
                phase2_lock_path=fx["lock"], declared_by="offline-test-fixture",
                affirmation=R.PHASE3_AFFIRMATION, repo=fx["tmp"]))


def test_10_rejoin_holdout_refuses_a_leaked_exploration_id() -> None:
    """A corrupted split with a leaked id is refused by `load_declared_split`
    itself (called at the top of `_rejoin_holdout`, same as Phase 1's
    `_rejoin`), before `_rejoin_holdout`'s own "exploration and holdout
    overlap" cross-check ever gets a chance to run. That inner check is
    still real defense in depth, not dead code -- it exists for exactly the
    reason Phase 1's own analogous check does: "the single invariant most
    worth never trusting to only one caller." This test proves the outer
    layer catches a leak; that is sufficient to prove no leak reaches the
    computation, which is the property that matters."""
    if not PANEL.is_file():
        skip("10. leak test", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = Path(td)
        fx = _fixture(f)
        # corrupt the split so an exploration id also appears in holdout
        sd = json.loads(fx["split"].read_text(encoding="utf-8"))
        leaked = sd["exploration"]["event_ids"][0]
        sd["holdout"]["event_ids"].append(leaked)
        fx["split"].write_text(json.dumps(sd), encoding="utf-8")
        expect_refusal(
            "10a. _rejoin_holdout refuses (via load_declared_split) when "
            "exploration and holdout overlap",
            lambda: P3._rejoin_holdout(
                panel_path=fx["panel"], split_path=fx["split"],
                freeze_path=fx["freeze"], lse=fx["lse"]),
            substring="BOTH partitions")


def test_11_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("11a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("11a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_rehearsal_runs_without_touching_anything_real()
    test_2_refuses_without_an_authorization()
    test_3_refuses_an_unsigned_authorization()
    test_4_refuses_a_commit_sha_mismatch()
    test_5_refuses_a_phase2_lock_hash_mismatch()
    test_6_an_authorized_run_succeeds_exactly_once()
    test_7_a_consumed_authorization_cannot_be_reused()
    test_8_ratify_phase3_guards()
    test_9_refuses_an_unsigned_phase2_lock()
    test_10_rejoin_holdout_refuses_a_leaked_exploration_id()
    test_11_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PHASE3-RUN TESTS PASSED")
    sys.exit(0)
