#!/usr/bin/env python3
# Deterministic tests for the Layer B market-response addendum emitter.
#
# Every test copies a SYNTHETIC fixture (one of the protocol's own validator
# fixtures) into a temp directory and works only there. No real dossier, no
# real event, no operational artifact, no network. The real, unmodified Event
# Dossier validator is run against the emitted output.
#
# On the freeze question: the protocol's corrected capture-vs-reveal rule
# (B_Market_Response_Addendum/README.md, 2026-08-02) states that capture is
# NOT gated on freeze -- "Row may be created regardless of the linked label's
# status" -- and fixture case_10_layerB_captured_before_freeze_unrevealed
# encodes that as an expected PASS. These tests therefore assert that
# capture-before-freeze is ACCEPTED, and that the genuine ineligibility
# conditions the protocol does define (unknown event, unknown label,
# event/label disagreement) are rejected. Requiring human_frozen here would
# invent stricter sequencing than the protocol has and would contradict a
# locked fixture verdict.
#
# Run directly: python test_market_response_layer_b_emission.py

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.layer_b_addendum import (
    ADDENDUM_CSV_NAME,
    AddendumAlreadyExistsError,
    LayerBEmissionError,
    MarketResponseSummary,
    build_addendum_row,
    emit_addendum,
    layer_a_tables_untouched_digest,
    next_addendum_id,
    validate_emitted,
)
from gst_market_response.protocol_boundary import load_layer_b_schema_columns

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = HERE / "Event_Dossier_Protocol" / "validator" / "fixtures"
FROZEN_FIXTURE = FIXTURES / "case_41_valid_linked_surprise_arithmetic"

EVENT_ID = "EVT-AAPL-FY26Q3-ERN"
LABEL_ID = "EVT-AAPL-FY26Q3-ERN-LBL-01"

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


def expect_raises(label: str, exc_type, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except exc_type:
        print(f"PASS: {label}")
    except Exception as exc:
        print(f"FAIL: {label} (raised {type(exc).__name__}, expected {exc_type.__name__})")
        FAILURES.append(label)
    else:
        print(f"FAIL: {label} (did not raise)")
        FAILURES.append(label)


def staged(tmp: str, source: Path = FROZEN_FIXTURE) -> Path:
    dest = Path(tmp) / "fixture"
    shutil.copytree(source, dest)
    return dest


def complete_summary(**overrides) -> MarketResponseSummary:
    base = dict(
        event_id=EVENT_ID,
        linked_label_id=LABEL_ID,
        market_response_state="COMPLETE",
        captured_at_utc="2026-08-03T21:30:00+00:00",
        captured_by="ai",
        price_reaction_pct=8.0,
        price_reaction_window="after_hours",
        volume_reaction="2.4x 20d median",
        market_response_record_seq=6,
        release_market_session="AMC",
    )
    base.update(overrides)
    return MarketResponseSummary(**base)


def test_frozen_eligible_plus_complete_yields_valid_layer_b():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        ok_before, _ = validate_emitted(fx, mode="freeze")
        check("1a. the staged Layer A fixture validates cleanly BEFORE emission", ok_before)

        row = emit_addendum(complete_summary(), fx)
        check("1b. emitted addendum_id follows {event_id}-ADD-{seq:02d}",
              row["addendum_id"] == f"{EVENT_ID}-ADD-01")
        check("1c. emitted row uses the protocol's exact column set",
              tuple(row.keys()) == load_layer_b_schema_columns())

        ok_after, findings = validate_emitted(fx, mode="freeze")
        check("1d. the REAL validator still passes after emission (freeze mode)", ok_after)
        if not ok_after:
            for f in findings:
                print("      ", f)

        written = list(csv.DictReader(open(fx / ADDENDUM_CSV_NAME, encoding="utf-8")))
        check("1e. exactly one addendum row was written", len(written) == 1)
        check("1f. the file's header matches the protocol schema header",
              tuple(written[0].keys()) == load_layer_b_schema_columns())


def test_session_vocabulary_is_translated_at_the_boundary():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        row = build_addendum_row(complete_summary(release_market_session="AMC"), fx)
        check("2a. AMC is translated to after_close in the recorded provenance",
              "mr_release_market_session=AMC->after_close" in row["notes"])

        row_bmo = build_addendum_row(complete_summary(release_market_session="BMO"), fx)
        check("2b. BMO is translated to before_open", "BMO->before_open" in row_bmo["notes"])

        row_intra = build_addendum_row(complete_summary(release_market_session="INTRADAY"), fx)
        check("2c. INTRADAY is translated to during_session",
              "INTRADAY->during_session" in row_intra["notes"])

        from gst_market_response.protocol_boundary import SessionVocabularyError
        expect_raises(
            "2d. an untranslatable session fails closed rather than being emitted raw",
            SessionVocabularyError, build_addendum_row,
            complete_summary(release_market_session="PREMARKET"), fx,
        )


def test_event_id_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        expect_raises(
            "3a. an event_id with no Layer A row is rejected",
            LayerBEmissionError, build_addendum_row,
            complete_summary(event_id="EVT-MSFT-FY26Q4-ERN"), fx,
        )
        expect_raises(
            "3b. an event_id that disagrees with the linked label's event is rejected",
            LayerBEmissionError, build_addendum_row,
            complete_summary(event_id="EVT-TSLA-FY26Q1-ERN"), fx,
        )


def test_label_id_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        expect_raises(
            "4a. an unknown linked_label_id is rejected",
            LayerBEmissionError, build_addendum_row,
            complete_summary(linked_label_id=f"{EVENT_ID}-LBL-99"), fx,
        )
        expect_raises(
            "4b. a blank linked_label_id is rejected",
            LayerBEmissionError, build_addendum_row,
            complete_summary(linked_label_id=""), fx,
        )


def test_ineligible_layer_a_per_protocol_rules():
    """The protocol's actual ineligibility conditions -- and proof that
    'not yet frozen' is deliberately NOT one of them."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        (fx / "events.csv").unlink()
        expect_raises(
            "5a. a fixture with no Layer A events at all is rejected",
            LayerBEmissionError, build_addendum_row, complete_summary(), fx,
        )

    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        (fx / "event_labels.csv").unlink()
        expect_raises(
            "5b. a fixture with no Layer A labels is rejected",
            LayerBEmissionError, build_addendum_row, complete_summary(), fx,
        )

    # Capture before freeze IS allowed -- README.md 2026-08-02 and fixture
    # case_10_layerB_captured_before_freeze_unrevealed (expected PASS).
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        rows = list(csv.DictReader(open(fx / "event_labels.csv", encoding="utf-8")))
        cols = list(rows[0].keys())
        rows[0]["label_status"] = "draft"
        with open(fx / "event_labels.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        try:
            build_addendum_row(complete_summary(), fx)
            allowed = True
        except LayerBEmissionError:
            allowed = False
        check(
            "5c. capture against a NOT-yet-frozen label is ALLOWED (protocol: capture is "
            "not gated on freeze; reveal is)",
            allowed,
        )


def test_partial_market_response_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        for state in ("PARTIAL", "ABSTAIN_DATA_QUALITY", "D1_COMPLETE", "REGISTERED"):
            expect_raises(
                f"6. market-response state {state} is refused (only COMPLETE is eligible)",
                LayerBEmissionError, build_addendum_row,
                complete_summary(market_response_state=state), fx,
            )


def test_missing_values_never_become_zero():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        row = build_addendum_row(
            complete_summary(
                price_reaction_pct=None, price_reaction_window=None,
                volume_reaction=None, iv_reaction=None,
            ),
            fx,
        )
        check("7a. absent price_reaction_pct is empty, not '0'", row["price_reaction_pct"] == "")
        check("7b. absent volume_reaction is empty, not '0'", row["volume_reaction"] == "")
        check("7c. absent iv_reaction is empty, not '0'", row["iv_reaction"] == "")
        check(
            "7d. no optional column was zero-filled",
            all(row[c] != "0" for c in (
                "price_reaction_pct", "volume_reaction", "iv_reaction",
                "options_reaction_notes", "post_event_media_sentiment_notes")),
        )
        # A genuine 0.0 reaction must still be recorded as 0.0, not dropped.
        row_zero = build_addendum_row(
            complete_summary(price_reaction_pct=0.0, price_reaction_window="after_hours"), fx
        )
        check("7e. a real measured 0.0 is preserved as 0.0 (not confused with missing)",
              row_zero["price_reaction_pct"] == "0.0")
        # price_reaction_window is conditionally required by the dictionary.
        expect_raises(
            "7f. a price_reaction_pct without its window fails closed",
            LayerBEmissionError, build_addendum_row,
            complete_summary(price_reaction_pct=5.0, price_reaction_window=None), fx,
        )
        expect_raises(
            "7g. a window outside the protocol enum fails closed",
            LayerBEmissionError, build_addendum_row,
            complete_summary(price_reaction_pct=5.0, price_reaction_window="whenever"), fx,
        )


def test_existing_destination_is_never_overwritten():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        emit_addendum(complete_summary(), fx)
        first_bytes = (fx / ADDENDUM_CSV_NAME).read_bytes()

        expect_raises(
            "8a. re-emitting the same addendum_id raises rather than overwriting",
            AddendumAlreadyExistsError, emit_addendum,
            complete_summary(), fx, addendum_id=f"{EVENT_ID}-ADD-01",
        )
        check("8b. the existing file's bytes are unchanged after the refused write",
              (fx / ADDENDUM_CSV_NAME).read_bytes() == first_bytes)

        # A NEW addendum appends without disturbing the first row's bytes.
        emit_addendum(complete_summary(captured_at_utc="2026-08-04T14:00:00+00:00"), fx)
        after = (fx / ADDENDUM_CSV_NAME).read_bytes()
        check("8c. a second addendum APPENDS -- the original bytes remain a prefix",
              after.startswith(first_bytes))
        rows = list(csv.DictReader(open(fx / ADDENDUM_CSV_NAME, encoding="utf-8")))
        check("8d. the second row got the next sequence number",
              [r["addendum_id"] for r in rows] == [f"{EVENT_ID}-ADD-01", f"{EVENT_ID}-ADD-02"])
        ok, _ = validate_emitted(fx, mode="freeze")
        check("8e. two appended addenda still validate", ok)


def test_amendment_preserves_the_original_record():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        emit_addendum(complete_summary(price_reaction_pct=8.0, market_response_record_seq=6), fx)
        original_bytes = (fx / ADDENDUM_CSV_NAME).read_bytes()
        original_rows = list(csv.DictReader(open(fx / ADDENDUM_CSV_NAME, encoding="utf-8")))

        # A corrected measurement arrives as a market-response AMENDMENT.
        emit_addendum(
            complete_summary(
                price_reaction_pct=9.0,
                captured_at_utc="2026-08-04T10:00:00+00:00",
                market_response_record_seq=7,
                market_response_amends_seq=6,
                notes="corrects the window conflation in ADD-01",
            ),
            fx,
        )
        rows = list(csv.DictReader(open(fx / ADDENDUM_CSV_NAME, encoding="utf-8")))
        check("9a. the amendment is a NEW row, not an edit", len(rows) == 2)
        check("9b. the original row's every field is byte-identical", rows[0] == original_rows[0])
        check("9c. the original bytes are still an exact prefix of the file",
              (fx / ADDENDUM_CSV_NAME).read_bytes().startswith(original_bytes))
        check("9d. the amendment records which market-response record it corrects",
              "mr_amends_seq=6" in rows[1]["notes"])
        check("9e. the original still carries its own record identity",
              "mr_record_seq=6" in rows[0]["notes"])
        ok, _ = validate_emitted(fx, mode="freeze")
        check("9f. the amended pair validates", ok)


def test_market_response_never_appears_in_layer_a():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        before = layer_a_tables_untouched_digest(fx)
        emit_addendum(complete_summary(), fx)
        after = layer_a_tables_untouched_digest(fx)
        check("10a. every Layer A artifact is byte-identical after emission", before == after)
        check("10b. the freeze manifest specifically is untouched",
              before.get("freeze_manifest.json") == after.get("freeze_manifest.json"))

        # No market-response token may appear in any Layer A file.
        tokens = ("mr_record_seq", "mr_state", "market_response", "AMC", "2.4x 20d median")
        leaked = []
        for path in sorted(fx.rglob("*")):
            if not path.is_file() or path.name == ADDENDUM_CSV_NAME:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for t in tokens:
                if t in text:
                    leaked.append((path.name, t))
        check(f"10c. no market-response token leaked into Layer A (found {leaked})", not leaked)

        # And the emitted value itself lives only in the addendum.
        addendum_text = (fx / ADDENDUM_CSV_NAME).read_text(encoding="utf-8")
        check("10d. the measured reaction appears in the addendum only",
              "2.4x 20d median" in addendum_text)


def test_final_combined_fixture_passes_the_real_validator():
    """The end-to-end gate: a frozen Layer A dossier plus an emitted Layer B
    addendum, checked by the shipped validator in its strictest mode."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        emit_addendum(complete_summary(), fx)
        emit_addendum(
            complete_summary(
                captured_at_utc="2026-08-05T13:00:00+00:00",
                price_reaction_pct=None, price_reaction_window=None,
                post_event_media_sentiment_notes="mixed coverage",
                market_response_record_seq=8,
            ),
            fx,
        )
        for mode in ("draft", "proposed", "freeze"):
            ok, findings = validate_emitted(fx, mode=mode)
            check(f"11. combined Layer A + emitted Layer B passes the real validator (mode={mode})", ok)
            if not ok:
                for f in findings:
                    print("      ", f)


def test_next_addendum_id_sequencing():
    check("12a. first id is -ADD-01", next_addendum_id(EVENT_ID, []) == f"{EVENT_ID}-ADD-01")
    existing = [{"addendum_id": f"{EVENT_ID}-ADD-01"}, {"addendum_id": f"{EVENT_ID}-ADD-02"}]
    check("12b. next id continues the sequence", next_addendum_id(EVENT_ID, existing) == f"{EVENT_ID}-ADD-03")
    check("12c. another event's ids do not affect this event's sequence",
          next_addendum_id(EVENT_ID, [{"addendum_id": "EVT-MSFT-FY26Q4-ERN-ADD-07"}]) == f"{EVENT_ID}-ADD-01")


def test_timestamp_semantics_are_the_protocols():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        expect_raises(
            "13a. a timezone-naive captured_at_utc fails closed (matches the validator)",
            LayerBEmissionError, build_addendum_row,
            complete_summary(captured_at_utc="2026-08-03T21:30:00"), fx,
        )
        expect_raises(
            "13b. a malformed captured_at_utc fails closed",
            LayerBEmissionError, build_addendum_row,
            complete_summary(captured_at_utc="not-a-timestamp"), fx,
        )
        expect_raises(
            "13c. a blank captured_at_utc fails closed",
            LayerBEmissionError, build_addendum_row, complete_summary(captured_at_utc=""), fx,
        )
        expect_raises(
            "13d. a blank captured_by fails closed",
            LayerBEmissionError, build_addendum_row, complete_summary(captured_by=""), fx,
        )
        # Capture BEFORE the freeze timestamp is explicitly legal.
        manifest = json.loads((fx / "freeze_manifest.json").read_text(encoding="utf-8"))
        freeze_ts = manifest["freeze_timestamp_utc"]
        row = build_addendum_row(complete_summary(captured_at_utc="2026-08-01T09:00:00+00:00"), fx)
        check(
            f"13e. captured_at_utc BEFORE freeze_timestamp_utc ({freeze_ts}) is accepted "
            f"-- capture is not reveal",
            row["captured_at_utc"] == "2026-08-01T09:00:00+00:00",
        )


def test_emitter_never_writes_outside_the_addendum():
    with tempfile.TemporaryDirectory() as tmp:
        fx = staged(tmp)
        before = {p.relative_to(fx).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(fx.rglob("*")) if p.is_file()}
        emit_addendum(complete_summary(), fx)
        after = {p.relative_to(fx).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(fx.rglob("*")) if p.is_file()}
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        check(f"14. the ONLY file created or changed is {ADDENDUM_CSV_NAME} (changed={sorted(changed)})",
              changed == {ADDENDUM_CSV_NAME})


if __name__ == "__main__":
    test_frozen_eligible_plus_complete_yields_valid_layer_b()
    test_session_vocabulary_is_translated_at_the_boundary()
    test_event_id_mismatch_is_rejected()
    test_label_id_mismatch_is_rejected()
    test_ineligible_layer_a_per_protocol_rules()
    test_partial_market_response_is_rejected()
    test_missing_values_never_become_zero()
    test_existing_destination_is_never_overwritten()
    test_amendment_preserves_the_original_record()
    test_market_response_never_appears_in_layer_a()
    test_final_combined_fixture_passes_the_real_validator()
    test_next_addendum_id_sequencing()
    test_timestamp_semantics_are_the_protocols()
    test_emitter_never_writes_outside_the_addendum()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL LAYER B EMISSION TESTS PASSED")
    sys.exit(0)
