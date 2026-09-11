#!/usr/bin/env python3
"""Computational tests for HYP-04's D10 independent R-reference validation.

These EXECUTE the bridge and recompute the comparison. They do not trust the
committed artifact's declarations: the Python side is recomputed by calling
`hyp04_supply_chain_hedge.clustered_se` directly, and where R is present the
reference is re-run and re-compared.

Where R is absent the R-dependent assertions are SKIPPED and counted as
skips, never as passes. The test says plainly what it could not check.

Offline. Sockets blocked. Synthetic fixtures only.

Structurally mirrors test_market_response_hyp01_r_reference_validation.py,
adapted to HYP-04's bridge, fields, and artifacts.

Run directly: python test_hyp04_supply_chain_hedge_r_reference.py
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
BRIDGE = ROOT / "tools" / "hyp04_r_reference"
EXPORT = BRIDGE / "export_fixtures.py"
COMPARE = BRIDGE / "compare_reference.py"
R_SCRIPT = BRIDGE / "cr2_reference.R"
DRIVER = BRIDGE / "run_validation.py"
VERIFY = BRIDGE / "verify_artifact.py"
LOCK = BRIDGE / "r-packages.lock.json"
RUNNER = BRIDGE / "fixtures.py"
CSE = ROOT / "hyp04_supply_chain_hedge" / "clustered_se.py"
ARTIFACT_PATH = LS / "HYP04_R_REFERENCE_VALIDATION_v1.0.json"

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


R = load(RUNNER, "hyp04_r_ref_fixtures")
CMP = load(COMPARE, "hyp04_compare_reference")
EXP = load(EXPORT, "hyp04_export_fixtures")
ARTIFACT_DOC = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8")) if ARTIFACT_PATH.exists() else None
LOCK_DOC = json.loads(LOCK.read_text(encoding="utf-8"))

# Real tickers and canonical-artifact tokens that must never appear in a
# synthetic interchange file. Not exhaustive by construction -- it is the set
# actually seen in this project's committed HYP-04 artifacts (the Phase 1
# diagnostic's peer coverage, the anchor JBL) plus the canonical file-name
# fragments the freeze/split/lock machinery itself guards.
REAL_TICKERS = ["AAPL", "BB", "CSCO", "CVS", "HPQ", "MSFT", "JBL"]
CANONICAL_TOKENS = ("HYP04_ANALYSIS_LOCK", "HYP04_LINKAGE", "HYP04_FREEZE",
                    "HYP04_VALIDATION_SPLIT", "HYP04_PHASE1", "HYP04_PHASE2",
                    "HYP04_PEER_EARNINGS", "curated_linkage", "AllTickers_Sectors")


def find_rscript():
    env = os.environ.get("RSCRIPT")
    if env and Path(env).exists():
        return env
    w = shutil.which("Rscript")
    if w:
        return w
    c = Path(os.environ.get("LOCALAPPDATA", "x")) / "Programs" / "R" / "R-4.6.1" / "bin" / "x64" / "Rscript.exe"
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
        g07 = [f for f in doc["fixtures"] if f["fixture_id"] == "G07_missing_value"][0]
        check("1g. a missing outcome is encoded as null, not zero-filled",
              None in g07["y"])
        check("1h. strict JSON (no NaN/Infinity tokens)",
              "NaN" not in out.read_text(encoding="utf-8"))
        check("1i. every fixture has HYP-04's real 3-column shape",
              all(f["n_params"] == 3 for f in doc["fixtures"]))


# ---------------------------------------------------------------- 2. no research values
def test_2_interchange_carries_no_research_value() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "fx.json"
        subprocess.run([sys.executable, str(EXPORT), "--out", str(out)],
                       capture_output=True, text=True, timeout=900)
        text = out.read_text(encoding="utf-8")
        hits = [t for t in REAL_TICKERS if re.search(rf"\b{re.escape(t)}\b", text)]
        check(f"2a. no real ticker appears in the interchange (hits={hits})", not hits)
        labels = set()
        for fx in json.loads(text)["fixtures"]:
            labels.update(fx["cluster_labels"])
        check("2b. every cluster label is synthetic CALENDAR_PERIOD_###",
              all(re.fullmatch(r"CALENDAR_PERIOD_\d{3}", s) for s in labels))
        hits2 = [t for t in CANONICAL_TOKENS if t in text]
        check(f"2c. interchange never mentions a canonical-artifact token (hits={hits2})", not hits2)


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
        check("3g. a clean run reports d10_satisfied", fresh["d10_satisfied"] is True)

        if ARTIFACT_DOC is not None:
            commit_cls = {r_["fixture_id"]: r_["classification"] for r_ in ARTIFACT_DOC["results"]}
            fresh_cls = {r_["fixture_id"]: r_["classification"] for r_ in fresh["results"]}
            check("3h. fresh run reproduces the committed classifications",
                  commit_cls == fresh_cls,
                  str({k: (commit_cls.get(k), v) for k, v in fresh_cls.items() if commit_cls.get(k) != v}))
        else:
            skip("3h. fresh run reproduces the committed classifications",
                 "no committed artifact yet")

        worst = 0.0
        for r_ in fresh["results"]:
            if r_["classification"] != CMP.MATCH:
                continue
            for name, f in r_["fields"].items():
                if name == "satterthwaite_df":
                    continue
                worst = max(worst, f["max_abs_difference"])
                check(f"3i. {r_['fixture_id']}.{name} within reused tolerance", f["within"])
        check(f"3j. worst reused-field difference is at the noise floor ({worst:.3e})",
              worst < 1e-9)


# ---------------------------------------------------------------- 4. python side recomputed
def test_4_python_side_is_recomputed_not_read() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "fx.json"
        subprocess.run([sys.executable, str(EXPORT), "--out", str(out)],
                       capture_output=True, text=True, timeout=900)
        doc = json.loads(out.read_text(encoding="utf-8"))
        by_id = {f["fixture_id"]: f for f in doc["fixtures"]}
        if ARTIFACT_DOC is None:
            skip("4. live recomputation against the committed artifact", "no committed artifact yet")
        else:
            rec = [r_ for r_ in ARTIFACT_DOC["results"] if r_["classification"] == CMP.MATCH]
            check("4a. the artifact has matched fixtures to recheck", len(rec) >= 5)
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
        # the CR2 path is HYP-04's actual production module, called directly
        fx = R.make_fixture("G01_balanced_70c_300n", n_clusters=70, n_obs=300, shape="balanced")
        _, V2, _ = CMP.cr_vcov(fx["X"], fx["y"], fx["cluster_index"], "CR2")
        _, V1, _ = CMP.cr_vcov(fx["X"], fx["y"], fx["cluster_index"], "CR1")
        check("4c. CR2 and CR1 are genuinely different estimators here",
              abs(V2[1, 1] - V1[1, 1]) > 1e-12)
        check("4d. compare_reference.py imports the real production module, not a copy",
              "from hyp04_supply_chain_hedge.clustered_se import" in COMPARE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 5. tolerance discipline
def test_5_tolerances_are_reused_correctly() -> None:
    if ARTIFACT_DOC is None:
        skip("5. tolerance discipline against the committed artifact", "no committed artifact yet")
        return
    check("5a. the artifact records the reused tolerances verbatim",
          ARTIFACT_DOC["preregistered_tolerances"] == R.TOLERANCES)
    check("5b. it states they were used as written",
          ARTIFACT_DOC["preregistered_tolerances_used_as_written"] is True)
    tp = ARTIFACT_DOC["tolerance_provenance"]
    check("5c. tolerances are flagged as NOT preregistered specifically for HYP-04",
          tp["preregistered_specifically_for_hyp04"] is False)
    sdt = tp["pr18_satterthwaite_df_tolerance_reused_from_hyp01"]
    check("5d. the df tolerance is flagged as not preregistered for HYP-04",
          sdt["preregistered_for_hyp04"] is False)
    check("5e. it explains why the PR #17 exact-integer df rule cannot apply",
          "exact_integer_equality" in sdt["why_not_the_pr17_df_rule"])
    check("5f. PR17 and PR18 covered-field sets are disjoint",
          not (set(tp["pr17_covered_fields"]) & set(tp["pr18_covered_fields"])))
    check("5g. the df field is governed by the PR18 set only",
          tp["pr18_covered_fields"] == ["satterthwaite_df"]
          and "satterthwaite_df" not in tp["pr17_covered_fields"])
    check("5h. the preregistered df rule is still exact integer equality (unmodified)",
          R.TOLERANCES["degrees_of_freedom"] == {"exact_integer_equality": True})
    # no tolerance may be looser in the artifact than in the runner
    loosened = []
    for name, t in R.TOLERANCES.items():
        if name == "degrees_of_freedom":
            continue
        a = ARTIFACT_DOC["preregistered_tolerances"][name]
        if a["rtol"] > t["rtol"] or a["atol"] > t["atol"]:
            loosened.append(name)
    check(f"5i. no reused tolerance was loosened (loosened={loosened})", not loosened)
    check("5j. the module docstring explains why tolerances are reused, not re-derived",
          "reused" in RUNNER.read_text(encoding="utf-8").lower())


# ---------------------------------------------------------------- 6. refusals not forced
def test_6_refusals_are_reported_not_forced() -> None:
    if ARTIFACT_DOC is None:
        skip("6. refusal handling against the committed artifact", "no committed artifact yet")
        return
    by = {r_["fixture_id"]: r_ for r_ in ARTIFACT_DOC["results"]}
    both = [k for k, v in by.items() if v["classification"] == "REFUSED_BY_BOTH"]
    check(f"6a. at least G08 (fewer than two clusters) refuses on both sides ({both})",
          "G08_below_min_two_clusters" in both)
    check("6b. differing refusal reasons are recorded, not hidden",
          all("reference_refusal_reason" in by[k] and "python_refusal_reason" in by[k] for k in both))
    check("6e. no fixture was dropped: every committed fixture appears",
          {r_["fixture_id"] for r_ in ARTIFACT_DOC["results"]} == {n for n, _ in R.FIXTURE_SPECS})


# ---------------------------------------------------------------- 7. scope of the claim
FORBIDDEN_CLAIMS = (
    "cr2 is approved", "method is approved", "scientifically optimal", "is optimal",
    "supply-chain transmission exists", "supply chain transmission exists",
    "will be significant", "production ready", "production-ready",
    "recommended method is",
)


def _asserted_occurrences(text: str, phrase: str) -> list[str]:
    """Occurrences of `phrase` that are NOT directly negated (same pattern as HYP-01's test)."""
    negators = ("no ", "not ", "never", "nothing", "cannot", "n't", "neither", "without")
    out, start = [], 0
    while True:
        i = text.find(phrase, start)
        if i < 0:
            return out
        window = text[max(0, i - 45):i]
        if not any(n in window for n in negators):
            out.append(text[max(0, i - 45):i + len(phrase) + 15])
        start = i + len(phrase)


def test_7_no_overclaim() -> None:
    if ARTIFACT_DOC is None:
        skip("7. no-overclaim check against the committed artifact", "no committed artifact yet")
        return
    art = json.dumps(ARTIFACT_DOC).lower()
    for phrase in FORBIDDEN_CLAIMS:
        check(f"7a. artifact never asserts '{phrase}'", not _asserted_occurrences(art, phrase))
    check("7b. artifact records that no method is approved",
          ARTIFACT_DOC["method_approved"] is False)
    check("7c. artifact records the gate status is unchanged",
          ARTIFACT_DOC["implementation_validation"]["gate_status_changed"] is False)
    check("7d. artifact carries the exact two-part supported claim",
          ARTIFACT_DOC["supported_claim"] == CMP.SUPPORTED_CLAIM)


# ---------------------------------------------------------------- 8. isolation
def test_8_isolation() -> None:
    for f, label in ((EXPORT, "exporter"), (COMPARE, "comparison harness")):
        src = f.read_text(encoding="utf-8")
        check(f"8a. {label} blocks sockets before numerical imports",
              "socket.getaddrinfo = _deny_network" in src)
    rsrc = R_SCRIPT.read_text(encoding="utf-8")
    for tok in CANONICAL_TOKENS:
        check(f"8c. the R script never references {tok}", tok not in rsrc)
    check("8d. the R script does not download anything",
          not any(t in rsrc for t in ("install.packages", "download.file", "url(", "curl")))
    driver = DRIVER.read_text(encoding="utf-8")
    check("8e. the driver installs nothing",
          "install.packages" not in driver and "pip install" not in driver)

    # Production code must not import this bridge. Plain substring scan over
    # every non-test, non-tools/ .py file, same pattern as HYP-01's
    # test_8_isolation and test_repo_invariants.py -- it cannot distinguish an
    # import from a passing mention, which is intentional: a passing mention
    # should also route through a description rather than the literal path
    # (as hyp04_supply_chain_hedge/clustered_se.py already does).
    offenders = []
    for p in ROOT.rglob("*.py"):
        if p.name.startswith("test_") or "hyp04_r_reference" in str(p) or "tools" in p.parts:
            continue
        try:
            if "hyp04_r_reference" in p.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(p.relative_to(ROOT)))
        except OSError:
            pass
    check(f"8f. no production module imports this bridge (offenders={offenders})", not offenders)
    check("8g. compare_reference.py imports FROM production (the opposite, allowed direction)",
          "hyp04_supply_chain_hedge.clustered_se" in COMPARE.read_text(encoding="utf-8"))
    try:
        socket.getaddrinfo("example.com", 443)
        check("8h. network blocked", False)
    except Exception as e:
        check("8h. network blocked", type(e).__name__ == "NetworkBlocked")


# ---------------------------------------------------------------- 9. pinning
def test_9_dependencies_are_pinned() -> None:
    check("9a. R version is pinned", LOCK_DOC["r"]["version"] == "4.6.1")
    check("9b. the installer hash is recorded", len(LOCK_DOC["r"]["installer_sha256"]) == 64)
    pkgs = {p["package"]: p for p in LOCK_DOC["packages"]}
    check("9c. clubSandwich is pinned, with its Windows binary hash scoped to Windows",
          "clubSandwich" in pkgs
          and len(pkgs["clubSandwich"]["local_windows_binary"]["sha256"]) == 64
          and "Windows" in pkgs["clubSandwich"]["local_windows_binary"]["authenticates"])
    check("9d. every pinned package has an exact version",
          all(re.fullmatch(r"[\d.\-]+", p["version"]) for p in LOCK_DOC["packages"]))
    check("9e. every CI action is pinned to an immutable commit SHA",
          all(re.fullmatch(r"[0-9a-f]{40}", a["pinned_commit_sha"])
              for a in LOCK_DOC["github_actions"]) and len(LOCK_DOC["github_actions"]) >= 3)
    check("9h. the lockfile's package_count matches the list it carries",
          LOCK_DOC["package_count"] == len(LOCK_DOC["packages"]) == 10)
    check("9f. no wild-bootstrap reference was installed",
          "fwildclusterboot" not in {p["package"] for p in LOCK_DOC["packages"]})
    check("9g. the lock states installing it approves no method",
          "approves no statistical method" in LOCK_DOC["purpose"])
    check("9i. the observed snapshot-binary instability is recorded, not hidden",
          "observed_snapshot_binary_instability" in LOCK_DOC
          and LOCK_DOC["observed_snapshot_binary_instability"]["what_was_observed"])


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
                "coefficients": ["1.0", "2.0", "3.0"],
                "cr2_covariance": [["1.0", "0.0", "0.0"], ["0.0", "1.0", "0.0"], ["0.0", "0.0", "1.0"]],
                "target_variance": "1.0", "target_estimate": "2.0",
                "standard_error": "1.0", "t_statistic": "2.0",
                "satterthwaite_df": "10.0", "p_value": "0.5",
                "conf_int_defined": False}}}
        rr = fake_ref["results"][target["fixture_id"]]
        py = CMP.python_side(R, target)
        rec = CMP.compare_one(target, py, rr, R.TOLERANCES)
        check("10d. a deliberately wrong reference is NOT classified as a match",
              rec["classification"] != CMP.MATCH, rec["classification"])
        check("10e. and it is classified UNRESOLVED, forcing diagnosis",
              rec["classification"] == "UNRESOLVED", rec["classification"])


# ---------------------------------------------------------------- 11. artifact verifier
def test_11_artifact_verifier_rejects_a_corrupted_artifact() -> None:
    """The verifier must FAIL on a doctored artifact, or it proves nothing."""
    if ARTIFACT_DOC is None:
        skip("11. artifact verifier tests", "no committed artifact yet")
        return
    with tempfile.TemporaryDirectory() as td:
        good = ARTIFACT_DOC
        cases = {}

        c1 = json.loads(json.dumps(good))
        for r_ in c1["results"]:
            if r_.get("python_values"):
                r_["python_values"]["standard_error"] *= 1.01
                break
        cases["perturbed numeric value"] = c1

        c2 = json.loads(json.dumps(good))
        for r_ in c2["results"]:
            if r_["classification"] == CMP.MATCH:
                r_["classification"] = "REFUSED_BY_BOTH"
                break
        cases["altered classification"] = c2

        c3 = json.loads(json.dumps(good))
        c3["tolerance_provenance"]["preregistered_specifically_for_hyp04"] = True
        cases["falsified tolerance provenance"] = c3

        c4 = json.loads(json.dumps(good))
        c4["results"] = c4["results"][:-1]
        cases["dropped fixture"] = c4

        for label, doc in cases.items():
            f = Path(td) / "bad.json"
            f.write_text(json.dumps(doc), encoding="utf-8")
            r = subprocess.run([sys.executable, str(VERIFY), "--fresh", str(f),
                                "--committed", str(ARTIFACT_PATH)],
                               capture_output=True, text=True, timeout=600)
            check(f"11a. verifier rejects: {label}", r.returncode != 0)

        r = subprocess.run([sys.executable, str(VERIFY), "--fresh", str(ARTIFACT_PATH),
                            "--committed", str(ARTIFACT_PATH)],
                           capture_output=True, text=True, timeout=600)
        check("11b. verifier accepts the committed artifact against itself", r.returncode == 0,
              (r.stdout or "")[-200:])


# ---------------------------------------------------------------- 12. CI enforcement
def test_12_ci_enforces_the_lock_and_pins_every_action() -> None:
    wf_path = ROOT / ".github" / "workflows" / "hyp04-r-reference-validation.yml"
    wf = wf_path.read_text(encoding="utf-8")

    uses = re.findall(r"uses:\s*([^\s#]+)", wf)
    movable = [u for u in uses if not re.search(r"@[0-9a-f]{40}$", u)]
    check(f"12a. every workflow action is pinned to an immutable SHA (movable={movable})", not movable)
    check("12b. the workflow uses at least three external actions", len(uses) >= 3)
    locked_shas = {a["pinned_commit_sha"] for a in LOCK_DOC["github_actions"]}
    used_shas = {u.split("@")[1] for u in uses if "@" in u}
    check(f"12c. every action SHA used is recorded in the lockfile "
          f"(unrecorded={sorted(used_shas - locked_shas)})", used_shas <= locked_shas)

    check("12d. CI iterates over the lockfile's package list rather than a literal subset",
          "lock$packages" in wf and "seq_len(nrow(pkgs))" in wf)
    check("12d2. the install list is resolved from the lockfile, not hardcoded",
          "r-packages.lock.json" in wf and "R_LOCKED_PKGS" in wf
          and 'install.packages(pkgs' in wf)
    check("12d3. the snapshot URL is read from the lockfile, not duplicated in the workflow",
          "R_SNAPSHOT" in wf and LOCK_DOC["sources"]["ci_snapshot_linux_binary_path"] not in wf)
    check("12f. CI fails closed on a version mismatch",
          "LOCKFILE VIOLATION" in wf and "quit(status = 1)" in wf)
    check("12f2. versions are compared as versions, not as strings",
          "numeric_version(exp)" in wf)
    check("12g. CI verifies the exact R version",
          "R VERSION MISMATCH" in wf and "ci_pinned_version" in wf)
    check("12h. CI installs only required dependency classes, never Suggests",
          'dependencies = c("Depends", "Imports", "LinkingTo")' in wf
          and "dependencies = TRUE" not in wf)
    check("12m. CI runs the full artifact verifier", "verify_artifact.py" in wf)
    ver = VERIFY.read_text(encoding="utf-8")
    for field in ("python_values", "reference_values", "tolerance_provenance",
                  "max_abs_difference", "reference_warnings", "clubSandwich", "classification"):
        check(f"12n. artifact verification covers {field}", field in ver)
    check("12o. artifact verification does not demand bitwise equality",
          "CROSS_ENV" in ver and "rtol" in ver)
    check("12p. CI is scoped separately from the ordinary HYP-04 test workflow",
          "hyp04-supply-chain-hedge-tests.yml" not in wf)


# ---------------------------------------------------------------- 13. HYP-04 protected state
def test_13_hyp04_protected_state_unaffected() -> None:
    """This bridge must move no HYP-04 gate condition or already-signed artifact."""
    phase2 = LS / "HYP04_PHASE2_LOCK_2026-09-10.json"
    if phase2.exists():
        p2 = json.loads(phase2.read_text(encoding="utf-8"))
        check("13a. the signed Phase 2 lock is still declared/signed",
              p2.get("declared") is True)
    else:
        skip("13a. Phase 2 lock check", "artifact not present in this checkout")
    check("13b. clustered_se.py's provenance docstring is unchanged by this bridge",
          "COPY, NOT AN IMPORT" in CSE.read_text(encoding="utf-8"))
    check("13c. this bridge's own artifact never claims a gate condition changed",
          ARTIFACT_DOC is None or ARTIFACT_DOC["implementation_validation"]["gate_status_changed"] is False)


if __name__ == "__main__":
    test_1_interchange_is_built_from_the_committed_generator()
    test_2_interchange_carries_no_research_value()
    test_3_reference_reruns_and_recompares()
    test_4_python_side_is_recomputed_not_read()
    test_5_tolerances_are_reused_correctly()
    test_6_refusals_are_reported_not_forced()
    test_7_no_overclaim()
    test_8_isolation()
    test_9_dependencies_are_pinned()
    test_10_driver_exits_nonzero_on_unexplained_mismatch()
    test_11_artifact_verifier_rejects_a_corrupted_artifact()
    test_12_ci_enforces_the_lock_and_pins_every_action()
    test_13_hyp04_protected_state_unaffected()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 D10 R-REFERENCE VALIDATION TESTS PASSED")
    sys.exit(0)
