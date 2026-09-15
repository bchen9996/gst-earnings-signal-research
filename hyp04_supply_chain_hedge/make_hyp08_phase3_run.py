#!/usr/bin/env python3
"""HYP-08 Phase 3 -- the one exploratory run against the real, pooled
973-pair, 31-peer, ~33-anchor universe, testing same-session reaction and
reaction heterogeneity for the first time in this project.

Mirrors `make_hyp07_phase3_run.py` in SHAPE (authorization required BEFORE
computation, an in-process synthetic rehearsal every invocation, at most
one result ever, the authorization consumed the instant a real run
succeeds) but its TREATMENT is structurally different from every prior
hypothesis's own: there is no horizon grid, so none of
`local_projection_analysis`'s onset/peak/max-T-permutation/D6-disclosure
machinery applies. `target_same_session.build_feature_table_same_session`
produces one row per (event, peer) -- not per (event, peer, horizon) --
and TWO fits are computed directly: `inference.fit_local_projections(
table, horizons=(0,))` (the plain pooled test) and `inference.
fit_interaction_model(table)` (the heterogeneity test), each judged
against `make_hyp08_sample_size_gate.sidak_critical_t`'s closed-form,
k=2-exact critical value -- not a permutation null, since there is no
max-selection-over-correlated-horizons problem here to need one.

=== EXACTLY TWO QUANTITIES ARE HELD TO THE CORRECTED THRESHOLD ===

`inference.fit_interaction_model` also returns `beta_customer_supplier`
and `beta_competitor_implied` -- useful for INTERPRETING what a
significant interaction term means, but neither is one of HYP-08's two
preregistered, Sidak-corrected tests (see
`HYP08_PHASE2_LOCK_*.json`'s own `model_spec.test_family`). This module
reports both for descriptive context and explicitly labels them
NOT-VERDICTED, so a reader cannot mistake a merely descriptive number for
a third, uncorrected significance claim -- exactly the "do not keep
adding tests" discipline external review's own feedback asked for.

=== THE FIELD-NAME SUBTLETY, ONCE MORE, NOW ACROSS A POOLED SOURCE ===

Same substitution `make_hyp07_phase3_run.py`'s own docstring describes:
`_group_by_event_same_session` reads `ev["excess_return"]` (SIGNED) from
the pooled lock's own locked events into the generic `shock` slot every
target module shares -- for BOTH the customer/supplier side (looked up
fresh by `make_hyp08_phase2_lock.py` from the anchor-shocks CSVs) and the
competitor side (already carried by HYP-07's own lock). It additionally
carries `relationship_type` per event -- confirmed, not assumed, that no
single anchor event mixes relationship types across its own peers (a
live check against the real pooled lock at build time; see module
docstring's own verification note in the project's build history).

=== REUSE, NOT REIMPLEMENTATION ===

`make_phase1_diagnostics._attribute_peer_earnings`, `make_event_panel.
_session_index`, `peer_returns.load_peer_closes`/`build_series` are
imported unchanged -- none of these are specific to any one target.
`make_phase1_diagnostics._calendar_period_int` is reused for the pooled,
namespaced event_id strings exactly as every prior hypothesis's own
module reuses it.

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
from .fixtures_same_session import make_panel_same_session
from .inference import fit_interaction_model, fit_local_projections
from .make_event_panel import _session_index
from .make_freeze_draft import _commit_sha, _sha256
from .make_hyp08_phase2_lock import (
    ANCHOR_SHOCKS_CSVS,
    ANCHOR_SHOCK_PY,
    CLUSTERED_SE_PY,
    HYP06_PHASE2_LOCK_JSON,
    HYP07_PHASE2_LOCK_JSON,
    INFERENCE_PY,
    PRIMARY_CLUSTER_KEY,
    SAMPLE_SIZE_GATE_PY,
    TARGET_SAME_SESSION_PY,
    Phase2LockError,
    load_declared_phase2_lock,
)
from .make_hyp08_sample_size_gate import FAMILY_SIZE_K, sidak_critical_t
from .peer_returns import build_series, load_peer_closes
from .target_same_session import BENCHMARK_TICKER, build_feature_table_same_session

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

AS_OF = "2026-09-14"
DEFAULT_PHASE2_LOCK = LSE / f"HYP08_PHASE2_LOCK_{AS_OF}.json"
DEFAULT_PEER_CLOSES = LSE / f"HYP08_PEER_CLOSES_{AS_OF}.csv"
DEFAULT_PEER_EARNINGS = LSE / f"HYP08_PEER_EARNINGS_{AS_OF}.json"

RESULT_PATTERN = "HYP08_PHASE3_RESULT_*.json"
AUTHORIZATION_PATTERN = "HYP08_PHASE3_AUTHORIZATION_*.json"


class Phase3Error(RuntimeError):
    """A precondition does not hold."""


# ==========================================================================
# 1. The in-process rehearsal. Runs every time, before any real file opens.
# ==========================================================================

def run_rehearsal(*, seed: int = 42) -> dict[str, Any]:
    """Exercise the FULL same-session estimator (both fits) on synthetic
    data, clustered on HYP-08's own primary key, before touching anything
    real. Uses `fixtures_same_session.make_panel_same_session` with a real,
    mixed-sign injected effect so BOTH fits actually return a value, not
    just the pipeline shape."""
    panel = make_panel_same_session(
        "hyp08-phase3-rehearsal", n_anchors=8, n_quarters=6,
        n_peers_per_anchor=3, injected_effect_customer_supplier=3.0,
        injected_effect_competitor=-3.0, seed=seed)
    result = _run_treatment_same_session(panel, cluster_key=PRIMARY_CLUSTER_KEY)
    if result["n_rows"] <= 0:
        raise Phase3Error(
            "the synthetic rehearsal produced zero rows -- it must actually "
            "exercise the pipeline, not pass vacuously")
    if result["primary_fit"] is None or result["heterogeneity_fit"] is None:
        raise Phase3Error(
            "the synthetic rehearsal did not produce both fits -- the real "
            "run's reporting path is untested")
    return result


# ==========================================================================
# 2. The same-session treatment -- the one real substitute for
#    make_phase1_diagnostics._run_treatment / _run_treatment_signed.
# ==========================================================================

def _judge(t_stat: Optional[float], dof: Optional[float]) -> dict[str, Any]:
    if t_stat is None or dof is None:
        return {"critical_value": None, "significant": None}
    crit = sidak_critical_t(dof, k=FAMILY_SIZE_K)
    return {"critical_value": crit, "significant": bool(abs(t_stat) > crit)}


def _run_treatment_same_session(panel, *, cluster_key: str = PRIMARY_CLUSTER_KEY
                                ) -> dict[str, Any]:
    """No horizon grid, no D6/D7/onset machinery -- see module docstring.
    Returns both fits plus a significance verdict for EXACTLY the two
    preregistered, Sidak-corrected quantities."""
    built = build_feature_table_same_session(panel)
    table = built["table"]

    primary_fits = fit_local_projections(table, horizons=(0,),
                                         cluster_key=cluster_key)
    primary = primary_fits[0] if primary_fits else None
    interaction = fit_interaction_model(table, cluster_key=cluster_key)

    primary_report = None
    if primary is not None:
        verdict = _judge(primary.t_stat, primary.satterthwaite_dof)
        primary_report = {
            "beta": primary.beta, "se": primary.se, "t_stat": primary.t_stat,
            "satterthwaite_dof": primary.satterthwaite_dof,
            "n_obs": primary.n_obs, "n_clusters": primary.n_clusters,
            **verdict,
        }

    heterogeneity_report = None
    if interaction is not None:
        interaction_verdict = _judge(interaction.t_interaction,
                                     interaction.dof_interaction)
        heterogeneity_report = {
            "beta_interaction": interaction.beta_interaction,
            "se_interaction": interaction.se_interaction,
            "t_interaction": interaction.t_interaction,
            "dof_interaction": interaction.dof_interaction,
            **interaction_verdict,
            "n_obs": interaction.n_obs, "n_clusters": interaction.n_clusters,
            "n_customer_supplier": interaction.n_customer_supplier,
            "n_competitor": interaction.n_competitor,
            "descriptive_context_not_verdicted": {
                "beta_customer_supplier": interaction.beta_customer_supplier,
                "se_customer_supplier": interaction.se_customer_supplier,
                "t_customer_supplier": interaction.t_customer_supplier,
                "beta_competitor_implied": interaction.beta_competitor_implied,
                "se_competitor_implied": interaction.se_competitor_implied,
                "t_competitor_implied": interaction.t_competitor_implied,
                "note": (
                    "These two implied group-specific slopes are reported "
                    "for INTERPRETATION only. Neither is one of HYP-08's "
                    "two preregistered, Sidak-corrected (k=2) tests -- "
                    "only the plain pooled coefficient (primary_fit) and "
                    "the shock:is_competitor interaction term "
                    "(heterogeneity_fit.t_interaction) are held to the "
                    "corrected threshold. No significance verdict is "
                    "computed for either number here, deliberately -- "
                    "treating them as a third and fourth test would be "
                    "exactly the 'keep adding tests' external review "
                    "explicitly warned against."),
            },
        }

    return {
        "residualize": False,
        "residualization_note": built["residualization_note"],
        "n_candidate_observations": built["n_candidate_observations"],
        "n_excluded_short_or_missing_window":
            built["n_excluded_short_or_missing_window"],
        "excluded_fraction": built["excluded_fraction"],
        "n_rows": built["n_rows"],
        "n_rows_customer_supplier": built["n_rows_customer_supplier"],
        "n_rows_competitor": built["n_rows_competitor"],
        "primary_fit": primary_report,
        "heterogeneity_fit": heterogeneity_report,
        "sign_convention_reminder": (
            "Nothing is flipped, anywhere. A priori: customer/supplier "
            "peers predicted POSITIVE (comovement), competitor peers "
            "predicted NEGATIVE (displacement). Whichever result actually "
            "came back -- for either test, in either direction, or null "
            "-- is reported as computed."),
        "point_estimate_permitted": False,
    }


# ==========================================================================
# 3. Authorization: read, verify, and (only after a real run) consume it.
# ==========================================================================

AUTHORIZATION_FIELDS = ("declared", "declared_by", "declared_date",
                        "attestation_text", "pinned_commit_sha",
                        "pinned_phase2_lock_sha256",
                        "pinned_peer_closes_sha256",
                        "pinned_peer_earnings_sha256", "consumed")


def _find_authorization(lse: Path) -> Optional[Path]:
    hits = sorted(lse.glob(AUTHORIZATION_PATTERN))
    if len(hits) > 1:
        raise Phase3Error(
            f"{len(hits)} HYP-08 Phase 3 authorization files exist "
            f"({[p.name for p in hits]}) -- exactly one is expected.")
    return hits[0] if hits else None


def _load_valid_authorization(lse: Path, *, repo: Path, phase2_lock_path: Path,
                              peer_closes_path: Path, peer_earnings_path: Path
                              ) -> dict[str, Any]:
    path = _find_authorization(lse)
    if path is None:
        raise Phase3Error(
            "no HYP-08 Phase 3 authorization on disk. The real run "
            "requires one, typed by the owner BEFORE any computation -- "
            "see 'python -m hyp04_supply_chain_hedge.ratify_hyp08 phase3 "
            "--template'.")
    doc = json.loads(path.read_text(encoding="utf-8"))
    for f in AUTHORIZATION_FIELDS:
        if f not in doc:
            raise Phase3Error(
                f"{path.name} has no {f!r} key; this does not look like an "
                "authorization written by 'ratify_hyp08 phase3'")
    if doc["declared"] is not True:
        raise Phase3Error(f"{path.name} is a draft: 'declared' is not true.")
    if doc["consumed"] is True:
        raise Phase3Error(
            f"{path.name} was already consumed by a prior run "
            f"(consumed_by={doc.get('consumed_by_result')!r}).")
    _commit_sha(repo)
    lock_sha = _sha256(phase2_lock_path)
    if doc["pinned_phase2_lock_sha256"] != lock_sha:
        raise Phase3Error(
            f"{path.name} authorizes Phase 2 lock hash "
            f"{doc['pinned_phase2_lock_sha256'][:12]}, but the lock on disk "
            f"now hashes to {lock_sha[:12]}.")
    closes_sha = _sha256(peer_closes_path)
    if doc["pinned_peer_closes_sha256"] != closes_sha:
        raise Phase3Error(
            f"{path.name} authorizes peer-closes hash "
            f"{doc['pinned_peer_closes_sha256'][:12]}, but "
            f"{peer_closes_path.name} on disk now hashes to {closes_sha[:12]}.")
    earnings_sha = _sha256(peer_earnings_path)
    if doc["pinned_peer_earnings_sha256"] != earnings_sha:
        raise Phase3Error(
            f"{path.name} authorizes peer-earnings hash "
            f"{doc['pinned_peer_earnings_sha256'][:12]}, but "
            f"{peer_earnings_path.name} on disk now hashes to {earnings_sha[:12]}.")
    return doc


def _consume_authorization(path: Path, *, result_artifact_name: str) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["consumed"] = True
    doc["consumed_by_result"] = result_artifact_name
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")


# ==========================================================================
# 4. Build the one real, pooled SyntheticPanel from the lock's own
#    already-derived events and every locked peer's real closes/earnings,
#    PLUS the SPY benchmark leg.
# ==========================================================================

def _group_by_event_same_session(locked_events: list[dict[str, Any]]
                                 ) -> dict[str, dict[str, Any]]:
    """event_id -> {anchor, attributed_session, shock (from excess_return),
    relationship_type, peers: [...]}. Refuses if two rows sharing an
    event_id disagree on anchor/session/excess_return/relationship_type."""
    grouped: dict[str, dict[str, Any]] = {}
    for ev in locked_events:
        eid = ev["event_id"]
        signed_shock = float(ev["excess_return"])
        if eid not in grouped:
            grouped[eid] = {
                "anchor": ev["anchor_ticker"],
                "attributed_session": ev["attributed_session"],
                "shock": signed_shock,
                "relationship_type": ev["relationship_type"],
                "peers": [],
            }
        g = grouped[eid]
        if (g["anchor"] != ev["anchor_ticker"]
                or g["attributed_session"] != ev["attributed_session"]
                or g["shock"] != signed_shock
                or g["relationship_type"] != ev["relationship_type"]):
            raise Phase3Error(
                f"event_id {eid!r} has inconsistent anchor/session/"
                "excess_return/relationship_type across its own locked "
                "rows -- refusing rather than picking one")
        g["peers"].append(ev["peer_ticker"])
    return grouped


def _build_real_panel(*, lock: dict[str, Any], peer_closes_path: Path,
                      peer_earnings_path: Path):
    locked_peers = sorted({e["peer_ticker"] for e in lock["locked_events"]})

    obs, rejects, closes_sha = load_peer_closes(peer_closes_path)
    if rejects:
        raise Phase3Error(
            f"{peer_closes_path.name} has {len(rejects)} unparseable row(s) "
            "-- refusing rather than silently dropping them")
    tickers = {o.ticker for o in obs}
    expected = set(locked_peers) | {BENCHMARK_TICKER}
    if tickers != expected:
        raise Phase3Error(
            f"{peer_closes_path.name} names {sorted(tickers)}, expected "
            f"exactly the {len(locked_peers)} locked peer(s) plus the "
            f"{BENCHMARK_TICKER} benchmark: {sorted(expected)}")

    attributed: dict[str, date] = {}
    for ev in lock["locked_events"]:
        attributed.setdefault(ev["event_id"],
                              date.fromisoformat(ev["attributed_session"]))

    idx, _idx_prov = _session_index(attributed, [peer_closes_path])
    pos = {d: i for i, d in enumerate(idx)}

    all_series_tickers = [*locked_peers, BENCHMARK_TICKER]
    series = {t: build_series(obs, ticker=t, sessions=idx)
             for t in all_series_tickers}

    peer_earnings_days, earnings_coverage = P1._attribute_peer_earnings(
        peer_earnings_path, idx, peers=locked_peers)

    grouped = _group_by_event_same_session(lock["locked_events"])
    anchor_events: list[dict[str, Any]] = []
    for eid, g in grouped.items():
        d = date.fromisoformat(g["attributed_session"])
        day = pos.get(d)
        if day is None:
            raise Phase3Error(
                f"locked event {eid}'s attributed session {d} is not a "
                "session in the shared trading calendar.")
        anchor_events.append({
            "anchor": g["anchor"], "anchor_day": day, "shock": g["shock"],
            "peers": sorted(set(g["peers"])),
            "calendar_period": P1._calendar_period_int(eid),
            "relationship_type": g["relationship_type"],
        })

    returns = {
        t: np.array([np.nan if r is None else r for r in series[t].log_returns],
                   dtype=float)
        for t in all_series_tickers
    }

    from .fixtures import SyntheticPanel
    panel = SyntheticPanel(
        name=f"hyp08-phase3-real-{len(locked_peers)}peers",
        returns=returns, peer_earnings_days=peer_earnings_days,
        anchor_events=anchor_events, n_trading_days=len(idx),
        injected_lag=None, injected_effect=0.0, injected_effect_window=0,
        peer_base_vol={}, earnings_ramp_amplitude=0.0,
        truth={"real_data": True, "not_applicable": True},
    )
    n_pairs = sum(len(e["peers"]) for e in anchor_events)
    extra = {
        "peer_closes_sha256": closes_sha,
        "benchmark_ticker": BENCHMARK_TICKER,
        "n_sessions": len(idx),
        "first_session": idx[0].isoformat(),
        "last_session": idx[-1].isoformat(),
        "peer_earnings_coverage": earnings_coverage,
        "n_grouped_anchor_events": len(anchor_events),
        "n_pairs": n_pairs,
    }
    return panel, extra


# ==========================================================================
# 5. Orchestration
# ==========================================================================

def build_result(*, out_path: Path, phase2_lock_path: Path = DEFAULT_PHASE2_LOCK,
                 peer_closes_path: Path = DEFAULT_PEER_CLOSES,
                 peer_earnings_path: Path = DEFAULT_PEER_EARNINGS,
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
            f"a HYP-08 Phase 3 result already exists "
            f"({[p.name for p in existing_results]}) -- this exploratory "
            "check is run ONCE. Refusing regardless of --out.")

    lock = load_declared_phase2_lock(phase2_lock_path)

    for label, pinned_path, pinned_hash in (
        ("target_same_session.py", TARGET_SAME_SESSION_PY,
         lock["pins"]["target_same_session_py_sha256"]),
        ("inference.py", INFERENCE_PY, lock["pins"]["inference_py_sha256"]),
        ("clustered_se.py", CLUSTERED_SE_PY, lock["pins"]["clustered_se_py_sha256"]),
        ("anchor_shock.py", ANCHOR_SHOCK_PY, lock["pins"]["anchor_shock_py_sha256"]),
        ("make_hyp08_sample_size_gate.py", SAMPLE_SIZE_GATE_PY,
         lock["pins"]["sample_size_gate_py_sha256"]),
    ):
        current = _sha256(pinned_path)
        if current != pinned_hash:
            raise Phase3Error(
                f"{label} has changed since the Phase 2 lock was declared "
                f"(pinned {pinned_hash[:12]}, now {current[:12]}). The lock "
                "no longer describes the code that would run.")

    for label, pinned_path, pinned_hash in (
        ("HYP-06 Phase 2 lock", HYP06_PHASE2_LOCK_JSON,
         lock["pins"]["hyp06_phase2_lock_sha256"]),
        ("HYP-07 Phase 2 lock", HYP07_PHASE2_LOCK_JSON,
         lock["pins"]["hyp07_phase2_lock_sha256"]),
    ):
        current = _sha256(pinned_path)
        if current != pinned_hash:
            raise Phase3Error(
                f"{label} has changed since the Phase 2 lock was declared "
                f"(pinned {pinned_hash[:12]}, now {current[:12]}).")
    for p, pinned_hash in zip(ANCHOR_SHOCKS_CSVS, lock["pins"]["anchor_shocks_sha256"]):
        current = _sha256(p)
        if current != pinned_hash:
            raise Phase3Error(
                f"anchor shocks ({p.name}) on disk does not match the "
                f"Phase 2 lock's pinned hash (pinned {pinned_hash[:12]}, "
                f"now {current[:12]}).")

    auth_path = _find_authorization(lse)
    auth = _load_valid_authorization(
        lse, repo=repo, phase2_lock_path=phase2_lock_path,
        peer_closes_path=peer_closes_path, peer_earnings_path=peer_earnings_path)

    run_rehearsal()

    panel, extra = _build_real_panel(
        lock=lock, peer_closes_path=peer_closes_path,
        peer_earnings_path=peer_earnings_path)
    if extra["n_pairs"] != lock["n_locked_events"]:
        raise Phase3Error(
            f"the built panel carries {extra['n_pairs']} (peer, event) "
            f"pairs, but the lock fixes {lock['n_locked_events']} -- "
            "refusing rather than running against a panel that does not "
            "reproduce the locked set")

    treatment = _run_treatment_same_session(
        panel, cluster_key=lock["model_spec"]["primary_cluster_key"])

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-08",
        "phase": "Phase 3 -- the one exploratory run against the real, "
                "pooled 973-pair universe (778 customer/supplier + 195 "
                "competitor), testing same-session reaction and reaction "
                "heterogeneity for the first time in this project",
        "what_this_is": (
            "The single, preregistered, exploratory run of the Phase "
            "2-locked spec against every pooled peer's real returns on "
            "the exact session its own anchor event is attributed to. "
            "Reported once, regardless of outcome."),
        "what_this_is_not": (
            "NOT confirmatory, NOT repeatable, and NOT a license to "
            "iterate on the spec having seen this. Whichever of the two "
            "preregistered tests comes back significant, both, or "
            "neither -- gets reported exactly the same way."),
        "reported_regardless_of_outcome": True,
        "no_rerun_permitted": True,
        "point_estimate_permitted": False,
        "is_a_confidence_interval": False,
        "sample_size_disclosure": dict(lock["sample_size_disclosure"]),
        "look_ahead_disclosure": dict(lock["look_ahead_disclosure"]),
        "sign_convention": dict(lock["target_definition"])["sign_convention"],
        "test_family": dict(lock["model_spec"])["test_family"],
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
        "locked_peers": lock["locked_peers"],
        "locked_anchors": lock["locked_anchors"],
        "n_locked_events": lock["n_locked_events"],
        "n_locked_events_customer_supplier":
            lock["n_locked_events_customer_supplier"],
        "n_locked_events_competitor": lock["n_locked_events_competitor"],
        "treatment": treatment,
        "peer_data_provenance": extra,
        "sources": {
            "phase2_lock_sha256": _sha256(phase2_lock_path),
            "peer_closes": peer_closes_path.name,
            "peer_closes_sha256": _sha256(peer_closes_path),
            "peer_earnings": peer_earnings_path.name,
            "peer_earnings_sha256": _sha256(peer_earnings_path),
        },
        "opens_no_gate": (
            "This is a computed HYP-08 Phase 3 result, not a freeze, not a "
            "registry change, not a linkage ratification. It moves no "
            "gate condition, whatever the gate reads at the moment this "
            "file is read."),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1, default=str) + "\n",
                        encoding="utf-8")
    _consume_authorization(auth_path, result_artifact_name=out_path.name)
    return doc


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="HYP-08 Phase 3: the one exploratory run against the "
                    "real, pooled 973-pair universe. Requires a prior, "
                    "typed 'ratify_hyp08 phase3' authorization.")
    ap.add_argument("--phase2-lock", type=Path, default=DEFAULT_PHASE2_LOCK)
    ap.add_argument("--peer-closes", type=Path, default=DEFAULT_PEER_CLOSES)
    ap.add_argument("--peer-earnings", type=Path, default=DEFAULT_PEER_EARNINGS)
    ap.add_argument("--out", type=Path, default=None,
                    help="default: Live Signal Engine/"
                         "HYP08_PHASE3_RESULT_<today>.json")
    ap.add_argument("--rehearsal-only", action="store_true",
                    help="run ONLY the synthetic rehearsal; touches no real "
                         "file, requires no authorization")
    a = ap.parse_args(argv)

    if a.rehearsal_only:
        result = run_rehearsal()
        print("REHEARSAL ONLY -- synthetic data, nothing real touched.")
        print(f"  rows={result['n_rows']}  "
              f"primary_significant={result['primary_fit']['significant']}  "
              f"interaction_significant={result['heterogeneity_fit']['significant']}")
        return 0

    out = a.out or (LSE / f"HYP08_PHASE3_RESULT_{date.today().isoformat()}.json")
    doc = build_result(out_path=out, phase2_lock_path=a.phase2_lock,
                       peer_closes_path=a.peer_closes,
                       peer_earnings_path=a.peer_earnings)

    t = doc["treatment"]
    print(f"locked peers ({len(doc['locked_peers'])}) / anchors "
          f"({len(doc['locked_anchors'])})")
    print(f"n_locked_events    : {doc['n_locked_events']}  "
          f"({doc['n_locked_events_customer_supplier']} customer/supplier "
          f"+ {doc['n_locked_events_competitor']} competitor)")
    print(f"n_rows (analyzed)  : {t['n_rows']}")
    pf = t["primary_fit"]
    hf = t["heterogeneity_fit"]
    print(f"primary:      beta={pf['beta']:.4f}  t={pf['t_stat']:.3f}  "
          f"crit={pf['critical_value']:.3f}  significant={pf['significant']}")
    print(f"heterogeneity: beta_interaction={hf['beta_interaction']:.4f}  "
          f"t={hf['t_interaction']:.3f}  crit={hf['critical_value']:.3f}  "
          f"significant={hf['significant']}")
    print(f"\nWROTE {doc['artifact']}")
    print("EXPLORATORY, NOT CONFIRMATORY. This check is now spent; no "
          "further run against this lock is permitted.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Phase3Error as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(1)
