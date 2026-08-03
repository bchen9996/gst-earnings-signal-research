#!/usr/bin/env python3
"""Deterministic tests for validate_event_dossier.py (2026-08-03 hardening
pass) against the full fixture set: the original 20 required scenarios
(outcomes preserved) plus 28 new scenarios covering mechanical field/enum/
type enforcement, complete foreign-key validation (including the new
event_label_cross_company_implications.csv child table and
corroborates_claim_source_id), hardened freeze-manifest validation,
expanded blinding-language coverage, strict reveal>freeze timestamp
ordering, explicit EPS/revenue surprise-claim linkage with recomputation,
and the fixed_24_ticker_earnings_panel niche rename.

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

# (fixture directory name, expected_ok, short description)
CASES = [
    # --- 1-20: preserved from the original fixture set (outcomes unchanged) ---
    ("case_01_fully_valid", True, "Fully valid blinded event"),
    ("case_02_stock_reaction_sentence", False, "MSFT-style stock-reaction sentence in claim_text"),
    ("case_03_reaction_in_source_title", False, "Price-reaction language inside a source title"),
    ("case_04_forbidden_feature_in_core", False, "GST/IV-style forbidden feature term in Layer A"),
    ("case_05_surprise_without_consensus", False, "Surprise percentage without consensus provider/timestamp"),
    ("case_06_blended_consensus_provider", False, "Blended Zacks/LSEG consensus value"),
    ("case_07_snippet_only_supports_frozen_label", False, "Search-snippet-only claim supporting a frozen label"),
    ("case_08_ai_proposed_qna_pending", True, "AI-proposed Q&A classification remaining pending"),
    ("case_09_ai_label_marked_human_frozen", False, "AI-generated label incorrectly marked human-frozen"),
    ("case_10_layerB_captured_before_freeze_unrevealed", True, "Layer B captured before freeze but unrevealed"),
    ("case_11_layerB_revealed_before_freeze", False, "Layer B revealed before freeze"),
    ("case_12_reviewer_exposed_before_freeze", False, "Reviewer exposed to Layer C before freeze"),
    ("case_13_pilot_reverted_to_confirmatory", False, "Development-pilot event reverted to confirmatory"),
    ("case_14_append_only_amendment", True, "Append-only amendment preserving the prior label"),
    ("case_15_broken_foreign_key", False, "Broken foreign key (claim references unknown event_id)"),
    ("case_16_ticker_outside_universe", False, "Ticker outside the locked v0.1 universe"),
    ("case_17_operating_statement_allowed", True, '"Azure grew 43%" operating statement'),
    ("case_18_reaction_statement_blocked", False, '"Microsoft shares rose 8%" reaction statement'),
    ("case_19_changed_layer_a_hash", False, "Frozen manifest with a changed Layer A artifact hash"),
    ("case_20_consensus_unavailable_null_surprise", True, "Consensus unavailable, surprise fields explicitly null"),
    # --- 21-48: new 2026-08-03 hardening-pass scenarios ---
    ("case_21_empty_required_field", False, "Blank required field (events.company_name)"),
    ("case_22_malformed_numeric", False, "numeric_value not parseable for a value_type=numeric claim"),
    ("case_23_out_of_range_score", False, "information_novelty_score_1_to_5 outside [1,5]"),
    ("case_24_naive_timestamp", False, "created_at_utc has no timezone designator (naive)"),
    ("case_25_corroborates_fk_invalid", False, "corroborates_claim_source_id references a nonexistent source"),
    ("case_26_corroborates_fk_cross_claim", False, "corroborates_claim_source_id references a source of a different claim"),
    ("case_27_capex_evidence_fk_invalid", False, "event_label_capex_effects.evidence_claim_id references a nonexistent claim"),
    ("case_28_cross_company_implications_fk_invalid", False, "event_label_cross_company_implications.claim_id references a nonexistent claim"),
    ("case_29_claim_event_mismatch", False, "eps_actual_claim_id belongs to a different event than the label"),
    ("case_30_manifest_missing_required_artifact", False, "Freeze manifest inventory omits a required Layer-A artifact"),
    ("case_31_manifest_nonexistent_artifact_file", False, "Manifest references an artifact file that was never written"),
    ("case_32_manifest_path_traversal", False, "Manifest artifact_path attempts to escape the fixture directory"),
    ("case_33_manifest_duplicate_artifact_entry", False, "Same artifact_path listed twice in one manifest"),
    ("case_34_manifest_layer_bc_leak", False, "Manifest references a Layer-B path"),
    ("case_35_manifest_missing_required_json_field", False, "Manifest omits the required 'frozen_by' field"),
    ("case_36_manifest_additional_property", False, "Manifest carries an undeclared extra top-level field"),
    ("case_37_manifest_label_disagreement", False, "Manifest frozen_by disagrees with event_labels.csv"),
    ("case_38_equal_reveal_freeze_timestamps", False, "reveal_events timestamp equals freeze_timestamp_utc exactly"),
    ("case_39_mismatched_gaap_bases", False, "EPS actual (GAAP) paired with EPS consensus (non-GAAP)"),
    ("case_40_incorrect_surprise_arithmetic", False, "Stored eps_surprise_pct disagrees with recomputed value"),
    ("case_41_valid_linked_surprise_arithmetic", True, "Correctly linked and arithmetically correct surprise on a human_frozen label"),
    ("case_42_null_unverifiable_consensus_linkage", True, "Null surprise stays valid when the only consensus claim is unverifiable"),
    ("case_43_reaction_language_in_notes", False, "'shares gained 8%' inside event_labels.notes"),
    ("case_44_reaction_language_in_management_tone", False, "'the stock was up 9%' inside management_tone"),
    ("case_45_reaction_language_in_classification_basis", False, "'market value added' inside classification_basis"),
    ("case_46_reaction_language_in_source_notes", False, "Reaction language inside claim_sources.notes"),
    ("case_47_old_niche_value_rejected", False, "niche='large_cap_earnings' (superseded value) is rejected"),
    ("case_48_fixed_24_niche_value_accepted", True, "niche='fixed_24_ticker_earnings_panel' is accepted"),
]


class TestEventDossierValidator(unittest.TestCase):
    def test_all_fixture_dirs_exist(self):
        for name, _expected_ok, _desc in CASES:
            fixture_dir = FIXTURES_DIR / name
            self.assertTrue(fixture_dir.is_dir(), f"fixture directory missing: {fixture_dir}")

    def test_fixture_count_matches_directory(self):
        actual_dirs = {p.name for p in FIXTURES_DIR.iterdir() if p.is_dir()}
        expected_dirs = {name for name, _ok, _desc in CASES}
        self.assertEqual(actual_dirs, expected_dirs, "fixture directory set and CASES list have drifted apart")

    def test_fixture_cases(self):
        failures = []
        for name, expected_ok, desc in CASES:
            fixture_dir = FIXTURES_DIR / name
            ok, findings = v.validate(fixture_dir)
            with self.subTest(case=name):
                if ok != expected_ok:
                    detail = "\n".join(f"    {f}" for f in findings) or "    (no findings)"
                    failures.append(
                        f"{name} ({desc}): expected {'PASS' if expected_ok else 'FAIL'}, "
                        f"got {'PASS' if ok else 'FAIL'}\n{detail}"
                    )
        self.assertEqual(failures, [], "\n\n".join(failures))

    def test_validator_never_touches_network_or_operational_paths(self):
        src = (Path(__file__).resolve().parent / "validate_event_dossier.py").read_text(encoding="utf-8")
        for forbidden in ("import requests", "import urllib", "import socket", "subprocess",
                          "GST_Phase2_DailyPanel", "Phase2_Wikipedia_Cache"):
            self.assertNotIn(forbidden, src, f"validator source unexpectedly references {forbidden!r}")

    def test_operating_statement_vs_reaction_statement_distinction(self):
        ok_operating, _ = v.validate(FIXTURES_DIR / "case_17_operating_statement_allowed")
        ok_reaction, _ = v.validate(FIXTURES_DIR / "case_18_reaction_statement_blocked")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
