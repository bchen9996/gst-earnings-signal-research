#!/usr/bin/env python3
"""Generate hypothesis-registry v1.4 from v1.3 -- resolve a self-contradiction.

NOT A TEST. NOT RUN BY CI. Named off the `test_*` discovery pattern for the
same reason the live audit runners and the other registry generators are.

=== WHAT WENT WRONG IN v1.3 ===

v1.3 corrected HYP-04's linkage availability from `does_not_exist` to
`exists_partial`. It did not correct two OTHER places in the same document that
assert the map does not exist. The published artifact therefore contradicts
itself:

    required_external_measurement.availability  -> "exists_partial"
    eligible_event_counts.note                  -> "no peer linkage map exists"
    statistical_governance
      .adding_a_hypothesis_rule                 -> "no linkage map exists"

Nothing computes from either sentence and no display-gate condition reads them,
so no result or decision was affected. But a governance document that asserts
two incompatible things is precisely what these documents exist to prevent, and
"nothing reads it" is the argument that lets prose rot.

**This is the same failure the rest of the session was spent removing**: a fact
corrected in one place while a copy of it survives somewhere else. It was
produced BY the correction. v1.3's guards checked that immovable fields had not
moved and that no other hypothesis changed; nothing checked whether the field
being corrected still had copies elsewhere.

=== WHY v1.4 AND NOT AN EDIT ===

v1.3 is published and append-only. It asserts that rule about v1.2, and it
applies to itself. v1.3 stays on disk, byte for byte, contradiction included --
a superseded version is allowed to be wrong; that is what superseded means.

=== THE GUARD, WHICH IS THE ACTUAL DELIVERABLE ===

`find_availability_contradictions()` walks a whole registry document and reports
every string still asserting the linkage map does not exist while the
availability field says otherwise. `build_v1_4()` runs it on its OWN OUTPUT and
refuses to write a document that fails.

Fields whose JOB is to name a previous state are exempt, and the exemption is
narrow and listed: a change summary that says the value moved FROM
`does_not_exist`, the vocabulary that DEFINES that word, the basis note, and
the correction record. Without those exemptions the guard would forbid a
document from explaining its own history.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterator, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

V1_3 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.3.json"
V1_4 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.4.json"
V1_4_MARKDOWN = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.4_DRAFT.md"

HYPOTHESIS_ID = "HYP-04"
AVAILABILITY_DOES_NOT_EXIST = "does_not_exist"

# Phrases that assert the linkage map does not exist. Matched case-insensitively.
NONEXISTENCE_CLAIMS: tuple[str, ...] = (
    "no peer linkage map exists",
    "no linkage map exists",
    "no peer linkage map",
    "linkage map does not exist",
    "does not exist in any form",
)

# Keys whose JOB is to name a previous or alternative state. The exemption is
# narrow on purpose: it covers documents EXPLAINING their own history, not
# documents making a current claim.
EXEMPT_KEYS: tuple[str, ...] = (
    "change_summary",
    "supersession_rule",
    "external_measurement_availability_vocabulary",
    "external_measurement_availability_vocabulary_note",
    "availability_basis",
    "placeholder_description_correction",
    "contradiction_corrected",
)

IMMOVABLE_HYP04_FIELDS = (
    "status", "classification", "minimum_eligible_events",
    "minimum_eligible_events_unit", "required_eligibility_class",
    "is_primary_confirmatory", "options_benchmark_required",
    "display_rule", "forbidden_substitutions", "forbidden_substitution_rule",
    "unresolved_analysis_decisions", "required_external_measurement",
    "capture_path_modules", "status_basis",
)


class RefusedError(RuntimeError):
    """Raised when a precondition for generating v1.4 is not met."""


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _walk_strings(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string in the document, with a dotted path to where it lives."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def _is_exempt(path: str) -> bool:
    return any(part in EXEMPT_KEYS for part in path.replace("[", ".").split("."))


def linkage_availability(doc: dict) -> Optional[str]:
    entry = next((h for h in doc.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    if not entry:
        return None
    return (entry.get("required_external_measurement") or {}).get("availability")


def find_availability_contradictions(doc: dict) -> list[str]:
    """Places the document still says the map does not exist, when it does.

    Returns dotted paths with the offending phrase. Empty means consistent.

    When availability IS `does_not_exist` there is nothing to contradict, so
    the check is vacuous by design and returns nothing -- a document may say
    the map is absent as often as it likes while the map is absent.
    """
    avail = linkage_availability(doc)
    if avail is None or avail == AVAILABILITY_DOES_NOT_EXIST:
        return []

    hits: list[str] = []
    for path, text in _walk_strings(doc):
        if _is_exempt(path):
            continue
        low = text.lower()
        for claim in NONEXISTENCE_CLAIMS:
            if claim in low:
                hits.append(f"{path}: {claim!r}")
                break
    return hits


def check_preconditions(*, v1_3: Path = V1_3, v1_4: Path = V1_4) -> list[str]:
    refusals: list[str] = []
    if not v1_3.is_file():
        refusals.append(f"registry v1.3 not found at {v1_3.name}")
        return refusals
    if v1_4.exists():
        refusals.append(
            f"{v1_4.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really intended.")

    src = _load(v1_3)
    if not find_availability_contradictions(src):
        refusals.append(
            "v1.3 carries no availability contradiction. v1.4 exists to fix "
            "one; with nothing to fix it would be an empty version bump.")
    return refusals


def build_v1_4(*, v1_3: Path = V1_3, authored_at: Optional[str] = None,
               ) -> tuple[dict, list[str]]:
    """Return (v1.4 document, list of changes). Pure; writes nothing."""
    src = _load(v1_3)
    doc = copy.deepcopy(src)
    changes: list[str] = []
    date = authored_at or "2026-08-23"

    before = find_availability_contradictions(src)
    if not before:
        raise RefusedError("nothing to correct in v1.3")

    doc["registry_version"] = "1.4"
    doc["authored_at_utc"] = date
    doc["supersedes"] = v1_3.name
    doc["supersedes_sha256"] = _sha256(v1_3)
    doc["companion_markdown"] = f"{LSE.name}/{V1_4_MARKDOWN.name}"
    doc["supersession_rule"] = (
        f"{v1_3.name} is NOT edited in place. It remains on disk, unchanged, "
        "byte-for-byte, CONTRADICTION INCLUDED -- a superseded version is "
        "allowed to be wrong, which is what superseded means. This version is a "
        "consistency correction: it resolves a self-contradiction v1.3 "
        "introduced. It resolves no decision, changes no threshold, moves no "
        "hypothesis, and alters no measurement.")
    doc["change_summary"] = (
        "Resolves a SELF-CONTRADICTION in v1.3. v1.3 corrected HYP-04's linkage "
        "availability to 'exists_partial' but left two other statements in the "
        "same document asserting that no linkage map exists "
        "(eligible_event_counts.note and "
        "statistical_governance.adding_a_hypothesis_rule). Nothing computed "
        "from either sentence and no display-gate condition read them, so no "
        "result or decision was affected -- but a governance document that "
        "asserts two incompatible things is what these documents exist to "
        "prevent. NO hypothesis is modified, reclassified, promoted, demoted or "
        "re-thresholded; no measurement, capture path or decision ledger "
        "changes. HYP-04's status remains "
        "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED and the gate stays CLOSED "
        "with C4 MET.")
    changes.append(f"registry_version 1.3 -> 1.4, authored_at_utc {date}")
    changes.append(f"companion_markdown -> {V1_4_MARKDOWN.name}")

    # --- correction 1: the counts note ------------------------------------
    counts = doc.get("eligible_event_counts")
    if not isinstance(counts, dict) or "note" not in counts:
        raise RefusedError("eligible_event_counts.note is missing")
    counts["note"] = (
        "Zero for every hypothesis, including HYP-04. No candidate has been "
        "screened for HYP-04, no prospective HYP-04 event has been observed, "
        "and no result exists. A curated linkage map now exists in part "
        "(availability 'exists_partial') and is nowhere near sufficient; it is "
        "NOT a reason these counters are non-zero, because they count eligible "
        "ANCHOR EVENTS, which curating linkage edges does not produce. These "
        "counters are structural placeholders.")
    changes.append("eligible_event_counts.note: no longer claims the map does "
                   "not exist; says why edges do not move an event counter")

    # --- correction 2: the hypothesis-addition rule ------------------------
    gov = doc.get("statistical_governance")
    if not isinstance(gov, dict) or "adding_a_hypothesis_rule" not in gov:
        raise RefusedError("statistical_governance.adding_a_hypothesis_rule is missing")
    gov["adding_a_hypothesis_rule"] = (
        "A new hypothesis enters this registry only via a new dated registry "
        "version, authored before any observation or result for that hypothesis "
        "exists. v1.1 added HYP-04 under that rule: AT THAT TIME zero HYP-04 "
        "eligible events existed, no linkage map existed, and no HYP-04 result "
        "had been produced or looked at. That is a statement about the "
        "conditions when HYP-04 was added, not about the present -- curation "
        "began 2026-08-22. The eligible-event count and the result are still "
        "zero and null respectively.")
    changes.append("adding_a_hypothesis_rule: made explicitly historical rather "
                   "than reading as a present-tense claim")

    doc["contradiction_corrected"] = {
        "in_version": "1.3",
        "corrected_by": "1.4",
        "paths": before,
        "why_it_happened": (
            "v1.3 corrected required_external_measurement.availability and "
            "inherited two other statements of the same fact. Its guards "
            "verified that immovable fields had not moved and that no other "
            "hypothesis changed; nothing verified that the field being "
            "corrected had no surviving copies elsewhere in the document."),
        "guard_added": (
            "make_registry_v1_4.find_availability_contradictions() walks the "
            "whole document and reports every non-exempt string asserting the "
            "map does not exist while availability says otherwise. build_v1_4 "
            "runs it on its OWN output and refuses to write a failing "
            "document, so this class cannot ship again."),
        "no_effect_on_results": (
            "Nothing computed from either sentence and no display-gate "
            "condition read them. No result, decision or gate state changed."),
    }
    changes.append("added contradiction_corrected (what, why, and the guard)")

    # --- immovability, checked not assumed --------------------------------
    ids_new = [h.get("hypothesis_id") for h in doc.get("hypotheses", [])]
    ids_old = [h.get("hypothesis_id") for h in src.get("hypotheses", [])]
    if ids_new != ids_old:
        raise RefusedError(f"hypothesis list changed: {ids_old} -> {ids_new}")
    if doc.get("hypotheses_carried_forward_unchanged") != \
            src.get("hypotheses_carried_forward_unchanged"):
        raise RefusedError("hypotheses_carried_forward_unchanged was touched")

    new_e = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == HYPOTHESIS_ID)
    old_e = next(h for h in src["hypotheses"] if h["hypothesis_id"] == HYPOTHESIS_ID)
    for field in IMMOVABLE_HYP04_FIELDS:
        if new_e.get(field) != old_e.get(field):
            raise RefusedError(
                f"{HYPOTHESIS_ID}.{field} changed; v1.4 corrects prose only")
    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.4 reports nothing")

    # --- the guard, on our OWN output -------------------------------------
    after = find_availability_contradictions(doc)
    if after:
        raise RefusedError(
            "v1.4 would itself contradict its availability field at: "
            + "; ".join(after))
    changes.append(f"guard: {len(before)} contradiction(s) in v1.3 -> 0 in v1.4")

    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.4 from v1.3, resolving "
                    "the self-contradiction v1.3 introduced.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.4 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        return 1

    print("Contradictions found in v1.3:")
    for c in find_availability_contradictions(_load(V1_3)):
        print(f"  * {c}")
    print()

    doc, changes = build_v1_4(authored_at=a.authored_at)
    print("Changes v1.3 -> v1.4:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_4.name}.")
        return 0

    before = _sha256(V1_3)
    V1_4.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if _sha256(V1_3) != before:
        raise RefusedError("v1.3 changed on disk during generation")

    print(f"\nWrote {V1_4.name}")
    print(f"v1.3 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nThe gate must stay CLOSED with C4 MET across the bump.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
