#!/usr/bin/env python3
"""Repository-wide invariants. No dependencies, no network, ~1 second.

WHY THIS FILE EXISTS SEPARATELY, and it is not tidiness.

The bridge-isolation check below already lived inside the HYP-01 R-reference
validation suite, where it was RED from 2026-08-19 to 2026-09-03 and nothing
could see it. Two independent causes, both structural:

  1. That suite imports the inference-feasibility runner at module scope, which
     imports statsmodels. Without statsmodels the whole file aborts at import
     before a single assertion runs, so the check could not execute in any
     environment lacking an optional dependency it does not itself need.

  2. Its input surface is EVERY production module in the repository, but the
     workflows that run it filter on the directories they are named after. The
     one file that broke the check lived in a package no filter mentioned, so
     the change that broke it could never trigger it.

A check whose scope is the whole repository needs a home whose dependencies are
nothing and whose trigger is every Python file. That is this file, paired with
.github/workflows/repo-invariants.yml. The original copy stays where it was as
a second chance; this one is the copy that always runs.

The scan logic has to live in a `test_`-prefixed file. A helper module holding
the banned literal would itself become an offender of the very rule it
implements -- and that is not hypothetical either: the first attempt at fixing
the 2026-08-19 breakage was rejected because the validation suite's own
FILENAME embeds the banned string.

Run: python test_repo_invariants.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}" + (f"   {detail}" if detail else ""))
        FAILURES.append(label)


# Directories that are not this repository's source. The original check omitted
# these and walked ~1857 files locally, the vast majority of them vendored
# packages -- so a dependency that happened to contain a banned string would
# have failed a check about OUR code. CI never noticed because CI has no venv.
SKIP_DIRS = {".venv", "venv", ".git", "__pycache__", "node_modules", ".mypy_cache"}

# Isolation rules. Each entry bans a literal substring from production modules.
# A table rather than one hardcoded string, so the next isolation rule lands
# here instead of being buried in whichever suite happens to own the subject.
#
#   token            the literal that must not appear
#   allow_dirs       path parts under which the token IS expected
#   why              what the rule protects, for the failure message
BANNED_IN_PRODUCTION: tuple[tuple[str, frozenset[str], str], ...] = (
    (
        "hyp01_r_reference",
        frozenset({"tools"}),
        "The R cross-check bridge is a VALIDATION harness. Production code that "
        "reaches it would make a research result depend on a reference "
        "implementation that exists to audit the primary method, not to be it.",
    ),
)


def _production_py_files() -> list[Path]:
    """Every .py file that is this repo's own production source.

    Excludes test files by the same rule the original check used -- a basename
    starting with `test_` -- so a test may name what it forbids.
    """
    out: list[Path] = []
    for p in ROOT.rglob("*.py"):
        if SKIP_DIRS & set(p.parts):
            continue
        if p.name.startswith("test_"):
            continue
        out.append(p)
    return out


def test_1_production_modules_stay_isolated() -> None:
    print("\n--- 1: production isolation ---")
    files = _production_py_files()

    # A scan that silently covers nothing always passes. Assert it found the
    # repository before trusting anything it reports about it.
    check("1a. the scan actually reaches this repository's source",
          len(files) >= 20, f"only {len(files)} production .py files found")

    for token, allow_dirs, why in BANNED_IN_PRODUCTION:
        offenders = []
        for p in files:
            if allow_dirs & set(p.parts):
                continue
            try:
                if token in p.read_text(encoding="utf-8", errors="ignore"):
                    offenders.append(str(p.relative_to(ROOT)))
            except OSError:
                pass
        check(f"1b. no production module names {token!r} "
              f"(scanned {len(files)} files, offenders={offenders})",
              not offenders, why)


def test_2_the_scan_can_actually_fail() -> None:
    """A guard nobody has seen fail is not known to work.

    This one had never been observed failing in CI or locally, which is exactly
    how it stayed broken for fifteen days. The matching logic is exercised here
    against a planted string so the mechanism is proven on every run, without
    touching the filesystem.
    """
    print("\n--- 2: the matcher is exercised, not assumed ---")
    token, allow_dirs, _ = BANNED_IN_PRODUCTION[0]

    planted = f"# a comment that mentions {token} in passing"
    check("2a. a planted occurrence IS detected", token in planted)
    check("2b. an unrelated module is NOT flagged",
          token not in "import numpy as np\nx = 1\n")

    # The exemption is by path part, not substring, so a directory merely
    # containing the allowed name does not exempt a file elsewhere.
    check("2c. the allow-list is matched on path PARTS, not substrings",
          allow_dirs & set(Path("tools/x.py").parts)
          and not (allow_dirs & set(Path("hyp04_supply_chain_hedge/x.py").parts)))

    check("2d. skipped directories are matched on path parts too",
          bool(SKIP_DIRS & set(Path(".venv/lib/site-packages/x.py").parts))
          and not (SKIP_DIRS & set(Path("hyp04_supply_chain_hedge/x.py").parts)))


def test_3_this_file_needs_nothing_to_run() -> None:
    """The dependency-free property is the point, so it is asserted.

    If this file ever grows a numerical or network import it stops being
    runnable in the cheap always-on workflow, and it silently returns to being
    a check that only runs when something heavier is installed.
    """
    print("\n--- 3: no dependencies ---")
    # An ALLOW-list over the real top-level import statements, not a deny-list
    # of substrings over the whole source. The deny-list version of this check
    # failed against its own token list -- it cannot name what it forbids
    # without containing it. That is the same shape that made the isolation
    # rule above awkward, and it is why the scan lives in a test_ file.
    allowed = {
        "from __future__ import annotations",
        "import sys",
        "from pathlib import Path",
    }
    lines = Path(__file__).read_text(encoding="utf-8").splitlines()
    imports = [ln.strip() for ln in lines if ln.startswith(("import ", "from "))]
    unexpected = [ln for ln in imports if ln not in allowed]
    check(f"3a. this file imports only the standard library it declares "
          f"({len(imports)} top-level import lines)",
          not unexpected, f"unexpected: {unexpected}")


if __name__ == "__main__":
    test_1_production_modules_stay_isolated()
    test_2_the_scan_can_actually_fail()
    test_3_this_file_needs_nothing_to_run()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL REPO INVARIANT TESTS PASSED")
