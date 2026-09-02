#!/usr/bin/env python3
"""Which dated artifact is the newest one. Version-aware, not lexical.

HYP-04's artifacts are named `NAME_<ISO date>[_vN].<ext>`, and four places
picked the newest by plain `sorted(paths)[-1]`: the dashboard, the shock
builder, the peer-ceiling builder and the lineage runner.

That is right up to `_v9` and WRONG at `_v10`, because lexical order puts
"_v10" before "_v2". The dashboard's own comment conceded it was "not correct
in general".

=== WHY IT WAS WORTH FIXING BEFORE IT BIT ===

Because of how it fails. It does not raise, and it does not produce an empty
result. It silently reads a STALE artifact and renders it as current -- on a
page whose entire job is to state what is true right now, and in builders that
re-derive from whatever they are handed.

The project already has `_v4` on disk
(`HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-08-27_v4.json`), and the
peer-ceiling artifacts reached `_v2` within a day of being created. Same-day
revisions are the repo's normal correction mechanism, so the counter climbs
exactly when corrections are happening -- the worst moment to start reading the
superseded copy.

=== THE KEY ===

Sort on `(name with the version suffix removed, version as an INT)`. The date
sits inside the base, and ISO dates sort correctly as text, so a later date
still wins over any revision of an earlier one. A bare name is version 0, which
puts it before its own `_v2`, which is what supersession means.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

#: `_v12` or `_v1.10` immediately before the extension. Deliberately anchored:
#: a `_v2` in the MIDDLE of a name is part of the name, not a revision counter.
#:
#: The dotted form was added 2026-09-01. The curated linkage map is named
#: `HYP04_Linkage_Map_v1.0.csv`, which the integer-only pattern did not match at
#: all -- so every map fell back to lexical order and `newest` picked `_v1.2`
#: over `_v1.10`. That is the same double-digit failure this module was written
#: to fix, surviving in the one artifact family whose version happens to have a
#: dot in it.
_VERSION_SUFFIX = re.compile(
    r"^(?P<base>.*)_v(?P<maj>\d+)(?:\.(?P<min>\d+))?(?P<ext>\.[^.]*)$")


def split_version(name: str) -> tuple[str, tuple[int, int]]:
    """'X_v10.json' -> ('X.json', (10, 0)); 'M_v1.10.csv' -> ('M.csv', (1, 10)).

    A name with no revision suffix is version (0, 0), which sorts before its
    own `_v1` -- that is what supersession means.

    The version is a TUPLE, not an int, so `_v1.10` compares above `_v1.2`
    numerically rather than as text. A deeper form (`_v1.2.3`) does not match
    and is treated as part of the name, which is the conservative direction:
    an unrecognised scheme keeps its whole filename and orders lexically rather
    than being silently reinterpreted.
    """
    m = _VERSION_SUFFIX.match(name)
    if not m:
        return name, (0, 0)
    minor = m.group("min")
    return (m.group("base") + m.group("ext"),
            (int(m.group("maj")), int(minor) if minor is not None else 0))


def artifact_sort_key(name: str) -> tuple[str, tuple[int, int]]:
    """Order artifacts by base name, then by revision NUMBER."""
    return split_version(name)


def newest(paths: Iterable[Any]) -> Optional[Any]:
    """The newest artifact, or None. Accepts Paths or anything with `.name`.

    Returns None rather than raising on an empty input: every caller already
    has to handle "no artifact on disk", and an IndexError from a sort helper
    would tell them nothing about which glob came back empty.
    """
    items: Sequence[Any] = list(paths)
    if not items:
        return None
    return max(items, key=lambda p: artifact_sort_key(
        p.name if isinstance(p, Path) else str(p)))


def newest_in(directory: Path, pattern: str) -> Optional[Path]:
    """The newest artifact in `directory` matching `pattern`, or None."""
    return newest(directory.glob(pattern))
