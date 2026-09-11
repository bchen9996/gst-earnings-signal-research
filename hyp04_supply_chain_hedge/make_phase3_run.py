#!/usr/bin/env python3
"""HYP-04 Phase 3 -- the one locked run against the holdout.

=== WHERE THIS SITS ===

Plan v0.2 section 5.3: *"Run the locked model against the holdout **once**,
report the result regardless of outcome, no re-running until it looks
better."* Its own smoke-test clause: *"a dry run against a copy of the
holdout **schema** must pass before the one real execution -- the real run
should never be the first time the code has executed end-to-end."*

D10 (the R cross-check) is satisfied (commit `80626cc`). Phase 2's lock
(`HYP04_PHASE2_LOCK_2026-09-10.json`) is signed. Every prior spec question is
closed. This module is what Phase 2's own text calls "that later, separate,
explicitly-authorized run."

=== WHY THIS IS NOT SHAPED LIKE make_phase1_diagnostics.py OR
    make_phase2_lock.py ===

Every earlier phase had a rehearsal-then-sign shape: build an inert draft,
inspect it, THEN sign. Phase 3 has no such shape. The moment this code
touches the real holdout, the one-time look has happened -- whether or not
anything is later "signed." So the authorization has to come BEFORE
computation, not after, and it has to be unforgeable by this module itself:

  1. A signed `HYP04_PHASE3_AUTHORIZATION_<date>.json` (`ratify phase3`) must
     already exist, unconsumed, with its `pinned_phase2_lock_sha256` matching
     the signed Phase 2 lock's actual hash right now. (Its `pinned_commit_sha`
     is recorded for provenance, same as every other governing artifact's
     commit-sha field -- never re-checked against a live HEAD; see
     `_load_valid_authorization`'s own comment for why that comparison is a
     fixed point, not a drift signal.) This module writes none of the
     authorization's fields; the owner types the affirmation themselves, in
     their own terminal, exactly as for `ratify phase2` / `ratify attest`.
  2. The in-process synthetic rehearsal (a `fixtures.make_panel`-shaped
     panel, run through the SAME `_run_treatment` -> D6/D7 path the real
     holdout will use) is not an opt-in step someone might skip -- it runs
     EVERY time `main()` is invoked, before any real file is opened, so plan
     v0.2's requirement is true by construction rather than by convention.
  3. If ANY `HYP04_PHASE3_RESULT_*.json` already exists anywhere under `Live
     Signal Engine/`, this refuses unconditionally, regardless of `--out`.
     "No re-running" is enforced structurally, not by trusting a human not to
     ask twice.
  4. The authorization is marked CONSUMED the instant a real run succeeds, so
     even a leftover authorization file cannot trigger a second run.

=== REUSE, NOT REIMPLEMENTATION ===

`_run_treatment`, `_d6_disclosure`, `_assert_d6_complete`,
`_calendar_period_int`, `_attribute_peer_earnings`, `_sha256`, `_pinned_file`,
`_rows` are imported from `make_phase1_diagnostics` unchanged -- none of them
know or care whether the ids passed in are exploration or holdout.

`_rejoin_holdout` below is a deliberate NEW function, not a parameterised
version of `make_phase1_diagnostics._rejoin`. That function is deliberately,
structurally hostile to letting a holdout id through (its own docstring: "a
holdout event cannot leak in... it is never computed over at all"); adding an
`ids` parameter so it could also serve Phase 3 would be exactly the kind of
shared-footgun this project's governance exists to avoid. This function has
the mirror-image invariant -- an EXPLORATION id must never enter it -- kept
as its own auditable thing.

`validate_phase2_lock`'s hash-pin checks are reused directly for the Phase 2
lock/target.py/constants.py drift check, rather than a second implementation.

=== ONE TREATMENT ONLY ===

Phase 2's lock fixed `residualize=True` unconditionally; Phase 1's
`unresidualized_sensitivity` was an ad hoc BB diagnostic aid and "is not
carried forward" (the lock's own text). There is one treatment here, not two
to choose between after seeing results.

Never a bare `assert`: `python -O` strips asserts, and every guard here that
must hold in production raises `Phase3Error`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from . import make_phase1_diagnostics as P1
from .constants import LOCKED_CLUSTER_KEY, N_PERMUTATIONS, RANDOM_SEED
from .fixtures import make_panel
from .make_freeze_draft import _commit_sha, _sha256, validate_freeze
from .make_phase2_lock import (
    CONSTANTS_PY,
    TARGET_PY,
    load_declared_phase2_lock,
)
from .make_validation_split import load_declared_split

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

DEFAULT_PANEL = P1.DEFAULT_PANEL
DEFAULT_SPLIT = P1.DEFAULT_SPLIT
DEFAULT_PEER_EARNINGS = P1.DEFAULT_PEER_EARNINGS
DEFAULT_PHASE2_LOCK = LSE / "HYP04_PHASE2_LOCK_2026-09-10.json"

RESULT_PATTERN = "HYP04_PHASE3_RESULT_*.json"
AUTHORIZATION_PATTERN = "HYP04_PHASE3_AUTHORIZATION_*.json"


class Phase3Error(RuntimeError):
    """A precondition does not hold.

    Phase3Error, never a bare `assert`: `python -O` strips asserts, and a
    guard that vanishes under an optimisation flag is not a guard -- and this
    is the one place in the whole project where that would matter most.
    """


# ==========================================================================
# 1. The in-process rehearsal. Runs every time, before any real file opens.
# ==========================================================================

def run_rehearsal(*, n_permutations: int = 200, seed: int = RANDOM_SEED
                  ) -> dict[str, Any]:
    """Exercise the FULL estimator + D6/D7 disclosure path on synthetic data
    shaped like the real holdout, before touching anything real.

    Not a mock of the pipeline -- the actual `_run_treatment` function the
    real holdout run below calls, on a `fixtures.make_panel` panel (the same
    generator this project's other test suites already use). If this fails,
    the real run never proceeds.
    """
    panel = make_panel(
        "hyp04-phase3-rehearsal", n_anchors=4, n_quarters=5,
        n_peers_per_anchor=3, injected_lag=None, injected_effect=0.0,
        seed=seed)
    result = P1._run_treatment(
        panel, residualize=True, cluster_key=LOCKED_CLUSTER_KEY,
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

#: What `ratify phase3` requires you to type, verbatim, BEFORE any
#: computation happens -- see ratify.py's PHASE3_AFFIRMATION for the single
#: source of truth. Duplicated here as a constant ONLY for the refusal
#: message; the actual comparison happens in ratify.py.
AUTHORIZATION_FIELDS = ("declared", "declared_by", "declared_date",
                        "attestation_text", "pinned_commit_sha",
                        "pinned_phase2_lock_sha256", "consumed")


def _find_authorization(lse: Path) -> Optional[Path]:
    hits = sorted(lse.glob(AUTHORIZATION_PATTERN))
    if len(hits) > 1:
        raise Phase3Error(
            f"{len(hits)} Phase 3 authorization files exist "
            f"({[p.name for p in hits]}) -- exactly one is expected. "
            "Refusing rather than guessing which one governs.")
    return hits[0] if hits else None


def _load_valid_authorization(lse: Path, *, repo: Path,
                              phase2_lock_path: Path) -> dict[str, Any]:
    path = _find_authorization(lse)
    if path is None:
        raise Phase3Error(
            "no Phase 3 authorization on disk. The real holdout run requires "
            "one, typed by the owner BEFORE any computation -- see "
            "'python -m hyp04_supply_chain_hedge.ratify phase3 --template'. "
            "This module will not compute against the holdout without it.")
    doc = json.loads(path.read_text(encoding="utf-8"))
    for f in AUTHORIZATION_FIELDS:
        if f not in doc:
            raise Phase3Error(
                f"{path.name} has no {f!r} key; this does not look like an "
                "authorization written by 'ratify phase3'")
    if doc["declared"] is not True:
        raise Phase3Error(f"{path.name} is a draft: 'declared' is not true.")
    if doc["consumed"] is True:
        raise Phase3Error(
            f"{path.name} was already consumed by a prior run "
            f"(consumed_by={doc.get('consumed_by_result')!r}). A consumed "
            "authorization cannot trigger a second run -- that is the "
            "entire point of marking it consumed.")
    # `_commit_sha` still runs -- refuses on a dirty tree, the same hygiene
    # every other consequential step here requires. Its VALUE is not
    # compared against `pinned_commit_sha`: that field records what HEAD was
    # the instant before the authorization file itself was written, and the
    # owner committing that very file (required to satisfy the clean-tree
    # check on every other governance step in this project) necessarily
    # produces a NEW commit sha the authorization cannot have predicted --
    # a fixed-point problem, not a drift signal. What actually matters --
    # "does the code/spec that would run match what was authorized" -- is
    # caught by the target.py/constants.py/Phase 2 lock hash pins below,
    # exactly as `validate_phase2_lock` catches its own drift, without a
    # live-HEAD comparison either.
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
# 3. The holdout-only rejoin -- the mirror image of Phase 1's `_rejoin`.
# ==========================================================================

def _rejoin_holdout(*, panel_path: Path, split_path: Path,
                    freeze_path: Optional[Path], lse: Path) -> dict[str, Any]:
    """Everything needed to build a SyntheticPanel, over HOLDOUT events only.

    An exploration id must never enter this computation. Enforced the same
    way Phase 1 enforces the opposite: filtered BEFORE eligibility
    resolution, not afterward, plus an explicit cross-check at the end.
    """
    from .artifacts import newest_in
    from .curated_linkage import load_curated_linkage
    from .make_event_panel import _attributed_sessions, _session_index, _coverage
    from .peer_ceiling import events_from_calendar, shocks_from_rows
    from .peer_returns import load_peer_closes, build_series
    from .linkage_resolution import freeze_record_fields, resolve_from_curated_map

    if not panel_path.is_file():
        raise Phase3Error(f"no event panel at {panel_path}")
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    panel_sha256 = _sha256(panel_path)

    split = load_declared_split(split_path)
    if split["pins"]["panel"] != panel_path.name:
        raise Phase3Error(
            f"the signed split pins panel {split['pins']['panel']!r}, not "
            f"{panel_path.name!r}. Wrong panel for this split.")
    if split["pins"]["panel_sha256"] != panel_sha256:
        raise Phase3Error(
            "the signed split's pinned panel_sha256 does not match the "
            "panel on disk. The panel has changed since the split was "
            "declared.")
    exploration_ids = set(split["exploration"]["event_ids"])
    holdout_ids = set(split["holdout"]["event_ids"])
    if exploration_ids & holdout_ids:
        raise Phase3Error("exploration and holdout overlap -- refusing")

    freeze_path = freeze_path or newest_in(lse, "HYP04_FREEZE_DRAFT_*.json")
    if freeze_path is None:
        raise Phase3Error("no freeze draft on disk")
    rec = validate_freeze(Path(freeze_path), panel_path=panel_path)
    frozen_ids = set(rec.eligible_event_ids)
    if not holdout_ids <= frozen_ids:
        raise Phase3Error(
            f"{len(holdout_ids - frozen_ids)} holdout id(s) are not members "
            "of the frozen event set. The split does not describe this "
            "freeze.")

    src = panel["sources"]
    cal_path = P1._pinned_file(lse, src["calendar"], src["calendar_sha256"],
                               what="anchor calendar")
    shocks_path = P1._pinned_file(lse, src["shocks"], src["shocks_sha256"],
                                  what="anchor shocks")
    map_path = P1._pinned_file(lse, src["curated_map"], src["curated_map_sha256"],
                               what="curated linkage map")

    cal_rows = P1._rows(cal_path)
    shock_rows = P1._rows(shocks_path)

    all_events = events_from_calendar(cal_rows)
    shocks = shocks_from_rows(shock_rows)
    attributed = _attributed_sessions(shock_rows)

    peer_files = sorted((lse / "HYP04_PEER_CLOSES_REQUEST").glob(
        "*_closes_REQUEST.csv"))
    idx, idx_prov = _session_index(attributed, peer_files)
    pos = {d: i for i, d in enumerate(idx)}

    rec_idx = panel["session_index"]
    if (idx_prov["first"] != rec_idx["first"]
            or idx_prov["last"] != rec_idx["last"]
            or idx_prov["n_sessions"] != rec_idx["n_sessions"]):
        raise Phase3Error(
            f"the rebuilt session index ({idx_prov['first']}..{idx_prov['last']}"
            f", {idx_prov['n_sessions']} sessions) does not match what the "
            f"frozen panel recorded ({rec_idx['first']}..{rec_idx['last']}, "
            f"{rec_idx['n_sessions']} sessions).")

    series: dict[str, Any] = {}
    for f in peer_files:
        obs, rejects, _digest = load_peer_closes(f)
        if rejects:
            raise Phase3Error(f"{f.name} has {len(rejects)} unparseable rows")
        tickers = {o.ticker for o in obs if o.ticker}
        if len(tickers) != 1:
            raise Phase3Error(f"{f.name} names {sorted(tickers)} tickers")
        ticker = tickers.pop()
        series[ticker] = build_series(obs, ticker=ticker, sessions=idx)

    # --- the enforcement point: HOLDOUT ONLY, filtered BEFORE resolution ---
    events = [e for e in all_events if e["event_id"] in holdout_ids]
    if len(events) != len(holdout_ids):
        missing = holdout_ids - {e["event_id"] for e in events}
        raise Phase3Error(
            f"{len(missing)} holdout event id(s) are not in the anchor "
            f"calendar: {sorted(missing)[:5]}")
    leaked = [e for e in events if e["event_id"] in exploration_ids]
    if leaked:
        raise Phase3Error(
            f"{len(leaked)} event(s) selected for the holdout rejoin are "
            "also exploration ids -- refusing rather than computing over an "
            "ambiguous set")

    res = load_curated_linkage(map_path)
    if not res.ok:
        raise Phase3Error(
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

    rejoined_ids = set(freeze_record_fields(panel_pair)["eligible_event_ids"])
    if rejoined_ids != holdout_ids:
        raise Phase3Error(
            f"recomputing eligibility over the holdout set does not "
            f"reproduce it: {len(holdout_ids - rejoined_ids)} id(s) lost, "
            f"{len(rejoined_ids - holdout_ids)} id(s) gained. Something has "
            "drifted since the freeze -- refusing.")
    if any(eid in exploration_ids for eid in rejoined_ids):
        raise Phase3Error(
            "the rejoined eligible set contains an exploration id -- "
            "refusing rather than computing over a contaminated set")
    if panel_pair.provenance.uses_placeholder_linkage:
        raise Phase3Error("resolved linkage is placeholder -- refusing")

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
# 4. Orchestration
# ==========================================================================

def build_result(*, out_path: Path, panel_path: Path = DEFAULT_PANEL,
                 split_path: Path = DEFAULT_SPLIT,
                 peer_earnings_path: Path = DEFAULT_PEER_EARNINGS,
                 phase2_lock_path: Path = DEFAULT_PHASE2_LOCK,
                 freeze_path: Optional[Path] = None, lse: Path = LSE,
                 repo: Path = REPO_ROOT, today: Optional[date] = None
                 ) -> dict[str, Any]:
    """The one real run. Refuses unless authorized, un-run, and un-drifted."""
    when = today or date.today()

    if out_path.exists():
        raise Phase3Error(
            f"{out_path.name} already exists. Dated artifacts are never "
            "overwritten.")
    existing_results = sorted(lse.glob(RESULT_PATTERN))
    if existing_results:
        raise Phase3Error(
            f"a Phase 3 result already exists ({[p.name for p in existing_results]}"
            f") -- the holdout is run ONCE. Refusing regardless of --out.")

    lock = load_declared_phase2_lock(phase2_lock_path)
    for label, pinned_path, pinned_hash in (
        ("target.py", TARGET_PY, lock["pins"]["target_py_sha256"]),
        ("constants.py", CONSTANTS_PY, lock["pins"]["constants_py_sha256"]),
    ):
        current = _sha256(pinned_path)
        if current != pinned_hash:
            raise Phase3Error(
                f"{label} has changed since the Phase 2 lock was declared "
                f"(pinned {pinned_hash[:12]}, now {current[:12]}). The lock "
                "no longer describes the code that would run.")
    if _sha256(split_path) != lock["pins"]["validation_split_sha256"]:
        raise Phase3Error(
            "the validation split on disk does not match the Phase 2 lock's "
            "pinned hash. The split has changed since the lock was declared.")

    auth_path = _find_authorization(lse)
    auth = _load_valid_authorization(lse, repo=repo,
                                     phase2_lock_path=phase2_lock_path)

    # The rehearsal runs even here, one more time, immediately before the
    # real computation -- not only as a separate --rehearsal-only step
    # someone could skip.
    run_rehearsal()

    j = _rejoin_holdout(panel_path=panel_path, split_path=split_path,
                        freeze_path=freeze_path, lse=lse)
    panel_pair = j["panel_pair"]
    holdout_events = [ev for ev in panel_pair.anchor_events if ev["peers"]]
    peers_used = sorted({p for ev in holdout_events for p in ev["peers"]})

    peer_earnings_days, earnings_coverage = P1._attribute_peer_earnings(
        peer_earnings_path, j["idx"], peers=peers_used)

    import numpy as np
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
            "calendar_period": P1._calendar_period_int(ev["event_id"]),
        }
        for ev in holdout_events
    ]
    real_event_ids = [ev["event_id"] for ev in holdout_events]

    from .fixtures import SyntheticPanel
    synth = SyntheticPanel(
        name=f"hyp04-phase3-holdout-{when.isoformat()}",
        returns=returns, peer_earnings_days=peer_earnings_days,
        anchor_events=anchor_events, n_trading_days=len(j["idx"]),
        injected_lag=None, injected_effect=0.0, injected_effect_window=0,
        peer_base_vol={}, earnings_ramp_amplitude=0.0,
        truth={"real_data": True, "not_applicable": True},
    )

    treatment = P1._run_treatment(
        synth, residualize=lock["model_spec"]["residualize"],
        cluster_key=lock["model_spec"]["cluster_key"],
        n_permutations=lock["model_spec"]["n_permutations"],
        seed=lock["model_spec"]["random_seed"])

    doc: dict[str, Any] = {
        "artifact": out_path.name,
        "as_of_date": when.isoformat(),
        "hypothesis_id": "HYP-04",
        "phase": "Phase 3 -- the one locked run against the holdout "
                "(plan v0.2 section 5.3)",
        "what_this_is": (
            "The single, preregistered run of the Phase 2-locked model "
            "against the frozen 57-event holdout. Reported once, "
            "regardless of outcome."),
        "what_this_is_not": (
            "NOT a diagnostic, NOT repeatable, and NOT a license to iterate "
            "on the spec having seen this. If this result is disappointing, "
            "the answer is a new hypothesis or a new preregistration cycle "
            "against fresh data -- never a second run against this holdout."),
        "reported_regardless_of_outcome": True,
        "no_rerun_permitted": True,
        "point_estimate_permitted": False,
        "is_a_confidence_interval": False,
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
        "treatment": treatment,
        "peer_earnings_coverage": earnings_coverage,
        "peer_earnings_source": {
            "artifact": Path(peer_earnings_path).name,
            "sha256": _sha256(Path(peer_earnings_path)),
        },
        "denial_reasons_p1_p6": j["denial_reasons"],
        "n_holdout_events_used": len(holdout_events),
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
        "event_ids_consumed": sorted(j["holdout_ids"]),
        "opens_no_gate": (
            "This is a computed Phase 3 result, not a freeze, not a "
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
        description="HYP-04 Phase 3: the one locked run against the "
                    "holdout. Requires a prior, typed 'ratify phase3' "
                    "authorization.")
    ap.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    ap.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    ap.add_argument("--peer-earnings", type=Path, default=DEFAULT_PEER_EARNINGS)
    ap.add_argument("--phase2-lock", type=Path, default=DEFAULT_PHASE2_LOCK)
    ap.add_argument("--out", type=Path, default=None,
                    help="default: Live Signal Engine/"
                         "HYP04_PHASE3_RESULT_<today>.json")
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

    out = a.out or (LSE / f"HYP04_PHASE3_RESULT_{date.today().isoformat()}.json")
    doc = build_result(out_path=out, panel_path=a.panel, split_path=a.split,
                       peer_earnings_path=a.peer_earnings,
                       phase2_lock_path=a.phase2_lock)

    t = doc["treatment"]
    print(f"holdout events used: {doc['n_holdout_events_used']}")
    print(f"peak_horizon={t['peak_horizon']}  peak_significant={t['peak_significant']}  "
          f"k_eff={t['effective_independent_tests']}")
    print(f"onset_interval={t['onset_interval'] and t['onset_interval']['reported_interval']}")
    print(f"\nWROTE {doc['artifact']}")
    print("This holdout is now spent. No further run against it is permitted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
