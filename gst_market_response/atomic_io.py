# Atomic write helpers: write-to-temp-then-rename, so a crash or concurrent
# reader never observes a partially-written file. Used by raw_bars.py
# (immutable bar files + manifest) and completion_marker.py.
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True, default=str))


def append_bytes_never_truncate(path: Path, data: bytes) -> None:
    """Appends to a file, creating it if necessary. Explicitly opens in 'ab'
    mode only -- never 'w' or 'r+' truncating modes -- so any bytes already
    on disk are physically untouched by this call. Used for the append-only
    event-record log (see event_record.py)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
