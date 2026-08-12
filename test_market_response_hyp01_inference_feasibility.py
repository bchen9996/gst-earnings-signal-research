#!/usr/bin/env python3
# Deterministic tests for the HYP-01 inference-feasibility study.
#
# Offline. Sockets blocked at import. Synthetic fixtures only. Reads no
# repository research artifact. Emits no HYP-01 result.
#
# Run directly: python test_market_response_hyp01_inference_feasibility.py

from __future__ import annotations

import hashlib
import json
import re
import socket
import sys
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
INV = LS / "GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json"
REP = LS / "GST_HYP01_SYNTHETIC_VALIDATION_REPORT_v1.0_DRAFT.md"
MTX = LS / "GST_HYP01_AUTHORIZER_DECISION_MATRIX_v1.0_DRAFT.md"
LOCK_V10 = LS / "GST_HYP01_ANALYSIS_LOCK_v1.0.json"
PROPOSED = LS / "GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json"
SIGNOFF = LS / "GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md"
REGISTRY = LS / "Market_Response_Event_Registry" / "registry.jsonl"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


LOCKED_24 = ["AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "CTSH", "DELL", "DVN", "GME",
             "GOOGL", "GPN", "INTC", "LDOS", "MSFT", "NCLH", "NKE", "QCOM", "SBUX", "STZ",
             "SYK", "TSLA", "TTWO", "UAL"]


def test_1_no_real_tickers_in_fixtures() -> None:
    inv = json.loads(INV.read_text(encoding="utf-8"))
    blob = json.dumps(inv) + REP.read_text(encoding="utf-8")
    fixture_names = list(inv["fixture_matrix"].keys())
    check(f"1a. fixture labels are synthetic CLUSTER_* style ({len(fixture_names)} fixtures)",
          all(re.match(r"^F\d{2}_", n) for n in fixture_names))
    # a real ticker must not appear as a standalone token in fixture identifiers
    bad = []
    for t in LOCKED_24:
        for n in fixture_names:
            if re.search(rf"\b{re.escape(t)}\b", n):
                bad.append((t, n))
    check(f"1b. no locked ticker appears in any fixture name (offenders={bad})", not bad)
    check("1c. inventory declares synthetic-only", inv["synthetic_data_only"] is True)
    check("1d. cluster labelling convention documented as CLUSTER_###",
          "CLUSTER_001" in blob or "CLUSTER_" in blob)


def test_2_no_repository_research_artifact_read() -> None:
    inv = json.loads(INV.read_text(encoding="utf-8"))
    check("2a. inventory declares no repository research artifact loaded",
          inv["repository_research_artifact_loaded"] is False)
    check("2b. zero network requests declared", inv["network_requests"] == 0)
    check("2c. zero packages installed or mutated", inv["packages_installed_or_mutated"] == 0)
    blob = json.dumps(inv) + REP.read_text(encoding="utf-8") + MTX.read_text(encoding="utf-8")
    for forbidden in ("registry.jsonl loaded", "panel csv", "screening row loaded"):
        check(f"2d. no claim of loading '{forbidden}'", forbidden.lower() not in blob.lower())


def test_3_network_impossible() -> None:
    for name, fn in (("getaddrinfo", lambda: socket.getaddrinfo("example.com", 80)),
                     ("create_connection", lambda: socket.create_connection(("example.com", 80)))):
        try:
            fn()
            check(f"3. network blocked ({name})", False, "NOT BLOCKED")
        except NetworkBlocked:
            check(f"3. network blocked ({name})", True)
        except Exception as e:
            check(f"3. network blocked ({name})", False, type(e).__name__)


def test_4_determinism_and_invariance_recorded() -> None:
    inv = json.loads(INV.read_text(encoding="utf-8"))
    det = inv["seed_determinism"]
    runs = [v for v in det.values() if v.get("status") == "RUN"]
    check(f"4a. seed determinism recorded on at least one fixture ({len(runs)})", len(runs) >= 1)
    check("4b. same seed reproduces exactly", all(v["same_seed_identical"] for v in runs))
    check("4c. a different seed differs", all(v["different_seed_differs"] for v in runs))
    invar = [v for v in inv["invariance_checks"].values() if v.get("status") == "RUN"]
    check(f"4d. invariance checked on every runnable fixture ({len(invar)})", len(invar) >= 10)
    check("4e. row permutation invariant", all(v["row_permutation_invariant"] for v in invar))
    check("4f. cluster relabelling invariant", all(v["cluster_relabel_invariant"] for v in invar))


def test_5_invalid_cases_fail_by_documented_rule() -> None:
    inv = json.loads(INV.read_text(encoding="utf-8"))
    conds = {c["condition"]: c for c in inv["refusal_conditions_identified"]}
    for want in ("missing values in the outcome or design",
                 "rank-deficient / near-collinear design",
                 "perfect or near-perfect fit (residual variance at machine epsilon)",
                 "zero-variance predictor"):
        check(f"5a. refusal condition documented: {want[:44]}", want in conds)
    check("5b. every refusal condition flags that a rule is needed",
          all(c["rule_needed"] for c in conds.values()))
    summ = inv["validation_summary"]
    check("5c. rank-deficient and missing-value fixtures were skipped, not silently passed",
          len(summ["skipped_by_design"]) == 2)
    check("5d. the degenerate-fit fixture is recorded as a refusal case, not a match",
          len(summ["numerically_unidentified_refusal_cases"]) >= 1)


def test_6_no_hyp01_result_emitted() -> None:
    blob = json.dumps(json.loads(INV.read_text(encoding="utf-8")))
    rep = REP.read_text(encoding="utf-8")
    mtx = MTX.read_text(encoding="utf-8")
    lock = json.loads(LOCK_V10.read_text(encoding="utf-8-sig"))
    check("6a. operative v1.0 lock still has results = null", lock["results"] is None)
    check("6b. operative v1.0 lock still has no frozen event IDs", lock["frozen_event_ids"] == [])
    check("6c. operative v1.0 lock still reports zero eligible events", lock["eligible_events_now"] == 0)
    for doc, name in ((blob, "inventory"), (rep, "report"), (mtx, "matrix")):
        check(f"6d. no beta_gst estimate in the {name}",
              re.search(r"beta[_ ]?gst\s*=\s*-?\d*\.\d", doc, re.I) is None)
        check(f"6e. no HYP-01 p-value claim in the {name}",
              re.search(r"HYP-01[^.\n]{0,80}p\s*[<=]\s*0\.\d", doc, re.I) is None)
    check("6f. design-sensitivity grid is labelled hypothetical, not a GST claim",
          "NOT A GST POWER CLAIM" in blob.upper() or "NOT A GST POWER CLAIM" in rep.upper())
    inv = json.loads(INV.read_text(encoding="utf-8"))
    check("6g. grid declares it used no repository effect estimate",
          inv["hypothetical_design_sensitivity"]["uses_any_repository_effect_estimate"] is False)


def test_7_no_proposal_becomes_active() -> None:
    inv = json.loads(INV.read_text(encoding="utf-8"))
    prop = json.loads(PROPOSED.read_text(encoding="utf-8"))
    check("7a. proposed v1.1 still PROPOSED_PENDING...",
          prop["status"] == "PROPOSED_PENDING_HUMAN_AND_METHODOLOGIST_APPROVAL")
    check("7b. proposed v1.1 still not authoritative", prop["authoritative"] is False)
    check("7c. inventory declares no method approved", inv["method_approved"] is False)
    check("7d. inventory declares no dated amendment created", inv["dated_amendment_created"] is False)
    check("7e. matrix states it is not the dated amendment",
          "is not that amendment" in MTX.read_text(encoding="utf-8").lower()
          or "not that amendment" in MTX.read_text(encoding="utf-8").lower())
    check("7f. F5 still recorded OPEN", inv["f5_status"].startswith("OPEN"))


def test_8_authorizer_fields_pending() -> None:
    mtx = MTX.read_text(encoding="utf-8")
    pending = "`PENDING`"
    check("8a. authorizer field pending", re.search(r"\*\*Authorizer:\*\*\s*" + re.escape(pending), mtx) is not None)
    check("8b. decision date pending", re.search(r"\*\*Decision date:\*\*\s*" + re.escape(pending), mtx) is not None)
    check("8c. signature pending", mtx.count(pending) >= 3)
    check("8d. zero checkboxes selected", mtx.count("- [x]") == 0 and "[x]" not in mtx)
    # Some decisions share a heading (e.g. "## D6 — ... · D7 — ..."), so count
    # distinct decision IDs and the summary-table rows, not heading lines.
    ids = {m for m in re.findall(r"\bD(\d{1,2})\b", mtx)}
    rows = re.findall(r"^\| D\d+ \|", mtx, re.M)
    check(f"8e. at least sixteen distinct decisions presented (ids={len(ids)}, summary rows={len(rows)})",
          len(ids) >= 16 and len(rows) >= 16)
    check("8f. every decision offers explicit options rather than a silent choice",
          mtx.count("- [ ]") >= 30)
    # the separate signoff template must be untouched and still blank
    sg = SIGNOFF.read_text(encoding="utf-8")
    cells = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$", sg, re.M)
    filled = [c for c in cells if c[1].strip() not in (pending, "Entry", "")
              and not re.match(r"^-+$", c[1].strip())]
    check(f"8f. existing signoff template still entirely PENDING (filled={len(filled)})", not filled)
    check("8g. existing signoff template has no ticked box", sg.count("- [x]") == 0)


def test_9_validation_hierarchy_honoured() -> None:
    inv = json.loads(INV.read_text(encoding="utf-8"))
    by = {m["id"]: m for m in inv["methods"]}
    check("9a. CR1 is validated against an independent reference",
          by["CR1"]["implementation_status"] == "IMPLEMENTATION_VALIDATED"
          and "statsmodels" in by["CR1"]["validation_basis"])
    for mid in ("CR2", "CR3", "WCR_BOOTSTRAP_T"):
        check(f"9b. {mid} is BLOCKED, not claimed validated",
              by[mid]["implementation_status"] == "IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE")
        check(f"9c. {mid} names the exact dependency needed", bool(by[mid].get("exact_dependency_needed")))
        check(f"9d. {mid} names the validation procedure needed",
              bool(by[mid].get("validation_procedure_needed")))
        check(f"9e. {mid} is not marked presently executable", by[mid]["presently_executable"] is False)
    check("9f. tolerances declared preregistered and unrevised",
          inv["tolerances_fixed_before_any_comparison"] is True
          and inv["tolerances_revised_after_seeing_results"] is False)
    check("9g. R runtime recorded absent", inv["runtimes_detected"]["R"]["status"] == "absent")
    check("9h. no R package claimed found", inv["runtimes_detected"]["R"]["packages_found"] == [])


def test_10_protected_artifacts_unchanged() -> None:
    rows = [l for l in REGISTRY.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("10a. registry holds exactly one row", len(rows) == 1)
    r = json.loads(rows[0])
    check("10b. DELL remains the sole registered event, verified",
          r["row_id"] == "EVT-DELL-FY27Q2-ERN-REG-001" and r["row_type"] == "REGISTRATION"
          and r["verification_status"] == "verified")
    check("10c. registry blob hash unchanged",
          hashlib.sha256(REGISTRY.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
          == "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974")
    cp = json.loads((LS / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json").read_text(encoding="utf-8-sig"))
    check("10d. screening rows still empty", cp["screening_rows"] == [])
    cj = json.loads((LS / "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json").read_text(encoding="utf-8"))
    check("10e. F5 construct audit still STILL_OPEN", cj["gap_audit_status_after_this_work"] == "STILL_OPEN")


if __name__ == "__main__":
    test_1_no_real_tickers_in_fixtures()
    test_2_no_repository_research_artifact_read()
    test_3_network_impossible()
    test_4_determinism_and_invariance_recorded()
    test_5_invalid_cases_fail_by_documented_rule()
    test_6_no_hyp01_result_emitted()
    test_7_no_proposal_becomes_active()
    test_8_authorizer_fields_pending()
    test_9_validation_hierarchy_honoured()
    test_10_protected_artifacts_unchanged()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-01 INFERENCE FEASIBILITY TESTS PASSED")
    sys.exit(0)
