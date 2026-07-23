#!/usr/bin/env python3
# Stock Screening Pipeline — Step 1: Insider buying pull (informational, not
# a hard pass/fail gate).
#
# Pulls Form 4 filings from SEC EDGAR for the candidate universe, keeps only
# open-market/private PURCHASE transactions (transactionCode == "P" — this
# excludes sells, grants/awards, tax-withholding dispositions, option
# exercises, etc., since those aren't a discretionary "insider put their own
# cash in" signal), and reports buy activity per ticker at THREE lookback
# windows (90 / 180 / 365 days) side by side, so the choice of window isn't
# baked in before we've seen how sensitive the picture is to it.
#
# Filings are fetched once at the widest window (365 days) and then bucketed
# into all three windows by transaction_date, so each filing/XML is only
# fetched once regardless of how many windows it falls into.
#
# Output: Stock Screening/insider_buying_summary.csv           (wide, one row per ticker)
#         Stock Screening/insider_buying_transactions_detail.csv (one row per buy txn)

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
import time
import xml.etree.ElementTree as ET
import requests
import urllib3
import pandas as pd

# Local AVG web-shield SSL interception breaks cert verification on this
# machine; browsers trust its injected root cert, requests/certifi doesn't.
urllib3.disable_warnings()

TICKERS = [
    "ADI","ALB","AMAT","AXON","BEN","CIEN","COHR","CSCO","DELL","EME","F",
    "FLEX","FOXA","HPE","INTC","JBL","KEYS","MCHP","MU","NWS","Q","ROST",
    "SNPS","TPR","WDC","XYZ"
]

LOOKBACK_WINDOWS_DAYS = [90, 180, 365]
MAX_LOOKBACK_DAYS = max(LOOKBACK_WINDOWS_DAYS)
USER_AGENT = "Harshith Akurati Independent Research hakurati11@gmail.com"

OUT_DIR = Path("Stock Screening")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})
SESSION.verify = False

REQUEST_PAUSE_S = 0.15  # SEC asks for <=10 req/s; stay well under that


def get(url: str, retries: int = 5):
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(url, timeout=30)
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


def load_ticker_cik_map(tickers: list[str]) -> dict[str, str]:
    resp = get("https://www.sec.gov/files/company_tickers.json")
    data = resp.json()
    wanted = set(tickers)
    out = {}
    for row in data.values():
        t = row["ticker"].upper()
        if t in wanted:
            out[t] = str(row["cik_str"]).zfill(10)
    missing = wanted - out.keys()
    if missing:
        print(f"WARNING: no CIK found for: {sorted(missing)}")
    return out


def fetch_recent_form4_filings(cik: str, cutoff: datetime) -> list[dict]:
    """Return list of {accessionNumber, primaryDocument, filingDate} for Form 4 filings on/after cutoff."""
    resp = get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    data = resp.json()
    recent = data["filings"]["recent"]
    out = []
    for form, acc, doc, fdate in zip(recent["form"], recent["accessionNumber"],
                                       recent["primaryDocument"], recent["filingDate"]):
        if form != "4":
            continue
        fdate_dt = datetime.strptime(fdate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if fdate_dt < cutoff:
            continue
        out.append({"accessionNumber": acc, "primaryDocument": doc, "filingDate": fdate})
    return out


def _text(el, path, default=None):
    node = el.find(path)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def parse_form4_buys(xml_bytes: bytes) -> list[dict]:
    """Extract non-derivative PURCHASE (code 'P') transactions from a Form 4 XML doc."""
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
        if shares_txt is None or price_txt is None:
            continue
        try:
            shares = float(shares_txt)
            price = float(price_txt)
        except ValueError:
            continue
        buys.append({
            "insider_name": owner_name,
            "insider_cik": owner_cik,
            "transaction_date": date_txt,
            "shares": shares,
            "price": price,
            "dollar_value": shares * price,
        })
    return buys


def summarize_window(buys: list[dict], cutoff_date) -> dict:
    windowed = [b for b in buys if b["transaction_date_dt"] >= cutoff_date]
    n_txns = len(windowed)
    total_value = sum(b["dollar_value"] for b in windowed)
    n_insiders = len({b["insider_cik"] for b in windowed})
    return {
        "n_buy_transactions": n_txns,
        "total_buy_dollar_value": round(total_value, 2),
        "n_distinct_insiders_buying": n_insiders,
    }


def main():
    now = datetime.now(timezone.utc)
    max_cutoff = now - timedelta(days=MAX_LOOKBACK_DAYS)
    print(f"Pulling Form 4 buy transactions back to {max_cutoff.date()} "
          f"({MAX_LOOKBACK_DAYS}d) for {len(TICKERS)} tickers, "
          f"then bucketing into {LOOKBACK_WINDOWS_DAYS}-day windows...\n")

    cik_map = load_ticker_cik_map(TICKERS)

    rows = []
    all_buy_txns = []
    for ticker in TICKERS:
        cik = cik_map.get(ticker)
        if cik is None:
            print(f"[{ticker}] no CIK, skipping")
            row = {"ticker": ticker, "cik": None, "n_form4_filings_scanned": 0}
            for w in LOOKBACK_WINDOWS_DAYS:
                row.update({f"{k}_{w}d": v for k, v in
                             {"n_buy_transactions": 0, "total_buy_dollar_value": 0.0,
                              "n_distinct_insiders_buying": 0}.items()})
            rows.append(row)
            continue

        filings = fetch_recent_form4_filings(cik, max_cutoff)
        time.sleep(REQUEST_PAUSE_S)

        cik_int = int(cik)
        ticker_buys = []
        for f in filings:
            accession_nodash = f["accessionNumber"].replace("-", "")
            raw_filename = f["primaryDocument"].split("/")[-1]
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{raw_filename}"
            try:
                resp = get(doc_url)
            except Exception as e:
                print(f"  [{ticker}] failed to fetch {doc_url}: {e}")
                continue
            time.sleep(REQUEST_PAUSE_S)

            try:
                buys = parse_form4_buys(resp.content)
            except ET.ParseError as e:
                print(f"  [{ticker}] failed to parse {doc_url}: {e}")
                continue

            for b in buys:
                b["ticker"] = ticker
                b["accession"] = f["accessionNumber"]
                b["filing_date"] = f["filingDate"]
                b["transaction_date_dt"] = datetime.strptime(
                    b["transaction_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            ticker_buys.extend(buys)

        row = {"ticker": ticker, "cik": cik, "n_form4_filings_scanned": len(filings)}
        window_reports = []
        for w in LOOKBACK_WINDOWS_DAYS:
            cutoff = now - timedelta(days=w)
            stats = summarize_window(ticker_buys, cutoff)
            row.update({f"{k}_{w}d": v for k, v in stats.items()})
            window_reports.append(f"{w}d: {stats['n_buy_transactions']} txns / "
                                   f"${stats['total_buy_dollar_value']:,.0f} / "
                                   f"{stats['n_distinct_insiders_buying']} insiders")
        rows.append(row)
        all_buy_txns.extend(ticker_buys)

        print(f"[{ticker}] {len(filings)} Form 4 filings scanned ({MAX_LOOKBACK_DAYS}d)  |  " +
              "   ".join(window_reports))

    summary = pd.DataFrame(rows).sort_values("total_buy_dollar_value_365d", ascending=False)
    summary_path = OUT_DIR / "insider_buying_summary.csv"
    summary.to_csv(summary_path, index=False)

    if all_buy_txns:
        detail = pd.DataFrame(all_buy_txns).drop(columns=["transaction_date_dt"])
        detail_path = OUT_DIR / "insider_buying_transactions_detail.csv"
        detail.to_csv(detail_path, index=False)
        print(f"\nWrote transaction-level detail to: {detail_path}")

    print(f"\nWrote summary to: {summary_path}")
    print("\n--- Summary: buy transactions / $ value / distinct insiders, by window ---")
    display_cols = ["ticker"] + [f"{k}_{w}d" for w in LOOKBACK_WINDOWS_DAYS
                                  for k in ("n_buy_transactions", "total_buy_dollar_value", "n_distinct_insiders_buying")]
    print(summary[display_cols].to_string(index=False))


if __name__ == "__main__":
    main()
