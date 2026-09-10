#!/usr/bin/env python3
"""HYP-04 freeze machinery -- it derives what it can and refuses the rest.

Two things this suite exists to pin:

  1. The ratification guard is SATISFIED, not disabled. v1.3 ratified every
     edge on 2026-09-08, so the guard no longer fires against the real map --
     and a test that merely flipped to "it does not refuse" would pass just as
     well if the guard had been deleted. It is checked both ways: against
     v1.2's unratified edges it must still refuse.
  2. On a fixture where everything is ratified, a completed freeze takes the
     display gate from four denials to NONE. The module's docstring claims
     "four to one, the survivor being C1" -- true until registry v1.12 moved
     C1 on 2026-09-09, which it would only do once a valid freeze existed.
     The order it insisted on is what turned one into none.
  3. The draft in the repository is ATTESTED as of 2026-09-09 and validates.
     It shipped inert, as test_3 still pins on a fresh fixture; what changed
     is that a human signed it, which is the one thing this module refuses to
     do and the reason the record names a person.

Repo testing convention (hand-rolled check(), run directly, no pytest).
Offline: no network, and it never writes into the real Live Signal Engine.

Run directly: python test_hyp04_supply_chain_hedge_freeze_draft.py
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

import csv  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import make_freeze_draft as F  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import evaluate_gate  # noqa: E402

ROOT = Path(__file__).resolve().parent
LSE = ROOT / "Live Signal Engine"
PANEL = LSE / "HYP04_EVENT_PANEL_2026-09-08.json"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def expect_refusal(label: str, fn, expect: str) -> None:
    """Refuse, AND refuse for the stated reason. `expect` is REQUIRED.

    This used to assert only that something was raised, then print the message
    without checking it. That is how a guard firing for the wrong reason passes
    as the guard the test names -- and it has hidden three separate bugs in
    this project, most recently when a real v1.3 on disk made every refusal
    test in the ratify suite trip the already-exists guard first.

    A refusal is only evidence about the guard it came from, so the reason is
    part of the assertion now. Keep `expect` a short distinctive fragment of
    the message, not the whole sentence: pinning full prose makes the test
    fail on rewording, which teaches people to loosen it.
    """
    if not expect.strip():
        check(label, False,
              "expect= is empty, which matches ANY message and makes this "
              "assertion vacuous. Give it a real fragment.")
        return
    try:
        fn()
    except F.FreezeError as e:
        got = str(e)
        if expect.lower() in got.lower():
            check(label, True)
        else:
            check(label, False,
                  f"refused for the WRONG reason -- wanted {expect!r}, "
                  f"got: {got[:140]}")
        return
    except Exception as e:  # noqa: BLE001
        check(label, False, f"wrong type {type(e).__name__}: {e}")
        return
    check(label, False, "did not refuse")


# --------------------------------------------------------------------------
# the fixture: everything ratified, in a temp dir, with its own git repo
# --------------------------------------------------------------------------
def _fixture(tmp: Path) -> dict:
    lse = tmp / "Live Signal Engine"
    lse.mkdir(parents=True)

    panel = json.loads(PANEL.read_text(encoding="utf-8"))
    src_map = LSE / panel["sources"]["curated_map"]

    # Same map, every row ratified.
    rows = list(csv.DictReader(src_map.open(newline="", encoding="utf-8")))
    for r in rows:
        r["review_status"] = "reviewed"
    dst_map = lse / src_map.name
    with dst_map.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    import hashlib
    panel["sources"]["curated_map_sha256"] = hashlib.sha256(
        dst_map.read_bytes()).hexdigest()
    dst_panel = lse / PANEL.name
    dst_panel.write_text(json.dumps(panel, indent=1), encoding="utf-8")

    lock = lse / "GST_HYP04_ANALYSIS_LOCK_v1.0.md"
    lock.write_text("# lock\n\n> **SIGNED 2026-08-20. IN FORCE.**\n",
                    encoding="utf-8")

    # A real, clean git repo, so _commit_sha is exercised rather than faked.
    for cmd in (("init", "-q"), ("config", "user.email", "t@t"),
                ("config", "user.name", "t")):
        subprocess.run(("git", *cmd), cwd=str(tmp), capture_output=True)
    (tmp / "README").write_text("fixture\n", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=str(tmp), capture_output=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=str(tmp),
                   capture_output=True)

    return {"tmp": tmp, "lse": lse, "panel": dst_panel, "map": dst_map,
            "lock": lock, "out": lse / "HYP04_FREEZE_DRAFT_2026-09-09.json"}


def _build(f: dict, **kw):
    return F.build_draft(panel_path=f["panel"], out_path=f["out"],
                         lse=f["lse"], repo=f["tmp"], lock_path=f["lock"],
                         today=date(2026, 9, 9), **kw)


# --------------------------------------------------------------------------
def test_1_the_ratification_guard_is_satisfied_not_disabled() -> None:
    """The map is ratified now, so this guard no longer fires. Prove it still can.

    This used to assert build_draft refused against the real repo. It did,
    because every edge read `draft`. All seven are now `reviewed`, so the
    refusal is gone -- and an assertion that simply flipped to "it does not
    refuse" would pass just as happily if the guard had been deleted.

    So: point `_require_ratified` at edges that are NOT ratified and require
    it to fire, then at the live ones and require it not to.
    """
    from hyp04_supply_chain_hedge.curated_linkage import load_curated_linkage

    v12 = load_curated_linkage(LSE / "HYP04_Linkage_Map_v1.2.csv")
    expect_refusal("1a. unratified edges still refuse",
                   lambda: F._require_ratified(list(v12.edges)),
                   expect="not 'reviewed'")

    v13 = load_curated_linkage(LSE / "HYP04_Linkage_Map_v1.3.csv")
    F._require_ratified(list(v13.edges))          # must not raise
    check("1b. and the ratified ones do not", True)
    check("1c. the ratified status it demands is 'reviewed'",
          F.RATIFIED_REVIEW_STATUS == "reviewed")
    check("1d. v1.2 really was unratified -- the guard had something to catch",
          any(e.review_status != "reviewed" for e in v12.edges))


def test_2_the_fixture_produces_a_complete_draft() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        d = _build(f)
        check("2a. the eligible set is enumerated, not just counted",
              len(d["eligible_event_ids"]) == d["eligible_event_count"] > 0)
        check("2b. it clears the registered floor",
              d["eligible_event_count"] >= d["registered_floor"])
        check("2c. placeholder linkage is derived false",
              d["uses_placeholder_linkage"] is False)
        check("2d. a real commit sha was read from a clean tree",
              len(d["analysis_commit_sha"]) == 40)
        check("2e. the analysis lock is cited and predates the freeze",
              d["analysis_lock_signed"] < d["freeze_date"])
        check("2f. every contributing edge is ratified",
              all(e["review_status"] == "reviewed"
                  for e in d["contributing_edges"]))


def test_3_the_owner_fields_are_left_blank() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = _build(_fixture(Path(td)))
        check("3a. frozen is false -- a draft is not a freeze",
              d["frozen"] is False)
        check("3b. the attestation is null, not defaulted to true",
              d["frozen_before_any_result_computed"] is None)
        check("3c. the attributions are blank",
              d["attested_by"] == "" and d["attested_date"] == "")
        check("3d. the draft says which fields are the owner's",
              set(d["owner_fields"]) == set(F.OWNER_FIELDS))
        check("3e. and admits the result scan is not proof",
              "not proof" in json.dumps(d["result_scan"]).lower()
              or "cannot establish" in json.dumps(d["result_scan"]).lower())


def test_4_an_unattested_draft_is_not_a_freeze() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        d = _build(f)
        f["out"].write_text(json.dumps(d), encoding="utf-8")
        expect_refusal("4a. an untouched draft is refused",
                       lambda: F.validate_freeze(f["out"]),
                       expect="'frozen' is not true")

        d["frozen"] = True
        f["out"].write_text(json.dumps(d), encoding="utf-8")
        expect_refusal("4b. frozen=true alone is still refused -- the "
                       "attestation is separate",
                       lambda: F.validate_freeze(f["out"]),
                       expect="is not attested")

        d["frozen_before_any_result_computed"] = True
        f["out"].write_text(json.dumps(d), encoding="utf-8")
        expect_refusal("4c. an unattributed attestation is refused",
                       lambda: F.validate_freeze(f["out"]),
                       expect="is blank")


def test_5_a_completed_freeze_now_leaves_nothing() -> None:
    """The module's headline claim, asserted -- and it has grown.

    "Four denials to one" while C1 had not moved; "four to none" since
    registry v1.12 moved it on 2026-09-09, which it would only do once a valid
    freeze existed.
    """
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        d = _build(f)
        d.update(frozen=True, frozen_before_any_result_computed=True,
                 attested_by="fixture-operator", attested_date="2026-09-09")
        f["out"].write_text(json.dumps(d), encoding="utf-8")

        rec = F.validate_freeze(f["out"], panel_path=f["panel"])
        check("5a. the completed draft validates", rec.frozen is True)

        g = evaluate_gate(eligible_event_count=d["eligible_event_count"],
                          freeze=rec)
        c = g.conditions
        check("5b. C2 clears", c["C2_threshold"] is True)
        check("5c. C3 clears", c["C3_frozen"] is True)
        check("5d. C4 was already met", c["C4_decisions_resolved"] is True)
        check("5e. C5 clears", c["C5_not_placeholder"] is True)
        # This asserted that ONE denial survived and that it was C1 -- true
        # while HYP-04's registry status was PREREGISTERED_MEASUREMENT_NOT_
        # IMPLEMENTED, i.e. right up until registry v1.12 moved it on
        # 2026-09-09. C1 was the survivor by design: the freeze had to come
        # FIRST, and v1.12 refuses to move C1 until one exists.
        #
        # Now that it has, a completed freeze leaves NO denial. The module's
        # headline claim has gone from "four denials to one" to "four to none",
        # and the order it insisted on is what earned that.
        check("5f. no denial survives -- C1 moved once the freeze existed",
              len(g.denials) == 0, str(g.denials))
        check("5g. C1 passes from the REGISTRY, not from this freeze",
              c["C1_status"] is True
              and g.evidence["registry_status"] == "ACTIVE_COLLECTING")
        check("5h. so a completed freeze now opens the gate outright",
              g.open is True)


def test_6_a_tampered_derived_field_is_refused() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        d = _build(f)
        d.update(frozen=True, frozen_before_any_result_computed=True,
                 attested_by="x", attested_date="2026-09-09")
        d["eligible_event_ids"] = d["eligible_event_ids"][:-1]
        f["out"].write_text(json.dumps(d), encoding="utf-8")
        expect_refusal("6a. an edited event-id set is refused against the panel",
                       lambda: F.validate_freeze(f["out"],
                                                 panel_path=f["panel"]),
                       expect="does not match the panel")

        d["eligible_event_ids"] = d["eligible_event_ids"] + [
            d["eligible_event_ids"][0]]
        f["out"].write_text(json.dumps(d), encoding="utf-8")
        expect_refusal("6b. a duplicated id is refused",
                       lambda: F.validate_freeze(f["out"]),
                       expect="contains duplicates")


def test_7_every_other_precondition_refuses() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))

        f["out"].write_text("{}", encoding="utf-8")
        expect_refusal("7a. an existing freeze is never overwritten",
                       lambda: _build(f), expect="already exists")
        f["out"].unlink()

        expect_refusal("7b. a missing panel refuses",
                       lambda: F.build_draft(
                           panel_path=f["lse"] / "nope.json",
                           out_path=f["out"], lse=f["lse"], repo=f["tmp"],
                           lock_path=f["lock"], today=date(2026, 9, 9)),
                       expect="no event panel")

        (f["lse"] / "HYP04_STAGE2_results.json").write_text("{}", encoding="utf-8")
        expect_refusal("7c. an existing result artifact refuses -- the freeze "
                       "comes first", lambda: _build(f),
                       expect="result artifacts already exist")
        (f["lse"] / "HYP04_STAGE2_results.json").unlink()

        (f["tmp"] / "dirty.txt").write_text("x", encoding="utf-8")
        expect_refusal("7d. a dirty working tree refuses", lambda: _build(f),
                       expect="uncommitted change")
        (f["tmp"] / "dirty.txt").unlink()

        expect_refusal("7e. a lock signed ON the freeze date refuses -- equal "
                       "is not before",
                       # `today` == the lock's SIGNED date, so the dates are
                       # equal and equal is not before.
                       lambda: F.build_draft(
                           panel_path=f["panel"], out_path=f["out"],
                           lse=f["lse"], repo=f["tmp"], lock_path=f["lock"],
                           today=date(2026, 8, 20)),
                       expect="is not before")

        # Commit after each lock mutation, or the dirty-tree guard fires first
        # and these two are never actually exercised. It did, on this suite's
        # first run: both "passed" against the wrong refusal.
        def _commit():
            subprocess.run(("git", "add", "-A"), cwd=str(f["tmp"]),
                           capture_output=True)
            subprocess.run(("git", "commit", "-q", "-m", "mutate"),
                           cwd=str(f["tmp"]), capture_output=True)

        f["lock"].write_text("# no marker\n", encoding="utf-8")
        _commit()
        expect_refusal("7f. an unsigned lock refuses", lambda: _build(f),
                       expect="carries no 'SIGNED")

        f["lock"].unlink()
        _commit()
        expect_refusal("7g. a missing lock refuses", lambda: _build(f),
                       expect="no analysis lock at")


def test_9_the_computation_surface_is_evidence_not_a_verdict() -> None:
    """What the attestation is made AGAINST -- and what it still cannot do."""
    s = F.computation_surface()

    check("9a. it refuses to be read as proof",
          "NOT proof" in s["what_this_is_not"])
    check("9b. and names the hole it cannot see into -- work off-repo",
          "outside this repository" in s["what_this_is_not"])
    check("9c. it concedes the estimator exists",
          s["estimator_modules_exist"] is True)
    check("9d. the structural question is whether a path INTO it exists",
          isinstance(s["panel_to_estimator_paths"], list))
    check("9e. every notebook is accounted for, with its execution state",
          all({"code_cells", "cells_with_saved_outputs",
               "references_real_inputs"} <= set(nb)
              for nb in s["notebooks"] if "unreadable" not in nb))
    check("9f. history is searched, not just the working tree",
          isinstance(s["result_artifacts_in_git_history"], list))
    check("9g. and it bounds the window a signer must think back over",
          bool(s["all_real_inputs_coexist_from"]),
          str(s["real_inputs_first_committed"]))


def test_10_the_detector_catches_wiring_and_ignores_mentions() -> None:
    """A scanner that flags itself is a field the reader learns to skip.

    `make_freeze_draft` names all five estimator functions as string literals,
    so a mention-match reported this module as a panel-to-estimator path. It
    was a false positive on its first run and it is pinned here.
    """
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "wired.py").write_text(
            'p = "HYP04_EVENT_PANEL_x.json"\n'
            "r = local_projection_analysis(p)\n", encoding="utf-8")
        (t / "mention_only.py").write_text(
            'NAMES = ("local_projection_analysis",)\n'
            'P = "HYP04_EVENT_PANEL"\n', encoding="utf-8")
        (t / "imports_but_never_calls.py").write_text(
            "from x import local_projection_analysis\n"
            'P = "HYP04_EVENT_PANEL"\n', encoding="utf-8")
        (t / "wired_via_module.py").write_text(
            'P = "HYP04_EVENT_PANEL_x.json"\n'
            "r = inference.local_projection_analysis(P)\n", encoding="utf-8")
        (t / "broken.py").write_text(
            'P = "HYP04_EVENT_PANEL"\ndef (\n', encoding="utf-8")
        found = F._estimator_paths(t)
        check("10a. a real wiring is caught", "wired.py" in found, str(found))
        check("10a2. including one called through its module",
              "wired_via_module.py" in found, str(found))
        check("10a3. and a file that will not parse is REPORTED, not skipped",
              any(f.startswith("broken.py") for f in found), str(found))
        check("10b. a bare mention is not", "mention_only.py" not in found)
        check("10c. nor is an import that never calls",
              "imports_but_never_calls.py" not in found)

    check("10d. and the real repository has no such path today",
          F._estimator_paths(ROOT) == [], str(F._estimator_paths(ROOT)))


def test_11_a_computed_outcome_blocks_the_freeze() -> None:
    """The two refusals fire on evidence an outcome WAS computed."""
    nb = {"cells": [{"cell_type": "code",
                     "source": ['df = load("HYP04_EVENT_PANEL_2026-09-08.json")'],
                     "execution_count": 1,
                     "outputs": [{"output_type": "stream", "text": ["0.31"]}]}]}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "ran.ipynb").write_text(json.dumps(nb), encoding="utf-8")
        surf = F._notebook_surface(t)[0]
        check("11a. an executed notebook over real inputs is detected",
              surf["cells_with_saved_outputs"] == 1
              and surf["references_real_inputs"] == ["HYP04_EVENT_PANEL"],
              str(surf))

    live = F._notebook_surface(ROOT)
    ran = [n for n in live if n.get("cells_with_saved_outputs")
           and n.get("references_real_inputs")]
    check("11b. no notebook in this repo has been run over real inputs",
          not ran, str(ran))
    check("11c. the Colab notebook is unexecuted and synthetic-only",
          any(n["path"].endswith("HYP04_Phase0_Colab.ipynb")
              and n["cells_with_saved_outputs"] == 0
              and n["cells_with_execution_count"] == 0
              and n["references_real_inputs"] == [] for n in live),
          str(live))


def test_12_the_result_refusal_discriminates_by_scope() -> None:
    """A prior result blocks a freeze over THOSE events, not over any events.

    Why this changed. The refusal was "a result artifact exists, anywhere,
    ever" -- right about the case it was written for, wrong about one it was
    not. Phase 1 computes a diagnostic over an EXPLORATION set; Phase 3 later
    freezes the DISJOINT holdout. Under a blanket refusal that second freeze is
    impossible, so a correctly-ordered project would be pushed either to skip
    the freeze or to name the artifact so the scan misses it. A control people
    route around is worse than one that discriminates.

    The loosening is bounded by making unknown scope refuse: an artifact that
    will not say what it ranged over cannot be shown to be disjoint.
    """
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        ids = list(json.loads(f["panel"].read_text(encoding="utf-8"))
                   ["eligible_event_ids"])
        art = f["lse"] / "HYP04_INFERENCE_PHASE1_2026-09-09.json"

        # 1. Declares no scope -> refuses. Unknown resolves to DENY.
        art.write_text(json.dumps({"note": "no scope"}), encoding="utf-8")
        expect_refusal("12a. a result declaring no scope refuses",
                       lambda: _build(f),
                       expect=f"declares no {F.RESULT_SCOPE_FIELD}")

        # 2. Overlaps by ONE event -> refuses.
        art.write_text(json.dumps({F.RESULT_SCOPE_FIELD: [ids[0]]}),
                       encoding="utf-8")
        expect_refusal("12b. an overlap of a single event refuses",
                       lambda: _build(f), expect="1 event(s) in common")

        # 3. Disjoint -> the freeze proceeds. This is the case the old refusal
        #    made impossible, and it is the whole point of the change.
        art.write_text(json.dumps(
            {F.RESULT_SCOPE_FIELD: ["ZZZ-1999-01-04", "ZZZ-1999-04-05"]}),
            encoding="utf-8")
        # The artifact lives inside the fixture repo, so writing it dirtied the
        # tree. 12a and 12b refused before reaching the clean-tree check; the
        # success case does not, and a freeze legitimately requires a sha that
        # describes the tree.
        subprocess.run(("git", "add", "-A"), cwd=str(f["tmp"]),
                       capture_output=True)
        subprocess.run(("git", "commit", "-q", "-m", "disjoint prior result"),
                       cwd=str(f["tmp"]), capture_output=True)
        draft = _build(f)
        check("12c. a DISJOINT prior result does not block the freeze",
              draft["eligible_event_count"] == len(ids),
              str(draft.get("eligible_event_count")))
        check("12d. and the draft records that it checked, rather than "
              "silently allowing it",
              draft["computation_surface"]["result_artifact_scopes"]
              [art.name]["declares_scope"] is True)
        check("12e. with the count it was disjoint on",
              draft["computation_surface"]["result_artifact_scopes"]
              [art.name]["n_events_declared"] == 2)
        # No unlink: build_draft COMPUTES the draft and returns it; main()
        # does the writing. Nothing was written here.
        check("12e2. and building wrote nothing -- build_draft is pure",
              not f["out"].exists())

        # 4. The scope reader itself, directly -- so 12a-c cannot pass because
        #    _declared_scope returns None for everything.
        check("12f. CONTROL -- the scope reader reads a real declaration",
              F._declared_scope(art.name, lse=f["lse"])
              == frozenset({"ZZZ-1999-01-04", "ZZZ-1999-04-05"}))
        check("12g. and returns None for an artifact that is not there, which "
              "is the refusing answer",
              F._declared_scope("HYP04_BETA_nothing.json", lse=f["lse"]) is None)


def test_13_the_committed_freeze_still_validates() -> None:
    """This edit touched machinery underneath an ATTESTED freeze.

    `validate_freeze` never rescans the computation surface, so changing the
    scan cannot retroactively invalidate what the owner signed. Asserted here
    rather than reasoned about, because the cost of being wrong is the gate.
    """
    draft = sorted(LSE.glob("HYP04_FREEZE_DRAFT_*.json"))[-1]
    rec = F.validate_freeze(draft, panel_path=PANEL)
    check("13a. the committed freeze still validates unchanged",
          rec.frozen is True and len(rec.eligible_event_ids) == 214,
          f"{len(rec.eligible_event_ids)} ids")
    check("13b. attested by a human, and still says so",
          json.loads(draft.read_text(encoding="utf-8"))["attested_by"].strip()
          != "")
    from hyp04_supply_chain_hedge.display_gate import current_decision
    live = current_decision()
    check("13c. and the live gate is still OPEN with zero denials",
          live.open is True and len(live.denials) == 0, str(live.denials))


def test_8_this_suite_moved_nothing() -> None:
    """The suite must not move the gate. The OWNER did, on 2026-09-09.

    This asserted the real gate was CLOSED with four denials and that every
    freeze artifact on disk was an inert draft. Both were true until the owner
    attested `HYP04_FREEZE_DRAFT_2026-09-08.json` on 2026-09-09, which is the
    act this whole module exists to make possible and refuses to perform.

    So the assertions invert, and the thing worth pinning is that the
    attestation is a HUMAN's: the record names one, and no code path here can
    produce that.
    """
    # Withholding the freeze still denies -- three denials, not four, because
    # C1 now passes from registry v1.12.
    g = evaluate_gate()
    check("8a. with the freeze withheld the gate still denies", g.open is False)
    check("8b. on C2, C3 and C5", len(g.denials) == 3
          and not any(x.startswith("C1") for x in g.denials), str(g.denials))
    # `eligible_event_count`, not `eligible_count`: the latter is not a key the
    # gate emits, so `.get(...) is None` passed no matter what it reported.
    check("8c. and a freeze-less gate sees no count",
          g.evidence["eligible_event_count"] is None)

    drafts = sorted(LSE.glob("HYP04_FREEZE_DRAFT_*.json"))
    check("8d. a freeze artifact exists", bool(drafts), "none on disk")
    for d in drafts:
        rec = json.loads(d.read_text(encoding="utf-8"))
        check(f"8e. {d.name}: attested, and it validates",
              rec.get("frozen") is True
              and F.validate_freeze(d).frozen is True)
        check(f"8f. {d.name}: the attestation is TRUE, never defaulted",
              rec.get("frozen_before_any_result_computed") is True)
        check(f"8g. {d.name}: attributed to a named human on a date",
              bool(str(rec.get("attested_by") or "").strip())
              and bool(str(rec.get("attested_date") or "").strip()),
              f"{rec.get('attested_by')!r} / {rec.get('attested_date')!r}")
        check(f"8h. {d.name}: and the derived fields still match the panel",
              len(F.validate_freeze(
                  d, panel_path=sorted(
                      LSE.glob("HYP04_EVENT_PANEL_*.json"))[-1]
              ).eligible_event_ids) == rec["eligible_event_count"])

    # The claim that survives all of it: this MODULE never writes those fields.
    # A draft it produces is inert, which test_3 pins on a fresh fixture.
    check("8i. and the module still ships every owner field blank",
          set(F.OWNER_FIELDS) == {"frozen", "frozen_before_any_result_computed",
                                  "attested_by", "attested_date"})


if __name__ == "__main__":
    test_1_the_ratification_guard_is_satisfied_not_disabled()
    test_2_the_fixture_produces_a_complete_draft()
    test_3_the_owner_fields_are_left_blank()
    test_4_an_unattested_draft_is_not_a_freeze()
    test_5_a_completed_freeze_now_leaves_nothing()
    test_6_a_tampered_derived_field_is_refused()
    test_7_every_other_precondition_refuses()
    test_9_the_computation_surface_is_evidence_not_a_verdict()
    test_10_the_detector_catches_wiring_and_ignores_mentions()
    test_11_a_computed_outcome_blocks_the_freeze()
    test_12_the_result_refusal_discriminates_by_scope()
    test_13_the_committed_freeze_still_validates()
    test_8_this_suite_moved_nothing()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 FREEZE-MACHINERY TESTS PASSED")
    sys.exit(0)
