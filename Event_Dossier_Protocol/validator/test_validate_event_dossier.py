#!/usr/bin/env python3
"""Deterministic tests for validate_event_dossier.py against the 20 required
fixture cases (Event Dossier Protocol Phase 4). No network access, no
operational cache access, no Phase 2 panel execution -- every fixture is a
small, synthetic, self-contained directory under fixtures/.

Run directly: python test_validate_event_dossier.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_event_dossier as v

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# (fixture directory name, expected_ok, short description) -- mirrors the 20
# required deterministic fixture cases from the master execution prompt.
CASES = [
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
]


class TestEventDossierValidator(unittest.TestCase):
    def test_all_fixture_dirs_exist(self):
        for name, _expected_ok, _desc in CASES:
            fixture_dir = FIXTURES_DIR / name
            self.assertTrue(fixture_dir.is_dir(), f"fixture directory missing: {fixture_dir}")

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
        # Static guard: the validator module must not import networking
        # libraries or reference the operational Phase 2 cache/panel paths.
        src = (Path(__file__).resolve().parent / "validate_event_dossier.py").read_text(encoding="utf-8")
        for forbidden in ("import requests", "import urllib", "import socket", "subprocess", "GST_Phase2_DailyPanel", "Phase2_Wikipedia_Cache"):
            self.assertNotIn(forbidden, src, f"validator source unexpectedly references {forbidden!r}")

    def test_operating_statement_vs_reaction_statement_distinction(self):
        # Direct, isolated regression for the leakage-detector's core claim:
        # growth language passes, reaction language fails, on otherwise
        # identical fixture shapes.
        ok_operating, _ = v.validate(FIXTURES_DIR / "case_17_operating_statement_allowed")
        ok_reaction, _ = v.validate(FIXTURES_DIR / "case_18_reaction_statement_blocked")
        self.assertTrue(ok_operating, "operating-metric growth language must not be flagged")
        self.assertFalse(ok_reaction, "stock-reaction language must be flagged")

    def test_msft_pilot_artifacts_fail_validation_as_expected(self):
        # Regression case tying the validator back to the actual incident
        # that motivated it: the preserved MSFT pilot dossier's narrative
        # (Sections 11/13, and its source-title citation of S5) should be
        # caught by the same reaction-language scan used on fixtures, when
        # run over an equivalent narrative_text.txt. This does not modify or
        # re-validate the real dossier.md file -- it exercises the same
        # detector on representative excerpts to prove the checklist's own
        # "would have failed" claim (see MSFT_PILOT_QC_AND_DISPOSITION.md).
        excerpt = (
            "even if the +8-9% after-hours magnitude was not guaranteed. "
            'Source title: "Microsoft Q4 2026 beats forecasts, stock jumps 8%"'
        )
        hits = []
        for pat in v.REACTION_PATTERNS:
            hits.extend(m.group(0) for m in pat.finditer(excerpt))
        self.assertTrue(hits, "MSFT pilot's own reaction-language excerpt should trigger the detector")


if __name__ == "__main__":
    unittest.main(verbosity=2)
