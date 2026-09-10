#!/usr/bin/env python3
"""Tests for registry v1.10 -- the two specifications v1.9 left open.

=== THE RISK THAT DEFINES THIS SUITE ===

One of the two changes moves results in the FAVOURABLE direction. Ending the
peer target's reference window at anchor_day - 1 removes a possibly contaminated
session from the baseline, which lowers the baseline and RAISES the measured
log-ratio. That is the shape of change this project's rules exist to stop being
made after the fact.

It is legitimate only because nothing has been measured. So this suite asserts
the conditions that make it legitimate, not merely that it happened:

  * every eligible-event counter is still zero, and `results` is still null
    (test_e) -- if a result existed, this version could not have been written
  * the superseded window is REGISTERED as the robustness variant and
    reproduces the old arithmetic exactly (test_d)
  * the attestation is IN THE ARTIFACT, not only in a commit message (test_d)

=== AND THE RISK OF A WIDER RULE WEARING AN ERA-AWARE LABEL ===

"Accept Item 12 as well" and "select by the numbering in force on the report
date" produce identical counts on this corpus and are not the same rule. The
first would admit a bare `12` on a 2010 filing. The first draft of
`results_item_verdict` did exactly that and was caught by v1.10's own
`code_disagreements()` guard, because no filing in the corpus would have caught
it. test_b pins both era boundaries.

=== NO EXCEPTION IS CLAIMED ===

v1.9 needed one named immovable field. v1.10 adds KEYS and needs none, so
`SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` must be EMPTY and every immovable
field must be byte-identical (test_c).

Offline. No network. Nothing in the repo is written by this suite.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_10.py
"""
from __future__ import annotations

import hashlib
import inspect
import json
import socket
import sys
from pathlib import Path
from unittest import mock


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import numpy as np  # noqa: E402

from hyp04_supply_chain_hedge import anchor_calendar as acal  # noqa: E402
from hyp04_supply_chain_hedge import anchor_shock as ashock  # noqa: E402
from hyp04_supply_chain_hedge import closes_requirements as creq  # noqa: E402
from hyp04_supply_chain_hedge import constants as K  # noqa: E402
from hyp04_supply_chain_hedge import earnings_events as ee  # noqa: E402
from hyp04_supply_chain_hedge import peer_returns as pret  # noqa: E402
from hyp04_supply_chain_hedge import target as tgt  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    REGISTRY_CURRENT,
    current_decision,
)
from hyp04_supply_chain_hedge.make_registry_v1_6 import (  # noqa: E402
    IMMOVABLE_HYP04_FIELDS,
    LSE,
)
from hyp04_supply_chain_hedge.make_registry_v1_10 import (  # noqa: E402
    DECISIONS_TAKEN_ON,
    SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE,
    V1_9,
    V1_10,
    RefusedError,
    build_v1_10,
    code_disagreements,
)

FAILURES: list[str] = []
SKIPS: list[str] = []

# Pinned. Every earlier version must stay byte-identical: this chain is the only
# thing that makes "superseded, not edited" a checkable claim rather than a
# promise.
PINNED = {
    "1.4": "b7900bcd5c6676da1221dcdc",
    "1.5": "731ee4f2228477ee6e920045",
    "1.6": "1cce4dcb926640a497337bfa",
    "1.7": "abe45f4d6ff2a78b03439709",
    "1.8": "574baa5dc4b86b73b4f76ea4",
    "1.9": "e7c0b3b746382b0ee7a79445",
}


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _doc() -> dict:
    return json.loads(V1_10.read_text(encoding="utf-8"))


def _entry(doc: dict) -> dict:
    return next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-04")


def test_a_the_artifact_exists_and_supersedes_cleanly() -> None:
    print("\n--- A: the chain ---")
    if not V1_10.is_file():
        skip("A. v1.10 on disk", "not generated")
        return
    doc = _doc()
    check("A1. it is version 1.10", doc.get("registry_version") == "1.10",
          str(doc.get("registry_version")))
    check("A2. it supersedes v1.9 by name and hash",
          doc.get("supersedes") == V1_9.name
          and doc.get("supersedes_sha256") == _sha(V1_9))
    check("A3. v1.9 is still on disk, byte-identical",
          _sha(V1_9).startswith(PINNED["1.9"]), _sha(V1_9)[:24])
    for v, pin in PINNED.items():
        p = LSE / f"GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v{v}.json"
        if not p.is_file():
            skip(f"A4. v{v} pinned", "absent")
            continue
        check(f"A4. v{v} unchanged", _sha(p).startswith(pin), _sha(p)[:24])
    # AUTHORED and DECIDED are different dates and must not be collapsed.
    check("A5. the decision date is recorded separately from the authoring date",
          doc.get("decisions_taken_on") == DECISIONS_TAKEN_ON
          and doc.get("authored_at_utc") != doc.get("decisions_taken_on"),
          f'{doc.get("decisions_taken_on")} / {doc.get("authored_at_utc")}')
    # NARROWED, not retargeted -- the same treatment v1.7's, v1.8's and v1.9's
    # suites got when they were superseded. A frozen version's suite asserting
    # that IT is current breaks at every subsequent version, which trains the
    # reader to retarget a failing assertion instead of reading it. What v1.10
    # must still be able to claim is that it WAS superseded, not that it is in
    # force. The positive claim -- that the gate reads the current version --
    # moves with the pointer, to v1.11's suite, where it is A6 again.
    check("A6. v1.10 is no longer the current artifact -- v1.11 superseded it",
          not REGISTRY_CURRENT.name.endswith("v1.10.json"),
          REGISTRY_CURRENT.name)


def test_b_the_era_rule_is_era_aware_not_merely_wider() -> None:
    """The distinction that has no corpus example, so only a test can hold it."""
    print("\n--- B: the anchor-event rule ---")
    if not V1_10.is_file():
        skip("B. era rule", "v1.10 not generated")
        return
    blk = _entry(_doc()).get("anchor_event_rule")
    check("B1. the block exists", isinstance(blk, dict))
    if not isinstance(blk, dict):
        return

    again = acal.rule_description()
    overlap = {k: blk[k] for k in blk if k in again}
    check("B2. every declared field re-derives from the rule itself",
          overlap == {k: again[k] for k in overlap},
          str([k for k in overlap if overlap[k] != again[k]]))
    check("B3. it names the rule", blk.get("rule_id") == ee.ANCHOR_EVENT_RULE_ID)
    check("B4. all three eras are carried, not summarised",
          len(blk.get("eras") or []) == 3, str(len(blk.get("eras") or [])))

    # THE BOUNDARIES. Both are real dates in an SEC release, and both matter.
    check("B5. Item 12 counts INSIDE its era",
          ee.is_results_filing("12,7", "2004-01-22"))
    check("B6. and NOT after the renumbering -- otherwise the rule is merely "
          "wider, not era-aware",
          not ee.is_results_filing("12,7", "2010-01-22"))
    check("B7. and NOT before Item 12 existed",
          not ee.is_results_filing("12,7", "2001-01-22"))
    check("B8. an out-of-era legacy code is FLAGGED, not silently dropped",
          ee.results_item_verdict("12,7", "2010-01-22")[2]
          == ee.FLAG_LEGACY_CODE_OUT_OF_ERA)
    check("B9. Item 2.02 counts in the modern era",
          ee.is_results_filing("2.02,9.01", "2010-04-13"))
    check("B10. a MODERN code before the renumbering is counted but flagged",
          ee.is_results_filing("2.02", "2001-12-16")
          and ee.results_item_verdict("2.02", "2001-12-16")[2]
          == ee.FLAG_MODERN_CODE_BEFORE_RENUMBERING)
    check("B11. codes are EXACT tokens -- '12' is not found inside '1.12'",
          not ee.is_results_filing("1.12,9.01", "2003-06-01"))
    check("B12. the derivation DEFAULTS to this rule",
          inspect.signature(acal.derive_anchor_calendar)
          .parameters["accept_legacy_item_12"].default is True)
    check("B13. and the superseded rule is still reachable, so the earlier "
          "artifact stays reproducible",
          not ee.is_results_filing("12,7", "2004-01-22",
                                   accept_legacy_item_12=False))
    check("B14. the under-inclusion before Item 12 existed is stated, not hidden",
          any("no earnings-specific item code" in s
              for s in blk.get("known_limitations") or []),
          str(blk.get("known_limitations"))[:120])


def test_c_no_immovable_field_moved_and_no_exception_claimed() -> None:
    print("\n--- C: nothing moved that must not ---")
    if not V1_10.is_file():
        skip("C. immovable fields", "v1.10 not generated")
        return
    doc, src = _doc(), json.loads(V1_9.read_text(encoding="utf-8"))
    new, old = _entry(doc), _entry(src)

    check("C1. the version claims NO immovable-field exception",
          SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE == (),
          str(SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE))
    moved = [f for f in IMMOVABLE_HYP04_FIELDS if new.get(f) != old.get(f)]
    check("C2. and none moved", not moved, str(moved))
    check("C3. membership is byte-identical to v1.9",
          new.get("anchor_universe") == old.get("anchor_universe"))
    check("C4. unresolved_analysis_decisions is untouched -- adding one would "
          "flip C4 and produce a fifth denial",
          new.get("unresolved_analysis_decisions")
          == old.get("unresolved_analysis_decisions"))
    check("C5. peer_price_data_policy is untouched -- it governs the PEER side "
          "and still has no selected source",
          doc.get("peer_price_data_policy") == src.get("peer_price_data_policy"))
    check("C6. v1.9's anchor_shock fields are untouched; v1.10 only ADDS",
          {k: v for k, v in new["anchor_shock"].items()
           if k in old["anchor_shock"]} == old["anchor_shock"])
    check("C7. and the addition is the return basis",
          new["anchor_shock"].get("return_basis") == "log"
          and "return_basis" not in old["anchor_shock"])


def test_d_the_window_change_carries_its_own_justification() -> None:
    print("\n--- D: the peer target window ---")
    if not V1_10.is_file():
        skip("D. window", "v1.10 not generated")
        return
    w = _entry(_doc()).get("peer_target_window")
    check("D1. the block exists", isinstance(w, dict))
    if not isinstance(w, dict):
        return

    check("D2. it re-derives from the constants",
          w["reference_window_length_sessions"] == K.REFERENCE_WINDOW_TRADING_DAYS
          and w["reference_window_offset_sessions"]
          == K.REFERENCE_WINDOW_OFFSET_SESSIONS)
    check("D3. anchor_day is in NEITHER window",
          w.get("anchor_day_is_in_neither_window") is True)
    check("D4. the FAVOURABLE direction is stated, not buried",
          "FAVOURABLE" in w.get("direction_of_the_change", ""))
    check("D5. and the attestation that makes it legitimate is IN THE ARTIFACT",
          "NOTHING HAS BEEN MEASURED" in w.get("why_this_is_legitimate_now", ""))
    check("D6. the superseded window is REGISTERED as the robustness variant",
          w["robustness_specification"]["reference_window_offset_sessions"] == 0)
    check("D7. only the endpoint moved -- the length is unchanged",
          "length is unchanged" in w.get("only_the_endpoint_moved", "").lower(),
          w.get("only_the_endpoint_moved", "")[:80])

    # The robustness variant must actually reproduce the old arithmetic, or the
    # superseded specification is registered in name only.
    #
    # DETERMINISTIC, not random. A governance assertion should not depend on an
    # RNG at all, and numpy.random additionally pulls a DLL that Application
    # Control blocks on this machine -- so the seeded version of this test could
    # fail for a reason that has nothing to do with the registry. The sequence
    # below just needs varying magnitudes so the two windows differ.
    # Strictly increasing magnitude inside each window, so shifting the
    # window by ONE session provably changes the variance. The first
    # attempt used a period-13 pattern whose squares are symmetric, and
    # the two windows came out exactly equal -- the test data, not the
    # code, was hiding the difference.
    r = np.array([0.0005 * (i % 37) for i in range(200)], dtype=float)
    old_ref = tgt.log_rvar(r[81:101])
    post = tgt.log_rvar(r[101:106])
    check("D8. reference_offset=0 reproduces the SUPERSEDED arithmetic exactly",
          abs(tgt.raw_log_ratio_target(r, 100, 5, reference_offset=0)
              - (post - old_ref)) < 1e-12)
    check("D9. and the DEFAULT is a genuinely different window",
          abs(tgt.raw_log_ratio_target(r, 100, 5)
              - (post - tgt.log_rvar(r[80:100]))) < 1e-12
          and tgt.raw_log_ratio_target(r, 100, 5)
          != tgt.raw_log_ratio_target(r, 100, 5, reference_offset=0))

    # COVERAGE AND THE TARGET MUST SLICE THE SAME WINDOW.
    check("D10. peer coverage defaults to the same offset as the target",
          inspect.signature(pret.coverage_for_event)
          .parameters["reference_offset"].default
          == inspect.signature(tgt.raw_log_ratio_target)
          .parameters["reference_offset"].default)

    # And the request must cover BOTH, or the registered robustness check is
    # uncollectable without a second round.
    check("D11. the data cost is one extra close, and it is stated",
          creq.closes_per_event() - creq.closes_per_event(reference_offset=0) == 1
          and "one additional close" in w.get("data_cost", "").lower())
    check("D12. the emitted span COVERS the robustness variant too",
          creq.session_span(100)[0]
          <= creq.session_span(100, reference_offset=0)[0])


def test_e_nothing_was_measured_and_nothing_moved() -> None:
    print("\n--- E: this version reports nothing ---")
    if not V1_10.is_file():
        skip("E. no results", "v1.10 not generated")
        return
    doc, src = _doc(), json.loads(V1_9.read_text(encoding="utf-8"))
    entry = _entry(doc)

    check("E1. results is still null", doc.get("results") in (None, {}),
          str(doc.get("results"))[:60])
    counts = doc.get("eligible_event_counts") or {}
    check("E2. every eligible-event counter is still zero",
          all(v == 0 for v in counts.values() if isinstance(v, int)),
          str(counts))
    check("E3. and they are byte-identical to v1.9's",
          counts == src.get("eligible_event_counts"))
    check("E4. the threshold is still 193 anchor events",
          entry.get("minimum_eligible_events") == 193)
    check("E5. status is unchanged",
          entry.get("status") == _entry(src).get("status"),
          str(entry.get("status")))
    check("E6. statistical_governance is untouched",
          doc.get("statistical_governance") == src.get("statistical_governance"))

    d = current_decision()
    # OPENED 2026-09-09 (freeze attested + registry v1.12 moved C1); CLOSED
    # with 4 denials for all of Phase 0. v1.10 is not what opened it -- the
    # four conditions below cleared through the freeze and v1.12, in that
    # order, months after this version.
    check("E7. the gate is OPEN", getattr(d, "open", False))
    check("E8. with zero denials", len(d.denials) == 0, str(d.denials))
    check("E9. and C4 is MET", d.conditions.get("C4_decisions_resolved") is True)
    for c in ("C1_status", "C2_threshold", "C3_frozen", "C5_not_placeholder"):
        check(f"E10. {c} now passes", d.conditions.get(c) is True)


def test_f_the_generator_refuses_to_outrun_the_code() -> None:
    """A guard nobody has seen fail is not known to work.

    Each disagreement is forced and the refusal asserted. The era-bound guard
    in particular already caught a real defect on its first run -- the first
    draft accepted a bare Item 12 on a 2010 filing -- so this is a regression
    test for something that actually happened, not a hypothetical.
    """
    print("\n--- F: the refusal fires ---")
    check("F0. CONTROL -- with the code as it is, there is no disagreement",
          code_disagreements() == [], str(code_disagreements()))

    def _forces(what, patcher, needle):
        with patcher:
            problems = code_disagreements()
        check(f"F. {what} is refused", any(needle in p for p in problems),
              str(problems)[:130])

    _forces("an item rule that is merely wider",
            mock.patch.object(ee, "ITEM_RENUMBERED_TO_2_02", "2099-01-01"),
            "AFTER the renumbering")
    _forces("a derivation not defaulting to the era rule",
            mock.patch.object(
                acal, "derive_anchor_calendar",
                lambda *a, accept_legacy_item_12=False, **k: None),
            "does not DEFAULT")
    _forces("a reference window still ending at the anchor day",
            mock.patch.object(K, "REFERENCE_WINDOW_OFFSET_SESSIONS", 0),
            "still ends AT the anchor day")
    _forces("a target with no window parameter",
            mock.patch.object(tgt, "raw_log_ratio_target",
                              lambda *a, **k: 0.0),
            "no `reference_offset` parameter")
    _forces("coverage and the target disagreeing on the window",
            mock.patch.object(
                pret, "coverage_for_event",
                lambda *a, reference_offset=0, **k: None),
            "disagree")
    _forces("an unstated return basis",
            mock.patch.object(ashock, "RETURN_BASIS", "simple"),
            "is not 'log'")

    # And the build itself must refuse, not merely report.
    with mock.patch.object(ashock, "RETURN_BASIS", "simple"):
        try:
            build_v1_10()
            check("F7. build_v1_10 RAISES on a disagreement", False,
                  "it returned a document")
        except RefusedError:
            check("F7. build_v1_10 RAISES on a disagreement", True)

    check("F8. CONTROL -- the guard is restored afterwards",
          code_disagreements() == [])


def test_g_offline() -> None:
    print("\n--- G: offline ---")
    try:
        socket.getaddrinfo("example.com", 443)
        check("G1. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("G1. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_a_the_artifact_exists_and_supersedes_cleanly()
    test_b_the_era_rule_is_era_aware_not_merely_wider()
    test_c_no_immovable_field_moved_and_no_exception_claimed()
    test_d_the_window_change_carries_its_own_justification()
    test_e_nothing_was_measured_and_nothing_moved()
    test_f_the_generator_refuses_to_outrun_the_code()
    test_g_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.10 TESTS PASSED")
