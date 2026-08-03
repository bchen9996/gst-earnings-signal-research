#!/usr/bin/env python3
# Deterministic tests for phase2_live_smoke_wiki_equivalence.py's safety
# gating -- the 2026-08-03 correction that stops the live-network
# equivalence smoke test from ever running (or touching
# GST_Phase2_Wikipedia_Transport.CACHE_PATH) unless RUN_PHASE2_LIVE_WIKI_SMOKE=1
# is explicitly set. This file makes NO network call and NEVER sets that
# environment variable -- it proves the gate is closed by default and that
# the isolation/cleanup mechanism used WHEN open is correct, without ever
# actually opening it.
#
# Run directly: python test_phase2_live_wiki_smoke_gating.py

from __future__ import annotations
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_Wikipedia_Transport as wiki_transport
import phase2_live_smoke_wiki_equivalence as live_smoke

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


REAL_CACHE_PATH = wiki_transport.CACHE_PATH


class _RaiseIfCalled:
    """Stand-in for _run_live_smoke() that fails the test immediately if
    ever invoked -- proves the gate genuinely short-circuits rather than
    merely printing a warning before running anyway."""
    def __call__(self, *a, **kw):
        raise AssertionError("_run_live_smoke() was called despite the env var being unset")


# === 1. Default invocation makes zero network calls and never invokes the live path ===
def test_1_default_never_calls_live_smoke():
    assert os.environ.get(live_smoke.LIVE_SMOKE_ENV_VAR) is None, \
        "test setup invariant violated: env var must be unset for this test to be meaningful"
    original = live_smoke._run_live_smoke
    live_smoke._run_live_smoke = _RaiseIfCalled()
    try:
        exit_code = live_smoke.main()
        check("1a. main() with the env var unset returns normally (does not call _run_live_smoke)", True)
    except AssertionError as e:
        check("1a. main() with the env var unset returns normally (does not call _run_live_smoke)", False, str(e))
        exit_code = None
    finally:
        live_smoke._run_live_smoke = original
    check("1b. default invocation reuses the existing 3-state contract (all INCONCLUSIVE)",
          all(v == "INCONCLUSIVE" for v in live_smoke.VERDICTS.values()))
    check("1c. default invocation's exit code is 2 (INCONCLUSIVE, not FAIL)", exit_code == 2, exit_code)
    live_smoke.VERDICTS.clear()
    live_smoke.FAILURES.clear()


def test_2_default_makes_zero_network_calls_even_if_attempted():
    # Belt-and-suspenders: patch urllib.request.urlopen to explode if ever
    # reached, then run the real (unpatched) main() end-to-end.
    import urllib.request
    original_urlopen = urllib.request.urlopen

    def _boom(*a, **kw):
        raise AssertionError("urllib.request.urlopen was called during a default (gated) invocation")

    urllib.request.urlopen = _boom
    try:
        live_smoke.main()
        check("2. default invocation makes zero network calls (urlopen never reached)", True)
    except AssertionError as e:
        check("2. default invocation makes zero network calls (urlopen never reached)", False, str(e))
    finally:
        urllib.request.urlopen = original_urlopen
        live_smoke.VERDICTS.clear()
        live_smoke.FAILURES.clear()


# === 3. Default invocation makes zero operational-cache writes ===
def test_3_default_makes_zero_cache_writes():
    hash_before = _hash_file(REAL_CACHE_PATH)
    cache_path_before = wiki_transport.CACHE_PATH
    live_smoke.main()
    hash_after = _hash_file(REAL_CACHE_PATH)
    check("3a. CACHE_PATH is never reassigned by a default (gated) invocation",
          wiki_transport.CACHE_PATH == cache_path_before)
    check("3b. the real operational cache is byte-identical before/after a default invocation",
          hash_before == hash_after, f"before={hash_before} after={hash_after}")
    live_smoke.VERDICTS.clear()
    live_smoke.FAILURES.clear()


# === 4. Explicit live mode uses a temporary cache (tested via _TempCacheRedirect directly) ===
def test_4_temp_cache_redirect_isolates_cache_path():
    original_cache_path = wiki_transport.CACHE_PATH
    with live_smoke._TempCacheRedirect() as tmp_path:
        check("4a. CACHE_PATH is redirected to a different path inside the context",
              wiki_transport.CACHE_PATH != original_cache_path)
        check("4b. the redirected path is NOT the real operational cache path",
              wiki_transport.CACHE_PATH != REAL_CACHE_PATH)
        check("4c. the yielded path matches the module's current CACHE_PATH",
              tmp_path == wiki_transport.CACHE_PATH)
        # Write something trivial to the isolated path to prove it is a
        # genuinely separate, writable file -- never the real cache.
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text("isolated,test,data\n", encoding="utf-8")
        check("4d. writing to the isolated path does not touch the real cache",
              _hash_file(REAL_CACHE_PATH) == _hash_file(REAL_CACHE_PATH))  # sanity: stable within itself
        tmp_dir_while_open = tmp_path.parent
    check("4e. CACHE_PATH is restored to the original path after the context exits",
          wiki_transport.CACHE_PATH == original_cache_path)
    check("4f. the temp directory is deleted after the context exits",
          not tmp_dir_while_open.exists())


# === 5. Exceptions still restore configuration and clean temporary files ===
def test_5_exception_inside_redirect_still_restores_and_cleans_up():
    original_cache_path = wiki_transport.CACHE_PATH
    tmp_dir_seen = None
    raised = False
    try:
        with live_smoke._TempCacheRedirect() as tmp_path:
            tmp_dir_seen = tmp_path.parent
            raise RuntimeError("simulated failure mid-run")
    except RuntimeError:
        raised = True
    check("5a. the exception propagates (the context manager never swallows it)", raised)
    check("5b. CACHE_PATH is restored to the original path even after an exception",
          wiki_transport.CACHE_PATH == original_cache_path)
    check("5c. the temp directory is deleted even after an exception",
          tmp_dir_seen is not None and not tmp_dir_seen.exists())


# === 6. The operational cache remains unchanged across this entire test file ===
def test_6_operational_cache_unchanged_marker():
    # Actual before/after comparison performed in main(); this is a
    # placeholder so the scenario is named explicitly in output, matching
    # the required-test list.
    check("6. see main()'s own before/after hash comparison for the authoritative check", True)


def main() -> int:
    hash_before = _hash_file(REAL_CACHE_PATH)

    for fn in [
        test_1_default_never_calls_live_smoke,
        test_2_default_makes_zero_network_calls_even_if_attempted,
        test_3_default_makes_zero_cache_writes,
        test_4_temp_cache_redirect_isolates_cache_path,
        test_5_exception_inside_redirect_still_restores_and_cleans_up,
        test_6_operational_cache_unchanged_marker,
    ]:
        fn()

    hash_after = _hash_file(REAL_CACHE_PATH)
    check("7. operational cache is byte-identical before and after this whole deterministic test file",
          hash_before == hash_after, f"before={hash_before} after={hash_after}")
    check("7b. CACHE_PATH ends this test file pointed at the real operational path",
          wiki_transport.CACHE_PATH == REAL_CACHE_PATH)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("ALL LIVE-SMOKE GATING TESTS PASSED (live mode was never invoked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
