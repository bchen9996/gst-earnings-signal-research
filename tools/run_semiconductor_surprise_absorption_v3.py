#!/usr/bin/env python3
"""Semiconductor information-price gap study (v3).

Question: among semiconductor earnings announcements, does the discrepancy between a
VENDOR-DEFINED earnings surprise and the market's initial abnormal reaction predict
subsequent abnormal return?

=============================== FROZEN_DESIGN ===============================
Committed BEFORE any price or return file was opened. Every rule below is fixed.

PROVENANCE AND HONESTY STATEMENTS (recorded, not softened)
  * The structured-source feasibility crosswalk gate FAILED at 0.6719 against a
    required 0.90 and REMAINS FAILED. Nothing here re-scores, relaxes or retries it.
    That gate required a fiscal-period match, and fiscal_period_end exists for only
    267 of the 306 SEC Item 2.02 events, capping it at 0.8344.
  * This is a SUCCESSOR design. It was created AFTER inspecting identity and coverage
    information, and BEFORE inspecting any outcome. No return, price or reaction had
    been opened when this block was committed.
  * The exact-date crosswalk rule below was motivated by the ALREADY-RECORDED
    identity-only diagnostic (report-date-only matching reached 300/320 with zero
    ambiguity). That diagnostic used no outcome of any kind.
  * The outcome synthesis is EXPLORATORY RETROSPECTIVE DEVELOPMENT. It is NOT
    preregistered confirmation, not production-ready, and not investable.
  * This is NOT a Google Trends / GST test. No GST series is read.

SURPRISE PROVENANCE -- mandatory language
  The Alpha Vantage series is VENDOR_DEFINED_REPORTED_EPS_SURPRISE. It is NOT a GAAP
  earnings surprise, NOT an SEC-validated EPS surprise, NOT a guaranteed
  contemporaneous-consensus vintage, NOT preregistered evidence, and NOT
  production-ready or investable.
  POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED is recorded.
  PRIMARY SURPRISE FIELD = surprisePercentage, chosen because a proportional split
  restatement scales reportedEPS, estimatedEPS and surprise together and therefore
  leaves the percentage invariant. That invariance is verified MECHANICALLY wherever
  the required fields exist. Raw reportedEPS and estimatedEPS are NEVER primary model
  features.

UNIVERSE   NVDA, AMD, INTC, QCOM, AVGO, MU, TXN, AMAT, LRCX, KLAC
PERIOD     Alpha Vantage earnings records with reportedDate in 2018-01-01..2025-12-31

CROSSWALK  exact ticker AND exact reported-calendar-date equality to the SEC Item 2.02
  event index (event_panel_v1.0.csv). A provider record is admitted only if EXACTLY ONE
  SEC event has the same ticker and filing_date == reportedDate. Zero matches or more
  than one match -> EXCLUDED WITHOUT SUBSTITUTION. No window, no nearest-date fallback.

SAMPLE GATE (checked before any model is fitted)
  >= 8 tickers; >= 240 uniquely matched events; >= 90 OOS events across 2023-2025;
  >= 25 OOS events in EACH of 2023, 2024, 2025; zero duplicated event identities.
  Failure -> DATA_INSUFFICIENT and NO model is fitted.

EVENT TIMING  SEC acceptance timestamp converted to America/New_York.
  acceptance < 09:30 ET on a trading day        -> T = that trading day
  acceptance >= 16:00 ET                        -> T = next trading session
  acceptance on a weekend or market holiday     -> T = next trading session
  acceptance 09:30 ET <= t < 16:00 ET           -> EXCLUDED, because a daily bar cannot
                                                   isolate the post-release response
  Counts for every timing category are recorded.
  Session calendar: XNYS via exchange_calendars (the repository's validated module).

RETURNS  Split-adjusted daily closes. Provider chain, in this fixed order:
  (1) yfinance with auto_adjust=True (split AND dividend adjusted);
  (2) if unavailable, Alpaca daily bars with adjustment=all.
  Adjusted closes are used directly; raw discontinuous closes are NEVER used. A
  discontinuity audit records every |daily return| >= 0.40 remaining after adjustment.
  BENCHMARK = SMH.

  initial abnormal reaction (AR0):
      [close(T)/close(T-1) - 1] - [SMH(T)/SMH(T-1) - 1]
  primary subsequent abnormal return (AR5):
      [close(T+5)/close(T) - 1] - [SMH(T+5)/SMH(T) - 1]
  T-1 is the prior trading session; T+5 is the 5th trading session after T.
  The proposed trade, if ever authorized, enters at close(T). Every signal input is
  therefore observable by close(T).
  PRIMARY HORIZON = 5 sessions. A 20-session return is reported as CLEARLY SECONDARY
  and may never replace the 5-session result.

SURPRISE TRANSFORM  computed INSIDE EACH TRAINING FOLD ONLY, then applied frozen:
  1. signed_log_surprise = sign(x) * log1p(abs(x)),  x = surprisePercentage
  2. winsorize at the TRAINING fold's 1st and 99th percentiles
  3. standardize by the TRAINING fold's mean and standard deviation
  4. apply those frozen training values to the test fold
  NO full-sample standardization anywhere.

FOLDS  expanding chronological windows, no identity crossing train and test:
  train 2018-2022 -> test 2023
  train 2018-2023 -> test 2024
  train 2018-2024 -> test 2025

RIDGE  fixed closed-form linear ridge, intercept never penalized:
  beta = (X'X + alpha*D)^-1 X'y,  D = diag(0, 1, 1, ...)
  alpha selected ONLY within the training fold from EXACTLY [0.0, 0.1, 1.0, 10.0].
  Selection: lowest MAE on an INNER CHRONOLOGICAL validation split, defined as the
  FINAL calendar year of the training window, with all earlier years as inner-training.
  Tie-break toward the LARGER alpha. The grid is never expanded.
  After selection the model is refit on the FULL training fold.
  Ticker indicators are fitted from TRAINING data only; a ticker unseen in training
  maps to the all-zero baseline.

STAGE 1 -- does surprise explain the initial reaction? (mandatory gate)
  Model B: intercept + ticker indicators
  Model C: Model B + transformed vendor-defined surprise
  Primary metric: MAE of initial abnormal reaction (AR0), pooled over OOS folds.
  improvement = 100 * (MAE_B - MAE_C) / MAE_B
  PASSES only if ALL hold:
    1. pooled MAE improvement >= 1.0%
    2. the 95% bootstrap interval for (MAE_B - MAE_C) lies ENTIRELY above zero
    3. Model C beats Model B in >= 2 of the 3 OOS years
    4. the OOS signed-surprise / initial-reaction relationship has the economically
       expected POSITIVE sign (pooled OOS Spearman > 0)
  FAILURE -> report all fixed Stage-1 results, assign
  SURPRISE_DOES_NOT_EXPLAIN_INITIAL_REACTION, do NOT construct the gap, do NOT run
  Stage 2, do NOT simulate trading.

BOOTSTRAP  2000 deterministic moving-block draws, non-overlapping 4-week (28-day)
  calendar blocks over the pooled OOS window. A sampled block contributes ALL of its
  tickers and events together. Blocks are drawn with replacement, as many blocks as
  exist, so expected resample size equals the sample size. SEED = 20260817.
  Interval = the 2.5th and 97.5th percentiles of the draw distribution.

PHASE 3 -- the information-price gap (only if Stage 1 passes)
  For every OOS observation, Model C's predicted AR0 is produced using ONLY that fold's
  training data. NEVER an in-sample fitted value.
      information_price_gap = predicted_AR0 - observed_AR0
  positive gap: price reacted less positively (or more negatively) than the surprise
  model expected. negative gap: price reacted more positively than expected.

STAGE 2 -- does the gap predict drift?
  Model D: intercept + ticker indicators + observed AR0
  Model E: Model D + information_price_gap
  Same ridge grid, same inner selection and tie-break.
  Primary metric: MAE of the 5-session subsequent abnormal return (AR5).
  Also reported: RMSE, OOS R2, Spearman IC between gap and AR5, the gap coefficient,
  CR2/BRL standard error clustered by ticker, Satterthwaite degrees of freedom,
  t-statistic, p-value, 95% interval, and results separately for 2023, 2024 and 2025.
  The CR2/Satterthwaite implementation is IMPORTED from
  tools/hyp01_inference_feasibility.py and is NOT reimplemented here.
  PASSES only if ALL hold:
    1. pooled MAE improvement >= 1.0%
    2. the block-bootstrap interval for (MAE_D - MAE_E) lies entirely above zero
    3. pooled Spearman IC is positive
    4. Model E beats Model D in >= 2 of 3 years
    5. the gap coefficient is positive
  FAILURE -> NO_EVIDENCE_OF_INFORMATION_PRICE_UNDERREACTION. No trading strategy is
  manufactured from a failed predictive gate.

PHASE 5 -- trading evaluation ONLY if Stage 1 AND Stage 2 both pass
  Rank OOS events by the information-price gap; long the top quintile; short the bottom
  quintile; enter at close(T); exit at close(T+5); subtract 10 bps round trip per stock
  trade. Report gross and net mean, CR2 inference, hit rate, annual results, turnover,
  trade count and maximum drawdown, and compare with an equal-count strategy ranked on
  surprise alone. NO search over alternative quantiles, horizons, costs, features or
  models.

SENSITIVITIES (reported, never allowed to replace the primary result)
  S1 exclude fiscal-year-end quarters
  S2 restrict to records overlapping an SEC-validated parser value
  S3 strict SEC-derived seasonal EPS shock where available (smaller-sample, so labeled)
  S4 20-session subsequent abnormal return
  S5 raw results by ticker and by year
  A sensitivity with too few observations is REPORTED AS SUCH, never gate-lowered.

LABELS  exactly one of
  DATA_INSUFFICIENT |
  SURPRISE_DOES_NOT_EXPLAIN_INITIAL_REACTION |
  NO_EVIDENCE_OF_INFORMATION_PRICE_UNDERREACTION |
  PREDICTIVE_BUT_NOT_TRADABLE_AFTER_COSTS |
  EXPLORATORY_INFORMATION_PRICE_GAP_SIGNAL
  EXPLORATORY is mandatory in the success label because estimate-vintage provenance is
  not guaranteed.
============================= END FROZEN_DESIGN =============================
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

SRC = ROOT / "Live Signal Engine" / "Semiconductor_EPS_Absorption"
OUT = ROOT / "Live Signal Engine" / "Semiconductor_Surprise_Absorption_v3"
FEAS = SRC / "structured_earnings_feasibility_v1.0.json"
SEC_PANEL = SRC / "event_panel_v1.0.csv"
RESULTS = ROOT / "SEMICONDUCTOR_SURPRISE_ABSORPTION_V3_RESULTS_v1.0.json"
PANEL_OUT = OUT / "event_panel_v1.0.csv"
PRICE_CACHE = Path(os.environ.get("GST_PRICE_CACHE_DIR")
                   or (ROOT.parent / "gst-price-cache-v3"))

UNIVERSE = ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "MU", "TXN", "AMAT", "LRCX", "KLAC"]
BENCH = "SMH"
PERIOD_START, PERIOD_END = "2018-01-01", "2025-12-31"
ET = ZoneInfo("America/New_York")
ALPHAS = [0.0, 0.1, 1.0, 10.0]
FOLDS = [((2018, 2022), 2023), ((2018, 2023), 2024), ((2018, 2024), 2025)]
H_PRIMARY, H_SECONDARY = 5, 20
BOOT_DRAWS, BOOT_BLOCK_DAYS, BOOT_SEED = 2000, 28, 20260817
COST_BPS_ROUND_TRIP = 10.0
QUANTILE = 5
DISCONTINUITY_ABS = 0.40
MAE_IMPROVEMENT_MIN = 1.0
SAMPLE_GATE = {"tickers": 8, "events": 240, "oos_events": 90, "oos_per_year": 25}
GATE_YEARS = (2023, 2024, 2025)
CONSTRUCT = "VENDOR_DEFINED_REPORTED_EPS_SURPRISE"
PIT = "POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED"
LABELS = ("DATA_INSUFFICIENT",
          "SURPRISE_DOES_NOT_EXPLAIN_INITIAL_REACTION",
          "NO_EVIDENCE_OF_INFORMATION_PRICE_UNDERREACTION",
          "PREDICTIVE_BUT_NOT_TRADABLE_AFTER_COSTS",
          "EXPLORATORY_INFORMATION_PRICE_GAP_SIGNAL")


# ------------------------------------------------------------------ ridge core

def ridge_fit(X, y, alpha):
    """Closed-form ridge. Column 0 is the intercept and is never penalized."""
    k = X.shape[1]
    D = np.eye(k)
    D[0, 0] = 0.0
    return np.linalg.pinv(X.T @ X + alpha * D) @ (X.T @ y)


def mae(a, b):
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def select_alpha(tr, build, ycol):
    """Inner chronological selection: final training year validates, earlier years fit.
    Lowest inner MAE wins; ties break toward the LARGER alpha."""
    yrs = sorted(tr.year.unique())
    if len(yrs) < 2:
        return ALPHAS[-1]
    inner_tr, inner_va = tr[tr.year < yrs[-1]], tr[tr.year == yrs[-1]]
    if inner_tr.empty or inner_va.empty:
        return ALPHAS[-1]
    cols, Xtr = build(inner_tr, None)
    ytr = inner_tr[ycol].values.astype(float)
    _, Xva = build(inner_va, cols)
    yva = inner_va[ycol].values.astype(float)
    best, best_mae = ALPHAS[0], float("inf")
    for a in ALPHAS:                       # ascending; >= keeps the LARGER alpha on ties
        m = mae(yva, Xva @ ridge_fit(Xtr, ytr, a))
        if m < best_mae or (math.isclose(m, best_mae, rel_tol=1e-12, abs_tol=1e-15)):
            best, best_mae = a, min(m, best_mae)
    return best


def ticker_design(df, cols, extra=()):
    """Intercept + ticker indicators (+ extra numeric columns), training-fitted."""
    if cols is None:
        cols = sorted(df.ticker.unique())[1:]      # first ticker is the baseline
    M = [np.ones(len(df))]
    for t in cols:
        M.append((df.ticker.values == t).astype(float))
    for e in extra:
        M.append(df[e].values.astype(float))
    return cols, np.column_stack(M)


# ------------------------------------------------------------------- bootstrap

def block_bootstrap_diff(dates, err_a, err_b, draws=BOOT_DRAWS, seed=BOOT_SEED,
                         block_days=BOOT_BLOCK_DAYS):
    """95% interval for (MAE_a - MAE_b) over non-overlapping calendar blocks."""
    d = pd.to_datetime(pd.Series(dates)).values.astype("datetime64[D]")
    origin = d.min()
    bid = ((d - origin).astype(int) // block_days)
    groups = {}
    for i, b in enumerate(bid):
        groups.setdefault(int(b), []).append(i)
    keys = sorted(groups)
    rng = np.random.default_rng(seed)
    ea, eb = np.abs(np.asarray(err_a)), np.abs(np.asarray(err_b))
    out = np.empty(draws)
    for k in range(draws):
        pick = rng.integers(0, len(keys), len(keys))
        idx = np.concatenate([groups[keys[p]] for p in pick])
        out[k] = ea[idx].mean() - eb[idx].mean()
    return {"draws": draws, "block_days": block_days, "seed": seed, "blocks": len(keys),
            "mean": float(out.mean()),
            "ci95": [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))],
            "entirely_above_zero": bool(np.percentile(out, 2.5) > 0)}


# ------------------------------------------------------------- data assembly

def load_av_records():
    a = json.loads(FEAS.read_text(encoding="utf-8"))
    return a["sanitized_panel"], a


def verify_surprise_percentage_invariance(records, tol=0.5):
    """Mechanical check that surprisePercentage is a ratio, hence split-invariant.

    (a) surprisePercentage ~= 100 * surprise / |estimatedEPS| where computable;
    (b) scaling reportedEPS, estimatedEPS and surprise by a common split factor leaves
        the recomputed percentage numerically unchanged.
    """
    checked = agree = 0
    worst = 0.0
    invariant = True
    for r in records:
        e, s, p = r.get("estimatedEPS"), r.get("surprise"), r.get("surprisePercentage")
        if e in (None, 0) or s is None or p is None or abs(e) < 1e-9:
            continue
        checked += 1
        recomputed = 100.0 * s / abs(e)
        worst = max(worst, abs(recomputed - p))
        if abs(recomputed - p) <= tol:
            agree += 1
        for f in (0.1, 0.25, 4.0):                     # proportional split restatements
            if abs((100.0 * (s * f) / abs(e * f)) - recomputed) > 1e-9:
                invariant = False
    return {"checked": checked, "agree_within_0_5pp": agree,
            "agreement_rate": (None if not checked else round(agree / checked, 4)),
            "largest_absolute_deviation_pp": round(worst, 4),
            "proportional_split_invariance_holds": invariant,
            "note": ("surprisePercentage is a ratio of two EPS quantities, so a "
                     "proportional split restatement cancels exactly. Verified "
                     "mechanically, not assumed.")}


def load_sec_events():
    df = pd.read_csv(SEC_PANEL, usecols=["ticker", "accession", "filing_date",
                                         "acceptance_utc", "fiscal_period_end", "eps",
                                         "audit_status"])
    return df[df.filing_date.notna() & df.acceptance_utc.notna()].copy()


def crosswalk_exact(records, sec):
    """Exact ticker + exact reported-calendar-date. Anything else is excluded."""
    key = {}
    for r in sec.itertuples(index=False):
        key.setdefault((r.ticker, str(r.filing_date)[:10]), []).append(r)
    rows, excl = [], {"no_match": 0, "ambiguous": 0, "outside_period": 0}
    for r in records:
        if not (PERIOD_START <= r["reportedDate"] <= PERIOD_END):
            excl["outside_period"] += 1
            continue
        c = key.get((r["ticker"], r["reportedDate"]), [])
        if len(c) == 0:
            excl["no_match"] += 1
            continue
        if len(c) > 1:
            excl["ambiguous"] += 1
            continue
        e = c[0]
        rows.append({"ticker": r["ticker"], "reportedDate": r["reportedDate"],
                     "fiscalDateEnding": r["fiscalDateEnding"],
                     "surprisePercentage": r["surprisePercentage"],
                     "reportedEPS": r["reportedEPS"], "estimatedEPS": r["estimatedEPS"],
                     "accession": e.accession, "acceptance_utc": e.acceptance_utc,
                     "sec_fiscal_period_end": e.fiscal_period_end,
                     "sec_eps": (None if pd.isna(e.eps) else float(e.eps)),
                     "sec_audit_status": (None if pd.isna(e.audit_status)
                                          else str(e.audit_status))})
    return rows, excl


# ---------------------------------------------------------------- event timing

def assign_session(acceptance_utc):
    """Frozen timing rule. Returns (session_date or None, category)."""
    from gst_market_response.exchange_calendar import is_trading_day, next_session
    ts = pd.Timestamp(acceptance_utc)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    et = ts.tz_convert(ET)
    d, t = et.date(), et.time()
    if not is_trading_day(d):
        return next_session(d), "non_session_day_next_session"
    if t < datetime.strptime("09:30", "%H:%M").time():
        return d, "before_open_same_session"
    if t >= datetime.strptime("16:00", "%H:%M").time():
        return next_session(d), "after_close_next_session"
    return None, "intraday_excluded"


# --------------------------------------------------------------------- prices

def fetch_prices(tickers, start="2017-10-01", end="2026-03-01"):
    """Split-adjusted daily closes, cached repository-external. Network step -- runs
    BEFORE the CR2 module (which disables sockets on import) is ever imported."""
    PRICE_CACHE.mkdir(parents=True, exist_ok=True)
    meta = []
    for t in tickers:
        f = PRICE_CACHE / f"{t}.csv"
        if f.exists():
            meta.append({"ticker": t, "source": "cache", "rows": sum(1 for _ in f.open()) - 1})
            continue
        import yfinance as yf
        df = yf.download(t, start=start, end=end, auto_adjust=True, progress=False,
                         actions=False)
        if df is None or df.empty:
            meta.append({"ticker": t, "source": "yfinance", "rows": 0, "error": "empty"})
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        out = df[["Close"]].rename(columns={"Close": "close"})
        out.index.name = "date"
        out.to_csv(f)
        meta.append({"ticker": t, "source": "yfinance_auto_adjust", "rows": int(len(out))})
    return meta


def load_prices(tickers):
    px, audit = {}, []
    for t in tickers:
        f = PRICE_CACHE / f"{t}.csv"
        if not f.exists():
            continue
        s = pd.read_csv(f, parse_dates=["date"]).set_index("date")["close"].astype(float)
        s = s[~s.index.duplicated(keep="first")].sort_index()
        r = s.pct_change()
        jumps = int((r.abs() >= DISCONTINUITY_ABS).sum())
        audit.append({"ticker": t, "rows": int(len(s)),
                      "first": str(s.index.min().date()), "last": str(s.index.max().date()),
                      "abs_daily_return_ge_0_40": jumps})
        px[t] = s
    return px, audit


def abnormal(px, bench, t, sess, h):
    """Abnormal return over h sessions from sess (h<0 means the prior session)."""
    s, b = px.get(t), bench
    if s is None:
        return None
    si, bi = s.index, b.index
    ts = pd.Timestamp(sess)
    if ts not in si or ts not in bi:
        return None
    i, j = si.get_loc(ts), bi.get_loc(ts)
    k, m = i + h, j + h
    if k < 0 or m < 0 or k >= len(si) or m >= len(bi):
        return None
    if h < 0:
        sr = s.iloc[i] / s.iloc[k] - 1.0
        br = b.iloc[j] / b.iloc[m] - 1.0
    else:
        sr = s.iloc[k] / s.iloc[i] - 1.0
        br = b.iloc[m] / b.iloc[j] - 1.0
    return float(sr - br)


# ------------------------------------------------------------------ transforms

def fit_surprise_transform(train_x):
    v = np.sign(train_x) * np.log1p(np.abs(train_x))
    lo, hi = np.percentile(v, 1), np.percentile(v, 99)
    w = np.clip(v, lo, hi)
    mu, sd = float(w.mean()), float(w.std(ddof=0))
    return {"lo": float(lo), "hi": float(hi), "mu": mu, "sd": (sd if sd > 1e-12 else 1.0)}


def apply_surprise_transform(x, p):
    v = np.sign(x) * np.log1p(np.abs(x))
    return (np.clip(v, p["lo"], p["hi"]) - p["mu"]) / p["sd"]


# ----------------------------------------------------------------- stage runner

def run_stage(d, ycol, base_extra, add_extra, label_a, label_b, transform_col=None):
    """Fit baseline and augmented models fold by fold. Returns pooled OOS frame."""
    recs = []
    for (y0, y1), test_year in FOLDS:
        tr = d[(d.year >= y0) & (d.year <= y1)].copy()
        te = d[d.year == test_year].copy()
        if tr.empty or te.empty:
            continue
        if transform_col:
            p = fit_surprise_transform(tr[transform_col].values.astype(float))
            tr["z"] = apply_surprise_transform(tr[transform_col].values.astype(float), p)
            te["z"] = apply_surprise_transform(te[transform_col].values.astype(float), p)

        def build_a(df, cols):
            return ticker_design(df, cols, base_extra)

        def build_b(df, cols):
            return ticker_design(df, cols, base_extra + add_extra)

        aa = select_alpha(tr, build_a, ycol)
        ab = select_alpha(tr, build_b, ycol)
        ca, Xa = build_a(tr, None)
        cb, Xb = build_b(tr, None)
        yt = tr[ycol].values.astype(float)
        beta_a, beta_b = ridge_fit(Xa, yt, aa), ridge_fit(Xb, yt, ab)
        _, Xa_te = build_a(te, ca)
        _, Xb_te = build_b(te, cb)
        te = te.assign(pred_a=Xa_te @ beta_a, pred_b=Xb_te @ beta_b,
                       alpha_a=aa, alpha_b=ab,
                       coef_add=(beta_b[-1] if add_extra else np.nan))
        recs.append(te)
    if not recs:
        return pd.DataFrame()
    o = pd.concat(recs, ignore_index=True)
    o["err_a"] = o[ycol] - o.pred_a
    o["err_b"] = o[ycol] - o.pred_b
    o.attrs["labels"] = (label_a, label_b)
    return o


def stage_summary(o, ycol, la, lb):
    from scipy import stats
    y = o[ycol].values.astype(float)
    ma, mb = mae(y, o.pred_a), mae(y, o.pred_b)
    imp = 100.0 * (ma - mb) / ma if ma > 0 else 0.0
    per_year = {}
    for yr in sorted(o.year.unique()):
        s = o[o.year == yr]
        pa, pb = mae(s[ycol], s.pred_a), mae(s[ycol], s.pred_b)
        per_year[int(yr)] = {"n": int(len(s)), f"mae_{la}": round(pa, 6),
                             f"mae_{lb}": round(pb, 6),
                             "improvement_pct": round(100.0 * (pa - pb) / pa, 4) if pa > 0 else 0.0,
                             "augmented_better": bool(pb < pa)}
    ss_res = float(np.sum((y - o.pred_b) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "n_oos": int(len(o)),
        f"mae_{la}": round(ma, 6), f"mae_{lb}": round(mb, 6),
        "mae_improvement_pct": round(imp, 4),
        f"rmse_{la}": round(rmse(y, o.pred_a), 6),
        f"rmse_{lb}": round(rmse(y, o.pred_b), 6),
        "oos_r2_augmented": round(1.0 - ss_res / ss_tot, 6) if ss_tot > 0 else None,
        "per_year": per_year,
        "years_augmented_better": int(sum(v["augmented_better"] for v in per_year.values())),
        "alphas_selected": {f"{la}": sorted(set(o.alpha_a.tolist())),
                            f"{lb}": sorted(set(o.alpha_b.tolist()))},
        "bootstrap_mae_diff": block_bootstrap_diff(o.session.values, o.err_a, o.err_b),
    }


def cr2_inference(o, ycol, feature):
    """CR2/BRL clustered by ticker. Implementation imported, not reimplemented."""
    from hyp01_inference_feasibility import cr_vcov, satterthwaite_df
    from scipy import stats
    d = o.dropna(subset=[ycol, feature]).copy()
    if d.ticker.nunique() < 2 or len(d) < 10:
        return {"status": "INSUFFICIENT_VARIATION", "n": int(len(d))}
    cols = sorted(d.ticker.unique())[1:]
    M = [np.ones(len(d)), d[feature].values.astype(float)]
    for t in cols:
        M.append((d.ticker.values == t).astype(float))
    X = np.column_stack(M)
    y = 100.0 * d[ycol].values.astype(float)          # percentage points
    g = d.ticker.values
    beta, V, G = cr_vcov(X, y, g, "CR2")
    c = np.zeros(X.shape[1])
    c[1] = 1.0
    se = float(math.sqrt(max(c @ V @ c, 0.0)))
    dfree = satterthwaite_df(X, g, c)
    b = float(beta[1])
    t = b / se if se > 0 else float("nan")
    return {"n": int(len(d)), "n_clusters": int(G), "vcov": "CR2 (BRL)",
            "implementation": "imported from tools/hyp01_inference_feasibility.py",
            "df_method": "coefficient-specific Satterthwaite", "cluster_unit": "ticker",
            "units": "percentage points of abnormal return per unit feature",
            "coef_pp": round(b, 5), "cr2_se_pp": round(se, 5),
            "satterthwaite_df": round(dfree, 3), "t_stat": round(t, 4),
            "p_value": round(float(2 * stats.t.sf(abs(t), dfree)), 6),
            "ci95_pp": [round(b - stats.t.ppf(.975, dfree) * se, 5),
                        round(b + stats.t.ppf(.975, dfree) * se, 5)]}


# ------------------------------------------------------------------------ main

def build_panel():
    records, feas = load_av_records()
    inv = verify_surprise_percentage_invariance(records)
    sec = load_sec_events()
    matched, excl = crosswalk_exact(records, sec)

    timing = {}
    rows = []
    for m in matched:
        sess, cat = assign_session(m["acceptance_utc"])
        timing[cat] = timing.get(cat, 0) + 1
        if sess is None:
            continue
        m = dict(m, session=str(sess), timing_category=cat)
        rows.append(m)
    return rows, {"crosswalk_excluded": excl, "timing_categories": timing,
                  "surprise_percentage_invariance": inv,
                  "av_records_considered": len(records),
                  "uniquely_matched": len(matched)}


def attach_returns(rows):
    px, audit = load_prices(UNIVERSE + [BENCH])
    bench = px.get(BENCH)
    if bench is None:
        return pd.DataFrame(), audit, {"error": "benchmark unavailable"}
    kept, dropped = [], 0
    for r in rows:
        ar0 = abnormal(px, bench, r["ticker"], r["session"], -1)
        ar5 = abnormal(px, bench, r["ticker"], r["session"], H_PRIMARY)
        ar20 = abnormal(px, bench, r["ticker"], r["session"], H_SECONDARY)
        if ar0 is None or ar5 is None:
            dropped += 1
            continue
        kept.append(dict(r, ar0=ar0, ar5=ar5, ar20=ar20,
                         year=int(str(r["session"])[:4])))
    return pd.DataFrame(kept), audit, {"dropped_for_missing_prices": dropped}


def main(argv=None):
    OUT.mkdir(parents=True, exist_ok=True)
    rows, prov = build_panel()
    # Network step FIRST: the CR2 module disables sockets when imported.
    fetch_meta = fetch_prices(UNIVERSE + [BENCH])
    d, price_audit, rprov = attach_returns(rows)

    res = {
        "artifact": "SEMICONDUCTOR_SURPRISE_ABSORPTION_V3_RESULTS", "version": "1.0",
        "status": "EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY",
        "is_gst_test": False,
        "surprise_construct": CONSTRUCT,
        "point_in_time_provenance": PIT,
        "not_claimed": ["GAAP earnings surprise", "SEC-validated EPS surprise",
                        "guaranteed contemporaneous-consensus vintage",
                        "preregistered evidence", "production-ready", "investable"],
        "predecessor_gate": {
            "structured_source_crosswalk_gate": "FAILED",
            "value": 0.6719, "required": 0.90, "still_failed": True,
            "note": ("The structured-source feasibility crosswalk gate failed and "
                     "remains failed. It was not re-scored, relaxed or retried."),
        },
        "successor_design_disclosure": (
            "Successor design created AFTER inspecting identity and coverage "
            "information and BEFORE inspecting any outcome. The exact-date crosswalk "
            "was motivated by the already-recorded identity-only diagnostic, which "
            "used no outcome. The outcome synthesis is exploratory retrospective "
            "development, not preregistered confirmation."),
        "universe": UNIVERSE, "benchmark": BENCH,
        "period": {"start": PERIOD_START, "end": PERIOD_END},
        "primary_surprise_field": "surprisePercentage",
        "primary_horizon_sessions": H_PRIMARY,
        "secondary_horizon_sessions": H_SECONDARY,
        "provenance": prov, "price_fetch": fetch_meta, "price_audit": price_audit,
        "return_provenance": rprov,
    }

    if d.empty:
        res["decision_label"] = LABELS[0]
        res["sample_gate"] = {"passed": False, "reason": "no priced events"}
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                           encoding="utf-8", newline="\n")
        print(LABELS[0])
        return 2

    d = d.sort_values(["session", "ticker"]).reset_index(drop=True)
    dup = int(d.duplicated(subset=["ticker", "reportedDate", "accession"]).sum())
    oos = d[d.year.isin(GATE_YEARS)]
    per_year = {int(y): int((oos.year == y).sum()) for y in GATE_YEARS}
    gate = {
        "tickers": {"value": int(d.ticker.nunique()), "required": SAMPLE_GATE["tickers"],
                    "passed": d.ticker.nunique() >= SAMPLE_GATE["tickers"]},
        "events": {"value": int(len(d)), "required": SAMPLE_GATE["events"],
                   "passed": len(d) >= SAMPLE_GATE["events"]},
        "oos_events": {"value": int(len(oos)), "required": SAMPLE_GATE["oos_events"],
                       "passed": len(oos) >= SAMPLE_GATE["oos_events"]},
        "oos_per_year": {"value": per_year, "required": SAMPLE_GATE["oos_per_year"],
                         "passed": all(v >= SAMPLE_GATE["oos_per_year"]
                                       for v in per_year.values())},
        "duplicate_identities": {"value": dup, "required": 0, "passed": dup == 0},
    }
    gate["passed"] = all(v["passed"] for k, v in gate.items() if k != "passed")
    res["sample_gate"] = gate
    res["events_by_ticker"] = {t: int((d.ticker == t).sum()) for t in UNIVERSE}
    res["events_by_year"] = {int(y): int((d.year == y).sum()) for y in sorted(d.year.unique())}

    d.to_csv(PANEL_OUT, index=False, lineterminator="\n")

    if not gate["passed"]:
        res["decision_label"] = LABELS[0]
        res["stage1"] = "not run -- sample gate failed"
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                           encoding="utf-8", newline="\n")
        print(LABELS[0], json.dumps(gate, default=str))
        return 2

    # ---------------- Stage 1 ----------------
    from scipy import stats
    s1 = run_stage(d, "ar0", (), ("z",), "B", "C", transform_col="surprisePercentage")
    s1sum = stage_summary(s1, "ar0", "B", "C")
    sp = stats.spearmanr(s1.z.values, s1.ar0.values)
    s1sum["oos_spearman_surprise_vs_initial_reaction"] = round(float(sp.statistic), 5)
    s1sum["oos_spearman_p"] = round(float(sp.pvalue), 6)
    s1sum["mean_coef_on_transformed_surprise"] = round(float(np.nanmean(s1.coef_add)), 6)
    g1 = {
        "mae_improvement_at_least_1pct": s1sum["mae_improvement_pct"] >= MAE_IMPROVEMENT_MIN,
        "bootstrap_ci_entirely_above_zero": s1sum["bootstrap_mae_diff"]["entirely_above_zero"],
        "c_beats_b_in_at_least_2_years": s1sum["years_augmented_better"] >= 2,
        "expected_positive_sign": s1sum["oos_spearman_surprise_vs_initial_reaction"] > 0,
    }
    g1["passed"] = all(g1.values())
    res["stage1"] = {"model_b": "intercept + ticker indicators",
                     "model_c": "model B + transformed vendor-defined surprise",
                     **s1sum, "gates": g1}

    if not g1["passed"]:
        res["decision_label"] = LABELS[1]
        res["stage2"] = "not run -- Stage 1 failed; the gap was not constructed"
        res["trading"] = "not run -- Stage 1 failed"
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                           encoding="utf-8", newline="\n")
        print(LABELS[1])
        return 1

    # ---------------- Phase 3: the gap (OOS only, never in-sample) ----------------
    s1 = s1.assign(gap=s1.pred_b - s1.ar0)
    res["information_price_gap"] = {
        "definition": "predicted_initial_abnormal_reaction - observed_initial_abnormal_reaction",
        "computed_from": "Model C predictions produced with that fold's training data only",
        "in_sample_fitted_values_used": False,
        "n": int(len(s1)), "mean": round(float(s1.gap.mean()), 6),
        "sd": round(float(s1.gap.std(ddof=0)), 6),
        "positive_share": round(float((s1.gap > 0).mean()), 4),
    }

    # ---------------- Stage 2 ----------------
    s2 = run_stage(s1, "ar5", ("ar0",), ("gap",), "D", "E")
    s2sum = stage_summary(s2, "ar5", "D", "E")
    ic = stats.spearmanr(s2.gap.values, s2.ar5.values)
    s2sum["pooled_spearman_ic_gap_vs_ar5"] = round(float(ic.statistic), 5)
    s2sum["pooled_spearman_ic_p"] = round(float(ic.pvalue), 6)
    s2sum["mean_gap_coefficient"] = round(float(np.nanmean(s2.coef_add)), 6)
    s2sum["cr2_inference_gap_on_ar5"] = cr2_inference(s2, "ar5", "gap")
    s2sum["per_year_ic"] = {
        int(y): round(float(stats.spearmanr(s2[s2.year == y].gap.values,
                                            s2[s2.year == y].ar5.values).statistic), 5)
        for y in sorted(s2.year.unique())}
    g2 = {
        "mae_improvement_at_least_1pct": s2sum["mae_improvement_pct"] >= MAE_IMPROVEMENT_MIN,
        "bootstrap_ci_entirely_above_zero": s2sum["bootstrap_mae_diff"]["entirely_above_zero"],
        "pooled_spearman_ic_positive": s2sum["pooled_spearman_ic_gap_vs_ar5"] > 0,
        "e_beats_d_in_at_least_2_years": s2sum["years_augmented_better"] >= 2,
        "gap_coefficient_positive": s2sum["mean_gap_coefficient"] > 0,
    }
    g2["passed"] = all(g2.values())
    res["stage2"] = {"model_d": "intercept + ticker indicators + observed initial reaction",
                     "model_e": "model D + information-price gap",
                     **s2sum, "gates": g2}

    res["sensitivities"] = sensitivities(s1, s2)

    if not g2["passed"]:
        res["decision_label"] = LABELS[2]
        res["trading"] = "not run -- Stage 2 failed; no strategy is manufactured " \
                         "from a failed predictive gate"
        RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                           encoding="utf-8", newline="\n")
        print(LABELS[2])
        return 1

    # ---------------- Phase 5: trading ----------------
    tr = trading(s2)
    res["trading"] = tr
    res["decision_label"] = (LABELS[4] if tr["net_mean_positive"] else LABELS[3])
    RESULTS.write_text(json.dumps(res, indent=1, default=str) + "\n",
                       encoding="utf-8", newline="\n")
    print(res["decision_label"])
    return 0


def sensitivities(s1, s2):
    """Reported, never allowed to replace the primary result."""
    from scipy import stats
    out = {"note": "Reported for context. None of these replaces the primary result."}

    def ic_block(df, gcol, ycol, name, minimum=30):
        if len(df) < minimum:
            return {"status": "INSUFFICIENT_OBSERVATIONS", "n": int(len(df)),
                    "minimum": minimum,
                    "note": "reported as insufficient rather than gate-lowered"}
        r = stats.spearmanr(df[gcol].values, df[ycol].values)
        return {"n": int(len(df)), "spearman_ic": round(float(r.statistic), 5),
                "p_value": round(float(r.pvalue), 6),
                "mean_ar5_top_quintile_minus_bottom": None}

    fy = s2[s2.sec_fiscal_period_end.notna()].copy()
    fy["fye_month"] = pd.to_datetime(fy.sec_fiscal_period_end).dt.month
    mode = fy.groupby("ticker").fye_month.agg(lambda x: x.value_counts().idxmax())
    fy["is_fye_quarter"] = [m == mode.get(t) for t, m in zip(fy.ticker, fy.fye_month)]
    out["S1_exclude_fiscal_year_end_quarters"] = ic_block(
        fy[~fy.is_fye_quarter], "gap", "ar5", "S1")
    out["S1_excluded_count"] = int(fy.is_fye_quarter.sum())

    val = s2[s2.sec_audit_status == "validated"]
    out["S2_sec_validated_overlap_only"] = ic_block(val, "gap", "ar5", "S2")

    out["S3_strict_sec_seasonal_eps_shock"] = sec_seasonal_shock(s2)

    a20 = s2.dropna(subset=["ar20"])
    out["S4_twenty_session_horizon"] = {
        **ic_block(a20, "gap", "ar20", "S4"),
        "clearly_secondary": True,
        "note": "Secondary. It may not replace the five-session primary result."}

    out["S5_by_ticker"] = {
        t: {"n": int(len(g)),
            "spearman_ic": (round(float(stats.spearmanr(g.gap.values, g.ar5.values).statistic), 5)
                            if len(g) >= 8 else None),
            "mean_ar5_pct": round(100.0 * float(g.ar5.mean()), 4)}
        for t, g in s2.groupby("ticker")}
    out["S5_by_year"] = {
        int(y): {"n": int(len(g)),
                 "spearman_ic": round(float(stats.spearmanr(g.gap.values,
                                                            g.ar5.values).statistic), 5),
                 "mean_ar5_pct": round(100.0 * float(g.ar5.mean()), 4)}
        for y, g in s2.groupby("year")}
    return out


def sec_seasonal_shock(s2, min_hist=4):
    """Strict SEC-derived seasonal EPS shock, where SEC-validated EPS history allows."""
    from scipy import stats
    d = s2[(s2.sec_audit_status == "validated") & s2.sec_eps.notna()].copy()
    if d.empty:
        return {"status": "INSUFFICIENT_OBSERVATIONS", "n": 0,
                "note": "no SEC-validated EPS available on matched events"}
    panel = pd.read_csv(SEC_PANEL, usecols=["ticker", "fiscal_period_end", "eps",
                                            "audit_status"])
    panel = panel[(panel.audit_status == "validated") & panel.eps.notna()].copy()
    panel["fpe"] = pd.to_datetime(panel.fiscal_period_end, errors="coerce")
    panel = panel.dropna(subset=["fpe"]).sort_values(["ticker", "fpe"])
    shocks = []
    for r in d.itertuples(index=False):
        h = panel[(panel.ticker == r.ticker)
                  & (panel.fpe < pd.Timestamp(r.sec_fiscal_period_end))]
        if len(h) < min_hist + 4:
            continue
        e = h.eps.values
        diffs = e[4:] - e[:-4]
        if len(diffs) < min_hist:
            continue
        sd = float(np.std(diffs, ddof=0))
        if sd < 1e-9:
            continue
        prior = h[h.fpe <= pd.Timestamp(r.sec_fiscal_period_end) - pd.Timedelta(days=300)]
        if prior.empty:
            continue
        shocks.append({"gap": r.gap, "ar5": r.ar5,
                       "sue": (r.sec_eps - float(prior.eps.values[-1])) / sd})
    if len(shocks) < 30:
        return {"status": "INSUFFICIENT_OBSERVATIONS", "n": len(shocks), "minimum": 30,
                "note": ("smaller-sample sensitivity; reported as insufficient rather "
                         "than gate-lowered")}
    sdf = pd.DataFrame(shocks)
    r = stats.spearmanr(sdf.sue.values, sdf.ar5.values)
    return {"n": int(len(sdf)), "label": "SMALLER_SAMPLE_SENSITIVITY",
            "spearman_sue_vs_ar5": round(float(r.statistic), 5),
            "p_value": round(float(r.pvalue), 6)}


def trading(s2):
    """Quintile long/short on the OOS gap. Enters at close(T), exits at close(T+5)."""
    from scipy import stats
    d = s2.dropna(subset=["gap", "ar5"]).copy()
    d["q"] = d.groupby("year").gap.transform(
        lambda x: pd.qcut(x, QUANTILE, labels=False, duplicates="drop"))
    longs = d[d.q == d.q.max()]
    shorts = d[d.q == 0]
    gross = pd.concat([longs.ar5, -shorts.ar5]).values
    cost = COST_BPS_ROUND_TRIP / 10000.0
    net = gross - cost
    by_year = {}
    for y in sorted(d.year.unique()):
        ly = longs[longs.year == y].ar5
        sy = shorts[shorts.year == y].ar5
        gy = pd.concat([ly, -sy]).values
        by_year[int(y)] = {"trades": int(len(gy)),
                           "gross_mean_pct": round(100.0 * float(np.mean(gy)), 4),
                           "net_mean_pct": round(100.0 * float(np.mean(gy - cost)), 4)}
    eq = np.cumsum(net)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))
                      - np.concatenate([[0.0], eq])))
    t = stats.ttest_1samp(net, 0.0) if len(net) > 1 else None
    ls = pd.concat([longs.assign(sig=1.0), shorts.assign(sig=-1.0)])
    ls["signed_ret"] = ls.sig * ls.ar5
    return {
        "rule": ("rank OOS events by information-price gap; long the top quintile, "
                 "short the bottom quintile; enter at close(T); exit at close(T+5)"),
        "cost_bps_round_trip": COST_BPS_ROUND_TRIP,
        "trades": int(len(net)), "long_trades": int(len(longs)),
        "short_trades": int(len(shorts)),
        "gross_mean_pct": round(100.0 * float(np.mean(gross)), 4),
        "net_mean_pct": round(100.0 * float(np.mean(net)), 4),
        "net_mean_positive": bool(np.mean(net) > 0),
        "hit_rate": round(float((net > 0).mean()), 4),
        "turnover_trades_per_year": round(len(net) / max(1, d.year.nunique()), 2),
        "max_drawdown_of_cumulative_net": round(dd, 6),
        "t_stat": (None if t is None else round(float(t.statistic), 4)),
        "p_value": (None if t is None else round(float(t.pvalue), 6)),
        "cr2_inference_net": cr2_inference(ls.assign(gap_sig=ls.sig), "signed_ret", "gap_sig"),
        "by_year": by_year,
        "surprise_only_comparison": surprise_only(d, cost),
    }


def surprise_only(d, cost):
    q = d.groupby("year").z.transform(
        lambda x: pd.qcut(x, QUANTILE, labels=False, duplicates="drop"))
    longs, shorts = d[q == q.max()], d[q == 0]
    g = pd.concat([longs.ar5, -shorts.ar5]).values
    if len(g) == 0:
        return {"status": "INSUFFICIENT_OBSERVATIONS"}
    return {"rule": "equal-count quintile long/short ranked on transformed surprise alone",
            "trades": int(len(g)),
            "gross_mean_pct": round(100.0 * float(np.mean(g)), 4),
            "net_mean_pct": round(100.0 * float(np.mean(g - cost)), 4)}


if __name__ == "__main__":
    sys.exit(main())
