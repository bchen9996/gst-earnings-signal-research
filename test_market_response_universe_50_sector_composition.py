#!/usr/bin/env python3
"""Deterministic tests for the descriptive sector-composition audit.

These EXECUTE the classification and recompute every metric independently. They
do not trust the audit's own declarations.

Offline. Sockets blocked. No GST, price, return, or market weight is read.

Run directly: python test_market_response_universe_50_sector_composition.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import socket
import sys
from collections import Counter
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline sector-audit test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

ROOT = Path(__file__).resolve().parent
LS = ROOT / "Live Signal Engine"
D = LS / "Universe_Sector_Audit_2026-08-16"
U = LS / "Universe_Expansion_2026-08-16"
CLASSIFIER = ROOT / "tools" / "sector_composition" / "classify_universe_sectors.py"
AUDIT = D / "GST_UNIVERSE_50_SECTOR_COMPOSITION_AUDIT_v1.0.json"
CLS_JSON = D / "GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1.0.json"
CLS_CSV = D / "GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1.0.csv"
OEF_JSON = D / "GST_OEF_PROXY_SECTOR_CLASSIFICATION_v1.0.json"
REVIEW = D / "GST_UNIVERSE_50_SECTOR_COMPOSITION_REVIEW_TEMPLATE_v1.0.md"
RULE = D / "PRE_RETRIEVAL_SECTOR_COMPOSITION_AUDIT_RULE_2026-08-16.md"
REPORT = D / "GST_UNIVERSE_50_SECTOR_COMPOSITION_AUDIT_v1.0_DRAFT.md"
PROPOSAL = U / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED.json"
CONSTANTS = ROOT / "gst_market_response" / "constants.py"
REGISTRY = LS / "Market_Response_Event_Registry" / "registry.jsonl"

SOURCES = D / "sources"
IDENTITY = SOURCES / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json"
FF12_SRC = SOURCES / "FF12_SIC_DEFINITION_SOURCE_2026-08-16.txt"
FF12_NORM = SOURCES / "FF12_SIC_INTERVALS_NORMALIZED_2026-08-16.json"
PROVENANCE = SOURCES / "GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json"
OEF_SNAPSHOT = U / "GST_OEF_IDENTITY_SNAPSHOT_2026-08-13.json"

# The proxy denominator is the ECONOMIC ISSUER, keyed by SEC CIK.
OEF_GROUP = "OEF_UNIQUE_ISSUER_PROXY_POOL"
OEF_KEY = "oef_unique_issuer_proxy_pool"

RULE_SHA = "5ce6a0f01ce7dec84bcf755ee655c4b938165859cdb495a6ff9c37c5021b4dab"

PROTECTED = {
    "gst_market_response/constants.py": "99beea34f5bb55f1d56dbbe581485b270c7ac9b3c6d7e9e5b02d64e3de35f094",
    "Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.0.json": "85264e9786e42180547a22f320da7384b4a54d1e45c777e40b2f596a982b3805",
    "Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-08-16.json": "11b4df9a6e3321584a617fb2134afae431ac2c84ced193f85279b5bee70b54bd",
    "Live Signal Engine/GST_HYP01_EFFECTIVE_LOCK_REPORT_v1.0.json": "3c718796a646fd00b943ca737f1c5c2f9a33b47ccfa48479e511a0b07b2cd59e",
    "Live Signal Engine/Market_Response_Event_Registry/registry.jsonl": "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974",
    "Live Signal Engine/GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json": "2ebb1639d5bb964e6d784cb988eb0a80cf9618ef42eb261e33cca2a7d97cc020",
    "Live Signal Engine/GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json": "03aa177242169cbca20e22a52fe1d70a7f295040e82e9fb3c71c97641d2dfad3",
    "Live Signal Engine/Universe_Expansion_2026-08-16/GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED.json":
        "aeab18e845fa7cc5f152f43b43c6afbe28403f64d58568a76b319aade4ecb07a",
}

# Fields that must never influence any figure in this audit. Tested in READ POSITION
# (subscript, .get(), or attribute), NOT as a bare substring: the classifier legitimately
# contains "return" as a Python keyword and names these fields inside disclaimer strings
# asserting they were not used. A substring match flags those and proves nothing about
# whether a weight was ever actually read.
PROHIBITED_WEIGHT_FIELDS = ("market_value", "marketvalue", "market_cap", "marketcap",
                            "weight", "oef_weight", "notional", "quantity", "price",
                            "shares", "volume", "adj_close", "close", "ret", "pnl")

FAILURES: list[str] = []
SKIPPED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    """Never silent: a skipped check is announced and counted."""
    print(f"SKIP: {label}   ({why})")
    SKIPPED.append(f"{label} - {why}")


def sha_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


spec = importlib.util.spec_from_file_location("sector_classifier", CLASSIFIER)
SEC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SEC)

A = json.loads(AUDIT.read_text(encoding="utf-8"))
P = json.loads(PROPOSAL.read_text(encoding="utf-8"))
R = A["records"]
M = A["metrics"]


# ---------------------------------------------------------------- 1. universe untouched
def test_1_universe_not_altered() -> None:
    f50 = [r["canonical_ticker"] for r in R["proposed_final_50"]]
    check("1a. exactly 50 final records", len(R["proposed_final_50"]) == 50)
    check("1b. exactly 24 legacy records", len(R["legacy_24"]) == 24)
    check("1c. exactly 26 proposed additions", len(R["proposed_additions_26"]) == 26)
    check("1d. final ordering matches the merged proposal exactly", f50 == P["final_50"])
    check("1e. legacy 24 match positions 1-24", f50[:24] == P["locked_24"])
    check("1f. additions match positions 25-50", f50[24:] == P["selected_26"])
    check("1g. no duplicates", len(set(f50)) == 50)
    check("1h. audit declares the universe unaltered", A["universe_altered"] is False)
    check("1i. positions are 1..50 in order",
          [r["universe_position"] for r in R["proposed_final_50"]] == list(range(1, 51)))


# ---------------------------------------------------------------- 2. classification provenance
def test_2_every_record_tied_to_official_sic() -> None:
    bad_sic, bad_cik, bad_url = [], [], []
    for r in R["proposed_final_50"] + R[OEF_KEY]:
        if r["classification_status"] == "CLASSIFIED":
            if not isinstance(r["sec_sic"], int):
                bad_sic.append(r["canonical_ticker"])
            if not r["cik"]:
                bad_cik.append(r["canonical_ticker"])
            if not (r["provenance_url"] or "").startswith("https://data.sec.gov/submissions/"):
                bad_url.append(r["canonical_ticker"])
    check(f"2a. every classified record has an official SEC SIC (bad={bad_sic[:3]})", not bad_sic)
    check(f"2b. every classified record has a CIK (bad={bad_cik[:3]})", not bad_cik)
    check(f"2c. every provenance URL is an official SEC submissions URL (bad={bad_url[:3]})", not bad_url)
    check("2d. aggregators not used as evidence", A["sources"]["aggregators_used_as_evidence"] is False)
    check("2e. FF12 definitions came from the French library",
          "ken.french" in A["sources"]["french_ff12_definitions"]["url"])
    check("2f. frozen rule hash recorded and matches the committed file",
          A["frozen_rule"]["sha256_lf"] == RULE_SHA == sha_lf(RULE))
    check("2g. rule was frozen before retrieval",
          A["frozen_rule"]["frozen_before_any_retrieval"] is True
          and A["frozen_rule"]["created_utc"] < A["sources"]["sec_ticker_cik"]["retrieved_utc"])


# ---------------------------------------------------------------- 3. mechanical derivation
def test_3_ff12_derived_from_frozen_intervals() -> None:
    ff = {"categories": A["ff12_definitions"]}
    bad = []
    for r in R["proposed_final_50"] + R[OEF_KEY]:
        got = SEC.ff12_for_sic(r["sec_sic"], ff)
        if (got["category_abbr"] != r["ff12_category_abbr"]
                or got["status"] != r["classification_status"]):
            bad.append((r["canonical_ticker"], r["sec_sic"], r["ff12_category_abbr"], got["category_abbr"]))
    check(f"3a. every FF12 category recomputes from the frozen intervals (bad={bad[:3]})", not bad)
    check("3b. exactly 12 categories defined", len(A["ff12_definitions"]) == 12)
    check("3c. category 12 is the residual with no explicit intervals",
          A["ff12_definitions"][-1]["code"] == 12 and not A["ff12_definitions"][-1]["intervals"])
    # interval membership must actually hold
    off = []
    for r in R["proposed_final_50"]:
        iv = r["matched_sic_interval"]
        if iv and re.fullmatch(r"\d{4}-\d{4}", iv):
            lo, hi = (int(x) for x in iv.split("-"))
            if not (lo <= r["sec_sic"] <= hi):
                off.append(r["canonical_ticker"])
    check(f"3d. each matched interval actually contains its SIC (bad={off})", not off)
    check("3e. every record has exactly one classification field set",
          all((r["ff12_category_abbr"] is not None) ^ (r["classification_status"] == SEC.UNRESOLVED)
              for r in R["proposed_final_50"]))
    check("3f. every record carries a full trace",
          all("-> FF12 " in r["trace"] and "CIK" in r["trace"] for r in R["proposed_final_50"]))


# ---------------------------------------------------------------- 4. unresolved policy
def test_4_unresolved_never_inferred() -> None:
    ff = {"categories": A["ff12_definitions"]}
    got = SEC.ff12_for_sic(None, ff)
    check("4a. a missing SIC yields CLASSIFICATION_UNRESOLVED", got["status"] == SEC.UNRESOLVED)
    check("4b. an unresolved record gets no category", got["category_abbr"] is None)
    n_unres = M["PROPOSED_FINAL_50"]["n_unresolved"]
    check(f"4c. unresolved records are reported, not dropped ({n_unres} in this run)",
          M["PROPOSED_FINAL_50"]["n_records"] == 50)
    check("4d. this run produced zero unresolved final-50 records", n_unres == 0)


# ---------------------------------------------------------------- 5. equal weights only
def test_5_equal_ticker_weights_only() -> None:
    src = CLASSIFIER.read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1].lower()
    # read position only: rec["price"], rec.get("weight"), rec.price
    hits = [f for f in PROHIBITED_WEIGHT_FIELDS
            if re.search(r"""(?:\[\s*["']|\.get\(\s*["']|(?<![\w"'])\.)""" + re.escape(f)
                         + r"""(?:["']|\b)""", body)]
    check(f"5a. classifier reads no market weight field in any read position (hits={hits})", not hits)
    # and the matcher itself must be able to catch one
    check("5a'. read-position matcher detects a planted weight read",
          bool(re.search(r"""(?:\[\s*["']|\.get\(\s*["']|(?<![\w"'])\.)""" + "price" + r"""(?:["']|\b)""",
                         'w = row["price"] * n')))
    blob = json.dumps(A).lower()
    for f in ("market_value", "oef_weight", "marketcap"):
        check(f"5b. audit output contains no {f}", f'"{f}"' not in blob)
    check("5c. audit declares equal ticker weights", A["weighting"] == "equal ticker weights only")
    check("5d. every metric block declares equal weights",
          all("equal ticker weights" in M[g]["weighting"] for g in M))
    check("5e. prohibited inputs declared unused", A["prohibited_inputs_used"] is False)
    # the OEF proxy classification must not carry holdings weights
    o = json.loads(OEF_JSON.read_text(encoding="utf-8"))
    keys = {k for r in o["records"] for k in r}
    check(f"5f. OEF proxy records carry no weight field",
          not any(any(p in k.lower() for p in ("weight", "value", "price", "quantity")) for k in keys))


# ---------------------------------------------------------------- 6. metric arithmetic
def _recompute(records):
    cls = [r for r in records if r["classification_status"] == "CLASSIFIED"]
    n = len(cls)
    counts = Counter(r["ff12_category_abbr"] for r in cls)
    shares = {k: v / n for k, v in counts.items()}
    return counts, shares, n


def test_6_metrics_recompute() -> None:
    for g, key in (("LEGACY_24", "legacy_24"), ("PROPOSED_ADDITIONS_26", "proposed_additions_26"),
                   ("PROPOSED_FINAL_50", "proposed_final_50"),
                   (OEF_GROUP, OEF_KEY)):
        counts, shares, n = _recompute(R[key])
        m = M[g]
        check(f"6a. {g}: counts tie to records", dict(sorted(counts.items())) == m["counts"])
        check(f"6b. {g}: counts sum to the denominator", sum(counts.values()) == n == m["n_classified"])
        # Stored percentages are rounded to 4 dp, so their sum need not be exactly 100
        # when n does not divide evenly. Assert the STRONGER pair instead: the unrounded
        # shares sum to exactly 100, and every stored value is the exact 4-dp rounding
        # of its unrounded share. This pins each figure individually.
        check(f"6c. {g}: unrounded shares sum to exactly 100%",
              abs(100 * sum(shares.values()) - 100.0) < 1e-12,
              f"{100 * sum(shares.values())!r}")
        badpct = [c for c, v in m["percentages"].items()
                  if v != round(100 * shares.get(c, 0.0), 4)]
        check(f"6c'. {g}: every percentage is the exact 4-dp rounding of its share "
              f"(bad={badpct[:3]})", not badpct)
        check(f"6c''. {g}: rounded percentages sum to 100% within rounding error",
              abs(sum(m["percentages"].values()) - 100.0) <= 12 * 5e-5,
              f"{sum(m['percentages'].values())}")
        hhi = sum(s * s for s in shares.values())
        ent = -sum(s * math.log(s) for s in shares.values() if s > 0)
        check(f"6d. {g}: HHI recomputes", abs(hhi - m["hhi_equal_ticker_weights"]) < 1e-6)
        check(f"6e. {g}: entropy recomputes", abs(ent - m["shannon_entropy_nats"]) < 1e-6)
        check(f"6f. {g}: effective categories = exp(entropy)",
              abs(math.exp(ent) - m["effective_number_of_categories"]) < 1e-5)
        check(f"6g. {g}: represented + absent = 12",
              m["categories_represented"] + m["categories_absent"] == 12)
        check(f"6h. {g}: largest-category share is the exact 4-dp rounding of the recomputed share",
              m["largest_category_share_pct"] == round(100 * max(shares.values()), 4),
              f"stored={m['largest_category_share_pct']} recomputed={100 * max(shares.values())}")
        check(f"6i. {g}: largest category and count tie to the recomputed counts",
              counts[m["largest_category"]] == max(counts.values()) == m["largest_category_count"])


# ---------------------------------------------------------------- 7. comparison + sensitivity
def test_7_comparison_and_sensitivity_recompute() -> None:
    f = M["PROPOSED_FINAL_50"]["percentages"]
    o = M[OEF_GROUP]["percentages"]
    diff = A["final50_vs_oef_percentage_point_difference"]
    bad = [c for c in set(f) | set(o) if abs((f.get(c, 0.0) - o.get(c, 0.0)) - diff.get(c, 0.0)) > 1e-6]
    check(f"7a. FINAL_50 vs OEF differences recompute (bad={bad})", not bad)
    loo_share, loo_hhi = [], []
    recs = R["proposed_final_50"]
    for i in range(len(recs)):
        _, shares, _ = _recompute(recs[:i] + recs[i + 1:])
        loo_share.append(100 * max(shares.values()))
        loo_hhi.append(sum(s * s for s in shares.values()))
    s = A["sensitivity"]
    check("7b. leave-one-out largest-share range recomputes",
          abs(min(loo_share) - s["leave_one_out_largest_category_share_pct"]["min"]) < 1e-4
          and abs(max(loo_share) - s["leave_one_out_largest_category_share_pct"]["max"]) < 1e-4)
    check("7c. leave-one-out HHI range recomputes",
          abs(min(loo_hhi) - s["leave_one_out_hhi"]["min"]) < 1e-6
          and abs(max(loo_hhi) - s["leave_one_out_hhi"]["max"]) < 1e-6)
    check("7d. no alternative universe generated", s["alternative_universe_generated"] is False)
    check("7e. no subset search performed", s["subset_search_performed"] is False)


# ---------------------------------------------------------------- 8. CSV/JSON one source of truth
def test_8_csv_and_json_agree() -> None:
    import csv as _csv
    with CLS_CSV.open(encoding="utf-8") as fh:
        rows = list(_csv.DictReader(fh))
    j = json.loads(CLS_JSON.read_text(encoding="utf-8"))["records"]
    check("8a. CSV has 50 rows", len(rows) == 50)
    check("8b. CSV tickers match the JSON in order",
          [r["canonical_ticker"] for r in rows] == [r["canonical_ticker"] for r in j])
    check("8c. CSV categories match the JSON",
          [r["ff12_category_abbr"] for r in rows] == [str(r["ff12_category_abbr"]) for r in j])
    check("8d. CSV SIC values match the JSON",
          [r["sec_sic"] for r in rows] == [str(r["sec_sic"]) for r in j])


# ---------------------------------------------------------------- 9. language discipline
FORBIDDEN = ("representative", "balanced", "acceptable", "unacceptable", "biased",
             "statistically significant")
NEG = ("not ", "no ", "never", "does not", "cannot", "must not", "without", "unless")


def test_9_no_verdict_language() -> None:
    text = REPORT.read_text(encoding="utf-8")
    flat = " ".join(text.split()).lower()
    for w in FORBIDDEN:
        hits, i = [], 0
        while True:
            k = flat.find(w, i)
            if k < 0:
                break
            if not any(n in flat[max(0, k - 90):k] for n in NEG):
                hits.append(flat[max(0, k - 60):k + len(w) + 10])
            i = k + len(w)
        check(f"9a. report never asserts {w!r}", not hits, str(hits[:1]))
    check("9b. audit asserts no accept/reject conclusion",
          A["accept_reject_conclusion_asserted"] is False)
    check("9c. no concentration threshold specified",
          A["concentration_threshold_specified"] is False
          and A["frozen_rule"]["concentration_threshold_frozen"] is False)
    check("9d. the report says no threshold was specified",
          "no automated accept/reject threshold was specified" in flat)
    check("9e. required banners present",
          all(b in text for b in ("DESCRIPTIVE AUDIT ONLY", "NO UNIVERSE CHANGE",
                                  "PROPOSED 50 REMAIN INACTIVE", "PRODUCTION UNIVERSE REMAINS 24",
                                  "NO GST OR MARKET OUTCOME USED", "F5 REMAINS OPEN",
                                  "COLLECTION REMAINS BLOCKED",
                                  "NO CONCENTRATION THRESHOLD WAS INVENTED")))


# ---------------------------------------------------------------- 10. review template
def test_10_review_template_pending() -> None:
    raw = REVIEW.read_text(encoding="utf-8")
    rv = " ".join(raw.split())   # phrases are line-wrapped in the source Markdown
    check("10a. no ticked checkbox", not re.search(r"- \[[xX]\]", raw))
    check("10b. all four dispositions offered",
          all(o in rv for o in ("ACCEPT_CURRENT_BROAD_PROPOSAL", "REQUIRE_STRATIFIED_REDESIGN",
                                "REQUIRE_SECTOR_SPECIFIC_REDESIGN", "UNRESOLVED")))
    check("10c. reviewer identity not filled", "**Reviewer:** `PENDING`" in rv)
    check("10d. findings remain PENDING", rv.count("`PENDING`") >= 15)
    check("10e. threshold decision deferred to the reviewer",
          "without consulting GST attention data or return outcomes" in rv)


# ---------------------------------------------------------------- 11. protected state
def test_11_protected_state_unchanged() -> None:
    for rel, want in PROTECTED.items():
        p = ROOT / rel
        check(f"11a. {rel.split('/')[-1]} byte-identical", p.is_file() and sha_lf(p) == want)
    sys.path.insert(0, str(ROOT))
    from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE as L24
    check("11b. production universe still exactly the original 24",
          len(L24) == 24 and list(L24) == P["locked_24"])
    for t in ("CAT", "NFLX", "WMT", "MMM"):
        check(f"11c. production constant does not contain proposed addition {t}",
              t not in set(L24))
    lock = json.loads((LS / "GST_HYP01_ANALYSIS_LOCK_v1.0.json").read_text(encoding="utf-8-sig"))
    cp = json.loads((LS / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json").read_text(encoding="utf-8-sig"))
    f5 = json.loads((LS / "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json").read_text(encoding="utf-8"))
    eff = json.loads((LS / "GST_HYP01_EFFECTIVE_LOCK_REPORT_v1.0.json").read_text(encoding="utf-8"))
    check("11d. F5 remains OPEN", f5["gap_audit_status_after_this_work"] == "STILL_OPEN"
          and eff["effective_state"]["f5_construct_validity"] == "OPEN")
    check("11e. collection remains BLOCKED", eff["effective_state"]["prospective_collection"] == "BLOCKED")
    check("11f. research state unchanged",
          lock["results"] is None and lock["frozen_event_ids"] == []
          and lock["eligible_events_now"] == 0 and cp["screening_rows"] == [])
    rows = [json.loads(l) for l in REGISTRY.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("11g. registry is the single unchanged DELL row",
          len(rows) == 1 and rows[0]["ticker"] == "DELL")


# ---------------------------------------------------------------- 12. isolation
def test_12_offline_and_no_outcome_data() -> None:
    src = CLASSIFIER.read_text(encoding="utf-8")
    check("12a. classifier blocks sockets", "socket.getaddrinfo = _deny" in src)
    body = src.split('"""', 2)[-1]
    for tok in ("pytrends", "yfinance", "TrendReq", "interest_over_time", "alpaca"):
        check(f"12b. classifier never references {tok}", tok not in body)
    try:
        socket.getaddrinfo("example.com", 443)
        check("12c. network blocked", False)
    except Exception as e:
        check("12c. network blocked", type(e).__name__ == "NetworkBlocked")


# ---------------------------------------------------------------- 13. issuer denominator
def test_13_issuer_level_denominator() -> None:
    dn = A["denominators"]
    ig = A["issuer_level_grouping"]
    oef = R[OEF_KEY]
    snap = json.loads(OEF_SNAPSHOT.read_text(encoding="utf-8"))
    alias = P["frozen_ticker_aliases"]

    # ---- recompute the grouping from the committed identity snapshot ----
    ident = {s["canonical_ticker"]: s for s in
             json.loads(IDENTITY.read_text(encoding="utf-8"))["securities"]}
    groups: dict[int, set] = {}
    n_src = 0
    for row in snap["rows"]:
        if row["asset_class"] != "Equity":
            continue
        n_src += 1
        raw = row["source_ticker"].strip().upper().replace(".", "-")
        t = alias.get(raw, raw)
        groups.setdefault(ident[t]["cik"], set()).add(t)

    check(f"13a. OEF source equity securities recompute ({n_src})",
          dn["oef_source_equity_securities"] == n_src)
    check(f"13b. OEF unique issuers recompute ({len(groups)}) and are NOT the security count",
          dn["oef_unique_issuers"] == len(groups) == len(oef) < n_src)
    check("13c. every OEF record is one CIK, appearing exactly once",
          len({r["cik"] for r in oef}) == len(oef))
    check("13d. issuer key is the official SEC CIK", ig["issuer_key"] == "official SEC CIK")

    # ---- duplicate tickers sharing one CIK count once; GOOG+GOOGL in one group ----
    alpha = [r for r in oef if "GOOGL" in r["canonical_securities"]]
    check("13e. GOOG and GOOGL fall in exactly one CIK group", len(alpha) == 1)
    if alpha:
        g = alpha[0]
        check("13f. that group holds both share classes",
              sorted(g["canonical_securities"]) == ["GOOG", "GOOGL"], str(g["canonical_securities"]))
        check("13g. it contributes exactly one observation", g["n_source_securities"] == 2
              and sum(1 for r in oef if r["cik"] == g["cik"]) == 1)
        check("13h. source securities are preserved", sorted(g["source_securities"]) == ["GOOG", "GOOGL"])
        check("13i. display ticker is the lexicographically smallest canonical ticker",
              g["display_ticker"] == min(g["canonical_securities"]) == "GOOG")
    check("13j. every record declares the display ticker affects no metric",
          all(r["display_ticker_affects_metrics"] is False for r in oef)
          and ig["display_ticker_affects_metrics"] is False)
    # the display ticker must be cosmetic: renaming it must not move any metric
    import copy as _copy
    mutated = _copy.deepcopy(oef)
    for r in mutated:
        r["display_ticker"] = r["canonical_ticker"] = "ZZZZ"
    ffdef = {"categories": A["ff12_definitions"]}
    check("13k. renaming every display ticker changes no metric",
          SEC.metrics(mutated, ffdef) == SEC.metrics(oef, ffdef))

    # ---- alias applied before identity matching ----
    check("13l. frozen alias applied before identity matching",
          ig["alias_applied_before_identity_matching"] == alias and "BRKB" in alias)
    check("13m. BRK-B resolves through the alias to one issuer",
          any(r["canonical_ticker"] == "BRK-B" or "BRK-B" in r["canonical_securities"] for r in oef))

    # ---- the final 50 is verified, not assumed ----
    f50 = R["proposed_final_50"]
    ciks = [r["cik"] for r in f50]
    check("13n. the final 50 has 50 unique CIKs (verified from records)",
          len(set(ciks)) == 50 == len(ciks) and None not in ciks)
    check("13o. the audit reports that verification",
          dn["proposed_final_50_unique_ciks"] == 50 and dn["proposed_final_50_securities"] == 50)

    # ---- denominators are stated, not implied ----
    union_sec = {r["canonical_ticker"] for r in f50} | {
        t for r in oef for t in r["canonical_securities"]}
    union_cik = {r["cik"] for r in f50} | {r["cik"] for r in oef}
    check(f"13p. union unique canonical securities recompute ({len(union_sec)})",
          dn["union_unique_canonical_securities"] == len(union_sec))
    check(f"13q. union unique CIKs recompute ({len(union_cik)})",
          dn["union_unique_ciks"] == len(union_cik))
    check("13r. classification requests = final 50 + OEF issuers",
          dn["classification_requests"] == len(f50) + len(oef))
    check("13s. the security and issuer denominators are defined in the artifact",
          "security" in dn["definitions"] and "issuer" in dn["definitions"]
          and "CIK" in dn["definitions"]["issuer"])

    # ---- labels say issuer, not security ----
    check("13t. the metric group is named for unique issuers", OEF_GROUP in M
          and "OEF_ELIGIBLE_PROXY_POOL" not in M)
    check("13u. the records block is named for unique issuers", OEF_KEY in R
          and "oef_eligible_proxy_pool" not in R)
    ojson = json.loads(OEF_JSON.read_text(encoding="utf-8"))
    check("13v. the OEF classification artifact declares the issuer denominator",
          ojson["denominator_level"] == "ECONOMIC_ISSUER" and ojson["issuer_key"] == "official SEC CIK")
    flat = " ".join(REPORT.read_text(encoding="utf-8").split())
    check("13w. the report defines the 113 figure rather than asserting it bare",
          "unique canonical securities across the union" in flat)
    check("13x. the report states the issuer denominator for the proxy pool",
          "unique issuers" in flat and "OEF issuer proxy pool" in flat)
    # The proxy denominator must be LABELLED as issuers everywhere it is named, not
    # merely mentioned as issuers once. Relabelling it "securities" must fail.
    n_iss = dn["oef_unique_issuers"]
    check("13x'. the denominator table labels the proxy pool as unique issuers",
          "| **OEF pool, unique issuers**" in flat
          and "OEF pool, unique securities" not in flat)
    check(f"13x''. the proxy count {n_iss} is stated as issuers, never as securities",
          f"{n_iss} unique issuers" in flat and f"{n_iss} unique securities" not in flat
          and f"{n_iss} securities" not in flat)
    check("13x'''. the source-security count is not presented as the proxy denominator",
          f"OEF percentages are over **{n_iss} unique issuers**" in flat)
    for art, label in ((REPORT, "report"), (REVIEW, "review template")):
        t = " ".join(art.read_text(encoding="utf-8").split())
        check(f"13x''''. the {label} never calls the proxy pool a security pool",
              "OEF security proxy pool" not in t and "security proxy pool" not in t)
    check("13y. the frozen rule is unchanged by this correction",
          A["frozen_rule"]["unchanged_by_this_correction"] is True and sha_lf(RULE) == RULE_SHA)


# ---------------------------------------------------------------- 14. reproducible from committed sources
def _tmp_sources(tmp: Path) -> Path:
    """A writable copy of the committed sources directory."""
    import shutil
    dst = tmp / "sources"
    shutil.copytree(SOURCES, dst)
    return dst


def _refuses(sources: Path, why: str) -> bool:
    """build() must raise SystemExit and write nothing."""
    try:
        SEC.build(sources)
    except SystemExit:
        return True
    except Exception:
        return False
    return False


def _remanifest(sources: Path) -> None:
    """Re-hash the manifest so a mutation is internally consistent (isolates the
    check under test from the hash gate that would otherwise fire first)."""
    prov = json.loads((sources / "GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json").read_text(encoding="utf-8"))
    for item in prov["inputs"]:
        p = SEC.resolve_input(sources, item)
        if p.is_file():
            item["sha256_lf"] = sha_lf(p)
    (sources / "GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json").write_text(
        json.dumps(prov, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def test_14_sources_committed_and_fail_closed() -> None:
    import subprocess
    import tempfile

    for p in (IDENTITY, FF12_SRC, FF12_NORM, PROVENANCE):
        check(f"14a. committed source present: {p.name}", p.is_file())

    prov = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    check("14b. manifest declares no network is needed",
          prov["network_required_for_reproduction"] is False and prov["all_inputs_committed"] is True)
    bad = [i["filename"] for i in prov["inputs"]
           if not all(k in i for k in ("filename", "url", "retrieved_utc", "bytes", "sha256_lf"))]
    check(f"14c. manifest records filename, URL, retrieval time, bytes and SHA-256 (bad={bad})", not bad)
    mism = [i["filename"] for i in prov["inputs"]
            if not (ROOT / i["repo_path"]).is_file() or sha_lf(ROOT / i["repo_path"]) != i["sha256_lf"]]
    check(f"14d. every manifest hash matches the committed file (bad={mism})", not mism)

    # ---- a clean git archive must contain every required input ----
    in_git = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT,
                            capture_output=True, text=True).returncode == 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tar = tmp / "clean.tar"
        r = (subprocess.run(["git", "archive", "--format=tar", "-o", str(tar), "HEAD"],
                            cwd=ROOT, capture_output=True, text=True)
             if in_git else None)
        if not in_git:
            # This tree is itself an export (no .git), so the archive checks cannot run
            # here. They are NOT quietly passed - they are reported as skipped, and they
            # do run in the repository, which is where a reviewer executes them.
            for lbl in ("14e. clean archive contains every declared input",
                        "14f. clean archive contains the classifier and the frozen rule",
                        "14g. documented reproduction command succeeds from a clean LF export",
                        "14h. clean-export output is byte-identical to the committed audit",
                        "14i. the reproduction run did not touch the network"):
                skip(lbl, "not a git repository - this tree is already a clean export")
        elif r.returncode != 0:
            check("14e. git archive export succeeded", False, r.stderr[:120])
        else:
            import tarfile
            ex = tmp / "clean"
            ex.mkdir()
            with tarfile.open(tar) as tf:
                names = set(tf.getnames())
                tf.extractall(ex)
            need = [i["repo_path"] for i in prov["inputs"]]
            missing = [n for n in need if n not in names]
            check(f"14e. clean archive contains every declared input (missing={missing})", not missing)
            check("14f. clean archive contains the classifier and the frozen rule",
                  "tools/sector_composition/classify_universe_sectors.py" in names
                  and any(n.endswith("PRE_RETRIEVAL_SECTOR_COMPOSITION_AUDIT_RULE_2026-08-16.md")
                          for n in names))
            # ---- documented reproduction command, no external scratch dir, LF checkout ----
            out = tmp / "repro"
            rr = subprocess.run([sys.executable,
                                 "tools/sector_composition/classify_universe_sectors.py",
                                 "--out-dir", str(out)],
                                cwd=ex, capture_output=True, text=True)
            check("14g. documented reproduction command succeeds from a clean LF export",
                  rr.returncode == 0, (rr.stderr or rr.stdout)[-200:])
            produced = out / "GST_UNIVERSE_50_SECTOR_COMPOSITION_AUDIT_v1.0.json"
            if produced.is_file():
                check("14h. clean-export output is byte-identical to the committed audit",
                      sha_lf(produced) == sha_lf(AUDIT))
                for nm in ("GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1.0.csv",
                           "GST_UNIVERSE_50_SECTOR_CLASSIFICATION_v1.0.json",
                           "GST_OEF_PROXY_SECTOR_CLASSIFICATION_v1.0.json"):
                    check(f"14h'. clean-export {nm} is byte-identical", sha_lf(out / nm) == sha_lf(D / nm))
            else:
                check("14h. clean-export output produced", False)
            check("14i. the reproduction run did not touch the network",
                  "NetworkBlocked" not in (rr.stderr or ""))

    # ---- removing any source input refuses ----
    for name in ("SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json",
                 "FF12_SIC_DEFINITION_SOURCE_2026-08-16.txt",
                 "GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json"):
        with tempfile.TemporaryDirectory() as td:
            s = _tmp_sources(Path(td))
            (s / name).unlink()
            check(f"14j. removing {name} refuses", _refuses(s, name))

    # ---- changing any source hash refuses ----
    with tempfile.TemporaryDirectory() as td:
        s = _tmp_sources(Path(td))
        prov2 = json.loads((s / "GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json").read_text(encoding="utf-8"))
        prov2["inputs"][0]["sha256_lf"] = "0" * 64
        (s / "GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json").write_text(
            json.dumps(prov2, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        check("14k. a falsified manifest hash refuses", _refuses(s, "hash"))

    with tempfile.TemporaryDirectory() as td:
        s = _tmp_sources(Path(td))
        b = (s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").read_text(encoding="utf-8")
        (s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").write_text(
            b.replace('"sec_sic": 3571', '"sec_sic": 2911', 1), encoding="utf-8", newline="\n")
        check("14l. editing a source without updating the manifest refuses", _refuses(s, "tamper"))

    # ---- changing a CIK / SIC / FF interval changes the output detectably ----
    ffdef = {"categories": A["ff12_definitions"]}
    before = SEC.ff12_for_sic(3571, ffdef)["category_abbr"]
    with tempfile.TemporaryDirectory() as td:
        s = _tmp_sources(Path(td))
        b = (s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").read_text(encoding="utf-8")
        (s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").write_text(
            b.replace('"sec_sic": 3571', '"sec_sic": 2911', 1), encoding="utf-8", newline="\n")
        _remanifest(s)
        try:
            doc2 = SEC.build(s)
            changed = doc2["metrics"]["PROPOSED_FINAL_50"]["counts"] != M["PROPOSED_FINAL_50"]["counts"]
        except SystemExit:
            changed = True
        check("14m. changing a SIC changes the output detectably", changed)

    with tempfile.TemporaryDirectory() as td:
        s = _tmp_sources(Path(td))
        b = (s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").read_text(encoding="utf-8")
        (s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").write_text(
            b.replace('"cik": 320193', '"cik": 999999999', 1), encoding="utf-8", newline="\n")
        _remanifest(s)
        try:
            doc2 = SEC.build(s)
            changed = [r["cik"] for r in doc2["records"]["proposed_final_50"]] != \
                      [r["cik"] for r in R["proposed_final_50"]]
        except SystemExit:
            changed = True
        check("14n. changing a CIK changes the output detectably", changed)

    with tempfile.TemporaryDirectory() as td:
        s = _tmp_sources(Path(td))
        f = s / "FF12_SIC_DEFINITION_SOURCE_2026-08-16.txt"
        f.write_text(f.read_text(encoding="utf-8").replace("3570-3579", "3570-3570", 1),
                     encoding="utf-8", newline="\n")
        _remanifest(s)
        try:
            doc2 = SEC.build(s)
            changed = doc2["metrics"]["PROPOSED_FINAL_50"]["counts"] != M["PROPOSED_FINAL_50"]["counts"]
        except SystemExit:
            changed = True
        check("14o. changing an FF12 interval changes the output detectably", changed)

    # ---- conflicting SIC / FF12 within one CIK is refused ----
    with tempfile.TemporaryDirectory() as td:
        s = _tmp_sources(Path(td))
        ident = json.loads((s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").read_text(encoding="utf-8"))
        for sec in ident["securities"]:
            if sec["canonical_ticker"] == "GOOGL":
                sec["sec_sic"] = 7371          # same FF12 category (BusEq), different SIC
        (s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").write_text(
            json.dumps(ident, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        _remanifest(s)
        check("14p. one CIK with conflicting SICs is refused", _refuses(s, "sic conflict"))

    with tempfile.TemporaryDirectory() as td:
        s = _tmp_sources(Path(td))
        ident = json.loads((s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").read_text(encoding="utf-8"))
        for sec in ident["securities"]:
            if sec["canonical_ticker"] == "GOOGL":
                sec["sec_sic"] = 4813          # Telcm: different SIC AND different FF12
        (s / "SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json").write_text(
            json.dumps(ident, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        _remanifest(s)
        check("14q. one CIK with conflicting FF12 results is refused", _refuses(s, "ff12 conflict"))
    check("14q'. the SIC conflict gate fires before the FF12 gate, so both are reachable",
          SEC.ff12_for_sic(7371, ffdef)["category_abbr"] == before
          and SEC.ff12_for_sic(4813, ffdef)["category_abbr"] != before)

    # ---- no prohibited input anywhere in the committed sources ----
    # Scope to the DATA records: the document also carries declaration flags such as
    # contains_market_capitalization / contains_earnings_values whose whole purpose is to
    # assert those inputs are absent. Matching the full blob flags the disclaimer and
    # proves nothing about the data.
    ident_doc = json.loads(IDENTITY.read_text(encoding="utf-8"))
    blob = json.dumps(ident_doc["securities"]).lower()
    for f in ("market_value", "marketcap", "market_cap", "oef_weight", "weight",
              "price", "return", "volume", "earnings", "revenue", "market cap"):
        check(f"14r. identity records contain no {f}", f not in blob)
    check("14r'. that matcher would catch a planted weight in a record",
          "oef_weight" in json.dumps([{**ident_doc["securities"][0], "oef_weight": 1.0}]).lower())
    for flag in ("contains_financial_statement_data", "contains_earnings_values",
                 "contains_market_data", "contains_market_capitalization",
                 "contains_prices_returns_or_volumes"):
        check(f"14s. identity snapshot declares {flag} is False", ident_doc[flag] is False)
    check("14t. manifest declares no prohibited inputs", prov["prohibited_inputs_present"] is False)
    keys = {k for s in ident_doc["securities"] for k in s}
    check(f"14u. identity records carry only identity/SIC fields",
          not any(any(p in k.lower() for p in ("weight", "price", "value", "return", "volume",
                                               "shares", "cap")) for k in keys), str(sorted(keys)))


if __name__ == "__main__":
    test_1_universe_not_altered()
    test_2_every_record_tied_to_official_sic()
    test_3_ff12_derived_from_frozen_intervals()
    test_4_unresolved_never_inferred()
    test_5_equal_ticker_weights_only()
    test_6_metrics_recompute()
    test_7_comparison_and_sensitivity_recompute()
    test_8_csv_and_json_agree()
    test_9_no_verdict_language()
    test_10_review_template_pending()
    test_11_protected_state_unchanged()
    test_12_offline_and_no_outcome_data()
    test_13_issuer_level_denominator()
    test_14_sources_committed_and_fail_closed()

    print()
    if SKIPPED:
        print(f"{len(SKIPPED)} SKIPPED (announced, not silent):")
        for s_ in SKIPPED:
            print(f"  - {s_}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL SECTOR-COMPOSITION AUDIT TESTS PASSED")
    sys.exit(0)
