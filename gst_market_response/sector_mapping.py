# Loader for the locked ticker-to-sector-ETF mapping (SPEC section 7.1).
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DEFAULT_MAPPING_PATH = (
    Path(__file__).resolve().parent.parent / "Live Signal Engine" / "GST_Sector_ETF_Mapping_v0.1.json"
)


class SectorMappingError(ValueError):
    pass


@dataclass(frozen=True)
class SectorMapping:
    schema_version: str
    spy_benchmark: str
    mapping: dict[str, str]

    def sector_etf_for(self, ticker: str) -> Optional[str]:
        return self.mapping.get(ticker)


def load_sector_mapping(path: Optional[Path] = None) -> SectorMapping:
    target = path or _DEFAULT_MAPPING_PATH
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    for required in ("schema_version", "spy_benchmark", "mapping"):
        if required not in data:
            raise SectorMappingError(f"sector mapping file missing required key {required!r}: {target}")
    return SectorMapping(
        schema_version=data["schema_version"],
        spy_benchmark=data["spy_benchmark"],
        mapping=dict(data["mapping"]),
    )
