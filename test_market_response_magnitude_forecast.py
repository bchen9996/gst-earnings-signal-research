#!/usr/bin/env python3
"""Focused check on the magnitude-forecast study.

Verifies point-in-time feature construction, deduplication, that B and C differ only
by the GST column, chronological folds, and that reported errors recompute.
Deterministic, offline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
RES = json.loads((ROOT / "RETROSPECTIVE_MAGNITUDE_FORECAST_RESULTS_v1.0.json").read_text(encoding="utf-8"))
REPORT = (ROOT / "RETROSPECTIVE_MAGNITUDE_FORECAST_REPORT_v1.0.md").read_text(encoding="utf-8")
OOS = pd.read_csv(ROOT / "Live Signal Engine" / "retrospective_magnitude_oos_predictions.csv")
SRC = pd.read_csv(ROOT / "Live Signal Engine" / "retrospective_event_components.csv")
OHLC = ROOT / "Daily OHLC Data (2021-2025 Opening Gap Test)"
TOOL = (ROOT / "tools" / "run_retrospective_magnitude_forecast.py").read_text(encoding="utf-8")

FAIL = []


def check(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


import run_retrospective_magnitude_forecast as M  # noqa: E402

# ---- 1. models differ only by the GST feature ----
check("1a. C is exactly B plus the GST column",
      M.BASE_FEATURES + [M.GST_FEATURE] == M.BASE_FEATURES + ["gst_z_pre"]
      and M.GST_FEATURE not in M.BASE_FEATURES)
check("1b. five frozen baseline predictors", len(M.BASE_FEATURES) == 5)
check("1c. one fixed regularized linear model, alpha not tuned",
      "Ridge(alpha=RIDGE_ALPHA" in TOOL and M.RIDGE_ALPHA == 1.0
      and "GridSearch" not in TOOL and "RandomizedSearch" not in TOOL)
check("1d. no directional trading or profitability is evaluated",
      RES["evaluates_directional_trading_or_profitability"] is False
      and not any(k in TOOL for k in ("strategy_return", "hit_rate", "max_drawdown", "net_pct")))

# ---- 2. outcome and point-in-time features ----
bad = []
for _, r in OOS.sample(n=20, random_state=0).iterrows():
    px = pd.read_csv(OHLC / f"{r.ticker}_ohlc.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    T = int(px.index[px["Date"] == pd.Timestamp(r.event_day)][0])
    if abs(abs(px.Open[T] / px.Close[T - 1] - 1) - r.abs_gap) > 1e-9:
        bad.append((r.ticker, r.event_day))
check(f"2a. outcome recomputes as abs(open(T)/close(T-1)-1) (bad={bad[:2]})", not bad)
check("2b. outcome is the absolute gap", RES["outcome"] == "abs(open(T)/close(T-1) - 1)")
body = TOOL.split('"""', 2)[-1]
feat = body.split("c = px[\"Close\"].values")[1].split("zs, anch = ref.get")[0]
feat_no_outcome = feat.replace('y = abs(px["Open"].values[T] / c[T - 1] - 1.0)', "")
check("2c. no predictor reads an index at or after T",
      "c[T]" not in feat_no_outcome and "Open" not in feat_no_outcome)
check("2d. the GST feature uses only weeks closing strictly before the event",
      'g["week_close"] < pd.Timestamp(r.event_day)' in TOOL)
check("2e. the lookahead-prone spike z-score is excluded from every model",
      "population_spike_zscore_reference_only" not in M.BASE_FEATURES + [M.GST_FEATURE]
      and "reference only" in RES["why_not_population_spike_zscore"])

# ---- 3. deduplication ----
s = RES["sample"]
k = SRC.ticker + "|" + SRC.event_day
check("3a. duplicates removed", s["duplicate_rows_removed"] == len(SRC) - k.nunique() == 68)
check("3b. unique identities", s["unique_event_identities"] == 217)
ok = OOS.ticker + "|" + OOS.event_day
check("3c. no duplicated identity in the out-of-sample set", ok.nunique() == len(OOS))
check("3d. accounting ties", s["built"] - s["dropped_incomplete_features"]
      == s["usable_after_feature_completeness"])

# ---- 4. chronological folds ----
check("4a. same folds as PR #23", [f["test_year"] for f in RES["folds"]] == ["2023", "2024", "2025"])
check("4b. training expands", all(RES["folds"][i]["n_train"] < RES["folds"][i + 1]["n_train"]
                                  for i in range(len(RES["folds"]) - 1)))
check("4c. no random splitting", "train_test_split" not in TOOL and "KFold" not in TOOL)
check("4d. scaling fit on the training fold only", "mu, sd = Xtr.mean(0), Xtr.std(0)" in TOOL)
check("4e. out-of-sample rows equal the sum of test folds",
      sum(f["n_test"] for f in RES["folds"] if "n_test" in f) == len(OOS))

# ---- 5. errors and the decisive statistic recompute ----
P = RES["pooled_out_of_sample"]
y = OOS.abs_gap.values
for key, col in (("A_intercept_only", "pred_A"), ("B_baseline_no_gst", "pred_B"),
                 ("C_baseline_plus_gst", "pred_C")):
    mae = 100 * float(np.mean(np.abs(y - OOS[col].values)))
    check(f"5a. {key} MAE recomputes", abs(mae - P[key]["mae_pp"]) < 1e-3, f"{mae}")
check("5b. abs errors recompute",
      bool(np.allclose(np.abs(y - OOS.pred_B.values), OOS.abs_err_B.values, atol=1e-12))
      and bool(np.allclose(np.abs(y - OOS.pred_C.values), OOS.abs_err_C.values, atol=1e-12)))
check("5c. loss difference is B minus C",
      bool(np.allclose(OOS.abs_err_B.values - OOS.abs_err_C.values, OOS.loss_diff.values, atol=1e-12)))
D = RES["decisive_paired_loss_difference"]
check("5d. mean loss difference recomputes",
      abs(100 * float(OOS.loss_diff.mean()) - D["mean_pp"]) < 1e-4)
check("5e. MAE improvement equals the mean paired loss difference",
      abs((P["B_baseline_no_gst"]["mae_pp"] - P["C_baseline_plus_gst"]["mae_pp"]) - D["mean_pp"]) < 1e-3)

# ---- 6. clustered inference ----
C = D["clustered"]
check("6a. CR2 + Satterthwaite, ticker-clustered",
      C["vcov"] == "CR2 (BRL)" and C["cluster_unit"] == "ticker"
      and C["df_method"] == "coefficient-specific Satterthwaite")
check("6b. standard error is finite and positive (the saturated-design trap is avoided)",
      C["cr2_se_pp"] > 0 and np.isfinite(C["cr2_se_pp"]))
check("6c. t == mean/SE", abs(C["t_stat"] - C["mean_loss_difference_pp"] / C["cr2_se_pp"]) < 5e-3)
check("6d. p-value is finite", np.isfinite(C["p_value"]))
check("6e. CI brackets the estimate",
      C["ci95_pp"][0] < C["mean_loss_difference_pp"] < C["ci95_pp"][1])
check("6f. clusters fewer than observations", C["n_clusters"] < C["n"])

# ---- 7. conclusion matches the evidence ----
check("7a. GST does not add predictive value",
      RES["gst_adds_out_of_sample_predictive_value"] is False)
check("7b. conclusion label matches",
      RES["conclusion"] == "GST_DOES_NOT_IMPROVE_MAGNITUDE_FORECAST")
check("7c. the null is not merely underpowered — the CI excludes a large improvement",
      C["ci95_pp"][1] < 0.5)
check("7d. report leads with the answer, not methodology",
      REPORT.index("GST_DOES_NOT_IMPROVE_MAGNITUDE_FORECAST") < REPORT.index("Frozen before fitting"))
check("7e. report discloses the secondary metrics where GST does help",
      "RMSE" in REPORT and "1.261" in REPORT)
# phrases are line-wrapped in the Markdown source, so normalize whitespace
FLAT = " ".join(REPORT.split())
check("7f. report states no trading was evaluated",
      "No directional trading or profitability is evaluated" in FLAT)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("ALL MAGNITUDE FORECAST CHECKS PASSED")
sys.exit(0)
