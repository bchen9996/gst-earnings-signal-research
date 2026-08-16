#!/usr/bin/env python3
"""Focused check on the retrospective decomposition.

Recomputes the return arithmetic from the source CSVs for a sample of events,
verifies sample counts and cost subtraction, and checks the report's headline
numbers match the results JSON. Deterministic, offline.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RES = json.loads((ROOT / "RETROSPECTIVE_MARKET_RESPONSE_RESULTS_v1.0.json").read_text(encoding="utf-8"))
REPORT = (ROOT / "RETROSPECTIVE_MARKET_RESPONSE_REPORT_v1.0.md").read_text(encoding="utf-8")
EV = pd.read_csv(ROOT / "Live Signal Engine" / "retrospective_event_components.csv")
POP = pd.read_csv(ROOT / "Live Signal Engine" / "C5_PostEarnings_Population.csv")
OHLC = ROOT / "Daily OHLC Data (2021-2025 Opening Gap Test)"

FAIL = []


def check(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


# ---- 1. sample counts tie to the source population ----
check("1a. usable + dropped == population",
      RES["sample"]["events_usable"] + RES["sample"]["dropped"] == len(POP) == 304)
check("1b. usable count matches the component file",
      RES["sample"]["events_usable"] == len(EV) == 285)
check("1c. high + control == usable",
      RES["sample"]["high_gst_events"] + RES["sample"]["control_events"] == len(EV))
check("1d. every high-GST event really is a signal-role event with z>=5",
      float(EV[EV.role == "signal"].zscore.min()) >= 5.0)

# ---- 2. return arithmetic recomputed from raw OHLC for sampled events ----
bad = []
for _, r in EV.sample(n=25, random_state=0).iterrows():
    px = pd.read_csv(OHLC / f"{r.ticker}_ohlc.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    i = px.index[px["Date"] == pd.Timestamp(r.event_day)]
    if len(i) != 1:
        bad.append((r.ticker, r.event_day, "event day not a session"))
        continue
    T = int(i[0])
    gap = px.Open[T] / px.Close[T - 1] - 1
    oc = px.Close[T] / px.Open[T] - 1
    day = px.Close[T] / px.Close[T - 1] - 1
    pre = px.Close[T - 1] / px.Close[T - 6] - 1
    post = px.Close[T + 3] / px.Close[T] - 1
    for nm, got, want in (("gap", gap, r.gap), ("open_to_close", oc, r.open_to_close),
                          ("day_return", day, r.day_return), ("pre_drift", pre, r.pre_drift),
                          ("post_1_3", post, r.post_1_3)):
        if abs(got - want) > 1e-9:
            bad.append((r.ticker, r.event_day, nm, got, want))
check(f"2a. 25 sampled events recompute exactly from raw OHLC (bad={bad[:2]})", not bad)
check("2b. day return is consistent with gap and open-to-close",
      bool(np.allclose((1 + EV.gap) * (1 + EV.open_to_close), 1 + EV.day_return, atol=1e-9)))

# ---- 3. event-day convention ----
amc = EV[EV.bmo_amc == "AMC"]
check("3a. AMC events react strictly after the earnings date",
      bool((pd.to_datetime(amc.event_day) > pd.to_datetime(amc.earnings_date)).all()))
bmo = EV[EV.bmo_amc == "BMO"]
check("3b. BMO events react on or after the earnings date",
      bool((pd.to_datetime(bmo.event_day) >= pd.to_datetime(bmo.earnings_date)).all()))

# ---- 4. cost subtraction ----
for s in RES["scorecard"]:
    if s.get("n_trades") and "mean_gross_pct" in s:
        want = round(s["mean_gross_pct"] - s["cost_bps_round_trip"] / 100.0, 4)
        check(f"4. {s['strategy'][:34]}: net == gross - cost", abs(s["mean_net_pct"] - want) < 1e-6,
              f"net={s['mean_net_pct']} expected={want}")

# ---- 5. strategy returns recompute from the component file ----
hi = EV[EV.role == "signal"].dropna(subset=["gap", "open_to_close"])
b = np.sign(hi.gap.values) * hi.open_to_close.values
sB = next(s for s in RES["scorecard"] if s["strategy"].startswith("B."))
check("5a. B mean gross recomputes", abs(100 * b.mean() - sB["mean_gross_pct"]) < 1e-3)
check("5b. C is exactly the negative of B",
      abs(next(s for s in RES["scorecard"] if s["strategy"].startswith("C."))["mean_gross_pct"]
          + sB["mean_gross_pct"]) < 1e-9)
he = EV[EV.role == "signal"].dropna(subset=["gap", "post_1_3_ex"])
e = np.sign(he.gap.values) * he.post_1_3_ex.values
sE = next(s for s in RES["scorecard"] if s["strategy"].startswith("E."))
check("5c. E mean gross recomputes", abs(100 * e.mean() - sE["mean_gross_pct"]) < 1e-3)
# stored rounded to 2 dp, so compare against the same rounding
check("5d. E hit rate recomputes", round(100 * float((e > 0).mean()), 2) == sE["hit_rate_pct"])

# ---- 6. the conclusion's load-bearing comparison ----
check("6a. E's control comparator is not worse than the high-GST result "
      "(the filter adds nothing)",
      sE["control_only_mean_net_pct"] >= sE["mean_net_pct"] - 0.05)
check("6b. E's within-pair difference is statistically indistinguishable from zero",
      abs(sE["same_ticker_paired_t"]) < 2.0)
check("6c. A is reported NOT_TESTABLE with no fabricated trades",
      next(s for s in RES["scorecard"] if s["strategy"].startswith("A."))["verdict"] == "NOT_TESTABLE"
      and next(s for s in RES["scorecard"] if s["strategy"].startswith("A."))["n_trades"] == 0)
check("6d. results declare no prospective outcome used",
      RES["uses_prospective_outcomes"] is False and RES["confirms_hyp01"] is False)
check("6e. intraday unavailability is recorded, not worked around",
      RES["data_availability"]["intraday_bars_available"] is False)

# ---- 7. report headline numbers match the JSON ----
flat = " ".join(REPORT.split())
for val in (f"{sE['mean_net_pct']:.3f}%", f"{RES['Q1_abs_move_high_vs_control']['difference_pp']:.2f} pp",
            f"{RES['Q6_robustness_of_the_attention_effect']['same_ticker_pairs_only_t']}"):
    check(f"7. report states {val}", val in flat)
check("7d. report leads with the results table, not methodology",
      flat.index("Strategy scorecard") < flat.index("Frozen definitions"))
check("7e. report records the NO STRATEGY verdict", "NO STRATEGY" in REPORT)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("ALL RETROSPECTIVE DECOMPOSITION CHECKS PASSED")
sys.exit(0)
