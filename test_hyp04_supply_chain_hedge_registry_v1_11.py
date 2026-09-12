#!/usr/bin/env python3
"""Tests for registry v1.11 -- the peer price source, and the bias it imports.

=== THE RISK THAT DEFINES THIS SUITE ===

v1.11 records that a SURVIVORS-ONLY price source was adopted. That is the one
thing `peer_price_data_policy` has permitted since v1.5, and only on a
condition: the restriction "and its bias" must be STATED in the version that
does it. A version that took the option while softening, omitting or
de-quantifying the bias would satisfy the letter of the policy and defeat it.

So this suite asserts the conditions that make the option legitimate, not
merely that it was taken:

  * the policy's ORIGINAL reasoning survives verbatim -- especially the
    paragraph explaining why survivorship correlates with the hypothesis
    (test_c); a version that takes an option is not entitled to edit the
    argument for why the option is dangerous
  * the bias is an INTEGER, not a sentence (test_c). "Stated" means quantified.
  * the directional claim is present -- that the unreachable peers are NOT
    missing at random with respect to HYP-04 (test_c)

=== AND THE RISK OF A ROBUSTNESS CHECK NOBODY CAN RUN ===

The split-only series is registered as a robustness variant. Unlike v1.10's
day-0-inclusive window -- which is a slice of data already collected -- it is a
DIFFERENT SERIES and cannot be derived from the primary. A variant registered
without that caveat would promise a check that requires an uncollected fetch.
test_d pins `status` and `derivable_from_the_primary`.

=== SCOPE IS ONE FIELD ===

v1.11 records a DATA SOURCE. It moves no immovable field -- in particular not
`status`, which would need a production capture path this repository does not
have. `SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` must be EMPTY, because
`peer_price_data_policy` is TOP-LEVEL and not an entry field (test_b).

Offline. No network. Nothing in the repo is written by this suite.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_11.py
"""
from __future__ import annotations

import hashlib
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

from hyp04_supply_chain_hedge import run_peer_closes_fetch as fetch  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    REGISTRY_CURRENT,
    current_decision,
)
from hyp04_supply_chain_hedge.make_registry_v1_6 import (  # noqa: E402
    IMMOVABLE_HYP04_FIELDS,
    LSE,
    RefusedError,
)
from hyp04_supply_chain_hedge.make_registry_v1_11 import (  # noqa: E402
    CLOSES_DIR,
    EXPECTED_PEERS,
    EXPECTED_ROWS,
    POLICY_FIELDS_THAT_MUST_SURVIVE,
    SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE,
    V1_10,
    V1_11,
    build_v1_11,
    code_disagreements,
)

FAILURES: list[str] = []
SKIPS: list[str] = []

# Pinned. Every earlier version must stay byte-identical: this chain is the only
# thing that makes "superseded, not edited" a checkable claim rather than a
# promise.
PINNED = {
    "1.3": "03ef40768fa4a45b6192166a",
    "1.4": "b7900bcd5c6676da1221dcdc",
    "1.5": "731ee4f2228477ee6e920045",
    "1.6": "1cce4dcb926640a497337bfa",
    "1.7": "abe45f4d6ff2a78b03439709",
    "1.8": "574baa5dc4b86b73b4f76ea4",
    "1.9": "e7c0b3b746382b0ee7a79445",
    "1.10": "d960190c8202a55bc426ecca",
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
    return json.loads(V1_11.read_text(encoding="utf-8"))


def _entry(doc: dict) -> dict:
    return next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-04")


def test_a_the_chain() -> None:
    print("\n--- A: the chain ---")
    if not V1_11.is_file():
        skip("A. v1.11 on disk", "not generated")
        return
    doc = _doc()
    check("A1. it is version 1.11", doc.get("registry_version") == "1.11",
          str(doc.get("registry_version")))
    check("A2. it supersedes v1.10 by name and hash",
          doc.get("supersedes") == V1_10.name
          and doc.get("supersedes_sha256") == _sha(V1_10))
    check("A3. it names its own companion, not an inherited one",
          str(doc.get("companion_markdown", "")).endswith(
              "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.11_DRAFT.md"),
          str(doc.get("companion_markdown")))

    for ver, prefix in sorted(PINNED.items()):
        p = LSE / f"GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v{ver}.json"
        if not p.is_file():
            skip(f"A4. v{ver} pinned", "not on disk")
            continue
        check(f"A4. v{ver} is still byte-identical",
              _sha(p).startswith(prefix), _sha(p)[:24])

    again, _ = build_v1_11()
    check("A5. the artifact re-derives from its generator",
          again == doc, "generator output differs from the file on disk")

    # Inherited from v1.10's suite when v1.11 superseded it, and weakened
    # again now that v1.13 supersedes v1.12: pinning this to a SPECIFIC next
    # version ("...endswith v1.12.json") is exactly what broke the moment a
    # further version came along, despite this comment already saying the
    # direction "stays true forever" -- the wording said it, the assertion
    # didn't enforce it. What actually stays true forever, and is all this
    # suite should claim, is the direction: v1.11 is superseded, never
    # un-superseded, and never edited in place. The live gate's actual state
    # (open/closed, denial count) belongs to exactly one suite at a time --
    # the CURRENT version's, now
    # test_hyp04_supply_chain_hedge_registry_v1_13.py's test_5.
    check("A6. v1.11 has been superseded -- the gate has moved past it, "
          "whatever it has moved to", REGISTRY_CURRENT.name != V1_11.name,
          REGISTRY_CURRENT.name)


def test_b_scope_is_one_field() -> None:
    print("\n--- B: scope ---")
    if not V1_11.is_file():
        skip("B. scope", "v1.11 not generated")
        return
    doc, src = _doc(), json.loads(V1_10.read_text(encoding="utf-8"))
    new, old = _entry(doc), _entry(src)

    check("B1. no immovable-field exception is claimed",
          SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE == (),
          str(SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE))
    moved = [f for f in IMMOVABLE_HYP04_FIELDS if new.get(f) != old.get(f)]
    check("B2. every immovable field is byte-identical to v1.10",
          not moved, str(moved))
    check("B3. status is STILL PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED -- "
          "collecting prices is not a production capture path",
          new.get("status") == "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED",
          str(new.get("status")))
    check("B4. the threshold is still 193 anchor events",
          new.get("minimum_eligible_events") == 193)
    check("B5. the anchor universe is byte-identical",
          new.get("anchor_universe") == old.get("anchor_universe"))
    check("B6. peer_price_data_policy is TOP-LEVEL, which is why B1 needs no "
          "exception", "peer_price_data_policy" in doc
          and "peer_price_data_policy" not in new)


def test_c_the_bias_is_stated_not_softened() -> None:
    print("\n--- C: the bias ---")
    if not V1_11.is_file():
        skip("C. the bias", "v1.11 not generated")
        return
    doc, src = _doc(), json.loads(V1_10.read_text(encoding="utf-8"))
    pol, old_pol = doc["peer_price_data_policy"], src["peer_price_data_policy"]

    check("C1. the option is recorded as TAKEN",
          pol.get("no_option_taken_here") is False,
          str(pol.get("no_option_taken_here")))
    check("C2. the restriction is named",
          pol.get("restriction_taken") == "survivors_only",
          str(pol.get("restriction_taken")))

    survived = [f for f in POLICY_FIELDS_THAT_MUST_SURVIVE
                if pol.get(f) != old_pol.get(f)]
    check("C3. the policy's ORIGINAL reasoning survives verbatim -- a version "
          "that takes an option may not edit the argument for why the option "
          "is dangerous", not survived, str(survived))

    mb = pol.get("measured_bias") or {}
    n = mb.get("incremental_anchor_events_behind_unresolvable_names")
    check("C4. the bias is QUANTIFIED -- an integer, not a sentence",
          isinstance(n, int) and not isinstance(n, bool), repr(n))
    check("C5. and it is the measured exposure, not a placeholder",
          isinstance(n, int) and n > 0, str(n))
    check("C6. the unresolvable counterparties are counted",
          isinstance(mb.get("unresolvable"), int) and mb["unresolvable"] > 0)
    check("C7. and named, so the exposure is auditable to companies",
          isinstance(mb.get("named_among_the_unreachable"), list)
          and len(mb["named_among_the_unreachable"]) >= 3)

    why = str(pol.get("why_it_biases_toward_the_hypothesis", ""))
    check("C8. the DIRECTIONAL claim is present -- the unreachable peers are "
          "not missing at random with respect to this hypothesis",
          "not missing at random" in why.lower(), why[:70])
    check("C9. and the sample it does NOT touch is stated separately, so the "
          "harmless case does not read as an excuse",
          "bias_does_not_touch_the_current_sample" in pol)


def test_d_the_variant_does_not_overclaim() -> None:
    print("\n--- D: the robustness variant ---")
    if not V1_11.is_file():
        skip("D. the variant", "v1.11 not generated")
        return
    pol = _doc()["peer_price_data_policy"]
    rv = pol.get("robustness_variant") or {}

    check("D1. the primary basis is the fetcher's own constant, not a retyped "
          "copy of it", pol.get("adjustment_basis")
          == fetch.ADJUST_SPLIT_AND_DIVIDEND, str(pol.get("adjustment_basis")))
    check("D2. the variant is the split-only basis",
          rv.get("adjustment_basis") == fetch.ADJUST_SPLIT_ONLY,
          str(rv.get("adjustment_basis")))
    check("D3. it states that it is NOT COLLECTED",
          rv.get("status") == "DECLARED, NOT COLLECTED", str(rv.get("status")))
    check("D4. and that it cannot be derived from the primary -- unlike "
          "v1.10's window variant, which is a slice of data already held",
          rv.get("derivable_from_the_primary") is False,
          str(rv.get("derivable_from_the_primary")))
    check("D5. it says what running it would cost",
          "what_running_it_requires" in rv)


def test_e_nothing_was_measured_and_nothing_moved() -> None:
    print("\n--- E: nothing measured ---")
    if not V1_11.is_file():
        skip("E. nothing measured", "v1.11 not generated")
        return
    doc, src = _doc(), json.loads(V1_10.read_text(encoding="utf-8"))

    check("E1. results is still null", doc.get("results") in (None, {}),
          str(doc.get("results"))[:60])
    check("E2. every eligible-event counter is unchanged",
          doc.get("eligible_event_counts") == src.get("eligible_event_counts"))
    check("E3. statistical_governance is unchanged",
          doc.get("statistical_governance") == src.get("statistical_governance"))
    check("E4. unresolved_analysis_decisions is unchanged -- adding one would "
          "flip C4 and produce a fifth denial",
          _entry(doc).get("unresolved_analysis_decisions")
          == _entry(src).get("unresolved_analysis_decisions"))

    col = doc["peer_price_data_policy"].get("collected") or {}
    check("E5. the collection count is labelled AVAILABILITY, not eligibility",
          "this_is_availability_not_eligibility" in col)
    check("E6. and the artifact says so in the same block as the number",
          "not an eligible-event count" in str(
              col.get("this_is_availability_not_eligibility", "")).lower())

    d = current_decision()
    # E7, E8 and E10 used to assert the live gate was OPEN with zero denials.
    # That is a live-gate claim, which belongs to exactly one suite at a
    # time -- the CURRENT version's, now
    # test_hyp04_supply_chain_hedge_registry_v1_13.py's test_5 -- and it
    # silently went stale the moment v1.13 closed HYP-04 and C1 denied again.
    # v1.11 itself only recorded a DATA SOURCE and said C1 was "a later
    # version's to move"; it never claimed to open anything, so it needs no
    # live-gate opinion at all. C4 (E9) and the frozen count (E11) are not
    # live-gate claims -- they describe facts this version's own text and the
    # freeze established, unaffected by any later status change -- and stay.
    check("E9. and C4 is MET",
          d.conditions.get("C4_decisions_resolved") is True)
    check("E11. the eligible count is the frozen 214, not zero",
          d.evidence["eligible_event_count"] == 214,
          str(d.evidence["eligible_event_count"]))


def test_f_the_generator_refuses_to_outrun_the_code() -> None:
    print("\n--- F: forced refusals ---")

    check("F0. CONTROL -- with the repo as it stands there is no disagreement",
          code_disagreements() == [], str(code_disagreements()))

    with mock.patch(
            "hyp04_supply_chain_hedge.make_registry_v1_11.EXPECTED_ROWS", 999):
        check("F1. a declared row count the files do not have refuses",
              any("999" in p for p in code_disagreements()))

    with mock.patch(
            "hyp04_supply_chain_hedge.make_registry_v1_11.EXPECTED_PEERS",
            ("AAPL", "NOPE")):
        check("F2. a declared peer with no collected file refuses",
              code_disagreements() != [])

    with mock.patch(
            "hyp04_supply_chain_hedge.make_registry_v1_11.CLOSES_DIR",
            Path("no_such_directory_anywhere")):
        problems = code_disagreements()
        check("F3. no collected closes at all refuses",
              any("no peer closes" in p for p in problems), str(problems)[:70])

    with mock.patch.object(fetch, "ADJUST_SPLIT_AND_DIVIDEND", "something_else"):
        check("F4. a basis the fetcher does not apply refuses",
              any("ADJUST_SPLIT_AND_DIVIDEND" in p
                  for p in code_disagreements()))

    # --- the content guards, forced through the policy builder -------------
    import hyp04_supply_chain_hedge.make_registry_v1_11 as gen
    original = gen._policy_block

    def mutating(fn):
        def _f(src):
            pol = original(src)
            fn(pol)
            return pol
        return mock.patch.object(gen, "_policy_block", _f)

    def refuses(label: str, patcher, expect: str) -> None:
        """Refuse, AND refuse for the stated reason. `expect` is REQUIRED.

        build_v1_11 has a dozen guards and all of them raise RefusedError, so
        asserting the TYPE alone lets a mutation that trips some other guard
        first pass as though it exercised the one named. Six mutations here
        share one code path; without the reason they could all be checking the
        same guard and the suite would stay green.
        """
        if not expect.strip():
            check(label, False,
                  "expect= is empty, which matches ANY message and makes this "
                  "assertion vacuous. Give it a real fragment.")
            return
        try:
            with patcher:
                gen.build_v1_11()
        except RefusedError as exc:
            got = str(exc)
            if expect.lower() in got.lower():
                check(label, True)
            else:
                check(label, False,
                      f"refused for the WRONG reason -- wanted {expect!r}, "
                      f"got: {got[:140]}")
        except Exception as exc:                  # noqa: BLE001 -- reported
            check(label, False, f"{type(exc).__name__}: {exc}")
        else:
            check(label, False, "the guard did not fire")

    refuses("F5. rewriting the policy's own reasoning refuses",
            mutating(lambda p: p.__setitem__("why", "shortened")),
            expect="does not rewrite the policy's reasoning")
    refuses("F6. leaving no_option_taken_here True refuses",
            mutating(lambda p: p.__setitem__("no_option_taken_here", True)),
            expect="no_option_taken_here is not False")
    refuses("F7. a bias that is not an integer refuses",
            mutating(lambda p: p["measured_bias"].__setitem__(
                "incremental_anchor_events_behind_unresolvable_names", "lots")),
            expect="carries no integer event count")
    refuses("F8. a variant claiming to be derivable refuses",
            mutating(lambda p: p["robustness_variant"].__setitem__(
                "derivable_from_the_primary", True)),
            expect="claims to be derivable")
    refuses("F9. a variant hiding that it is uncollected refuses",
            mutating(lambda p: p["robustness_variant"].__setitem__(
                "status", "COLLECTED")),
            expect="does not state that it is uncollected")

    with mock.patch(
            "hyp04_supply_chain_hedge.make_registry_v1_11."
            "SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE", ("status",)):
        refuses("F10. claiming an immovable-field exception refuses",
                mock.patch.object(gen, "_policy_block", original),
                expect="claims an immovable-field exception")

    check("F11. CONTROL -- the real build still succeeds after every forced "
          "failure", build_v1_11()[0].get("registry_version") == "1.11")


def test_g_offline() -> None:
    print("\n--- G: offline ---")
    try:
        socket.getaddrinfo("example.com", 443)
        check("G1. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("G1. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_a_the_chain()
    test_b_scope_is_one_field()
    test_c_the_bias_is_stated_not_softened()
    test_d_the_variant_does_not_overclaim()
    test_e_nothing_was_measured_and_nothing_moved()
    test_f_the_generator_refuses_to_outrun_the_code()
    test_g_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.11 TESTS PASSED")
