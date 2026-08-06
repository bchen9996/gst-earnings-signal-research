#!/usr/bin/env python3
"""Deterministic tests for validate_event_dossier.py against the full
fixture set: 48 preserved scenarios from the first 2026-08-03 hardening
pass, plus 18 new scenarios from the SECOND 2026-08-03 correction pass
covering required-table/mode enforcement, header-only column validation,
surprise-linkage correctness (metric_name matching, unit/GAAP/nonzero-
consensus/nonnumeric checks), explicit null-surprise reasons, child-table
event/layer consistency, market-response addendum event consistency, the
immutable frozen/{event_id}/{label_id}/ freeze-bundle architecture, real
JSON Schema validation (including nested array items), and component-aware
(Path.is_relative_to) path containment.

No network access, no operational cache access, no Phase 2 panel
execution -- every fixture is a small, synthetic, self-contained directory
under fixtures/.

Run directly: python test_validate_event_dossier.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_event_dossier as v

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# (fixture directory name, expected_ok, short description, validation mode)
CASES = [
    # --- 1-20: preserved from the original fixture set (outcomes unchanged) ---
    ("case_01_fully_valid", True, "Fully valid blinded event", "draft"),
    ("case_02_stock_reaction_sentence", False, "MSFT-style stock-reaction sentence in claim_text", "draft"),
    ("case_03_reaction_in_source_title", False, "Price-reaction language inside a source title", "draft"),
    ("case_04_forbidden_feature_in_core", False, "GST/IV-style forbidden feature term in Layer A", "draft"),
    ("case_05_surprise_without_consensus", False, "Surprise percentage without consensus provider/timestamp", "draft"),
    ("case_06_blended_consensus_provider", False, "Blended Zacks/LSEG consensus value", "draft"),
    ("case_07_snippet_only_supports_frozen_label", False, "Search-snippet-only claim supporting a frozen label", "draft"),
    ("case_08_ai_proposed_qna_pending", True, "AI-proposed Q&A classification remaining pending", "draft"),
    ("case_09_ai_label_marked_human_frozen", False, "AI-generated label incorrectly marked human-frozen", "draft"),
    ("case_10_layerB_captured_before_freeze_unrevealed", True, "Layer B captured before freeze but unrevealed", "draft"),
    ("case_11_layerB_revealed_before_freeze", False, "Layer B revealed before freeze", "draft"),
    ("case_12_reviewer_exposed_before_freeze", False, "Reviewer exposed to Layer C before freeze", "draft"),
    ("case_13_pilot_reverted_to_confirmatory", False, "Development-pilot event reverted to confirmatory", "draft"),
    ("case_14_append_only_amendment", True, "Append-only amendment preserving the prior label's own bundle", "draft"),
    ("case_15_broken_foreign_key", False, "Broken foreign key (claim references unknown event_id)", "draft"),
    ("case_16_ticker_outside_universe", False, "Ticker outside the locked v0.1 universe", "draft"),
    ("case_17_operating_statement_allowed", True, '"Azure grew 43%" operating statement', "draft"),
    ("case_18_reaction_statement_blocked", False, '"Microsoft shares rose 8%" reaction statement', "draft"),
    ("case_19_changed_layer_a_hash", False, "Frozen bundle with a changed artifact hash", "draft"),
    ("case_20_consensus_unavailable_null_surprise", True, "Consensus unavailable, surprise fields explicitly null with a reason", "draft"),
    # --- 21-48: first hardening-pass scenarios (2026-08-03) ---
    ("case_21_empty_required_field", False, "Blank required field (events.company_name)", "draft"),
    ("case_22_malformed_numeric", False, "numeric_value not parseable for a value_type=numeric claim", "draft"),
    ("case_23_out_of_range_score", False, "information_novelty_score_1_to_5 outside [1,5]", "draft"),
    ("case_24_naive_timestamp", False, "created_at_utc has no timezone designator (naive)", "draft"),
    ("case_25_corroborates_fk_invalid", False, "corroborates_claim_source_id references a nonexistent source", "draft"),
    ("case_26_corroborates_fk_cross_claim", False, "corroborates_claim_source_id references a source of a different claim", "draft"),
    ("case_27_capex_evidence_fk_invalid", False, "event_label_capex_effects.evidence_claim_id references a nonexistent claim", "draft"),
    ("case_28_cross_company_implications_fk_invalid", False, "event_label_cross_company_implications.claim_id references a nonexistent claim", "draft"),
    ("case_29_claim_event_mismatch", False, "eps_actual_claim_id belongs to a different event than the label", "draft"),
    ("case_30_manifest_missing_required_artifact", False, "Freeze manifest inventory omits a required artifact", "draft"),
    ("case_31_manifest_nonexistent_artifact_file", False, "Manifest references an artifact file that was never written", "draft"),
    ("case_32_manifest_path_traversal", False, "Manifest artifact_path attempts to escape via '..'", "draft"),
    ("case_33_manifest_duplicate_artifact_entry", False, "Same artifact_path listed twice in one manifest", "draft"),
    ("case_34_manifest_layer_bc_leak", False, "Manifest references a Layer-B path", "draft"),
    ("case_35_manifest_missing_required_json_field", False, "Manifest omits the required 'frozen_by' field", "draft"),
    ("case_36_manifest_additional_property", False, "Manifest carries an undeclared extra top-level field", "draft"),
    ("case_37_manifest_label_disagreement", False, "Manifest frozen_by disagrees with event_labels.csv", "draft"),
    ("case_38_equal_reveal_freeze_timestamps", False, "reveal_events timestamp equals freeze_timestamp_utc exactly", "draft"),
    ("case_39_mismatched_gaap_bases", False, "EPS actual (GAAP) paired with EPS consensus (non-GAAP)", "draft"),
    ("case_40_incorrect_surprise_arithmetic", False, "Stored eps_surprise_pct disagrees with recomputed value", "draft"),
    ("case_41_valid_linked_surprise_arithmetic", True, "Correctly linked and arithmetically correct surprise on a human_frozen label", "freeze"),
    ("case_42_null_unverifiable_consensus_linkage", True, "Null surprise stays valid when the only consensus claim is unverifiable", "draft"),
    ("case_43_reaction_language_in_notes", False, "'shares gained 8%' inside event_labels.notes", "draft"),
    ("case_44_reaction_language_in_management_tone", False, "'the stock was up 9%' inside management_tone", "draft"),
    ("case_45_reaction_language_in_classification_basis", False, "'market value added' inside classification_basis", "draft"),
    ("case_46_reaction_language_in_source_notes", False, "Reaction language inside claim_sources.notes", "draft"),
    ("case_47_old_niche_value_rejected", False, "niche='large_cap_earnings' (superseded value) is rejected", "draft"),
    ("case_48_fixed_24_niche_value_accepted", True, "niche='fixed_24_ticker_earnings_panel' is accepted", "draft"),
    # --- 49-66: SECOND hardening pass (2026-08-03) ---
    ("case_49_empty_directory", False, "Completely empty fixture directory", "draft"),
    ("case_50_missing_required_table_proposed_mode", False, "proposed mode requires claim_sources.csv; fixture omits it", "proposed"),
    ("case_51_malformed_header_only_csv", False, "claims.csv header (0 rows) is missing the 'metric_name' column", "draft"),
    ("case_52_freeze_mode_missing_table", False, "freeze mode requires management_qna.csv + a human_frozen row; fixture has neither", "freeze"),
    ("case_53_unexplained_null_surprise", False, "eps_surprise_pct blank AND eps_surprise_null_reason blank", "draft"),
    ("case_54_legitimate_unverifiable_null_surprise", True, "eps_surprise_pct blank, eps_surprise_null_reason='consensus_unverifiable'", "draft"),
    ("case_55_nonnumeric_linked_claim", False, "EPS actual claim has value_type=categorical, not numeric", "draft"),
    ("case_56_missing_unit", False, "EPS actual claim has a blank unit", "draft"),
    ("case_57_missing_gaap_basis", False, "EPS consensus claim has a blank gaap_basis", "draft"),
    ("case_58_zero_consensus", False, "EPS consensus claim has numeric_value=0", "draft"),
    ("case_59_eps_linked_to_revenue_claim", False, "eps_actual_claim_id points to a claim with metric_name=revenue", "draft"),
    ("case_60_child_claim_from_wrong_event", False, "capex-effect evidence_claim_id belongs to a different event", "draft"),
    ("case_61_child_claim_from_layer_b", False, "cross-company-implication claim_id has layer=B_market_response", "draft"),
    ("case_62_mutable_working_file_changed_after_freeze", True, "Working events.csv edited after the frozen bundle snapshot -- manifest hashes the frozen copy", "freeze"),
    ("case_63_prior_bundle_valid_after_amendment", True, "LBL-01's frozen bundle stays valid after LBL-02's own separate amendment bundle", "freeze"),
    ("case_64_manifest_filename_path_disagreement", False, "event_labels.csv freeze_manifest_path names a different file than the one present", "draft"),
    ("case_65_manifest_prefix_collision_escape", False, "artifact_path escapes via a sibling dir that is a string-prefix superset of the real bundle", "draft"),
    ("case_66_nested_json_schema_violation", False, "reveal_events[0] missing required 'revealed_by' -- nested JSON Schema violation", "draft"),
]


class TestEventDossierValidator(unittest.TestCase):
    def test_all_fixture_dirs_exist(self):
        for name, _expected_ok, _desc, _mode in CASES:
            fixture_dir = FIXTURES_DIR / name
            self.assertTrue(fixture_dir.is_dir(), f"fixture directory missing: {fixture_dir}")

    def test_fixture_count_matches_directory(self):
        actual_dirs = {p.name for p in FIXTURES_DIR.iterdir() if p.is_dir()}
        expected_dirs = {name for name, _ok, _desc, _mode in CASES}
        self.assertEqual(actual_dirs, expected_dirs, "fixture directory set and CASES list have drifted apart")

    def test_fixture_cases(self):
        failures = []
        for name, expected_ok, desc, mode in CASES:
            fixture_dir = FIXTURES_DIR / name
            ok, findings = v.validate(fixture_dir, mode=mode)
            with self.subTest(case=name):
                if ok != expected_ok:
                    detail = "\n".join(f"    {f}" for f in findings) or "    (no findings)"
                    failures.append(
                        f"{name} (mode={mode}, {desc}): expected {'PASS' if expected_ok else 'FAIL'}, "
                        f"got {'PASS' if ok else 'FAIL'}\n{detail}"
                    )
        self.assertEqual(failures, [], "\n\n".join(failures))

    def test_validator_never_touches_network_or_operational_paths(self):
        src = (Path(__file__).resolve().parent / "validate_event_dossier.py").read_text(encoding="utf-8")
        for forbidden in ("import requests", "import urllib", "import socket", "subprocess",
                          "GST_Phase2_DailyPanel", "Phase2_Wikipedia_Cache"):
            self.assertNotIn(forbidden, src, f"validator source unexpectedly references {forbidden!r}")

    def test_operating_statement_vs_reaction_statement_distinction(self):
        ok_operating, _ = v.validate(FIXTURES_DIR / "case_17_operating_statement_allowed", mode="draft")
        ok_reaction, _ = v.validate(FIXTURES_DIR / "case_18_reaction_statement_blocked", mode="draft")
        self.assertTrue(ok_operating, "operating-metric growth language must not be flagged")
        self.assertFalse(ok_reaction, "stock-reaction language must be flagged")

    def test_msft_pilot_artifacts_fail_validation_as_expected(self):
        # Regression case tying the validator back to the actual incident
        # that motivated it: the preserved MSFT pilot dossier's narrative
        # should be caught by the same reaction-language scan used on
        # fixtures. Does not modify or re-validate the real dossier.md file.
        excerpt = (
            "even if the +8-9% after-hours magnitude was not guaranteed. "
            'Source title: "Microsoft Q4 2026 beats forecasts, stock jumps 8%"'
        )
        hits = []
        for pat in v.REACTION_PATTERNS:
            hits.extend(m.group(0) for m in pat.finditer(excerpt))
        self.assertTrue(hits, "MSFT pilot's own reaction-language excerpt should trigger the detector")

    def test_niche_rename_is_the_only_accepted_value(self):
        self.assertEqual(v.NICHE_VALUES, {"fixed_24_ticker_earnings_panel"})
        self.assertNotIn("large_cap_earnings", v.NICHE_VALUES)

    def test_locked_universe_includes_non_large_cap_tickers(self):
        # The motivating fact behind the niche rename: GME and NCLH are
        # locked v0.1 tickers and are not large-cap by any conventional
        # definition -- "large_cap_earnings" was inaccurate.
        universe = v.load_locked_universe()
        self.assertIn("GME", universe)
        self.assertIn("NCLH", universe)

    def test_timestamp_ordering_never_raises_on_naive_or_mixed_tz(self):
        # A naive timestamp must fail validation, never crash the
        # comparison with a TypeError.
        self.assertIsNone(v._parse_ts_strict("2026-08-02T10:00:00"))  # naive, no offset
        self.assertIsNone(v._parse_ts_strict("not-a-timestamp"))
        self.assertIsNotNone(v._parse_ts_strict("2026-08-02T10:00:00+00:00"))
        self.assertIsNotNone(v._parse_ts_strict("2026-08-02T10:00:00Z"))

    def test_surprise_tolerance_is_documented_and_small(self):
        self.assertLess(v.SURPRISE_PCT_TOLERANCE, 1.0)
        self.assertGreater(v.SURPRISE_PCT_TOLERANCE, 0.0)

    # --- second correction pass: new invariant tests -----------------------

    def test_empty_directory_fails_in_every_mode(self):
        empty = FIXTURES_DIR / "case_49_empty_directory"
        for mode in v.VALIDATION_MODES:
            ok, findings = v.validate(empty, mode=mode)
            with self.subTest(mode=mode):
                self.assertFalse(ok, f"an empty directory must fail validation in mode={mode!r}")
                self.assertTrue(any(f.gate == "required_tables" for f in findings))

    def test_validation_modes_have_increasingly_strict_requirements(self):
        self.assertEqual(v.REQUIRED_TABLES_BY_MODE["draft"], {"events"})
        self.assertTrue(v.REQUIRED_TABLES_BY_MODE["draft"] <= v.REQUIRED_TABLES_BY_MODE["proposed"])
        self.assertTrue(v.REQUIRED_TABLES_BY_MODE["proposed"] <= v.REQUIRED_TABLES_BY_MODE["freeze"])

    def test_invalid_mode_raises_programmer_error(self):
        with self.assertRaises(ValueError):
            v.validate(FIXTURES_DIR / "case_01_fully_valid", mode="not_a_real_mode")

    def test_header_only_csv_is_checked_even_with_zero_data_rows(self):
        # case_51's claims.csv has 0 data rows but a header missing
        # 'metric_name' -- must be caught, not silently skipped because
        # there happen to be no rows to inspect.
        ok, findings = v.validate(FIXTURES_DIR / "case_51_malformed_header_only_csv", mode="draft")
        self.assertFalse(ok)
        self.assertTrue(any("metric_name" in f.message for f in findings))

    def test_metric_names_enum_declared(self):
        self.assertEqual(v.METRIC_NAMES, {"eps", "revenue", "guidance_revenue", "cloud_growth", "margin", "capex", "other"})

    def test_surprise_null_reasons_enum_declared(self):
        self.assertEqual(v.SURPRISE_NULL_REASONS, {"consensus_unavailable", "consensus_unverifiable", "not_applicable"})

    def test_frozen_bundle_required_basenames_are_seven_and_distinct_from_working_tables(self):
        self.assertEqual(len(v.FROZEN_BUNDLE_REQUIRED_BASENAMES), 7)
        self.assertIn("event_label.csv", v.FROZEN_BUNDLE_REQUIRED_BASENAMES)
        self.assertNotIn("event_labels.csv", v.FROZEN_BUNDLE_REQUIRED_BASENAMES)

    def test_mutable_working_file_after_freeze_does_not_invalidate_the_bundle(self):
        # Direct proof of the immutable-bundle design: the working events.csv
        # was edited AFTER the frozen bundle snapshot was taken, and the
        # fixture must still PASS because the manifest hashes the frozen
        # copy, never the mutable working table.
        d = FIXTURES_DIR / "case_62_mutable_working_file_changed_after_freeze"
        working = (d / "events.csv").read_text(encoding="utf-8")
        frozen = (d / "frozen" / "EVT-AAPL-FY26Q3-ERN" / "EVT-AAPL-FY26Q3-ERN-LBL-01" / "events.csv").read_text(encoding="utf-8")
        self.assertNotEqual(working, frozen, "fixture setup sanity check: working and frozen copies must actually differ")
        ok, findings = v.validate(d, mode="freeze")
        self.assertTrue(ok, f"expected PASS despite working/frozen divergence, got findings: {findings}")

    def test_path_containment_uses_is_relative_to_not_string_prefix(self):
        # A sibling directory whose name is a string-prefix superset of the
        # real bundle dir (.../LBL-01_evil/ vs .../LBL-01/) must NOT be
        # treated as contained -- str.startswith() would wrongly accept it.
        d = FIXTURES_DIR / "case_65_manifest_prefix_collision_escape"
        ok, findings = v.validate(d, mode="draft")
        self.assertFalse(ok)
        self.assertTrue(any("outside this label's immutable bundle directory" in f.message for f in findings))

    def test_nested_json_schema_violations_are_caught(self):
        # The old hand-rolled top-level-only required/additionalProperties
        # check never inspected array items; jsonschema's recursive
        # validation does.
        ok, findings = v.validate(FIXTURES_DIR / "case_66_nested_json_schema_violation", mode="draft")
        self.assertFalse(ok)
        self.assertTrue(any("revealed_by" in f.message for f in findings))

    def test_jsonschema_dependency_is_available_and_pinned(self):
        self.assertTrue(v._HAVE_JSONSCHEMA, "jsonschema must be importable for freeze-manifest structural validation")
        req = (Path(__file__).resolve().parent / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("jsonschema==", req)


if __name__ == "__main__":
    unittest.main(verbosity=2)
