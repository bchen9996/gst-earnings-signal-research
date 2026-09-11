#!/usr/bin/env python3
"""HYP-04 Phase 1 -- the first look at real data. Diagnostic only.

=== WHERE THIS SITS, SAID BEFORE ANYTHING ELSE ===

Plan v0.2 section 5.3's ladder: Phase 0 (complete, placeholder linkage) ->
Phase 1 -- "run Stage 1 openly (no lock) to see whether a plausible signal
exists. Results are diagnostic only; nothing is shown as a finding" -- ->
Phase 2 (the preregistration lock: target, feature set, model spec, validation
split) -> Phase 3 (one locked run against the holdout).

The analysis lock (D1-D10) fixes ESTIMATOR AND REPORTING RULES ONLY. Its own
`scope.does_not_fix` reserves target definition, feature set and model spec
for Phase 2. This module computes Phase 1's diagnostic under those fixed
estimator rules; it does not preregister anything and its output is never
displayable as a HYP-04 result.

The display gate being OPEN does not license this. The gate governs DISPLAY.
Phase sequencing is a separate control, exactly as quantum-provenance is
separate: an open gate clears neither.

=== IT RANGES OVER EXPLORATION EVENTS ONLY, MECHANICALLY ENFORCED ===

`HYP04_VALIDATION_SPLIT_2026-09-09.json`, once signed, partitions the 214
frozen events into 157 exploration / 57 holdout. This module reads ONLY the
signed split's exploration list; the calendar rows fed into eligibility
resolution are filtered to that list BEFORE `_coverage` or
`resolve_from_curated_map` ever sees them, so a holdout event cannot leak in
by being silently included in a coverage computation that is then discarded --
it is never computed over at all. Refuses outright if the split is unsigned,
if its pinned panel hash does not match the panel on disk, or if any
exploration id is not a member of the frozen freeze's own eligible set.

=== THE REJOIN REUSES THE PANEL'S OWN MACHINERY, NOT A SECOND COPY ===

`HYP04_EVENT_PANEL_2026-09-08.json` carries `eligible_event_ids` but no
`anchor_day`, `shock`, or per-event `peers` -- those were computed in memory
by `make_event_panel.build()` and never written out. Recomputing them by hand
here would be a second implementation that could silently diverge from the
one the freeze actually pinned. Instead this calls the SAME functions
(`make_event_panel._coverage`, `linkage_resolution.resolve_from_curated_map`,
`linkage_resolution.freeze_record_fields`) over the SAME pinned input files
(verified by sha256 against what the frozen panel recorded, not re-discovered
by a "newest file" glob), and then asserts the freshly-recomputed eligible set
matches the frozen one exactly before doing anything else. If it does not,
something has drifted since the freeze and this refuses rather than silently
computing over a different world than the one that was frozen.

=== TWO TREATMENTS, REPORTED SIDE BY SIDE -- NEITHER CHOSEN ===

`target.build_feature_table(residualize=...)` is a single global flag; there
is no way to residualize some rows and not others within one call, and this
module has no standing to invent a per-peer carve-out.

That matters concretely for one peer. The authorized EDGAR pull
(`HYP04_PEER_EARNINGS_2026-09-10.json`) found BB carries ZERO recorded 8-K
Item 2.02 filings before 2020-03-31 -- confirmed genuine (the pre-2012
submissions shard is fully cached and contains zero 8-Ks of any kind),
consistent with BlackBerry's foreign-private-issuer status before it lost
that status around 2019-2020. 67 of the 70 exploration-set events on JBL (the
only anchor with a curated BB edge) predate that date, so for those there is
no real earnings-day record to residualize BB's target against.

Rather than exclude those pairs, backfill a synthetic calendar, or silently
pick unresidualized for BB alone, this module runs BOTH the registered
primary spec (residualize=True, per registry `peer_target_window`) and the
sensitivity companion (residualize=False) over the IDENTICAL exploration set,
reports both, and separately discloses per-peer earnings-coverage so a reader
can see exactly which peer's baseline is thin and why. Choosing between them
-- or adopting a peer-specific carve-out -- is feature-set work reserved for
Phase 2, not decided here.

=== D1-D10 COMPLIANCE, BY REFUSAL ===

  1. HOLDOUT LEAK -- see above. Enforced on the calendar rows BEFORE
     eligibility resolution, not on the table `build_feature_table` returns
     (which reindexes event_id as an enumerate position and could not be
     checked against the real ids at all).
  2. NO SIGNED SPLIT, NO RUN. Panel-hash pin verified, not trusted.
  3. FREEZE INTEGRITY. `validate_freeze` must pass; `uses_placeholder_linkage`
     must be False.
  4. D3/D4 (CR2). `fit_local_projections` hardcodes the covariance estimator
     to CR2 internally -- this module never calls that estimator directly
     with a caller-suppliable `kind`, so there is no live path for another
     estimator to enter through this code. Verified by a dedicated test that
     greps this module's source for any direct call site (there must be
     none).
  5. SILENT HORIZON DROPS. `fit_local_projections` skips a horizon with <3
     rows or <2 clusters without saying so. Every requested horizon absent
     from the fitted result is reported explicitly, with the row/cluster count
     that caused the drop.
  6. D7. Only `OnsetInterval.from_onset(...)` is ever written for a lag
     quantity -- `point_estimate_permitted: false` is stated, and the raw
     `onset_horizon` int is carried ONLY alongside the interval, never alone,
     never labelled a confidence interval.
  7. D6. Cluster count, singleton count, cluster-size distribution, realized
     Satterthwaite df, N_pairs, N_events, raw (unfloored) ICC with its
     backing cluster count, DEFF, N_eff -- reported at every REPORTING_HORIZON
     plus the peak and onset horizons for each treatment. Completeness is
     asserted before the artifact is written; a missing field refuses the
     whole write rather than shipping a partial disclosure.
  8. D2. The residual-limitation text is computed from the MEASURED
     exploration-set structure at generation time, not the lock's own fixture
     numbers (~8 clusters / 24.5 df) or this project's earlier measurement of
     the FULL 214-event set (92 quarters / 4 anchors) -- the 157-event
     exploration set has its own, smaller structure, computed fresh.
  9. NOT A FINDING. States its own scope; wires into no findings panel (this
     module imports nothing from the display-rendering module); a
     fed-through-the-gate test in the suite confirms `assert_display_allowed`
     refuses it regardless of gate state.
  10. `event_ids_consumed`. Every exploration event_id actually fed into
      eligibility resolution is enumerated, so Step 2's scope-aware freeze
      refusal can tell this result apart from one touching the holdout.

Never a bare `assert`: `python -O` strips asserts, and every guard here that
must hold in production raises `Phase1Error`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Optional

import numpy as np

from . import gate as sample_gate
from .clustered_se import intraclass_correlation
from .constants import HORIZON_GRID, LOCKED_CLUSTER_KEY, REPORTING_HORIZONS
from .fixtures import SyntheticPanel
from .inference import LocalProjectionResult, local_projection_analysis
from .linkage_resolution import freeze_record_fields, resolve_from_curated_map
from .make_freeze_draft import validate_freeze
from .make_validation_split import event_quarter, load_declared_split
from .onset import OnsetInterval, RefusedError as OnsetRefusedError
from .peer_ceiling import events_from_calendar, shocks_from_rows
from .target import build_feature_table

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"
AS_OF = "2026-09-10"

# Matches `make_freeze_draft.RESULT_ARTIFACT_PATTERNS` ("HYP04_INFERENCE_*")
# deliberately: this IS a computed outcome and must register as one, so a
# future freeze over an OVERLAPPING event set is refused by Step 2's
# scope-aware guard rather than silently permitted.
OUT_JSON = LSE / f"HYP04_INFERENCE_PHASE1_{AS_OF}.json"

DEFAULT_PANEL = LSE / "HYP04_EVENT_PANEL_2026-09-08.json"
DEFAULT_SPLIT = LSE / "HYP04_VALIDATION_SPLIT_2026-09-09.json"
DEFAULT_PEER_EARNINGS = LSE / "HYP04_PEER_EARNINGS_2026-09-10.json"

#: The two treatments this module runs, in the order reported. Registered
#: primary first -- see "TWO TREATMENTS" above.
TREATMENTS: tuple[tuple[str, bool], ...] = (
    ("residualized_primary", True),
    ("unresidualized_sensitivity", False),
)


class Phase1Error(RuntimeError):
    """A precondition does not hold.

    Phase1Error, never a bare `assert`: `python -O` strips asserts, and a
    guard that vanishes under an optimisation flag is not a guard.
    """


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _calendar_period_int(event_id: str) -> int:
    """D1's cluster key, as a single sortable integer.

    `make_validation_split.event_quarter` returns (year, quarter) for
    comparing against a split boundary; `build_feature_table` casts
    `calendar_period` to `dtype=int`, so a tuple cannot pass through it. This
    is the one place that conversion happens, so both modules agree on what
    `calendar_period` IS without one importing the other's internals for it.
    """
    y, q = event_quarter(event_id)
    return y * 4 + q


def _pinned_file(directory: Path, name: str, expected_sha256: str, *,
                 what: str) -> Path:
    """Resolve a file BY NAME, then verify its bytes against a pinned hash.

    Deliberately not `newest_in(...)` -- discovery-by-glob is right for a
    generator deriving a NEW artifact, and wrong here: this module must read
    the EXACT bytes the frozen panel was built from, not whatever happens to
    be newest on disk today.
    """
    p = directory / name
    if not p.is_file():
        raise Phase1Error(f"no {what} at {p} -- the frozen panel names this "
                          "file and it is not on disk")
    got = _sha256(p)
    if got != expected_sha256:
        raise Phase1Error(
            f"{what} {name!r} has drifted: the frozen panel recorded sha256 "
            f"{expected_sha256[:16]}..., this file now hashes to "
            f"{got[:16]}.... Rejoining over changed inputs would not "
            "reproduce what was frozen.")
    return p


def _rows(path: Path) -> list[dict[str, str]]:
    import csv
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ==========================================================================
# The rejoin
# ==========================================================================

def _rejoin(*, panel_path: Path, split_path: Path, freeze_path: Optional[Path],
           lse: Path) -> dict[str, Any]:
    """Everything needed to build a SyntheticPanel, over EXPLORATION events
    only, cross-checked against the frozen panel's own recorded eligible set.
    """
    from .artifacts import newest_in
    from .curated_linkage import load_curated_linkage
    from .make_event_panel import PanelError, _coverage
    from .peer_returns import load_peer_closes, build_series

    if not panel_path.is_file():
        raise Phase1Error(f"no event panel at {panel_path}")
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    panel_sha256 = _sha256(panel_path)

    # --- the split: signed, and pinned to THIS panel -----------------------
    split = load_declared_split(split_path)
    if split["pins"]["panel"] != panel_path.name:
        raise Phase1Error(
            f"the signed split pins panel {split['pins']['panel']!r}, not "
            f"{panel_path.name!r}. Wrong panel for this split.")
    if split["pins"]["panel_sha256"] != panel_sha256:
        raise Phase1Error(
            "the signed split's pinned panel_sha256 does not match the panel "
            "on disk. The panel has changed since the split was declared.")
    exploration_ids = set(split["exploration"]["event_ids"])
    holdout_ids = set(split["holdout"]["event_ids"])

    # --- the freeze: valid, real linkage, and this IS its event set --------
    freeze_path = freeze_path or newest_in(lse, "HYP04_FREEZE_DRAFT_*.json")
    if freeze_path is None:
        raise Phase1Error("no freeze draft on disk")
    rec = validate_freeze(Path(freeze_path), panel_path=panel_path)
    frozen_ids = set(rec.eligible_event_ids)
    if not exploration_ids <= frozen_ids:
        raise Phase1Error(
            f"{len(exploration_ids - frozen_ids)} exploration id(s) are not "
            "members of the frozen event set. The split does not describe "
            "this freeze.")
    if exploration_ids & holdout_ids:
        # load_declared_split already refuses this; re-asserted here because
        # it is the single invariant most worth never trusting to only one
        # caller.
        raise Phase1Error("exploration and holdout overlap -- refusing")

    # --- pinned inputs, resolved by name+hash, not by "newest" -------------
    src = panel["sources"]
    cal_path = _pinned_file(lse, src["calendar"], src["calendar_sha256"],
                            what="anchor calendar")
    shocks_path = _pinned_file(lse, src["shocks"], src["shocks_sha256"],
                               what="anchor shocks")
    map_path = _pinned_file(lse, src["curated_map"], src["curated_map_sha256"],
                            what="curated linkage map")

    cal_rows = _rows(cal_path)
    shock_rows = _rows(shocks_path)

    from .make_event_panel import _attributed_sessions, _session_index
    all_events = events_from_calendar(cal_rows)
    shocks = shocks_from_rows(shock_rows)
    attributed = _attributed_sessions(shock_rows)

    # Session index built from the UNRESTRICTED attributed-session set, same
    # as make_event_panel.build() -- restricting it to exploration events
    # would shift day-index POSITIONS relative to what the frozen panel used,
    # and anchor_day must mean the same integer in both places.
    peer_files = sorted((lse / "HYP04_PEER_CLOSES_REQUEST").glob(
        "*_closes_REQUEST.csv"))
    idx, idx_prov = _session_index(attributed, peer_files)
    pos = {d: i for i, d in enumerate(idx)}

    # Cross-check against what the frozen panel recorded, so a silently
    # different session index (a different pad, a different calendar
    # version) is caught here rather than producing day-indices that only
    # LOOK right.
    rec_idx = panel["session_index"]
    if (idx_prov["first"] != rec_idx["first"]
            or idx_prov["last"] != rec_idx["last"]
            or idx_prov["n_sessions"] != rec_idx["n_sessions"]):
        raise Phase1Error(
            f"the rebuilt session index ({idx_prov['first']}..{idx_prov['last']}"
            f", {idx_prov['n_sessions']} sessions) does not match what the "
            f"frozen panel recorded ({rec_idx['first']}..{rec_idx['last']}, "
            f"{rec_idx['n_sessions']} sessions).")

    # --- peer return series, aligned to that index --------------------------
    series: dict[str, Any] = {}
    for f in peer_files:
        obs, rejects, _digest = load_peer_closes(f)
        if rejects:
            raise Phase1Error(f"{f.name} has {len(rejects)} unparseable rows")
        tickers = {o.ticker for o in obs if o.ticker}
        if len(tickers) != 1:
            raise Phase1Error(f"{f.name} names {sorted(tickers)} tickers")
        ticker = tickers.pop()
        series[ticker] = build_series(obs, ticker=ticker, sessions=idx)

    # --- eligibility, EXPLORATION EVENTS ONLY -------------------------------
    # This is the enforcement point for refusal #1. Holdout events are
    # dropped from `events` here, before _coverage or resolve_from_curated_map
    # ever see them -- not filtered out of a result afterward.
    events = [e for e in all_events if e["event_id"] in exploration_ids]
    if len(events) != len(exploration_ids):
        missing = exploration_ids - {e["event_id"] for e in events}
        raise Phase1Error(
            f"{len(missing)} exploration event id(s) are not in the anchor "
            f"calendar: {sorted(missing)[:5]}")

    res = load_curated_linkage(map_path)
    if not res.ok:
        raise Phase1Error(
            f"{map_path.name} did not load cleanly ({res.rows_rejected} "
            "rows rejected)")
    edges_by_anchor: dict[str, list[str]] = {}
    for e in res.edges:
        edges_by_anchor.setdefault(e.anchor_ticker.upper(), []).append(
            e.peer_ticker.upper())

    by_pair, _unresolved, _short = _coverage(
        series, events, edges_by_anchor, attributed, pos)
    panel_pair = resolve_from_curated_map(
        events, map_path=map_path, anchor_shock=shocks,
        peer_history_by_pair=by_pair)

    # --- THE cross-check: this reproduces what was frozen -------------------
    rejoined_ids = set(freeze_record_fields(panel_pair)["eligible_event_ids"])
    if rejoined_ids != exploration_ids:
        raise Phase1Error(
            f"recomputing eligibility over the exploration set does not "
            f"reproduce it: {len(exploration_ids - rejoined_ids)} id(s) lost, "
            f"{len(rejoined_ids - exploration_ids)} id(s) gained. Something "
            "has drifted since the freeze -- refusing rather than computing "
            "over a different world than the one that was frozen.")
    if panel_pair.provenance.uses_placeholder_linkage:
        raise Phase1Error("resolved linkage is placeholder -- refusing")

    return {
        "panel_pair": panel_pair, "shocks": shocks, "attributed": attributed,
        "idx": idx, "pos": pos, "series": series,
        "exploration_ids": exploration_ids, "holdout_ids": holdout_ids,
        "split": split, "freeze": rec, "freeze_path": Path(freeze_path),
        "panel_sha256": panel_sha256, "panel": panel,
        "cal_sha256": src["calendar_sha256"], "shocks_sha256": src["shocks_sha256"],
        "map_sha256": src["curated_map_sha256"],
        "denial_reasons": panel_pair.denial_reasons(),
    }


# ==========================================================================
# Peer earnings -> attributed session -> day index
# ==========================================================================

def _attribute_peer_earnings(peer_earnings_path: Path, idx: list[date], *,
                             peers: list[str]) -> tuple[dict[str, list[int]],
                                                        dict[str, Any]]:
    """Each peer's release dates -> day-index positions in `idx`.

    Reuses `anchor_closes.resolve_attributed_session` -- the SAME BMO/AMC
    attribution `event_panel.resolve_events` uses for anchor events -- rather
    than reimplementing the same-session/next-session rule a second time.
    Returns (peer_earnings_days, coverage_report); the report is what makes
    a gap like BB's visible rather than silently absorbed into an empty list
    that looks the same as "no data was ever collected".
    """
    from .anchor_closes import resolve_attributed_session
    pos = {d: i for i, d in enumerate(idx)}

    if not peer_earnings_path.is_file():
        raise Phase1Error(f"no peer-earnings artifact at {peer_earnings_path}")
    doc = json.loads(peer_earnings_path.read_text(encoding="utf-8"))
    releases = doc.get("per_peer_earnings_releases", {})

    out: dict[str, list[int]] = {}
    coverage: dict[str, Any] = {}
    for peer in peers:
        rows = releases.get(peer, [])
        attributed_days: list[int] = []
        n_unknown_session = 0
        n_outside_index = 0
        for r in rows:
            att, _prior, why = resolve_attributed_session(
                r["release_date"], r["release_session"], idx)
            if att is None:
                n_unknown_session += 1
                continue
            if att not in pos:
                n_outside_index += 1
                continue
            attributed_days.append(pos[att])
        attributed_days.sort()
        out[peer] = attributed_days
        coverage[peer] = {
            "n_releases_total": len(rows),
            "n_attributed": len(attributed_days),
            "n_unknown_session": n_unknown_session,
            "n_outside_session_index": n_outside_index,
            "earliest_attributed_date": (
                idx[attributed_days[0]].isoformat() if attributed_days else None),
            "latest_attributed_date": (
                idx[attributed_days[-1]].isoformat() if attributed_days else None),
        }
    return out, coverage


# ==========================================================================
# D6 disclosure, per horizon
# ==========================================================================

#: D6's mandatory fields, exactly. Checked for completeness before the
#: artifact is written -- see `_assert_d6_complete`.
D6_MANDATORY_FIELDS = (
    "total_cluster_count", "n_singleton_clusters", "cluster_size_distribution",
    "realized_satterthwaite_df", "n_pairs", "n_events",
    "icc_raw_unfloored", "icc_n_clusters", "deff", "n_eff",
)


def _d6_disclosure(table: dict[str, np.ndarray], horizon: int, *,
                   cluster_key: str, k_effective_tests: float) -> dict[str, Any]:
    """Every field D6 makes mandatory, for ONE horizon. Reuses `gate.py`'s
    own N_eff machinery (ICC, DEFF, N_eff, the bootstrap CI) rather than
    hand-rolling a second computation of the same quantities."""
    mask = table["horizon"] == horizon
    n = int(mask.sum())
    if n == 0:
        return {"horizon": horizon, "n_pairs": 0, "n_events": 0,
                "note": "no rows survived at this horizon"}
    g = table[cluster_key][mask]
    clusters, counts = np.unique(g, return_counts=True)

    gr = sample_gate.evaluate_gate(
        table, k_effective_tests=k_effective_tests, reference_horizon=horizon,
        cluster_key=cluster_key)

    return {
        "horizon": horizon,
        "total_cluster_count": int(clusters.size),
        "n_singleton_clusters": int(np.sum(counts == 1)),
        "cluster_size_distribution": {
            "min": int(counts.min()), "median": float(np.median(counts)),
            "max": int(counts.max())},
        "realized_satterthwaite_df": gr.satterthwaite_dof,
        "n_pairs": gr.n_pairs,
        "n_events": gr.n_events,
        "mean_peers_per_event": round(gr.mean_peers_per_event, 4),
        "icc_raw_unfloored": gr.icc_raw,
        "icc_n_clusters": gr.icc_n_clusters,
        "icc_bootstrap_ci_95": gr.icc_bootstrap_ci,
        "deff": gr.deff,
        "n_eff": gr.n_eff,
    }


def _assert_d6_complete(disclosure: dict[str, Any]) -> None:
    if "note" in disclosure:
        return                      # the zero-row case; nothing to disclose
    missing = [f for f in D6_MANDATORY_FIELDS if f not in disclosure]
    if missing:
        raise Phase1Error(
            f"D6 disclosure at horizon {disclosure.get('horizon')} is missing "
            f"mandatory field(s) {missing}. Refusing to write a partial "
            "disclosure.")


# ==========================================================================
# One treatment: residualize=True or False, over the SAME panel
# ==========================================================================

def _run_treatment(panel: SyntheticPanel, *, residualize: bool,
                   cluster_key: str = LOCKED_CLUSTER_KEY,
                   n_permutations: int, seed: int) -> dict[str, Any]:
    built = build_feature_table(panel, residualize=residualize)
    table = built["table"]

    result: LocalProjectionResult = local_projection_analysis(
        table, cluster_key=cluster_key, n_permutations=n_permutations, seed=seed)

    # --- refusal #5: silent horizon drops, made explicit --------------------
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

    # --- D6 disclosure: REPORTING_HORIZONS + peak + onset --------------------
    k = result.effective_independent_tests or 1.0
    report_at = sorted({h for h in REPORTING_HORIZONS if h in fitted_horizons}
                       | ({result.peak_horizon} if result.peak_horizon else set())
                       | ({result.onset_horizon} if result.onset_horizon else set()))
    disclosures = []
    for h in report_at:
        d = _d6_disclosure(table, h, cluster_key=cluster_key,
                           k_effective_tests=k)
        _assert_d6_complete(d)
        disclosures.append(d)

    # --- D7/D8: interval only, never a bare point --------------------------
    onset_interval = None
    onset_refusal = None
    if result.onset_horizon is not None:
        try:
            onset_interval = OnsetInterval.from_onset(result.onset_horizon)
        except OnsetRefusedError as e:
            onset_refusal = str(e)

    # --- D2: measured on THIS table, not the lock's fixture or the full set -
    ref_h = report_at[0] if report_at else (HORIZON_GRID[0] if HORIZON_GRID else 0)
    ref_mask = table["horizon"] == ref_h
    ref_events = table["anchor"][ref_mask]
    ref_periods = table[cluster_key][ref_mask]
    d2_text = (
        f"SEs are clustered ONE WAY, on {cluster_key} (D1). At horizon "
        f"{ref_h}: {int(np.unique(ref_periods).size)} distinct {cluster_key} "
        f"values, {int(np.unique(ref_events).size)} distinct anchors over "
        f"{int(ref_mask.sum())} pairs. The same anchor recurring within a "
        f"cluster is NOT covered by this standard error -- see "
        "clustered_se.TWO_WAY_LIMITATION_NOTE. Two-way clustering is not "
        "implemented anywhere in this repository, validated or otherwise.")

    return {
        "residualize": residualize,
        "n_rows": int(table["event_id"].size),
        "retained_history": built["retained_history"],
        "bucket_population": built["bucket_population"],
        "fits_by_horizon": [
            {"horizon": f.horizon, "beta": f.beta, "se": f.se,
             "t_stat": f.t_stat, "satterthwaite_dof": f.satterthwaite_dof,
             "n_obs": f.n_obs, "n_clusters": f.n_clusters}
            for f in result.fits],
        "horizons_dropped": dropped,
        "peak_horizon": result.peak_horizon,
        "peak_abs_t": result.peak_abs_t,
        "max_abs_t": result.max_abs_t,
        "max_t_critical_value": result.max_t_critical_value,
        "max_t_p_value": result.max_t_p_value,
        "peak_significant": result.peak_significant,
        "effective_independent_tests": result.effective_independent_tests,
        "n_permutations": result.n_permutations,
        "clustering": result.clustering,
        # D7. `onset_horizon_raw` is carried ONLY beside the interval, never
        # alone -- see the module docstring's item 6.
        "onset_horizon_raw": result.onset_horizon,
        "onset_interval": (onset_interval.as_dict() if onset_interval else None),
        "onset_refused": onset_refusal,
        "point_estimate_permitted": False,
        "d2_residual_limitation": d2_text,
        "d6_disclosures": disclosures,
    }


# ==========================================================================
# Orchestration
# ==========================================================================

def build_diagnostics(*, out_path: Path, panel_path: Path = DEFAULT_PANEL,
                      split_path: Path = DEFAULT_SPLIT,
                      peer_earnings_path: Path = DEFAULT_PEER_EARNINGS,
                      freeze_path: Optional[Path] = None, lse: Path = LSE,
                      n_permutations: int = 2000, seed: int = 42,
                      today: Optional[date] = None) -> dict[str, Any]:
    if out_path.exists():
        raise Phase1Error(
            f"{out_path.name} already exists. Dated artifacts are never "
            "overwritten -- delete it deliberately first.")

    # `lse` is where the freeze, pinned calendar/shocks/map, and peer closes
    # actually live -- NOT necessarily out_path's directory. A --dry-run
    # writes out_path into a throwaway tempdir while every real input still
    # lives under the real Live Signal Engine; conflating the two left the
    # dry-run unable to find any of them.
    j = _rejoin(panel_path=panel_path, split_path=split_path,
               freeze_path=freeze_path, lse=lse)

    panel_pair = j["panel_pair"]
    exploration_events = [ev for ev in panel_pair.anchor_events if ev["peers"]]
    peers_used = sorted({p for ev in exploration_events for p in ev["peers"]})

    peer_earnings_days, earnings_coverage = _attribute_peer_earnings(
        peer_earnings_path, j["idx"], peers=peers_used)

    returns = {
        p: np.array([np.nan if r is None else r
                    for r in j["series"][p].log_returns], dtype=float)
        for p in peers_used
    }

    anchor_events = [
        {
            "anchor": ev["anchor"],
            "anchor_day": j["pos"][j["attributed"][ev["event_id"]]],
            "shock": j["shocks"][ev["event_id"]].shock,
            "peers": ev["peers"],
            "calendar_period": _calendar_period_int(ev["event_id"]),
        }
        for ev in exploration_events
    ]
    # Parallel list of the REAL event ids, in the SAME order as anchor_events
    # -- build_feature_table's own `event_id` column is an enumerate index
    # into this list, never the string id. Kept for audit; not fed to the
    # estimator.
    real_event_ids = [ev["event_id"] for ev in exploration_events]

    synth = SyntheticPanel(
        name=f"hyp04-phase1-exploration-{AS_OF}",
        returns=returns, peer_earnings_days=peer_earnings_days,
        anchor_events=anchor_events, n_trading_days=len(j["idx"]),
        # Ground truth fields: N/A on real data, never read by the pipeline
        # (fixtures.SyntheticPanel's own docstring). Left explicit rather than
        # silently defaulted so a reader sees they were deliberately unset.
        injected_lag=None, injected_effect=0.0, injected_effect_window=0,
        peer_base_vol={}, earnings_ramp_amplitude=0.0,
        truth={"real_data": True, "not_applicable": True},
    )

    treatments = {
        name: _run_treatment(synth, residualize=flag,
                             n_permutations=n_permutations, seed=seed)
        for name, flag in TREATMENTS
    }

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-04",
        "phase": "Phase 1 -- exploratory, non-binding (plan v0.2 section 5.3)",
        "what_this_is": (
            "A Phase 1 diagnostic: Stage 1 run openly over the frozen "
            "exploration set (157 of 214 events; the 57-event holdout is "
            "reserved for Phase 3), under the analysis lock's fixed "
            "estimator and reporting rules (D1-D10)."),
        "what_this_is_not": (
            "NOT a finding, NOT a validated strategy, and NOT preregistered -- "
            "target definition, feature set, model spec and validation split "
            "belong to the Phase 2 lock, written after this diagnostic. Moves "
            "no gate condition; wired into no findings panel; not displayable "
            "as a HYP-04 result under any gate state."),
        "point_estimate_permitted": False,
        "is_a_confidence_interval": False,
        "treatments": treatments,
        "peer_earnings_coverage": earnings_coverage,
        "peer_earnings_source": {
            "artifact": Path(peer_earnings_path).name,
            "sha256": _sha256(Path(peer_earnings_path)),
        },
        "denial_reasons_p1_p6": j["denial_reasons"],
        "n_exploration_events_used": len(exploration_events),
        "real_event_ids_in_anchor_event_order": real_event_ids,
        "sources": {
            "panel": panel_path.name, "panel_sha256": j["panel_sha256"],
            "split": split_path.name,
            "split_sha256": _sha256(split_path),
            "freeze": j["freeze_path"].name,
            "freeze_sha256": _sha256(j["freeze_path"]),
            "calendar_sha256": j["cal_sha256"],
            "shocks_sha256": j["shocks_sha256"],
            "curated_map_sha256": j["map_sha256"],
            "analysis_commit_sha": j["freeze"].analysis_commit_sha,
            "analysis_lock_document": j["freeze"].analysis_lock_document,
        },
        # Refusal #10: exactly the exploration ids fed into eligibility
        # resolution, so Step 2's scope-aware freeze refusal can compare
        # against this without guessing.
        "event_ids_consumed": sorted(j["exploration_ids"]),
        "opens_no_gate": (
            "This is a computed Phase 1 diagnostic, not a freeze, not a "
            "registry change, not a linkage ratification. It moves no gate "
            "condition, whatever the gate reads at the moment this file is "
            "read."),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1, default=str) + "\n",
                        encoding="utf-8")
    return doc


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="HYP-04 Phase 1 diagnostic. Exploratory, non-binding. "
                    "Ranges over the signed exploration set only.")
    ap.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    ap.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    ap.add_argument("--peer-earnings", type=Path, default=DEFAULT_PEER_EARNINGS)
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--n-permutations", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print without writing")
    a = ap.parse_args(argv)

    if a.dry_run:
        with tempfile.TemporaryDirectory() as td:
            doc = build_diagnostics(
                out_path=Path(td) / "phase1.json", panel_path=a.panel,
                split_path=a.split, peer_earnings_path=a.peer_earnings,
                n_permutations=a.n_permutations, seed=a.seed)
    else:
        doc = build_diagnostics(
            out_path=a.out, panel_path=a.panel, split_path=a.split,
            peer_earnings_path=a.peer_earnings,
            n_permutations=a.n_permutations, seed=a.seed)

    print(f"exploration events used: {doc['n_exploration_events_used']}")
    for name, t in doc["treatments"].items():
        print(f"\n[{name}]  residualize={t['residualize']}  rows={t['n_rows']}")
        print(f"  peak_horizon={t['peak_horizon']}  "
              f"peak_significant={t['peak_significant']}  "
              f"k_eff={t['effective_independent_tests']}")
        print(f"  onset_interval={t['onset_interval'] and t['onset_interval']['reported_interval']}")
        if t["horizons_dropped"]:
            print(f"  {len(t['horizons_dropped'])} horizon(s) silently "
                  "dropped by the estimator -- see horizons_dropped")
    print("\nPeer earnings coverage:")
    for peer, c in doc["peer_earnings_coverage"].items():
        print(f"  {peer:6} {c['n_attributed']:3}/{c['n_releases_total']:3} "
              f"attributed  {c['earliest_attributed_date']} .. "
              f"{c['latest_attributed_date']}")

    if a.dry_run:
        print("\nDRY RUN -- nothing written.")
    else:
        print(f"\nWROTE {doc['artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
