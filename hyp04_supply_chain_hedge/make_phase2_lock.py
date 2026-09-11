#!/usr/bin/env python3
"""The HYP-04 Phase 2 preregistration lock -- target, feature set, model spec.

=== WHY THIS EXISTS ===

Plan v0.2 section 5.3: "Phase 2 -- Preregistration lock. Freeze target
definition, feature set, model spec, and validation split in a dated lock
before touching the holdout." The D1-D10 analysis lock's own
`scope.does_not_fix` names exactly those items -- `does_not_fix: ["target
definition", "feature set", "model specification", "validation split"]` --
because Phase 1 had not run when it was written. It has now (Phase 1's
diagnostic, `HYP04_INFERENCE_PHASE1_2026-09-10.json`, ranged over the
EXPLORATION set only). This module fixes the three still-open items.
`validation split` is already closed -- see `make_validation_split.py`,
Phase 1 step 1 -- and is REFERENCED here, not re-declared.

=== MOSTLY RESTATING, NOT NEWLY CHOOSING ===

Most of what this lock fixes is already decided elsewhere and this module's
job is to PIN it, not invent it:

  - The target formula, the h=1..20 grid, and residualization being
    UNCONDITIONAL (not optional) all come from plan section 3.2 -- already
    implemented in `target.py`, hash-pinned here so future drift is caught.
  - The estimator (LP + CR2/Satterthwaite + max-T permutation) and the
    cluster key (`calendar_period`) come from the D1-D10 analysis lock,
    referenced by name, not restated.

What this module actually DECIDES, because nothing upstream had:

  - The feature set. Plan section 3.4 names five candidate features; only
    two are built (`_design_matrix` in `inference.py`: shock magnitude and
    days-to-peer-earnings). Locked as-built; the other three are named
    below as a stated, documented deviation -- not silently dropped, not
    built here.
  - A real bug found while scoping this lock: `estimate_earnings_cycle_
    baseline` computed "days to own earnings" by scanning forward with no
    lower bound, so an event before a peer's own first recorded earnings
    (confirmed for BB, whose earliest release is 2020-04-01; 384 of 2874
    rows in the committed Phase 1 diagnostic) got residualized against a
    baseline blended from the peer's history AFTER that point. Fixed
    generally in `target.py` (see `EarningsCycleBaseline.
    has_earnings_history_at`) before this lock was written -- the fix is
    part of what gets pinned, not a separate footnote.

=== WHAT THIS MODULE WILL NOT DO ===

It does not run the pipeline over the holdout. It does not compute or
declare a result -- `Phase3`, later, is the one locked run. It does not
sign -- like `make_freeze_draft` and `make_validation_split`, it writes an
inert draft with the owner's fields blank; `ratify phase2` fills them.

=== THE REFUSAL ===

A result artifact whose declared `event_ids_consumed` overlaps the
HOLDOUT ids blocks this lock -- the holdout must still be untouched when
Phase 2 is written. One that stays within the exploration ids (Phase 1's
own diagnostic; its `event_ids_consumed` is exactly the 157 exploration
ids) does not block it. Reuses `_overlapping_results` /
`_declared_scope` from `make_freeze_draft.py` rather than a second
implementation, keyed against the holdout ids instead of the full frozen
set.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .constants import (
    ANCHOR_ADJACENT_EXCLUSION_TRADING_DAYS,
    HORIZON_GRID,
    LOCKED_CLUSTER_KEY,
    MIN_BUCKET_COUNT,
    MIN_RETAINED_HISTORY_FRACTION,
    N_PERMUTATIONS,
    RANDOM_SEED,
)
from .make_freeze_draft import (
    RESULT_ARTIFACT_PATTERNS,
    _commit_sha,
    _overlapping_results,
    _scan_for_results,
    _sha256,
)
from .make_validation_split import load_declared_split
from .make_validation_split import OUT_JSON as DEFAULT_SPLIT_PATH

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"
TARGET_PY = Path(__file__).resolve().parent / "target.py"
CONSTANTS_PY = Path(__file__).resolve().parent / "constants.py"

AS_OF = "2026-09-10"
OUT_JSON = LSE / f"HYP04_PHASE2_LOCK_{AS_OF}.json"

#: Fields a human must supply. Blank on every draft; that is what makes a
#: draft inert.
OWNER_FIELDS = ("declared", "declared_by", "declared_date")

#: The feature set as actually built -- `_design_matrix` in inference.py.
#: Column 0 is always the intercept; these are what follow it.
FEATURE_SET = ("shock_magnitude", "days_to_peer_earnings")

#: Plan section 3.4 names five candidates. These three are not implemented.
#: Named here so the gap is a stated deviation, not a silent one.
DEFERRED_FEATURES = (
    {
        "name": "peer_anchor_correlation_beta",
        "reason": ("requires new computation over historical peer/anchor "
                   "return series; nothing in the current inference layer "
                   "produces it"),
    },
    {
        "name": "relationship_type",
        "reason": ("the data already exists on every curated linkage edge "
                   "(CuratedEdge.relationship_type) and would be cheap to "
                   "read, but wiring it into the regression -- dummy or "
                   "interaction terms -- is unexercised code with no "
                   "end-to-end run behind it; deferred rather than locking "
                   "a path that has never actually run"),
    },
    {
        "name": "peer_coverage_thinness_proxy",
        "reason": ("needs GST/GDELT infrastructure integration; nothing in "
                   "hyp04_supply_chain_hedge currently touches that data "
                   "source"),
    },
)


class Phase2LockError(RuntimeError):
    """A precondition does not hold.

    Phase2LockError, never a bare `assert`: `python -O` strips asserts, and
    a precondition that vanishes under an optimisation flag is not one.
    """


def build_draft(*, out_path: Path, split_path: Path = DEFAULT_SPLIT_PATH,
                lse: Path = LSE, repo: Path = REPO_ROOT,
                today: Optional[date] = None) -> dict[str, Any]:
    """Everything derivable, derived and stated -- not just hashed."""
    when = today or date.today()

    if out_path.exists():
        raise Phase2LockError(
            f"{out_path.name} already exists. A second lock would make the "
            "first unfalsifiable, and re-deriving one after seeing a "
            "diagnostic is exactly the tuning this document exists to rule "
            "out. Delete it deliberately if it was never signed.")

    # The split must already be SIGNED -- an inert draft constrains nothing,
    # and this lock's holdout-overlap refusal below needs real holdout ids,
    # not a draft's blank ones.
    split = load_declared_split(split_path)
    exploration_ids = set(split["exploration"]["event_ids"])
    holdout_ids = set(split["holdout"]["event_ids"])

    # ORDER. The holdout must still be untouched when this is written. A
    # result that stayed within exploration (Phase 1's own diagnostic) does
    # not block; one that touched the holdout, or that will not say what it
    # ranged over, does.
    existing = _scan_for_results(lse)
    blocking = _overlapping_results(existing, holdout_ids, lse=lse)
    if blocking:
        raise Phase2LockError(
            f"result artifact(s) touch the HOLDOUT ({'; '.join(blocking[:4])}). "
            "Phase 2 orders the lock BEFORE the holdout is touched; writing "
            "one now would record an order that did not happen. Patterns "
            f"scanned: {', '.join(RESULT_ARTIFACT_PATTERNS)}.")

    sha = _commit_sha(repo)  # refuses on a dirty tree

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-04",
        "what_this_is": (
            "The Phase 2 preregistration lock: target definition, feature "
            "set, and model spec, fixed before the holdout is touched. "
            "Validation split is referenced, not re-declared -- it was "
            "already fixed at Phase 1 step 1."),
        "what_this_is_not": (
            "Not a result, not Phase 3's one real holdout run, and not "
            "permission to compute anything against the holdout. It "
            "constrains what that later, separate, explicitly-authorized "
            "run may do; it performs none."),
        "governing_documents": {
            "plan": "HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md section 5.3",
            "analysis_lock": "GST_HYP04_ANALYSIS_LOCK_v1.0.json",
            "which_decisions": (
                "target definition, feature set, model specification -- the "
                "three items GST_HYP04_ANALYSIS_LOCK_v1.0.json's own "
                "scope.does_not_fix names"),
        },
        "pins": {
            "validation_split": Path(split_path).name,
            "validation_split_sha256": _sha256(Path(split_path)),
            "target_py_sha256": _sha256(TARGET_PY),
            "constants_py_sha256": _sha256(CONSTANTS_PY),
            "lock_declared_at_commit": sha,
            "exploration_event_count": len(exploration_ids),
            "holdout_event_count": len(holdout_ids),
        },
        "target_definition": {
            "formula": (
                "RVar(h) = (1/h) * sum_{i=1..h} r_i^2 over [t+1, t+h]; "
                "RVar_ref = (1/20) * sum r_i^2 over the trailing 20 sessions "
                "ending at the anchor's earnings date; raw = log(RVar(h)) - "
                "log(RVar_ref); target = raw - earnings_cycle_baseline(peer, "
                "days_to_own_earnings)"),
            "horizon_grid": list(HORIZON_GRID),
            "residualization": (
                "REQUIRED, not optional -- section 3.2's own definition "
                "subtracts earnings_cycle_baseline unconditionally. Phase "
                "1's unresidualized_sensitivity treatment was an ad hoc "
                "diagnostic aid for the BB coverage question, never a "
                "preregistered alternate spec, and is not carried forward "
                "here."),
            "min_bucket_count": MIN_BUCKET_COUNT,
            "min_retained_history_fraction": MIN_RETAINED_HISTORY_FRACTION,
            "anchor_adjacent_exclusion_trading_days":
                ANCHOR_ADJACENT_EXCLUSION_TRADING_DAYS,
            "pre_earnings_history_exclusion": (
                "an observation before a peer's own first recorded earnings "
                "release is excluded from both baseline fitting and "
                "application, never extrapolated backward. Fixed in "
                "target.py while scoping this lock -- see "
                "EarningsCycleBaseline.has_earnings_history_at -- and pinned "
                "here as part of the locked spec, not a separate footnote."),
            "source": "target.py, hash-pinned above",
        },
        "feature_set": {
            "locked": list(FEATURE_SET),
            "source": "_design_matrix in inference.py",
            "deferred_candidates": [dict(f) for f in DEFERRED_FEATURES],
            "deviation_from_plan": (
                "plan section 3.4 names five candidate features; only the "
                "two above are implemented and locked. The other three are "
                "named as a stated, documented deviation -- not silently "
                "dropped, not built for this lock."),
        },
        "model_spec": {
            "estimator": (
                "local projections with CR2 clustered standard errors, "
                "Satterthwaite degrees of freedom, and max-T permutation "
                "multiplicity correction -- fixed by the D1-D10 analysis "
                "lock and referenced here, not restated"),
            "analysis_lock": "GST_HYP04_ANALYSIS_LOCK_v1.0.json",
            "cluster_key": LOCKED_CLUSTER_KEY,
            "residualize": True,
            "n_permutations": N_PERMUTATIONS,
            "random_seed": RANDOM_SEED,
        },
        "validation_split": {
            "referenced_not_redeclared": True,
            "exploration_event_count": len(exploration_ids),
            "holdout_event_count": len(holdout_ids),
        },
        "smoke_test": (
            "validate_phase2_lock() re-runs the locked pipeline over the "
            "EXPLORATION set only and confirms it reproduces this lock's own "
            "declared feature set, cluster key, and hash pins -- a "
            "tamper/drift check, never a result, and it never touches the "
            "holdout."),
        "opens_no_gate": (
            "This is a computed Phase 2 lock, not a freeze, not a registry "
            "change, not a linkage ratification. It moves no gate condition, "
            "whatever the gate reads at the moment this file is read."),
        # Blank on purpose. See OWNER_FIELDS.
        "declared": False,
        "declared_by": "",
        "declared_date": "",
        "owner_fields": list(OWNER_FIELDS),
        "how_to_complete": (
            "python -m hyp04_supply_chain_hedge.ratify phase2 --template"),
        "status": "DRAFT -- inert until declared",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def load_declared_phase2_lock(path: Path) -> dict[str, Any]:
    """Read a SIGNED lock. Refuses a draft.

    Mirrors `make_validation_split.load_declared_split`: an unsigned
    document must not answer "what is locked", or a run could proceed
    against a spec nobody committed to.
    """
    if not path.is_file():
        raise Phase2LockError(f"no Phase 2 lock at {path}")
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("declared") is not True:
        raise Phase2LockError(
            f"{path.name} is a draft: 'declared' is not true. An undeclared "
            "lock fixes nothing.")
    for f in ("declared_by", "declared_date"):
        if not str(d.get(f) or "").strip():
            raise Phase2LockError(
                f"{f!r} is blank; an unattributed declaration is not a "
                "declaration")
    return d


def validate_phase2_lock(path: Path, *, panel_path: Optional[Path] = None,
                         split_path: Optional[Path] = None,
                         peer_earnings_path: Optional[Path] = None,
                         lse: Path = LSE,
                         n_permutations: int = 200,
                         seed: int = RANDOM_SEED) -> dict[str, Any]:
    """The plan's own required smoke test: run the locked pipeline against
    in-sample (exploration) data only, and confirm it reproduces the exact
    frozen spec -- a tamper/drift check, never a result.

    `n_permutations` defaults far below the locked model spec's 2000: this
    function checks structural fidelity to the declared spec (feature
    columns, cluster key, hash pins), not inference validity, so it is
    deliberately cheap to run. The locked value of 2000 is what a real
    Phase 3 run would use, and is asserted to equal what this lock declares
    -- not substituted here.

    `lse` is where the pinned calendar/shocks/map/peer-closes/freeze
    actually live -- NOT necessarily `panel_path`'s or `split_path`'s
    directory. Left as an explicit parameter, not derived, after the exact
    same mistake (`out_path.parent` standing in for the real data directory)
    was found and fixed in `make_phase1_diagnostics.build_diagnostics`.
    """
    from . import make_phase1_diagnostics as P

    lock = load_declared_phase2_lock(path)

    for label, pinned_path, pinned_hash in (
        ("target.py", TARGET_PY, lock["pins"]["target_py_sha256"]),
        ("constants.py", CONSTANTS_PY, lock["pins"]["constants_py_sha256"]),
    ):
        current = _sha256(pinned_path)
        if current != pinned_hash:
            raise Phase2LockError(
                f"{label} has changed since the lock was declared "
                f"(pinned {pinned_hash[:12]}, now {current[:12]}). The lock "
                "no longer describes the code that would run -- re-derive "
                "and re-declare rather than running against drift.")

    default_split = split_path or DEFAULT_SPLIT_PATH
    split = load_declared_split(Path(default_split))
    if _sha256(Path(default_split)) != lock["pins"]["validation_split_sha256"]:
        raise Phase2LockError(
            "the validation split on disk does not match this lock's pinned "
            "hash. The split has changed since the lock was declared.")

    panel_path = panel_path or P.DEFAULT_PANEL
    peer_earnings_path = peer_earnings_path or P.DEFAULT_PEER_EARNINGS
    j = P._rejoin(panel_path=panel_path, split_path=Path(default_split),
                 freeze_path=None, lse=lse)

    exploration_events = [ev for ev in j["panel_pair"].anchor_events
                          if ev["peers"]]
    peers_used = sorted({p for ev in exploration_events for p in ev["peers"]})
    peer_earnings_days, _cov = P._attribute_peer_earnings(
        peer_earnings_path, j["idx"], peers=peers_used)

    import numpy as np
    from .fixtures import SyntheticPanel

    returns = {
        p: np.array([np.nan if r is None else r
                    for r in j["series"][p].log_returns], dtype=float)
        for p in peers_used
    }
    anchor_events = [
        {
            "anchor": ev["anchor"],
            "anchor_day": j["pos"][j["attributed"][ev["event_id"]]],
            "shock": j["shocks"][ev["event_id"]].shock,
            "peers": ev["peers"],
            "calendar_period": P._calendar_period_int(ev["event_id"]),
        }
        for ev in exploration_events
    ]
    synth = SyntheticPanel(
        name="hyp04-phase2-lock-smoke-test", returns=returns,
        peer_earnings_days=peer_earnings_days, anchor_events=anchor_events,
        n_trading_days=len(j["idx"]), injected_lag=None, injected_effect=0.0,
        injected_effect_window=0, peer_base_vol={},
        earnings_ramp_amplitude=0.0, truth={"real_data": True})

    result = P._run_treatment(
        synth, residualize=lock["model_spec"]["residualize"],
        cluster_key=lock["model_spec"]["cluster_key"],
        n_permutations=n_permutations, seed=seed)

    if result["n_rows"] <= 0:
        raise Phase2LockError(
            "the locked pipeline produced zero rows over the exploration "
            "set -- the smoke test must actually exercise the pipeline, not "
            "pass vacuously")

    holdout_ids = set(split["holdout"]["event_ids"])
    used_ids = {ev["event_id"] for ev in exploration_events}
    if used_ids & holdout_ids:
        raise Phase2LockError(
            "the smoke test's own rejoin touched holdout event id(s) -- "
            "refusing to report success")

    return {
        "reproduces_declared_spec": True,
        "n_rows": result["n_rows"],
        "cluster_key_used": lock["model_spec"]["cluster_key"],
        "residualize_used": lock["model_spec"]["residualize"],
        "n_exploration_events_used": len(used_ids),
        "target_py_sha256_matched": True,
        "constants_py_sha256_matched": True,
        "validation_split_sha256_matched": True,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Write an INERT Phase 2 preregistration lock.")
    ap.add_argument("--split", type=Path, default=DEFAULT_SPLIT_PATH)
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print without writing")
    a = ap.parse_args(argv)

    import tempfile
    if a.dry_run:
        with tempfile.TemporaryDirectory() as td:
            doc = build_draft(out_path=Path(td) / "p2.json",
                              split_path=a.split)
    else:
        doc = build_draft(out_path=a.out, split_path=a.split)

    print(f"target definition : {doc['target_definition']['formula'][:60]}...")
    print(f"feature set        : {doc['feature_set']['locked']}")
    print(f"deferred candidates: "
          f"{[f['name'] for f in doc['feature_set']['deferred_candidates']]}")
    print(f"model spec         : cluster_key={doc['model_spec']['cluster_key']} "
          f"residualize={doc['model_spec']['residualize']} "
          f"n_permutations={doc['model_spec']['n_permutations']}")
    print(f"validation split   : {doc['validation_split']['exploration_event_count']} "
          f"exploration / {doc['validation_split']['holdout_event_count']} holdout")
    print(f"\nBLANK, and this module will not fill them: "
          + ", ".join(doc["owner_fields"]))

    if a.dry_run:
        print("\nDRY RUN -- nothing written.")
    else:
        print(f"\nWROTE {doc['artifact']}  (INERT -- 'declared' is false)")
        print("Next: python -m hyp04_supply_chain_hedge.ratify phase2 --template")
    return 0


if __name__ == "__main__":
    sys.exit(main())
