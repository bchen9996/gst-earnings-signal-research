#!/usr/bin/env python3
"""Do pre-earnings consumer-brand searches predict unusually large earnings moves?

EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY. Not HYP-01 confirmation, not prospective
collection. Targets MAGNITUDE, never direction. Stock direction is never a target.

FROZEN BEFORE RETRIEVAL
  Universe/queries  Live Signal Engine/Restaurant_Search_Pilot/frozen_queries_v1.0.csv
                    8 tickers, one consumer query and one "[TICKER] stock" query each,
                    geo=US, gprop=web, cat=0, weekly. No substitution, no ranking, no
                    related-query selection.
  Timing            SEC 8-K item 2.02 acceptance timestamp (authoritative, point-in-time).
                    BMO (accepted < 09:30 ET) -> outcome session is that trading day.
                    AMC (accepted >= 16:00 ET) -> outcome session is the next trading day.
                    Non-trading announcement date -> next session, disclosed.
  Search cutoff     every search week must CLOSE strictly before the announcement
                    timestamp. Asserted mechanically per event (see assert_no_leakage).
  Abnormal level    robust z: (x - median of preceding 52 weeks) / (1.4826 * MAD of those
                    weeks). One transformation, fixed, applied identically to the investor
                    and product series. No window or transformation search.
  Outcome           large move = |outcome-session return| above the 75th percentile
                    computed FROM THE TRAINING FOLD ONLY.
  Models            A intercept-only training prevalence
                    B baseline (history/fundamental/vol/quarter/ticker)
                    C B + investor-attention search features
                    D C + product-demand search features
                    one logistic for the tail target, one ridge for continuous |return|;
                    regularization chosen inside each training fold from a fixed grid
                    declared here before any test outcome was evaluated.
  Primary metric    pooled chronological out-of-sample Brier. Lower is better.
  Central test      Brier loss(C) - Brier loss(D) per event; positive means product
                    demand helped. Mean estimated with the repository's validated
                    CR2/BRL implementation clustered by ticker, Satterthwaite df.
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
# NOTE: hyp01_inference_feasibility blocks sockets at import time (it is an offline
# runner). It is therefore imported LAZILY, after all retrieval is finished, so the
# block cannot kill the SEC and price fetches.

OUT = ROOT / "Live Signal Engine" / "Restaurant_Search_Pilot"
QMAP = OUT / "frozen_queries_v1.0.csv"
TRENDS = OUT / "search_weekly_v1.0.csv"
PRICES = OUT / "daily_prices_v1.0.csv"
EVENTS = OUT / "earnings_events_v1.0.csv"
PANEL = OUT / "event_panel_v1.0.csv"
RESULTS = ROOT / "RESTAURANT_SEARCH_PILOT_RESULTS_v1.0.json"

UA = {"User-Agent": "gst-earnings-signal-research academic research (hakurati11@gmail.com)"}
UA_MKT = {"User-Agent": "Mozilla/5.0 (gst-earnings-signal-research restaurant pilot)"}
START, END = "2019-01-01", "2026-01-01"
TAIL_Q = 0.75
MIN_TRAIN = 40                     # first test event only after this many prior events
LOGIT_GRID = [0.1, 1.0, 10.0]      # fixed, declared before any test outcome
RIDGE_GRID = [0.1, 1.0, 10.0]
REV_CONCEPTS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]

BASE_F = ["prior4_mean_abs_move", "prior4_median_abs_move", "realized_vol_20d",
          "prior_rev_growth_yoy"]
INV_F = ["inv_level", "inv_mean4", "inv_slope4", "inv_abnormal"]
PRD_F = ["prd_level", "prd_mean4", "prd_slope4", "prd_abnormal"]


def sec_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return json.loads(r.read())


def fetch_prices(tickers):
    if PRICES.exists():
        return pd.read_csv(PRICES, parse_dates=["Date"])
    fr = []
    for s in tickers:
        p1 = int(pd.Timestamp("2018-01-01").timestamp()); p2 = int(pd.Timestamp(END).timestamp())
        u = (f"https://query1.finance.yahoo.com/v8/finance/chart/{s}"
             f"?period1={p1}&period2={p2}&interval=1d")
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA_MKT), timeout=60) as r:
            b = json.loads(r.read())
        res = b["chart"]["result"][0]; q = res["indicators"]["quote"][0]
        d = pd.DataFrame({"Date": pd.to_datetime(res["timestamp"], unit="s").normalize(),
                          "Close": q["close"]})
        d["symbol"] = s
        fr.append(d.dropna().drop_duplicates("Date").sort_values("Date"))
        time.sleep(0.3)
    d = pd.concat(fr, ignore_index=True)
    d.to_csv(PRICES, index=False, lineterminator="\n")
    return d


def fetch_events(tickers):
    if EVENTS.exists():
        return pd.read_csv(EVENTS, parse_dates=["filing_date"]), json.loads(
            (OUT / "revenue_facts_v1.0.json").read_text(encoding="utf-8"))
    ct = sec_json("https://www.sec.gov/files/company_tickers.json")
    cik = {v["ticker"]: int(v["cik_str"]) for v in ct.values()}
    rows, revfacts = [], {}
    for t in tickers:
        c = cik[t]
        sub = sec_json(f"https://data.sec.gov/submissions/CIK{c:010d}.json")
        rec = sub["filings"]["recent"]
        for form, items, fdate, acc in zip(rec["form"], rec["items"], rec["filingDate"],
                                           rec["acceptanceDateTime"]):
            if form == "8-K" and "2.02" in (items or "") and START <= fdate < END:
                rows.append({"ticker": t, "cik": c, "filing_date": fdate, "acceptance": acc})
        facts = sec_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c:010d}.json")
        gaap = facts.get("facts", {}).get("us-gaap", {})
        best, bn = None, 0
        for concept in REV_CONCEPTS:
            if concept in gaap:
                us = gaap[concept]["units"].get("USD", [])
                q = [x for x in us if x.get("start") and x.get("end")
                     and 80 <= (pd.Timestamp(x["end"]) - pd.Timestamp(x["start"])).days <= 100]
                if len(q) > bn:
                    best, bn = q, len(q)
        revfacts[t] = [{"start": x["start"], "end": x["end"], "val": float(x["val"]),
                        "filed": x.get("filed"), "accn": x.get("accn")} for x in (best or [])]
        time.sleep(0.3)
    e = pd.DataFrame(rows).drop_duplicates(subset=["ticker", "filing_date"])
    e.to_csv(EVENTS, index=False, lineterminator="\n")
    (OUT / "revenue_facts_v1.0.json").write_text(json.dumps(revfacts, indent=1), encoding="utf-8",
                                                 newline="\n")
    return e, revfacts


def robust_z(x, hist):
    """(x - median) / (1.4826 * MAD). Fixed transformation, applied identically."""
    if len(hist) < 20:
        return float("nan")
    med = float(np.median(hist))
    mad = float(np.median(np.abs(hist - med)))
    s = 1.4826 * mad
    return float((x - med) / s) if s > 0 else float("nan")


def search_features(ts, ann_ts, prefix):
    """Only weeks whose period CLOSES strictly before the announcement timestamp."""
    if ts is None or not len(ts):
        return {f"{prefix}_level": np.nan, f"{prefix}_mean4": np.nan,
                f"{prefix}_slope4": np.nan, f"{prefix}_abnormal": np.nan, f"{prefix}_last_close": None}
    closes = ts.week + pd.Timedelta(days=6)          # weekly period closes 6 days after start
    ok = ts[closes < ann_ts].sort_values("week")
    if len(ok) < 8:
        return {f"{prefix}_level": np.nan, f"{prefix}_mean4": np.nan,
                f"{prefix}_slope4": np.nan, f"{prefix}_abnormal": np.nan, f"{prefix}_last_close": None}
    v = ok.interest.values.astype(float)
    last4 = v[-4:]
    slope = float(np.polyfit(np.arange(len(last4)), last4, 1)[0]) if len(last4) == 4 else np.nan
    hist = v[-53:-1] if len(v) >= 53 else v[:-1]
    return {f"{prefix}_level": float(v[-1]), f"{prefix}_mean4": float(last4.mean()),
            f"{prefix}_slope4": slope, f"{prefix}_abnormal": robust_z(v[-1], hist),
            f"{prefix}_last_close": (ok.week.values[-1] + np.timedelta64(6, "D"))}


def main() -> int:
    qm = pd.read_csv(QMAP)
    tickers = list(qm.ticker)
    if not TRENDS.exists():
        print("DATA_UNAVAILABLE: trends cache missing")
        return 1
    tr = pd.read_csv(TRENDS, parse_dates=["week"])
    px = fetch_prices(tickers)
    ev, revfacts = fetch_events(tickers)
    P = {s: g.reset_index(drop=True) for s, g in px.groupby("symbol")}

    have = {(t, k) for t, k in tr.groupby(["ticker", "kind"]).groups}
    unavailable = [t for t in tickers if (t, "consumer") not in have or (t, "investor") not in have]

    rows, leak_checks, dropped = [], [], []
    for t in tickers:
        if t in unavailable:
            continue
        p = P.get(t)
        if p is None:
            dropped.append((t, "", "no prices")); continue
        te = ev[ev.ticker == t].sort_values("filing_date")
        cons = tr[(tr.ticker == t) & (tr.kind == "consumer")]
        inv = tr[(tr.ticker == t) & (tr.kind == "investor")]
        rf = sorted(revfacts.get(t, []), key=lambda x: x["end"])
        prior_moves = []
        for _, r in te.iterrows():
            ann = pd.Timestamp(r.acceptance)
            if ann.tzinfo is not None:
                ann = ann.tz_convert("America/New_York").tz_localize(None)
            d = pd.Timestamp(r.filing_date).normalize()
            is_bmo = ann.hour < 9 or (ann.hour == 9 and ann.minute < 30)
            same = p.index[p.Date == d]
            if is_bmo and len(same) == 1:
                T, timing = int(same[0]), "BMO"
            else:
                nxt = p.index[p.Date > d]
                if not len(nxt):
                    dropped.append((t, str(d.date()), "no session after announcement")); continue
                T, timing = int(nxt[0]), ("AMC" if ann.hour >= 16 else "NON_TRADING_OR_INTRADAY")
            if T < 21 or T >= len(p):
                dropped.append((t, str(d.date()), "insufficient prior sessions")); continue
            c = p.Close.values
            ret = float(c[T] / c[T - 1] - 1.0)
            absmove = abs(ret)
            dr = c[T - 20:T] / c[T - 21:T - 1] - 1.0
            rvol = float(np.std(dr, ddof=1))
            pm = prior_moves[-4:]
            base = {"prior4_mean_abs_move": float(np.mean(pm)) if len(pm) == 4 else np.nan,
                    "prior4_median_abs_move": float(np.median(pm)) if len(pm) == 4 else np.nan,
                    "realized_vol_20d": rvol}
            # prior-quarter YoY revenue growth, point-in-time: both quarters must have been
            # FILED strictly before this announcement.
            g = np.nan
            # One value per period end: a long filer restates and re-files the same
            # quarter under several accessions, so keep the EARLIEST-filed value for
            # each end date. Without this the year-ago match is ambiguous and the
            # feature silently drops every established company.
            avail = {}
            for x in rf:
                if not x["filed"] or pd.Timestamp(x["filed"]) >= d:
                    continue
                k = x["end"]
                if k not in avail or pd.Timestamp(x["filed"]) < pd.Timestamp(avail[k]["filed"]):
                    avail[k] = x
            if avail:
                ends = sorted(avail)
                last = avail[ends[-1]]
                tgt = pd.Timestamp(last["end"]) - pd.Timedelta(days=365)
                yr = [avail[e] for e in ends
                      if abs((pd.Timestamp(e) - tgt).days) <= 20 and pd.Timestamp(e) < pd.Timestamp(last["end"])]
                if len(yr) == 1 and yr[0]["val"]:
                    g = float(last["val"] / yr[0]["val"] - 1.0)
            base["prior_rev_growth_yoy"] = g
            f_inv = search_features(inv, ann, "inv")
            f_prd = search_features(cons, ann, "prd")
            for lbl, f in (("investor", f_inv), ("product", f_prd)):
                lc = f.pop(f"{'inv' if lbl == 'investor' else 'prd'}_last_close")
                if lc is not None:
                    leak_checks.append({"ticker": t, "announcement": str(ann),
                                        "series": lbl, "last_week_close": str(pd.Timestamp(lc)),
                                        "closes_before_announcement": bool(pd.Timestamp(lc) < ann)})
            rows.append({"ticker": t, "announcement": ann, "event_date": str(p.Date.values[T])[:10],
                         "timing": timing, "abs_move": absmove, "quarter": ann.quarter,
                         **base, **f_inv, **f_prd})
            prior_moves.append(absmove)

    d = pd.DataFrame(rows).sort_values("announcement").reset_index(drop=True)
    d = d.drop_duplicates(subset=["ticker", "event_date"])
    leaks = pd.DataFrame(leak_checks)

    res: dict = {
        "artifact": "RESTAURANT_SEARCH_PILOT_RESULTS", "version": "1.0",
        "status": "EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY",
        "hyp01_confirmation": False, "prospective_collection": False,
        "targets_direction": False, "target": "magnitude (large-move indicator)",
        "frozen_queries": qm.to_dict("records"),
        "unavailable_tickers": unavailable,
        "overlapping_gst_spike_window_used": False,
        "search_transformation": "robust z: (x - median52) / (1.4826 * MAD52); one fixed transformation",
        "stitching_note": ("weekly resolution requires windows under ~5 years; two overlapping "
                           "sub-5-year pulls were stitched on the overlap median ratio, a fixed "
                           "procedure declared before outcomes"),
        "regularization_grid": {"logistic_C": LOGIT_GRID, "ridge_alpha": RIDGE_GRID,
                                "selected": "inside each training fold only"},
        "options_history": "OPTIONS_HISTORY_UNAVAILABLE",
        "options_history_detail": ("no per-event pre-announcement implied move exists for these "
                                   "tickers in the repository (the committed IV files cover one "
                                   "ticker and are keyed on the forbidden GST spike window), and "
                                   "no authenticated options provider is configured. Current "
                                   "options data was NOT substituted and no implied move was "
                                   "reconstructed from realized returns."),
    }

    # mechanical leakage assertion
    bad = leaks[~leaks.closes_before_announcement] if len(leaks) else pd.DataFrame()
    res["leakage_assertion"] = {"checks": int(len(leaks)), "violations": int(len(bad)),
                                "passed": bool(len(bad) == 0)}
    if len(bad):
        res["decision_label"] = "DATA_UNAVAILABLE"
        res["blocker"] = "search weeks did not close before the announcement"
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
        print("LEAKAGE VIOLATION - stopping"); return 1

    usable = d.dropna(subset=BASE_F + INV_F + PRD_F + ["abs_move"]).reset_index(drop=True)
    res["sample"] = {"tickers_usable": sorted(usable.ticker.unique().tolist()),
                     "events_built": int(len(d)), "events_complete": int(len(usable)),
                     "by_ticker": usable.ticker.value_counts().to_dict(),
                     "date_range": [str(usable.announcement.min())[:10],
                                    str(usable.announcement.max())[:10]] if len(usable) else None,
                     "timing_counts": usable.timing.value_counts().to_dict(),
                     "dropped": len(dropped),
                     "drop_reasons": pd.Series([x[2] for x in dropped]).value_counts().to_dict() if dropped else {}}

    if len(usable) < MIN_TRAIN + 10:
        res["decision_label"] = "DATA_UNAVAILABLE"
        res["blocker"] = f"only {len(usable)} complete events; need > {MIN_TRAIN + 10}"
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
        print("DATA_UNAVAILABLE:", res["blocker"]); return 0

    SETS = {"B": BASE_F, "C": BASE_F + INV_F, "D": BASE_F + INV_F + PRD_F}
    preds = {k: [] for k in ("A", "B", "C", "D")}
    cont = {k: [] for k in ("B", "C", "D")}
    keep = []
    for i in range(MIN_TRAIN, len(usable)):
        tr_ = usable.iloc[:i]
        te_ = usable.iloc[i:i + 1]
        thr = float(tr_.abs_move.quantile(TAIL_Q))          # training fold only
        ytr = (tr_.abs_move.values > thr).astype(int)
        yte = int(te_.abs_move.values[0] > thr)
        if len(np.unique(ytr)) < 2:
            continue
        preds["A"].append(float(ytr.mean()))
        qd_tr = pd.get_dummies(tr_.quarter, prefix="q").reindex(columns=[f"q_{k}" for k in (1, 2, 3, 4)], fill_value=0)
        qd_te = pd.get_dummies(te_.quarter, prefix="q").reindex(columns=[f"q_{k}" for k in (1, 2, 3, 4)], fill_value=0)
        td_tr = pd.get_dummies(tr_.ticker, prefix="t")
        td_te = pd.get_dummies(te_.ticker, prefix="t").reindex(columns=td_tr.columns, fill_value=0)
        for name, feats in SETS.items():
            Xtr = np.column_stack([tr_[feats].values.astype(float), qd_tr.values, td_tr.values])
            Xte = np.column_stack([te_[feats].values.astype(float), qd_te.values, td_te.values])
            mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1.0
            Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd
            best_c, best_s = LOGIT_GRID[0], np.inf
            for C in LOGIT_GRID:                       # selected on TRAINING data only
                m = LogisticRegression(C=C, max_iter=2000, random_state=0).fit(Ztr, ytr)
                s = brier_score_loss(ytr, m.predict_proba(Ztr)[:, 1])
                if s < best_s:
                    best_c, best_s = C, s
            m = LogisticRegression(C=best_c, max_iter=2000, random_state=0).fit(Ztr, ytr)
            preds[name].append(float(m.predict_proba(Zte)[0, 1]))
            best_a, best_r = RIDGE_GRID[0], np.inf
            for a in RIDGE_GRID:
                rm = Ridge(alpha=a).fit(Ztr, tr_.abs_move.values)
                r = float(np.mean(np.abs(tr_.abs_move.values - rm.predict(Ztr))))
                if r < best_r:
                    best_a, best_r = a, r
            rm = Ridge(alpha=best_a).fit(Ztr, tr_.abs_move.values)
            cont[name].append(float(rm.predict(Zte)[0]))
        k = te_.iloc[0].to_dict(); k["y_large"] = yte; k["train_threshold"] = thr
        keep.append(k)

    oos = pd.DataFrame(keep).reset_index(drop=True)
    for k in preds:
        oos[f"p_{k}"] = preds[k]
    for k in cont:
        oos[f"c_{k}"] = cont[k]
    y = oos.y_large.values

    def sc(p):
        p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
        return {"n": int(len(y)), "brier": round(float(brier_score_loss(y, p)), 5),
                "log_loss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 5),
                "auc": round(float(roc_auc_score(y, p)), 4) if len(np.unique(y)) > 1 and len(np.unique(p)) > 1 else None,
                "accuracy_at_0.5": round(float(((p > 0.5).astype(int) == y).mean()), 4)}

    res["out_of_sample"] = {"n_events": int(len(oos)), "large_move_rate": round(float(y.mean()), 4),
                            "tickers": int(oos.ticker.nunique())}
    res["models"] = {n: sc(oos[f"p_{n}"].values) for n in ("A", "B", "C", "D")}
    res["continuous_mae_abs_move_pp"] = {
        n: round(100 * float(np.mean(np.abs(oos.abs_move.values - oos[f"c_{n}"].values))), 4)
        for n in ("B", "C", "D")}

    # top predicted quintile realized large-move rate
    res["top_quintile_large_move_rate"] = {}
    for n in ("B", "C", "D"):
        q = pd.qcut(oos[f"p_{n}"], 5, labels=False, duplicates="drop")
        top = q == max(pd.Series(q).dropna().unique())
        res["top_quintile_large_move_rate"][n] = {
            "n": int(top.sum()), "rate": round(float(y[top.values].mean()), 4),
            "lift_vs_base": round(float(y[top.values].mean() / y.mean()), 4) if y.mean() else None}
    res["calibration_D"] = []
    qd = pd.qcut(oos.p_D, 4, labels=False, duplicates="drop")
    for k in sorted(pd.Series(qd).dropna().unique()):
        m = (qd == k).values
        res["calibration_D"].append({"bin": int(k) + 1, "n": int(m.sum()),
                                     "mean_predicted": round(float(oos.p_D[m].mean()), 4),
                                     "observed_rate": round(float(y[m].mean()), 4)})

    # ---- central incremental test: Brier loss(C) - Brier loss(D) ----
    lc = (oos.p_C.values - y) ** 2
    ld = (oos.p_D.values - y) ** 2
    diff = lc - ld
    inc = {"definition": "Brier loss(C) - Brier loss(D); positive means product demand helped",
           "raw_mean": round(float(diff.mean()), 6),
           "raw_ci95": [round(float(diff.mean() - 1.96 * diff.std(ddof=1) / math.sqrt(len(diff))), 6),
                        round(float(diff.mean() + 1.96 * diff.std(ddof=1) / math.sqrt(len(diff))), 6)],
           "pct_events_D_beats_C": round(100 * float((diff > 0).mean()), 2)}
    if oos.ticker.nunique() >= 3:
        from hyp01_inference_feasibility import cr_vcov, satterthwaite_df
        from scipy import stats
        X = np.ones((len(diff), 1))
        g = oos.ticker.values
        beta, V, G = cr_vcov(X, diff.astype(float), g, "CR2")
        se = float(math.sqrt(max(V[0, 0], 0.0)))
        dfree = satterthwaite_df(X, g, np.array([1.0]))
        b = float(beta[0]); t = b / se if se > 0 else float("nan")
        inc["clustered"] = {"vcov": "CR2 (BRL)", "cluster_unit": "ticker", "n_clusters": int(G),
                            "mean": round(b, 6), "cr2_se": round(se, 6),
                            "satterthwaite_df": round(dfree, 3), "t_stat": round(t, 3),
                            "p_value": round(float(2 * stats.t.sf(abs(t), dfree)), 5),
                            "ci95": [round(b - stats.t.ppf(.975, dfree) * se, 6),
                                     round(b + stats.t.ppf(.975, dfree) * se, 6)]}
    res["incremental_C_vs_D"] = inc

    M = res["models"]
    d_beats_c = M["D"]["brier"] < M["C"]["brier"]
    cl = inc.get("clustered", {})
    supported = bool(d_beats_c and cl.get("p_value", 1) < 0.05 and cl.get("mean", 0) > 0)
    c_beats_b = M["C"]["brier"] < M["B"]["brier"]
    if supported:
        label = "PRODUCT_DEMAND_ADDS_INCREMENTAL_VALUE"
    elif c_beats_b:
        label = "INVESTOR_ATTENTION_ONLY"
    else:
        label = "NO_INCREMENTAL_SEARCH_VALUE"
    res["decision_label"] = label
    res["label_basis"] = {"D_beats_C_on_pooled_brier": d_beats_c,
                          "clustered_interval_supports_positive": bool(cl.get("p_value", 1) < 0.05
                                                                       and cl.get("mean", 0) > 0),
                          "C_beats_B_on_pooled_brier": c_beats_b,
                          "note": "secondary metrics alone cannot trigger the positive label"}

    oos.to_csv(PANEL, index=False, lineterminator="\n")
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    print(f"usable tickers {len(res['sample']['tickers_usable'])} | complete events {len(usable)} | OOS {len(oos)}")
    for n in ("A", "B", "C", "D"):
        print(f"  {n}: brier={M[n]['brier']} logloss={M[n]['log_loss']} auc={M[n]['auc']}")
    print(f"  MAE |move| pp: {res['continuous_mae_abs_move_pp']}")
    print(f"  C-D raw mean {inc['raw_mean']} | D beats C {inc['pct_events_D_beats_C']}%"
          + (f" | clustered p={cl.get('p_value')} CI {cl.get('ci95')}" if cl else ""))
    print(f"  leakage checks {res['leakage_assertion']['checks']} violations {res['leakage_assertion']['violations']}")
    print(f"  DECISION: {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
