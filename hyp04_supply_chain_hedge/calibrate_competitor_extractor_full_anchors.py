#!/usr/bin/env python3
"""Extend the competitor/supplier extractor calibration from 5 tickers to
LOCKED_24_ANCHORS, a large, real, non-outcome-adjacent ticker universe.
MAKES REAL SEC REQUESTS.

CORRECTION (2026-09-12, same day, caught before any peer was curated
against it): this module's docstring originally called `LOCKED_24_ANCHORS`
"HYP-04's full anchor universe". That is WRONG -- `anchor_universe.py`'s own
`NEVER_CONDITIONS` states plainly that `LOCKED_24_ANCHORS` is "HYP-01
confirmatory infrastructure" that "HYP-04 is exploratory and does not
modify"; HYP-04's REAL anchors (read off `HYP04_ANCHOR_SHOCKS_2026-08-31.
csv`, the artifact that fed the actual completed Phase 3 test) are a
DIFFERENT seven tickers: ADBE, CTSH, INTC, JBL, MCK, NKE, NVDA -- four of
which happen to also sit in `LOCKED_24_ANCHORS`, three of which (JBL, MCK,
NVDA) do not. See `peer_selection.py`'s docstring for the full correction
and HYP-05's actual (corrected) target-anchor-universe decision.

What survives this correction: everything below about `LOCKED_24_ANCHORS`
being a large, real, non-outcome-adjacent CALIBRATION sample is still true
-- it was fixed by a different hypothesis (HYP-01) weeks before HYP-05
existed, so using it to calibrate the extractor is still not outcome-
adjacent to that calibration, no matter which names are on it. What does
NOT survive: the claim that this calibration run also constitutes HYP-05's
real target-anchor-universe curation. It does not. It is extractor
calibration only; real HYP-05 curation is a separate run against the
seven tickers above.

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
was fixed weeks before HYP-05 existed and long before this extractor was
written -- so using it here cannot be outcome-adjacent to THIS calibration
no matter which names are on it.

WHY THIS SET, AND WHY NOW.

  1. It is a large (24-ticker), real, already-frozen (2026-08-17, by a
     different hypothesis entirely) ticker set -- exactly the kind of
     non-outcome-adjacent sample a bigger calibration needs, whether or not
     it turns out to also be HYP-05's own anchor universe (it does not,
     see the correction above).

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
