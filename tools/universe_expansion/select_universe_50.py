#!/usr/bin/env python3
"""Deterministic outcome-blind expansion of the prospective universe from 24 to 50.

NOT PRODUCTION CODE. PROPOSAL ONLY. It does not modify the production universe
constant, the panel, any active protocol, the effective lock, the registry, or
any research state.

Input is the sanitized identity-only projection of the dated official iShares OEF
holdings snapshot, used as an identity-only proxy for the S&P 100 investable
universe. That file is NOT the index provider's canonical constituent list.

The selection rule was frozen and hashed BEFORE the candidate names were
retrieved. This module implements it and nothing else:

  R4  normalize: uppercase, trim, provider share-class separator -> repository
      convention ('.' -> '-'), class identifiers preserved
  R5  deduplicate by economic issuer; an issuer already represented in the
      locked 24 contributes no further share classes; otherwise keep the
      lexicographically smallest canonical ticker
  R6  exclude only: duplicate issuer, non-operating-company-common-equity,
      malformed identifier, membership not establishable from the snapshot
  R8  score = SHA256(UTF8("GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|" + ticker))
  R9  lowercase hexadecimal
  R10 sort ascending by (digest, canonical_ticker)
  R11 take the first 26
  R12 final = locked 24 in existing order + selected 26 in hash order
  R13 exactly 50 unique tickers
  R14 no backfill, ever

No price, weight, market value, quantity, attention, earnings, outcome or
performance value is read: the sanitized input does not contain any.

    python select_universe_50.py --snapshot <sanitized.json> --out-dir <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _deny(*_a, **_k):
    raise NetworkBlocked("network access attempted during selection")


socket.socket.connect = _deny
socket.socket.connect_ex = _deny
socket.create_connection = _deny
socket.getaddrinfo = _deny

HASH_PREFIX = "GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|"

# Frozen ticker-alias map (PRE_SELECTION_ALIAS_AMENDMENT_2026-08-16.md,
# sha256 5faabac1e5a6b77a8dc3cbb894c667948cbcbb8824e2f159e81b29ca2b30ffc6).
#
# Identity reconciliation only: the OEF snapshot writes Berkshire Hathaway Inc.
# Class B as "BRKB" with no separator, while the repository writes "BRK-B".
# Frozen R4 converts a provider separator; it cannot INSERT one, and R5 cannot
# match by issuer because the locked 24 carries no issuer names. This map is
# applied BEFORE locked-24 comparison, issuer deduplication, hashing and
# uniqueness counting, so one security is one identity everywhere.
#
# This map is EXACTLY this pair. No other alias may be inferred or added; any
# further unresolved identifier mismatch is a stop condition, not an excuse to
# extend it.
FROZEN_TICKER_ALIASES: dict[str, str] = {"BRKB": "BRK-B"}
TARGET_ADDITIONS = 26
TARGET_TOTAL = 50

LOCKED_24 = ("AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "CTSH", "DELL", "DVN", "GME",
             "GOOGL", "GPN", "INTC", "LDOS", "MSFT", "NCLH", "NKE", "QCOM", "SBUX", "STZ",
             "SYK", "TSLA", "TTWO", "UAL")

# Asset-class values that are not operating-company common equity (R6.2).
NON_EQUITY_ASSET_CLASSES = {"cash", "cash collateral and margins", "futures",
                            "money market", "fx", "forward", "swap", "bond"}

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z])?$")

# Fields that must never appear in the input. Selection reads identity only.
FORBIDDEN_INPUT_FIELDS = ("market_value", "weight", "notional", "quantity", "shares",
                          "price", "fx_rate", "return", "performance", "yield",
                          "market cap", "index weight")


def normalize_ticker(raw: str) -> tuple[str, bool]:
    """R4 plus the frozen alias map. Returns (canonical_ticker, alias_applied)."""
    t = raw.strip().upper()
    # provider share-class separator -> repository convention (BRK.B -> BRK-B).
    # The class letter is preserved; it is economically meaningful.
    t = t.replace(".", "-").replace(" ", "-")
    t = re.sub(r"-+", "-", t).strip("-")
    if t in FROZEN_TICKER_ALIASES:
        return FROZEN_TICKER_ALIASES[t], True
    return t, False


def issuer_key(name: str) -> str:
    """R5. Economic-issuer identity from the snapshot's own company-name field.

    Case and punctuation are normalized. A trailing share-class designator is
    then removed, because that suffix IS the marker distinguishing two classes
    of one issuer -- without removing it, R5 could never group them and the rule
    would be inoperative. This is applied ONLY to build the grouping key and
    NEVER to the ticker. It is deterministic and reads no outcome.
    """
    s = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+(CLASS|CL|SER|SERIES)\s+[A-Z]$", "", s)
    return s.strip()


def digest_for(ticker: str) -> tuple[str, str]:
    payload = HASH_PREFIX + ticker
    return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build(snapshot: dict) -> dict:
    rows = snapshot["rows"]
    if not rows:
        raise SystemExit("STOP: sanitized snapshot contains no rows")

    # Selection may read exactly three identity fields per row. The check is on
    # ROW KEYS, not on the document text: the snapshot legitimately records the
    # NAMES of the columns it dropped ("Quantity", "Weight (%)", ...) as evidence
    # of what was excluded, and scanning raw text would flag that documentation.
    for i, r in enumerate(rows):
        extra = set(r) - {"source_ticker", "name", "asset_class"}
        if extra:
            raise SystemExit(f"STOP: row {i} carries non-identity fields: {sorted(extra)}")
        for f in FORBIDDEN_INPUT_FIELDS:
            if any(f in str(k).lower() for k in r):
                raise SystemExit(f"STOP: prohibited field {f!r} present in row {i}")
    # No row value may be a bare number: identity fields are symbols and names.
    for i, r in enumerate(rows):
        for k, v in r.items():
            if isinstance(v, (int, float)):
                raise SystemExit(f"STOP: numeric value in identity field {k!r} of row {i}")

    locked_set = set(LOCKED_24)
    ledger = []

    # ---- pass 1: normalize and classify every source row -------------------
    for r in rows:
        src = r["source_ticker"]
        name = r["name"]
        asset = r["asset_class"]
        rec = {
            "source_ticker": src,
            "name": name,
            "asset_class": asset,
            "canonical_ticker": None,
            "alias_applied": False,
            "issuer_key": issuer_key(name),
            "status": None,
            "exclusion_rule": None,
            "hash_input": None,
            "digest": None,
            "rank": None,
            "selected": False,
        }
        if asset.strip().lower() in NON_EQUITY_ASSET_CLASSES:
            rec["status"] = "EXCLUDED"
            rec["exclusion_rule"] = "R6.2 not operating-company common equity"
            ledger.append(rec)
            continue
        canon, aliased = normalize_ticker(src)
        rec["canonical_ticker"] = canon
        rec["alias_applied"] = aliased
        if not canon or not TICKER_RE.match(canon):
            rec["status"] = "EXCLUDED"
            rec["exclusion_rule"] = "R6.3 malformed or unresolvable ticker identifier"
            ledger.append(rec)
            continue
        rec["status"] = "PENDING"
        ledger.append(rec)

    # ---- pass 2: economic-issuer deduplication (R5) ------------------------
    by_issuer: dict[str, list[dict]] = {}
    for rec in ledger:
        if rec["status"] == "PENDING":
            by_issuer.setdefault(rec["issuer_key"], []).append(rec)

    duplicate_decisions = []
    for key, group in sorted(by_issuer.items()):
        locked_here = sorted(g["canonical_ticker"] for g in group
                             if g["canonical_ticker"] in locked_set)
        if len(group) == 1 and not locked_here:
            continue
        if locked_here:
            # R5.1 issuer already represented in the locked 24
            for g in group:
                if g["canonical_ticker"] not in locked_set:
                    g["status"] = "EXCLUDED"
                    g["exclusion_rule"] = (
                        f"R5.1 issuer already represented in the locked 24 by "
                        f"{locked_here[0]}")
            if len(group) > 1:
                duplicate_decisions.append({
                    "issuer_key": key,
                    "classes_present": sorted(g["canonical_ticker"] for g in group),
                    "rule": "R5.1",
                    "kept": locked_here[0],
                    "excluded": sorted(g["canonical_ticker"] for g in group
                                       if g["canonical_ticker"] not in locked_set),
                    "rationale": ("the issuer already has a share class among the locked 24, "
                                  "so its other classes are excluded from the candidate pool"),
                })
        elif len(group) > 1:
            # R5.2 keep the lexicographically smallest canonical ticker
            keep = min(g["canonical_ticker"] for g in group)
            for g in group:
                if g["canonical_ticker"] != keep:
                    g["status"] = "EXCLUDED"
                    g["exclusion_rule"] = f"R5.2 duplicate economic issuer; kept {keep}"
            duplicate_decisions.append({
                "issuer_key": key,
                "classes_present": sorted(g["canonical_ticker"] for g in group),
                "rule": "R5.2",
                "kept": keep,
                "excluded": sorted(g["canonical_ticker"] for g in group
                                   if g["canonical_ticker"] != keep),
                "rationale": "lexicographically smallest canonical ticker, outcome-blind",
            })

    # ---- pass 3: remove the locked 24, then score and rank -----------------
    for rec in ledger:
        if rec["status"] != "PENDING":
            continue
        if rec["canonical_ticker"] in locked_set:
            # An aliased identifier that resolves onto a locked ticker is the same
            # security, so it is never hashed as a new candidate.
            rec["status"] = ("ALREADY_LOCKED_AFTER_ALIAS_NORMALIZATION"
                             if rec["alias_applied"] else "ALREADY_LOCKED")
            continue
        rec["status"] = "ELIGIBLE_CANDIDATE"
        rec["hash_input"], rec["digest"] = digest_for(rec["canonical_ticker"])

    candidates = [r for r in ledger if r["status"] == "ELIGIBLE_CANDIDATE"]
    seen = {}
    for c in candidates:
        if c["canonical_ticker"] in seen:
            raise SystemExit(f"STOP: duplicate canonical ticker after dedup: {c['canonical_ticker']}")
        seen[c["canonical_ticker"]] = True

    candidates.sort(key=lambda r: (r["digest"], r["canonical_ticker"]))
    for i, c in enumerate(candidates, start=1):
        c["rank"] = i
        c["selected"] = i <= TARGET_ADDITIONS

    if len(candidates) < TARGET_ADDITIONS:
        raise SystemExit(f"STOP: only {len(candidates)} eligible candidates, need {TARGET_ADDITIONS}")

    selected = [c["canonical_ticker"] for c in candidates[:TARGET_ADDITIONS]]
    final = list(LOCKED_24) + selected
    if len(final) != TARGET_TOTAL or len(set(final)) != TARGET_TOTAL:
        raise SystemExit(f"STOP: final universe is {len(final)} entries, {len(set(final))} unique")

    # ---- duplicate-SECURITY guard (not merely duplicate-string) ------------
    # Without the alias map, BRKB and BRK-B are two strings for one security and
    # this check is what catches it.
    aliased_into_locked = [r for r in ledger
                           if r["status"] == "ALREADY_LOCKED_AFTER_ALIAS_NORMALIZATION"]
    for c in candidates:
        if c["canonical_ticker"] in locked_set:
            raise SystemExit(f"STOP: candidate {c['canonical_ticker']} is already locked")
    canon_of_source = {}
    for rec in ledger:
        if rec["canonical_ticker"] and rec["status"] not in ("EXCLUDED",):
            canon_of_source.setdefault(rec["canonical_ticker"], []).append(rec["source_ticker"])
    collisions = {k: v for k, v in canon_of_source.items() if len(v) > 1}
    if collisions:
        raise SystemExit(f"STOP: two source identifiers map to one canonical ticker: {collisions}")

    locked_present = [r for r in ledger
                      if r["status"] in ("ALREADY_LOCKED", "ALREADY_LOCKED_AFTER_ALIAS_NORMALIZATION")]
    disposition = {
        "source_rows": len(rows),
        "excluded_non_equity": sum(1 for r in ledger if r["exclusion_rule"] and r["exclusion_rule"].startswith("R6.2")),
        "excluded_malformed": sum(1 for r in ledger if r["exclusion_rule"] and r["exclusion_rule"].startswith("R6.3")),
        "excluded_duplicate_issuer": sum(1 for r in ledger if r["exclusion_rule"] and r["exclusion_rule"].startswith("R5")),
        "already_in_locked_24": len(locked_present),
        "already_locked_after_alias": len(aliased_into_locked),
        "eligible_candidates": len(candidates),
        "selected": len(selected),
        "not_selected": len(candidates) - len(selected),
    }
    total = (disposition["excluded_non_equity"] + disposition["excluded_malformed"]
             + disposition["excluded_duplicate_issuer"] + disposition["already_in_locked_24"]
             + disposition["eligible_candidates"])
    if total != len(rows):
        raise SystemExit(f"STOP: dispositions total {total}, source rows {len(rows)}")

    return {
        "artifact": "Proposed outcome-blind universe expansion 24 -> 50",
        "schema": "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1",
        "status": "PROPOSAL_ONLY_NOT_ACTIVE",
        "production_universe_unchanged": True,
        "source": {
            "description": ("the dated official iShares OEF holdings snapshot, used as an "
                            "identity-only proxy for the S&P 100 investable universe"),
            "is_sp_dji_constituent_file": False,
            "publisher": "BlackRock / iShares (fund issuer)",
            "source_url": snapshot.get("source_url"),
            "retrieved_utc": snapshot.get("retrieved_utc"),
            "source_reported_as_of": snapshot.get("source_reported_as_of"),
            "raw_sha256_lf": snapshot.get("raw_sha256_lf"),
        },
        "frozen_ticker_aliases": dict(FROZEN_TICKER_ALIASES),
        "alias_amendment": {
            "file": "PRE_SELECTION_ALIAS_AMENDMENT_2026-08-16.md",
            "sha256_lf": "5faabac1e5a6b77a8dc3cbb894c667948cbcbb8824e2f159e81b29ca2b30ffc6",
            "created_after_collision_discovery": True,
            "created_before_final_selection": True,
            "informed_by_prohibited_data": False,
            "applied_before": ["locked-24 comparison", "issuer deduplication",
                               "candidate hashing", "uniqueness counting"],
        },
        "aliased_into_locked": [
            {"source_ticker": r["source_ticker"], "canonical_ticker": r["canonical_ticker"],
             "name": r["name"], "status": r["status"]}
            for r in aliased_into_locked],
        "hash_prefix": HASH_PREFIX,
        "digest_case": "lowercase hexadecimal",
        "sort_order": "(digest ascending, canonical_ticker ascending)",
        "locked_24": list(LOCKED_24),
        "selected_26": selected,
        "final_50": final,
        "disposition_counts": disposition,
        "duplicate_class_decisions": duplicate_decisions,
        "candidate_ledger": ledger,
        "no_backfill_rule": ("A selected ticker is never replaced because it later fails F5, has an "
                             "ambiguous search construct, lacks an accessible issuer page, produces "
                             "missing data, fails an eligibility gate, or contributes no usable "
                             "event. Backfilling from rank 27 onward is prohibited."),
        "prohibited_inputs_used": False,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic 24 -> 50 universe expansion (proposal only).")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)

    snap = json.loads(Path(a.snapshot).read_text(encoding="utf-8"))
    doc = build(snap)

    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    proposal = out_dir / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED.json"
    proposal.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    print(f"wrote {proposal}")
    for k, v in doc["disposition_counts"].items():
        print(f"  {k:28s} {v}")
    print(f"  final universe size          {len(doc['final_50'])} ({len(set(doc['final_50']))} unique)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
