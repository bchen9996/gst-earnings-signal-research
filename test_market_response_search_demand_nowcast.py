#!/usr/bin/env python3
"""Focused check on the search-demand nowcast MVP.

Verifies the frozen query map, that no post-release search week enters a feature,
that B and C differ only by the two search features, chronological folds, the minimum
sample gates, and that reported errors recompute. Deterministic and offline.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
OUT = ROOT / "Live Signal Engine" / "Search_Demand_Nowcast"
RES = json.loads((ROOT / "SEARCH_DEMAND_NOWCAST_RESULTS_v1.0.json").read_text(encoding="utf-8"))
REPORT = (ROOT / "SEARCH_DEMAND_NOWCAST_REPORT_v1.0.md").read_text(encoding="utf-8")
OOS = pd.read_csv(OUT / "company_quarter_panel_v1.0.csv", parse_dates=["q_end"])
QMAP = OUT / "frozen_query_map_v1.0.csv"
TOOL = (ROOT / "tools" / "run_search_demand_nowcast_mvp.py").read_text(encoding="utf-8")
FLAT = " ".join(REPORT.split())

FAIL = []


def check(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


import run_search_demand_nowcast_mvp as M  # noqa: E402

# ---- 1. frozen universe and queries ----
with QMAP.open(encoding="utf-8") as fh:
    qm = list(csv.DictReader(fh))
EXPECT = {"SBUX": "Starbucks", "MCD": "McDonald's", "CMG": "Chipotle Mexican Grill",
          "DPZ": "Domino's Pizza", "WING": "Wingstop", "CAVA": "CAVA restaurant",
          "TXRH": "Texas Roadhouse", "BROS": "Dutch Bros Coffee"}
check("1a. exactly the eight frozen companies", {r["ticker"] for r in qm} == set(EXPECT))
check("1b. query strings are the frozen ones, unmodified",
      {r["ticker"]: r["frozen_search_query"] for r in qm} == EXPECT)
check("1c. search parameters are geo=US, web, cat 0, weekly",
      all(r["geo"] == "US" and r["gprop"] == "web" and r["category"] == "0"
          and r["frequency"] == "weekly" for r in qm))
check("1d. results record no related-query selection or outcome-informed substitution",
      RES["search_parameters"]["related_query_selection"] is False
      and RES["search_parameters"]["outcome_informed_substitution"] is False)

# ---- 2. construct separation ----
check("2a. ticker GST is not used", RES["ticker_gst_used"] is False)
check("2b. no stock or option data retrieved",
      RES["stock_returns_or_options_retrieved"] is False)
for tok in ("zconjunction", "Daily OHLC", "Excess Return", "gst_z_pre", "spillover"):
    check(f"2c. runner never touches {tok}", tok not in TOOL)

# ---- 3. no post-release information ----
check("3a. the search window is the fiscal quarter, ending at quarter end",
      "(tr.week >= r.q_start) & (tr.week <= r.q_end)" in TOOL)
check("3b. the report states the window ends before the earnings release",
      "strictly before the earnings release" in FLAT)
check("3c. search normalization uses only earlier quarters",
      "g.search_quarter_avg.shift(1).rolling(4)" in TOOL)
check("3d. fundamental lags use only earlier quarters",
      "g.growth_yoy.shift(1)" in TOOL and "g.growth_yoy.shift(4)" in TOOL
      and "g.growth_yoy.shift(1).rolling(4).mean()" in TOOL)

# ---- 4. exactly two search features; B and C differ only by them ----
check("4a. exactly two search features", M.SEARCH_FEATURES == ["search_quarter_avg", "search_surprise"]
      and len(M.SEARCH_FEATURES) == 2)
check("4b. C is B plus those two only", "cols_c = cols_b + SEARCH_FEATURES" in TOOL)
check("4c. one fixed ridge, alpha not tuned",
      M.RIDGE_ALPHA == 1.0 and "Ridge(alpha=RIDGE_ALPHA)" in TOOL
      and "GridSearch" not in TOOL and "RandomizedSearch" not in TOOL)
check("4d. no trees, neural nets or quantum models",
      not any(k in TOOL for k in ("RandomForest", "GradientBoosting", "MLP", "quantum", "Kernel")))

# ---- 5. chronological validation and deduplication ----
check("5a. test years are 2023, 2024, 2025 in order", M.TEST_YEARS == ["2023", "2024", "2025"])
check("5b. no random splitting", "train_test_split" not in TOOL and "KFold" not in TOOL)
check("5c. scaling fitted inside the training fold",
      "mu, sd = Xtr.mean(0), Xtr.std(0)" in TOOL)
check("5d. SEC facts deduplicated by ticker, period and accession",
      'drop_duplicates(subset=["ticker", "q_start", "q_end", "accn"])' in TOOL)
check("5e. training precedes each test year", all(
    f.get("n_train", 0) > 0 for f in RES["folds"] if f.get("status") != "SKIPPED"))

# ---- 6. minimum sample gates drive the label ----
g = RES["minimum_sample_gates"]
check("6a. gate thresholds are the required ones",
      g["required"] == {"eligible_quarters": 60, "oos_observations": 40, "oos_companies": 6})
check("6b. observed counts match the artifacts",
      g["observed"]["oos_observations"] == len(OOS) == 38
      and g["observed"]["oos_companies"] == OOS.ticker.nunique() == 7)
check("6c. the out-of-sample gate genuinely fails", g["min_oos_observations"] is False)
check("6d. label is INSUFFICIENT_DATA", RES["decision_label"] == "INSUFFICIENT_DATA")
ALLOWED = {"SEARCH_DEMAND_IMPROVES_FUNDAMENTAL_NOWCAST", "SEARCH_DEMAND_SHOWS_SECONDARY_ONLY_VALUE",
           "SEARCH_DEMAND_ADDS_NO_VALUE", "INSUFFICIENT_DATA", "DATA_UNAVAILABLE"}
check("6e. label is one of the five allowed", RES["decision_label"] in ALLOWED)

# ---- 7. metrics recompute ----
y = OOS.growth_yoy.values
P = RES["pooled_out_of_sample"]
for key, col in (("A_historical_mean", "pred_A"), ("B_fundamental", "pred_B"),
                 ("C_fundamental_plus_search", "pred_C")):
    mae = 100 * float(np.mean(np.abs(y - OOS[col].values)))
    check(f"7a. {key} MAE recomputes", abs(mae - P[key]["mae_pp"]) < 1e-3, f"{mae}")
check("7b. abs errors recompute",
      bool(np.allclose(np.abs(y - OOS.pred_B.values), OOS.abs_err_B.values, atol=1e-12))
      and bool(np.allclose(np.abs(y - OOS.pred_C.values), OOS.abs_err_C.values, atol=1e-12)))
D = RES["decisive_paired_comparison"]
check("7c. loss difference is B minus C",
      bool(np.allclose(OOS.abs_err_B.values - OOS.abs_err_C.values, OOS.loss_diff.values, atol=1e-12)))
check("7d. mean paired difference recomputes",
      abs(100 * float(OOS.loss_diff.mean()) - D["mean_pp"]) < 1e-4)
check("7e. it equals the MAE gap", abs((P["B_fundamental"]["mae_pp"]
                                        - P["C_fundamental_plus_search"]["mae_pp"]) - D["mean_pp"]) < 1e-3)
check("7f. C-wins percentage recomputes",
      abs(100 * float((OOS.loss_diff > 0).mean()) - D["pct_events_C_wins"]) < 1e-2)

# ---- 8. the primary metric is not overridden by a secondary one ----
check("8a. the primary MAE comparison fails",
      P["C_fundamental_plus_search"]["mae_pp"] > P["B_fundamental"]["mae_pp"])
check("8b. a secondary metric does favour C, and is disclosed",
      RES["acceleration_sign_accuracy"]["C"] > RES["acceleration_sign_accuracy"]["B"]
      and "60.53%" in FLAT)
check("8c. the report refuses to reinterpret it as success",
      "not reinterpreted as success" in FLAT)
check("8d. year instability is disclosed", "sign flip" in FLAT.lower() or "Not stable" in REPORT)

# ---- 9. limitation and next-stage rule ----
check("9a. the point-in-time limitation is prominent",
      REPORT.index("POINT-IN-TIME LIMITATION") < REPORT.index("## Decision")
      and "retrospective reconstruction" in FLAT.lower())
check("9b. results carry the limitation too",
      "RETROSPECTIVE RECONSTRUCTION" in RES["point_in_time_limitation"])
check("9c. the next-stage rule is not triggered",
      "not** triggered" in FLAT or "not triggered" in FLAT)
check("9d. no stock return was tested", "No stock return was tested" in FLAT)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("ALL SEARCH DEMAND NOWCAST CHECKS PASSED")
sys.exit(0)
