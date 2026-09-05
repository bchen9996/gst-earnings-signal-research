#!/usr/bin/env python3
"""Fix the reason audit section 8.2 failed, and correct section 8.3's diagnosis.

Section 8.2 found no detectable difference between selected and non-selected
earnings weeks, on any of the eight tickers. Section 8.3 blamed a SATURATED
instrument, on the evidence that earnings-week medians sit at 73-87 while
non-earnings weeks sit near 0.

That diagnosis names the consequence and misses the mechanism.
GST_IntentFiltered_Pull.py line 45 requests

    timeframe = f"{year}-01-01 {year}-12-31"

-- one Google Trends call PER CALENDAR YEAR. Google renormalises 0-100 to the
peak of each queried window, so the series section 8.2 analysed is five
independently normalised annual segments concatenated. Every year's peak is
forced to 100 whatever its true volume, and levels are not comparable across
years. Section 8.2 pooled ~20 earnings weeks spanning five years and compared
medians -- it compared numbers drawn on five different scales.

This is a SECOND normalisation axis, distinct from section 7.1's per-QUERY
normalisation. 7.1 stands; this adds the time axis to the term axis.

The project already knew. Live Signal Engine/CHANGELOG.md (2026-07-18)
documents per-year chunking and window renormalisation for the MAIN GST series
and corrected it the same day by re-pulling continuously. That correction was
never applied to the intent-filtered series.

The fix here: block on ticker x calendar year, where the normalisation anchor
IS shared, and permute labels within stratum only.

OFFLINE. Committed CSVs only. No Google Trends call, no network.

RETROSPECTIVE_DEVELOPMENT_ONLY. Confirms no hypothesis, moves no gate.

Run:  python tools/run_gst_instrument_normalization_fix.py [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gst_corroboration_fix import (  # noqa: E402
    D_INTENT,
    LSE,
    MIN_ARM_N,
    N_PERMUTATIONS,
    RANDOM_SEED,
    TICKERS,
    RefusedError,
    _arms,
    _intent_series,
    _load_inputs,
)

OUT = LSE / "GST_SEARCH_CONSTRUCT_VALIDITY_NORMALIZATION_2026-09-04.json"
CONTINUOUS = LSE / "FullPopulation_ContinuousWindow_Recompute.csv"

YEARS = tuple(range(2021, 2026))

# The collection script whose timeframe argument is the defect, cited so a
# reader can check the claim rather than take it.
PULL_SCRIPT = "GST_IntentFiltered_Pull.py"
PULL_SCRIPT_LINE = 45

# PRE-DECLARED POWER RULE, extending MIN_ARM_N, fixed before the test was run.
# A stratum contributes only if BOTH arms are non-empty. Below this many
# contributing strata the pooled test is reported as UNDERPOWERED, never as a
# null. Declared here so it cannot be relaxed after seeing the outcome.
MIN_INFORMATIVE_STRATA = 20

# PRE-DECLARED INTERPRETATION, fixed before the test was run.
INTERPRETATION = {
    "selected_arm_higher": (
        "once the cross-year scale break is removed the signal captures "
        "attention BEYOND earnings-ness; section 7.3's corroboration is "
        "partially reinstated, in weakened and explicitly blocked form"),
    "no_detectable_difference": (
        "the withdrawal in section 8 stands, and now stands on an instrument "
        "whose known scale defect has been controlled rather than ignored"),
    "selected_arm_lower": (
        "reported as-is, as evidence against the signal"),
    "commitment": (
        "the primary statistic is the mean within-stratum difference of arm "
        "MEANS; the rank statistic is a pre-declared robustness check that "
        "does not govern, and disagreement between them is reported as "
        "instability rather than used to choose. No re-slicing, no "
        "re-blocking, no threshold change after seeing the result"),
}

ALPHA = 0.05


# --------------------------------------- 9.1 the instrument is per-year scaled
def section_normalization_evidence() -> dict:
    """Per ticker-year: the forced-100 signature of an independent pull."""
    per: dict[str, dict] = {}
    n_years_total = 0
    n_years_one_hundred = 0
    n_years_any_hundred = 0
    for t in TICKERS:
        rows = {}
        for y in YEARS:
            f = D_INTENT / f"{t}_{y}.csv"
            if not f.exists():
                continue
            df = pd.read_csv(f)
            cols = [c for c in df.columns if c not in ("Week", "isPartial")]
            if not cols:
                continue
            v = pd.to_numeric(df[cols[0]], errors="coerce").dropna()
            n_100 = int((v == 100).sum())
            rows[str(y)] = {
                "n_weeks": int(len(v)),
                "max": float(v.max()),
                "n_at_100": n_100,
                "n_nonzero": int((v > 0).sum()),
            }
            n_years_total += 1
            if n_100 == 1:
                n_years_one_hundred += 1
            if n_100 >= 1:
                n_years_any_hundred += 1
        per[t] = rows
    return {
        "claim": (
            "each yearly file is an independent Google Trends pull, so each "
            "year's peak is forced to 100 regardless of its true volume"),
        "cause": f"{PULL_SCRIPT} line {PULL_SCRIPT_LINE}: "
                 "timeframe = f'{year}-01-01 {year}-12-31'",
        "prior_diagnosis_not_applied_here": (
            "Live Signal Engine/CHANGELOG.md 2026-07-18 documents this for the "
            "MAIN GST series and corrects it by continuous re-pull; the "
            "intent-filtered series was never corrected"),
        "n_ticker_years": n_years_total,
        # The load-bearing test. An independently normalised window MUST contain
        # its own maximum at 100, so "at least one" is the prediction; "exactly
        # one" merely adds that the maximum is usually unique.
        "n_ticker_years_with_at_least_one_100": n_years_any_hundred,
        "every_ticker_year_has_at_least_one_100":
            n_years_total > 0 and n_years_any_hundred == n_years_total,
        "n_ticker_years_with_exactly_one_100": n_years_one_hundred,
        "every_ticker_year_has_exactly_one_100":
            n_years_total > 0 and n_years_one_hundred == n_years_total,
        "ties_at_the_annual_ceiling": (
            "SBUX 2021 carries two weeks at 100 -- a tie at that year's "
            "maximum, which is the same forced-ceiling signature and not a "
            "counterexample to it"),
        "corrects_section": "8.3",
        "section_8_3_was": (
            "directionally right about the consequence (no usable range within "
            "earnings weeks) and wrong about the mechanism (it read the "
            "compression as saturation of a single scale)"),
        "per_ticker": per,
    }


# ----------------------------------- 9.2 does the SELECTION side survive too?
def section_selection_side(ed: pd.DataFrame, br: pd.DataFrame) -> dict:
    if not CONTINUOUS.exists():
        raise RefusedError(f"missing evidence file: {CONTINUOUS.name}")
    r = pd.read_csv(CONTINUOUS)
    for col in ("ticker", "spike_week", "status"):
        if col not in r.columns:
            raise RefusedError(f"{CONTINUOUS.name} has no '{col}' column")
    r["spike_week"] = pd.to_datetime(r.spike_week, errors="coerce")
    r = r.dropna(subset=["spike_week"])

    # The file is the POST-correction population: it carries no 'dropped' rows,
    # so a dropped event is an audited spike week absent from it. Refuse if that
    # assumption ever stops holding rather than silently miscounting.
    vocab = set(r.status.dropna())
    if "dropped" in vocab:
        raise RefusedError(
            f"{CONTINUOUS.name} now carries explicit 'dropped' rows; the "
            "set-difference used here would double-count them")

    per = {}
    tot = {"audited": 0, "retained": 0, "dropped": 0, "newly_qualifying": 0}
    for t in TICKERS:
        audited = set(br.loc[br.ticker == t, "spike_week"])
        sub = r[r.ticker == t]
        kept = set(sub.loc[sub.status == "retained", "spike_week"])
        new = set(sub.loc[sub.status == "newly_qualifying", "spike_week"])
        retained = audited & kept
        per[t] = {
            "audited_spike_weeks": len(audited),
            "retained": len(retained),
            "dropped": len(audited) - len(retained),
            "newly_qualifying": len(new),
        }
        tot["audited"] += len(audited)
        tot["retained"] += len(retained)
        tot["dropped"] += len(audited) - len(retained)
        tot["newly_qualifying"] += len(new)
    return {
        "question": (
            "section 8's SELECTION side came from the same per-year-chunked "
            "data; does it survive the continuous-window correction?"),
        "source": CONTINUOUS.name,
        "totals": tot,
        "selection_side_is_robust": tot["retained"] >= 0.9 * tot["audited"],
        "per_ticker": per,
    }


# ------------------------------- 9.3 the like-for-like test, blocked on year
def _strata(ticker: str, ed: pd.DataFrame, br: pd.DataFrame):
    """[(year, selected values, non-selected values)] for one ticker."""
    _, sel, non = _arms(ticker, ed, br)
    s = _intent_series(ticker)
    if s.empty:
        return []
    out = []
    for y in YEARS:
        a = np.array([s.get(w) for w in sorted(sel) if pd.Timestamp(w).year == y
                      and w in s.index], dtype=float)
        b = np.array([s.get(w) for w in sorted(non) if pd.Timestamp(w).year == y
                      and w in s.index], dtype=float)
        a, b = a[~np.isnan(a)], b[~np.isnan(b)]
        out.append((y, a, b))
    return out


def _mean_diff(strata) -> float | None:
    """Primary statistic: mean over informative strata of arm-mean difference."""
    d = [float(a.mean() - b.mean()) for _, a, b in strata if len(a) and len(b)]
    return float(np.mean(d)) if d else None


def _rank_diff(strata) -> float | None:
    """Robustness statistic: same, on within-stratum ranks scaled to [0, 1].

    Scale-free within stratum, so it does not mix the five annual scales the
    way the primary statistic's index points do.
    """
    d = []
    for _, a, b in strata:
        if not (len(a) and len(b)):
            continue
        pooled = np.concatenate([a, b])
        order = pooled.argsort().argsort().astype(float)
        if len(pooled) > 1:
            order /= (len(pooled) - 1)
        d.append(float(order[:len(a)].mean() - order[len(a):].mean()))
    return float(np.mean(d)) if d else None


def _stratified_perm_p(strata, stat_fn, rng) -> float | None:
    """Two-sided p, permuting arm labels WITHIN each stratum only.

    Within a ticker-year the 0-100 anchor is shared, so labels are exchangeable
    there and nowhere else. Permuting across strata would reintroduce exactly
    the cross-year scale break this section exists to remove.
    """
    obs = stat_fn(strata)
    if obs is None:
        return None
    live = [(y, a, b) for y, a, b in strata if len(a) and len(b)]
    hits = 0
    for _ in range(N_PERMUTATIONS):
        shuffled = []
        for y, a, b in live:
            pooled = np.concatenate([a, b])
            rng.shuffle(pooled)
            shuffled.append((y, pooled[:len(a)], pooled[len(a):]))
        s = stat_fn(shuffled)
        if s is not None and abs(s) >= abs(obs):
            hits += 1
    return round(hits / N_PERMUTATIONS, 5)


def section_blocked_like_for_like(ed: pd.DataFrame, br: pd.DataFrame) -> dict:
    rng = np.random.default_rng(RANDOM_SEED)

    pooled_strata = []
    per = {}
    for t in TICKERS:
        st = _strata(t, ed, br)
        live = [(y, a, b) for y, a, b in st if len(a) and len(b)]
        per[t] = {
            "informative_strata": len(live),
            "cells": {str(y): [len(a), len(b)] for y, a, b in st},
            "mean_within_stratum_difference": _mean_diff(st),
            "note": "DESCRIPTIVE ONLY: three to five strata cannot support an "
                    "inference for a single ticker",
        }
        pooled_strata.extend(st)

    live = [(y, a, b) for y, a, b in pooled_strata if len(a) and len(b)]
    n_live = len(live)
    powered = n_live >= MIN_INFORMATIVE_STRATA

    obs = _mean_diff(pooled_strata)
    obs_rank = _rank_diff(pooled_strata)
    p = _stratified_perm_p(pooled_strata, _mean_diff, rng) if powered else None
    p_rank = _stratified_perm_p(pooled_strata, _rank_diff, rng) if powered else None

    if not powered:
        verdict, reading = "underpowered", (
            f"fewer than {MIN_INFORMATIVE_STRATA} informative strata; reported "
            "as underpowered, not as a null")
    elif p is not None and p < ALPHA and obs is not None and obs > 0:
        verdict, reading = "selected_arm_higher", INTERPRETATION["selected_arm_higher"]
    elif p is not None and p < ALPHA and obs is not None and obs < 0:
        verdict, reading = "selected_arm_lower", INTERPRETATION["selected_arm_lower"]
    else:
        verdict, reading = "no_detectable_difference", INTERPRETATION["no_detectable_difference"]

    agree = None
    if p is not None and p_rank is not None:
        agree = (p < ALPHA) == (p_rank < ALPHA)

    return {
        "design": (
            "both arms are earnings weeks (as in 8.2) AND every comparison is "
            "made within one ticker-year, where the 0-100 anchor is shared"),
        "primary_statistic": "mean over informative strata of (selected mean - "
                             "non-selected mean), in index points",
        "n_strata_possible": len(TICKERS) * len(YEARS),
        "n_informative_strata": n_live,
        "min_informative_strata": MIN_INFORMATIVE_STRATA,
        "min_arm_n_inherited": MIN_ARM_N,
        "adequately_powered": powered,
        "observed_mean_difference": obs,
        "perm_p": p,
        "observed_rank_difference": obs_rank,
        "perm_p_rank_robustness": p_rank,
        "statistics_agree": agree,
        "alpha": ALPHA,
        "n_permutations": N_PERMUTATIONS,
        "random_seed": RANDOM_SEED,
        "pre_declared_interpretation": INTERPRETATION,
        "verdict": verdict,
        "reading": reading,
        "effect_size_caveat": (
            "the p-value is exact under within-stratum exchangeability, but "
            "the observed difference in index points mixes five annual "
            "scales and is not a physical quantity"),
        "per_ticker": per,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    ed, br = _load_inputs()
    doc = {
        "artifact": "GST_SEARCH_CONSTRUCT_VALIDITY_NORMALIZATION",
        "date": "2026-09-04",
        "status": "RETROSPECTIVE_DEVELOPMENT_ONLY",
        "corrects": "audit v1.0 section 8.3",
        "resolves_decision": False,
        "uses_network": False,
        "normalization_evidence": section_normalization_evidence(),
        "selection_side": section_selection_side(ed, br),
        "blocked_like_for_like": section_blocked_like_for_like(ed, br),
    }

    ne = doc["normalization_evidence"]
    print("=== 9.1 THE INSTRUMENT IS PER-YEAR RENORMALISED ===")
    print(f"  ticker-years with AT LEAST one week at 100: "
          f"{ne['n_ticker_years_with_at_least_one_100']}/{ne['n_ticker_years']}")
    print(f"  every ticker-year: {ne['every_ticker_year_has_at_least_one_100']}")
    print(f"  of those, exactly one: {ne['n_ticker_years_with_exactly_one_100']} "
          "(SBUX 2021 ties two weeks at its annual maximum)")
    for t, rows in ne["per_ticker"].items():
        cells = " ".join(f"{y[2:]}:{v['n_at_100']}" for y, v in rows.items())
        print(f"  {t:6s} n_at_100 by year -> {cells}")

    ss = doc["selection_side"]
    print("\n=== 9.2 DOES THE SELECTION SIDE SURVIVE? ===")
    tot = ss["totals"]
    print(f"  audited {tot['audited']}  retained {tot['retained']}  "
          f"dropped {tot['dropped']}  newly qualifying {tot['newly_qualifying']}")
    print(f"  selection side robust: {ss['selection_side_is_robust']}")

    bl = doc["blocked_like_for_like"]
    print("\n=== 9.3 LIKE-FOR-LIKE, BLOCKED ON YEAR (the fix) ===")
    print(f"  informative strata : {bl['n_informative_strata']}/"
          f"{bl['n_strata_possible']}  (minimum {bl['min_informative_strata']})")
    print(f"  adequately powered : {bl['adequately_powered']}")
    print(f"  observed mean diff : {bl['observed_mean_difference']}")
    print(f"  permutation p      : {bl['perm_p']}")
    print(f"  rank robustness p  : {bl['perm_p_rank_robustness']}  "
          f"(agree: {bl['statistics_agree']})")
    print(f"  VERDICT            : {bl['verdict']}")
    print(f"  reading            : {bl['reading']}")
    print("  per ticker (DESCRIPTIVE ONLY):")
    for t, v in bl["per_ticker"].items():
        d = v["mean_within_stratum_difference"]
        ds = "   n/a" if d is None else f"{d:6.1f}"
        print(f"    {t:6s} strata={v['informative_strata']}  mean diff={ds}")

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
