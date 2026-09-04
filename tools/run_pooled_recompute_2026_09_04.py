#!/usr/bin/env python3
"""Recompute the four AFFECTED pooled clustered-inference specifications.

Implements GST_POOLED_RECOMPUTE_DESIGN_v1.0_FROZEN_2026-09-04.md, which was
written and frozen BEFORE any corrected value existed. This script decides
nothing: every rule it applies is fixed in that document.

CORRECTION_OVERLAY_2026-08-22.md marks four pooled results
DO_NOT_CITE_PENDING_CORRECTION because they pool 152 treated + 133 control rows
containing 20 cross-arm identities and 48 redundant control rows. The citation
policy clears that label only by computing the corrected value and reporting it,
whatever it is.

The estimator is REUSED UNMODIFIED from the original generator, so the before
and after numbers differ only in which rows are in the sample.

RETROSPECTIVE_DEVELOPMENT_ONLY. Confirms no hypothesis, moves no gate.

Run:  python tools/run_pooled_recompute_2026_09_04.py --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# The generator's own cr2_fe, imported rather than reimplemented. A second
# implementation of the estimator would make any difference between the old and
# new numbers ambiguous between "the sample changed" and "the code changed".
_gen_path = ROOT / "tools" / "run_retrospective_market_response_decomposition.py"
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("_retro_gen", _gen_path)
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)
cr2_fe = _gen.cr2_fe

EVENTS = ROOT / "Live Signal Engine" / "retrospective_event_components.csv"
OUT = ROOT / "Live Signal Engine" / "GST_POOLED_RECOMPUTE_RESULTS_2026-09-04.json"
DESIGN = "GST_POOLED_RECOMPUTE_DESIGN_v1.0_FROZEN_2026-09-04.md"

# The committed values being corrected, from RETROSPECTIVE_MARKET_RESPONSE_
# RESULTS_v1.0.json. Pinned here so the comparison cannot drift.
BEFORE = {
    "primary_magnitude_abs_day_return":
        {"n": 285, "coef_pp": 1.509, "cr2_se_pp": 0.7664, "satterthwaite_df": 16.301,
         "t_stat": 1.969, "p_value": 0.0662},
    "magnitude_abs_excess_vs_spy":
        {"n": 285, "coef_pp": 1.5388, "cr2_se_pp": 0.6777, "satterthwaite_df": 16.301,
         "t_stat": 2.270, "p_value": 0.03707},
    "strategy_E_incremental_high_gst":
        {"n": 285, "coef_pp": 0.0131, "cr2_se_pp": 0.6175, "satterthwaite_df": 16.301,
         "t_stat": 0.021, "p_value": 0.98332},
    "strategy_B_incremental_high_gst":
        {"n": 285, "coef_pp": -0.3439, "cr2_se_pp": 0.4605, "satterthwaite_df": 16.301,
         "t_stat": -0.747, "p_value": 0.46577},
}

SPECS = (
    ("primary_magnitude_abs_day_return", "abs_day"),
    ("magnitude_abs_excess_vs_spy", "abs_day_ex"),
    ("strategy_E_incremental_high_gst", "strat_E"),
    ("strategy_B_incremental_high_gst", "strat_B"),
)


class RefusedError(RuntimeError):
    """A precondition of the frozen design does not hold."""


def build_frame() -> pd.DataFrame:
    """The 285-row frame with the same derived columns the generator makes."""
    ev = pd.read_csv(EVENTS)
    ev["high_gst"] = (ev.role == "signal").astype(float)
    ev["abs_day"] = pd.to_numeric(ev.day_return, errors="coerce").abs()
    ev["abs_day_ex"] = pd.to_numeric(ev.day_return_ex, errors="coerce").abs()
    import numpy as np
    ev["strat_B"] = np.sign(pd.to_numeric(ev.gap, errors="coerce")) * \
        pd.to_numeric(ev.open_to_close, errors="coerce")
    ev["strat_E"] = np.sign(pd.to_numeric(ev.gap, errors="coerce")) * \
        pd.to_numeric(ev.post_1_3_ex, errors="coerce")
    return ev


def corrected(ev: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Frozen design section 3. Identity is (ticker, earnings_date)."""
    ev = ev.copy()
    ev["_id"] = list(zip(ev.ticker, ev.earnings_date))
    sig = ev[ev.role == "signal"]
    ctl = ev[ev.role == "control"]
    sig_ids = set(sig["_id"])

    # Rule 2: a control identity that also appears in the signal arm carries the
    # wrong label -- it meets the z >= 5.0 signal rule, which is why it is a
    # signal event. Drop the control copy, never the signal one.
    ctl_no_overlap = ctl[~ctl["_id"].isin(sig_ids)]
    # Rule 3: exact-duplicate removal. Verified below to be immaterial.
    ctl_dedup = (ctl_no_overlap
                 .sort_values(["ticker", "earnings_date", "pair_id"])
                 .drop_duplicates(subset="_id", keep="first"))

    out = pd.concat([sig, ctl_dedup], ignore_index=True)
    audit = {
        "signal_rows_kept": int(len(sig)),
        "control_rows_kept": int(len(ctl_dedup)),
        "n_corrected": int(len(out)),
        "control_rows_dropped_total": int(len(ctl) - len(ctl_dedup)),
        "dropped_cross_arm_overlap_rows": int(len(ctl) - len(ctl_no_overlap)),
        "dropped_redundant_duplicate_rows": int(len(ctl_no_overlap) - len(ctl_dedup)),
        "distinct_signal_identities": int(sig["_id"].nunique()),
        "distinct_control_identities_before": int(ctl["_id"].nunique()),
        "distinct_control_identities_after": int(ctl_dedup["_id"].nunique()),
        "overlap_identities": int(len(sig_ids & set(ctl["_id"]))),
        "clusters": int(out.ticker.nunique()),
    }
    return out.drop(columns="_id"), audit


def check_preconditions(ev: pd.DataFrame, audit: dict) -> None:
    """Refuse if the data is not the data the design was frozen against.

    RefusedError, never assert: python -O strips asserts, and a precondition
    that vanishes under an optimisation flag is not a precondition.
    """
    if len(ev) != 285:
        raise RefusedError(f"expected 285 rows, found {len(ev)}")
    if audit["distinct_signal_identities"] != 152:
        raise RefusedError("signal arm is not 152 distinct identities")
    if audit["distinct_control_identities_before"] != 85:
        raise RefusedError("control arm is not 85 distinct identities")
    if audit["overlap_identities"] != 20:
        raise RefusedError(f"expected 20 overlap identities, found "
                           f"{audit['overlap_identities']}")
    if audit["dropped_redundant_duplicate_rows"] + \
            audit["dropped_cross_arm_overlap_rows"] < 48:
        raise RefusedError("the 48 redundant rows are not accounted for")
    if audit["n_corrected"] != 217:
        raise RefusedError(f"frozen design says 217 rows, got {audit['n_corrected']}")

    # The design claims dedup is immaterial because duplicate control rows are
    # identical on every outcome column. Claimed in the document, so verified
    # here rather than trusted.
    cols = ["day_return", "day_return_ex", "gap", "open_to_close",
            "post_1_3", "post_1_3_ex", "pre_drift", "zscore"]
    ctl = ev[ev.role == "control"].copy()
    ctl["_id"] = list(zip(ctl.ticker, ctl.earnings_date))
    for ident, grp in ctl.groupby("_id"):
        if len(grp) < 2:
            continue
        for c in cols:
            if grp[c].astype(str).nunique() > 1:
                raise RefusedError(
                    f"duplicate control rows for {ident} disagree on {c}; the "
                    "frozen design's 'dedup is immaterial' claim is false")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write the artifact; otherwise dry-run to stdout")
    args = ap.parse_args()

    ev = build_frame()
    fixed, audit = corrected(ev)
    check_preconditions(ev, audit)

    results = {}
    for name, ycol in SPECS:
        after = cr2_fe(fixed, ycol)
        results[name] = {"before_committed": BEFORE[name], "after_corrected": after}

    doc = {
        "artifact": "GST_POOLED_RECOMPUTE_RESULTS",
        "date": "2026-09-04",
        "status": "RETROSPECTIVE_DEVELOPMENT_ONLY",
        "confirms_hyp01": False,
        "uses_prospective_outcomes": False,
        "frozen_design": DESIGN,
        "clears_label": "DO_NOT_CITE_PENDING_CORRECTION",
        "estimator": ("cr2_fe reused UNMODIFIED from "
                      "tools/run_retrospective_market_response_decomposition.py; "
                      "only the sample changed"),
        "sample_audit": audit,
        "results": results,
        "inherited_limitation": (
            "A restriction of an existing sample, not a re-match. The surviving "
            "control arm is a non-random subset: controls that were reused, or "
            "that double as signal events, are systematically removed."),
    }

    print(json.dumps(doc["sample_audit"], indent=2))
    print()
    for name, _ in SPECS:
        b = results[name]["before_committed"]
        a = results[name]["after_corrected"]
        print(f"{name}")
        print(f"   before  n={b['n']:3d}  coef={b['coef_pp']:+7.4f}pp  "
              f"se={b['cr2_se_pp']:.4f}  df={b['satterthwaite_df']:.3f}  "
              f"t={b['t_stat']:+.3f}  p={b['p_value']:.5f}")
        print(f"   after   n={a['n']:3d}  coef={a['coef_pp']:+7.4f}pp  "
              f"se={a['cr2_se_pp']:.4f}  df={a['satterthwaite_df']:.3f}  "
              f"t={a['t_stat']:+.3f}  p={a['p_value']:.5f}")
        print()

    if args.write:
        if OUT.exists():
            raise RefusedError(f"{OUT.name} exists; refusing to overwrite a "
                               "run-once artifact")
        OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        print(f"WROTE {OUT.name}")
    else:
        print("DRY RUN -- pass --write to persist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
