#!/usr/bin/env python3
# TASK 2 — 8-K frequency signal infrastructure. Uses SEC EDGAR's public
# submissions API (data.sec.gov/submissions/) to count 8-K filings in the
# 30 days before a given earnings date vs a ticker's own baseline 8-K rate
# (prior 12 months, computed BEFORE that same 30-day window so the
# baseline never overlaps the signal window).
#
# 8K_anomaly_score = (recent_30day_count - baseline_monthly_rate) / baseline_std
# High positive score = unusually heavy 8-K filing activity right before
# earnings (could reflect material-event disclosures clustering ahead of
# a report). baseline_std is computed across 12 monthly buckets within the
# baseline window, not assumed.
#
# *** POINT-IN-TIME DISCLOSURE ***
# Both the 30-day window and the 12-month baseline window are strictly
# BEFORE the earnings_date passed in — no filing on or after earnings_date
# is ever counted, so this is safe to use as a historical backtest feature
# without look-ahead risk (unlike the Alpha Vantage EARNINGS_ESTIMATES
# endpoint recon'd in Task 1, which recomputes against today's date).
#
# *** RATE LIMIT / ETIQUETTE ***
# SEC EDGAR requires a descriptive User-Agent identifying the requester
# (fair-access policy) and recommends staying under ~10 req/sec. This
# module caches each ticker's full submissions history in memory after
# one fetch, so repeated calls for the same ticker across many earnings
# dates (as Task 4 will do) cost exactly one HTTP request per ticker.

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import time
import numpy as np
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings()

USER_AGENT = "GST Research Project research@example.com"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"

RECENT_WINDOW_DAYS = 30
BASELINE_WINDOW_DAYS = 365
BASELINE_N_MONTHS = 12

_SESSION = requests.Session()
_SESSION.verify = False
_SESSION.headers.update({"User-Agent": USER_AGENT})

_ticker_to_cik_cache: dict[str, str] | None = None
_filings_cache: dict[str, pd.DataFrame] = {}


def _load_ticker_to_cik() -> dict[str, str]:
    global _ticker_to_cik_cache
    if _ticker_to_cik_cache is not None:
        return _ticker_to_cik_cache
    r = _SESSION.get(TICKER_MAP_URL, timeout=20)
    r.raise_for_status()
    data = r.json()
    _ticker_to_cik_cache = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}
    return _ticker_to_cik_cache


def get_cik(ticker: str) -> str | None:
    return _load_ticker_to_cik().get(ticker.upper())


def _fetch_submissions_page(url_or_name: str, is_full_url: bool = False) -> dict:
    url = url_or_name if is_full_url else SUBMISSIONS_PAGE_URL.format(name=url_or_name)
    r = _SESSION.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def get_all_filings(ticker: str, earliest_needed: pd.Timestamp | None = None) -> pd.DataFrame:
    """All (form, filingDate) rows for this ticker, sorted ascending. Cached per ticker.
    Fetches older paginated submission files only if `earliest_needed` predates
    what the 'recent' page already covers."""
    ticker = ticker.upper()
    if ticker in _filings_cache:
        return _filings_cache[ticker]

    cik = get_cik(ticker)
    if cik is None:
        _filings_cache[ticker] = pd.DataFrame(columns=["form", "filingDate"])
        return _filings_cache[ticker]

    data = _fetch_submissions_page(SUBMISSIONS_URL.format(cik=cik), is_full_url=True)
    recent = data["filings"]["recent"]
    rows = pd.DataFrame({"form": recent["form"], "filingDate": pd.to_datetime(recent["filingDate"])})

    if earliest_needed is not None and not rows.empty and rows["filingDate"].min() > earliest_needed:
        for page in data["filings"].get("files", []):
            page_from = pd.Timestamp(page["filingFrom"])
            if page_from > rows["filingDate"].min() and rows["filingDate"].min() <= earliest_needed:
                break  # already have enough history
            page_data = _fetch_submissions_page(page["name"])
            page_rows = pd.DataFrame({"form": page_data["form"], "filingDate": pd.to_datetime(page_data["filingDate"])})
            rows = pd.concat([rows, page_rows], ignore_index=True)
            time.sleep(0.15)
            if rows["filingDate"].min() <= earliest_needed:
                break

    rows = rows.sort_values("filingDate").reset_index(drop=True)
    _filings_cache[ticker] = rows
    return rows


def compute_8k_anomaly_score(ticker: str, earnings_date) -> dict:
    """Point-in-time 8-K filing anomaly score as of `earnings_date`.
    Returns dict with recent_30d_count, baseline_monthly_rate, baseline_std,
    anomaly_score (None if baseline_std is 0 or data is insufficient)."""
    earnings_date = pd.Timestamp(earnings_date)
    baseline_start = earnings_date - timedelta(days=RECENT_WINDOW_DAYS + BASELINE_WINDOW_DAYS)

    filings = get_all_filings(ticker, earliest_needed=baseline_start)
    eight_k = filings[filings["form"] == "8-K"]

    recent_start = earnings_date - timedelta(days=RECENT_WINDOW_DAYS)
    recent_mask = (eight_k["filingDate"] >= recent_start) & (eight_k["filingDate"] < earnings_date)
    recent_30d_count = int(recent_mask.sum())

    baseline_end = recent_start
    baseline_mask = (eight_k["filingDate"] >= baseline_start) & (eight_k["filingDate"] < baseline_end)
    baseline_filings = eight_k.loc[baseline_mask].copy()

    if baseline_filings.empty:
        monthly_counts = np.zeros(BASELINE_N_MONTHS)
    else:
        baseline_filings["month_bucket"] = ((baseline_end - baseline_filings["filingDate"]).dt.days // 30).clip(upper=BASELINE_N_MONTHS - 1)
        counts = baseline_filings.groupby("month_bucket").size()
        monthly_counts = np.array([counts.get(i, 0) for i in range(BASELINE_N_MONTHS)], dtype=float)

    baseline_monthly_rate = float(monthly_counts.mean())
    baseline_std = float(monthly_counts.std(ddof=1)) if len(monthly_counts) > 1 else 0.0

    if baseline_std > 0:
        anomaly_score = (recent_30d_count - baseline_monthly_rate) / baseline_std
    else:
        anomaly_score = None

    return {
        "ticker": ticker, "earnings_date": earnings_date.date(),
        "recent_30d_count": recent_30d_count, "baseline_monthly_rate": round(baseline_monthly_rate, 3),
        "baseline_std": round(baseline_std, 3),
        "anomaly_score": round(anomaly_score, 3) if anomaly_score is not None else None,
        "cik": get_cik(ticker),
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(compute_8k_anomaly_score("MSFT", "2023-07-25"))
