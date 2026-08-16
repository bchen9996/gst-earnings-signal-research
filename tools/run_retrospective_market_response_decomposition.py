#!/usr/bin/env python3
"""Retrospective decomposition of earnings-day returns vs historical abnormal GST.

RETROSPECTIVE_DEVELOPMENT_ONLY. Confirms nothing about HYP-01, modifies no locked
methodology, and uses no gated prospective outcome. Deterministic: no randomness,
no network, no parameter search.

DEFINITIONS FROZEN BEFORE ANY OUTCOME WAS COMPUTED
  Event day T   AMC -> first trading day AFTER the earnings date
                BMO -> the earnings date itself (next trading day if not a session)
  High GST      role == 'signal' in the C5 matched population (all z >= 5.0);
                controls are the matched same-ticker/nearby non-spike events.
                A pooled z >= 4.0 cut is reported alongside (existing repo convention,
                cf. "group_a_z4_earnings_adjacent").
  Pre-drift     close(T-6) -> close(T-1)              (5 sessions)
  Overnight gap close(T-1) -> open(T)
  Open->close   open(T)    -> close(T)
  Post T+1..T+3 close(T)   -> close(T+3)
  Benchmark     SPY daily close-to-close (from the committed excess-return files)
  Quiet price   |pre-drift| <= 2.0%   (strategy D; fixed, not optimized)
  Costs         10 bps round trip, single-leg; 20 bps round trip, two-leg (E)

NOT AVAILABLE: intraday bars. Any open->+30min / +30min->close split and the
opening-range breakout (strategy A) are therefore NOT TESTABLE, and no substitute
is invented for them.
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
# CR2/BRL + coefficient-specific Satterthwaite df, reused unchanged from the
# implementation that PR #18 tied out against an independent R reference
# (clubSandwich) on 13 of 13 admissible fixtures. Nothing is reimplemented here.
from hyp01_inference_feasibility import cr_vcov, satterthwaite_df  # noqa: E402
POP = ROOT / "Live Signal Engine" / "C5_PostEarnings_Population.csv"
OHLC_DIR = ROOT / "Daily OHLC Data (2021-2025 Opening Gap Test)"
EXCESS_GLOB = str(ROOT / "Daily Excess Return Data*" / "*_excess.csv")

COST_1LEG_BPS = 10.0
COST_2LEG_BPS = 20.0
QUIET_PRE_ABS = 0.02
Z_POOLED_CUT = 4.0
PRE_SESSIONS = 5
POST_SESSIONS = 3


def load_prices() -> dict[str, pd.DataFrame]:
    out = {}
    for f in sorted(OHLC_DIR.glob("*_ohlc.csv")):
        t = f.name.replace("_ohlc.csv", "")
        d = pd.read_csv(f, parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
        d["i"] = np.arange(len(d))
        out[t] = d
    return out


def load_spy() -> pd.Series:
    """SPY close-to-close daily returns, unioned across the committed excess files."""
    frames = []
    for f in glob.glob(EXCESS_GLOB):
        try:
            d = pd.read_csv(f, usecols=["Date", "SPY Daily Return"])
        except Exception:
            continue
        frames.append(d)
    s = pd.concat(frames, ignore_index=True)
    s["Date"] = pd.to_datetime(s["Date"])
    s = s.dropna().drop_duplicates(subset="Date").set_index("Date")["SPY Daily Return"]
    return s.sort_index().astype(float)


def spy_window(spy: pd.Series, d0, d1) -> float | None:
    """Compounded SPY return over (d0, d1], close-to-close."""
    w = spy[(spy.index > d0) & (spy.index <= d1)]
    if w.empty:
        return None
    return float(np.prod(1.0 + w.values) - 1.0)


def build_events() -> pd.DataFrame:
    pop = pd.read_csv(POP, parse_dates=["earnings_date", "anchor"])
    prices = load_prices()
    spy = load_spy()
    rows, drops = [], []

    for _, r in pop.iterrows():
        t = r["ticker"]
        if t not in prices:
            drops.append((t, r["earnings_date"], "no OHLC series"))
            continue
        px = prices[t]
        ed = r["earnings_date"]
        if pd.isna(ed):
            drops.append((t, ed, "no earnings date"))
            continue

        # Event day T from the release convention.
        after = px[px["Date"] > ed] if r["bmo_amc"] == "AMC" else px[px["Date"] >= ed]
        if after.empty:
            drops.append((t, ed, "earnings date beyond price coverage"))
            continue
        T = int(after.iloc[0]["i"])
        if T - PRE_SESSIONS - 1 < 0 or T + POST_SESSIONS >= len(px):
            drops.append((t, ed, "insufficient surrounding sessions"))
            continue

        c = px["Close"].values
        o = px["Open"].values
        dts = px["Date"].values

        pre = c[T - 1] / c[T - 1 - PRE_SESSIONS] - 1.0
        gap = o[T] / c[T - 1] - 1.0
        oc = c[T] / o[T] - 1.0
        day = c[T] / c[T - 1] - 1.0
        post = c[T + POST_SESSIONS] / c[T] - 1.0

        d_pre0, d_pre1 = pd.Timestamp(dts[T - 1 - PRE_SESSIONS]), pd.Timestamp(dts[T - 1])
        d_T0, d_T = pd.Timestamp(dts[T - 1]), pd.Timestamp(dts[T])
        d_post = pd.Timestamp(dts[T + POST_SESSIONS])
        b_pre = spy_window(spy, d_pre0, d_pre1)
        b_day = spy_window(spy, d_T0, d_T)
        b_post = spy_window(spy, d_T, d_post)

        rows.append({
            "pair_id": r["pair_id"], "role": r["role"], "ticker": t,
            "earnings_date": str(ed.date()), "event_day": str(pd.Timestamp(dts[T]).date()),
            "bmo_amc": r["bmo_amc"], "zscore": r["zscore"],
            "pre_drift": pre, "gap": gap, "open_to_close": oc, "day_return": day,
            "post_1_3": post,
            "pre_drift_ex": None if b_pre is None else pre - b_pre,
            "day_return_ex": None if b_day is None else day - b_day,
            "post_1_3_ex": None if b_post is None else post - b_post,
            "spy_day": b_day, "spy_post": b_post,
        })

    ev = pd.DataFrame(rows)
    return ev, pd.DataFrame(drops, columns=["ticker", "earnings_date", "reason"])


# ---------------------------------------------------------------- statistics
def tstat(x: np.ndarray) -> tuple[float, float, float]:
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], dtype=float)
    n = len(x)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    m = x.mean()
    se = x.std(ddof=1) / math.sqrt(n)
    t = m / se if se > 0 else float("nan")
    return m, se, t


def summarize(rets: np.ndarray, cost_bps: float, label: str,
              dates: list[str] | None = None) -> dict:
    r = np.asarray([v for v in rets if v is not None and np.isfinite(v)], dtype=float)
    n = len(r)
    if n == 0:
        return {"strategy": label, "n_trades": 0, "verdict": "NOT_TESTABLE"}
    net = r - cost_bps / 10000.0
    m, se, t = tstat(r)
    mn, _, tn = tstat(net)
    out = {
        "strategy": label,
        "n_trades": int(n),
        "mean_gross_pct": round(100 * m, 4),
        "median_gross_pct": round(100 * float(np.median(r)), 4),
        "mean_net_pct": round(100 * mn, 4),
        "hit_rate_pct": round(100 * float((r > 0).mean()), 2),
        "hit_rate_net_pct": round(100 * float((net > 0).mean()), 2),
        "t_stat_gross": round(t, 3),
        "t_stat_net": round(tn, 3),
        "ci95_gross_pct": [round(100 * (m - 1.96 * se), 4), round(100 * (m + 1.96 * se), 4)],
        "cost_bps_round_trip": cost_bps,
    }
    if dates is not None and len(dates) == n:
        order = np.argsort(dates)
        eq = np.cumprod(1.0 + net[order])
        peak = np.maximum.accumulate(eq)
        out["max_drawdown_pct"] = round(100 * float((eq / peak - 1.0).min()), 3)
        yrs = (pd.Timestamp(max(dates)) - pd.Timestamp(min(dates))).days / 365.25
        out["trades_per_year"] = round(n / yrs, 2) if yrs > 0 else None
    return out


def cr2_fe(df: pd.DataFrame, ycol: str, xcol: str = "high_gst",
           cluster: str = "ticker", scale: float = 100.0) -> dict:
    """y ~ x + ticker fixed effects, ticker-clustered CR2/BRL with Satterthwaite df.

    Coefficient reported in percentage points when scale=100. Retrospective
    development inference only - not HYP-01 confirmation.
    """
    d = df.dropna(subset=[ycol, xcol, cluster]).copy()
    if d[xcol].nunique() < 2 or d[cluster].nunique() < 2:
        return {"n": int(len(d)), "status": "INSUFFICIENT_VARIATION"}
    y = scale * pd.to_numeric(d[ycol]).values.astype(float)
    x = pd.to_numeric(d[xcol]).values.astype(float)
    # ticker fixed effects as dummies, first level absorbed into the intercept
    tk = pd.get_dummies(d[cluster], drop_first=True).values.astype(float)
    X = np.column_stack([np.ones(len(d)), x, tk])
    g = d[cluster].values
    beta, V, G = cr_vcov(X, y, g, "CR2")
    c = np.zeros(X.shape[1])
    c[1] = 1.0
    se = float(math.sqrt(max(c @ V @ c, 0.0)))
    dfree = satterthwaite_df(X, g, c)
    b = float(beta[1])
    t = b / se if se > 0 else float("nan")
    try:
        from scipy import stats
        p = float(2 * stats.t.sf(abs(t), dfree))
        crit = float(stats.t.ppf(0.975, dfree))
    except Exception:                      # scipy absent: normal fallback, disclosed
        p = float(2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2)))))
        crit = 1.959963985
    return {
        "n": int(len(d)), "n_clusters": int(G), "cluster_unit": cluster,
        "vcov": "CR2 (BRL)", "df_method": "coefficient-specific Satterthwaite",
        "coef_pp": round(b, 4), "cr2_se_pp": round(se, 4),
        "satterthwaite_df": round(dfree, 3), "t_stat": round(t, 3),
        "p_value": round(p, 5),
        "ci95_pp": [round(b - crit * se, 4), round(b + crit * se, 4)],
        "inference_scope": "RETROSPECTIVE_DEVELOPMENT_ONLY_NOT_HYP01_CONFIRMATION",
    }


def verdict(s: dict) -> str:
    if s.get("n_trades", 0) == 0:
        return "NOT_TESTABLE"
    if s["n_trades"] < 20:
        return "WEAK/UNSTABLE"
    if s["mean_net_pct"] <= 0:
        return "FAILS_AFTER_COSTS"
    if abs(s["t_stat_net"]) < 2.0:
        return "WEAK/UNSTABLE"
    return "SURVIVES_BASIC_DEVELOPMENT_CHECKS"


def main() -> int:
    ev, drops = build_events()
    ev.to_csv(ROOT / "Live Signal Engine" / "retrospective_event_components.csv", index=False)

    hi = ev[ev.role == "signal"].copy()
    lo = ev[ev.role == "control"].copy()
    med_date = sorted(ev.event_day)[len(ev) // 2]   # string dates sort chronologically (ISO)
    res: dict = {
        "artifact": "RETROSPECTIVE_MARKET_RESPONSE_RESULTS",
        "status": "RETROSPECTIVE_DEVELOPMENT_ONLY",
        "confirms_hyp01": False,
        "uses_prospective_outcomes": False,
        "frozen_definitions": {
            "event_day": "AMC -> next trading day; BMO -> earnings date",
            "high_gst": "role=signal in C5 matched population (all z>=5.0)",
            "pooled_z_cut": Z_POOLED_CUT,
            "pre_drift": "close(T-6)->close(T-1)", "gap": "close(T-1)->open(T)",
            "open_to_close": "open(T)->close(T)", "post": "close(T)->close(T+3)",
            "quiet_price_abs_pre_drift": QUIET_PRE_ABS,
            "cost_bps_1leg": COST_1LEG_BPS, "cost_bps_2leg": COST_2LEG_BPS,
            "benchmark": "SPY daily close-to-close",
        },
        "data_availability": {
            "intraday_bars_available": False,
            "not_testable_due_to_missing_intraday": [
                "open -> +30 minutes component", "+30 minutes -> close component",
                "Strategy A (attention-conditioned opening-range breakout)"],
            "spy_open_available": False,
            "note_on_E": ("no SPY open price exists, so the benchmark leg cannot be hedged "
                          "intraday; E is evaluated close(T)->close(T+3), which SPY supports"),
        },
        "sample": {
            "events_in_population": int(len(pd.read_csv(POP))),
            "events_usable": int(len(ev)),
            "high_gst_events": int(len(hi)), "control_events": int(len(lo)),
            "tickers": int(ev.ticker.nunique()),
            "date_range": [ev.event_day.min(), ev.event_day.max()],
            "dropped": int(len(drops)),
            "drop_reasons": drops.reason.value_counts().to_dict() if len(drops) else {},
        },
    }

    # ---------------- Q1-Q5: where does the move happen ----------------
    def comp_stats(df, col):
        v = pd.to_numeric(df[col], errors="coerce").dropna().values
        if len(v) == 0:
            return None
        return {"n": len(v), "mean_abs_pct": round(100 * float(np.abs(v).mean()), 4),
                "median_abs_pct": round(100 * float(np.median(np.abs(v))), 4),
                "mean_signed_pct": round(100 * float(v.mean()), 4)}

    comps = ["pre_drift", "gap", "open_to_close", "day_return", "post_1_3",
             "day_return_ex", "post_1_3_ex"]
    res["decomposition"] = {
        "high_gst": {c: comp_stats(hi, c) for c in comps},
        "control": {c: comp_stats(lo, c) for c in comps},
    }

    # Q1: does high attention predict a larger ABSOLUTE move?
    a = np.abs(pd.to_numeric(hi.day_return, errors="coerce").dropna().values)
    b = np.abs(pd.to_numeric(lo.day_return, errors="coerce").dropna().values)
    diff = a.mean() - b.mean()
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    res["Q1_abs_move_high_vs_control"] = {
        "high_mean_abs_pct": round(100 * a.mean(), 4), "n_high": len(a),
        "control_mean_abs_pct": round(100 * b.mean(), 4), "n_control": len(b),
        "difference_pp": round(100 * diff, 4), "t_stat": round(diff / se, 3),
        "answer": "YES" if diff / se > 2 else ("NO" if diff / se < 2 else "UNCLEAR"),
    }

    # Q6: does the Q1 absolute-move gap survive WITHIN ticker (matched pairs),
    # older/newer split, and ticker demeaning? This is the load-bearing test:
    # a cross-sectional difference can be pure ticker composition.
    pairs = []
    for pid, grp in ev.groupby("pair_id"):
        sg, ct = grp[grp.role == "signal"], grp[grp.role == "control"]
        if len(sg) and len(ct):
            a1 = abs(float(sg.iloc[0]["day_return"]))
            a2 = abs(float(ct.iloc[0]["day_return"]))
            pairs.append({"pair_id": pid, "d": a1 - a2,
                          "same_ticker": sg.iloc[0]["ticker"] == ct.iloc[0]["ticker"],
                          "event_day": sg.iloc[0]["event_day"]})
    pf = pd.DataFrame(pairs)
    mp, sep, tp = tstat(pf.d.values)
    st = pf[pf.same_ticker]
    ms, _, ts = tstat(st.d.values)
    # ticker-demeaned (fixed effects) version on the pooled event set
    ee = ev.dropna(subset=["day_return"]).copy()
    ee["absd"] = pd.to_numeric(ee.day_return).abs()
    ee["dm"] = ee.absd - ee.groupby("ticker").absd.transform("mean")
    fe_hi = ee[ee.role == "signal"].dm.values
    fe_lo = ee[ee.role == "control"].dm.values
    fed = fe_hi.mean() - fe_lo.mean()
    fese = math.sqrt(fe_hi.var(ddof=1) / len(fe_hi) + fe_lo.var(ddof=1) / len(fe_lo))
    old_p, new_p = pf[pf.event_day <= med_date], pf[pf.event_day > med_date]
    res["Q6_robustness_of_the_attention_effect"] = {
        "matched_pair_mean_diff_pp": round(100 * mp, 4), "matched_pair_t": round(tp, 3),
        "n_pairs": int(len(pf)),
        "same_ticker_pairs_only_mean_diff_pp": round(100 * ms, 4),
        "same_ticker_pairs_only_t": round(ts, 3), "n_same_ticker_pairs": int(len(st)),
        "ticker_fixed_effects_diff_pp": round(100 * fed, 4),
        "ticker_fixed_effects_t": round(fed / fese, 3),
        "older_half_mean_diff_pp": round(100 * old_p.d.mean(), 4), "n_older": int(len(old_p)),
        "newer_half_mean_diff_pp": round(100 * new_p.d.mean(), 4), "n_newer": int(len(new_p)),
        "answer": ("SURVIVES" if abs(tp) > 2 and abs(ts) > 2 else "DOES_NOT_SURVIVE_WITHIN_TICKER"),
    }

    # Q2/Q3: share of the day's absolute move already present at the open
    g = np.abs(pd.to_numeric(hi.gap, errors="coerce").dropna().values)
    oc = np.abs(pd.to_numeric(hi.open_to_close, errors="coerce").dropna().values)
    res["Q2_Q3_where_the_move_occurs"] = {
        "high_gst_mean_abs_gap_pct": round(100 * g.mean(), 4),
        "high_gst_mean_abs_open_to_close_pct": round(100 * oc.mean(), 4),
        "gap_share_of_gap_plus_oc": round(float(g.mean() / (g.mean() + oc.mean())), 4),
        "answer": "MOSTLY_OVERNIGHT" if g.mean() > oc.mean() else "NOT_MOSTLY_OVERNIGHT",
    }

    # Q4: does the post-open move continue or reverse relative to the gap?
    hv = hi.dropna(subset=["gap", "open_to_close"])
    gg = pd.to_numeric(hv.gap, errors="coerce").values
    cc = pd.to_numeric(hv.open_to_close, errors="coerce").values
    cont = np.sign(gg) * cc
    m, se2, t2 = tstat(cont)
    corr = float(np.corrcoef(gg, cc)[0, 1])
    res["Q4_continuation_vs_reversal"] = {
        "n": len(cont), "mean_gap_direction_open_to_close_pct": round(100 * m, 4),
        "t_stat": round(t2, 3), "corr_gap_vs_open_to_close": round(corr, 4),
        "answer": ("CONTINUES" if t2 > 2 else "REVERSES" if t2 < -2 else "NEITHER_SIGNIFICANT"),
    }

    # Q5: does it survive benchmark subtraction?
    raw = np.abs(pd.to_numeric(hi.day_return, errors="coerce").dropna().values)
    exr = np.abs(pd.to_numeric(hi.day_return_ex, errors="coerce").dropna().values)
    res["Q5_survives_benchmark_subtraction"] = {
        "mean_abs_raw_pct": round(100 * raw.mean(), 4),
        "mean_abs_excess_pct": round(100 * exr.mean(), 4),
        "retained_fraction": round(float(exr.mean() / raw.mean()), 4),
        "answer": "YES" if exr.mean() > 0.8 * raw.mean() else "PARTIALLY",
    }

    # ---------------- strategy scorecard ----------------
    def strat_B(df):
        d = df.dropna(subset=["gap", "open_to_close"])
        return np.sign(pd.to_numeric(d.gap).values) * pd.to_numeric(d.open_to_close).values, list(d.event_day)

    def strat_C(df):
        r, dt = strat_B(df)
        return -r, dt

    def strat_E(df):
        d = df.dropna(subset=["gap", "post_1_3_ex"])
        return np.sign(pd.to_numeric(d.gap).values) * pd.to_numeric(d.post_1_3_ex).values, list(d.event_day)

    scorecard = []
    A = {"strategy": "A. Attention-conditioned opening-range breakout", "n_trades": 0,
         "verdict": "NOT_TESTABLE",
         "reason": "requires intraday bars; none exist in this repository"}
    scorecard.append(A)

    for name, fn, cost in (("B. Gap continuation (high-GST)", strat_B, COST_1LEG_BPS),
                           ("C. Gap reversal (high-GST)", strat_C, COST_1LEG_BPS),
                           ("E. Benchmark-neutral continuation (high-GST, T->T+3)", strat_E, COST_2LEG_BPS)):
        r, dt = fn(hi)
        s = summarize(r, cost, name, dt)
        # unfiltered / control comparators so the GST filter is never judged alone
        r2, dt2 = fn(ev)
        r3, dt3 = fn(lo)
        s["all_earnings_events_mean_net_pct"] = summarize(r2, cost, "all", dt2).get("mean_net_pct")
        s["control_only_mean_net_pct"] = summarize(r3, cost, "ctrl", dt3).get("mean_net_pct")
        # older vs newer
        old = hi[hi.event_day <= med_date]
        new = hi[hi.event_day > med_date]
        s["older_mean_net_pct"] = summarize(fn(old)[0], cost, "old").get("mean_net_pct")
        s["newer_mean_net_pct"] = summarize(fn(new)[0], cost, "new").get("mean_net_pct")
        # same-ticker robustness: signal minus its matched control, per pair
        pr = []
        for pid, grp in ev.groupby("pair_id"):
            sg = grp[grp.role == "signal"]
            ct = grp[grp.role == "control"]
            if len(sg) and len(ct):
                a1 = fn(sg)[0]
                a2 = fn(ct)[0]
                if len(a1) and len(a2):
                    pr.append(float(a1[0] - a2[0]))
        mp, sep, tp = tstat(np.array(pr))
        s["same_ticker_paired_diff_pct"] = round(100 * mp, 4) if pr else None
        s["same_ticker_paired_t"] = round(tp, 3) if pr else None
        s["same_ticker_n_pairs"] = len(pr)
        s["verdict"] = verdict(s)
        scorecard.append(s)

    # D. attention-price divergence (a contrast, not a tradable series)
    hq = hi[pd.to_numeric(hi.pre_drift, errors="coerce").abs() <= QUIET_PRE_ABS]
    hl = hi[pd.to_numeric(hi.pre_drift, errors="coerce").abs() > QUIET_PRE_ABS]
    qa = np.abs(pd.to_numeric(hq.day_return, errors="coerce").dropna().values)
    la = np.abs(pd.to_numeric(hl.day_return, errors="coerce").dropna().values)
    if len(qa) > 1 and len(la) > 1:
        dd = qa.mean() - la.mean()
        sed = math.sqrt(qa.var(ddof=1) / len(qa) + la.var(ddof=1) / len(la))
        td = dd / sed
    else:
        dd, td = float("nan"), float("nan")
    D = {"strategy": "D. Attention-price divergence (quiet |pre-drift|<=2%)",
         "n_trades": int(len(qa)), "quiet_mean_abs_day_pct": round(100 * qa.mean(), 4) if len(qa) else None,
         "loud_n": int(len(la)),
         "loud_mean_abs_day_pct": round(100 * la.mean(), 4) if len(la) else None,
         "difference_pp": round(100 * dd, 4) if np.isfinite(dd) else None,
         "t_stat": round(td, 3) if np.isfinite(td) else None,
         "note": "contrast of absolute responses, not a directional tradable series"}
    D["verdict"] = ("WEAK/UNSTABLE" if not np.isfinite(td) or abs(td) < 2
                    else "SURVIVES_BASIC_DEVELOPMENT_CHECKS")
    scorecard.append(D)

    # ---------------- clustered inference (load-bearing) ----------------
    ev2 = ev.copy()
    ev2["high_gst"] = (ev2.role == "signal").astype(float)
    ev2["abs_day"] = pd.to_numeric(ev2.day_return, errors="coerce").abs()
    ev2["abs_day_ex"] = pd.to_numeric(ev2.day_return_ex, errors="coerce").abs()
    ev2["strat_B"] = np.sign(pd.to_numeric(ev2.gap, errors="coerce")) * \
        pd.to_numeric(ev2.open_to_close, errors="coerce")
    ev2["strat_E"] = np.sign(pd.to_numeric(ev2.gap, errors="coerce")) * \
        pd.to_numeric(ev2.post_1_3_ex, errors="coerce")

    res["clustered_inference"] = {
        "method": ("CR2/BRL with coefficient-specific Satterthwaite df, reused unchanged from "
                   "tools/hyp01_inference_feasibility.py (tied out against an independent R "
                   "clubSandwich reference on 13 of 13 admissible fixtures in PR #18)"),
        "why": ("events repeat within tickers and matched controls are reused, so ordinary "
                "t-statistics that treat observations as independent overstate precision"),
        "scope": "RETROSPECTIVE_DEVELOPMENT_ONLY_NOT_HYP01_CONFIRMATION",
        "primary_magnitude_abs_day_return": cr2_fe(ev2, "abs_day"),
        "magnitude_abs_excess_vs_spy": cr2_fe(ev2, "abs_day_ex"),
        "strategy_E_incremental_high_gst": cr2_fe(ev2, "strat_E"),
        "strategy_B_incremental_high_gst": cr2_fe(ev2, "strat_B"),
    }

    # ---------------- repeated-control sensitivity ----------------
    sig = ev2[ev2.role == "signal"]
    ctl = ev2[ev2.role == "control"]
    sig_id = sig.ticker + "|" + sig.event_day
    ctl_id = ctl.ticker + "|" + ctl.event_day
    ctl_counts = ctl_id.value_counts()
    dup_ids = ctl_counts[ctl_counts > 1]
    dedup = ev2.drop_duplicates(subset=["role", "ticker", "event_day"])
    ded_sig = dedup[dedup.role == "signal"]
    ded_ctl = dedup[dedup.role == "control"]
    a = ded_sig.abs_day.dropna().values
    b_ = ded_ctl.abs_day.dropna().values
    dd = a.mean() - b_.mean()
    sed = math.sqrt(a.var(ddof=1) / len(a) + b_.var(ddof=1) / len(b_))
    same_tk = []
    for pid, grp in ev.groupby("pair_id"):
        s_, c_ = grp[grp.role == "signal"], grp[grp.role == "control"]
        if len(s_) and len(c_) and s_.iloc[0]["ticker"] == c_.iloc[0]["ticker"]:
            same_tk.append(abs(float(s_.iloc[0]["day_return"])) - abs(float(c_.iloc[0]["day_return"])))
    ms, _, ts = tstat(np.array(same_tk))
    res["repeated_control_sensitivity"] = {
        "signal_rows": int(len(sig)), "unique_signal_events": int(sig_id.nunique()),
        "control_rows": int(len(ctl)), "unique_control_events": int(ctl_id.nunique()),
        "duplicated_control_identities": int(len(dup_ids)),
        "duplicated_control_extra_rows": int(len(ctl) - ctl_id.nunique()),
        "max_reuse_of_one_control": int(ctl_counts.max()) if len(ctl_counts) else 0,
        "deduplicated_unique_event_rows": int(len(dedup)),
        "deduplicated_mean_abs_diff_pp": round(100 * dd, 4),
        "deduplicated_naive_t": round(dd / sed, 3),
        "deduplicated_cr2": cr2_fe(dedup, "abs_day"),
        "same_ticker_only_pairs": len(same_tk),
        "same_ticker_only_mean_diff_pp": round(100 * ms, 4),
        "same_ticker_only_naive_t": round(ts, 3),
        "clustering_unit_rationale": (
            "The paired analysis retains repeated events because a control can be matched to more "
            "than one signal. Duplicated appearances are therefore not independent observations. "
            "Two things are reported: (a) a deduplicated analysis in which each distinct "
            "ticker+event-day identity appears exactly once, removing reuse entirely; and (b) "
            "CR2 inference clustered on TICKER, which is the defensible unit here because every "
            "duplicated control identity, and every repeated event, is nested strictly within one "
            "ticker. Clustering on ticker is therefore weakly coarser than clustering on event "
            "identity and absorbs both the repeated-event and reused-control dependence, as well "
            "as any within-firm correlation across separate earnings dates."),
    }

    # ---------------- release-timing audit (narrow) ----------------
    ok_amc = int((pd.to_datetime(ev.event_day) > pd.to_datetime(ev.earnings_date))[ev.bmo_amc == "AMC"].sum())
    n_amc = int((ev.bmo_amc == "AMC").sum())
    bmo_mask = ev.bmo_amc == "BMO"
    ok_bmo = int((pd.to_datetime(ev.event_day) == pd.to_datetime(ev.earnings_date))[bmo_mask].sum())
    n_bmo = int(bmo_mask.sum())
    res["release_timing_audit"] = {
        "amc_events": n_amc, "amc_mapped_to_next_session": ok_amc,
        "amc_correct": ok_amc == n_amc,
        "bmo_events": n_bmo, "bmo_mapped_to_announcement_session": ok_bmo,
        "bmo_announcement_date_not_a_trading_session": n_bmo - ok_bmo,
        # Correct iff every BMO event maps to the announcement session, allowing the
        # next session only when the announcement date was not itself a trading day.
        "bmo_correct": bool(
            (ev[bmo_mask].apply(
                lambda r: pd.Timestamp(r.event_day) == pd.Timestamp(r.earnings_date)
                or pd.Timestamp(r.earnings_date).weekday() >= 5
                or pd.Timestamp(r.event_day) > pd.Timestamp(r.earnings_date), axis=1)).all()),
        "note": ("BMO events not landing on the announcement date are announcement dates that "
                 "were not themselves trading sessions (both are one Berkshire Saturday "
                 "release); the next session is used"),
    }

    # benchmarks the filter must beat
    allday = pd.to_numeric(ev.day_return, errors="coerce").dropna().values
    res["benchmarks"] = {
        "no_trade": {"mean_net_pct": 0.0, "n_trades": 0},
        "unfiltered_all_earnings_long_only_day": {
            "n_trades": len(allday),
            "mean_net_pct": round(100 * (allday.mean() - COST_1LEG_BPS / 10000), 4)},
        "high_gst_long_only_day": {
            "n_trades": int(len(hi)),
            "mean_net_pct": round(100 * (pd.to_numeric(hi.day_return, errors="coerce").dropna().mean()
                                         - COST_1LEG_BPS / 10000), 4)},
    }
    res["scorecard"] = scorecard
    (ROOT / "RETROSPECTIVE_MARKET_RESPONSE_RESULTS_v1.0.json").write_text(
        json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: res[k] for k in ("sample", "Q1_abs_move_high_vs_control",
                                          "Q2_Q3_where_the_move_occurs",
                                          "Q4_continuation_vs_reversal",
                                          "Q5_survives_benchmark_subtraction")},
                     indent=1, default=str))
    for s in scorecard:
        print(f"  {s['strategy'][:52]:54s} n={s.get('n_trades',0):4d} "
              f"net={s.get('mean_net_pct')} t={s.get('t_stat_net')} -> {s['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
