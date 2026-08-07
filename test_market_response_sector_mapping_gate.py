#!/usr/bin/env python3
# Deterministic tests: sector-BENCHMARK mapping mechanical review gate.
#
# The central property under test (mapping_version 0.3): the benchmark
# assignment is derived from the GICS sector ALONE, so a company that is a
# confirmed NONconstituent of its benchmark ETF still has a valid, approved
# sector benchmark -- and is never represented anywhere as an ETF holding.
#
# Run directly: python test_market_response_sector_mapping_gate.py

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE
from gst_market_response.sector_mapping import (
    VALID_BENCHMARK_BASES,
    VALID_CONSTITUENT_STATUSES,
    SectorMapping,
    SectorMappingEntry,
    SectorMappingError,
    SectorMappingNotApprovedError,
    assert_usable_for_real_event,
    load_sector_mapping,
    validate_sector_mapping,
)

MAPPING_PATH = "Live Signal Engine/GST_Sector_ETF_Mapping_v0.1.json"

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def _entry(**overrides) -> SectorMappingEntry:
    base = dict(
        gics_sector="Information Technology",
        benchmark_etf="XLK",
        benchmark_basis="gics_sector",
        constituent_status="confirmed_constituent",
        classification_source="fixture source",
        retrieval_date="2026-08-04",
    )
    base.update(overrides)
    return SectorMappingEntry(**base)


def _valid_full_mapping(**overrides) -> SectorMapping:
    mapping = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    base = dict(
        schema_version="0.2", mapping_version="0.3", spy_benchmark="SPY",
        review_status="DRAFT", reviewed_by=None, reviewed_at_utc=None, effective_date=None, mapping=mapping,
    )
    base.update(overrides)
    return SectorMapping(**base)


# --------------------------------------------------------------------------
# 1. The shipped mapping file
# --------------------------------------------------------------------------
def test_shipped_mapping_file_is_mechanically_valid():
    sm = load_sector_mapping()
    errors = validate_sector_mapping(sm)
    check("1a. Shipped mapping file currently has no validation errors", errors == [], str(errors))
    check("1b. Shipped mapping is APPROVED", sm.review_status == "APPROVED")
    check("1c. reviewed_by/reviewed_at_utc/effective_date are all populated for an APPROVED mapping",
          bool(sm.reviewed_by and sm.reviewed_at_utc and sm.effective_date))
    check("1d. mapping_version bumped to 0.3 rather than edited in place", sm.mapping_version == "0.3")
    check("1e. schema_version bumped to 0.2 -- the entry shape changed", sm.schema_version == "0.2")


def test_every_ticker_carries_the_six_separated_fields():
    sm = load_sector_mapping()
    incomplete = [
        t for t, e in sm.mapping.items()
        if not e.gics_sector or not e.benchmark_etf or not e.benchmark_basis
        or not e.constituent_status or not e.classification_source or not e.retrieval_date
    ]
    check("2a. All 24 tickers carry gics_sector, benchmark_etf, benchmark_basis, constituent_status, "
          "classification_source and retrieval_date as separate populated fields",
          incomplete == [], str(incomplete))
    check("2b. Exactly the locked 24 tickers are present", set(sm.mapping) == set(LOCKED_24_TICKER_UNIVERSE))

    bad_basis = {t: e.benchmark_basis for t, e in sm.mapping.items() if e.benchmark_basis != "gics_sector"}
    check("2c. Every benchmark_basis is 'gics_sector' -- no assignment is justified by ETF membership",
          bad_basis == {}, str(bad_basis))

    bad_status = {t: e.constituent_status for t, e in sm.mapping.items()
                  if e.constituent_status not in VALID_CONSTITUENT_STATUSES}
    check("2d. Every constituent_status is one of the recognized values", bad_status == {}, str(bad_status))

    undated = {t: e.retrieval_date for t, e in sm.mapping.items()
               if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", e.retrieval_date or "")}
    check("2e. Every retrieval_date is a real ISO-8601 date", undated == {}, str(undated))


# --------------------------------------------------------------------------
# 2. THE CENTRAL PROPERTY: nonconstituent + approved benchmark
# --------------------------------------------------------------------------
def test_confirmed_nonconstituent_still_has_an_approved_benchmark():
    """A confirmed NONconstituent must be able to carry an approved sector
    benchmark, without being represented as an ETF holding."""
    mapping = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    target = LOCKED_24_TICKER_UNIVERSE[0]
    mapping[target] = _entry(
        gics_sector="Consumer Discretionary",
        benchmark_etf="XLY",
        constituent_status="confirmed_nonconstituent",
        classification_source="authoritative GICS source",
    )
    sm = _valid_full_mapping(
        mapping=mapping, review_status="APPROVED",
        reviewed_by="reviewer", reviewed_at_utc="2026-08-04T00:00:00+00:00",
    )

    errors = validate_sector_mapping(sm)
    check("3a. A confirmed_nonconstituent entry produces NO validation error", errors == [], str(errors))

    assert_usable_for_real_event(sm, is_demo=False)  # must not raise
    check("3b. An APPROVED mapping containing a confirmed_nonconstituent IS usable for a real event", True)

    check("3c. The nonconstituent still resolves to its sector benchmark",
          sm.benchmark_etf_for(target) == "XLY")
    check("3d. The benchmark is justified by the GICS sector, not by membership",
          sm.mapping[target].benchmark_basis == "gics_sector")
    check("3e. The entry reports itself as a nonconstituent -- it is not represented as a holding",
          sm.mapping[target].is_confirmed_nonconstituent
          and sm.constituent_status_for(target) == "confirmed_nonconstituent")


def test_gme_is_the_shipped_worked_example():
    sm = load_sector_mapping()
    gme = sm.mapping["GME"]
    check("4a. GME's GICS sector is Consumer Discretionary", gme.gics_sector == "Consumer Discretionary")
    check("4b. GME is benchmarked against XLY", gme.benchmark_etf == "XLY")
    check("4c. GME's benchmark basis is the GICS sector", gme.benchmark_basis == "gics_sector")
    check("4d. GME is recorded as a CONFIRMED NONCONSTITUENT of XLY, not as an unresolved ambiguity",
          gme.constituent_status == "confirmed_nonconstituent")
    check("4e. GME's GICS classification cites S&P Dow Jones Indices, the GICS co-owner",
          "S&P Dow Jones Indices" in gme.classification_source)
    check("4f. GME's nonconstituency carries its own separate evidence",
          bool(gme.constituent_status_source) and "S&P 500" in (gme.constituent_status_source or ""))
    check("4g. GPN remains assigned to XLF", sm.benchmark_etf_for("GPN") == "XLF"
          and sm.gics_sector_for("GPN") == "Financials")


def test_file_never_claims_gme_is_an_xly_constituent():
    raw = open(MAPPING_PATH, encoding="utf-8").read()
    data = json.loads(raw)
    gme = data["mapping"]["GME"]

    check("5a. GME's entry carries no key or value asserting it is an XLY holding/constituent",
          gme["constituent_status"] == "confirmed_nonconstituent")

    # No sentence anywhere may AFFIRMATIVELY assert GME is a constituent or
    # holding. Sentences that deny it (which the file has several of, by
    # design) are exactly what we want and must not count as violations.
    negation = re.compile(
        r"\b(not|no|never|nowhere|none|non|nonconstituent|absent|ineligible|without)\b", re.I
    )
    claim = re.compile(r"\b(is|as) an? (current )?(XLY )?(constituent|holding)\b", re.I)
    offending = [
        s for s in re.split(r"(?<=[.!?])\s+", raw)
        if re.search(r"\bGME\b|GameStop", s) and claim.search(s) and not negation.search(s)
    ]
    check("5b. No sentence in the file affirmatively asserts GME is a constituent or holding",
          offending == [], str(offending[:2]))

    # The retracted membership-count framing must be gone entirely -- including
    # any restatement of it, not merely the one literal string.
    check("5c. The retracted '23/24 confirmed constituents' phrasing is gone",
          "23 of 24" not in raw and "23/24" not in raw)
    check("5d. No count-of-constituents claim of any form survives anywhere in the file",
          re.search(r"\b\d+\s*(of|/)\s*\d+\b[^.]{0,40}\bconstituents?\b", raw, re.I) is None)
    check("5e. The old 'unresolved_ambiguity_documented' status is gone",
          "unresolved_ambiguity" not in raw)


def test_file_states_the_rule_explicitly():
    raw = open(MAPPING_PATH, encoding="utf-8").read().lower()
    check("6a. The file states the benchmark does not imply constituency",
          "does not assert" in raw and "constituent" in raw)
    check("6b. The file still documents this as a benchmark-design choice, not an alpha assertion",
          "benchmark-design choice" in raw and "alpha" in raw)
    check("6c. The file documents the source-quality caveat on the aggregator holdings pages",
          "third-party aggregator" in raw)


# --------------------------------------------------------------------------
# 3. Mechanical gate behaviour
# --------------------------------------------------------------------------
def test_exactly_locked_24_tickers_required():
    missing_one = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    del missing_one[LOCKED_24_TICKER_UNIVERSE[0]]
    errors_missing = validate_sector_mapping(_valid_full_mapping(mapping=missing_one))
    check("7a. A mapping missing one locked-universe ticker fails validation",
          any("missing tickers" in e for e in errors_missing), str(errors_missing))

    with_extra = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    with_extra["NVDA"] = _entry()
    errors_extra = validate_sector_mapping(_valid_full_mapping(mapping=with_extra))
    check("7b. A mapping with an extra, non-universe ticker fails validation",
          any("outside the locked" in e for e in errors_extra), str(errors_extra))


def test_valid_etf_symbols_enforced():
    bad = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    bad["AAPL"] = _entry(benchmark_etf="NOTANETF")
    errors = validate_sector_mapping(_valid_full_mapping(mapping=bad))
    check("8. An unrecognized benchmark_etf symbol is rejected",
          any("not a recognized sector ETF" in e for e in errors), str(errors))


def test_membership_can_never_become_the_benchmark_basis():
    check("9a. 'etf_membership' is not an accepted benchmark_basis",
          "etf_membership" not in VALID_BENCHMARK_BASES)
    bad = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    bad["AAPL"] = _entry(benchmark_basis="etf_membership")
    errors = validate_sector_mapping(_valid_full_mapping(mapping=bad))
    check("9b. An entry claiming ETF membership as its benchmark basis is rejected",
          any("benchmark_basis" in e for e in errors), str(errors))


def test_unrecognized_constituent_status_rejected():
    bad = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    bad["AAPL"] = _entry(constituent_status="probably_in_there_somewhere")
    errors = validate_sector_mapping(_valid_full_mapping(mapping=bad))
    check("10. An unrecognized constituent_status is rejected",
          any("constituent_status" in e for e in errors), str(errors))


def test_approved_requires_all_24_actually_reviewed():
    approved = dict(review_status="APPROVED", reviewed_by="r", reviewed_at_utc="2026-08-04T00:00:00+00:00")

    no_source = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    no_source["AAPL"] = _entry(classification_source="")
    errors = validate_sector_mapping(_valid_full_mapping(mapping=no_source, **approved))
    check("11a. APPROVED with a ticker lacking a classification_source is rejected",
          any("not actually reviewed" in e for e in errors), str(errors))

    no_date = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    no_date["MSFT"] = _entry(retrieval_date="")
    errors2 = validate_sector_mapping(_valid_full_mapping(mapping=no_date, **approved))
    check("11b. APPROVED with a ticker lacking a retrieval_date is rejected",
          any("not actually reviewed" in e for e in errors2), str(errors2))

    unverified = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    unverified["TSLA"] = _entry(constituent_status="not_verified")
    errors3 = validate_sector_mapping(_valid_full_mapping(mapping=unverified, **approved))
    check("11c. APPROVED with a ticker whose constituent_status is still 'not_verified' is rejected",
          any("not actually reviewed" in e for e in errors3), str(errors3))

    # ...but the SAME unreviewed entry is fine while the mapping is DRAFT.
    errors4 = validate_sector_mapping(_valid_full_mapping(mapping=unverified, review_status="DRAFT"))
    check("11d. The same unreviewed entry is acceptable while the mapping is DRAFT -- the gate is on APPROVED",
          errors4 == [], str(errors4))


def test_mapping_version_and_review_fields_required():
    errors = validate_sector_mapping(_valid_full_mapping(mapping_version=""))
    check("12a. Missing mapping_version fails validation", any("mapping_version" in e for e in errors), str(errors))

    errors2 = validate_sector_mapping(_valid_full_mapping(review_status="FINAL_DEFINITELY_APPROVED"))
    check("12b. An unrecognized review_status value fails validation",
          any("review_status" in e for e in errors2), str(errors2))

    errors3 = validate_sector_mapping(
        _valid_full_mapping(review_status="APPROVED", reviewed_by=None, reviewed_at_utc=None)
    )
    check("12c. review_status=APPROVED without reviewed_by/reviewed_at_utc fails validation",
          any("APPROVED but" in e for e in errors3), str(errors3))


def test_draft_usable_in_fixtures_not_for_real_event():
    sm = _valid_full_mapping(review_status="DRAFT")
    assert_usable_for_real_event(sm, is_demo=True)  # must not raise
    check("13a. DRAFT mapping is usable in deterministic/demo fixtures", True)

    try:
        assert_usable_for_real_event(sm, is_demo=False)
        ok = False
    except SectorMappingNotApprovedError:
        ok = True
    check("13b. DRAFT mapping cannot be used for a real (non-demo) event -- raises", ok)


def test_invalid_mapping_rejected_even_for_demo():
    bad = {t: _entry() for t in LOCKED_24_TICKER_UNIVERSE}
    del bad[LOCKED_24_TICKER_UNIVERSE[0]]
    try:
        assert_usable_for_real_event(_valid_full_mapping(mapping=bad), is_demo=True)
        ok = False
    except SectorMappingError:
        ok = True
    check("14. A structurally-invalid mapping is rejected even for demo use", ok)


def test_loader_rejects_entry_missing_a_required_field():
    import tempfile

    data = json.load(open(MAPPING_PATH, encoding="utf-8"))
    del data["mapping"]["AAPL"]["constituent_status"]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        tmp = f.name
    try:
        load_sector_mapping(__import__("pathlib").Path(tmp))
        ok = False
        detail = "loader accepted an entry missing constituent_status"
    except SectorMappingError as e:
        ok = "constituent_status" in str(e)
        detail = str(e)
    finally:
        os.unlink(tmp)
    check("15. The loader rejects a mapping entry missing one of the six required fields", ok, detail)


if __name__ == "__main__":
    test_shipped_mapping_file_is_mechanically_valid()
    test_every_ticker_carries_the_six_separated_fields()
    test_confirmed_nonconstituent_still_has_an_approved_benchmark()
    test_gme_is_the_shipped_worked_example()
    test_file_never_claims_gme_is_an_xly_constituent()
    test_file_states_the_rule_explicitly()
    test_exactly_locked_24_tickers_required()
    test_valid_etf_symbols_enforced()
    test_membership_can_never_become_the_benchmark_basis()
    test_unrecognized_constituent_status_rejected()
    test_approved_requires_all_24_actually_reviewed()
    test_mapping_version_and_review_fields_required()
    test_draft_usable_in_fixtures_not_for_real_event()
    test_invalid_mapping_rejected_even_for_demo()
    test_loader_rejects_entry_missing_a_required_field()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL SECTOR MAPPING REVIEW GATE TESTS PASSED")
        sys.exit(0)
