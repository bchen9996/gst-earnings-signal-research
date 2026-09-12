#!/usr/bin/env python3
"""Generate hypothesis-registry v1.13 from v1.12. Closes HYP-04.

=== WHAT v1.13 SETTLES ===

One thing: HYP-04's `status` moves from `ACTIVE_COLLECTING` to a NEW
vocabulary value, `HOLDOUT_TESTED_NULL`, and the registry's top-level
`results`/`results_note` (deliberately null since this registry began) are
filled in for the first time, sourced from the one real, committed,
non-repeatable Phase 3 artifact.

This is possible because Phase 3 already happened for real: the owner typed
`ratify phase3`'s authorization, `make_phase3_run.py` ran against the actual
57-event holdout, and `HYP04_PHASE3_RESULT_2026-09-11.json` (committed
`4c7ae32`) reports NOT_SIGNIFICANT at every tested horizon, exactly as
`reported_regardless_of_outcome` commits it to. Nothing here computes
anything -- it is closing the book on a result that already exists.

=== C1 MOVING NOW CLOSES THE GATE, AND THAT IS CORRECT, NOT A REGRESSION ===

`display_gate.py`'s C1 checks `status == "ACTIVE_COLLECTING"` literally.
`HOLDOUT_TESTED_NULL` is not that string, so C1 denies and the gate that has
read OPEN since 2026-09-09 will read CLOSED (1 denial) once this is written
and the gate is repointed at it. That is the intended effect, not a bug:
the display gate exists to govern whether a NOT-YET-COMPUTED result may be
looked at. HYP-04 has no such result pending -- the one permitted look
already happened, is already reported, and `make_phase3_run.py` refuses
unconditionally if any `HYP04_PHASE3_RESULT_*.json` already exists,
independent of anything the registry says. The gate closing is the registry
catching up to a fact the code already enforces structurally.

=== IT REFUSES UNLESS THE REPOSITORY ALREADY IS WHAT IT DECLARES ===

`code_disagreements()` refuses unless:

  * exactly one `HYP04_PHASE3_RESULT_*.json` exists,
  * its `reported_regardless_of_outcome` and `no_rerun_permitted` flags are
    both true (it really is shaped like the one committed result artifact),
  * its own `peak_significant` is exactly `False` -- HOLDOUT_TESTED_NULL is
    the wrong status to declare for a significant result, and this
    generator must not be usable to declare it anyway,
  * exactly one `HYP04_PHASE3_AUTHORIZATION_*.json` exists, is `consumed`,
    and its `consumed_by_result` names that same result file, and
  * the Phase 2 lock the result cites is still signed on disk.

=== IT CLAIMS AN IMMOVABLE-FIELD EXCEPTION, NARROWLY ===

Only `status` and `status_basis` are named in
`SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE`. `results`/`results_note` are
top-level document fields, not per-hypothesis ones, and are not in
`IMMOVABLE_HYP04_FIELDS` at all -- there is nothing to except them from.
Everything else about the HYP-04 entry (universe, floor, decision ledger,
display_rule) must survive byte-identical, same discipline as v1.12.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_13 --write

Named off the `test_*` pattern deliberately: this writes a governance
artifact and must only ever run when a human decides it should.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Optional

from hyp04_supply_chain_hedge.make_registry_v1_6 import (
    HYPOTHESIS_ID,
    IMMOVABLE_HYP04_FIELDS,
    LSE,
    RefusedError,
    _load,
    _sha256,
)

V1_12 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.12.json"
V1_13 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.13.json"

AUTHORED_AT = "2026-09-11"

#: The written basis. A status change with no dated finding behind it is
#: exactly what this project forbids.
FINDINGS = (
    "Live Signal Engine/HYP04_PHASE3_RESULT_2026-09-11.json",
)

NEW_STATUS = "HOLDOUT_TESTED_NULL"

STATUS_VOCAB_TEXT = (
    "The one preregistered holdout run (Phase 3) completed and reported a "
    "null result at the locked significance bar. No further run against "
    "this holdout is possible; the hypothesis is closed as tested, not "
    "confirmed.")

#: NOT empty, and each is named because this version genuinely moves it.
#: `results`/`results_note` are top-level document fields, not per-hypothesis
#: ones -- they are not in IMMOVABLE_HYP04_FIELDS and need no exception here.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE: tuple[str, ...] = (
    "status", "status_basis",
)

#: v1.13 records that the one holdout look is spent. It changes no membership.
UNIVERSE_MUST_NOT_MOVE = True


def _newest(pattern: str) -> Optional[Path]:
    hits = sorted(LSE.glob(pattern))
    return hits[-1] if hits else None


def code_disagreements() -> list[str]:
    """The repository must already BE what v1.13 is about to declare."""
    problems: list[str] = []

    results = sorted(LSE.glob("HYP04_PHASE3_RESULT_*.json"))
    if len(results) != 1:
        problems.append(
            f"expected exactly one HYP04_PHASE3_RESULT_*.json, found "
            f"{len(results)}. v1.13 closes HYP-04 against ONE specific "
            "result and must not be ambiguous about which.")
        return problems
    result_path = results[0]
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        problems.append(f"{result_path.name} did not parse: {exc}")
        return problems

    if result.get("reported_regardless_of_outcome") is not True:
        problems.append(
            f"{result_path.name} does not carry "
            "reported_regardless_of_outcome=true -- it is not shaped like "
            "the one committed Phase 3 result artifact.")
    if result.get("no_rerun_permitted") is not True:
        problems.append(
            f"{result_path.name} does not carry no_rerun_permitted=true.")

    peak_significant = (result.get("treatment") or {}).get("peak_significant")
    if peak_significant is not False:
        problems.append(
            f"{result_path.name}'s peak_significant is {peak_significant!r}, "
            "not False. HOLDOUT_TESTED_NULL is the wrong status to declare "
            "for anything but a null result, and this generator refuses to "
            "be usable for a different outcome.")

    auths = sorted(LSE.glob("HYP04_PHASE3_AUTHORIZATION_*.json"))
    if len(auths) != 1:
        problems.append(
            f"expected exactly one HYP04_PHASE3_AUTHORIZATION_*.json, found "
            f"{len(auths)}.")
    else:
        try:
            auth = json.loads(auths[0].read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            problems.append(f"{auths[0].name} did not parse: {exc}")
        else:
            if auth.get("consumed") is not True:
                problems.append(
                    f"{auths[0].name} is not consumed. The result it should "
                    "have produced does not trace back to it.")
            if auth.get("consumed_by_result") != result_path.name:
                problems.append(
                    f"{auths[0].name}.consumed_by_result "
                    f"({auth.get('consumed_by_result')!r}) does not name "
                    f"{result_path.name!r}.")

    lock_name = (result.get("phase2_lock") or {}).get("artifact")
    lock_path = LSE / lock_name if lock_name else None
    if lock_path is None or not lock_path.is_file():
        problems.append(
            f"{result_path.name} names a Phase 2 lock ({lock_name!r}) that "
            "is not on disk.")
    else:
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            problems.append(f"{lock_path.name} did not parse: {exc}")
        else:
            if lock.get("declared") is not True:
                problems.append(
                    f"{lock_path.name} is not declared/signed. v1.13 closes "
                    "HYP-04 against a result computed under a signed lock.")

    return problems


def check_preconditions(*, v1_12: Path = V1_12, v1_13: Path = V1_13,
                        ) -> list[str]:
    refusals: list[str] = []
    if not v1_12.is_file():
        refusals.append(f"registry v1.12 not found at {v1_12.name}")
    if v1_13.exists():
        refusals.append(
            f"{v1_13.name} already exists. Refusing to overwrite a "
            "governance artifact -- delete it deliberately first if that is "
            "really intended.")
    for f in FINDINGS:
        if not Path(f).is_file():
            refusals.append(
                f"the dated finding {f} is not on disk. A status change "
                "with no written basis is exactly what this project "
                "forbids.")
    refusals.extend(code_disagreements())
    return refusals


def build_v1_13(*, v1_12: Path = V1_12, authored_at: Optional[str] = None,
                ) -> tuple[dict[str, Any], list[str]]:
    doc = copy.deepcopy(_load(v1_12))
    src = _load(v1_12)
    changes: list[str] = []

    doc["registry_version"] = "v1.13"
    doc["authored_at"] = authored_at or AUTHORED_AT
    doc["supersedes"] = v1_12.name
    doc["supersedes_sha256"] = _sha256(v1_12)
    changes.append(f"registry_version: v1.12 -> v1.13 (supersedes {v1_12.name})")

    statuses = copy.deepcopy(doc.get("statuses") or {})
    if NEW_STATUS in statuses:
        raise RefusedError(
            f"{NEW_STATUS} is already in the statuses vocabulary. v1.13 "
            "adds it new.")
    statuses[NEW_STATUS] = STATUS_VOCAB_TEXT
    doc["statuses"] = statuses
    changes.append(f"statuses: adds {NEW_STATUS}")

    entry = None
    old_entry = None
    for h, oh in zip(doc.get("hypotheses", []), src.get("hypotheses", [])):
        if h.get("hypothesis_id") == HYPOTHESIS_ID:
            entry, old_entry = h, oh
            break
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not in {v1_12.name}")

    result_path = sorted(LSE.glob("HYP04_PHASE3_RESULT_*.json"))[0]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    treatment = result.get("treatment") or {}
    result_sha = _sha256(result_path)

    entry["status"] = NEW_STATUS
    changes.append(f"status: {old_entry['status']} -> {NEW_STATUS}")

    entry["status_basis"] = (
        "Phase 3 -- the one preregistered look against HYP-04's frozen "
        "57-event holdout -- ran for real under the owner's typed "
        f"authorization and reported {result_path.name} (sha256 "
        f"{result_sha}), committed 4c7ae32. peak_horizon="
        f"{treatment.get('peak_horizon')}, max_abs_t="
        f"{treatment.get('max_abs_t')} against a critical value of "
        f"{treatment.get('max_t_critical_value')} "
        f"(p={treatment.get('max_t_p_value')}), NOT significant at any of "
        "20 tested horizons. make_phase3_run.py refuses unconditionally if "
        "any HYP04_PHASE3_RESULT_*.json already exists, so this is a "
        "structurally enforced terminal state, not a policy that could be "
        "revised. HOLDOUT_TESTED_NULL asserts that this one look happened "
        "and came back null -- it asserts NOTHING about whether "
        "supply-chain earnings information diffuses slowly in general, "
        "only about this specific construction.")
    changes.append("status_basis: rewritten to cite the real Phase 3 result")

    doc["results"] = copy.deepcopy(doc.get("results") or {})
    if not isinstance(doc["results"], dict):
        doc["results"] = {}
    if HYPOTHESIS_ID in doc["results"]:
        raise RefusedError(f"results already has a {HYPOTHESIS_ID} entry")
    doc["results"][HYPOTHESIS_ID] = {
        "hypothesis_id": HYPOTHESIS_ID,
        "primary_test_artifact": result_path.name,
        "primary_test_artifact_sha256": result_sha,
        "outcome": "NOT_SIGNIFICANT",
        "peak_horizon": treatment.get("peak_horizon"),
        "max_abs_t": treatment.get("max_abs_t"),
        "max_t_critical_value": treatment.get("max_t_critical_value"),
        "max_t_p_value": treatment.get("max_t_p_value"),
        "effective_independent_tests": treatment.get(
            "effective_independent_tests"),
        "n_holdout_events_used": result.get("n_holdout_events_used"),
        "reported_regardless_of_outcome": True,
        "no_rerun_permitted": True,
    }
    changes.append(f"results: adds {HYPOTHESIS_ID} (was null)")

    doc["results_note"] = (
        "HYP-04's one preregistered holdout run (Phase 3) is complete and "
        "reported above in full, per its own reported_regardless_of_outcome "
        "commitment. The result is NOT_SIGNIFICANT at every tested horizon. "
        "It does NOT establish that supply-chain earnings information never "
        "diffuses slowly -- it establishes only that this specific "
        "construction (four large, analyst-covered anchors; six large, "
        "analyst-covered peers; a two-feature linear model; one-way "
        "calendar_period clustering) did not detect a significant effect. "
        f"See {result_path.name} for the full disclosure. HYP-01, HYP-02 "
        "and HYP-03's results remain entirely out of this registry's scope "
        "(see hypotheses_carried_forward_unchanged) and are unaffected. No "
        "further result may ever be added for HYP-04: make_phase3_run.py "
        "structurally refuses if any HYP04_PHASE3_RESULT_*.json already "
        "exists, so this is enforced by the code that would have to run to "
        "produce a second one, not by a policy that could be revised.")
    changes.append("results_note: rewritten (was the deliberately-null note)")

    # --- the exception is claimed, and it is narrow -----------------------
    if not SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
        raise RefusedError(
            "v1.13 moves immovable fields and must say which in its own "
            "source.")
    for f in IMMOVABLE_HYP04_FIELDS:
        if f in SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
            continue
        if entry.get(f) != old_entry.get(f):
            raise RefusedError(
                f"{HYPOTHESIS_ID}.{f} changed. v1.13 moves only "
                f"{SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE}.")
    changes.append(
        "guard: every immovable field outside "
        f"{SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE} is byte-identical to "
        "v1.12")

    if UNIVERSE_MUST_NOT_MOVE and entry.get("anchor_universe") != old_entry.get(
            "anchor_universe"):
        raise RefusedError(
            "the anchor_universe block changed. v1.13 closes a STATUS; "
            "membership is unchanged and must survive byte-identical.")
    changes.append("guard: the anchor universe is byte-identical to v1.12")

    if entry.get("display_rule") != old_entry.get("display_rule"):
        raise RefusedError("display_rule changed. v1.13 does not relax it.")
    changes.append("guard: display_rule is byte-identical to v1.12")

    doc.setdefault("findings_responded_to", {})["v1.13"] = list(FINDINGS)
    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.13 from v1.12, closing "
                    "HYP-04 as HOLDOUT_TESTED_NULL.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.13 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        print("\nv1.13 closes HYP-04 against exactly one, real, committed "
              "Phase 3 result. It refuses if that is not unambiguously what "
              "the repository shows.")
        return 1

    doc, changes = build_v1_13(authored_at=a.authored_at)
    print("Changes v1.12 -> v1.13:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_13.name}.")
        return 0

    before = _sha256(V1_12)
    V1_13.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    if _sha256(V1_12) != before:
        raise RefusedError("v1.12 changed on disk during generation")

    print(f"\nWrote {V1_13.name}")
    print(f"v1.12 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nAfter repointing, C1 DENIES (status is no longer "
          "ACTIVE_COLLECTING) and the gate reads CLOSED, 1 denial. That is "
          "correct: HYP-04 has no pending result for the gate to protect --"
          " the one permitted look already happened and is already "
          "reported.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
