# Loader + mechanical review gate for the locked ticker-to-sector-BENCHMARK
# mapping (SPEC section 7.1).
#
# THE RULE, stated once: each ticker is benchmarked against the broad SPDR
# Select Sector ETF corresponding to its GICS sector. That is the entire
# basis of the assignment. Whether the company is currently a holding of that
# ETF is a separate, independently recorded observation that never affects
# the assignment -- a confirmed NONconstituent (GME/XLY) is a legitimate,
# fully approvable entry, and nothing in this mapping represents any company
# as an ETF holding.
#
# mapping_version 0.3 exists to correct exactly that conflation: version 0.2
# described the mapping as "23/24 confirmed constituents" with GME as an
# "unresolved ambiguity", which framed fund membership as the thing being
# verified when only the GICS sector ever mattered.
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
# for benchmark_etf. Not an assertion that these are the only valid choices in
# general, only that this is the closed, documented set this codebase uses.
VALID_SECTOR_ETF_SYMBOLS = frozenset(
    {"XLK", "XLV", "XLE", "XLY", "XLP", "XLI", "XLF", "XLU", "XLB", "XLRE", "XLC"}
)

REVIEW_STATUSES = ("DRAFT", "APPROVED", "REJECTED")

# The ONLY permitted basis for a benchmark assignment. The mapping benchmarks
# each stock against the broad sector ETF for its GICS sector; membership of
# that ETF is never the reason for the assignment. 'etf_membership' is
# deliberately absent from this set so it cannot be introduced silently.
VALID_BENCHMARK_BASES = frozenset({"gics_sector"})

# Whether the company is currently a disclosed holding of its benchmark ETF.
# Recorded as an INDEPENDENT observation. 'confirmed_nonconstituent' is a
# perfectly valid state for an APPROVED entry -- a company is benchmarked
# against its GICS sector's ETF whether or not the fund happens to hold it.
VALID_CONSTITUENT_STATUSES = frozenset(
    {"confirmed_constituent", "confirmed_nonconstituent", "not_verified"}
)


class SectorMappingError(ValueError):
    pass


class SectorMappingNotApprovedError(SectorMappingError):
    """Raised when a DRAFT (or REJECTED) mapping is used for anything other
    than a deterministic/demo fixture -- see assert_usable_for_real_event()."""


@dataclass(frozen=True)
class SectorMappingEntry:
    """One ticker's sector-benchmark assignment.

    The six fields are deliberately separate concepts. `gics_sector` is the
    company's GICS sector; `benchmark_etf` is the sector ETF used as its
    return benchmark; `benchmark_basis` records WHY that ETF was chosen
    (always the GICS sector, never fund membership); `constituent_status` is
    an independent observation of whether the fund actually holds the company;
    `classification_source` and `retrieval_date` are the evidence for the
    GICS sector.

    Keeping constituent_status separate is the whole point: an entry may be a
    confirmed NONconstituent and still be a fully approved sector benchmark.
    Conflating the two is what produced the retracted '23/24 confirmed
    constituents' framing in mapping_version 0.2.
    """

    gics_sector: str
    benchmark_etf: str
    benchmark_basis: str
    constituent_status: str
    classification_source: str
    retrieval_date: str
    constituent_status_source: Optional[str] = None
    notes: Optional[str] = None

    @property
    def is_confirmed_nonconstituent(self) -> bool:
        return self.constituent_status == "confirmed_nonconstituent"


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

    def benchmark_etf_for(self, ticker: str) -> Optional[str]:
        entry = self.mapping.get(ticker)
        return entry.benchmark_etf if entry else None

    def gics_sector_for(self, ticker: str) -> Optional[str]:
        entry = self.mapping.get(ticker)
        return entry.gics_sector if entry else None

    def constituent_status_for(self, ticker: str) -> Optional[str]:
        entry = self.mapping.get(ticker)
        return entry.constituent_status if entry else None

    # Back-compatible aliases. Deliberately named for the BENCHMARK, since the
    # ETF has never been anything other than a benchmark in this codebase.
    def sector_etf_for(self, ticker: str) -> Optional[str]:
        return self.benchmark_etf_for(ticker)

    def sector_for(self, ticker: str) -> Optional[str]:
        return self.gics_sector_for(ticker)


def load_sector_mapping(path: Optional[Path] = None) -> SectorMapping:
    target = path or _DEFAULT_MAPPING_PATH
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    for required in ("schema_version", "mapping_version", "spy_benchmark", "review_status", "mapping"):
        if required not in data:
            raise SectorMappingError(f"sector mapping file missing required key {required!r}: {target}")
    mapping = {}
    for ticker, entry in data["mapping"].items():
        for required in ("gics_sector", "benchmark_etf", "benchmark_basis", "constituent_status",
                         "classification_source", "retrieval_date"):
            if required not in entry:
                raise SectorMappingError(f"{ticker}: mapping entry missing required key {required!r} in {target}")
        mapping[ticker] = SectorMappingEntry(
            gics_sector=entry["gics_sector"],
            benchmark_etf=entry["benchmark_etf"],
            benchmark_basis=entry["benchmark_basis"],
            constituent_status=entry["constituent_status"],
            classification_source=entry["classification_source"],
            retrieval_date=entry["retrieval_date"],
            constituent_status_source=entry.get("constituent_status_source"),
            notes=entry.get("notes"),
        )
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
        if not entry.gics_sector or not isinstance(entry.gics_sector, str):
            errors.append(f"{ticker}: missing or invalid gics_sector")
        if entry.benchmark_etf not in VALID_SECTOR_ETF_SYMBOLS:
            errors.append(f"{ticker}: benchmark_etf {entry.benchmark_etf!r} is not a recognized sector ETF symbol")
        if entry.benchmark_basis not in VALID_BENCHMARK_BASES:
            errors.append(
                f"{ticker}: benchmark_basis {entry.benchmark_basis!r} must be one of {sorted(VALID_BENCHMARK_BASES)} "
                f"-- a benchmark is assigned from the GICS sector, never from ETF membership"
            )
        if entry.constituent_status not in VALID_CONSTITUENT_STATUSES:
            errors.append(
                f"{ticker}: constituent_status {entry.constituent_status!r} must be one of "
                f"{sorted(VALID_CONSTITUENT_STATUSES)}"
            )

    if not sm.mapping_version:
        errors.append("mapping_version is required")

    if sm.review_status not in REVIEW_STATUSES:
        errors.append(f"review_status {sm.review_status!r} must be one of {REVIEW_STATUSES}")

    if sm.review_status == "APPROVED":
        if not sm.reviewed_by or not sm.reviewed_at_utc:
            errors.append("review_status is APPROVED but reviewed_by/reviewed_at_utc is missing")
        # APPROVED is only valid if every single ticker was ACTUALLY reviewed
        # under the stated rule -- meaning each carries a GICS-sector source,
        # a retrieval date, and an explicit (not defaulted) constituent
        # observation. A mapping cannot be approved wholesale while individual
        # entries remain unevidenced.
        unreviewed = sorted(
            t
            for t, e in sm.mapping.items()
            if not (e.classification_source or "").strip()
            or not (e.retrieval_date or "").strip()
            or e.constituent_status == "not_verified"
        )
        if unreviewed:
            errors.append(
                f"review_status is APPROVED but these tickers were not actually reviewed under the "
                f"GICS-sector rule (missing classification_source/retrieval_date, or constituent_status "
                f"still 'not_verified'): {unreviewed}"
            )

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
