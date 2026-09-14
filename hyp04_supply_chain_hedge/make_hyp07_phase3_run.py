#!/usr/bin/env python3
"""HYP-07 Phase 3 -- the one exploratory run against the real, 195-pair,
6-peer, 6-anchor universe, using the SIGNED target for the first time in
this project.

Mirrors `make_hyp06_phase3_run.py` in SHAPE (authorization required BEFORE
computation, an in-process synthetic rehearsal every invocation, at most
one result ever, the authorization consumed the instant a real run
succeeds) but is NOT that module modified: HYP-06's real panel reads
`target.build_feature_table` (the magnitude-only realized-variance ratio,
`residualize` a caller choice) and feeds it the anchor's `shock` magnitude.
HYP-07 reads `target_signed.build_feature_table_signed` instead (the
signed cumulative abnormal return, no residualization choice at all -- see
target_signed.py's own docstring, "DELIBERATELY NOT PORTED") and feeds it
the anchor's SIGNED `excess_return`, not `shock`.

=== THE ONE FIELD-NAME SUBTLETY THIS MODULE MUST GET RIGHT ===

`fixtures.SyntheticPanel.anchor_events[i]["shock"]` and the feature
table's own `shock` column are GENERIC field names in a schema every
hypothesis's target function shares (see target_signed.py's own
docstring: "same table schema ... reused unchanged"). For HYP-04/05/06
that field holds the anchor's magnitude-only `shock` (`abs(excess_return)`
-- `anchor_shock.AnchorShock`'s own AS-4). For HYP-07 it MUST hold the
anchor's SIGNED `excess_return` instead -- the whole point of a signed
target is a signed regressor. `_group_by_event_signed` below reads
`ev["excess_return"]` from the signed Phase 2 lock's own locked events
(which carries both fields side by side -- see
make_hyp07_phase2_lock.py's own docstring, "EACH LOCKED EVENT CARRIES
excess_return, NOT JUST shock") into that same generic `shock` slot. A
future reader diffing this module against HYP-06's own `_group_by_event`
line-by-line will see `ev["excess_return"]` where HYP-06 has `ev["shock"]`
and nothing else different -- that one substitution is the entire signed-
target wiring for the treatment side.

=== SPY (THE BENCHMARK) RIDES ALONG IN THE SAME PANEL, EXCLUDED FROM
    PEERS EVERYWHERE THAT MATTERS ===

`run_hyp07_peer_returns_fetch.py` writes SPY into the SAME combined closes
CSV as the 6 real peers. `_build_real_panel` below loads all 7 tickers
into `panel.returns` (target_signed.build_feature_table_signed requires
the benchmark series present there) but computes `locked_peers`,
`days_to_peer_earnings` coverage, and the `tickers != set(locked_peers)`
sanity check against the 6 REAL peers only -- SPY is verified present
separately, not folded into "locked peers."

=== AUTHORIZATION, REHEARSAL, NO-RERUN: THE SAME THREE GUARANTEES ===

  1. A signed `HYP07_PHASE3_AUTHORIZATION_<date>.json` (`ratify_hyp07
     phase3`) must already exist, unconsumed, with its
     `pinned_phase2_lock_sha256` matching the signed HYP-07 Phase 2 lock's
     actual hash right now, AND its `pinned_peer_closes_sha256`/
     `pinned_peer_earnings_sha256` matching the real fetched data on disk.
     This module writes none of the authorization's fields; the owner
     types the affirmation themselves.
  2. `run_rehearsal()` runs every time `main()` is invoked, before any
     real file is opened -- against `fixtures_signed.make_panel_signed`,
     not `fixtures.make_panel`, since it must exercise the SAME signed
     code path the real run will use.
  3. If ANY `HYP07_PHASE3_RESULT_*.json` already exists anywhere under
     `Live Signal Engine/`, this refuses unconditionally.

=== REUSE, NOT REIMPLEMENTATION ===

`make_phase1_diagnostics._d6_disclosure`, `_assert_d6_complete`,
`_calendar_period_int`, and `_attribute_peer_earnings` are imported
unchanged -- none of these are specific to the magnitude target.
`make_event_panel._session_index`, `peer_returns.load_peer_closes`/
`build_series`, `inference._design_matrix`/`local_projection_analysis`,
and `clustered_se.dual_cluster_report` are likewise reused unchanged.
Only the feature-table construction itself (`target_signed.
build_feature_table_signed` vs `target.build_feature_table`) and the
`shock`-vs-`excess_return` field it is fed differ from HYP-06's own
module -- see both notes above.

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
from .constants import HORIZON_GRID
from .fixtures_signed import make_panel_signed
from .inference import LocalProjectionResult, _design_matrix, local_projection_analysis
from .make_event_panel import _session_index
from .make_freeze_draft import _commit_sha, _sha256
from .make_hyp07_phase2_lock import (
    ANCHOR_SHOCKS_CSVS,
    CLUSTERED_SE_PY,
    CONSTANTS_PY,
    PEER_UNIVERSE_JSON,
    PRIMARY_CLUSTER_KEY,
    SECONDARY_CLUSTER_KEY,
    TARGET_SIGNED_PY,
    Phase2LockError,
    load_declared_phase2_lock,
)
from .peer_returns import build_series, load_peer_closes
from .target_signed import BENCHMARK_TICKER, build_feature_table_signed

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

AS_OF = "2026-09-14"
DEFAULT_PHASE2_LOCK = LSE / f"HYP07_PHASE2_LOCK_{AS_OF}.json"
DEFAULT_PEER_CLOSES = LSE / f"HYP07_PEER_CLOSES_{AS_OF}.csv"
DEFAULT_PEER_EARNINGS = LSE / f"HYP07_PEER_EARNINGS_{AS_OF}.json"

RESULT_PATTERN = "HYP07_PHASE3_RESULT_*.json"
AUTHORIZATION_PATTERN = "HYP07_PHASE3_AUTHORIZATION_*.json"


class Phase3Error(RuntimeError):
    """A precondition does not hold."""


# ==========================================================================
# 1. The in-process rehearsal. Runs every time, before any real file opens.
# ==========================================================================

def run_rehearsal(*, n_permutations: int = 200, seed: int = 42) -> dict[str, Any]:
    """Exercise the FULL signed-target estimator + D6/D7 disclosure path on
    synthetic data, clustered on HYP-07's own primary key, before touching
    anything real. Uses `fixtures_signed.make_panel_signed` (a genuinely
    signed shock series, a real benchmark leg) -- `fixtures.make_panel`
    would not exercise the code path this module actually runs."""
    panel = make_panel_signed(
        "hyp07-phase3-rehearsal", n_anchors=4, n_quarters=5,
        n_peers_per_anchor=3, injected_lag=None, injected_effect=0.0,
        seed=seed)
    result = _run_treatment_signed(
        panel, cluster_key=PRIMARY_CLUSTER_KEY,
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
# 2. The signed-target treatment -- the one real substitute for
#    make_phase1_diagnostics._run_treatment.
# ==========================================================================

def _run_treatment_signed(panel, *, cluster_key: str = PRIMARY_CLUSTER_KEY,
                          n_permutations: int, seed: int) -> dict[str, Any]:
    """Structurally identical to P1._run_treatment (same D5/D6/D7
    disclosure machinery, same refusal-on-incompleteness discipline) but
    built on `target_signed.build_feature_table_signed` -- HYP-07 has no
    `residualize` choice at all, unlike every prior hypothesis's target."""
    built = build_feature_table_signed(panel)
    table = built["table"]

    result: LocalProjectionResult = local_projection_analysis(
        table, cluster_key=cluster_key, n_permutations=n_permutations, seed=seed)

    fitted_horizons = {f.horizon for f in result.fits}
    dropped = []
    for h in HORIZON_GRID:
        if h in fitted_horizons:
            continue
        mask = table["horizon"] == h
        n = int(mask.sum())
        g = table[cluster_key][mask]
        dropped.append({
            "horizon": h, "n_rows": n,
            "n_clusters": int(np.unique(g).size) if n else 0,
            "why": ("fewer than 3 rows" if n < 3
                    else "fewer than 2 distinct clusters"),
        })

    from .constants import REPORTING_HORIZONS
    k = result.effective_independent_tests or 1.0
    report_at = sorted({h for h in REPORTING_HORIZONS if h in fitted_horizons}
                       | ({result.peak_horizon} if result.peak_horizon else set())
                       | ({result.onset_horizon} if result.onset_horizon else set()))
    disclosures = []
    for h in report_at:
        d = P1._d6_disclosure(table, h, cluster_key=cluster_key,
                              k_effective_tests=k)
        P1._assert_d6_complete(d)
        disclosures.append(d)

    from .onset import OnsetInterval, RefusedError as OnsetRefusedError
    onset_interval = None
    onset_refusal = None
    if result.onset_horizon is not None:
        try:
            onset_interval = OnsetInterval.from_onset(result.onset_horizon)
        except OnsetRefusedError as e:
            onset_refusal = str(e)

    ref_h = report_at[0] if report_at else (HORIZON_GRID[0] if HORIZON_GRID else 0)
    ref_mask = table["horizon"] == ref_h
    ref_events = table["anchor"][ref_mask]
    ref_periods = table[cluster_key][ref_mask]
    d2_text = (
        f"SEs are clustered ONE WAY, on {cluster_key}. At horizon {ref_h}: "
        f"{int(np.unique(ref_periods).size)} distinct {cluster_key} values, "
        f"{int(np.unique(ref_events).size)} distinct anchors over "
        f"{int(ref_mask.sum())} pairs. The same anchor recurring within a "
        f"cluster is NOT covered by this standard error -- see "
        "clustered_se.TWO_WAY_LIMITATION_NOTE. Two-way clustering is not "
        "implemented anywhere in this repository, validated or otherwise.")

    return {
        "residualize": False,
        "residualization_note": built["residualization_note"],
        "n_candidate_observations": built["n_candidate_observations"],
        "n_excluded_short_or_missing_window":
            built["n_excluded_short_or_missing_window"],
        "excluded_fraction": built["excluded_fraction"],
        "n_rows": int(table["event_id"].size),
        "fits_by_horizon": [
            {"horizon": f.horizon, "beta": f.beta, "se": f.se,
             "t_stat": f.t_stat, "satterthwaite_dof": f.satterthwaite_dof,
             "n_obs": f.n_obs, "n_clusters": f.n_clusters}
            for f in result.fits],
        "horizons_dropped": dropped,
        "peak_horizon": result.peak_horizon,
        "peak_horizon_caveat": (
            "target_signed.signed_car(h) is a CUMULATIVE SUM, not the "
            "diluting MEAN target.py's RVar(h) is -- peak_horizon here "
            "means 'where the cumulative effect saturates,' not the same "
            "geometric quantity HYP-04/05/06's own peak_horizon measures, "
            "even though both share the name. See target_signed.py's "
            "docstring, 'A REAL CAVEAT THIS DESIGN SURFACES'."),
        "peak_abs_t": result.peak_abs_t,
        "max_abs_t": result.max_abs_t,
        "max_t_critical_value": result.max_t_critical_value,
        "max_t_p_value": result.max_t_p_value,
        "peak_significant": result.peak_significant,
        "sign_convention_reminder": (
            "Nothing is flipped, anywhere. A significantly NEGATIVE "
            "beta at the peak confirms competitive displacement; a "
            "significantly POSITIVE beta indicates comovement/contagion "
            "instead -- the OPPOSITE of what a competitor relationship "
            "predicts, and must be reported as such, not silently "
            "relabeled a confirming result."),
        "effective_independent_tests": result.effective_independent_tests,
        "n_permutations": result.n_permutations,
        "clustering": result.clustering,
        "onset_horizon_raw": result.onset_horizon,
        "onset_interval": (onset_interval.as_dict() if onset_interval else None),
        "onset_refused": onset_refusal,
        "point_estimate_permitted": False,
        "d2_residual_limitation": d2_text,
        "d6_disclosures": disclosures,
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
            f"{len(hits)} HYP-07 Phase 3 authorization files exist "
            f"({[p.name for p in hits]}) -- exactly one is expected. "
            "Refusing rather than guessing which one governs.")
    return hits[0] if hits else None


def _load_valid_authorization(lse: Path, *, repo: Path, phase2_lock_path: Path,
                              peer_closes_path: Path, peer_earnings_path: Path
                              ) -> dict[str, Any]:
    path = _find_authorization(lse)
    if path is None:
        raise Phase3Error(
            "no HYP-07 Phase 3 authorization on disk. The real run "
            "requires one, typed by the owner BEFORE any computation -- "
            "see 'python -m hyp04_supply_chain_hedge.ratify_hyp07 phase3 "
            "--template'. This module will not compute against any locked "
            "peer's real returns without it.")
    doc = json.loads(path.read_text(encoding="utf-8"))
    for f in AUTHORIZATION_FIELDS:
        if f not in doc:
            raise Phase3Error(
                f"{path.name} has no {f!r} key; this does not look like an "
                "authorization written by 'ratify_hyp07 phase3'")
    if doc["declared"] is not True:
        raise Phase3Error(f"{path.name} is a draft: 'declared' is not true.")
    if doc["consumed"] is True:
        raise Phase3Error(
            f"{path.name} was already consumed by a prior run "
            f"(consumed_by={doc.get('consumed_by_result')!r}). A consumed "
            "authorization cannot trigger a second run.")
    _commit_sha(repo)
    lock_sha = _sha256(phase2_lock_path)
    if doc["pinned_phase2_lock_sha256"] != lock_sha:
        raise Phase3Error(
            f"{path.name} authorizes Phase 2 lock hash "
            f"{doc['pinned_phase2_lock_sha256'][:12]}, but the lock on disk "
            f"now hashes to {lock_sha[:12]}. Re-authorize against the "
            "current lock rather than running against drift.")
    closes_sha = _sha256(peer_closes_path)
    if doc["pinned_peer_closes_sha256"] != closes_sha:
        raise Phase3Error(
            f"{path.name} authorizes peer-closes hash "
            f"{doc['pinned_peer_closes_sha256'][:12]}, but "
            f"{peer_closes_path.name} on disk now hashes to "
            f"{closes_sha[:12]}. Re-authorize against the current file "
            "rather than running against drift.")
    earnings_sha = _sha256(peer_earnings_path)
    if doc["pinned_peer_earnings_sha256"] != earnings_sha:
        raise Phase3Error(
            f"{path.name} authorizes peer-earnings hash "
            f"{doc['pinned_peer_earnings_sha256'][:12]}, but "
            f"{peer_earnings_path.name} on disk now hashes to "
            f"{earnings_sha[:12]}. Re-authorize against the current file "
            "rather than running against drift.")
    return doc


def _consume_authorization(path: Path, *, result_artifact_name: str) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["consumed"] = True
    doc["consumed_by_result"] = result_artifact_name
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")


# ==========================================================================
# 4. Build the one real, multi-peer, multi-anchor SyntheticPanel from the
#    signed lock's own already-derived events and every locked peer's real
#    closes/earnings, PLUS the SPY benchmark leg.
# ==========================================================================

def _group_by_event_signed(locked_events: list[dict[str, Any]]
                           ) -> dict[str, dict[str, Any]]:
    """event_id -> {anchor, attributed_session, shock, peers: [...]}, where
    `shock` here is read from `ev["excess_return"]` -- the anchor's SIGNED
    reaction, not the magnitude `ev["shock"]` HYP-06's own `_group_by_event`
    reads. See this module's own docstring, "THE ONE FIELD-NAME SUBTLETY".
    Refuses if two rows sharing an event_id disagree on the anchor/session/
    excess_return a single anchor earnings release must describe uniquely."""
    grouped: dict[str, dict[str, Any]] = {}
    for ev in locked_events:
        eid = ev["event_id"]
        signed_shock = float(ev["excess_return"])
        if eid not in grouped:
            grouped[eid] = {
                "anchor": ev["anchor_ticker"],
                "attributed_session": ev["attributed_session"],
                "shock": signed_shock,
                "peers": [],
            }
        g = grouped[eid]
        if (g["anchor"] != ev["anchor_ticker"]
                or g["attributed_session"] != ev["attributed_session"]
                or g["shock"] != signed_shock):
            raise Phase3Error(
                f"event_id {eid!r} has inconsistent anchor/session/"
                "excess_return across its own locked rows -- refusing "
                "rather than picking one")
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

    grouped = _group_by_event_signed(lock["locked_events"])
    anchor_events: list[dict[str, Any]] = []
    for eid, g in grouped.items():
        d = date.fromisoformat(g["attributed_session"])
        day = pos.get(d)
        if day is None:
            raise Phase3Error(
                f"locked event {eid}'s attributed session {d} is not a "
                "session in the shared trading calendar -- refusing "
                "rather than guessing which nearby session it means")
        anchor_events.append({
            "anchor": g["anchor"], "anchor_day": day, "shock": g["shock"],
            "peers": sorted(set(g["peers"])),
            "calendar_period": P1._calendar_period_int(eid),
        })

    returns = {
        t: np.array([np.nan if r is None else r for r in series[t].log_returns],
                   dtype=float)
        for t in all_series_tickers
    }

    from .fixtures import SyntheticPanel
    panel = SyntheticPanel(
        name=f"hyp07-phase3-real-{len(locked_peers)}peers",
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
# 5. The secondary robustness lens.
# ==========================================================================

def _secondary_lens(panel, horizons: list[int]) -> list[dict[str, Any]]:
    table = build_feature_table_signed(panel)["table"]
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
# 6. Orchestration
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
            f"a HYP-07 Phase 3 result already exists "
            f"({[p.name for p in existing_results]}) -- this exploratory "
            "check is run ONCE. Refusing regardless of --out.")

    lock = load_declared_phase2_lock(phase2_lock_path)

    for label, pinned_path, pinned_hash in (
        ("target_signed.py", TARGET_SIGNED_PY, lock["pins"]["target_signed_py_sha256"]),
        ("constants.py", CONSTANTS_PY, lock["pins"]["constants_py_sha256"]),
        ("clustered_se.py", CLUSTERED_SE_PY, lock["pins"]["clustered_se_py_sha256"]),
    ):
        current = _sha256(pinned_path)
        if current != pinned_hash:
            raise Phase3Error(
                f"{label} has changed since the Phase 2 lock was declared "
                f"(pinned {pinned_hash[:12]}, now {current[:12]}). The lock "
                "no longer describes the code that would run.")

    current_pu = _sha256(PEER_UNIVERSE_JSON)
    if current_pu != lock["pins"]["peer_universe_sha256"]:
        raise Phase3Error(
            f"peer universe on disk does not match the Phase 2 lock's "
            f"pinned hash (pinned {lock['pins']['peer_universe_sha256'][:12]}"
            f", now {current_pu[:12]}). It has drifted since the lock was "
            "declared.")
    for p, pinned_hash in zip(ANCHOR_SHOCKS_CSVS, lock["pins"]["anchor_shocks_sha256"]):
        current = _sha256(p)
        if current != pinned_hash:
            raise Phase3Error(
                f"anchor shocks ({p.name}) on disk does not match the "
                f"Phase 2 lock's pinned hash (pinned {pinned_hash[:12]}, "
                f"now {current[:12]}). It has drifted since the lock was "
                "declared.")

    auth_path = _find_authorization(lse)
    auth = _load_valid_authorization(
        lse, repo=repo, phase2_lock_path=phase2_lock_path,
        peer_closes_path=peer_closes_path, peer_earnings_path=peer_earnings_path)

    # The rehearsal runs even here, one more time, immediately before the
    # real computation.
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

    treatment = _run_treatment_signed(
        panel, cluster_key=lock["model_spec"]["primary_cluster_key"],
        n_permutations=lock["model_spec"]["n_permutations"],
        seed=lock["model_spec"]["random_seed"])

    reported_horizons = sorted({d["horizon"] for d in treatment["d6_disclosures"]
                                if "horizon" in d})
    secondary = _secondary_lens(panel, reported_horizons)

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-07",
        "phase": "Phase 3 -- the one exploratory run against the real, "
                "195-pair, 6-peer, 6-anchor universe (see "
                "HYP07_PHASE2_LOCK's sample_size_disclosure), using the "
                "SIGNED target for the first time in this project",
        "what_this_is": (
            "The single, preregistered, exploratory run of the Phase "
            f"2-locked spec against every locked peer's real returns "
            f"around every locked anchor event. Reported once, "
            "regardless of outcome."),
        "what_this_is_not": (
            "NOT confirmatory (the 195-pair provisional floor this "
            "sample clears EXACTLY, not comfortably, is itself "
            "provisional and an even weaker borrow than HYP-06's own -- "
            "see sample_size_disclosure below), NOT repeatable, and NOT a "
            "license to iterate on the spec having seen this. A "
            "disappointing or a striking result -- displacement, "
            "comovement, or null -- gets reported exactly the same way."),
        "reported_regardless_of_outcome": True,
        "no_rerun_permitted": True,
        "point_estimate_permitted": False,
        "is_a_confidence_interval": False,
        "sample_size_disclosure": dict(lock["sample_size_disclosure"]),
        "look_ahead_disclosure": dict(lock["look_ahead_disclosure"]),
        "sign_convention": dict(lock["target_definition"])["sign_convention"],
        "peak_horizon_caveat": dict(lock["target_definition"])["peak_horizon_caveat"],
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
        "treatment": treatment,
        "clustering_label_note": (
            "treatment.clustering below reads '-- SENSITIVITY, NOT THE D1 "
            "PRIMARY' because inference.local_projection_analysis stamps "
            "that label whenever cluster_key != constants.LOCKED_CLUSTER_"
            "KEY ('calendar_period', HYP-04's own D1). That label "
            "describes HYP-04's decision, not HYP-07's: HYP-07 reuses "
            "HYP-05's/HYP-06's own re-decision that event_id IS its "
            "primary clustering dimension. Read the label as HYP-04 "
            "vocabulary surfacing through reused code, not as a statement "
            "that this is a sensitivity check -- it is HYP-07's actual "
            "inferential result."),
        "secondary_cluster_robustness_lens": {
            "dimension": SECONDARY_CLUSTER_KEY,
            "per_horizon": secondary,
            "note": ("Two ONE-WAY clusterings shown side by side, never a "
                    "two-way estimator -- see clustered_se."
                    "dual_cluster_report. The primary result above is "
                    "HYP-07's actual inferential result; this is a "
                    "robustness lens only, computed at exactly the "
                    "horizons the primary result already discloses under "
                    "D6."),
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
            "This is a computed HYP-07 Phase 3 result, not a freeze, not a "
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
        description="HYP-07 Phase 3: the one exploratory run against the "
                    "real 195-pair universe. Requires a prior, typed "
                    "'ratify_hyp07 phase3' authorization.")
    ap.add_argument("--phase2-lock", type=Path, default=DEFAULT_PHASE2_LOCK)
    ap.add_argument("--peer-closes", type=Path, default=DEFAULT_PEER_CLOSES)
    ap.add_argument("--peer-earnings", type=Path, default=DEFAULT_PEER_EARNINGS)
    ap.add_argument("--out", type=Path, default=None,
                    help="default: Live Signal Engine/"
                         "HYP07_PHASE3_RESULT_<today>.json")
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

    out = a.out or (LSE / f"HYP07_PHASE3_RESULT_{date.today().isoformat()}.json")
    doc = build_result(out_path=out, phase2_lock_path=a.phase2_lock,
                       peer_closes_path=a.peer_closes,
                       peer_earnings_path=a.peer_earnings)

    t = doc["treatment"]
    print(f"locked peers ({len(doc['locked_peers'])}) / anchors "
          f"({len(doc['locked_anchors'])})")
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
