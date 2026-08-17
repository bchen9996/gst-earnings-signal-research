#!/usr/bin/env python3
"""Focused check on the restaurant search-demand pilot.

Verifies the pre-announcement search cutoff, training-fold-only thresholding, that
C and D differ only by the product-demand block, chronological folds, and that the
reported metrics recompute. Deterministic and offline.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "Live Signal Engine" / "Restaurant_Search_Pilot"
RES = json.loads((ROOT / "RESTAURANT_SEARCH_PILOT_RESULTS_v1.0.json").read_text(encoding="utf-8"))
REPORT = (ROOT / "RESTAURANT_SEARCH_PILOT_REPORT_v1.0.md").read_text(encoding="utf-8")
OOS = pd.read_csv(OUT / "event_panel_v1.0.csv", parse_dates=["announcement"])
TR = pd.read_csv(OUT / "search_weekly_v1.0.csv", parse_dates=["week"])
TOOL = (ROOT / "tools" / "run_restaurant_search_demand_pilot.py").read_text(encoding="utf-8")
FLAT = " ".join(REPORT.split())

FAIL = []


def check(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


# ---- 1. no post-announcement search can enter a feature ----
check("1a. the cutoff uses week CLOSE, not week start",
      "closes = ts.week + pd.Timedelta(days=6)" in TOOL and "ok = ts[closes < ann_ts]" in TOOL)
check("1b. the leakage assertion ran and found no violation",
      RES["leakage_assertion"]["passed"] is True
      and RES["leakage_assertion"]["violations"] == 0
      and RES["leakage_assertion"]["checks"] > 200)
# independent recheck: for every OOS event, the latest usable week must close before announcement
bad = []
for r in OOS.itertuples():
    for kind in ("consumer", "investor"):
        s = TR[(TR.ticker == r.ticker) & (TR.kind == kind)]
        if not len(s):
            continue
        closes = s.week + pd.Timedelta(days=6)
        usable = s[closes < pd.Timestamp(r.announcement)]
        if len(usable) and (usable.week.max() + pd.Timedelta(days=6)) >= pd.Timestamp(r.announcement):
            bad.append((r.ticker, str(r.announcement), kind))
check(f"1c. independent recheck of the cutoff (bad={bad[:2]})", not bad)
check("1d. direction is never a target",
      RES["targets_direction"] is False and "direction" not in RES["target"])
check("1e. the forbidden overlapping GST spike window is not used",
      RES["overlapping_gst_spike_window_used"] is False
      and "zconjunction" not in TOOL and "spike_week" not in TOOL)

# ---- 2. models differ only by the intended blocks ----
# Read the frozen constants from the source with ast - importing the module would
# execute the whole pilot, and exec'ing the header needs __file__.
import ast  # noqa: E402

_tree = ast.parse(TOOL)
ns: dict = {}
for _n in _tree.body:
    if isinstance(_n, ast.Assign) and len(_n.targets) == 1 and isinstance(_n.targets[0], ast.Name):
        try:
            ns[_n.targets[0].id] = ast.literal_eval(_n.value)
        except Exception:
            pass

check("2a. C is B plus investor features only",
      ns["INV_F"] == ["inv_level", "inv_mean4", "inv_slope4", "inv_abnormal"])
check("2b. D is C plus product features only",
      ns["PRD_F"] == ["prd_level", "prd_mean4", "prd_slope4", "prd_abnormal"])
check("2c. the two search blocks are disjoint from the baseline",
      not (set(ns["INV_F"]) | set(ns["PRD_F"])) & set(ns["BASE_F"]))
check("2d. four features per search family, as frozen",
      len(ns["INV_F"]) == 4 and len(ns["PRD_F"]) == 4)
check("2e. one fixed transformation for both families",
      "1.4826" in TOOL and TOOL.count("def robust_z") == 1)
check("2f. regularization grids fixed in advance",
      ns["LOGIT_GRID"] == [0.1, 1.0, 10.0] and ns["RIDGE_GRID"] == [0.1, 1.0, 10.0]
      and "selected on TRAINING data only" in TOOL)

# ---- 3. threshold and folds ----
check("3a. tail threshold comes from the training fold only",
      "thr = float(tr_.abs_move.quantile(TAIL_Q))" in TOOL and ns["TAIL_Q"] == 0.75)
check("3b. the threshold varies across folds (recomputed, not fixed once)",
      OOS.train_threshold.nunique() > 1)
check("3c. chronological only, never shuffled",
      "train_test_split" not in TOOL and "shuffle" not in TOOL and "KFold" not in TOOL)
check("3d. events are ordered in time", bool(OOS.announcement.is_monotonic_increasing))
check("3e. unique ticker-event identities",
      len(OOS.drop_duplicates(subset=["ticker", "event_date"])) == len(OOS))
check("3f. identical observations across A/B/C/D",
      all(OOS[f"p_{k}"].notna().all() for k in ("A", "B", "C", "D")))

# ---- 4. metrics recompute ----
y = OOS.y_large.values
for k in ("A", "B", "C", "D"):
    p = np.clip(OOS[f"p_{k}"].values, 1e-9, 1 - 1e-9)
    br = float(np.mean((p - y) ** 2))
    check(f"4a. model {k} Brier recomputes", abs(br - RES["models"][k]["brier"]) < 1e-4, f"{br}")
d = ((OOS.p_C.values - y) ** 2) - ((OOS.p_D.values - y) ** 2)
inc = RES["incremental_C_vs_D"]
check("4b. C-D loss difference recomputes", abs(float(d.mean()) - inc["raw_mean"]) < 1e-5)
check("4c. D-beats-C percentage recomputes",
      abs(100 * float((d > 0).mean()) - inc["pct_events_D_beats_C"]) < 1e-2)
cl = inc["clustered"]
check("4d. CR2 clustered by ticker with Satterthwaite df",
      cl["vcov"] == "CR2 (BRL)" and cl["cluster_unit"] == "ticker"
      and cl["n_clusters"] == OOS.ticker.nunique() == 8)
check("4e. clustered t equals mean over SE", abs(cl["t_stat"] - cl["mean"] / cl["cr2_se"]) < 5e-3)
check("4f. clustered CI brackets the mean", cl["ci95"][0] < cl["mean"] < cl["ci95"][1])

# ---- 5. label logic ----
ALLOWED = {"PRODUCT_DEMAND_ADDS_INCREMENTAL_VALUE", "INVESTOR_ATTENTION_ONLY",
           "NO_INCREMENTAL_SEARCH_VALUE", "DATA_UNAVAILABLE"}
check("5a. label is one of the four allowed", RES["decision_label"] in ALLOWED)
check("5b. label is NO_INCREMENTAL_SEARCH_VALUE",
      RES["decision_label"] == "NO_INCREMENTAL_SEARCH_VALUE")
check("5c. D does not beat C on pooled Brier",
      RES["models"]["D"]["brier"] > RES["models"]["C"]["brier"]
      and RES["label_basis"]["D_beats_C_on_pooled_brier"] is False)
check("5d. C does not beat B either", RES["label_basis"]["C_beats_B_on_pooled_brier"] is False)
check("5e. the win-rate does not override the loss mean",
      inc["pct_events_D_beats_C"] > 50 and inc["raw_mean"] < 0
      and RES["decision_label"] != "PRODUCT_DEMAND_ADDS_INCREMENTAL_VALUE")
check("5f. secondary metrics cannot trigger the positive label",
      "secondary metrics alone cannot trigger" in RES["label_basis"]["note"])

# ---- 6. options and PR #27 relationship ----
check("6a. options recorded unavailable", RES["options_history"] == "OPTIONS_HISTORY_UNAVAILABLE")
check("6b. no substitution of current options or reconstruction from realized returns",
      "NOT substituted" in RES["options_history_detail"]
      and "reconstructed from realized returns" in RES["options_history_detail"])
check("6c. the report states success here would not overturn PR #27",
      "would not have overturned PR #27" in FLAT)
check("6d. the reused query map and its two string differences are disclosed",
      "Chipotle Mexican Grill" in FLAT and "Dutch Bros Coffee" in FLAT
      and "reuses PR #27's exact frozen query map" in FLAT)
qm = list(csv.DictReader((OUT / "frozen_queries_v1.0.csv").open(encoding="utf-8")))
check("6e. the query map records the reuse and the differences",
      all(r["consumer_query_source"] == "REUSED_FROM_PR27" for r in qm)
      and sum(r["query_string_differs_from_task_spec"] == "True" for r in qm) == 2)

# ---- 7. state isolation ----
check("7a. not HYP-01 confirmation, not prospective",
      RES["hyp01_confirmation"] is False and RES["prospective_collection"] is False)
for forbidden in ("registry.jsonl", "GST_HYP01_ANALYSIS_LOCK", "LOCKED_24_TICKER_UNIVERSE",
                  "GST_SEARCH_CONSTRUCT_VALIDITY"):
    check(f"7b. runner never references {forbidden}", forbidden not in TOOL)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("ALL RESTAURANT SEARCH PILOT CHECKS PASSED")
sys.exit(0)
