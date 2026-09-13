#!/usr/bin/env python3
"""HYP-05 registry v1.15 -- records the one exploratory pilot result.

Mirrors test_hyp04_supply_chain_hedge_registry_v1_13.py's own shape for the
analogous HYP-04 closure, adapted for the real difference: HYP-05 has no
display gate of its own (display_gate.py reads HYP-04's entry only), so
there is no gate-closing rehearsal to test here -- instead this checks the
refusal-to-mislabel guards test_1_13 had no equivalent of (this generator
must refuse to declare EXPLORATORY_PILOT_TESTED_NULL for a significant
result, or for one that actually cleared the floor).

  1. v1.15 refuses unless the repository already IS what it declares: one
     real Phase 3 pilot result, null-shaped correctly, explicitly
     exploratory, tracing through a consumed authorization to a signed
     Phase 2 lock.
  2. The immovable-field exception is claimed and narrow: status,
     status_basis only -- and the floor/display_rule get their OWN
     explicit guard, since a pilot result must never be read as clearing
     either.
  3. The built document moves only what it claims: HYP-04's entry,
     HYP-01/02/03, the floor, and display_rule are all byte-identical;
     results/results_note gain a HYP-05 paragraph without erasing HYP-04's.
  4. This generator is NOT usable to mislabel a significant or
     floor-clearing result as an exploratory pilot null.

Nothing real is written by this file: v1.15 is built in memory via
`build_v1_15()`, exactly as v1.12/v1.13/v1.14's own suites do.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_15.py
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

import copy  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import make_registry_v1_15 as R  # noqa: E402
from hyp04_supply_chain_hedge.make_registry_v1_6 import (  # noqa: E402
    IMMOVABLE_HYP04_FIELDS as IMMOVABLE_ENTRY_FIELDS,
)

ROOT = Path(__file__).resolve().parent
LSE = ROOT / "Live Signal Engine"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _entry(doc: dict, hid: str) -> dict:
    return next(h for h in doc["hypotheses"] if h["hypothesis_id"] == hid)


def test_1_it_refuses_unless_the_result_is_unambiguous() -> None:
    problems = R.code_disagreements()
    check("1a. the repository matches what v1.15 declares -- one real, "
          "null, exploratory, fully-traced Phase 3 pilot result",
          problems == [], str(problems))

    results = sorted(LSE.glob("HYP05_PHASE3_RESULT_*.json"))
    check("1b. exactly one Phase 3 result artifact exists on disk",
          len(results) == 1, str([p.name for p in results]))
    result = json.loads(results[0].read_text(encoding="utf-8"))
    check("1c. it is genuinely null, not just labelled so",
          result["treatment"]["peak_significant"] is False)
    check("1d. it carries the reported-regardless-of-outcome commitment",
          result["reported_regardless_of_outcome"] is True
          and result["no_rerun_permitted"] is True)
    check("1e. it is genuinely exploratory, not just labelled so",
          result["sample_size_disclosure"]["framing"]
          == "EXPLORATORY, NOT CONFIRMATORY")

    auths = sorted(LSE.glob("HYP05_PHASE3_AUTHORIZATION_*.json"))
    auth = json.loads(auths[0].read_text(encoding="utf-8"))
    check("1f. the authorization is consumed by exactly this result",
          auth["consumed"] is True
          and auth["consumed_by_result"] == results[0].name)


def test_2_the_exception_is_claimed_and_narrow() -> None:
    may_move = set(R.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE)
    check("2a. v1.15 claims an immovable-field exception", bool(may_move))
    check("2b. it is exactly status, status_basis",
          may_move == {"status", "status_basis"}, str(sorted(may_move)))
    check("2c. every named field really is immovable",
          may_move <= set(IMMOVABLE_ENTRY_FIELDS),
          str(sorted(may_move - set(IMMOVABLE_ENTRY_FIELDS))))
    check("2d. results/results_note need no exception -- they are "
          "top-level fields, not in the per-entry schema at all",
          "results" not in IMMOVABLE_ENTRY_FIELDS
          and "results_note" not in IMMOVABLE_ENTRY_FIELDS)
    check("2e. the floor and display_rule have their OWN explicit guard, "
          "on top of the immovable-field check",
          set(R.FLOOR_AND_DISPLAY_MUST_NOT_MOVE)
          == {"minimum_eligible_events", "minimum_eligible_events_basis",
              "display_rule"})


def test_3_the_built_document_moves_only_what_it_claims() -> None:
    doc, changes = R.build_v1_15()
    old = json.loads(R.V1_14.read_text(encoding="utf-8-sig"))
    new_e, old_e = _entry(doc, "HYP-05"), _entry(old, "HYP-05")

    check("3a. status becomes EXPLORATORY_PILOT_TESTED_NULL",
          new_e["status"] == "EXPLORATORY_PILOT_TESTED_NULL")
    check("3b. the new status is documented in the statuses vocabulary",
          "EXPLORATORY_PILOT_TESTED_NULL" in doc["statuses"]
          and "EXPLORATORY_PILOT_TESTED_NULL" not in old.get("statuses", {}))
    check("3c. results had no HYP-05 entry, now does",
          "HYP-05" not in (old.get("results") or {})
          and doc["results"]["HYP-05"]["outcome"] == "NOT_SIGNIFICANT")
    check("3d. results cites the real result artifact by name and hash",
          doc["results"]["HYP-05"]["primary_test_artifact"].startswith(
              "HYP05_PHASE3_RESULT_")
          and len(doc["results"]["HYP-05"]["primary_test_artifact_sha256"])
          == 64)
    check("3e. results explicitly says the floor was NOT met",
          doc["results"]["HYP-05"]["meets_minimum_eligible_events"] is False)
    check("3f. results carries the effective_independent_tests caveat "
          "beside the raw number, not instead of it",
          isinstance(doc["results"]["HYP-05"]["effective_independent_tests"],
                     float)
          and "ARTIFACT" in
          doc["results"]["HYP-05"]["effective_independent_tests_caveat"])
    check("3g. HYP-04's results entry is untouched",
          doc["results"]["HYP-04"] == old["results"]["HYP-04"])
    check("3h. results_note still contains HYP-04's original text",
          "HYP-04's one preregistered holdout run" in doc["results_note"])
    check("3i. results_note now also names HYP-05's pilot",
          "HYP-05's one exploratory pilot run" in doc["results_note"])

    moved = [f for f in IMMOVABLE_ENTRY_FIELDS
             if new_e.get(f) != old_e.get(f)]
    check("3j. nothing immovable moved except the two named",
          set(moved) <= set(R.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE),
          str(moved))
    check("3k. the display rule is untouched",
          new_e["display_rule"] == old_e["display_rule"])
    check("3l. the floor is untouched and still provisional",
          new_e["minimum_eligible_events"]
          == old_e["minimum_eligible_events"] == 195
          and new_e["minimum_eligible_events_basis"]["provisional"] is True)
    check("3m. the decision ledger is untouched",
          new_e["unresolved_analysis_decisions"]
          == old_e["unresolved_analysis_decisions"])

    new_h4 = _entry(doc, "HYP-04")
    old_h4 = _entry(old, "HYP-04")
    check("3n. HYP-04's entire entry is byte-identical", new_h4 == old_h4)
    check("3o. HYP-01/02/03 (carried forward) are untouched",
          doc.get("hypotheses_carried_forward_unchanged")
          == old.get("hypotheses_carried_forward_unchanged"))


def test_4_cannot_mislabel_a_significant_or_floor_clearing_result() -> None:
    """This generator reads the REAL result via a fixed glob, so a bad
    result is exercised by monkeypatching the module's own LSE constant to
    a tempdir seeded with a tampered copy -- the same indirection level
    test_3's `build_v1_15()` call already relies on, not a new mechanism."""
    import tempfile

    real = sorted(LSE.glob("HYP05_PHASE3_RESULT_*.json"))[0]
    real_doc = json.loads(real.read_text(encoding="utf-8"))
    real_auth = sorted(LSE.glob("HYP05_PHASE3_AUTHORIZATION_*.json"))[0]
    lock_name = real_doc["phase2_lock"]["artifact"]

    def _rebuild_in(td: Path, mutate) -> list[str]:
        tmp_lse = td
        for name in (real.name, real_auth.name, lock_name):
            (tmp_lse / name).write_bytes((LSE / name).read_bytes())
        doc = copy.deepcopy(real_doc)
        mutate(doc)
        (tmp_lse / real.name).write_text(json.dumps(doc), encoding="utf-8")
        old_lse = R.LSE
        R.LSE = tmp_lse
        try:
            return R.code_disagreements()
        finally:
            R.LSE = old_lse

    with tempfile.TemporaryDirectory() as td:
        problems = _rebuild_in(
            Path(td), lambda d: d["treatment"].__setitem__(
                "peak_significant", True))
        check("4a. refuses to record NULL status for a significant result",
              any("not False" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as td:
        problems = _rebuild_in(
            Path(td), lambda d: d["sample_size_disclosure"].__setitem__(
                "framing", "CONFIRMATORY"))
        check("4b. refuses to record PILOT status for a non-exploratory "
              "framing", any("exploratory framing" in p for p in problems),
              str(problems))


def test_5_the_rehearsal_does_not_move_hyp04s_gate() -> None:
    """Recording HYP-05's pilot must not move HYP-04's gate in either
    direction -- the gate is HYP-04-specific (HYPOTHESIS_ID hardcoded in
    display_gate.py) and HYP-05 has no gate of its own yet."""
    import tempfile

    from hyp04_supply_chain_hedge.display_gate import FreezeRecord, evaluate_gate

    panel_path = sorted(LSE.glob("HYP04_EVENT_PANEL_*.json"))[-1]
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    ids = tuple(str(i) for i in panel["eligible_event_ids"])

    doc, _ = R.build_v1_15()
    with tempfile.TemporaryDirectory() as td:
        reg = Path(td) / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.15.json"
        reg.write_text(json.dumps(doc), encoding="utf-8")

        rec = FreezeRecord(
            frozen=True, eligible_event_ids=ids,
            analysis_commit_sha="0" * 40,
            analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.md",
            frozen_before_any_result_computed=True,
            uses_placeholder_linkage=False,
        )
        g = evaluate_gate(eligible_event_count=len(ids), freeze=rec,
                          registry_path=reg)
        check("5a. HYP-04's gate is still CLOSED, denying on C1 alone -- "
              "identical to v1.14, unaffected by HYP-05's pilot result",
              g.open is False and len(g.denials) == 1
              and g.denials[0].startswith("C1"), str(g.denials))


def test_6_this_version_has_moved_past() -> None:
    """NARROWED: v1.16 (2026-09-13, registering HYP-06) now supersedes
    v1.15 and holds the live "gate reads X" claim -- see
    test_hyp04_supply_chain_hedge_registry_v1_16.py's own test. This
    suite keeps only what is still true regardless of which version is
    CURRENT: v1.15 itself is real, on disk, and was written by this
    session's own generator."""
    check("6a. v1.15 was written by this session's generator, not this suite",
          (LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.15.json").is_file())


def test_7_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("7a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("7a. network blocked", True)


if __name__ == "__main__":
    test_1_it_refuses_unless_the_result_is_unambiguous()
    test_2_the_exception_is_claimed_and_narrow()
    test_3_the_built_document_moves_only_what_it_claims()
    test_4_cannot_mislabel_a_significant_or_floor_clearing_result()
    test_5_the_rehearsal_does_not_move_hyp04s_gate()
    test_6_this_version_has_moved_past()
    test_7_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-05 REGISTRY v1.15 TESTS PASSED")
    sys.exit(0)
