#!/usr/bin/env python3
"""Extend the competitor/supplier extractor calibration from 5 tickers to
HYP-04's full 24-ticker LOCKED_24_ANCHORS universe. MAKES REAL SEC REQUESTS.

WHY THIS EXISTS, AND WHY IT IS A NEW SCRIPT RATHER THAN AN EDIT TO
`calibrate_competitor_extractor.py`.

That module's own `CALIBRATION_TICKERS` docstring says its 5 tickers were
"fixed before running, not chosen after seeing which filings 'look good'."
Changing that tuple now -- after already seeing the fix work cleanly on
INTC/JBL/NVDA -- would itself be outcome-adjacent, exactly what that
discipline exists to prevent. This script does not touch that file or its
tuple; it reuses `run_calibration()` and `render_findings_markdown()`
UNCHANGED (same functions, same logic, zero duplication) against a
DIFFERENT, independently-justified ticker set: `LOCKED_24_ANCHORS`, which
was fixed by HYP-04 on 2026-08-17 -- weeks before HYP-05 existed and long
before this extractor was written -- so using it here cannot be outcome-
adjacent to THIS calibration no matter which names are on it.

WHY THIS SET, AND WHY NOW. Two independent reasons converge on the same
action:

  1. HYP-05's own "target anchor/peer universe" decision (one of its four
     `unresolved_analysis_decisions`, 2026-09-12): `peer_selection.py`'s
     `NEVER_CONDITIONS` already assumes candidates are drawn from filings
     naming one of `LOCKED_24_ANCHORS` as the anchor -- that assumption is
     ratified here, explicitly, rather than left implicit. HYP-05 does NOT
     select new anchors; it reuses HYP-04's frozen 24, exactly as it reuses
     HYP-04's target/outcome construction. Its novelty is in who counts as
     a peer, not in which anchors produce the shocks.

  2. HYP05_EXTRACTOR_CALIBRATION_2026-09-12.md's own updated recommendation:
     "not wiring this into extract_for_universe()'s default path on the
     strength of a 5-filing sample -- that bar should be a materially
     larger, still-real-filing measurement..., not five tickers picked to
     include the ones already known to work." All 24 anchors are exactly
     that larger, real-filing, non-cherry-picked measurement.

This script produces RAW findings only, exactly like the 5-ticker run --
context snippets for a human to read and judge, no pass/fail asserted here,
nothing added to any linkage map. Deliberately NOT part of the offline test
suite; sockets are not blocked.

Run directly (needs network):
  python -m hyp04_supply_chain_hedge.calibrate_competitor_extractor_full_anchors --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

from .calibrate_competitor_extractor import (  # noqa: E402
    CONTACT,
    render_findings_markdown,
    run_calibration,
)
from .run_canary_audit import LOCKED_24_ANCHORS  # noqa: E402

ANCHOR_TICKERS: tuple[str, ...] = tuple(sorted(LOCKED_24_ANCHORS))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="persist the findings markdown to Live Signal "
                         "Engine/HYP05_EXTRACTOR_CALIBRATION_FULL24ANCHORS_"
                         "<date>.md")
    ap.add_argument("--json", action="store_true",
                    help="print the raw findings as JSON instead of markdown")
    a = ap.parse_args(argv)

    findings = run_calibration(ANCHOR_TICKERS, contact=CONTACT)
    md = render_findings_markdown(findings)

    if a.json:
        print(json.dumps(findings, indent=2))
    else:
        print(md)

    if a.write:
        out = LSE / f"HYP05_EXTRACTOR_CALIBRATION_FULL24ANCHORS_{findings['calibration_date']}.md"
        if out.is_file():
            print(f"\nREFUSED: {out} already exists. Dated artifacts are "
                  "never overwritten.", file=sys.stderr)
            return 1
        out.write_text(md, encoding="utf-8")
        print(f"\nwrote: {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
