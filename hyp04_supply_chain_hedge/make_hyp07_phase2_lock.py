#!/usr/bin/env python3
"""HYP-07's Phase 2 preregistration lock -- target, model spec, and the
exact locked (peer, anchor-event) set. Mirrors HYP-06's own
`make_hyp06_phase2_lock.py` in SHAPE (multi-peer, multi-anchor, an inert
draft, blank owner fields, a human declares it) but does NOT reuse a
prior lock's target_definition/model_spec the way HYP-06 reused HYP-05's:
HYP-07's target (`target_signed.py`) has never been locked before, so
this module authors `target_definition`/`model_spec` fresh, importing the
real constants directly -- the same thing HYP-05's own lock did the first
time `target.py`'s formula was locked, not a copy of a prior lock's dict.

=== THE EVENT SET IS DERIVED, NOT HAND-TYPED ===

The locked (peer, anchor-event) pairs are read directly from the already-
committed `HYP07_PEER_UNIVERSE_REVERSE_SEARCH_SCALED_2026-09-13.json`
(qualifications where `qualifies` is true), cross-joined against
WHICHEVER of the three anchor-shocks CSVs actually carries that row's
anchor_ticker -- the exact same three files, read the exact same way,
`run_hyp07_peer_market_cap.py`'s own `ANCHOR_SHOCKS_CSVS_DEFAULT` already
used to derive this universe, and the same three files HYP-06's own lock
reads (`_all_shock_rows` imported unchanged in spirit, reimplemented here
only because it lives in a sibling module, not because the logic differs).
`build_draft` asserts the derived count is exactly 195 and refuses
otherwise, since a different count would mean an upstream artifact
changed since this module was written.

=== EACH LOCKED EVENT CARRIES excess_return, NOT JUST shock ===

HYP-04/05/06's target reads the anchor's magnitude-only `shock` column.
HYP-07's signed target needs the anchor's SIGNED `excess_return` instead
(see `target_signed.py`'s own docstring, "SIGN CONVENTION: NOTHING IS
FLIPPED, ANYWHERE") -- both columns already exist side by side in every
anchor-shocks CSV (`anchor_shock.AnchorShock`'s own AS-4:
`shock = abs(excess_return)`), so both are carried onto each locked event:
`shock` for direct comparability with HYP-04/05/06's own locked events,
`excess_return` as the value this hypothesis's regressor actually reads.

=== SAMPLE SIZE: THE FLOOR IS CLEARED EXACTLY, NOT COMFORTABLY ===

HYP-06's 778 qualifying pairs cleared the same provisional 195-pair floor
by nearly 4x. HYP-07's 195 locked events clear it AT EXACTLY 195 -- the
count and the floor are numerically identical. This lock's
`sample_size_disclosure` states that plainly rather than reusing HYP-06's
"cleared by Nx" framing, which would misdescribe HYP-07's actual margin.
See `HYP07_SAMPLE_SIZE_GATE_2026-09-13.md` for the full derivation,
including why borrowing HYP-04's k range is an even weaker analogy here
than it was for HYP-06 (HYP-07's target is a different formula, a
plateauing cumulative sum rather than a diluting mean).
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
from .constants import (
    HORIZON_GRID,
    N_PERMUTATIONS,
    RANDOM_SEED,
    REFERENCE_WINDOW_OFFSET_SESSIONS,
    REFERENCE_WINDOW_TRADING_DAYS,
)
from .make_freeze_draft import _commit_sha, _sha256

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"
TARGET_SIGNED_PY = Path(__file__).resolve().parent / "target_signed.py"
CONSTANTS_PY = Path(__file__).resolve().parent / "constants.py"
CLUSTERED_SE_PY = Path(__file__).resolve().parent / "clustered_se.py"
ANCHOR_SHOCK_PY = Path(__file__).resolve().parent / "anchor_shock.py"

#: Dated the day this lock is actually generated (2026-09-14), one day
#: after the registration/model-plan/sample-size-gate artifacts it cites
#: (2026-09-13) -- the background dashboard verification run crossed
#: midnight. Those citations are unaffected: dated artifacts in this
#: registry are dated by when THEY were produced, not by the date of
#: whatever later artifact cites them.
AS_OF = "2026-09-14"
OUT_JSON = LSE / f"HYP07_PHASE2_LOCK_{AS_OF}.json"

PEER_UNIVERSE_JSON = LSE / "HYP07_PEER_UNIVERSE_REVERSE_SEARCH_SCALED_2026-09-13.json"
ANCHOR_SHOCKS_CSVS = (
    LSE / "HYP04_ANCHOR_SHOCKS_2026-08-31.csv",
    LSE / "HYP05_ADDITIONAL_ANCHOR_SHOCKS_2026-09-12.csv",
    LSE / "HYP05_ADDITIONAL_ANCHOR_SHOCKS_2026-09-13.csv",
)

EXPECTED_N_EVENTS = 195

#: Reused unchanged from HYP-05/06's own clustering convention -- a
#: project-wide method choice, not re-decided for HYP-07. See
#: HYP07_CompetitorRelationshipSignedReaction_MODEL_PLAN_2026-09-13.md S2.
PRIMARY_CLUSTER_KEY = "event_id"
SECONDARY_CLUSTER_KEY = "calendar_period"

SAMPLE_SIZE_GATE_MD = LSE / "HYP07_SAMPLE_SIZE_GATE_2026-09-13.md"
PROVISIONAL_FLOOR_PAIRS = 195

#: Fields a human must supply. Blank on every draft; that is what makes a
#: draft inert.
OWNER_FIELDS = ("declared", "declared_by", "declared_date")


class Phase2LockError(RuntimeError):
    """A precondition does not hold. Never a bare `assert` -- same
    reasoning as HYP-05's/HYP-06's own Phase2LockError."""


def _all_shock_rows(paths: tuple[Path, ...]) -> dict[tuple[str, str], dict[str, Any]]:
    """{(anchor_ticker, release_date): row} across every CSV, for rows
    with status == shock_computed. Refuses rather than silently picking
    one file over another if a key ever appeared in two -- checked
    explicitly below. Structurally identical to HYP-06's own
    `_all_shock_rows`; reimplemented here (not imported) because it lives
    in a sibling per-hypothesis module, same as every other per-
    hypothesis lock module in this package."""
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
            "excess_return": float(row["excess_return"]),
        })
    return events


def build_draft(*, out_path: Path = OUT_JSON,
                peer_universe_path: Path = PEER_UNIVERSE_JSON,
                anchor_shocks_paths: tuple[Path, ...] = ANCHOR_SHOCKS_CSVS,
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
        ("sample-size gate", SAMPLE_SIZE_GATE_MD),
    ):
        if not p.is_file():
            raise Phase2LockError(f"no {label} at {p}")

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

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-07",
        "what_this_is": (
            "The Phase 2 preregistration lock: the exact locked (peer, "
            "anchor-event) set, target definition, and model spec, fixed "
            "before any target/outcome value has been computed for any "
            "peer around any locked anchor event. See "
            "'look_ahead_disclosure' below for exactly what has and has "
            "not already been touched."),
        "what_this_is_not": (
            "Not a result, not the one locked run (a separate, later, "
            "not-yet-built module), and not permission to compute "
            "anything. It constrains what that later, separate, "
            "explicitly-authorized run may do; it performs none. No "
            "Phase 3 authorization has been drafted, requested, or "
            "signed for HYP-07 as of this lock -- that is a distinct, "
            "later, separately-authorized decision this document does "
            "not make."),
        "governing_documents": {
            "model_plan": "HYP07_CompetitorRelationshipSignedReaction_"
                          "MODEL_PLAN_2026-09-13.md",
            "discovery_methodology": "HYP07_DISCOVERY_AND_TARGET_"
                                     "METHODOLOGY_2026-09-13.md",
            "sample_size_gate": SAMPLE_SIZE_GATE_MD.name,
            "registry_entry": "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.17."
                              "json, hypothesis_id=HYP-07",
        },
        "pins": {
            "peer_universe": peer_universe_path.name,
            "peer_universe_sha256": _sha256(peer_universe_path),
            "anchor_shocks": [p.name for p in anchor_shocks_paths],
            "anchor_shocks_sha256": [_sha256(p) for p in anchor_shocks_paths],
            "target_signed_py_sha256": _sha256(TARGET_SIGNED_PY),
            "constants_py_sha256": _sha256(CONSTANTS_PY),
            "clustered_se_py_sha256": _sha256(CLUSTERED_SE_PY),
            "anchor_shock_py_sha256": _sha256(ANCHOR_SHOCK_PY),
            "lock_declared_at_commit": sha,
        },
        "locked_peers": locked_peers,
        "locked_anchors": locked_anchors,
        "locked_events": events,
        "n_locked_events": len(events),
        "n_locked_peers": len(locked_peers),
        "n_locked_anchors": len(locked_anchors),
        "target_definition": {
            "formula": (
                "signed_car(h) = sum_{i=t+1..t+h} (r_peer,i - beta * "
                "r_bench,i) - h * mean_{i in [ref_start, ref_end)} "
                "(r_peer,i - beta * r_bench,i). FIRST USE of a SIGNED "
                "target in this project -- HYP-04/05/06 all used "
                "target.py's magnitude-only realized-variance ratio "
                "instead. See target_signed.py's own docstring for the "
                "full derivation and provenance of each choice below."),
            "benchmark_ticker": BENCHMARK_TICKER,
            "benchmark_beta": BENCHMARK_BETA,
            "benchmark_beta_note": (
                "FIXED, never estimated -- the same anchor_shock.py "
                "AS-2 convention this project already uses on the "
                "anchor side, applied here peer-side. Choosing an "
                "estimation window after seeing how results move would "
                "be exactly the after-the-fact tuning this project's "
                "rules exist to prevent."),
            "horizon_grid": list(HORIZON_GRID),
            "reference_window_trading_days": REFERENCE_WINDOW_TRADING_DAYS,
            "reference_window_offset_sessions": REFERENCE_WINDOW_OFFSET_SESSIONS,
            "return_basis": "log, additive across days -- what makes a "
                            "cumulative sum the natural signed analog of "
                            "target.py's mean-based RVar ratio.",
            "residualization": (
                "NOT APPLIED. Deliberate v1 simplification, not an "
                "oversight -- target.EarningsCycleBaseline removes a "
                "MAGNITUDE confound (volatility rises into a company's "
                "own earnings) with no obvious signed analog for a "
                "cumulative abnormal RETURN. days_to_peer_earnings is "
                "still carried as a design-matrix control column. See "
                "target_signed.py's own docstring, 'DELIBERATELY NOT "
                "PORTED'."),
            "sign_convention": (
                "Nothing is flipped, anywhere: the anchor's raw SIGNED "
                "excess_return and the raw signed signed_car are used "
                "as-is. Significantly NEGATIVE peak beta confirms "
                "competitive displacement (anchor bad news, peer good "
                "news, and vice versa). Significantly POSITIVE peak "
                "beta indicates comovement/contagion instead -- the "
                "OPPOSITE of what a competitor relationship predicts, "
                "flagged explicitly as evidence the 'competitor' label "
                "may be picking up shared-sector/macro exposure, never "
                "silently relabeled as a confirming result. Not "
                "significant is a null, same reporting discipline as "
                "HYP-04/05/06."),
            "peak_horizon_caveat": (
                "target.py's RVar(h) is a MEAN over an expanding window "
                "-- later, unaffected days DILUTE it, so peak_horizon "
                "lands at the END of the true reaction window. "
                "signed_car(h) is a CUMULATIVE SUM instead -- it does "
                "not dilute, it PLATEAUS. Any HYP-07 result's "
                "peak_horizon must be read as 'where the cumulative "
                "effect saturates,' not the same geometric quantity "
                "HYP-04/05/06's own peak_horizon measures, even though "
                "both share the name. No code change follows from this "
                "-- inference.py stays correct exactly as written -- but "
                "every future report of a HYP-07 result must carry this "
                "disclosure."),
            "source": "target_signed.py, hash-pinned above, first use of "
                     "a signed target in this project.",
        },
        "model_spec": {
            "estimator": (
                "local projections with CR2 clustered standard errors, "
                "Satterthwaite degrees of freedom, and max-T permutation "
                "multiplicity correction -- reused unmodified from "
                "inference.py/clustered_se.py, same as HYP-04/05/06."),
            "primary_cluster_key": PRIMARY_CLUSTER_KEY,
            "primary_cluster_key_note": (
                "Reused unchanged from HYP-05's own re-decision "
                "(clustered_se.HYP05_TWO_WAY_LIMITATION_NOTE), NOT "
                "re-decided for HYP-07 -- a project-wide method choice, "
                "not mechanism-specific. 195 locked events, each its own "
                "distinct (anchor, event_date) cluster."),
            "secondary_cluster_key_robustness_lens": SECONDARY_CLUSTER_KEY,
            "secondary_cluster_key_note": (
                "Reported via clustered_se.dual_cluster_report -- two "
                "ONE-WAY clusterings shown side by side, never a two-way "
                "estimator. The primary result above is HYP-07's actual "
                "inferential result; this is a robustness lens only."),
            "residualize": False,
            "residualize_note": (
                "See target_definition.residualization above -- HYP-07's "
                "target has no residualization step of any kind, unlike "
                "HYP-04/05/06's required residualize=True."),
            "n_permutations": N_PERMUTATIONS,
            "random_seed": RANDOM_SEED,
            "n_permutations_note": (
                "Reused unchanged from constants.py -- same values "
                "HYP-04/05/06 all used, not re-decided for HYP-07."),
        },
        "sample_size_disclosure": {
            "n_locked_events": len(events),
            "n_peers": len(locked_peers),
            "n_anchors": len(locked_anchors),
            "provisional_operative_floor_pairs": PROVISIONAL_FLOOR_PAIRS,
            "floor_source": SAMPLE_SIZE_GATE_MD.name,
            "framing": "EXPLORATORY, FLOOR CLEARED EXACTLY (provisional floor)",
            "why": (
                f"{len(events)} locked (peer, event) pairs clears the "
                f"provisional {PROVISIONAL_FLOOR_PAIRS}-pair floor -- but "
                "EXACTLY, not comfortably: the count and the floor are "
                "numerically identical, unlike HYP-06's own 778 pairs, "
                "which cleared the same floor by nearly 4x. Still framed "
                "exploratory, not confirmatory: the floor itself remains "
                "PROVISIONAL, and an even weaker borrow here than for "
                "HYP-06 (HYP-07's target is a different formula from the "
                "one the floor's k range was measured against) -- see "
                f"{SAMPLE_SIZE_GATE_MD.name}."),
        },
        "look_ahead_disclosure": {
            "already_touched": (
                "Every locked peer's raw close prices (auto_adjust=False) "
                "were fetched and used ONLY to compute point-in-time "
                "MARKET CAP for PS-1..PS-4 eligibility screening in "
                "run_hyp07_peer_market_cap.py. That computation never "
                "touched any peer's returns, signed cumulative abnormal "
                "return, or any quantity resembling this hypothesis's "
                "target measure. Relationship direction (competitor) was "
                "hand-verified from filing text during the round-7 "
                "review, which also never touches return data."),
            "not_touched": (
                "No log return, no signed cumulative abnormal return, "
                "and no beta has been computed for any locked peer "
                "around any locked anchor event, at any horizon, before "
                "this lock. This lock is written before that computation "
                "happens for the first time."),
        },
        "opens_no_gate": (
            "This is a computed HYP-07 Phase 2 lock, not a freeze, not a "
            "registry change, not a linkage ratification. It moves no "
            "gate condition, whatever the gate reads at the moment this "
            "file is read."),
        # Blank on purpose. See OWNER_FIELDS.
        "declared": False,
        "declared_by": "",
        "declared_date": "",
        "owner_fields": list(OWNER_FIELDS),
        "how_to_complete": (
            "python -m hyp04_supply_chain_hedge.ratify_hyp07 phase2 --template"),
        "status": "DRAFT -- inert until declared",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def load_declared_phase2_lock(path: Path) -> dict[str, Any]:
    """Read a SIGNED lock. Refuses a draft."""
    if not path.is_file():
        raise Phase2LockError(f"no HYP-07 Phase 2 lock at {path}")
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
        description="Write an INERT HYP-07 Phase 2 preregistration lock.")
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
        print("Next: python -m hyp04_supply_chain_hedge.ratify_hyp07 "
              "phase2 --template")
    return 0


if __name__ == "__main__":
    sys.exit(main())
