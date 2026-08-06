#!/usr/bin/env python3
# Deterministic regression coverage for the option-helper dependency boundary.
#
# WHAT THIS LOCKS DOWN
#
# The first real GitHub Actions run of PR #3 (run 31126964980, event=push,
# ubuntu-latest, Python 3.12.13) failed importing
# test_market_response_decomposition.py:
#
#   gst_market_response.option_chain_adapter
#     -> GST_MultiTicker_Forward_Log        (a live execution entry point)
#       -> pytrends.request
#   ModuleNotFoundError: No module named 'pytrends'
#
# requirements.txt covers gst_market_response/ only and deliberately excludes
# the wider legacy GST stack, so the fix was to break the import edge -- the
# two option helpers now live in the dependency-light GST_Option_Chain_Core --
# not to install Google Trends into a module that never queries it.
#
# Several checks run in a SUBPROCESS so the verdict cannot be contaminated by
# modules the test runner already imported.
#
# No network, no credentials, no live provider, no panel. Synthetic doubles
# only.
#
# Run directly: python test_market_response_dependency_boundary.py

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = ("pytrends", "GST_Live_Signal_Engine", "GST_MultiTicker_Forward_Log")

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


def run_isolated(body: str) -> subprocess.CompletedProcess:
    """Run a snippet in a fresh interpreter rooted at the repo."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(body)],
        cwd=str(HERE), capture_output=True, text=True,
    )


# --- 1. the adapter imports with the legacy runtime forbidden ---------------

def test_adapter_imports_with_forbidden_modules_blocked():
    proc = run_isolated(f"""
        import sys
        FORBIDDEN = {FORBIDDEN!r}
        class Blocker:
            def find_module(self, name, path=None):
                if name.split('.')[0] in FORBIDDEN:
                    raise ImportError('BLOCKED: ' + name)
                return None
        sys.meta_path.insert(0, Blocker())
        import gst_market_response.option_chain_adapter as oca
        assert oca is not None
        print('IMPORT_OK')
    """)
    check(
        "1a. gst_market_response.option_chain_adapter imports while pytrends, "
        "GST_Live_Signal_Engine and GST_MultiTicker_Forward_Log are forbidden",
        proc.returncode == 0 and "IMPORT_OK" in proc.stdout,
    )
    if proc.returncode != 0:
        print("      stderr:", proc.stderr.strip()[-500:])


# --- 2. no forbidden module lands in sys.modules ---------------------------

def test_adapter_import_does_not_populate_sys_modules():
    proc = run_isolated(f"""
        import sys
        import gst_market_response.option_chain_adapter  # noqa: F401
        leaked = [m for m in {FORBIDDEN!r} if m in sys.modules]
        print('LEAKED=' + repr(leaked))
    """)
    check(
        "2a. importing the adapter leaves pytrends / GST_Live_Signal_Engine / "
        "GST_MultiTicker_Forward_Log out of sys.modules",
        "LEAKED=[]" in proc.stdout,
    )
    if "LEAKED=[]" not in proc.stdout:
        print("      stdout:", proc.stdout.strip()[-300:])
        print("      stderr:", proc.stderr.strip()[-300:])

    proc2 = run_isolated("""
        import sys
        import GST_Option_Chain_Core  # noqa: F401
        leaked = [m for m in ('pytrends','GST_Live_Signal_Engine') if m in sys.modules]
        print('CORE_LEAKED=' + repr(leaked))
    """)
    check("2b. importing GST_Option_Chain_Core alone leaks nothing either",
          "CORE_LEAKED=[]" in proc2.stdout)


# --- 3. behaviour is unchanged, via synthetic doubles ----------------------

class _FakeChain:
    def __init__(self, calls, puts):
        self.calls = calls
        self.puts = puts


class _FakeTicker:
    """Stands in for yfinance.Ticker. No network, ever."""

    def __init__(self, expirations, chain=None, options_raises=False, chain_raises=None):
        self._expirations = expirations
        self._chain = chain
        self._options_raises = options_raises
        self._chain_raises = chain_raises

    @property
    def options(self):
        if self._options_raises:
            raise RuntimeError("simulated yfinance failure")
        return self._expirations

    def option_chain(self, expiry):
        if self._chain_raises:
            raise RuntimeError(self._chain_raises)
        return self._chain


def test_expiry_selection_semantics_unchanged():
    import pandas as pd  # noqa: F401  (ensures the core's dep is importable)
    from GST_Option_Chain_Core import get_nearest_post_earnings_expiry as core_expiry
    import gst_market_response.option_chain_adapter as oca

    ed = date(2026, 7, 29)
    tk = _FakeTicker(["2026-07-24", "2026-07-29", "2026-07-31", "2026-08-07"])

    check("3a. nearest expiry is the earliest STRICTLY after earnings_date",
          core_expiry(tk, ed) == "2026-07-31")
    check("3b. an expiry ON the earnings date is excluded (strictly-after rule)",
          "2026-07-29" != core_expiry(tk, ed))
    check("3c. no expiry after the earnings date returns None",
          core_expiry(_FakeTicker(["2026-07-01", "2026-07-29"]), ed) is None)
    check("3d. an empty expiration list returns None",
          core_expiry(_FakeTicker([]), ed) is None)
    check("3e. a raising .options returns None (unchanged fail-quiet behaviour)",
          core_expiry(_FakeTicker(None, options_raises=True), ed) is None)
    check("3f. the adapter's bound helper IS the core function (no duplicate)",
          oca._select_nearest_expiry_after is core_expiry)


def test_atm_snapshot_semantics_unchanged():
    import pandas as pd
    from GST_Option_Chain_Core import get_option_snapshot as core_snapshot
    import gst_market_response.option_chain_adapter as oca

    calls = pd.DataFrame({
        "strike": [95.0, 100.0, 105.0],
        "bid": [6.0, 3.0, 1.0], "ask": [6.4, 3.2, 1.2],
        "bidSize": [10, 20, 30], "askSize": [11, 21, 31],
        "openInterest": [100, 200, 300], "volume": [5, 6, 7],
        "impliedVolatility": [0.51, 0.42, 0.39],
    })
    puts = pd.DataFrame({
        "strike": [95.0, 100.0, 105.0],
        "bid": [1.0, 2.9, 5.9], "ask": [1.2, 3.1, 6.3],
        "bidSize": [1, 2, 3], "askSize": [4, 5, 6],
        "openInterest": [10, 20, 30], "volume": [1, 2, 3],
        "impliedVolatility": [0.40, 0.41, 0.55],
    })
    tk = _FakeTicker([], chain=_FakeChain(calls, puts))

    snap = core_snapshot(tk, "2026-07-31", spot=101.0)
    check("4a. ATM strike is min(abs(strike - spot))", snap["call_strike"] == 100.0)
    check("4b. put ATM strike uses the same rule", snap["put_strike"] == 100.0)
    check("4c. bid/ask extracted unchanged",
          snap["call_bid"] == 3.0 and snap["call_ask"] == 3.2)
    check("4d. bid/ask sizes extracted unchanged as ints",
          snap["call_bid_size"] == 20 and snap["call_ask_size"] == 21)
    check("4e. open interest and volume extracted unchanged",
          snap["call_open_interest"] == 200 and snap["call_volume"] == 6)
    check("4f. implied volatility extracted unchanged",
          snap["call_implied_volatility"] == 0.42)
    check("4g. put leg extracted unchanged",
          snap["put_bid"] == 2.9 and snap["put_ask"] == 3.1 and snap["put_open_interest"] == 20)

    # Exact tie -> pandas idxmin picks the first; behaviour preserved verbatim.
    tie = core_snapshot(_FakeTicker([], chain=_FakeChain(calls, puts)), "x", spot=97.5)
    check("4h. an exact-tie spot resolves the same way as before (first idxmin)",
          tie["call_strike"] == 95.0)

    # Missing values stay None, never 0.
    sparse = pd.DataFrame({
        "strike": [100.0], "bid": [None], "ask": [None], "bidSize": [None],
        "askSize": [None], "openInterest": [None], "volume": [None],
        "impliedVolatility": [None],
    })
    s2 = core_snapshot(_FakeTicker([], chain=_FakeChain(sparse, sparse)), "x", spot=100.0)
    check("4i. missing quote fields stay None -- never coerced to 0",
          all(s2[f"call_{k}"] is None for k in
              ("bid", "ask", "bid_size", "ask_size", "open_interest", "volume",
               "implied_volatility")))

    # Empty leg is skipped entirely.
    empty = pd.DataFrame({"strike": []})
    s3 = core_snapshot(_FakeTicker([], chain=_FakeChain(empty, puts)), "x", spot=100.0)
    check("4j. an empty call frame is skipped, put leg still captured",
          "call_strike" not in s3 and s3["put_strike"] == 100.0)

    # A raising option_chain returns the error dict, unchanged.
    err = core_snapshot(_FakeTicker([], chain_raises="boom"), "x", spot=100.0)
    check("4k. a failed option_chain returns {'option_chain_error': ...} unchanged",
          err == {"option_chain_error": "boom"})

    check("4l. the adapter's bound snapshot helper IS the core function",
          oca._capture_atm_snapshot is core_snapshot)


# --- 5. legacy logger re-exports and defines no duplicate ------------------

def test_legacy_logger_reexports_without_duplicating():
    src = (HERE / "GST_MultiTicker_Forward_Log.py").read_text(encoding="utf-8")
    check("5a. the legacy logger imports both helpers from GST_Option_Chain_Core",
          "from GST_Option_Chain_Core import" in src
          and "get_nearest_post_earnings_expiry" in src
          and "get_option_snapshot" in src)
    check("5b. it defines NO duplicate get_nearest_post_earnings_expiry",
          "def get_nearest_post_earnings_expiry(" not in src)
    check("5c. it defines NO duplicate get_option_snapshot",
          "def get_option_snapshot(" not in src)
    core = (HERE / "GST_Option_Chain_Core.py").read_text(encoding="utf-8")
    check("5d. the core defines both helpers exactly once",
          core.count("def get_nearest_post_earnings_expiry(") == 1
          and core.count("def get_option_snapshot(") == 1)


# --- 6. the core is dependency-light and network-free at import ------------

def _top_level_imports(path: Path) -> set[str]:
    """Real import statements only, via AST -- prose in comments and
    docstrings must never be mistaken for a dependency."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module.split(".")[0])
    return mods


def test_core_is_dependency_light():
    imported = _top_level_imports(HERE / "GST_Option_Chain_Core.py")
    for banned in ("pytrends", "GST_Live_Signal_Engine", "GST_Phase2_DailyPanel",
                   "GST_MultiTicker_Forward_Log", "requests", "urllib3"):
        check(f"6a. the core never imports {banned} (AST-verified)", banned not in imported)
    check(f"6a2. the core's imports are exactly the ones these two functions need "
          f"(found {sorted(imported)})",
          imported <= {"__future__", "datetime", "pandas", "yfinance"})

    proc = run_isolated("""
        import socket
        calls = []
        real = socket.socket
        class Guard(real):
            def connect(self, *a, **k):
                calls.append(a)
                raise AssertionError('network call at import time')
        socket.socket = Guard
        socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError('network call at import time'))
        import GST_Option_Chain_Core  # noqa: F401
        print('NO_NETWORK_AT_IMPORT')
    """)
    check("6b. importing the core performs no network call",
          proc.returncode == 0 and "NO_NETWORK_AT_IMPORT" in proc.stdout)
    if proc.returncode != 0:
        print("      stderr:", proc.stderr.strip()[-400:])


# --- 7. requirements.txt stays sufficient, and pytrends-free ---------------

def test_requirements_remain_sufficient_and_pytrends_free():
    """Parse actual requirement lines -- requirements.txt discusses pytrends in
    a comment explaining it is deliberately out of scope, and that comment must
    not be read as a dependency."""
    raw = (HERE / "requirements.txt").read_text(encoding="utf-8").splitlines()
    reqs = [l.strip() for l in raw if l.strip() and not l.strip().startswith("#")]
    names = [__import__("re").split(r"[=<>!~\[ ]", r, 1)[0].lower() for r in reqs]

    check(f"7a. no requirement line installs pytrends (declared: {names})",
          "pytrends" not in names)
    for pkg in ("pandas", "yfinance"):
        check(f"7b. requirements.txt still declares {pkg} (needed by the core)",
              pkg in names)
    check("7c. no requirement line pulls the legacy GST engine",
          not any("gst" in n for n in names))
    check("7d. every module the core imports is either stdlib or a declared requirement",
          _top_level_imports(HERE / "GST_Option_Chain_Core.py")
          <= ({"__future__", "datetime"} | set(names)))


# --- 8. no production rule changed ----------------------------------------

def test_no_production_rule_changed():
    import gst_market_response.option_chain_adapter as oca
    check("8a. MAX_COMPATIBLE_QUOTE_SKEW_SECONDS is unchanged (120)",
          oca.MAX_COMPATIBLE_QUOTE_SKEW_SECONDS == 120)
    statuses = {
        "OK": "ok", "PARTIAL": "partial", "MISSING": "missing",
        "REJECTED_EXPIRY_NOT_AFTER_EVENT": "rejected_expiry_not_after_event",
        "REJECTED_BID_GT_ASK": "rejected_bid_gt_ask",
        "REJECTED_INCOMPATIBLE_TIMESTAMPS": "rejected_incompatible_timestamps",
    }
    for attr, val in statuses.items():
        check(f"8b. ContractSelectionStatus.{attr} is unchanged",
              getattr(oca.ContractSelectionStatus, attr) == val)


if __name__ == "__main__":
    test_adapter_imports_with_forbidden_modules_blocked()
    test_adapter_import_does_not_populate_sys_modules()
    test_expiry_selection_semantics_unchanged()
    test_atm_snapshot_semantics_unchanged()
    test_legacy_logger_reexports_without_duplicating()
    test_core_is_dependency_light()
    test_requirements_remain_sufficient_and_pytrends_free()
    test_no_production_rule_changed()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL DEPENDENCY BOUNDARY TESTS PASSED")
    sys.exit(0)
