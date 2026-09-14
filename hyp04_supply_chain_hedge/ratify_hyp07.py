#!/usr/bin/env python3
"""HYP-07's own ratification driver -- phase2 (declare the lock) ONLY.

=== WHY THERE IS NO phase3 COMMAND HERE, ON PURPOSE ===

Same reasoning as `ratify_hyp06.py`'s own docstring, at the point in this
project's history before its `phase3` subcommand was added: authorizing
and running HYP-07's Phase 3 spends a real, one-shot holdout against a
universe that took this session's entire round-7 effort to discover and
lock, and that decision belongs to the repo owner's own explicit,
real-time go-ahead -- not to whatever already-granted autonomy produced
this lock. The owner asked to "start with the phase 2 lock," which this
module answers in full; `phase3` is deliberately not added here, the same
way `ratify_hyp06.py` did not gain its own `phase3` subcommand until a
separate, later, explicit go-ahead was given for HYP-06.

=== OTHERWISE, THE SAME SHAPE AS ratify_hyp06.py's OWN phase2 ===

Borrows `ratify.py`'s PROVEN mechanics (`_reject_placeholder`, `_iso`,
`RatifyError`) by IMPORTING them directly, not copying them -- same
reason every prior per-hypothesis ratify module does.

  python -m hyp04_supply_chain_hedge.ratify_hyp07 phase2 --template
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .ratify import RatifyError, _iso, _reject_placeholder

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

#: Typed verbatim or the declaration does not happen -- same discipline as
#: ratify_hyp05.py's/ratify_hyp06.py's own AFFIRMATION constants.
HYP07_PHASE2_AFFIRMATION = (
    "HYP-07's Phase 2 lock -- target definition (target_signed.py's new "
    "signed cumulative abnormal return, first use of a signed target in "
    "this project), model spec, and the locked 195-pair, 6-peer, 6-anchor "
    "set -- was fixed before any return, signed cumulative abnormal "
    "return, or beta value was computed for any locked peer around any "
    "locked anchor event. Every locked peer's raw closes were touched "
    "only to compute point-in-time market cap for peer-eligibility "
    "screening, never their returns or outcome. I understand this sample "
    "clears its own provisional 195-pair floor EXACTLY, not comfortably, "
    "and that the floor itself is an even weaker borrow than HYP-06's "
    "own reuse of the same numbers, since HYP-07's target is a different "
    "formula from the one that floor was measured against.")

#: Fields declaring a Phase 2 lock may move. Everything else is derived.
PHASE2_FIELDS = ("declared", "declared_by", "declared_date", "status")


def declare_phase2_lock(*, lock_path: Path, declared_by: str,
                        affirmation: str,
                        declared_date: Optional[str] = None
                        ) -> dict[str, Any]:
    """Fill the three owner fields on the HYP-07 Phase 2 lock. Nothing
    else moves."""
    from .make_hyp07_phase2_lock import (
        OWNER_FIELDS as PHASE2_OWNER_FIELDS,
        load_declared_phase2_lock,
    )

    if not lock_path.is_file():
        raise RatifyError(f"no HYP-07 Phase 2 lock at {lock_path}")
    declared_by = _reject_placeholder("--declared-by", declared_by)
    declared_date = _iso("--declared-date", declared_date)

    if (affirmation or "").strip() != HYP07_PHASE2_AFFIRMATION:
        raise RatifyError(
            "the affirmation does not match, so nothing was written.\n\n"
            "A lock is only a preregistration if it was fixed before any "
            "locked peer's outcome was examined. Nothing in this "
            "repository can establish that, so type it exactly:\n\n"
            f'  --affirm "{HYP07_PHASE2_AFFIRMATION}"\n\n'
            "If you have looked at how any locked peer's returns behave "
            "around these events, do not type it. The lock is then a "
            "description, and that is the finding.")

    before = json.loads(lock_path.read_text(encoding="utf-8"))
    if before.get("declared") is True:
        raise RatifyError(
            f"{lock_path.name} is already declared by "
            f"{before.get('declared_by')!r} on {before.get('declared_date')!r}. "
            "Re-declaring would overwrite the record any future run cites.")
    for f in PHASE2_OWNER_FIELDS:
        if f not in before:
            raise RatifyError(
                f"{lock_path.name} has no {f!r} key; this does not look "
                "like a draft from make_hyp07_phase2_lock")

    after = dict(before)
    after["declared"] = True
    after["declared_by"] = declared_by
    after["declared_date"] = declared_date
    after["status"] = f"DECLARED -- by {declared_by} on {declared_date}"
    after["attestation_text"] = HYP07_PHASE2_AFFIRMATION

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
        "locked_peers": d["locked_peers"],
        "locked_anchors": d["locked_anchors"],
        "n_locked_events": d["n_locked_events"],
        "primary_cluster_key": d["model_spec"]["primary_cluster_key"],
    }


def _print_phase2_template() -> None:
    """One line, no continuations -- same rule as ratify.py's templates."""
    from .make_hyp07_phase2_lock import OUT_JSON
    print("Replace <your name>, then paste as ONE line:\n")
    print(f'python -m hyp04_supply_chain_hedge.ratify_hyp07 phase2 '
          f'--lock "{OUT_JSON}" --declared-by "<your name>" '
          f'--affirm "{HYP07_PHASE2_AFFIRMATION}"\n')
    print(f"(--declared-date defaults to today if omitted.)")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="HYP-07's ratification driver -- phase2 (declare the "
                    "Phase 2 lock) only. No phase3 command exists yet -- "
                    "see module docstring for why.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p2 = sub.add_parser("phase2", help="declare the HYP-07 Phase 2 lock")
    p2.add_argument("--template", action="store_true",
                    help="print the exact command to run, then exit")
    p2.add_argument("--lock", type=Path, default=None)
    p2.add_argument("--declared-by", default=None)
    p2.add_argument("--declared-date", default=None)
    p2.add_argument("--affirm", default=None)

    args = ap.parse_args(argv)

    if args.cmd == "phase2":
        from .make_hyp07_phase2_lock import OUT_JSON as PHASE2_JSON
        if args.template:
            _print_phase2_template()
            return 0
        if not (PHASE2_JSON.exists() or (args.lock and args.lock.exists())):
            print("REFUSED -- no draft found. Run "
                  "make_hyp07_phase2_lock first -- this signs a "
                  "derivation, it does not create one.", file=sys.stderr)
            return 1
        try:
            out = declare_phase2_lock(
                lock_path=args.lock or PHASE2_JSON,
                declared_by=args.declared_by or "",
                affirmation=args.affirm or "",
                declared_date=args.declared_date)
        except RatifyError as e:
            print(f"REFUSED -- {e}", file=sys.stderr)
            return 1
        print(f"DECLARED {out['written']}")
        print(f"  by {out['declared_by']} on {out['declared_date']}")
        print(f"  locked peers   ({len(out['locked_peers'])}): "
              f"{out['locked_peers']}")
        print(f"  locked anchors ({len(out['locked_anchors'])}): "
              f"{out['locked_anchors']}")
        print(f"  n_locked_events: {out['n_locked_events']}")
        print(f"  primary_cluster_key: {out['primary_cluster_key']}")
        return 0

    return 1  # pragma: no cover -- argparse enforces cmd in {"phase2"}


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RatifyError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(1)
