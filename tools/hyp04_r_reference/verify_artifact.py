#!/usr/bin/env python3
"""Verify a freshly computed HYP-04 D10 validation result against the committed artifact.

NOT PRODUCTION CODE. SYNTHETIC DATA ONLY.

Compares every MATERIAL field, not just the classifications:

    fixture identities and coverage      exact
    classifications and split statuses   exact
    tolerance provenance                 exact
    Python and reference numeric fields  under the applicable tolerance
    worst-difference summaries           under a summary tolerance
    refusal outcomes                     exact
    behaviour differences                exact
    package / runtime versions           reported; mismatch is a warning, not a
                                         failure, because CI runs a different OS
    d10/approval fields                  exact

BITWISE EQUALITY IS NOT REQUIRED for continuous quantities. CI runs a different
operating system, R build and BLAS than the workstation that generated the
committed artifact, so demanding identical bits would fail for reasons that have
nothing to do with correctness. Continuous fields are compared under the same
documented tolerances the validation itself uses; discrete fields are exact.

Structurally mirrors tools/hyp01_r_reference/verify_artifact.py, adapted to
HYP-04's artifact field names.

Exit code 1 on any material difference.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# Cross-environment tolerance for reproducing a stored continuous value. Looser
# than the implementation-agreement tolerances on purpose: this asks "did a
# different machine land in the same place", not "do two implementations agree".
CROSS_ENV = {"rtol": 1e-6, "atol": 1e-12}

# Worst-difference summaries are themselves noise-floor quantities; comparing
# them tightly would be comparing noise to noise. They must stay in the same
# regime, and must not grow.
SUMMARY_CEILING = 1e-9

EXACT_TOP_LEVEL = (
    "method_approved", "d10_satisfied", "supported_claim", "fixtures_regenerated_in_r",
)

EXACT_PER_FIXTURE = (
    "classification", "overall_implementation_agreement_status",
    "pr17_covered_fields_status", "satterthwaite_df_status",
    "python_status", "reference_status",
    "python_refusal_reason", "reference_refusal_reason",
    "reference_warned",
)

NUMERIC_VALUE_KEYS = ("target_estimate", "target_variance", "standard_error",
                      "t_statistic", "satterthwaite_df", "p_value")

FAILURES: list[str] = []
NOTES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def close(a, b, tol) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    a, b = float(a), float(b)
    if math.isnan(a) and math.isnan(b):
        return True
    return abs(a - b) <= tol["atol"] + tol["rtol"] * max(abs(a), abs(b))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify a fresh HYP-04 D10 validation against the committed artifact.")
    ap.add_argument("--fresh", required=True)
    ap.add_argument("--committed", required=True)
    a = ap.parse_args(argv)

    fresh = json.loads(Path(a.fresh).read_text(encoding="utf-8"))
    comm = json.loads(Path(a.committed).read_text(encoding="utf-8"))

    print("1. fixture identities and coverage")
    F = {r["fixture_id"]: r for r in fresh["results"]}
    C = {r["fixture_id"]: r for r in comm["results"]}
    if set(F) != set(C):
        fail(f"fixture set differs: only-fresh={sorted(set(F) - set(C))} "
             f"only-committed={sorted(set(C) - set(F))}")
    else:
        ok(f"{len(F)} fixtures, identical identities")
    if len(F) != len(fresh["results"]):
        fail("duplicate fixture ids in the fresh result")

    print("2. classifications and split statuses (exact)")
    bad = 0
    for k in sorted(set(F) & set(C)):
        for key in EXACT_PER_FIXTURE:
            if F[k].get(key) != C[k].get(key):
                fail(f"{k}.{key}: fresh={F[k].get(key)!r} committed={C[k].get(key)!r}")
                bad += 1
    if not bad:
        ok("every classification and split status matches exactly")

    print("3. tolerance provenance (exact)")
    tp_f, tp_c = fresh.get("tolerance_provenance"), comm.get("tolerance_provenance")
    if tp_f != tp_c:
        fail("tolerance_provenance block differs")
    elif tp_f is None:
        fail("tolerance_provenance block is missing")
    else:
        ok("tolerance provenance identical")
        if tp_f.get("preregistered_specifically_for_hyp04") is not False:
            fail("tolerances are not marked as reused rather than preregistered for HYP-04")
        pr18 = tp_f.get("pr18_satterthwaite_df_tolerance_reused_from_hyp01", {})
        if pr18.get("preregistered_for_hyp04") is not False:
            fail("PR #18 df tolerance is not marked preregistered_for_hyp04: false")
    if fresh.get("preregistered_tolerances") != comm.get("preregistered_tolerances"):
        fail("PR #17 tolerance set differs")
    else:
        ok("PR #17 tolerance set (reused) unchanged")

    print("4. numeric fields under the applicable tolerance")
    nbad = 0
    for k in sorted(set(F) & set(C)):
        for side in ("python_values", "reference_values"):
            fv, cv = F[k].get(side), C[k].get(side)
            if fv is None and cv is None:
                continue
            if (fv is None) != (cv is None):
                fail(f"{k}.{side}: present on one side only")
                nbad += 1
                continue
            for key in NUMERIC_VALUE_KEYS:
                if not close(fv.get(key), cv.get(key), CROSS_ENV):
                    fail(f"{k}.{side}.{key}: fresh={fv.get(key)!r} committed={cv.get(key)!r}")
                    nbad += 1
        fci, cci = F[k].get("reference_conf_int"), C[k].get("reference_conf_int")
        if (fci is None) != (cci is None):
            fail(f"{k}.reference_conf_int: present on one side only")
            nbad += 1
        elif fci is not None:
            for i in (0, 1):
                if not close(fci[i], cci[i], CROSS_ENV):
                    fail(f"{k}.reference_conf_int[{i}]: {fci[i]!r} vs {cci[i]!r}")
                    nbad += 1
    if not nbad:
        ok(f"all numeric fields reproduce within rtol={CROSS_ENV['rtol']}")

    print("5. worst-difference summaries")
    sbad = 0
    for k in sorted(set(F) & set(C)):
        ff, cf = F[k].get("fields"), C[k].get("fields")
        if ff is None and cf is None:
            continue
        if (ff is None) != (cf is None):
            fail(f"{k}.fields: present on one side only")
            sbad += 1
            continue
        for name in sorted(set(ff) | set(cf)):
            if name not in ff or name not in cf:
                fail(f"{k}.fields.{name}: present on one side only")
                sbad += 1
                continue
            if ff[name].get("within") is not cf[name].get("within"):
                fail(f"{k}.fields.{name}.within: {ff[name].get('within')} vs {cf[name].get('within')}")
                sbad += 1
            if ff[name].get("tolerance_provenance") != cf[name].get("tolerance_provenance"):
                fail(f"{k}.fields.{name}.tolerance_provenance differs")
                sbad += 1
            for m in ("max_abs_difference", "max_rel_difference"):
                fd = ff[name].get(m)
                if fd is None:
                    continue
                if fd > SUMMARY_CEILING:
                    fail(f"{k}.fields.{name}.{m} = {fd:.3e} exceeds the noise-floor ceiling")
                    sbad += 1
    if not sbad:
        ok(f"every worst-difference summary agrees on pass/fail and stays under {SUMMARY_CEILING:g}")

    print("6. refusal outcomes and behaviour differences (exact)")
    rb = 0
    for k in sorted(set(F) & set(C)):
        if F[k].get("reasons_identical") != C[k].get("reasons_identical"):
            fail(f"{k}.reasons_identical differs")
            rb += 1
        if sorted(F[k].get("reference_warnings") or []) != sorted(C[k].get("reference_warnings") or []):
            fail(f"{k}.reference_warnings differ")
            rb += 1
    fresh_counts = fresh.get("classification_counts", {})
    comm_counts = comm.get("classification_counts", {})
    if fresh_counts != comm_counts:
        fail(f"classification counts differ: {fresh_counts} vs {comm_counts}")
        rb += 1
    if not rb:
        ok("refusal reasons, warnings and class counts identical")

    print("7. package and runtime versions")
    fe = (fresh.get("reference") or {}).get("environment") or {}
    ce = (comm.get("reference") or {}).get("environment") or {}
    for key in sorted(set(fe) | set(ce)):
        if fe.get(key) != ce.get(key):
            NOTES.append(f"{key}: fresh={fe.get(key)} committed={ce.get(key)}")
    # clubSandwich is the reference whose agreement defines the result: it must match.
    if fe.get("clubSandwich") != ce.get("clubSandwich"):
        fail(f"clubSandwich version differs: {fe.get('clubSandwich')} vs {ce.get('clubSandwich')}")
    else:
        ok(f"clubSandwich {fe.get('clubSandwich')} matches the committed artifact")
    if NOTES:
        print("  note  environment differences (expected across OS, not a failure):")
        for n in NOTES:
            print(f"          {n}")

    print("8. d10/approval fields (exact)")
    tb = 0
    for key in EXACT_TOP_LEVEL:
        if fresh.get(key) != comm.get(key):
            fail(f"{key}: fresh={fresh.get(key)!r} committed={comm.get(key)!r}")
            tb += 1
    for doc, label in ((fresh, "fresh"), (comm, "committed")):
        if doc.get("method_approved") is not False:
            fail(f"{label}: method_approved is not False")
            tb += 1
        iv = doc.get("implementation_validation") or {}
        if iv.get("production_selection_approved") is not False:
            fail(f"{label}: production_selection_approved is not False")
            tb += 1
        if iv.get("gate_status_changed") is not False:
            fail(f"{label}: gate_status_changed is not False")
            tb += 1
    if not tb:
        ok("nothing approved, gate status unchanged on both sides")

    print()
    if FAILURES:
        print(f"ARTIFACT REPRODUCTION FAILED: {len(FAILURES)} difference(s)")
        return 1
    print(f"artifact reproduces: {len(F)} fixtures, all material fields verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
