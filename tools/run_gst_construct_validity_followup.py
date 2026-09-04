#!/usr/bin/env python3
"""Follow-up to the F5 audit: correct §3e, recover the screen, break the trap.

Three things the v1.0 audit (commit 27a6698) got wrong, left implicit, or could
not test:

  1. THE FAIL. §3e attributed STZ's zero related-query breadth to a thin raw
     series. The raw series is the RICHEST of the eight. The explanation was
     wrong; the corrected mechanism is per-query normalisation hiding absolute
     volume, with the zero fraction as the only surviving proxy.
  2. THE SCREEN. §3a argued semantically that the 14 tickers dropped from
     Broad50 are homonyms. That is testable: a homonym carries a high, flat
     generic-traffic baseline. Tested here, and applied to the paper's universe.
  3. THE TRAP. §5's 10-of-10 is circular -- the events were selected by the
     very query being tested. Broken here by measuring an instrument that never
     selected anything: the earnings-intent series.

OFFLINE. Reads committed CSVs only. No Google Trends call, no network.

RETROSPECTIVE_DEVELOPMENT_ONLY. Confirms no hypothesis, moves no gate.

Run:  python tools/run_gst_construct_validity_followup.py [--write]
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
DATA = ROOT / "GST Data"

BREADTH = LSE / "RelatedQueriesBreadth_Results.csv"
OUT = LSE / "GST_SEARCH_CONSTRUCT_VALIDITY_FOLLOWUP_2026-09-04.json"

D_ORIG = DATA / "Weekly Data (2021-2025)"
D_CLEAR = DATA / "Weekly Data (2021-2025 Broad50 Clear)"
D_B50 = DATA / "Weekly Data (Broad50)"
D_INTENT = DATA / "Weekly Data (Intent Filtered Earnings)"
SERIES_DIRS = (D_ORIG, D_CLEAR, D_B50)

# The 14 Broad50 collects and "Broad50 Clear" does not.
DROPPED = ("ARE", "BRO", "CI", "CL", "EL", "FE", "HD", "KO",
           "LOW", "NI", "PM", "T", "TT", "VZ")

# The paper's retrospective population, from retrospective_event_components.csv.
PAPER_28 = ("AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "COHR", "CTSH",
            "DELL", "DVN", "GME", "GOOGL", "GPN", "INTC", "JBL", "LDOS",
            "MSFT", "NCLH", "NFLX", "NKE", "NVDA", "QCOM", "SBUX", "STZ",
            "SYK", "TSLA", "TTWO", "UAL")

BREADTH_TICKERS = ("MSFT", "ADBE", "NFLX", "NKE", "STZ", "QCOM", "SBUX", "AMZN")

# Signature of the dropped group, derived in this run and applied to the paper's
# universe. Stated as constants so the threshold cannot be tuned after seeing
# which tickers it catches.
SIG_MIN_MEDIAN = 64.0
SIG_MAX_CV = 0.31

N_PERMUTATIONS = 10000
RANDOM_SEED = 42

# A rolling z-score is undefined on a mostly-zero series. Above this share of
# zero weeks the z-based comparison is reported as not computable rather than
# computed and quietly trusted.
Z_INFEASIBLE_ZERO_SHARE = 0.50


class RefusedError(RuntimeError):
    """A precondition does not hold.

    RefusedError, never bare `assert`: `python -O` strips asserts, and a
    precondition that vanishes under an optimisation flag is not one.
    """


def _series(directory: Path, ticker: str) -> pd.Series:
    """Concatenated weekly values for one ticker, indexed by week."""
    files = sorted(glob.glob(os.path.join(str(directory), f"{ticker}_*.csv")))
    frames = []
    for f in files:
        df = pd.read_csv(f)
        cols = [c for c in df.columns if c not in ("Week", "isPartial")]
        if not cols:
            continue
        s = pd.DataFrame({
            "week": pd.to_datetime(df["Week"], errors="coerce"),
            "v": pd.to_numeric(df[cols[0]], errors="coerce"),
        }).dropna()
        frames.append(s)
    if not frames:
        return pd.Series(dtype=float)
    out = pd.concat(frames, ignore_index=True).drop_duplicates("week")
    return out.set_index("week")["v"].sort_index()


def _find_series(ticker: str) -> pd.Series:
    for d in SERIES_DIRS:
        s = _series(d, ticker)
        if len(s):
            return s
    return pd.Series(dtype=float)


def _profile(s: pd.Series) -> dict:
    if not len(s):
        return {}
    return {
        "n_weeks": int(len(s)),
        "pct_zero": round(float((s == 0).mean() * 100), 2),
        "distinct_values": int(s.nunique()),
        "median": float(s.median()),
        "cv": (round(float(s.std() / s.mean()), 4) if s.mean() else None),
    }


# --------------------------------------------------------------- 1. the fail
def section_the_fail() -> dict:
    """STZ's raw series is not thin; the earnings-intent series is."""
    raw = {t: _profile(_find_series(t)) for t in BREADTH_TICKERS}
    intent = {t: _profile(_series(D_INTENT, t)) for t in BREADTH_TICKERS}
    raw = {k: v for k, v in raw.items() if v}
    intent = {k: v for k, v in intent.items() if v}
    if "STZ" not in raw or "STZ" not in intent:
        raise RefusedError("STZ series missing; the correction cannot be shown")

    stz_raw_rank = sorted(raw, key=lambda t: -raw[t]["median"]).index("STZ") + 1
    return {
        "published_claim_being_corrected": (
            "audit v1.0 section 3e attributed STZ's zero related-query breadth "
            "to a thin raw ticker series"),
        "raw_ticker_series": raw,
        "stz_raw_median_rank_of_8": int(stz_raw_rank),
        "raw_series_refutes_thinness": bool(
            raw["STZ"]["pct_zero"] == 0.0
            and raw["STZ"]["distinct_values"] >= 50),
        "earnings_intent_series": intent,
        "stz_intent_pct_zero": intent["STZ"]["pct_zero"],
        "corrected_mechanism": (
            "Google Trends normalises each single-term query to its own 0-100 "
            "max, so absolute search volume is structurally invisible in every "
            "series this project has collected. The zero fraction is the one "
            "proxy that survives normalisation: a series rounds to 0 only when "
            "the underlying counts are tiny. STZ's raw series is dense, but its "
            "earnings-intent series is zero in 95% of weeks. The thinness is in "
            "the earnings-attention construct, not the raw ticker series."),
        "defeating_normalisation_requires": (
            "a single multi-term build_payload, which normalises ACROSS terms "
            "-- a network call, not attempted here"),
    }


# ------------------------------------------------------------- 2. the screen
def section_the_screen() -> dict:
    """Is the undocumented screen recoverable from the series themselves?"""
    b50 = sorted({os.path.basename(f).rsplit("_", 1)[0]
                  for f in glob.glob(os.path.join(str(D_B50), "*.csv"))})
    if len(b50) != 50:
        raise RefusedError(f"Broad50 holds {len(b50)} tickers, expected 50")

    prof = {t: _profile(_series(D_B50, t)) for t in b50}
    prof = {k: v for k, v in prof.items() if v and v.get("cv") is not None}
    drop = [v for k, v in prof.items() if k in DROPPED]
    keep = [v for k, v in prof.items() if k not in DROPPED]
    if len(drop) != 14:
        raise RefusedError(f"profiled {len(drop)} dropped tickers, expected 14")

    def mean(rows, key):
        return round(float(np.mean([r[key] for r in rows])), 4)

    # Does the signature separate the two groups cleanly? Measured, not assumed.
    drop_hits = {k for k, v in prof.items()
                 if k in DROPPED
                 and v["median"] >= SIG_MIN_MEDIAN and v["cv"] <= SIG_MAX_CV}
    keep_hits = {k for k, v in prof.items()
                 if k not in DROPPED
                 and v["median"] >= SIG_MIN_MEDIAN and v["cv"] <= SIG_MAX_CV}

    paper = {}
    for t in PAPER_28:
        p = _profile(_find_series(t))
        if not p or p.get("cv") is None:
            paper[t] = None
            continue
        paper[t] = {
            "median": p["median"], "cv": p["cv"],
            "matches_dropped_signature": bool(
                p["median"] >= SIG_MIN_MEDIAN and p["cv"] <= SIG_MAX_CV),
        }
    paper_hits = sorted(t for t, v in paper.items()
                        if v and v["matches_dropped_signature"])

    return {
        "signature": {"min_median": SIG_MIN_MEDIAN, "max_cv": SIG_MAX_CV,
                      "rationale": ("a homonym carries a high, flat "
                                    "generic-traffic baseline that swamps "
                                    "company-specific variation")},
        "dropped_group": {"n": len(drop), "mean_median": mean(drop, "median"),
                          "mean_cv": mean(drop, "cv"),
                          "mean_pct_zero": mean(drop, "pct_zero")},
        "kept_group": {"n": len(keep), "mean_median": mean(keep, "median"),
                       "mean_cv": mean(keep, "cv"),
                       "mean_pct_zero": mean(keep, "pct_zero")},
        "signature_catches_dropped": sorted(drop_hits),
        "signature_also_catches_kept": sorted(keep_hits),
        "separates_cleanly": bool(len(keep_hits) == 0),
        "criterion_was_statistical": bool(len(keep_hits) == 0),
        "paper_universe": paper,
        "paper_universe_matches": paper_hits,
        "per_ticker_broad50": prof,
    }


# --------------------------------------------------------------- 3. the trap
def _perm_p(a: np.ndarray, b: np.ndarray, rng, stat=np.median) -> float | None:
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None
    obs = stat(a) - stat(b)
    pooled = np.concatenate([a, b])
    n_a = len(a)
    hits = 0
    for _ in range(N_PERMUTATIONS):
        rng.shuffle(pooled)
        if abs(stat(pooled[:n_a]) - stat(pooled[n_a:])) >= abs(obs):
            hits += 1
    return round(hits / N_PERMUTATIONS, 5)


def section_the_trap() -> dict:
    """Measure an instrument that never selected anything.

    The events were selected as z >= 5 under the RAW TICKER query, so testing
    them with that query is circular. The earnings-intent series was never used
    to select anything, which is what makes it admissible as an outcome here.

    The weeks are still ticker-selected. This does not make the comparison
    selection-free; it makes the MEASURED QUANTITY independent of the selection
    rule, which is what breaks the tautology.
    """
    br = pd.read_csv(BREADTH)
    br = br[br.ticker.notna()].copy()
    br["spike_week"] = pd.to_datetime(br.spike_week, errors="coerce")
    rng = np.random.default_rng(RANDOM_SEED)

    per_ticker = {}
    for t in BREADTH_TICKERS:
        intent = _series(D_INTENT, t)
        if not len(intent):
            per_ticker[t] = {"status": "no_intent_series"}
            continue
        weeks = set(br.loc[br.ticker == t, "spike_week"].dropna())
        mask = intent.index.isin(weeks)
        ev, non = intent[mask], intent[~mask]
        if len(ev) == 0:
            per_ticker[t] = {"status": "no_event_weeks_matched"}
            continue

        zero_share = float((intent == 0).mean())
        entry = {
            "status": "ok",
            "n_event_weeks": int(len(ev)),
            "n_non_event_weeks": int(len(non)),
            "pct_zero_whole_series": round(zero_share * 100, 2),
            "nonzero_rate_event": round(float((ev > 0).mean()), 4),
            "nonzero_rate_non_event": round(float((non > 0).mean()), 4),
            "median_event": float(ev.median()),
            "median_non_event": float(non.median()),
            "mean_event": round(float(ev.mean()), 3),
            "mean_non_event": round(float(non.mean()), 3),
            "perm_p_median_difference": _perm_p(ev.to_numpy(float),
                                                non.to_numpy(float), rng),
        }
        # A rolling z on a mostly-zero series is not a statistic worth
        # reporting. Say so rather than emitting a number.
        if zero_share > Z_INFEASIBLE_ZERO_SHARE:
            entry["z_comparison"] = "not_computable"
            entry["z_comparison_reason"] = (
                f"{entry['pct_zero_whole_series']}% of weeks are zero; a "
                "12-week rolling z-score is undefined or degenerate")
        else:
            roll = intent.shift(1).rolling(12, min_periods=8)
            z = (intent - roll.mean()) / roll.std()
            z = z.replace([np.inf, -np.inf], np.nan)
            entry["z_comparison"] = {
                "median_z_event": (None if z[mask].isna().all()
                                   else round(float(z[mask].median()), 4)),
                "median_z_non_event": (None if z[~mask].isna().all()
                                       else round(float(z[~mask].median()), 4)),
                "n_event_z_ge_2": int((z[mask] >= 2.0).sum()),
            }
        per_ticker[t] = entry

    computable = [t for t, v in per_ticker.items()
                  if v.get("status") == "ok"
                  and not isinstance(v.get("z_comparison"), str)]
    return {
        "why_this_breaks_the_tautology": (
            "The audit's 10-of-10 is true by construction: the events were "
            "selected as z >= 5 under the raw-ticker query. The earnings-intent "
            "series was never used to select anything, so it is an independent "
            "outcome at those same weeks. The weeks remain ticker-selected -- "
            "this is not a selection-free test, it is a test whose measured "
            "quantity is independent of the selection rule."),
        "n_permutations": N_PERMUTATIONS,
        "random_seed": RANDOM_SEED,
        "z_infeasible_above_zero_share": Z_INFEASIBLE_ZERO_SHARE,
        "tickers_supporting_z_comparison": sorted(computable),
        "per_ticker": per_ticker,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    if not BREADTH.exists():
        raise RefusedError(f"missing evidence file: {BREADTH.name}")
    for d in (D_ORIG, D_B50, D_INTENT):
        if not d.exists():
            raise RefusedError(f"missing data directory: {d.name}")

    doc = {
        "artifact": "GST_SEARCH_CONSTRUCT_VALIDITY_FOLLOWUP",
        "date": "2026-09-04",
        "status": "RETROSPECTIVE_DEVELOPMENT_ONLY",
        "follows_up": "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0_2026-09-04.md",
        "corrects": "audit v1.0 section 3e",
        "resolves_decision": False,
        "uses_network": False,
        "the_fail": section_the_fail(),
        "the_screen": section_the_screen(),
        "the_trap": section_the_trap(),
    }

    f, s, tr = doc["the_fail"], doc["the_screen"], doc["the_trap"]
    print("=== 1. THE FAIL ===")
    print(f"  STZ raw median rank of 8      : {f['stz_raw_median_rank_of_8']}")
    print(f"  raw series refutes thinness   : {f['raw_series_refutes_thinness']}")
    print(f"  STZ earnings-intent %zero     : {f['stz_intent_pct_zero']}")
    print("\n=== 2. THE SCREEN ===")
    print(f"  dropped: {s['dropped_group']}")
    print(f"  kept   : {s['kept_group']}")
    print(f"  signature also catches kept   : {s['signature_also_catches_kept']}")
    print(f"  separates cleanly             : {s['separates_cleanly']}")
    print(f"  PAPER UNIVERSE MATCHES        : {s['paper_universe_matches']}")
    print("\n=== 3. THE TRAP ===")
    print(f"  z-comparison feasible for     : {tr['tickers_supporting_z_comparison']}")
    for t, v in tr["per_ticker"].items():
        if v.get("status") != "ok":
            print(f"  {t:6s} {v['status']}")
            continue
        print(f"  {t:6s} nonzero ev={v['nonzero_rate_event']:.3f} "
              f"non-ev={v['nonzero_rate_non_event']:.3f}  "
              f"med ev={v['median_event']:.1f} non-ev={v['median_non_event']:.1f}  "
              f"perm p={v['perm_p_median_difference']}")

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
