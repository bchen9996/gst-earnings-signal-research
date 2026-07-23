#!/usr/bin/env python3
# CANDIDATE B v1 FORWARD TRACKER — implements the mechanics locked in
# Live Signal Engine/CandidateB_v1_FORWARD_LOCKED.md. Runs AFTER
# GST_MultiTicker_Forward_Log.py each day (same daily job), reading that
# script's freshly-appended rows to:
#   1. Open new positions: any ticker whose z-score crosses 5 for the
#      first time this earnings cycle (while within_earnings_window) gets
#      a signal position opened (z>=10 or 5<=z<10 tier) using TODAY's
#      already-logged option-chain snapshot as the entry. Any ticker
#      newly entering its earnings window (days_to_earnings first reads
#      5) gets a PROVISIONAL control-candidate position opened the same
#      way, in case no signal ever fires this cycle.
#   2. Close positions: any OPEN position (signal or control-candidate)
#      whose target exit date is today gets closed using TODAY's
#      already-logged option-chain snapshot for the SAME contract
#      recorded at entry. A control-candidate that never saw a signal
#      fire becomes a finalized "control" position at this point; a
#      control-candidate that DID see a signal fire during its window
#      was already reclassified (see below) and closed as that signal
#      tier instead.
#   3. Reclassify: if a control-candidate position is still open when a
#      signal first crosses 5 for that ticker's SAME cycle, it is
#      RECLASSIFIED to the signal tier in place -- the entry snapshot
#      already recorded (from window-entry day) is replaced with the
#      signal day's entry snapshot, per the locked entry rule (signal
#      groups enter when the signal is observed, not on window-entry
#      day). This can only happen once per cycle (first crossing wins).
#
# State: Live Signal Engine/CandidateB_v1_OpenPositions.csv (positions not
# yet closed -- committed back to the repo each run, so state persists
# across GitHub Actions runs, which are otherwise stateless).
# Results: Live Signal Engine/CandidateB_v1_ForwardResults.csv (closed
# positions, append-only, one row per resolved event).
#
# NOTE ON DUPLICATE-CYCLE PROTECTION: a ticker only gets ONE position per
# earnings cycle. "Cycle" is identified by the fetched next_earnings_date
# -- a new position is only opened if no OPEN or CLOSED position already
# exists for that (ticker, earnings_date) pair.

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

LOG_PATH = Path("Live Signal Engine") / "MultiTicker_Forward_Log.csv"
OPEN_PATH = Path("Live Signal Engine") / "CandidateB_v1_OpenPositions.csv"
RESULTS_PATH = Path("Live Signal Engine") / "CandidateB_v1_ForwardResults.csv"

HIGH_CONFIDENCE_Z_THRESHOLD = 10.0
SIGNAL_Z_THRESHOLD = 5.0

FEE_PER_CONTRACT_USD = 0.65
FEE_LEGS = 4
FEES_IN_QUOTE_UNITS = (FEE_PER_CONTRACT_USD * FEE_LEGS) / 100.0
FILL_PENALTY_PCT = 2.0   # entry cost inflated 2%, exit value reduced 2% -- see CandidateB_v1_FORWARD_LOCKED.md section 4

FLAT_POSITION_SIZE = 10_000.0

OPEN_COLUMNS = [
    "ticker", "earnings_date", "group", "status",
    "entry_run_date", "entry_zscore", "entry_call_bid", "entry_call_ask",
    "entry_put_bid", "entry_put_ask", "entry_spot", "entry_expiry",
    "target_exit_date", "note",
]


def load_open_positions() -> pd.DataFrame:
    if OPEN_PATH.exists():
        df = pd.read_csv(OPEN_PATH)
        for c in ["earnings_date", "entry_run_date", "target_exit_date"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
        return df
    return pd.DataFrame(columns=OPEN_COLUMNS)


def save_open_positions(df: pd.DataFrame) -> None:
    OPEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OPEN_PATH, index=False)


def append_result(row: dict) -> None:
    df = pd.DataFrame([row])
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RESULTS_PATH.exists():
        df.to_csv(RESULTS_PATH, mode="a", header=False, index=False)
    else:
        df.to_csv(RESULTS_PATH, mode="w", header=True, index=False)


def compute_target_exit_date(earnings_date: date, _unused=None) -> date:
    """Last trading day before earnings_date: simple weekday-skip rule (no
    US market-holiday calendar lookup -- a disclosed simplification, same
    one already used throughout this project, e.g. GST_MSFT_Forward_Quote_Log.py's
    trading_days_between()). Deliberately does NOT try to derive this from
    MultiTicker_Forward_Log.csv's own accumulated history -- that history
    only covers PAST dates, and earnings_date is typically a few days in
    the FUTURE relative to when a position opens, so no log data reaching
    that far exists yet. An earlier version of this function tried the
    log-history approach and always returned "today" as a result -- fixed
    2026-07-19 during smoke-testing, before any real position was tracked."""
    d = earnings_date - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def main():
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    print(f"*** CANDIDATE B v1 FORWARD TRACKER -- run at {now_utc.isoformat()} ***\n")

    if not LOG_PATH.exists():
        print("MultiTicker_Forward_Log.csv does not exist yet -- nothing to do.")
        return

    full_log = pd.read_csv(LOG_PATH)
    full_log["run_date_et"] = pd.to_datetime(full_log["run_date_et"], errors="coerce").dt.date
    todays_log = full_log[full_log["run_date_et"] == today].copy()
    if todays_log.empty:
        print(f"No log rows found for today ({today.isoformat()}) -- run "
              f"GST_MultiTicker_Forward_Log.py first. Nothing to do.")
        return
    print(f"Today's log rows: {len(todays_log)}\n")

    open_positions = load_open_positions()
    closed_this_run = []

    # --- Step 1: close any position whose target exit date is today (or has passed) ---
    still_open_rows = []
    for _, pos in open_positions.iterrows():
        if pos["status"] == "open" and pos["target_exit_date"] is not None and pos["target_exit_date"] <= today:
            match = todays_log[todays_log["ticker"] == pos["ticker"]]
            if match.empty:
                print(f"  [{pos['ticker']}] target exit date reached but no log row today -- leaving open, will retry.")
                still_open_rows.append(pos)
                continue
            exit_row = match.iloc[-1]   # most recent matching row, in case of any same-day duplicates
            exit_call_bid, exit_put_bid = exit_row.get("call_bid"), exit_row.get("put_bid")
            if pd.isna(exit_call_bid) or pd.isna(exit_put_bid):
                print(f"  [{pos['ticker']}] exit reached but no real bid quote today "
                      f"(option chain not captured -- outside earnings window or pull failed). Leaving open.")
                still_open_rows.append(pos)
                continue

            entry_cost = (pos["entry_call_ask"] + pos["entry_put_ask"]) * (1 + FILL_PENALTY_PCT / 100.0)
            exit_value = (exit_call_bid + exit_put_bid) * (1 - FILL_PENALTY_PCT / 100.0)
            real_pnl_pct = (exit_value - entry_cost - FEES_IN_QUOTE_UNITS) / entry_cost * 100
            dollar_pnl = FLAT_POSITION_SIZE * (real_pnl_pct / 100.0)

            # A "control-candidate" that reaches its target exit date without ever
            # being reclassified (Step 2 would have converted it to a signal tier
            # if a signal had fired) is, by definition, a genuine control -- finalize
            # the label at the point of closing, not via a separate later date check.
            final_group = "control" if pos["group"] == "control-candidate" else pos["group"]

            result_row = {
                "ticker": pos["ticker"], "earnings_date": pos["earnings_date"], "group": final_group,
                "entry_run_date": pos["entry_run_date"], "entry_zscore": pos["entry_zscore"],
                "exit_run_date": today.isoformat(),
                "entry_call_ask": pos["entry_call_ask"], "entry_put_ask": pos["entry_put_ask"],
                "exit_call_bid": exit_call_bid, "exit_put_bid": exit_put_bid,
                "real_pnl_pct": round(real_pnl_pct, 2), "dollar_pnl": round(dollar_pnl, 2),
                "win": bool(real_pnl_pct > 0),
            }
            append_result(result_row)
            closed_this_run.append(result_row)
            print(f"  [{pos['ticker']}] CLOSED ({pos['group']}): real_pnl={real_pnl_pct:.1f}%  ${dollar_pnl:,.0f}")
        else:
            still_open_rows.append(pos)

    open_positions = pd.DataFrame(still_open_rows, columns=OPEN_COLUMNS) if still_open_rows else \
        pd.DataFrame(columns=OPEN_COLUMNS)

    # --- Step 2: reclassify open control-candidates if a signal fires today, and open new positions ---
    existing_keys = set(zip(open_positions["ticker"], open_positions["earnings_date"])) if not open_positions.empty else set()
    if RESULTS_PATH.exists():
        closed_keys_df = pd.read_csv(RESULTS_PATH)
        closed_keys_df["earnings_date"] = pd.to_datetime(closed_keys_df["earnings_date"], errors="coerce").dt.date
        existing_keys |= set(zip(closed_keys_df["ticker"], closed_keys_df["earnings_date"]))

    new_rows = []
    for _, log_row in todays_log.iterrows():
        ticker = log_row["ticker"]
        earnings_date_str = log_row.get("next_earnings_date")
        if pd.isna(earnings_date_str):
            continue
        earnings_date = pd.to_datetime(earnings_date_str).date()
        zscore = log_row.get("gst_zscore")
        within_window = bool(log_row.get("within_earnings_window"))
        days_to_earnings = log_row.get("days_to_next_earnings")

        has_entry_quotes = pd.notna(log_row.get("call_ask")) and pd.notna(log_row.get("put_ask"))

        is_signal_today = within_window and pd.notna(zscore) and zscore >= SIGNAL_Z_THRESHOLD and has_entry_quotes
        group_today = None
        if is_signal_today:
            group_today = "z>=10" if zscore >= HIGH_CONFIDENCE_Z_THRESHOLD else "5<=z<10"

        # Reclassify an open control-candidate for this exact cycle if a signal fires today
        existing_mask = (open_positions["ticker"] == ticker) & (open_positions["earnings_date"] == earnings_date) \
            if not open_positions.empty else pd.Series([], dtype=bool)
        already_open = existing_mask.any() if not open_positions.empty else False

        if is_signal_today and already_open:
            idx = open_positions[existing_mask].index
            if (open_positions.loc[idx, "group"] == "control-candidate").all():
                target_exit = compute_target_exit_date(earnings_date)
                open_positions.loc[idx, ["group", "entry_run_date", "entry_zscore",
                                          "entry_call_ask", "entry_call_bid", "entry_put_ask", "entry_put_bid",
                                          "entry_spot", "target_exit_date", "note"]] = [
                    group_today, today.isoformat(), zscore,
                    log_row.get("call_ask"), log_row.get("call_bid"), log_row.get("put_ask"), log_row.get("put_bid"),
                    log_row.get("underlying_price"), target_exit,
                    "reclassified from control-candidate: signal fired mid-window",
                ]
                print(f"  [{ticker}] RECLASSIFIED control-candidate -> {group_today} (z={zscore})")
            continue

        if (ticker, earnings_date) in existing_keys or already_open:
            continue

        if is_signal_today:
            target_exit = compute_target_exit_date(earnings_date)
            new_rows.append({
                "ticker": ticker, "earnings_date": earnings_date, "group": group_today, "status": "open",
                "entry_run_date": today.isoformat(), "entry_zscore": zscore,
                "entry_call_bid": log_row.get("call_bid"), "entry_call_ask": log_row.get("call_ask"),
                "entry_put_bid": log_row.get("put_bid"), "entry_put_ask": log_row.get("put_ask"),
                "entry_spot": log_row.get("underlying_price"), "entry_expiry": log_row.get("nearest_post_earnings_expiry"),
                "target_exit_date": target_exit, "note": "",
            })
            print(f"  [{ticker}] OPENED new {group_today} position (z={zscore})")
        elif days_to_earnings == 5 and has_entry_quotes:
            target_exit = compute_target_exit_date(earnings_date)
            new_rows.append({
                "ticker": ticker, "earnings_date": earnings_date, "group": "control-candidate", "status": "open",
                "entry_run_date": today.isoformat(), "entry_zscore": zscore,
                "entry_call_bid": log_row.get("call_bid"), "entry_call_ask": log_row.get("call_ask"),
                "entry_put_bid": log_row.get("put_bid"), "entry_put_ask": log_row.get("put_ask"),
                "entry_spot": log_row.get("underlying_price"), "entry_expiry": log_row.get("nearest_post_earnings_expiry"),
                "target_exit_date": target_exit, "note": "provisional control -- becomes final control if no signal fires this cycle",
            })
            print(f"  [{ticker}] OPENED control-candidate position (window entry, z={zscore})")

    if new_rows:
        open_positions = pd.concat([open_positions, pd.DataFrame(new_rows)], ignore_index=True)

    save_open_positions(open_positions)

    print(f"\nOpen positions: {len(open_positions)}   Closed this run: {len(closed_this_run)}")
    print(f"State: {OPEN_PATH}")
    print(f"Results: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
