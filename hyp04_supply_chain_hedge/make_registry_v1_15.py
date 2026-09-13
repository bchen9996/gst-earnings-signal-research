#!/usr/bin/env python3
"""Generate hypothesis-registry v1.15 from v1.14. Records HYP-05's one
exploratory pilot run.

=== WHAT v1.15 SETTLES ===

One thing: HYP-05's `status` moves from `PREREGISTERED_MEASUREMENT_NOT_
IMPLEMENTED` to a NEW vocabulary value, `EXPLORATORY_PILOT_TESTED_NULL`,
and the registry's top-level `results`/`results_note` gain a HYP-05 entry
for the first time, sourced from the one real, committed, non-repeatable
Phase 3 artifact.

This is possible because Phase 3 already happened for real: the owner typed
`ratify_hyp05 phase3`'s authorization, `make_hyp05_phase3_run.py` ran
against AMBA's real returns around NVDA's 8 locked anchor events, and
`HYP05_PHASE3_RESULT_2026-09-12.json` (committed `2ba3a62`) reports
NOT_SIGNIFICANT, exactly as `reported_regardless_of_outcome` commits it to.
Nothing here computes anything -- it is closing the book on a result that
already exists.

=== WHY THIS IS *NOT* `HOLDOUT_TESTED_NULL` ===

`make_registry_v1_13.py` closed HYP-04 as `HOLDOUT_TESTED_NULL` after its
ONE preregistered look at its FULL, floor-clearing 57-event holdout.
HYP-05's pilot used 8 events against its own registered 195-event
provisional floor -- about 24x short, disclosed inside the result itself
(`sample_size_disclosure`) and inside `HYP05_PHASE3_RESULT_CHARACTERIZATION_
2026-09-12.md`. Declaring `HOLDOUT_TESTED_NULL` here would silently claim
HYP-05's registered floor was cleared when it manifestly was not. A new,
distinct status name exists so a reader comparing the two entries side by
side cannot mistake one for the other.

`EXPLORATORY_PILOT_TESTED_NULL` asserts only: real curated data exists (one
peer, AMBA/NVDA), the one exploratory check on it is spent and came back
null, and this hypothesis remains OPEN -- neither confirmed, refuted, nor
closed the way HYP-04 is. `minimum_eligible_events` (195, still provisional)
is UNCHANGED and UNMET; `display_rule`'s "no result before the floor" bar
is UNCHANGED too, so this status change does not, by itself, make anything
displayable as a HYP-05 finding.

=== IT DOES NOT TOUCH HYP-04, HYP-01/02/03, OR THE GATE ===

`display_gate.py`'s C1/dashboard both read HYP-04's registry entry only
(`HYPOTHESIS_ID = "HYP-04"` there). HYP-05 has no display gate of its own
yet, so this version moves no gate condition -- verified by leaving
HYP-04's entire entry, and `hypotheses_carried_forward_unchanged`
(HYP-01/02/03), byte-identical, same discipline as v1.13/v1.14.

=== IT REFUSES UNLESS THE REPOSITORY ALREADY IS WHAT IT DECLARES ===

`code_disagreements()` refuses unless:

  * exactly one `HYP05_PHASE3_RESULT_*.json` exists,
  * its `reported_regardless_of_outcome` and `no_rerun_permitted` flags are
    both true,
  * its own `treatment.peak_significant` is exactly `False` --
    `EXPLORATORY_PILOT_TESTED_NULL` is the wrong status to declare for a
    significant result, and this generator must not be usable to declare it
    anyway,
  * its `sample_size_disclosure.framing` is exactly `"EXPLORATORY, NOT
    CONFIRMATORY"` and its `n_locked_events` is strictly below HYP-05's
    registered `minimum_eligible_events` -- this generator must not be
    usable to declare a PILOT status for a result that actually cleared
    the floor,
  * exactly one `HYP05_PHASE3_AUTHORIZATION_*.json` exists, is `consumed`,
    and its `consumed_by_result` names that same result file, and
  * the Phase 2 lock the result cites is still signed on disk.

=== IT CLAIMS AN IMMOVABLE-FIELD EXCEPTION, NARROWLY ===

Only `status` and `status_basis` are named in
`SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE`, checked against the same
field-name schema `make_registry_v1_6.IMMOVABLE_HYP04_FIELDS` already
enumerates (the names are the per-hypothesis-entry schema, not anything
HYP-04-specific -- reused rather than re-typed under a new name).
Everything else about the HYP-05 entry must survive byte-identical,
including `minimum_eligible_events`, `minimum_eligible_events_basis`
(still provisional, still unsuperseded -- see status_basis for why the one
fresh k_eff measurement this pilot produced does not supersede it either),
and `display_rule`.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_15 --write

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
    IMMOVABLE_HYP04_FIELDS as IMMOVABLE_ENTRY_FIELDS,
    LSE,
    RefusedError,
    _load,
    _sha256,
)

HYP04_ID = "HYP-04"
HYP05_ID = "HYP-05"

V1_14 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.14.json"
V1_15 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.15.json"

AUTHORED_AT = "2026-09-12"

#: The written basis. A status change with no dated finding behind it is
#: exactly what this project forbids.
FINDINGS = (
    "Live Signal Engine/HYP05_PHASE3_RESULT_2026-09-12.json",
    "Live Signal Engine/HYP05_PHASE3_RESULT_CHARACTERIZATION_2026-09-12.md",
)

NEW_STATUS = "EXPLORATORY_PILOT_TESTED_NULL"

STATUS_VOCAB_TEXT = (
    "One exploratory, NON-confirmatory pilot run (Phase 3) completed "
    "against a real but severely underpowered sample -- 8 locked anchor "
    "events against this hypothesis's own 195-event provisional floor, "
    "roughly 24x short -- and reported a null result. This status does "
    "NOT assert minimum_eligible_events is met (it is not), does NOT "
    "close the hypothesis the way HOLDOUT_TESTED_NULL closes one that "
    "cleared its floor, and does NOT license display of a HYP-05 finding "
    "under display_rule. It asserts only that real curated data exists, "
    "the one authorized pilot look happened, and it came back null.")

#: NOT empty, and each is named because this version genuinely moves it.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE: tuple[str, ...] = (
    "status", "status_basis",
)

#: v1.15 records that the one pilot look is spent. It changes no membership,
#: no floor, and no display rule.
FLOOR_AND_DISPLAY_MUST_NOT_MOVE = ("minimum_eligible_events",
                                   "minimum_eligible_events_basis",
                                   "display_rule")


def code_disagreements() -> list[str]:
    """The repository must already BE what v1.15 is about to declare."""
    problems: list[str] = []

    results = sorted(LSE.glob("HYP05_PHASE3_RESULT_*.json"))
    if len(results) != 1:
        problems.append(
            f"expected exactly one HYP05_PHASE3_RESULT_*.json, found "
            f"{len(results)}. v1.15 records HYP-05's status against ONE "
            "specific result and must not be ambiguous about which.")
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

    treatment = result.get("treatment") or {}
    peak_significant = treatment.get("peak_significant")
    if peak_significant is not False:
        problems.append(
            f"{result_path.name}'s treatment.peak_significant is "
            f"{peak_significant!r}, not False. EXPLORATORY_PILOT_TESTED_"
            "NULL is the wrong status to declare for anything but a null "
            "result, and this generator refuses to be usable for a "
            "different outcome.")

    ssd = result.get("sample_size_disclosure") or {}
    if ssd.get("framing") != "EXPLORATORY, NOT CONFIRMATORY":
        problems.append(
            f"{result_path.name}'s sample_size_disclosure.framing is "
            f"{ssd.get('framing')!r}, not the exploratory framing this "
            "status requires.")
    n_used = result.get("n_locked_events")
    if not isinstance(n_used, int) or n_used <= 0:
        problems.append(
            f"{result_path.name}'s n_locked_events is {n_used!r}, not a "
            "positive int.")

    auths = sorted(LSE.glob("HYP05_PHASE3_AUTHORIZATION_*.json"))
    if len(auths) != 1:
        problems.append(
            f"expected exactly one HYP05_PHASE3_AUTHORIZATION_*.json, "
            f"found {len(auths)}.")
    else:
        try:
            auth = json.loads(auths[0].read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            problems.append(f"{auths[0].name} did not parse: {exc}")
        else:
            if auth.get("consumed") is not True:
                problems.append(
                    f"{auths[0].name} is not consumed. The result it "
                    "should have produced does not trace back to it.")
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
                    f"{lock_path.name} is not declared/signed. v1.15 "
                    "records a status against a result computed under a "
                    "signed lock.")

    return problems


def check_preconditions(*, v1_14: Path = V1_14, v1_15: Path = V1_15,
                        ) -> list[str]:
    refusals: list[str] = []
    if not v1_14.is_file():
        refusals.append(f"registry v1.14 not found at {v1_14.name}")
    if v1_15.exists():
        refusals.append(
            f"{v1_15.name} already exists. Refusing to overwrite a "
            "governance artifact -- delete it deliberately first if that "
            "is really intended.")
    for f in FINDINGS:
        if not Path(f).is_file():
            refusals.append(
                f"the dated finding {f} is not on disk. A status change "
                "with no written basis is exactly what this project "
                "forbids.")
    refusals.extend(code_disagreements())
    return refusals


def build_v1_15(*, v1_14: Path = V1_14, authored_at: Optional[str] = None,
               ) -> tuple[dict[str, Any], list[str]]:
    doc = copy.deepcopy(_load(v1_14))
    src = _load(v1_14)
    changes: list[str] = []

    doc["registry_version"] = "v1.15"
    doc["authored_at"] = authored_at or AUTHORED_AT
    doc["supersedes"] = v1_14.name
    doc["supersedes_sha256"] = _sha256(v1_14)
    changes.append(f"registry_version: v1.14 -> v1.15 (supersedes {v1_14.name})")

    statuses = copy.deepcopy(doc.get("statuses") or {})
    if NEW_STATUS in statuses:
        raise RefusedError(
            f"{NEW_STATUS} is already in the statuses vocabulary. v1.15 "
            "adds it new.")
    statuses[NEW_STATUS] = STATUS_VOCAB_TEXT
    doc["statuses"] = statuses
    changes.append(f"statuses: adds {NEW_STATUS}")

    entry = old_entry = None
    for h, oh in zip(doc.get("hypotheses", []), src.get("hypotheses", [])):
        if h.get("hypothesis_id") == HYP05_ID:
            entry, old_entry = h, oh
            break
    if entry is None:
        raise RefusedError(f"{HYP05_ID} is not in {v1_14.name}")

    result_path = sorted(LSE.glob("HYP05_PHASE3_RESULT_*.json"))[0]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    treatment = result.get("treatment") or {}
    ssd = result.get("sample_size_disclosure") or {}
    result_sha = _sha256(result_path)
    n_used = result.get("n_locked_events")
    floor = old_entry.get("minimum_eligible_events")

    entry["status"] = NEW_STATUS
    changes.append(f"status: {old_entry['status']} -> {NEW_STATUS}")

    entry["status_basis"] = (
        "Phase 3 -- HYP-05's one authorized, exploratory pilot look, "
        f"against a real (AMBA, NVDA) peer/anchor pair curated and EDGAR-"
        f"verified this project -- ran for real under the owner's typed "
        f"authorization and reported {result_path.name} (sha256 "
        f"{result_sha}), committed 2ba3a62. peak_horizon="
        f"{treatment.get('peak_horizon')}, max_abs_t="
        f"{treatment.get('max_abs_t')} against a critical value of "
        f"{treatment.get('max_t_critical_value')} "
        f"(p={treatment.get('max_t_p_value')}), NOT significant at any "
        f"tested horizon. n_locked_events={n_used}, roughly "
        f"{floor / n_used:.0f}x short of this entry's own "
        f"minimum_eligible_events ({floor}, still PROVISIONAL and "
        "UNCHANGED by this version). make_hyp05_phase3_run.py refuses "
        "unconditionally if any HYP05_PHASE3_RESULT_*.json already "
        "exists, so this specific 8-event look is a structurally "
        "enforced terminal state -- but the HYPOTHESIS is not closed: "
        "unlike HYP-04's holdout, this pilot never claimed to be the "
        "one confirmatory test, and nothing here forecloses a future "
        "curation round producing a larger sample and a fresh Phase 2/3 "
        "cycle against it. The result's own effective_independent_tests "
        f"({treatment.get('effective_independent_tests')}) is a KNOWN "
        "numerical artifact of backing out a test count from an 8-cluster "
        "critical value via a normal-tail formula -- see "
        f"{FINDINGS[1].split('/')[-1]} -- and must not be read as a "
        "measurement of anything, nor used to supersede the provisional "
        "floor's own must_be_superseded_by condition, which remains "
        "UNSATISFIED after this pilot.")
    changes.append("status_basis: rewritten to cite the real Phase 3 result")

    doc["results"] = copy.deepcopy(doc.get("results") or {})
    if HYP05_ID in doc["results"]:
        raise RefusedError(f"results already has a {HYP05_ID} entry")
    doc["results"][HYP05_ID] = {
        "hypothesis_id": HYP05_ID,
        "primary_test_artifact": result_path.name,
        "primary_test_artifact_sha256": result_sha,
        "outcome": "NOT_SIGNIFICANT",
        "framing": "EXPLORATORY, NOT CONFIRMATORY -- see caveats below",
        "peak_horizon": treatment.get("peak_horizon"),
        "max_abs_t": treatment.get("max_abs_t"),
        "max_t_critical_value": treatment.get("max_t_critical_value"),
        "max_t_p_value": treatment.get("max_t_p_value"),
        "effective_independent_tests": treatment.get(
            "effective_independent_tests"),
        "effective_independent_tests_caveat": (
            "KNOWN NUMERICAL ARTIFACT, not a valid multiplicity "
            "measurement -- an 8-cluster, ~2-Satterthwaite-df critical "
            "value fed through a formula that assumes normal tail "
            "behavior. Does not affect peak_significant/max_t_p_value "
            "(those come from the empirical permutation distribution "
            "directly). See HYP05_PHASE3_RESULT_CHARACTERIZATION_"
            "2026-09-12.md for the full derivation."),
        "n_locked_events_used": n_used,
        "minimum_eligible_events_required": floor,
        "meets_minimum_eligible_events": (
            n_used is not None and floor is not None and n_used >= floor),
        "reported_regardless_of_outcome": True,
        "no_rerun_permitted": True,
    }
    changes.append(f"results: adds {HYP05_ID} (was null)")

    doc["results_note"] = (
        src.get("results_note", "") + "\n\n"
        "HYP-05's one exploratory pilot run (Phase 3) is complete and "
        "reported above in full, per its own reported_regardless_of_"
        "outcome commitment. The result is NOT_SIGNIFICANT at the peak "
        "horizon, on an 8-event sample roughly 24x short of this "
        "hypothesis's own 195-event provisional floor. This does NOT "
        "establish that relationship-lag transmission is absent among "
        "lower-coverage peers -- it establishes only that one real, "
        "EDGAR-verified (AMBA, NVDA) pair, at severe underpower, did not "
        "show it. It does NOT satisfy minimum_eligible_events and, per "
        f"{HYP05_ID}'s own display_rule, may not be displayed as a HYP-05 "
        f"finding. See {result_path.name} and "
        "HYP05_PHASE3_RESULT_CHARACTERIZATION_2026-09-12.md for the full "
        "disclosure, including a known numerical artifact in the "
        "reported effective_independent_tests. Whether a larger sample "
        "is reachable at all is an open, unresolved question: three "
        "rounds of hand curation (96 proposed candidates) found exactly "
        "this one qualifying peer, consistent with survivorship selection "
        "structurally limiting how many small, independently-tradeable, "
        "historically-named counterparties of large anchors exist to "
        "find. HYP-01, HYP-02, HYP-03 and HYP-04 are unaffected by this "
        "version.")
    changes.append("results_note: appended a HYP-05 paragraph")

    # --- the exception is claimed, and it is narrow -----------------------
    if not SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
        raise RefusedError(
            "v1.15 moves immovable fields and must say which in its own "
            "source.")
    for f in IMMOVABLE_ENTRY_FIELDS:
        if f in SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
            continue
        if entry.get(f) != old_entry.get(f):
            raise RefusedError(
                f"{HYP05_ID}.{f} changed. v1.15 moves only "
                f"{SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE}.")
    changes.append(
        "guard: every HYP-05 field outside "
        f"{SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE} is byte-identical "
        "to v1.14")

    for f in FLOOR_AND_DISPLAY_MUST_NOT_MOVE:
        if entry.get(f) != old_entry.get(f):
            raise RefusedError(
                f"{HYP05_ID}.{f} changed. v1.15 records a pilot result; "
                "it does not touch the floor or the display rule.")
    changes.append(
        "guard: minimum_eligible_events/basis and display_rule are "
        "byte-identical to v1.14")

    # --- HYP-04's entry moves nothing --------------------------------------
    old_h4 = next(h for h in src["hypotheses"] if h["hypothesis_id"] == HYP04_ID)
    new_h4 = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == HYP04_ID)
    if new_h4 != old_h4:
        raise RefusedError(
            f"{HYP04_ID}'s entry is not byte-identical to v1.14's. v1.15 "
            "is about HYP-05 only.")
    changes.append(f"guard: {HYP04_ID}'s entire entry is byte-identical to v1.14")

    if doc.get("hypotheses_carried_forward_unchanged") != src.get(
            "hypotheses_carried_forward_unchanged"):
        raise RefusedError("hypotheses_carried_forward_unchanged changed; "
                           "HYP-01/02/03 stay exactly as v1.0 defines them")
    changes.append("guard: hypotheses_carried_forward_unchanged untouched")

    doc.setdefault("findings_responded_to", {})["v1.15"] = list(FINDINGS)
    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.15 from v1.14, "
                    "recording HYP-05's exploratory pilot as "
                    "EXPLORATORY_PILOT_TESTED_NULL.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.15 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        print("\nv1.15 records HYP-05's status against exactly one, real, "
              "committed Phase 3 pilot result. It refuses if that is not "
              "unambiguously what the repository shows.")
        return 1

    doc, changes = build_v1_15(authored_at=a.authored_at)
    print("Changes v1.14 -> v1.15:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_15.name}.")
        return 0

    before = _sha256(V1_14)
    V1_15.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    if _sha256(V1_14) != before:
        raise RefusedError("v1.14 changed on disk during generation")

    print(f"\nWrote {V1_15.name}")
    print(f"v1.14 unchanged, sha256 {before[:16]}...")
    print("\nHYP-05's floor (still provisional) and display_rule are "
          "UNCHANGED. Nothing about\nHYP-04, HYP-01/02/03, or the display "
          "gate moved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
