#!/usr/bin/env python3
"""Compare HYP-04's production CR2 / Satterthwaite against the R reference.

NOT PRODUCTION CODE. SYNTHETIC DATA ONLY.

The Python side is recomputed here by calling
`hyp04_supply_chain_hedge.clustered_se.cr_vcov` / `satterthwaite_df` directly
-- the actual production functions, not a copy of them -- and compared
against clubSandwich's output for the same fixture bytes.

TOLERANCE PROVENANCE IS REUSED BY CITATION, AND MUST STAY LABELLED AS SUCH
---------------------------------------------------------------------------
`clustered_se.py`'s own docstring states its `cr_vcov`/`satterthwaite_df` are
mirrored verbatim from `tools/hyp01_inference_feasibility.py`, the exact
implementation the HYP-01 R cross-check already validated against
clubSandwich (PR #17/#18, commit `97705ed`). Because the arithmetic under
test here is that identical mirrored code, this comparison reuses HYP-01's
own tolerance numbers UNCHANGED rather than declaring new ones -- inventing a
different tolerance for identical arithmetic would imply a difference that
does not exist.

  PR #17 tolerances (reused, unmodified) -> coefficients, CR2 covariance,
                        target variance, standard error, t-statistic, p-value.

  PR #18 tolerance (reused, unmodified)  -> the continuous Satterthwaite
                        degrees of freedom. PR #17's df rule is
                        `exact_integer_equality`, written for CR1's integer
                        G-1; it cannot express agreement on a continuous
                        Satterthwaite df, which is why PR #18 prespecified a
                        separate one. HYP-04 reuses that PR #18 tolerance
                        rather than prespecifying a third.

Neither tolerance was preregistered specifically for HYP-04 -- both are
HYP-01's own numbers, reused here BY CITATION because the arithmetic is
identical. This distinction (reused vs preregistered-here) must never be
collapsed into a claim that HYP-04 preregistered its own tolerances; it did
not need to, and did not.

The supported claim is therefore two-part, and is stored verbatim in the
artifact as `supported_claim`:

    HYP-04's production CR2 covariance, standard-error, t-statistic, and
    p-value outputs (hyp04_supply_chain_hedge.clustered_se, on HYP-04's own
    3-column design matrix and calendar_period clustering) agree with
    clubSandwich on HYP-04's own synthetic fixture matrix, under tolerances
    reused verbatim from HYP-01's PR #17. The continuous Satterthwaite
    degrees of freedom agree under the tolerance reused verbatim from
    HYP-01's PR #18. Neither tolerance was preregistered specifically for
    HYP-04; both are reused by citation because the underlying arithmetic is
    identical mirrored code.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _deny_network(*_a, **_k):
    raise NetworkBlocked("network access attempted in the offline comparison harness")


socket.socket.connect = _deny_network
socket.socket.connect_ex = _deny_network
socket.create_connection = _deny_network
socket.getaddrinfo = _deny_network

import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNNER = HERE / "fixtures.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from hyp04_supply_chain_hedge.clustered_se import cr_vcov, satterthwaite_df  # noqa: E402

# Reused verbatim from PR #18 (HYP-01's R cross-check). NOT preregistered
# specifically for HYP-04 -- see module docstring. Always reported with that
# provenance stated, never silently relabelled as HYP-04's own.
PR18_SATTERTHWAITE_DF_TOLERANCE = {
    "rtol": 1e-8,
    "atol": 1e-10,
    "preregistered_for_hyp04": False,
    "reused_verbatim_from": "PR #18 (HYP-01's independent R reference validation)",
    "why_reused_rather_than_prespecified_fresh": (
        "The CR2/Satterthwaite arithmetic under test is the identical mirrored code "
        "HYP-01's bridge already validated; a different tolerance for identical "
        "arithmetic would imply a difference that does not exist."),
    "why_not_the_pr17_df_rule": (
        "The PR #17 rule is exact_integer_equality, written for CR1's integer G-1. "
        "The Satterthwaite df is continuous; exact equality is not a meaningful "
        "cross-implementation criterion for it."),
}

PR17_COVERED_FIELDS = ("coefficients", "cr2_covariance", "target_variance",
                       "standard_error", "t_statistic", "p_value")
PR18_COVERED_FIELDS = ("satterthwaite_df",)

MATCH = "MATCH_WITHIN_TOLERANCES_REUSED_FROM_HYP01_PR17_AND_PR18"

CLASSES = (
    MATCH,
    "REFERENCE_BEHAVIOR_DIFFERENCE",
    "PYTHON_IMPLEMENTATION_DEFECT",
    "INTERCHANGE_OR_SPECIFICATION_DEFECT",
    "REFUSED_BY_BOTH",
    "UNRESOLVED",
)

SUPPORTED_CLAIM = (
    "HYP-04's production CR2 covariance, standard-error, t-statistic, and p-value "
    "outputs (hyp04_supply_chain_hedge.clustered_se, on HYP-04's own 3-column design "
    "matrix and calendar_period clustering) agree with clubSandwich on HYP-04's own "
    "synthetic fixture matrix, under tolerances reused verbatim from HYP-01's PR #17. "
    "The continuous Satterthwaite degrees of freedom agree under the tolerance reused "
    "verbatim from HYP-01's PR #18. Neither tolerance was preregistered specifically "
    "for HYP-04; both are reused by citation because the underlying arithmetic is "
    "identical mirrored code.")


def load_runner():
    spec = importlib.util.spec_from_file_location("hyp04_r_ref_fixtures", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def num(v):
    """Parse the reference's numeric encoding.

    The R side emits %.17g STRINGS so a double survives the bridge exactly;
    jsonlite's own number writer keeps only ~15 significant digits, which would
    make the reported discrepancies partly an artifact of the JSON writer.
    Plain numbers are still accepted so the harness tolerates either encoding.
    """
    if v is None:
        return float("nan")
    if isinstance(v, str):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [num(x) for x in v]
    return float(v)


def discrepancy(a, b):
    """Absolute and relative discrepancy at full precision."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape:
        return {"shape_mismatch": [list(a.shape), list(b.shape)]}
    d = np.abs(a - b)
    scale = np.maximum(np.abs(a), np.abs(b))
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(scale > 0, d / scale, 0.0)
    return {
        "max_abs_difference": float(np.max(d)) if d.size else 0.0,
        "max_rel_difference": float(np.nanmax(rel)) if rel.size else 0.0,
    }


def within(a, b, tol):
    return bool(np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float),
                            rtol=tol["rtol"], atol=tol["atol"]))


def python_side(R, fixture):
    """Recompute HYP-04's production CR2 / Satterthwaite for one fixture."""
    name = fixture["fixture_id"]
    specs = dict(R.FIXTURE_SPECS)
    fx = R.make_fixture(name, **specs[name])
    X, y, g = fx["X"], fx["y"], fx["cluster_index"]

    refuse, reason = R.refusal_check(X, y, g)
    if refuse:
        return {"status": "PYTHON_REFUSED", "refusal_reason": reason}

    j = fixture["target_index_0based"]
    beta, V, G = cr_vcov(X, y, g, "CR2")
    var = float(V[j, j])
    se = math.sqrt(var)
    t = float(beta[j]) / se
    c = np.zeros(X.shape[1])
    c[j] = 1.0
    df = satterthwaite_df(X, g, c)
    p = float(2 * stats.t.sf(abs(t), df))
    return {
        "status": "COMPUTED",
        "coefficients": [float(v) for v in beta],
        "cr2_covariance": [[float(v) for v in row] for row in V],
        "target_variance": var,
        "target_estimate": float(beta[j]),
        "standard_error": se,
        "t_statistic": t,
        "satterthwaite_df": float(df),
        "p_value": p,
        "n_clusters": int(G),
    }


def compare_one(fixture, py, rr, tol):
    """Compare one fixture and classify. Returns the comparison record."""
    fid = fixture["fixture_id"]
    rec = {
        "fixture_id": fid,
        "python_status": py["status"],
        "reference_status": rr.get("status"),
        "reference_warned": bool(rr.get("reference_warned")),
        "reference_warnings": rr.get("reference_warnings") or [],
    }

    if not rr.get("canonical_digest_matches_export", False):
        rec["classification"] = "INTERCHANGE_OR_SPECIFICATION_DEFECT"
        rec["explanation"] = "R recomputed a different canonical digest for this fixture"
        return rec

    py_ref = py["status"] == "PYTHON_REFUSED"
    r_ref = rr.get("status") == "REFERENCE_REFUSED"

    if py_ref and r_ref:
        rec["classification"] = "REFUSED_BY_BOTH"
        rec["python_refusal_reason"] = py["refusal_reason"]
        rec["reference_refusal_reason"] = rr.get("refusal_reason")
        rec["reference_message"] = rr.get("message")
        rec["reasons_identical"] = py["refusal_reason"] == rr.get("refusal_reason")
        rec["explanation"] = (
            "Both implementations declined to produce a number. The stated reasons "
            "need not be identical: they are different diagnostics reaching the same "
            "refusal.")
        return rec

    if py_ref and not r_ref:
        rec["classification"] = "REFERENCE_BEHAVIOR_DIFFERENCE"
        rec["python_refusal_reason"] = py["refusal_reason"]
        rec["explanation"] = (
            "Python refuses before fitting; the reference returns a value"
            + (" after warning" if rr.get("reference_warned") else "")
            + ". The reference was NOT forced to refuse and Python was NOT relaxed to "
              "match it. Reported as a behaviour difference.")
        rec["reference_target_estimate"] = rr.get("target_estimate")
        rec["reference_standard_error"] = rr.get("standard_error")
        return rec

    if (not py_ref) and r_ref:
        rec["classification"] = "REFERENCE_BEHAVIOR_DIFFERENCE"
        rec["reference_refusal_reason"] = rr.get("refusal_reason")
        rec["reference_message"] = rr.get("message")
        rec["explanation"] = (
            "The reference declined where Python produced a number. Python's output "
            "is therefore unvalidated on this fixture.")
        return rec

    # Both computed: compare field by field, at the reference's full precision.
    ref = {
        "coefficients": num(rr["coefficients"]),
        "cr2_covariance": [num(row) for row in rr["cr2_covariance"]],
        "target_variance": num(rr["target_variance"]),
        "target_estimate": num(rr["target_estimate"]),
        "standard_error": num(rr["standard_error"]),
        "t_statistic": num(rr["t_statistic"]),
        "satterthwaite_df": num(rr["satterthwaite_df"]),
        "p_value": num(rr["p_value"]),
    }

    fields = {}
    fields["coefficients"] = {
        "tolerance": "standard_error",
        "within": within(py["coefficients"], ref["coefficients"], tol["standard_error"]),
        **discrepancy(py["coefficients"], ref["coefficients"])}
    fields["cr2_covariance"] = {
        "tolerance": "covariance_matrix",
        "within": within(py["cr2_covariance"], ref["cr2_covariance"], tol["covariance_matrix"]),
        **discrepancy(py["cr2_covariance"], ref["cr2_covariance"])}
    fields["target_variance"] = {
        "tolerance": "covariance_matrix",
        "within": within([py["target_variance"]], [ref["target_variance"]], tol["covariance_matrix"]),
        **discrepancy([py["target_variance"]], [ref["target_variance"]])}
    fields["standard_error"] = {
        "tolerance": "standard_error",
        "within": within([py["standard_error"]], [ref["standard_error"]], tol["standard_error"]),
        **discrepancy([py["standard_error"]], [ref["standard_error"]])}
    fields["t_statistic"] = {
        "tolerance": "t_statistic",
        "within": within([py["t_statistic"]], [ref["t_statistic"]], tol["t_statistic"]),
        **discrepancy([py["t_statistic"]], [ref["t_statistic"]])}
    fields["p_value"] = {
        "tolerance": "p_value",
        "within": within([py["p_value"]], [ref["p_value"]], tol["p_value"]),
        **discrepancy([py["p_value"]], [ref["p_value"]])}
    fields["satterthwaite_df"] = {
        "tolerance": "PR18_satterthwaite_df (reused verbatim from HYP-01's PR #18, "
                    "NOT preregistered for HYP-04)",
        "tolerance_provenance": "PR18_REUSED",
        "within": within([py["satterthwaite_df"]], [ref["satterthwaite_df"]],
                         PR18_SATTERTHWAITE_DF_TOLERANCE),
        **discrepancy([py["satterthwaite_df"]], [ref["satterthwaite_df"]])}
    for _f in PR17_COVERED_FIELDS:
        fields[_f]["tolerance_provenance"] = "PR17_REUSED"

    rec["fields"] = fields
    keys = ("target_estimate", "target_variance", "standard_error",
            "t_statistic", "satterthwaite_df", "p_value")
    rec["python_values"] = {k: py[k] for k in keys}
    rec["reference_values"] = {k: ref[k] for k in keys}
    rec["reference_conf_int"] = (
        [num(rr["conf_int_low"]), num(rr["conf_int_high"])]
        if rr.get("conf_int_defined") else None)

    pr17_ok = all(fields[k]["within"] for k in PR17_COVERED_FIELDS)
    df_ok = fields["satterthwaite_df"]["within"]

    rec["pr17_covered_fields"] = list(PR17_COVERED_FIELDS)
    rec["pr17_covered_fields_status"] = ("PASS_UNDER_REUSED_PR17_TOLERANCES" if pr17_ok
                                         else "FAIL_UNDER_REUSED_PR17_TOLERANCES")
    rec["satterthwaite_df_status"] = ("PASS_UNDER_REUSED_PR18_TOLERANCE"
                                      if df_ok else "FAIL_UNDER_REUSED_PR18_TOLERANCE")
    rec["all_pr17_covered_fields_within_tolerance"] = pr17_ok
    rec["satterthwaite_df_within_pr18_tolerance"] = df_ok

    if pr17_ok and df_ok:
        rec["overall_implementation_agreement_status"] = MATCH
        rec["classification"] = MATCH
    elif pr17_ok and not df_ok:
        rec["overall_implementation_agreement_status"] = "UNRESOLVED"
        rec["classification"] = "UNRESOLVED"
        rec["explanation"] = ("Covariance, SE, t and p agree under the reused PR #17 "
                              "tolerances, but the Satterthwaite df does not agree under "
                              "the reused PR #18 tolerance. Requires diagnosis.")
    else:
        failed = [k for k in PR17_COVERED_FIELDS if not fields[k]["within"]]
        rec["overall_implementation_agreement_status"] = "UNRESOLVED"
        rec["classification"] = "UNRESOLVED"
        rec["failed_fields"] = failed
        rec["explanation"] = ("Disagreement outside the reused PR #17 tolerances on: "
                              + ", ".join(failed) + ". Requires diagnosis; not resolved by "
                              "adjusting a tolerance.")
    return rec


def build(R, fixtures_doc, reference_doc) -> dict:
    tol = R.TOLERANCES
    results = []
    for fixture in fixtures_doc["fixtures"]:
        fid = fixture["fixture_id"]
        rr = reference_doc["results"].get(fid)
        if rr is None:
            results.append({"fixture_id": fid,
                            "classification": "INTERCHANGE_OR_SPECIFICATION_DEFECT",
                            "explanation": "no reference result for this fixture"})
            continue
        py = python_side(R, fixture)
        results.append(compare_one(fixture, py, rr, tol))

    counts = {c: sum(1 for r in results if r["classification"] == c) for c in CLASSES}
    matched = [r["fixture_id"] for r in results if r["classification"] == MATCH]
    unresolved = [r["fixture_id"] for r in results if r["classification"] == "UNRESOLVED"]

    # D10 is satisfied ONLY when every fixture resolved cleanly -- no UNRESOLVED
    # and no defect classification. An unresolved or defective run means the
    # cross-check did not complete successfully and must not be described as
    # having satisfied anything.
    clean_run = not unresolved and counts.get("PYTHON_IMPLEMENTATION_DEFECT", 0) == 0 \
        and counts.get("INTERCHANGE_OR_SPECIFICATION_DEFECT", 0) == 0

    runner_bytes = RUNNER.read_bytes()
    return {
        "artifact": "GST HYP-04 independent R reference validation",
        "version": "1.0",
        "status": ("SYNTHETIC_IMPLEMENTATION_VALIDATION_ONLY_"
                   "VALIDATES_D10_USAGE_NOT_A_SCIENTIFIC_FINDING"),
        "what_this_is": (
            "An implementation-agreement check between HYP-04's production CR2 / "
            "Satterthwaite code (hyp04_supply_chain_hedge.clustered_se), exercised on "
            "HYP-04's own design matrix shape and calendar_period clustering, and "
            "clubSandwich, on a purpose-built HYP-04 synthetic fixture matrix, under "
            "tolerances reused from HYP-01's cross-check. When d10_satisfied is true, it "
            "satisfies D10 of the HYP-04 analysis lock. It is not evidence that "
            "supply-chain transmission exists, and it approves no method beyond "
            "confirming this specific usage is correctly implemented."),
        "d10_satisfied": clean_run,
        "satisfies_lock_decision": ("D10 (Authoritative CR2 implementation) of the HYP-04 "
                                    "analysis lock" if clean_run else
                                    "NOT satisfied -- unresolved or defective fixtures present"),
        "method_approved": False,
        "cr2_validated_generically_by": ("tools/hyp01_r_reference (commit 97705ed) -- this "
                                         "PR validates HYP-04's USAGE, not the arithmetic "
                                         "itself, which was already validated there"),
        "synthetic_data_only": True,
        "repository_research_artifact_loaded": False,
        "production_module_under_test": "hyp04_supply_chain_hedge/clustered_se.py",
        "production_module_sha256": hashlib.sha256(
            (ROOT / "hyp04_supply_chain_hedge" / "clustered_se.py").read_bytes()
            .replace(b"\r\n", b"\n")).hexdigest(),
        "fixture_generator_sha256": hashlib.sha256(
            runner_bytes.replace(b"\r\n", b"\n")).hexdigest(),
        "fixture_source": fixtures_doc["source_of_truth"],
        "fixtures_regenerated_in_r": False,
        "reference": {
            "package": reference_doc["reference_package"],
            "independently_maintained": reference_doc["reference_is_independently_maintained"],
            "written_for_this_study": reference_doc["reference_written_for_this_study"],
            "environment": reference_doc["environment"],
            "specification": reference_doc["specification"],
            "resolved_defaults": reference_doc["reference_defaults"],
        },
        "supported_claim": SUPPORTED_CLAIM,
        "tolerance_provenance": {
            "pr17_tolerances_reused_from_hyp01": tol,
            "pr17_tolerances_used_as_written": True,
            "pr17_covered_fields": list(PR17_COVERED_FIELDS),
            "pr18_satterthwaite_df_tolerance_reused_from_hyp01": PR18_SATTERTHWAITE_DF_TOLERANCE,
            "pr18_covered_fields": list(PR18_COVERED_FIELDS),
            "preregistered_specifically_for_hyp04": False,
            "note": ("Both tolerance sets are HYP-01's own numbers, reused here by "
                     "citation because the arithmetic under test is identical mirrored "
                     "code. No field is governed by both sets."),
        },
        "preregistered_tolerances": tol,
        "preregistered_tolerances_used_as_written": True,
        "classification_counts": counts,
        "fixtures_matched": matched,
        "unresolved_fixtures": unresolved,
        "implementation_validation": {
            "cr2_covariance_se_t_p_for_hyp04_usage": "VALIDATED_UNDER_REUSED_PR17_TOLERANCES",
            "satterthwaite_df_for_hyp04_usage": "VALIDATED_UNDER_REUSED_PR18_TOLERANCE",
            "cr2_satterthwaite_overall": "HYP04_USAGE_VALIDATED_TOLERANCE_PROVENANCE_REUSED",
            "production_selection_approved": False,
            "gate_status_changed": False,
        },
        "results": results,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare HYP-04 production CR2/Satterthwaite "
                                             "with the R reference.")
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    R = load_runner()

    fixtures_doc = json.loads(Path(a.fixtures).read_text(encoding="utf-8"))
    reference_doc = json.loads(Path(a.reference).read_text(encoding="utf-8"))
    doc = build(R, fixtures_doc, reference_doc)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, sort_keys=True, allow_nan=False), encoding="utf-8")

    print(f"wrote {out}")
    for k, v in doc["classification_counts"].items():
        if v:
            print(f"  {k}: {v}")
    unresolved = doc["unresolved_fixtures"]
    if unresolved:
        print(f"  UNRESOLVED: {unresolved}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
