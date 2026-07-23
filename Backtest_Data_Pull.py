#!/usr/bin/env python3
# Point-in-time backtest — Step B: pull raw SEC data for the universe.
#
# For each of the 150 universe tickers:
#   1. All Form 4 filings (and their parsed BUY-code-'P' transactions) from
#      FORM4_FETCH_START to today — wide enough to cover every quarterly
#      test date's trailing 90-day insider-buying lookback window.
#   2. Full historical XBRL "companyfacts" (Assets, AssetsCurrent, Cash,
#      LiabilitiesCurrent, debt-current, Depreciation/Amortization tags),
#      WITH each fact's `filed` date preserved, so Step D (the simulation)
#      can reconstruct "what was known as of test date T" without any
#      look-ahead — a 10-K isn't usable for a test date before its filed
#      date, even if its fiscal-year-end is earlier.
#
# This step is pure data collection — no signal logic, no thresholds — so
# Step D can be re-run/tuned repeatedly without re-hitting SEC.
#
# Runs concurrently (thread pool) with a shared rate limiter capped under
# SEC's stated 10 req/s guideline, since a fully serial pull across 150
# tickers x ~3 years of Form 4 history would take on the order of hours.
#
# Output: Stock Screening/Backtest Data/insider_buys_raw.csv
#         Stock Screening/Backtest Data/accrual_facts_raw.csv
#         Stock Screening/Backtest Data/data_pull_log.csv  (per-ticker status)

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
import pandas as pd

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

USER_AGENT = "Harshith Akurati Independent Research hakurati11@gmail.com"
OUT_DIR = Path("Stock Screening") / "Backtest Data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK_YEARS = 3
END_BUFFER_DAYS = 210          # test dates must end this far before "today" (leaves room for 180d forward return)
INSIDER_LOOKBACK_DAYS = 90     # matches the Step 1 gate definition

MAX_WORKERS = 8
MAX_REQ_PER_SEC = 8.0          # stays under SEC's ~10 req/s guideline with headroom

BALANCE_SHEET_TAGS = ["Assets", "AssetsCurrent", "LiabilitiesCurrent"]
CASH_TAGS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "CashCashEquivalentsAndShortTermInvestments",
    "Cash",
]
DEBT_CURRENT_TAGS = ["DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings", "NotesPayableCurrent", "CommercialPaper"]
DEPRECIATION_TAGS = [
    "DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
    "DepreciationAmortizationAndAccretionNet", "Depreciation", "AmortizationOfIntangibleAssets",
]
ALL_FACT_TAGS = list(dict.fromkeys(BALANCE_SHEET_TAGS + CASH_TAGS + DEBT_CURRENT_TAGS + DEPRECIATION_TAGS))


class RateLimiter:
    def __init__(self, max_per_sec: float):
        self.min_interval = 1.0 / max_per_sec
        self.lock = threading.Lock()
        self.last_call = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.monotonic()


RATE_LIMITER = RateLimiter(MAX_REQ_PER_SEC)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    s.verify = False
    return s


def get(session: requests.Session, url: str, retries: int = 5):
    for attempt in range(1, retries + 1):
        RATE_LIMITER.wait()
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 429:
                time.sleep(5 * attempt)
                continue
            resp.raise_for_status()
            return resp
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 * attempt)
    raise RuntimeError(f"failed to fetch {url}")


def _text(el, path, default=None):
    node = el.find(path)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def parse_form4_buys(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    owner_name = _text(root, "./reportingOwner/reportingOwnerId/rptOwnerName", "UNKNOWN")
    owner_cik = _text(root, "./reportingOwner/reportingOwnerId/rptOwnerCik", "UNKNOWN")

    buys = []
    for txn in root.findall("./nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(txn, "./transactionCoding/transactionCode")
        if code != "P":
            continue
        shares_txt = _text(txn, "./transactionAmounts/transactionShares/value")
        price_txt = _text(txn, "./transactionAmounts/transactionPricePerShare/value")
        date_txt = _text(txn, "./transactionDate/value")
        if shares_txt is None or price_txt is None or date_txt is None:
            continue
        try:
            shares, price = float(shares_txt), float(price_txt)
        except ValueError:
            continue
        buys.append({
            "insider_name": owner_name, "insider_cik": owner_cik,
            "transaction_date": date_txt, "shares": shares, "price": price,
            "dollar_value": shares * price,
        })
    return buys


def fetch_ticker(ticker: str, cik: str, form4_fetch_start: datetime) -> dict:
    session = make_session()
    result = {"ticker": ticker, "cik": cik, "buys": [], "facts": [], "status": "ok", "error": ""}

    try:
        resp = get(session, f"https://data.sec.gov/submissions/CIK{cik}.json")
        sub = resp.json()
        recent = sub["filings"]["recent"]
        cik_int = int(cik)
        n_form4 = 0
        for form, acc, doc, fdate in zip(recent["form"], recent["accessionNumber"],
                                          recent["primaryDocument"], recent["filingDate"]):
            if form != "4":
                continue
            fdate_dt = datetime.strptime(fdate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if fdate_dt < form4_fetch_start:
                continue
            n_form4 += 1
            accession_nodash = acc.replace("-", "")
            raw_filename = doc.split("/")[-1]
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{raw_filename}"
            try:
                xml_resp = get(session, doc_url)
                buys = parse_form4_buys(xml_resp.content)
            except Exception:
                continue
            for b in buys:
                b["ticker"] = ticker
                b["accession"] = acc
                b["filing_date"] = fdate
            result["buys"].extend(buys)
        result["n_form4_scanned"] = n_form4
    except Exception as e:
        result["status"] = "form4_failed"
        result["error"] = str(e)

    try:
        resp = get(session, f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        cf = resp.json()
        gaap = cf.get("facts", {}).get("us-gaap", {})
        for tag in ALL_FACT_TAGS:
            entries = gaap.get(tag, {}).get("units", {}).get("USD", [])
            for e in entries:
                if not e.get("form", "").startswith("10-K"):
                    continue
                if e.get("end") is None or e.get("val") is None or e.get("filed") is None:
                    continue
                result["facts"].append({
                    "ticker": ticker, "tag": tag, "start": e.get("start"),
                    "end": e["end"], "val": e["val"], "filed": e["filed"],
                    "fy": e.get("fy"), "fp": e.get("fp"),
                })
    except Exception as e:
        if result["status"] == "ok":
            result["status"] = "companyfacts_failed"
        result["error"] = (result["error"] + " | " if result["error"] else "") + f"companyfacts: {e}"

    return result


def main():
    universe = pd.read_csv(Path("Stock Screening") / "Backtest Data" / "backtest_universe.csv",
                            dtype={"cik": str})

    now = datetime.now(timezone.utc)
    test_date_end = now - timedelta(days=END_BUFFER_DAYS)
    test_date_start = test_date_end - timedelta(days=LOOKBACK_YEARS * 365)
    form4_fetch_start = test_date_start - timedelta(days=INSIDER_LOOKBACK_DAYS)

    print(f"Universe: {len(universe)} tickers")
    print(f"Test date window: {test_date_start.date()} to {test_date_end.date()}")
    print(f"Form 4 fetch start (covers first test date's {INSIDER_LOOKBACK_DAYS}d lookback): {form4_fetch_start.date()}")
    print(f"Concurrency: {MAX_WORKERS} workers, capped at {MAX_REQ_PER_SEC} req/s aggregate\n")

    all_buys = []
    all_facts = []
    log_rows = []
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(fetch_ticker, row.ticker, row.cik, form4_fetch_start): row.ticker
            for row in universe.itertuples()
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            done += 1
            try:
                result = fut.result()
            except Exception as e:
                print(f"[{done}/{len(universe)}] {ticker}: FAILED unexpectedly: {e}", flush=True)
                log_rows.append({"ticker": ticker, "status": "exception", "error": str(e),
                                  "n_form4_scanned": 0, "n_buys": 0, "n_facts": 0})
                continue

            all_buys.extend(result["buys"])
            all_facts.extend(result["facts"])
            log_rows.append({
                "ticker": result["ticker"], "status": result["status"], "error": result["error"],
                "n_form4_scanned": result.get("n_form4_scanned", 0),
                "n_buys": len(result["buys"]), "n_facts": len(result["facts"]),
            })
            print(f"[{done}/{len(universe)}] {ticker}: {result.get('n_form4_scanned', 0)} Form4s scanned, "
                  f"{len(result['buys'])} buys, {len(result['facts'])} fact-entries "
                  f"({result['status']})", flush=True)

    buys_df = pd.DataFrame(all_buys)
    facts_df = pd.DataFrame(all_facts)
    log_df = pd.DataFrame(log_rows)

    buys_df.to_csv(OUT_DIR / "insider_buys_raw.csv", index=False)
    facts_df.to_csv(OUT_DIR / "accrual_facts_raw.csv", index=False)
    log_df.to_csv(OUT_DIR / "data_pull_log.csv", index=False)

    print(f"\nWrote {len(buys_df)} buy transactions to insider_buys_raw.csv")
    print(f"Wrote {len(facts_df)} fact entries to accrual_facts_raw.csv")
    print(f"Wrote per-ticker pull log to data_pull_log.csv")
    n_failed = (log_df["status"] != "ok").sum()
    if n_failed:
        print(f"\n{n_failed} tickers had a pull issue (see data_pull_log.csv):")
        print(log_df[log_df["status"] != "ok"][["ticker", "status", "error"]].to_string(index=False))


if __name__ == "__main__":
    main()
