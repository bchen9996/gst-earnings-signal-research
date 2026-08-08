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

# --- Phase 2 source-status normalisation -----------------------------------
#
# Phase 2's per-leg status vocabulary is NOT binary. It distinguishes a fresh
# successful retrieval ("ok") from one whose fresh request failed but which
# was honestly served from the recent last-known-good cache
# ("complete_recent_cache_fallback"). Phase 2 itself treats the latter as a
# COMPLETE outcome -- validate_amzn_wiki_only.py maps both "ok" and
# "complete_recent_cache_fallback" to exit_status COMPLETE, and
# test_phase2_wikipedia_recent_cache_fallback.py proves the fallback-served
# z-score exactly equals the original successful response's.
#
# An earlier version of this adapter collapsed everything that was not
# literally "ok" to "error", which mislabelled a Phase-2-complete observation
# as a failure. Corrected here with an explicit mapping. The fallback keeps
# its OWN normalised category rather than being folded into "ok", so no
# downstream consumer can mistake cache-served data for ordinary fresh data,
# and the exact original Phase 2 string is preserved alongside it on the
# result object (source_status_*_raw).
#
# This module never changes Phase 2's own status values, completeness rules,
# source-selection logic, or panel output -- it only interprets what Phase 2
# already wrote.

NORMALIZED_OK = "ok"
NORMALIZED_OK_RECENT_CACHE_FALLBACK = "ok_recent_cache_fallback"
NORMALIZED_MISSING = "missing"
NORMALIZED_ERROR = "error"

NORMALIZED_STATUSES = (
    NORMALIZED_OK,
    NORMALIZED_OK_RECENT_CACHE_FALLBACK,
    NORMALIZED_MISSING,
    NORMALIZED_ERROR,
)

# Categories meaning "Phase 2 produced a usable observation". Both are
# successes; they are NOT interchangeable when describing provenance.
NORMALIZED_SUCCESS_STATUSES = frozenset({NORMALIZED_OK, NORMALIZED_OK_RECENT_CACHE_FALLBACK})

# Explicit allowlist of recognised Phase 2 statuses denoting completeness.
# Anything non-blank and unlisted fails closed to NORMALIZED_ERROR while its
# raw value is retained -- a new Phase 2 status must be classified
# deliberately here, never silently promoted to success.
PHASE2_COMPLETE_STATUS_MAP: dict[str, str] = {
    "ok": NORMALIZED_OK,
    "complete_recent_cache_fallback": NORMALIZED_OK_RECENT_CACHE_FALLBACK,
}


def normalize_leg_status(raw_status: Optional[str]) -> str:
    """Map a raw Phase 2 leg status onto one of NORMALIZED_STATUSES.

    Blank/None -> missing. A recognised complete status -> its own success
    category. Every other non-blank value (timeout, error,
    incomplete_after_second_pass, incomplete_effective_watermark_unavailable,
    incomplete_watermark_unavailable, or any status never seen before) ->
    error, fail-closed.
    """
    if raw_status is None:
        return NORMALIZED_MISSING
    raw = str(raw_status).strip()
    if raw == "":
        return NORMALIZED_MISSING
    return PHASE2_COMPLETE_STATUS_MAP.get(raw, NORMALIZED_ERROR)


def is_successful_leg_status(normalized_status: str) -> bool:
    """True for both fresh-ok and fallback-ok. Use this rather than comparing
    against the literal "ok", so the fallback case is never dropped."""
    return normalized_status in NORMALIZED_SUCCESS_STATUSES


def was_served_from_recent_cache_fallback(normalized_status: str) -> bool:
    return normalized_status == NORMALIZED_OK_RECENT_CACHE_FALLBACK


def preserve_raw_status(raw_status: Optional[str]) -> str:
    """The exact original Phase 2 string, kept verbatim beside the normalised
    category. Blank/None becomes "" so the field is always a string."""
    return "" if raw_status is None else str(raw_status)


# Backwards-compatible private alias so nothing importing the old private
# name breaks. New code should call normalize_leg_status().
_normalize_leg_status = normalize_leg_status


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
    # The exact original Phase 2 status strings, preserved verbatim beside the
    # normalised categories above. A consumer that needs to know a leg was
    # served from the recent last-known-good cache rather than freshly
    # retrieved reads these (or is_recent_cache_fallback_* below) -- the
    # normalised category alone deliberately never claims fresh provenance.
    source_status_gst_raw: str
    source_status_wiki_raw: str
    source_status_price_raw: str
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

    # --- v0.2 strict six-field core + authoritative dates + panel provenance ---
    # panel_implied_volatility is the panel's generic IV, persisted ONLY as
    # six-field completeness provenance. SPEC section 5's prohibition is
    # unchanged: it is never exposed as `implied_volatility`, never fed to the
    # option benchmark, and never usable as an earnings-implied-move value.
    panel_implied_volatility: Optional[float] = None
    run_date: Optional[str] = None
    price_asof_date: Optional[str] = None
    panel_row_count: Optional[int] = None
    panel_unique_ticker_count: Optional[int] = None
    panel_all_six_fields_clean_count: Optional[int] = None
    adapter_schema_version: str = "0.2"

    # --- per-leg statuses for the IV and realized-volatility legs -------------
    # The Phase 2 panel emits FIVE independent per-leg statuses: gst_status,
    # wiki_status, iv_status, realized_vol_status and price_history_status. The
    # first version of the v0.2 strict gate backed implied volatility and
    # realized volatility with `source_status_price`, which is a different leg
    # that fails for different reasons -- so a failed option-chain lookup passed
    # the six-field gate whenever price history happened to be OK. These two
    # legs now carry their own normalised and raw statuses.
    #
    # The defaults are the FAIL-CLOSED value: a result constructed without them
    # reports "missing", which the strict gate rejects. They are never defaulted
    # to a success.
    source_status_iv: str = NORMALIZED_MISSING
    source_status_iv_raw: str = ""
    source_status_realized_vol: str = NORMALIZED_MISSING
    source_status_realized_vol_raw: str = ""

    def to_strict_core_fields(self) -> dict:
        """to_pre_event_fields() PLUS the panel's IV, for the strict v0.2
        six-field gate only.

        panel_implied_volatility is deliberately NOT in to_pre_event_fields():
        that dict is guarded against any implied-move-shaped key so no
        downstream consumer can mistake a generic panel IV for an earnings
        implied move (SPEC v0.1 section 5). The guard is intentionally broad and
        is NOT weakened here. The value still needs to be checked and persisted
        for six-field completeness, so it travels through this separate,
        explicitly-named channel instead -- and it is never emitted as
        `implied_volatility` nor fed to the option benchmark.
        """
        fields = self.to_pre_event_fields()
        fields["panel_implied_volatility"] = self.panel_implied_volatility
        return fields

    @property
    def is_recent_cache_fallback_iv(self) -> bool:
        return was_served_from_recent_cache_fallback(self.source_status_iv)

    @property
    def is_recent_cache_fallback_realized_vol(self) -> bool:
        return was_served_from_recent_cache_fallback(self.source_status_realized_vol)

    @property
    def is_recent_cache_fallback_gst(self) -> bool:
        return was_served_from_recent_cache_fallback(self.source_status_gst)

    @property
    def is_recent_cache_fallback_wiki(self) -> bool:
        return was_served_from_recent_cache_fallback(self.source_status_wiki)

    @property
    def is_recent_cache_fallback_price(self) -> bool:
        return was_served_from_recent_cache_fallback(self.source_status_price)

    @property
    def any_leg_served_from_recent_cache_fallback(self) -> bool:
        return any((
            self.is_recent_cache_fallback_gst,
            self.is_recent_cache_fallback_wiki,
            self.is_recent_cache_fallback_price,
        ))

    def to_pre_event_fields(self) -> dict:
        """The subset/shape consumed by gst_market_response.completeness /
        pipeline.capture_pre_event_and_option_benchmark_v0_1 -- deliberately
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
            "source_status_iv": self.source_status_iv,
            "source_status_realized_vol": self.source_status_realized_vol,
            "source_status_gst_raw": self.source_status_gst_raw,
            "source_status_wiki_raw": self.source_status_wiki_raw,
            "source_status_price_raw": self.source_status_price_raw,
            "source_status_iv_raw": self.source_status_iv_raw,
            "source_status_realized_vol_raw": self.source_status_realized_vol_raw,
            "volume": self.volume,
            "run_date": self.run_date,
            "price_asof_date": self.price_asof_date,
            "panel_status": self.panel_status,
            "panel_row_count": self.panel_row_count,
            "panel_unique_ticker_count": self.panel_unique_ticker_count,
            "panel_all_six_fields_clean_count": self.panel_all_six_fields_clean_count,
            "source_csv_path": self.source_csv_path,
            "source_csv_sha256": self.source_csv_sha256,
            "source_marker_path": self.source_marker_path,
            "source_marker_sha256": self.source_marker_sha256,
            "research_commit_sha": self.research_commit_sha,
            "methodology_version": self.methodology_version,
            "adapter_schema_version": self.adapter_schema_version,
            "ticker": self.ticker,
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

    raw_status_gst = row.get("gst_status")
    raw_status_wiki = row.get("wiki_status")
    raw_status_price = row.get("price_history_status")
    # Independent legs, read from their own columns -- never inherited from the
    # price leg. An absent column normalises to "missing", which fails closed.
    raw_status_iv = row.get("iv_status")
    raw_status_realized_vol = row.get("realized_vol_status")

    source_status_gst = normalize_leg_status(raw_status_gst)
    source_status_wiki = normalize_leg_status(raw_status_wiki)
    source_status_price = normalize_leg_status(raw_status_price)
    source_status_iv = normalize_leg_status(raw_status_iv)
    source_status_realized_vol = normalize_leg_status(raw_status_realized_vol)

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
        source_status_gst_raw=preserve_raw_status(raw_status_gst),
        source_status_wiki_raw=preserve_raw_status(raw_status_wiki),
        source_status_price_raw=preserve_raw_status(raw_status_price),
        source_status_iv=source_status_iv,
        source_status_iv_raw=preserve_raw_status(raw_status_iv),
        source_status_realized_vol=source_status_realized_vol,
        source_status_realized_vol_raw=preserve_raw_status(raw_status_realized_vol),
        panel_implied_volatility=_parse_optional_float(row.get("implied_volatility")),
        run_date=(row.get("run_date") or None),
        price_asof_date=(row.get("price_asof_date") or None),
        panel_row_count=marker.get("row_count"),
        panel_unique_ticker_count=marker.get("unique_ticker_count"),
        panel_all_six_fields_clean_count=marker.get("all_six_fields_clean_count"),
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
