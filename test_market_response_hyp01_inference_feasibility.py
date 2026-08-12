#!/usr/bin/env python3
# Computational tests for the HYP-01 inference-feasibility study.
#
# These EXECUTE the committed reproduction runner and recompute its results.
# They do not trust declarations in the generated artifact: every numerical
# claim is either recomputed here or checked arithmetically against the
# committed full-precision artifact.
#
# Offline. Sockets blocked. Synthetic fixtures only. No repository research
# observation is read. Routine CI runs a small deterministic smoke grid, not
# the multi-minute full-precision grid.
#
# Run directly: python test_market_response_hyp01_inference_feasibility.py

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline feasibility test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

ROOT = Path(__file__).resolve().parent
LS = ROOT / "Live Signal Engine"
RUNNER = ROOT / "tools" / "hyp01_inference_feasibility.py"
INV = LS / "GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json"
REP = LS / "GST_HYP01_SYNTHETIC_VALIDATION_REPORT_v1.0_DRAFT.md"
MATRIX = LS / "GST_HYP01_AUTHORIZER_DECISION_MATRIX_v1.0_DRAFT.md"
MTX = LS / "GST_HYP01_AUTHORIZER_DECISION_MATRIX_v1.0_DRAFT.md"
LOCK10 = LS / "GST_HYP01_ANALYSIS_LOCK_v1.0.json"
PROPOSED = LS / "GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json"
SIGNOFF = LS / "GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md"
REGISTRY = LS / "Market_Response_Event_Registry" / "registry.jsonl"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def load_runner():
    spec = importlib.util.spec_from_file_location("hyp01_feas_runner", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = load_runner()
INVENTORY = json.loads(INV.read_text(encoding="utf-8"))

LOCKED_24 = ["AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "CTSH", "DELL", "DVN", "GME",
             "GOOGL", "GPN", "INTC", "LDOS", "MSFT", "NCLH", "NKE", "QCOM", "SBUX", "STZ",
             "SYK", "TSLA", "TTWO", "UAL"]


# ---------------------------------------------------------------- 1. CR1 vs statsmodels
def test_1_recompute_cr1_against_statsmodels() -> None:
    import numpy as np
    import statsmodels.api as sm
    from scipy import stats

    fx = R.make_fixture("F01_balanced_24c_72n", n_clusters=24, n_obs=72, shape="balanced")
    X, y, g = fx["X"], fx["y"], fx["cluster_index"]
    beta, V, G = R.cr_vcov(X, y, g, "CR1")
    res = sm.OLS(y, X).fit(cov_type="cluster",
                           cov_kwds={"groups": g, "use_correction": True, "df_correction": True},
                           use_t=True)
    tol = R.TOLERANCES
    se = np.sqrt(np.diag(V))
    t = beta / se
    df = G - 1
    sm_df = int(getattr(res, "df_resid_inference", res.df_resid))
    p = 2 * stats.t.sf(np.abs(t), df)
    check("1a. recomputed CR1 covariance matches statsmodels",
          bool(np.allclose(V, res.cov_params(), **tol["covariance_matrix"])))
    check("1b. recomputed CR1 standard errors match", bool(np.allclose(se, res.bse, **tol["standard_error"])))
    check("1c. recomputed CR1 t-statistics match", bool(np.allclose(t, res.tvalues, **tol["t_statistic"])))
    check("1d. inference df matches statsmodels df_resid_inference (G-1)", sm_df == df,
          f"{sm_df} vs {df}")
    check("1e. recomputed CR1 p-values match", bool(np.allclose(p, res.pvalues, **tol["p_value"])))
    # and the artifact's per-fixture verdict must agree with what we just recomputed
    rec = INVENTORY["cr1_reference_comparison"]["F01_balanced_24c_72n"]
    check("1f. artifact's CR1 verdict agrees with live recomputation",
          rec["all_within_preregistered_tolerance"] is True)


# ---------------------------------------------------------------- 2. refusals
def test_2_recompute_all_five_refusals() -> None:
    expected = {
        "F05_near_collinear_full_rank": "ILL_CONDITIONED_DESIGN",
        "F06_exactly_rank_deficient": "RANK_DEFICIENT_DESIGN",
        "F07_zero_variance_predictor": "ZERO_VARIANCE_PREDICTOR",
        "F08_perfect_fit": "DEGENERATE_FIT_RESIDUAL_VARIANCE_AT_NOISE_FLOOR",
        "F09_missing_value": "NONFINITE_VALUE_PRESENT",
    }
    specs = dict(R.FIXTURE_SPECS)
    seen = {}
    for name, want in expected.items():
        fx = R.make_fixture(name, **specs[name])
        refuse, reason = R.refusal_check(fx["X"], fx["y"], fx["cluster_index"])
        seen[name] = reason
        check(f"2a. {name} refuses with {want}", refuse and reason == want, f"got {reason}")
    check("2b. all five refusal reasons are distinct", len(set(seen.values())) == 5, str(seen))
    check("2c. artifact records the same refusal reasons",
          all(INVENTORY["refusal_outcomes"][n]["reason"] == r for n, r in seen.items()))
    # a runnable fixture must NOT refuse
    fx = R.make_fixture("F01_balanced_24c_72n", **specs["F01_balanced_24c_72n"])
    refuse, _ = R.refusal_check(fx["X"], fx["y"], fx["cluster_index"])
    check("2d. a well-conditioned fixture does not refuse", not refuse)


# ---------------------------------------------------------------- 3. invariance / sign
def test_3_recompute_invariance_and_sign() -> None:
    import numpy as np
    specs = dict(R.FIXTURE_SPECS)
    fx = R.make_fixture("F10_row_permutation_source", **specs["F10_row_permutation_source"])
    X, y, g, lab = fx["X"], fx["y"], fx["cluster_index"], fx["labels"]
    b0, V0, _ = R.cr_vcov(X, y, g, "CR1")

    rng = np.random.default_rng(11)
    perm = rng.permutation(len(y))
    b1, V1, _ = R.cr_vcov(X[perm], y[perm], g[perm], "CR1")
    check("3a. row permutation leaves beta and covariance unchanged",
          bool(np.allclose(b0, b1, rtol=1e-12, atol=1e-14) and np.allclose(V0, V1, rtol=1e-10, atol=1e-14)))

    remap = {c: f"ZZZ_{i:03d}" for i, c in enumerate(np.unique(lab))}
    _, inv_idx = np.unique(np.array([remap[c] for c in lab]), return_inverse=True)
    b2, V2, _ = R.cr_vcov(X, y, inv_idx, "CR1")
    check("3b. cluster relabelling leaves beta and covariance unchanged",
          bool(np.allclose(b0, b2, rtol=1e-12, atol=1e-14) and np.allclose(V0, V2, rtol=1e-10, atol=1e-14)))

    pos = R.make_fixture("F14_positive_hypothetical_effect", **specs["F14_positive_hypothetical_effect"])
    neg = R.make_fixture("F12_sign_reversed_effect", **specs["F12_sign_reversed_effect"])
    bp, _, _ = R.cr_vcov(pos["X"], pos["y"], pos["cluster_index"], "CR1")
    bn, _, _ = R.cr_vcov(neg["X"], neg["y"], neg["cluster_index"], "CR1")
    check("3c. sign-reversed fixture yields an opposite-signed slope",
          float(bp[1]) > 0 > float(bn[1]), f"pos={bp[1]:.4f} neg={bn[1]:.4f}")


# ---------------------------------------------------------------- 4. bootstrap
def test_4_recompute_bootstrap_seed_behaviour() -> None:
    specs = dict(R.FIXTURE_SPECS)
    fx = R.make_fixture("F17_bootstrap_seed_repeat", **specs["F17_bootstrap_seed_repeat"])
    X, y, g = fx["X"], fx["y"], fx["cluster_index"]
    a = R.wcr_bootstrap_t(X, y, g, 1, B=199, seed=R.BOOTSTRAP["seed_default"])
    b = R.wcr_bootstrap_t(X, y, g, 1, B=199, seed=R.BOOTSTRAP["seed_default"])
    c = R.wcr_bootstrap_t(X, y, g, 1, B=199, seed=R.BOOTSTRAP["seed_default"] + 1)
    check("4a. same seed reproduces the identical bootstrap draw vector",
          a["bootstrap_t_digest"] == b["bootstrap_t_digest"])
    check("4b. same seed reproduces the identical derived p-value", a["p_value"] == b["p_value"])
    check("4c. a different seed changes the underlying draw vector",
          a["bootstrap_t_digest"] != c["bootstrap_t_digest"])
    # Deliberately NOT asserted: that a different seed changes the p-value. The
    # bootstrap p-value lies on a coarse 1/(B+1) grid and collisions are legitimate.
    check("4d. p-value stays on the 1/(B+1) grid", abs(a["p_value"] * 200 - round(a["p_value"] * 200)) < 1e-9)
    check("4e. bootstrap output is tagged UNVALIDATED_STUDY_IMPLEMENTATION",
          a["label"] == "UNVALIDATED_STUDY_IMPLEMENTATION")


# ---------------------------------------------------------------- 5. CI smoke grid
def test_5_smoke_grid_executes_and_is_deterministic() -> None:
    with tempfile.TemporaryDirectory() as td:
        out1, out2 = Path(td) / "a.json", Path(td) / "b.json"
        for o in (out1, out2):
            r = subprocess.run([sys.executable, str(RUNNER), "--reproduce", "--quick", "--out", str(o)],
                               capture_output=True, text=True, timeout=900)
            if r.returncode != 0:
                check("5a. smoke grid runs", False, (r.stderr or "")[-200:])
                return
        d1, d2 = json.loads(out1.read_text(encoding="utf-8")), json.loads(out2.read_text(encoding="utf-8"))
    check("5a. smoke grid runs", True)
    check("5b. smoke run is reproducible across processes (output digest)",
          d1["output_sha256"] == d2["output_sha256"])
    check("5c. smoke grid produces every planned cell",
          len(d1["monte_carlo_grid"]) == sum(len(c["effects"]) for c in R.SIM_PLAN["cells"]))
    check("5d. smoke mode is flagged and is not publication precision",
          d1["generated_by"]["quick_mode"] is True
          and d1["monte_carlo_grid"][0]["replications_requested"] == R.SIM_PLAN["replications_quick_mode"])
    check("5e. smoke run refuses the same five fixtures",
          sum(1 for v in d1["refusal_outcomes"].values() if v["refused"]) == 5)


# ---------------------------------------------------------------- 6. artifact arithmetic
def test_6_full_precision_artifact_arithmetic() -> None:
    grid = INVENTORY["monte_carlo_grid"]
    alpha = INVENTORY["simulation_plan"]["nominal_alpha"]
    bad_rate = bad_se = bad_wil = bad_claim = 0
    for cell in grid:
        for m, v in cell["methods"].items():
            k, n = v["numerator"], v["denominator"]
            if round(k / n, 5) != v["rate"]:
                bad_rate += 1
            p = k / n
            if round(math.sqrt(p * (1 - p) / n), 5) != v["monte_carlo_standard_error"]:
                bad_se += 1
            lo, hi = R.wilson(k, n)
            if round(lo, 5) != v["wilson_95_low"] or round(hi, 5) != v["wilson_95_high"]:
                bad_wil += 1
            if cell["hypothetical_effect"] == 0.0:
                want = ("evidence_of_over_rejection" if lo > alpha else
                        "evidence_of_under_rejection" if hi < alpha else
                        "not_distinguishable_from_nominal_at_this_precision")
                if v["claim"] != want:
                    bad_claim += 1
    check(f"6a. every rate equals numerator/denominator (bad={bad_rate})", bad_rate == 0)
    check(f"6b. every Monte Carlo SE matches the binomial formula (bad={bad_se})", bad_se == 0)
    check(f"6c. every Wilson interval recomputes exactly (bad={bad_wil})", bad_wil == 0)
    check(f"6d. every null-cell claim follows the preregistered rule (bad={bad_claim})", bad_claim == 0)
    nulls = [c for c in grid if c["hypothetical_effect"] == 0.0]
    check("6e. full-precision null cells used the planned replication count",
          all(c["replications_requested"] == INVENTORY["simulation_plan"]["replications_null_cell"]
              for c in nulls))
    check("6f. full-precision effect cells used the planned replication count",
          all(c["replications_requested"] == INVENTORY["simulation_plan"]["replications_effect_cell"]
              for c in grid if c["hypothetical_effect"] != 0.0))
    check("6g. committed artifact is full precision, not smoke",
          INVENTORY["generated_by"]["quick_mode"] is False)


# ---------------------------------------------------------------- 7. artifact provenance
def test_7_artifact_matches_this_runner() -> None:
    on_disk = hashlib.sha256(RUNNER.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    check("7a. artifact runner_sha256 matches the committed runner",
          INVENTORY["generated_by"]["runner_sha256"] == on_disk,
          "runner changed without regenerating the artifact")
    plan_hash = hashlib.sha256(json.dumps(R.SIM_PLAN, sort_keys=True).encode()).hexdigest()[:16]
    check("7b. artifact build id embeds the runner's current simulation plan",
          plan_hash in INVENTORY["generated_by"]["deterministic_build_id"],
          "simulation plan changed without regenerating the artifact")
    check("7c. artifact records the exact reproduction command",
          "--reproduce" in INVENTORY["generated_by"]["exact_command"])
    check("7d. artifact records environment versions",
          set(INVENTORY["environment"]) >= {"python", "numpy", "scipy", "pandas", "statsmodels"})
    check("7e. runner path recorded",
          INVENTORY["generated_by"]["runner_path"] == "tools/hyp01_inference_feasibility.py")


# ---------------------------------------------------------------- 8. markdown ties to data
def _null_cells():
    return {(c["clusters"], c["shape"]): c for c in INVENTORY["monte_carlo_grid"]
            if c["hypothetical_effect"] == 0.0}


def test_8_markdown_numbers_tie_to_inventory() -> None:
    rep = REP.read_text(encoding="utf-8")
    cells = _null_cells()
    checked = 0
    missing = []
    for (G, shape), cell in cells.items():
        v = cell["methods"]["CR1_tG1"]
        frac = f"{v['numerator']}/{v['denominator']}"
        interval = f"[{v['wilson_95_low']:.4f}, {v['wilson_95_high']:.4f}]"
        for token in (frac, interval):
            if token in rep:
                checked += 1
            else:
                missing.append((G, shape, token))
    check(f"8a. every CR1 null-cell numerator/denominator and Wilson interval appears in the report "
          f"(checked={checked}, missing={missing})", not missing)
    # any 4-dp number in the report's CR1 rows must exist in the inventory
    inv_nums = set()
    for c in INVENTORY["monte_carlo_grid"]:
        for v in c["methods"].values():
            for f in ("rate", "monte_carlo_standard_error", "wilson_95_low", "wilson_95_high"):
                if v[f] is not None:
                    inv_nums.add(f"{v[f]:.4f}")
        for f in ("mean_satterthwaite_df", "p5_satterthwaite_df"):
            if c[f] is not None:
                inv_nums.add(f"{c[f]:.3f}")
                inv_nums.add(f"{c[f]:.2f}")
    # Allowed non-grid constants, both derived from the artifact rather than hardcoded:
    # the nominal alpha, and the leading "0.14" of the recorded statsmodels version.
    allowed = {f"{INVENTORY['simulation_plan']['nominal_alpha']:.2f}",
               ".".join(INVENTORY["environment"]["statsmodels"].split(".")[:2])}
    # Scans BOTH prose and tables, and both documents. The regex takes one or more
    # leading digits: an earlier single-digit form silently exempted every
    # Satterthwaite df figure (e.g. "11.42") from the tie-out.
    stray = []
    for label, text in (("report", rep), ("decision matrix", MATRIX.read_text(encoding="utf-8"))):
        for line in text.splitlines():
            for num in re.findall(r"\b\d+\.\d{2,4}\b", line):
                if num not in inv_nums and num not in allowed:
                    stray.append((label, num, line.strip()[:60]))
    check(f"8b. every 2-to-4-decimal number in the report and decision matrix is either in the "
          f"inventory or a declared constant (stray={stray[:3]})", not stray)


# ---------------------------------------------------------------- 9. language guards
def test_9_unvalidated_never_described_as_validated() -> None:
    docs = {"inventory": json.dumps(INVENTORY), "report": REP.read_text(encoding="utf-8"),
            "matrix": MTX.read_text(encoding="utf-8")}
    for name, txt in docs.items():
        for meth in ("CR2", "CR3", "bootstrap"):
            pat = re.compile(rf"{meth}[^.\n]{{0,60}}\b(is|was|has been)\s+(independently\s+)?validated", re.I)
            m = pat.search(txt)
            check(f"9a. {name} never calls {meth} validated", m is None, m.group(0) if m else "")
    for meth in ("CR2", "CR3", "WCR_BOOTSTRAP_T"):
        check(f"9b. inventory marks {meth} blocked and not independently validated",
              INVENTORY["methods"][meth]["implementation_status"]
              == "IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE"
              and INVENTORY["methods"][meth]["independently_validated"] is False)
    check("9c. CR1 is the only independently validated method",
          INVENTORY["methods"]["CR1"]["independently_validated"] is True)
    warn = INVENTORY["simulation_plan"]["unvalidated_column_label"]
    check("9d. unvalidated columns carry the prominent warning label",
          "UNVALIDATED ENGINEERING OUTPUT" in warn and "NOT METHOD-COMPARISON EVIDENCE" in warn)
    check("9e. every unvalidated grid column is tagged in the artifact",
          all(v["validation_label"] == "UNVALIDATED_STUDY_IMPLEMENTATION"
              for c in INVENTORY["monte_carlo_grid"]
              for k, v in c["methods"].items()
              if k in INVENTORY["simulation_plan"]["unvalidated_columns"]))
    rep = docs["report"] + docs["matrix"]
    for banned in ("performed best", "outperform", "statistically superior"):
        check(f"9f. no comparative-superiority claim: '{banned}'", banned.lower() not in rep.lower())
    check("9g. R absence is scoped to the tested environment",
          "currently tested environment" in json.dumps(INVENTORY))
    check("9h. perfect-fit language does not call both implementations correct",
          not re.search(r"both\s+(implementations\s+)?(are|were)\s+correct", rep, re.I))


# ---------------------------------------------------------------- 10. isolation guarantees
def test_10_isolation() -> None:
    src = RUNNER.read_text(encoding="utf-8")
    check("10a. runner declares itself non-production", "NOT PRODUCTION CODE" in src)
    for tok in ("registry.jsonl", "Cohort_Screening", "ANALYSIS_LOCK", "SIGNOFF"):
        check(f"10b. runner guard lists forbidden token {tok!r}", tok in R.FORBIDDEN_PATH_TOKENS)
    for bad in ("Live Signal Engine/Market_Response_Event_Registry/registry.jsonl",
                "Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.0.json",
                "Live Signal Engine/Cohort_Screening_Round2/x.json"):
        try:
            R.assert_not_canonical(bad)
            check(f"10c. runner refuses canonical path {Path(bad).name}", False, "not refused")
        except PermissionError:
            check(f"10c. runner refuses canonical path {Path(bad).name}", True)
    prod = [p for p in ROOT.glob("gst_market_response/*.py")]
    offenders = [p.name for p in prod
                 if "hyp01_inference_feasibility" in p.read_text(encoding="utf-8", errors="replace")]
    check(f"10d. no production module imports the runner (offenders={offenders})", not offenders)
    # The runner installs its own blocker at import, so the raised class may be
    # either this module's NetworkBlocked or the runner's. Both are acceptable;
    # what must never happen is the call succeeding.
    try:
        socket.getaddrinfo("example.com", 80)
        check("10e. network blocked", False, "NOT BLOCKED")
    except Exception as e:
        check("10e. network blocked", type(e).__name__ == "NetworkBlocked", type(e).__name__)
    # generated fixtures must never carry a real ticker
    specs = dict(R.FIXTURE_SPECS)
    fx = R.make_fixture("F02_unbalanced_24c_60n", **specs["F02_unbalanced_24c_60n"])
    labels = set(fx["labels"].tolist())
    check("10f. generated cluster labels are CLUSTER_### only",
          all(re.fullmatch(r"CLUSTER_\d{3}", s) for s in labels))
    check("10g. no locked ticker appears in generated labels",
          not (labels & set(LOCKED_24)))
    check("10h. no locked ticker appears in the inventory as a cluster label",
          not any(re.search(rf'"{t}"', json.dumps(INVENTORY["fixtures"])) for t in LOCKED_24))


# ---------------------------------------------------------------- 11. protected state
def test_11_protected_state_unchanged() -> None:
    lock = json.loads(LOCK10.read_text(encoding="utf-8-sig"))
    check("11a. operative v1.0 results null", lock["results"] is None)
    check("11b. operative v1.0 frozen ids empty", lock["frozen_event_ids"] == [])
    check("11c. operative v1.0 eligible count zero", lock["eligible_events_now"] == 0)
    prop = json.loads(PROPOSED.read_text(encoding="utf-8"))
    check("11d. proposed v1.1 still pending and not authoritative",
          prop["status"] == "PROPOSED_PENDING_HUMAN_AND_METHODOLOGIST_APPROVAL"
          and prop["authoritative"] is False)
    sg = SIGNOFF.read_text(encoding="utf-8")
    pending = "`PENDING`"
    cells = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$", sg, re.M)
    filled = [c for c in cells if c[1].strip() not in (pending, "Entry", "")
              and not re.match(r"^-+$", c[1].strip())]
    check(f"11e. signoff entirely pending (filled={len(filled)})", not filled)
    check("11f. signoff has no ticked box", sg.count("- [x]") == 0)
    rows = [l for l in REGISTRY.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("11g. registry holds exactly one row", len(rows) == 1)
    check("11h. registry blob hash unchanged",
          hashlib.sha256(REGISTRY.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
          == "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974")
    cp = json.loads((LS / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json").read_text(encoding="utf-8-sig"))
    check("11i. screening rows empty", cp["screening_rows"] == [])
    cj = json.loads((LS / "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json").read_text(encoding="utf-8"))
    check("11j. F5 still OPEN", cj["gap_audit_status_after_this_work"] == "STILL_OPEN")
    check("11k. study declares no method approved and no amendment created",
          INVENTORY["method_approved"] is False and INVENTORY["dated_amendment_created"] is False)


if __name__ == "__main__":
    test_1_recompute_cr1_against_statsmodels()
    test_2_recompute_all_five_refusals()
    test_3_recompute_invariance_and_sign()
    test_4_recompute_bootstrap_seed_behaviour()
    test_5_smoke_grid_executes_and_is_deterministic()
    test_6_full_precision_artifact_arithmetic()
    test_7_artifact_matches_this_runner()
    test_8_markdown_numbers_tie_to_inventory()
    test_9_unvalidated_never_described_as_validated()
    test_10_isolation()
    test_11_protected_state_unchanged()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-01 INFERENCE FEASIBILITY COMPUTATIONAL TESTS PASSED")
    sys.exit(0)
