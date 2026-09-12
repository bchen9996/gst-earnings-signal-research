#!/usr/bin/env python3
"""HYP-04 registry v1.14 -- registers HYP-05, moves nothing about HYP-04.

Two jobs:

  1. v1.14 refuses unless a dated plan and sample-size-gate finding for
     HYP-05 exist, and refuses if HYP-05 is already registered.
  2. HYP-04's entire entry, and the top-level results/results_note and
     hypotheses_carried_forward_unchanged fields, are asserted
     byte-identical to v1.13 -- v1.14's only content is the new HYP-05
     entry.

This is now the CURRENT version, so this suite holds the live "the gate
reads X" claim -- exactly one suite holds it at a time, and v1.13's own
suite was narrowed to a version-agnostic supersession check when this
version superseded it, the same treatment v1.12 got from v1.13.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_14.py
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
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import make_registry_v1_14 as R  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    REGISTRY_CURRENT,
    current_decision,
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


def _hyp04(doc: dict) -> dict:
    return next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-04")


def _hyp05(doc: dict) -> dict:
    return next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-05")


def test_1_it_refuses_unless_the_plan_exists() -> None:
    for f in R.FINDINGS:
        check(f"1b. dated finding on disk: {f}", Path(f).is_file())
    doc = json.loads(R.V1_13.read_text(encoding="utf-8-sig"))
    check("1a. HYP-05 is not registered in v1.13 -- v1.14 adds it new",
          not any(h.get("hypothesis_id") == "HYP-05"
                  for h in doc.get("hypotheses", [])))

    # v1.14 is real and on disk (written by this session's generator, not
    # this suite) -- the generator now refuses for that reason, same
    # discipline as every other governance-artifact generator here.
    refusals = R.check_preconditions()
    check("1c. the generator refuses once v1.14 already exists",
          any("already exists" in r for r in refusals), str(refusals))


def test_2_no_exception_is_claimed() -> None:
    check("2a. SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE is empty -- v1.14 "
          "moves nothing about HYP-04",
          R.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE == ())


def test_3_hyp04_is_untouched_and_hyp05_is_light() -> None:
    doc, changes = R.build_v1_14()
    old = json.loads(R.V1_13.read_text(encoding="utf-8-sig"))

    check("3a. HYP-04's entry is byte-identical to v1.13",
          _hyp04(doc) == _hyp04(old))
    for f in IMMOVABLE_HYP04_FIELDS:
        check(f"3b. HYP-04.{f} unchanged", _hyp04(doc)[f] == _hyp04(old)[f])
    check("3c. results/results_note untouched",
          doc.get("results") == old.get("results")
          and doc.get("results_note") == old.get("results_note"))
    check("3d. hypotheses_carried_forward_unchanged untouched -- HYP-01/02/03 "
          "stay exactly as v1.0 defines them",
          doc.get("hypotheses_carried_forward_unchanged")
          == old.get("hypotheses_carried_forward_unchanged"))

    h5 = _hyp05(doc)
    check("3e. HYP-05 status is PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED",
          h5["status"] == "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED")
    check("3f. HYP-05 is light -- no universe-shaped field is present, "
          "same weight HYP-04 had at its own first registration (v1.1)",
          not any(k in h5 for k in (
              "capture_path_modules", "anchor_universe", "anchor_shock",
              "anchor_event_rule", "peer_target_window")))
    check("3g. HYP-05's floor is explicitly labelled provisional",
          h5["minimum_eligible_events_basis"]["provisional"] is True)
    check("3h. HYP-05's floor is the conservative end of HYP-04's own "
          "borrowed k range (195, not 193)",
          h5["minimum_eligible_events"] == 195, str(h5["minimum_eligible_events"]))
    check("3i. the naive baseline is 126, same as HYP-04's",
          h5["minimum_eligible_events_basis"]["derivation_inputs"]
          ["naive_single_test_baseline"] == 126)
    check("3j. classification and is_primary_confirmatory match HYP-04's own",
          h5["classification"] == "preregistered_exploratory"
          and h5["is_primary_confirmatory"] is False)
    check("3k. every unresolved decision is PENDING_SEPARATE_ANALYSIS_LOCK, "
          "not inherited as resolved from HYP-04",
          all(d["state"] == "PENDING_SEPARATE_ANALYSIS_LOCK"
              for d in h5["unresolved_analysis_decisions"]))


def test_4_the_rehearsal_does_not_open_a_new_gate() -> None:
    """Registering HYP-05 must not move HYP-04's gate in either direction --
    the gate is HYP-04-specific (HYPOTHESIS_ID hardcoded in display_gate.py)
    and HYP-05 has no gate of its own yet."""
    import tempfile

    from hyp04_supply_chain_hedge.display_gate import FreezeRecord, evaluate_gate

    panel_path = sorted(LSE.glob("HYP04_EVENT_PANEL_*.json"))[-1]
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    ids = tuple(str(i) for i in panel["eligible_event_ids"])

    doc, _ = R.build_v1_14()
    with tempfile.TemporaryDirectory() as td:
        reg = Path(td) / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.14.json"
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
        check("4a. HYP-04's gate is still CLOSED, denying on C1 alone -- "
              "identical to v1.13, unaffected by HYP-05's registration",
              g.open is False and len(g.denials) == 1
              and g.denials[0].startswith("C1"), str(g.denials))


def test_5_the_live_gate_reads_v1_14_and_is_closed() -> None:
    """The CURRENT version's suite holds this claim. v1.14 changes nothing
    about HYP-04's gate state -- it is closed for the same reason v1.13
    closed it (HOLDOUT_TESTED_NULL), and this asserts that directly against
    the real, live, committed registry."""
    check("5a. v1.14 was written by this session's generator, not this suite",
          (LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.14.json").is_file())
    check("5b. the gate now reads v1.14",
          REGISTRY_CURRENT.name.endswith("v1.14.json"))
    live = current_decision()
    check("5c. the REAL gate is CLOSED, denying on C1 alone -- unchanged "
          "from v1.13, since v1.14 touches nothing about HYP-04",
          live.open is False and len(live.denials) == 1
          and live.denials[0].startswith("C1"), str(live.denials))


def test_6_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("6a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("6a. network blocked", True)


if __name__ == "__main__":
    test_1_it_refuses_unless_the_plan_exists()
    test_2_no_exception_is_claimed()
    test_3_hyp04_is_untouched_and_hyp05_is_light()
    test_4_the_rehearsal_does_not_open_a_new_gate()
    test_5_the_live_gate_reads_v1_14_and_is_closed()
    test_6_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.14 TESTS PASSED")
    sys.exit(0)
