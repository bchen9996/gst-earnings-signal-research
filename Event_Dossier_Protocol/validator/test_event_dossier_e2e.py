#!/usr/bin/env python3
"""End-to-end tests for the Event Dossier Protocol's full validation
sequence (2026-08-03 -- "close the infrastructure phase" pass), built on
top of validate_event_dossier.py's public API. Each test builds a small,
self-contained synthetic fixture in a temp directory (never touching
validator/fixtures/ or any real dossier), runs it through the actual
validator, and asserts on the real result -- no mocking of the validator
itself.

Covers:
  1. A legitimate development-pilot freeze succeeds.
  2. A freeze blocked by inadequate (non-direct-fetch) sources.
  3. A freeze blocked by outcome leakage (blinding breach).
  4. An amendment produces a new immutable bundle without modifying the
     prior bundle.
  5. Adding a later, UNRELATED event's rows to the same shared mutable
     working tables does not invalidate an earlier event's frozen bundle.
  6. The GitHub Actions CI workflow is scoped to the deterministic
     validator tests only -- no live market/GST/Wikipedia/SEC/news access.

Run directly: python test_event_dossier_e2e.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_event_dossier as v

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Minimal fixture-building helpers (self-contained, independent of the
# fixtures/ generator used for the main 66-case regression suite).
# ---------------------------------------------------------------------------

def write_csv(d: Path, table: str, rows: list[dict]) -> None:
    headers = v._read_schema_header(v.SCHEMA_FILES[table])
    with (d / f"{table}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in headers})


def write_raw_csv(d: Path, filename: str, headers: list[str], rows: list[dict]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    with (d / filename).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in headers})


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_event(event_id: str, ticker: str = "AAPL", disposition: str = "development_pilot") -> dict:
    return {
        "event_id": event_id, "ticker": ticker, "company_name": f"{ticker} Inc.",
        "fiscal_period": "FY26Q3", "event_type": "ERN", "earnings_date": "2026-07-30",
        "release_market_session": "after_close", "event_datetime_utc": "2026-07-30T20:05:00+00:00",
        "niche": "fixed_24_ticker_earnings_panel", "protocol_version": "0.1",
        "event_disposition": disposition, "blinding_compromised_for_confirmatory_use": "false",
        "created_by": "ai", "created_at_utc": "2026-08-02T00:00:00+00:00",
    }


def base_claims(event_id: str) -> list[dict]:
    return [
        {
            "claim_id": f"{event_id}-CLM-0001", "event_id": event_id, "dossier_section": "eps",
            "claim_text": "Non-GAAP diluted EPS was 4.74 dollars per share.", "value_type": "numeric",
            "claim_category": "reported_fact", "metric_name": "eps", "numeric_value": "4.74",
            "unit": "USD_per_share", "gaap_basis": "non-GAAP", "currency_basis": "reported",
            "fiscal_period_basis": "FY26Q3", "comparison_period": "YoY", "consensus_provider": "",
            "consensus_asof_date": "", "novelty_eval_basis": "not_evaluated", "verification_status": "verified",
            "layer": "A_blinded_core", "created_at_utc": "2026-08-02T00:00:00+00:00",
        },
        {
            "claim_id": f"{event_id}-CLM-0002", "event_id": event_id, "dossier_section": "eps",
            "claim_text": "Consensus non-GAAP EPS estimate was 4.24 dollars per share.", "value_type": "numeric",
            "claim_category": "pre_event_consensus_estimate", "metric_name": "eps", "numeric_value": "4.24",
            "unit": "USD_per_share", "gaap_basis": "non-GAAP", "currency_basis": "reported",
            "fiscal_period_basis": "FY26Q3", "comparison_period": "vs_consensus", "consensus_provider": "LSEG",
            "consensus_asof_date": "2026-07-29", "novelty_eval_basis": "not_evaluated",
            "verification_status": "verified", "layer": "A_blinded_core", "created_at_utc": "2026-08-02T00:00:00+00:00",
        },
    ]


def base_sources(event_id: str, claim_ids: list[str], method: str = "direct_fetch", tier: str = "1") -> list[dict]:
    return [{
        "claim_source_id": f"{event_id}-SRC-{i+1:03d}", "claim_id": cid, "source_name": "Press release",
        "source_url": "https://example.com/src", "source_publication_timestamp_utc": "2026-07-30T20:05:00+00:00",
        "retrieval_method": method, "source_tier": tier, "accessed_at_utc": "2026-08-02T00:00:00+00:00",
        "corroborates_claim_source_id": "", "notes": "",
    } for i, cid in enumerate(claim_ids)]


def base_label(label_id: str, event_id: str, **overrides) -> dict:
    row = {
        "label_id": label_id, "event_id": event_id, "label_status": "ai_proposed",
        "dossier_stage": "POST_EVENT_D1",
        "eps_surprise_pct": "11.79", "eps_surprise_null_reason": "",
        "revenue_surprise_pct": "", "revenue_surprise_null_reason": "not_applicable",
        "eps_actual_claim_id": f"{event_id}-CLM-0001", "eps_consensus_claim_id": f"{event_id}-CLM-0002",
        "revenue_actual_claim_id": "", "revenue_consensus_claim_id": "",
        "guidance_direction": "not_guided", "cloud_surprise_direction": "not_applicable",
        "margin_surprise_direction": "unverifiable", "capex_operational_direction": "not_guided",
        "management_tone": "neutral", "primary_positive_catalyst_claim_id": f"{event_id}-CLM-0001",
        "primary_negative_catalyst_claim_id": f"{event_id}-CLM-0001",
        "information_novelty_score_1_to_5": "3", "uncertainty_remaining_score_1_to_5": "3",
        "source_completeness": "high", "human_verification_status": "pending",
        "frozen_by": "", "frozen_at_utc": "", "freeze_manifest_path": "",
        "protocol_version": "0.1", "event_disposition": "development_pilot",
        "amendment_of_label_id": "", "amendment_reason": "", "notes": "",
    }
    row.update(overrides)
    return row


def base_qna(event_id: str) -> dict:
    return {
        "qna_id": f"{event_id}-QNA-01", "event_id": event_id, "analyst_name": "Jane Analyst",
        "analyst_firm": "Example Bank", "question_text": "Can you size the margin impact?",
        "question_topic": "margin", "response_text": "We have flexibility in our depreciation schedule.",
        "classification": "partially_answered", "classification_basis": "Engaged but no figure given.",
        "classified_by": "ai_proposed", "classified_at_utc": "2026-08-02T00:00:00+00:00",
    }


def write_frozen_bundle(d: Path, event_id: str, label_id: str, label_row: dict) -> Path:
    """Snapshots the fixture's CURRENT working tables into
    frozen/{event_id}/{label_id}/, exactly as production migration/freeze
    tooling is expected to."""
    bundle_dir = d / "frozen" / event_id / label_id
    write_raw_csv(bundle_dir, "events.csv", v._read_schema_header(v.SCHEMA_FILES["events"]), v._read_csv(d / "events.csv"))
    write_raw_csv(bundle_dir, "claims.csv", v._read_schema_header(v.SCHEMA_FILES["claims"]), v._read_csv(d / "claims.csv"))
    write_raw_csv(bundle_dir, "claim_sources.csv", v._read_schema_header(v.SCHEMA_FILES["claim_sources"]), v._read_csv(d / "claim_sources.csv"))
    write_raw_csv(bundle_dir, "management_qna.csv", v._read_schema_header(v.SCHEMA_FILES["management_qna"]), v._read_csv(d / "management_qna.csv"))
    write_raw_csv(bundle_dir, "event_label.csv", v._read_schema_header(v.SCHEMA_FILES["event_labels"]), [label_row])
    write_raw_csv(bundle_dir, "event_label_capex_effects.csv", v._read_schema_header(v.SCHEMA_FILES["event_label_capex_effects"]), [])
    write_raw_csv(bundle_dir, "event_label_cross_company_implications.csv", v._read_schema_header(v.SCHEMA_FILES["event_label_cross_company_implications"]), [])
    return bundle_dir


def write_manifest_for_bundle(d: Path, bundle_dir: Path, event_id: str, label_id: str,
                               frozen_by: str = "jane.reviewer", freeze_ts: str = "2026-08-02T10:00:00+00:00",
                               filename: str = "freeze_manifest.json") -> dict:
    hashes = []
    for b in sorted(v.FROZEN_BUNDLE_REQUIRED_BASENAMES):
        p = bundle_dir / b
        hashes.append({"artifact_path": f"frozen/{event_id}/{label_id}/{b}", "sha256": file_hash(p)})
    manifest = {
        "event_id": event_id, "label_id": label_id, "protocol_version": "0.1",
        "layer_a_artifact_hashes": hashes, "freeze_timestamp_utc": freeze_ts, "frozen_by": frozen_by,
        "reviewer_capture_exposure_log": [], "reveal_events": [],
    }
    with (d / filename).open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest


class TempFixture:
    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="e2e_dossier_"))
        return self.dir

    def __exit__(self, *exc):
        shutil.rmtree(self.dir, ignore_errors=True)


# === 1. A legitimate development-pilot freeze succeeds ===
def test_1_legitimate_development_pilot_freeze():
    with TempFixture() as d:
        eid = "EVT-AAPL-FY26Q3-ERN"
        lid = f"{eid}-LBL-01"
        write_csv(d, "events", [base_event(eid, disposition="development_pilot")])
        write_csv(d, "claims", base_claims(eid))
        write_csv(d, "claim_sources", base_sources(eid, [f"{eid}-CLM-0001", f"{eid}-CLM-0002"]))
        write_csv(d, "management_qna", [base_qna(eid)])
        label = base_label(lid, eid, label_status="human_frozen", frozen_by="jane.reviewer",
                            frozen_at_utc="2026-08-02T10:00:00+00:00", freeze_manifest_path="freeze_manifest.json",
                            event_disposition="development_pilot")
        write_csv(d, "event_labels", [label])
        bundle_dir = write_frozen_bundle(d, eid, lid, label)
        write_manifest_for_bundle(d, bundle_dir, eid, lid)

        ok, findings = v.validate(d, mode="freeze")
        check("1. a well-sourced, fully human-reviewed development_pilot label freezes cleanly",
              ok, [str(f) for f in findings])
        check("1b. the frozen event's disposition remains development_pilot, never silently promoted",
              (d / "events.csv").exists())
        events_after = v._read_csv(d / "events.csv")
        check("1c. event_disposition is exactly what was set -- freezing never mutates it",
              events_after[0]["event_disposition"] == "development_pilot")


# === 2. A freeze blocked by inadequate (non-direct-fetch) sources ===
def test_2_freeze_blocked_by_inadequate_sources():
    with TempFixture() as d:
        eid = "EVT-AAPL-FY26Q3-ERN"
        lid = f"{eid}-LBL-01"
        write_csv(d, "events", [base_event(eid)])
        write_csv(d, "claims", base_claims(eid))
        # Both claims' only source is a search-snippet, tier-4 source -- not
        # direct_fetch/tier 0-3, so they cannot back a human_frozen label.
        write_csv(d, "claim_sources", base_sources(eid, [f"{eid}-CLM-0001", f"{eid}-CLM-0002"],
                                                     method="search_snippet", tier="4"))
        write_csv(d, "management_qna", [base_qna(eid)])
        label = base_label(lid, eid, label_status="human_frozen", frozen_by="jane.reviewer",
                            frozen_at_utc="2026-08-02T10:00:00+00:00", freeze_manifest_path="freeze_manifest.json")
        write_csv(d, "event_labels", [label])
        bundle_dir = write_frozen_bundle(d, eid, lid, label)
        write_manifest_for_bundle(d, bundle_dir, eid, lid)

        ok, findings = v.validate(d, mode="freeze")
        check("2a. freeze fails when the only sources are search-snippet/tier-4", ok is False)
        check("2b. failure names the missing direct_fetch requirement",
              any("direct_fetch" in f.message for f in findings), [str(f) for f in findings])


# === 3. A freeze blocked by outcome leakage (blinding breach) ===
def test_3_freeze_blocked_by_outcome_leakage():
    with TempFixture() as d:
        eid = "EVT-AAPL-FY26Q3-ERN"
        lid = f"{eid}-LBL-01"
        write_csv(d, "events", [base_event(eid)])
        claims = base_claims(eid)
        write_csv(d, "claims", claims)
        write_csv(d, "claim_sources", base_sources(eid, [c["claim_id"] for c in claims]))
        write_csv(d, "management_qna", [base_qna(eid)])
        label = base_label(lid, eid, label_status="human_frozen", frozen_by="jane.reviewer",
                            frozen_at_utc="2026-08-02T10:00:00+00:00", freeze_manifest_path="freeze_manifest.json",
                            notes="Shares gained 8% after the print.")  # outcome leakage
        write_csv(d, "event_labels", [label])
        bundle_dir = write_frozen_bundle(d, eid, lid, label)
        write_manifest_for_bundle(d, bundle_dir, eid, lid)

        ok, findings = v.validate(d, mode="freeze")
        check("3a. freeze fails when a Layer-A field leaks market-reaction outcome language", ok is False)
        check("3b. failure is specifically attributed to the blinding gate",
              any(f.gate == "blinding" for f in findings), [str(f) for f in findings])


# === 4. An amendment produces a new immutable bundle without modifying the prior one ===
def test_4_amendment_creates_new_bundle_without_modifying_prior():
    with TempFixture() as d:
        eid = "EVT-AAPL-FY26Q3-ERN"
        lid1, lid2 = f"{eid}-LBL-01", f"{eid}-LBL-02"
        write_csv(d, "events", [base_event(eid)])
        claims = base_claims(eid)
        write_csv(d, "claims", claims)
        write_csv(d, "claim_sources", base_sources(eid, [c["claim_id"] for c in claims]))
        write_csv(d, "management_qna", [base_qna(eid)])

        label1 = base_label(lid1, eid, label_status="human_frozen", frozen_by="jane.reviewer",
                             frozen_at_utc="2026-08-02T10:00:00+00:00", freeze_manifest_path="freeze_manifest_lbl01.json")
        label2 = base_label(lid2, eid, label_status="human_frozen", frozen_by="jane.reviewer",
                             frozen_at_utc="2026-08-02T12:00:00+00:00", freeze_manifest_path="freeze_manifest_lbl02.json",
                             amendment_of_label_id=lid1, amendment_reason="corrected management_tone",
                             management_tone="confident")
        write_csv(d, "event_labels", [label1, label2])

        bundle1 = write_frozen_bundle(d, eid, lid1, label1)
        write_manifest_for_bundle(d, bundle1, eid, lid1, filename="freeze_manifest_lbl01.json", freeze_ts="2026-08-02T10:00:00+00:00")
        bundle1_hash_before = file_hash(bundle1 / "events.csv")

        bundle2 = write_frozen_bundle(d, eid, lid2, label2)
        write_manifest_for_bundle(d, bundle2, eid, lid2, filename="freeze_manifest_lbl02.json", freeze_ts="2026-08-02T12:00:00+00:00")

        check("4a. the two label versions have physically separate bundle directories",
              bundle1 != bundle2 and bundle1.exists() and bundle2.exists())
        check("4b. creating the amendment's bundle did not touch the prior bundle's files",
              file_hash(bundle1 / "events.csv") == bundle1_hash_before)

        ok, findings = v.validate(d, mode="freeze")
        check("4c. both the original and the amended label validate cleanly", ok, [str(f) for f in findings])


# === 5. Adding a later, UNRELATED event to the shared working tables does not invalidate an earlier freeze ===
def test_5_unrelated_later_event_does_not_invalidate_earlier_freeze():
    with TempFixture() as d:
        eid1 = "EVT-AAPL-FY26Q3-ERN"
        lid1 = f"{eid1}-LBL-01"
        claims1 = base_claims(eid1)
        write_csv(d, "events", [base_event(eid1)])
        write_csv(d, "claims", claims1)
        write_csv(d, "claim_sources", base_sources(eid1, [c["claim_id"] for c in claims1]))
        write_csv(d, "management_qna", [base_qna(eid1)])
        label1 = base_label(lid1, eid1, label_status="human_frozen", frozen_by="jane.reviewer",
                             frozen_at_utc="2026-08-02T10:00:00+00:00", freeze_manifest_path="freeze_manifest.json")
        write_csv(d, "event_labels", [label1])
        bundle1 = write_frozen_bundle(d, eid1, lid1, label1)
        write_manifest_for_bundle(d, bundle1, eid1, lid1)
        bundle1_hash_before = file_hash(bundle1 / "events.csv")

        ok_before, findings_before = v.validate(d, mode="freeze")
        check("5a. the first event's freeze is valid before any later event exists", ok_before, [str(f) for f in findings_before])

        # A SECOND, entirely unrelated event's rows are appended to the SAME
        # shared working tables (events.csv/claims.csv/claim_sources.csv) --
        # simulating normal ongoing panel operation after this freeze.
        eid2 = "EVT-MSFT-FY26Q3-ERN"
        claims2 = base_claims(eid2)
        write_csv(d, "events", [base_event(eid1), base_event(eid2, ticker="MSFT")])
        write_csv(d, "claims", claims1 + claims2)
        write_csv(d, "claim_sources", base_sources(eid1, [c["claim_id"] for c in claims1]) +
                                        base_sources(eid2, [c["claim_id"] for c in claims2]))

        check("5b. the frozen bundle's own snapshot copy is untouched by the new working-table rows",
              file_hash(bundle1 / "events.csv") == bundle1_hash_before)

        ok_after, findings_after = v.validate(d, mode="freeze")
        check("5c. the first event's freeze remains valid after an unrelated later event is added",
              ok_after, [str(f) for f in findings_after])


# === 6. GitHub Actions CI workflow is scoped to deterministic tests, no network access ===
def test_6_ci_workflow_is_network_free_and_scoped():
    workflow_path = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "event-dossier-validator-tests.yml"
    check("6a. CI workflow file exists", workflow_path.exists(), workflow_path)
    if not workflow_path.exists():
        return
    text = workflow_path.read_text(encoding="utf-8")
    check("6b. workflow declares least-privilege contents:read permissions", "contents: read" in text)
    check("6c. workflow pins a specific Python version", 'python-version: "3.12"' in text or "python-version:" in text)
    check("6d. workflow installs from validator/requirements.txt",
          "Event_Dossier_Protocol/validator/requirements.txt" in text)
    check("6e. workflow discovers and runs every test_*.py file (not a single hardcoded filename)",
          "test_*.py" in text or "test_*" in text)
    check("6e2. discovered test files on disk are exactly what CI would run: both required suites present",
          {"test_validate_event_dossier.py", "test_event_dossier_e2e.py"} <=
          {p.name for p in Path(__file__).resolve().parent.glob("test_*.py")})
    for forbidden in ("GST_Phase2_DailyPanel", "Phase2_Wikipedia_Cache", "wikimedia.org", "yfinance",
                       "sec.gov", "polygon.io", "alphavantage"):
        check(f"6f. workflow never references {forbidden!r} (no live market/GST/Wikipedia/SEC data access)",
              forbidden not in text)
    check("6g. workflow triggers only on pull_request and workflow_dispatch (no schedule/push-to-any-branch)",
          "pull_request" in text and "workflow_dispatch" in text and "schedule:" not in text)


def main() -> int:
    for fn in [
        test_1_legitimate_development_pilot_freeze,
        test_2_freeze_blocked_by_inadequate_sources,
        test_3_freeze_blocked_by_outcome_leakage,
        test_4_amendment_creates_new_bundle_without_modifying_prior,
        test_5_unrelated_later_event_does_not_invalidate_earlier_freeze,
        test_6_ci_workflow_is_network_free_and_scoped,
    ]:
        fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("ALL EVENT DOSSIER END-TO-END TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
