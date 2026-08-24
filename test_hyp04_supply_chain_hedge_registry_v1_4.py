#!/usr/bin/env python3
"""Tests for the v1.3 -> v1.4 registry consistency correction -- HYP-04.

v1.4 exists because v1.3 contradicted itself: it corrected HYP-04's linkage
availability to `exists_partial` and left two other statements in the same
document asserting no linkage map exists. Nothing computed from either
sentence, so no result or decision was affected -- but a governance document
that asserts two incompatible things is exactly what these documents exist to
prevent.

=== THE GUARD IS THE DELIVERABLE, AND IT IS TESTED AGAINST THE REAL DEFECT ===

A guard written after the fact is easy to write so that it passes. So test_2
points `find_availability_contradictions()` at the ACTUAL PUBLISHED v1.3 --
which is still on disk, unedited, contradiction included -- and requires it to
find both. If the guard ever stops catching the defect it was written for, that
test fails.

This is the reason v1.3 is not edited in place beyond the append-only rule: the
uncorrected document is the guard's regression fixture.

=== THE EXEMPTIONS ARE THE RISKY PART ===

The guard must not fire on a document EXPLAINING its own history -- a change
summary saying the value moved from `does_not_exist`, or the vocabulary that
DEFINES that word. Those keys are exempt.

An exemption list is how a guard quietly stops guarding. So test_4 checks both
directions: exempt fields are ignored, and an identical phrase in a NON-exempt
field is still caught.

Offline. No network. Nothing is written to the repo by this suite.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_4.py
"""
from __future__ import annotations

import copy
import json
import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge import make_registry_v1_4 as gen  # noqa: E402
from hyp04_supply_chain_hedge.make_registry_v1_4 import (  # noqa: E402
    AVAILABILITY_DOES_NOT_EXIST,
    EXEMPT_KEYS,
    IMMOVABLE_HYP04_FIELDS,
    NONEXISTENCE_CLAIMS,
    V1_3,
    V1_4,
    RefusedError,
    build_v1_4,
    check_preconditions,
    find_availability_contradictions,
    linkage_availability,
)

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


HYP = "HYP-04"


def _src() -> dict:
    return json.loads(V1_3.read_text(encoding="utf-8-sig"))


def _entry(doc: dict, hid: str = HYP) -> dict:
    return next(h for h in doc["hypotheses"] if h["hypothesis_id"] == hid)


# --------------------------------------------------------------------------


def test_1_version_and_supersession() -> None:
    doc, changes = build_v1_4()
    src = _src()

    check("1a. version becomes 1.4", doc["registry_version"] == "1.4",
          str(doc["registry_version"]))
    check("1b. it supersedes v1.3 by name", doc["supersedes"] == V1_3.name)
    check("1c. and records v1.3's hash",
          doc.get("supersedes_sha256") == gen._sha256(V1_3))
    check("1d. companion_markdown names v1.4's own companion",
          doc["companion_markdown"].endswith("v1.4_DRAFT.md"),
          str(doc["companion_markdown"]))
    check("1e. and is NOT inherited from v1.3",
          doc["companion_markdown"] != src.get("companion_markdown"))
    check("1f. the supersession rule says v1.3 keeps its contradiction",
          "CONTRADICTION INCLUDED" in doc["supersession_rule"],
          "a superseded version is allowed to be wrong")
    check("1g. changes are reported, not silent", len(changes) >= 5,
          f"{len(changes)}")


def test_2_the_guard_catches_the_REAL_published_defect() -> None:
    """The load-bearing test. v1.3 on disk is the regression fixture."""
    src = _src()
    check("2a. v1.3 really does say exists_partial",
          linkage_availability(src) == "exists_partial",
          f"got {linkage_availability(src)!r} -- if this changed, the premise "
          "of this whole suite changed")

    hits = find_availability_contradictions(src)
    check("2b. the guard finds contradictions in the published v1.3",
          len(hits) == 2, str(hits))

    paths = " ".join(hits)
    check("2c. it names eligible_event_counts.note",
          "eligible_event_counts.note" in paths, paths)
    check("2d. it names statistical_governance.adding_a_hypothesis_rule",
          "adding_a_hypothesis_rule" in paths, paths)
    check("2e. and reports a dotted path plus the phrase, not just a count",
          all(":" in h and "'" in h for h in hits), str(hits))

    # v1.4 must resolve every one of them.
    doc = build_v1_4()[0]
    after = find_availability_contradictions(doc)
    check("2f. v1.4 resolves all of them", after == [], str(after))
    check("2g. and the corrected note no longer denies the map exists",
          not any(c in doc["eligible_event_counts"]["note"].lower()
                  for c in NONEXISTENCE_CLAIMS),
          doc["eligible_event_counts"]["note"][:120])
    check("2h. while still explaining why the counters stay zero",
          "ANCHOR EVENTS" in doc["eligible_event_counts"]["note"],
          "edges do not produce eligible events")
    check("2i. the hypothesis-addition rule is now explicitly historical",
          "AT THAT TIME" in doc["statistical_governance"]["adding_a_hypothesis_rule"])


def test_3_the_guard_is_vacuous_only_when_it_should_be() -> None:
    """When the map really is absent, saying so is not a contradiction."""
    src = _src()
    absent = copy.deepcopy(src)
    _entry(absent)["required_external_measurement"]["availability"] = \
        AVAILABILITY_DOES_NOT_EXIST
    check("3a. with availability does_not_exist the guard finds nothing",
          find_availability_contradictions(absent) == [],
          "a document may say the map is absent while it is absent")

    # ... and that must NOT be because the guard never fires. Same document,
    # only the availability value differs.
    check("3b. the SAME document with exists_partial does report them",
          len(find_availability_contradictions(src)) == 2,
          "3a must be about the availability value, not a dead guard")

    missing = copy.deepcopy(src)
    missing["hypotheses"] = []
    check("3c. a document with no HYP-04 yields no availability",
          linkage_availability(missing) is None)
    check("3d. and the guard returns nothing rather than raising",
          find_availability_contradictions(missing) == [])


def test_4_exemptions_are_narrow_in_both_directions() -> None:
    """An exemption list is how a guard quietly stops guarding."""
    src = _src()
    phrase = "no peer linkage map exists"

    # Exempt: a change summary explaining the history must not trip it.
    exempt = copy.deepcopy(src)
    exempt["change_summary"] = f"Historically: {phrase}. It now exists in part."
    hits = find_availability_contradictions(exempt)
    check("4a. an exempt key explaining history is not flagged",
          not any("change_summary" in h for h in hits), str(hits))

    # NOT exempt: the identical phrase elsewhere must still be caught.
    nonexempt = copy.deepcopy(src)
    nonexempt["some_new_prose_field"] = f"As of today, {phrase}."
    hits2 = find_availability_contradictions(nonexempt)
    check("4b. the SAME phrase in a non-exempt field IS caught",
          any("some_new_prose_field" in h for h in hits2), str(hits2))

    # Nested, to prove the walk is not top-level only.
    nested = copy.deepcopy(src)
    nested["a"] = {"b": [{"c": f"note: {phrase}"}]}
    check("4c. the walk reaches nested dicts and lists",
          any("a.b[0].c" in h for h in find_availability_contradictions(nested)),
          str(find_availability_contradictions(nested)))

    check("4d. the exemption list is short and explicit",
          len(EXEMPT_KEYS) <= 8, f"{len(EXEMPT_KEYS)} keys: {EXEMPT_KEYS}")
    check("4e. and does not exempt the fields that were actually wrong",
          "eligible_event_counts" not in EXEMPT_KEYS
          and "statistical_governance" not in EXEMPT_KEYS,
          "exempting those would make the guard useless")


def test_5_the_generator_refuses_its_own_bad_output() -> None:
    """build_v1_4 runs the guard on what it is about to write."""
    src = _src()
    real = gen._load
    try:
        # A v1.3 with an EXTRA contradiction the generator does not know to fix.
        poisoned = copy.deepcopy(src)
        poisoned["unfixed_prose"] = "As of now, no peer linkage map exists."
        gen._load = lambda p, _d=poisoned: copy.deepcopy(_d)  # type: ignore
        try:
            build_v1_4()
            check("5a. it refuses to write a document that still contradicts",
                  False, "no refusal -- the guard did not run on its own output")
        except RefusedError as e:
            check("5a. it refuses to write a document that still contradicts",
                  "unfixed_prose" in str(e), str(e)[:140])
    finally:
        gen._load = real

    # The control: with the real v1.3 it does NOT refuse.
    try:
        build_v1_4()
        check("5b. control -- the real v1.3 builds without refusal", True)
    except RefusedError as e:
        check("5b. control -- the real v1.3 builds without refusal", False, str(e))


def test_6_nothing_but_prose_moves() -> None:
    doc = build_v1_4()[0]
    src = _src()
    new, old = _entry(doc), _entry(src)

    for field in IMMOVABLE_HYP04_FIELDS:
        check(f"6a. HYP-04.{field} unchanged", new.get(field) == old.get(field))

    check("6b. the whole measurement block is byte-identical",
          new["required_external_measurement"] == old["required_external_measurement"],
          "v1.4 corrects prose ABOUT the measurement, never the measurement")
    check("6c. capture paths still report no data captured",
          all(v.get("data_captured") is False
              for v in new["capture_path_modules"].values()
              if isinstance(v, dict)))
    check("6d. results stay null", doc.get("results") is None)
    check("6e. eligible counts stay zero",
          all(v == 0 for k, v in doc["eligible_event_counts"].items()
              if isinstance(v, int)))
    check("6f. carried-forward hypotheses untouched",
          doc["hypotheses_carried_forward_unchanged"]
          == src["hypotheses_carried_forward_unchanged"])

    # The control: something DID change, or the transform did nothing.
    check("6g. control -- the document did change",
          doc["eligible_event_counts"]["note"]
          != src["eligible_event_counts"]["note"])

    rec = doc.get("contradiction_corrected")
    check("6h. the correction records what was wrong and why",
          isinstance(rec, dict) and len(rec.get("paths", [])) == 2, str(rec)[:120])
    check("6i. and states that no result was affected",
          "No result, decision or gate state changed" in
          str(rec.get("no_effect_on_results", "")))


def test_7_the_gate_does_not_move() -> None:
    from hyp04_supply_chain_hedge.display_gate import current_decision

    d = current_decision()
    check("7a. the gate is CLOSED", not d.open, str(d.status))
    check("7b. C4 reads MET", d.conditions.get("C4_decisions_resolved") is True)
    check("7c. exactly four denials", len(d.denials) == 4, str(len(d.denials)))
    check("7d. C5 still denies", not d.conditions.get("C5_not_placeholder", True))


def test_8_older_versions_survive_unedited() -> None:
    before = gen._sha256(V1_3)
    build_v1_4()
    check("8a. building v1.4 does not touch v1.3",
          gen._sha256(V1_3) == before)
    for older in ("v1.0", "v1.1", "v1.2", "v1.3"):
        p = gen.LSE / f"GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_{older}.json"
        check(f"8b. {older} still on disk", p.is_file())

    check("8c. v1.3 keeps its contradiction as the guard's fixture",
          len(find_availability_contradictions(_src())) == 2,
          "if v1.3 were quietly fixed, test_2 would pass vacuously forever")


def test_9_the_written_artifact() -> None:
    if not V1_4.exists():
        skip("9. v1.4 artifact on disk",
             f"{V1_4.name} not generated yet -- run make_registry_v1_4 --write")
        return
    doc = json.loads(V1_4.read_text(encoding="utf-8-sig"))
    check("9a. the artifact matches what the generator builds",
          doc == build_v1_4()[0])
    check("9b. it declares version 1.4", doc["registry_version"] == "1.4")
    check("9c. and contradicts itself nowhere",
          find_availability_contradictions(doc) == [])


def test_10_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("10a. network blocked", False, "a lookup succeeded")
    except Exception as e:  # noqa: BLE001
        check("10a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_version_and_supersession()
    test_2_the_guard_catches_the_REAL_published_defect()
    test_3_the_guard_is_vacuous_only_when_it_should_be()
    test_4_exemptions_are_narrow_in_both_directions()
    test_5_the_generator_refuses_its_own_bad_output()
    test_6_nothing_but_prose_moves()
    test_7_the_gate_does_not_move()
    test_8_older_versions_survive_unedited()
    test_9_the_written_artifact()
    test_10_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.4 TESTS PASSED")
    sys.exit(0)
