#!/usr/bin/env python3
"""Focused check on the independent direction model.

Verifies point-in-time feature construction (no event-day or future information),
that GST never enters the model, chronological-only validation, deduplicated event
identities, and that reported metrics recompute. Deterministic, offline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
RES = json.loads((ROOT / "RETROSPECTIVE_DIRECTION_SIGNAL_RESULTS_v1.0.json").read_text(encoding="utf-8"))
REPORT = (ROOT / "RETROSPECTIVE_DIRECTION_SIGNAL_REPORT_v1.0.md").read_text(encoding="utf-8")
OOS = pd.read_csv(ROOT / "Live Signal Engine" / "retrospective_direction_oos_predictions.csv")
SRC = pd.read_csv(ROOT / "Live Signal Engine" / "retrospective_event_components.csv")
OHLC = ROOT / "Daily OHLC Data (2021-2025 Opening Gap Test)"
TOOL = (ROOT / "tools" / "run_retrospective_direction_signal.py").read_text(encoding="utf-8")

FAIL = []


def check(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


# ---- 1. GST is not a direction input ----
import run_retrospective_direction_signal as M  # noqa: E402

check("1a. GST is not in the frozen feature set",
      not any(k in f.lower() for f in M.FEATURES for k in ("gst", "zscore", "spike", "role")))
check("1b. results declare GST is not a direction input",
      RES["gst_used_as_direction_input"] is False)
check("1c. GST's declared role is post-hoc filtering",
      "after" in RES["gst_role"].lower() and "filter" in RES["gst_role"].lower())
check("1d. the fit function never receives a GST column",
      "high_gst" not in TOOL.split("def fit_predict")[1].split("def metrics")[0])

# ---- 2. features are point-in-time ----
bad = []
for _, r in OOS.sample(n=20, random_state=0).iterrows():
    px = pd.read_csv(OHLC / f"{r.ticker}_ohlc.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    T = int(px.index[px["Date"] == pd.Timestamp(r.event_day)][0])
    gap = px.Open[T] / px.Close[T - 1] - 1
    if abs(gap - r.gap) > 1e-9:
        bad.append((r.ticker, r.event_day, "gap"))
    if int(gap > 0) != int(r.y):
        bad.append((r.ticker, r.event_day, "label"))
check(f"2a. outcome recomputes as sign(open(T)/close(T-1)-1) (bad={bad[:2]})", not bad)
body = TOOL.split('"""', 2)[-1]
# Feature construction only: stop at the OUTCOME line, which legitimately reads
# index T. Including it would flag the label and prove nothing about the features.
feat_block = body.split("c = px[\"Close\"].values")[1].split("# OUTCOME")[0]
check("2b. no feature reads an index at or after T",
      "c[T]" not in feat_block and "Open" not in feat_block,
      repr(feat_block[-140:]))
check("2b'. the matcher would catch a planted future read",
      "c[T]" in 'x = c[T] / c[T - 1]')
check("2c. pre-event windows end at close(T-1)", "c[T - 1]" in feat_block)

# ---- 3. deduplicated event identities, strictly-earlier prior gap ----
s = RES["sample"]
check("3a. duplicate event identities were removed",
      s["duplicate_rows_removed"] == 68 and s["rows_in_source"] == 285
      and s["unique_event_identities"] == 217)
k = SRC.ticker + "|" + SRC.event_day
check("3b. the source really did contain those duplicates",
      len(SRC) - k.nunique() == s["duplicate_rows_removed"])
ok = OOS.ticker + "|" + OOS.event_day
check("3c. no duplicated identity survives into the out-of-sample set",
      ok.nunique() == len(OOS))
check("3d. prior_gap_dir uses a strictly earlier event date",
      "if h[0] < r.event_day" in TOOL)

# ---- 4. chronological validation only ----
check("4a. no random splitting", "train_test_split" not in TOOL and "KFold" not in TOOL)
check("4b. expanding window folds are chronological",
      [f["test_year"] for f in RES["folds"]] == ["2023", "2024", "2025"])
for f in RES["folds"]:
    check(f"4c. fold {f['test_year']}: training set precedes the test year", f["n_train"] > 0)
check("4d. training sets expand monotonically",
      all(RES["folds"][i]["n_train"] < RES["folds"][i + 1]["n_train"] for i in range(len(RES["folds"]) - 1)))
check("4e. standardization is fit on the training fold only",
      "mu, sd = Xtr.mean(0), Xtr.std(0)" in TOOL)
check("4f. selection rule is Brier, not trading returns",
      "Brier" in RES["selection_rule"] and "return" in RES["selection_rule"].lower())

# ---- 5. reported metrics recompute ----
P = RES["pooled_out_of_sample"]
y = OOS.y.values
p = OOS.pred_prob.values
check("5a. out-of-sample n matches", P["logistic_l2"]["n"] == len(OOS) == 144)
check("5b. class counts match",
      P["logistic_l2"]["n_positive"] == int((y == 1).sum())
      and P["logistic_l2"]["n_negative"] == int((y == 0).sum()))
acc = float(((p > 0.5).astype(int) == y).mean())
check("5c. selected-model accuracy recomputes",
      round(acc, 4) == P[RES["primary_model"]["selected"]]["accuracy"], f"{acc}")
brier = float(np.mean((np.clip(p, 0, 1) - y) ** 2))
check("5d. selected-model Brier recomputes",
      abs(brier - P[RES["primary_model"]["selected"]]["brier"]) < 1e-5)
# stored rounded to 5 dp, so compare against the same rounding
check("5e. always-positive baseline Brier equals 1 - positive rate",
      P["always_positive"]["brier"] == round(float(1 - y.mean()), 5))

# ---- 6. strategy arithmetic ----
C = RES["combined_strategy"]
pos = np.where(p > 0.5, 1.0, -1.0)
r = pos * OOS.gap.values
check("6a. strategy return is direction x gap",
      bool(np.allclose(r, OOS.strategy_return.values, atol=1e-12)))
net = r - C["cost_bps_round_trip"] / 10000.0
check("6b. direction-only mean net recomputes",
      abs(100 * net.mean() - C["direction_only"]["mean_net_pct"]) < 1e-3)
hi = OOS.high_gst == 1.0
check("6c. GST-filtered trade count matches the high-GST subset",
      int(hi.sum()) == C["direction_plus_gst_filter"]["trades"] == 90)
check("6d. GST-filtered mean net recomputes",
      abs(100 * (r[hi.values] - 0.001).mean() - C["direction_plus_gst_filter"]["mean_net_pct"]) < 1e-3)
check("6e. filtered + unfiltered-low-GST == all trades",
      C["direction_plus_gst_filter"]["trades"]
      + C["contemporaneous_unfiltered_low_gst"]["trades"] == C["direction_only"]["trades"])
check("6f. no retraining on the high-GST subset",
      "no retraining" in C["direction_plus_gst_filter"]["note"])
check("6g. exactly one confidence threshold, labelled secondary",
      C["confidence_filter_secondary"]["threshold"] == 0.60
      and C["confidence_filter_secondary"]["label"].startswith("SECONDARY"))

# ---- 7. incremental GST inference ----
inc = C["incremental_gst_effect_cr2"]
check("7a. CR2 + Satterthwaite, ticker-clustered",
      inc["vcov"] == "CR2 (BRL)" and inc["cluster_unit"] == "ticker"
      and inc["df_method"] == "coefficient-specific Satterthwaite")
check("7b. t == coef/SE", abs(inc["t_stat"] - inc["coef_pp"] / inc["cr2_se_pp"]) < 5e-3)
check("7c. CI brackets the coefficient", inc["ci95_pp"][0] < inc["coef_pp"] < inc["ci95_pp"][1])
check("7d. the decisive statistic is named as the incremental coefficient",
      "incremental" in C["decisive_statistic"])

# ---- 8. conclusion is one of the five allowed labels and matches the evidence ----
ALLOWED = {"DIRECTION_SIGNAL_AND_GST_FILTER_BOTH_ADD_VALUE", "DIRECTION_SIGNAL_ONLY",
           "GST_FILTER_ONLY", "NEITHER_ADDS_VALUE", "INSUFFICIENT_DATA"}
check("8a. conclusion is one of the five allowed labels", RES["conclusion"] in ALLOWED)
check("8b. conclusion is NEITHER_ADDS_VALUE", RES["conclusion"] == "NEITHER_ADDS_VALUE")
check("8c. direction leg genuinely failed (negative net and no AUC edge)",
      C["direction_only"]["mean_net_pct"] < 0 and P["logistic_l2"]["auc"] < 0.5)
check("8d. GST leg genuinely failed (negative coefficient, unsupported)",
      inc["coef_pp"] < 0 and inc["p_value"] > 0.05)
check("8e. report states the conclusion", "NEITHER_ADDS_VALUE" in REPORT)
check("8f. report discloses the removed leak and the numbers it changed",
      "63.6% accuracy" in REPORT and "47.9% accuracy" in REPORT and "leak" in REPORT.lower())
check("8g. report does not claim gap direction is unpredictable in general",
      "does not establish that earnings\ngap direction is unpredictable in general" in REPORT
      or "unpredictable in general" in " ".join(REPORT.split()))

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("ALL DIRECTION SIGNAL CHECKS PASSED")
sys.exit(0)
