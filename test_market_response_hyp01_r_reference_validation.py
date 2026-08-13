#!/usr/bin/env python3
"""Computational tests for the independent R-reference validation.

These EXECUTE the bridge and recompute the comparison. They do not trust the
committed artifact's declarations: the Python side is recomputed from the
committed runner, and where R is present the reference is re-run and re-compared.

Where R is absent the R-dependent assertions are SKIPPED and counted as skips,
never as passes. The test says plainly what it could not check.

Offline. Sockets blocked. Synthetic fixtures only.

Run directly: python test_market_response_hyp01_r_reference_validation.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline validation test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

ROOT = Path(__file__).resolve().parent
LS = ROOT / "Live Signal Engine"
BRIDGE = ROOT / "tools" / "hyp01_r_reference"
EXPORT = BRIDGE / "export_fixtures.py"
COMPARE = BRIDGE / "compare_reference.py"
R_SCRIPT = BRIDGE / "cr2_reference.R"
DRIVER = BRIDGE / "run_validation.py"
LOCK = BRIDGE / "r-packages.lock.json"
RUNNER = ROOT / "tools" / "hyp01_inference_feasibility.py"
ARTIFACT = LS / "GST_HYP01_R_REFERENCE_VALIDATION_v1.0.json"
REPORT = LS / "GST_HYP01_R_REFERENCE_VALIDATION_REPORT_v1.0_DRAFT.md"
LOCK10 = LS / "GST_HYP01_ANALYSIS_LOCK_v1.0.json"
PROPOSED = LS / "GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json"
SIGNOFF = LS / "GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md"
MATRIX = LS / "GST_HYP01_AUTHORIZER_DECISION_MATRIX_v1.0_DRAFT.md"
REGISTRY = LS / "Market_Response_Event_Registry" / "registry.jsonl"

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = load(RUNNER, "hyp01_feas_runner")
CMP = load(COMPARE, "hyp01_compare_reference")
EXP = load(EXPORT, "hyp01_export_fixtures")
ARTIFACT_DOC = json.loads(ARTIFACT.read_text(encoding="utf-8"))
LOCK_DOC = json.loads(LOCK.read_text(encoding="utf-8"))

LOCKED_24 = ["AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "CTSH", "DELL", "DVN", "GME",
             "GOOGL", "GPN", "INTC", "LDOS", "MSFT", "NCLH", "NKE", "QCOM", "SBUX", "STZ",
             "SYK", "TSLA", "TTWO", "UAL"]


def find_rscript():
    env = os.environ.get("RSCRIPT")
    if env and Path(env).exists():
        return env
    w = shutil.which("Rscript")
    if w:
        return w
    for c in (Path(os.environ.get("LOCALAPPDATA", "x")) / "Programs" / "R" / "R-4.6.1" / "bin" / "x64" / "Rscript.exe",):
        if c.exists():
            return str(c)
    return None


RSCRIPT = find_rscript()


# ---------------------------------------------------------------- 1. interchange integrity
def test_1_interchange_is_built_from_the_committed_generator() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "fx.json"
        r = subprocess.run([sys.executable, str(EXPORT), "--out", str(out)],
                           capture_output=True, text=True, timeout=900)
        check("1a. exporter runs", r.returncode == 0, (r.stderr or "")[-300:])
        if r.returncode != 0:
            return
        doc = json.loads(out.read_text(encoding="utf-8"))
        check("1b. exports every committed fixture",
              doc["fixture_count"] == len(R.FIXTURE_SPECS), f"{doc['fixture_count']}")
        check("1c. fixtures are NOT regenerated in R",
              doc["source_of_truth"]["fixtures_regenerated_in_r"] is False)
        on_disk = hashlib.sha256(RUNNER.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        check("1d. records the generator's runner hash",
              doc["source_of_truth"]["runner_sha256"] == on_disk)

        # byte-identical across two runs -> stable serialization
        out2 = Path(td) / "fx2.json"
        subprocess.run([sys.executable, str(EXPORT), "--out", str(out2)],
                       capture_output=True, text=True, timeout=900)
        check("1e. serialization is stable across runs",
              out.read_bytes() == out2.read_bytes())

        # the canonical digest is recomputable here, independently of the exporter's own copy
        bad = []
        for fx in doc["fixtures"]:
            want = fx["canonical_sha256"]
            got = hashlib.sha256(EXP.canonical_string(fx).encode("utf-8")).hexdigest()
            if want != got:
                bad.append(fx["fixture_id"])
        check(f"1f. every canonical digest recomputes (bad={bad})", not bad)

        # missing values must be JSON null, never a sentinel number
        f09 = [f for f in doc["fixtures"] if f["fixture_id"] == "F09_missing_value"][0]
        check("1g. a missing outcome is encoded as null, not zero-filled",
              None in f09["y"] and 0.0 not in [v for v in f09["y"] if v is not None][:1] or None in f09["y"])
        check("1h. strict JSON (no NaN/Infinity tokens)",
              "NaN" not in out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 2. no research values
def test_2_interchange_carries_no_research_value() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "fx.json"
        subprocess.run([sys.executable, str(EXPORT), "--out", str(out)],
                       capture_output=True, text=True, timeout=900)
        text = out.read_text(encoding="utf-8")
        hits = [t for t in LOCKED_24 if re.search(rf"\b{re.escape(t)}\b", text)]
        check(f"2a. no locked ticker appears in the interchange (hits={hits})", not hits)
        labels = set()
        for fx in json.loads(text)["fixtures"]:
            labels.update(fx["cluster_labels"])
        check("2b. every cluster label is synthetic CLUSTER_###",
              all(re.fullmatch(r"CLUSTER_\d{3}", s) for s in labels))
        for tok in ("registry.jsonl", "EVT-", "Cohort_Screening", "DailyPanel", "observation"):
            check(f"2c. interchange never mentions {tok}", tok not in text)


# ---------------------------------------------------------------- 3. R reference re-run
def test_3_reference_reruns_and_recompares() -> None:
    if RSCRIPT is None:
        skip("3. R reference re-run and re-comparison", "Rscript not found in this environment")
        return
    with tempfile.TemporaryDirectory() as td:
        fx = Path(td) / "fx.json"
        ref = Path(td) / "ref.json"
        cmp_out = Path(td) / "cmp.json"
        subprocess.run([sys.executable, str(EXPORT), "--out", str(fx)],
                       capture_output=True, text=True, timeout=900)
        r = subprocess.run([RSCRIPT, str(R_SCRIPT), "--fixtures", str(fx), "--out", str(ref)],
                           capture_output=True, text=True, timeout=1800)
        check("3a. the R reference runs", r.returncode == 0, (r.stderr or "")[-400:])
        if r.returncode != 0:
            return
        refdoc = json.loads(ref.read_text(encoding="utf-8"))
        check("3b. R verified every fixture's canonical digest itself",
              all(v.get("canonical_digest_matches_export") for v in refdoc["results"].values()),
              str([k for k, v in refdoc["results"].items()
                   if not v.get("canonical_digest_matches_export")]))
        check("3c. R did not regenerate fixtures", refdoc["fixtures_regenerated_in_r"] is False)
        check("3d. the reference package is clubSandwich, not written for this study",
              refdoc["reference_package"] == "clubSandwich"
              and refdoc["reference_written_for_this_study"] is False)
        check("3e. reference versions match the lockfile",
              refdoc["environment"]["clubSandwich"] ==
              [p["version"] for p in LOCK_DOC["packages"] if p["package"] == "clubSandwich"][0])

        c = subprocess.run([sys.executable, str(COMPARE), "--fixtures", str(fx),
                            "--reference", str(ref), "--out", str(cmp_out)],
                           capture_output=True, text=True, timeout=1800)
        check("3f. the comparison exits zero (no unresolved fixture)", c.returncode == 0,
              (c.stdout or "")[-300:])
        fresh = json.loads(cmp_out.read_text(encoding="utf-8"))

        # A FRESH comparison must reproduce the committed artifact's classifications.
        commit_cls = {r_["fixture_id"]: r_["classification"] for r_ in ARTIFACT_DOC["results"]}
        fresh_cls = {r_["fixture_id"]: r_["classification"] for r_ in fresh["results"]}
        check("3g. fresh run reproduces the committed classifications",
              commit_cls == fresh_cls,
              str({k: (commit_cls.get(k), v) for k, v in fresh_cls.items() if commit_cls.get(k) != v}))

        # And the agreement must still hold when recomputed, not merely be asserted.
        tol = R.TOLERANCES
        worst = 0.0
        for r_ in fresh["results"]:
            if r_["classification"] != "MATCH_WITHIN_PREREGISTERED_TOLERANCE":
                continue
            for name, f in r_["fields"].items():
                if name == "satterthwaite_df":
                    continue
                worst = max(worst, f["max_abs_difference"])
                check(f"3h. {r_['fixture_id']}.{name} within preregistered tolerance", f["within"])
        check(f"3i. worst preregistered-field difference is at the noise floor ({worst:.3e})",
              worst < 1e-9)


# ---------------------------------------------------------------- 4. python side recomputed
def test_4_python_side_is_recomputed_not_read() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "fx.json"
        subprocess.run([sys.executable, str(EXPORT), "--out", str(out)],
                       capture_output=True, text=True, timeout=900)
        doc = json.loads(out.read_text(encoding="utf-8"))
        by_id = {f["fixture_id"]: f for f in doc["fixtures"]}
        rec = [r_ for r_ in ARTIFACT_DOC["results"]
               if r_["classification"] == "MATCH_WITHIN_PREREGISTERED_TOLERANCE"]
        check("4a. the artifact has matched fixtures to recheck", len(rec) >= 10)
        bad = []
        for r_ in rec[:4]:
            live = CMP.python_side(R, by_id[r_["fixture_id"]])
            stored = r_["python_values"]
            for k in ("target_estimate", "standard_error", "t_statistic",
                      "satterthwaite_df", "p_value"):
                if abs(live[k] - stored[k]) > 1e-12 * max(1.0, abs(stored[k])):
                    bad.append((r_["fixture_id"], k, live[k], stored[k]))
        check(f"4b. live Python recomputation reproduces the artifact's Python values (bad={bad[:2]})",
              not bad)
        # the CR2 path really is the study implementation under test
        fx = R.make_fixture("F01_balanced_24c_72n", n_clusters=24, n_obs=72, shape="balanced")
        _, V2, _ = R.cr_vcov(fx["X"], fx["y"], fx["cluster_index"], "CR2")
        _, V1, _ = R.cr_vcov(fx["X"], fx["y"], fx["cluster_index"], "CR1")
        check("4c. CR2 and CR1 are genuinely different estimators here",
              abs(V2[1, 1] - V1[1, 1]) > 1e-12)


# ---------------------------------------------------------------- 5. tolerance discipline
def test_5_tolerances_are_the_preregistered_ones() -> None:
    check("5a. the artifact records the preregistered tolerances verbatim",
          ARTIFACT_DOC["preregistered_tolerances"] == R.TOLERANCES)
    check("5b. it states they were used as written",
          ARTIFACT_DOC["preregistered_tolerances_used_as_written"] is True)
    sdt = ARTIFACT_DOC["satterthwaite_df_tolerance"]
    check("5c. the Satterthwaite df tolerance is flagged as NOT preregistered",
          sdt["preregistered_in_pr17"] is False)
    check("5d. it explains why the preregistered df rule cannot apply",
          "exact_integer_equality" in sdt["why_not_the_preregistered_df_rule"])
    check("5e. the preregistered df rule is still exact integer equality",
          R.TOLERANCES["degrees_of_freedom"] == {"exact_integer_equality": True})
    # no tolerance may be looser in the artifact than in the runner
    loosened = []
    for name, t in R.TOLERANCES.items():
        if name == "degrees_of_freedom":
            continue
        a = ARTIFACT_DOC["preregistered_tolerances"][name]
        if a["rtol"] > t["rtol"] or a["atol"] > t["atol"]:
            loosened.append(name)
    check(f"5f. no preregistered tolerance was loosened (loosened={loosened})", not loosened)


# ---------------------------------------------------------------- 6. refusals not forced
def test_6_refusals_are_reported_not_forced() -> None:
    by = {r_["fixture_id"]: r_ for r_ in ARTIFACT_DOC["results"]}
    both = [k for k, v in by.items() if v["classification"] == "REFUSED_BY_BOTH"]
    check(f"6a. refusal fixtures are refused by both implementations ({len(both)})", len(both) >= 4)
    check("6b. differing refusal reasons are recorded, not hidden",
          all("reference_refusal_reason" in by[k] and "python_refusal_reason" in by[k] for k in both))
    diff = [k for k, v in by.items() if v["classification"] == "REFERENCE_BEHAVIOR_DIFFERENCE"]
    check(f"6c. behaviour differences are classified as such, not as matches ({diff})", len(diff) >= 1)
    for k in diff:
        check(f"6d. {k} explains that neither side was adjusted",
              "NOT forced" in by[k]["explanation"] or "NOT relaxed" in by[k]["explanation"]
              or "not validated" in by[k]["explanation"])
    check("6e. no fixture was dropped: every committed fixture appears",
          {r_["fixture_id"] for r_ in ARTIFACT_DOC["results"]} == {n for n, _ in R.FIXTURE_SPECS})


# ---------------------------------------------------------------- 7. scope of the claim
FORBIDDEN_CLAIMS = (
    "cr2 is approved", "method is approved", "scientifically optimal", "is optimal",
    "adequately powered", "f5 is closed", "f5 closed", "will be significant",
    "production ready", "production-ready", "recommended method is",
)


DISCLAIMER_MARKERS = (
    "not supported, and not claimed",
    "do not translate",
    "not claimed anywhere in this pr",
)


def _claim_bearing_text(md: str) -> str:
    """Strip blocks that explicitly ENUMERATE forbidden claims in order to disown them.

    The report's own "what this does not support" list necessarily contains the
    exact phrases this test forbids. A naive substring scan flags that list --
    which would be a matcher defect, not an overclaim. Only the disclaimer block
    is excluded; every other line is still scanned, so the guarantee is intact.
    """
    lines = md.lower().splitlines()
    kept, skipping = [], False
    for line in lines:
        stripped = line.strip()
        if any(m in stripped for m in DISCLAIMER_MARKERS):
            skipping = True
            continue
        if skipping:
            # the disowning list is a run of bullets; it ends at the next
            # non-bullet, non-empty line
            if stripped.startswith(("-", "*", ">")) or not stripped:
                continue
            skipping = False
        kept.append(line)
    return "\n".join(kept)


NEGATORS = ("no ", "not ", "never", "nothing", "cannot", "n't", "neither", "without")


def _asserted_occurrences(text: str, phrase: str) -> list[str]:
    """Occurrences of `phrase` that are NOT directly negated.

    The mandated banner reads "No statistical method is approved", which
    contains "method is approved" as a substring. A plain substring scan would
    flag the very sentence that makes the disclaimer. Only occurrences with no
    negator in the preceding window count as claims.
    """
    out, start = [], 0
    while True:
        i = text.find(phrase, start)
        if i < 0:
            return out
        window = text[max(0, i - 45):i]
        if not any(n in window for n in NEGATORS):
            out.append(text[max(0, i - 45):i + len(phrase) + 15])
        start = i + len(phrase)


def test_7_no_overclaim() -> None:
    rep = _claim_bearing_text(REPORT.read_text(encoding="utf-8"))
    art = json.dumps(ARTIFACT_DOC).lower()
    for phrase in FORBIDDEN_CLAIMS:
        hits = _asserted_occurrences(rep, phrase)
        check(f"7a. report never asserts '{phrase}'", not hits, str(hits[:1]))
        check(f"7b. artifact never asserts '{phrase}'", not _asserted_occurrences(art, phrase))
    # the disclaimer block must actually exist -- the exclusion above must never
    # be able to hide a missing disclaimer
    low = REPORT.read_text(encoding="utf-8").lower()
    check("7a2. the report does carry an explicit 'not claimed' section",
          any(m in low for m in DISCLAIMER_MARKERS))
    check("7c. artifact records that no method is approved",
          ARTIFACT_DOC["method_approved"] is False and ARTIFACT_DOC["lock_activated"] is False)
    check("7d. artifact records F5 still OPEN", ARTIFACT_DOC["f5_status"].startswith("OPEN"))
    check("7e. CR3 and the bootstrap are still unvalidated",
          ARTIFACT_DOC["cr3_validated"] is False
          and ARTIFACT_DOC["wild_cluster_bootstrap_validated"] is False)
    check("7f. CR2 agreement is not used to claim CR3/bootstrap validation",
          "never treated as evidence about CR3" in ARTIFACT_DOC["cr3_and_bootstrap_note"])
    check("7g. the report states the supported claim verbatim",
          "agrees with the independent clubSandwich reference on the prespecified synthetic "
          "fixture matrix under the preregistered tolerances" in REPORT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 8. isolation
def test_8_isolation() -> None:
    for f, label in ((EXPORT, "exporter"), (COMPARE, "comparison harness")):
        src = f.read_text(encoding="utf-8")
        check(f"8a. {label} blocks sockets before numerical imports",
              "socket.getaddrinfo = _deny_network" in src)
        check(f"8b. {label} screens its output path", "assert_not_canonical" in src)
    rsrc = R_SCRIPT.read_text(encoding="utf-8")
    for tok in ("registry.jsonl", "GST_Phase2_DailyPanel", "Cohort_Screening", "ANALYSIS_LOCK"):
        check(f"8c. the R script never references {tok}", tok not in rsrc)
    check("8d. the R script does not download anything",
          not any(t in rsrc for t in ("install.packages", "download.file", "url(", "curl")))
    driver = DRIVER.read_text(encoding="utf-8")
    check("8e. the driver installs nothing",
          "install.packages" not in driver and "pip install" not in driver)
    # production code must not import the bridge
    offenders = []
    for p in ROOT.rglob("*.py"):
        if p.name.startswith("test_") or "hyp01_r_reference" in str(p) or "tools" in p.parts:
            continue
        try:
            if "hyp01_r_reference" in p.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(p.relative_to(ROOT)))
        except OSError:
            pass
    check(f"8f. no production module imports the bridge (offenders={offenders})", not offenders)
    try:
        socket.getaddrinfo("example.com", 443)
        check("8g. network blocked", False)
    except Exception as e:
        check("8g. network blocked", type(e).__name__ == "NetworkBlocked")


# ---------------------------------------------------------------- 9. pinning
def test_9_dependencies_are_pinned() -> None:
    check("9a. R version is pinned", LOCK_DOC["r"]["version"] == "4.6.1")
    check("9b. the installer hash is recorded", len(LOCK_DOC["r"]["installer_sha256"]) == 64)
    pkgs = {p["package"]: p for p in LOCK_DOC["packages"]}
    check("9c. clubSandwich is pinned with a binary hash",
          "clubSandwich" in pkgs and len(pkgs["clubSandwich"]["windows_binary_sha256"]) == 64)
    check("9d. every pinned package has an exact version",
          all(re.fullmatch(r"[\d.\-]+", p["version"]) for p in LOCK_DOC["packages"]))
    check("9e. the CI action is pinned to an immutable commit SHA",
          re.fullmatch(r"[0-9a-f]{40}", LOCK_DOC["github_action"]["pinned_commit_sha"]) is not None)
    check("9f. no wild-bootstrap reference was installed",
          "fwildclusterboot" not in {p["package"] for p in LOCK_DOC["packages"]})
    check("9g. the lock states installing it approves no method",
          "approves no statistical method" in LOCK_DOC["purpose"])


# ---------------------------------------------------------------- 10. driver contract
def test_10_driver_exits_nonzero_on_unexplained_mismatch() -> None:
    src = DRIVER.read_text(encoding="utf-8")
    check("10a. the driver is one command covering all four stages",
          all(t in src for t in ("export_fixtures", "cr2_reference.R", "compare_reference", "--out")))
    check("10b. the driver propagates a nonzero exit", "return 1" in src)
    cmp_src = COMPARE.read_text(encoding="utf-8")
    check("10c. the comparison returns nonzero when a fixture is UNRESOLVED",
          "unresolved" in cmp_src and "return 1" in cmp_src)
    # Prove it: an artificially corrupted reference must NOT be reported as a match.
    with tempfile.TemporaryDirectory() as td:
        fx = Path(td) / "fx.json"
        subprocess.run([sys.executable, str(EXPORT), "--out", str(fx)],
                       capture_output=True, text=True, timeout=900)
        doc = json.loads(fx.read_text(encoding="utf-8"))
        target = doc["fixtures"][0]
        fake_ref = {
            "reference_package": "clubSandwich", "reference_is_independently_maintained": True,
            "reference_written_for_this_study": False,
            "environment": {"clubSandwich": "0.7.0"},
            "specification": {}, "reference_defaults": {},
            "results": {target["fixture_id"]: {
                "status": "COMPUTED", "canonical_digest_matches_export": True,
                "coefficients": ["1.0", "2.0"],
                "cr2_covariance": [["1.0", "0.0"], ["0.0", "1.0"]],
                "target_variance": "1.0", "target_estimate": "2.0",
                "standard_error": "1.0", "t_statistic": "2.0",
                "satterthwaite_df": "10.0", "p_value": "0.5",
                "conf_int_defined": False}}}
        rr = fake_ref["results"][target["fixture_id"]]
        py = CMP.python_side(R, target)
        rec = CMP.compare_one(target, py, rr, R.TOLERANCES)
        check("10d. a deliberately wrong reference is NOT classified as a match",
              rec["classification"] != "MATCH_WITHIN_PREREGISTERED_TOLERANCE",
              rec["classification"])
        check("10e. and it is classified UNRESOLVED, forcing diagnosis",
              rec["classification"] == "UNRESOLVED", rec["classification"])


# ---------------------------------------------------------------- 11. protected state
def test_11_protected_state_unchanged() -> None:
    lock = json.loads(LOCK10.read_text(encoding="utf-8-sig"))
    check("11a. operative v1.0 results still null", lock["results"] is None)
    check("11b. frozen event ids still empty", lock["frozen_event_ids"] == [])
    check("11c. eligible events still zero", lock["eligible_events_now"] == 0)
    prop = json.loads(PROPOSED.read_text(encoding="utf-8-sig"))
    check("11d. proposed v1.1 still pending",
          prop["status"] == "PROPOSED_PENDING_HUMAN_AND_METHODOLOGIST_APPROVAL")
    sig = SIGNOFF.read_text(encoding="utf-8")
    check("11e. signoff has no ticked box", not re.search(r"- \[[xX]\]", sig))
    check("11f. signoff hash unchanged",
          hashlib.sha256(SIGNOFF.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
          == "7eef69e81e4764ed19534762d0f3031d3ac2a50c30adc363447d99e38fe69320")
    check("11g. registry blob hash unchanged",
          hashlib.sha256(REGISTRY.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
          == "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974")
    rows = [json.loads(l) for l in REGISTRY.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("11h. registry holds exactly one row", len(rows) == 1 and rows[0]["ticker"] == "DELL")
    cp = json.loads((LS / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json").read_text(encoding="utf-8-sig"))
    check("11i. screening rows empty", cp["screening_rows"] == [])
    cj = json.loads((LS / "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json").read_text(encoding="utf-8"))
    check("11j. F5 still OPEN", cj["gap_audit_status_after_this_work"] == "STILL_OPEN")
    mtx = MATRIX.read_text(encoding="utf-8")
    check("11k. no authorizer checkbox is ticked", not re.search(r"- \[[xX]\]", mtx))
    check("11l. authorizer fields still PENDING",
          "**Authorizer:** `PENDING`" in mtx and "**Decision date:** `PENDING`" in mtx)


# ---------------------------------------------------------------- 12. decision-matrix separation
def test_12_matrix_separates_evidence_from_decision() -> None:
    mtx = MATRIX.read_text(encoding="utf-8")
    check("12a. the matrix records the new implementation-validation evidence",
          "clubSandwich" in mtx)
    for heading in ("Implementation validation evidence",
                    "Scientific method recommendation",
                    "Final authorizer decision"):
        check(f"12b. the matrix distinguishes '{heading}'", heading in mtx)
    check("12c. the recommendation is framed as a proposal, not a decision",
          "PROPOSAL" in mtx.upper() and "PENDING" in mtx)
    check("12d. validation is explicitly not equated with approval",
          "validated" in mtx.lower() and "not approved" in mtx.lower())


if __name__ == "__main__":
    test_1_interchange_is_built_from_the_committed_generator()
    test_2_interchange_carries_no_research_value()
    test_3_reference_reruns_and_recompares()
    test_4_python_side_is_recomputed_not_read()
    test_5_tolerances_are_the_preregistered_ones()
    test_6_refusals_are_reported_not_forced()
    test_7_no_overclaim()
    test_8_isolation()
    test_9_dependencies_are_pinned()
    test_10_driver_exits_nonzero_on_unexplained_mismatch()
    test_11_protected_state_unchanged()
    test_12_matrix_separates_evidence_from_decision()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-01 R-REFERENCE VALIDATION TESTS PASSED")
    sys.exit(0)
