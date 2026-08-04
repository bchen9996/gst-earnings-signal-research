# Phase 2 pre-event adapter. TASK 2 of the operational-readiness pass.
#
# Accepts an EXPLICITLY supplied Phase 2 panel CSV and its paired
# completion marker -- never discovers "the latest file" (no globbing, no
# directory scan). Read-only: only ever opens the given paths in read mode.
# Cross-verifies the marker's own claimed counts against what the CSV
# actually contains rather than trusting the marker blindly, and hashes
# both inputs for provenance. Does NOT invoke GST_Phase2_DailyPanel.py in
# any way -- it only parses files that module already wrote.
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .completeness import is_valid_pre_event_observation

# Phase 2 panel's per-leg status vocabulary is "ok" or a free-text error
# string (see GST_Phase2_DailyPanel.py COLUMN_ORDER) -- NOT this module's
# ok/partial/missing/error enum. This is the one, explicit, documented
# normalization point between the two vocabularies.
def _normalize_leg_status(raw_status: Optional[str]) -> str:
    if raw_status is None or raw_status == "":
        return "missing"
    if raw_status == "ok":
        return "ok"
    return "error"


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class Phase2AdapterError(ValueError):
    pass


class MarkerCsvMismatchError(Phase2AdapterError):
    """Raised when the completion marker's own claimed counts don't match
    what the CSV actually contains -- the marker is never trusted blindly."""


def _parse_optional_float(raw: Optional[str]) -> Optional[float]:
    if raw is None or raw == "":
        return None
    return float(raw)


def _parse_optional_int(raw: Optional[str]) -> Optional[int]:
    if raw is None or raw == "":
        return None
    return int(float(raw))


def _parse_bool(raw: Optional[str]) -> bool:
    return str(raw).strip().lower() in ("true", "1", "yes")


@dataclass(frozen=True)
class Phase2AdapterResult:
    ticker: str
    panel_status: str  # "COMPLETE" | "PARTIAL", preserved exactly from the marker
    gst_zscore: Optional[float]
    wiki_zscore: Optional[float]
    realized_volatility: Optional[float]
    price: Optional[float]
    volume: Optional[float]
    days_to_earnings: Optional[int]
    previous_close: Optional[float]  # mirrors `price` -- see module docstring below
    pre_event_snapshot_asof_utc: Optional[str]
    source_status_gst: str
    source_status_wiki: str
    source_status_price: str
    retrieved_at_utc_gst: Optional[str]
    retrieved_at_utc_wiki: Optional[str]
    retrieved_at_utc_price: Optional[str]
    source_csv_path: str
    source_csv_sha256: str
    source_marker_path: str
    source_marker_sha256: str
    research_commit_sha: str
    methodology_version: str
    eligible_for_pre_event_captured: bool

    def to_pre_event_fields(self) -> dict:
        """The subset/shape consumed by gst_market_response.completeness /
        pipeline.capture_pre_event_and_option_benchmark -- deliberately
        excludes panel-only provenance fields that aren't part of the
        pre-event snapshot schema itself."""
        return {
            "gst_zscore": self.gst_zscore,
            "wiki_zscore": self.wiki_zscore,
            "realized_volatility": self.realized_volatility,
            "previous_close": self.previous_close,
            "days_to_earnings": self.days_to_earnings,
            "pre_event_snapshot_asof_utc": self.pre_event_snapshot_asof_utc,
            "source_status_gst": self.source_status_gst,
            "source_status_wiki": self.source_status_wiki,
            "source_status_price": self.source_status_price,
            "retrieved_at_utc_gst": self.retrieved_at_utc_gst,
            "retrieved_at_utc_wiki": self.retrieved_at_utc_wiki,
            "retrieved_at_utc_price": self.retrieved_at_utc_price,
        }


def _read_panel_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_marker(marker_path: Path) -> dict:
    with open(marker_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _cross_verify_marker_against_csv(marker: dict, rows: list[dict]) -> None:
    """Recomputes the same counts the marker itself claims, from the actual
    CSV content, and rejects on any disagreement. Never proceeds on a
    marker/CSV mismatch."""
    actual_row_count = len(rows)
    if marker.get("row_count") != actual_row_count:
        raise MarkerCsvMismatchError(
            f"marker row_count={marker.get('row_count')} but CSV has {actual_row_count} rows"
        )
    actual_unique_tickers = len({r.get("ticker") for r in rows})
    if marker.get("unique_ticker_count") != actual_unique_tickers:
        raise MarkerCsvMismatchError(
            f"marker unique_ticker_count={marker.get('unique_ticker_count')} but CSV has {actual_unique_tickers}"
        )
    actual_clean_count = sum(1 for r in rows if _parse_bool(r.get("all_six_fields_clean")))
    if marker.get("all_six_fields_clean_count") != actual_clean_count:
        raise MarkerCsvMismatchError(
            f"marker all_six_fields_clean_count={marker.get('all_six_fields_clean_count')} "
            f"but CSV has {actual_clean_count}"
        )
    if marker.get("status") not in ("COMPLETE", "PARTIAL"):
        raise MarkerCsvMismatchError(f"marker status {marker.get('status')!r} is neither COMPLETE nor PARTIAL")


def import_pre_event_fields_for_ticker(
    *,
    csv_path: Path,
    marker_path: Path,
    ticker: str,
    research_commit_sha: str,
    methodology_version: str,
) -> Phase2AdapterResult:
    """Reads exactly the two explicitly-given files (no discovery), verifies
    them, and returns one ticker's pre-event fields. `price` (the Phase 2
    panel's last-close-as-of-retrieval field) is imported as
    `previous_close` -- that is what it already represents (see the
    provenance report: 'pulls Close/Volume/index date off the last row').
    The panel's own `implied_volatility` field is deliberately NEVER read
    into any earnings_implied_move-shaped field -- see
    option_chain_adapter.py, which is the only source for that."""
    if not csv_path.exists():
        raise Phase2AdapterError(f"CSV path does not exist: {csv_path}")
    if not marker_path.exists():
        raise Phase2AdapterError(f"marker path does not exist: {marker_path}")

    csv_hash = sha256_of_file(csv_path)
    marker_hash = sha256_of_file(marker_path)

    rows = _read_panel_rows(csv_path)
    marker = _read_marker(marker_path)
    _cross_verify_marker_against_csv(marker, rows)

    matching = [r for r in rows if r.get("ticker") == ticker]
    if not matching:
        raise Phase2AdapterError(f"ticker {ticker!r} not found in {csv_path}")
    if len(matching) > 1:
        raise Phase2AdapterError(f"ticker {ticker!r} appears {len(matching)} times in {csv_path} -- ambiguous")
    row = matching[0]

    retrieval_ts = row.get("retrieval_timestamp_utc") or None
    price = _parse_optional_float(row.get("price"))

    source_status_gst = _normalize_leg_status(row.get("gst_status"))
    source_status_wiki = _normalize_leg_status(row.get("wiki_status"))
    source_status_price = _normalize_leg_status(row.get("price_history_status"))

    pre_event_fields = {
        "gst_zscore": _parse_optional_float(row.get("gst_zscore")),
        "previous_close": price,
        "pre_event_snapshot_asof_utc": retrieval_ts,
        "source_status_gst": source_status_gst,
    }
    eligible = is_valid_pre_event_observation(pre_event_fields)

    return Phase2AdapterResult(
        ticker=ticker,
        panel_status=marker["status"],
        gst_zscore=_parse_optional_float(row.get("gst_zscore")),
        wiki_zscore=_parse_optional_float(row.get("wiki_zscore")),
        realized_volatility=_parse_optional_float(row.get("realized_vol")),
        price=price,
        volume=_parse_optional_float(row.get("volume")),
        days_to_earnings=_parse_optional_int(row.get("days_to_nearest_earnings")),
        previous_close=price,
        pre_event_snapshot_asof_utc=retrieval_ts,
        source_status_gst=source_status_gst,
        source_status_wiki=source_status_wiki,
        source_status_price=source_status_price,
        retrieved_at_utc_gst=retrieval_ts,
        retrieved_at_utc_wiki=retrieval_ts,
        retrieved_at_utc_price=retrieval_ts,
        source_csv_path=str(csv_path),
        source_csv_sha256=csv_hash,
        source_marker_path=str(marker_path),
        source_marker_sha256=marker_hash,
        research_commit_sha=research_commit_sha,
        methodology_version=methodology_version,
        eligible_for_pre_event_captured=eligible,
    )
