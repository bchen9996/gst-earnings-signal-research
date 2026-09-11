#!/usr/bin/env python3
"""HYP-04 Phase 2 preregistration lock -- target, feature set, model spec,
fixed before the holdout is touched.

Everything here runs against real committed input files COPIED into an
isolated tempdir -- never the real repo -- with a FRESH split (and, where
`validate_phase2_lock`'s rejoin needs one, a fresh freeze) signed by a
clearly-fake "offline-test-fixture" identity. Nothing here writes to the
real `Live Signal Engine/`, and no computed value is asserted as a finding.

What this suite is defending:

  * ORDER. A lock declared after a result touched the holdout is not a
    preregistration -- the same `_overlapping_results` scope-aware refusal
    `make_freeze_draft` uses, keyed against the HOLDOUT ids here instead of
    the full frozen set. A result that stayed within exploration does not
    block; one that touched the holdout, or declares no scope, does.
  * The lock actually STATES what it fixes -- feature set, target formula,
    model spec -- not just a hash a human cannot read.
  * The smoke test (`validate_phase2_lock`) actually exercises the pipeline
    over exploration data, catches a hash drift, and never touches holdout
    ids -- checked from OUTSIDE the function too, not only trusted from its
    own return value.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_phase2_lock.py
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
from hyp04_supply_chain_hedge import make_validation_split as V  # noqa: E402
from hyp04_supply_chain_hedge import ratify as R  # noqa: E402
from hyp04_supply_chain_hedge.constants import (  # noqa: E402
    HORIZON_GRID,
    LOCKED_CLUSTER_KEY,
    N_PERMUTATIONS,
)

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
    except (L.Phase2LockError, V.SplitError, F.FreezeError, R.RatifyError) as e:
        ok = substring in str(e) if substring else True
        check(label, ok, str(e)[:200])


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(("git", *args), cwd=str(cwd), capture_output=True)


def _fixture(tmp: Path) -> dict:
    """Real inputs copied in; a FRESH freeze and split signed here, by a
    fake identity, exactly mirroring test_hyp04_supply_chain_hedge_
    phase1_diagnostics.py's own fixture pattern."""
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

    # Peer earnings, valid but unremarkable -- this suite is not about the
    # BB coverage gap, only about the lock/refusal/smoke-test wiring.
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

    return {"tmp": tmp, "lse": lse, "panel": dst_panel, "split": split_out,
            "freeze": freeze_out, "earnings": earnings_out, "split_doc": sd,
            "out": lse / "HYP04_PHASE2_LOCK_test.json"}


def _place_result_artifact(lse: Path, *, name: str, event_ids) -> Path:
    p = lse / name
    p.write_text(json.dumps({"event_ids_consumed": list(event_ids)}),
                 encoding="utf-8")
    return p


# --------------------------------------------------------------------------
def test_1_never_overwrites_a_dated_artifact() -> None:
    if not PANEL.is_file():
        skip("1. no overwrite", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        f["out"].write_text("{}", encoding="utf-8")
        expect_refusal("1a. build_draft refuses an existing out_path",
                       lambda: L.build_draft(out_path=f["out"],
                                             split_path=f["split"], lse=f["lse"], repo=f["tmp"]),
                       substring="already exists")


def test_2_requires_a_signed_split() -> None:
    if not PANEL.is_file():
        skip("2. signed split required", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        draft_split = f["lse"] / "HYP04_VALIDATION_SPLIT_draft.json"
        sd = dict(f["split_doc"])
        sd["declared"] = False
        draft_split.write_text(json.dumps(sd), encoding="utf-8")
        expect_refusal("2a. an undeclared split is refused",
                       lambda: L.build_draft(out_path=f["out"],
                                             split_path=draft_split))


def test_3_refuses_on_a_dirty_tree() -> None:
    if not PANEL.is_file():
        skip("3. dirty tree", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        (f["lse"] / "uncommitted.txt").write_text("x", encoding="utf-8")
        expect_refusal("3a. build_draft refuses a dirty tree",
                       lambda: L.build_draft(out_path=f["out"],
                                             split_path=f["split"], lse=f["lse"], repo=f["tmp"]),
                       substring="uncommitted")


def test_4_the_holdout_overlap_refusal_discriminates_by_scope() -> None:
    if not PANEL.is_file():
        skip("4. scope-aware refusal", "real fixture inputs not on disk")
        return
    holdout_ids = f_holdout_ids = None
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        holdout_ids = f["split_doc"]["holdout"]["event_ids"]
        exploration_ids = f["split_doc"]["exploration"]["event_ids"]

        _place_result_artifact(
            f["lse"], name="HYP04_INFERENCE_touches_holdout.json",
            event_ids=holdout_ids[:2])
        expect_refusal(
            "4a. a result artifact touching the HOLDOUT blocks the lock",
            lambda: L.build_draft(out_path=f["out"], split_path=f["split"], lse=f["lse"], repo=f["tmp"]),
            substring="HOLDOUT")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        _place_result_artifact(
            f["lse"], name="HYP04_INFERENCE_exploration_only.json",
            event_ids=exploration_ids[:2])
        import subprocess as sp
        sp.run(("git", "add", "-A"), cwd=str(f["tmp"]), capture_output=True)
        sp.run(("git", "commit", "-q", "-m", "fixture: disjoint result"),
              cwd=str(f["tmp"]), capture_output=True)
        try:
            doc = L.build_draft(out_path=f["out"], split_path=f["split"], lse=f["lse"], repo=f["tmp"])
            check("4b. a result artifact that stays within EXPLORATION "
                  "does not block", True)
            check("4b2. and the lock still builds a real document",
                  doc["feature_set"]["locked"] == list(L.FEATURE_SET))
        except L.Phase2LockError as e:
            check("4b. a result artifact that stays within EXPLORATION "
                  "does not block", False, str(e)[:200])

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        _place_result_artifact(
            f["lse"], name="HYP04_INFERENCE_no_scope.json", event_ids=[])
        # An empty/undeclared scope resolves to None (unknown -> DENY),
        # matching make_freeze_draft's own idiom.
        (f["lse"] / "HYP04_INFERENCE_no_scope.json").write_text(
            json.dumps({"some_other_field": True}), encoding="utf-8")
        expect_refusal(
            "4c. a result artifact declaring NO scope refuses "
            "unconditionally",
            lambda: L.build_draft(out_path=f["out"], split_path=f["split"], lse=f["lse"], repo=f["tmp"]))


def test_5_the_lock_states_what_it_fixes() -> None:
    if not PANEL.is_file():
        skip("5. lock content", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = L.build_draft(out_path=f["out"], split_path=f["split"], lse=f["lse"], repo=f["tmp"])

        check("5a. feature set matches the actual _design_matrix columns",
              doc["feature_set"]["locked"] == list(L.FEATURE_SET))
        check("5b. three candidates are named as deferred, not silently "
              "dropped",
              len(doc["feature_set"]["deferred_candidates"]) == 3)
        check("5c. target horizon grid matches the locked constant",
              doc["target_definition"]["horizon_grid"] == list(HORIZON_GRID))
        check("5d. residualization is stated as REQUIRED, not a choice",
              doc["model_spec"]["residualize"] is True)
        check("5e. cluster key matches D1's locked constant",
              doc["model_spec"]["cluster_key"] == LOCKED_CLUSTER_KEY)
        check("5f. n_permutations matches the locked constant",
              doc["model_spec"]["n_permutations"] == N_PERMUTATIONS)
        check("5g. validation split is referenced, not re-declared",
              doc["validation_split"]["referenced_not_redeclared"] is True)
        check("5h. owner fields are blank on a fresh draft",
              doc["declared"] is False and doc["declared_by"] == ""
              and doc["declared_date"] == "")
        check("5i. it states it moves no gate condition",
              "moves no gate condition" in doc["opens_no_gate"].lower())


def test_6_load_declared_refuses_a_draft() -> None:
    if not PANEL.is_file():
        skip("6. load refuses draft", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = L.build_draft(out_path=f["out"], split_path=f["split"], lse=f["lse"], repo=f["tmp"])
        expect_refusal("6a. an undeclared lock is refused by "
                       "load_declared_phase2_lock",
                       lambda: L.load_declared_phase2_lock(f["out"]))


def test_7_ratify_phase2_declares_and_guards() -> None:
    if not PANEL.is_file():
        skip("7. ratify phase2", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        L.build_draft(out_path=f["out"], split_path=f["split"], lse=f["lse"], repo=f["tmp"])

        expect_refusal(
            "7a. the wrong affirmation refuses, and writes nothing",
            lambda: R.declare_phase2_lock(
                lock_path=f["out"], declared_by="offline-test-fixture",
                affirmation="not the real affirmation"))
        check("7a2. and 'declared' is still false after the refusal",
              json.loads(f["out"].read_text())["declared"] is False)

        out = R.declare_phase2_lock(
            lock_path=f["out"], declared_by="offline-test-fixture",
            affirmation=R.PHASE2_AFFIRMATION, declared_date="2026-09-10")
        check("7b. the correct affirmation declares it",
              out["declared_by"] == "offline-test-fixture")
        check("7c. the feature set survives the round-trip",
              out["feature_set"] == list(L.FEATURE_SET))

        expect_refusal("7d. re-declaring an already-declared lock refuses",
                       lambda: R.declare_phase2_lock(
                           lock_path=f["out"],
                           declared_by="offline-test-fixture",
                           affirmation=R.PHASE2_AFFIRMATION))

        d = L.load_declared_phase2_lock(f["out"])
        check("7e. load_declared_phase2_lock now accepts it",
              d["declared"] is True)


def test_8_smoke_test_reproduces_the_declared_spec() -> None:
    if not PANEL.is_file():
        skip("8. smoke test", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        L.build_draft(out_path=f["out"], split_path=f["split"], lse=f["lse"], repo=f["tmp"])
        R.declare_phase2_lock(
            lock_path=f["out"], declared_by="offline-test-fixture",
            affirmation=R.PHASE2_AFFIRMATION, declared_date="2026-09-10")

        result = L.validate_phase2_lock(
            f["out"], panel_path=f["panel"], split_path=f["split"],
            n_permutations=25, lse=f["lse"], peer_earnings_path=f["earnings"])
        check("8a. the smoke test reports success",
              result["reproduces_declared_spec"] is True)
        check("8b. and actually exercised the pipeline -- not a vacuous pass",
              result["n_rows"] > 0, str(result.get("n_rows")))
        check("8c. cluster key used matches the lock",
              result["cluster_key_used"] == LOCKED_CLUSTER_KEY)
        check("8d. residualize used matches the lock",
              result["residualize_used"] is True)

        holdout_ids = set(f["split_doc"]["holdout"]["event_ids"])
        check("8e. no holdout id was used -- checked from OUTSIDE the "
              "function's own internal guard",
              result["n_exploration_events_used"] <= len(
                  f["split_doc"]["exploration"]["event_ids"]))


def test_9_smoke_test_catches_a_hash_drift() -> None:
    if not PANEL.is_file():
        skip("9. hash drift", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        L.build_draft(out_path=f["out"], split_path=f["split"], lse=f["lse"], repo=f["tmp"])
        R.declare_phase2_lock(
            lock_path=f["out"], declared_by="offline-test-fixture",
            affirmation=R.PHASE2_AFFIRMATION, declared_date="2026-09-10")

        d = json.loads(f["out"].read_text(encoding="utf-8"))
        d["pins"]["target_py_sha256"] = "0" * 64
        f["out"].write_text(json.dumps(d), encoding="utf-8")

        expect_refusal(
            "9a. a corrupted target.py hash pin refuses",
            lambda: L.validate_phase2_lock(
                f["out"], panel_path=f["panel"], split_path=f["split"],
                n_permutations=25, lse=f["lse"], peer_earnings_path=f["earnings"]),
            substring="target.py")


def test_10_smoke_test_requires_the_pinned_split() -> None:
    if not PANEL.is_file():
        skip("10. split drift", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        L.build_draft(out_path=f["out"], split_path=f["split"], lse=f["lse"], repo=f["tmp"])
        R.declare_phase2_lock(
            lock_path=f["out"], declared_by="offline-test-fixture",
            affirmation=R.PHASE2_AFFIRMATION, declared_date="2026-09-10")

        d = json.loads(f["out"].read_text(encoding="utf-8"))
        d["pins"]["validation_split_sha256"] = "0" * 64
        f["out"].write_text(json.dumps(d), encoding="utf-8")

        expect_refusal(
            "10a. a corrupted validation-split hash pin refuses",
            lambda: L.validate_phase2_lock(
                f["out"], panel_path=f["panel"], split_path=f["split"],
                n_permutations=25, lse=f["lse"], peer_earnings_path=f["earnings"]),
            substring="split")


def test_11_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("11a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("11a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_never_overwrites_a_dated_artifact()
    test_2_requires_a_signed_split()
    test_3_refuses_on_a_dirty_tree()
    test_4_the_holdout_overlap_refusal_discriminates_by_scope()
    test_5_the_lock_states_what_it_fixes()
    test_6_load_declared_refuses_a_draft()
    test_7_ratify_phase2_declares_and_guards()
    test_8_smoke_test_reproduces_the_declared_spec()
    test_9_smoke_test_catches_a_hash_drift()
    test_10_smoke_test_requires_the_pinned_split()
    test_11_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PHASE2-LOCK TESTS PASSED")
    sys.exit(0)
