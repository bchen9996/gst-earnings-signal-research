#!/usr/bin/env python3
"""Fetch the 16 frozen queries at WEEKLY resolution across 2019-2025.

Google serves weekly resolution only for windows up to ~5 years; a 7-year request
silently returns MONTHLY points. Two overlapping sub-5-year windows are therefore
pulled and stitched on the overlap. The stitch is a FIXED, PRE-SPECIFIED procedure
declared before any outcome was computed - it is not searched or tuned:

    scale = median( early[w] / late[w] ) over weeks present in BOTH windows,
            using only weeks where late[w] > 0
    stitched = late values, plus early values divided by that scale for weeks
               before the overlap

Queries are used exactly as frozen. No related-query selection, no substitution.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Live Signal Engine" / "Restaurant_Search_Pilot"
QMAP = OUT / "frozen_queries_v1.0.csv"
CACHE = OUT / "search_weekly_v1.0.csv"

W1 = ("2019-01-01", "2023-06-30")     # 4.5 years -> weekly
W2 = ("2021-07-01", "2025-12-31")     # 4.5 years -> weekly


def pull(pt, q, tf):
    pt.build_payload([q], timeframe=f"{tf[0]} {tf[1]}", geo="US", gprop="", cat=0)
    d = pt.interest_over_time()
    if d is None or d.empty:
        return None
    if "isPartial" in d:
        d = d[~d["isPartial"].astype(bool)]
    return d[q].astype(float)


def main() -> int:
    from pytrends.request import TrendReq
    qm = pd.read_csv(QMAP)
    pt = TrendReq(hl="en-US", tz=360)
    rows, failed = [], []
    jobs = [(r.ticker, r.consumer_query, "consumer") for r in qm.itertuples()] + \
           [(r.ticker, r.investor_query, "investor") for r in qm.itertuples()]
    for tick, q, kind in jobs:
        try:
            a = pull(pt, q, W1)
            time.sleep(3)
            b = pull(pt, q, W2)
            time.sleep(3)
        except Exception as e:                                  # noqa: BLE001
            failed.append({"ticker": tick, "query": q, "kind": kind,
                           "reason": f"{type(e).__name__}: {str(e)[:90]}"})
            print(f"  [{tick}/{kind}] ERROR {type(e).__name__}: {str(e)[:80]}")
            continue
        if a is None and b is None:
            failed.append({"ticker": tick, "query": q, "kind": kind, "reason": "no data in either window"})
            print(f"  [{tick}/{kind}] no data")
            continue
        if a is None:
            s = b
        elif b is None:
            s = a
        else:
            ov = a.index.intersection(b.index)
            ratios = [a[w] / b[w] for w in ov if b[w] > 0]
            scale = float(np.median(ratios)) if ratios else 1.0
            early = (a[a.index < b.index.min()] / scale) if scale > 0 else a[a.index < b.index.min()]
            s = pd.concat([early, b]).sort_index()
        for wk, v in s.items():
            rows.append({"ticker": tick, "kind": kind, "query": q,
                         "week": pd.Timestamp(wk), "interest": float(v)})
        print(f"  [{tick}/{kind}] {len(s)} weekly points {s.index.min().date()} -> {s.index.max().date()}")
    d = pd.DataFrame(rows)
    if len(d):
        d.to_csv(CACHE, index=False, lineterminator="\n")
    if failed:
        pd.DataFrame(failed).to_csv(OUT / "unavailable_queries_v1.0.csv", index=False, lineterminator="\n")
    print(f"\nseries fetched: {d.groupby(['ticker','kind']).ngroups if len(d) else 0} | failed: {len(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
