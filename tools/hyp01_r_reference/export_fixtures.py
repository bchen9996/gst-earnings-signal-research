#!/usr/bin/env python3
"""Export the committed synthetic fixtures to a language-neutral interchange file.

NOT PRODUCTION CODE. SYNTHETIC DATA ONLY.

The fixtures are NOT regenerated here and are NOT reimplemented in R. They come
from exactly one place: `make_fixture` in tools/hyp01_inference_feasibility.py,
the generator already committed and validated in PR #17. This module only
serialises what that generator produces.

The interchange file carries only:

    synthetic outcome vector, synthetic design matrix, coefficient names,
    synthetic cluster labels, target coefficient, fixture identifier, and the
    expected refusal status where applicable.

No ticker, company, event, observation, price, return or canonical research
value appears in it, and none can: every value is generated from the fixed
master seed.

Missing values are encoded as JSON `null`, never as a sentinel number, so a
missing outcome cannot silently become a zero on either side of the bridge.
`allow_nan=False` guarantees the file is strict JSON that R can parse.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _deny_network(*_a, **_k):
    raise NetworkBlocked("network access attempted in the offline fixture exporter")


socket.socket.connect = _deny_network
socket.socket.connect_ex = _deny_network
socket.create_connection = _deny_network
socket.getaddrinfo = _deny_network

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "hyp01_inference_feasibility.py"

SCHEMA = "GST_HYP01_R_REFERENCE_FIXTURE_INTERCHANGE_v1"

# The slope on the synthetic regressor. Index 1 in every fixture: column 0 is
# the explicit intercept (a column of ones), column 1 is x. Fixtures F05/F06
# append a third column, which never becomes the target.
TARGET_INDEX = 1
NULL_VALUE = 0.0
CONFIDENCE_LEVEL = 0.95

# %.17g round-trips an IEEE-754 double exactly and is produced identically by
# Python's format() and R's sprintf(), so the two languages can agree on a
# canonical digest without either trusting the other's JSON writer.
FLOAT_FORMAT = "%.17g"
MISSING_TOKEN = "NA"


def load_runner():
    spec = importlib.util.spec_from_file_location("hyp01_feas_runner", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fmt(v: float) -> str:
    """Canonical, language-neutral rendering of one double."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return MISSING_TOKEN
    return FLOAT_FORMAT % v


def canonical_string(fx: dict) -> str:
    """Format-independent canonical form, reproducible byte-for-byte in R.

    Deliberately not the JSON text: JSON number formatting differs between
    writers, and a digest over it would prove only that one writer was used
    twice. This form is rebuilt independently by the R side from the parsed
    values, so a match means the NUMBERS survived the bridge, not the bytes.
    """
    parts = [
        fx["fixture_id"],
        str(fx["n_obs"]),
        str(fx["n_params"]),
        ",".join(fx["coefficient_names"]),
        fx["target_coefficient"],
        ",".join(fx["cluster_labels"]),
        ",".join(_fmt(v) for v in fx["y"]),
        ",".join(_fmt(v) for row in fx["X"] for v in row),
    ]
    return "|".join(parts)


def build_fixture(R, name: str, kw: dict) -> dict:
    fx = R.make_fixture(name, **kw)
    X, y, g = fx["X"], fx["y"], fx["cluster_index"]
    refuse, reason = R.refusal_check(X, y, g)
    n_params = int(X.shape[1])

    names = ["b0_intercept", "b1_x"] + [f"b{i}_aux" for i in range(2, n_params)]
    rec = {
        "fixture_id": name,
        "n_obs": int(X.shape[0]),
        "n_params": n_params,
        "n_clusters": int(len(np.unique(g))),
        "coefficient_names": names,
        "target_coefficient": names[TARGET_INDEX],
        "target_index_0based": TARGET_INDEX,
        "null_value": NULL_VALUE,
        "confidence_level": CONFIDENCE_LEVEL,
        "cluster_labels": [str(s) for s in fx["labels"]],
        # JSON null for missing; never a sentinel number.
        "y": [None if np.isnan(v) else float(v) for v in y],
        "X": [[None if np.isnan(v) else float(v) for v in row] for row in X],
        "expected_refusal": {
            "python_refuses_before_fit": bool(refuse),
            "python_refusal_reason": reason,
        },
    }
    rec["canonical_sha256"] = hashlib.sha256(
        canonical_string(rec).encode("utf-8")).hexdigest()
    return rec


def build(R) -> dict:
    runner_bytes = RUNNER.read_bytes()
    fixtures = [build_fixture(R, name, kw) for name, kw in R.FIXTURE_SPECS]

    ids = [f["fixture_id"] for f in fixtures]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate fixture identifiers in the export")

    doc = {
        "schema": SCHEMA,
        "purpose": ("Language-neutral export of the committed synthetic fixtures so an "
                    "independent R reference can consume exactly the same numbers. "
                    "Synthetic only; no research artifact is read."),
        "source_of_truth": {
            "generator": "tools/hyp01_inference_feasibility.py::make_fixture",
            "runner_sha256": hashlib.sha256(runner_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            "master_seed": R.MASTER_SEED,
            "fixtures_regenerated_in_r": False,
            "note": "R must never rebuild 'equivalent' fixtures; it reads these values.",
        },
        "canonicalization": {
            "float_format": FLOAT_FORMAT,
            "missing_token": MISSING_TOKEN,
            "missing_encoding_in_json": "null",
            "field_order": ["fixture_id", "n_obs", "n_params", "coefficient_names",
                            "target_coefficient", "cluster_labels", "y", "X(row-major)"],
            "separator": "|",
            "list_separator": ",",
            "digest": "SHA-256 of the UTF-8 canonical string",
        },
        "preregistered_tolerances": R.TOLERANCES,
        "target_index_0based": TARGET_INDEX,
        "null_value": NULL_VALUE,
        "confidence_level": CONFIDENCE_LEVEL,
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
    }
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Export synthetic fixtures for the R reference "
                                             "(synthetic only, not production).")
    ap.add_argument("--out", required=True, help="output JSON path (caller-supplied)")
    a = ap.parse_args(argv)

    R = load_runner()
    R.assert_not_canonical(a.out)
    doc = build(R)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys + strict JSON so the bytes are stable across runs.
    text = json.dumps(doc, sort_keys=True, indent=1, allow_nan=False)
    out.write_text(text, encoding="utf-8")

    file_hash = hashlib.sha256(out.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    print(f"wrote {out}")
    print(f"  fixtures      : {doc['fixture_count']}")
    print(f"  file sha256   : {file_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
