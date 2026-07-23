#!/usr/bin/env python3
# TASK 4 — Mechanism B validation framework: the honest test. Runs both
# the 8-K anomaly signal and the price/volume anomaly signal against
# EVERY event in FalseNegative_Analysis.csv (n=1021, both large and small
# realized moves, both GST-caught and GST-missed) — not just the recovered
# false negatives — and reports precision/recall tradeoffs against a
# GST-only baseline. "How many false negatives recovered" alone is
# meaningless without knowing the false-positive cost; this measures that
# cost directly.
#
# *** EXCLUSIONS, DISCLOSED ***
# 43/1021 events have data_missing=True in the source file (already
# flagged there as unreliable) — excluded here, leaving n=978. Any event
# where either mechanism signal itself returns None (insufficient
# EDGAR/price data) is kept in the table but excluded from precision/
# recall math for that specific signal, with the exclusion count reported.
#
# Output: Live Signal Engine/Mechanism_B/mechanism_b_validation.csv

from __future__ import annotations
from pathlib import Path
import sys, time
sys.path.insert(0, str(Path(__file__).parent / "Live Signal Engine" / "Mechanism_B"))

import numpy as np
import pandas as pd
from edgar_8k_signal import compute_8k_anomaly_score
from price_volume_signal import compute_price_volume_score

sys.stdout.reconfigure(encoding="utf-8")

FN_PATH = Path("Live Signal Engine") / "FalseNegative_Analysis.csv"
OUT_PATH = Path("Live Signal Engine") / "Mechanism_B" / "mechanism_b_validation.csv"

Z_THRESHOLDS_FOR_CURVE = [2, 3, 4, 5, 6, 7, 8, 9, 10]
ANOMALY_SCORE_THRESHOLDS = [-1, -0.5, 0, 0.5, 1, 1.5, 2, 2.5, 3]
PV_SCORE_THRESHOLDS = [0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]


def precision_recall(predicted_positive: np.ndarray, actual_positive: np.ndarray) -> dict:
    tp = int((predicted_positive & actual_positive).sum())
    fp = int((predicted_positive & ~actual_positive).sum())
    fn = int((~predicted_positive & actual_positive).sum())
    n_flagged = int(predicted_positive.sum())
    n_actual = int(actual_positive.sum())
    precision = tp / n_flagged if n_flagged > 0 else None
    recall = tp / n_actual if n_actual > 0 else None
    return {"n_flagged": n_flagged, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None}


def main():
    print("*** TASK 4: Mechanism B validation framework ***\n")

    fn = pd.read_csv(FN_PATH)
    fn["earnings_date"] = pd.to_datetime(fn["earnings_date"])
    n_total = len(fn)
    fn = fn[~fn["data_missing"]].reset_index(drop=True)
    print(f"Total events: {n_total}  |  usable (data_missing=False): {len(fn)}\n")

    print(f"Computing 8-K anomaly scores and price/volume scores for {len(fn)} events "
          f"({fn['ticker'].nunique()} unique tickers, EDGAR calls cached per ticker)...")
    rows = []
    t0 = time.time()
    for i, ev in fn.iterrows():
        edgar_res = compute_8k_anomaly_score(ev["ticker"], ev["earnings_date"])
        pv_res = compute_price_volume_score(ev["ticker"], ev["earnings_date"])
        rows.append({
            "ticker": ev["ticker"], "earnings_date": ev["earnings_date"].date(),
            "realized_move_pct": ev["realized_move_pct"], "large_move": bool(ev["large_move"]),
            "z_at_earnings_week": ev["z_at_earnings_week"], "week_match_gap_days": ev["week_match_gap_days"],
            "had_spike": bool(ev["had_spike"]),
            "anomaly_score_8k": edgar_res["anomaly_score"],
            "price_volume_score": pv_res["price_volume_score"],
        })
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(fn)} done ({time.time()-t0:.0f}s elapsed)")
    print(f"Done in {time.time()-t0:.0f}s.\n")

    events = pd.DataFrame(rows)
    events.to_csv(OUT_PATH.parent / "mechanism_b_event_level.csv", index=False)

    actual = events["large_move"].to_numpy(dtype=bool)
    n_large = int(actual.sum())
    print(f"Ground truth: {n_large}/{len(events)} events are large_move=True\n")

    all_curve_rows = []

    # --- GST-only baseline: single operating point (had_spike) ---
    print("=== GST-ONLY BASELINE (had_spike, fixed operating point: z>=5, within 5 days) ===")
    gst_pred = events["had_spike"].to_numpy(dtype=bool)
    pr = precision_recall(gst_pred, actual)
    print(f"  n_flagged={pr['n_flagged']}  precision={pr['precision']}  recall={pr['recall']}\n")
    all_curve_rows.append({"signal": "GST_had_spike", "threshold": "z>=5,gap<=5d", **pr})

    # --- GST full curve, varying z threshold (earnings-adjacent only, gap<=5) ---
    print("=== GST CURVE (varying z threshold, earnings-adjacent gap<=5d only) ===")
    adjacent_mask = events["week_match_gap_days"] <= 5
    for zt in Z_THRESHOLDS_FOR_CURVE:
        pred = (adjacent_mask & (events["z_at_earnings_week"] >= zt)).to_numpy(dtype=bool)
        pr = precision_recall(pred, actual)
        print(f"  z>={zt:<3} n_flagged={pr['n_flagged']:<4} precision={pr['precision']}  recall={pr['recall']}")
        all_curve_rows.append({"signal": "GST_curve", "threshold": f"z>={zt}", **pr})
    print()

    # --- 8-K signal curve ---
    print("=== 8-K ANOMALY SIGNAL CURVE ===")
    valid_8k = events["anomaly_score_8k"].notna()
    n_valid_8k = int(valid_8k.sum())
    print(f"Usable events (non-null anomaly_score_8k): {n_valid_8k}/{len(events)}")
    for thr in ANOMALY_SCORE_THRESHOLDS:
        pred = np.where(valid_8k, events["anomaly_score_8k"].fillna(-999) >= thr, False)
        pr = precision_recall(pred, actual)
        print(f"  score>={thr:<5} n_flagged={pr['n_flagged']:<4} precision={pr['precision']}  recall={pr['recall']}")
        all_curve_rows.append({"signal": "8K_anomaly_curve", "threshold": f"score>={thr}", **pr})
    print()

    # --- price/volume signal curve ---
    print("=== PRICE/VOLUME ANOMALY SIGNAL CURVE ===")
    valid_pv = events["price_volume_score"].notna()
    n_valid_pv = int(valid_pv.sum())
    print(f"Usable events (non-null price_volume_score): {n_valid_pv}/{len(events)}")
    for thr in PV_SCORE_THRESHOLDS:
        pred = np.where(valid_pv, events["price_volume_score"].fillna(-999) >= thr, False)
        pr = precision_recall(pred, actual)
        print(f"  score>={thr:<5} n_flagged={pr['n_flagged']:<4} precision={pr['precision']}  recall={pr['recall']}")
        all_curve_rows.append({"signal": "price_volume_curve", "threshold": f"score>={thr}", **pr})
    print()

    # --- combined: GST OR 8-K OR price/volume, at representative thresholds ---
    print("=== COMBINED SIGNALS (GST had_spike OR 8-K>=1.0 OR price/volume>=0.75) ===")
    combined_pred = (gst_pred |
                      (events["anomaly_score_8k"].fillna(-999) >= 1.0).to_numpy() |
                      (events["price_volume_score"].fillna(-999) >= 0.75).to_numpy())
    pr_combined = precision_recall(combined_pred, actual)
    print(f"  n_flagged={pr_combined['n_flagged']}  precision={pr_combined['precision']}  recall={pr_combined['recall']}")
    print(f"\n  Incremental vs GST-only: recall {pr['recall']} -> see GST baseline above "
          f"({pr_combined['recall']} combined), at precision cost "
          f"{all_curve_rows[0]['precision']} -> {pr_combined['precision']}")
    all_curve_rows.append({"signal": "combined_GST_OR_8K_OR_PV", "threshold": "8K>=1.0,PV>=0.75", **pr_combined})

    curve_df = pd.DataFrame(all_curve_rows)
    combined = pd.concat([curve_df, pd.DataFrame([{}]), events], ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")
    print(f"Wrote: {OUT_PATH.parent / 'mechanism_b_event_level.csv'}")


if __name__ == "__main__":
    main()
