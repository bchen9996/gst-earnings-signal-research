#!/usr/bin/env python3
"""The HYP-04 validation split -- declared BEFORE anything is computed.

=== WHY THIS EXISTS, SAID BEFORE ANYTHING ELSE ===

Plan v0.2 section 5.3 orders three things that must not be reordered:

  Phase 1  run Stage 1 openly (no lock). Diagnostic only.
  Phase 2  freeze target, feature set, model spec and validation split in a
           dated lock BEFORE TOUCHING THE HOLDOUT.
  Phase 3  run the locked model against the holdout ONCE.

Read literally, Phase 2 declares the split. Read carefully, that is too late:
Phase 1 runs on real data, and if it ranges over everything then by the time
Phase 2 writes the split there is no untouched holdout left to declare. The
split would be drawn across events whose behaviour is already known, which is
the precise thing a preregistered split exists to prevent.

So the split is declared HERE, before the first diagnostic, and Phase 2 cites
it rather than inventing it.

=== WHAT THIS MODULE WILL NOT DO ===

It will not choose the rule after seeing where the rule lands. The fraction is
an argument with a default, the cut is derived mechanically from it, and the
resulting counts are reported -- in that order. Re-running with a different
fraction until the split "looks better" is exactly the tuning the locks exist
to prevent, and the one-shot dated artifact plus the append-only refusal below
are what make that visible rather than silent.

It also does not SIGN. Like `make_freeze_draft`, this writes an inert draft
with the owner's fields blank; `ratify split` fills them.

=== THE RULE ===

The holdout is the most recent HOLDOUT_FRACTION of frozen eligible events by
event date, snapped UP to a quarter boundary.

Snapped up, not to the nearest event, because D1 clusters on `calendar_period`
and a cut through the middle of a quarter would split a cluster across the
exploration/holdout boundary. A cluster that appears on both sides is a
correlation channel between the two, which is the one property the split is
supposed to rule out.

=== THE SECOND DECLARATION ===

`calendar_period` is D1's locked cluster key and it exists nowhere in the real
data -- only in `fixtures.py`, as an integer. D1 locks BOTH the standard-error
clustering and the permutation restriction to it, and `max_t_permutation`
raises if it is not constant within an event, so it cannot be left to whatever
a caller happens to pass. This artifact declares it: the calendar quarter of
the anchor event date.

That reading is near-mechanical -- D1's own rationale reasons in terms of "24
quarterly anchors x 8 quarters" -- but near-mechanical is not the same as
stated, and an unstated cluster key is a free parameter.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .make_freeze_draft import (
    RESULT_ARTIFACT_PATTERNS,
    _commit_sha,
    _scan_for_results,
    _sha256,
    validate_freeze,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

AS_OF = "2026-09-09"
OUT_JSON = LSE / f"HYP04_VALIDATION_SPLIT_{AS_OF}.json"

#: Share of frozen eligible events reserved, most recent first. An argument
#: with a default rather than a constant nobody may change -- but it is
#: RECORDED in the artifact, so a later run with a different value is a visible
#: second document, not a quiet edit.
HOLDOUT_FRACTION = 0.25

#: What D1's `calendar_period` means on real data. Declared, not assumed.
CLUSTER_KEY = "calendar_period"
CLUSTER_KEY_DEFINITION = (
    "the calendar quarter of the anchor event date, as (year, quarter) with "
    "quarter in 1..4 taken from the event_id's own YYYY-MM-DD suffix. One "
    "value per anchor event, so it is constant within an event by "
    "construction -- which is what inference.max_t_permutation requires."
)

#: Fields a human must supply. Blank on every draft; that is what makes a
#: draft inert.
OWNER_FIELDS = ("declared", "declared_by", "declared_date")


class SplitError(RuntimeError):
    """A precondition does not hold.

    SplitError, never a bare `assert`: `python -O` strips asserts, and a
    guard that vanishes under an optimisation flag is not a guard.
    """


def event_quarter(event_id: str) -> tuple[int, int]:
    """(year, quarter) from an event id shaped `TICKER-YYYY-MM-DD`.

    Raises rather than guessing. An event id this cannot parse would silently
    land in whichever partition the sort put it in, and a misfiled event is a
    holdout leak with no symptom.
    """
    _, _, tail = str(event_id).partition("-")
    try:
        y, m = int(tail[:4]), int(tail[5:7])
        if not 1 <= m <= 12 or tail[4] != "-" or tail[7] != "-":
            raise ValueError(tail)
    except (ValueError, IndexError) as e:
        raise SplitError(
            f"event id {event_id!r} does not end in a YYYY-MM-DD date, so its "
            "calendar_period cannot be derived. The split partitions on that "
            "date; guessing one would misfile the event.") from e
    return y, (m - 1) // 3 + 1


def _event_date(event_id: str) -> str:
    return str(event_id).partition("-")[2]


def derive_split(event_ids: list[str], *, fraction: float = HOLDOUT_FRACTION
                 ) -> dict[str, Any]:
    """Partition by date, then snap the cut up to a quarter boundary.

    Returns both id lists in full. The holdout is enumerated, not described:
    a later check that Phase 1 did not touch it needs the actual ids, and a
    rule plus a count can be satisfied by the wrong 57 events.
    """
    if not 0.0 < fraction < 1.0:
        raise SplitError(f"holdout fraction {fraction!r} is not in (0, 1)")
    if len(set(event_ids)) != len(event_ids):
        raise SplitError("the event id set contains duplicates")
    if not event_ids:
        raise SplitError("no event ids to split")

    ordered = sorted(event_ids, key=_event_date)
    quarters = [event_quarter(i) for i in ordered]

    idx = int(len(ordered) * (1.0 - fraction))
    cut = quarters[idx]                       # snap UP: this whole quarter is holdout

    exploration = [i for i in ordered if event_quarter(i) < cut]
    holdout = [i for i in ordered if event_quarter(i) >= cut]

    if not exploration or not holdout:
        raise SplitError(
            f"the cut at {cut[0]}Q{cut[1]} leaves one side empty "
            f"({len(exploration)}/{len(holdout)}); a split that partitions "
            "nothing is not a split")
    # A quarter on both sides would be a correlation channel between the two
    # partitions under D1, which is the property this split exists to remove.
    overlap = {event_quarter(i) for i in exploration} & {
        event_quarter(i) for i in holdout}
    if overlap:
        raise SplitError(
            f"calendar_period(s) {sorted(overlap)} appear in BOTH partitions. "
            "The cut did not land on a quarter boundary, so a D1 cluster "
            "straddles the split.")

    def side(ids: list[str]) -> dict[str, Any]:
        qs = sorted({event_quarter(i) for i in ids})
        return {
            "n_events": len(ids),
            "n_calendar_periods": len(qs),
            "n_anchors": len({str(i).partition("-")[0] for i in ids}),
            "anchors": sorted({str(i).partition("-")[0] for i in ids}),
            "first_event_date": _event_date(ids[0]),
            "last_event_date": _event_date(ids[-1]),
            "event_ids": list(ids),
        }

    return {
        "rule": (
            f"The holdout is the most recent {fraction:.0%} of frozen eligible "
            "events by event date, snapped UP to a quarter boundary so that no "
            "calendar_period cluster straddles the cut."),
        "holdout_fraction_requested": fraction,
        "cut_calendar_period": f"{cut[0]}Q{cut[1]}",
        "cut_is_first_holdout_period": True,
        "exploration": side(exploration),
        "holdout": side(holdout),
        "holdout_fraction_realized": round(len(holdout) / len(ordered), 4),
    }


def build_draft(*, panel_path: Path, out_path: Path,
                freeze_path: Optional[Path] = None, lse: Path = LSE,
                repo: Path = REPO_ROOT, fraction: float = HOLDOUT_FRACTION,
                today: Optional[date] = None) -> dict[str, Any]:
    """Everything the rule makes derivable. Nothing it does not."""
    from .artifacts import newest_in

    when = today or date.today()

    if out_path.exists():
        raise SplitError(
            f"{out_path.name} already exists. A second split for the same "
            "frozen set would make the first unfalsifiable -- and re-deriving "
            "one after seeing a diagnostic is the tuning this document exists "
            "to rule out. Delete it deliberately if it was never signed.")

    # ORDER. A split declared after a result is not a preregistration, it is a
    # description. This is the same check `make_freeze_draft` runs before a
    # freeze, for the same reason and against the same patterns.
    existing = _scan_for_results(lse)
    if existing:
        raise SplitError(
            f"result artifacts already exist ({', '.join(existing[:4])}). A "
            "validation split declared after an outcome has been computed is "
            "not a preregistered split. Patterns scanned: "
            f"{', '.join(RESULT_ARTIFACT_PATTERNS)}.")

    if not panel_path.is_file():
        raise SplitError(f"no event panel at {panel_path.name}")
    panel = json.loads(panel_path.read_text(encoding="utf-8"))

    freeze_path = freeze_path or newest_in(lse, "HYP04_FREEZE_DRAFT_*.json")
    if freeze_path is None:
        raise SplitError(
            "no freeze draft on disk. The split partitions the FROZEN set; "
            "without a valid freeze there is no set to partition and nothing "
            "stops the membership moving underneath it.")
    rec = validate_freeze(Path(freeze_path), panel_path=panel_path)

    ids = list(rec.eligible_event_ids)
    split = derive_split(ids, fraction=fraction)

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-04",
        "what_this_is": (
            "A preregistered partition of the frozen eligible event set into "
            "an exploration part, which Phase 1 may range over, and a holdout, "
            "which it may not. Declared before any HYP-04 outcome exists."),
        "what_this_is_not": (
            "Not a result, not the Phase 2 preregistration lock, and not "
            "permission to compute anything. It constrains what a later "
            "computation may range over; it performs none."),
        "governing_documents": {
            "plan": "HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md section 5.3",
            "analysis_lock": "GST_HYP04_ANALYSIS_LOCK_v1.0.json",
            "which_decision": "D1 (clustering dimension) for the cluster key",
        },
        # Pinned, so the split cannot silently re-derive against a different
        # panel. The freeze pins the panel's sha256 too; both are recorded so
        # a later reader can check the chain without trusting this file.
        "pins": {
            "panel": panel_path.name,
            "panel_sha256": _sha256(panel_path),
            "freeze": Path(freeze_path).name,
            "freeze_sha256": _sha256(Path(freeze_path)),
            "analysis_commit_sha": rec.analysis_commit_sha,
            "split_declared_at_commit": _commit_sha(repo),
            "frozen_event_count": len(ids),
            "registered_floor": panel.get("registered_floor"),
        },
        "cluster_key": {
            "name": CLUSTER_KEY,
            "definition": CLUSTER_KEY_DEFINITION,
            "locked_by": "D1",
            "why_declared_here": (
                "D1 locks the name, not a derivation. The key exists only in "
                "fixtures.py on synthetic panels, so on real data it is a free "
                "parameter until something states it. An unstated cluster key "
                "silently sets both the standard error and the permutation "
                "restriction."),
        },
        **split,
        "consequences_stated_not_chosen": [
            "A 2021Q1 cut places the 2020 COVID quarters in EXPLORATION, so "
            "the holdout excludes that regime. Recorded as a consequence of "
            "the stated rule, not as a reason for choosing it.",
            "Peer coverage is thin early and complete late: every pair dropped "
            "for insufficient reference/horizon windows falls in exploration, "
            "so the holdout carries complete peer coverage.",
        ],
        "opens_no_gate": (
            "Declaring a split moves no gate condition. It does not supply a "
            "count, a freeze, a linkage ratification or a registry status, and "
            "it is not displayable as a HYP-04 result."),
        # Blank on purpose. See OWNER_FIELDS.
        "declared": False,
        "declared_by": "",
        "declared_date": "",
        "owner_fields": list(OWNER_FIELDS),
        "how_to_complete": (
            "python -m hyp04_supply_chain_hedge.ratify split --template"),
        "status": "DRAFT -- inert until declared",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def load_declared_split(path: Path) -> dict[str, Any]:
    """Read a SIGNED split. Refuses a draft.

    Callers use this to find out what they may range over, so an unsigned
    document must not answer that question -- it would let a diagnostic run
    against a partition nobody committed to.
    """
    if not path.is_file():
        raise SplitError(f"no validation split at {path}")
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("declared") is not True:
        raise SplitError(
            f"{path.name} is a draft: 'declared' is not true. An undeclared "
            "split constrains nothing.")
    for f in ("declared_by", "declared_date"):
        if not str(d.get(f) or "").strip():
            raise SplitError(f"{f!r} is blank; an unattributed declaration is "
                             "not a declaration")
    for part in ("exploration", "holdout"):
        ids = (d.get(part) or {}).get("event_ids")
        if not isinstance(ids, list) or not ids:
            raise SplitError(f"{part!r} enumerates no event ids")
    both = (set(d["exploration"]["event_ids"])
            & set(d["holdout"]["event_ids"]))
    if both:
        raise SplitError(
            f"{len(both)} event id(s) appear in BOTH partitions "
            f"({sorted(both)[:3]}); the split does not partition.")
    return d


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Write an INERT validation split.")
    ap.add_argument("--panel", type=Path,
                    default=LSE / "HYP04_EVENT_PANEL_2026-09-08.json")
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--fraction", type=float, default=HOLDOUT_FRACTION,
                    help=f"holdout share, most recent first "
                         f"(default {HOLDOUT_FRACTION})")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print without writing")
    a = ap.parse_args(argv)

    import tempfile
    if a.dry_run:
        with tempfile.TemporaryDirectory() as td:
            doc = build_draft(panel_path=a.panel, out_path=Path(td) / "s.json",
                              fraction=a.fraction)
    else:
        doc = build_draft(panel_path=a.panel, out_path=a.out,
                          fraction=a.fraction)

    ex, ho = doc["exploration"], doc["holdout"]
    print(f"rule              : {doc['rule']}")
    print(f"cut               : {doc['cut_calendar_period']} "
          f"(first holdout period)")
    print(f"cluster key       : {CLUSTER_KEY} = "
          f"{doc['cluster_key']['definition'][:52]}...")
    print()
    print(f"{'':<12}{'events':>8}{'quarters':>10}{'anchors':>9}  span")
    for name, s in (("exploration", ex), ("holdout", ho)):
        print(f"{name:<12}{s['n_events']:>8}{s['n_calendar_periods']:>10}"
              f"{s['n_anchors']:>9}  {s['first_event_date']} -> "
              f"{s['last_event_date']}")
    print(f"\nrealized holdout share: {doc['holdout_fraction_realized']:.1%}")
    print(f"frozen set pinned     : {doc['pins']['frozen_event_count']} events, "
          f"panel {doc['pins']['panel_sha256'][:12]}")

    if a.dry_run:
        print("\nDRY RUN -- nothing written.")
    else:
        print(f"\nWROTE {doc['artifact']}  (INERT -- 'declared' is false)")
        print("Next: python -m hyp04_supply_chain_hedge.ratify split --template")
    return 0


if __name__ == "__main__":
    sys.exit(main())
