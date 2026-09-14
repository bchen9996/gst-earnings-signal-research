#!/usr/bin/env python3
"""HYP-07's own ratification driver -- phase2 (declare the lock) and
phase3 (authorize the one run).

=== BOTH COMMANDS ARE BUILT AND TESTED; NEITHER HAS BEEN RUN ===

The owner said "go to phase 3, and keep going" -- explicit authorization
to BUILD everything Phase 3 needs, given directly in response to the full
195/195-pair disclosure this session already made. What was NOT given,
and what this module does not take: the owner's own act of typing either
affirmation. Both `HYP07_PHASE2_AFFIRMATION` and `HYP07_PHASE3_AFFIRMATION`
below are worded in first person ("I understand...", "I authorize...") on
purpose -- they are the one checkpoint in this whole pipeline that must
come from the human, not from whatever process produced the lock, or the
entire point of a preregistration (a record that the spec was fixed
BEFORE anyone looked) collapses into theater. Mirrors exactly the
reasoning `ratify_hyp06.py`'s own docstring gives for why ITS `phase3`
command did not exist until a separate, explicit go-ahead was given for
HYP-06 -- the difference here is that go-ahead already covers both
commands' construction, not their invocation.

=== OTHERWISE, THE SAME SHAPE AS ratify_hyp06.py's OWN phase2/phase3 ===

Borrows `ratify.py`'s PROVEN mechanics (`_reject_placeholder`, `_iso`,
`RatifyError`) by IMPORTING them directly, not copying them -- same
reason every prior per-hypothesis ratify module does.

  python -m hyp04_supply_chain_hedge.ratify_hyp07 phase2 --template
  python -m hyp04_supply_chain_hedge.ratify_hyp07 phase3 --template
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


# --------------------------------------------------------------------------
# phase3 -- authorize the one run, BEFORE it happens
# --------------------------------------------------------------------------

#: Typed verbatim or the authorization does not happen -- see
#: HYP07_PHASE2_AFFIRMATION's own comment for why this is a sentence, not
#: a flag.
HYP07_PHASE3_AFFIRMATION = (
    "I authorize the one, single exploratory run of HYP-07's locked spec "
    "against the real returns of every one of its 6 locked peers around "
    "every one of its 195 locked anchor events. I understand this sample "
    "clears its own provisional 195-pair floor EXACTLY, not comfortably, "
    "and that the floor itself is an even weaker borrow than HYP-06's own "
    "reuse of the same numbers, since HYP-07's target is a different "
    "formula (a plateauing cumulative sum) from the one that floor was "
    "measured against. I understand a significantly negative peak beta "
    "confirms competitive displacement, a significantly positive one "
    "indicates comovement instead, and not significant is a null -- and "
    "that whichever it is, it will be reported as computed. I understand "
    "this cannot be undone or repeated.")

#: Fields declaring a Phase 3 authorization may move. Everything else is
#: derived.
PHASE3_FIELDS = ("consumed", "consumed_by_result")


def declare_phase3_authorization(*, out_path: Path, phase2_lock_path: Path,
                                  peer_closes_path: Path,
                                  peer_earnings_path: Path,
                                  declared_by: str, affirmation: str,
                                  declared_date: Optional[str] = None,
                                  repo: Path = REPO_ROOT) -> dict[str, Any]:
    """Write the HYP-07 Phase 3 authorization -- BEFORE any real
    computation. Mirrors `ratify_hyp06.declare_phase3_authorization`
    exactly in shape."""
    from .make_freeze_draft import _commit_sha, _sha256
    from .make_hyp07_phase2_lock import Phase2LockError, load_declared_phase2_lock
    from .make_hyp07_phase3_run import RESULT_PATTERN

    if out_path.exists():
        raise RatifyError(
            f"{out_path.name} already exists. At most one authorization "
            "exists at a time. If it was never consumed and you need to "
            "re-authorize against new code, delete it deliberately first.")
    existing = sorted(out_path.parent.glob("HYP07_PHASE3_AUTHORIZATION_*.json"))
    if existing:
        raise RatifyError(
            f"an authorization already exists ({[p.name for p in existing]}"
            "). Refusing to write a second one under a different name.")
    existing_results = sorted(out_path.parent.glob(RESULT_PATTERN))
    if existing_results:
        raise RatifyError(
            f"a HYP-07 Phase 3 result already exists "
            f"({[p.name for p in existing_results]}). This exploratory "
            "check has already been run once; authorizing another run "
            "would not be honest about what this is for.")

    try:
        load_declared_phase2_lock(phase2_lock_path)
    except Phase2LockError as e:
        raise RatifyError(f"cannot authorize Phase 3: {e}") from e

    for label, p in (("peer closes", peer_closes_path),
                     ("peer earnings", peer_earnings_path)):
        if not p.is_file():
            raise RatifyError(
                f"cannot authorize Phase 3: no {label} at {p}. Run "
                "run_hyp07_peer_returns_fetch.py --yes-run-live first -- "
                "this authorization pins real data, it does not fetch it.")

    declared_by = _reject_placeholder("--declared-by", declared_by)
    declared_date = _iso("--declared-date", declared_date)

    if (affirmation or "").strip() != HYP07_PHASE3_AFFIRMATION:
        raise RatifyError(
            "the affirmation does not match, so nothing was written.\n\n"
            "This authorizes the one real computation against every "
            "locked peer's real returns. Type it exactly:\n\n"
            f'  --affirm "{HYP07_PHASE3_AFFIRMATION}"\n\n'
            "If you are not ready to spend this check, do not type it.")

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "hypothesis_id": "HYP-07",
        "what_this_is": (
            "Authorization for the one, single exploratory run -- typed "
            "and pinned BEFORE any computation against any locked peer's "
            "real returns happens. make_hyp07_phase3_run.py refuses to "
            "run without it."),
        "what_this_is_not": (
            "Not a result, not a retroactive declaration, and not itself "
            "a computation. It authorizes exactly one future run of "
            "make_hyp07_phase3_run.py, pinned to the exact code, lock, "
            "and real peer data that exist right now."),
        "declared": True,
        "declared_by": declared_by,
        "declared_date": declared_date,
        "attestation_text": HYP07_PHASE3_AFFIRMATION,
        "pinned_commit_sha": _commit_sha(repo),  # refuses a dirty tree
        "pinned_phase2_lock_sha256": _sha256(phase2_lock_path),
        "pinned_phase2_lock": phase2_lock_path.name,
        "pinned_peer_closes_sha256": _sha256(peer_closes_path),
        "pinned_peer_closes": peer_closes_path.name,
        "pinned_peer_earnings_sha256": _sha256(peer_earnings_path),
        "pinned_peer_earnings": peer_earnings_path.name,
        "consumed": False,
        "consumed_by_result": None,
        "how_it_is_used": (
            "make_hyp07_phase3_run.py verifies: exactly one authorization "
            "exists, declared is true, consumed is false, and every "
            "pinned hash (Phase 2 lock, peer closes, peer earnings) "
            "matches what is on disk. It marks this consumed the instant "
            "a real run succeeds."),
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
    from datetime import date as _date
    print("Replace <your name>, then paste as ONE line:\n")
    print("  " + " ".join([
        "python -m hyp04_supply_chain_hedge.ratify_hyp07 phase3",
        '--declared-by "<your name>"',
        f'--affirm "{HYP07_PHASE3_AFFIRMATION}"']))
    print(f"\nWill write: HYP07_PHASE3_AUTHORIZATION_{_date.today().isoformat()}.json")
    print("\nThis authorizes the ONE exploratory run. Read "
          "HYP07_PHASE3_AFFIRMATION above before\ntyping it -- there is no "
          "undo, and no second run. It also requires "
          "HYP07_PEER_CLOSES_*.csv\nand HYP07_PEER_EARNINGS_*.json to "
          "already exist -- run run_hyp07_peer_returns_fetch.py\n"
          "--yes-run-live first if they do not.")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="HYP-07's ratification driver -- phase2 (declare the "
                    "Phase 2 lock) and phase3 (authorize the one run).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p2 = sub.add_parser("phase2", help="declare the HYP-07 Phase 2 lock")
    p2.add_argument("--template", action="store_true",
                    help="print the exact command to run, then exit")
    p2.add_argument("--lock", type=Path, default=None)
    p2.add_argument("--declared-by", default=None)
    p2.add_argument("--declared-date", default=None)
    p2.add_argument("--affirm", default=None)

    p3 = sub.add_parser("phase3", help="authorize the one HYP-07 Phase 3 "
                                       "run, BEFORE it happens")
    p3.add_argument("--template", action="store_true")
    p3.add_argument("--lock", type=Path, default=None)
    p3.add_argument("--peer-closes", type=Path, default=None)
    p3.add_argument("--peer-earnings", type=Path, default=None)
    p3.add_argument("--declared-by", default=None)
    p3.add_argument("--declared-date", default=None)
    p3.add_argument("--affirm", default=None)

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

    if args.cmd == "phase3":
        from datetime import date as _date
        from .make_hyp07_phase2_lock import OUT_JSON as PHASE2_JSON
        from .make_hyp07_phase3_run import DEFAULT_PEER_CLOSES, DEFAULT_PEER_EARNINGS
        if args.template:
            _print_phase3_template()
            return 0
        out = LSE / f"HYP07_PHASE3_AUTHORIZATION_{_date.today().isoformat()}.json"
        try:
            result = declare_phase3_authorization(
                out_path=out, phase2_lock_path=args.lock or PHASE2_JSON,
                peer_closes_path=args.peer_closes or DEFAULT_PEER_CLOSES,
                peer_earnings_path=args.peer_earnings or DEFAULT_PEER_EARNINGS,
                declared_by=args.declared_by or "", affirmation=args.affirm or "",
                declared_date=args.declared_date)
        except RatifyError as e:
            print(f"REFUSED -- {e}", file=sys.stderr)
            return 1
        print(f"AUTHORIZED {result['written']}")
        print(f"  by             {result['declared_by']} on {result['declared_date']}")
        print(f"  pinned commit  {result['pinned_commit_sha'][:12]}")
        print("\nNo locked peer's outcome has been touched. Run "
              "make_hyp07_phase3_run.py to spend this\nauthorization -- it "
              "will be consumed and cannot authorize a second run.")
        return 0

    return 1  # pragma: no cover -- argparse enforces cmd in {"phase2", "phase3"}


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RatifyError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(1)
