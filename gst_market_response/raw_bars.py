# Immutable raw-bar storage with SHA-256 provenance manifests. SPEC section 8.
#
# Raw bars are stored separately from derived event-level fields (see
# event_record.py) and are never edited after being written -- a correction
# writes a new, separately-named file and an amendment record; the original
# file and its hash stay on disk untouched.
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Sequence

from .atomic_io import atomic_write_bytes, atomic_write_json
from .bars import Bar


class RawBarStoreError(ValueError):
    pass


class RawBarAlreadyExistsError(RawBarStoreError):
    """Raised on an attempt to overwrite an existing raw-bar file -- raw bars
    are immutable; a correction must go through write_amendment_bars()
    instead, which never touches the original file."""


@dataclass(frozen=True)
class RawBarManifestEntry:
    relative_path: str
    sha256: str
    symbol: str
    session_date: str
    bar_interval: str
    source: str
    retrieved_at_utc: str
    is_amendment: bool = False
    amends_relative_path: Optional[str] = None


def _bars_to_csv_bytes(bars: Sequence[Bar]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["symbol", "timestamp_utc", "open", "high", "low", "close", "volume"])
    for b in bars:
        writer.writerow([b.symbol, b.timestamp_utc.isoformat(), b.open, b.high, b.low, b.close, b.volume])
    return buf.getvalue().encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RawBarStore:
    def __init__(self, root: Path):
        self.root = root

    def _event_dir(self, event_id: str) -> Path:
        return self.root / event_id

    def _manifest_path(self, event_id: str) -> Path:
        return self._event_dir(event_id) / "MANIFEST.json"

    def _load_manifest(self, event_id: str) -> list[dict]:
        manifest_path = self._manifest_path(event_id)
        if not manifest_path.exists():
            return []
        import json

        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_raw_bars(
        self,
        *,
        event_id: str,
        symbol: str,
        session_date: date,
        bars: Sequence[Bar],
        bar_interval: str,
        source: str,
        retrieved_at_utc: datetime,
    ) -> RawBarManifestEntry:
        filename = f"{symbol}_{session_date.isoformat()}.csv"
        target_path = self._event_dir(event_id) / filename
        if target_path.exists():
            raise RawBarAlreadyExistsError(
                f"{target_path} already exists -- raw bars are immutable, use write_amendment_bars()"
            )
        data = _bars_to_csv_bytes(bars)
        atomic_write_bytes(target_path, data)
        entry = RawBarManifestEntry(
            relative_path=filename,
            sha256=sha256_hex(data),
            symbol=symbol,
            session_date=session_date.isoformat(),
            bar_interval=bar_interval,
            source=source,
            retrieved_at_utc=retrieved_at_utc.isoformat(),
        )
        manifest = self._load_manifest(event_id)
        manifest.append(asdict(entry))
        atomic_write_json(self._manifest_path(event_id), manifest)
        return entry

    def write_amendment_bars(
        self,
        *,
        event_id: str,
        symbol: str,
        session_date: date,
        bars: Sequence[Bar],
        bar_interval: str,
        source: str,
        retrieved_at_utc: datetime,
        amends_relative_path: str,
        amendment_seq: int,
    ) -> RawBarManifestEntry:
        """Writes a NEW file (never overwrites amends_relative_path) and
        records an amendment manifest entry pointing back at the original."""
        filename = f"{symbol}_{session_date.isoformat()}_AMENDMENT_{amendment_seq:03d}.csv"
        target_path = self._event_dir(event_id) / filename
        if target_path.exists():
            raise RawBarAlreadyExistsError(f"{target_path} already exists")
        data = _bars_to_csv_bytes(bars)
        atomic_write_bytes(target_path, data)
        entry = RawBarManifestEntry(
            relative_path=filename,
            sha256=sha256_hex(data),
            symbol=symbol,
            session_date=session_date.isoformat(),
            bar_interval=bar_interval,
            source=source,
            retrieved_at_utc=retrieved_at_utc.isoformat(),
            is_amendment=True,
            amends_relative_path=amends_relative_path,
        )
        manifest = self._load_manifest(event_id)
        manifest.append(asdict(entry))
        atomic_write_json(self._manifest_path(event_id), manifest)
        return entry

    def verify(self, event_id: str, relative_path: str) -> bool:
        """Recomputes the SHA-256 of the file currently on disk and compares
        it against the manifest's recorded hash for that file. Returns False
        on any mismatch (file edited, corrupted, or manifest entry
        missing) -- callers must reject rather than use unverified bars."""
        manifest = self._load_manifest(event_id)
        recorded = next((e for e in manifest if e["relative_path"] == relative_path), None)
        if recorded is None:
            return False
        target_path = self._event_dir(event_id) / relative_path
        if not target_path.exists():
            return False
        with open(target_path, "rb") as f:
            actual_hash = sha256_hex(f.read())
        return actual_hash == recorded["sha256"]
