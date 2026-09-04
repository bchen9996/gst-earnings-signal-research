#!/usr/bin/env python3
"""Derive every number in the F5 search-construct validity audit.

Implements sections 4 and 5 of
`Live Signal Engine/GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0_2026-09-04.md`.
Sections 1-3 of that document -- including its recommendation -- were written
and committed BEFORE this script was run, so the construct argument cannot have
been shaped by the term-sensitivity results computed here.

OFFLINE. Reads four committed CSVs and nothing else. No Google Trends call, no
network, no live runner.

RETROSPECTIVE_DEVELOPMENT_ONLY. Confirms no hypothesis, moves no gate.

Run:  python tools/run_gst_construct_validity_audit.py [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LSE = ROOT / "Live Signal Engine"

REPRO = LSE / "GST_Reproducibility_Audit.csv"
BREADTH = LSE / "RelatedQueriesBreadth_Results.csv"
NOISE = LSE / "GSTSamplingNoise_Results.csv"
PARTIAL = LSE / "PartialWeekSamplingNoise_Results.csv"
OUT = LSE / "GST_SEARCH_CONSTRUCT_VALIDITY_RESULTS_2026-09-04.json"

Z_STRONG = 5.0

# The 14 tickers Broad50 collects and "Broad50 Clear" does not. Pinned so a
# change to either universe surfaces here rather than silently altering the
# audit's principal finding.
DROPPED_BY_UNDOCUMENTED_SCREEN = (
    "ARE", "BRO", "CI", "CL", "EL", "FE", "HD", "KO",
    "LOW", "NI", "PM", "T", "TT", "VZ",
)
AUDIT_NAMED_RISKS = ("BKR", "GME", "STZ")


class RefusedError(RuntimeError):
    """A precondition of the audit does not hold.

    RefusedError, never `assert`: `python -O` strips asserts, and a
    precondition that vanishes under an optimisation flag is not one.
    """


def _load(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise RefusedError(f"missing evidence file: {path.name}")
    return pd.read_csv(path)


def check_preconditions(repro: pd.DataFrame, breadth: pd.DataFrame) -> None:
    """Refuse unless the evidence is the evidence the audit was written against."""
    counts = repro.test.value_counts().to_dict()
    expected = {"reproducibility": 100, "term_sensitivity": 10,
                "category_sensitivity": 10, "EVENT_SUMMARY": 10}
    for name, n in expected.items():
        if counts.get(name) != n:
            raise RefusedError(
                f"{REPRO.name}: expected {n} '{name}' rows, found "
                f"{counts.get(name)}. The audit text describes the 10-event "
                "design; a different shape needs a re-read, not a re-run.")
    n_events = repro[repro.test == "EVENT_SUMMARY"].shape[0]
    if n_events != 10:
        raise RefusedError(f"expected 10 events, found {n_events}")
    if breadth.ticker.nunique() != 8:
        raise RefusedError(
            f"{BREADTH.name}: expected 8 tickers, found "
            f"{breadth.ticker.nunique()}. Section 3d states 8 explicitly.")


def section4_reproducibility(repro, noise, partial) -> dict:
    """Does re-pulling the same closed week reproduce the same z-score?"""
    summ = repro[repro.test == "EVENT_SUMMARY"]
    rng = pd.to_numeric(summ.zscore_range, errors="coerce")
    std = pd.to_numeric(summ.zscore_std, errors="coerce")
    flagged = summ.flagged_unstable.astype(str).str.lower().isin(["true", "1"])

    zmax = pd.to_numeric(noise.get("z_max_diff"), errors="coerce").dropna()
    tiers_differ = noise.get("tiers_differ")
    tiers_differ = (tiers_differ.astype(str).str.lower().isin(["true", "1"]).sum()
                    if tiers_differ is not None else None)

    p_z = pd.to_numeric(partial.zscore, errors="coerce").dropna()
    p_gst = pd.to_numeric(partial.gst_value, errors="coerce").dropna()

    return {
        "closed_week_repeat_pulls": {
            "events": int(len(summ)),
            "pulls_per_event": 10,
            "max_zscore_range_across_events": float(rng.max()),
            "max_zscore_std_across_events": float(std.max()),
            "events_flagged_unstable": int(flagged.sum()),
            "all_deterministic": bool(rng.max() == 0.0 and std.max() == 0.0),
        },
        "five_pull_weekly_series": {
            "weeks_compared": int(len(noise)),
            "max_z_difference_any_week": (float(zmax.max()) if len(zmax) else None),
            "weeks_where_tier_differs": (int(tiers_differ)
                                         if tiers_differ is not None else None),
        },
        "partial_week": {
            "pulls": int(len(partial)),
            "is_partial_week": bool(partial.is_partial_week.astype(str)
                                    .str.lower().eq("true").all()),
            "distinct_gst_values": int(p_gst.nunique()),
            "distinct_zscores": int(p_z.nunique()),
            "zscore_range": (float(p_z.max() - p_z.min()) if len(p_z) else None),
        },
    }


def section5_term_sensitivity(repro: pd.DataFrame) -> dict:
    """The comparison §2's recommendation must NOT have been informed by."""
    summ = repro[repro.test == "EVENT_SUMMARY"].copy()
    tick = pd.to_numeric(summ.orig_zscore, errors="coerce")
    name = pd.to_numeric(summ.zscore_company_name, errors="coerce")
    fin = pd.to_numeric(summ.zscore_finance_category, errors="coerce")

    def clears(s):
        return (s >= Z_STRONG)

    per_event = []
    for _, r in summ.iterrows():
        t = pd.to_numeric(r.orig_zscore, errors="coerce")
        n = pd.to_numeric(r.zscore_company_name, errors="coerce")
        f = pd.to_numeric(r.zscore_finance_category, errors="coerce")
        per_event.append({
            "ticker": r.ticker, "spike_week": r.spike_week,
            "z_ticker": None if pd.isna(t) else round(float(t), 4),
            "z_company_name": None if pd.isna(n) else round(float(n), 4),
            "z_finance_category": None if pd.isna(f) else round(float(f), 4),
            "clears_z5_ticker": bool(t >= Z_STRONG) if pd.notna(t) else None,
            "clears_z5_company_name": bool(n >= Z_STRONG) if pd.notna(n) else None,
            "clears_z5_finance_category": bool(f >= Z_STRONG) if pd.notna(f) else None,
        })

    return {
        "threshold": Z_STRONG,
        "n_events": int(len(summ)),
        "clears_z5_counts": {
            "raw_ticker_cat0": int(clears(tick).sum()),
            "company_name_cat0": int(clears(name).sum()),
            "raw_ticker_cat7_finance": int(clears(fin).sum()),
        },
        "n_with_value": {
            "raw_ticker_cat0": int(tick.notna().sum()),
            "company_name_cat0": int(name.notna().sum()),
            "raw_ticker_cat7_finance": int(fin.notna().sum()),
        },
        "events_changing_status_vs_ticker": {
            "under_company_name": int((clears(tick) != clears(name))[
                tick.notna() & name.notna()].sum()),
            "under_finance_category": int((clears(tick) != clears(fin))[
                tick.notna() & fin.notna()].sum()),
        },
        "per_event": per_event,
    }


def section3_breadth(breadth: pd.DataFrame) -> dict:
    """Related-query breadth per event.

    The file carries trailing aggregate rows with a blank ticker (a
    high/low-breadth group comparison). Those are dropped here: they are a
    different analysis, and averaging them into per-ticker statistics would
    silently mix an event-level metric with a group-level one.
    """
    ev = breadth[breadth.ticker.notna()].copy()
    ok = ev[ev.status.astype(str).str.lower() == "ok"].copy()
    ok["breadth_score"] = pd.to_numeric(ok.breadth_score, errors="coerce")
    score = ok.breadth_score.dropna()

    # A z >= 5 spike week that returns ZERO related queries is the sharpest
    # available evidence of a thin query: the term spiked, and Google could
    # not name a single associated search. Reported per ticker because it is
    # concentrated, not spread.
    zero = ok[ok.breadth_score == 0.0]
    by_ticker = {
        str(t): {
            "events_ok": int((ok.ticker == t).sum()),
            "events_zero_breadth": int((zero.ticker == t).sum()),
            "median_breadth": (None if not (ok.ticker == t).any() else
                               float(ok.loc[ok.ticker == t, "breadth_score"].median())),
        }
        for t in sorted(ok.ticker.unique())
    }
    return {
        "tickers_with_any_breadth_data": sorted(ev.ticker.unique().tolist()),
        "n_tickers": int(ev.ticker.nunique()),
        "rows_total": int(len(ev)),
        "rows_usable": int(len(ok)),
        "rows_rate_limited": int((ev.status.astype(str).str.lower()
                                  == "rate_limited").sum()),
        "breadth_score_min": (float(score.min()) if len(score) else None),
        "breadth_score_median": (float(score.median()) if len(score) else None),
        "breadth_score_max": (float(score.max()) if len(score) else None),
        "events_with_zero_breadth": int(len(zero)),
        "by_ticker": by_ticker,
        "caveat": ("breadth is a COUNT of related queries, not the query "
                   "strings, so it bounds ambiguity only weakly"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="persist the artifact; otherwise dry-run to stdout")
    args = ap.parse_args()

    repro, breadth = _load(REPRO), _load(BREADTH)
    noise, partial = _load(NOISE), _load(PARTIAL)
    check_preconditions(repro, breadth)

    doc = {
        "artifact": "GST_SEARCH_CONSTRUCT_VALIDITY_RESULTS",
        "date": "2026-09-04",
        "status": "RETROSPECTIVE_DEVELOPMENT_ONLY",
        "discharges_gap_audit_item": "F5",
        "resolves_decision": False,
        "uses_network": False,
        "audit_document": "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0_2026-09-04.md",
        "ordering_note": (
            "Sections 1-3 of the audit, including its recommendation, were "
            "committed before this script was run. Section 5 below is reported "
            "as robustness and does not revise that recommendation."),
        "mapping_in_force": {
            "term": "raw ticker string", "geo": "US",
            "gprop": "", "cat": 0,
            "note": "all categories; no disambiguation applied",
        },
        "undocumented_screen": {
            "broad50_n": 50, "broad50_clear_n": 36,
            "dropped": list(DROPPED_BY_UNDOCUMENTED_SCREEN),
            "audit_named_risks": list(AUDIT_NAMED_RISKS),
        },
        "section3_breadth": section3_breadth(breadth),
        "section4_reproducibility": section4_reproducibility(repro, noise, partial),
        "section5_term_sensitivity": section5_term_sensitivity(repro),
    }

    print(json.dumps({k: v for k, v in doc.items() if k != "section5_term_sensitivity"},
                     indent=1)[:2000])
    print("\n--- section 5 ---")
    s5 = doc["section5_term_sensitivity"]
    print(json.dumps({k: v for k, v in s5.items() if k != "per_event"}, indent=1))

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
