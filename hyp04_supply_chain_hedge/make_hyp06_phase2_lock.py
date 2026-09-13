#!/usr/bin/env python3
"""HYP-06's Phase 2 preregistration lock -- target, model spec, and the
exact locked (peer, anchor-event) set. Mirrors HYP-05's own
`make_hyp05_phase2_lock.py` in SHAPE (an inert draft, blank owner fields,
a human declares it) but is NOT that module modified: HYP-05's lock is
tied to its own single (AMBA, NVDA) pair; HYP-06's is a real, multi-peer,
multi-anchor universe and should not be squeezed into that shape.

=== THE EVENT SET IS DERIVED, NOT HAND-TYPED ===

The locked (peer, anchor-event) pairs are read directly from the already-
committed `HYP05_PEER_UNIVERSE_SCALED_2026-09-13.json` (qualifications
where `qualifies` is true), cross-joined against WHICHEVER of the three
anchor-shocks CSVs actually carries that row's anchor_ticker (HYP-04's
own 7-anchor file, plus round 5's and round 6's additional-anchor files --
never merged, read side by side, same as run_hyp05_peer_market_cap.py's
own multi-CSV `_anchor_event_dates()`). `build_draft` asserts the derived
count is exactly 778 and refuses otherwise, since a different count would
mean an upstream artifact changed since this module was written.

=== SAMPLE SIZE: THIS TIME, THE FLOOR IS CLEARED, NOT MISSED ===

HYP-05's own lock disclosed its 8 events as ~24x SHORT of the provisional
195-event floor. HYP-06's 778 qualifying pairs are roughly 4x OVER that
same provisional floor (`HYP06_SAMPLE_SIZE_GATE_2026-09-13.md`) -- the
first hypothesis in this project's supply-chain-hedge line whose real,
discovered sample clears its own governance floor rather than falling
short of it. Framed EXPLORATORY still (`is_primary_confirmatory=False`
in the registry, since the floor itself remains provisional -- see the
sample-size gate doc), not CONFIRMATORY -- clearing a provisional floor
is not the same claim as clearing a measured one.

=== MODEL SPEC: REUSED FROM HYP-05's OWN LOCK, VERBATIM ===

Target definition, clustering choice (event_id primary, calendar_period
secondary robustness lens), residualization, permutation count and seed
are all read from HYP-05's OWN signed Phase 2 lock
(`HYP05_PHASE2_LOCK_2026-09-12.json`) rather than re-typed, so a future
edit to that file's values cannot silently diverge from what this lock
actually reuses.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .make_freeze_draft import _commit_sha, _sha256

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"
TARGET_PY = Path(__file__).resolve().parent / "target.py"
CONSTANTS_PY = Path(__file__).resolve().parent / "constants.py"
CLUSTERED_SE_PY = Path(__file__).resolve().parent / "clustered_se.py"

AS_OF = "2026-09-13"
OUT_JSON = LSE / f"HYP06_PHASE2_LOCK_{AS_OF}.json"

PEER_UNIVERSE_JSON = LSE / "HYP05_PEER_UNIVERSE_SCALED_2026-09-13.json"
ANCHOR_SHOCKS_CSVS = (
    LSE / "HYP04_ANCHOR_SHOCKS_2026-08-31.csv",
    LSE / "HYP05_ADDITIONAL_ANCHOR_SHOCKS_2026-09-12.csv",
    LSE / "HYP05_ADDITIONAL_ANCHOR_SHOCKS_2026-09-13.csv",
)
HYP05_PHASE2_LOCK_JSON = LSE / "HYP05_PHASE2_LOCK_2026-09-12.json"

EXPECTED_N_EVENTS = 778

#: Reused from HYP-05's own re-decided clustering, read from its signed
#: lock rather than re-typed -- see build_draft().
PRIMARY_CLUSTER_KEY = "event_id"
SECONDARY_CLUSTER_KEY = "calendar_period"

SAMPLE_SIZE_GATE_MD = LSE / "HYP06_SAMPLE_SIZE_GATE_2026-09-13.md"
PROVISIONAL_FLOOR_PAIRS = 195

#: Fields a human must supply. Blank on every draft; that is what makes a
#: draft inert.
OWNER_FIELDS = ("declared", "declared_by", "declared_date")


class Phase2LockError(RuntimeError):
    """A precondition does not hold. Never a bare `assert` -- see
    make_hyp05_phase2_lock.Phase2LockError's identical reasoning."""


def _all_shock_rows(paths: tuple[Path, ...]) -> dict[tuple[str, str], dict[str, Any]]:
    """{(anchor_ticker, release_date): row} across every CSV, for rows
    with status == shock_computed. Refuses (via a KeyError surfaced by
    the caller) rather than silently picking one file over another if a
    key ever appeared in two -- checked explicitly below."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    dupes: list[tuple[str, str]] = []
    for p in paths:
        with p.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row["status"] != "shock_computed":
                    continue
                key = (row["anchor_ticker"], row["release_date"])
                if key in out:
                    dupes.append(key)
                out[key] = row
    if dupes:
        raise Phase2LockError(
            f"{len(dupes)} (anchor_ticker, release_date) key(s) appear in "
            f"more than one anchor-shocks CSV: {dupes[:5]}... The three "
            "files are supposed to be disjoint by anchor; re-examine "
            "before trusting either value.")
    return out


def _locked_events(peer_universe_path: Path,
                   anchor_shocks_paths: tuple[Path, ...]) -> list[dict[str, Any]]:
    """The exact (peer, anchor-event) rows this lock fixes -- derived from
    already-committed artifacts, never hand-typed."""
    universe = json.loads(peer_universe_path.read_text(encoding="utf-8"))
    shocks = _all_shock_rows(anchor_shocks_paths)

    events: list[dict[str, Any]] = []
    for q in universe["qualifications"]:
        if not q["qualifies"]:
            continue
        cand = q["evidence"]["candidate"]
        key = (cand["anchor_ticker"], cand["anchor_event_date"])
        row = shocks.get(key)
        if row is None:
            raise Phase2LockError(
                f"qualifying pair {q['ticker']}/{key} has no matching "
                "shock_computed row in any anchor-shocks CSV -- the "
                "universe artifact and the shocks files have drifted "
                "apart")
        events.append({
            "event_id": row["event_id"],
            "anchor_ticker": cand["anchor_ticker"],
            "peer_ticker": q["ticker"],
            "relationship_type": cand["relationship_type"],
            "as_of_date": cand["as_of_date"],
            "release_date": row["release_date"],
            "attributed_session": row["attributed_session"],
            "shock": float(row["shock"]),
        })
    return events


def build_draft(*, out_path: Path = OUT_JSON,
                peer_universe_path: Path = PEER_UNIVERSE_JSON,
                anchor_shocks_paths: tuple[Path, ...] = ANCHOR_SHOCKS_CSVS,
                hyp05_phase2_lock_path: Path = HYP05_PHASE2_LOCK_JSON,
                repo: Path = REPO_ROOT,
                today: Optional[date] = None) -> dict[str, Any]:
    when = today or date.today()

    if out_path.exists():
        raise Phase2LockError(
            f"{out_path.name} already exists. A second lock would make the "
            "first unfalsifiable, and re-deriving one after seeing a "
            "result is exactly the tuning this document exists to rule "
            "out. Delete it deliberately if it was never signed.")

    for label, p in (
        ("peer universe", peer_universe_path),
        *[(f"anchor shocks ({p.name})", p) for p in anchor_shocks_paths],
        ("HYP-05's own signed Phase 2 lock", hyp05_phase2_lock_path),
        ("sample-size gate", SAMPLE_SIZE_GATE_MD),
    ):
        if not p.is_file():
            raise Phase2LockError(f"no {label} at {p}")

    hyp05_lock = json.loads(hyp05_phase2_lock_path.read_text(encoding="utf-8"))
    if hyp05_lock.get("declared") is not True:
        raise Phase2LockError(
            f"{hyp05_phase2_lock_path.name} is not a SIGNED lock -- "
            "refusing to reuse an undeclared draft's model spec.")

    events = _locked_events(peer_universe_path, anchor_shocks_paths)
    if len(events) != EXPECTED_N_EVENTS:
        raise Phase2LockError(
            f"derived {len(events)} qualifying (peer, anchor-event) "
            f"row(s), expected exactly {EXPECTED_N_EVENTS}. An upstream "
            "artifact has changed since this module was written -- "
            "re-examine the derivation rather than trusting a different "
            "count.")

    locked_peers = sorted({e["peer_ticker"] for e in events})
    locked_anchors = sorted({e["anchor_ticker"] for e in events})

    sha = _commit_sha(repo)  # refuses on a dirty tree

    hyp05_target = hyp05_lock["target_definition"]
    hyp05_model = hyp05_lock["model_spec"]

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-06",
        "what_this_is": (
            "The Phase 2 preregistration lock: the exact locked (peer, "
            "anchor-event) set, target definition, and model spec, fixed "
            "before any target/outcome value has been computed for any "
            "peer around any locked anchor event. See "
            "'LOOK-AHEAD DISCLOSURE' below for exactly what has and has "
            "not already been touched."),
        "what_this_is_not": (
            "Not a result, not the one locked run (a separate, later, "
            "not-yet-built module), and not permission to compute "
            "anything. It constrains what that later, separate, "
            "explicitly-authorized run may do; it performs none. No "
            "Phase 3 authorization has been drafted, requested, or "
            "signed for HYP-06 as of this lock -- that is a distinct, "
            "later, separately-authorized decision this document does "
            "not make."),
        "governing_documents": {
            "hyp05_phase2_lock_shape": "make_hyp05_phase2_lock.py "
                                       "(mirrored in shape, not modified)",
            "hyp05_phase2_lock_reused": hyp05_phase2_lock_path.name,
            "sample_size_gate": SAMPLE_SIZE_GATE_MD.name,
            "model_plan": "HYP06_ScaledSupplyChainRelationshipLag_MODEL_"
                          "PLAN_2026-09-13.md",
            "registry_entry": "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.16."
                              "json, hypothesis_id=HYP-06",
        },
        "pins": {
            "peer_universe": peer_universe_path.name,
            "peer_universe_sha256": _sha256(peer_universe_path),
            "anchor_shocks": [p.name for p in anchor_shocks_paths],
            "anchor_shocks_sha256": [_sha256(p) for p in anchor_shocks_paths],
            "hyp05_phase2_lock": hyp05_phase2_lock_path.name,
            "hyp05_phase2_lock_sha256": _sha256(hyp05_phase2_lock_path),
            "target_py_sha256": _sha256(TARGET_PY),
            "constants_py_sha256": _sha256(CONSTANTS_PY),
            "clustered_se_py_sha256": _sha256(CLUSTERED_SE_PY),
            "lock_declared_at_commit": sha,
        },
        "locked_peers": locked_peers,
        "locked_anchors": locked_anchors,
        "locked_events": events,
        "n_locked_events": len(events),
        "n_locked_peers": len(locked_peers),
        "n_locked_anchors": len(locked_anchors),
        "target_definition": {
            **hyp05_target,
            "source": "HYP-05's own signed Phase 2 lock's target_definition, "
                      "reused verbatim, not re-derived.",
        },
        "model_spec": {
            **hyp05_model,
            "source": "HYP-05's own signed Phase 2 lock's model_spec, "
                      "reused verbatim, not re-derived.",
        },
        "sample_size_disclosure": {
            "n_locked_events": len(events),
            "n_peers": len(locked_peers),
            "n_anchors": len(locked_anchors),
            "provisional_operative_floor_pairs": PROVISIONAL_FLOOR_PAIRS,
            "floor_source": SAMPLE_SIZE_GATE_MD.name,
            "framing": "EXPLORATORY, FLOOR CLEARED (provisional floor)",
            "why": (
                f"{len(events)} locked (peer, event) pairs clears the "
                f"provisional {PROVISIONAL_FLOOR_PAIRS}-pair floor by "
                f"{len(events) / PROVISIONAL_FLOOR_PAIRS:.1f}x -- unlike "
                "HYP-05's own 8-event pilot, which fell ~24x short. Still "
                "framed exploratory, not confirmatory: the floor itself "
                "remains PROVISIONAL (borrowed, not measured against "
                "HYP-06's own design) -- see HYP06_SAMPLE_SIZE_GATE_"
                "2026-09-13.md."),
        },
        "look_ahead_disclosure": {
            "already_touched": (
                "Every locked peer's raw close prices (auto_adjust=False) "
                "were fetched and used ONLY to compute point-in-time "
                "MARKET CAP for PS-1..PS-4 eligibility screening in "
                "run_hyp05_peer_market_cap.py (committed b3983ba). That "
                "computation never touched any peer's returns, realized "
                "variance, or any quantity resembling this hypothesis's "
                "target measure. Relationship direction (customer/"
                "supplier) was hand-corrected from filing text during "
                "round-6 review, which also never touches return data."),
            "not_touched": (
                "No log return, no realized-variance ratio, and no "
                "residualized target value has been computed for any "
                "locked peer around any locked anchor event, at any "
                "horizon, before this lock. This lock is written before "
                "that computation happens for the first time."),
        },
        "opens_no_gate": (
            "This is a computed HYP-06 Phase 2 lock, not a freeze, not a "
            "registry change, not a linkage ratification. It moves no "
            "gate condition, whatever the gate reads at the moment this "
            "file is read."),
        # Blank on purpose. See OWNER_FIELDS.
        "declared": False,
        "declared_by": "",
        "declared_date": "",
        "owner_fields": list(OWNER_FIELDS),
        "how_to_complete": (
            "python -m hyp04_supply_chain_hedge.ratify_hyp06 phase2 --template"),
        "status": "DRAFT -- inert until declared",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def load_declared_phase2_lock(path: Path) -> dict[str, Any]:
    """Read a SIGNED lock. Refuses a draft."""
    if not path.is_file():
        raise Phase2LockError(f"no HYP-06 Phase 2 lock at {path}")
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("declared") is not True:
        raise Phase2LockError(
            f"{path.name} is a draft: 'declared' is not true. An "
            "undeclared lock fixes nothing.")
    for f in ("declared_by", "declared_date"):
        if not str(d.get(f) or "").strip():
            raise Phase2LockError(
                f"{f!r} is blank; an unattributed declaration is not a "
                "declaration")
    return d


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Write an INERT HYP-06 Phase 2 preregistration lock.")
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print without writing")
    a = ap.parse_args(argv)

    import tempfile
    if a.dry_run:
        with tempfile.TemporaryDirectory() as td:
            doc = build_draft(out_path=Path(td) / "p2.json")
    else:
        doc = build_draft(out_path=a.out)

    print(f"locked peers  ({doc['n_locked_peers']}): {doc['locked_peers']}")
    print(f"locked anchors({doc['n_locked_anchors']}): {doc['locked_anchors']}")
    print(f"n_locked_events    : {doc['n_locked_events']}")
    print(f"primary cluster key   : {doc['model_spec']['primary_cluster_key']}")
    print(f"secondary (robustness): "
          f"{doc['model_spec']['secondary_cluster_key_robustness_lens']}")
    print(f"sample-size framing   : {doc['sample_size_disclosure']['framing']}")
    print(f"\nBLANK, and this module will not fill them: "
          + ", ".join(doc["owner_fields"]))

    if a.dry_run:
        print("\nDRY RUN -- nothing written.")
    else:
        print(f"\nWROTE {doc['artifact']}  (INERT -- 'declared' is false)")
        print("Next: python -m hyp04_supply_chain_hedge.ratify_hyp06 "
              "phase2 --template")
    return 0


if __name__ == "__main__":
    sys.exit(main())
