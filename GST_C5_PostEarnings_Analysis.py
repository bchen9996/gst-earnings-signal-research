#!/usr/bin/env python3
# LOCKED REGRESSION ANALYSIS for the post-earnings continuation/reversal
# (C5) test. Implements Live Signal Engine/C5_PostEarnings_PreRegistration.md
# sections 5-8 EXACTLY as written, against real QC/AlgoSeek data
# (Live Signal Engine/QC_C5_PostEarnings_RawResults.csv, n=235, pulled and
# returned after the pre-registration was locked). No metric, control, or
# threshold introduced here that isn't already in that document.
#
# Adds two covariates not in the QC pull (which only pulls prices):
#   - mkt_vol: VIX close on Day 0 (yfinance ^VIX), SPY 20-day trailing
#     realized vol as the documented fallback (pre-reg section 5).
#   - sector_ret: the sector ETF's own return over the SAME window used
#     inside C5 (9:45 Day0 -> close Day5) -- derived directly from columns
#     already in the QC pull (etf_945_price, etf_close_day5).
# gap_magnitude, BMO indicator, and year_FE are derived directly from
# existing columns.
#
# Output: Live Signal Engine/C5_PostEarnings_Analysis_Results.csv (per-row
# analysis dataset) + console report (the actual pre-registered result).

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf
import statsmodels.api as sm

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

RESULTS_PATH = Path("Live Signal Engine") / "QC_C5_PostEarnings_RawResults.csv"
OUT_PATH = Path("Live Signal Engine") / "C5_PostEarnings_Analysis_Results.csv"

N_BOOTSTRAP = 10000
RANDOM_SEED = 42
ALPHA = 0.05
SPY_VOL_LOOKBACK_TRADING_DAYS = 20

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_vix() -> pd.DataFrame:
    tk = yf.Ticker("^VIX", session=YF_SESSION)
    df = tk.history(start="2020-12-01", end="2026-01-15", interval="1d", auto_adjust=True)
    out = pd.DataFrame({"Date": pd.to_datetime(df.index).tz_localize(None), "vix_close": df["Close"].to_numpy()})
    return out.sort_values("Date").reset_index(drop=True)


def fetch_spy_realized_vol() -> pd.DataFrame:
    tk = yf.Ticker("SPY", session=YF_SESSION)
    df = tk.history(start="2020-10-01", end="2026-01-15", interval="1d", auto_adjust=True)
    out = pd.DataFrame({"Date": pd.to_datetime(df.index).tz_localize(None), "close": df["Close"].to_numpy()})
    out = out.sort_values("Date").reset_index(drop=True)
    out["ret"] = out["close"].pct_change()
    out["realized_vol"] = out["ret"].rolling(SPY_VOL_LOOKBACK_TRADING_DAYS).std() * np.sqrt(252)
    return out[["Date", "realized_vol"]]


def nearest_on_or_before(df: pd.DataFrame, date_col: str, val_col: str, target: pd.Timestamp) -> float | None:
    eligible = df.loc[df[date_col] <= target, val_col]
    return float(eligible.iloc[-1]) if not eligible.empty else None


def cluster_bootstrap_beta1(data: pd.DataFrame, y_col: str, x_cols: list[str], cluster_col: str,
                             n_boot: int, seed: int) -> np.ndarray:
    """Resample UNIQUE TICKERS with replacement (cluster/block bootstrap --
    preserves each ticker's own row structure intact, does not resample
    individual rows i.i.d.), refit OLS, record the z coefficient each time."""
    rng = np.random.RandomState(seed)
    tickers = data[cluster_col].unique()
    betas = np.empty(n_boot)
    grouped = {t: data[data[cluster_col] == t] for t in tickers}
    for b in range(n_boot):
        chosen = rng.choice(tickers, size=len(tickers), replace=True)
        sample = pd.concat([grouped[t] for t in chosen], ignore_index=True)
        X = sm.add_constant(sample[x_cols])
        try:
            fit = sm.OLS(sample[y_col], X).fit()
            betas[b] = fit.params["z"]
        except Exception:
            betas[b] = np.nan
    return betas


def fit_clustered(data: pd.DataFrame, y_col: str, x_cols: list[str], cluster_col: str):
    X = sm.add_constant(data[x_cols])
    model = sm.OLS(data[y_col], X)
    return model.fit(cov_type="cluster", cov_kwds={"groups": data[cluster_col]})


def build_design(df: pd.DataFrame, y_col: str) -> tuple[pd.DataFrame, list[str]]:
    d = df.dropna(subset=[y_col, "zscore", "gap_magnitude", "bmo_flag", "mkt_vol", "sector_ret", "year"]).copy()
    year_dummies = pd.get_dummies(d["year"], prefix="year", drop_first=True).astype(float)
    d = pd.concat([d, year_dummies], axis=1)
    x_cols = ["zscore", "gap_magnitude", "bmo_flag", "mkt_vol", "sector_ret"] + list(year_dummies.columns)
    d = d.rename(columns={"zscore": "z"})
    x_cols = ["z" if c == "zscore" else c for c in x_cols]
    return d, x_cols


def main():
    print("*** C5 POST-EARNINGS TEST -- LOCKED REGRESSION ANALYSIS ***\n")
    print(f"Source: {RESULTS_PATH}\n")

    raw = pd.read_csv(RESULTS_PATH)
    raw["earnings_date"] = pd.to_datetime(raw["earnings_date"])
    raw["day0_date"] = pd.to_datetime(raw["day0_date"])
    raw["day5_date"] = pd.to_datetime(raw["day5_date"])
    print(f"Rows loaded: {len(raw)} (expected 235, the locked sample size)\n")

    # ---- covariates not already in the QC pull ----
    print("Fetching VIX + SPY realized-vol (market-volatility control)...")
    vix = fetch_vix()
    spy_vol = fetch_spy_realized_vol()

    raw["mkt_vol"] = raw["day0_date"].apply(lambda d: nearest_on_or_before(vix, "Date", "vix_close", d))
    fallback_mask = raw["mkt_vol"].isna()
    if fallback_mask.any():
        print(f"  {fallback_mask.sum()} rows fell back to SPY realized vol (no VIX close resolved)")
        raw.loc[fallback_mask, "mkt_vol"] = raw.loc[fallback_mask, "day0_date"].apply(
            lambda d: nearest_on_or_before(spy_vol, "Date", "realized_vol", d))

    raw["sector_ret"] = (raw["etf_close_day5"] - raw["etf_945_price"]) / raw["etf_945_price"]
    raw["gap_magnitude"] = raw["gap"].abs()
    raw["bmo_flag"] = (raw["bmo_amc"] == "BMO").astype(float)
    raw["year"] = raw["day0_date"].dt.year

    raw.to_csv(OUT_PATH, index=False)
    print(f"Analysis dataset written: {OUT_PATH}\n")

    # =====================================================================
    # PRIMARY: Day 5
    # =====================================================================
    print("=" * 78)
    print("PRIMARY RESULT -- Day 5 (the sole primary horizon per pre-registration)")
    print("=" * 78 + "\n")

    d5, x_cols = build_design(raw, "C5")
    print(f"Usable rows for the primary regression: {len(d5)} / {len(raw)}")
    print(f"Regressors: {x_cols}\n")

    fit5 = fit_clustered(d5, "C5", x_cols, "ticker")
    beta1 = fit5.params["z"]
    se1_clustered = fit5.bse["z"]
    p1_clustered = fit5.pvalues["z"]
    ci_clustered = fit5.conf_int().loc["z"]

    print("--- Ticker-clustered OLS ---")
    print(f"beta_1 (z coefficient): {beta1:+.5f}")
    print(f"Clustered SE: {se1_clustered:.5f}   p-value: {p1_clustered:.4f}")
    print(f"95% CI (clustered): [{ci_clustered[0]:+.5f}, {ci_clustered[1]:+.5f}]")
    clustered_significant = p1_clustered < ALPHA
    print(f"Significant at 95% (clustered SE): {clustered_significant}\n")

    print(f"--- Ticker-cluster block bootstrap (N={N_BOOTSTRAP}, seed={RANDOM_SEED}) ---")
    boot_betas = cluster_bootstrap_beta1(d5, "C5", x_cols, "ticker", N_BOOTSTRAP, RANDOM_SEED)
    boot_betas = boot_betas[~np.isnan(boot_betas)]
    boot_lo, boot_hi = np.percentile(boot_betas, [2.5, 97.5])
    print(f"Bootstrap 95% CI: [{boot_lo:+.5f}, {boot_hi:+.5f}]  (n_valid_replicates={len(boot_betas)}/{N_BOOTSTRAP})")
    bootstrap_significant = not (boot_lo <= 0 <= boot_hi)
    print(f"Significant at 95% (bootstrap CI excludes 0): {bootstrap_significant}\n")

    # =====================================================================
    # STABILITY: LOTO + LOYO
    # =====================================================================
    print("=" * 78)
    print("STABILITY CHECKS -- Leave-One-Ticker-Out (LOTO) + Leave-One-Year-Out (LOYO)")
    print("=" * 78 + "\n")

    loto_results = []
    for t in sorted(d5["ticker"].unique()):
        sub = d5[d5["ticker"] != t]
        try:
            f = fit_clustered(sub, "C5", x_cols, "ticker")
            loto_results.append({"held_out": t, "n": len(sub), "beta_1": f.params["z"], "p": f.pvalues["z"]})
        except Exception as e:
            loto_results.append({"held_out": t, "n": len(sub), "beta_1": np.nan, "p": np.nan, "error": str(e)})
    loto_df = pd.DataFrame(loto_results)
    print(f"LOTO: {len(loto_df)} refits (one per unique ticker)")
    print(f"  beta_1 range: [{loto_df['beta_1'].min():+.5f}, {loto_df['beta_1'].max():+.5f}]")
    loto_sign_flips = (np.sign(loto_df["beta_1"]) != np.sign(beta1)).sum()
    print(f"  Sign flips vs. full-sample beta_1 ({beta1:+.5f}): {loto_sign_flips} / {len(loto_df)}")
    if loto_sign_flips:
        print(f"  Flipped when excluding: {loto_df.loc[np.sign(loto_df['beta_1']) != np.sign(beta1), 'held_out'].tolist()}")
    print()

    loyo_results = []
    for y in sorted(d5["year"].unique()):
        sub = d5[d5["year"] != y]
        try:
            f = fit_clustered(sub, "C5", x_cols, "ticker")
            loyo_results.append({"held_out": int(y), "n": len(sub), "beta_1": f.params["z"], "p": f.pvalues["z"]})
        except Exception as e:
            loyo_results.append({"held_out": int(y), "n": len(sub), "beta_1": np.nan, "p": np.nan, "error": str(e)})
    loyo_df = pd.DataFrame(loyo_results)
    print(f"LOYO: {len(loyo_df)} refits (one per calendar year)")
    print(f"  beta_1 range: [{loyo_df['beta_1'].min():+.5f}, {loyo_df['beta_1'].max():+.5f}]")
    loyo_sign_flips = (np.sign(loyo_df["beta_1"]) != np.sign(beta1)).sum()
    print(f"  Sign flips vs. full-sample beta_1 ({beta1:+.5f}): {loyo_sign_flips} / {len(loyo_df)}")
    if loyo_sign_flips:
        print(f"  Flipped when excluding: {loyo_df.loc[np.sign(loyo_df['beta_1']) != np.sign(beta1), 'held_out'].tolist()}")
    print()

    total_flips = loto_sign_flips + loyo_sign_flips
    total_refits = len(loto_df) + len(loyo_df)
    stable = total_flips == 0
    print(f"STABILITY VERDICT: {'STABLE' if stable else 'NOT STABLE'} -- "
          f"{total_flips} sign flip(s) across all {total_refits} LOTO+LOYO refits\n")

    # =====================================================================
    # BINDING DECISION RULE (pre-registration section 8, applied exactly)
    # =====================================================================
    print("=" * 78)
    print("BINDING DECISION RULE (C5_PostEarnings_PreRegistration.md section 8)")
    print("=" * 78 + "\n")
    condition_1 = clustered_significant and bootstrap_significant
    condition_2 = stable
    print(f"Condition 1 (beta_1 significant at 95% under BOTH clustered SE AND bootstrap CI): {condition_1}")
    print(f"Condition 2 (sign does not flip in any of {total_refits} LOTO/LOYO refits): {condition_2}")
    verdict = condition_1 and condition_2
    print()
    if verdict:
        print(">>> VERDICT: GST z-score shows a REAL, ROBUST relationship with C5 (post-earnings")
        print("    continuation/reversal) under this test's binding rule.")
    else:
        print(">>> VERDICT: this test does NOT show a real, robust relationship between GST z-score")
        print("    and C5, regardless of the full-sample point estimate's face-value magnitude or sign.")
    print()

    # =====================================================================
    # SECONDARY DIAGNOSTICS -- context only, NOT part of the decision rule
    # =====================================================================
    print("=" * 78)
    print("SECONDARY DIAGNOSTICS (context only -- do not affect the decision rule above)")
    print("=" * 78 + "\n")
    for label, col in [("Same-day (C_day0)", "C_day0"), ("Day 2 (C_day2)", "C_day2"), ("Day 20 (C_day20)", "C_day20")]:
        dN, xN = build_design(raw, col)
        fN = fit_clustered(dN, col, xN, "ticker")
        print(f"{label}: n={len(dN)}  beta_1(z)={fN.params['z']:+.5f}  "
              f"clustered SE={fN.bse['z']:.5f}  p={fN.pvalues['z']:.4f}")
    print()

    print("=== Full-sample descriptive context ===")
    print(f"n={len(d5)}  Mean C5={d5['C5'].mean():+.5f}  Median C5={d5['C5'].median():+.5f}  "
          f"Fraction C5>0: {(d5['C5']>0).mean()*100:.1f}%")
    print(f"Raw (unclustered) Pearson r(z, C5) = {d5['z'].corr(d5['C5']):.3f}   "
          f"Spearman rho = {d5['z'].corr(d5['C5'], method='spearman'):.3f}  "
          f"(uncontrolled -- the regression above is the actual test, this is context only)")


if __name__ == "__main__":
    main()
