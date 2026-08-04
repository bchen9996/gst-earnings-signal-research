#!/usr/bin/env python3
# TASK 3 deterministic tests: sector-ETF mapping mechanical review gate.
#
# Run directly: python test_market_response_sector_mapping_gate.py

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE
from gst_market_response.sector_mapping import (
    SectorMapping,
    SectorMappingEntry,
    SectorMappingError,
    SectorMappingNotApprovedError,
    assert_usable_for_real_event,
    load_sector_mapping,
    validate_sector_mapping,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def _valid_full_mapping(**overrides) -> SectorMapping:
    mapping = {t: SectorMappingEntry(sector="Some Sector", sector_etf="XLK") for t in LOCKED_24_TICKER_UNIVERSE}
    base = dict(
        schema_version="0.1", mapping_version="0.1", spy_benchmark="SPY",
        review_status="DRAFT", reviewed_by=None, reviewed_at_utc=None, effective_date=None, mapping=mapping,
    )
    base.update(overrides)
    return SectorMapping(**base)


def test_shipped_mapping_file_is_mechanically_valid():
    sm = load_sector_mapping()
    errors = validate_sector_mapping(sm)
    check("1a. Shipped GST_Sector_ETF_Mapping_v0.1.json currently has no validation errors", errors == [], str(errors))
    # As of the Section D sourced review (2026-08-04), the mapping was
    # individually reviewed (all 24 tickers) and legitimately promoted to
    # APPROVED -- not because it was merely mechanically valid, but because
    # every entry now carries a per-ticker `review` block with a source or a
    # documented, defensible rule. See test_shipped_mapping_every_ticker_has_review().
    check("1b. Shipped mapping has been through Section D's sourced review and is APPROVED", sm.review_status == "APPROVED")
    check("1c. reviewed_by/reviewed_at_utc/effective_date are all populated for an APPROVED mapping", sm.reviewed_by and sm.reviewed_at_utc and sm.effective_date)
    check("1d. mapping_version was bumped (0.2) rather than silently edited in place", sm.mapping_version == "0.2")


def test_shipped_mapping_every_ticker_has_review():
    sm = load_sector_mapping()
    missing_review = [t for t, entry in sm.mapping.items() if not entry.review]
    check("1e. Every one of the 24 tickers carries its own review block (source or defensible rule)", missing_review == [], str(missing_review))

    gpn_review = sm.mapping["GPN"].review
    check("1f. GPN's review is explicitly marked 'corrected' (not silently left as XLK)", gpn_review is not None and gpn_review.get("status") == "corrected")
    check("1g. GPN was actually corrected to XLF", sm.sector_etf_for("GPN") == "XLF")

    gme_review = sm.mapping["GME"].review
    check(
        "1h. GME's remaining ambiguity is visibly documented, not silently resolved as a clean confirmation",
        gme_review is not None and gme_review.get("status") == "unresolved_ambiguity_documented",
    )

    confirmed_count = sum(1 for entry in sm.mapping.values() if entry.review and entry.review.get("status") == "confirmed")
    check("1i. The remaining 22 tickers are marked 'confirmed' via a sourced check", confirmed_count == 22, str(confirmed_count))


def test_exactly_locked_24_tickers_required():
    missing_one = dict({t: SectorMappingEntry("S", "XLK") for t in LOCKED_24_TICKER_UNIVERSE})
    del missing_one[LOCKED_24_TICKER_UNIVERSE[0]]
    sm_missing = _valid_full_mapping(mapping=missing_one)
    errors_missing = validate_sector_mapping(sm_missing)
    check("2a. A mapping missing one locked-universe ticker fails validation", any("missing tickers" in e for e in errors_missing), str(errors_missing))

    with_extra = dict({t: SectorMappingEntry("S", "XLK") for t in LOCKED_24_TICKER_UNIVERSE})
    with_extra["NVDA"] = SectorMappingEntry("Some Sector", "XLK")  # not in the locked universe
    sm_extra = _valid_full_mapping(mapping=with_extra)
    errors_extra = validate_sector_mapping(sm_extra)
    check("2b. A mapping with an extra, non-universe ticker fails validation", any("outside the locked" in e for e in errors_extra), str(errors_extra))


def test_valid_etf_symbols_enforced():
    bad_etf_mapping = dict({t: SectorMappingEntry("S", "XLK") for t in LOCKED_24_TICKER_UNIVERSE})
    bad_etf_mapping["AAPL"] = SectorMappingEntry("Information Technology", "NOTANETF")
    sm = _valid_full_mapping(mapping=bad_etf_mapping)
    errors = validate_sector_mapping(sm)
    check("3. An unrecognized sector_etf symbol is rejected", any("not a recognized sector ETF" in e for e in errors), str(errors))


def test_mapping_version_and_review_fields_required():
    sm_no_version = _valid_full_mapping(mapping_version="")
    errors = validate_sector_mapping(sm_no_version)
    check("4a. Missing mapping_version fails validation", any("mapping_version" in e for e in errors), str(errors))

    sm_bad_status = _valid_full_mapping(review_status="FINAL_DEFINITELY_APPROVED")
    errors2 = validate_sector_mapping(sm_bad_status)
    check("4b. An unrecognized review_status value fails validation", any("review_status" in e for e in errors2), str(errors2))

    sm_approved_no_reviewer = _valid_full_mapping(review_status="APPROVED", reviewed_by=None, reviewed_at_utc=None)
    errors3 = validate_sector_mapping(sm_approved_no_reviewer)
    check("4c. review_status=APPROVED without reviewed_by/reviewed_at_utc fails validation", any("APPROVED but" in e for e in errors3), str(errors3))


def test_draft_usable_in_fixtures_not_for_real_event():
    sm = _valid_full_mapping(review_status="DRAFT")
    assert_usable_for_real_event(sm, is_demo=True)  # must not raise
    check("5a. DRAFT mapping is usable in deterministic/demo fixtures", True)

    try:
        assert_usable_for_real_event(sm, is_demo=False)
        ok = False
    except SectorMappingNotApprovedError:
        ok = True
    check("5b. DRAFT mapping cannot be used for a real (non-demo) event -- raises", ok)


def test_approved_mapping_usable_for_real_event():
    sm = _valid_full_mapping(review_status="APPROVED", reviewed_by="research_lead", reviewed_at_utc="2026-08-04T00:00:00+00:00")
    assert_usable_for_real_event(sm, is_demo=False)  # must not raise
    check("6. An APPROVED, fully-reviewed mapping IS usable for a real event", True)


def test_invalid_mapping_rejected_even_for_demo():
    bad = dict({t: SectorMappingEntry("S", "XLK") for t in LOCKED_24_TICKER_UNIVERSE})
    del bad[LOCKED_24_TICKER_UNIVERSE[0]]
    sm = _valid_full_mapping(mapping=bad)
    try:
        assert_usable_for_real_event(sm, is_demo=True)
        ok = False
    except SectorMappingError:
        ok = True
    check("7. A structurally-invalid mapping is rejected even for demo use -- DRAFT status never excuses a broken mapping", ok)


def test_benchmark_design_choice_documented_not_alpha():
    text = open("Live Signal Engine/GST_Sector_ETF_Mapping_v0.1.json", encoding="utf-8").read().lower()
    check(
        "8. The mapping file itself documents this as a benchmark-design choice, not an alpha assertion",
        "benchmark-design choice" in text and "alpha" in text,
    )


if __name__ == "__main__":
    test_shipped_mapping_file_is_mechanically_valid()
    test_shipped_mapping_every_ticker_has_review()
    test_exactly_locked_24_tickers_required()
    test_valid_etf_symbols_enforced()
    test_mapping_version_and_review_fields_required()
    test_draft_usable_in_fixtures_not_for_real_event()
    test_approved_mapping_usable_for_real_event()
    test_invalid_mapping_rejected_even_for_demo()
    test_benchmark_design_choice_documented_not_alpha()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL SECTOR MAPPING REVIEW GATE TESTS PASSED")
        sys.exit(0)
