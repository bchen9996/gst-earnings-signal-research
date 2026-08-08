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


class ImmutableArtifactExistsError(FileExistsError):
    """An immutable artifact already exists at this path.

    PROTOCOL v0.2 marker lifecycle: progress is never made by overwriting or
    unlinking evidence. Stage markers are written once and never replaced.
    """


def _fsync_dir(directory: Path) -> None:
    """Best-effort directory fsync so the new entry is durable.

    Windows cannot open a directory as a file descriptor; that is a platform
    limitation, not a correctness failure of the link itself, so it is skipped
    rather than raised.
    """
    try:
        fd = os.open(str(directory), getattr(os, "O_DIRECTORY", os.O_RDONLY))
    except (OSError, AttributeError):
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _exclusive_create_bytes(path: Path, data: bytes) -> None:
    """Write-once primitive with NO time-of-check/time-of-use window.

    The previous implementation was:

        if path.exists(): raise          # (1) check
        atomic_write_bytes(path, data)   # (2) write temp, then os.replace()

    os.replace() REPLACES unconditionally, so any artifact created by another
    writer between (1) and (2) was silently destroyed -- precisely the evidence
    loss the immutable-marker rule exists to prevent. There is no ordering of
    exists()+replace() that fixes this; the create itself must be the exclusive
    operation.

    Sequence here:
      * write the full payload to a temp file in the target directory and fsync
        it, so the bytes are durable before the name exists at all;
      * os.link() the temp file to the final path. link() creates a NEW
        directory entry and fails with FileExistsError if the name is taken --
        it never replaces. The final name therefore appears atomically, already
        carrying complete content, and a loser of the race raises;
      * fsync the directory, then unlink the temp file on every path.

    If the filesystem does not support hard links, fall back to an exclusive
    open (O_CREAT|O_EXCL), which is equally race-safe on the create; only the
    content-atomicity is weaker, and a partial file cannot be mistaken for a
    complete one because the winner is the only writer that ever holds the fd.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp_name, str(path))
        except FileExistsError as exc:
            raise ImmutableArtifactExistsError(
                f"refusing to overwrite immutable artifact {path}; evidence is append-only"
            ) from exc
        except (OSError, AttributeError, NotImplementedError):
            # No hard-link support on this filesystem: exclusive create instead.
            _exclusive_open_write(path, data)
        _fsync_dir(path.parent)
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def _exclusive_open_write(path: Path, data: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    flags |= getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(path), flags, 0o644)
    except FileExistsError as exc:
        raise ImmutableArtifactExistsError(
            f"refusing to overwrite immutable artifact {path}; evidence is append-only"
        ) from exc
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def atomic_write_bytes_no_overwrite(path: Path, data: bytes) -> None:
    """Write-once bytes. Raises ImmutableArtifactExistsError if the name is
    already taken -- with no exists()-then-replace race."""
    _exclusive_create_bytes(Path(path), data)


def atomic_write_json_no_overwrite(path: Path, obj: Any) -> None:
    """Atomic write that REFUSES to replace an existing file.

    Immutable stage markers use this so that no production path -- and no test
    -- can advance by clobbering prior evidence. Race-safe: see
    _exclusive_create_bytes().
    """
    text = json.dumps(obj, indent=2, sort_keys=True, default=str)
    _exclusive_create_bytes(Path(path), text.encode("utf-8"))


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
