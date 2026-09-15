#!/usr/bin/env python3
"""HYP-08's Phase 2 preregistration lock -- target, model spec, and the
exact locked (peer, anchor-event) set. Structurally different from every
prior hypothesis's own lock in one respect: its locked-event universe is
not re-derived from a raw peer-universe/qualification artifact at all --
it is read WHOLESALE from two already-signed prior locks
(`HYP06_PHASE2_LOCK_2026-09-13.json`'s 778 customer/supplier pairs,
`HYP07_PHASE2_LOCK_2026-09-14.json`'s 195 competitor pairs), pooled. See
`HYP08_SameSessionReactionHeterogeneity_MODEL_PLAN_2026-09-14.md` for why
reusing two already-discovered, already-EDGAR-verified universes for a
fresh, differently-preregistered question is the same sanctioned pattern
HYP-06 itself used over HYP-05's own discovery, not a new exception.

=== EACH POOLED EVENT CARRIES excess_return -- ONE SIDE ALREADY DID, ONE DID NOT ===

HYP-07's own locked events already carry signed `excess_return` alongside
`shock` (its target needed it from the start). HYP-06's own locked events
carry only the magnitude `shock` -- HYP-06's target never read the sign.
For the customer/supplier side, this module looks `excess_return` up
fresh from the SAME three anchor-shocks CSVs both HYP-06's and HYP-07's
own lock modules already read, by `(anchor_ticker, release_date)` -- the
exact key HYP-07's own `_locked_events` uses, just applied to a different
lock's already-fixed pairs instead of a raw qualifications list.

=== EVENT IDS ARE NAMESPACED BY SOURCE HYPOTHESIS ===

`"HYP06-" + event_id` / `"HYP07-" + event_id`, not the bare original
strings -- disclosure of provenance, and a hard guarantee against an
accidental collision, even though the two source universes are already
confirmed to share zero peer tickers.

=== NO HORIZON GRID, NO PERMUTATION -- model_spec SAYS SO EXPLICITLY ===

Every prior hypothesis's model_spec cites max-T permutation multiplicity
correction, because a 20-horizon local-projection grid has no closed-form
null. HYP-08 has no horizon grid (`target_same_session.py`: every row's
own `horizon` field is a constant 0) and exactly two preregistered tests,
so its model_spec instead cites a closed-form Sidak-corrected critical
t-value at k=2 (`make_hyp08_sample_size_gate.sidak_critical_t`) -- see
that module's own docstring for why this is the correct tool for a fixed,
small test family rather than a departure from the project's own
discipline.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .anchor_shock import BENCHMARK_BETA, BENCHMARK_TICKER
from .make_freeze_draft import _commit_sha, _sha256

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"
TARGET_SAME_SESSION_PY = Path(__file__).resolve().parent / "target_same_session.py"
INFERENCE_PY = Path(__file__).resolve().parent / "inference.py"
CLUSTERED_SE_PY = Path(__file__).resolve().parent / "clustered_se.py"
ANCHOR_SHOCK_PY = Path(__file__).resolve().parent / "anchor_shock.py"
SAMPLE_SIZE_GATE_PY = Path(__file__).resolve().parent / "make_hyp08_sample_size_gate.py"

AS_OF = "2026-09-14"
OUT_JSON = LSE / f"HYP08_PHASE2_LOCK_{AS_OF}.json"

HYP06_PHASE2_LOCK_JSON = LSE / "HYP06_PHASE2_LOCK_2026-09-13.json"
HYP07_PHASE2_LOCK_JSON = LSE / "HYP07_PHASE2_LOCK_2026-09-14.json"
ANCHOR_SHOCKS_CSVS = (
    LSE / "HYP04_ANCHOR_SHOCKS_2026-08-31.csv",
    LSE / "HYP05_ADDITIONAL_ANCHOR_SHOCKS_2026-09-12.csv",
    LSE / "HYP05_ADDITIONAL_ANCHOR_SHOCKS_2026-09-13.csv",
)

EXPECTED_N_EVENTS_HYP06_SIDE = 778
EXPECTED_N_EVENTS_HYP07_SIDE = 195
EXPECTED_N_EVENTS = EXPECTED_N_EVENTS_HYP06_SIDE + EXPECTED_N_EVENTS_HYP07_SIDE

#: Reused unchanged from every prior hypothesis's own clustering
#: convention -- a project-wide method choice, not re-decided for HYP-08.
PRIMARY_CLUSTER_KEY = "event_id"

SAMPLE_SIZE_GATE_MD = LSE / f"HYP08_SAMPLE_SIZE_GATE_{AS_OF}.md"
PROVISIONAL_FLOOR_PAIRS = 152  # k=2, EXACT -- see make_hyp08_sample_size_gate

OWNER_FIELDS = ("declared", "declared_by", "declared_date")


class Phase2LockError(RuntimeError):
    """A precondition does not hold. Never a bare `assert` -- same
    reasoning as every prior hypothesis's own Phase2LockError."""


def _all_shock_rows(paths: tuple[Path, ...]) -> dict[tuple[str, str], dict[str, Any]]:
    """{(anchor_ticker, release_date): row}, status == shock_computed only.
    Structurally identical to HYP-06's/HYP-07's own `_all_shock_rows`;
    reimplemented here, not imported, same as every other per-hypothesis
    lock module in this package."""
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
            f"more than one anchor-shocks CSV: {dupes[:5]}...")
    return out


def _load_declared(path: Path, hypothesis_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise Phase2LockError(f"no {hypothesis_id} Phase 2 lock at {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("declared") is not True:
        raise Phase2LockError(
            f"{path.name} is not a SIGNED lock -- refusing to pool an "
            "undeclared draft's events into a new hypothesis.")
    return doc


def _locked_events(hyp06_lock_path: Path, hyp07_lock_path: Path,
                   anchor_shocks_paths: tuple[Path, ...]) -> list[dict[str, Any]]:
    """The exact pooled (peer, anchor-event) rows this lock fixes --
    every one already fixed by a prior, signed lock; this function adds
    only a namespaced event_id and (for the HYP-06 side) the looked-up
    signed excess_return."""
    hyp06 = _load_declared(hyp06_lock_path, "HYP-06")
    hyp07 = _load_declared(hyp07_lock_path, "HYP-07")
    shocks = _all_shock_rows(anchor_shocks_paths)

    events: list[dict[str, Any]] = []
    for e in hyp06["locked_events"]:
        key = (e["anchor_ticker"], e["release_date"])
        row = shocks.get(key)
        if row is None:
            raise Phase2LockError(
                f"HYP-06 locked pair {e['peer_ticker']}/{key} has no "
                "matching shock_computed row in any anchor-shocks CSV.")
        events.append({
            "event_id": f"HYP06-{e['event_id']}",
            "source_hypothesis": "HYP-06",
            "source_lock": hyp06_lock_path.name,
            "anchor_ticker": e["anchor_ticker"],
            "peer_ticker": e["peer_ticker"],
            "relationship_type": e["relationship_type"],
            "as_of_date": e["as_of_date"],
            "release_date": e["release_date"],
            "attributed_session": e["attributed_session"],
            "shock": float(e["shock"]),
            "excess_return": float(row["excess_return"]),
        })
    for e in hyp07["locked_events"]:
        events.append({
            "event_id": f"HYP07-{e['event_id']}",
            "source_hypothesis": "HYP-07",
            "source_lock": hyp07_lock_path.name,
            "anchor_ticker": e["anchor_ticker"],
            "peer_ticker": e["peer_ticker"],
            "relationship_type": e["relationship_type"],
            "as_of_date": e["as_of_date"],
            "release_date": e["release_date"],
            "attributed_session": e["attributed_session"],
            "shock": float(e["shock"]),
            "excess_return": float(e["excess_return"]),
        })
    return events


def build_draft(*, out_path: Path = OUT_JSON,
                hyp06_lock_path: Path = HYP06_PHASE2_LOCK_JSON,
                hyp07_lock_path: Path = HYP07_PHASE2_LOCK_JSON,
                anchor_shocks_paths: tuple[Path, ...] = ANCHOR_SHOCKS_CSVS,
                repo: Path = REPO_ROOT,
                today: Optional[date] = None) -> dict[str, Any]:
    when = today or date.today()

    if out_path.exists():
        raise Phase2LockError(
            f"{out_path.name} already exists. A second lock would make "
            "the first unfalsifiable. Delete it deliberately if it was "
            "never signed.")

    for label, p in (
        ("HYP-06 Phase 2 lock", hyp06_lock_path),
        ("HYP-07 Phase 2 lock", hyp07_lock_path),
        *[(f"anchor shocks ({p.name})", p) for p in anchor_shocks_paths],
        ("sample-size gate", SAMPLE_SIZE_GATE_MD),
    ):
        if not p.is_file():
            raise Phase2LockError(f"no {label} at {p}")

    events = _locked_events(hyp06_lock_path, hyp07_lock_path, anchor_shocks_paths)
    n_hyp06 = sum(1 for e in events if e["source_hypothesis"] == "HYP-06")
    n_hyp07 = sum(1 for e in events if e["source_hypothesis"] == "HYP-07")
    if n_hyp06 != EXPECTED_N_EVENTS_HYP06_SIDE or n_hyp07 != EXPECTED_N_EVENTS_HYP07_SIDE:
        raise Phase2LockError(
            f"pooled {n_hyp06} HYP-06-side + {n_hyp07} HYP-07-side events, "
            f"expected exactly {EXPECTED_N_EVENTS_HYP06_SIDE} + "
            f"{EXPECTED_N_EVENTS_HYP07_SIDE}. One of the two source locks "
            "has changed since this module was written.")

    locked_peers = sorted({e["peer_ticker"] for e in events})
    locked_anchors = sorted({e["anchor_ticker"] for e in events})
    overlap = ({e["peer_ticker"] for e in events if e["source_hypothesis"] == "HYP-06"}
              & {e["peer_ticker"] for e in events if e["source_hypothesis"] == "HYP-07"})
    if overlap:
        raise Phase2LockError(
            f"peer ticker(s) {sorted(overlap)} appear on BOTH sides of the "
            "pool -- the two source universes were confirmed disjoint when "
            "this module was written; re-examine before trusting a pooled "
            "fit over them.")

    sha = _commit_sha(repo)  # refuses on a dirty tree

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-08",
        "what_this_is": (
            "The Phase 2 preregistration lock: the exact pooled (peer, "
            "anchor-event) set -- 778 customer/supplier pairs from "
            "HYP-06's own signed lock, 195 competitor pairs from HYP-07's "
            "own signed lock -- target definition, and model spec, fixed "
            "before any same-session value has been computed for any "
            "pooled pair. See 'look_ahead_disclosure' below."),
        "what_this_is_not": (
            "Not a re-run or revision of HYP-06's or HYP-07's own already-"
            "reported results -- both remain exactly as signed and "
            "reported; this lock only reuses their already-fixed EVENT "
            "SETS for a new, differently preregistered same-session "
            "question. Not a result, not the one locked run, and not "
            "permission to compute anything. No Phase 3 authorization has "
            "been drafted, requested, or signed for HYP-08 as of this "
            "lock."),
        "governing_documents": {
            "model_plan": "HYP08_SameSessionReactionHeterogeneity_"
                          "MODEL_PLAN_2026-09-14.md",
            "sample_size_gate": SAMPLE_SIZE_GATE_MD.name,
            "source_locks": [hyp06_lock_path.name, hyp07_lock_path.name],
        },
        "pins": {
            "hyp06_phase2_lock": hyp06_lock_path.name,
            "hyp06_phase2_lock_sha256": _sha256(hyp06_lock_path),
            "hyp07_phase2_lock": hyp07_lock_path.name,
            "hyp07_phase2_lock_sha256": _sha256(hyp07_lock_path),
            "anchor_shocks": [p.name for p in anchor_shocks_paths],
            "anchor_shocks_sha256": [_sha256(p) for p in anchor_shocks_paths],
            "target_same_session_py_sha256": _sha256(TARGET_SAME_SESSION_PY),
            "inference_py_sha256": _sha256(INFERENCE_PY),
            "clustered_se_py_sha256": _sha256(CLUSTERED_SE_PY),
            "anchor_shock_py_sha256": _sha256(ANCHOR_SHOCK_PY),
            "sample_size_gate_py_sha256": _sha256(SAMPLE_SIZE_GATE_PY),
            "lock_declared_at_commit": sha,
        },
        "locked_peers": locked_peers,
        "locked_anchors": locked_anchors,
        "locked_events": events,
        "n_locked_events": len(events),
        "n_locked_events_customer_supplier": n_hyp06,
        "n_locked_events_competitor": n_hyp07,
        "n_locked_peers": len(locked_peers),
        "n_locked_anchors": len(locked_anchors),
        "target_definition": {
            "formula": (
                "same_session_excess_return = r_peer[attributed_session] "
                "- beta * r_bench[attributed_session]. No horizon grid, "
                "no cumulation, no reference-window baseline -- the "
                "peer's benchmark-adjusted return on the EXACT trading "
                "session the anchor's own excess return is attributed "
                "to, and nothing else. See target_same_session.py's own "
                "docstring for full provenance."),
            "benchmark_ticker": BENCHMARK_TICKER,
            "benchmark_beta": BENCHMARK_BETA,
            "benchmark_beta_note": (
                "FIXED, never estimated -- the same anchor_shock.py AS-2 "
                "convention every prior hypothesis in this project "
                "already uses."),
            "horizon_grid": None,
            "horizon_grid_note": (
                "None, deliberately -- every row's own horizon field is "
                "the constant 0. This is the genuinely distinct design "
                "external review asked for: no delayed-horizon grid of "
                "any kind, unlike HYP-04/05/06/07 alike."),
            "return_basis": "log, same as every prior hypothesis's own "
                            "convention.",
            "residualization": "NOT APPLIED, same v1 simplification as "
                               "HYP-07's own target_signed.py.",
            "relationship_type_pooling": (
                "Every locked event carries the relationship_type its "
                "SOURCE lock already assigned (HYP-06's own "
                "customer/supplier categories, HYP-07's own competitor "
                "category), mapped by target_same_session.py to a single "
                "boolean is_competitor design column."),
            "sign_convention": (
                "Nothing is flipped, anywhere. A priori, economically "
                "motivated predictions, stated before any fit: "
                "customer/supplier peers POSITIVE (comovement -- shared "
                "revenue chain), competitor peers NEGATIVE (displacement, "
                "same convention HYP-07's own target_signed.py already "
                "uses). Not significant is a null either way, for either "
                "test below."),
            "source": "target_same_session.py, hash-pinned above, first "
                     "use of a same-session (no-horizon-grid) target in "
                     "this project.",
        },
        "model_spec": {
            "estimator": (
                "CR2 clustered standard errors with Satterthwaite degrees "
                "of freedom -- clustered_se.py, reused unmodified. "
                "SIGNIFICANCE differs from every prior hypothesis: a "
                "closed-form Sidak-corrected critical t-value at k=2 "
                "EXACT preregistered tests (make_hyp08_sample_size_gate."
                "sidak_critical_t), not a max-T permutation null -- there "
                "is no horizon grid here for a max-selection problem to "
                "exist over. See make_hyp08_sample_size_gate.py's own "
                "docstring for why this is the correct tool for this "
                "design, not a departure from this project's own "
                "discipline."),
            "primary_cluster_key": PRIMARY_CLUSTER_KEY,
            "primary_cluster_key_note": (
                "Reused unchanged from HYP-05's own re-decision "
                "(clustered_se.HYP05_TWO_WAY_LIMITATION_NOTE), a project-"
                "wide method choice, not re-decided for HYP-08."),
            "residualize": False,
            "n_permutations": None,
            "n_permutations_note": (
                "Not applicable -- see estimator above. No permutation "
                "null is computed for HYP-08."),
            "test_family": {
                "k": 2,
                "test_1_primary": (
                    "inference.fit_local_projections(table, "
                    "horizons=(0,), cluster_key='event_id') -- the plain "
                    "pooled same-session coefficient, both relationship "
                    "types combined."),
                "test_2_heterogeneity": (
                    "inference.fit_interaction_model(table, "
                    "cluster_key='event_id') -- the shock:is_competitor "
                    "interaction coefficient."),
                "complementarity_note": (
                    "These are COMPLEMENTARY tests, not redundant ones. "
                    "If the two relationship types' true effects are "
                    "opposite-signed and roughly offsetting in the pooled "
                    "sample, test 1 can come back null while test 2's "
                    "interaction term is significant -- that is a "
                    "coherent, reportable joint result, not a "
                    "contradiction requiring explanation."),
            },
        },
        "sample_size_disclosure": {
            "n_locked_events": len(events),
            "n_peers": len(locked_peers),
            "n_anchors": len(locked_anchors),
            "provisional_operative_floor_pairs": PROVISIONAL_FLOOR_PAIRS,
            "floor_source": SAMPLE_SIZE_GATE_MD.name,
            "framing": "EXPLORATORY -- floor is EXACT (k=2 by design), not "
                      "provisional or borrowed, unlike every prior "
                      "hypothesis's own floor",
            "why": (
                f"{len(events)} pooled (peer, event) pairs clears the "
                f"k=2-exact {PROVISIONAL_FLOOR_PAIRS}-pair floor by "
                f"{len(events) / PROVISIONAL_FLOOR_PAIRS:.1f}x. Still "
                "framed exploratory: a governance eligibility floor is "
                "not a claim of guaranteed power, and the true analyzed "
                "sample will be smaller after same-session NaN exclusion "
                "-- see make_hyp08_phase3_run.py's own real result for "
                "the actual analyzed count."),
        },
        "look_ahead_disclosure": {
            "already_touched": (
                "Every pooled event's anchor-side signed excess_return "
                "was already computed (HYP-04/05/06's own anchor-shock "
                "pipeline) and already used by HYP-06's and/or HYP-07's "
                "own prior, completed, spent Phase 3 runs. HYP-06's peers' "
                "MAGNITUDE-based results and HYP-07's peers' delayed-"
                "horizon signed results are both already reported and "
                "unaffected by this lock."),
            "not_touched": (
                "No same-session peer excess return of any kind, for any "
                "pooled peer around any pooled anchor event, has been "
                "computed before this lock -- target_same_session.py did "
                "not exist before this pass. This lock is written before "
                "that computation happens for the first time."),
        },
        "opens_no_gate": (
            "This is a computed HYP-08 Phase 2 lock, not a freeze, not a "
            "registry change, not a linkage ratification. It moves no "
            "gate condition, whatever the gate reads at the moment this "
            "file is read."),
        "declared": False,
        "declared_by": "",
        "declared_date": "",
        "owner_fields": list(OWNER_FIELDS),
        "how_to_complete": (
            "python -m hyp04_supply_chain_hedge.ratify_hyp08 phase2 --template"),
        "status": "DRAFT -- inert until declared",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def load_declared_phase2_lock(path: Path) -> dict[str, Any]:
    """Read a SIGNED lock. Refuses a draft."""
    if not path.is_file():
        raise Phase2LockError(f"no HYP-08 Phase 2 lock at {path}")
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("declared") is not True:
        raise Phase2LockError(
            f"{path.name} is a draft: 'declared' is not true.")
    for f in ("declared_by", "declared_date"):
        if not str(d.get(f) or "").strip():
            raise Phase2LockError(f"{f!r} is blank.")
    return d


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Write an INERT HYP-08 Phase 2 preregistration lock.")
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    import tempfile
    if a.dry_run:
        with tempfile.TemporaryDirectory() as td:
            doc = build_draft(out_path=Path(td) / "p2.json")
    else:
        doc = build_draft(out_path=a.out)

    print(f"locked peers  ({doc['n_locked_peers']}): {doc['locked_peers']}")
    print(f"locked anchors({doc['n_locked_anchors']}): {doc['locked_anchors']}")
    print(f"n_locked_events    : {doc['n_locked_events']}  "
          f"({doc['n_locked_events_customer_supplier']} customer/supplier "
          f"+ {doc['n_locked_events_competitor']} competitor)")
    print(f"sample-size framing   : {doc['sample_size_disclosure']['framing']}")
    print(f"\nBLANK, and this module will not fill them: "
          + ", ".join(doc["owner_fields"]))

    if a.dry_run:
        print("\nDRY RUN -- nothing written.")
    else:
        print(f"\nWROTE {doc['artifact']}  (INERT -- 'declared' is false)")
        print("Next: python -m hyp04_supply_chain_hedge.ratify_hyp08 "
              "phase2 --template")
    return 0


if __name__ == "__main__":
    sys.exit(main())
