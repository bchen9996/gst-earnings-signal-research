#!/usr/bin/env python3
"""Descriptive sector-composition audit of the proposed 50-ticker universe.

DESCRIPTIVE AUDIT ONLY. It alters no ticker, creates no selection, introduces no
sector quota, activates nothing, and modifies neither the production 24 nor
HYP-01. It reads no GST, price, return, volume, options, earnings-result,
analyst, news or performance data.

Every Fama-French 12 category is derived MECHANICALLY from the official Kenneth
R. French SIC intervals applied to the official SEC SIC code. There are no manual
overrides and no name-based inference: a security whose SIC cannot be established
from SEC data is CLASSIFICATION_UNRESOLVED and stays in the universe unchanged.

DENOMINATOR. The proxy pool is counted at the level of the ECONOMIC ISSUER, keyed
by official SEC CIK, because the frozen pre-retrieval rule defines it as every
eligible equity *issuer*. Multiple share classes of one issuer (e.g. GOOG and
GOOGL, one CIK) collapse to ONE equal-weight observation; every constituent
security is preserved in `source_securities`. The final 50 contains no duplicate
issuer, so both sides of the comparison are issuer-level.

All weights are EQUAL TICKER WEIGHTS. Market capitalization, OEF holdings
weights, prices and returns are prohibited inputs and are never read.

Reproduction (no network, no external scratch directory needed - every input is
committed in the repository):

    python tools/sector_composition/classify_universe_sectors.py

Add --out-dir to write elsewhere; --sources to point at a different committed
source directory. Any missing input, or any input whose SHA-256 does not match
the committed provenance manifest, is a REFUSAL: the run stops and writes nothing.
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
from collections import Counter, defaultdict
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
AUDIT_DIR = LS / "Universe_Sector_Audit_2026-08-16"
DEFAULT_SOURCES = AUDIT_DIR / "sources"

IDENTITY_FILE = "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json"
FF12_FILE = "FF12_SIC_DEFINITION_SOURCE_2026-08-16.txt"
PROVENANCE_FILE = "GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json"

UNRESOLVED = "CLASSIFICATION_UNRESOLVED"
# Category 12 carries no explicit SIC intervals in the official file: it is the
# residual for every SIC not captured by categories 1-11.
RESIDUAL_CODE, RESIDUAL_ABBR, RESIDUAL_NAME = 12, "Other", "Other"

# The operative label for the proxy denominator. The frozen pre-retrieval rule is
# UNCHANGED and still names the group OEF_ELIGIBLE_PROXY_POOL; this name states the
# denominator the rule always specified - eligible equity ISSUERS, not securities.
OEF_GROUP = "OEF_UNIQUE_ISSUER_PROXY_POOL"
RULE_GROUP_NAME = "OEF_ELIGIBLE_PROXY_POOL"


def refuse(msg: str) -> "NoReturn":  # noqa: F821
    raise SystemExit(f"REFUSAL: {msg}")


def sha_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


SOURCES_MARKER = "Universe_Sector_Audit_2026-08-16/sources/"


def resolve_input(sources: Path, item: dict) -> Path:
    """Resolve a manifest entry to the file that will ACTUALLY be read.

    Inputs living in the audit's own sources directory resolve inside `sources`, so
    that pointing --sources at a different directory verifies THAT directory rather
    than the pristine repository copy. Anything else resolves against the repo root.
    """
    if item["repo_path"].replace("\\", "/").find(SOURCES_MARKER) >= 0:
        return sources / item["filename"]
    return ROOT / item["repo_path"]


def verify_sources(sources: Path) -> dict:
    """Fail closed: every declared input must be present and hash-exact."""
    prov_path = sources / PROVENANCE_FILE
    if not prov_path.is_file():
        refuse(f"missing provenance manifest {prov_path}")
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    for item in prov["inputs"]:
        p = resolve_input(sources, item)
        if not p.is_file():
            refuse(f"declared input is missing: {item['filename']} (expected at {p})")
        got = sha_lf(p)
        if got != item["sha256_lf"]:
            refuse(f"input hash mismatch for {item['filename']}: "
                   f"manifest {item['sha256_lf']} != actual {got}")
    for required in (IDENTITY_FILE, FF12_FILE):
        if not any(i["filename"] == required for i in prov["inputs"]):
            refuse(f"provenance manifest does not declare required input {required}")
    return prov


def parse_ff12(path: Path) -> dict:
    """Parse the official FF12 SIC definition bytes into ordered intervals."""
    if not path.is_file():
        refuse(f"missing FF12 definition source {path}")
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
        refuse(f"expected 12 FF categories, parsed {len(cats)}")
    if cats[-1]["code"] != RESIDUAL_CODE or cats[-1]["intervals"]:
        refuse("category 12 must be the residual with no explicit intervals")
    return {"categories": cats, "source_file": path.name, "source_sha256_lf": sha_lf(path)}


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


def metrics(records: list[dict], ff: dict) -> dict:
    """Equal ticker weights only. One observation per record."""
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
        "absent_categories": sorted(c["abbr"] for c in ff["categories"] if c["abbr"] not in counts),
        "hhi_equal_ticker_weights": round(hhi, 6),
        "shannon_entropy_nats": round(ent, 6),
        "effective_number_of_categories": round(math.exp(ent), 6),
        "weighting": "equal ticker weights only; no market cap, OEF weight, price or return used",
    }


def build(sources: Path) -> dict:
    prov = verify_sources(sources)
    ff = parse_ff12(sources / FF12_FILE)

    identity = json.loads((sources / IDENTITY_FILE).read_text(encoding="utf-8"))
    for flag in ("contains_financial_statement_data", "contains_earnings_values",
                 "contains_market_data", "contains_market_capitalization",
                 "contains_prices_returns_or_volumes"):
        if identity.get(flag) is not False:
            refuse(f"identity snapshot declares {flag} is not False")
    by_ticker = {s["canonical_ticker"]: s for s in identity["securities"]}

    prop = json.loads((U / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED.json").read_text(encoding="utf-8"))
    snap = json.loads((U / "GST_OEF_IDENTITY_SNAPSHOT_2026-08-13.json").read_text(encoding="utf-8"))
    alias = prop["frozen_ticker_aliases"]

    def classify(ticker: str) -> dict:
        s = by_ticker.get(ticker, {})
        sic = s.get("sec_sic")
        sic = int(sic) if sic not in (None, "") else None
        return s, sic, ff12_for_sic(sic, ff)

    def record(ticker: str, status: str, position: int | None) -> dict:
        s, sic, cat = classify(ticker)
        return {
            "universe_position": position,
            "canonical_ticker": ticker,
            "group_status": status,
            "issuer_name": s.get("sec_entity_name"),
            "cik": s.get("cik"),
            "sec_sic": sic,
            "sec_sic_description": s.get("sec_sic_description"),
            "ff12_category_code": cat["category_code"],
            "ff12_category_abbr": cat["category_abbr"],
            "ff12_category_name": cat["category_name"],
            "matched_sic_interval": cat["matched_interval"],
            "classification_status": cat["status"],
            "provenance_url": s.get("sec_url"),
            "provenance_sha256": s.get("raw_response_sha256"),
            "trace": (f"{ticker} -> CIK {s.get('cik')} -> SEC SIC {sic} -> "
                      f"interval {cat['matched_interval']} -> FF12 {cat['category_abbr']}"),
        }

    # ---------------- the proposed 50, at security level (one share class each) ----------------
    final50 = prop["final_50"]
    legacy = [record(t, "LEGACY_24", i + 1) for i, t in enumerate(final50[:24])]
    adds = [record(t, "PROPOSED_ADDITION_26", i + 25) for i, t in enumerate(final50[24:])]
    all50 = legacy + adds

    # The final 50 must itself be one-security-per-issuer, verified rather than assumed.
    f50_by_cik = defaultdict(list)
    for r in all50:
        if r["cik"] is None:
            refuse(f"final-50 member {r['canonical_ticker']} has no SEC CIK")
        f50_by_cik[r["cik"]].append(r["canonical_ticker"])
    dupes = {c: t for c, t in f50_by_cik.items() if len(t) > 1}
    if dupes:
        refuse(f"the final 50 contains duplicate issuers (CIK -> tickers): {dupes}")
    if len(f50_by_cik) != len(all50):
        refuse(f"final-50 unique CIK count {len(f50_by_cik)} != record count {len(all50)}")

    # ---------------- the OEF proxy pool, at ECONOMIC ISSUER level ----------------
    groups: dict[int, dict] = {}
    for row in snap["rows"]:
        if row["asset_class"] != "Equity":
            continue
        raw = row["source_ticker"].strip().upper()
        t = alias.get(raw.replace(".", "-"), raw.replace(".", "-"))   # BRKB -> BRK-B before matching
        s, sic, cat = classify(t)
        cik = s.get("cik")
        if cik is None:
            refuse(f"OEF equity row {row['source_ticker']!r} (canonical {t}) has no SEC CIK; "
                   f"issuer-level grouping cannot proceed")
        g = groups.setdefault(cik, {"cik": cik, "canonical_tickers": set(),
                                    "source_securities": set(), "sics": set(),
                                    "ff12": set(), "sample": None})
        g["canonical_tickers"].add(t)
        g["source_securities"].add(row["source_ticker"])
        g["sics"].add(sic)
        g["ff12"].add(cat["category_abbr"])
        g["sample"] = (s, sic, cat)

    oef = []
    for cik in sorted(groups):
        g = groups[cik]
        # Every security under one CIK must agree, or the run stops.
        if len(g["sics"]) != 1:
            refuse(f"CIK {cik} has conflicting SEC SIC values across its share classes: "
                   f"{sorted(g['sics'])} for {sorted(g['canonical_tickers'])}")
        if len(g["ff12"]) != 1:
            refuse(f"CIK {cik} has conflicting FF12 classifications across its share classes: "
                   f"{sorted(g['ff12'])} for {sorted(g['canonical_tickers'])}")
        s, sic, cat = g["sample"]
        # Display ticker: lexicographically smallest canonical ticker. Identification
        # only - it enters no count, share, HHI, entropy or difference.
        display = sorted(g["canonical_tickers"])[0]
        oef.append({
            "universe_position": None,
            "display_ticker": display,
            "canonical_ticker": display,
            "display_ticker_rule": "lexicographically smallest canonical ticker; identification only",
            "display_ticker_affects_metrics": False,
            "group_status": OEF_GROUP,
            "issuer_name": s.get("sec_entity_name"),
            "cik": cik,
            "source_securities": sorted(g["source_securities"]),
            "canonical_securities": sorted(g["canonical_tickers"]),
            "n_source_securities": len(g["source_securities"]),
            "sec_sic": sic,
            "sec_sic_description": s.get("sec_sic_description"),
            "ff12_category_code": cat["category_code"],
            "ff12_category_abbr": cat["category_abbr"],
            "ff12_category_name": cat["category_name"],
            "matched_sic_interval": cat["matched_interval"],
            "classification_status": cat["status"],
            "provenance_url": s.get("sec_url"),
            "provenance_sha256": s.get("raw_response_sha256"),
            "trace": (f"CIK {cik} {sorted(g['canonical_tickers'])} -> SEC SIC {sic} -> "
                      f"interval {cat['matched_interval']} -> FF12 {cat['category_abbr']}"),
        })

    n_oef_source_securities = sum(r["n_source_securities"] for r in oef)
    multi = [{"cik": r["cik"], "issuer_name": r["issuer_name"],
              "source_securities": r["source_securities"],
              "canonical_securities": r["canonical_securities"]}
             for r in oef if r["n_source_securities"] > 1]

    m50 = metrics(all50, ff)
    mleg = metrics(legacy, ff)
    madd = metrics(adds, ff)
    moef = metrics(oef, ff)

    cats = sorted({*m50["percentages"], *moef["percentages"]})
    diff = {c: round(m50["percentages"].get(c, 0.0) - moef["percentages"].get(c, 0.0), 4)
            for c in cats}
    max_abs_diff = max((abs(v) for v in diff.values()), default=0.0)

    loo_share, loo_hhi = [], []
    for i in range(len(all50)):
        mm = metrics(all50[:i] + all50[i + 1:], ff)
        loo_share.append(mm["largest_category_share_pct"])
        loo_hhi.append(mm["hhi_equal_ticker_weights"])

    union_tickers = {r["canonical_ticker"] for r in all50} | {
        t for r in oef for t in r["canonical_securities"]}
    union_ciks = {r["cik"] for r in all50} | {r["cik"] for r in oef}

    return {
        "artifact": "Proposed 50-ticker universe - sector composition audit",
        "schema": "GST_UNIVERSE_50_SECTOR_COMPOSITION_v2",
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
            "unchanged_by_this_correction": True,
        },
        "denominators": {
            "note": ("Stated explicitly so no figure is reported against an undefined "
                     "denominator."),
            "proposed_final_50_securities": len(all50),
            "proposed_final_50_unique_ciks": len(f50_by_cik),
            "oef_source_equity_securities": n_oef_source_securities,
            "oef_unique_issuers": len(oef),
            "oef_issuers_with_multiple_share_classes": multi,
            "union_unique_canonical_securities": len(union_tickers),
            "union_unique_ciks": len(union_ciks),
            "classification_requests": len(all50) + len(oef),
            "definitions": {
                "security": "one canonical ticker (one share class)",
                "issuer": "one official SEC CIK; all its share classes collapse to one "
                          "equal-weight observation",
                "classification_requests": "final-50 records plus OEF issuer records; the "
                                           "overlap between the two groups is counted in both",
            },
        },
        "issuer_level_grouping": {
            "denominator_level": "ECONOMIC_ISSUER",
            "issuer_key": "official SEC CIK",
            "alias_applied_before_identity_matching": alias,
            "share_classes_collapsed": True,
            "display_ticker_rule": "lexicographically smallest canonical ticker",
            "display_ticker_affects_metrics": False,
            "conflicting_sic_within_cik_refused": True,
            "conflicting_ff12_within_cik_refused": True,
            "rule_group_name": RULE_GROUP_NAME,
            "operative_group_name": OEF_GROUP,
            "rename_note": ("The frozen pre-retrieval rule is unchanged and names this group "
                            f"{RULE_GROUP_NAME}, defining it as every eligible equity ISSUER. "
                            f"{OEF_GROUP} is the operative label stating that denominator "
                            "explicitly; it is a naming correction, not a rule change."),
        },
        "sources": {
            "all_inputs_committed": True,
            "network_required_for_reproduction": False,
            "provenance_manifest": PROVENANCE_FILE,
            "verified_inputs": [{"repo_path": i["repo_path"], "sha256_lf": i["sha256_lf"],
                                 "bytes": i["bytes"], "url": i["url"],
                                 "retrieved_utc": i["retrieved_utc"]} for i in prov["inputs"]],
            "sec_ticker_cik": identity["ticker_to_cik_source"],
            "sec_sic_per_issuer": identity["sic_source"],
            "french_ff12_definitions": {
                "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Siccodes12.zip",
                "retrieved_utc": "2026-08-16T07:51:11Z",
                "zip_sha256": "d801141acf039f2e06e6d4d9ba2b3992e9747a1d82fabd53ef21da4a3af79fff",
                "definition_file": FF12_FILE,
                "definition_sha256_lf": ff["source_sha256_lf"]},
            "aggregators_used_as_evidence": False,
        },
        "ff12_definitions": ff["categories"],
        "records": {"legacy_24": legacy, "proposed_additions_26": adds,
                    "proposed_final_50": all50, "oef_unique_issuer_proxy_pool": oef},
        "metrics": {"LEGACY_24": mleg, "PROPOSED_ADDITIONS_26": madd,
                    "PROPOSED_FINAL_50": m50, OEF_GROUP: moef},
        "final50_vs_oef_percentage_point_difference": diff,
        "final50_vs_oef_max_abs_percentage_point_difference": round(max_abs_diff, 4),
        "sensitivity": {
            "final_50_all_securities": m50,
            "final_50_excluding_unresolved": metrics(
                [r for r in all50 if r["classification_status"] == "CLASSIFIED"], ff),
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
    ap = argparse.ArgumentParser(
        description="Descriptive sector-composition audit (no universe change).")
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES),
                    help="committed source directory (default: the audit's own sources/)")
    ap.add_argument("--out-dir", default=str(AUDIT_DIR),
                    help="output directory (default: the audit directory)")
    a = ap.parse_args(argv)

    doc = build(Path(a.sources))
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def dump(name: str, payload) -> None:
        (out / name).write_text(
            json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n")

    dump("GST_UNIVERSE_50_SECTOR_COMPOSITION_AUDIT_v1.0.json", doc)

    cols = ["universe_position", "canonical_ticker", "group_status", "issuer_name", "cik",
            "sec_sic", "sec_sic_description", "ff12_category_code", "ff12_category_abbr",
            "ff12_category_name", "matched_sic_interval", "classification_status",
            "provenance_url", "trace"]
    with (out / "GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1.0.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in doc["records"]["proposed_final_50"]:
            w.writerow(r)
    dump("GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1.0.json",
         {"schema": "GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1", "columns": cols,
          "records": doc["records"]["proposed_final_50"]})
    dump("GST_OEF_PROXY_SECTOR_CLASSIFICATION_v1.0.json",
         {"schema": "GST_OEF_UNIQUE_ISSUER_SECTOR_CLASSIFICATION_v2",
          "denominator_level": "ECONOMIC_ISSUER",
          "issuer_key": "official SEC CIK",
          "note": ("identity-only OEF proxy pool counted once per economic issuer; equal "
                   "ticker weights; no OEF holdings weight, market capitalization, price or "
                   "return was read"),
          "denominators": doc["denominators"],
          "records": doc["records"]["oef_unique_issuer_proxy_pool"]})

    m, d = doc["metrics"], doc["denominators"]
    print(f"wrote {out}")
    print(f"  OEF: {d['oef_source_equity_securities']} source securities -> "
          f"{d['oef_unique_issuers']} unique issuers "
          f"({len(d['oef_issuers_with_multiple_share_classes'])} multi-class issuer(s))")
    print(f"  final 50: {d['proposed_final_50_securities']} securities, "
          f"{d['proposed_final_50_unique_ciks']} unique CIKs")
    for g in ("LEGACY_24", "PROPOSED_ADDITIONS_26", "PROPOSED_FINAL_50", OEF_GROUP):
        x = m[g]
        print(f"  {g:32s} n={x['n_classified']:3d} unresolved={x['n_unresolved']} "
              f"largest={x['largest_category']}({x['largest_category_share_pct']}%) "
              f"HHI={x['hhi_equal_ticker_weights']} eff_cats={x['effective_number_of_categories']}")
    print(f"  max |FINAL_50 - OEF| = "
          f"{doc['final50_vs_oef_max_abs_percentage_point_difference']} pp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
