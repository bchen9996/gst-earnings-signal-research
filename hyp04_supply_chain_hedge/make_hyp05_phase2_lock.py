#!/usr/bin/env python3
"""HYP-05's Phase 2 preregistration lock -- target, model spec, and the
exact locked (peer, anchor-event) set. Mirrors HYP-04's own
`make_phase2_lock.py` in SHAPE (an inert draft, blank owner fields, a
human declares it) but is NOT that module modified: HYP-04's lock is tied
to its own plan section 5.3, its own D1-D10 analysis lock, and a
multi-hundred-event exploration/holdout split that does not exist for
HYP-05 and should not be invented to make this fit.

=== WHY THIS IS NOT SHAPED LIKE make_phase2_lock.py'S EXPLORATION/HOLDOUT
    SPLIT ===

HYP-04's split exists to prevent tuning a spec against the same data it is
later tested on: explore on one partition, hold out the other, lock the
spec before touching the holdout. HYP-05's real sample here is ONE peer
(AMBA), ONE anchor (NVDA), 8 real qualifying events -- there is no second
candidate peer or anchor to explore a specification against, so a further
carve-out of those 8 into "exploration" and "holdout" would not buy any
of the integrity property the split exists for; it would only shrink an
already-tiny sample for no reason. The actual risk this lock guards
against -- deciding the spec AFTER seeing how AMBA's returns behave
around these events -- is closed a different way: see LOOK-AHEAD
DISCLOSURE below, which states plainly what has and has not been
computed from AMBA's data before this lock exists.

=== THE EVENT SET IS DERIVED, NOT HAND-TYPED ===

The locked 8 (peer, anchor-event) pairs are read directly from the
already-committed `HYP05_PEER_UNIVERSE_HAND_CURATED_2026-09-12.json`
(qualifications where ticker == "AMBA" and qualifies is true) and
cross-joined against `HYP04_ANCHOR_SHOCKS_2026-08-31.csv` for each
event's event_id/attributed_session/shock -- never typed by hand, so a
transcription slip cannot silently lock the wrong dates. `build_draft`
asserts the derived count is exactly 8 and refuses otherwise, since a
different count would mean either artifact changed since this module was
written and the derivation should be re-examined, not silently trusted.

=== SAMPLE SIZE: EXPLORATORY, NOT CONFIRMATORY, STATED PLAINLY ===

`HYP05_SAMPLE_SIZE_GATE_2026-09-11.md`'s own provisional operative floor
is ~195 anchor events. This lock's N is 8 -- about 24x short. Decided
with the repo owner 2026-09-12: proceed anyway, but the lock and every
downstream result must say so plainly rather than let silence imply
adequate power. This is NOT a claim the floor is wrong or waived; it is
a claim that a small, explicitly-labelled exploratory check is still
worth running and reporting honestly, the same way every null result
this session has been reported.

=== MODEL SPEC: HYP-05'S OWN RE-DECIDED CLUSTERING ===

`clustered_se.HYP05_TWO_WAY_LIMITATION_NOTE` records HYP-05's own
re-decision (2026-09-12): PRIMARY clustering is one-way on the anchor
event itself (`event_id` in this package's own table shape), not
`calendar_period` (HYP-04's own D1-locked dimension) -- reported inside
`local_projection_analysis`/`_run_treatment` exactly as HYP-04's pipeline
already supports (`cluster_key` is a parameter there, not a hardcoded
constant). `calendar_period` is additionally reported as a SECOND,
one-way robustness lens via `clustered_se.dual_cluster_report` -- not a
two-way estimator, and not a replacement for the primary result.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .constants import (
    ANCHOR_ADJACENT_EXCLUSION_TRADING_DAYS,
    HORIZON_GRID,
    MIN_BUCKET_COUNT,
    MIN_RETAINED_HISTORY_FRACTION,
    N_PERMUTATIONS,
    RANDOM_SEED,
)
from .make_freeze_draft import _commit_sha, _sha256

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"
TARGET_PY = Path(__file__).resolve().parent / "target.py"
CONSTANTS_PY = Path(__file__).resolve().parent / "constants.py"
CLUSTERED_SE_PY = Path(__file__).resolve().parent / "clustered_se.py"

AS_OF = "2026-09-12"
OUT_JSON = LSE / f"HYP05_PHASE2_LOCK_{AS_OF}.json"

PEER_UNIVERSE_JSON = LSE / "HYP05_PEER_UNIVERSE_HAND_CURATED_2026-09-12.json"
ANCHOR_SHOCKS_CSV = LSE / "HYP04_ANCHOR_SHOCKS_2026-08-31.csv"
PEER_CLOSES_CSV = LSE / "HYP05_PEER_CLOSES_AMBA_2026-09-12.csv"
PEER_EARNINGS_JSON = LSE / "HYP05_PEER_EARNINGS_AMBA_2026-09-12.json"

LOCKED_PEER = "AMBA"
LOCKED_ANCHOR = "NVDA"
EXPECTED_N_EVENTS = 8

#: HYP-05's own re-decided primary/secondary clustering dimensions. See
#: clustered_se.HYP05_TWO_WAY_LIMITATION_NOTE and dual_cluster_report.
PRIMARY_CLUSTER_KEY = "event_id"
SECONDARY_CLUSTER_KEY = "calendar_period"

SAMPLE_SIZE_GATE_MD = LSE / "HYP05_SAMPLE_SIZE_GATE_2026-09-11.md"
PROVISIONAL_FLOOR_ANCHOR_EVENTS = 195

#: Fields a human must supply. Blank on every draft; that is what makes a
#: draft inert.
OWNER_FIELDS = ("declared", "declared_by", "declared_date")


class Phase2LockError(RuntimeError):
    """A precondition does not hold.

    Phase2LockError, never a bare `assert`: `python -O` strips asserts,
    and a precondition that vanishes under an optimisation flag is not
    one.
    """


def _locked_events(peer_universe_path: Path,
                   anchor_shocks_path: Path) -> list[dict[str, Any]]:
    """The exact (peer, anchor-event) rows this lock fixes -- derived from
    two already-committed artifacts, never hand-typed. See module
    docstring, "THE EVENT SET IS DERIVED, NOT HAND-TYPED"."""
    universe = json.loads(peer_universe_path.read_text(encoding="utf-8"))
    qualifying_dates: list[str] = []
    for q in universe["qualifications"]:
        if q["ticker"] != LOCKED_PEER or not q["qualifies"]:
            continue
        cand = q["evidence"]["candidate"]
        if cand["anchor_ticker"] != LOCKED_ANCHOR:
            continue
        qualifying_dates.append(cand["anchor_event_date"])
    qualifying_dates = sorted(set(qualifying_dates))

    with anchor_shocks_path.open(encoding="utf-8", newline="") as fh:
        shock_rows = {r["release_date"]: r for r in csv.DictReader(fh)
                     if r["anchor_ticker"] == LOCKED_ANCHOR}

    events: list[dict[str, Any]] = []
    for d in qualifying_dates:
        row = shock_rows.get(d)
        if row is None:
            raise Phase2LockError(
                f"qualifying date {d!r} has no matching {LOCKED_ANCHOR} row "
                f"in {anchor_shocks_path.name} -- the two artifacts have "
                "drifted apart")
        events.append({
            "event_id": row["event_id"],
            "anchor_ticker": LOCKED_ANCHOR,
            "peer_ticker": LOCKED_PEER,
            "release_date": row["release_date"],
            "attributed_session": row["attributed_session"],
            "shock": float(row["shock"]),
        })
    return events


def build_draft(*, out_path: Path = OUT_JSON,
                peer_universe_path: Path = PEER_UNIVERSE_JSON,
                anchor_shocks_path: Path = ANCHOR_SHOCKS_CSV,
                peer_closes_path: Path = PEER_CLOSES_CSV,
                peer_earnings_path: Path = PEER_EARNINGS_JSON,
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
        ("anchor shocks", anchor_shocks_path),
        ("peer closes", peer_closes_path),
        ("peer earnings", peer_earnings_path),
        ("sample-size gate", SAMPLE_SIZE_GATE_MD),
    ):
        if not p.is_file():
            raise Phase2LockError(f"no {label} at {p}")

    events = _locked_events(peer_universe_path, anchor_shocks_path)
    if len(events) != EXPECTED_N_EVENTS:
        raise Phase2LockError(
            f"derived {len(events)} qualifying (peer, anchor-event) "
            f"row(s), expected exactly {EXPECTED_N_EVENTS}. Either "
            f"{peer_universe_path.name} or {anchor_shocks_path.name} has "
            "changed since this module was written -- re-examine the "
            "derivation rather than trusting a different count.")

    sha = _commit_sha(repo)  # refuses on a dirty tree

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-05",
        "what_this_is": (
            "The Phase 2 preregistration lock: the exact locked (peer, "
            "anchor-event) set, target definition, and model spec, fixed "
            "before any target/outcome value has been computed for AMBA "
            "around any NVDA event. See 'LOOK-AHEAD DISCLOSURE' below for "
            "exactly what has and has not already been touched."),
        "what_this_is_not": (
            "Not a result, not the one locked run (that is "
            "make_hyp05_phase3_run.py, separate and not yet executed), "
            "and not permission to compute anything. It constrains what "
            "that later, separate, explicitly-authorized run may do; it "
            "performs none."),
        "governing_documents": {
            "hyp04_phase2_lock_shape": "make_phase2_lock.py (mirrored in "
                                       "shape, not modified or extended)",
            "sample_size_gate": SAMPLE_SIZE_GATE_MD.name,
            "clustering_redecision": "clustered_se.HYP05_TWO_WAY_LIMITATION_NOTE",
        },
        "pins": {
            "peer_universe": peer_universe_path.name,
            "peer_universe_sha256": _sha256(peer_universe_path),
            "anchor_shocks": anchor_shocks_path.name,
            "anchor_shocks_sha256": _sha256(anchor_shocks_path),
            "peer_closes": peer_closes_path.name,
            "peer_closes_sha256": _sha256(peer_closes_path),
            "peer_earnings": peer_earnings_path.name,
            "peer_earnings_sha256": _sha256(peer_earnings_path),
            "target_py_sha256": _sha256(TARGET_PY),
            "constants_py_sha256": _sha256(CONSTANTS_PY),
            "clustered_se_py_sha256": _sha256(CLUSTERED_SE_PY),
            "lock_declared_at_commit": sha,
        },
        "locked_peer": LOCKED_PEER,
        "locked_anchor": LOCKED_ANCHOR,
        "locked_events": events,
        "n_locked_events": len(events),
        "target_definition": {
            "formula": (
                "RVar(h) = (1/h) * sum_{i=1..h} r_i^2 over [t+1, t+h]; "
                "RVar_ref = (1/20) * sum r_i^2 over the trailing 20 "
                "sessions ending at the anchor's earnings date; raw = "
                "log(RVar(h)) - log(RVar_ref); target = raw - "
                "earnings_cycle_baseline(peer, days_to_own_earnings) -- "
                "IDENTICAL to HYP-04's own locked formula, reused "
                "unchanged, not re-derived."),
            "horizon_grid": list(HORIZON_GRID),
            "residualization": "REQUIRED, not optional -- same as HYP-04.",
            "min_bucket_count": MIN_BUCKET_COUNT,
            "min_retained_history_fraction": MIN_RETAINED_HISTORY_FRACTION,
            "anchor_adjacent_exclusion_trading_days":
                ANCHOR_ADJACENT_EXCLUSION_TRADING_DAYS,
            "source": "target.py, hash-pinned above, reused unmodified",
        },
        "model_spec": {
            "estimator": (
                "local projections with CR2 clustered standard errors, "
                "Satterthwaite degrees of freedom, and max-T permutation "
                "multiplicity correction -- reused unmodified from "
                "inference.py/clustered_se.py"),
            "primary_cluster_key": PRIMARY_CLUSTER_KEY,
            "primary_cluster_key_note": (
                "HYP-05's own re-decision (clustered_se."
                "HYP05_TWO_WAY_LIMITATION_NOTE), NOT HYP-04's D1-locked "
                "calendar_period. With one peer and one anchor, "
                "event_id clustering here means exactly 8 clusters (one "
                "per locked event) -- a small-sample scenario, "
                "consistent with the exploratory framing below."),
            "secondary_cluster_key_robustness_lens": SECONDARY_CLUSTER_KEY,
            "secondary_cluster_key_note": (
                "Reported via clustered_se.dual_cluster_report -- two "
                "ONE-WAY clusterings shown side by side, never a two-way "
                "estimator. The primary result above is HYP-05's actual "
                "inferential result; this is a robustness lens only."),
            "residualize": True,
            "n_permutations": N_PERMUTATIONS,
            "random_seed": RANDOM_SEED,
            "n_permutations_note": (
                "Reused from HYP-04's own constants -- permutation-test "
                "validity does not depend on N being large, only power "
                "does, and power is already disclosed as inadequate "
                "below."),
        },
        "sample_size_disclosure": {
            "n_locked_events": len(events),
            "n_peers": 1,
            "max_rows_before_exclusions": len(events) * len(HORIZON_GRID),
            "provisional_operative_floor_anchor_events":
                PROVISIONAL_FLOOR_ANCHOR_EVENTS,
            "floor_source": SAMPLE_SIZE_GATE_MD.name,
            "framing": "EXPLORATORY, NOT CONFIRMATORY",
            "why": (
                f"{len(events)} locked events is roughly "
                f"{PROVISIONAL_FLOOR_ANCHOR_EVENTS / len(events):.0f}x "
                "short of HYP-05's own provisional 195-event operative "
                "floor. Decided with the repo owner 2026-09-12: proceed "
                "anyway, but every downstream result must state this "
                "plainly rather than let silence imply adequate power. "
                "This is not a claim the floor is wrong or waived."),
        },
        "look_ahead_disclosure": {
            "already_touched": (
                "AMBA's raw close prices (auto_adjust=False) were fetched "
                "and used ONLY to compute point-in-time MARKET CAP for "
                "PS-3 eligibility screening in run_hyp05_peer_market_cap."
                "py (committed 751d9c5 / 3d7a240 / abf4527). That "
                "computation never touched AMBA's returns, realized "
                "variance, or any quantity resembling this hypothesis's "
                "target measure."),
            "not_touched": (
                "No log return, no realized-variance ratio, and no "
                "residualized target value has been computed for AMBA "
                "around any NVDA event, at any horizon, before this "
                "lock. This lock is written before that computation "
                "happens for the first time."),
            "why_this_replaces_a_holdout_split": (
                "HYP-04's exploration/holdout split guards against "
                "tuning a spec after seeing how it performs on some "
                "data. With one peer and one anchor there is no second "
                "candidate to explore a spec against, so a further "
                "split of these 8 events would not buy that property; "
                "it would only shrink an already-tiny sample. The "
                "disclosure above closes the actual risk directly: the "
                "spec below was fixed before AMBA's outcome data was "
                "ever computed, not merely before some OTHER data was "
                "computed."),
        },
        "peer_relationship_note": (
            "AMBA's qualifying edge is sourced from "
            f"{peer_universe_path.name} as relationship_type="
            "'sector_competitor', from a real, filed NVDA 10-K sentence "
            "(EDGAR_10K_FULLTEXT_SEARCH_HAND_CURATED_VERIFIED) naming "
            "Ambarella among SOC-product competitors -- not an "
            "independently verified claim beyond what that sentence "
            "itself says."),
        "opens_no_gate": (
            "This is a computed HYP-05 Phase 2 lock, not a freeze, not a "
            "registry change, not a linkage ratification. It moves no "
            "gate condition, whatever the gate reads at the moment this "
            "file is read."),
        # Blank on purpose. See OWNER_FIELDS.
        "declared": False,
        "declared_by": "",
        "declared_date": "",
        "owner_fields": list(OWNER_FIELDS),
        "how_to_complete": (
            "python -m hyp04_supply_chain_hedge.ratify_hyp05 phase2 --template"),
        "status": "DRAFT -- inert until declared",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def load_declared_phase2_lock(path: Path) -> dict[str, Any]:
    """Read a SIGNED lock. Refuses a draft. Mirrors HYP-04's own
    `load_declared_phase2_lock` -- an unsigned document must not answer
    "what is locked", or a run could proceed against a spec nobody
    committed to."""
    if not path.is_file():
        raise Phase2LockError(f"no HYP-05 Phase 2 lock at {path}")
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
        description="Write an INERT HYP-05 Phase 2 preregistration lock.")
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

    print(f"locked peer/anchor : {doc['locked_peer']} / {doc['locked_anchor']}")
    print(f"n_locked_events    : {doc['n_locked_events']}")
    for ev in doc["locked_events"]:
        print(f"  {ev['event_id']:16s} attributed={ev['attributed_session']} "
              f"shock={ev['shock']:.4f}")
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
        print("Next: python -m hyp04_supply_chain_hedge.ratify_hyp05 "
              "phase2 --template")
    return 0


if __name__ == "__main__":
    sys.exit(main())
