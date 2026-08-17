#!/usr/bin/env python3
"""Terminal temporal replication of the semiconductor surprise-absorption Stage 1.

Question: does vendor-defined earnings surprise improve chronological out-of-sample
prediction of the first full-session SMH-adjusted price reaction for the same ten
semiconductor companies during 2010-2017?

=================== FROZEN_TEMPORAL_REPLICATION_DESIGN ===================
Committed BEFORE any pre-2018 price or return observation was read.

NATURE OF THIS TEST
  This is a RETROSPECTIVE TEMPORAL REPLICATION motivated by PR #34's suggestive but
  gate-failing result. It is NOT a prospectively registered independent replication.
  It is exploratory retrospective development, NOT preregistered evidence.
  This is the TERMINAL replication for this hypothesis. If it fails, the research path
  stops: no new specification, and NO THIRD REPLICATION IS PROPOSED.
  This is not a GST test. No Google Trends series is read.

CONSTRUCT -- unchanged from PR #34
  Predictor: VENDOR_DEFINED_REPORTED_EPS_SURPRISE. Primary field: surprisePercentage.
  POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED.
  It is NOT a GAAP surprise, NOT an SEC-validated surprise, NOT a guaranteed
  contemporaneous consensus, NOT preregistered evidence, NOT an investable signal.

REUSE DISCIPLINE
  Every model, transform, alpha grid, selection rule, tie-break, bootstrap and gate is
  IMPORTED from tools/run_semiconductor_surprise_absorption_v3.py and executed
  unmodified. Only the fold calendar and the data window differ. The imported module's
  own source is never edited. Its FOLDS and PRICE_CACHE globals are rebound at runtime
  to the replication calendar and a separate repository-external cache; that rebinding
  is explicit, recorded in the artifact, and asserted by the test.

UNIVERSE  exactly, with no addition, removal, replacement or outcome-based exclusion:
  NVDA, AMD, INTC, QCOM, AVGO, MU, TXN, AMAT, LRCX, KLAC
  A ticker lacking sufficient historical identity or data is REPORTED and left to the
  sample gate. It is never replaced.

PERIODS
  Training begins 2004-01-01. Replication OOS window 2010-01-01 .. 2017-12-31.
  Expanding folds, eight of them:
    train 2004-2009 -> test 2010 ... train 2004-2016 -> test 2017
  The 2018-2025 observations used by PR #34 MUST NOT enter this replication's fitting,
  transformations, hyperparameter selection, inference or gate. PR #34 may be referenced
  ONLY after the replication result is finalized, as a clearly secondary comparison.

EVENT IDENTITY AND CROSSWALK -- the same successor rule as PR #34
  Alpha Vantage ticker + EXACT reportedDate == the filing_date of a UNIQUE SEC Item 2.02
  8-K on the same ticker and calendar date. Zero ambiguous matches are permitted.
  Unmatched events are excluded WITHOUT replacement.
  Historical identity is resolved ONLY from authoritative SEC identity metadata, read
  before any outcome is opened: https://www.sec.gov/files/company_tickers.json for the
  ticker->CIK map, then the complete https://data.sec.gov/submissions/ history for that
  CIK, which means filings.recent AND every archived file listed under filings.files.
  Every CIK, entityName and formerNames entry actually used is recorded.
  Returns are NEVER used to resolve an identity.
  If a ticker's pre-2018 filing history is not reachable from its current CIK, its
  historical identity is NOT mechanically resolved: the affected records are EXCLUDED
  and the sample gate applies. No predecessor entity is guessed or hand-supplied.
  NOTE, recorded in advance: SEC Item 2.02 only came into force with the 8-K
  restructuring effective 2004-08-23. Earnings releases filed before that date carry a
  different item number and therefore cannot match. Those events are excluded by the
  unchanged rule, not by a new one. They fall entirely inside the training window.

EVENT TIMING -- identical to PR #34, in America/New_York
  acceptance < 09:30 ET on a trading day -> that trading session
  acceptance >= 16:00 ET                 -> next trading session
  weekend or market holiday              -> next trading session
  acceptance 09:30 ET .. < 16:00 ET      -> EXCLUDED
  Timing is never reinterpreted after a return is viewed.

PRICES AND RETURNS -- the same Yahoo split- and dividend-adjusted close series and the
  same direct urllib transport already recorded in PR #34. yfinance is NOT retried and
  no other provider is substituted.
  BENCHMARK = SMH.
    initial abnormal reaction AR0 = [c(T)/c(T-1) - 1] - [SMH(T)/SMH(T-1) - 1]
    primary subsequent AR5        = [c(T+5)/c(T) - 1] - [SMH(T+5)/SMH(T) - 1]
    secondary horizon             = T+20
  Entry, if trading ever becomes permitted, is close(T); every price defining AR0 is
  therefore known before that entry.
  SPLIT AUDIT: every absolute daily move >= 0.40 is REPORTED and DIAGNOSED as either a
  genuine move or an adjustment failure. None is deleted automatically.

SURPRISE TRANSFORM -- reused from PR #34 exactly, training fold only:
  signed_log = sign(x)*log1p(abs(x)); winsorize at the TRAINING fold's 1st/99th
  percentiles; standardize by the TRAINING fold's mean and sd; apply those frozen
  training values to the test fold. No full-sample transformation.

MODELS  Stage-1 Model B = intercept + ticker indicators.
        Stage-1 Model C = Model B + transformed vendor-defined surprise.
  Ridge grid unchanged: [0.0, 0.1, 1.0, 10.0], alpha chosen by chronological
  inner-training MAE with PR #34's tie-break toward the larger alpha. No grid
  expansion, no interactions, no nonlinear model, no extra controls, and no
  company-specific surprise slopes.

SAMPLE GATE -- checked before any model is fitted
  >= 8 tickers; >= 200 uniquely matched events across 2004-2017; >= 160 OOS events in
  2010-2017; >= 15 OOS events in EACH replication year; zero duplicate event
  identities; zero training/test identity overlap.
  Any failure -> DATA_INSUFFICIENT_FOR_TEMPORAL_REPLICATION, and NO model is fitted.

STAGE 1 REPLICATION GATE -- passes only if ALL FOUR hold
  1. pooled MAE improvement = 100*(MAE_B - MAE_C)/MAE_B >= 1.0%
  2. the 95% bootstrap interval for (MAE_B - MAE_C) lies ENTIRELY above zero
  3. Model C beats Model B in at least ceil(2 * N_years / 3) evaluable years
  4. the pooled surprise / initial-reaction relationship has the expected POSITIVE sign
  BOOTSTRAP: 2000 moving-block draws, 28-calendar-day blocks, every event in a sampled
  block retained together, seed 20260817, statistic (MAE_B - MAE_C).
  The 2010-2017 sample is NEVER combined with PR #34's 2023-2025 sample to determine
  these gates.
  FAILURE -> TEMPORAL_REPLICATION_FAILS, and then STOP: no information-price gap, no
  Stage 2, no trading, no new specification, and no proposed third replication. Whether
  the original and replication point estimates agree in sign is reported, but the failed
  gate is NEVER rescued by pooling them.

STAGE 2 -- only if every Stage-1 replication gate passes
  Gap = fold-specific OOS predicted AR0 - observed AR0. Never an in-sample prediction.
  Model D = intercept + ticker indicators + observed AR0. Model E = D + gap.
  Same grid, selection, transforms, five-session outcome, bootstrap, and the
  ticker-clustered CR2/BRL + Satterthwaite implementation already specified in PR #34.
  Passes only if: improvement >= 1.0%; bootstrap interval for (MAE_D - MAE_E) entirely
  above zero; pooled Spearman IC positive; E beats D in >= ceil(2*N/3) years; gap
  coefficient positive.
  FAILURE -> NO_EVIDENCE_OF_INFORMATION_PRICE_UNDERREACTION and no trading.

STAGE 3 -- trading only if Stages 1 and 2 both pass
  Long top-quintile OOS gap, short bottom quintile, equal weight, enter close(T), exit
  close(T+5), deduct 10 bps round trip per stock trade, compared with an equal-count
  surprise-only strategy. No search over quantiles, horizons or costs.

SECONDARY REPORTING -- descriptive, and never a replacement for the primary gate
  by ticker; by year; fiscal-year-end quarters excluded; SEC-validated overlap only;
  twenty-session return only if Stage 2 is permitted; and the PR #34 result shown beside
  the completed replication result. No further analysis is added after viewing these.

LABELS  exactly one of
  DATA_INSUFFICIENT_FOR_TEMPORAL_REPLICATION | TEMPORAL_REPLICATION_FAILS |
  NO_EVIDENCE_OF_INFORMATION_PRICE_UNDERREACTION |
  PREDICTIVE_BUT_NOT_TRADABLE_AFTER_COSTS | EXPLORATORY_INFORMATION_PRICE_GAP_SIGNAL
================= END FROZEN_TEMPORAL_REPLICATION_DESIGN =================
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import run_semiconductor_surprise_absorption_v3 as V3  # noqa: E402

OUT = ROOT / "Live Signal Engine" / "Semiconductor_Surprise_Temporal_Replication"
RESULTS = ROOT / "SEMICONDUCTOR_SURPRISE_TEMPORAL_REPLICATION_RESULTS_v1.0.json"
PANEL_OUT = OUT / "event_panel_v1.0.csv"
AV_CACHE = ROOT.parent / "gst-av-earnings-cache"          # already-retrieved raw bodies
SEC_CACHE = ROOT.parent / "gst-sec-repl-cache"            # repository-external
PRICE_CACHE = ROOT.parent / "gst-price-cache-repl"        # repository-external

UNIVERSE = list(V3.UNIVERSE)
BENCH = V3.BENCH
TRAIN_START = "2004-01-01"
OOS_START, OOS_END = "2010-01-01", "2017-12-31"
REPL_YEARS = list(range(2010, 2018))
REPL_FOLDS = [((2004, y - 1), y) for y in REPL_YEARS]
PRICE_START, PRICE_END = "2003-01-01", "2018-06-01"
ITEM_202_EFFECTIVE = "2004-08-23"
SAMPLE_GATE = {"tickers": 8, "events": 200, "oos_events": 160, "oos_per_year": 15}
UA = {"User-Agent": "gst-earnings-signal-research academic research (hakurati11@gmail.com)"}
LABELS = ("DATA_INSUFFICIENT_FOR_TEMPORAL_REPLICATION",
          "TEMPORAL_REPLICATION_FAILS",
          "NO_EVIDENCE_OF_INFORMATION_PRICE_UNDERREACTION",
          "PREDICTIVE_BUT_NOT_TRADABLE_AFTER_COSTS",
          "EXPLORATORY_INFORMATION_PRICE_GAP_SIGNAL")

# Explicit, recorded rebinding of the imported module's calendar and price cache.
# The imported module's SOURCE is never edited; only these two globals are rebound so
# that the identical model code runs on the replication window.
V3.FOLDS = REPL_FOLDS
V3.PRICE_CACHE = PRICE_CACHE


def two_thirds(n):
    return math.ceil(2 * n / 3)


# --------------------------------------------------------------- SEC identity

def _get(url, key, cache=SEC_CACHE, pause=0.15):
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / key
    if f.exists():
        return f.read_bytes()
    b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
    f.write_bytes(b)
    time.sleep(pause)
    return b


def sec_identity_and_events():
    """Full 8-K Item 2.02 index for 2004-2017 from authoritative SEC metadata only."""
    ct = json.loads(_get("https://www.sec.gov/files/company_tickers.json", "cik.json"))
    cikmap = {v["ticker"]: int(v["cik_str"]) for v in ct.values()}
    rows, identity = [], {}
    for t in UNIVERSE:
        c = cikmap.get(t)
        if c is None:
            identity[t] = {"cik": None, "resolved": False,
                           "reason": "ticker absent from company_tickers.json"}
            continue
        sub = json.loads(_get(f"https://data.sec.gov/submissions/CIK{c:010d}.json",
                              f"sub_{t}.json"))
        blocks = [sub["filings"]["recent"]]
        archived = [f["name"] for f in sub["filings"].get("files", [])]
        for name in archived:
            blocks.append(json.loads(_get(f"https://data.sec.gov/submissions/{name}",
                                          f"arch_{t}_{name}")))
        n_before, earliest = 0, None
        for r in blocks:
            for form, items, fd, acc, adt in zip(r["form"], r["items"], r["filingDate"],
                                                 r["accessionNumber"],
                                                 r["acceptanceDateTime"]):
                if earliest is None or fd < earliest:
                    earliest = fd
                if fd < "2018-01-01":
                    n_before += 1
                if (form == "8-K" and "2.02" in (items or "")
                        and TRAIN_START <= fd <= OOS_END):
                    rows.append({"ticker": t, "cik": c, "accession": acc,
                                 "filing_date": fd, "acceptance_utc": adt})
        identity[t] = {
            "cik": c, "entity_name": sub.get("name"),
            "former_names": [f.get("name") for f in (sub.get("formerNames") or [])],
            "archived_submission_files": archived,
            "earliest_filing_under_this_cik": earliest,
            "filings_before_2018_under_this_cik": n_before,
            "resolved": bool(n_before > 0),
            "reason": (None if n_before > 0 else
                       "current CIK carries no pre-2018 filing history; the historical "
                       "issuer is a predecessor entity not reachable from the "
                       "authoritative ticker->CIK map. Records EXCLUDED, never replaced."),
        }
    return pd.DataFrame(rows), identity


# ------------------------------------------------------------ provider records

def av_records():
    """Pre-retrieved Alpha Vantage bodies. No new vendor call and no new parser."""
    recs, meta = [], []
    for t in UNIVERSE:
        f = AV_CACHE / f"AV_EARNINGS_{t}.json"
        if not f.exists():
            meta.append({"ticker": t, "status": "no cached provider body"})
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        n = 0
        for r in d.get("quarterlyEarnings", []) or []:
            rd, fpe = r.get("reportedDate"), r.get("fiscalDateEnding")
            sp = r.get("surprisePercentage")
            if not rd or not fpe or sp in (None, "None", ""):
                continue
            if not (TRAIN_START <= rd <= OOS_END):
                continue
            try:
                spv = float(sp)
            except (TypeError, ValueError):
                continue
            recs.append({"ticker": t, "reportedDate": rd, "fiscalDateEnding": fpe,
                         "surprisePercentage": spv})
            n += 1
        meta.append({"ticker": t, "records_2004_2017": n})
    return recs, meta


def crosswalk_exact(records, sec):
    key = {}
    for r in sec.itertuples(index=False):
        key.setdefault((r.ticker, str(r.filing_date)[:10]), []).append(r)
    rows, excl = [], {"no_match": 0, "ambiguous": 0}
    for r in records:
        c = key.get((r["ticker"], r["reportedDate"]), [])
        if len(c) == 0:
            excl["no_match"] += 1
            continue
        if len(c) > 1:
            excl["ambiguous"] += 1
            continue
        e = c[0]
        rows.append(dict(r, accession=e.accession, cik=e.cik,
                         acceptance_utc=e.acceptance_utc))
    return rows, excl


# ------------------------------------------------------------------ price audit

def diagnose_jumps(px):
    """Report every |daily move| >= 0.40 and diagnose it. Nothing is auto-deleted."""
    out = []
    for t, s in px.items():
        r = s.pct_change()
        for d, v in r[r.abs() >= V3.DISCONTINUITY_ABS].items():
            nxt = r.shift(-1).get(d)
            out.append({
                "ticker": t, "date": str(pd.Timestamp(d).date()),
                "daily_return": round(float(v), 4),
                "next_day_return": (None if nxt is None or pd.isna(nxt)
                                    else round(float(nxt), 4)),
                "diagnosis": ("probable adjustment failure: a near-exact reversal the "
                              "following session" if nxt is not None and not pd.isna(nxt)
                              and abs(v + nxt) < 0.15 * abs(v)
                              else "genuine move: no offsetting reversal"),
                "action": "reported, not deleted",
            })
    return out


# ------------------------------------------------------------------------ main

def main(argv=None):
    OUT.mkdir(parents=True, exist_ok=True)
    sec, identity = sec_identity_and_events()
    recs, av_meta = av_records()
    unresolved = [t for t, v in identity.items() if not v["resolved"]]
    matched, excl = crosswalk_exact(recs, sec)

    timing = {}
    rows = []
    for m in matched:
        sess, cat = V3.assign_session(m["acceptance_utc"])
        timing[cat] = timing.get(cat, 0) + 1
        if sess is None:
            continue
        rows.append(dict(m, session=str(sess), timing_category=cat))

    fetch_meta = V3.fetch_prices(UNIVERSE + [BENCH], start=PRICE_START, end=PRICE_END)
    px, price_audit = V3.load_prices(UNIVERSE + [BENCH])
    bench = px.get(BENCH)
    jumps = diagnose_jumps(px)

    kept, dropped = [], {"missing_prices": 0}
    for r in rows:
        if bench is None:
            break
        ar0 = V3.abnormal(px, bench, r["ticker"], r["session"], -1)
        ar5 = V3.abnormal(px, bench, r["ticker"], r["session"], V3.H_PRIMARY)
        ar20 = V3.abnormal(px, bench, r["ticker"], r["session"], V3.H_SECONDARY)
        if ar0 is None:
            dropped["missing_prices"] += 1
            continue
        kept.append(dict(r, ar0=ar0, ar5=ar5, ar20=ar20,
                         year=int(str(r["session"])[:4])))
    d = pd.DataFrame(kept)

    res = {
        "artifact": "SEMICONDUCTOR_SURPRISE_TEMPORAL_REPLICATION_RESULTS", "version": "1.0",
        "status": "EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY",
        "test_nature": ("RETROSPECTIVE TEMPORAL REPLICATION motivated by PR #34's "
                        "suggestive but gate-failing result. NOT a prospectively "
                        "registered independent replication."),
        "terminal_replication": True,
        "third_replication_proposed": False,
        "is_gst_test": False,
        "surprise_construct": "VENDOR_DEFINED_REPORTED_EPS_SURPRISE",
        "primary_surprise_field": "surprisePercentage",
        "point_in_time_provenance": "POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED",
        "not_claimed": ["GAAP surprise", "SEC-validated surprise",
                        "guaranteed contemporaneous consensus", "preregistered evidence",
                        "investable signal"],
        "universe": UNIVERSE, "benchmark": BENCH,
        "train_start": TRAIN_START, "oos_window": [OOS_START, OOS_END],
        "folds": [[list(a), b] for a, b in REPL_FOLDS],
        "reused_from_pr34": {
            "module": "tools/run_semiconductor_surprise_absorption_v3.py",
            "source_edited": False,
            "rebound_globals": ["FOLDS", "PRICE_CACHE"],
            "alpha_grid": V3.ALPHAS,
            "bootstrap": {"draws": V3.BOOT_DRAWS, "block_days": V3.BOOT_BLOCK_DAYS,
                          "seed": V3.BOOT_SEED},
            "horizons": [V3.H_PRIMARY, V3.H_SECONDARY],
            "cost_bps_round_trip": V3.COST_BPS_ROUND_TRIP,
        },
        "sec_identity": identity,
        "unresolved_historical_identity": unresolved,
        "item_202_effective_date": ITEM_202_EFFECTIVE,
        "item_202_note": ("SEC Item 2.02 came into force with the 8-K restructuring "
                          "effective 2004-08-23. Earlier earnings releases carry a "
                          "different item number and cannot match under the unchanged "
                          "crosswalk. Those events fall entirely inside the training "
                          "window and are excluded by the existing rule, not a new one."),
        "provider_records": av_meta,
        "provider_records_2004_2017": len(recs),
        "sec_item_202_events_2004_2017": int(len(sec)),
        "crosswalk_excluded": excl,
        "uniquely_matched": len(matched),
        "timing_categories": timing,
        "price_fetch": fetch_meta, "price_audit": price_audit,
        "price_discontinuities": jumps,
        "dropped": dropped,
    }

    if d.empty:
        res["decision_label"] = LABELS[0]
        res["sample_gate"] = {"passed": False, "reason": "no priced replication events"}
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                           encoding="utf-8", newline="\n")
        print(LABELS[0])
        return 2

    d = d.sort_values(["session", "ticker"]).reset_index(drop=True)
    d.to_csv(PANEL_OUT, index=False, lineterminator="\n")
    oos = d[(d.year >= 2010) & (d.year <= 2017)]
    per_year = {y: int((oos.year == y).sum()) for y in REPL_YEARS}
    dup = int(d.duplicated(subset=["ticker", "reportedDate", "accession"]).sum())
    overlap = 0
    for (y0, y1), ty in REPL_FOLDS:
        tr = set(map(tuple, d[(d.year >= y0) & (d.year <= y1)][["ticker",
                                                               "reportedDate"]].values))
        te = set(map(tuple, d[d.year == ty][["ticker", "reportedDate"]].values))
        overlap += len(tr & te)
    gate = {
        "tickers": {"value": int(d.ticker.nunique()), "required": SAMPLE_GATE["tickers"],
                    "passed": d.ticker.nunique() >= SAMPLE_GATE["tickers"]},
        "events_2004_2017": {"value": int(len(d)), "required": SAMPLE_GATE["events"],
                             "passed": len(d) >= SAMPLE_GATE["events"]},
        "oos_events": {"value": int(len(oos)), "required": SAMPLE_GATE["oos_events"],
                       "passed": len(oos) >= SAMPLE_GATE["oos_events"]},
        "oos_per_year": {"value": per_year, "required": SAMPLE_GATE["oos_per_year"],
                         "passed": all(v >= SAMPLE_GATE["oos_per_year"]
                                       for v in per_year.values())},
        "duplicate_identities": {"value": dup, "required": 0, "passed": dup == 0},
        "train_test_identity_overlap": {"value": overlap, "required": 0,
                                        "passed": overlap == 0},
    }
    gate["passed"] = all(v["passed"] for k, v in gate.items() if k != "passed")
    res["sample_gate"] = gate
    res["events_by_ticker"] = {t: int((d.ticker == t).sum()) for t in UNIVERSE}
    res["events_by_year"] = {int(y): int((d.year == y).sum())
                             for y in sorted(d.year.unique())}

    if not gate["passed"]:
        res["decision_label"] = LABELS[0]
        res["stage1"] = "not run -- sample gate failed"
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                           encoding="utf-8", newline="\n")
        print(LABELS[0], json.dumps({k: v for k, v in gate.items()}, default=str)[:400])
        return 2

    # ------------------------- Stage 1 replication -------------------------
    from scipy import stats
    s1 = V3.run_stage(d, "ar0", (), ("z",), "B", "C",
                      transform_col="surprisePercentage")
    s1sum = V3.stage_summary(s1, "ar0", "B", "C")
    sp = stats.spearmanr(s1.z.values, s1.ar0.values)
    n_years = len(s1sum["per_year"])
    need = two_thirds(n_years)
    s1sum["oos_spearman_surprise_vs_initial_reaction"] = round(float(sp.statistic), 5)
    s1sum["oos_spearman_p"] = round(float(sp.pvalue), 6)
    s1sum["mean_coef_on_transformed_surprise"] = round(float(np.nanmean(s1.coef_add)), 6)
    s1sum["evaluable_years"] = n_years
    s1sum["years_required_two_thirds"] = need
    g1 = {
        "mae_improvement_at_least_1pct":
            s1sum["mae_improvement_pct"] >= V3.MAE_IMPROVEMENT_MIN,
        "bootstrap_ci_entirely_above_zero":
            s1sum["bootstrap_mae_diff"]["entirely_above_zero"],
        "c_beats_b_in_two_thirds_of_years": s1sum["years_augmented_better"] >= need,
        "expected_positive_sign":
            s1sum["oos_spearman_surprise_vs_initial_reaction"] > 0,
    }
    g1["passed"] = all(g1.values())
    res["stage1_replication"] = {
        "model_b": "intercept + ticker indicators",
        "model_c": "model B + transformed vendor-defined surprise",
        **s1sum, "gates": g1}
    res["secondary_reporting"] = secondary(s1)
    res["pr34_comparison"] = pr34_comparison(s1sum, g1)

    if not g1["passed"]:
        res["decision_label"] = LABELS[1]
        res["stage2"] = "not run -- the temporal replication failed"
        res["trading"] = "not run -- the temporal replication failed"
        res["path_status"] = ("STOPPED. No information-price gap, no Stage 2, no "
                              "trading, no new specification, and NO THIRD REPLICATION "
                              "IS PROPOSED.")
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                           encoding="utf-8", newline="\n")
        print(LABELS[1])
        return 1

    # ------------------------------ Stage 2 ------------------------------
    s1 = s1.assign(gap=s1.pred_b - s1.ar0)
    res["information_price_gap"] = {
        "definition": "fold-specific OOS predicted AR0 - observed AR0",
        "in_sample_predictions_used": False, "n": int(len(s1))}
    s2src = s1.dropna(subset=["ar5"])
    s2 = V3.run_stage(s2src, "ar5", ("ar0",), ("gap",), "D", "E")
    s2sum = V3.stage_summary(s2, "ar5", "D", "E")
    ic = stats.spearmanr(s2.gap.values, s2.ar5.values)
    ny2 = len(s2sum["per_year"])
    need2 = two_thirds(ny2)
    s2sum["pooled_spearman_ic_gap_vs_ar5"] = round(float(ic.statistic), 5)
    s2sum["mean_gap_coefficient"] = round(float(np.nanmean(s2.coef_add)), 6)
    s2sum["cr2_inference_gap_on_ar5"] = V3.cr2_inference(s2, "ar5", "gap")
    s2sum["evaluable_years"] = ny2
    s2sum["years_required_two_thirds"] = need2
    s2sum["by_ticker"] = {t: {"n": int(len(g)),
                              "spearman_ic": (round(float(stats.spearmanr(
                                  g.gap.values, g.ar5.values).statistic), 5)
                                  if len(g) >= 8 else None)}
                          for t, g in s2.groupby("ticker")}
    g2 = {
        "mae_improvement_at_least_1pct":
            s2sum["mae_improvement_pct"] >= V3.MAE_IMPROVEMENT_MIN,
        "bootstrap_ci_entirely_above_zero":
            s2sum["bootstrap_mae_diff"]["entirely_above_zero"],
        "pooled_spearman_ic_positive": s2sum["pooled_spearman_ic_gap_vs_ar5"] > 0,
        "e_beats_d_in_two_thirds_of_years": s2sum["years_augmented_better"] >= need2,
        "gap_coefficient_positive": s2sum["mean_gap_coefficient"] > 0,
    }
    g2["passed"] = all(g2.values())
    res["stage2"] = {"model_d": "intercept + ticker indicators + observed AR0",
                     "model_e": "model D + information-price gap", **s2sum, "gates": g2}

    if not g2["passed"]:
        res["decision_label"] = LABELS[2]
        res["trading"] = "not run -- Stage 2 failed"
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                           encoding="utf-8", newline="\n")
        print(LABELS[2])
        return 1

    tr = V3.trading(s2)
    res["trading"] = tr
    res["decision_label"] = LABELS[4] if tr["net_mean_positive"] else LABELS[3]
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                       encoding="utf-8", newline="\n")
    print(res["decision_label"])
    return 0


def secondary(s1):
    """Descriptive only. Cannot replace the primary gate."""
    from scipy import stats

    def cell(g):
        y = g.ar0.values.astype(float)
        ma, mb = V3.mae(y, g.pred_a), V3.mae(y, g.pred_b)
        return {"n": int(len(g)), "mae_B": round(ma, 6), "mae_C": round(mb, 6),
                "improvement_pct": (round(100.0 * (ma - mb) / ma, 4) if ma > 0 else None),
                "c_better": bool(mb < ma),
                "spearman": (round(float(stats.spearmanr(g.z.values, y).statistic), 5)
                             if len(g) >= 8 and g.z.nunique() > 1 else None),
                "mean_ar0_pct": round(100.0 * float(y.mean()), 4)}

    fy = s1.copy()
    fy["m"] = pd.to_datetime(fy.fiscalDateEnding).dt.month
    mode = fy.groupby("ticker").m.agg(lambda x: x.value_counts().idxmax())
    fy["is_fye"] = [mm == mode.get(t) for t, mm in zip(fy.ticker, fy.m)]
    return {
        "note": "Descriptive. Defines no gate and replaces no primary result.",
        "by_ticker": {t: cell(g) for t, g in s1.groupby("ticker")},
        "by_year": {int(y): cell(g) for y, g in s1.groupby("year")},
        "excluding_fiscal_year_end_quarters": cell(fy[~fy.is_fye]),
        "fiscal_year_end_quarters_excluded": int(fy.is_fye.sum()),
        "sec_validated_overlap_only": {
            "status": "NOT_APPLICABLE",
            "reason": ("the SEC-validated parser values exist only for the 2018-2025 "
                       "extraction sample; none overlaps the 2010-2017 replication "
                       "window")},
        "twenty_session_return": {
            "status": "NOT_REPORTED",
            "reason": "Stage 2 is not permitted unless the replication gate passes"},
    }


def pr34_comparison(s1sum, g1):
    """Secondary comparison ONLY. Never pooled, never used to change the decision."""
    return {
        "note": ("Secondary comparison, produced AFTER the replication result was "
                 "finalized. The two samples are NEVER pooled and this comparison "
                 "cannot rescue or alter the replication gate."),
        "pr34_window": "2023-2025", "pr34_n_oos": 116,
        "pr34_mae_improvement_pct": 2.482,
        "pr34_spearman": 0.13515,
        "pr34_bootstrap_ci": [-0.0007271998959694952, 0.0031700017619433383],
        "pr34_stage1_passed": False,
        "replication_window": "2010-2017",
        "replication_n_oos": s1sum["n_oos"],
        "replication_mae_improvement_pct": s1sum["mae_improvement_pct"],
        "replication_spearman": s1sum["oos_spearman_surprise_vs_initial_reaction"],
        "replication_bootstrap_ci": s1sum["bootstrap_mae_diff"]["ci95"],
        "replication_stage1_passed": g1["passed"],
        "point_estimates_agree_in_sign": bool(
            (s1sum["mae_improvement_pct"] > 0) == (2.482 > 0)),
        "spearman_agrees_in_sign": bool(
            (s1sum["oos_spearman_surprise_vs_initial_reaction"] > 0) == (0.13515 > 0)),
        "pooled_to_change_decision": False,
    }


if __name__ == "__main__":
    sys.exit(main())
