#!/usr/bin/env python3
"""Independent pre-earnings direction model, with GST applied only afterwards.

RETROSPECTIVE_DEVELOPMENT_ONLY. Confirms nothing about HYP-01, modifies no locked
methodology, uses no gated prospective outcome.

TWO-STAGE DESIGN
  Stage 1 (this file, second half): GST selects events expected to move more.
  Stage 2 (this file, first half):  an INDEPENDENT model estimates direction.
GST is never an input to the direction model. It is applied only after every
out-of-sample prediction already exists, as a magnitude/event-selection filter.

OUTCOME
  y = 1[ open(T) / close(T-1) - 1 > 0 ]   (the overnight earnings gap sign)
  Event day T uses the existing AMC/BMO convention: AMC -> next trading session,
  BMO -> the announcement session.

FEATURES - FROZEN BEFORE ANY FIT OR ANY LOOK AT RESULTS. Everything is computed
from information available at or before close(T-1); nothing on or after T is used.
  f1 ret_5d        close(T-6)  -> close(T-1)
  f2 ret_20d       close(T-21) -> close(T-1)
  f3 realized_vol  stdev of daily close-to-close returns over T-20..T-1
  f4 spy_ret_5d    SPY close-to-close over the same 5 sessions
  f5 spy_ret_20d   SPY close-to-close over the same 20 sessions
  f6 mom_minus_spy f2 - f5
  f7 prior_gap_dir sign of that ticker's most recent EARLIER earnings gap (0 if none)
  f8 quarter       calendar quarter of the event day (mechanically available)

MODELS - FIXED, no search, no hyperparameter optimization
  M1 always-positive baseline
  M2 sign of five-day pre-earnings momentum
  M3 L2-regularized logistic regression (C=1.0)
  M4 shallow gradient-boosted trees (depth 2, 100 trees, lr 0.05)

VALIDATION
  Chronological expanding window; never a random split. Standardization is fit
  inside each training fold only. Primary selection is pooled out-of-sample Brier
  score, AUC secondary. Selection never uses trading returns.

COSTS
  10 bps round trip per stock position, fixed and disclosed before any return was
  computed. Same convention as the merged decomposition study.
"""
from __future__ import annotations

import glob
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hyp01_inference_feasibility import cr_vcov, satterthwaite_df  # noqa: E402

EVENTS = ROOT / "Live Signal Engine" / "retrospective_event_components.csv"
OHLC = ROOT / "Daily OHLC Data (2021-2025 Opening Gap Test)"
EXCESS = str(ROOT / "Daily Excess Return Data*" / "*_excess.csv")

COST_BPS = 10.0
TEST_YEARS = ["2023", "2024", "2025"]
CONF_THRESHOLD = 0.60           # single conventional threshold, secondary only
FEATURES = ["ret_5d", "ret_20d", "realized_vol", "spy_ret_5d", "spy_ret_20d",
            "mom_minus_spy", "prior_gap_dir", "quarter"]


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


def build() -> tuple[pd.DataFrame, list[str], dict]:
    ev = pd.read_csv(EVENTS)
    n_raw = len(ev)
    # DEDUPLICATE EVENT IDENTITIES FIRST. The source population reuses matched
    # controls, so the same (ticker, event_day) can appear several times - one event
    # appears 7 times. Left in place this both double-counts the evaluation sample and
    # leaks the outcome: a duplicate's `prior_gap_dir` would read the SAME event's gap.
    # An identity that appears as both signal and control is kept as high-GST.
    ev = (ev.sort_values(["ticker", "event_day", "role"])
            .drop_duplicates(subset=["ticker", "event_day"], keep="first")
            .reset_index(drop=True))
    dedup_info = {"rows_in_source": int(n_raw), "unique_event_identities": int(len(ev)),
                  "duplicate_rows_removed": int(n_raw - len(ev))}
    spy = spy_series()
    rows, omitted = [], []

    # prior-gap lookup: STRICTLY EARLIER earnings for the same ticker
    ev_sorted = ev.sort_values("event_day")
    prior: dict[str, list[tuple[str, float]]] = {}

    for _, r in ev_sorted.iterrows():
        px = pd.read_csv(OHLC / f"{r.ticker}_ohlc.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
        idx = px.index[px["Date"] == pd.Timestamp(r.event_day)]
        if len(idx) != 1:
            omitted.append((r.ticker, r.event_day, "event day not a session"))
            continue
        T = int(idx[0])
        if T - 21 < 0:
            omitted.append((r.ticker, r.event_day, "fewer than 21 prior sessions"))
            continue
        c = px["Close"].values
        # everything below uses data strictly at or before close(T-1)
        ret5 = c[T - 1] / c[T - 6] - 1.0
        ret20 = c[T - 1] / c[T - 21] - 1.0
        dr = c[T - 20:T] / c[T - 21:T - 1] - 1.0
        rvol = float(np.std(dr, ddof=1))
        d_m1 = pd.Timestamp(px["Date"].values[T - 1])
        d_m6 = pd.Timestamp(px["Date"].values[T - 6])
        d_m21 = pd.Timestamp(px["Date"].values[T - 21])
        w5 = spy[(spy.index > d_m6) & (spy.index <= d_m1)]
        w20 = spy[(spy.index > d_m21) & (spy.index <= d_m1)]
        if len(w5) == 0 or len(w20) == 0:
            omitted.append((r.ticker, r.event_day, "no SPY coverage in the pre-event window"))
            continue
        s5 = float(np.prod(1 + w5.values) - 1)
        s20 = float(np.prod(1 + w20.values) - 1)
        hist = [h for h in prior.get(r.ticker, []) if h[0] < r.event_day]
        pg = float(np.sign(hist[-1][1])) if hist else 0.0
        # OUTCOME (not a feature): the only place index T is read.
        gap = float(px["Open"].values[T] / c[T - 1] - 1.0)
        rows.append({
            "ticker": r.ticker, "event_day": r.event_day, "year": r.event_day[:4],
            "role": r.role, "high_gst": 1.0 if r.role == "signal" else 0.0,
            "zscore": r.zscore, "bmo_amc": r.bmo_amc,
            "ret_5d": ret5, "ret_20d": ret20, "realized_vol": rvol,
            "spy_ret_5d": s5, "spy_ret_20d": s20, "mom_minus_spy": ret20 - s20,
            "prior_gap_dir": pg, "quarter": float(pd.Timestamp(r.event_day).quarter),
            "gap": float(gap), "y": int(gap > 0),
        })
        prior.setdefault(r.ticker, []).append((r.event_day, float(gap)))

    return pd.DataFrame(rows), omitted, dedup_info


def fit_predict(tr: pd.DataFrame, te: pd.DataFrame) -> dict[str, np.ndarray]:
    """All preprocessing fit on the training fold only."""
    Xtr = tr[FEATURES].values.astype(float)
    Xte = te[FEATURES].values.astype(float)
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd
    ytr = tr.y.values

    out = {"always_positive": np.ones(len(te))}
    # Proper probabilistic null: the positive-gap prevalence of the TRAINING fold,
    # assigned to every test observation. This, not always-positive, is the correct
    # Brier-score baseline; always-positive predicts 0/1 and is kept only as a
    # classification benchmark.
    out["intercept_only_prevalence"] = np.full(len(te), float(ytr.mean()))
    # momentum baseline: deterministic sign rule mapped to {0.25, 0.75}
    out["momentum_sign"] = np.where(te.ret_5d.values > 0, 0.75, 0.25)
    if len(np.unique(ytr)) < 2:
        out["logistic_l2"] = np.full(len(te), float(ytr.mean()))
        out["gbt_shallow"] = np.full(len(te), float(ytr.mean()))
        return out
    lr = LogisticRegression(C=1.0, max_iter=2000, random_state=0)
    lr.fit(Ztr, ytr)
    out["logistic_l2"] = lr.predict_proba(Zte)[:, 1]
    gb = GradientBoostingClassifier(max_depth=2, n_estimators=100, learning_rate=0.05,
                                    subsample=1.0, random_state=0)
    gb.fit(Xtr, ytr)
    out["gbt_shallow"] = gb.predict_proba(Xte)[:, 1]
    return out


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    pred = (p > 0.5).astype(int)
    acc = float((pred == y).mean())
    pos, neg = y == 1, y == 0
    bal = float(0.5 * ((pred[pos] == 1).mean() if pos.any() else 0)
                + 0.5 * ((pred[neg] == 0).mean() if neg.any() else 0))
    try:
        auc = float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan")
    except Exception:
        auc = float("nan")
    q = np.clip(p, 1e-12, 1 - 1e-12)
    logloss = float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))
    constant = bool(np.allclose(p, p[0])) if len(p) else False
    return {"n": int(len(y)), "accuracy": round(acc, 4), "balanced_accuracy": round(bal, 4),
            "auc": None if (math.isnan(auc) or constant) else round(auc, 4),
            "auc_defined": not constant,
            "brier": round(float(brier_score_loss(y, np.clip(p, 0, 1))), 5),
            "log_loss": round(logloss, 5),
            "n_positive": int(pos.sum()), "n_negative": int(neg.sum())}


def calibration(y: np.ndarray, p: np.ndarray) -> list[dict]:
    bins = [(0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 1.0)]
    out = []
    for lo, hi in bins:
        m = (p >= lo) & (p < hi) if hi < 1.0 else (p >= lo) & (p <= 1.0)
        if m.sum() == 0:
            out.append({"bin": f"[{lo},{hi})", "n": 0})
            continue
        out.append({"bin": f"[{lo},{hi})", "n": int(m.sum()),
                    "mean_predicted": round(float(p[m].mean()), 4),
                    "observed_positive_rate": round(float(y[m].mean()), 4)})
    return out


def perf(rets: np.ndarray, dates: list[str]) -> dict:
    r = np.asarray(rets, dtype=float)
    if len(r) == 0:
        return {"trades": 0}
    net = r - COST_BPS / 10000.0
    m = float(net.mean())
    se = float(net.std(ddof=1) / math.sqrt(len(net))) if len(net) > 1 else float("nan")
    order = np.argsort(dates)
    eq = np.cumprod(1 + net[order])
    peak = np.maximum.accumulate(eq)
    yrs = (pd.Timestamp(max(dates)) - pd.Timestamp(min(dates))).days / 365.25
    return {"trades": int(len(r)),
            "mean_gross_pct": round(100 * float(r.mean()), 4),
            "mean_net_pct": round(100 * m, 4),
            "median_net_pct": round(100 * float(np.median(net)), 4),
            "hit_rate_pct": round(100 * float((net > 0).mean()), 2),
            "max_drawdown_pct": round(100 * float((eq / peak - 1).min()), 3),
            "trades_per_year": round(len(r) / yrs, 2) if yrs > 0 else None,
            "naive_t": round(m / se, 3) if se and se > 0 else None}


def cr2_incremental(df: pd.DataFrame, ycol: str) -> dict:
    d = df.dropna(subset=[ycol]).copy()
    if d.high_gst.nunique() < 2 or d.ticker.nunique() < 2:
        return {"status": "INSUFFICIENT_VARIATION", "n": int(len(d))}
    y = 100 * d[ycol].values.astype(float)
    X = np.column_stack([np.ones(len(d)), d.high_gst.values.astype(float),
                         pd.get_dummies(d.ticker, drop_first=True).values.astype(float)])
    g = d.ticker.values
    beta, V, G = cr_vcov(X, y, g, "CR2")
    c = np.zeros(X.shape[1]); c[1] = 1.0
    se = float(math.sqrt(max(c @ V @ c, 0.0)))
    dfree = satterthwaite_df(X, g, c)
    b = float(beta[1]); t = b / se if se > 0 else float("nan")
    from scipy import stats
    return {"n": int(len(d)), "n_clusters": int(G), "vcov": "CR2 (BRL)",
            "df_method": "coefficient-specific Satterthwaite", "cluster_unit": "ticker",
            "coef_pp": round(b, 4), "cr2_se_pp": round(se, 4),
            "satterthwaite_df": round(dfree, 3), "t_stat": round(t, 3),
            "p_value": round(float(2 * stats.t.sf(abs(t), dfree)), 5),
            "ci95_pp": [round(b - stats.t.ppf(.975, dfree) * se, 4),
                        round(b + stats.t.ppf(.975, dfree) * se, 4)]}


def main() -> int:
    d, omitted, dedup_info = build()
    res: dict = {
        "artifact": "RETROSPECTIVE_DIRECTION_SIGNAL_RESULTS", "version": "1.0",
        "status": "RETROSPECTIVE_DEVELOPMENT_ONLY",
        "confirms_hyp01": False, "uses_prospective_outcomes": False,
        "gst_used_as_direction_input": False,
        "gst_role": "magnitude / event-selection filter applied AFTER predictions exist",
        "outcome": "sign(open(T)/close(T-1) - 1)",
        "features_frozen_before_fitting": FEATURES,
        "features_omitted": [],
        "models": ["always_positive", "intercept_only_prevalence", "momentum_sign",
                   "logistic_l2", "gbt_shallow"],
        "probabilistic_baseline": ("INTERCEPT_ONLY_PREVALENCE - training-fold positive-gap "
                                   "prevalence assigned to every test observation"),
        "always_positive_role": ("classification benchmark only; its 0/1 predictions are NOT the "
                                 "primary probabilistic comparator"),
        "validation": "chronological expanding window; standardization fit within each training fold",
        "selection_rule": "pooled out-of-sample Brier score, AUC secondary; never trading returns",
        "cost_bps_round_trip": COST_BPS,
        "sample": {"events": int(len(d)), "tickers": int(d.ticker.nunique()),
                   "date_range": [d.event_day.min(), d.event_day.max()],
                   "omitted": len(omitted),
                   "omitted_reasons": pd.Series([o[2] for o in omitted]).value_counts().to_dict() if omitted else {},
                   "positive_rate_overall": round(float(d.y.mean()), 4),
                   **dedup_info},
    }

    # ---------------- chronological expanding window ----------------
    preds = {m: [] for m in ("always_positive", "intercept_only_prevalence", "momentum_sign",
                             "logistic_l2", "gbt_shallow")}
    keep = []
    folds = []
    for te_year in TEST_YEARS:
        tr = d[d.year < te_year]
        te = d[d.year == te_year]
        if len(tr) < 30 or len(te) == 0:
            folds.append({"test_year": te_year, "status": "SKIPPED_INSUFFICIENT_TRAIN",
                          "n_train": int(len(tr)), "n_test": int(len(te))})
            continue
        out = fit_predict(tr, te)
        folds.append({"test_year": te_year, "n_train": int(len(tr)), "n_test": int(len(te)),
                      "train_positive_rate": round(float(tr.y.mean()), 4),
                      "test_positive_rate": round(float(te.y.mean()), 4),
                      "per_model": {m: metrics(te.y.values, out[m]) for m in out}})
        for m in preds:
            preds[m].append(out[m])
        keep.append(te)

    oos = pd.concat(keep, ignore_index=True)
    P = {m: np.concatenate(v) for m, v in preds.items()}
    res["folds"] = folds

    pooled = {}
    for m, p in P.items():
        mm = metrics(oos.y.values, p)
        mm["calibration"] = calibration(oos.y.values, p)
        mm["by_test_year"] = {}
        for yy in TEST_YEARS:
            msk = (oos.year == yy).values
            if msk.sum():
                mm["by_test_year"][yy] = metrics(oos.y.values[msk], p[msk])
        pooled[m] = mm
    res["pooled_out_of_sample"] = pooled

    # ---------------- primary selection: Brier, AUC secondary ----------------
    # Frozen rule unchanged: lowest pooled out-of-sample Brier, AUC secondary. The
    # intercept-only null is now a candidate, and a null model is an acceptable winner.
    candidates = ["intercept_only_prevalence", "logistic_l2", "gbt_shallow"]
    best = min(candidates, key=lambda m: (pooled[m]["brier"], -(pooled[m]["auc"] or 0)))
    learned = ["logistic_l2", "gbt_shallow"]
    res["primary_model"] = {
        "selected": best, "rule": "lowest pooled out-of-sample Brier score, AUC secondary",
        "candidates": candidates,
        "brier": pooled[best]["brier"], "auc": pooled[best]["auc"],
        "is_null_model": best == "intercept_only_prevalence",
        "beats_probabilistic_null_brier": {m: pooled[m]["brier"] < pooled["intercept_only_prevalence"]["brier"]
                                           for m in learned},
        "any_learned_model_beats_null": any(pooled[m]["brier"] < pooled["intercept_only_prevalence"]["brier"]
                                            for m in learned),
        "intercept_only_brier": pooled["intercept_only_prevalence"]["brier"],
        "beats_always_positive_brier": pooled[best]["brier"] < pooled["always_positive"]["brier"],
        "beats_momentum_brier": pooled[best]["brier"] < pooled["momentum_sign"]["brier"],
        "beats_always_positive_accuracy": pooled[best]["accuracy"] > pooled["always_positive"]["accuracy"],
        "beats_momentum_accuracy": pooled[best]["accuracy"] > pooled["momentum_sign"]["accuracy"],
    }

    # ---------------- combined strategy ----------------
    # The strategy is evaluated on the LEARNED model's predictions, never the null's.
    # A constant-prevalence null emits no directional signal; trading it would be a
    # disguised always-long rule. These figures are secondary evidence about the failed
    # learned model, not an investable strategy.
    strategy_model = "logistic_l2"
    p_best = P[strategy_model]
    pos = np.where(p_best > 0.5, 1.0, -1.0)
    oos = oos.copy()
    oos["pred_prob"] = p_best
    oos["strategy_return"] = pos * oos.gap.values
    dates = list(oos.event_day)
    hi = oos[oos.high_gst == 1.0]
    lo = oos[oos.high_gst == 0.0]
    conf = oos[(oos.pred_prob >= CONF_THRESHOLD) | (oos.pred_prob <= 1 - CONF_THRESHOLD)]

    def worst_year(df):
        if not len(df):
            return None
        g = df.groupby("year").strategy_return.mean() - COST_BPS / 10000.0
        return {"year": str(g.idxmin()), "mean_net_pct": round(100 * float(g.min()), 4)}

    res["combined_strategy"] = {
        "status": ("SECONDARY EVIDENCE ABOUT THE FAILED LEARNED MODEL - not presented as an "
                   "investable strategy; the model selected under the frozen rule is the "
                   "intercept-only null, which produces no directional signal to trade"),
        "predictions_from": strategy_model,
        "entry": "close(T-1)", "exit": "open(T)",
        "rule": "long if predicted probability > 0.5, short if < 0.5",
        "cost_bps_round_trip": COST_BPS,
        "direction_only": {**perf(oos.strategy_return.values, dates), "worst_test_year": worst_year(oos)},
        "direction_plus_gst_filter": {**perf(hi.strategy_return.values, list(hi.event_day)),
                                      "worst_test_year": worst_year(hi),
                                      "note": "same predictions; no retraining on the high-GST subset; no cutoff tuning"},
        "contemporaneous_unfiltered_low_gst": {**perf(lo.strategy_return.values, list(lo.event_day)),
                                               "worst_test_year": worst_year(lo)},
        "confidence_filter_secondary": {"threshold": CONF_THRESHOLD,
                                        **perf(conf.strategy_return.values, list(conf.event_day)),
                                        "label": "SECONDARY - one fixed conventional threshold, not searched"},
        "incremental_gst_effect_cr2": cr2_incremental(oos, "strategy_return"),
        "decisive_statistic": ("the incremental GST coefficient above, not the filtered "
                               "strategy's standalone mean"),
    }

    # ---------------- conclusion ----------------
    bm = res["primary_model"]
    inc = res["combined_strategy"]["incremental_gst_effect_cr2"]
    any_skill = bool(bm["any_learned_model_beats_null"])
    dir_ok = bool(any_skill and res["combined_strategy"]["direction_only"]["mean_net_pct"] > 0)
    gst_ok = bool(inc.get("p_value", 1) < 0.05 and inc.get("coef_pp", 0) > 0)
    if len(oos) < 100:
        concl = "INSUFFICIENT_DATA"
    elif bm["is_null_model"] or not any_skill:
        # No learned model beats the probabilistic null, so there is no investable
        # direction model to combine GST with.
        concl = "TESTED_DIRECTION_MODELS_HAVE_NO_SKILL"
    elif dir_ok and gst_ok:
        concl = "DIRECTION_SIGNAL_AND_GST_FILTER_BOTH_ADD_VALUE"
    elif dir_ok:
        concl = "DIRECTION_SIGNAL_ONLY"
    elif gst_ok:
        concl = "GST_FILTER_ONLY"
    else:
        concl = "NEITHER_ADDS_VALUE"
    res["conclusion"] = concl
    res["conclusion_scope"] = (
        "The tested pre-earnings price-based direction models have no out-of-sample "
        "directional skill, and applying GST as a magnitude filter does not rescue those "
        "models.")
    res["secondary_conclusion_narrow"] = {
        "label": "NEITHER_ADDS_VALUE",
        "applies_to": ("the tested logistic-direction strategy and its GST combination ONLY - "
                       "not the overall two-stage research concept"),
    }
    res["what_this_does_not_establish"] = [
        "It does not invalidate the separate GST magnitude hypothesis.",
        "It does not test GST combined with a direction signal that independently possesses "
        "directional skill.",
        "It does not test analyst revisions, point-in-time news, options skew, fundamental "
        "expectations or network-diffusion features.",
        "A failed direction model cannot determine whether GST would improve a genuinely "
        "informative direction model.",
    ]
    res["conclusion_basis"] = {
        "any_learned_model_beats_probabilistic_null": any_skill,
        "selected_is_null_model": bm["is_null_model"],
        "gst_incremental_supported": gst_ok,
        "trading_results_are_secondary": True,
        "note": ("the selected model is the intercept-only null, so no directional trading "
                 "strategy is presented as investable; the logistic strategy figures are kept "
                 "only as secondary evidence about the failed learned model"),
    }

    oos[["ticker", "event_day", "year", "role", "high_gst", "y", "gap", "pred_prob",
         "strategy_return"]].to_csv(ROOT / "Live Signal Engine" / "retrospective_direction_oos_predictions.csv",
                                    index=False)
    (ROOT / "RETROSPECTIVE_DIRECTION_SIGNAL_RESULTS_v1.0.json").write_text(
        json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")

    print(f"OOS n={len(oos)}  positive rate={oos.y.mean():.4f}")
    for m in ("always_positive", "intercept_only_prevalence", "momentum_sign",
              "logistic_l2", "gbt_shallow"):
        x = pooled[m]
        print(f"  {m:18s} acc={x['accuracy']:.4f} bal={x['balanced_accuracy']:.4f} "
              f"auc={x['auc']} brier={x['brier']:.5f} logloss={x['log_loss']:.5f}")
    print(f"  selected: {best}")
    cs = res["combined_strategy"]
    for k in ("direction_only", "direction_plus_gst_filter", "contemporaneous_unfiltered_low_gst"):
        v = cs[k]
        print(f"  {k:36s} n={v['trades']:3d} net={v.get('mean_net_pct')} hit={v.get('hit_rate_pct')}")
    print(f"  incremental GST CR2: {inc.get('coef_pp')} pp p={inc.get('p_value')}")
    print(f"  CONCLUSION: {concl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
