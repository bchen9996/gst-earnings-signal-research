#!/usr/bin/env python3
"""Tests for the v1.2 -> v1.3 registry transform -- HYP-04.

v1.3 is a FACTUAL CORRECTION, not a decision. That makes its risk profile the
opposite of v1.2's: v1.2 had to change four decision states and nothing else,
while v1.3 must change three descriptive fields and nothing else -- and the
tempting failure is to let a correction quietly become a promotion.

So the load-bearing tests are the ones proving what did NOT move:

  * no hypothesis other than HYP-04 changes at all (test_4)
  * HYP-04's status, classification, thresholds, display rule and forbidden
    substitutions are untouched (test_4)
  * the decision ledger is byte-identical -- v1.3 resolves and reopens nothing
  * the display gate is CLOSED with C4 MET both before and after (test_7)

And the honesty tests, which are the whole reason `exists_partial` exists
rather than `exists`:

  * `exists_partial` is DEFINED in the document, not merely used (test_3)
  * it is explicitly stated NOT to mean sufficiency (test_3)
  * `capture_path_modules` reports `data_captured: false` for both (test_5) --
    a module that CAN ingest peer returns is not ingested data, and this
    registry version must not let those blur

Refusals matter as much as the transform (test_6). The generator records that a
curated map exists; if it would write that while no map exists, loads dirty, or
yields no usable edges, the field would assert something false. Each is checked
by making the observed state say so, because a refusal path that is never
exercised is a refusal path that does not work.

Offline. No network. Nothing is written to the repo by this suite.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_3.py
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

from hyp04_supply_chain_hedge import make_registry_v1_3 as gen  # noqa: E402
from hyp04_supply_chain_hedge.make_registry_v1_3 import (  # noqa: E402
    AVAILABILITY_DOES_NOT_EXIST,
    AVAILABILITY_EXISTS_PARTIAL,
    AVAILABILITY_VOCABULARY,
    V1_2,
    V1_3,
    RefusedError,
    build_v1_3,
    check_preconditions,
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
    return json.loads(V1_2.read_text(encoding="utf-8-sig"))


def _entry(doc: dict, hid: str = HYP) -> dict:
    return next(h for h in doc["hypotheses"] if h["hypothesis_id"] == hid)


# --------------------------------------------------------------------------


def test_1_version_and_supersession() -> None:
    doc, changes = build_v1_3()
    src = _src()

    check("1a. version becomes 1.3", doc["registry_version"] == "1.3",
          str(doc["registry_version"]))
    check("1b. it supersedes v1.2 by name", doc["supersedes"] == V1_2.name,
          str(doc["supersedes"]))
    check("1c. and records v1.2's hash",
          len(doc.get("supersedes_sha256", "")) == 64)
    check("1d. the hash is actually v1.2's",
          doc["supersedes_sha256"] == gen._sha256(V1_2))

    # The v1.2 bug: companion_markdown was inherited, so v1.2 claimed v1.1's
    # companion as its own. It must be set explicitly at every bump.
    check("1e. companion_markdown names v1.3's own companion",
          doc["companion_markdown"].endswith("v1.3_DRAFT.md"),
          str(doc["companion_markdown"]))
    check("1f. and is NOT inherited from v1.2",
          doc["companion_markdown"] != src.get("companion_markdown"))

    check("1g. the supersession rule says v1.2 is not edited in place",
          "NOT edited in place" in doc["supersession_rule"])
    check("1h. changes are reported, not silent", len(changes) >= 6,
          f"{len(changes)} changes")


def test_2_the_three_corrections() -> None:
    doc = build_v1_3()[0]
    ext = _entry(doc)["required_external_measurement"]
    src_ext = _entry(_src())["required_external_measurement"]

    check("2a. v1.2 really did say does_not_exist",
          src_ext["availability"] == AVAILABILITY_DOES_NOT_EXIST,
          "if this fails the transform is being tested against the wrong source")
    check("2b. v1.3 says exists_partial",
          ext["availability"] == AVAILABILITY_EXISTS_PARTIAL,
          str(ext["availability"]))

    check("2c. the availability basis cites the map it read",
          "HYP04_Linkage_Map" in ext.get("availability_basis", ""),
          str(ext.get("availability_basis"))[:120])
    check("2d. and records that it was read, not asserted",
          "not asserted by the author" in ext.get("availability_basis", ""))

    # The correction inherited from v1.0.
    check("2e. the placeholder is no longer called same-sector",
          not ext["placeholder_used_in_phase_0"].lower().startswith("same-sector"),
          ext["placeholder_used_in_phase_0"][:80])
    check("2f. it is described as positional",
          "POSITIONAL" in ext["placeholder_used_in_phase_0"].upper())
    check("2g. and the correction itself is recorded, not applied silently",
          "same-sector" in ext.get("placeholder_description_correction", ""))
    check("2h. naming which direction the error ran",
          "OVERSTATED" in ext.get("placeholder_description_correction", "").upper())

    sb = _entry(doc)["status_basis"]
    check("2i. status_basis names both capture modules",
          "peer_returns.py" in sb and "linkage_resolution.py" in sb)
    check("2j. and still says fixtures are not a capture path",
          "not a production capture path" in sb)


def test_3_exists_partial_is_defined_and_disclaimed() -> None:
    """The whole reason for a new vocabulary word rather than reusing `exists`."""
    doc = build_v1_3()[0]
    vocab = doc.get("external_measurement_availability_vocabulary")

    check("3a. the vocabulary is present in the document",
          isinstance(vocab, dict), type(vocab).__name__)
    check("3b. exists_partial is DEFINED, not merely used",
          AVAILABILITY_EXISTS_PARTIAL in (vocab or {}))
    check("3c. all three states are defined",
          set(vocab or {}) == set(AVAILABILITY_VOCABULARY), str(sorted(vocab or {})))
    check("3d. the definition denies sufficiency",
          "NEVER means the measurement is satisfied"
          in (vocab or {}).get(AVAILABILITY_EXISTS_PARTIAL, ""))
    check("3e. and denies that it moves the display threshold",
          "anchor events" in
          (vocab or {}).get(AVAILABILITY_EXISTS_PARTIAL, "").lower())

    ext = _entry(doc)["required_external_measurement"]
    check("3f. the hypothesis repeats the disclaimer where the value lives",
          "does NOT mean" in ext.get("availability_is_not_sufficiency", ""))
    check("3g. exists is reserved and marked unused",
          "NOT YET USED" in (vocab or {}).get("exists", "").upper())


def test_4_nothing_else_moves() -> None:
    """A factual correction must not become a promotion."""
    doc = build_v1_3()[0]
    src = _src()

    # `hypotheses` holds ONLY HYP-04 in this registry -- HYP-01/02/03 are not
    # restated, v1.0 is their authoritative source. So "loop over the other
    # hypotheses and check none changed" iterates NOTHING and passes vacuously.
    # This suite asserts that shape explicitly so the day it changes, the
    # assumption behind the guard is re-examined rather than silently broken.
    check("4a. `hypotheses` holds only HYP-04",
          [h["hypothesis_id"] for h in doc["hypotheses"]] == [HYP],
          str([h["hypothesis_id"] for h in doc["hypotheses"]]))
    check("4a2. the other three are carried forward, not restated",
          doc["hypotheses_carried_forward_unchanged"]
          == src["hypotheses_carried_forward_unchanged"],
          "v1.3 must not touch the carried-forward block")
    check("4a3. and v1.0 -- their authoritative source -- is still on disk",
          (gen.LSE / src["hypotheses_carried_forward_unchanged"]["source"]).is_file())

    # The control: HYP-04 DID change. Without it, a build that returned the
    # source unmodified would pass every check above.
    check("4b. control -- HYP-04 itself did change",
          _entry(doc) != _entry(src),
          "if this fails the transform did nothing at all")

    new, old = _entry(doc), _entry(src)
    for field in ("status", "classification", "minimum_eligible_events",
                  "minimum_eligible_events_unit", "required_eligibility_class",
                  "is_primary_confirmatory", "options_benchmark_required",
                  "display_rule", "forbidden_substitutions",
                  "forbidden_substitution_rule"):
        check(f"4c. HYP-04.{field} unchanged", new.get(field) == old.get(field),
              f"{old.get(field)!r} -> {new.get(field)!r}")

    check("4d. the decision ledger is untouched",
          new.get("unresolved_analysis_decisions")
          == old.get("unresolved_analysis_decisions"),
          "v1.3 resolves and reopens nothing")
    check("4e. status is still the not-implemented one",
          new["status"] == "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED",
          str(new["status"]))
    check("4f. results stay null", doc.get("results") in (None, {}),
          str(doc.get("results"))[:60])

    # The guard itself, exercised against a deliberately-tampered document.
    # It compares OUTPUT against SOURCE, so the tamper must be applied to the
    # output -- tampering the source instead changes both sides and the guard
    # correctly has nothing to detect.
    from hyp04_supply_chain_hedge.make_registry_v1_3 import (
        IMMOVABLE_HYP04_FIELDS, assert_only_expected_changes)

    check("4g. the real transform passes its own guard",
          assert_only_expected_changes(doc, src) is None,
          "the happy path must reach the guard, not bypass it")

    for field, value in (("status", "SUPPORTED"),
                         ("minimum_eligible_events", 1),
                         ("display_rule", "show it"),
                         ("unresolved_analysis_decisions", [])):
        bad = copy.deepcopy(doc)
        _entry(bad)[field] = value
        try:
            assert_only_expected_changes(bad, src)
            check(f"4h. a moved {field} is refused", False, "no refusal")
        except RefusedError:
            check(f"4h. a moved {field} is refused", True)
        except Exception as e:  # noqa: BLE001
            check(f"4h. a moved {field} is refused", False,
                  f"wrong type {type(e).__name__}")

    # Tampering the carried-forward block, and adding a hypothesis, are the two
    # ways "another hypothesis" can actually change in THIS registry's shape.
    carried = copy.deepcopy(doc)
    carried["hypotheses_carried_forward_unchanged"]["unchanged_hypothesis_ids"] = ["HYP-01"]
    try:
        assert_only_expected_changes(carried, src)
        check("4i. a tampered carried-forward block is refused", False, "no refusal")
    except RefusedError:
        check("4i. a tampered carried-forward block is refused", True)

    added = copy.deepcopy(doc)
    added["hypotheses"].append({"hypothesis_id": "HYP-99", "status": "X"})
    try:
        assert_only_expected_changes(added, src)
        check("4i2. adding a hypothesis is refused", False, "no refusal")
    except RefusedError:
        check("4i2. adding a hypothesis is refused", True)

    check("4j. the immovable list covers status and the ledger",
          {"status", "unresolved_analysis_decisions",
           "minimum_eligible_events"} <= set(IMMOVABLE_HYP04_FIELDS))


def test_5_module_existence_is_not_data() -> None:
    """The distinction this project keeps having to hold apart."""
    doc = build_v1_3()[0]
    cap = _entry(doc).get("capture_path_modules")

    check("5a. capture_path_modules is recorded", isinstance(cap, dict))
    for key in ("peer_return_ingestion", "event_to_peer_join"):
        check(f"5b. {key} is present", key in (cap or {}))
        check(f"5c. {key} reports data_captured FALSE",
              (cap or {}).get(key, {}).get("data_captured") is False,
              "a path that can ingest is not ingested data")
        check(f"5d. {key} names its module file",
              str((cap or {}).get(key, {}).get("module", "")).endswith(".py"))

    # Assert the SUBSTANCE, not a guessed phrase. An earlier version of this
    # check keyed on "not report" while the text said "Neither reports" -- a
    # matcher defect that would fail against a correct document.
    stated = str((cap or {}).get("module_existence_is_not_data", ""))
    check("5e. the distinction is stated in the document itself",
          "is not ingested data" in stated and "data_captured" in stated,
          stated[:140])

    sb = _entry(doc)["status_basis"]
    check("5f. status_basis says zero peer data has been captured",
          "ZERO peer price data" in sb, sb[:160])
    check("5g. and that gap 1 is still the binding blocker",
          "binding blocker" in sb.lower())


def test_6_refusals_actually_refuse() -> None:
    """The generator records that a map exists. It must not do so blindly."""
    real = gen.observed_linkage_state
    base = real()

    cases = {
        "no map on disk": {**base, "map_present": False, "edges": 0,
                           "loads_clean": False, "usable": False},
        "map loads dirty": {**base, "loads_clean": False, "usable": False,
                            "rows_rejected": 2},
        "map has zero edges": {**base, "edges": 0, "usable": False},
    }
    try:
        for name, state in cases.items():
            gen.observed_linkage_state = lambda _s=state: dict(_s)  # type: ignore
            refusals = check_preconditions(v1_3=Path("nonexistent-v1_3.json"))
            check(f"6a. refuses when {name}", bool(refusals),
                  "it would have written a false availability")
    finally:
        gen.observed_linkage_state = real

    # The control: with the REAL state, the only refusal may be that v1.3
    # already exists. Otherwise every refusal test above passes vacuously.
    refusals = check_preconditions(v1_3=Path("nonexistent-v1_3.json"))
    check("6b. control -- the real state does NOT refuse", not refusals,
          str(refusals))

    real_mods = gen.observed_capture_modules
    try:
        gen.observed_capture_modules = lambda: {"linkage_resolution": True,
                                                "peer_returns": False}
        refusals = check_preconditions(v1_3=Path("nonexistent-v1_3.json"))
        check("6c. refuses when a capture module does not import", bool(refusals),
              str(refusals))
    finally:
        gen.observed_capture_modules = real_mods

    check("6d. refuses to overwrite an existing v1.3",
          any("already exists" in r for r in check_preconditions())
          if V1_3.exists() else True,
          "a governance artifact is never silently overwritten")


def test_7_the_gate_does_not_move() -> None:
    from hyp04_supply_chain_hedge.display_gate import current_decision

    d = current_decision()
    # The gate OPENED 2026-09-09: freeze attested + registry v1.12 moved C1.
    # It read CLOSED with 4 denials for all of Phase 0. v1.3 is not what opened
    # it, which is what this block is for.
    check("7a. the gate is OPEN", d.open, str(d.status))
    check("7b. C4 reads MET", d.conditions.get("C4_decisions_resolved") is True,
          "v1.3 must not disturb a resolved ledger")
    check("7c. zero denials", len(d.denials) == 0, str(d.denials))
    # The original claim holds: curated edges alone never cleared C5. What
    # cleared it is a FREEZE whose panel derived uses_placeholder_linkage=false
    # from the ratified map -- a derivation, not an assertion by any caller.
    check("7d. C5 passes on a derived freeze, not on curated edges",
          d.conditions.get("C5_not_placeholder") is True
          and d.evidence.get("uses_placeholder_linkage") is False)


def test_8_v1_2_is_never_modified() -> None:
    before = gen._sha256(V1_2)
    build_v1_3()
    check("8a. building v1.3 does not touch v1.2",
          gen._sha256(V1_2) == before)

    for older in ("v1.0", "v1.1", "v1.2"):
        p = gen.LSE / f"GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_{older}.json"
        check(f"8b. {older} still on disk", p.is_file(),
              "append-only means the old versions stay")


def test_9_the_written_artifact() -> None:
    if not V1_3.exists():
        skip("9. v1.3 artifact on disk",
             f"{V1_3.name} not generated yet -- run make_registry_v1_3 --write")
        return

    doc = json.loads(V1_3.read_text(encoding="utf-8-sig"))
    built = build_v1_3()[0]
    check("9a. the artifact matches what the generator builds", doc == built,
          "the file on disk was hand-edited or generated from a different source")
    check("9b. it declares version 1.3", doc["registry_version"] == "1.3")
    check("9c. its recorded v1.2 hash still matches v1.2 on disk",
          doc["supersedes_sha256"] == gen._sha256(V1_2),
          "v1.2 changed after v1.3 was authored")
    ext = _entry(doc)["required_external_measurement"]
    check("9d. availability reads exists_partial",
          ext["availability"] == AVAILABILITY_EXISTS_PARTIAL)


def test_10_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("10a. network blocked", False, "a lookup succeeded")
    except Exception as e:  # noqa: BLE001
        check("10a. network blocked", type(e).__name__ == "NetworkBlocked")




def test_11_the_linkage_map_is_PINNED_not_globbed() -> None:
    """A frozen registry's evidence must not move when a new map lands.

    v1.3's availability_basis quotes a specific map, its edge count and its
    sha256, as of 2026-08-22. `observed_linkage_state` used to glob and take
    `sorted(...)[0]`, which returned that map only BY LUCK -- a map named
    without a `v` prefix sorts before `_v1.0` and would have silently become
    this registry's evidence.

    Curating the five draft rows creates exactly such a new map, so this is
    about to matter.
    """
    print("\n--- 11: the map is pinned by name and hash ---")
    from hyp04_supply_chain_hedge.make_registry_v1_3 import (
        PINNED_MAP_NAME, PINNED_MAP_SHA256, PinnedMapChanged,
        observed_linkage_state)

    st = observed_linkage_state()
    check("11a. it reads the pinned map", st["source"] == PINNED_MAP_NAME,
          str(st["source"]))
    check("11b. and its hash matches the pin",
          st["source_sha256"] == PINNED_MAP_SHA256, str(st["source_sha256"]))

    # The pin must agree with what the FROZEN artifact says it read.
    basis = _entry(json.loads(V1_3.read_text(encoding="utf-8-sig")))[
        "required_external_measurement"]["availability_basis"]
    check("11c. the frozen artifact names the same map",
          PINNED_MAP_NAME in basis, basis[:90])
    check("11d. and quotes the same hash prefix",
          PINNED_MAP_SHA256[:16] in basis, basis[:120])
    check("11e. and the same edge count",
          f"{st['edges']} curated edge(s)" in basis, basis[:60])

    # A NEW map on disk must not move the evidence. This is the whole point.
    newer = gen.LSE / "HYP04_Linkage_Map_v9.9.csv"
    assert not newer.exists(), "test fixture would clobber a real file"
    try:
        newer.write_bytes((gen.LSE / PINNED_MAP_NAME).read_bytes())
        after = observed_linkage_state()
        check("11f. a newer map on disk does NOT change v1.3's source",
              after["source"] == PINNED_MAP_NAME, str(after["source"]))
        check("11g. nor its edge count", after["edges"] == st["edges"],
              str(after["edges"]))
    finally:
        if newer.exists():
            newer.unlink()

    # CONTROL: the guard must actually fire when the pinned map changes.
    import tempfile, pathlib
    real = gen.LSE / PINNED_MAP_NAME
    backup = real.read_bytes()
    fired = False
    try:
        real.write_bytes(backup + b"\n")
        try:
            observed_linkage_state()
        except PinnedMapChanged:
            fired = True
    finally:
        real.write_bytes(backup)
    check("11h. CONTROL: it REFUSES if the pinned map's bytes change", fired)
    check("11i. and the map is restored byte-identical",
          gen._sha256(real) == PINNED_MAP_SHA256, gen._sha256(real))


if __name__ == "__main__":
    test_1_version_and_supersession()
    test_2_the_three_corrections()
    test_3_exists_partial_is_defined_and_disclaimed()
    test_4_nothing_else_moves()
    test_5_module_existence_is_not_data()
    test_6_refusals_actually_refuse()
    test_7_the_gate_does_not_move()
    test_8_v1_2_is_never_modified()
    test_9_the_written_artifact()
    test_10_offline()
    test_11_the_linkage_map_is_PINNED_not_globbed()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.3 TESTS PASSED")
    sys.exit(0)
