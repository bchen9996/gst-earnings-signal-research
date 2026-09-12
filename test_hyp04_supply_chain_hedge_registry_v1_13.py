#!/usr/bin/env python3
"""HYP-04 registry v1.13 -- closes HYP-04, and closing it CLOSES the gate.

Three jobs:

  1. v1.13 refuses unless the repository already IS what it declares: one
     real Phase 3 result, null-shaped correctly, tracing through a consumed
     authorization to a signed Phase 2 lock. That is verified granularly --
     each piece is checked directly, not just inferred from an empty refusal
     list, the same discipline v1.12's test suite established.
  2. THE REHEARSAL. v1.13 is built in memory and evaluated through
     `evaluate_gate`, asserting C1 now DENIES and the gate reads CLOSED. That
     is the intended effect of closing HYP-04, not a regression -- the gate
     protects a not-yet-computed result, and HYP-04 has none pending.
  3. The real, live gate is asserted directly once display_gate.py/
     dashboard.py are repointed to v1.13: CLOSED, denying on C1 alone. This
     is now the CURRENT version, so this suite holds that live claim --
     exactly one suite holds it at a time.

Nothing real is written by this file: v1.13 is built in memory and evaluated
through `evaluate_gate(registry_path=...)`, exactly as v1.12's suite did.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_13.py
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

from hyp04_supply_chain_hedge import make_registry_v1_13 as R  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    FreezeRecord,
    evaluate_gate,
)
from hyp04_supply_chain_hedge.make_registry_v1_6 import (  # noqa: E402
    IMMOVABLE_HYP04_FIELDS,
)

ROOT = Path(__file__).resolve().parent
LSE = ROOT / "Live Signal Engine"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _entry(doc: dict) -> dict:
    return next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-04")


def test_1_it_refuses_unless_the_result_is_unambiguous() -> None:
    problems = R.code_disagreements()
    check("1a. the repository matches what v1.13 declares -- one real, "
          "null, fully-traced Phase 3 result", problems == [], str(problems))

    results = sorted(LSE.glob("HYP04_PHASE3_RESULT_*.json"))
    check("1b. exactly one Phase 3 result artifact exists on disk",
          len(results) == 1, str([p.name for p in results]))
    result = json.loads(results[0].read_text(encoding="utf-8"))
    check("1c. it is genuinely null, not just labelled so",
          result["treatment"]["peak_significant"] is False)
    check("1d. it carries the reported-regardless-of-outcome commitment",
          result["reported_regardless_of_outcome"] is True
          and result["no_rerun_permitted"] is True)

    auths = sorted(LSE.glob("HYP04_PHASE3_AUTHORIZATION_*.json"))
    auth = json.loads(auths[0].read_text(encoding="utf-8"))
    check("1e. the authorization is consumed by exactly this result",
          auth["consumed"] is True
          and auth["consumed_by_result"] == results[0].name)

    # And it STILL refuses to run for a different reason: v1.13 is on disk.
    refusals = R.check_preconditions()
    check("1f. the generator refuses once v1.13 already exists",
          any("already exists" in r for r in refusals), str(refusals))


def test_2_the_exception_is_claimed_and_narrow() -> None:
    may_move = set(R.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE)
    check("2a. v1.13 claims an immovable-field exception", bool(may_move))
    check("2b. it is exactly status, status_basis",
          may_move == {"status", "status_basis"}, str(sorted(may_move)))
    check("2c. every named field really is immovable",
          may_move <= set(IMMOVABLE_HYP04_FIELDS),
          str(sorted(may_move - set(IMMOVABLE_HYP04_FIELDS))))
    check("2d. results/results_note need no exception -- they are top-level "
          "fields, not in IMMOVABLE_HYP04_FIELDS at all",
          "results" not in IMMOVABLE_HYP04_FIELDS
          and "results_note" not in IMMOVABLE_HYP04_FIELDS)


def test_3_the_built_document_moves_only_what_it_claims() -> None:
    doc, changes = R.build_v1_13()
    old = json.loads(R.V1_12.read_text(encoding="utf-8-sig"))
    new_e, old_e = _entry(doc), _entry(old)

    check("3a. status becomes HOLDOUT_TESTED_NULL",
          new_e["status"] == "HOLDOUT_TESTED_NULL")
    check("3b. the new status is documented in the statuses vocabulary",
          "HOLDOUT_TESTED_NULL" in doc["statuses"]
          and "HOLDOUT_TESTED_NULL" not in old.get("statuses", {}))
    check("3c. results was null, now carries HYP-04",
          old.get("results") is None and doc["results"]["HYP-04"]["outcome"]
          == "NOT_SIGNIFICANT")
    check("3d. results cites the real result artifact by name and hash",
          doc["results"]["HYP-04"]["primary_test_artifact"].startswith(
              "HYP04_PHASE3_RESULT_")
          and len(doc["results"]["HYP-04"]["primary_test_artifact_sha256"])
          == 64)
    check("3e. results_note no longer claims results are deliberately null",
          "Deliberately null" not in doc["results_note"])

    moved = [f for f in IMMOVABLE_HYP04_FIELDS
             if new_e.get(f) != old_e.get(f)]
    check("3f. nothing immovable moved except the two named",
          set(moved) <= set(R.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE),
          str(moved))
    check("3g. the display rule is untouched",
          new_e["display_rule"] == old_e["display_rule"])
    check("3h. the floor is untouched",
          new_e["minimum_eligible_events"]
          == old_e["minimum_eligible_events"] == 193)
    check("3i. the anchor universe is untouched",
          new_e["anchor_universe"] == old_e["anchor_universe"])
    check("3j. the decision ledger is untouched",
          new_e["unresolved_analysis_decisions"]
          == old_e["unresolved_analysis_decisions"])


def test_4_closing_the_hypothesis_closes_the_gate() -> None:
    """The claim the closure makes: it is a terminal state, and the gate
    reflects that rather than staying open with nothing left to protect."""
    panel_path = sorted(LSE.glob("HYP04_EVENT_PANEL_*.json"))[-1]
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    ids = tuple(str(i) for i in panel["eligible_event_ids"])

    doc, _ = R.build_v1_13()
    with tempfile.TemporaryDirectory() as td:
        reg = Path(td) / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.13.json"
        reg.write_text(json.dumps(doc), encoding="utf-8")

        rec = FreezeRecord(
            frozen=True,
            eligible_event_ids=ids,
            analysis_commit_sha="0" * 40,
            analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.md",
            frozen_before_any_result_computed=True,
            uses_placeholder_linkage=False,
        )
        g = evaluate_gate(eligible_event_count=len(ids), freeze=rec,
                          registry_path=reg)
        c = g.conditions
        check("4a. C1_status now denies -- status is no longer "
              "ACTIVE_COLLECTING", c["C1_status"] is False)
        for cond in ("C2_threshold", "C3_frozen", "C4_decisions_resolved",
                     "C5_not_placeholder"):
            check(f"4b. {cond} still clears -- nothing else about the "
                  "underlying evidence changed", c[cond] is True)
        check("4c. exactly one denial, and it is C1",
              len(g.denials) == 1 and g.denials[0].startswith("C1"),
              str(g.denials))
        check("4d. the gate reads CLOSED", g.open is False)


def test_5_the_live_gate_is_now_closed() -> None:
    """v1.13 is real, on disk, and is what display_gate.py/dashboard.py
    currently read. `evaluate_gate()` with no arguments is a bare call with
    no real freeze or panel supplied -- it always shows C2/C3/C5 failing
    regardless of registry version, which is why v1.12's own suite used
    `current_decision()` for the real answer instead. This does the same.

    This is now the CURRENT version, so this suite holds the live "gate
    reads X" claim -- exactly one suite holds it at a time."""
    check("5a. v1.13 was written by this session's generator, not this suite",
          (LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.13.json").is_file())
    from hyp04_supply_chain_hedge.display_gate import (
        REGISTRY_CURRENT,
        current_decision,
    )
    check("5b. the gate now reads v1.13",
          REGISTRY_CURRENT.name.endswith("v1.13.json"))
    live = current_decision()
    check("5c. so the REAL gate is CLOSED, denying on C1 alone",
          live.open is False and len(live.denials) == 1
          and live.denials[0].startswith("C1"), str(live.denials))


if __name__ == "__main__":
    test_1_it_refuses_unless_the_result_is_unambiguous()
    test_2_the_exception_is_claimed_and_narrow()
    test_3_the_built_document_moves_only_what_it_claims()
    test_4_closing_the_hypothesis_closes_the_gate()
    test_5_the_live_gate_is_now_closed()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.13 TESTS PASSED")
    sys.exit(0)
