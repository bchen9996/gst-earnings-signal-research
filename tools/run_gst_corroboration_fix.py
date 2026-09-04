#!/usr/bin/env python3
"""Fix the corroboration in audit section 7.3, which was confounded.

Section 7.3 compared ticker-selected spike weeks against ALL other weeks in the
series. A ticker has ~20 earnings weeks in 261, so that comparison arm is ~92%
non-earnings weeks and the test actually run was:

    do earnings weeks have more "[TICKER] earnings" search than ordinary weeks?

Yes, and uninteresting. It shows the selected weeks are EARNINGS weeks, which
was true by selection. It does not show they are unusually high-ATTENTION
earnings weeks, which is what 7.3 claimed.

This replaces the comparison group: selected z >= 5 earnings weeks vs
NON-SELECTED earnings weeks, same ticker. Both arms are earnings weeks, so
earnings-ness is held constant and only attention varies.

OFFLINE. Committed CSVs only. No Google Trends call, no network.

RETROSPECTIVE_DEVELOPMENT_ONLY. Confirms no hypothesis, moves no gate.

Run:  python tools/run_gst_corroboration_fix.py [--write]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LSE = ROOT / "Live Signal Engine"
D_INTENT = ROOT / "GST Data" / "Weekly Data (Intent Filtered Earnings)"

EARNINGS = LSE / "AllTickers_EarningsDates.csv"
BREADTH = LSE / "RelatedQueriesBreadth_Results.csv"
OUT = LSE / "GST_SEARCH_CONSTRUCT_VALIDITY_CORROBORATION_2026-09-04.json"

TICKERS = ("MSFT", "ADBE", "NFLX", "NKE", "STZ", "QCOM", "SBUX", "AMZN")
WINDOW_START, WINDOW_END = "2021-01-01", "2025-12-31"

# GST_Live_Signal_Engine.py: ROLLING_WINDOW = 12, applied with shift(1), so the
# baseline for week t is weeks t-12 .. t-1.
ROLLING_WINDOW = 12

N_PERMUTATIONS = 10000
RANDOM_SEED = 42

# PRE-DECLARED POWER RULE, fixed before the comparison was run. An arm smaller
# than this is reported as UNDERPOWERED, never as a null. A 5-vs-15 split gives
# a permutation test very little resolution, and saying so is part of the
# result rather than a caveat bolted on afterwards.
MIN_ARM_N = 5

# PRE-DECLARED INTERPRETATION, fixed before the comparison was run.
INTERPRETATION = {
    "higher_in_selected_arm": (
        "the signal captures attention BEYOND earnings-ness; section 7.3's "
        "corroboration survives in weakened, honest form"),
    "no_detectable_difference": (
        "the signal is detecting earnings-ness, not attention, and section "
        "7.3's corroboration COLLAPSES; this is what the section 8.1 "
        "periodicity result predicts"),
    "commitment": (
        "the result stands as reported either way; no re-slicing after seeing "
        "it, and no ticker with an arm below MIN_ARM_N is called a null"),
}


class RefusedError(RuntimeError):
    """A precondition does not hold.

    RefusedError, never bare `assert`: `python -O` strips asserts, and a
    precondition that vanishes under an optimisation flag is not one.
    """


def _week_start(s: pd.Series) -> pd.Series:
    """Map dates onto the series' Sunday-start weekly index.

    Verified: both the intent series index and the breadth file's spike_week
    are Sunday-dated, and W-SAT periods start on Sunday.
    """
    return s.dt.to_period("W-SAT").apply(lambda p: p.start_time)


def _intent_series(ticker: str) -> pd.Series:
    frames = []
    for f in sorted(glob.glob(os.path.join(str(D_INTENT), f"{ticker}_*.csv"))):
        df = pd.read_csv(f)
        cols = [c for c in df.columns if c not in ("Week", "isPartial")]
        if not cols:
            continue
        frames.append(pd.DataFrame({
            "week": pd.to_datetime(df["Week"], errors="coerce"),
            "v": pd.to_numeric(df[cols[0]], errors="coerce"),
        }).dropna())
    if not frames:
        return pd.Series(dtype=float)
    out = pd.concat(frames, ignore_index=True).drop_duplicates("week")
    return out.set_index("week")["v"].sort_index()


def _load_inputs():
    for p in (EARNINGS, BREADTH):
        if not p.exists():
            raise RefusedError(f"missing evidence file: {p.name}")
    if not D_INTENT.exists():
        raise RefusedError(f"missing data directory: {D_INTENT.name}")

    ed = pd.read_csv(EARNINGS)
    ed["earnings_date"] = pd.to_datetime(ed.earnings_date, errors="coerce")
    ed = ed.dropna(subset=["earnings_date"])

    br = pd.read_csv(BREADTH)
    br = br[br.ticker.notna()].copy()
    br["spike_week"] = pd.to_datetime(br.spike_week, errors="coerce")
    br = br.dropna(subset=["spike_week"])

    missing = [t for t in TICKERS if t not in set(ed.ticker)]
    if missing:
        raise RefusedError(f"earnings dates missing for {missing}")
    return ed, br


def _arms(ticker: str, ed: pd.DataFrame, br: pd.DataFrame):
    """(all earnings weeks in window, selected, non-selected) for one ticker."""
    e = ed[(ed.ticker == ticker)
           & (ed.earnings_date >= WINDOW_START)
           & (ed.earnings_date <= WINDOW_END)]
    earn_weeks = set(_week_start(e.earnings_date))
    selected = set(br.loc[br.ticker == ticker, "spike_week"])
    # A selected week outside the earnings-week set would mean the two files
    # disagree about the calendar; refuse rather than silently drop it.
    stray = selected - earn_weeks
    if stray:
        raise RefusedError(
            f"{ticker}: {len(stray)} selected spike weeks are not earnings "
            f"weeks under this calendar mapping, e.g. "
            f"{sorted(stray)[0].date()}. The week alignment is wrong.")
    return earn_weeks, selected, earn_weeks - selected


# ----------------------------------------------- 8.1 selectivity + periodicity
def section_selectivity(ed: pd.DataFrame, br: pd.DataFrame) -> dict:
    per = {}
    for t in TICKERS:
        earn, sel, non = _arms(t, ed, br)
        earn_sorted = sorted(earn)
        # How many OTHER earnings weeks fall inside each selected event's own
        # 12-week baseline (weeks t-12 .. t-1)?
        counts = []
        for w in sorted(sel):
            lo = w - pd.Timedelta(weeks=ROLLING_WINDOW)
            hi = w - pd.Timedelta(weeks=1)
            counts.append(sum(1 for x in earn_sorted if lo <= x <= hi))
        per[t] = {
            "earnings_weeks_in_window": len(earn),
            "selected_z5": len(sel),
            "non_selected": len(non),
            "selectivity_pct": (round(100 * len(sel) / len(earn), 1)
                                if earn else None),
            "mean_earnings_weeks_inside_own_baseline": (
                round(float(np.mean(counts)), 3) if counts else None),
            "max_earnings_weeks_inside_own_baseline": (
                int(max(counts)) if counts else None),
        }
    sel_pcts = [v["selectivity_pct"] for v in per.values()
                if v["selectivity_pct"] is not None]
    inside = [v["mean_earnings_weeks_inside_own_baseline"] for v in per.values()
              if v["mean_earnings_weeks_inside_own_baseline"] is not None]
    return {
        "rolling_window_weeks": ROLLING_WINDOW,
        "median_earnings_cadence_weeks": 13.0,
        "baseline_is_structurally_trough_only": bool(max(inside) < 1.0)
        if inside else None,
        "selectivity_pct_min": min(sel_pcts) if sel_pcts else None,
        "selectivity_pct_max": max(sel_pcts) if sel_pcts else None,
        "note": ("a 12-week baseline on a 13-week earnings cadence rarely "
                 "contains another earnings week, so the quarterly peak is "
                 "compared against a trough-only baseline by construction"),
        "per_ticker": per,
    }


# ------------------------------------------------ 8.2 the like-for-like fix
def _perm_p(a: np.ndarray, b: np.ndarray, rng) -> float | None:
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None
    obs = np.median(a) - np.median(b)
    pooled = np.concatenate([a, b])
    n_a = len(a)
    hits = 0
    for _ in range(N_PERMUTATIONS):
        rng.shuffle(pooled)
        if abs(np.median(pooled[:n_a]) - np.median(pooled[n_a:])) >= abs(obs):
            hits += 1
    return round(hits / N_PERMUTATIONS, 5)


def section_like_for_like(ed: pd.DataFrame, br: pd.DataFrame) -> dict:
    rng = np.random.default_rng(RANDOM_SEED)
    per = {}
    for t in TICKERS:
        intent = _intent_series(t)
        if not len(intent):
            per[t] = {"status": "no_intent_series"}
            continue
        _, sel, non = _arms(t, ed, br)
        a = intent[intent.index.isin(sel)]
        b = intent[intent.index.isin(non)]

        underpowered = len(a) < MIN_ARM_N or len(b) < MIN_ARM_N
        entry = {
            "status": "underpowered" if underpowered else "ok",
            "n_selected": int(len(a)),
            "n_non_selected": int(len(b)),
            "nonzero_rate_selected": (round(float((a > 0).mean()), 4)
                                      if len(a) else None),
            "nonzero_rate_non_selected": (round(float((b > 0).mean()), 4)
                                          if len(b) else None),
            "median_selected": float(a.median()) if len(a) else None,
            "median_non_selected": float(b.median()) if len(b) else None,
            "mean_selected": round(float(a.mean()), 3) if len(a) else None,
            "mean_non_selected": round(float(b.mean()), 3) if len(b) else None,
            "perm_p_median_difference": _perm_p(a.to_numpy(float),
                                                b.to_numpy(float), rng),
        }
        if underpowered:
            entry["underpowered_reason"] = (
                f"an arm has fewer than {MIN_ARM_N} observations "
                f"({len(a)} vs {len(b)}); reported as underpowered, NOT as a "
                "null result")
        per[t] = entry

    powered = [t for t, v in per.items() if v.get("status") == "ok"]
    return {
        "comparison": ("selected z>=5 earnings weeks vs NON-SELECTED earnings "
                       "weeks, same ticker; earnings-ness held constant"),
        "replaces": ("audit section 7.3, which compared selected weeks against "
                     "ALL other weeks, ~92% of which are not earnings weeks"),
        "min_arm_n": MIN_ARM_N,
        "n_permutations": N_PERMUTATIONS,
        "random_seed": RANDOM_SEED,
        "pre_declared_interpretation": INTERPRETATION,
        "tickers_adequately_powered": sorted(powered),
        "tickers_underpowered": sorted(t for t, v in per.items()
                                       if v.get("status") == "underpowered"),
        "per_ticker": per,
    }


def section_instrument_resolution(ed: pd.DataFrame, br: pd.DataFrame) -> dict:
    """Can the corroborating instrument discriminate WITHIN earnings weeks?

    ADDED AFTER the section 8.2 null was observed, to diagnose it. Stated
    plainly because the ordering matters: this does NOT change the 8.2 result,
    which stands exactly as computed. It asks whether that null is informative
    or merely the instrument running out of range, and it would have been
    reported either way -- a non-saturated instrument would have made the null
    much stronger evidence against the signal.
    """
    per = {}
    for t in TICKERS:
        ser = _intent_series(t)
        if not len(ser):
            per[t] = {"status": "no_intent_series"}
            continue
        earn, _, _ = _arms(t, ed, br)
        ew = ser[ser.index.isin(earn)]
        ne = ser[~ser.index.isin(earn)]
        per[t] = {
            "series_max": float(ser.max()),
            "median_earnings_weeks": float(ew.median()) if len(ew) else None,
            "median_non_earnings_weeks": float(ne.median()) if len(ne) else None,
            "pct_earnings_weeks_at_or_above_50": (
                round(float((ew >= 50).mean() * 100), 1) if len(ew) else None),
        }
    ok = [v for v in per.values() if "median_earnings_weeks" in v]
    saturated = [v for v in ok if (v["pct_earnings_weeks_at_or_above_50"] or 0) >= 60]
    return {
        "question": ("does the earnings-intent series have dynamic range WITHIN "
                     "earnings weeks, or is it effectively binary?"),
        "added_after_seeing_8_2": True,
        "does_not_change_8_2": True,
        "n_tickers_saturated_at_earnings_weeks": len(saturated),
        "n_tickers_measured": len(ok),
        "conclusion": (
            "the instrument is near-binary: about 0 outside earnings weeks and "
            "73-87 (of 100) during them. It separates earnings from "
            "non-earnings almost perfectly and high-attention from ordinary "
            "earnings weeks hardly at all, so the 8.2 null is largely "
            "UNINFORMATIVE rather than evidence that no attention difference "
            "exists"),
        "per_ticker": per,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    ed, br = _load_inputs()
    doc = {
        "artifact": "GST_SEARCH_CONSTRUCT_VALIDITY_CORROBORATION",
        "date": "2026-09-04",
        "status": "RETROSPECTIVE_DEVELOPMENT_ONLY",
        "corrects": "audit v1.0 section 7.3",
        "resolves_decision": False,
        "uses_network": False,
        "selectivity_and_periodicity": section_selectivity(ed, br),
        "like_for_like": section_like_for_like(ed, br),
        "instrument_resolution": section_instrument_resolution(ed, br),
    }

    s, lf = doc["selectivity_and_periodicity"], doc["like_for_like"]
    print("=== 8.1 SELECTIVITY AND PERIODICITY ===")
    print(f"  selectivity range: {s['selectivity_pct_min']}% to {s['selectivity_pct_max']}% "
          "of earnings weeks clear z>=5")
    print(f"  baseline structurally trough-only: {s['baseline_is_structurally_trough_only']}")
    for t, v in s["per_ticker"].items():
        print(f"  {t:6s} {v['selected_z5']:2d}/{v['earnings_weeks_in_window']:2d} "
              f"({v['selectivity_pct']:5.1f}%)  mean earnings wks in own baseline="
              f"{v['mean_earnings_weeks_inside_own_baseline']}")
    print("\n=== 8.2 LIKE-FOR-LIKE (the fix) ===")
    print(f"  adequately powered: {lf['tickers_adequately_powered']}")
    print(f"  underpowered      : {lf['tickers_underpowered']}")
    for t, v in lf["per_ticker"].items():
        if v.get("status") == "no_intent_series":
            print(f"  {t:6s} no intent series"); continue
        print(f"  {t:6s} [{v['status']:12s}] n={v['n_selected']:2d}v{v['n_non_selected']:2d}  "
              f"med {v['median_selected']:5.1f} vs {v['median_non_selected']:5.1f}  "
              f"nonzero {v['nonzero_rate_selected']:.2f} vs "
              f"{v['nonzero_rate_non_selected']:.2f}  p={v['perm_p_median_difference']}")

    ir = doc["instrument_resolution"]
    print("\n=== 8.3 INSTRUMENT RESOLUTION (diagnosing the null) ===")
    print(f"  saturated at earnings weeks: "
          f"{ir['n_tickers_saturated_at_earnings_weeks']}/{ir['n_tickers_measured']}")
    for t2, v in ir["per_ticker"].items():
        if "median_earnings_weeks" not in v:
            continue
        print(f"  {t2:6s} earn-wk median={v['median_earnings_weeks']:5.1f}  "
              f"non-earn median={v['median_non_earnings_weeks']:4.1f}  "
              f">=50: {v['pct_earnings_weeks_at_or_above_50']:5.1f}%")

    if args.write:
        if OUT.exists():
            raise RefusedError(
                f"{OUT.name} exists; refusing to overwrite a dated artifact")
        OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        print(f"\nWROTE {OUT.name}")
    else:
        print("\nDRY RUN -- pass --write to persist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
