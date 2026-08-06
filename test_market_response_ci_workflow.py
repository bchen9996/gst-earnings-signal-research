#!/usr/bin/env python3
# Static, deterministic assertions about the Market Response CI workflow.
#
# Reads .github/workflows/market-response-tests.yml as text and proves that (a)
# it discovers the full intended suite rather than a hardcoded subset, and (b)
# it can never invoke a live-network, credentialed, or panel-running command.
#
# Pure file inspection -- no network, no subprocess, no credentials.
#
# Run directly: python test_market_response_ci_workflow.py

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = HERE / ".github" / "workflows" / "market-response-tests.yml"

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


def test_workflow_exists_and_is_wired_up():
    check("1a. the market-response workflow file exists", WORKFLOW.is_file())
    text = WORKFLOW.read_text(encoding="utf-8")
    check("1b. it triggers on pull_request", "pull_request:" in text)
    check("1c. it supports workflow_dispatch", "workflow_dispatch:" in text)
    check("1h. it carries the branch-specific push bootstrap trigger", "push:" in text)
    check("1d. it declares least-privilege contents: read", "contents: read" in text)
    check("1e. it pins a specific Python version", 'python-version: "3.12"' in text)
    check("1f. it installs the repository's pinned requirements",
          "pip install -r requirements.txt" in text)
    check("1g. it never grants write permissions",
          "contents: write" not in text and "packages: write" not in text)


def test_all_three_triggers_are_present_and_correctly_scoped():
    """pull_request + workflow_dispatch + the branch-scoped push bootstrap.

    The push trigger exists only because GitHub scheduled nothing from the
    pull_request trigger (see the workflow's own header comment). It must stay
    pinned to this one branch -- an unscoped push trigger would run this suite
    on every branch in the repository.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    lines = [l.rstrip() for l in text.splitlines()]

    check("8a. all three triggers declared", all(
        t in text for t in ("push:", "pull_request:", "workflow_dispatch:")))

    # The push trigger must be branch-scoped, and to exactly this branch.
    try:
        i = lines.index("  push:")
    except ValueError:
        i = -1
    check("8b. push: is a top-level trigger key (two-space indent)", i >= 0)
    if i >= 0:
        block = lines[i + 1:i + 4]
        check("8c. push declares a branches: filter", any(l.strip() == "branches:" for l in block))
        check("8d. push is pinned to phase2-market-response only",
              any(l.strip() == "- phase2-market-response" for l in block))
        # No second branch smuggled in before the next trigger key.
        nxt = next((j for j in range(i + 1, len(lines))
                    if lines[j].startswith("  ") and lines[j].strip().endswith(":")
                    and not lines[j].startswith("    ")), len(lines))
        branch_entries = [l.strip() for l in lines[i + 1:nxt] if l.strip().startswith("- ")]
        check(f"8e. exactly one push branch is listed (found {branch_entries})",
              branch_entries == ["- phase2-market-response"])

    check("8f. push is NOT wildcarded to all branches",
          "'**'" not in text and '"**"' not in text and "branches: ['*']" not in text)
    check("8g. the bootstrap is documented as temporary in the workflow itself",
          "BOOTSTRAP TRIGGER" in text and "Remove it once" in text)


def test_path_filters_cover_every_relevant_surface():
    text = WORKFLOW.read_text(encoding="utf-8")
    required_paths = [
        "gst_market_response/**",
        "test_market_response*.py",
        "Event_Dossier_Protocol/**",
        "requirements.txt",
        ".github/workflows/market-response-tests.yml",
        "GST_Earnings_Market_Response_Decomposition_SPEC_v0.1_DRAFT.md",
        "GST_MARKET_RESPONSE_FIELD_DICTIONARY_v0.1.md",
    ]
    for p in required_paths:
        check(f"2. path filter includes {p}", p in text)


def test_discovery_is_dynamic_and_complete():
    text = WORKFLOW.read_text(encoding="utf-8")
    check("3a. the suite is discovered with a glob, not a hardcoded filename",
          "ls test_market_response*.py" in text)
    check("3b. zero discovered files is treated as a failure, not a pass",
          "failing rather than reporting a vacuous success" in text and "exit 1" in text)

    # Every deterministic test file on disk must actually be reachable by the
    # workflow's discovery glob.
    on_disk = sorted(p.name for p in HERE.glob("test_market_response*.py"))
    check(f"3c. discovery glob would run all {len(on_disk)} market-response test files on disk",
          len(on_disk) >= 13)
    check("3d. the new integration test files are among them",
          {"test_market_response_protocol_boundary.py",
           "test_market_response_layer_b_emission.py",
           "test_market_response_canonical_drift.py",
           "test_market_response_phase2_status_normalization.py",
           "test_market_response_ci_workflow.py"} <= set(on_disk))
    check("3e. the cross-protocol validator suite is also run",
          "Event_Dossier_Protocol/validator" in text and "ls test_*.py" in text)


def test_workflow_contains_no_live_network_command():
    text = WORKFLOW.read_text(encoding="utf-8")
    forbidden = [
        "phase2_live_smoke_wiki_equivalence",
        "GST_Phase2_DailyPanel",
        "alpaca_intraday_diagnostic",
        "intraday_provider_diagnostic",
        "validate_amzn_wiki_only",
        "diagnose_wiki_watermark_only",
        "Phase2_Wikipedia_Cache",
        "wikimedia.org",
        "data.alpaca.markets",
        "paper-api.alpaca.markets",
        "api.alpaca.markets",
        "yfinance",
        "sec.gov",
        "polygon.io",
        "alphavantage",
    ]
    for token in forbidden:
        check(f"4. workflow never references {token}", token not in text)


def test_workflow_never_uses_credentials():
    text = WORKFLOW.read_text(encoding="utf-8")
    for token in ("secrets.", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "ALPACA_"):
        check(f"5. workflow never references {token}", token not in text)


def test_live_smoke_script_is_off_the_discovery_pattern():
    """The live smoke script must remain un-discoverable by any test_* glob."""
    live = HERE / "phase2_live_smoke_wiki_equivalence.py"
    check("6a. the live smoke script still exists (not deleted)", live.is_file())
    check("6b. it is NOT named test_*.py, so no discovery convention can reach it",
          not live.name.startswith("test_"))
    check("6c. it is not matched by the market-response discovery glob",
          live.name not in {p.name for p in HERE.glob("test_market_response*.py")})


def test_dossier_workflow_is_left_untouched():
    """This pass adds a workflow; it must not have altered the existing one."""
    dossier = HERE / ".github" / "workflows" / "event-dossier-validator-tests.yml"
    check("7a. the event-dossier workflow still exists", dossier.is_file())
    text = dossier.read_text(encoding="utf-8")
    check("7b. it still declares least privilege", "contents: read" in text)
    check("7c. it still discovers every validator test file", "ls test_*.py" in text)


if __name__ == "__main__":
    test_workflow_exists_and_is_wired_up()
    test_all_three_triggers_are_present_and_correctly_scoped()
    test_path_filters_cover_every_relevant_surface()
    test_discovery_is_dynamic_and_complete()
    test_workflow_contains_no_live_network_command()
    test_workflow_never_uses_credentials()
    test_live_smoke_script_is_off_the_discovery_pattern()
    test_dossier_workflow_is_left_untouched()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL CI WORKFLOW TESTS PASSED")
    sys.exit(0)
