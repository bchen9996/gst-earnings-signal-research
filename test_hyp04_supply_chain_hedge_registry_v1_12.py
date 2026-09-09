#!/usr/bin/env python3
"""HYP-04 registry v1.12 -- the C1 generator, and the end-to-end rehearsal.

Two jobs:

  1. v1.12 refuses to run out of order. C1 is the LAST gate condition to move,
     and the generator must not clear it while the map is unratified or the
     freeze is missing.
  2. THE REHEARSAL. Signing the documents has to actually work, so this
     assembles the whole chain -- v1.12's registry, the real panel's 214
     enumerated events, a completed freeze -- and asserts `evaluate_gate`
     returns OPEN with ZERO denials.

Nothing real is written: v1.12 is built in memory and evaluated through
`evaluate_gate(registry_path=...)`, which takes the path as an argument
precisely so this can be checked without repointing anything.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_12.py
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

from hyp04_supply_chain_hedge import make_registry_v1_12 as R  # noqa: E402
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


def test_1_it_refuses_out_of_order_today() -> None:
    """The map is unratified and no freeze exists, so C1 must not move."""
    problems = R.code_disagreements()
    check("1a. the generator refuses against the real repository",
          bool(problems))
    joined = " ".join(problems)
    check("1b. it names the unratified map", "not 'reviewed'" in joined,
          joined[:160])
    check("1c. it names the missing freeze", "freeze" in joined.lower())
    check("1d. and says C1 moves last",
          "LAST condition" in joined or "last condition" in joined.lower())


def test_2_the_exception_is_claimed_and_narrow() -> None:
    may_move = set(R.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE)
    check("2a. v1.12 claims an immovable-field exception", bool(may_move))
    check("2b. it is exactly status, status_basis, capture_path_modules",
          may_move == {"status", "status_basis", "capture_path_modules"},
          str(sorted(may_move)))
    check("2c. every named field really is immovable",
          may_move <= set(IMMOVABLE_HYP04_FIELDS),
          str(sorted(may_move - set(IMMOVABLE_HYP04_FIELDS))))


def test_3_the_built_document_moves_only_what_it_claims() -> None:
    doc, changes = R.build_v1_12()
    old = json.loads(R.V1_11.read_text(encoding="utf-8-sig"))
    new_e, old_e = _entry(doc), _entry(old)

    check("3a. status becomes ACTIVE_COLLECTING",
          new_e["status"] == "ACTIVE_COLLECTING")
    check("3b. both original capture paths now carry data",
          all(new_e["capture_path_modules"][k]["data_captured"] is True
              for k in ("peer_return_ingestion", "event_to_peer_join")))
    check("3c. the assembler is registered as a path",
          new_e["capture_path_modules"]["panel_assembly"]["module"]
          == "hyp04_supply_chain_hedge/make_event_panel.py")
    check("3d. the stale curated-edge count is gone from status_basis",
          "2 curated edge(s) as of 2026-08-22" not in new_e["status_basis"]
          and "2 curated edge(s) as of 2026-08-22" in old_e["status_basis"])

    moved = [f for f in IMMOVABLE_HYP04_FIELDS
             if new_e.get(f) != old_e.get(f)]
    check("3e. nothing immovable moved except the three named",
          set(moved) <= set(R.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE),
          str(moved))
    check("3f. the display rule is untouched",
          new_e["display_rule"] == old_e["display_rule"])
    check("3g. the floor is untouched",
          new_e["minimum_eligible_events"]
          == old_e["minimum_eligible_events"] == 193)
    check("3h. the anchor universe is untouched",
          new_e["anchor_universe"] == old_e["anchor_universe"])
    check("3i. the decision ledger is untouched",
          new_e["unresolved_analysis_decisions"]
          == old_e["unresolved_analysis_decisions"])


def test_4_the_rehearsal_opens_the_gate() -> None:
    """The claim the deliverables make: signing these actually works."""
    panel_path = sorted(LSE.glob("HYP04_EVENT_PANEL_*.json"))[-1]
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    ids = tuple(str(i) for i in panel["eligible_event_ids"])
    check("4a. the panel enumerates its eligible set",
          len(ids) == panel["per_pair"]["eligible_anchor_events"] > 0)

    doc, _ = R.build_v1_12()
    with tempfile.TemporaryDirectory() as td:
        reg = Path(td) / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.12.json"
        reg.write_text(json.dumps(doc), encoding="utf-8")

        # What a completed freeze looks like once the owner has attested.
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
        for cond in ("C1_status", "C2_threshold", "C3_frozen",
                     "C4_decisions_resolved", "C5_not_placeholder"):
            check(f"4b. {cond} clears", c[cond] is True)
        check("4c. ZERO denials", len(g.denials) == 0, str(g.denials))
        check("4d. the gate is OPEN", g.open is True)

        # And the order guard is real: the same registry with no freeze denies.
        g2 = evaluate_gate(eligible_event_count=len(ids), freeze=None,
                           registry_path=reg)
        check("4e. without the freeze, the same registry still denies",
              g2.open is False and any(d.startswith("C3") for d in g2.denials),
              str(g2.denials))
        check("4f. and C5 denies too -- a missing freeze is placeholder "
              "linkage by default",
              g2.conditions["C5_not_placeholder"] is False)


def test_5_the_real_gate_is_untouched() -> None:
    g = evaluate_gate()
    check("5a. the real gate is still CLOSED", g.open is False)
    check("5b. still four denials", len(g.denials) == 4, str(len(g.denials)))
    check("5c. no v1.12 was written",
          not (LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.12.json").exists())
    check("5d. the gate still reads v1.11",
          "v1.11" in str(__import__(
              "hyp04_supply_chain_hedge.display_gate",
              fromlist=["REGISTRY_CURRENT"]).REGISTRY_CURRENT))


if __name__ == "__main__":
    test_1_it_refuses_out_of_order_today()
    test_2_the_exception_is_claimed_and_narrow()
    test_3_the_built_document_moves_only_what_it_claims()
    test_4_the_rehearsal_opens_the_gate()
    test_5_the_real_gate_is_untouched()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.12 TESTS PASSED")
    sys.exit(0)
