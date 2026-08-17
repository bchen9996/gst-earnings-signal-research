#!/usr/bin/env python3
"""Attention-Activity Mismatch: does search add out-of-sample information only when
trading activity suggests the attention is not already reflected in activity?

EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY. Not HYP-01 confirmation, not prospective
collection. Modifies no lock, registry, protocol, universe constant or prior result.

INTERPRETATION GUARD. The measured variable is a SEARCH-TRADING-ACTIVITY MISMATCH
PROXY. "Unabsorbed attention" is an interpretation, not a measurement, and nothing here
establishes market absorption or causality. Google Trends remains a CANDIDATE proxy:
F5 construct validity is open, so it is not validated investor attention.

POINT-IN-TIME CAVEAT. Historical Google Trends downloads are NOT point-in-time vintages.
Google rescales to the requested window and may revise sampling, so the series used here
may differ from what was observable contemporaneously.

TIMELINE (executable, no target-week information in any feature)
  Trends week t starts Sunday and CLOSES the following Saturday.
  Features use information through the close of week t only.
  Target week t+1 runs Monday open -> Friday close, strictly after week t closes.
  Return target    excess = (Fri close / Mon open - 1) - same-window SPY return
  Volatility target log realized vol of target-week DAILY open-to-close returns
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Live Signal Engine" / "Attention_Activity_Mismatch"
OUT.mkdir(parents=True, exist_ok=True)
PANEL = OUT / "weekly_panel_v1.0.csv"
SPY_CSV = OUT / "spy_daily_v1.0.csv"
RESULTS = ROOT / "ATTENTION_ACTIVITY_MISMATCH_RESULTS_v1.0.json"

OHLC_DIR = ROOT / "Daily OHLC Data (2021-2025 Opening Gap Test)"
VOL_DIR = ROOT / "Daily Volume Data (2021-2025)"
AUDIT = ROOT / "Live Signal Engine" / "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json"
C5 = ROOT / "Live Signal Engine" / "C5_PostEarnings_Population.csv"

ROLL = 52
TEST_YEARS = ["2023", "2024", "2025"]
RIDGE_GRID = [0.1, 1.0, 10.0, 100.0]
LOGIT_GRID = [0.01, 0.1, 1.0, 10.0]
BOOT_DRAWS, BLOCK = 2000, 4
SEED = 20260817
MIN_TICKERS, MIN_WEEKS, MIN_OBS = 18, 100, 1800

BASE_F = ["ret_1w", "ret_4w", "absret_1w", "vol_4w", "volume_z", "spy_ret_1w", "spy_vol_4w"]
VOL_C_EXTRA = ["search_z", "search_x_volume"]
R1_EXTRA = ["search_z", "search_x_ret1w", "search_x_volume", "search_x_volume_x_ret1w"]


def fetch_spy() -> pd.DataFrame:
    if SPY_CSV.exists():
        return pd.read_csv(SPY_CSV, parse_dates=["Date"])
    p1 = int(pd.Timestamp("2020-06-01").timestamp())
    p2 = int(pd.Timestamp("2026-01-10").timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/SPY"
           f"?period1={p1}&period2={p2}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (gst research)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        b = json.loads(r.read())
    res = b["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    d = pd.DataFrame({"Date": pd.to_datetime(res["timestamp"], unit="s").normalize(),
                      "Open": q["open"], "Close": q["close"]}).dropna()
    d = d.drop_duplicates("Date").sort_values("Date")
    d.to_csv(SPY_CSV, index=False, lineterminator="\n")
    return d


def weekly_gst(t: str) -> pd.DataFrame | None:
    fr = []
    for f in glob.glob(str(ROOT / "GST Data" / "Weekly Data*" / f"{t}_*.csv")):
        try:
            d = pd.read_csv(f)
        except Exception:
            continue
        if "Week" in d.columns and t in d.columns:
            fr.append(d[["Week", t]].rename(columns={t: "search"}))
    if not fr:
        return None
    d = pd.concat(fr, ignore_index=True)
    d["Week"] = pd.to_datetime(d["Week"])
    return d.dropna().drop_duplicates("Week").sort_values("Week").reset_index(drop=True)


def build_panel() -> tuple[pd.DataFrame, dict]:
    sys.path.insert(0, str(ROOT))
    from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE as U
    tickers = list(U)
    spy = fetch_spy()
    spy["wk"] = spy.Date - pd.to_timedelta(spy.Date.dt.weekday, unit="D")   # Monday label
    spy_wk = spy.groupby("wk").agg(o=("Open", "first"), c=("Close", "last"),
                                   n=("Close", "size")).reset_index()
    spy_wk["spy_ret"] = spy_wk.c / spy_wk.o - 1.0
    spy_daily_oc = spy.assign(oc=spy.Close / spy.Open - 1.0)
    spy_vol = spy_daily_oc.groupby("wk").oc.std(ddof=1).rename("spy_wvol").reset_index()
    spy_wk = spy_wk.merge(spy_vol, on="wk", how="left")

    rows, skipped = [], []
    for t in tickers:
        g = weekly_gst(t)
        pf, vf = OHLC_DIR / f"{t}_ohlc.csv", VOL_DIR / f"{t}_volume.csv"
        if g is None or not pf.exists() or not vf.exists():
            skipped.append((t, "missing series"))
            continue
        px = pd.read_csv(pf, parse_dates=["Date"]).sort_values("Date")
        vol = pd.read_csv(vf, parse_dates=["Date"]).sort_values("Date")
        px = px.merge(vol, on="Date", how="left")
        px["wk"] = px.Date - pd.to_timedelta(px.Date.dt.weekday, unit="D")
        wk = px.groupby("wk").agg(o=("Open", "first"), c=("Close", "last"),
                                  ndays=("Close", "size"), vsum=("Volume", "sum")).reset_index()
        oc = px.assign(oc=px.Close / px.Open - 1.0)
        wvol = oc.groupby("wk").oc.std(ddof=1).rename("wvol").reset_index()
        wk = wk.merge(wvol, on="wk", how="left")
        wk["ret"] = wk.c / wk.o - 1.0
        # Trends week label is Sunday-start; the trading week it PRECEDES starts the
        # next day (Monday). Shift by +1 day so a Trends week maps to the Monday that
        # opens the following trading week; its data is complete by the prior Saturday.
        g["wk"] = g.Week + pd.Timedelta(days=1)
        m = wk.merge(g[["wk", "search"]], on="wk", how="inner").merge(
            spy_wk[["wk", "spy_ret", "spy_wvol"]], on="wk", how="inner").sort_values("wk")
        m = m[m.ndays >= 3].reset_index(drop=True)

        # rolling stats use the PREVIOUS 52 weeks and EXCLUDE the current observation
        for col, out in (("search", "search_z"), ("vsum", "volume_z")):
            mu = m[col].shift(1).rolling(ROLL).mean()
            sd = m[col].shift(1).rolling(ROLL).std(ddof=1)
            m[out] = (m[col] - mu) / sd.replace(0, np.nan)
        m["ret_1w"] = m.ret
        m["ret_4w"] = m.c / m.o.shift(3) - 1.0
        m["absret_1w"] = m.ret.abs()
        m["vol_4w"] = m.wvol.shift(0).rolling(4).mean()
        m["spy_ret_1w"] = m.spy_ret
        m["spy_vol_4w"] = m.spy_wvol.rolling(4).mean()
        # TARGETS come from week t+1 only
        m["target_week"] = m.wk.shift(-1)
        m["y_exc"] = m.ret.shift(-1) - m.spy_ret.shift(-1)
        m["y_logvol"] = np.log(m.wvol.shift(-1).replace(0, np.nan))
        m["target_ndays"] = m.ndays.shift(-1)
        m["ticker"] = t
        rows.append(m)
    p = pd.concat(rows, ignore_index=True)
    p = p.dropna(subset=["target_week", "y_exc", "y_logvol"] + BASE_F + ["search_z"])
    p = p[p.target_ndays >= 3]
    p["search_x_volume"] = p.search_z * p.volume_z
    p["search_x_ret1w"] = p.search_z * p.ret_1w
    p["search_x_volume_x_ret1w"] = p.search_z * p.volume_z * p.ret_1w
    p["year"] = p.target_week.dt.year.astype(str)
    before = len(p)
    p = p.drop_duplicates(subset=["ticker", "target_week"], keep=False if False else "first")
    dup_removed = before - len(p)
    p = p.sort_values(["target_week", "ticker"]).reset_index(drop=True)
    return p, {"tickers_skipped": skipped, "duplicate_rows_removed": int(dup_removed)}


def design(tr, te, feats):
    tk_tr = pd.get_dummies(tr.ticker, prefix="tk")
    tk_te = pd.get_dummies(te.ticker, prefix="tk").reindex(columns=tk_tr.columns, fill_value=0)
    Xtr = np.column_stack([tr[feats].values.astype(float), tk_tr.values.astype(float)])
    Xte = np.column_stack([te[feats].values.astype(float), tk_te.values.astype(float)])
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    return (Xtr - mu) / sd, (Xte - mu) / sd, list(feats) + list(tk_tr.columns)


def fit_ridge(tr, te, feats):
    Ztr, Zte, names = design(tr, te, feats)
    y = tr.y_logvol.values
    best_a, best_s = RIDGE_GRID[0], np.inf
    for a in RIDGE_GRID:                       # chosen on TRAINING data only
        m = Ridge(alpha=a).fit(Ztr, y)
        s = float(np.mean(np.abs(y - m.predict(Ztr))))
        if s < best_s:
            best_a, best_s = a, s
    m = Ridge(alpha=best_a).fit(Ztr, y)
    return m.predict(Zte), dict(zip(names, m.coef_)), best_a


def fit_logit(tr, te, feats):
    Ztr, Zte, names = design(tr, te, feats)
    y = (tr.y_exc.values > 0).astype(int)
    best_c, best_s = LOGIT_GRID[0], np.inf
    for C in LOGIT_GRID:
        m = LogisticRegression(C=C, max_iter=3000, random_state=0).fit(Ztr, y)
        p = np.clip(m.predict_proba(Ztr)[:, 1], 1e-9, 1 - 1e-9)
        s = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
        if s < best_s:
            best_c, best_s = C, s
    m = LogisticRegression(C=best_c, max_iter=3000, random_state=0).fit(Ztr, y)
    return m.predict_proba(Zte)[:, 1], dict(zip(names, m.coef_[0])), best_c


def block_boot(df, loss_a, loss_b, seed=SEED):
    """Fixed-seed calendar-week block bootstrap: resample 4-week blocks, keep all
    tickers within each sampled week."""
    rng = np.random.default_rng(seed)
    weeks = np.array(sorted(df.target_week.unique()))
    idx = {w: np.where(df.target_week.values == w)[0] for w in weeks}
    diff = loss_a - loss_b
    nblk = max(1, len(weeks) // BLOCK)
    starts = np.arange(0, len(weeks) - BLOCK + 1)
    out = np.empty(BOOT_DRAWS)
    for b in range(BOOT_DRAWS):
        pick = rng.choice(starts, size=nblk, replace=True)
        sel = np.concatenate([idx[w] for s in pick for w in weeks[s:s + BLOCK]])
        out[b] = diff[sel].mean()
    return {"mean": float(diff.mean()),
            "ci95": [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))],
            "draws": BOOT_DRAWS, "block_weeks": BLOCK, "seed": seed,
            "entirely_above_zero": bool(np.percentile(out, 2.5) > 0)}


def run_folds(panel, feats_b, feats_c, kind):
    keep = []
    coefs = {"B": [], "C": []}
    for ty in TEST_YEARS:
        tr, te = panel[panel.year < ty], panel[panel.year == ty]
        if len(tr) < 500 or len(te) == 0:
            continue
        if kind == "vol":
            pb, cb, ab = fit_ridge(tr, te, feats_b)
            pc, cc, ac = fit_ridge(tr, te, feats_c)
        else:
            pb, cb, ab = fit_logit(tr, te, feats_b)
            pc, cc, ac = fit_logit(tr, te, feats_c)
        t2 = te.copy()
        t2["pred_b"], t2["pred_c"] = pb, pc
        t2["alpha_b"], t2["alpha_c"] = ab, ac
        keep.append(t2)
        coefs["B"].append(cb)
        coefs["C"].append(cc)
    return pd.concat(keep, ignore_index=True), coefs


def vol_metrics(d):
    y = d.y_logvol.values
    out = {}
    for k in ("b", "c"):
        p = d[f"pred_{k}"].values
        ss = float(np.sum((y - p) ** 2))
        ss0 = float(np.sum((y - y.mean()) ** 2))
        out[k.upper()] = {"mae": round(float(np.mean(np.abs(y - p))), 6),
                          "rmse": round(float(math.sqrt(np.mean((y - p) ** 2))), 6),
                          "r2_oos": round(1 - ss / ss0, 5)}
    return out


def ret_metrics(d, prevalence):
    y = (d.y_exc.values > 0).astype(int)
    out = {}
    for k in ("b", "c"):
        p = np.clip(d[f"pred_{k}"].values, 1e-9, 1 - 1e-9)
        ll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
        try:
            from sklearn.metrics import roc_auc_score
            auc = float(roc_auc_score(y, p))
        except Exception:
            auc = float("nan")
        out[k.upper()] = {"log_loss": round(ll, 6), "brier": round(float(np.mean((p - y) ** 2)), 6),
                          "auc": round(auc, 4), "accuracy": round(float(((p > .5) == y).mean()), 4)}
    pn = np.clip(prevalence, 1e-9, 1 - 1e-9)
    out["NULL_prevalence"] = {
        "log_loss": round(float(-np.mean(y * np.log(pn) + (1 - y) * np.log(1 - pn))), 6),
        "brier": round(float(np.mean((pn - y) ** 2)), 6),
        "accuracy": round(float(((pn > .5) == y).mean()), 4)}
    return out


def main() -> int:
    t0 = time.time()
    panel, meta = build_panel()
    panel.to_csv(PANEL, index=False, lineterminator="\n")
    oos = panel[panel.year.isin(TEST_YEARS)]
    gate = {"tickers": int(panel.ticker.nunique()),
            "oos_weeks": int(oos.target_week.nunique()),
            "oos_observations": int(len(oos)),
            "required": {"tickers": MIN_TICKERS, "oos_weeks": MIN_WEEKS, "oos_obs": MIN_OBS}}
    gate["passed"] = bool(gate["tickers"] >= MIN_TICKERS and gate["oos_weeks"] >= MIN_WEEKS
                          and gate["oos_observations"] >= MIN_OBS)

    res = {
        "artifact": "ATTENTION_ACTIVITY_MISMATCH_RESULTS", "version": "1.0",
        "status": "EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY",
        "hyp01_confirmation": False, "prospective_collection": False,
        "measured_variable": "search-trading-activity mismatch proxy",
        "interpretation_guard": ("'unabsorbed attention' is an interpretation, not a "
                                 "measurement; no absorption or causality is established"),
        "gst_status": "CANDIDATE proxy; F5 construct validity open; not validated investor attention",
        "point_in_time_caveat": ("historical Google Trends downloads are NOT point-in-time "
                                 "vintages and may reflect later revisions or rescaling"),
        "timeline": {"feature_cutoff": "close of Trends week t (Sunday-start, closes Saturday)",
                     "target_week": "t+1, Monday open to Friday close",
                     "return_target": "stock Mon-open->Fri-close minus same-window SPY",
                     "volatility_target": "log realized vol of target-week daily open-to-close returns"},
        "folds": [{"train_through": str(int(y) - 1), "test_year": y} for y in TEST_YEARS],
        "sample": {"panel_rows": int(len(panel)), "tickers": int(panel.ticker.nunique()),
                   "weeks": int(panel.target_week.nunique()),
                   "date_range": [str(panel.target_week.min().date()), str(panel.target_week.max().date())],
                   **meta},
        "minimum_data_gate": gate,
    }
    if not gate["passed"]:
        res["decision_label"] = "DATA_UNAVAILABLE"
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
        print("DATA_UNAVAILABLE", gate)
        return 0

    # ---------------- primary: volatility ----------------
    dv, cv = run_folds(panel, BASE_F, BASE_F + VOL_C_EXTRA, "vol")
    mv = vol_metrics(dv)
    lb = np.abs(dv.y_logvol.values - dv.pred_b.values)
    lc = np.abs(dv.y_logvol.values - dv.pred_c.values)
    impr = 100 * (mv["B"]["mae"] - mv["C"]["mae"]) / mv["B"]["mae"]
    boot_v = block_boot(dv, lb, lc)
    yearly_v = {}
    for ty in TEST_YEARS:
        s = dv[dv.year == ty]
        if len(s):
            a = float(np.mean(np.abs(s.y_logvol - s.pred_b)))
            b = float(np.mean(np.abs(s.y_logvol - s.pred_c)))
            yearly_v[ty] = {"B_mae": round(a, 6), "C_mae": round(b, 6), "C_better": bool(b < a)}
    res["volatility"] = {"metrics": mv, "mae_improvement_pct": round(impr, 4),
                         "paired_bootstrap_B_minus_C": boot_v, "by_year": yearly_v,
                         "n_oos": int(len(dv))}
    gv = {"improves_1pct": bool(impr >= 1.0),
          "ci_above_zero": boot_v["entirely_above_zero"],
          "beats_in_2of3_years": sum(v["C_better"] for v in yearly_v.values()) >= 2}
    res["volatility"]["gates"] = gv
    res["volatility"]["passes"] = bool(all(gv.values()))

    # ---------------- secondary: return direction ----------------
    dr, cr = run_folds(panel, BASE_F, BASE_F + R1_EXTRA, "ret")
    prev = float((panel[panel.year < TEST_YEARS[0]].y_exc > 0).mean())
    mr = ret_metrics(dr, prev)
    y = (dr.y_exc.values > 0).astype(int)
    l0 = -(y * np.log(np.clip(dr.pred_b, 1e-9, 1 - 1e-9))
           + (1 - y) * np.log(1 - np.clip(dr.pred_b, 1e-9, 1 - 1e-9)))
    l1 = -(y * np.log(np.clip(dr.pred_c, 1e-9, 1 - 1e-9))
           + (1 - y) * np.log(1 - np.clip(dr.pred_c, 1e-9, 1 - 1e-9)))
    boot_r = block_boot(dr, l0.values if hasattr(l0, "values") else l0,
                        l1.values if hasattr(l1, "values") else l1)
    yearly_r = {}
    for ty in TEST_YEARS:
        s = dr[dr.year == ty]
        if len(s):
            ys = (s.y_exc.values > 0).astype(int)
            f = lambda p: float(-np.mean(ys * np.log(np.clip(p, 1e-9, 1 - 1e-9))
                                         + (1 - ys) * np.log(1 - np.clip(p, 1e-9, 1 - 1e-9))))
            a, b = f(s.pred_b.values), f(s.pred_c.values)
            yearly_r[ty] = {"R0_log_loss": round(a, 6), "R1_log_loss": round(b, 6),
                            "R1_better": bool(b < a)}
    res["return_direction"] = {"metrics": mr, "training_prevalence": round(prev, 4),
                               "paired_bootstrap_R0_minus_R1": boot_r, "by_year": yearly_r,
                               "n_oos": int(len(dr))}
    gr = {"beats_on_log_loss": bool(mr["C"]["log_loss"] < mr["B"]["log_loss"]),
          "ci_above_zero": boot_r["entirely_above_zero"],
          "auc_above_0_52": bool(mr["C"]["auc"] > 0.52),
          "beats_in_2of3_years": sum(v["R1_better"] for v in yearly_r.values()) >= 2}
    res["return_direction"]["gates"] = gr
    res["return_direction"]["passes"] = bool(all(gr.values()))

    # prespecified interaction coefficient signs (descriptive, no causal reading)
    def sgn(coefs, keys):
        out = {}
        for k in keys:
            vals = [c.get(k) for c in coefs if k in c]
            if vals:
                out[k] = {"mean_coef": round(float(np.mean(vals)), 6),
                          "sign": "positive" if np.mean(vals) > 0 else "negative",
                          "consistent_across_folds": bool(len({v > 0 for v in vals}) == 1)}
        return out
    res["interaction_coefficients"] = {
        "note": "descriptive only; standardized ridge/logit coefficients, no causal interpretation",
        "volatility_model_C": sgn(cv["C"], VOL_C_EXTRA),
        "return_model_R1": sgn(cr["C"], R1_EXTRA)}

    # ---------------- prespecified sensitivity checks ----------------
    sens = {}
    # 1. exclude known earnings weeks (from the existing frozen C5 population)
    try:
        c5 = pd.read_csv(C5, parse_dates=["earnings_date"])
        ew = set()
        for r in c5.dropna(subset=["earnings_date"]).itertuples():
            w = r.earnings_date - pd.Timedelta(days=r.earnings_date.weekday())
            ew.add((r.ticker, w))
        mask = ~pd.Series(list(zip(dv.ticker, dv.target_week)), index=dv.index).isin(ew)
        sub = dv[mask.values]
        a = float(np.mean(np.abs(sub.y_logvol - sub.pred_b)))
        b = float(np.mean(np.abs(sub.y_logvol - sub.pred_c)))
        sens["exclude_earnings_weeks"] = {
            "source": "existing frozen C5_PostEarnings_Population.csv (partial ticker coverage)",
            "rows_excluded": int(len(dv) - len(sub)), "n": int(len(sub)),
            "B_mae": round(a, 6), "C_mae": round(b, 6),
            "improvement_pct": round(100 * (a - b) / a, 4), "C_better": bool(b < a)}
    except Exception as e:                                       # noqa: BLE001
        sens["exclude_earnings_weeks"] = {"status": f"unavailable: {type(e).__name__}"}

    # 2. drop the five most lexically ambiguous queries per the existing construct audit
    aud = json.loads(AUDIT.read_text(encoding="utf-8"))
    rank = {"HIGH_LEXICAL_AMBIGUITY": 0, "MODERATE_LEXICAL_AMBIGUITY": 1, "LOW_LEXICAL_AMBIGUITY": 2}
    ordered = sorted(enumerate(aud["records"]),
                     key=lambda kv: (rank.get(kv[1]["ambiguity_classification"], 9), kv[0]))
    drop5 = [r["ticker"] for _, r in ordered[:5]]
    sub = dv[~dv.ticker.isin(drop5)]
    a = float(np.mean(np.abs(sub.y_logvol - sub.pred_b)))
    b = float(np.mean(np.abs(sub.y_logvol - sub.pred_c)))
    sens["drop_ambiguous_queries"] = {"dropped": drop5, "n": int(len(sub)),
                                      "B_mae": round(a, 6), "C_mae": round(b, 6),
                                      "improvement_pct": round(100 * (a - b) / a, 4),
                                      "C_better": bool(b < a)}

    # 3. winsorize continuous predictors at TRAINING-fold 1st/99th percentiles
    keep = []
    for ty in TEST_YEARS:
        tr, te = panel[panel.year < ty], panel[panel.year == ty]
        if len(tr) < 500 or len(te) == 0:
            continue
        tr2, te2 = tr.copy(), te.copy()
        for c in BASE_F + VOL_C_EXTRA:
            lo, hi = tr[c].quantile(0.01), tr[c].quantile(0.99)
            tr2[c] = tr[c].clip(lo, hi)
            te2[c] = te[c].clip(lo, hi)
        pb, _, _ = fit_ridge(tr2, te2, BASE_F)
        pc, _, _ = fit_ridge(tr2, te2, BASE_F + VOL_C_EXTRA)
        t2 = te2.copy()
        t2["pred_b"], t2["pred_c"] = pb, pc
        keep.append(t2)
    dw = pd.concat(keep, ignore_index=True)
    a = float(np.mean(np.abs(dw.y_logvol - dw.pred_b)))
    b = float(np.mean(np.abs(dw.y_logvol - dw.pred_c)))
    sens["winsorized_predictors"] = {"n": int(len(dw)), "B_mae": round(a, 6), "C_mae": round(b, 6),
                                     "improvement_pct": round(100 * (a - b) / a, 4),
                                     "C_better": bool(b < a)}
    res["sensitivity_checks"] = sens
    res["sensitivity_note"] = "robustness checks only; not alternative primary specifications"

    vp, rp = res["volatility"]["passes"], res["return_direction"]["passes"]
    res["decision_label"] = ("CONDITIONAL_ATTENTION_SIGNAL" if vp and rp else
                             "VOLATILITY_SIGNAL_ONLY" if vp else
                             "RETURN_SIGNAL_ONLY" if rp else
                             "RETIRE_GST_AS_TRADING_SIGNAL")
    res["portfolio_simulation"] = ("not run: the return gate did not pass, and a strategy is not "
                                   "manufactured from the volatility result"
                                   if not rp else "return gate passed; see portfolio block")
    res["runtime_seconds"] = round(time.time() - t0, 1)
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")

    print(f"tickers {gate['tickers']} | oos weeks {gate['oos_weeks']} | oos obs {gate['oos_observations']} | gate {gate['passed']}")
    print(f"VOL  B_mae {mv['B']['mae']} C_mae {mv['C']['mae']} impr {impr:.4f}% CI {boot_v['ci95']} gates {gv}")
    print(f"RET  R0_ll {mr['B']['log_loss']} R1_ll {mr['C']['log_loss']} auc {mr['C']['auc']} CI {boot_r['ci95']} gates {gr}")
    print(f"DECISION: {res['decision_label']}  ({res['runtime_seconds']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
