# Loader + mechanical review gate for the locked ticker-to-sector-ETF
# mapping (SPEC section 7.1). TASK 3 of the operational-readiness pass adds
# validate_sector_mapping() and assert_usable_for_real_event() -- the
# existing mapping is explicitly NOT declared final by this change; it
# remains review_status="DRAFT" until a human sets it to "APPROVED".
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .constants import LOCKED_24_TICKER_UNIVERSE

_DEFAULT_MAPPING_PATH = (
    Path(__file__).resolve().parent.parent / "Live Signal Engine" / "GST_Sector_ETF_Mapping_v0.1.json"
)

# The 11 SPDR Select Sector ETFs -- the only symbols this mapping may use
# for sector_etf. Not an assertion that these are the only valid choices in
# general, only that this is the closed, documented set this codebase uses.
VALID_SECTOR_ETF_SYMBOLS = frozenset(
    {"XLK", "XLV", "XLE", "XLY", "XLP", "XLI", "XLF", "XLU", "XLB", "XLRE", "XLC"}
)

REVIEW_STATUSES = ("DRAFT", "APPROVED", "REJECTED")


class SectorMappingError(ValueError):
    pass


class SectorMappingNotApprovedError(SectorMappingError):
    """Raised when a DRAFT (or REJECTED) mapping is used for anything other
    than a deterministic/demo fixture -- see assert_usable_for_real_event()."""


@dataclass(frozen=True)
class SectorMappingEntry:
    sector: str
    sector_etf: str
    review: Optional[dict] = None  # {status, source, retrieved_date, reason} -- see Section D review


@dataclass(frozen=True)
class SectorMapping:
    schema_version: str
    mapping_version: str
    spy_benchmark: str
    review_status: str
    reviewed_by: Optional[str]
    reviewed_at_utc: Optional[str]
    effective_date: Optional[str]
    mapping: dict[str, SectorMappingEntry]

    def sector_etf_for(self, ticker: str) -> Optional[str]:
        entry = self.mapping.get(ticker)
        return entry.sector_etf if entry else None

    def sector_for(self, ticker: str) -> Optional[str]:
        entry = self.mapping.get(ticker)
        return entry.sector if entry else None


def load_sector_mapping(path: Optional[Path] = None) -> SectorMapping:
    target = path or _DEFAULT_MAPPING_PATH
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    for required in ("schema_version", "mapping_version", "spy_benchmark", "review_status", "mapping"):
        if required not in data:
            raise SectorMappingError(f"sector mapping file missing required key {required!r}: {target}")
    mapping = {
        ticker: SectorMappingEntry(sector=entry["sector"], sector_etf=entry["sector_etf"], review=entry.get("review"))
        for ticker, entry in data["mapping"].items()
    }
    return SectorMapping(
        schema_version=data["schema_version"],
        mapping_version=data["mapping_version"],
        spy_benchmark=data["spy_benchmark"],
        review_status=data["review_status"],
        reviewed_by=data.get("reviewed_by"),
        reviewed_at_utc=data.get("reviewed_at_utc"),
        effective_date=data.get("effective_date"),
        mapping=mapping,
    )


def validate_sector_mapping(sm: SectorMapping) -> list[str]:
    """Mechanical validation. Returns a list of error strings -- empty means
    valid. Never raises itself, so a caller can collect and report every
    problem at once rather than stopping at the first one."""
    errors: list[str] = []

    mapping_tickers = set(sm.mapping.keys())
    universe = set(LOCKED_24_TICKER_UNIVERSE)

    missing = universe - mapping_tickers
    if missing:
        errors.append(f"missing tickers from the locked 24-ticker universe: {sorted(missing)}")

    extra = mapping_tickers - universe
    if extra:
        errors.append(f"mapping contains tickers outside the locked 24-ticker universe: {sorted(extra)}")

    if len(sm.mapping) != len(mapping_tickers):
        errors.append("duplicate ticker keys detected")  # structurally unreachable via a dict, kept as an explicit check

    for ticker, entry in sm.mapping.items():
        if not entry.sector or not isinstance(entry.sector, str):
            errors.append(f"{ticker}: missing or invalid sector name")
        if entry.sector_etf not in VALID_SECTOR_ETF_SYMBOLS:
            errors.append(f"{ticker}: sector_etf {entry.sector_etf!r} is not a recognized sector ETF symbol")

    if not sm.mapping_version:
        errors.append("mapping_version is required")

    if sm.review_status not in REVIEW_STATUSES:
        errors.append(f"review_status {sm.review_status!r} must be one of {REVIEW_STATUSES}")

    if sm.review_status == "APPROVED" and (not sm.reviewed_by or not sm.reviewed_at_utc):
        errors.append("review_status is APPROVED but reviewed_by/reviewed_at_utc is missing")

    return errors


def assert_usable_for_real_event(sm: SectorMapping, *, is_demo: bool) -> None:
    """A DRAFT (or REJECTED) mapping may be used freely in deterministic
    fixtures (is_demo=True) but must never be allowed to produce a COMPLETE
    real (non-demo) event -- raises SectorMappingNotApprovedError in that
    case. This is the mechanical enforcement of TASK 3's 'may not produce a
    COMPLETE real event' requirement."""
    errors = validate_sector_mapping(sm)
    if errors:
        raise SectorMappingError(f"sector mapping fails mechanical validation: {errors}")
    if is_demo:
        return
    if sm.review_status != "APPROVED":
        raise SectorMappingNotApprovedError(
            f"sector mapping review_status={sm.review_status!r} -- a real (non-demo) event "
            f"cannot reach COMPLETE using an unapproved mapping"
        )
