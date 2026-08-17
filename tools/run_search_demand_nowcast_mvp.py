#!/usr/bin/env python3
"""Does brand search demand improve out-of-sample quarterly revenue-growth nowcasts?

EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY. A fundamentals-nowcasting study. No stock
return, option, analyst estimate or prospective HYP-01 outcome is retrieved or used.
Ticker GST is NOT used: brand-demand search is a different construct from ticker
attention, and only the frozen brand queries enter this study.

POINT-IN-TIME LIMITATION - READ FIRST
  Google Trends series retrieved today are a RETROSPECTIVE RECONSTRUCTION. Google
  rescales to the maximum of the requested window and may revise its sampling, so the
  identical series was not necessarily available in this form at the time each quarter
  closed. This MVP can generate a prospective hypothesis; it CANNOT establish that the
  historical series was available in identical form contemporaneously.

FROZEN DESIGN (fixed before any outcome was computed)
  Universe/queries  Live Signal Engine/Search_Demand_Nowcast/frozen_query_map_v1.0.csv
                    geo=US, gprop=web, cat=0, weekly, exact query strings, no related-
                    query selection and no outcome-informed substitution.
  Outcome           revenue_growth_yoy = rev(q) / rev(same fiscal quarter prior year) - 1
  Search window     the company's own fiscal quarter [start, end]; it ends at quarter
                    end, strictly BEFORE the earnings release, so no post-release search
                    week can enter a feature.
  Search features   exactly two:
                      s1 quarter-average search interest
                      s2 surprise = (s1 - mean of the preceding 4 available quarters)
                         / stdev of those quarters, where defined
                    All normalization uses EARLIER quarters only.
  Models            A expanding company-level historical mean
                    B ridge(alpha=1.0) on prior-quarter growth, growth 4 quarters back,
                      mean growth over preceding 4, fiscal-quarter indicators, company
                      indicators
                    C identical to B plus s1 and s2
  Validation        chronological expanding window; test quarters REPORTED in 2023, then
                    2024, then 2025. Scaling fitted inside each training fold only.
  Primary metric    out-of-sample MAE in revenue-growth percentage points
  Decisive test     paired |error(B)| - |error(C)|; positive means search helps
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
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
OUT = ROOT / "Live Signal Engine" / "Search_Demand_Nowcast"
OUT.mkdir(parents=True, exist_ok=True)
QMAP = OUT / "frozen_query_map_v1.0.csv"
PANEL = OUT / "company_quarter_panel_v1.0.csv"
TRENDS_CACHE = OUT / "search_interest_weekly_v1.0.csv"
RESULTS = ROOT / "SEARCH_DEMAND_NOWCAST_RESULTS_v1.0.json"

UA = {"User-Agent": "gst-earnings-signal-research academic research (hakurati11@gmail.com)"}
# Google serves WEEKLY resolution only for windows up to ~5 years; an 8-year request
# silently returns MONTHLY points. 2021-2025 keeps weekly resolution and still leaves
# 2021-2022 available for the year-ago revenue and the 4-quarter search baseline that
# a 2023 test observation needs.
TRENDS_START, TRENDS_END = "2021-01-01", "2025-12-31"
REV_CONCEPTS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]
TEST_YEARS = ["2023", "2024", "2025"]
RIDGE_ALPHA = 1.0
MIN_QUARTERS, MIN_OOS, MIN_OOS_COMPANIES = 60, 40, 6

BASE_FEATURES = ["growth_lag1", "growth_lag4", "growth_mean_prev4"]
SEARCH_FEATURES = ["search_quarter_avg", "search_surprise"]


def sec_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return json.loads(r.read())


def fetch_trends(qmap: pd.DataFrame) -> pd.DataFrame:
    if TRENDS_CACHE.exists():
        return pd.read_csv(TRENDS_CACHE, parse_dates=["week"])
    from pytrends.request import TrendReq
    rows = []
    pt = TrendReq(hl="en-US", tz=360)
    for _, r in qmap.iterrows():
        try:
            pt.build_payload([r.frozen_search_query],
                             timeframe=f"{TRENDS_START} {TRENDS_END}",
                             geo="US", gprop="", cat=0)
            d = pt.interest_over_time()
            if d is None or d.empty:
                print(f"  [{r.ticker}] frozen query returned no data - marked unavailable")
                continue
            d = d[~d.get("isPartial", False).astype(bool)] if "isPartial" in d else d
            for wk, v in d[r.frozen_search_query].items():
                rows.append({"ticker": r.ticker, "query": r.frozen_search_query,
                             "week": pd.Timestamp(wk), "interest": float(v)})
            print(f"  [{r.ticker}] {len(d)} weekly points")
        except Exception as e:                                    # noqa: BLE001
            print(f"  [{r.ticker}] trends error: {type(e).__name__}: {str(e)[:90]}")
        time.sleep(2.0)
    t = pd.DataFrame(rows)
    if len(t):
        t.to_csv(TRENDS_CACHE, index=False, lineterminator="\n")
    return t


def fetch_revenue(tickers: list[str]) -> tuple[pd.DataFrame, dict]:
    ct = sec_json("https://www.sec.gov/files/company_tickers.json")
    cik = {v["ticker"]: int(v["cik_str"]) for v in ct.values()}
    rows, releases, concept_used = [], [], {}
    for t in tickers:
        c = cik.get(t)
        if c is None:
            continue
        facts = sec_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c:010d}.json")
        gaap = facts.get("facts", {}).get("us-gaap", {})
        best, best_n = None, 0
        for concept in REV_CONCEPTS:
            if concept not in gaap:
                continue
            us = gaap[concept]["units"].get("USD", [])
            q = [x for x in us if x.get("start") and x.get("end")
                 and 80 <= (pd.Timestamp(x["end"]) - pd.Timestamp(x["start"])).days <= 100]
            if len(q) > best_n:
                best, best_n = (concept, q), len(q)
        if not best:
            continue
        concept, q = best
        concept_used[t] = concept
        for x in q:
            rows.append({"ticker": t, "cik": c, "concept": concept,
                         "q_start": pd.Timestamp(x["start"]), "q_end": pd.Timestamp(x["end"]),
                         "revenue": float(x["val"]), "fy": x.get("fy"), "fp": x.get("fp"),
                         "form": x.get("form"), "accn": x.get("accn"),
                         "filed": pd.Timestamp(x.get("filed"))})
        # earnings release dates: 8-K item 2.02
        sub = sec_json(f"https://data.sec.gov/submissions/CIK{c:010d}.json")
        rec = sub["filings"]["recent"]
        for form, items, fdate in zip(rec["form"], rec["items"], rec["filingDate"]):
            if form == "8-K" and "2.02" in (items or ""):
                releases.append({"ticker": t, "release_date": pd.Timestamp(fdate)})
        time.sleep(0.3)
    rev = pd.DataFrame(rows)
    # DEDUPLICATE by ticker, fiscal period and accession before modeling
    rev = rev.drop_duplicates(subset=["ticker", "q_start", "q_end", "accn"])
    rev = (rev.sort_values(["ticker", "q_end", "filed"])
              .drop_duplicates(subset=["ticker", "q_start", "q_end"], keep="first")
              .reset_index(drop=True))
    return rev, {"releases": pd.DataFrame(releases).drop_duplicates(),
                 "concept_used": concept_used}


def build_panel(rev: pd.DataFrame, releases: pd.DataFrame, trends: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for t, g in rev.groupby("ticker"):
        g = g.sort_values("q_end").reset_index(drop=True)
        tr = trends[trends.ticker == t] if len(trends) else pd.DataFrame()
        rel = releases[releases.ticker == t].sort_values("release_date") if len(releases) else pd.DataFrame()
        for i, r in g.iterrows():
            # year-ago quarter: nearest q_end ~365 days earlier
            tgt = r.q_end - pd.Timedelta(days=365)
            prior = g[(g.q_end - tgt).abs() <= pd.Timedelta(days=20)]
            prior = prior[prior.q_end < r.q_end]
            if len(prior) != 1:
                continue
            growth = float(r.revenue / prior.iloc[0].revenue - 1.0)
            # earnings release strictly after quarter end
            rd = None
            if len(rel):
                after = rel[rel.release_date > r.q_end]
                if len(after):
                    rd = after.iloc[0].release_date
            s1 = float("nan")
            if len(tr):
                w = tr[(tr.week >= r.q_start) & (tr.week <= r.q_end)]
                if len(w) >= 8:
                    s1 = float(w.interest.mean())
            rows.append({"ticker": t, "q_start": r.q_start, "q_end": r.q_end,
                         "fiscal_quarter": r.fp, "revenue": r.revenue,
                         "growth_yoy": growth, "release_date": rd, "accn": r.accn,
                         "search_quarter_avg": s1})
    p = pd.DataFrame(rows).sort_values(["ticker", "q_end"]).reset_index(drop=True)

    # lags and the search surprise, all from EARLIER quarters only
    out = []
    for t, g in p.groupby("ticker"):
        g = g.sort_values("q_end").reset_index(drop=True)
        g["growth_lag1"] = g.growth_yoy.shift(1)
        g["growth_lag4"] = g.growth_yoy.shift(4)
        g["growth_mean_prev4"] = g.growth_yoy.shift(1).rolling(4).mean()
        base_m = g.search_quarter_avg.shift(1).rolling(4).mean()
        base_s = g.search_quarter_avg.shift(1).rolling(4).std(ddof=1)
        g["search_surprise"] = (g.search_quarter_avg - base_m) / base_s.replace(0, np.nan)
        out.append(g)
    p = pd.concat(out, ignore_index=True)
    p["report_year"] = p.release_date.dt.year.astype("Int64").astype(str)
    return p


def scores(y, pred, base) -> dict:
    y, pred, base = np.asarray(y, float), np.asarray(pred, float), np.asarray(base, float)
    mae = float(np.mean(np.abs(y - pred)))
    rmse = float(math.sqrt(np.mean((y - pred) ** 2)))
    ss, ss0 = float(np.sum((y - pred) ** 2)), float(np.sum((y - base) ** 2))
    return {"n": int(len(y)), "mae_pp": round(100 * mae, 4), "rmse_pp": round(100 * rmse, 4),
            "r2_vs_model_a": round(1 - ss / ss0, 5) if ss0 > 0 else None}


def fit_fold(tr, te, feats):
    Xtr, Xte = tr[feats].values.astype(float), te[feats].values.astype(float)
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    m = Ridge(alpha=RIDGE_ALPHA)
    m.fit((Xtr - mu) / sd, tr.growth_yoy.values)
    return m.predict((Xte - mu) / sd)


def main() -> int:
    qmap = pd.read_csv(QMAP)
    trends = fetch_trends(qmap)
    rev, meta = fetch_revenue(list(qmap.ticker))
    panel = build_panel(rev, meta["releases"], trends)

    unavailable = sorted(set(qmap.ticker) - set(trends.ticker.unique())) if len(trends) else list(qmap.ticker)
    res: dict = {
        "artifact": "SEARCH_DEMAND_NOWCAST_RESULTS", "version": "1.0",
        "status": "EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY",
        "study_type": "fundamentals nowcasting; NOT a stock-return or trading study",
        "ticker_gst_used": False,
        "stock_returns_or_options_retrieved": False,
        "point_in_time_limitation": (
            "Google Trends series retrieved today are a RETROSPECTIVE RECONSTRUCTION. Google "
            "rescales to the requested window's maximum and may revise sampling, so the identical "
            "series was not necessarily available at the time each quarter closed. This MVP can "
            "generate a prospective hypothesis; it cannot establish contemporaneous availability."),
        "frozen_queries": qmap.to_dict("records"),
        "companies_unavailable": unavailable,
        "search_parameters": {"geo": "US", "gprop": "web", "category": 0, "frequency": "weekly",
                              "related_query_selection": False,
                              "outcome_informed_substitution": False},
        "search_features": SEARCH_FEATURES,
        "revenue_concepts_used": meta["concept_used"],
        "models": {"A": "expanding company-level historical mean",
                   "B": f"ridge(alpha={RIDGE_ALPHA}) on fundamentals + fiscal-quarter + company indicators",
                   "C": "B plus the two frozen search-demand features"},
        "no_model_or_hyperparameter_search": True,
    }

    usable = panel.dropna(subset=BASE_FEATURES + SEARCH_FEATURES + ["growth_yoy"])
    usable = usable[usable.report_year.isin([str(y) for y in range(2019, 2027)])]
    res["sample"] = {
        "raw_quarterly_revenue_facts": int(len(rev)),
        "panel_company_quarters": int(len(panel)),
        "eligible_company_quarters": int(len(usable)),
        "companies": sorted(usable.ticker.unique().tolist()),
        "date_range": [str(usable.q_end.min().date()), str(usable.q_end.max().date())] if len(usable) else None,
    }

    folds, keep = [], []
    for ty in TEST_YEARS:
        tr = usable[usable.report_year < ty]
        te = usable[usable.report_year == ty]
        if len(tr) < 20 or len(te) == 0:
            folds.append({"test_year": ty, "status": "SKIPPED", "n_train": int(len(tr)),
                          "n_test": int(len(te))})
            continue
        feats_q = pd.get_dummies(usable.fiscal_quarter, prefix="fq")
        feats_c = pd.get_dummies(usable.ticker, prefix="co")
        aug = pd.concat([usable, feats_q, feats_c], axis=1)
        cols_b = BASE_FEATURES + list(feats_q.columns) + list(feats_c.columns)
        cols_c = cols_b + SEARCH_FEATURES
        atr, ate = aug[aug.report_year < ty], aug[aug.report_year == ty]
        pa = np.array([atr[atr.ticker == r.ticker].growth_yoy.mean()
                       if len(atr[atr.ticker == r.ticker]) else atr.growth_yoy.mean()
                       for r in ate.itertuples()])
        pb = fit_fold(atr, ate, cols_b)
        pc = fit_fold(atr, ate, cols_c)
        t2 = ate.copy()
        t2["pred_A"], t2["pred_B"], t2["pred_C"] = pa, pb, pc
        keep.append(t2)
        folds.append({"test_year": ty, "n_train": int(len(atr)), "n_test": int(len(ate)),
                      "A": scores(ate.growth_yoy, pa, pa), "B": scores(ate.growth_yoy, pb, pa),
                      "C": scores(ate.growth_yoy, pc, pa)})
    res["folds"] = folds

    if not keep:
        res["decision_label"] = "INSUFFICIENT_DATA"
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
        print("INSUFFICIENT_DATA: no usable fold")
        return 0

    oos = pd.concat(keep, ignore_index=True)
    res["out_of_sample"] = {"n": int(len(oos)), "companies": int(oos.ticker.nunique())}
    gates = {"min_eligible_quarters": len(usable) >= MIN_QUARTERS,
             "min_oos_observations": len(oos) >= MIN_OOS,
             "min_oos_companies": oos.ticker.nunique() >= MIN_OOS_COMPANIES}
    res["minimum_sample_gates"] = {**gates,
                                   "required": {"eligible_quarters": MIN_QUARTERS,
                                                "oos_observations": MIN_OOS,
                                                "oos_companies": MIN_OOS_COMPANIES},
                                   "observed": {"eligible_quarters": int(len(usable)),
                                                "oos_observations": int(len(oos)),
                                                "oos_companies": int(oos.ticker.nunique())}}

    y = oos.growth_yoy.values
    res["pooled_out_of_sample"] = {
        "A_historical_mean": scores(y, oos.pred_A, oos.pred_A),
        "B_fundamental": scores(y, oos.pred_B, oos.pred_A),
        "C_fundamental_plus_search": scores(y, oos.pred_C, oos.pred_A)}
    mae_b = res["pooled_out_of_sample"]["B_fundamental"]["mae_pp"]
    mae_c = res["pooled_out_of_sample"]["C_fundamental_plus_search"]["mae_pp"]
    res["mae_improvement_pct"] = round(100 * (mae_b - mae_c) / mae_b, 4) if mae_b else None

    oos["abs_err_B"] = np.abs(y - oos.pred_B.values)
    oos["abs_err_C"] = np.abs(y - oos.pred_C.values)
    oos["loss_diff"] = oos.abs_err_B - oos.abs_err_C
    dec = {"definition": "abs_error(B) - abs_error(C); positive means search helps",
           "mean_pp": round(100 * float(oos.loss_diff.mean()), 5),
           "median_pp": round(100 * float(oos.loss_diff.median()), 5),
           "pct_events_C_wins": round(100 * float((oos.loss_diff > 0).mean()), 2),
           "by_test_year": {ty: round(100 * float(oos[oos.report_year == ty].loss_diff.mean()), 5)
                            for ty in TEST_YEARS if (oos.report_year == ty).any()}}
    if oos.ticker.nunique() >= 5:
        from hyp01_inference_feasibility import cr_vcov, satterthwaite_df
        from scipy import stats
        yv = 100 * oos.loss_diff.values.astype(float)
        X = np.ones((len(oos), 1))
        g = oos.ticker.values
        beta, V, G = cr_vcov(X, yv, g, "CR2")
        se = float(math.sqrt(max(V[0, 0], 0.0)))
        dfree = satterthwaite_df(X, g, np.array([1.0]))
        b = float(beta[0]); t = b / se if se > 0 else float("nan")
        dec["clustered"] = {"vcov": "CR2 (BRL)", "cluster_unit": "ticker", "n_clusters": int(G),
                            "mean_pp": round(b, 5), "cr2_se_pp": round(se, 5),
                            "satterthwaite_df": round(dfree, 3), "t_stat": round(t, 3),
                            "p_value": round(float(2 * stats.t.sf(abs(t), dfree)), 5),
                            "ci95_pp": [round(b - stats.t.ppf(.975, dfree) * se, 5),
                                        round(b + stats.t.ppf(.975, dfree) * se, 5)]}
    res["decisive_paired_comparison"] = dec

    res["by_company"] = {c: {"n": int(len(v)),
                             "mae_B_pp": round(100 * float(v.abs_err_B.mean()), 4),
                             "mae_C_pp": round(100 * float(v.abs_err_C.mean()), 4),
                             "improvement_pp": round(100 * float(v.loss_diff.mean()), 4)}
                         for c, v in oos.groupby("ticker")}
    res["by_test_year"] = {f["test_year"]: {"A_mae": f["A"]["mae_pp"], "B_mae": f["B"]["mae_pp"],
                                            "C_mae": f["C"]["mae_pp"]}
                           for f in folds if "A" in f}
    # acceleration sign: did growth rise vs the prior quarter, and did the model get it right?
    oos = oos.sort_values(["ticker", "q_end"])
    oos["actual_accel"] = np.sign(oos.growth_yoy - oos.growth_lag1)
    for m in ("B", "C"):
        oos[f"pred_accel_{m}"] = np.sign(oos[f"pred_{m}"] - oos.growth_lag1)
    res["acceleration_sign_accuracy"] = {
        m: round(100 * float((oos[f"pred_accel_{m}"] == oos.actual_accel).mean()), 2)
        for m in ("B", "C")}
    q = pd.qcut(oos.pred_C, 5, labels=False, duplicates="drop")
    res["calibration_by_predicted_quintile_C"] = [
        {"quintile": int(k) + 1, "n": int((q == k).sum()),
         "mean_predicted_pct": round(100 * float(oos.pred_C[q == k].mean()), 4),
         "mean_actual_pct": round(100 * float(oos.growth_yoy[q == k].mean()), 4)}
        for k in sorted(pd.Series(q).dropna().unique())]

    if not all(gates.values()):
        label = "INSUFFICIENT_DATA"
    else:
        cl = dec.get("clustered", {})
        primary_ok = mae_c < mae_b
        supported = bool(primary_ok and cl.get("p_value", 1) < 0.05 and cl.get("mean_pp", 0) > 0)
        secondary = bool((not primary_ok) and (
            res["pooled_out_of_sample"]["C_fundamental_plus_search"]["rmse_pp"]
            < res["pooled_out_of_sample"]["B_fundamental"]["rmse_pp"]
            or res["acceleration_sign_accuracy"]["C"] > res["acceleration_sign_accuracy"]["B"]))
        label = ("SEARCH_DEMAND_IMPROVES_FUNDAMENTAL_NOWCAST" if supported
                 else "SEARCH_DEMAND_SHOWS_SECONDARY_ONLY_VALUE" if secondary
                 else "SEARCH_DEMAND_ADDS_NO_VALUE")
    res["decision_label"] = label
    res["next_stage_rule"] = ("A later project may test whether a predicted fundamental surprise "
                              "helps forecast earnings-gap direction ONLY if search demand improves "
                              "the fixed primary MAE metric. No stock return was tested here.")

    oos[["ticker", "q_end", "fiscal_quarter", "report_year", "growth_yoy", "search_quarter_avg",
         "search_surprise", "pred_A", "pred_B", "pred_C", "abs_err_B", "abs_err_C",
         "loss_diff"]].to_csv(PANEL, index=False, lineterminator="\n")
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")

    P = res["pooled_out_of_sample"]
    print(f"eligible company-quarters: {len(usable)} | OOS: {len(oos)} across {oos.ticker.nunique()} companies")
    for k in P:
        print(f"  {k:28s} MAE={P[k]['mae_pp']}pp RMSE={P[k]['rmse_pp']}pp R2vsA={P[k]['r2_vs_model_a']}")
    print(f"  MAE improvement B->C: {res['mae_improvement_pct']}%")
    print(f"  paired mean {dec['mean_pp']} pp | C wins {dec['pct_events_C_wins']}% | by year {dec['by_test_year']}")
    if "clustered" in dec:
        c = dec["clustered"]
        print(f"  clustered: {c['mean_pp']} pp SE {c['cr2_se_pp']} t={c['t_stat']} p={c['p_value']} CI {c['ci95_pp']}")
    print(f"  DECISION: {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
