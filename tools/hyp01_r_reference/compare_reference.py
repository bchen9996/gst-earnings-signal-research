#!/usr/bin/env python3
"""Compare the study-written Python CR2 / Satterthwaite against the R reference.

NOT PRODUCTION CODE. SYNTHETIC DATA ONLY.

The Python side is recomputed here from the committed runner -- not read out of
any stored artifact -- and compared against clubSandwich's output for the same
fixture bytes.

TOLERANCE POLICY, and one honest gap in it
------------------------------------------
Covariance, standard error, t-statistic and p-value are compared under the
tolerances preregistered in PR #17 and committed in the runner's TOLERANCES
dict. They are used exactly as written and are not reinterpreted here.

The preregistered set defines degrees of freedom as `exact_integer_equality`.
That rule was written for CR1, whose inference df is the integer G-1. The
Satterthwaite df is a continuous quantity, so the preregistered rule cannot be
applied to it: there is no preregistered tolerance for this field.

Rather than silently borrow a tolerance meant for another quantity, a separate
one is declared below and labelled as NEW IN THIS PR. It was fixed in source
before the comparison was executed for the first time, and it is reported
separately from the preregistered results so no reader can mistake it for part
of the PR #17 preregistration.
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

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "hyp01_inference_feasibility.py"

# NOT preregistered in PR #17. Declared here, in source, before this comparison
# was ever run, because the preregistered df rule (exact integer equality) was
# written for CR1's integer G-1 and cannot express agreement on a continuous
# Satterthwaite df. Reported separately from the preregistered fields.
SATTERTHWAITE_DF_TOLERANCE = {
    "rtol": 1e-8,
    "atol": 1e-10,
    "preregistered_in_pr17": False,
    "introduced_by": "PR: independent R reference validation",
    "declared_before_first_comparison_run": True,
    "why_not_the_preregistered_df_rule": (
        "TOLERANCES['degrees_of_freedom'] is exact_integer_equality, which "
        "applies to CR1's integer inference df G-1. The Satterthwaite df is "
        "continuous; exact equality is not a meaningful cross-implementation "
        "criterion for it and no preregistered tolerance covers this field."),
}

CLASSES = (
    "MATCH_WITHIN_PREREGISTERED_TOLERANCE",
    "REFERENCE_BEHAVIOR_DIFFERENCE",
    "PYTHON_IMPLEMENTATION_DEFECT",
    "INTERCHANGE_OR_SPECIFICATION_DEFECT",
    "REFUSED_BY_BOTH",
    "UNRESOLVED",
)


def load_runner():
    spec = importlib.util.spec_from_file_location("hyp01_feas_runner", RUNNER)
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
    """Recompute the Python CR2 / Satterthwaite for one fixture."""
    name = fixture["fixture_id"]
    specs = dict(R.FIXTURE_SPECS)
    fx = R.make_fixture(name, **specs[name])
    X, y, g = fx["X"], fx["y"], fx["cluster_index"]

    refuse, reason = R.refusal_check(X, y, g)
    if refuse:
        return {"status": "PYTHON_REFUSED", "refusal_reason": reason}

    j = fixture["target_index_0based"]
    beta, V, G = R.cr_vcov(X, y, g, "CR2")
    var = float(V[j, j])
    se = math.sqrt(var)
    t = float(beta[j]) / se
    c = np.zeros(X.shape[1])
    c[j] = 1.0
    df = R.satterthwaite_df(X, g, c)
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
        "tolerance": "satterthwaite_df (NEW IN THIS PR, not preregistered)",
        "within": within([py["satterthwaite_df"]], [ref["satterthwaite_df"]],
                         SATTERTHWAITE_DF_TOLERANCE),
        **discrepancy([py["satterthwaite_df"]], [ref["satterthwaite_df"]])}

    rec["fields"] = fields
    keys = ("target_estimate", "target_variance", "standard_error",
            "t_statistic", "satterthwaite_df", "p_value")
    rec["python_values"] = {k: py[k] for k in keys}
    rec["reference_values"] = {k: ref[k] for k in keys}
    rec["reference_conf_int"] = (
        [num(rr["conf_int_low"]), num(rr["conf_int_high"])]
        if rr.get("conf_int_defined") else None)

    preregistered = [k for k in fields if k != "satterthwaite_df"]
    rec["all_preregistered_fields_within_tolerance"] = all(fields[k]["within"] for k in preregistered)
    rec["satterthwaite_df_within_declared_tolerance"] = fields["satterthwaite_df"]["within"]

    if rec["all_preregistered_fields_within_tolerance"]:
        rec["classification"] = "MATCH_WITHIN_PREREGISTERED_TOLERANCE"
        if not rec["satterthwaite_df_within_declared_tolerance"]:
            rec["classification"] = "UNRESOLVED"
            rec["explanation"] = ("Covariance, SE, t and p agree under the preregistered "
                                  "tolerances, but the Satterthwaite df does not agree under "
                                  "the separately declared tolerance. Requires diagnosis.")
    else:
        failed = [k for k in preregistered if not fields[k]["within"]]
        rec["classification"] = "UNRESOLVED"
        rec["failed_fields"] = failed
        rec["explanation"] = ("Disagreement outside the preregistered tolerances on: "
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
    matched = [r["fixture_id"] for r in results
               if r["classification"] == "MATCH_WITHIN_PREREGISTERED_TOLERANCE"]
    unresolved = [r["fixture_id"] for r in results if r["classification"] == "UNRESOLVED"]

    runner_bytes = RUNNER.read_bytes()
    return {
        "artifact": "GST HYP-01 independent R reference validation",
        "version": "1.0",
        "status": ("SYNTHETIC_IMPLEMENTATION_VALIDATION_ONLY_"
                   "NO_METHOD_APPROVED_NO_LOCK_ACTIVATED_F5_OPEN"),
        "what_this_is": (
            "An implementation-agreement check between the study-written Python CR2 / "
            "Satterthwaite code and clubSandwich, on a prespecified synthetic fixture "
            "matrix, under the preregistered tolerances. It is not evidence that CR2 is "
            "scientifically preferable, and it approves nothing."),
        "method_approved": False,
        "lock_activated": False,
        "f5_status": "OPEN (unchanged by this validation)",
        "operative_lock": "Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.0.json (v1.0, unchanged)",
        "synthetic_data_only": True,
        "repository_research_artifact_loaded": False,
        "python_runner_sha256": hashlib.sha256(runner_bytes.replace(b"\r\n", b"\n")).hexdigest(),
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
        "preregistered_tolerances": tol,
        "preregistered_tolerances_used_as_written": True,
        "satterthwaite_df_tolerance": SATTERTHWAITE_DF_TOLERANCE,
        "classification_counts": counts,
        "fixtures_matched_within_preregistered_tolerance": matched,
        "unresolved_fixtures": unresolved,
        "cr3_validated": False,
        "wild_cluster_bootstrap_validated": False,
        "cr3_and_bootstrap_note": (
            "Not validated here. clubSandwich supplies CR3, but this PR validates only "
            "the CR2 + Satterthwaite path that was actually compared. CR2 agreement is "
            "never treated as evidence about CR3 or the wild cluster bootstrap."),
        "results": results,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare Python CR2/Satterthwaite with the R reference.")
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    R = load_runner()
    R.assert_not_canonical(a.out)

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
