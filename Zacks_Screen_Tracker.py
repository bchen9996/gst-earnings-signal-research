#!/usr/bin/env python3
# Zacks Screen Tracker — ingests a Zacks screener CSV export, timestamps it
# as a snapshot, appends it to a running history log, and (once at least
# two snapshots exist) reports what changed since the prior snapshot:
# tickers added, tickers dropped, and Zacks Rank / Analyst Recommendation
# changes for tickers present in both.
#
# On the very first run there is nothing to compare against — the import
# is simply recorded as the baseline and the change report is skipped.
# That's expected, not an error.
#
# *** HOW TO LOG A NEW EXPORT ***
# Export a new screen from Zacks, then update SOURCE_CSV below to point at
# the new file and re-run. Each run is idempotent for a given calendar day
# (re-running against the same source on the same day won't duplicate rows).
#
# Zacks export format handled: a few "Criteria" rows, a blank line, then a
# header row starting with "Selected,Company Name,Ticker,...". Percent
# columns (returns, dividend yield) are parsed to floats; blanks (e.g. a
# recent spinoff with no 52-week history) are kept as NaN, not dropped.
#
# Input : SOURCE_CSV (edit this path per run — see above)
# Output: Zacks Screen Tracker/snapshots/<DATE>_<source filename>
#         Zacks Screen Tracker/screen_history_log.csv   (append-only, long format)
#         Zacks Screen Tracker/change_report_<DATE>.csv  (only written when a prior snapshot exists)

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import shutil
import pandas as pd

# --- Edit this for each new export ---
SOURCE_CSV = Path(r"C:\Users\hakur\Downloads\screen_Screen_07_07_2026 (1).csv")

OUT_DIR = Path("Zacks Screen Tracker")
SNAPSHOT_DIR = OUT_DIR / "snapshots"
HISTORY_LOG_PATH = OUT_DIR / "screen_history_log.csv"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

PCT_COLS = [
    "Zacks Analyst Recommendation", "Zacks Rank",
    "1 Month Total Return %", "% Total Return YTD",
    "Relative Price Change % - 52 Weeks", "Relative Price Change % - YTD",
    "Dividend Yield",
]


def parse_zacks_export(path: Path) -> tuple[pd.DataFrame, list[str]]:
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()

    criteria_lines = []
    header_idx = None
    for i, line in enumerate(raw_lines):
        if line.startswith("Selected,Company Name,Ticker"):
            header_idx = i
            break
        if line.strip():
            criteria_lines.append(line.strip())

    if header_idx is None:
        raise ValueError(f"Could not find the 'Selected,Company Name,Ticker...' header row in {path}")

    df = pd.read_csv(path, skiprows=header_idx, encoding="utf-8-sig")
    df = df[df["Selected"].notna()].copy()

    for col in ["Zacks Analyst Recommendation", "Zacks Rank",
                "1 Month Total Return %", "% Total Return YTD",
                "Relative Price Change % - 52 Weeks", "Relative Price Change % - YTD",
                "Dividend Yield"]:
        if col in df.columns:
            df[col] = (df[col].astype(str).str.replace("%", "", regex=False)
                       .str.strip().replace({"": None, "nan": None}))
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df, criteria_lines


def build_change_report(prev: pd.DataFrame, curr: pd.DataFrame) -> dict:
    prev_tickers = set(prev["Ticker"])
    curr_tickers = set(curr["Ticker"])

    added = sorted(curr_tickers - prev_tickers)
    dropped = sorted(prev_tickers - curr_tickers)

    prev_idx = prev.set_index("Ticker")
    curr_idx = curr.set_index("Ticker")
    common = sorted(prev_tickers & curr_tickers)

    changes = []
    for t in common:
        p_rank, c_rank = prev_idx.loc[t, "Zacks Rank"], curr_idx.loc[t, "Zacks Rank"]
        p_rec, c_rec = prev_idx.loc[t, "Zacks Analyst Recommendation"], curr_idx.loc[t, "Zacks Analyst Recommendation"]
        if p_rank != c_rank or p_rec != c_rec:
            changes.append({
                "ticker": t, "prev_rank": p_rank, "curr_rank": c_rank,
                "prev_analyst_rec": p_rec, "curr_analyst_rec": c_rec,
            })

    return {"added": added, "dropped": dropped, "changed": changes, "unchanged_count": len(common) - len(changes)}


def main():
    if not SOURCE_CSV.exists():
        print(f"SOURCE_CSV not found: {SOURCE_CSV}\nEdit the SOURCE_CSV path at the top of this script and re-run.")
        return

    snapshot_date = datetime.now(timezone.utc).date().isoformat()
    imported_at = datetime.now(timezone.utc).isoformat()

    df, criteria_lines = parse_zacks_export(SOURCE_CSV)
    print(f"Parsed {len(df)} tickers from: {SOURCE_CSV.name}")
    print("Screen criteria:")
    for line in criteria_lines:
        print(f"  {line}")

    df.insert(0, "snapshot_date", snapshot_date)
    df["imported_at"] = imported_at
    df["source_file"] = SOURCE_CSV.name

    history = pd.DataFrame()
    if HISTORY_LOG_PATH.exists():
        history = pd.read_csv(HISTORY_LOG_PATH)

    already_logged_today = (not history.empty) and (snapshot_date in set(history["snapshot_date"].astype(str)))
    if already_logged_today:
        print(f"\nA snapshot for {snapshot_date} is already in the history log — "
              f"overwriting today's entries with this import (re-run of the same day).")
        history = history[history["snapshot_date"].astype(str) != snapshot_date]

    updated_history = pd.concat([history, df], ignore_index=True) if not history.empty else df
    updated_history.to_csv(HISTORY_LOG_PATH, index=False)

    snapshot_copy_path = SNAPSHOT_DIR / f"{snapshot_date}_{SOURCE_CSV.name}"
    shutil.copyfile(SOURCE_CSV, snapshot_copy_path)

    print(f"\nLogged snapshot for {snapshot_date} ({len(df)} tickers) to: {HISTORY_LOG_PATH}")
    print(f"Archived raw export to: {snapshot_copy_path}")

    prior_dates = sorted(set(history["snapshot_date"].astype(str))) if not history.empty else []
    prior_dates = [d for d in prior_dates if d != snapshot_date]

    if not prior_dates:
        print("\n--- No prior snapshot to compare against — this is the baseline. ---")
        print("Rank-change reporting will activate once a second export is logged.")
        return

    prior_date = prior_dates[-1]
    prev_df = history[history["snapshot_date"].astype(str) == prior_date]

    report = build_change_report(prev_df, df)

    print(f"\n--- Change report: {prior_date} -> {snapshot_date} ---")
    print(f"Added ({len(report['added'])}): {report['added'] if report['added'] else 'none'}")
    print(f"Dropped ({len(report['dropped'])}): {report['dropped'] if report['dropped'] else 'none'}")
    print(f"Unchanged: {report['unchanged_count']}")
    if report["changed"]:
        print(f"Rank/Recommendation changes ({len(report['changed'])}):")
        for c in report["changed"]:
            print(f"  {c['ticker']}: rank {c['prev_rank']}->{c['curr_rank']}, "
                  f"analyst rec {c['prev_analyst_rec']}->{c['curr_analyst_rec']}")
    else:
        print("Rank/Recommendation changes: none")

    report_rows = (
        [{"type": "added", "ticker": t} for t in report["added"]]
        + [{"type": "dropped", "ticker": t} for t in report["dropped"]]
        + [{"type": "changed", **c} for c in report["changed"]]
    )
    if report_rows:
        report_path = OUT_DIR / f"change_report_{snapshot_date}.csv"
        pd.DataFrame(report_rows).to_csv(report_path, index=False)
        print(f"\nWrote change report to: {report_path}")


if __name__ == "__main__":
    main()
