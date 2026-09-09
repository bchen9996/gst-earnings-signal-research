#!/usr/bin/env python3
"""Generate hypothesis-registry v1.12 from v1.11. C1 ONLY.

=== WHAT v1.12 SETTLES ===

One thing: `status` moves from `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` to
`ACTIVE_COLLECTING`, which is gate condition C1.

v1.11 named the precondition itself, in its own source:

    "it does NOT move `status` to ACTIVE_COLLECTING. That vocabulary requires
     a production capture path with `data_captured` true, and while closes now
     exist there is still no module that assembles them into the panel the
     estimator consumes -- so claiming it would be declaring a path the
     repository does not have. C1 IS A LATER VERSION'S TO MOVE, ONCE THAT
     ASSEMBLER EXISTS."

`make_event_panel` is that assembler. This is that later version.

=== IT REFUSES TO RUN OUT OF ORDER, AND THAT IS THE POINT ===

C1 is the LAST condition to move, not the first. If `status` went first, C1
would clear while C3 was still open, leaving the gate a single file away from
open with no freeze behind it -- and the freeze is the step that fixes the
event set before anyone looks at an outcome.

So `code_disagreements` refuses unless BOTH already hold:

  * every curated edge contributing an eligible event is `reviewed`, and
  * a freeze draft on disk passes `make_freeze_draft.validate_freeze`.

Run today, it refuses on both. That is correct: neither has happened.

=== IT CLAIMS AN IMMOVABLE-FIELD EXCEPTION, NARROWLY ===

`status`, `status_basis` and `capture_path_modules` are all in
`IMMOVABLE_HYP04_FIELDS`. v1.12 names exactly those three in
`SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` and the guard runs unweakened over
every other one. No membership moves: the anchor universe, the eligibility
class, the floor and the decision ledger must all survive byte-identical.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_12 --write

Named off the `test_*` pattern deliberately: this writes a governance artifact
and must only ever run when a human decides it should.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Optional

from hyp04_supply_chain_hedge.artifacts import newest_in
from hyp04_supply_chain_hedge.make_registry_v1_6 import (
    HYPOTHESIS_ID,
    IMMOVABLE_HYP04_FIELDS,
    LSE,
    RefusedError,
    _load,
    _sha256,
)

V1_11 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.11.json"
V1_12 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.12.json"

AUTHORED_AT = "2026-09-08"

#: The written basis. A status change with no dated finding behind it is
#: exactly what this project forbids.
FINDINGS = (
    "Live Signal Engine/HYP04_EVENT_PANEL_FINDING_2026-09-08.md",
    "Live Signal Engine/HYP04_FREEZE_MACHINERY_FINDING_2026-09-08.md",
)

NEW_STATUS = "ACTIVE_COLLECTING"

#: NOT empty, and each is named because this version genuinely moves it.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE: tuple[str, ...] = (
    "status", "status_basis", "capture_path_modules",
)

#: v1.12 records that a capture path now carries data. It changes no membership.
UNIVERSE_MUST_NOT_MOVE = True


def _panel() -> tuple[Optional[Path], dict[str, Any]]:
    p = newest_in(LSE, "HYP04_EVENT_PANEL_*.json")
    if p is None:
        return None, {}
    return Path(p), json.loads(Path(p).read_text(encoding="utf-8"))


def code_disagreements() -> list[str]:
    """The repository must already BE what v1.12 is about to declare."""
    problems: list[str] = []

    # --- 1. the assembler v1.11 named as the precondition ------------------
    try:
        from hyp04_supply_chain_hedge import make_event_panel  # noqa: F401
        from hyp04_supply_chain_hedge import make_freeze_draft
    except ImportError as exc:
        problems.append(
            f"the panel assembler or freeze machinery does not import ({exc}). "
            "v1.11 made the assembler's existence the precondition for moving "
            "C1; a status of ACTIVE_COLLECTING would name a path the "
            "repository does not have.")
        return problems

    # --- 2. a derived count that clears the registered floor ---------------
    path, panel = _panel()
    if path is None:
        problems.append(
            "no event-panel artifact on disk. ACTIVE_COLLECTING asserts data "
            "has flowed through a capture path; nothing here shows it did.")
        return problems
    per_pair = panel.get("per_pair") or {}
    count = per_pair.get("eligible_anchor_events")
    floor = panel.get("registered_floor")
    if not isinstance(count, int) or not isinstance(floor, int):
        problems.append(f"{path.name} carries no integer count and floor.")
    elif count < floor:
        problems.append(
            f"{path.name} derives {count} eligible events, below the floor of "
            f"{floor}.")
    prov = panel.get("linkage_provenance") or {}
    if prov.get("uses_placeholder_linkage") is not False:
        problems.append(
            f"{path.name} derives placeholder linkage. C5 bars displaying such "
            "results at any event count, so declaring ACTIVE_COLLECTING would "
            "advertise a path whose output can never be shown.")

    # --- 3. THE ORDER GUARD: the map must be ratified first -----------------
    from hyp04_supply_chain_hedge.curated_linkage import load_curated_linkage
    map_name = (panel.get("sources") or {}).get("curated_map")
    map_path = LSE / map_name if map_name else None
    if map_path is None or not map_path.is_file():
        problems.append("the panel names no curated map on disk.")
    else:
        res = load_curated_linkage(map_path)
        anchors = set((panel.get("eligible_event_anchors") or {}).values())
        unratified = sorted(
            f"{e.anchor_ticker}->{e.peer_ticker}({e.review_status or 'blank'})"
            for e in res.edges
            if e.anchor_ticker.upper() in {a.upper() for a in anchors}
            and (e.review_status or "").strip() != "reviewed")
        if unratified:
            problems.append(
                f"{len(unratified)} contributing edge(s) are not 'reviewed': "
                f"{', '.join(unratified)}. ACTIVE_COLLECTING would declare a "
                "capture path whose linkage no human has ratified.")

    # --- 4. THE ORDER GUARD: a valid freeze must already exist -------------
    draft = newest_in(LSE, "HYP04_FREEZE_DRAFT_*.json")
    if draft is None:
        problems.append(
            "no freeze draft on disk. C1 is the LAST condition to move: "
            "clearing it while C3 is open leaves the gate one file from open "
            "with no frozen event set behind it.")
    else:
        try:
            make_freeze_draft.validate_freeze(Path(draft), panel_path=path)
        except Exception as exc:                  # noqa: BLE001 -- reported
            problems.append(
                f"{Path(draft).name} is not a valid freeze ({exc}). A draft is "
                "not a freeze, and C1 does not move ahead of C3.")
    return problems


def check_preconditions(*, v1_11: Path = V1_11, v1_12: Path = V1_12,
                        ) -> list[str]:
    refusals: list[str] = []
    if not v1_11.is_file():
        refusals.append(f"registry v1.11 not found at {v1_11.name}")
    if v1_12.exists():
        refusals.append(
            f"{v1_12.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really "
            "intended.")
    for f in FINDINGS:
        if not Path(f).is_file():
            refusals.append(
                f"the dated finding {f} is not on disk. A status change with "
                "no written basis is exactly what this project forbids.")
    refusals.extend(code_disagreements())
    return refusals


def build_v1_12(*, v1_11: Path = V1_11, authored_at: Optional[str] = None,
                ) -> tuple[dict[str, Any], list[str]]:
    doc = copy.deepcopy(_load(v1_11))
    changes: list[str] = []

    doc["registry_version"] = "v1.12"
    doc["authored_at"] = authored_at or AUTHORED_AT
    doc["supersedes"] = v1_11.name
    doc["supersedes_sha256"] = _sha256(v1_11)
    changes.append(f"registry_version: v1.11 -> v1.12 (supersedes {v1_11.name})")

    entry = None
    old_entry = None
    for h, oh in zip(doc.get("hypotheses", []),
                     _load(v1_11).get("hypotheses", [])):
        if h.get("hypothesis_id") == HYPOTHESIS_ID:
            entry, old_entry = h, oh
            break
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not in {v1_11.name}")

    path, panel = _panel()
    count = (panel.get("per_pair") or {}).get("eligible_anchor_events")
    floor = panel.get("registered_floor")

    entry["status"] = NEW_STATUS
    changes.append(f"status: {old_entry['status']} -> {NEW_STATUS} (C1)")

    entry["status_basis"] = (
        "All three capture paths now have production modules AND data has "
        f"flowed through them. Peer closes: 13,056 sessions across six peers, "
        "every panel loading clean. Linkage: a curated map whose contributing "
        "edges are ratified, from which the panel derives "
        "uses_placeholder_linkage=false. Assembly: "
        "hyp04_supply_chain_hedge/make_event_panel.py joins calendar, shocks, "
        "map and closes through pair_eligibility and derives "
        f"{count} eligible anchor events against the floor of {floor}, using "
        "the per-pair coverage unit v1.11 registered. v1.11 stated that C1 was "
        "a later version's to move 'once that assembler exists'; it does, and "
        "this is that version. ACTIVE_COLLECTING asserts a working capture "
        "path -- it asserts NOTHING about transmission, direction or effect, "
        "and the display_rule is unchanged.")
    changes.append("status_basis: rewritten; the stale '2 curated edge(s) as "
                   "of 2026-08-22' is replaced by the derived count")

    cpm = copy.deepcopy(entry.get("capture_path_modules") or {})
    for key in ("peer_return_ingestion", "event_to_peer_join"):
        if key in cpm:
            cpm[key]["data_captured"] = True
    cpm["panel_assembly"] = {
        "module": "hyp04_supply_chain_hedge/make_event_panel.py",
        "imports": True,
        "data_captured": True,
        "note": ("Joins the four inputs through pair_eligibility and "
                 "enumerates the eligible event set. The path v1.11 said did "
                 "not exist."),
    }
    cpm["module_existence_is_not_data"] = (
        "This note said, through v1.11, that both data_captured flags were "
        "false and that a module which CAN ingest is not ingested data. That "
        "was the reason HYP-04's status did not move. It is now false as a "
        "description: closes are collected, the join runs, and the eligible "
        "set is enumerated. The DISTINCTION it drew remains correct and still "
        "governs any path added later.")
    entry["capture_path_modules"] = cpm
    changes.append("capture_path_modules: both data_captured flags true; adds "
                   "panel_assembly; module_existence_is_not_data rewritten")

    # --- the exception is claimed, and it is narrow -----------------------
    if not SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
        raise RefusedError(
            "v1.12 moves immovable fields and must say which in its own "
            "source.")
    for f in IMMOVABLE_HYP04_FIELDS:
        if f in SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
            continue
        if entry.get(f) != old_entry.get(f):
            raise RefusedError(
                f"{HYPOTHESIS_ID}.{f} changed. v1.12 moves only "
                f"{SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE}.")
    changes.append(
        "guard: every immovable field outside "
        f"{SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE} is byte-identical to "
        "v1.11")

    if UNIVERSE_MUST_NOT_MOVE and entry.get("anchor_universe") != old_entry.get(
            "anchor_universe"):
        raise RefusedError(
            "the anchor_universe block changed. v1.12 moves a STATUS; "
            "membership is unchanged and must survive byte-identical.")
    changes.append("guard: the anchor universe is byte-identical to v1.11")

    if entry.get("display_rule") != old_entry.get("display_rule"):
        raise RefusedError("display_rule changed. v1.12 does not relax it.")
    changes.append("guard: display_rule is byte-identical to v1.11")

    doc.setdefault("findings_responded_to", {})["v1.12"] = list(FINDINGS)
    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.12 from v1.11, moving "
                    "status to ACTIVE_COLLECTING (gate condition C1).")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.12 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        print("\nC1 is the LAST gate condition to move. Ratify the map and "
              "complete a freeze first.")
        return 1

    doc, changes = build_v1_12(authored_at=a.authored_at)
    print("Changes v1.11 -> v1.12:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_12.name}.")
        return 0

    before = _sha256(V1_11)
    V1_12.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    if _sha256(V1_11) != before:
        raise RefusedError("v1.11 changed on disk during generation")

    print(f"\nWrote {V1_12.name}")
    print(f"v1.11 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nAfter repointing, C1 clears. With C2/C3/C5 already satisfied by "
          "the freeze, the gate OPENS -- which licenses reporting a "
          "measurement, and nothing about what it means.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
