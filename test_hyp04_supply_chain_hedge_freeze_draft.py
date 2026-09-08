#!/usr/bin/env python3
"""HYP-04 freeze machinery -- it derives what it can and refuses the rest.

Two things this suite exists to pin:

  1. Against the REAL repository, the machinery refuses, because the curated
     map is not ratified. That refusal is the feature.
  2. On a fixture where everything is ratified, a completed freeze takes the
     display gate from four denials to ONE (C1). That is the consequence the
     module claims in its own docstring, asserted rather than asserted-in-prose.

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


def expect_refusal(label: str, fn) -> None:
    try:
        fn()
    except F.FreezeError as e:
        check(label, True)
        print(f"        -> {str(e)[:120]}")
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
def test_1_the_real_repository_refuses() -> None:
    """The curated map is not ratified, so nothing can be frozen from it."""
    with tempfile.TemporaryDirectory() as td:
        expect_refusal(
            "1a. against the real repo, an unratified map refuses",
            lambda: F.build_draft(panel_path=PANEL,
                                  out_path=Path(td) / "x.json"))
    check("1b. the ratified status it demands is 'reviewed'",
          F.RATIFIED_REVIEW_STATUS == "reviewed")


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
                       lambda: F.validate_freeze(f["out"]))

        d["frozen"] = True
        f["out"].write_text(json.dumps(d), encoding="utf-8")
        expect_refusal("4b. frozen=true alone is still refused -- the "
                       "attestation is separate",
                       lambda: F.validate_freeze(f["out"]))

        d["frozen_before_any_result_computed"] = True
        f["out"].write_text(json.dumps(d), encoding="utf-8")
        expect_refusal("4c. an unattributed attestation is refused",
                       lambda: F.validate_freeze(f["out"]))


def test_5_a_completed_freeze_leaves_exactly_c1() -> None:
    """The module's headline claim, asserted."""
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
        check("5f. exactly one denial survives", len(g.denials) == 1,
              str(g.denials))
        check("5g. and it is C1", c["C1_status"] is False
              and g.denials and g.denials[0].startswith("C1"))
        check("5h. the gate is still CLOSED -- one denial is enough",
              g.open is False)


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
                                                 panel_path=f["panel"]))

        d["eligible_event_ids"] = d["eligible_event_ids"] + [
            d["eligible_event_ids"][0]]
        f["out"].write_text(json.dumps(d), encoding="utf-8")
        expect_refusal("6b. a duplicated id is refused",
                       lambda: F.validate_freeze(f["out"]))


def test_7_every_other_precondition_refuses() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))

        f["out"].write_text("{}", encoding="utf-8")
        expect_refusal("7a. an existing freeze is never overwritten",
                       lambda: _build(f))
        f["out"].unlink()

        expect_refusal("7b. a missing panel refuses",
                       lambda: F.build_draft(
                           panel_path=f["lse"] / "nope.json",
                           out_path=f["out"], lse=f["lse"], repo=f["tmp"],
                           lock_path=f["lock"], today=date(2026, 9, 9)))

        (f["lse"] / "HYP04_STAGE2_results.json").write_text("{}", encoding="utf-8")
        expect_refusal("7c. an existing result artifact refuses -- the freeze "
                       "comes first", lambda: _build(f))
        (f["lse"] / "HYP04_STAGE2_results.json").unlink()

        (f["tmp"] / "dirty.txt").write_text("x", encoding="utf-8")
        expect_refusal("7d. a dirty working tree refuses", lambda: _build(f))
        (f["tmp"] / "dirty.txt").unlink()

        expect_refusal("7e. a lock signed ON the freeze date refuses -- equal "
                       "is not before",
                       lambda: _build(f, ) if False else F.build_draft(
                           panel_path=f["panel"], out_path=f["out"],
                           lse=f["lse"], repo=f["tmp"], lock_path=f["lock"],
                           today=date(2026, 8, 20)))

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
        expect_refusal("7f. an unsigned lock refuses", lambda: _build(f))

        f["lock"].unlink()
        _commit()
        expect_refusal("7g. a missing lock refuses", lambda: _build(f))


def test_8_the_real_gate_is_untouched() -> None:
    """This suite must not have moved anything."""
    g = evaluate_gate()
    check("8a. the real gate is still CLOSED", g.open is False)
    check("8b. still four denials", len(g.denials) == 4, str(len(g.denials)))
    check("8c. eligible count still unset",
          g.evidence.get("eligible_count") is None)
    check("8d. no freeze artifact was written into the repo",
          not list(LSE.glob("HYP04_FREEZE_DRAFT_*.json")),
          str([p.name for p in LSE.glob("HYP04_FREEZE_DRAFT_*.json")]))


if __name__ == "__main__":
    test_1_the_real_repository_refuses()
    test_2_the_fixture_produces_a_complete_draft()
    test_3_the_owner_fields_are_left_blank()
    test_4_an_unattested_draft_is_not_a_freeze()
    test_5_a_completed_freeze_leaves_exactly_c1()
    test_6_a_tampered_derived_field_is_refused()
    test_7_every_other_precondition_refuses()
    test_8_the_real_gate_is_untouched()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 FREEZE-MACHINERY TESTS PASSED")
    sys.exit(0)
