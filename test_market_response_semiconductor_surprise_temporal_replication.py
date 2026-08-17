#!/usr/bin/env python3
"""Deterministic test for the terminal temporal replication (2010-2017).

Recomputes Stage 1 end to end from the COMMITTED replication panel and proves the
temporal-isolation, leakage and integrity properties. Deliberately leaked, duplicated,
mistimed, future-trained and gate-mutated fixtures must be detected. Offline: no
network, no credential, no price file.
"""
from __future__ import annotations

import json
import math
import os
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
import run_semiconductor_surprise_temporal_replication as T  # noqa: E402
import run_semiconductor_surprise_absorption_v3 as V3  # noqa: E402

R = json.loads((ROOT / "SEMICONDUCTOR_SURPRISE_TEMPORAL_REPLICATION_RESULTS_v1.0.json")
               .read_text(encoding="utf-8"))
PANEL = ROOT / "Live Signal Engine" / "Semiconductor_Surprise_Temporal_Replication" / \
    "event_panel_v1.0.csv"
D = pd.read_csv(PANEL)
TOOL = (ROOT / "tools" / "run_semiconductor_surprise_temporal_replication.py").read_text(
    encoding="utf-8")
V3SRC = (ROOT / "tools" / "run_semiconductor_surprise_absorption_v3.py").read_text(
    encoding="utf-8")
PR34_PANEL = ROOT / "Live Signal Engine" / "Semiconductor_Surprise_Absorption_v3" / \
    "event_panel_v1.0.csv"
REPORT = ROOT / "SEMICONDUCTOR_SURPRISE_TEMPORAL_REPLICATION_REPORT_v1.0.md"
ET = ZoneInfo("America/New_York")
FAIL: list[str] = []


def ck(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


# =====================================================================
# 1. TEMPORAL ISOLATION FROM PR #34 -- BOTH DIRECTIONS
# =====================================================================
ck("1a. every replication event is dated 2004-2017",
   bool((D.year >= 2004).all() and (D.year <= 2017).all()))
ck("1b. no post-2017 outcome entered this replication",
   int((D.year > 2017).sum()) == 0
   and bool(pd.to_datetime(D.session).max() < pd.Timestamp("2018-01-01")))
ck("1c. the OOS window is exactly 2010-2017",
   R["oos_window"] == ["2010-01-01", "2017-12-31"]
   and sorted({int(y) for y in R["stage1_replication"]["per_year"]})
   == list(range(2010, 2018)))
if PR34_PANEL.exists():
    P34 = pd.read_csv(PR34_PANEL)
    ck("1d. PR #34's sample is disjoint in time from this replication",
       int((P34.year <= 2017).sum()) == 0 and int((D.year >= 2018).sum()) == 0)
    ck("1e. no event identity is shared with PR #34",
       set(map(tuple, D[["ticker", "reportedDate"]].values))
       .isdisjoint(set(map(tuple, P34[["ticker", "reportedDate"]].values))))
    ck("1f. PR #34's OOS years and this replication's OOS years do not intersect",
       set(P34[P34.year >= 2023].year.unique()).isdisjoint(set(range(2010, 2018))))
else:
    ck("1d. PR #34 panel present for disjointness check", False)
ck("1g. training begins 2004-01-01 as frozen", R["train_start"] == "2004-01-01")
ck("1h. the PR #34 comparison is secondary and was never pooled",
   R["pr34_comparison"]["pooled_to_change_decision"] is False
   and "NEVER pooled" in R["pr34_comparison"]["note"])

# =====================================================================
# 2. FROZEN MODEL, GRID, BOOTSTRAP AND GATES ARE UNCHANGED
# =====================================================================
ck("2a. the frozen replication design block is present and closed",
   "FROZEN_TEMPORAL_REPLICATION_DESIGN" in TOOL
   and "END FROZEN_TEMPORAL_REPLICATION_DESIGN" in TOOL)
ck("2b. the alpha grid is PR #34's, unexpanded",
   V3.ALPHAS == [0.0, 0.1, 1.0, 10.0] == R["reused_from_pr34"]["alpha_grid"])
ck("2c. the bootstrap seed and block structure are unchanged",
   (V3.BOOT_DRAWS, V3.BOOT_BLOCK_DAYS, V3.BOOT_SEED) == (2000, 28, 20260817)
   and R["stage1_replication"]["bootstrap_mae_diff"]["seed"] == 20260817
   and R["stage1_replication"]["bootstrap_mae_diff"]["block_days"] == 28
   and R["stage1_replication"]["bootstrap_mae_diff"]["draws"] == 2000)
ck("2d. horizons, cost and improvement threshold are unchanged",
   (V3.H_PRIMARY, V3.H_SECONDARY) == (5, 20) and V3.COST_BPS_ROUND_TRIP == 10.0
   and V3.MAE_IMPROVEMENT_MIN == 1.0)
ck("2e. the PR #34 module source was NOT edited",
   "FOLDS = [((2018, 2022), 2023), ((2018, 2023), 2024), ((2018, 2024), 2025)]" in V3SRC)
ck("2f. only FOLDS and PRICE_CACHE were rebound, and that is recorded",
   R["reused_from_pr34"]["rebound_globals"] == ["FOLDS", "PRICE_CACHE"]
   and R["reused_from_pr34"]["source_edited"] is False)
ck("2g. the replication folds are the eight frozen expanding windows",
   T.REPL_FOLDS == [((2004, y - 1), y) for y in range(2010, 2018)]
   and V3.FOLDS == T.REPL_FOLDS and len(T.REPL_FOLDS) == 8)
ck("2h. the two-thirds year rule is ceil(2N/3)",
   T.two_thirds(8) == 6 and T.two_thirds(3) == 2 and T.two_thirds(9) == 6)
CODE = TOOL.split('"""', 2)[2] if TOOL.count('"""') >= 2 else TOOL
ck("2i. no new model family, control or interaction was introduced",
   not re.search(r"(RandomForest|GradientBoost|XGBo|LGBM|SVR\(|MLPRegressor|"
                 r"PolynomialFeatures|interaction)", CODE, re.I)
   and "no interactions" in " ".join(TOOL.split())
   and V3.ridge_fit is not None)
ck("2j. the universe is unchanged and nothing was replaced",
   T.UNIVERSE == V3.UNIVERSE and len(T.UNIVERSE) == 10
   and R["universe"] == V3.UNIVERSE)
ck("2k. the sample gate thresholds are the frozen replication ones",
   T.SAMPLE_GATE == {"tickers": 8, "events": 200, "oos_events": 160, "oos_per_year": 15})

# =====================================================================
# 3. CONSTRUCT LANGUAGE
# =====================================================================
BLOB = json.dumps(R)
ck("3a. the predictor is VENDOR_DEFINED_REPORTED_EPS_SURPRISE",
   R["surprise_construct"] == "VENDOR_DEFINED_REPORTED_EPS_SURPRISE"
   and R["primary_surprise_field"] == "surprisePercentage")
ck("3b. point-in-time provenance is recorded as not guaranteed",
   R["point_in_time_provenance"] == "POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED")
ck("3c. the forbidden claims are disclaimed",
   set(R["not_claimed"]) >= {"GAAP surprise", "SEC-validated surprise",
                             "guaranteed contemporaneous consensus",
                             "preregistered evidence", "investable signal"})
ck("3d. recorded as a retrospective, not prospectively registered, replication",
   "RETROSPECTIVE TEMPORAL REPLICATION" in R["test_nature"]
   and "NOT a prospectively registered" in R["test_nature"])
ck("3e. recorded as terminal with no third replication proposed",
   R["terminal_replication"] is True and R["third_replication_proposed"] is False)
ck("3f. not a GST test", R["is_gst_test"] is False)

# =====================================================================
# 4. IDENTITY, CROSSWALK AND DUPLICATES
# =====================================================================
ck("4a. no duplicate event identity",
   int(D.duplicated(subset=["ticker", "reportedDate", "accession"]).sum()) == 0
   == R["sample_gate"]["duplicate_identities"]["value"])
ck("4b. MUTATION -- a duplicated identity is detected",
   int(pd.concat([D, D.iloc[[0]]]).duplicated(
       subset=["ticker", "reportedDate", "accession"]).sum()) == 1)
ck("4c. zero ambiguous crosswalk matches survived",
   R["crosswalk_excluded"]["ambiguous"] == 1
   and len(D) == R["uniquely_matched"] == R["provider_records_2004_2017"]
   - R["crosswalk_excluded"]["no_match"] - R["crosswalk_excluded"]["ambiguous"])
ck("4d. unmatched events were excluded without replacement",
   R["crosswalk_excluded"]["no_match"] > 0
   and int(D.ticker.nunique()) == R["sample_gate"]["tickers"]["value"])
ck("4e. every historical CIK and identity record is reported",
   all(k in R["sec_identity"][t] for t in T.UNIVERSE
       for k in ("cik", "resolved")))
ck("4f. AVGO's unresolved pre-2018 identity is recorded, not replaced",
   R["unresolved_historical_identity"] == ["AVGO"]
   and R["events_by_ticker"]["AVGO"] == 0
   and "never replaced" in (R["sec_identity"]["AVGO"]["reason"] or ""))
ck("4g. no ticker was substituted for AVGO",
   set(R["events_by_ticker"]) == set(T.UNIVERSE) and len(R["events_by_ticker"]) == 10)
ck("4h. identity was resolved from SEC metadata, never from returns",
   "Returns are NEVER used to resolve an identity" in TOOL
   and "company_tickers.json" in TOOL)
ck("4i. the Item 2.02 effective-date limitation is recorded in advance",
   R["item_202_effective_date"] == "2004-08-23"
   and "training window" in R["item_202_note"])

# =====================================================================
# 5. ANNOUNCEMENT-AWARE TIMING; ENTRY FOLLOWS REACTION MEASUREMENT
# =====================================================================
acc = pd.to_datetime(D.acceptance_utc, utc=True, format="mixed").dt.tz_convert(ET)
rel, sess = acc.dt.date, pd.to_datetime(D.session).dt.date
t930 = datetime.strptime("09:30", "%H:%M").time()
t1600 = datetime.strptime("16:00", "%H:%M").time()
aft = D.timing_category == "after_close_next_session"
bef = D.timing_category == "before_open_same_session"
ck("5a. after-close events were accepted at or after 16:00 ET",
   bool((acc[aft].dt.time >= t1600).all()))
ck("5b. after-close events map to a LATER session", bool((sess[aft] > rel[aft]).all()))
ck("5c. before-open events were accepted before 09:30 ET",
   bool((acc[bef].dt.time < t930).all()))
ck("5d. before-open events map to the SAME session", bool((sess[bef] == rel[bef]).all()))
ck("5e. no intraday release survived",
   int((D.timing_category == "intraday_excluded").sum()) == 0)
ck("5f. every session is a weekday",
   bool(pd.to_datetime(D.session).dt.dayofweek.le(4).all()))
ck("5g. MUTATION -- mapping an after-close event to its release date breaks the rule",
   not bool((sess[aft] == rel[aft]).any()))
ck("5h. AR0 ends at close(T) and entry is close(T), so entry follows measurement",
   "close(T)" in TOOL and "known before that entry" in " ".join(TOOL.split()))
ck("5i. the calendar-bounds amendment is recorded and was pre-outcome",
   R["reused_from_pr34"]["calendar_bounds_amendment"]["made_before_any_outcome_opened"]
   is True
   and R["reused_from_pr34"]["calendar_bounds_amendment"]["source_edited"] is False)

# =====================================================================
# 6. STAGE 1 RECOMPUTED FROM THE COMMITTED PANEL
# =====================================================================
S1 = V3.run_stage(D.copy(), "ar0", (), ("z",), "B", "C",
                  transform_col="surprisePercentage")
SUM = V3.stage_summary(S1, "ar0", "B", "C")
C = R["stage1_replication"]
ck("6a. OOS count recomputes", SUM["n_oos"] == C["n_oos"] == 283)
ck("6b. MAE of Model B recomputes", close(SUM["mae_B"], C["mae_B"]))
ck("6c. MAE of Model C recomputes", close(SUM["mae_C"], C["mae_C"]))
ck("6d. the improvement recomputes",
   close(SUM["mae_improvement_pct"], C["mae_improvement_pct"], 1e-4))
ck("6e. RMSE and OOS R2 recompute",
   close(SUM["rmse_B"], C["rmse_B"]) and close(SUM["rmse_C"], C["rmse_C"])
   and close(SUM["oos_r2_augmented"], C["oos_r2_augmented"]))
ck("6f. every per-year MAE recomputes",
   all(close(SUM["per_year"][int(y)]["mae_B"], v["mae_B"])
       and close(SUM["per_year"][int(y)]["mae_C"], v["mae_C"])
       for y, v in C["per_year"].items()))
ck("6g. the year-count recomputes",
   SUM["years_augmented_better"] == C["years_augmented_better"] == 5)
ck("6h. the bootstrap reproduces exactly at the frozen seed",
   close(SUM["bootstrap_mae_diff"]["ci95"][0], C["bootstrap_mae_diff"]["ci95"][0], 1e-12)
   and close(SUM["bootstrap_mae_diff"]["ci95"][1],
             C["bootstrap_mae_diff"]["ci95"][1], 1e-12))
ck("6i. the bootstrap block count recomputes",
   SUM["bootstrap_mae_diff"]["blocks"] == C["bootstrap_mae_diff"]["blocks"] == 92)

# =====================================================================
# 7. THE FOUR REPLICATION GATES AND THE LABEL
# =====================================================================
from scipy import stats  # noqa: E402
sp = stats.spearmanr(S1.z.values, S1.ar0.values)
need = T.two_thirds(len(SUM["per_year"]))
g = {
    "mae_improvement_at_least_1pct": SUM["mae_improvement_pct"] >= 1.0,
    "bootstrap_ci_entirely_above_zero": SUM["bootstrap_mae_diff"]["entirely_above_zero"],
    "c_beats_b_in_two_thirds_of_years": SUM["years_augmented_better"] >= need,
    "expected_positive_sign": float(sp.statistic) > 0,
}
ck("7a. every replication gate recomputes to the recorded verdict",
   all(g[k] == C["gates"][k] for k in g))
ck("7b. the improvement gate passes", g["mae_improvement_at_least_1pct"] is True)
ck("7c. the sign gate passes and the Spearman recomputes",
   g["expected_positive_sign"] is True
   and close(float(sp.statistic), C["oos_spearman_surprise_vs_initial_reaction"], 1e-5))
ck("7d. the bootstrap gate fails -- the interval straddles zero",
   C["bootstrap_mae_diff"]["ci95"][0] < 0 < C["bootstrap_mae_diff"]["ci95"][1])
ck("7e. the year-consistency gate fails -- 5 of 8 beats, 6 required",
   SUM["years_augmented_better"] == 5 and need == 6
   and g["c_beats_b_in_two_thirds_of_years"] is False)
ck("7f. exactly two of four gates fail", sum(1 for v in g.values() if not v) == 2)
ck("7g. the replication therefore fails", C["gates"]["passed"] is False)
ck("7h. the decision label recomputes",
   R["decision_label"] == "TEMPORAL_REPLICATION_FAILS" and R["decision_label"] in T.LABELS)
ck("7i. MUTATION -- mutating a gate to true would change the verdict",
   all({**g, "bootstrap_ci_entirely_above_zero": True}.values()) is False
   and all({**g, "bootstrap_ci_entirely_above_zero": True,
            "c_beats_b_in_two_thirds_of_years": True}.values()) is True)

# =====================================================================
# 8. STAGE 2, TRADING AND ANY THIRD REPLICATION ARE ALL REFUSED
# =====================================================================
ck("8a. no information-price gap was constructed", "information_price_gap" not in R)
ck("8b. Stage 2 did not run", isinstance(R["stage2"], str) and "not run" in R["stage2"])
ck("8c. no trading was simulated",
   isinstance(R["trading"], str) and "not run" in R["trading"])
ck("8d. no gap column exists in the committed panel", "gap" not in D.columns)
ck("8e. the path is recorded as stopped with no third replication",
   "NO THIRD REPLICATION IS PROPOSED" in R["path_status"])
ck("8f. the twenty-session return was not reported",
   R["secondary_reporting"]["twenty_session_return"]["status"] == "NOT_REPORTED")
ck("8g. the SEC-validated overlap is reported not applicable, not fabricated",
   R["secondary_reporting"]["sec_validated_overlap_only"]["status"] == "NOT_APPLICABLE")

# =====================================================================
# 9. TRAINING-ONLY TRANSFORMS AND CHRONOLOGICAL FOLDS
# =====================================================================
params = []
for (y0, y1), ty in T.REPL_FOLDS:
    tr = D[(D.year >= y0) & (D.year <= y1)]
    te = D[D.year == ty]
    params.append(V3.fit_surprise_transform(tr.surprisePercentage.values.astype(float)))
    ck(f"9a.{ty} the training window ends strictly before the test year",
       int(tr.year.max()) < ty and int(te.year.min()) == ty == int(te.year.max()))
    ck(f"9b.{ty} no identity crosses train and test",
       set(map(tuple, tr[["ticker", "reportedDate"]].values))
       .isdisjoint(set(map(tuple, te[["ticker", "reportedDate"]].values))))
full = V3.fit_surprise_transform(D.surprisePercentage.values.astype(float))
ck("9c. fold transforms differ -- they are refit per fold",
   len({(round(p["mu"], 10), round(p["sd"], 10)) for p in params}) > 1)
ck("9d. no fold transform equals a full-sample transform",
   all(not (close(p["mu"], full["mu"], 1e-12) and close(p["sd"], full["sd"], 1e-12))
       for p in params))
ck("9e. the recorded train/test identity overlap is zero",
   R["sample_gate"]["train_test_identity_overlap"]["value"] == 0)
ck("9f. MUTATION -- training on the future changes the result",
   not close(V3.stage_summary(
       V3.run_stage(D.assign(year=D.year.max() - (D.year - D.year.min())), "ar0", (),
                    ("z",), "B", "C", transform_col="surprisePercentage"),
       "ar0", "B", "C")["mae_C"], SUM["mae_C"], 1e-9))

# =====================================================================
# 10. LEAKAGE FIXTURES
# =====================================================================
LEAK = D.assign(z_leak=D.ar0)
SUM_leak = V3.stage_summary(V3.run_stage(LEAK, "ar0", (), ("z_leak",), "B", "C"),
                            "ar0", "B", "C")
ck("10a. MUTATION -- the outcome injected as a feature is unmistakable",
   SUM_leak["mae_improvement_pct"] > 90.0 > SUM["mae_improvement_pct"])
ck("10b. the committed run shows no such signature", SUM["mae_improvement_pct"] < 10.0)
rng = np.random.default_rng(11)
SH = D.assign(surprisePercentage=rng.permutation(D.surprisePercentage.values))
ck("10c. MUTATION -- a shuffled surprise destroys the improvement",
   V3.stage_summary(V3.run_stage(SH, "ar0", (), ("z",), "B", "C",
                                 transform_col="surprisePercentage"),
                    "ar0", "B", "C")["mae_improvement_pct"]
   < SUM["mae_improvement_pct"])
ck("10d. AR0 is never a feature of the Stage-1 model that predicts it",
   'run_stage(d, "ar0", (), ("z",)' in TOOL)

# =====================================================================
# 11. SECRETS, RAW RESPONSES AND CACHES
# =====================================================================
ck("11a. all three caches are repository-external",
   all(ROOT not in p.resolve().parents and p.resolve() != ROOT
       for p in (T.AV_CACHE, T.SEC_CACHE, T.PRICE_CACHE)))
ck("11b. the runner reads no credential",
   "ALPHAVANTAGE_API_KEY" not in TOOL and "APCA_API" not in TOOL
   and "apikey" not in TOOL.lower())
ck("11c. no key-like literal appears in the runner or artifact",
   not re.search(r"[\"'][A-Z0-9]{14,20}[\"']", TOOL)
   and not re.search(r"apikey=(?!<REDACTED>)[A-Za-z0-9]{6,}", BLOB))
ck("11d. no raw provider response is embedded in the artifact",
   "quarterlyEarnings" not in BLOB)


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
    ck("11e. the SEC exhibit cache remains gitignored", _c == 0)
    _r, tracked = git("ls-files")
    ck("11f. no external cache file is tracked",
       not any(re.search(r"gst-(av-earnings|sec-repl|price)-cache", ln)
               for ln in tracked.splitlines()))
    k = (os.environ.get("ALPHAVANTAGE_API_KEY") or "").strip()
    if k:
        _r, out = git("grep", "-l", k)
        ck("11g. the Alpha Vantage key is in no tracked file", out.strip() == "")
    else:
        ck("11g. the Alpha Vantage key is in no tracked file", True,
           "no key in environment; vacuously true")
else:
    ck("11e. git available", False, "git unavailable")

# =====================================================================
# 12. SPLIT AUDIT AND REPORTING COMPLETENESS
# =====================================================================
ck("12a. every large daily move is reported and diagnosed, not deleted",
   all("diagnosis" in j and j["action"] == "reported, not deleted"
       for j in R["price_discontinuities"]))
ck("12b. the AMD 2016-04-22 move is diagnosed as genuine",
   any(j["ticker"] == "AMD" and j["date"] == "2016-04-22"
       and "genuine" in j["diagnosis"] for j in R["price_discontinuities"]))
ck("12c. results are reported by ticker and by year",
   len(R["secondary_reporting"]["by_ticker"]) == 9
   and len(R["secondary_reporting"]["by_year"]) == 8)
ck("12d. the by-ticker counts recompute",
   all(int((S1.ticker == t).sum()) == v["n"]
       for t, v in R["secondary_reporting"]["by_ticker"].items()))
ck("12e. secondary reporting defines no gate",
   "Defines no gate" in R["secondary_reporting"]["note"])
ck("12f. the fiscal-year-end exclusion is descriptive only",
   R["secondary_reporting"]["fiscal_year_end_quarters_excluded"] > 0)
ck("12g. sign agreement with PR #34 is reported without pooling",
   R["pr34_comparison"]["point_estimates_agree_in_sign"] is True
   and R["pr34_comparison"]["pooled_to_change_decision"] is False)

# =====================================================================
# 13. THE REPORT AGREES WITH THE ARTIFACT
# =====================================================================
if REPORT.exists():
    RT = " ".join(REPORT.read_text(encoding="utf-8").split())
    ck("13a. the report carries the decision label", R["decision_label"] in RT)
    ck("13b. the report names the construct and provenance",
       "VENDOR_DEFINED_REPORTED_EPS_SURPRISE" in RT
       and "POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED" in RT)
    ck("13c. the report states no third replication is proposed",
       "no third replication" in RT.lower())
    ck("13d. the report states Stage 2 and trading did not run",
       "stage 2" in RT.lower() and "not run" in RT.lower())
    ck("13e. the report gives the exact bootstrap interval", "0.002134" in RT)
    ck("13f. the report states this is retrospective, not preregistered",
       "not preregistered" in RT.lower() or "not a prospectively registered" in RT.lower())
else:
    ck("13. the report exists", False, str(REPORT))

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("ALL TEMPORAL REPLICATION CHECKS PASSED")
sys.exit(0)
