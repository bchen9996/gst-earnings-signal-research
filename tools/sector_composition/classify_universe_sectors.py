#!/usr/bin/env python3
"""Descriptive sector-composition audit of the proposed 50-ticker universe.

DESCRIPTIVE AUDIT ONLY. It alters no ticker, creates no selection, introduces no
sector quota, activates nothing, and modifies neither the production 24 nor
HYP-01. It reads no GST, price, return, volume, options, earnings-result,
analyst, news or performance data.

Every Fama-French 12 category is derived MECHANICALLY from the official Kenneth
R. French `Siccodes12.txt` intervals applied to the official SEC SIC code. There
are no manual overrides and no name-based inference: a security whose SIC cannot
be established from SEC data is CLASSIFICATION_UNRESOLVED and stays in the
universe unchanged.

All weights are EQUAL TICKER WEIGHTS. Market capitalization, OEF holdings
weights, prices and returns are prohibited inputs and are never read.

    python classify_universe_sectors.py --sources <dir> --out-dir <dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import socket
import sys
from collections import Counter
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _deny(*_a, **_k):
    raise NetworkBlocked("network access attempted during offline classification")


socket.socket.connect = _deny
socket.socket.connect_ex = _deny
socket.create_connection = _deny
socket.getaddrinfo = _deny

ROOT = Path(__file__).resolve().parents[2]
LS = ROOT / "Live Signal Engine"
U = LS / "Universe_Expansion_2026-08-16"

UNRESOLVED = "CLASSIFICATION_UNRESOLVED"
# Category 12 carries no explicit SIC intervals in the official file: it is the
# residual for every SIC not captured by categories 1-11.
RESIDUAL_CODE, RESIDUAL_ABBR, RESIDUAL_NAME = 12, "Other", "Other"


def parse_ff12(path: Path) -> dict:
    """Parse the official Siccodes12 definition file into ordered intervals."""
    cats, cur = [], None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = re.match(r"^\s*(\d{1,2})\s+(\S+)\s+(.*)$", line)
        if m and not re.match(r"^\s*\d{4}-\d{4}\s*$", line.strip()):
            cur = {"code": int(m.group(1)), "abbr": m.group(2), "name": m.group(3).strip(),
                   "intervals": []}
            cats.append(cur)
            continue
        r = re.match(r"^\s*(\d{4})-(\d{4})\s*$", line)
        if r and cur is not None:
            cur["intervals"].append([int(r.group(1)), int(r.group(2))])
    if len(cats) != 12:
        raise SystemExit(f"STOP: expected 12 FF categories, parsed {len(cats)}")
    if cats[-1]["code"] != RESIDUAL_CODE or cats[-1]["intervals"]:
        raise SystemExit("STOP: category 12 must be the residual with no explicit intervals")
    return {"categories": cats,
            "source_file": path.name,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def ff12_for_sic(sic, ff: dict) -> dict:
    """Mechanical SIC -> FF12. No override, no name inference."""
    if sic is None:
        return {"category_code": None, "category_abbr": None, "category_name": None,
                "matched_interval": None, "status": UNRESOLVED}
    s = int(sic)
    for c in ff["categories"][:-1]:
        for lo, hi in c["intervals"]:
            if lo <= s <= hi:
                return {"category_code": c["code"], "category_abbr": c["abbr"],
                        "category_name": c["name"], "matched_interval": f"{lo}-{hi}",
                        "status": "CLASSIFIED"}
    return {"category_code": RESIDUAL_CODE, "category_abbr": RESIDUAL_ABBR,
            "category_name": RESIDUAL_NAME,
            "matched_interval": "residual (no interval in categories 1-11)",
            "status": "CLASSIFIED"}


def metrics(records: list[dict]) -> dict:
    """Equal ticker weights only."""
    classified = [r for r in records if r["classification_status"] == "CLASSIFIED"]
    n = len(classified)
    counts = Counter(r["ff12_category_abbr"] for r in classified)
    shares = {k: v / n for k, v in counts.items()} if n else {}
    hhi = sum(s * s for s in shares.values())
    ent = -sum(s * math.log(s) for s in shares.values() if s > 0)
    return {
        "n_records": len(records),
        "n_classified": n,
        "n_unresolved": len(records) - n,
        "counts": dict(sorted(counts.items())),
        "percentages": {k: round(100 * v, 4) for k, v in sorted(shares.items())},
        "largest_category": max(counts, key=lambda k: (counts[k], k)) if counts else None,
        "largest_category_count": max(counts.values()) if counts else 0,
        "largest_category_share_pct": round(100 * max(shares.values()), 4) if shares else 0.0,
        "categories_represented": len(counts),
        "categories_absent": 12 - len(counts),
        "absent_categories": sorted(
            c["abbr"] for c in FF["categories"] if c["abbr"] not in counts),
        "hhi_equal_ticker_weights": round(hhi, 6),
        "shannon_entropy_nats": round(ent, 6),
        "effective_number_of_categories": round(math.exp(ent), 6),
        "weighting": "equal ticker weights only; no market cap, OEF weight, price or return used",
    }


def build(sources: Path) -> dict:
    global FF
    FF = parse_ff12(sources / "Siccodes12" / "Siccodes12.txt")
    sic_map = json.loads((sources / "sec_sic_by_ticker.json").read_text(encoding="utf-8"))
    prop = json.loads((U / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED.json").read_text(encoding="utf-8"))
    snap = json.loads((U / "GST_OEF_IDENTITY_SNAPSHOT_2026-08-13.json").read_text(encoding="utf-8"))
    alias = prop["frozen_ticker_aliases"]

    def record(ticker: str, status: str, position: int | None) -> dict:
        s = sic_map.get(ticker, {})
        sic = s.get("sic")
        sic = int(sic) if sic not in (None, "") else None
        cat = ff12_for_sic(sic, FF)
        return {
            "universe_position": position,
            "canonical_ticker": ticker,
            "group_status": status,
            "issuer_name": s.get("entity_name") or s.get("sec_title"),
            "cik": s.get("cik"),
            "sec_sic": sic,
            "sec_sic_description": s.get("sic_description"),
            "ff12_category_code": cat["category_code"],
            "ff12_category_abbr": cat["category_abbr"],
            "ff12_category_name": cat["category_name"],
            "matched_sic_interval": cat["matched_interval"],
            "classification_status": cat["status"],
            "provenance_url": s.get("url"),
            "provenance_sha256": s.get("sha256"),
            "trace": (f"{ticker} -> CIK {s.get('cik')} -> SEC SIC {sic} -> "
                      f"interval {cat['matched_interval']} -> FF12 {cat['category_abbr']}"),
        }

    final50 = prop["final_50"]
    legacy = [record(t, "LEGACY_24", i + 1) for i, t in enumerate(final50[:24])]
    adds = [record(t, "PROPOSED_ADDITION_26", i + 25) for i, t in enumerate(final50[24:])]
    all50 = legacy + adds

    seen, oef = set(), []
    for r in snap["rows"]:
        if r["asset_class"] != "Equity":
            continue
        t = r["source_ticker"].strip().upper().replace(".", "-")
        t = alias.get(t, t)
        if t in seen:
            continue
        seen.add(t)
        rec = record(t, "OEF_ELIGIBLE_PROXY_POOL", None)
        rec["oef_source_ticker"] = r["source_ticker"]
        oef.append(rec)

    m50, mleg, madd, moef = metrics(all50), metrics(legacy), metrics(adds), metrics(oef)

    # FINAL_50 vs OEF proxy, percentage points
    cats = sorted({*m50["percentages"], *moef["percentages"]})
    diff = {c: round(m50["percentages"].get(c, 0.0) - moef["percentages"].get(c, 0.0), 4)
            for c in cats}

    # leave-one-out sensitivity on the final 50
    loo_share, loo_hhi = [], []
    for i in range(len(all50)):
        sub = all50[:i] + all50[i + 1:]
        mm = metrics(sub)
        loo_share.append(mm["largest_category_share_pct"])
        loo_hhi.append(mm["hhi_equal_ticker_weights"])

    return {
        "artifact": "Proposed 50-ticker universe - sector composition audit",
        "schema": "GST_UNIVERSE_50_SECTOR_COMPOSITION_v1",
        "status": "DESCRIPTIVE_AUDIT_ONLY_NO_UNIVERSE_CHANGE",
        "banner": ["DESCRIPTIVE AUDIT ONLY", "NO UNIVERSE CHANGE",
                   "PROPOSED 50 REMAIN INACTIVE", "PRODUCTION UNIVERSE REMAINS 24",
                   "NO GST OR MARKET OUTCOME USED", "F5 REMAINS OPEN",
                   "COLLECTION REMAINS BLOCKED", "NO CONCENTRATION THRESHOLD WAS INVENTED"],
        "frozen_rule": {
            "file": "PRE_RETRIEVAL_SECTOR_COMPOSITION_AUDIT_RULE_2026-08-16.md",
            "sha256_lf": "5ce6a0f01ce7dec84bcf755ee655c4b938165859cdb495a6ff9c37c5021b4dab",
            "created_utc": "2026-08-16T07:49:31Z",
            "frozen_before_any_retrieval": True,
            "concentration_threshold_frozen": False,
        },
        "sources": {
            "sec_ticker_cik": {
                "url": "https://www.sec.gov/files/company_tickers.json",
                "retrieved_utc": "2026-08-16T07:49:58Z", "http_status": 200,
                "bytes": 795501,
                "sha256": "2d3f4250a7b5c9c6e7ee4c3187dca1cff75431169857678c4b853cd9563c9b63"},
            "sec_sic_per_issuer": {
                "url_pattern": "https://data.sec.gov/submissions/CIK##########.json",
                "retrieved_utc": "2026-08-16T07:52Z",
                "note": ("identity and SIC classification metadata only; no financial statement or "
                         "earnings value retrieved"),
                "fair_access": "identifying User-Agent, request rate held well under 10/s"},
            "french_ff12_definitions": {
                "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Siccodes12.zip",
                "retrieved_utc": "2026-08-16T07:51:11Z",
                "zip_sha256": "d801141acf039f2e06e6d4d9ba2b3992e9747a1d82fabd53ef21da4a3af79fff",
                "definition_file": "Siccodes12.txt",
                "definition_sha256": FF["source_sha256"]},
            "aggregators_used_as_evidence": False,
        },
        "ff12_definitions": FF["categories"],
        "records": {"legacy_24": legacy, "proposed_additions_26": adds,
                    "proposed_final_50": all50, "oef_eligible_proxy_pool": oef},
        "metrics": {"LEGACY_24": mleg, "PROPOSED_ADDITIONS_26": madd,
                    "PROPOSED_FINAL_50": m50, "OEF_ELIGIBLE_PROXY_POOL": moef},
        "final50_vs_oef_percentage_point_difference": diff,
        "sensitivity": {
            "final_50_all_securities": m50,
            "final_50_excluding_unresolved": metrics(
                [r for r in all50 if r["classification_status"] == "CLASSIFIED"]),
            "leave_one_out_largest_category_share_pct": {
                "min": round(min(loo_share), 4), "max": round(max(loo_share), 4)},
            "leave_one_out_hhi": {"min": round(min(loo_hhi), 6), "max": round(max(loo_hhi), 6)},
            "alternative_universe_generated": False,
            "subset_search_performed": False,
        },
        "weighting": "equal ticker weights only",
        "prohibited_inputs_used": False,
        "universe_altered": False,
        "concentration_threshold_specified": False,
        "accept_reject_conclusion_asserted": False,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Descriptive sector-composition audit (no universe change).")
    ap.add_argument("--sources", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)

    doc = build(Path(a.sources))
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    (out / "GST_UNIVERSE_50_SECTOR_COMPOSITION_AUDIT_v1.0.json").write_text(
        json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    # CSV + JSON classification, generated from the SAME record objects
    cols = ["universe_position", "canonical_ticker", "group_status", "issuer_name", "cik",
            "sec_sic", "sec_sic_description", "ff12_category_code", "ff12_category_abbr",
            "ff12_category_name", "matched_sic_interval", "classification_status",
            "provenance_url", "trace"]
    with (out / "GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1.0.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in doc["records"]["proposed_final_50"]:
            w.writerow(r)
    (out / "GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1.0.json").write_text(
        json.dumps({"schema": "GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1",
                    "columns": cols,
                    "records": doc["records"]["proposed_final_50"]},
                   indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "GST_OEF_PROXY_SECTOR_CLASSIFICATION_v1.0.json").write_text(
        json.dumps({"schema": "GST_OEF_PROXY_SECTOR_CLASSIFICATION_v1",
                    "note": ("identity-only OEF proxy pool; equal ticker weights; no OEF holdings "
                             "weight, market capitalization, price or return was read"),
                    "records": doc["records"]["oef_eligible_proxy_pool"]},
                   indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    m = doc["metrics"]
    print(f"wrote {out}")
    for g in ("LEGACY_24", "PROPOSED_ADDITIONS_26", "PROPOSED_FINAL_50", "OEF_ELIGIBLE_PROXY_POOL"):
        x = m[g]
        print(f"  {g:26s} n={x['n_classified']:3d} unresolved={x['n_unresolved']} "
              f"largest={x['largest_category']}({x['largest_category_share_pct']}%) "
              f"HHI={x['hhi_equal_ticker_weights']} eff_cats={x['effective_number_of_categories']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
