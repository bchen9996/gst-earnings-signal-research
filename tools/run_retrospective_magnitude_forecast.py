#!/usr/bin/env python3
"""Does GST improve out-of-sample prediction of absolute overnight earnings-gap size?

RETROSPECTIVE_DEVELOPMENT_ONLY. Confirms nothing about HYP-01. No directional
trading or profitability is evaluated anywhere in this file.

OUTCOME (frozen)   y = abs(open(T)/close(T-1) - 1), the absolute overnight gap.
                   Event day T uses the existing AMC/BMO convention.

SAMPLE (frozen)    Deduplicated by (ticker, event_day). The source population
                   reuses matched controls, so identities repeat.

BASELINE PREDICTORS (frozen, all strictly pre-event)
  b1 prior_mean_abs_gap  that ticker's mean |gap| over STRICTLY EARLIER earnings
  b2 realized_vol_20d    stdev of daily close-to-close returns, T-20..T-1
  b3 abs_ret_5d          |close(T-1)/close(T-6) - 1|
  b4 spy_vol_20d         stdev of SPY daily returns over the same window
  b5 is_amc              1 if the release is AMC, else 0

GST PREDICTOR (frozen, and deliberately NOT the population's spike z-score)
  g1 gst_z_pre   Built from raw weekly GST. Using only weeks that CLOSE strictly
                 before the event day, z = (latest closed week - mean of the prior
                 BASELINE_WEEKS) / stdev of those weeks.

                 WHY NOT the population's own `zscore`: that spike z-score is
                 computed over a 14-day window anchored at the spike week, while
                 the maximum anchor-to-event lead in this sample is 5 days. Its
                 window therefore always overlaps the announcement, and 9 of 217
                 anchors fall on or after the event day outright. Using it as a
                 predictor would be lookahead. It is retained in the output for
                 reference only and never enters a model.

MODELS - exactly three, one fixed regularized linear model, no search
  A  intercept-only historical mean of |gap| (training folds only)
  B  ridge on the five baseline predictors
  C  ridge on the identical five predictors PLUS gst_z_pre

VALIDATION  chronological expanding window, the same 2023 / 2024 / 2025 test folds
            as PR #23. Standardization and the ridge are fit inside each training
            fold only. Primary metric is out-of-sample MAE.

DECISIVE TEST  the paired event-level loss difference, abs_error(B) - abs_error(C),
               with ticker-clustered CR2 uncertainty. Positive means GST reduces
               prediction error.
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hyp01_inference_feasibility import cr_vcov, satterthwaite_df  # noqa: E402

EVENTS = ROOT / "Live Signal Engine" / "retrospective_event_components.csv"
POP = ROOT / "Live Signal Engine" / "C5_PostEarnings_Population.csv"
OHLC = ROOT / "Daily OHLC Data (2021-2025 Opening Gap Test)"
EXCESS = str(ROOT / "Daily Excess Return Data*" / "*_excess.csv")
WEEKLY = str(ROOT / "GST Data" / "Weekly Data*" / "*.csv")

TEST_YEARS = ["2023", "2024", "2025"]
BASELINE_WEEKS = 52          # baseline window for the pre-event GST z-score
MIN_BASELINE_WEEKS = 20
RIDGE_ALPHA = 1.0            # fixed; not tuned
BASE_FEATURES = ["prior_mean_abs_gap", "realized_vol_20d", "abs_ret_5d",
                 "spy_vol_20d", "is_amc"]
GST_FEATURE = "gst_z_pre"


def spy_series() -> pd.Series:
    fr = []
    for f in glob.glob(EXCESS):
        try:
            fr.append(pd.read_csv(f, usecols=["Date", "SPY Daily Return"]))
        except Exception:
            continue
    s = pd.concat(fr, ignore_index=True)
    s["Date"] = pd.to_datetime(s["Date"])
    return s.dropna().drop_duplicates("Date").set_index("Date")["SPY Daily Return"].sort_index().astype(float)


def weekly_gst() -> dict[str, pd.DataFrame]:
    out: dict[str, list] = {}
    for f in glob.glob(WEEKLY):
        base = os.path.basename(f)
        t = base.rsplit("_", 1)[0]
        try:
            d = pd.read_csv(f)
        except Exception:
            continue
        if "Week" not in d.columns or t not in d.columns:
            continue
        d = d[["Week", t]].rename(columns={t: "value"})
        out.setdefault(t, []).append(d)
    res = {}
    for t, frames in out.items():
        d = pd.concat(frames, ignore_index=True)
        d["Week"] = pd.to_datetime(d["Week"])
        d = d.dropna().drop_duplicates("Week").sort_values("Week").reset_index(drop=True)
        d["week_close"] = d["Week"] + pd.Timedelta(days=6)
        res[t] = d
    return res


def build() -> tuple[pd.DataFrame, dict]:
    ev = pd.read_csv(EVENTS)
    n_raw = len(ev)
    ev = (ev.sort_values(["ticker", "event_day", "role"])
            .drop_duplicates(subset=["ticker", "event_day"], keep="first")
            .sort_values("event_day").reset_index(drop=True))
    spy = spy_series()
    wk = weekly_gst()

    # reference-only: the population's own spike z-score and its anchor lead
    pop = pd.read_csv(POP)
    ref = {(r.ticker, str(r.earnings_date)[:10]): (r.zscore, r.anchor)
           for r in pop.itertuples()}

    rows, dropped = [], []
    prior_abs: dict[str, list[float]] = {}

    for _, r in ev.iterrows():
        px = pd.read_csv(OHLC / f"{r.ticker}_ohlc.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
        idx = px.index[px["Date"] == pd.Timestamp(r.event_day)]
        if len(idx) != 1:
            dropped.append((r.ticker, r.event_day, "event day not a session"))
            continue
        T = int(idx[0])
        if T - 21 < 0:
            dropped.append((r.ticker, r.event_day, "fewer than 21 prior sessions"))
            continue
        c = px["Close"].values
        y = abs(px["Open"].values[T] / c[T - 1] - 1.0)

        dr = c[T - 20:T] / c[T - 21:T - 1] - 1.0
        rvol = float(np.std(dr, ddof=1))
        abs5 = abs(c[T - 1] / c[T - 6] - 1.0)
        d_m1 = pd.Timestamp(px["Date"].values[T - 1])
        d_m21 = pd.Timestamp(px["Date"].values[T - 21])
        w = spy[(spy.index > d_m21) & (spy.index <= d_m1)]
        if len(w) < 5:
            dropped.append((r.ticker, r.event_day, "insufficient SPY coverage"))
            continue
        svol = float(np.std(w.values, ddof=1))

        hist = prior_abs.get(r.ticker, [])
        pm = float(np.mean(hist)) if hist else np.nan

        # strictly pre-event GST z-score
        gz = np.nan
        g = wk.get(r.ticker)
        if g is not None:
            closed = g[g["week_close"] < pd.Timestamp(r.event_day)]
            if len(closed) >= MIN_BASELINE_WEEKS + 1:
                latest = float(closed["value"].values[-1])
                base = closed["value"].values[-(BASELINE_WEEKS + 1):-1]
                if len(base) >= MIN_BASELINE_WEEKS and np.std(base, ddof=1) > 0:
                    gz = float((latest - np.mean(base)) / np.std(base, ddof=1))

        zs, anch = ref.get((r.ticker, str(r.earnings_date)[:10]), (np.nan, None))
        rows.append({
            "ticker": r.ticker, "event_day": r.event_day, "year": r.event_day[:4],
            "role": r.role, "bmo_amc": r.bmo_amc, "is_amc": 1.0 if r.bmo_amc == "AMC" else 0.0,
            "abs_gap": y,
            "prior_mean_abs_gap": pm, "realized_vol_20d": rvol, "abs_ret_5d": abs5,
            "spy_vol_20d": svol, "gst_z_pre": gz,
            "population_spike_zscore_reference_only": zs,
            "spike_anchor_reference_only": anch,
        })
        prior_abs.setdefault(r.ticker, []).append(y)

    d = pd.DataFrame(rows)
    before = len(d)
    d = d.dropna(subset=BASE_FEATURES + [GST_FEATURE]).reset_index(drop=True)
    info = {
        "rows_in_source": int(n_raw), "unique_event_identities": int(len(ev)),
        "duplicate_rows_removed": int(n_raw - len(ev)),
        "built": int(before), "usable_after_feature_completeness": int(len(d)),
        "dropped_incomplete_features": int(before - len(d)),
        "drop_reasons": pd.Series([x[2] for x in dropped]).value_counts().to_dict() if dropped else {},
    }
    return d, info


def fit_fold(tr: pd.DataFrame, te: pd.DataFrame, feats: list[str]) -> np.ndarray:
    Xtr, Xte = tr[feats].values.astype(float), te[feats].values.astype(float)
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    m = Ridge(alpha=RIDGE_ALPHA, random_state=None)
    m.fit((Xtr - mu) / sd, tr.abs_gap.values)
    return m.predict((Xte - mu) / sd)


def scores(y: np.ndarray, p: np.ndarray, y_base: np.ndarray) -> dict:
    mae = float(np.mean(np.abs(y - p)))
    rmse = float(math.sqrt(np.mean((y - p) ** 2)))
    ss = float(np.sum((y - p) ** 2))
    ss0 = float(np.sum((y - y_base) ** 2))
    return {"n": int(len(y)), "mae_pp": round(100 * mae, 4), "rmse_pp": round(100 * rmse, 4),
            "r2_vs_intercept": round(1 - ss / ss0, 5) if ss0 > 0 else None}


def cr2_paired(d: pd.DataFrame, col: str) -> dict:
    # INTERCEPT-ONLY design, clustered by ticker: this is a test of the MEAN paired
    # loss difference. Adding ticker dummies here would saturate the model at the
    # cluster level - each cluster would get its own mean, within-cluster residuals
    # would vanish, and the CR2 adjustment would degenerate to a zero standard error.
    y = 100 * d[col].values.astype(float)
    X = np.ones((len(d), 1))
    g = d.ticker.values
    beta, V, G = cr_vcov(X, y, g, "CR2")
    c = np.array([1.0])
    se = float(math.sqrt(max(c @ V @ c, 0.0)))
    dfree = satterthwaite_df(X, g, c)
    b = float(beta[0]); t = b / se if se > 0 else float("nan")
    from scipy import stats
    return {"n": int(len(d)), "n_clusters": int(G), "vcov": "CR2 (BRL)",
            "df_method": "coefficient-specific Satterthwaite", "cluster_unit": "ticker",
            "mean_loss_difference_pp": round(b, 5), "cr2_se_pp": round(se, 5),
            "satterthwaite_df": round(dfree, 3), "t_stat": round(t, 3),
            "p_value": round(float(2 * stats.t.sf(abs(t), dfree)), 5),
            "ci95_pp": [round(b - stats.t.ppf(.975, dfree) * se, 5),
                        round(b + stats.t.ppf(.975, dfree) * se, 5)],
            "positive_means_gst_reduces_error": True}


def quintile_table(y: np.ndarray, p: np.ndarray) -> list[dict]:
    q = pd.qcut(pd.Series(p), 5, labels=False, duplicates="drop")
    out = []
    for k in sorted(pd.Series(q).dropna().unique()):
        m = (q == k).values
        out.append({"quintile": int(k) + 1, "n": int(m.sum()),
                    "mean_predicted_pp": round(100 * float(p[m].mean()), 4),
                    "mean_realized_pp": round(100 * float(y[m].mean()), 4)})
    return out


def main() -> int:
    d, info = build()
    res: dict = {
        "artifact": "RETROSPECTIVE_MAGNITUDE_FORECAST_RESULTS", "version": "1.0",
        "status": "RETROSPECTIVE_DEVELOPMENT_ONLY", "confirms_hyp01": False,
        "evaluates_directional_trading_or_profitability": False,
        "outcome": "abs(open(T)/close(T-1) - 1)",
        "baseline_features": BASE_FEATURES, "gst_feature": GST_FEATURE,
        "model": f"ridge(alpha={RIDGE_ALPHA}), fixed; no model, threshold or hyperparameter search",
        "validation": "chronological expanding window; 2023/2024/2025 folds, as PR #23",
        "primary_metric": "out-of-sample MAE",
        "gst_feature_definition": (
            "z of the latest weekly GST observation whose week CLOSES strictly before the "
            f"event day, against the prior {BASELINE_WEEKS} such weeks "
            f"(minimum {MIN_BASELINE_WEEKS})"),
        "why_not_population_spike_zscore": (
            "the population's spike z-score spans a 14-day window anchored at the spike week "
            "while the maximum anchor-to-event lead here is 5 days, so its window always "
            "overlaps the announcement; 9 of 217 anchors fall on or after the event day. It "
            "would be lookahead, so it is kept for reference only and never enters a model."),
        "sample": info,
    }

    folds, rowsets = [], []
    for te_year in TEST_YEARS:
        tr, te = d[d.year < te_year], d[d.year == te_year]
        if len(tr) < 30 or len(te) == 0:
            folds.append({"test_year": te_year, "status": "SKIPPED", "n_train": int(len(tr)),
                          "n_test": int(len(te))})
            continue
        base_mean = float(tr.abs_gap.mean())
        pa = np.full(len(te), base_mean)
        pb = fit_fold(tr, te, BASE_FEATURES)
        pc = fit_fold(tr, te, BASE_FEATURES + [GST_FEATURE])
        t2 = te.copy()
        t2["pred_A"], t2["pred_B"], t2["pred_C"] = pa, pb, pc
        rowsets.append(t2)
        folds.append({"test_year": te_year, "n_train": int(len(tr)), "n_test": int(len(te)),
                      "train_mean_abs_gap_pp": round(100 * base_mean, 4),
                      "A": scores(te.abs_gap.values, pa, pa),
                      "B": scores(te.abs_gap.values, pb, pa),
                      "C": scores(te.abs_gap.values, pc, pa)})
    res["folds"] = folds

    oos = pd.concat(rowsets, ignore_index=True)
    y = oos.abs_gap.values
    res["pooled_out_of_sample"] = {
        "A_intercept_only": scores(y, oos.pred_A.values, oos.pred_A.values),
        "B_baseline_no_gst": scores(y, oos.pred_B.values, oos.pred_A.values),
        "C_baseline_plus_gst": scores(y, oos.pred_C.values, oos.pred_A.values),
    }
    mae_b = res["pooled_out_of_sample"]["B_baseline_no_gst"]["mae_pp"]
    mae_c = res["pooled_out_of_sample"]["C_baseline_plus_gst"]["mae_pp"]
    res["mae_improvement_pct"] = round(100 * (mae_b - mae_c) / mae_b, 4)

    # decisive paired loss difference: |err B| - |err C|
    oos["abs_err_B"] = np.abs(y - oos.pred_B.values)
    oos["abs_err_C"] = np.abs(y - oos.pred_C.values)
    oos["loss_diff"] = oos.abs_err_B - oos.abs_err_C
    res["decisive_paired_loss_difference"] = {
        "definition": "abs_error(B, no GST) - abs_error(C, with GST); positive = GST helps",
        "mean_pp": round(100 * float(oos.loss_diff.mean()), 5),
        "median_pp": round(100 * float(oos.loss_diff.median()), 5),
        "share_events_gst_better_pct": round(100 * float((oos.loss_diff > 0).mean()), 2),
        "clustered": cr2_paired(oos, "loss_diff"),
    }
    res["calibration_by_predicted_quintile"] = {
        "B_baseline_no_gst": quintile_table(y, oos.pred_B.values),
        "C_baseline_plus_gst": quintile_table(y, oos.pred_C.values),
    }
    for k, pcol in (("B_baseline_no_gst", "pred_B"), ("C_baseline_plus_gst", "pred_C")):
        q = res["calibration_by_predicted_quintile"][k]
        top, overall = q[-1]["mean_realized_pp"], 100 * float(y.mean())
        res.setdefault("top_quintile_lift", {})[k] = {
            "top_quintile_mean_realized_pp": top, "overall_mean_realized_pp": round(overall, 4),
            "lift_ratio": round(top / overall, 4)}
    res["yearly_stability"] = {f["test_year"]: {"A_mae": f["A"]["mae_pp"], "B_mae": f["B"]["mae_pp"],
                                                "C_mae": f["C"]["mae_pp"]}
                               for f in folds if "A" in f}

    cl = res["decisive_paired_loss_difference"]["clustered"]
    res["gst_adds_out_of_sample_predictive_value"] = bool(cl["p_value"] < 0.05 and cl["mean_loss_difference_pp"] > 0)
    res["conclusion"] = ("GST_IMPROVES_MAGNITUDE_FORECAST" if res["gst_adds_out_of_sample_predictive_value"]
                         else "GST_DOES_NOT_IMPROVE_MAGNITUDE_FORECAST")

    oos[["ticker", "event_day", "year", "abs_gap", "gst_z_pre", "pred_A", "pred_B", "pred_C",
         "abs_err_B", "abs_err_C", "loss_diff"]].to_csv(
        ROOT / "Live Signal Engine" / "retrospective_magnitude_oos_predictions.csv", index=False)
    (ROOT / "RETROSPECTIVE_MAGNITUDE_FORECAST_RESULTS_v1.0.json").write_text(
        json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")

    P = res["pooled_out_of_sample"]
    print(f"OOS n={len(oos)}  (from {info['usable_after_feature_completeness']} usable events)")
    for k in P:
        print(f"  {k:22s} MAE={P[k]['mae_pp']:.4f}pp RMSE={P[k]['rmse_pp']:.4f}pp R2={P[k]['r2_vs_intercept']}")
    print(f"  MAE improvement B->C: {res['mae_improvement_pct']}%")
    print(f"  paired loss diff: {cl['mean_loss_difference_pp']} pp  SE {cl['cr2_se_pp']} "
          f"t={cl['t_stat']} p={cl['p_value']} CI {cl['ci95_pp']}")
    print(f"  CONCLUSION: {res['conclusion']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
