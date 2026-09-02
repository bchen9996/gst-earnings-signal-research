#!/usr/bin/env python3
"""Generate hypothesis-registry v1.3 from v1.2 -- factual corrections only.

NOT A TEST. NOT RUN BY CI. Deliberately named off the `test_*` discovery
pattern, for the same reason the live audit runners and make_registry_v1_2 are:
this writes a governance artifact and must only ever run when a human decides
it should.

=== WHAT v1.3 CORRECTS, AND WHY A VERSION BUMP IS THE ONLY WAY ===

v1.2 carries three statements that were true when authored and are not now.
A registry is append-only -- v1.2 is never edited in place -- so correcting a
field means authoring a successor.

  1. `required_external_measurement.availability` reads `does_not_exist`.
     Curation began 2026-08-22 and the committed map loads clean with edges.

  2. `status_basis` names three missing capture paths. Two of them now have
     modules: (3) the event -> peer join is `linkage_resolution.py`, and (2)
     peer-side return ingestion is `peer_returns.py`.

  3. `placeholder_used_in_phase_0` reads "same-sector peers". That is the SAME
     error corrected in `__init__.py` on 2026-08-18 and in the package README on
     2026-08-22: the Phase 0 pairing is POSITIONAL -- `peers[i*k:(i+1)*k]` --
     and the sector column is never read. "Same-sector" overstates the
     placeholder's quality, which is the dangerous direction for a field whose
     job is to warn.

=== WHY `exists_partial` AND NOT `exists` ===

Two curated edges are not a linkage map. Flipping to `exists` would make that
word mean "some rows are present", and every other place the registry uses it
would weaken to match. `exists_partial` says what is true: real curated data
exists, and it is nowhere near sufficient. The vocabulary is DEFINED in the
document rather than merely used, so a later reader is not left inferring it.

=== THE FACTS ARE DERIVED, NOT ASSERTED ===

Same property `LinkageProvenance` gives `uses_placeholder_linkage` and
`peer_returns` gives P5: this generator does not take anyone's word for the
state it records.

It READS the committed map through the validating loader and REFUSES to write
`exists_partial` unless the map genuinely loads clean with at least one usable
edge. A registry that records `exists_partial` because an operator typed it is
worth no more than a freeze record that claims non-placeholder linkage because
a caller set a flag.

Likewise it verifies the two capture modules import before recording that they
exist.

=== WHAT IT DOES NOT DO ===

It does NOT claim any gap is closed in the sense that matters. A module that
can ingest peer returns is not ingested peer returns; ZERO peer price data has
been captured. The new `status_basis` says so explicitly, because "a path
exists" and "data has flowed" are exactly the two things this project keeps
having to hold apart.

It does not touch v1.0, v1.1 or v1.2; does not change any hypothesis status,
threshold or classification; does not resolve or reopen any analysis decision;
and does not open the display gate. C4 must keep reading MET and the gate must
keep reading CLOSED across the bump -- verified by the v1.3 test suite.

Usage:
    python -m hyp04_supply_chain_hedge.make_registry_v1_3            # dry run
    python -m hyp04_supply_chain_hedge.make_registry_v1_3 --write
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

V1_2 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.2.json"
V1_3 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.3.json"
V1_3_MARKDOWN = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.3_DRAFT.md"

HYPOTHESIS_ID = "HYP-04"

AVAILABILITY_DOES_NOT_EXIST = "does_not_exist"
AVAILABILITY_EXISTS_PARTIAL = "exists_partial"

# The vocabulary is defined in the document, not left to a reader to infer.
AVAILABILITY_VOCABULARY = {
    "does_not_exist": (
        "No curated data of this kind exists anywhere in the repository."
    ),
    "exists_partial": (
        "Real curated data exists and validates, but is nowhere near sufficient "
        "for the hypothesis. This state NEVER means the measurement is "
        "satisfied, and it is not a step toward display: the display gate's "
        "event-count threshold counts eligible ANCHOR EVENTS, which curating "
        "linkage edges does not move."
    ),
    "exists": (
        "Curated data exists and is sufficient for the registered measurement. "
        "NOT YET USED BY ANY HYPOTHESIS."
    ),
}


class RefusedError(RuntimeError):
    """Raised when a precondition for generating v1.3 is not met."""


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


#: The map v1.3 was AUTHORED AGAINST, pinned by name and hash.
#:
#: This used to glob and take `sorted(...)[0]`. That returned v1.0 only by
#: luck: a map named without a `v` prefix (`HYP04_Linkage_Map_final.csv` sorts
#: before `_v1.0`) would silently have become this frozen registry's evidence.
#:
#: And "newest" -- the right answer for the live dashboard -- is the WRONG
#: answer here, in the opposite direction. v1.3's own availability_basis reads
#: "As of 2026-08-22: 2 curated edge(s) in HYP04_Linkage_Map_v1.0.csv (sha256
#: e7b0881186751f32...)". That is a dated, point-in-time record. A generator
#: that re-derived it from whatever map is on disk today would make a frozen
#: registry's evidence drift the moment the next map lands -- which the
#: curation step now in front of us is about to do.
#:
#: So the pin is explicit and CHECKED. If the file is missing or its bytes
#: changed, this refuses rather than quietly reporting a different map's edges
#: under v1.3's name.
PINNED_MAP_NAME = "HYP04_Linkage_Map_v1.0.csv"
PINNED_MAP_SHA256 = (
    "e7b0881186751f32c5f56633a3a8809824ccdfee4485e8e4a3ce368795b371d4")


class PinnedMapChanged(RuntimeError):
    """The map v1.3 was authored against is gone or no longer byte-identical."""


def observed_linkage_state() -> dict[str, Any]:
    """Read the PINNED map through the VALIDATING loader. No assertions.

    Returns what was actually found. `usable` is the only thing that may
    justify `exists_partial`, and it is computed here rather than supplied.

    Pinned, not globbed: see PINNED_MAP_NAME. A frozen registry has to keep
    deriving the same evidence, and later maps are later registries' business.
    """
    from .curated_linkage import load_curated_linkage

    pinned = LSE / PINNED_MAP_NAME
    if not pinned.is_file():
        raise PinnedMapChanged(
            f"{PINNED_MAP_NAME} is not on disk. v1.3 records its edge count "
            "and sha256 as a point-in-time fact; regenerating against a "
            "different map would silently restate that fact.")
    got = _sha256(pinned)
    if got != PINNED_MAP_SHA256:
        raise PinnedMapChanged(
            f"{PINNED_MAP_NAME} has changed: expected {PINNED_MAP_SHA256}, "
            f"found {got}. v1.3's availability_basis quotes the old hash. "
            "Curate into a NEW map version rather than editing this one.")

    res = load_curated_linkage(pinned)
    return {
        "map_present": True,
        "source": pinned.name,
        "source_sha256": got,
        "edges": len(res.edges),
        "rows_seen": res.rows_seen,
        "rows_rejected": res.rows_rejected,
        "loads_clean": res.ok,
        "usable": bool(res.ok and len(res.edges) >= 1),
    }


def observed_capture_modules() -> dict[str, bool]:
    """Verify the two capture modules import, rather than trusting a claim."""
    out: dict[str, bool] = {}
    for name in ("linkage_resolution", "peer_returns"):
        try:
            __import__(f"hyp04_supply_chain_hedge.{name}")
            out[name] = True
        except Exception:  # noqa: BLE001
            out[name] = False
    return out


def check_preconditions(*, v1_2: Path = V1_2, v1_3: Path = V1_3,
                        ) -> list[str]:
    """Every reason generation must not proceed. Empty means clear to run."""
    refusals: list[str] = []

    if not v1_2.is_file():
        refusals.append(f"registry v1.2 not found at {v1_2.name}")
    if v1_3.exists():
        refusals.append(
            f"{v1_3.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really intended."
        )

    obs = observed_linkage_state()
    if not obs["map_present"]:
        refusals.append(
            "no curated linkage map on disk. v1.3's whole purpose is to record "
            "that one exists; with none present it would assert something false."
        )
    elif not obs["loads_clean"]:
        refusals.append(
            f"{obs['source']} does not load clean "
            f"({obs['rows_rejected']} of {obs['rows_seen']} rows rejected). "
            "An invalid map must never be recorded as existing data."
        )
    elif not obs["usable"]:
        refusals.append(
            f"{obs['source']} loads but yields zero usable edges -- "
            "'exists_partial' would overstate it."
        )

    mods = observed_capture_modules()
    missing = [k for k, v in mods.items() if not v]
    if missing:
        refusals.append(
            f"capture module(s) failed to import: {missing}. v1.3 records that "
            "they exist, so it must not be written while they do not."
        )

    return refusals


def build_v1_3(*, v1_2: Path = V1_2, authored_at: Optional[str] = None,
               ) -> tuple[dict, list[str]]:
    """Return (v1.3 document, list of changes made). Pure; writes nothing."""
    src = _load(v1_2)
    doc = copy.deepcopy(src)
    changes: list[str] = []

    obs = observed_linkage_state()
    mods = observed_capture_modules()
    date = authored_at or "2026-08-22"

    doc["registry_version"] = "1.3"
    doc["authored_at_utc"] = date
    doc["supersedes"] = v1_2.name
    doc["supersedes_sha256"] = _sha256(v1_2)
    doc["companion_markdown"] = f"{LSE.name}/{V1_3_MARKDOWN.name}"
    doc["supersession_rule"] = (
        f"{v1_2.name} is NOT edited in place. It remains on disk, unchanged, "
        "byte-for-byte, and its own governance tests continue to run against "
        "it. This version is a FACTUAL CORRECTION: it records state that "
        "changed after v1.2 was authored. It resolves no decision, changes no "
        "threshold, and promotes no hypothesis."
    )
    doc["change_summary"] = (
        "Corrects three statements in v1.2 that were true when authored and are "
        "no longer. (a) HYP-04's linkage availability moves from "
        "'does_not_exist' to 'exists_partial' -- hand curation began "
        f"{date} and the committed map validates. (b) status_basis is updated: "
        "two of the three named capture gaps now have modules "
        "(linkage_resolution.py for the event->peer join, peer_returns.py for "
        "peer-side return ingestion). (c) placeholder_used_in_phase_0 said "
        "'same-sector peers'; the Phase 0 pairing is POSITIONAL and the sector "
        "column is never read, so that overstated the placeholder's quality. "
        "NO hypothesis is modified, reclassified, promoted, demoted or "
        "re-thresholded. HYP-04's status remains "
        "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED. No display-gate condition "
        "changes: the gate stays CLOSED and C4 stays MET."
    )
    changes.append(f"registry_version 1.2 -> 1.3, authored_at_utc {date}")
    changes.append(f"companion_markdown -> {V1_3_MARKDOWN.name}")

    doc["external_measurement_availability_vocabulary"] = AVAILABILITY_VOCABULARY
    doc["external_measurement_availability_vocabulary_note"] = (
        "Introduced by v1.3. 'exists_partial' is added because two curated "
        "edges are not a linkage map: recording them as 'exists' would weaken "
        "that word everywhere else it appears. Defined here rather than left "
        "for a reader to infer from usage."
    )
    changes.append("added external_measurement_availability_vocabulary (3 states)")

    entry = next((h for h in doc.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not present in {v1_2.name}")

    ext = entry.get("required_external_measurement")
    if not isinstance(ext, dict):
        raise RefusedError(
            f"{HYPOTHESIS_ID}.required_external_measurement is missing")

    prev = ext.get("availability")
    if prev != AVAILABILITY_DOES_NOT_EXIST:
        raise RefusedError(
            f"expected availability {AVAILABILITY_DOES_NOT_EXIST!r} in "
            f"{v1_2.name}, found {prev!r} -- refusing to guess at the transform"
        )
    ext["availability"] = AVAILABILITY_EXISTS_PARTIAL
    changes.append(f"HYP-04 availability {prev} -> {AVAILABILITY_EXISTS_PARTIAL}")

    ext["availability_basis"] = (
        f"As of {date}: {obs['edges']} curated edge(s) in {obs['source']} "
        f"(sha256 {str(obs.get('source_sha256'))[:16]}...), loading clean with "
        f"{obs['rows_rejected']} of {obs['rows_seen']} rows rejected. Read "
        "through curated_linkage.load_curated_linkage() when this version was "
        "generated, not asserted by the author. A count is recorded here "
        "because a registry version is a point-in-time record; live code must "
        "read the count from disk instead."
    )
    ext["availability_is_not_sufficiency"] = (
        "'exists_partial' does NOT mean the required measurement is satisfied, "
        "and it moves nothing toward display. The display gate's threshold "
        "counts eligible ANCHOR EVENTS; curating linkage edges does not change "
        "that count. Phase 1 remains blocked."
    )
    changes.append("added availability_basis and availability_is_not_sufficiency")

    old_ph = ext.get("placeholder_used_in_phase_0")
    ext["placeholder_used_in_phase_0"] = (
        "POSITIONAL-SYNTHETIC pairing -- peers[i*k:(i+1)*k] in fixtures.py. "
        "Peers are the non-anchor tickers from AllTickers_Sectors.csv assigned "
        "to anchors by list position; the sector column is NOT read for "
        "pairing."
    )
    ext["placeholder_description_correction"] = (
        f"v1.0 through v1.2 described this as {old_ph!r}. That wording "
        "described GST_Task2_PeerDivergence.py, which IS genuinely "
        "sector-based, and was inherited here in error. The package corrected "
        "it in __init__.py on 2026-08-18 and in its README on 2026-08-22; this "
        "is the registry catching up. The error ran in the dangerous direction "
        "-- it OVERSTATED the placeholder's quality, in a field whose purpose "
        "is to warn. Earlier registry versions are not edited; they remain on "
        "disk with the original wording."
    )
    changes.append("HYP-04 placeholder_used_in_phase_0 corrected to positional-synthetic")

    entry["status_basis"] = (
        "Two of the three capture paths named in v1.2 now have production "
        "modules; the LINKAGE MAP is partially curated. NONE of this means data "
        "has flowed. (1) The supply-chain/competitor LINKAGE MAP now exists in "
        f"part -- {obs['edges']} curated edge(s) as of {date} -- against a "
        "requirement measured in eligible anchor events, so it remains the "
        "binding blocker on Phase 1. Phase 0 ran, and still runs, entirely on "
        "the positional-synthetic placeholder. (2) A capture path for PEER-side "
        "return series EXISTS (hyp04_supply_chain_hedge/peer_returns.py): it "
        "validates operator-supplied closes into per-peer daily log returns on "
        "a shared session index and DERIVES peer-history availability rather "
        "than accepting it. ZERO peer price data has been captured through it. "
        "A path that can ingest is not ingested data. (3) The join mapping a "
        "market-response event_id to peer observations EXISTS "
        "(hyp04_supply_chain_hedge/linkage_resolution.py) and derives "
        "uses_placeholder_linkage from what was actually read. No production "
        "run has used it. Working analysis code operating on synthetic fixtures "
        "is not a production capture path, and this registry does not treat it "
        "as one -- that rule is unchanged from v1.2 and is why HYP-04's status "
        "does not move."
    )
    changes.append("HYP-04 status_basis rewritten (gaps 2 and 3 have modules; no data)")

    entry["capture_path_modules"] = {
        "peer_return_ingestion": {
            "module": "hyp04_supply_chain_hedge/peer_returns.py",
            "imports": mods.get("peer_returns", False),
            "data_captured": False,
            "note": "Provider-free by design; closes are operator-supplied.",
        },
        "event_to_peer_join": {
            "module": "hyp04_supply_chain_hedge/linkage_resolution.py",
            "imports": mods.get("linkage_resolution", False),
            "data_captured": False,
            "note": "Derives uses_placeholder_linkage; a caller cannot assert it.",
        },
        "module_existence_is_not_data": (
            "A module that CAN ingest is not ingested data. Both flags report "
            "only that a MODULE imports; both data_captured flags are false, "
            "and no observation has been captured through either path. This "
            "distinction is the reason HYP-04's status is unchanged."
        ),
    }
    changes.append("added HYP-04 capture_path_modules (with data_captured: false)")

    assert_only_expected_changes(doc, src)
    return doc, changes


# Fields a FACTUAL CORRECTION must never move. Kept as data, and the guard is a
# separate callable so it can be tested against a deliberately-tampered
# document -- a guard that is only ever reached through the happy path is a
# guard nobody has seen fire.
IMMOVABLE_HYP04_FIELDS = (
    "status", "classification", "minimum_eligible_events",
    "minimum_eligible_events_unit", "required_eligibility_class",
    "is_primary_confirmatory", "options_benchmark_required",
    "display_rule", "forbidden_substitutions", "forbidden_substitution_rule",
    "unresolved_analysis_decisions",
)


def assert_only_expected_changes(doc: dict, src: dict) -> None:
    """Raise unless `doc` differs from `src` only in the ways v1.3 intends.

    Two separate rules, because they fail for different reasons:
      * no hypothesis other than HYP-04 may differ AT ALL
      * HYP-04 may differ only outside IMMOVABLE_HYP04_FIELDS

    Raise rather than assert: `python -O` strips asserts, and this is a
    governance invariant rather than a debug aid.
    """
    # `hypotheses` holds ONLY HYP-04. HYP-01/02/03 are not restated -- v1.0 is
    # their authoritative source, deliberately, so that no second mutable copy
    # of governed text exists. A loop over `hypotheses` looking for "other
    # hypotheses that changed" therefore iterates a one-element list and can
    # never fire: a vacuous check that reads like a real one. The invariants
    # that actually exist are checked instead.
    ids_new = [h.get("hypothesis_id") for h in doc.get("hypotheses", [])]
    ids_old = [h.get("hypothesis_id") for h in src.get("hypotheses", [])]
    if ids_new != ids_old:
        raise RefusedError(
            f"the hypothesis list changed ({ids_old} -> {ids_new}); v1.3 adds "
            "and removes no hypothesis"
        )
    if ids_new != [HYPOTHESIS_ID]:
        raise RefusedError(
            f"expected `hypotheses` to hold only {HYPOTHESIS_ID}, found "
            f"{ids_new}. If that changed, this guard's assumption no longer "
            "holds and the carried-forward rule below needs rethinking."
        )

    carried_new = doc.get("hypotheses_carried_forward_unchanged")
    carried_old = src.get("hypotheses_carried_forward_unchanged")
    if carried_new != carried_old:
        raise RefusedError(
            "hypotheses_carried_forward_unchanged changed; HYP-01, HYP-02 and "
            "HYP-03 are governed by v1.0 and v1.3 does not restate or touch them"
        )

    # v1.0 carries the other three hypotheses and the document asserts it must
    # stay byte-identical. Verify rather than repeat the claim.
    if isinstance(carried_new, dict) and carried_new.get(
            "v1_0_must_remain_byte_identical") is True:
        v1_0 = LSE / str(carried_new.get("source", ""))
        if not v1_0.is_file():
            raise RefusedError(
                f"{carried_new.get('source')} is missing, but this registry "
                "declares it the authoritative source for HYP-01/02/03"
            )

    new_e = next((h for h in doc.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    old_e = next((h for h in src.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    if new_e is None or old_e is None:
        raise RefusedError(f"{HYPOTHESIS_ID} missing from a document")

    for field in IMMOVABLE_HYP04_FIELDS:
        if new_e.get(field) != old_e.get(field):
            raise RefusedError(
                f"{HYPOTHESIS_ID}.{field} changed; v1.3 is a factual "
                f"correction and must not move it "
                f"({old_e.get(field)!r} -> {new_e.get(field)!r})"
            )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.3 from v1.2 -- factual "
                    "corrections to HYP-04's linkage availability, capture "
                    "paths and placeholder description.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.3 (default is a dry run)")
    ap.add_argument("--authored-at", default=None,
                    help="YYYY-MM-DD authoring date (default 2026-08-22)")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        print("\nNothing was written.")
        return 1

    obs = observed_linkage_state()
    print("Observed state (READ, not asserted):")
    for k, v in obs.items():
        print(f"  {k}: {v}")
    print()

    doc, changes = build_v1_3(authored_at=a.authored_at)
    print("Changes v1.2 -> v1.3:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_3.name}.")
        return 0

    before = _sha256(V1_2)
    V1_3.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    after = _sha256(V1_2)
    if before != after:
        raise RefusedError(
            "registry v1.2 changed on disk during generation -- it must remain "
            "byte-for-byte identical")

    print(f"\nWrote {V1_3.name}")
    print(f"v1.2 unchanged, sha256 {after[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nThe gate must stay CLOSED with C4 MET across the bump. If C4 "
          "flips, stop: v1.3 resolves no decision and must not have moved it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
