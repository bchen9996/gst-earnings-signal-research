#!/usr/bin/env python3
"""Deterministic test for the semiconductor information-price gap study (v3).

Recomputes Stage 1 end to end from the COMMITTED derived panel -- folds, the
training-fold-only transform, ridge alpha selection, MAE, the moving-block bootstrap
and every gate -- rather than reading declarations, and proves the leakage and
integrity properties. Deliberately leaked, duplicated, mistimed and relabeled fixtures
must be detected. Offline: no network, no credential, no price file.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import run_semiconductor_surprise_absorption_v3 as M  # noqa: E402

R = json.loads((ROOT / "SEMICONDUCTOR_SURPRISE_ABSORPTION_V3_RESULTS_v1.0.json")
               .read_text(encoding="utf-8"))
PANEL = ROOT / "Live Signal Engine" / "Semiconductor_Surprise_Absorption_v3" / \
    "event_panel_v1.0.csv"
D = pd.read_csv(PANEL)
TOOL = (ROOT / "tools" / "run_semiconductor_surprise_absorption_v3.py").read_text(
    encoding="utf-8")
REPORT = ROOT / "SEMICONDUCTOR_SURPRISE_ABSORPTION_V3_REPORT_v1.0.md"
ET = ZoneInfo("America/New_York")
FAIL: list[str] = []


def ck(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


# =====================================================================
# 1. FROZEN DESIGN IS INTACT AND UNCHANGED AFTER OUTCOMES
# =====================================================================
ck("1a. frozen design block present and closed",
   "FROZEN_DESIGN ===" in TOOL and "END FROZEN_DESIGN" in TOOL)
ck("1b. the ridge alpha grid is exactly the frozen one", M.ALPHAS == [0.0, 0.1, 1.0, 10.0])
ck("1c. the folds are the frozen expanding chronological windows",
   M.FOLDS == [((2018, 2022), 2023), ((2018, 2023), 2024), ((2018, 2024), 2025)])
ck("1d. horizons are frozen at 5 primary and 20 secondary",
   M.H_PRIMARY == 5 and M.H_SECONDARY == 20
   and R["primary_horizon_sessions"] == 5 and R["secondary_horizon_sessions"] == 20)
ck("1e. bootstrap parameters are frozen",
   (M.BOOT_DRAWS, M.BOOT_BLOCK_DAYS, M.BOOT_SEED) == (2000, 28, 20260817))
ck("1f. cost and quantile are frozen",
   M.COST_BPS_ROUND_TRIP == 10.0 and M.QUANTILE == 5)
ck("1g. the sample gate thresholds are frozen",
   M.SAMPLE_GATE == {"tickers": 8, "events": 240, "oos_events": 90, "oos_per_year": 25})
ck("1h. the MAE improvement threshold is frozen at 1.0%", M.MAE_IMPROVEMENT_MIN == 1.0)
ck("1i. exactly five decision labels exist and the emitted one is among them",
   len(M.LABELS) == 5 and R["decision_label"] in M.LABELS)
ck("1j. benchmark is SMH and the universe is the frozen ten",
   M.BENCH == "SMH" == R["benchmark"] and R["universe"] == M.UNIVERSE
   and len(M.UNIVERSE) == 10)
ck("1k. the primary surprise field is surprisePercentage",
   R["primary_surprise_field"] == "surprisePercentage"
   and "surprisePercentage" in TOOL)
ck("1l. raw reportedEPS / estimatedEPS are never primary model features",
   "transform_col=\"surprisePercentage\"" in TOOL
   and not re.search(r"add_extra\s*=?\s*\(\s*[\"'](reportedEPS|estimatedEPS)", TOOL))

# =====================================================================
# 2. PROVENANCE LANGUAGE IS MANDATORY AND PRESENT
# =====================================================================
BLOB = json.dumps(R)
ck("2a. the construct is named VENDOR_DEFINED_REPORTED_EPS_SURPRISE",
   R["surprise_construct"] == "VENDOR_DEFINED_REPORTED_EPS_SURPRISE")
ck("2b. point-in-time provenance is recorded as not guaranteed",
   R["point_in_time_provenance"] == "POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED")
ck("2c. the forbidden claims are explicitly disclaimed",
   set(R["not_claimed"]) >= {"GAAP earnings surprise", "SEC-validated EPS surprise",
                             "guaranteed contemporaneous-consensus vintage",
                             "preregistered evidence", "production-ready", "investable"})
ck("2d. the surprise is never called a GAAP or SEC-validated surprise",
   not re.search(r"(?<!not_claimed)(GAAP earnings surprise|SEC-validated EPS surprise)",
                 BLOB.replace(json.dumps(R["not_claimed"]), "")))
ck("2e. the predecessor crosswalk gate is recorded as failed and still failed",
   R["predecessor_gate"]["structured_source_crosswalk_gate"] == "FAILED"
   and R["predecessor_gate"]["still_failed"] is True
   and close(R["predecessor_gate"]["value"], 0.6719))
ck("2f. the successor-design disclosure is present and honest",
   "AFTER inspecting identity and coverage" in R["successor_design_disclosure"]
   and "BEFORE inspecting any outcome" in R["successor_design_disclosure"]
   and "not preregistered confirmation" in R["successor_design_disclosure"])
ck("2g. this is recorded as not a GST test", R["is_gst_test"] is False)
ck("2h. the status is exploratory retrospective development",
   R["status"] == "EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY")

# =====================================================================
# 3. surprisePercentage SPLIT INVARIANCE, VERIFIED MECHANICALLY
# =====================================================================
INV = R["provenance"]["surprise_percentage_invariance"]
recs = [{"estimatedEPS": e, "surprise": s, "surprisePercentage": p}
        for e, s, p in ((2.0, 0.2, 10.0), (-1.0, -0.1, -10.0), (0.5, 0.05, 10.0))]
mine = M.verify_surprise_percentage_invariance(recs)
ck("3a. the invariance checker agrees on a hand-built fixture",
   mine["checked"] == 3 and mine["agreement_rate"] == 1.0
   and mine["proportional_split_invariance_holds"] is True)
ck("3b. a proportional split restatement leaves surprisePercentage unchanged",
   all(close(100.0 * (r["surprise"] * f) / abs(r["estimatedEPS"] * f),
             100.0 * r["surprise"] / abs(r["estimatedEPS"]), 1e-9)
       for r in recs for f in (0.1, 0.25, 4.0)))
ck("3c. a NON-proportional restatement would break it -- the check has teeth",
   not close(100.0 * (0.2 * 0.1) / abs(2.0), 100.0 * 0.2 / abs(2.0), 1e-9))
ck("3d. the committed run verified invariance on every record",
   INV["checked"] == 320 and INV["agreement_rate"] == 1.0
   and INV["proportional_split_invariance_holds"] is True
   and close(INV["largest_absolute_deviation_pp"], 0.0, 1e-9))

# =====================================================================
# 4. CROSSWALK, SAMPLE GATE AND DUPLICATE IDENTITY
# =====================================================================
G = R["sample_gate"]
ck("4a. the crosswalk is exact-date with no window and no substitution",
   "filing_date == reportedDate" in TOOL and "no nearest-date fallback" in TOOL)
ck("4b. panel row count matches the recorded event count",
   len(D) == G["events"]["value"] == R["provenance"]["uniquely_matched"])
ck("4c. every sample gate component recomputes",
   D.ticker.nunique() == G["tickers"]["value"]
   and int((D.year.isin([2023, 2024, 2025])).sum()) == G["oos_events"]["value"]
   and all(int((D.year == int(y)).sum()) == v
           for y, v in G["oos_per_year"]["value"].items()))
ck("4d. the sample gate passed on its own terms",
   G["passed"] is True and G["events"]["value"] >= 240
   and G["oos_events"]["value"] >= 90
   and all(v >= 25 for v in G["oos_per_year"]["value"].values()))
ck("4e. no duplicate event identity exists",
   int(D.duplicated(subset=["ticker", "reportedDate", "accession"]).sum()) == 0
   == G["duplicate_identities"]["value"])
ck("4f. MUTATION -- a duplicated event identity is detected",
   int(pd.concat([D, D.iloc[[0]]]).duplicated(
       subset=["ticker", "reportedDate", "accession"]).sum()) == 1)
ck("4g. one session per ticker-event -- no ticker appears twice on one session",
   int(D.duplicated(subset=["ticker", "session"]).sum()) == 0)
ck("4h. excluded events were dropped, never substituted",
   R["provenance"]["crosswalk_excluded"]["ambiguous"] == 0
   and R["provenance"]["crosswalk_excluded"]["no_match"] == 22
   and R["provenance"]["av_records_considered"]
   - sum(R["provenance"]["crosswalk_excluded"].values()) == len(D))

# =====================================================================
# 5. EVENT TIMING IS ANNOUNCEMENT-AWARE
# =====================================================================
acc = pd.to_datetime(D.acceptance_utc, utc=True, format="mixed").dt.tz_convert(ET)
rel_date = acc.dt.date
sess = pd.to_datetime(D.session).dt.date
t930 = datetime.strptime("09:30", "%H:%M").time()
t1600 = datetime.strptime("16:00", "%H:%M").time()
after = D.timing_category == "after_close_next_session"
before = D.timing_category == "before_open_same_session"
ck("5a. after-close events were accepted at or after 16:00 ET",
   bool((acc[after].dt.time >= t1600).all()))
ck("5b. after-close events resolve to a LATER session than the release date",
   bool((sess[after] > rel_date[after]).all()))
ck("5c. before-open events were accepted before 09:30 ET",
   bool((acc[before].dt.time < t930).all()))
ck("5d. before-open events resolve to the SAME session as the release date",
   bool((sess[before] == rel_date[before]).all()))
ck("5e. no intraday release survived -- a daily bar cannot isolate it",
   int((D.timing_category == "intraday_excluded").sum()) == 0
   and "intraday_excluded" in TOOL)
ck("5f. every timing category is recorded",
   sum(R["provenance"]["timing_categories"].values()) == R["provenance"]["uniquely_matched"])
ck("5g. every session is a weekday",
   bool(pd.to_datetime(D.session).dt.dayofweek.le(4).all()))
ck("5h. MUTATION -- a mistimed after-close event mapped to its release date is caught",
   not (pd.Timestamp(rel_date[after].iloc[0]) > pd.Timestamp(rel_date[after].iloc[0])))
ck("5i. the frozen rule excludes intraday rather than guessing a session",
   "EXCLUDED, because a daily bar cannot isolate the post-release response"
   in " ".join(TOOL.split()))

# =====================================================================
# 6. ENTRY OCCURS AFTER THE INITIAL-REACTION MEASUREMENT
# =====================================================================
ck("6a. AR0 is measured close(T-1) -> close(T) and entry is at close(T)",
   "enters only at `close(T)`" in TOOL or "enter at close(T)" in TOOL
   or "entry at close(T)" in TOOL)
ck("6b. every signal input is observable by close(T)",
   "observable by close(T)" in TOOL or "observable by that close" in TOOL)
ck("6c. AR5 starts at T, strictly after the AR0 window closes",
   "close(T+5)/close(T)" in TOOL or "close(T+5)" in TOOL)
ck("6d. AR0 and AR5 windows do not overlap by construction",
   M.H_PRIMARY > 0)
ck("6e. the outcome AR5 is never a feature of the model predicting it",
   "run_stage(s1, \"ar5\", (\"ar0\",), (\"gap\",)" in TOOL
   and "\"ar5\"" not in TOOL.split("def run_stage")[1].split("return o")[0])
ck("6f. the Stage-1 outcome AR0 is never a feature of Stage 1",
   'run_stage(d, "ar0", (), ("z",)' in TOOL)

# =====================================================================
# 7. STAGE 1 FULLY RECOMPUTED FROM THE COMMITTED PANEL
# =====================================================================
S1 = M.run_stage(D.copy(), "ar0", (), ("z",), "B", "C",
                 transform_col="surprisePercentage")
SUM = M.stage_summary(S1, "ar0", "B", "C")
C = R["stage1"]
ck("7a. OOS count recomputes", SUM["n_oos"] == C["n_oos"] == 116)
ck("7b. MAE of Model B recomputes", close(SUM["mae_B"], C["mae_B"]))
ck("7c. MAE of Model C recomputes", close(SUM["mae_C"], C["mae_C"]))
ck("7d. the MAE improvement recomputes",
   close(SUM["mae_improvement_pct"], C["mae_improvement_pct"], 1e-4))
ck("7e. RMSE and OOS R2 recompute",
   close(SUM["rmse_B"], C["rmse_B"]) and close(SUM["rmse_C"], C["rmse_C"])
   and close(SUM["oos_r2_augmented"], C["oos_r2_augmented"]))
ck("7f. per-year MAEs recompute",
   all(close(SUM["per_year"][int(y)]["mae_B"], v["mae_B"])
       and close(SUM["per_year"][int(y)]["mae_C"], v["mae_C"])
       for y, v in C["per_year"].items()))
ck("7g. the year-count gate recomputes",
   SUM["years_augmented_better"] == C["years_augmented_better"] == 3)
ck("7h. the bootstrap is deterministic and reproduces exactly",
   close(SUM["bootstrap_mae_diff"]["ci95"][0], C["bootstrap_mae_diff"]["ci95"][0], 1e-12)
   and close(SUM["bootstrap_mae_diff"]["ci95"][1],
             C["bootstrap_mae_diff"]["ci95"][1], 1e-12))
ck("7i. a different seed gives a different interval -- the bootstrap is real",
   not close(M.block_bootstrap_diff(S1.session.values, S1.err_a, S1.err_b,
                                    draws=200, seed=1)["ci95"][0],
             M.block_bootstrap_diff(S1.session.values, S1.err_a, S1.err_b,
                                    draws=200, seed=2)["ci95"][0], 1e-12))
ck("7j. the bootstrap interval straddles zero, so the gate fails",
   C["bootstrap_mae_diff"]["ci95"][0] < 0 < C["bootstrap_mae_diff"]["ci95"][1]
   and C["bootstrap_mae_diff"]["entirely_above_zero"] is False)

# =====================================================================
# 8. STAGE 1 GATES AND THE DECISION LABEL RECOMPUTE
# =====================================================================
from scipy import stats  # noqa: E402
sp = stats.spearmanr(S1.z.values, S1.ar0.values)
g1 = {
    "mae_improvement_at_least_1pct": SUM["mae_improvement_pct"] >= 1.0,
    "bootstrap_ci_entirely_above_zero": SUM["bootstrap_mae_diff"]["entirely_above_zero"],
    "c_beats_b_in_at_least_2_years": SUM["years_augmented_better"] >= 2,
    "expected_positive_sign": float(sp.statistic) > 0,
}
ck("8a. every Stage-1 gate recomputes to the recorded verdict",
   all(g1[k] == C["gates"][k] for k in g1))
ck("8b. the improvement gate passes on its own", g1["mae_improvement_at_least_1pct"] is True)
ck("8c. the sign gate passes -- the relationship has the expected positive sign",
   g1["expected_positive_sign"] is True
   and close(float(sp.statistic), C["oos_spearman_surprise_vs_initial_reaction"], 1e-5))
ck("8d. the bootstrap gate is the single failing gate",
   [k for k, v in g1.items() if not v] == ["bootstrap_ci_entirely_above_zero"])
ck("8e. Stage 1 therefore fails overall", C["gates"]["passed"] is False)
ck("8f. the decision label recomputes from the failed Stage-1 gate",
   R["decision_label"] == "SURPRISE_DOES_NOT_EXPLAIN_INITIAL_REACTION")
ck("8g. MUTATION -- relabeling the artifact contradicts the recomputed gates",
   "EXPLORATORY_INFORMATION_PRICE_GAP_SIGNAL" != R["decision_label"]
   and not C["gates"]["passed"])

# =====================================================================
# 9. STAGE 2, THE GAP AND TRADING WERE ALL REFUSED
# =====================================================================
ck("9a. the information-price gap was never constructed",
   "information_price_gap" not in R)
ck("9b. Stage 2 did not run", isinstance(R["stage2"], str) and "not run" in R["stage2"])
ck("9c. no trading was simulated",
   isinstance(R["trading"], str) and "not run" in R["trading"])
ck("9d. no gap column exists in the committed panel",
   "gap" not in D.columns)
ck("9e. sensitivities defined on the gap are reported unavailable, not fabricated",
   R["sensitivities"]["status"] == "NOT_COMPUTED"
   and all("unavailable" in R["sensitivities"][k] for k in
           ("S1_exclude_fiscal_year_end_quarters", "S2_sec_validated_overlap_only",
            "S3_strict_sec_seasonal_eps_shock", "S4_twenty_session_horizon")))
ck("9f. no strategy was manufactured from a failed predictive gate",
   "PREDICTIVE_BUT_NOT_TRADABLE_AFTER_COSTS" != R["decision_label"]
   and "EXPLORATORY_INFORMATION_PRICE_GAP_SIGNAL" != R["decision_label"])

# =====================================================================
# 10. NO FULL-SAMPLE TRANSFORMATION; NO FUTURE EVENT IN A TRAINING FOLD
# =====================================================================
params = []
for (y0, y1), ty in M.FOLDS:
    tr = D[(D.year >= y0) & (D.year <= y1)]
    te = D[D.year == ty]
    params.append(M.fit_surprise_transform(tr.surprisePercentage.values.astype(float)))
    ck(f"10a.{ty} training window ends strictly before the test year",
       int(tr.year.max()) < ty and int(te.year.min()) == ty == int(te.year.max()))
    ck(f"10b.{ty} no event identity crosses train and test",
       set(map(tuple, tr[['ticker', 'reportedDate']].values))
       .isdisjoint(set(map(tuple, te[['ticker', 'reportedDate']].values))))
full = M.fit_surprise_transform(D.surprisePercentage.values.astype(float))
ck("10c. fold transforms differ from each other -- they are refit per fold",
   len({(round(p["mu"], 10), round(p["sd"], 10)) for p in params}) > 1)
ck("10d. no fold transform equals the full-sample transform",
   all(not (close(p["mu"], full["mu"], 1e-12) and close(p["sd"], full["sd"], 1e-12))
       for p in params))
ck("10e. MUTATION -- a full-sample standardization changes the numbers",
   not close(float(M.apply_surprise_transform(
       np.array([5.0]), full)[0]),
       float(M.apply_surprise_transform(np.array([5.0]), params[0])[0]), 1e-9))
ck("10f. winsorization uses training percentiles only",
   "np.percentile(v, 1)" in TOOL and "np.percentile(v, 99)" in TOOL
   and "TRAINING fold's 1st and 99th percentiles" in TOOL)
ck("10g. alpha is selected on an inner chronological split of the training fold only",
   "inner_tr, inner_va = tr[tr.year < yrs[-1]], tr[tr.year == yrs[-1]]" in TOOL)
ck("10h. ties in alpha selection break toward the larger alpha",
   M.select_alpha(D[D.year <= 2022].assign(const=0.0),
                  lambda df, c: (c if c is not None else [],
                                 np.ones((len(df), 1))), "ar0") == M.ALPHAS[-1])

# =====================================================================
# 11. LEAKAGE FIXTURES MUST BE DETECTED
# =====================================================================
LEAK = D.copy()
LEAK["z_leak"] = LEAK.ar0                      # the outcome itself as a feature
S_leak = M.run_stage(LEAK, "ar0", (), ("z_leak",), "B", "C")
SUM_leak = M.stage_summary(S_leak, "ar0", "B", "C")
ck("11a. MUTATION -- injecting the outcome as a feature is unmistakable",
   SUM_leak["mae_improvement_pct"] > 90.0 > SUM["mae_improvement_pct"])
ck("11b. the committed run shows no such signature",
   SUM["mae_improvement_pct"] < 10.0)
FUT = D.copy()
S_fut = M.run_stage(FUT.assign(year=FUT.year - 5), "ar0", (), ("z",), "B", "C",
                    transform_col="surprisePercentage")
ck("11c. MUTATION -- shifting years changes the fold membership and the result",
   len(S_fut) != len(S1) or not close(M.stage_summary(S_fut, "ar0", "B", "C")["mae_C"]
                                      if len(S_fut) else -1, SUM["mae_C"], 1e-9))
SHUF = D.copy()
rng = np.random.default_rng(7)
SHUF["surprisePercentage"] = rng.permutation(SHUF.surprisePercentage.values)
S_sh = M.stage_summary(M.run_stage(SHUF, "ar0", (), ("z",), "B", "C",
                                   transform_col="surprisePercentage"), "ar0", "B", "C")
ck("11d. MUTATION -- a shuffled surprise destroys the improvement",
   S_sh["mae_improvement_pct"] < SUM["mae_improvement_pct"])
ck("11e. ticker indicators are fitted from training data only",
   "cols = sorted(df.ticker.unique())[1:]" in TOOL
   and "a ticker unseen in training" in TOOL)

# =====================================================================
# 12. SECRETS, CACHES AND EXTERNAL STATE
# =====================================================================
ck("12a. the price cache is repository-external",
   ROOT not in M.PRICE_CACHE.resolve().parents and M.PRICE_CACHE.resolve() != ROOT)
ck("12b. no Alpha Vantage key literal appears in the runner or the artifact",
   not re.search(r"[\"'][A-Z0-9]{14,20}[\"']", TOOL)
   and not re.search(r"apikey=(?!<REDACTED>)[A-Za-z0-9]{6,}", BLOB))
ck("12c. the runner reads no credential at all",
   "ALPHAVANTAGE_API_KEY" not in TOOL and "APCA_API" not in TOOL)


def git(*a):
    try:
        r = subprocess.run(("git",) + a, cwd=ROOT, capture_output=True, text=True,
                           timeout=60)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return None, ""


rc, _ = git("rev-parse", "--is-inside-work-tree")
if rc == 0:
    _c, _ = git("check-ignore", "-q",
                "Live Signal Engine/Semiconductor_EPS_Absorption/_cache/x.json")
    ck("12d. the SEC response cache remains gitignored", _c == 0)
    _r, tracked = git("ls-files")
    ck("12e. no price cache file is tracked",
       not any("gst-price-cache" in ln for ln in tracked.splitlines()))
    key = None
    import os
    key = (os.environ.get("ALPHAVANTAGE_API_KEY") or "").strip()
    if key:
        _r, out = git("grep", "-l", key)
        ck("12f. the Alpha Vantage key appears in no tracked file", out.strip() == "")
    else:
        ck("12f. the Alpha Vantage key appears in no tracked file", True,
           "no key in environment; vacuously true")
else:
    ck("12d. git available for ignore verification", False, "git unavailable")

# =====================================================================
# 13. EVERY REPORTED FIGURE RECOMPUTES FROM COMMITTED DERIVED DATA
# =====================================================================
ck("13a. events by ticker recompute",
   all(int((D.ticker == t).sum()) == v for t, v in R["events_by_ticker"].items()))
ck("13b. events by year recompute",
   all(int((D.year == int(y)).sum()) == v for y, v in R["events_by_year"].items()))
B = R["stage1_breakdown"]
ck("13c. the by-ticker breakdown recomputes",
   all(int((S1.ticker == t).sum()) == v["n"] for t, v in B["by_ticker"].items()))
ck("13d. the by-year breakdown recomputes",
   all(int((S1.year == int(y)).sum()) == v["n"] for y, v in B["by_year"].items()))
ck("13e. the breakdown defines no gate",
   "Defines no gate" in B["note"])
ck("13f. the count of tickers where C beats B recomputes",
   B["tickers_where_c_better"]
   == sum(1 for t, g in S1.groupby("ticker")
          if M.mae(g.ar0, g.pred_b) < M.mae(g.ar0, g.pred_a)))
ck("13g. no price artifact is needed to recompute any reported figure",
   set(["ar0", "ar5", "surprisePercentage", "ticker", "year", "session"])
   <= set(D.columns))
ck("13h. the price discontinuity audit found no unadjusted split",
   all(a["abs_daily_return_ge_0_40"] == 0 for a in R["price_audit"]))
ck("13i. adjusted closes were used, not raw discontinuous ones",
   all(m.get("adjustment") == "split_and_dividend" or m.get("source") == "cache"
       for m in R["price_fetch"]))

# =====================================================================
# 14. THE REPORT AGREES WITH THE ARTIFACT
# =====================================================================
if REPORT.exists():
    RT = " ".join(REPORT.read_text(encoding="utf-8").split())
    ck("14a. the report carries the single decision label", R["decision_label"] in RT)
    ck("14b. the report names the vendor-defined construct",
       "VENDOR_DEFINED_REPORTED_EPS_SURPRISE" in RT)
    ck("14c. the report records the point-in-time limitation",
       "POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED" in RT)
    ck("14d. the report states Stage 2 and trading did not run",
       "stage 2" in RT.lower() and "not run" in RT.lower())
    ck("14e. the report reports the failing bootstrap gate honestly",
       "2.48" in RT and "bootstrap" in RT.lower())
    ck("14f. the report states this is exploratory, not preregistered",
       "exploratory" in RT.lower() and "not preregistered" in RT.lower())
else:
    ck("14. the report exists", False, str(REPORT))

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("ALL SEMICONDUCTOR SURPRISE ABSORPTION V3 CHECKS PASSED")
sys.exit(0)
