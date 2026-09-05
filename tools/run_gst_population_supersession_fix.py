#!/usr/bin/env python3
"""Correct section 9.2, which cited a file the CHANGELOG quarantines.

Live Signal Engine/CHANGELOG.md (2026-07-19, "fixed-window per-event recompute")
establishes FixedWindow_PerEvent_Canonical.csv (n=152) as the canonical
historical population, superseding BOTH:

  - the original 147-event chunked archive (GST-Legacy-v1), and
  - the 148/149-event continuous-window reconstruction, which is quarantined
    for look-ahead contamination (93 of 175 events at risk).

Of the latter the CHANGELOG says the derived ledgers "should not be used for
new analysis."

Section 9.2 validated section 8.1 against exactly that quarantined file. It
reached for the recompute because it was the file that existed, not the file
that governs. This corrects that.

It also records a larger fact section 9 did not: the whole F5 audit selects
events through RelatedQueriesBreadth_Results.csv, whose spike weeks are the
GST-Legacy-v1 z>=5 set. The audit has been analysing a superseded population
throughout, and nowhere says so.

OFFLINE. Committed CSVs only. No Google Trends call, no network.

RETROSPECTIVE_DEVELOPMENT_ONLY. Confirms no hypothesis, moves no gate.

Run:  python tools/run_gst_population_supersession_fix.py [--write]
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
    LSE,
    TICKERS,
    RefusedError,
    _arms,
    _load_inputs,
)
from run_gst_instrument_normalization_fix import (  # noqa: E402
    ALPHA,
    CONTINUOUS,
    MIN_INFORMATIVE_STRATA,
    N_PERMUTATIONS,
    RANDOM_SEED,
    YEARS,
    _mean_diff,
    _rank_diff,
    _strata,
    _stratified_perm_p,
)

OUT = LSE / "GST_SEARCH_CONSTRUCT_VALIDITY_SUPERSESSION_2026-09-04.json"
CANONICAL = LSE / "FixedWindow_PerEvent_Canonical.csv"

# The CHANGELOG entry that governs, cited so a reader can check rather than take
# it. Both superseded sets stay on disk for the audit trail; neither may be
# cited as a current best estimate.
GOVERNING_ENTRY = ("Live Signal Engine/CHANGELOG.md, 2026-07-19, "
                   "'fixed-window per-event recompute "
                   "(resolves the look-ahead finding; new canonical baseline)'")
CANONICAL_N = 152

# PRE-DECLARED, fixed before the canonical re-run of 9.3 was computed.
#
# The canonical population is the correct one BY SUPERSESSION, not by outcome:
# the CHANGELOG designated it canonical on 2026-07-19, long before this audit
# existed and with no knowledge of what it would show here. That is why the
# canonical re-run may be named the one to cite going forward without this
# being a choice made after seeing a result.
INTERPRETATION = {
    "basis_for_preferring_canonical": (
        "supersession recorded in the CHANGELOG on 2026-07-19, not the outcome "
        "of this test"),
    "agrees_with_9_3": (
        "the null in 9.3 is not an artifact of the superseded event set; both "
        "are reported and the canonical one is what should be cited"),
    "disagrees_with_9_3": (
        "BOTH STAND AND THE DISAGREEMENT IS THE FINDING; neither is chosen "
        "after the fact, and section 9.3 is not rewritten"),
    "commitment": (
        "section 9.3's legacy result is retained unchanged as the "
        "pre-registered original and is not deleted or restated; "
        "MIN_INFORMATIVE_STRATA applies unchanged, and below it the run is "
        "reported as underpowered, never as a null"),
}


def _load_canonical() -> pd.DataFrame:
    if not CANONICAL.exists():
        raise RefusedError(f"missing evidence file: {CANONICAL.name}")
    c = pd.read_csv(CANONICAL)
    for col in ("ticker", "spike_week", "qualifies_z5", "fixed_window_zscore"):
        if col not in c.columns:
            raise RefusedError(f"{CANONICAL.name} has no '{col}' column")
    c["spike_week"] = pd.to_datetime(c.spike_week, errors="coerce")
    c = c.dropna(subset=["spike_week"])
    n_qual = int((c.qualifies_z5 == True).sum())  # noqa: E712
    if n_qual != CANONICAL_N:
        raise RefusedError(
            f"{CANONICAL.name} carries {n_qual} qualifying events, not the "
            f"{CANONICAL_N} the CHANGELOG designates canonical; the file this "
            "correction points at is not the one it was written against")
    return c


def _canonical_breadth(c: pd.DataFrame) -> pd.DataFrame:
    """A breadth-shaped frame of canonical events, so _arms can be reused.

    Verified: all 90 canonical qualifying events for these tickers fall on
    earnings weeks under the same mapping, so _arms does not refuse.
    """
    q = c[(c.qualifies_z5 == True) & (c.ticker.isin(TICKERS))]  # noqa: E712
    return pd.DataFrame({"ticker": q.ticker.values,
                         "spike_week": q.spike_week.values})


def _pairs(df: pd.DataFrame) -> set:
    return set(zip(df.ticker, df.spike_week))


# ------------------------------------- 10.1 section 9.2 cited a quarantined file
def section_citation_error(br: pd.DataFrame, c: pd.DataFrame) -> dict:
    if not CONTINUOUS.exists():
        raise RefusedError(f"missing evidence file: {CONTINUOUS.name}")
    r = pd.read_csv(CONTINUOUS)
    r["spike_week"] = pd.to_datetime(r.spike_week, errors="coerce")
    r = r.dropna(subset=["spike_week"])
    r = r[r.ticker.isin(TICKERS)]

    audited = _pairs(br[br.ticker.isin(TICKERS)])
    cont_keep = _pairs(r[r.status == "retained"])
    canon_keep = _pairs(c[(c.qualifies_z5 == True)  # noqa: E712
                          & (c.ticker.isin(TICKERS))])

    cont_rejects = audited - cont_keep
    canon_rejects = audited - canon_keep
    shared = cont_rejects & canon_rejects

    return {
        "error": (
            "section 9.2 validated section 8.1 against "
            f"{CONTINUOUS.name}, which the CHANGELOG supersedes and quarantines "
            "for look-ahead contamination and says must not be used for new "
            "analysis"),
        "governing_entry": GOVERNING_ENTRY,
        "quarantined_file": CONTINUOUS.name,
        "canonical_file": CANONICAL.name,
        "n_audited": len(audited),
        "n_retained_under_quarantined": len(audited & cont_keep),
        "n_retained_under_canonical": len(audited & canon_keep),
        "headline_figures_agree":
            len(audited & cont_keep) == len(audited & canon_keep),
        "n_rejected_under_quarantined": len(cont_rejects),
        "n_rejected_under_canonical": len(canon_rejects),
        "n_rejections_in_common": len(shared),
        "composition_agrees": cont_rejects == canon_rejects,
        "warning": (
            "the headline number is stable while the membership underneath it "
            "is not; a reader who checks only the count would conclude the two "
            "populations agree"),
        "rejected_by_quarantined_only": sorted(
            f"{t} {d.date()}" for t, d in cont_rejects - shared),
        "rejected_by_canonical_only": sorted(
            f"{t} {d.date()}" for t, d in canon_rejects - shared),
        "rejected_by_both": sorted(f"{t} {d.date()}" for t, d in shared),
    }


# ----------------------------- 10.2 the audit's population is GST-Legacy-v1
def section_population_provenance(ed: pd.DataFrame, br: pd.DataFrame,
                                  c: pd.DataFrame) -> dict:
    canon = c[(c.qualifies_z5 == True) & (c.ticker.isin(TICKERS))]  # noqa: E712
    per = {}
    tot_audit = tot_canon = tot_overlap = tot_earn = 0
    for t in TICKERS:
        earn, sel, _ = _arms(t, ed, br)
        can = set(canon.loc[canon.ticker == t, "spike_week"])
        rej = sorted(sel - can)
        unseen = sorted(can - sel)
        zs = {}
        for d in rej:
            row = c[(c.ticker == t) & (c.spike_week == d)]
            if len(row):
                zs[str(d.date())] = float(row.fixed_window_zscore.iloc[0])
        per[t] = {
            "earnings_weeks_in_window": len(earn),
            "audit_events_legacy": len(sel),
            "canonical_events": len(can),
            "in_both": len(sel & can),
            "audit_only_rejected_by_canonical": [str(d.date()) for d in rej],
            "canonical_z_of_rejected": zs,
            "canonical_only_never_analysed": [str(d.date()) for d in unseen],
            "selectivity_pct_legacy": round(100 * len(sel) / len(earn), 1),
            "selectivity_pct_canonical": round(100 * len(can) / len(earn), 1),
        }
        tot_audit += len(sel)
        tot_canon += len(can)
        tot_overlap += len(sel & can)
        tot_earn += len(earn)
    return {
        "finding": (
            "the F5 audit selects events through RelatedQueriesBreadth_Results"
            ".csv, whose spike weeks are the GST-Legacy-v1 z>=5 set; sections "
            "1-9 therefore analyse a superseded population and nowhere say so"),
        "manuscript_is_unaffected": (
            f"the citation policy and the paper use the canonical "
            f"{CANONICAL_N} signal events; it is the audit that drifted"),
        "totals": {
            "earnings_weeks": tot_earn,
            "audit_events_legacy": tot_audit,
            "canonical_events": tot_canon,
            "in_both": tot_overlap,
            "audit_only": tot_audit - tot_overlap,
            "canonical_only": tot_canon - tot_overlap,
        },
        # 8.1's conclusion, now measured against the right population instead of
        # inferred from a quarantined one.
        "selectivity_pct_legacy": round(100 * tot_audit / tot_earn, 1),
        "selectivity_pct_canonical": round(100 * tot_canon / tot_earn, 1),
        "section_8_1_conclusion_survives":
            abs(tot_canon - tot_audit) <= 0.1 * tot_audit,
        "per_ticker": per,
    }


# ------------------- 10.3 the blocked test, re-run on the canonical population
def section_canonical_blocked_test(ed: pd.DataFrame, br_canon: pd.DataFrame,
                                   legacy: dict | None = None) -> dict:
    rng = np.random.default_rng(RANDOM_SEED)

    pooled = []
    per = {}
    for t in TICKERS:
        st = _strata(t, ed, br_canon)
        live = [(y, a, b) for y, a, b in st if len(a) and len(b)]
        per[t] = {
            "informative_strata": len(live),
            "cells": {str(y): [len(a), len(b)] for y, a, b in st},
            "mean_within_stratum_difference": _mean_diff(st),
            "note": "DESCRIPTIVE ONLY, as in 9.3",
        }
        pooled.extend(st)

    n_live = len([1 for _, a, b in pooled if len(a) and len(b)])
    powered = n_live >= MIN_INFORMATIVE_STRATA

    obs = _mean_diff(pooled)
    obs_rank = _rank_diff(pooled)
    p = _stratified_perm_p(pooled, _mean_diff, rng) if powered else None
    p_rank = _stratified_perm_p(pooled, _rank_diff, rng) if powered else None

    if not powered:
        verdict = "underpowered"
    elif p is not None and p < ALPHA and obs is not None and obs > 0:
        verdict = "selected_arm_higher"
    elif p is not None and p < ALPHA and obs is not None and obs < 0:
        verdict = "selected_arm_lower"
    else:
        verdict = "no_detectable_difference"

    out = {
        "design": (
            "identical to 9.3 -- both arms earnings weeks, blocked on "
            "ticker x calendar year, labels permuted within stratum only -- "
            "with the selected arm defined by the CANONICAL event set"),
        "population": CANONICAL.name,
        "n_informative_strata": n_live,
        "n_strata_possible": len(TICKERS) * len(YEARS),
        "min_informative_strata": MIN_INFORMATIVE_STRATA,
        "adequately_powered": powered,
        "observed_mean_difference": obs,
        "perm_p": p,
        "observed_rank_difference": obs_rank,
        "perm_p_rank_robustness": p_rank,
        "alpha": ALPHA,
        "n_permutations": N_PERMUTATIONS,
        "random_seed": RANDOM_SEED,
        "pre_declared_interpretation": INTERPRETATION,
        "verdict": verdict,
        "per_ticker": per,
    }
    if legacy is not None:
        agrees = legacy.get("verdict") == verdict
        out["legacy_verdict_9_3"] = legacy.get("verdict")
        out["agrees_with_9_3"] = agrees
        out["reading"] = (INTERPRETATION["agrees_with_9_3"] if agrees
                          else INTERPRETATION["disagrees_with_9_3"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    ed, br = _load_inputs()
    c = _load_canonical()
    br_canon = _canonical_breadth(c)

    prior = LSE / "GST_SEARCH_CONSTRUCT_VALIDITY_NORMALIZATION_2026-09-04.json"
    if not prior.exists():
        raise RefusedError(
            f"missing {prior.name}; this section corrects 9.2 and cannot be "
            "written without the artifact that carries it")
    legacy = json.loads(prior.read_text(encoding="utf-8"))["blocked_like_for_like"]

    doc = {
        "artifact": "GST_SEARCH_CONSTRUCT_VALIDITY_SUPERSESSION",
        "date": "2026-09-04",
        "status": "RETROSPECTIVE_DEVELOPMENT_ONLY",
        "corrects": "audit v1.0 section 9.2",
        "resolves_decision": False,
        "uses_network": False,
        "citation_error": section_citation_error(br, c),
        "population_provenance": section_population_provenance(ed, br, c),
        "canonical_blocked_test": section_canonical_blocked_test(
            ed, br_canon, legacy),
    }

    ce = doc["citation_error"]
    print("=== 10.1 SECTION 9.2 CITED A QUARANTINED FILE ===")
    print(f"  quarantined: {ce['quarantined_file']}")
    print(f"  canonical  : {ce['canonical_file']}")
    print(f"  retained under quarantined / canonical: "
          f"{ce['n_retained_under_quarantined']} / "
          f"{ce['n_retained_under_canonical']}  of {ce['n_audited']}")
    print(f"  headline figures agree: {ce['headline_figures_agree']}   "
          f"composition agrees: {ce['composition_agrees']}")
    print(f"  rejections in common: {ce['n_rejections_in_common']} of "
          f"{ce['n_rejected_under_canonical']}")
    print(f"  rejected by quarantined only: {ce['rejected_by_quarantined_only']}")
    print(f"  rejected by canonical only  : {ce['rejected_by_canonical_only']}")

    pp = doc["population_provenance"]
    print("\n=== 10.2 THE AUDIT'S POPULATION IS GST-LEGACY-V1 ===")
    t = pp["totals"]
    print(f"  audit(legacy) {t['audit_events_legacy']}  canonical "
          f"{t['canonical_events']}  in both {t['in_both']}  "
          f"audit-only {t['audit_only']}  canonical-only {t['canonical_only']}")
    print(f"  selectivity legacy {pp['selectivity_pct_legacy']}%  vs canonical "
          f"{pp['selectivity_pct_canonical']}%")
    print(f"  section 8.1 conclusion survives: "
          f"{pp['section_8_1_conclusion_survives']}")

    bt = doc["canonical_blocked_test"]
    print("\n=== 10.3 THE BLOCKED TEST ON THE CANONICAL POPULATION ===")
    print(f"  informative strata : {bt['n_informative_strata']}/"
          f"{bt['n_strata_possible']}  powered: {bt['adequately_powered']}")
    print(f"  observed mean diff : {bt['observed_mean_difference']}")
    print(f"  permutation p      : {bt['perm_p']}")
    print(f"  rank robustness p  : {bt['perm_p_rank_robustness']}")
    print(f"  VERDICT            : {bt['verdict']}")
    print(f"  legacy 9.3 verdict : {bt.get('legacy_verdict_9_3')}   "
          f"agrees: {bt.get('agrees_with_9_3')}")
    print(f"  reading            : {bt.get('reading')}")

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
