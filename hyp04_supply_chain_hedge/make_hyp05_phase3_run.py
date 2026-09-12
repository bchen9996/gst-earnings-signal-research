#!/usr/bin/env python3
"""HYP-05 Phase 3 -- the one exploratory run against AMBA's real returns.

Mirrors HYP-04's own `make_phase3_run.py` in SHAPE (authorization required
BEFORE computation, an in-process synthetic rehearsal every invocation, at
most one result ever, the authorization consumed the instant a real run
succeeds) but is NOT that module modified: HYP-04's run rejoins a 57-event
HOLDOUT out of a multi-hundred-event panel via a curated linkage map and a
validation split. HYP-05 has no panel, no split, and no curated map to
rejoin against -- `make_hyp05_phase2_lock.py`'s own docstring already
explains why that split does not transfer to a single (peer, anchor) pair.
The 8 locked events here are not rejoined from anything: they are already
fully specified, verbatim, inside the signed Phase 2 lock's own
`locked_events` list (event_id, attributed_session, shock), so this module's
only real job is building the ONE `SyntheticPanel`-shaped structure AMBA's
real closes and earnings support, and running the SAME estimator HYP-04
already validated (`make_phase1_diagnostics._run_treatment`) over it.

=== AUTHORIZATION, REHEARSAL, NO-RERUN: THE SAME THREE GUARANTEES ===

  1. A signed `HYP05_PHASE3_AUTHORIZATION_<date>.json`
     (`ratify_hyp05.py phase3`) must already exist, unconsumed, with its
     `pinned_phase2_lock_sha256` matching the signed HYP-05 Phase 2 lock's
     actual hash right now. This module writes none of the authorization's
     fields; the owner types the affirmation themselves, exactly as for
     HYP-04's own `ratify phase3`.
  2. `run_rehearsal()` (a `fixtures.make_panel`-shaped synthetic panel, run
     through the SAME `make_phase1_diagnostics._run_treatment` path the
     real check will use, clustered on HYP-05's own primary key) runs EVERY
     time `main()` is invoked, before any real file is opened.
  3. If ANY `HYP05_PHASE3_RESULT_*.json` already exists anywhere under
     `Live Signal Engine/`, this refuses unconditionally. This exploratory
     check is run ONCE, same as HYP-04's holdout, even though it is not a
     holdout and not confirmatory.

=== REUSE, NOT REIMPLEMENTATION ===

`make_phase1_diagnostics._run_treatment`, `_calendar_period_int`, and
`_attribute_peer_earnings` are imported unchanged -- none of them know or
care whether the panel behind them is HYP-04's holdout or HYP-05's single
peer. `peer_returns.load_peer_closes`/`build_series`/`normalize_sessions`,
`target.build_feature_table`, `inference._design_matrix`, and
`clustered_se.dual_cluster_report` are likewise reused unchanged.

=== THE SECONDARY LENS, COMPUTED HERE FOR THE FIRST TIME ===

`clustered_se.dual_cluster_report` existed before this module (written for
HYP-05, per `HYP05_TWO_WAY_LIMITATION_NOTE`) but had no real caller --
its only exercise was synthetic fixtures in
`test_hyp04_supply_chain_hedge_clustered_se.py`. `_secondary_lens` below is
that first real caller: one call per horizon the primary result already
discloses under D6, never a wider or narrower set, so the robustness lens
answers exactly the same question the primary result does.

=== A LABEL THIS MODULE DOES NOT GET TO REWRITE ===

`inference.local_projection_analysis` stamps every fit's `clustering` field
"-- SENSITIVITY, NOT THE D1 PRIMARY" whenever `cluster_key !=
constants.LOCKED_CLUSTER_KEY` ("calendar_period", HYP-04's own D1). HYP-05's
primary key is `event_id`, so that generic, HYP-04-authored label appears
verbatim in this module's own primary result -- describing HYP-04's D1
decision, not HYP-05's. Rather than editing shared, HYP-04-load-bearing code
to special-case a second hypothesis's vocabulary, `build_result` carries an
explicit `clustering_label_note` beside it so the artifact explains its own
apparently-contradictory label rather than silently living with it.

Never a bare `assert`: `python -O` strips asserts, and a guard that
vanishes under an optimisation flag is not a guard.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

import numpy as np

from . import make_phase1_diagnostics as P1
from .clustered_se import dual_cluster_report
from .fixtures import SyntheticPanel, make_panel
from .inference import _design_matrix
from .make_freeze_draft import _commit_sha, _sha256
from .make_hyp05_phase2_lock import (
    ANCHOR_SHOCKS_CSV,
    CLUSTERED_SE_PY,
    CONSTANTS_PY,
    LOCKED_ANCHOR,
    LOCKED_PEER,
    PEER_CLOSES_CSV,
    PEER_EARNINGS_JSON,
    PEER_UNIVERSE_JSON,
    PRIMARY_CLUSTER_KEY,
    SECONDARY_CLUSTER_KEY,
    TARGET_PY,
    Phase2LockError,
    load_declared_phase2_lock,
)
from .peer_returns import build_series, load_peer_closes, normalize_sessions
from .target import build_feature_table

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

AS_OF = "2026-09-12"
DEFAULT_PHASE2_LOCK = LSE / f"HYP05_PHASE2_LOCK_{AS_OF}.json"

RESULT_PATTERN = "HYP05_PHASE3_RESULT_*.json"
AUTHORIZATION_PATTERN = "HYP05_PHASE3_AUTHORIZATION_*.json"


class Phase3Error(RuntimeError):
    """A precondition does not hold.

    Phase3Error, never a bare `assert`: this is the one place in HYP-05's
    package where that would matter most.
    """


# ==========================================================================
# 1. The in-process rehearsal. Runs every time, before any real file opens.
# ==========================================================================

def run_rehearsal(*, n_permutations: int = 200, seed: int = 42) -> dict[str, Any]:
    """Exercise the FULL estimator + D6/D7 disclosure path on synthetic data,
    clustered on HYP-05's own primary key, before touching anything real."""
    panel = make_panel(
        "hyp05-phase3-rehearsal", n_anchors=4, n_quarters=5,
        n_peers_per_anchor=3, injected_lag=None, injected_effect=0.0,
        seed=seed)
    result = P1._run_treatment(
        panel, residualize=True, cluster_key=PRIMARY_CLUSTER_KEY,
        n_permutations=n_permutations, seed=seed)
    if result["n_rows"] <= 0:
        raise Phase3Error(
            "the synthetic rehearsal produced zero rows -- it must actually "
            "exercise the pipeline, not pass vacuously")
    if not result["d6_disclosures"]:
        raise Phase3Error(
            "the synthetic rehearsal produced no D6 disclosure -- the real "
            "run's disclosure path is untested")
    return result


# ==========================================================================
# 2. Authorization: read, verify, and (only after a real run) consume it.
# ==========================================================================

#: What `ratify_hyp05 phase3` requires you to type, verbatim, BEFORE any
#: computation happens -- see ratify_hyp05.py's HYP05_PHASE3_AFFIRMATION for
#: the single source of truth. Duplicated here as a constant ONLY for the
#: refusal message; the actual comparison happens in ratify_hyp05.py.
AUTHORIZATION_FIELDS = ("declared", "declared_by", "declared_date",
                        "attestation_text", "pinned_commit_sha",
                        "pinned_phase2_lock_sha256", "consumed")


def _find_authorization(lse: Path) -> Optional[Path]:
    hits = sorted(lse.glob(AUTHORIZATION_PATTERN))
    if len(hits) > 1:
        raise Phase3Error(
            f"{len(hits)} HYP-05 Phase 3 authorization files exist "
            f"({[p.name for p in hits]}) -- exactly one is expected. "
            "Refusing rather than guessing which one governs.")
    return hits[0] if hits else None


def _load_valid_authorization(lse: Path, *, repo: Path,
                              phase2_lock_path: Path) -> dict[str, Any]:
    path = _find_authorization(lse)
    if path is None:
        raise Phase3Error(
            "no HYP-05 Phase 3 authorization on disk. The real run requires "
            "one, typed by the owner BEFORE any computation -- see "
            "'python -m hyp04_supply_chain_hedge.ratify_hyp05 phase3 "
            "--template'. This module will not compute against AMBA's real "
            "returns without it.")
    doc = json.loads(path.read_text(encoding="utf-8"))
    for f in AUTHORIZATION_FIELDS:
        if f not in doc:
            raise Phase3Error(
                f"{path.name} has no {f!r} key; this does not look like an "
                "authorization written by 'ratify_hyp05 phase3'")
    if doc["declared"] is not True:
        raise Phase3Error(f"{path.name} is a draft: 'declared' is not true.")
    if doc["consumed"] is True:
        raise Phase3Error(
            f"{path.name} was already consumed by a prior run "
            f"(consumed_by={doc.get('consumed_by_result')!r}). A consumed "
            "authorization cannot trigger a second run.")
    # Same fixed-point reasoning as HYP-04's own `_load_valid_authorization`:
    # `_commit_sha` still runs (refuses on a dirty tree), but its VALUE is
    # never compared against `pinned_commit_sha` -- see that function's own
    # comment for why that particular comparison cannot hold in general.
    _commit_sha(repo)
    lock_sha = _sha256(phase2_lock_path)
    if doc["pinned_phase2_lock_sha256"] != lock_sha:
        raise Phase3Error(
            f"{path.name} authorizes Phase 2 lock hash "
            f"{doc['pinned_phase2_lock_sha256'][:12]}, but the lock on disk "
            f"now hashes to {lock_sha[:12]}. Re-authorize against the "
            "current lock rather than running against drift.")
    return doc


def _consume_authorization(path: Path, *, result_artifact_name: str) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["consumed"] = True
    doc["consumed_by_result"] = result_artifact_name
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")


# ==========================================================================
# 3. Build the one real SyntheticPanel from AMBA's own fetched data and the
#    lock's already-derived events. No rejoin: the 8 events are already
#    fully specified inside the signed lock.
# ==========================================================================

def _build_real_panel(*, lock: dict[str, Any], peer_closes_path: Path,
                      peer_earnings_path: Path
                      ) -> tuple[SyntheticPanel, dict[str, Any]]:
    obs, rejects, closes_sha = load_peer_closes(peer_closes_path)
    if rejects:
        raise Phase3Error(
            f"{peer_closes_path.name} has {len(rejects)} unparseable row(s) "
            "-- refusing rather than silently dropping them")
    tickers = {o.ticker for o in obs}
    if tickers != {LOCKED_PEER}:
        raise Phase3Error(
            f"{peer_closes_path.name} names {sorted(tickers)}, expected "
            f"only {LOCKED_PEER!r}")

    idx = normalize_sessions(sorted({o.session_date for o in obs}))
    pos = {d: i for i, d in enumerate(idx)}
    series = build_series(obs, ticker=LOCKED_PEER, sessions=idx)

    peer_earnings_days, earnings_coverage = P1._attribute_peer_earnings(
        peer_earnings_path, idx, peers=[LOCKED_PEER])

    anchor_events: list[dict[str, Any]] = []
    for ev in lock["locked_events"]:
        d = date.fromisoformat(ev["attributed_session"])
        day = pos.get(d)
        if day is None:
            raise Phase3Error(
                f"locked event {ev['event_id']}'s attributed session "
                f"{ev['attributed_session']} is not a session in "
                f"{LOCKED_PEER}'s own trading calendar -- refusing rather "
                "than guessing which nearby session it means")
        anchor_events.append({
            "anchor": ev["anchor_ticker"],
            "anchor_day": day,
            "shock": float(ev["shock"]),
            "peers": [LOCKED_PEER],
            "calendar_period": P1._calendar_period_int(ev["event_id"]),
        })

    returns = {LOCKED_PEER: np.array(
        [np.nan if r is None else r for r in series.log_returns], dtype=float)}

    panel = SyntheticPanel(
        name=f"hyp05-phase3-real-{LOCKED_PEER}",
        returns=returns, peer_earnings_days=peer_earnings_days,
        anchor_events=anchor_events, n_trading_days=len(idx),
        injected_lag=None, injected_effect=0.0, injected_effect_window=0,
        peer_base_vol={}, earnings_ramp_amplitude=0.0,
        truth={"real_data": True, "not_applicable": True},
    )
    extra = {
        "peer_closes_sha256": closes_sha,
        "n_sessions": len(idx),
        "first_session": idx[0].isoformat(),
        "last_session": idx[-1].isoformat(),
        "peer_earnings_coverage": earnings_coverage,
    }
    return panel, extra


# ==========================================================================
# 4. The secondary robustness lens -- the first real caller of
#    clustered_se.dual_cluster_report, at exactly the horizons the primary
#    result already discloses under D6.
# ==========================================================================

def _secondary_lens(panel: SyntheticPanel, horizons: list[int], *,
                    residualize: bool) -> list[dict[str, Any]]:
    """Reuses the SAME residualize choice the primary treatment ran with --
    a lens computed on a differently-residualized table would not be
    answering the same question the primary result answers."""
    table = build_feature_table(panel, residualize=residualize)["table"]
    out: list[dict[str, Any]] = []
    for h in horizons:
        mask = table["horizon"] == h
        n = int(mask.sum())
        if n < 3:
            out.append({"horizon": h, "n_rows": n,
                        "note": "fewer than 3 rows -- no secondary lens computed"})
            continue
        g_primary = table[PRIMARY_CLUSTER_KEY][mask]
        g_secondary = table[SECONDARY_CLUSTER_KEY][mask]
        if np.unique(g_primary).size < 2 or np.unique(g_secondary).size < 2:
            out.append({
                "horizon": h, "n_rows": n,
                "note": "fewer than 2 distinct clusters on one dimension -- "
                        "no secondary lens computed"})
            continue
        X = _design_matrix(table, mask, controls=True)
        y = table["target"][mask]
        r = dual_cluster_report(X, y, g_primary, g_secondary)
        out.append({
            "horizon": h,
            "n_rows": n,
            "beta_shock": float(r["beta"][1]),
            "primary_se": float(r["primary"]["se"][1]),
            "primary_n_clusters": r["primary"]["n_clusters"],
            "secondary_se": float(r["secondary"]["se"][1]),
            "secondary_n_clusters": r["secondary"]["n_clusters"],
            "se_ratio_secondary_over_primary":
                float(r["se_ratio_secondary_over_primary"][1]),
            "note": r["note"],
        })
    return out


# ==========================================================================
# 5. Orchestration
# ==========================================================================

def build_result(*, out_path: Path, phase2_lock_path: Path = DEFAULT_PHASE2_LOCK,
                 peer_closes_path: Path = PEER_CLOSES_CSV,
                 peer_earnings_path: Path = PEER_EARNINGS_JSON,
                 lse: Path = LSE, repo: Path = REPO_ROOT,
                 today: Optional[date] = None) -> dict[str, Any]:
    """The one real, exploratory run. Refuses unless authorized, un-run, and
    un-drifted."""
    when = today or date.today()

    if out_path.exists():
        raise Phase3Error(
            f"{out_path.name} already exists. Dated artifacts are never "
            "overwritten.")
    existing_results = sorted(lse.glob(RESULT_PATTERN))
    if existing_results:
        raise Phase3Error(
            f"a HYP-05 Phase 3 result already exists "
            f"({[p.name for p in existing_results]}) -- this exploratory "
            "check is run ONCE. Refusing regardless of --out.")

    lock = load_declared_phase2_lock(phase2_lock_path)

    for label, pinned_path, pinned_hash in (
        ("target.py", TARGET_PY, lock["pins"]["target_py_sha256"]),
        ("constants.py", CONSTANTS_PY, lock["pins"]["constants_py_sha256"]),
        ("clustered_se.py", CLUSTERED_SE_PY, lock["pins"]["clustered_se_py_sha256"]),
    ):
        current = _sha256(pinned_path)
        if current != pinned_hash:
            raise Phase3Error(
                f"{label} has changed since the Phase 2 lock was declared "
                f"(pinned {pinned_hash[:12]}, now {current[:12]}). The lock "
                "no longer describes the code that would run.")

    for label, path, key in (
        ("peer universe", PEER_UNIVERSE_JSON, "peer_universe_sha256"),
        ("anchor shocks", ANCHOR_SHOCKS_CSV, "anchor_shocks_sha256"),
        ("peer closes", peer_closes_path, "peer_closes_sha256"),
        ("peer earnings", peer_earnings_path, "peer_earnings_sha256"),
    ):
        current = _sha256(path)
        if current != lock["pins"][key]:
            raise Phase3Error(
                f"{label} on disk does not match the Phase 2 lock's pinned "
                f"hash (pinned {lock['pins'][key][:12]}, now {current[:12]})"
                ". It has drifted since the lock was declared.")

    auth_path = _find_authorization(lse)
    auth = _load_valid_authorization(lse, repo=repo,
                                     phase2_lock_path=phase2_lock_path)

    # The rehearsal runs even here, one more time, immediately before the
    # real computation.
    run_rehearsal()

    panel, extra = _build_real_panel(
        lock=lock, peer_closes_path=peer_closes_path,
        peer_earnings_path=peer_earnings_path)

    treatment = P1._run_treatment(
        panel, residualize=lock["model_spec"]["residualize"],
        cluster_key=lock["model_spec"]["primary_cluster_key"],
        n_permutations=lock["model_spec"]["n_permutations"],
        seed=lock["model_spec"]["random_seed"])

    reported_horizons = sorted({d["horizon"] for d in treatment["d6_disclosures"]
                                if "horizon" in d})
    secondary = _secondary_lens(panel, reported_horizons,
                               residualize=lock["model_spec"]["residualize"])

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-05",
        "phase": "Phase 3 -- the one exploratory run against AMBA's real "
                "returns (see HYP05_PHASE2_LOCK's sample_size_disclosure)",
        "what_this_is": (
            "The single, preregistered, exploratory run of the Phase "
            f"2-locked spec against {LOCKED_PEER}'s real returns around "
            f"{LOCKED_ANCHOR}'s 8 locked anchor events. Reported once, "
            "regardless of outcome."),
        "what_this_is_not": (
            "NOT confirmatory (8 events is roughly 24x short of HYP-05's "
            "own 195-event provisional floor -- see sample_size_disclosure "
            "below), NOT repeatable, and NOT a license to iterate on the "
            "spec having seen this. A disappointing or a striking result "
            "gets reported exactly the same way."),
        "reported_regardless_of_outcome": True,
        "no_rerun_permitted": True,
        "point_estimate_permitted": False,
        "is_a_confidence_interval": False,
        "sample_size_disclosure": dict(lock["sample_size_disclosure"]),
        "look_ahead_disclosure": dict(lock["look_ahead_disclosure"]),
        "authorization": {
            "artifact": auth_path.name,
            "declared_by": auth["declared_by"],
            "declared_date": auth["declared_date"],
        },
        "phase2_lock": {
            "artifact": phase2_lock_path.name,
            "declared_by": lock["declared_by"],
            "declared_date": lock["declared_date"],
            "sha256": _sha256(phase2_lock_path),
        },
        "locked_peer": LOCKED_PEER,
        "locked_anchor": LOCKED_ANCHOR,
        "n_locked_events": len(lock["locked_events"]),
        "locked_event_ids": [ev["event_id"] for ev in lock["locked_events"]],
        "treatment": treatment,
        "clustering_label_note": (
            "treatment.clustering below reads '-- SENSITIVITY, NOT THE D1 "
            "PRIMARY' because inference.local_projection_analysis stamps "
            "that label whenever cluster_key != constants.LOCKED_CLUSTER_"
            "KEY ('calendar_period', HYP-04's own D1). That label describes "
            "HYP-04's decision, not HYP-05's: clustered_se."
            "HYP05_TWO_WAY_LIMITATION_NOTE records HYP-05's own re-decision "
            "(2026-09-12) that event_id IS its primary clustering "
            "dimension. Read the label as HYP-04 vocabulary surfacing "
            "through reused code, not as a statement that this is a "
            "sensitivity check -- it is HYP-05's actual inferential "
            "result."),
        "secondary_cluster_robustness_lens": {
            "dimension": SECONDARY_CLUSTER_KEY,
            "per_horizon": secondary,
            "note": ("Two ONE-WAY clusterings shown side by side, never a "
                    "two-way estimator -- see clustered_se."
                    "dual_cluster_report and HYP05_TWO_WAY_LIMITATION_NOTE. "
                    "The primary result above is HYP-05's actual "
                    "inferential result; this is a robustness lens only, "
                    "computed at exactly the horizons the primary result "
                    "already discloses under D6."),
        },
        "peer_data_provenance": extra,
        "sources": {
            "phase2_lock_sha256": _sha256(phase2_lock_path),
            "peer_closes": peer_closes_path.name,
            "peer_closes_sha256": _sha256(peer_closes_path),
            "peer_earnings": peer_earnings_path.name,
            "peer_earnings_sha256": _sha256(peer_earnings_path),
        },
        "opens_no_gate": (
            "This is a computed HYP-05 Phase 3 result, not a freeze, not a "
            "registry change, not a linkage ratification. It moves no gate "
            "condition, whatever the gate reads at the moment this file is "
            "read."),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1, default=str) + "\n",
                        encoding="utf-8")
    _consume_authorization(auth_path, result_artifact_name=out_path.name)
    return doc


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="HYP-05 Phase 3: the one exploratory run against "
                    "AMBA's real returns. Requires a prior, typed "
                    "'ratify_hyp05 phase3' authorization.")
    ap.add_argument("--phase2-lock", type=Path, default=DEFAULT_PHASE2_LOCK)
    ap.add_argument("--peer-closes", type=Path, default=PEER_CLOSES_CSV)
    ap.add_argument("--peer-earnings", type=Path, default=PEER_EARNINGS_JSON)
    ap.add_argument("--out", type=Path, default=None,
                    help="default: Live Signal Engine/"
                         "HYP05_PHASE3_RESULT_<today>.json")
    ap.add_argument("--rehearsal-only", action="store_true",
                    help="run ONLY the synthetic rehearsal; touches no real "
                         "file, requires no authorization")
    a = ap.parse_args(argv)

    if a.rehearsal_only:
        result = run_rehearsal()
        print("REHEARSAL ONLY -- synthetic data, nothing real touched.")
        print(f"  rows={result['n_rows']}  peak_horizon={result['peak_horizon']}  "
              f"onset_interval={result['onset_interval'] and result['onset_interval']['reported_interval']}")
        return 0

    out = a.out or (LSE / f"HYP05_PHASE3_RESULT_{date.today().isoformat()}.json")
    doc = build_result(out_path=out, phase2_lock_path=a.phase2_lock,
                       peer_closes_path=a.peer_closes,
                       peer_earnings_path=a.peer_earnings)

    t = doc["treatment"]
    print(f"locked peer/anchor : {doc['locked_peer']} / {doc['locked_anchor']}")
    print(f"n_locked_events    : {doc['n_locked_events']}")
    print(f"peak_horizon={t['peak_horizon']}  peak_significant={t['peak_significant']}  "
          f"k_eff={t['effective_independent_tests']}")
    print(f"onset_interval={t['onset_interval'] and t['onset_interval']['reported_interval']}")
    print(f"\nWROTE {doc['artifact']}")
    print("EXPLORATORY, NOT CONFIRMATORY (see sample_size_disclosure). This "
          "check is now spent;\nno further run against this lock is permitted.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Phase3Error as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(1)
