#!/usr/bin/env python3
"""HYP-04 artifact-selection tests. OFFLINE; touches only filenames.

This module exists because `sorted(paths)[-1]` is right up to `_v9` and wrong
at `_v10`, and it fails SILENTLY: it returns a superseded artifact and the
caller renders or re-derives from it with nothing to say anything is stale.

test_1 is the whole point -- the `_v2` / `_v3` / `_v10` ordering that lexical
sort gets backwards. test_4 asserts every site that used to sort lexically now
goes through this module.

Run directly: python test_hyp04_supply_chain_hedge_artifacts.py
"""
from __future__ import annotations

import io
import socket
import sys
from pathlib import Path

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


def _no_net(*a, **k):                                    # pragma: no cover
    raise AssertionError("this suite must make no network call")


socket.socket.connect = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.artifacts import (  # noqa: E402
    artifact_sort_key,
    newest,
    newest_in,
    split_version,
)

BASE = "HYP04_X_2026-08-31"


def _code_only(src: str) -> str:
    """Source with whole-line comments removed.

    The modules explain the old bug in their comments, so a raw substring
    search matches the explanation as readily as the defect -- which is exactly
    how test_4 first failed, against a comment I had just written.
    """
    return "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))


def test_1_the_double_digit_revision() -> None:
    print("\n--- 1: _v10 is newer than _v3, which lexical sort denies ---")
    names = [f"{BASE}.json", f"{BASE}_v2.json", f"{BASE}_v3.json",
             f"{BASE}_v10.json"]
    got = newest([Path(n) for n in names])
    check("1a. _v10 wins", got.name == f"{BASE}_v10.json", got.name)

    # CONTROL: the old behaviour, shown to be wrong on the same input. Without
    # this the test above could pass for the wrong reason.
    lexical = sorted(names)[-1]
    check("1b. CONTROL: lexical sort really does pick _v3 here",
          lexical == f"{BASE}_v3.json", lexical)
    check("1c. so the two genuinely disagree", lexical != got.name)

    check("1d. and it still holds at _v100",
          newest([Path(f"{BASE}_v{i}.json") for i in (9, 10, 100, 11)]).name
          == f"{BASE}_v100.json")


def test_2_a_later_date_beats_any_revision() -> None:
    print("\n--- 2: the date dominates the revision counter ---")
    names = [f"{BASE}_v10.json", "HYP04_X_2026-09-01.json"]
    check("2a. a later date wins over a high revision",
          newest([Path(n) for n in names]).name == "HYP04_X_2026-09-01.json")
    check("2b. even against _v2 of the later date",
          newest([Path(f"{BASE}_v10.json"),
                  Path("HYP04_X_2026-09-01_v2.json")]).name
          == "HYP04_X_2026-09-01_v2.json")
    check("2c. a bare name is older than its own revision",
          newest([Path(f"{BASE}_v2.json"), Path(f"{BASE}.json")]).name
          == f"{BASE}_v2.json")
    # Different artifact families must not be compared across each other by
    # version -- the base name has to sort first.
    check("2d. base name sorts before version",
          artifact_sort_key("A_v10.json") < artifact_sort_key("B_v2.json"))


def test_3_only_a_trailing_suffix_is_a_revision() -> None:
    print("\n--- 3: a _v2 in the middle of a name is part of the name ---")
    check("3a. trailing suffix parses",
          split_version(f"{BASE}_v10.json") == (f"{BASE}.json", 10),
          str(split_version(f"{BASE}_v10.json")))
    check("3b. bare name is version 0",
          split_version(f"{BASE}.json") == (f"{BASE}.json", 0))
    check("3c. a mid-name _v2 is NOT a revision",
          split_version("HYP04_v2_THING_2026-01-01.csv")
          == ("HYP04_v2_THING_2026-01-01.csv", 0),
          str(split_version("HYP04_v2_THING_2026-01-01.csv")))
    # The real one this protects: the registry files are named v1.10, and a
    # naive matcher could read them as revision suffixes.
    check("3d. a registry filename is not mangled",
          split_version("GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.10.json")[1] == 0,
          str(split_version("GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.10.json")))
    check("3e. a non-numeric suffix is not a revision",
          split_version(f"{BASE}_vFINAL.json")[1] == 0)
    check("3f. empty input returns None rather than raising",
          newest([]) is None)
    check("3g. plain strings work too",
          newest([f"{BASE}_v2.json", f"{BASE}_v10.json"]) == f"{BASE}_v10.json")


def test_4_every_former_lexical_site_uses_this() -> None:
    print("\n--- 4: the four sites that had the bug now share one helper ---")
    sites = {
        "hyp04_supply_chain_hedge/dashboard.py": "_newest",
        "hyp04_supply_chain_hedge/make_anchor_shocks.py": "_newest_calendar",
        "hyp04_supply_chain_hedge/make_peer_ceiling.py": "_newest",
        "hyp04_supply_chain_hedge/run_peer_lineage_audit.py": "_newest",
    }
    for path in sites:
        src = io.open(path, encoding="utf-8").read()
        check(f"4. {Path(path).name} imports the shared helper",
              "from .artifacts import" in src, path)
        # CODE ONLY. The modules explain the old bug in their comments, and a
        # raw substring search matches the explanation as readily as the
        # defect -- which is how this check first failed.
        code = _code_only(src)
        check(f"4. {Path(path).name} no longer sorts lexically",
              "sorted(paths)[-1]" not in code
              and "sorted(paths, key=lambda p: p.name)[-1]" not in code,
              path)

    # CONTROL: the code-only filter must still see a real occurrence, or 4
    # would pass on any file at all.
    probe = "x = 1\nbad = sorted(paths)[-1]\n"
    check("4e. CONTROL: the filter still detects a genuine occurrence",
          "sorted(paths)[-1]" in _code_only(probe))
    check("4f. CONTROL: and it really does drop commented-out ones",
          "sorted(paths)[-1]" not in _code_only("# sorted(paths)[-1]\n"))


def test_5_it_picks_the_real_artifacts_on_disk() -> None:
    print("\n--- 5: against the actual Live Signal Engine directory ---")
    lse = Path("Live Signal Engine")
    if not lse.is_dir():
        skip("5. real artifacts", "no Live Signal Engine directory")
        return
    got = newest_in(lse, "HYP04_PEER_CEILING_*.json")
    check("5a. the newest peer-ceiling artifact is found", got is not None)
    if got is not None:
        every = sorted(p.name for p in lse.glob("HYP04_PEER_CEILING_*.json"))
        check("5b. and it is the highest revision present",
              artifact_sort_key(got.name)
              == max(artifact_sort_key(n) for n in every), got.name)
    check("5c. a pattern matching nothing returns None",
          newest_in(lse, "HYP04_NOTHING_MATCHES_THIS_*.json") is None)


if __name__ == "__main__":
    test_1_the_double_digit_revision()
    test_2_a_later_date_beats_any_revision()
    test_3_only_a_trailing_suffix_is_a_revision()
    test_4_every_former_lexical_site_uses_this()
    test_5_it_picks_the_real_artifacts_on_disk()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 ARTIFACT-SELECTION TESTS PASSED")
