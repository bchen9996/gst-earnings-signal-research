#!/usr/bin/env python3
# TASK 4 — Simple predictive model: does a logistic regression on 7
# already-touched features beat the current simple rule (trade every
# z>=5 STRONG_EARNINGS signal)?
#
# Features: z_score, days_to_earnings, sector (one-hot, top-3 + Other),
# log_market_cap, bb_width_ratio, prior_week_return, prior_week_volume_ratio.
# Target: end_of_spike_week win (binary).
#
# *** DATA SOURCING ***
# z_score, win: existing Group A file. days_to_earnings: existing gap_days
# lookup (Earnings Clustering Test flags, reused from earlier tasks).
# sector: reconstructed from Task2_SectorEffects_Results.csv's ticker
# lists (already pulled). bb_width_ratio = pre_spike_bb_width /
# ticker_median_bb_width, both already saved in
# Task5_BollingerBandWidth_Results.csv. prior_week_return and
# prior_week_volume_ratio: recomputed from on-disk daily price/volume data
# (same weekly-aggregation logic as GST_AbnormalGST_Residual_Test.py, not
# persisted per-event before now — pure on-disk recomputation, no pull).
# log_market_cap: the ONE genuinely new pull here — only bucket labels
# (large/mid/small) were persisted from the earlier market-cap task, not
# exact dollar values, and a continuous feature needs the real number.
# One lightweight yfinance call per unique ticker (28), cached.
#
# *** NO SKLEARN IN THIS ENVIRONMENT ***
# Logistic regression fit via Newton-Raphson / IRLS from scratch (numpy
# only). AUC-ROC computed via the Mann-Whitney U rank-sum identity
# (equivalent to sklearn's roc_auc_score, not an approximation).
#
# *** IN-SAMPLE, NOT OUT-OF-SAMPLE — DISCLOSED ***
# With n=147 and up to 10 parameters, a genuine train/test split would
# leave too little data to fit or evaluate reliably. AUC and accuracy
# reported here are IN-SAMPLE (fit and evaluated on the same 147 events)
# — a realistic upper bound on this model's performance, not a validated
# out-of-sample estimate. Flagged explicitly, not presented as OOS.
#
# Output: Live Signal Engine/Task4_LogisticModel_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys, time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS_ORIGINAL = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR
YEARS = list(range(2021, 2026))

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})
VOLUME_DIR = Path("Daily Volume Data (2021-2025)")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
FLAGS_PATHS = [
    Path("Earnings Clustering Test (2021-2025)") / "spike_event_earnings_flags.csv",
    Path("Earnings Clustering Test (2021-2025 Broad50 Clear)") / "spike_event_earnings_flags.csv",
]
SECTOR_PATH = Path("Live Signal Engine") / "Task2_SectorEffects_Results.csv"
BB_PATH = Path("Live Signal Engine") / "Task5_BollingerBandWidth_Results.csv"
OUT_PATH = Path("Live Signal Engine") / "Task4_LogisticModel_Results.csv"

Z_THRESHOLD = 5.0
VOLUME_ROLLING_WEEKS = 52
MIN_VOLUME_HISTORY_WEEKS = 26

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def week_start(d: pd.Series) -> pd.Series:
    d = pd.to_datetime(d)
    return d - pd.to_timedelta((d.dt.weekday + 1) % 7, unit="D")


def load_weekly_price_and_volume(ticker: str) -> pd.DataFrame:
    ret_frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        ret_col = f"{ticker} Daily Return"
        if "Date" not in df.columns or ret_col not in df.columns:
            continue
        df = df.rename(columns={ret_col: "ret"})[["Date", "ret"]]
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        ret_frames.append(df.dropna(subset=["Date"]))
    if not ret_frames:
        return pd.DataFrame()
    daily_ret = pd.concat(ret_frames, ignore_index=True).sort_values("Date").reset_index(drop=True)

    vol_path = VOLUME_DIR / f"{ticker}_volume.csv"
    if not vol_path.exists():
        return pd.DataFrame()
    daily_vol = pd.read_csv(vol_path)
    daily_vol["Date"] = pd.to_datetime(daily_vol["Date"], errors="coerce")

    daily = pd.merge(daily_ret, daily_vol, on="Date", how="inner").dropna()
    if daily.empty:
        return pd.DataFrame()
    daily["week"] = week_start(daily["Date"])
    weekly = daily.groupby("week").agg(
        weekly_return=("ret", lambda x: float(np.prod(1 + x) - 1)),
        weekly_volume=("Volume", "sum"),
    ).reset_index().sort_values("week").reset_index(drop=True)
    weekly["vol_roll_avg"] = weekly["weekly_volume"].shift(1).rolling(
        window=VOLUME_ROLLING_WEEKS, min_periods=MIN_VOLUME_HISTORY_WEEKS).mean()
    weekly["vol_ratio"] = weekly["weekly_volume"] / weekly["vol_roll_avg"]
    return weekly


def fetch_market_cap(ticker: str, max_attempts: int = 3) -> float | None:
    for attempt in range(1, max_attempts + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            cap = tk.fast_info.get("marketCap") or tk.info.get("marketCap")
            if cap:
                return float(cap)
        except Exception as e:
            print(f"  [{ticker}] attempt {attempt} failed: {e}")
        if attempt < max_attempts:
            time.sleep(5)
    return None


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


def fit_logistic_irls(X: np.ndarray, y: np.ndarray, max_iter=100, tol=1e-8, ridge=1e-6):
    n, p = X.shape
    beta = np.zeros(p)
    for it in range(max_iter):
        eta = X @ beta
        mu = sigmoid(eta)
        W = mu * (1 - mu)
        W = np.clip(W, 1e-8, None)
        XtW = X.T * W
        H = XtW @ X + ridge * np.eye(p)
        grad = X.T @ (y - mu)
        try:
            delta = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            delta = np.linalg.lstsq(H, grad, rcond=None)[0]
        beta_new = beta + delta
        if np.max(np.abs(beta_new - beta)) < tol:
            beta = beta_new
            break
        beta = beta_new
    eta = X @ beta
    mu = sigmoid(eta)
    return beta, mu


def auc_roc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    n_pos = len(pos)
    sum_ranks_pos = ranks[:n_pos].sum()
    auc = (sum_ranks_pos - n_pos * (n_pos + 1) / 2) / (n_pos * len(neg))
    return float(auc)


def main():
    print(f"*** TASK 4: Logistic model for STRONG_EARNINGS (z>={Z_THRESHOLD:g}) win/loss ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    tickers = sorted(events["ticker"].unique())
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)} across {len(tickers)} tickers\n")

    # days_to_earnings via existing gap_days lookup
    flags_frames = []
    for p in FLAGS_PATHS:
        f = pd.read_csv(p)
        f["anchor"] = pd.to_datetime(f["anchor"]).dt.date.astype(str)
        flags_frames.append(f)
    flags = pd.concat(flags_frames, ignore_index=True)
    gap_lookup = {(r["ticker"], r["anchor"]): r["nearest_earnings_gap_days"] for _, r in flags.iterrows()}
    events["days_to_earnings"] = [gap_lookup.get((t, sw.date().isoformat())) for t, sw in zip(events["ticker"], events["spike_week"])]

    # sector via reconstructed mapping
    sector_df = pd.read_csv(SECTOR_PATH)
    ticker_to_sector = {}
    for _, r in sector_df.iterrows():
        for t in [x.strip() for x in r["tickers"].split(",")]:
            ticker_to_sector[t] = r["sector"]
    top_sectors = {"Technology", "Consumer Cyclical", "Communication Services"}
    events["sector"] = events["ticker"].map(ticker_to_sector)
    events["sector_grouped"] = events["sector"].apply(lambda s: s if s in top_sectors else "Other")

    # bb_width_ratio via existing Task5 file
    bb_df = pd.read_csv(BB_PATH)
    bb_df["spike_week"] = pd.to_datetime(bb_df["spike_week"])
    bb_df["bb_width_ratio"] = bb_df["pre_spike_bb_width"] / bb_df["ticker_median_bb_width"]
    events = events.merge(bb_df[["ticker", "spike_week", "bb_width_ratio"]], on=["ticker", "spike_week"], how="left")

    # prior_week_return / prior_week_volume_ratio -- recomputed from on-disk data
    print("Recomputing prior-week return/volume ratio per ticker (on-disk data)...")
    weekly_cache: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        weekly_cache[ticker] = load_weekly_price_and_volume(ticker)
    prior_returns, prior_vol_ratios = [], []
    for _, ev in events.iterrows():
        wk = weekly_cache.get(ev["ticker"], pd.DataFrame())
        if wk.empty:
            prior_returns.append(None); prior_vol_ratios.append(None)
            continue
        prior_week = ev["spike_week"] - timedelta(days=7)
        row = wk[wk["week"] == prior_week]
        if row.empty:
            prior_returns.append(None); prior_vol_ratios.append(None)
        else:
            prior_returns.append(float(row["weekly_return"].iloc[0]))
            prior_vol_ratios.append(float(row["vol_ratio"].iloc[0]) if pd.notna(row["vol_ratio"].iloc[0]) else None)
    events["prior_week_return"] = prior_returns
    events["prior_week_volume_ratio"] = prior_vol_ratios

    # log_market_cap -- the one new pull
    print("Pulling current market cap per ticker (cached, one pull each)...")
    cap_map = {}
    for i, ticker in enumerate(tickers, start=1):
        cap = fetch_market_cap(ticker)
        cap_map[ticker] = cap
        print(f"  [{i}/{len(tickers)}] {ticker}: {'$'+format(cap/1e9, '.1f')+'B' if cap else 'N/A'}")
        time.sleep(0.8)
    events["market_cap"] = events["ticker"].map(cap_map)
    events["log_market_cap"] = np.log(events["market_cap"])
    print()

    feature_cols = ["zscore", "days_to_earnings", "log_market_cap", "bb_width_ratio",
                     "prior_week_return", "prior_week_volume_ratio"]
    model_df = events.dropna(subset=feature_cols + ["end_of_spike_week_win", "sector_grouped"]).copy()
    n_dropped = len(events) - len(model_df)
    print(f"Usable events for model (complete features): n={len(model_df)}  (dropped {n_dropped} with missing features)\n")

    y = model_df["end_of_spike_week_win"].astype(int).to_numpy()

    # Standardize continuous features so coefficient magnitude reflects relative importance
    X_cont_raw = model_df[feature_cols].to_numpy(dtype=float)
    means = X_cont_raw.mean(axis=0)
    stds = X_cont_raw.std(axis=0)
    stds[stds == 0] = 1.0
    X_cont = (X_cont_raw - means) / stds

    sector_dummies = pd.get_dummies(model_df["sector_grouped"], prefix="sector").astype(float)
    # drop one category as reference (Technology, if present, else whichever sorts first)
    ref_col = "sector_Technology" if "sector_Technology" in sector_dummies.columns else sector_dummies.columns[0]
    sector_dummies = sector_dummies.drop(columns=[ref_col])

    const = np.ones((len(model_df), 1))
    X = np.hstack([const, X_cont, sector_dummies.to_numpy(dtype=float)])
    feature_names = ["const"] + feature_cols + list(sector_dummies.columns)

    beta, mu = fit_logistic_irls(X, y.astype(float))

    auc = auc_roc(y, mu)
    pred_label = (mu > 0.5).astype(int)
    model_accuracy = (pred_label == y).mean() * 100

    always_win_accuracy = y.mean() * 100  # the "simple rule": trade every z>=5 signal, i.e. always predict win

    print("=== LOGISTIC REGRESSION COEFFICIENTS (standardized features) ===")
    coef_table = sorted(zip(feature_names, beta), key=lambda t: -abs(t[1]))
    for name, b in coef_table:
        print(f"  {name:<25} {b:+.4f}")

    print(f"\n=== MODEL PERFORMANCE (IN-SAMPLE — see header disclosure) ===")
    print(f"n={len(model_df)}")
    print(f"AUC-ROC: {auc:.4f}")
    print(f"Model accuracy (pred_prob>0.5): {model_accuracy:.1f}%")
    print(f"Simple rule accuracy (always predict win, i.e. trade every z>=5 signal): {always_win_accuracy:.1f}%")
    diff = model_accuracy - always_win_accuracy
    if diff > 2:
        verdict = f"Model BEATS the simple rule by {diff:.1f}pt (in-sample)."
    elif diff < -2:
        verdict = f"Model UNDERPERFORMS the simple rule by {abs(diff):.1f}pt (in-sample) — POSITIVE finding: added complexity doesn't help."
    else:
        verdict = f"Model roughly MATCHES the simple rule ({diff:+.1f}pt) — added complexity doesn't help."
    print(f"=> {verdict}")

    out = model_df[["ticker", "spike_week"] + feature_cols + ["sector_grouped", "end_of_spike_week_win"]].copy()
    out["predicted_prob"] = mu
    out["predicted_label"] = pred_label
    out.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
