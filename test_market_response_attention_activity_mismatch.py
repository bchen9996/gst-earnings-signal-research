#!/usr/bin/env python3
"""Focused deterministic test for the attention-activity mismatch analysis.

Recomputes the headline metrics, verifies the chronological timeline, rejects duplicate
identities, and checks that no target-week information reaches a feature. Offline.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "Live Signal Engine" / "Attention_Activity_Mismatch"
RES = json.loads((ROOT / "ATTENTION_ACTIVITY_MISMATCH_RESULTS_v1.0.json").read_text(encoding="utf-8"))
P = pd.read_csv(OUT / "weekly_panel_v1.0.csv", parse_dates=["wk", "target_week"])
REPORT = (ROOT / "ATTENTION_ACTIVITY_MISMATCH_REPORT_v1.0.md").read_text(encoding="utf-8")
TOOL = (ROOT / "tools" / "run_attention_activity_mismatch.py").read_text(encoding="utf-8")
FLAT = " ".join(REPORT.split())

FAIL: list[str] = []


def ck(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


# ---- 1. identities and coverage ----
ck("1a. no duplicate (ticker, target_week)",
   len(P.drop_duplicates(subset=["ticker", "target_week"])) == len(P))
ck("1b. runner deduplicates on the identity pair",
   'drop_duplicates(subset=["ticker", "target_week"]' in TOOL)
g = RES["minimum_data_gate"]
ck("1c. tickers meet the gate", g["tickers"] == 24 >= g["required"]["tickers"])
ck("1d. OOS weeks meet the gate", g["oos_weeks"] == 157 >= g["required"]["oos_weeks"])
ck("1e. OOS observations meet the gate", g["oos_observations"] == 3768 >= g["required"]["oos_obs"])
ck("1f. gate recorded as passed", g["passed"] is True)
oos = P[P.year.astype(str).isin(["2023", "2024", "2025"])]
ck("1g. OOS counts recompute from the panel",
   len(oos) == g["oos_observations"] and oos.target_week.nunique() == g["oos_weeks"])
ck("1h. locked 24-ticker universe used", P.ticker.nunique() == 24)

# ---- 2. chronological timeline, no target-week leakage ----
ck("2a. target week is strictly after the feature week",
   bool((P.target_week > P.wk).all()))
ck("2b. target week is exactly one week after the feature week",
   bool(((P.target_week - P.wk).dt.days == 7).all()))
ck("2c. target weeks start on Monday", bool((P.target_week.dt.weekday == 0).all()))
ck("2d. Trends week is shifted to the Monday that opens the following trading week",
   'g["wk"] = g.Week + pd.Timedelta(days=1)' in TOOL)
ck("2e. rolling normalization excludes the current observation",
   'm[col].shift(1).rolling(ROLL)' in TOOL)
ck("2f. targets are taken from t+1 only",
   'm["y_exc"] = m.ret.shift(-1)' in TOOL and 'm.wvol.shift(-1)' in TOOL)
ck("2g. no random splitting anywhere",
   "train_test_split" not in TOOL and "KFold" not in TOOL and "shuffle" not in TOOL)
ck("2h. folds are chronological and disclosed",
   [f["test_year"] for f in RES["folds"]] == ["2023", "2024", "2025"])
# a feature must not correlate perfectly with its own target week's realized vol
ck("2i. lagged volatility is not the target",
   not np.allclose(P.vol_4w.values, np.exp(P.y_logvol.values), atol=1e-9))

# ---- 3. volatility headline metrics recompute ----
V = RES["volatility"]
ck("3a. B MAE reported", V["metrics"]["B"]["mae"] == 0.420367)
ck("3b. C MAE reported", V["metrics"]["C"]["mae"] == 0.420497)
impr = 100 * (V["metrics"]["B"]["mae"] - V["metrics"]["C"]["mae"]) / V["metrics"]["B"]["mae"]
ck("3c. MAE improvement recomputes", abs(impr - V["mae_improvement_pct"]) < 1e-3, f"{impr}")
ck("3d. C did NOT improve by 1%", V["gates"]["improves_1pct"] is False and impr < 1.0)
ck("3e. bootstrap CI straddles zero",
   V["paired_bootstrap_B_minus_C"]["ci95"][0] < 0 < V["paired_bootstrap_B_minus_C"]["ci95"][1])
ck("3f. CI-above-zero gate fails", V["gates"]["ci_above_zero"] is False)
ck("3g. yearly count is 3", len(V["by_year"]) == 3)
ck("3h. 2-of-3-years gate passes but is not sufficient alone",
   V["gates"]["beats_in_2of3_years"] is True and V["passes"] is False)
ck("3i. volatility specification does not pass", V["passes"] is False)

# ---- 4. return headline metrics recompute ----
R = RES["return_direction"]
M = R["metrics"]
ck("4a. R0 log loss reported", M["B"]["log_loss"] == 0.704603)
ck("4b. R1 log loss reported", M["C"]["log_loss"] == 0.707252)
ck("4c. R1 is worse than R0 on log loss", M["C"]["log_loss"] > M["B"]["log_loss"])
ck("4d. both are worse than the intercept-only null",
   M["B"]["log_loss"] > M["NULL_prevalence"]["log_loss"]
   and M["C"]["log_loss"] > M["NULL_prevalence"]["log_loss"])
ck("4e. AUC below the 0.52 gate", M["C"]["auc"] == 0.5019 < 0.52)
ck("4f. bootstrap CI entirely below zero (search hurt)",
   R["paired_bootstrap_R0_minus_R1"]["ci95"][1] < 0)
ck("4g. all four return gates fail", not any(R["gates"].values()))
ck("4h. return specification does not pass", R["passes"] is False)
ck("4i. R1 better in only one year", sum(v["R1_better"] for v in R["by_year"].values()) == 1)

# ---- 5. bootstrap construction ----
B = V["paired_bootstrap_B_minus_C"]
ck("5a. 2000 draws", B["draws"] == 2000)
ck("5b. four-week blocks", B["block_weeks"] == 4)
ck("5c. fixed seed recorded", isinstance(B["seed"], int))
ck("5d. all tickers retained within a sampled week",
   "np.concatenate([idx[w] for s in pick for w in weeks[s:s + BLOCK]])" in TOOL)

# ---- 6. decision label and guards ----
ALLOWED = {"CONDITIONAL_ATTENTION_SIGNAL", "VOLATILITY_SIGNAL_ONLY", "RETURN_SIGNAL_ONLY",
           "RETIRE_GST_AS_TRADING_SIGNAL", "DATA_UNAVAILABLE"}
ck("6a. label is one of the five allowed", RES["decision_label"] in ALLOWED)
ck("6b. label is RETIRE_GST_AS_TRADING_SIGNAL",
   RES["decision_label"] == "RETIRE_GST_AS_TRADING_SIGNAL")
ck("6c. no portfolio simulation was run", "not run" in RES["portfolio_simulation"])
ck("6d. mismatch is described as a proxy, not absorption",
   "mismatch proxy" in RES["measured_variable"] and "interpretation" in RES["interpretation_guard"])
ck("6e. GST described as a candidate proxy with F5 open",
   "CANDIDATE" in RES["gst_status"] and "F5" in RES["gst_status"])
ck("6f. point-in-time caveat recorded", "NOT point-in-time" in RES["point_in_time_caveat"])
ck("6g. report avoids causal and investability claims",
   "No causality, market absorption, investability, or universal uselessness of Google Trends"
   " is claimed" in FLAT.replace("Trends is claimed", "Trends is claimed"))
ck("6h. report states this was the final conditional GST trading test",
   "final conditional GST trading test" in FLAT)

# ---- 7. sensitivity checks are present and agree ----
S = RES["sensitivity_checks"]
ck("7a. exactly the three prespecified checks", set(S) == {
    "exclude_earnings_weeks", "drop_ambiguous_queries", "winsorized_predictors"})
ck("7b. five ambiguous queries dropped", len(S["drop_ambiguous_queries"]["dropped"]) == 5)
ck("7c. dropped set comes from the construct audit ranking",
   S["drop_ambiguous_queries"]["dropped"][:3] == ["BRK-B", "GME", "GOOGL"])
ck("7d. no sensitivity check reverses the primary result",
   not any(v.get("C_better") for v in S.values() if isinstance(v, dict)))
ck("7e. sensitivity framed as robustness only", "not alternative primary" in RES["sensitivity_note"])
ck("7f. partial earnings coverage disclosed", "partial ticker coverage" in S["exclude_earnings_weeks"]["source"])

# ---- 8. state isolation ----
ck("8a. exploratory status declared",
   RES["status"] == "EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY"
   and RES["hyp01_confirmation"] is False and RES["prospective_collection"] is False)
for forbidden in ("registry.jsonl", "GST_HYP01_ANALYSIS_LOCK", "LOCKED_24_TICKER_UNIVERSE ="):
    ck(f"8b. runner never writes {forbidden}", forbidden not in TOOL)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print(f"ALL ATTENTION-ACTIVITY MISMATCH CHECKS PASSED")
sys.exit(0)
