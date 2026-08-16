#!/usr/bin/env python3
"""Project a quarantined iShares OEF holdings file down to security identity only.

NOT PRODUCTION CODE. NOT AN INDEX CONSTITUENT FILE.

The input is the dated official iShares OEF holdings snapshot, used as an
identity-only proxy for the S&P 100 investable universe. It is NOT the index
provider's canonical constituent list, and nothing here may describe it as one.

Exactly three columns survive: Ticker, Name, Asset Class. `Asset Class` is kept
for one purpose only -- distinguishing ordinary equity from cash, derivative and
other non-equity rows. Every numeric holdings field (market value, weight,
notional, quantity, price, FX rate) is dropped and never read into the output.

The raw file stays outside version control. Only this sanitized projection may
enter the repository.

    python sanitize_oef_snapshot.py --raw <quarantined.csv> --out <sanitized.json>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _deny(*_a, **_k):
    raise NetworkBlocked("network access attempted in the offline sanitizer")


socket.socket.connect = _deny
socket.socket.connect_ex = _deny
socket.create_connection = _deny
socket.getaddrinfo = _deny

# The only columns permitted to survive.
IDENTITY_COLUMNS = ("Ticker", "Name", "Asset Class")

# Columns that must never reach the output. Matched case-insensitively against
# the header, so a renamed-but-equivalent column still fails closed below.
PROHIBITED_PATTERNS = (
    r"market\s*value", r"weight", r"notional", r"quantity", r"shares",
    r"price", r"fx\s*rate", r"return", r"performance", r"yield",
    r"cost", r"par\s*value", r"accrual",
)


def sha_lf(b: bytes) -> str:
    return hashlib.sha256(b.replace(b"\r\n", b"\n")).hexdigest()


def parse(raw_text: str) -> dict:
    lines = raw_text.splitlines()

    as_of = None
    for line in lines[:20]:
        m = re.search(r"as of[,\s\"]*([A-Za-z]{3}\s+\d{1,2},\s*\d{4})", line, re.I)
        if m:
            as_of = m.group(1).strip()
            break
    if as_of is None:
        raise SystemExit("STOP: could not locate the source-reported as-of date")

    hdr_idx = None
    for i, line in enumerate(lines[:40]):
        if re.search(r"(?i)\bticker\b", line):
            hdr_idx = i
            break
    if hdr_idx is None:
        raise SystemExit("STOP: could not locate the header row")

    header = next(csv.reader(io.StringIO(lines[hdr_idx])))
    missing = [c for c in IDENTITY_COLUMNS if c not in header]
    if missing:
        raise SystemExit(f"STOP: identity columns absent from the header: {missing}")

    idx = {c: header.index(c) for c in IDENTITY_COLUMNS}
    prohibited_idx = {
        j for j, name in enumerate(header)
        if any(re.search(p, name, re.I) for p in PROHIBITED_PATTERNS)
    }
    if prohibited_idx & set(idx.values()):
        raise SystemExit("STOP: an identity column also matches a prohibited pattern")

    rows = []
    reader = csv.reader(io.StringIO("\n".join(lines[hdr_idx + 1:])))
    for rec in reader:
        if not rec or not any(f.strip() for f in rec):
            continue
        if len(rec) <= max(idx.values()):
            continue
        ticker = rec[idx["Ticker"]].strip()
        name = rec[idx["Name"]].strip()
        asset = rec[idx["Asset Class"]].strip()
        if not ticker and not name:
            continue
        # ONLY these three fields are ever read out of the record.
        rows.append({"source_ticker": ticker, "name": name, "asset_class": asset})

    return {
        "as_of": as_of,
        "header_columns_seen": header,
        "identity_columns_kept": list(IDENTITY_COLUMNS),
        "columns_dropped": [c for c in header if c not in IDENTITY_COLUMNS],
        "row_count": len(rows),
        "rows": rows,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sanitize a quarantined OEF holdings file to identity only.")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-url", default="")
    ap.add_argument("--retrieved-utc", default="")
    a = ap.parse_args(argv)

    raw_bytes = Path(a.raw).read_bytes()
    parsed = parse(raw_bytes.decode("utf-8-sig"))

    doc = {
        "artifact": "Sanitized identity-only OEF holdings snapshot",
        "schema": "GST_OEF_IDENTITY_SNAPSHOT_v1",
        "source_description": ("the dated official iShares OEF holdings snapshot, used as an "
                               "identity-only proxy for the S&P 100 investable universe"),
        "is_sp_dji_constituent_file": False,
        "source_is_index_provider_canonical_list": False,
        "publisher": "BlackRock / iShares (fund issuer)",
        "source_url": a.source_url,
        "retrieved_utc": a.retrieved_utc,
        "source_reported_as_of": parsed["as_of"],
        "raw_sha256_lf": sha_lf(raw_bytes),
        "raw_bytes": len(raw_bytes),
        "raw_kept_outside_version_control": True,
        "identity_columns_kept": parsed["identity_columns_kept"],
        "columns_dropped": parsed["columns_dropped"],
        "prohibited_fields_emitted": False,
        "row_count": parsed["row_count"],
        "rows": parsed["rows"],
    }

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8")

    print(f"wrote {out}")
    print(f"  as-of              : {parsed['as_of']}")
    print(f"  rows               : {parsed['row_count']}")
    print(f"  identity kept      : {parsed['identity_columns_kept']}")
    print(f"  columns dropped    : {len(parsed['columns_dropped'])}")
    print(f"  sanitized sha256   : {sha_lf(text.encode('utf-8'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
