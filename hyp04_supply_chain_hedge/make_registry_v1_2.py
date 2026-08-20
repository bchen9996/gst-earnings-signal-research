#!/usr/bin/env python3
"""Generate hypothesis-registry v1.2 from v1.1, once the analysis lock is signed.

NOT A TEST. NOT RUN BY CI. Deliberately named off the `test_*` discovery
pattern, for the same reason the live audit runners are: this writes a
governance artifact and must only ever run when a human decides it should.

=== WHY A GENERATOR AND NOT A HAND-EDITED SKELETON ===

Registry v1.1 carries ~26 top-level keys and four hypotheses. Resolving HYP-04's
four analysis decisions changes exactly four nested `state` fields and adds four
`resolved_by_lock` fields. Everything else must survive byte-for-byte in
content. Hand-copying that invites a silent dropped key, which is the failure
mode the registry's own governance tests exist to catch -- so the transform is
mechanical, inspectable, and refuses to guess.

A pre-authored v1.2 skeleton was the obvious alternative and is worse: an inert
registry file sitting on disk can be mistaken for an authored one, and authoring
a registry version is a governed act that follows the signature rather than
preceding it.

=== THIS REFUSES TO RUN UNLESS THE LOCK IS SIGNED ===

The lock being signed is the whole precondition. This script checks it rather
than trusting the operator:

  * the signed lock file must exist -- NOT the `_DRAFT` one
  * its `status` must not be a draft status, and `in_force` must be true
  * it must carry an authorizer and an operative date
  * v1.2 must not already exist (no silent overwrite of a governance artifact)

Any failure aborts without writing. Dry-run is the default; `--write` is
required to produce a file.

=== WHAT IT DOES NOT DO ===

It does not sign anything, does not touch v1.0 or v1.1, does not repoint the
code that pins the v1.1 filename, and does not open the display gate. Clearing
C4 also requires those code changes -- the list is printed on completion and
recorded in the lock's section 11.

Usage:
    python -m hyp04_supply_chain_hedge.make_registry_v1_2            # dry run
    python -m hyp04_supply_chain_hedge.make_registry_v1_2 --write
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .display_gate import (
    HYPOTHESIS_ID,
    PENDING_TOKEN,
    RESOLVED_BY_FIELD,
    RESOLVED_TOKEN,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

V1_1 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json"
V1_2 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.2.json"

SIGNED_LOCK = LSE / "GST_HYP04_ANALYSIS_LOCK_v1.0.json"
DRAFT_LOCK = LSE / "GST_HYP04_ANALYSIS_LOCK_v1.0_DRAFT.json"

DRAFT_STATUSES = {"DRAFT", "DRAFT_UNSIGNED", "UNSIGNED", "PROPOSED"}

# Code that pins the v1.1 filename. Repointing these is a separate act, and
# skipping it means the gate keeps reading v1.1 and C4 never clears.
PINS_V1_1 = (
    "hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_V1_1 constant)",
    "hyp04_supply_chain_hedge/dashboard.py     (REGISTRY constant)",
    "test_hyp04_supply_chain_hedge_display_gate.py",
    "test_hyp04_supply_chain_hedge_quantum_provenance.py",
    "test_market_response_hypothesis_registry_v1_1.py  (keep pointing at v1.1)",
)


class RefusedError(RuntimeError):
    """Raised when a precondition for generating v1.2 is not met."""


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def check_preconditions(
    *,
    signed_lock: Path = SIGNED_LOCK,
    v1_1: Path = V1_1,
    v1_2: Path = V1_2,
) -> list[str]:
    """Every reason generation must not proceed. Empty means clear to run."""
    refusals: list[str] = []

    if not v1_1.is_file():
        refusals.append(f"registry v1.1 not found at {v1_1.name}")

    if v1_2.exists():
        refusals.append(
            f"{v1_2.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really intended."
        )

    if not signed_lock.is_file():
        hint = ""
        if DRAFT_LOCK.is_file():
            hint = (
                f" The draft {DRAFT_LOCK.name} exists, which is not the same "
                "thing: signing means completing the authorization, renaming off "
                "_DRAFT, and setting in_force."
            )
        refusals.append(f"signed lock not found at {signed_lock.name}.{hint}")
        return refusals

    try:
        lock = _load(signed_lock)
    except json.JSONDecodeError as e:
        refusals.append(f"{signed_lock.name} is not valid JSON ({e})")
        return refusals

    status = str(lock.get("status", "")).upper()
    if status in DRAFT_STATUSES or not status:
        refusals.append(
            f"lock status is {status or '<missing>'!r} -- an unsigned lock "
            "authorizes nothing"
        )
    if lock.get("in_force") is not True:
        refusals.append("lock does not declare in_force: true")
    if not str(lock.get("authorizer") or "").strip():
        refusals.append("lock records no authorizer")
    if not str(lock.get("operative_date") or "").strip():
        refusals.append("lock records no operative_date")
    if lock.get("no_outcome_inspected_before_signing_attested") is not True:
        refusals.append(
            "lock does not attest that no outcome was inspected before signing"
        )

    return refusals


def build_v1_2(
    *,
    v1_1: Path = V1_1,
    signed_lock: Path = SIGNED_LOCK,
    operative_date: Optional[str] = None,
) -> tuple[dict, list[str]]:
    """Return (v1.2 document, list of changes made). Pure; writes nothing."""
    src = _load(v1_1)
    doc = copy.deepcopy(src)
    changes: list[str] = []

    lock = _load(signed_lock) if signed_lock.is_file() else {}
    date = operative_date or lock.get("operative_date") or "<unset>"
    lock_ref = signed_lock.name

    doc["registry_version"] = "1.2"
    doc["authored_at_utc"] = date
    doc["supersedes"] = v1_1.name
    doc["supersession_rule"] = (
        f"{v1_1.name} is NOT edited in place. It remains on disk, unchanged, "
        "byte-for-byte, and its own governance tests continue to run against "
        "it. This version is additive: it records the resolution of HYP-04's "
        "four analysis decisions and changes nothing about HYP-01, HYP-02 or "
        "HYP-03."
    )
    doc["change_summary"] = (
        f"Records that HYP-04's four PENDING_SEPARATE_ANALYSIS_LOCK decisions "
        f"were resolved in {lock_ref} (operative {date}). No hypothesis is "
        "modified, reclassified, promoted, demoted or re-thresholded. The "
        "options-eligibility position is unchanged and still carries no "
        "registered hypothesis. HYP-04's status remains "
        "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED -- resolving these decisions "
        "clears display-gate condition C4 only."
    )
    doc["supersedes_sha256"] = _sha256(v1_1)
    changes.append(f"registry_version 1.1 -> 1.2, authored_at_utc {date}")

    entry = next(
        (h for h in doc.get("hypotheses", []) if h.get("hypothesis_id") == HYPOTHESIS_ID),
        None,
    )
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not present in {v1_1.name}")

    ledger = entry.get("unresolved_analysis_decisions")
    if not isinstance(ledger, list) or not ledger:
        raise RefusedError(
            f"{HYPOTHESIS_ID}'s decision ledger is missing or empty in "
            f"{v1_1.name} -- nothing to resolve, which is not an expected state"
        )

    source_ledger_len = len(
        next(h for h in src["hypotheses"] if h["hypothesis_id"] == HYPOTHESIS_ID)
        ["unresolved_analysis_decisions"]
    )

    for d in ledger:
        if d.get("state") != PENDING_TOKEN:
            changes.append(
                f"LEFT ALONE (not pending): {str(d.get('decision'))[:60]!r}"
            )
            continue
        d["state"] = RESOLVED_TOKEN
        d[RESOLVED_BY_FIELD] = lock_ref
        changes.append(f"resolved: {str(d.get('decision'))[:60]!r}")

    # The ledger keeps every entry. Resolution is recorded by MARKING, never by
    # removing -- the display gate denies an emptied ledger for exactly that
    # reason. Checked with a raise rather than an assert, because `python -O`
    # strips asserts and this is a governance invariant, not a debug aid.
    if len(ledger) != source_ledger_len:
        raise RefusedError(
            f"decision ledger changed length ({source_ledger_len} -> "
            f"{len(ledger)}). Resolution must never add or remove a decision."
        )

    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.2 from v1.1 after the "
                    "HYP-04 analysis lock is signed."
    )
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.2 (default is a dry run)")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        print("\nNothing was written. Sign the lock first; see the lock's "
              "section 11 and the authorization template.")
        return 1

    doc, changes = build_v1_2()
    print("Preconditions met. Changes v1.1 -> v1.2:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_2.name}.")
        return 0

    before = _sha256(V1_1)
    V1_2.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    after = _sha256(V1_1)
    if before != after:
        raise RefusedError(
            "registry v1.1 changed on disk during generation -- it must remain "
            "byte-for-byte identical"
        )

    print(f"\nWrote {V1_2.name}")
    print(f"v1.1 unchanged, sha256 {after[:16]}...")
    print("\nSTILL REQUIRED -- C4 will not clear until these are repointed:")
    for p in PINS_V1_1:
        print(f"  * {p}")
    print("\nThen re-run test_hyp04_supply_chain_hedge_registry_v1_2_artifact.py:"
          "\n  its two SKIPs must become passes. If they still skip, this file "
          "was not written where that suite looks for it.")
    print("\nThe gate stays CLOSED regardless: C4 clears, C1/C2/C3/C5 do not.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
