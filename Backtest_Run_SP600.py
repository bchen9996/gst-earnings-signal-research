#!/usr/bin/env python3
# Point-in-time backtest — Step D (S&P 600 / small-cap variant).
#
# Identical point-in-time engine to Backtest_Run.py — see that file for full
# header documentation — pointed at the S&P 600 sampled universe. Kept as a
# separate module (rather than a DATA_DIR parameter) so Backtest_Run_Variants_SP600.py
# can import its functions/constants directly, same pattern as the S&P 500 pair.
#
# Input : Stock Screening/Backtest Data SP600/backtest_universe.csv
#         Stock Screening/Backtest Data SP600/insider_buys_raw.csv
#         Stock Screening/Backtest Data SP600/accrual_facts_raw.csv
#         Stock Screening/Backtest Data SP600/backtest_prices.csv
# Output: Stock Screening/Backtest Data SP600/backtest_trades_90d.csv
#         Stock Screening/Backtest Data SP600/backtest_trades_180d.csv
#         Stock Screening/Backtest Data SP600/backtest_summary.csv

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd

DATA_DIR = Path("Stock Screening") / "Backtest Data SP600"

LOOKBACK_YEARS = 3
END_BUFFER_DAYS = 210
TEST_DATE_STEP_DAYS = 91          # ~quarterly
INSIDER_LOOKBACK_DAYS = 90
HORIZONS = [90, 180]
TRANSACTION_COST_ONE_WAY = 0.0010  # 10 bps per fill; round trip = 2x this
SLOAN_CAUTION_QUANTILE = 0.75
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

CASH_TAGS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "CashCashEquivalentsAndShortTermInvestments",
    "Cash",
]
DEBT_CURRENT_TAGS = ["DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings", "NotesPayableCurrent", "CommercialPaper"]
DEPRECIATION_COMBINED_TAGS = [
    "DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet",
]


def instant_value_asof(ticker_facts: pd.DataFrame, tags: list[str], end_date: str, asof: pd.Timestamp):
    for tag in tags:
        sub = ticker_facts[(ticker_facts["tag"] == tag) & (ticker_facts["end"] == end_date)
                            & (ticker_facts["filed"] <= asof)]
        if not sub.empty:
            return sub.sort_values("filed").iloc[-1]["val"], tag
    return None, None


def duration_value_asof(ticker_facts: pd.DataFrame, tag: str, end_date: str, asof: pd.Timestamp):
    sub = ticker_facts[(ticker_facts["tag"] == tag) & (ticker_facts["end"] == end_date)
                        & (ticker_facts["filed"] <= asof) & ticker_facts["start"].notna()]
    if sub.empty:
        return None
    sub = sub.copy()
    sub["days"] = (pd.to_datetime(sub["end"]) - pd.to_datetime(sub["start"])).dt.days
    sub = sub[(sub["days"] >= 340) & (sub["days"] <= 386)]
    if sub.empty:
        return None
    return sub.sort_values("filed").iloc[-1]["val"]


def depreciation_asof(ticker_facts: pd.DataFrame, end_date: str, asof: pd.Timestamp):
    for tag in DEPRECIATION_COMBINED_TAGS:
        v = duration_value_asof(ticker_facts, tag, end_date, asof)
        if v is not None:
            return v
    dep = duration_value_asof(ticker_facts, "Depreciation", end_date, asof)
    amort = duration_value_asof(ticker_facts, "AmortizationOfIntangibleAssets", end_date, asof)
    if dep is not None or amort is not None:
        return (dep or 0) + (amort or 0)
    return None


def accruals_asof(ticker_facts: pd.DataFrame, asof: pd.Timestamp):
    assets = ticker_facts[(ticker_facts["tag"] == "Assets") & (ticker_facts["filed"] <= asof)]
    if assets.empty:
        return None
    ends = sorted(assets["end"].unique(), reverse=True)
    if len(ends) < 2:
        return None
    curr_end, prior_end = ends[0], ends[1]

    total_assets_curr, _ = instant_value_asof(ticker_facts, ["Assets"], curr_end, asof)
    total_assets_prior, _ = instant_value_asof(ticker_facts, ["Assets"], prior_end, asof)
    if total_assets_curr is None or total_assets_prior is None:
        return None
    avg_ta = (total_assets_curr + total_assets_prior) / 2
    if avg_ta == 0:
        return None

    ca_curr, _ = instant_value_asof(ticker_facts, ["AssetsCurrent"], curr_end, asof)
    ca_prior, _ = instant_value_asof(ticker_facts, ["AssetsCurrent"], prior_end, asof)
    cash_curr, _ = instant_value_asof(ticker_facts, CASH_TAGS, curr_end, asof)
    cash_prior, _ = instant_value_asof(ticker_facts, CASH_TAGS, prior_end, asof)
    cl_curr, _ = instant_value_asof(ticker_facts, ["LiabilitiesCurrent"], curr_end, asof)
    cl_prior, _ = instant_value_asof(ticker_facts, ["LiabilitiesCurrent"], prior_end, asof)
    debt_curr, _ = instant_value_asof(ticker_facts, DEBT_CURRENT_TAGS, curr_end, asof)
    debt_prior, _ = instant_value_asof(ticker_facts, DEBT_CURRENT_TAGS, prior_end, asof)
    dep = depreciation_asof(ticker_facts, curr_end, asof)

    if None in (ca_curr, ca_prior, cash_curr, cash_prior, cl_curr, cl_prior, dep):
        return None

    debt_curr = debt_curr or 0.0
    debt_prior = debt_prior or 0.0

    delta_non_cash_ca = (ca_curr - cash_curr) - (ca_prior - cash_prior)
    delta_cl_excl_debt = (cl_curr - debt_curr) - (cl_prior - debt_prior)
    return (delta_non_cash_ca - delta_cl_excl_debt - dep) / avg_ta


def insider_signal_asof(ticker_buys: pd.DataFrame, test_date: pd.Timestamp):
    if ticker_buys.empty:
        return False, 0
    lo = test_date - pd.Timedelta(days=INSIDER_LOOKBACK_DAYS)
    sub = ticker_buys[(ticker_buys["filing_date"] <= test_date)
                       & (ticker_buys["transaction_date"] > lo)
                       & (ticker_buys["transaction_date"] <= test_date)]
    return len(sub) > 0, len(sub)


def price_on_or_after(series: pd.Series, date):
    pos = series.index.searchsorted(date)
    if pos >= len(series):
        return None, None
    return series.index[pos], series.iloc[pos]


def price_on_or_before(series: pd.Series, date):
    if len(series) == 0 or date < series.index[0]:
        return None, None
    pos = series.index.searchsorted(date, side="right") - 1
    if pos < 0:
        return None, None
    return series.index[pos], series.iloc[pos]


def sign_flip_test(values: np.ndarray, n_perm: int, rng: np.random.Generator):
    if len(values) == 0:
        return None, None
    obs = values.mean()
    count = 0
    for _ in range(n_perm):
        signs = rng.choice([-1.0, 1.0], size=len(values))
        if abs((values * signs).mean()) >= abs(obs):
            count += 1
    return obs, count / n_perm


def main():
    universe = pd.read_csv(DATA_DIR / "backtest_universe.csv")
    tickers = universe["ticker"].tolist()

    buys = pd.read_csv(DATA_DIR / "insider_buys_raw.csv")
    buys["transaction_date"] = pd.to_datetime(buys["transaction_date"])
    buys["filing_date"] = pd.to_datetime(buys["filing_date"])

    facts = pd.read_csv(DATA_DIR / "accrual_facts_raw.csv")
    facts["filed"] = pd.to_datetime(facts["filed"])

    prices = pd.read_csv(DATA_DIR / "backtest_prices.csv")
    prices["Date"] = pd.to_datetime(prices["Date"])

    price_series = {t: g.set_index("Date")["close"].sort_index() for t, g in prices.groupby("ticker")}
    if "SPY" not in price_series:
        raise RuntimeError("No SPY price data found — run Backtest_Prices_SP600.py first.")
    spy = price_series["SPY"]

    buys_by_ticker = {t: g for t, g in buys.groupby("ticker")} if not buys.empty else {}
    facts_by_ticker = {t: g for t, g in facts.groupby("ticker")} if not facts.empty else {}

    now = datetime.now(timezone.utc)
    test_date_end = (now - timedelta(days=END_BUFFER_DAYS)).date()
    test_date_start = (pd.Timestamp(test_date_end) - pd.Timedelta(days=LOOKBACK_YEARS * 365)).date()
    test_dates = pd.date_range(test_date_start, test_date_end, freq=f"{TEST_DATE_STEP_DAYS}D")

    print(f"Test dates ({len(test_dates)}): {test_dates[0].date()} to {test_dates[-1].date()}, "
          f"every {TEST_DATE_STEP_DAYS} days\n")

    signal_log = []
    trades = {h: [] for h in HORIZONS}

    for test_date in test_dates:
        rows = []
        for ticker in tickers:
            tbuys = buys_by_ticker.get(ticker, pd.DataFrame(columns=["filing_date", "transaction_date"]))
            insider_flag, n_buys = insider_signal_asof(tbuys, test_date)

            tfacts = facts_by_ticker.get(ticker)
            accr = accruals_asof(tfacts, test_date) if tfacts is not None else None

            rows.append({"ticker": ticker, "insider_flag": insider_flag, "n_buys": n_buys, "accr": accr})

        day_df = pd.DataFrame(rows)
        valid = day_df["accr"].notna()
        n_valid = int(valid.sum())
        if n_valid >= 4:
            q75 = day_df.loc[valid, "accr"].quantile(SLOAN_CAUTION_QUANTILE)
            day_df["sloan_ok"] = valid & (day_df["accr"] < q75)
        else:
            q75 = None
            day_df["sloan_ok"] = False

        day_df["combined_signal"] = day_df["insider_flag"] & day_df["sloan_ok"]
        fired = day_df[day_df["combined_signal"]]

        signal_log.append({
            "test_date": test_date.date(), "n_insider_flagged": int(day_df["insider_flag"].sum()),
            "n_accruals_valid": n_valid, "n_combined_signal": len(fired),
            "tickers_fired": ", ".join(fired["ticker"].tolist()),
        })

        for _, sig_row in fired.iterrows():
            ticker = sig_row["ticker"]
            s = price_series.get(ticker)
            if s is None or s.empty:
                continue
            entry_date, entry_price = price_on_or_after(s, test_date)
            spy_entry_date, spy_entry_price = price_on_or_after(spy, test_date)
            if entry_price is None or spy_entry_price is None:
                continue

            for h in HORIZONS:
                exit_target = entry_date + pd.Timedelta(days=h)
                exit_date, exit_price = price_on_or_before(s, exit_target)
                spy_exit_date, spy_exit_price = price_on_or_before(spy, exit_target)
                if exit_price is None or spy_exit_price is None or exit_date <= entry_date:
                    continue

                raw_return = exit_price / entry_price - 1
                net_return = raw_return - 2 * TRANSACTION_COST_ONE_WAY
                spy_return = spy_exit_price / spy_entry_price - 1
                excess_return = net_return - spy_return

                trades[h].append({
                    "test_date": test_date.date(), "ticker": ticker,
                    "n_insider_buys": int(sig_row["n_buys"]), "accruals_ratio": sig_row["accr"],
                    "entry_date": entry_date.date(), "entry_price": entry_price,
                    "exit_date": exit_date.date(), "exit_price": exit_price,
                    "raw_return": raw_return, "net_return": net_return,
                    "spy_return": spy_return, "excess_return": excess_return,
                })

    signal_log_df = pd.DataFrame(signal_log)
    signal_log_df.to_csv(DATA_DIR / "backtest_signal_log.csv", index=False)
    print("--- Signal fire log per test date ---")
    print(signal_log_df[["test_date", "n_insider_flagged", "n_accruals_valid", "n_combined_signal"]]
          .to_string(index=False))

    rng = np.random.default_rng(RANDOM_SEED)
    summary_rows = []
    for h in HORIZONS:
        tdf = pd.DataFrame(trades[h])
        out_path = DATA_DIR / f"backtest_trades_{h}d.csv"
        tdf.to_csv(out_path, index=False)

        if tdf.empty:
            summary_rows.append({"horizon_days": h, "n_trades": 0, "win_rate": None,
                                  "avg_excess_return": None, "avg_net_return": None,
                                  "avg_spy_return": None, "p_value": None})
            print(f"\nHorizon {h}d: 0 trades")
            continue

        excess = tdf["excess_return"].to_numpy()
        win_rate = float((excess > 0).mean())
        obs_mean, p_value = sign_flip_test(excess, N_PERMUTATIONS, rng)

        summary_rows.append({
            "horizon_days": h, "n_trades": len(tdf), "win_rate": round(win_rate, 4),
            "avg_excess_return": round(float(obs_mean), 5),
            "avg_net_return": round(float(tdf["net_return"].mean()), 5),
            "avg_spy_return": round(float(tdf["spy_return"].mean()), 5),
            "p_value": round(p_value, 4),
        })

        print(f"\n=== Horizon {h}d ===")
        print(f"Trades: {len(tdf)}")
        print(f"Win rate (excess return > 0): {win_rate*100:.1f}%")
        print(f"Avg net trade return (after {2*TRANSACTION_COST_ONE_WAY*10000:.0f}bps round-trip cost): "
              f"{tdf['net_return'].mean()*100:+.2f}%")
        print(f"Avg SPY return over same windows: {tdf['spy_return'].mean()*100:+.2f}%")
        print(f"Avg excess return vs SPY: {obs_mean*100:+.2f}%")
        print(f"Sign-flip permutation p-value (H0: mean excess return = 0): {p_value:.4f} "
              f"{'(significant at 0.05)' if p_value < 0.05 else '(NOT significant at 0.05)'}")

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(DATA_DIR / "backtest_summary.csv", index=False)

    print(f"\nWrote per-trade detail and summary to: {DATA_DIR}")
    print("\n--- CAVEATS ---")
    print("- Universe = today's S&P 600 sampled retroactively (150 names, seed=42) — "
          "survivorship/membership-date bias, not true point-in-time index reconstruction.")
    print("- Transaction cost: 10bps per fill, 20bps round trip, flat assumption — no slippage/spread/impact model.")
    print("- Entry = next close on/after signal date; exit = closest close at/before target horizon.")
    print("- Sloan accruals gate is a relative top-quartile CAUTION flag recomputed fresh at each test date "
          "from only point-in-time-available 10-K facts (filed date <= test date).")


if __name__ == "__main__":
    main()
