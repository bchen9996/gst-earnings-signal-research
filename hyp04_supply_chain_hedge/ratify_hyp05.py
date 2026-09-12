#!/usr/bin/env python3
"""HYP-05's own ratification driver -- phase2 (declare the lock) and phase3
(authorize the one run). Scoped ONLY to HYP-05's two artifacts.

=== WHY A SEPARATE MODULE, NOT ratify.py EXTENDED ===

`ratify.py`'s own module docstring ties it to HYP-04's specific chain (map,
panel, attest, split, phase2, phase3, pins, gate) and HYP-04's own registry/
freeze/holdout machinery. HYP-05 has no map to ratify, no panel to rebuild,
no freeze to attest, and no HYP-04-style holdout split (see
`make_hyp05_phase2_lock.py`'s own docstring for why that split does not
transfer to a single (peer, anchor) pair). Adding HYP-05-shaped subcommands
onto `ratify.py`'s `main()` would tangle two independent chains behind one
CLI for no benefit -- this module borrows `ratify.py`'s PROVEN mechanics
(`_reject_placeholder`, `_iso`, `RatifyError` -- including the 2026-09-10
angle-bracket placeholder fix) by IMPORTING them directly, not copying them,
so a future fix to either lands at both call sites.

=== THE TWO SIGNATURES ===

  phase2  declares `make_hyp05_phase2_lock.py`'s draft -- fixes target
          definition, model spec, and the locked 8-event set BEFORE AMBA's
          outcome data has been computed. Mirrors `ratify.py`'s own
          `phase2` exactly in shape.
  phase3  authorizes the ONE run of `make_hyp05_phase3_run.py` -- typed
          BEFORE any real computation happens, exactly as HYP-04's own
          `phase3` requires. Not resumable, not repeatable:
          `make_hyp05_phase3_run.py` marks this consumed the instant a real
          run succeeds.

Neither writes a result. Neither opens a gate. Both are the repo owner's
signature on a document someone else already computed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .ratify import RatifyError, _iso, _reject_placeholder

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

#: Typed verbatim or the declaration does not happen -- same discipline as
#: ratify.py's own AFFIRMATION constants, and for the same reason: a
#: sentence, not a flag, because `--yes` can be typed without reading it.
HYP05_PHASE2_AFFIRMATION = (
    "HYP-05's Phase 2 lock -- target definition, model spec, and the "
    "locked 8-event (AMBA, NVDA) set -- was fixed before any return, "
    "realized-variance, or target value was computed for AMBA around any "
    "NVDA event. AMBA's raw closes were touched only to compute "
    "point-in-time market cap for peer-eligibility screening, never its "
    "returns or outcome.")

HYP05_PHASE3_AFFIRMATION = (
    "I authorize the one, single exploratory run of HYP-05's locked spec "
    "against AMBA's real returns around NVDA's 8 locked anchor events. I "
    "understand this sample is roughly 24x short of HYP-05's own 195-event "
    "provisional floor, that this cannot be undone or repeated, and that "
    "whatever the result, it will be reported as computed and explicitly "
    "labeled exploratory, not confirmatory.")

#: Fields declaring a Phase 2 lock may move. Everything else is derived.
PHASE2_FIELDS = ("declared", "declared_by", "declared_date", "status")


# --------------------------------------------------------------------------
# phase2 -- declare the lock
# --------------------------------------------------------------------------

def declare_phase2_lock(*, lock_path: Path, declared_by: str,
                        affirmation: str,
                        declared_date: Optional[str] = None
                        ) -> dict[str, Any]:
    """Fill the three owner fields on the HYP-05 Phase 2 lock. Nothing else
    moves."""
    from .make_hyp05_phase2_lock import (
        OWNER_FIELDS as PHASE2_OWNER_FIELDS,
        load_declared_phase2_lock,
    )

    if not lock_path.is_file():
        raise RatifyError(f"no HYP-05 Phase 2 lock at {lock_path}")
    declared_by = _reject_placeholder("--declared-by", declared_by)
    declared_date = _iso("--declared-date", declared_date)

    if (affirmation or "").strip() != HYP05_PHASE2_AFFIRMATION:
        raise RatifyError(
            "the affirmation does not match, so nothing was written.\n\n"
            "A lock is only a preregistration if it was fixed before "
            "AMBA's outcome was examined. Nothing in this repository can "
            "establish that, so type it exactly:\n\n"
            f'  --affirm "{HYP05_PHASE2_AFFIRMATION}"\n\n'
            "If you have looked at how AMBA's returns behave around these "
            "events, do not type it. The lock is then a description, and "
            "that is the finding.")

    before = json.loads(lock_path.read_text(encoding="utf-8"))
    if before.get("declared") is True:
        raise RatifyError(
            f"{lock_path.name} is already declared by "
            f"{before.get('declared_by')!r} on {before.get('declared_date')!r}. "
            "Re-declaring would overwrite the record Phase 3 cites.")
    for f in PHASE2_OWNER_FIELDS:
        if f not in before:
            raise RatifyError(
                f"{lock_path.name} has no {f!r} key; this does not look "
                "like a draft from make_hyp05_phase2_lock")

    after = dict(before)
    after["declared"] = True
    after["declared_by"] = declared_by
    after["declared_date"] = declared_date
    after["status"] = f"DECLARED -- by {declared_by} on {declared_date}"
    after["attestation_text"] = HYP05_PHASE2_AFFIRMATION

    moved = sorted(k for k in set(before) | set(after)
                   if before.get(k) != after.get(k))
    unexpected = [k for k in moved
                  if k not in PHASE2_FIELDS and k != "attestation_text"]
    if unexpected:
        raise RatifyError(
            f"declaring would move {unexpected}, which are derived fields. "
            "Refusing.")

    lock_path.write_text(json.dumps(after, indent=1) + "\n", encoding="utf-8")
    try:
        d = load_declared_phase2_lock(lock_path)
    except Exception:
        lock_path.write_text(json.dumps(before, indent=1) + "\n",
                             encoding="utf-8")
        raise
    return {
        "written": lock_path.name,
        "declared_by": declared_by,
        "declared_date": declared_date,
        "locked_peer": d["locked_peer"],
        "locked_anchor": d["locked_anchor"],
        "n_locked_events": d["n_locked_events"],
        "primary_cluster_key": d["model_spec"]["primary_cluster_key"],
    }


def _print_phase2_template() -> None:
    """One line, no continuations -- same rule as ratify.py's templates."""
    from .make_hyp05_phase2_lock import OUT_JSON
    print("Replace <your name>, then paste as ONE line:\n")
    print("  " + " ".join([
        "python -m hyp04_supply_chain_hedge.ratify_hyp05 phase2",
        '--declared-by "<your name>"',
        f'--affirm "{HYP05_PHASE2_AFFIRMATION}"']))
    p = OUT_JSON
    print(f"\nLock: {p.name if p.is_file() else '(none yet -- run '
                                               'make_hyp05_phase2_lock)'}")
    print("\nThis fixes target definition and model spec BEFORE AMBA's "
          "outcome is touched.\nPhase 3, later, is the one exploratory run "
          "against it.")


# --------------------------------------------------------------------------
# phase3 -- authorize the one run, BEFORE it happens
# --------------------------------------------------------------------------

def declare_phase3_authorization(*, out_path: Path, phase2_lock_path: Path,
                                  declared_by: str, affirmation: str,
                                  declared_date: Optional[str] = None,
                                  repo: Path = REPO_ROOT
                                  ) -> dict[str, Any]:
    """Write the HYP-05 Phase 3 authorization -- BEFORE any real computation.

    Mirrors `ratify.py.declare_phase3_authorization` exactly in shape: every
    earlier step signs something already derived; this one does not, so it
    writes the complete, signed document in one step, pinned to whatever
    the commit and the HYP-05 Phase 2 lock hash actually are right now.
    """
    from .make_freeze_draft import _commit_sha, _sha256
    from .make_hyp05_phase2_lock import Phase2LockError, load_declared_phase2_lock
    from .make_hyp05_phase3_run import RESULT_PATTERN

    if out_path.exists():
        raise RatifyError(
            f"{out_path.name} already exists. At most one authorization "
            "exists at a time. If it was never consumed and you need to "
            "re-authorize against new code, delete it deliberately first.")
    existing = sorted(out_path.parent.glob("HYP05_PHASE3_AUTHORIZATION_*.json"))
    if existing:
        raise RatifyError(
            f"an authorization already exists ({[p.name for p in existing]}"
            "). Refusing to write a second one under a different name.")
    existing_results = sorted(out_path.parent.glob(RESULT_PATTERN))
    if existing_results:
        raise RatifyError(
            f"a HYP-05 Phase 3 result already exists "
            f"({[p.name for p in existing_results]}). This exploratory "
            "check has already been run once; authorizing another run "
            "would not be honest about what this is for.")

    try:
        load_declared_phase2_lock(phase2_lock_path)
    except Phase2LockError as e:
        raise RatifyError(f"cannot authorize Phase 3: {e}") from e

    declared_by = _reject_placeholder("--declared-by", declared_by)
    declared_date = _iso("--declared-date", declared_date)

    if (affirmation or "").strip() != HYP05_PHASE3_AFFIRMATION:
        raise RatifyError(
            "the affirmation does not match, so nothing was written.\n\n"
            "This authorizes the one real computation against AMBA's "
            "returns. Type it exactly:\n\n"
            f'  --affirm "{HYP05_PHASE3_AFFIRMATION}"\n\n'
            "If you are not ready to spend this check, do not type it.")

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "hypothesis_id": "HYP-05",
        "what_this_is": (
            "Authorization for the one, single exploratory run -- typed "
            "and pinned BEFORE any computation against AMBA's real "
            "returns happens. make_hyp05_phase3_run.py refuses to run "
            "without it."),
        "what_this_is_not": (
            "Not a result, not a retroactive declaration, and not itself "
            "a computation. It authorizes exactly one future run of "
            "make_hyp05_phase3_run.py, pinned to the exact code and lock "
            "that exist right now."),
        "declared": True,
        "declared_by": declared_by,
        "declared_date": declared_date,
        "attestation_text": HYP05_PHASE3_AFFIRMATION,
        "pinned_commit_sha": _commit_sha(repo),  # refuses a dirty tree
        "pinned_phase2_lock_sha256": _sha256(phase2_lock_path),
        "pinned_phase2_lock": phase2_lock_path.name,
        "consumed": False,
        "consumed_by_result": None,
        "how_it_is_used": (
            "make_hyp05_phase3_run.py verifies: exactly one authorization "
            "exists, declared is true, consumed is false, and "
            "pinned_phase2_lock_sha256 matches the lock on disk. It marks "
            "this consumed the instant a real run succeeds."),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return {
        "written": out_path.name,
        "declared_by": declared_by,
        "declared_date": declared_date,
        "pinned_commit_sha": doc["pinned_commit_sha"],
    }


def _print_phase3_template() -> None:
    """One line, no continuations -- same rule as ratify.py's templates."""
    print("Replace <your name>, then paste as ONE line:\n")
    print("  " + " ".join([
        "python -m hyp04_supply_chain_hedge.ratify_hyp05 phase3",
        '--declared-by "<your name>"',
        f'--affirm "{HYP05_PHASE3_AFFIRMATION}"']))
    print(f"\nWill write: HYP05_PHASE3_AUTHORIZATION_{date.today().isoformat()}.json")
    print("\nThis authorizes the ONE exploratory run. Read "
          "HYP05_PHASE3_AFFIRMATION above before\ntyping it -- there is no "
          "undo, and no second run.")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m hyp04_supply_chain_hedge.ratify_hyp05",
        description="Sign HYP-05's Phase 2 lock and Phase 3 authorization. "
                    "Scoped only to HYP-05's own two artifacts -- see "
                    "ratify.py for HYP-04's chain.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p2 = sub.add_parser("phase2", help="declare the HYP-05 Phase 2 lock")
    p2.add_argument("--template", action="store_true")
    p2.add_argument("--declared-by", default="")
    p2.add_argument("--declared-date", default=None)
    p2.add_argument("--affirm", default="")

    p3 = sub.add_parser("phase3", help="authorize the one HYP-05 Phase 3 "
                                       "run, BEFORE it happens")
    p3.add_argument("--template", action="store_true")
    p3.add_argument("--declared-by", default="")
    p3.add_argument("--declared-date", default=None)
    p3.add_argument("--affirm", default="")

    args = ap.parse_args(argv)

    if args.cmd == "phase2":
        from .make_hyp05_phase2_lock import OUT_JSON as PHASE2_JSON
        if args.template or not args.affirm:
            _print_phase2_template()
            return 0 if args.template else 1
        if not PHASE2_JSON.is_file():
            raise RatifyError(
                f"no HYP-05 Phase 2 lock at {PHASE2_JSON.name}. Run "
                "make_hyp05_phase2_lock first -- this signs a derivation, "
                "it does not perform one.")
        out = declare_phase2_lock(lock_path=PHASE2_JSON,
                                  declared_by=args.declared_by,
                                  affirmation=args.affirm,
                                  declared_date=args.declared_date)
        print(f"DECLARED {out['written']}")
        print(f"  locked peer/anchor  {out['locked_peer']} / {out['locked_anchor']}")
        print(f"  n_locked_events     {out['n_locked_events']}")
        print(f"  primary cluster key {out['primary_cluster_key']}")
        print(f"  by                  {out['declared_by']} on {out['declared_date']}")
        print("\nThis opens no gate and computes nothing against AMBA's "
              "outcome. Phase 3,\nlater, is the one exploratory run.")
        return 0

    if args.cmd == "phase3":
        from .make_hyp05_phase2_lock import OUT_JSON as PHASE2_JSON
        if args.template or not args.affirm:
            _print_phase3_template()
            return 0 if args.template else 1
        out = LSE / f"HYP05_PHASE3_AUTHORIZATION_{date.today().isoformat()}.json"
        result = declare_phase3_authorization(
            out_path=out, phase2_lock_path=PHASE2_JSON,
            declared_by=args.declared_by, affirmation=args.affirm,
            declared_date=args.declared_date)
        print(f"AUTHORIZED {result['written']}")
        print(f"  by             {result['declared_by']} on {result['declared_date']}")
        print(f"  pinned commit  {result['pinned_commit_sha'][:12]}")
        print("\nAMBA's outcome has NOT been touched. Run "
              "make_hyp05_phase3_run.py to spend this\nauthorization -- it "
              "will be consumed and cannot authorize a second run.")
        return 0

    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RatifyError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(1)
