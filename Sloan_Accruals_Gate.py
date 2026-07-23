#!/usr/bin/env python3
# Stock Screening Pipeline — Step 2: Sloan (1996) accruals quality gate.
#
# Pulls company XBRL "facts" from SEC's companyfacts API for the same 26
# tickers and computes the balance-sheet version of the Sloan accruals
# ratio over the most recent fiscal year (as specified):
#
#   Accruals = (delta Non-Cash Current Assets
#               - delta Current Liabilities excl. debt
#               - Depreciation) / Average Total Assets
#
# where:
#   Non-Cash Current Assets       = Current Assets - Cash & Cash Equivalents
#   Current Liabilities excl debt = Current Liabilities - current portion of debt
#   Average Total Assets          = (Total Assets_t + Total Assets_t-1) / 2
#
# This is a per-firm screen, not Sloan's original decile-portfolio design.
# A fixed absolute cutoff (accruals ratio >= 0.10) was tried first and found
# NOTHING in this universe — every ticker with data came in below it. That's
# likely because this universe is already pre-filtered on Zacks Rank=1 +
# Analyst Recommendation=1, which probably selects against aggressive-accrual
# names before this script ever sees them, leaving little room for an
# absolute threshold to bite.
#
# So the flag here is RELATIVE instead: rank the tickers with valid data by
# accruals ratio and flag the top quartile (highest/most positive — i.e. most
# aggressive/least conservative accruals) as CAUTION. This is a soft flag for
# Step 3, not a hard exclusion — high positive accruals are the direction
# Sloan's finding says to worry about (earnings propped up by non-cash/
# working-capital effects); very negative accruals are never flagged.
#
# BEN (Franklin Resources) is EXCLUDED from this gate entirely, not scored
# PASS/FAIL/CAUTION: as an asset manager it doesn't file a classified balance
# sheet (no current/non-current split), so AssetsCurrent/LiabilitiesCurrent
# don't exist in its XBRL facts. That's a structural feature of financial-
# sector filers, not a data gap, so it's called out explicitly rather than
# silently dropped or scored on missing pieces.
#
# XBRL tag naming is NOT standardized across filers (e.g. some report
# "DebtCurrent", others split "LongTermDebtCurrent" / "ShortTermBorrowings";
# some report a combined "DepreciationAndAmortization", others split
# "Depreciation" + "AmortizationOfIntangibleAssets", and some stop using a
# tag entirely mid-history). Each line item below tries a fallback list of
# tags in priority order and records which tag was actually used per
# ticker, for the same transparency as Step 1.
#
# Output: Stock Screening/sloan_accruals_summary.csv

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
import time
import requests
import urllib3
import pandas as pd

urllib3.disable_warnings()

TICKERS = [
    "ADI","ALB","AMAT","AXON","BEN","CIEN","COHR","CSCO","DELL","EME","F",
    "FLEX","FOXA","HPE","INTC","JBL","KEYS","MCHP","MU","NWS","Q","ROST",
    "SNPS","TPR","WDC","XYZ"
]

USER_AGENT = "Harshith Akurati Independent Research hakurati11@gmail.com"
OUT_DIR = Path("Stock Screening")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})
SESSION.verify = False
REQUEST_PAUSE_S = 0.15

CASH_TAGS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "CashCashEquivalentsAndShortTermInvestments",
    "Cash",
]
DEBT_CURRENT_TAGS = [
    "DebtCurrent",
    "LongTermDebtCurrent",
    "ShortTermBorrowings",
    "NotesPayableCurrent",
    "CommercialPaper",
]
DEPRECIATION_COMBINED_TAGS = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
]


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


def get_usd_units(facts: dict, tag: str) -> list[dict]:
    try:
        return facts["facts"]["us-gaap"][tag]["units"]["USD"]
    except KeyError:
        return []


def instant_series(entries: list[dict]) -> dict[str, float]:
    """end_date -> val, 10-K/10-K/A only."""
    out = {}
    for e in entries:
        if not e.get("form", "").startswith("10-K"):
            continue
        end, val = e.get("end"), e.get("val")
        if end is None or val is None:
            continue
        out.setdefault(end, val)
    return out


def pick_first_available_instant(facts: dict, tags: list[str], end_date: str):
    for tag in tags:
        series = instant_series(get_usd_units(facts, tag))
        if end_date in series:
            return series[end_date], tag
    return None, None


def annual_duration_value(facts: dict, tag: str, end_date: str):
    """Value for `tag` covering a ~1-year period ending exactly at end_date."""
    for e in get_usd_units(facts, tag):
        if not e.get("form", "").startswith("10-K"):
            continue
        if e.get("end") != end_date:
            continue
        start = e.get("start")
        if not start:
            continue
        days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days
        if 340 <= days <= 386:
            return e.get("val")
    return None


def pick_depreciation(facts: dict, end_date: str):
    for tag in DEPRECIATION_COMBINED_TAGS:
        val = annual_duration_value(facts, tag, end_date)
        if val is not None:
            return val, tag
    dep = annual_duration_value(facts, "Depreciation", end_date)
    amort = annual_duration_value(facts, "AmortizationOfIntangibleAssets", end_date)
    if dep is not None or amort is not None:
        used = "+".join(t for t, v in [("Depreciation", dep), ("AmortizationOfIntangibleAssets", amort)] if v is not None)
        return (dep or 0) + (amort or 0), used
    return None, None


def compute_accruals(ticker: str, cik: str) -> dict:
    row = {"ticker": ticker, "cik": cik}
    try:
        resp = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    except Exception as e:
        row["notes"] = f"companyfacts fetch failed: {e}"
        return row

    facts = resp.json()

    assets_series = instant_series(get_usd_units(facts, "Assets"))
    ends_sorted = sorted(assets_series.keys(), reverse=True)
    if len(ends_sorted) < 2:
        row["notes"] = "fewer than 2 annual Assets data points available"
        return row

    curr_end, prior_end = ends_sorted[0], ends_sorted[1]
    total_assets_curr = assets_series[curr_end]
    total_assets_prior = assets_series[prior_end]
    avg_total_assets = (total_assets_curr + total_assets_prior) / 2

    ca_curr, _ = pick_first_available_instant(facts, ["AssetsCurrent"], curr_end)
    ca_prior, _ = pick_first_available_instant(facts, ["AssetsCurrent"], prior_end)
    cash_curr, cash_tag = pick_first_available_instant(facts, CASH_TAGS, curr_end)
    cash_prior, _ = pick_first_available_instant(facts, CASH_TAGS, prior_end)
    cl_curr, _ = pick_first_available_instant(facts, ["LiabilitiesCurrent"], curr_end)
    cl_prior, _ = pick_first_available_instant(facts, ["LiabilitiesCurrent"], prior_end)
    debt_curr, debt_tag = pick_first_available_instant(facts, DEBT_CURRENT_TAGS, curr_end)
    debt_prior, _ = pick_first_available_instant(facts, DEBT_CURRENT_TAGS, prior_end)
    dep, dep_tag = pick_depreciation(facts, curr_end)

    debt_curr_used = debt_curr if debt_curr is not None else 0.0
    debt_prior_used = debt_prior if debt_prior is not None else 0.0
    debt_tag_note = debt_tag if debt_tag is not None else "none_found_assumed_zero"

    missing = []
    if ca_curr is None or ca_prior is None:
        missing.append("AssetsCurrent")
    if cash_curr is None or cash_prior is None:
        missing.append("Cash")
    if cl_curr is None or cl_prior is None:
        missing.append("LiabilitiesCurrent")
    if dep is None:
        missing.append("Depreciation")

    row.update({
        "curr_fy_end": curr_end,
        "prior_fy_end": prior_end,
        "total_assets_curr": total_assets_curr,
        "total_assets_prior": total_assets_prior,
        "avg_total_assets": round(avg_total_assets, 2),
        "current_assets_curr": ca_curr,
        "current_assets_prior": ca_prior,
        "cash_curr": cash_curr,
        "cash_prior": cash_prior,
        "current_liab_curr": cl_curr,
        "current_liab_prior": cl_prior,
        "debt_current_curr": debt_curr_used,
        "debt_current_prior": debt_prior_used,
        "depreciation": dep,
        "cash_tag_used": cash_tag,
        "debt_tag_used": debt_tag_note,
        "depreciation_tag_used": dep_tag,
    })

    if "AssetsCurrent" in missing and "LiabilitiesCurrent" in missing:
        row["notes"] = ("excluded from Sloan gate — no classified balance sheet "
                         "(structural feature of financial-sector filers, not missing data)")
        row["accruals_ratio"] = None
        row["quality_flag"] = "EXCLUDED — financial sector structure"
        return row

    if missing:
        row["notes"] = "missing data: " + ", ".join(missing)
        row["accruals_ratio"] = None
        row["quality_flag"] = "NO DATA"
        return row

    non_cash_ca_curr = ca_curr - cash_curr
    non_cash_ca_prior = ca_prior - cash_prior
    delta_non_cash_ca = non_cash_ca_curr - non_cash_ca_prior

    cl_excl_debt_curr = cl_curr - debt_curr_used
    cl_excl_debt_prior = cl_prior - debt_prior_used
    delta_cl_excl_debt = cl_excl_debt_curr - cl_excl_debt_prior

    accruals = (delta_non_cash_ca - delta_cl_excl_debt - dep) / avg_total_assets

    row["delta_non_cash_current_assets"] = round(delta_non_cash_ca, 2)
    row["delta_current_liab_excl_debt"] = round(delta_cl_excl_debt, 2)
    row["accruals_ratio"] = round(accruals, 4)
    row["quality_flag"] = None  # assigned after all tickers are in, relative to the group
    row["notes"] = ""
    return row


def main():
    print(f"Computing Sloan accruals ratio for {len(TICKERS)} tickers "
          f"(relative flag: top quartile of accruals ratio = CAUTION, not a hard exclusion)...\n")

    cik_map = load_ticker_cik_map(TICKERS)

    rows = []
    for ticker in TICKERS:
        cik = cik_map.get(ticker)
        if cik is None:
            rows.append({"ticker": ticker, "cik": None, "notes": "no CIK found",
                         "accruals_ratio": None, "quality_flag": "NO DATA"})
            print(f"[{ticker}] no CIK found, skipping")
            continue

        row = compute_accruals(ticker, cik)
        time.sleep(REQUEST_PAUSE_S)
        rows.append(row)

        if row.get("accruals_ratio") is not None:
            print(f"[{ticker}] FY end {row['curr_fy_end']}: accruals ratio = {row['accruals_ratio']:+.4f} "
                  f"(dep tag: {row['depreciation_tag_used']}, debt tag: {row['debt_tag_used']})")
        else:
            print(f"[{ticker}] {row.get('notes', 'no data')} -> {row.get('quality_flag')}")

    summary = pd.DataFrame(rows)

    # Relative top-quartile CAUTION flag, computed only over tickers with a
    # real accruals ratio (excludes BEN and any NO DATA/no-CIK rows).
    valid_mask = summary["accruals_ratio"].notna()
    q75 = summary.loc[valid_mask, "accruals_ratio"].quantile(0.75)
    summary.loc[valid_mask, "quality_flag"] = summary.loc[valid_mask, "accruals_ratio"].apply(
        lambda x: "CAUTION (top quartile — most aggressive accruals)" if x >= q75 else "OK"
    )
    print(f"\nTop-quartile cutoff (75th percentile of accruals ratio among {valid_mask.sum()} valid tickers): "
          f"{q75:+.4f}")

    col_order = [
        "ticker", "cik", "curr_fy_end", "prior_fy_end",
        "total_assets_curr", "total_assets_prior", "avg_total_assets",
        "current_assets_curr", "current_assets_prior", "cash_curr", "cash_prior",
        "current_liab_curr", "current_liab_prior", "debt_current_curr", "debt_current_prior",
        "depreciation", "delta_non_cash_current_assets", "delta_current_liab_excl_debt",
        "accruals_ratio", "quality_flag",
        "cash_tag_used", "debt_tag_used", "depreciation_tag_used", "notes",
    ]
    for c in col_order:
        if c not in summary.columns:
            summary[c] = None
    summary = summary[col_order].sort_values("accruals_ratio", ascending=True, na_position="last")

    summary_path = OUT_DIR / "sloan_accruals_summary.csv"
    summary.to_csv(summary_path, index=False)

    print(f"\nWrote summary to: {summary_path}")
    print("\n--- All 26 tickers, sorted by accruals ratio (most conservative first) ---")
    print(summary[["ticker", "curr_fy_end", "accruals_ratio", "quality_flag", "notes"]].to_string(index=False))


if __name__ == "__main__":
    main()
