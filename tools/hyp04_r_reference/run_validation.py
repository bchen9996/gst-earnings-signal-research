#!/usr/bin/env python3
"""One deterministic command for HYP-04's D10 independent R-reference validation.

NOT PRODUCTION CODE. SYNTHETIC DATA ONLY.

    python tools/hyp04_r_reference/run_validation.py --out <artifact.json>

It runs the whole bridge in order:

    1. export the committed synthetic fixtures to the interchange file
    2. run the R reference (clubSandwich) over those exact bytes
    3. recompute the Python side (hyp04_supply_chain_hedge.clustered_se) and
       compare under tolerances reused from HYP-01's PR #17/#18
    4. write the machine-readable validation artifact
    5. exit NONZERO if any fixture is UNRESOLVED

Exit code 1 means an unexplained mismatch. Fixtures that both implementations
refuse, and documented behaviour differences, are explained outcomes and do not
fail the run -- they are reported.

The validation itself is offline. Installing R and its packages is a separate,
prior step (see r-packages.lock.json); nothing here downloads anything.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPORT = HERE / "export_fixtures.py"
COMPARE = HERE / "compare_reference.py"
R_SCRIPT = HERE / "cr2_reference.R"
LOCK = HERE / "r-packages.lock.json"

# Where a per-user R install lands on each platform. Checked in order; the
# first hit wins. RSCRIPT in the environment overrides all of them. Same
# candidate paths as tools/hyp01_r_reference/run_validation.py -- both
# bridges share one R install.
CANDIDATE_RSCRIPT = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "R" / "R-4.6.1" / "bin" / "x64" / "Rscript.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "R" / "R-4.6.1" / "bin" / "Rscript.exe",
    Path("C:/Program Files/R/R-4.6.1/bin/x64/Rscript.exe"),
]


def find_rscript() -> str | None:
    env = os.environ.get("RSCRIPT")
    if env and Path(env).exists():
        return env
    which = shutil.which("Rscript")
    if which:
        return which
    for c in CANDIDATE_RSCRIPT:
        if str(c) and c.exists():
            return str(c)
    return None


def run(cmd: list[str], label: str) -> None:
    print(f"--- {label}")
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    for line in (r.stdout or "").splitlines():
        print(f"    {line}")
    if r.returncode != 0:
        for line in (r.stderr or "").splitlines()[-25:]:
            print(f"    ! {line}")
        raise SystemExit(f"{label} failed with exit code {r.returncode}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run HYP-04's D10 R-reference validation end to end.")
    ap.add_argument("--out", required=True, help="output validation artifact path")
    ap.add_argument("--keep-intermediates", metavar="DIR",
                    help="also write the fixture and raw reference files here")
    a = ap.parse_args(argv)

    rscript = find_rscript()
    if rscript is None:
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        print("Rscript not found.")
        print(f"  This validation requires R {lock['r']['version']} with "
              f"clubSandwich {[p['version'] for p in lock['packages'] if p['package'] == 'clubSandwich'][0]}.")
        print("  Install per r-packages.lock.json, or set RSCRIPT to the interpreter path.")
        print("  Nothing was validated.")
        return 2
    print(f"using Rscript: {rscript}")

    tmp = Path(tempfile.mkdtemp(prefix="hyp04_r_ref_"))
    try:
        fixtures = tmp / "fixtures.json"
        reference = tmp / "r_reference.json"

        run([sys.executable, str(EXPORT), "--out", str(fixtures)], "1/3 export synthetic fixtures")
        run([rscript, str(R_SCRIPT), "--fixtures", str(fixtures), "--out", str(reference)],
            "2/3 R reference (clubSandwich)")

        print("--- 3/3 compare under tolerances reused from HYP-01's PR #17/#18")
        r = subprocess.run([sys.executable, str(COMPARE), "--fixtures", str(fixtures),
                            "--reference", str(reference), "--out", a.out],
                           capture_output=True, text=True, errors="replace")
        for line in (r.stdout or "").splitlines():
            print(f"    {line}")
        for line in (r.stderr or "").splitlines()[-25:]:
            print(f"    ! {line}")

        if a.keep_intermediates:
            keep = Path(a.keep_intermediates)
            keep.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixtures, keep / "fixtures.json")
            shutil.copy2(reference, keep / "r_reference.json")
            print(f"    intermediates kept in {keep}")

        if r.returncode != 0:
            print("\nUNEXPLAINED MISMATCH -- exiting nonzero.")
            return 1

        doc = json.loads(Path(a.out).read_text(encoding="utf-8"))
        counts = doc["classification_counts"]
        print("\nvalidation complete:")
        for k, v in counts.items():
            if v:
                print(f"  {k}: {v}")
        print(f"  d10_satisfied: {doc['d10_satisfied']}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
