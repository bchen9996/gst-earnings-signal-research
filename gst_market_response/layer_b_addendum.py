# Layer B emission boundary: converts an eligible COMPLETE market-response
# record into a valid Event Dossier Protocol market_response_addendum.csv row.
#
# The protocol is authoritative here. Everything below is derived from, and
# deliberately does not exceed, these sources:
#
#   * B_Market_Response_Addendum/schemas/market_response_addendum.csv
#     (column order -- read at runtime, never hardcoded)
#   * B_Market_Response_Addendum/SCHEMA_FIELD_DICTIONARY.md
#   * B_Market_Response_Addendum/README.md   (capture-vs-reveal rule)
#   * validator/validate_event_dossier.py    (required cols, enums, FK gates)
#
# CAPTURE IS NOT GATED ON FREEZE -- THIS IS DELIBERATE
#
# The protocol's corrected rule (README.md, 2026-08-02) is explicit: an
# earlier draft said Layer B could not be *created* until Layer A froze, and
# that was withdrawn because it risks losing transient evidence. The current
# rule is:
#
#   "Capture of this layer's content may happen automatically and
#    contemporaneously with Layer A ... Capture and storage do not constitute
#    reveal."
#
# and the field dictionary states of linked_label_id: "Row may be created
# regardless of the linked label's status -- capture is not gated on freeze.
# Reveal is gated (enforced in the freeze manifest, not here)."
#
# Fixture case_10_layerB_captured_before_freeze_unrevealed encodes this as an
# expected PASS. So this emitter does NOT require the linked label to be
# human_frozen. Requiring it would invent stricter sequencing than the
# protocol defines and would contradict a locked fixture verdict.
#
# What this emitter DOES enforce, because the protocol does:
#   * the referenced Layer A event and label must exist (FK gates)
#   * the addendum's event_id must match the linked label's own event_id
#   * captured_at_utc must be a timezone-aware timestamp
#   * price_reaction_window must be in the validator's REACTION_WINDOWS
#     whenever price_reaction_pct is set
#   * reveal is NEVER recorded here (no revealed_at_utc column exists); the
#     emitter never writes or touches a freeze manifest
#   * nothing from this layer is ever written into a Layer A table
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .atomic_io import append_bytes_never_truncate, atomic_write_text
from .protocol_boundary import (
    ProtocolBoundaryError,
    load_layer_b_schema_columns,
    load_validator_module,
    to_protocol_release_session,
)

ADDENDUM_CSV_NAME = "market_response_addendum.csv"

# Layer A tables this emitter may READ for eligibility checks. It never opens
# any of them for writing.
EVENTS_CSV_NAME = "events.csv"
EVENT_LABELS_CSV_NAME = "event_labels.csv"

# The market-response state that makes a record eligible to be summarised into
# Layer B. Mirrors gst_market_response.event_record.TERMINAL_STATES; only the
# successful terminal state qualifies.
ELIGIBLE_MARKET_RESPONSE_STATE = "COMPLETE"


class LayerBEmissionError(ProtocolBoundaryError):
    """Fail-closed: the record must not be emitted as a Layer B addendum."""


class AddendumAlreadyExistsError(LayerBEmissionError):
    """The destination already holds this addendum_id. Append-only means we
    never silently overwrite a captured row."""


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _require_aware_timestamp(raw: Optional[str], field_name: str) -> str:
    if _is_blank(raw):
        raise LayerBEmissionError(f"{field_name} is required and must not be blank")
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError as exc:
        raise LayerBEmissionError(f"{field_name}={raw!r} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise LayerBEmissionError(
            f"{field_name}={raw!r} is timezone-naive -- the protocol's timestamp gates "
            f"fail closed on naive values, so it is refused here too"
        )
    return str(raw)


def next_addendum_id(event_id: str, existing_rows: list[dict]) -> str:
    """`{event_id}-ADD-{seq:02d}`, per the field dictionary. Sequence is one
    past the highest already present for this event, so a re-run never reuses
    an id that is already captured."""
    used = []
    prefix = f"{event_id}-ADD-"
    for row in existing_rows:
        aid = (row.get("addendum_id") or "").strip()
        if aid.startswith(prefix):
            tail = aid[len(prefix):]
            if tail.isdigit():
                used.append(int(tail))
    return f"{prefix}{(max(used) + 1) if used else 1:02d}"


@dataclass(frozen=True)
class MarketResponseSummary:
    """The narrow slice of a completed market-response record that Layer B
    accepts. Built explicitly by the caller rather than scraped from an
    arbitrary dict, so no unexpected market-response field can leak into the
    protocol."""

    event_id: str
    linked_label_id: str
    market_response_state: str
    captured_at_utc: str
    captured_by: str
    price_reaction_pct: Optional[float] = None
    price_reaction_window: Optional[str] = None
    volume_reaction: Optional[str] = None
    iv_reaction: Optional[str] = None
    options_reaction_notes: Optional[str] = None
    post_event_analyst_target_change_claim_ids: Optional[str] = None
    post_event_media_sentiment_notes: Optional[str] = None
    # Market-response provenance preserved in the free-text notes column. This
    # is the ONLY protocol column that carries market-response identity, and
    # notes is a documented free-text field.
    market_response_record_seq: Optional[int] = None
    market_response_amends_seq: Optional[int] = None
    release_market_session: Optional[str] = None
    notes: Optional[str] = None


def _provenance_note(summary: MarketResponseSummary) -> str:
    """Preserve the market-response record/amendment identity without adding
    any protocol column. Deterministic ordering so the row is reproducible."""
    parts: list[str] = []
    if summary.market_response_record_seq is not None:
        parts.append(f"mr_record_seq={summary.market_response_record_seq}")
    if summary.market_response_amends_seq is not None:
        parts.append(f"mr_amends_seq={summary.market_response_amends_seq}")
    if summary.market_response_state:
        parts.append(f"mr_state={summary.market_response_state}")
    if summary.release_market_session is not None:
        # Translated through the one boundary function -- never copied raw.
        parts.append(
            f"mr_release_market_session={summary.release_market_session}"
            f"->{to_protocol_release_session(summary.release_market_session)}"
        )
    if summary.notes:
        parts.append(str(summary.notes))
    return "; ".join(parts)


def check_eligibility(
    summary: MarketResponseSummary,
    fixture_dir: Path,
) -> None:
    """Fail closed unless every protocol precondition holds. Raises
    LayerBEmissionError with a specific reason; never returns a bool the
    caller might ignore."""
    if summary.market_response_state != ELIGIBLE_MARKET_RESPONSE_STATE:
        raise LayerBEmissionError(
            f"market-response state is {summary.market_response_state!r}; only "
            f"{ELIGIBLE_MARKET_RESPONSE_STATE!r} records may be summarised into Layer B "
            f"(PARTIAL and ABSTAIN_DATA_QUALITY are refused)"
        )

    if _is_blank(summary.event_id) or _is_blank(summary.linked_label_id):
        raise LayerBEmissionError("both event_id and linked_label_id are required")

    events = _read_csv_rows(fixture_dir / EVENTS_CSV_NAME)
    labels = _read_csv_rows(fixture_dir / EVENT_LABELS_CSV_NAME)

    event_ids = {r.get("event_id") for r in events}
    if summary.event_id not in event_ids:
        raise LayerBEmissionError(
            f"event_id {summary.event_id!r} has no row in {EVENTS_CSV_NAME} -- refusing to "
            f"emit an addendum against a Layer A event that does not exist"
        )

    label_by_id = {r.get("label_id"): r for r in labels}
    label = label_by_id.get(summary.linked_label_id)
    if label is None:
        raise LayerBEmissionError(
            f"linked_label_id {summary.linked_label_id!r} has no row in {EVENT_LABELS_CSV_NAME}"
        )

    if label.get("event_id") != summary.event_id:
        raise LayerBEmissionError(
            f"linked_label_id {summary.linked_label_id!r} belongs to event "
            f"{label.get('event_id')!r}, not {summary.event_id!r} -- the protocol's foreign-key "
            f"gate requires these to agree"
        )

    _require_aware_timestamp(summary.captured_at_utc, "captured_at_utc")
    if _is_blank(summary.captured_by):
        raise LayerBEmissionError("captured_by is required")

    validator = load_validator_module()
    if summary.price_reaction_pct is not None:
        if _is_blank(summary.price_reaction_window):
            raise LayerBEmissionError(
                "price_reaction_window is required whenever price_reaction_pct is set "
                "(field dictionary: the MSFT pilot's unresolved window-conflation issue)"
            )
        if summary.price_reaction_window not in validator.REACTION_WINDOWS:
            raise LayerBEmissionError(
                f"price_reaction_window {summary.price_reaction_window!r} is not in the "
                f"protocol's enum {sorted(validator.REACTION_WINDOWS)}"
            )

    # NOTE: the linked label's status is deliberately NOT checked. Capture is
    # not gated on freeze (README.md 2026-08-02, and fixture
    # case_10_layerB_captured_before_freeze_unrevealed expects PASS).


def build_addendum_row(
    summary: MarketResponseSummary,
    fixture_dir: Path,
    addendum_id: Optional[str] = None,
) -> dict:
    """Produce one schema-exact Layer B row. Missing optional values stay
    EMPTY -- never zero-filled, never defaulted to a plausible number."""
    check_eligibility(summary, fixture_dir)

    existing = _read_csv_rows(fixture_dir / ADDENDUM_CSV_NAME)
    aid = addendum_id or next_addendum_id(summary.event_id, existing)

    def optional(value: Any) -> str:
        # The single place a missing value becomes a cell. Blank, never 0.
        if _is_blank(value):
            return ""
        return str(value)

    values: dict[str, str] = {
        "addendum_id": aid,
        "event_id": summary.event_id,
        "linked_label_id": summary.linked_label_id,
        "captured_at_utc": summary.captured_at_utc,
        "captured_by": summary.captured_by,
        "price_reaction_pct": optional(summary.price_reaction_pct),
        "price_reaction_window": optional(summary.price_reaction_window),
        "volume_reaction": optional(summary.volume_reaction),
        "iv_reaction": optional(summary.iv_reaction),
        "options_reaction_notes": optional(summary.options_reaction_notes),
        "post_event_analyst_target_change_claim_ids": optional(
            summary.post_event_analyst_target_change_claim_ids
        ),
        "post_event_media_sentiment_notes": optional(summary.post_event_media_sentiment_notes),
        "notes": _provenance_note(summary),
    }

    columns = load_layer_b_schema_columns()
    unknown = set(values) - set(columns)
    if unknown:  # pragma: no cover - guards a schema edit
        raise LayerBEmissionError(
            f"refusing to emit: {sorted(unknown)} are not columns of the protocol schema {columns}"
        )
    # Column order and membership come from the schema file itself.
    return {col: values.get(col, "") for col in columns}


def emit_addendum(
    summary: MarketResponseSummary,
    fixture_dir: Path,
    addendum_id: Optional[str] = None,
) -> dict:
    """Append one addendum row to `fixture_dir/market_response_addendum.csv`.

    Append-only and atomic:
      * an existing addendum_id is never overwritten (raises);
      * an existing file is never truncated -- the header is written once via
        an atomic temp-file rename, and every row after that is a strict
        binary append;
      * no freeze manifest or Layer A table is opened for writing, ever.
    """
    row = build_addendum_row(summary, fixture_dir, addendum_id=addendum_id)
    columns = load_layer_b_schema_columns()
    dest = fixture_dir / ADDENDUM_CSV_NAME

    existing = _read_csv_rows(dest)
    if any((r.get("addendum_id") or "") == row["addendum_id"] for r in existing):
        raise AddendumAlreadyExistsError(
            f"{ADDENDUM_CSV_NAME} already contains addendum_id {row['addendum_id']!r} -- "
            f"refusing to overwrite a captured row; record a new addendum instead"
        )

    if not dest.is_file():
        fixture_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(dest, ",".join(columns) + "\n")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    writer.writerow(row)
    append_bytes_never_truncate(dest, buf.getvalue().encode("utf-8"))
    return row


def validate_emitted(fixture_dir: Path, mode: str = "freeze") -> tuple[bool, list]:
    """Run the real Event Dossier validator over the fixture directory this
    emitter just wrote into. The validator is used exactly as shipped -- no
    gate is disabled, relaxed, or monkeypatched."""
    validator = load_validator_module()
    return validator.validate(Path(fixture_dir), mode=mode)


def layer_a_tables_untouched_digest(fixture_dir: Path) -> dict:
    """SHA-256 of every Layer A artifact in the directory, so a caller (and
    the tests) can prove emission changed none of them."""
    import hashlib

    digests: dict[str, str] = {}
    for path in sorted(fixture_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == ADDENDUM_CSV_NAME:
            continue
        rel = path.relative_to(fixture_dir).as_posix()
        digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


__all__ = [
    "ADDENDUM_CSV_NAME",
    "AddendumAlreadyExistsError",
    "ELIGIBLE_MARKET_RESPONSE_STATE",
    "LayerBEmissionError",
    "MarketResponseSummary",
    "build_addendum_row",
    "check_eligibility",
    "emit_addendum",
    "layer_a_tables_untouched_digest",
    "next_addendum_id",
    "validate_emitted",
]
