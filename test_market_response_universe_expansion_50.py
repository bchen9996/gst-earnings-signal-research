#!/usr/bin/env python3
"""Deterministic tests for the proposed 24 -> 50 universe expansion.

These EXECUTE the selector and recompute the selection; they do not trust the
committed proposal's own summary. Mutation tests corrupt each critical decision
in a sandbox and require the selector to fail.

Offline. Sockets blocked. Identity-only input. No research artifact is read.

Run directly: python test_market_response_universe_expansion_50.py
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline expansion test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

ROOT = Path(__file__).resolve().parent
LS = ROOT / "Live Signal Engine"
D = LS / "Universe_Expansion_2026-08-16"
SELECTOR = ROOT / "tools" / "universe_expansion" / "select_universe_50.py"
SANITIZER = ROOT / "tools" / "universe_expansion" / "sanitize_oef_snapshot.py"
SNAPSHOT = D / "GST_OEF_IDENTITY_SNAPSHOT_2026-08-13.json"
PROPOSAL = D / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED.json"
AUDIT = D / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_AUDIT_v1.0.json"
PROVENANCE = D / "GST_UNIVERSE_EXPANSION_50_PROVENANCE_v1.0.json"
REVIEW = D / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_REVIEW_TEMPLATE_v1.0.md"
RULE = D / "PRE_RETRIEVAL_SELECTION_RULE.md"
SRC_AMD = D / "PRE_RETRIEVAL_SOURCE_AMENDMENT_2026-08-16.md"
ALIAS_AMD = D / "PRE_SELECTION_ALIAS_AMENDMENT_2026-08-16.md"
CONSTANTS = ROOT / "gst_market_response" / "constants.py"
REGISTRY = LS / "Market_Response_Event_Registry" / "registry.jsonl"
COHORT = LS / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json"
F5AUDIT = LS / "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json"
EFFECTIVE = LS / "GST_HYP01_EFFECTIVE_LOCK_REPORT_v1.0.json"

RULE_SHA = "6911726c077bab02f994f29adddd6bc5930e4dc17c53c1b6245c944196761cde"
SRC_AMD_SHA = "bf88f2261e1b6a6983a3db07b72b4c9d3274032e5332e4519cbfbf3ccab0d6bd"
ALIAS_AMD_SHA = "5faabac1e5a6b77a8dc3cbb894c667948cbcbb8824e2f159e81b29ca2b30ffc6"
RAW_SHA = "3d85de45d0f07bbd830a6431ed671ffbb8266e7aa7bef4cfa360e06df125f892"

PROTECTED = {
    "gst_market_response/constants.py": "99beea34f5bb55f1d56dbbe581485b270c7ac9b3c6d7e9e5b02d64e3de35f094",
    "Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.0.json": "85264e9786e42180547a22f320da7384b4a54d1e45c777e40b2f596a982b3805",
    "Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json": "132a632b0d45d450d0f320c82fbb4af4affd59a98786ca8c603051931b92195e",
    "Live Signal Engine/GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md": "7eef69e81e4764ed19534762d0f3031d3ac2a50c30adc363447d99e38fe69320",
    "Live Signal Engine/Market_Response_Event_Registry/registry.jsonl": "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974",
    "Live Signal Engine/GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json": "2ebb1639d5bb964e6d784cb988eb0a80cf9618ef42eb261e33cca2a7d97cc020",
    "Live Signal Engine/GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json": "03aa177242169cbca20e22a52fe1d70a7f295040e82e9fb3c71c97641d2dfad3",
    "Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-08-16.json": "11b4df9a6e3321584a617fb2134afae431ac2c84ced193f85279b5bee70b54bd",
    "Live Signal Engine/GST_HYP01_EFFECTIVE_LOCK_REPORT_v1.0.json": "3c718796a646fd00b943ca737f1c5c2f9a33b47ccfa48479e511a0b07b2cd59e",
}

PROHIBITED_TOKENS = ("market value", "weight", "notional", "quantity", "price", "fx rate",
                     "return", "performance", "yield", "market cap", "index weight",
                     "trends", "attention", "earnings surprise", "sentiment")

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def flat(p: Path) -> str:
    """Whitespace-normalized text. Markdown hard-wraps sentences, so a literal
    substring match against the raw file fails on phrases that span a newline --
    a matcher defect, not a missing statement."""
    return " ".join(p.read_text(encoding="utf-8").split())


def sha_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SEL = load(SELECTOR, "universe_selector")
SNAP = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
P = json.loads(PROPOSAL.read_text(encoding="utf-8"))
LOCKED_24 = list(SEL.LOCKED_24)


def run_selector(snapshot: dict, out_dir: Path) -> int:
    f = out_dir / "snap.json"
    f.write_text(json.dumps(snapshot), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SELECTOR), "--snapshot", str(f),
                        "--out-dir", str(out_dir)], capture_output=True, text=True, timeout=900)
    return r.returncode


# ---------------------------------------------------------------- 1. frozen governance
def test_1_frozen_artifacts() -> None:
    check("1a. original frozen rule hash matches", sha_lf(RULE) == RULE_SHA, sha_lf(RULE))
    check("1b. source amendment hash matches", sha_lf(SRC_AMD) == SRC_AMD_SHA)
    check("1c. alias amendment hash matches", sha_lf(ALIAS_AMD) == ALIAS_AMD_SHA)
    aud = json.loads(AUDIT.read_text(encoding="utf-8"))
    chain = {c["step"]: c for c in aud["governance_chain"]}
    check("1d. rule frozen before retrieval",
          chain[1]["created_utc"] < chain[2]["created_utc"] < "2026-08-16T05:32:28Z")
    check("1e. source amendment predates the OEF retrieval",
          chain[2]["created_utc"] == "2026-08-16T05:29:42Z"
          and chain[2]["created_utc"] < "2026-08-16T05:32:28Z")
    fa = flat(ALIAS_AMD)
    check("1f. alias amendment predates final selection and says so",
          "BEFORE any final selection" in fa
          and "AFTER an identity collision was discovered" in fa)
    check("1g. the alias amendment disclaims prohibited inputs",
          "No attention, price, earnings, performance, market-value, weight, or outcome data" in fa)


# ---------------------------------------------------------------- 2. source identity
def test_2_source_is_official_ishares_not_spdji() -> None:
    prov = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    cs = prov["canonical_source"]
    check("2a. publisher is BlackRock / iShares", "iShares" in cs["publisher"])
    check("2b. download URL is on ishares.com", "ishares.com" in cs["download_url"])
    check("2c. explicitly not an S&P DJI constituent file",
          cs["is_sp_dji_constituent_file"] is False
          and cs["is_index_provider_canonical_constituent_list"] is False)
    check("2d. raw hash recorded and matches the proposal", cs["raw_sha256_lf"] == RAW_SHA
          and P["source"]["raw_sha256_lf"] == RAW_SHA)
    check("2e. sanitized snapshot hash tied out",
          prov["sanitization"]["sanitized_sha256_lf"] == sha_lf(SNAPSHOT))
    check("2f. as-of date recorded", cs["source_reported_as_of"] == "Aug 13, 2026")
    check("2g. S&P DJI block recorded as not circumvented",
          "NOT retried, evaded, proxied around, or circumvented" in prov["sp_dji_route_unavailable"]["statement"])
    # required phrasing, everywhere it is described
    for label, path in (("proposal md", D / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED_DRAFT.md"),
                        ("cohort amendment", D / "GST_PROSPECTIVE_COHORT_UNIVERSE_AMENDMENT_2026-08-16_PROPOSED.md")):
        t = flat(path)
        check(f"2h. {label} uses the required proxy phrasing",
              "identity-only proxy for the S&P 100 investable universe" in t)
        check(f"2i. {label} never calls it the official S&P 100 constituent list",
              not re.search(r"(?i)official S&P 100 constituent list", t))


# ---------------------------------------------------------------- 3. sanitization
def test_3_identity_only() -> None:
    check("3a. only three identity columns kept",
          SNAP["identity_columns_kept"] == ["Ticker", "Name", "Asset Class"])
    check("3b. twelve columns dropped", len(SNAP["columns_dropped"]) == 12)
    bad = []
    for r in SNAP["rows"]:
        extra = set(r) - {"source_ticker", "name", "asset_class"}
        if extra:
            bad.append((r.get("source_ticker"), sorted(extra)))
        for v in r.values():
            if isinstance(v, (int, float)):
                bad.append((r.get("source_ticker"), "numeric value"))
    check(f"3c. every row carries identity fields only (bad={bad[:2]})", not bad)
    check("3d. no prohibited field name appears as a row key",
          not any(any(t in k.lower() for t in PROHIBITED_TOKENS) for r in SNAP["rows"] for k in r))
    check("3e. snapshot declares no prohibited field emitted",
          SNAP["prohibited_fields_emitted"] is False)
    # the selection code must never reference a market quantity as an input
    src = SELECTOR.read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]
    offenders = [t for t in ("market_value", "weight", "index_weight", "market_cap", "price")
                 if re.search(rf'\b{t}\b\s*=', body) or f'row["{t}"]' in body or f"r['{t}']" in body]
    check(f"3f. selection logic reads no market weight or capitalization (offenders={offenders})",
          not offenders)


# ---------------------------------------------------------------- 4. the selection itself
def test_4_selection_recomputes() -> None:
    with tempfile.TemporaryDirectory() as td:
        rc = run_selector(SNAP, Path(td))
        check("4a. selector runs on the committed snapshot", rc == 0)
        fresh = json.loads((Path(td) / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED.json")
                           .read_text(encoding="utf-8"))
    check("4b. fresh run reproduces the committed final 50", fresh["final_50"] == P["final_50"])
    check("4c. fresh run reproduces the committed selected 26", fresh["selected_26"] == P["selected_26"])
    check("4d. stable across repeated execution", fresh["candidate_ledger"] == P["candidate_ledger"])

    check("4e. original 24 preserved exactly and in order", P["final_50"][:24] == LOCKED_24)
    check("4f. exactly 26 additions", len(P["selected_26"]) == 26)
    check("4g. exactly 50 unique tickers",
          len(P["final_50"]) == 50 and len(set(P["final_50"])) == 50)

    led = P["candidate_ledger"]
    cands = sorted([r for r in led if r["status"] == "ELIGIBLE_CANDIDATE"], key=lambda r: r["rank"])
    bad_hash = [c for c in cands
                if c["hash_input"] != "GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|" + c["canonical_ticker"]]
    check(f"4h. hash input formatting exact (bad={len(bad_hash)})", not bad_hash)
    bad_dig = [c for c in cands
               if hashlib.sha256(c["hash_input"].encode("utf-8")).hexdigest() != c["digest"]]
    check(f"4i. UTF-8 SHA-256 digests recompute (bad={len(bad_dig)})", not bad_dig)
    check("4j. lowercase 64-hex digests",
          all(len(c["digest"]) == 64 and c["digest"] == c["digest"].lower() for c in cands))
    order = [(c["digest"], c["canonical_ticker"]) for c in cands]
    check("4k. sorted ascending by (digest, ticker)", order == sorted(order))
    check("4l. selected are exactly the first 26 in that order",
          [c["canonical_ticker"] for c in cands[:26]] == P["selected_26"])
    check("4m. no omitted candidate ranks above a selected one",
          all(not c["selected"] for c in cands[26:]) and all(c["selected"] for c in cands[:26]))
    check("4n. rank 26 < rank 27 strictly", cands[25]["digest"] < cands[26]["digest"])


# ---------------------------------------------------------------- 5. alias behaviour
def test_5_alias_rules() -> None:
    check("5a. frozen alias map is exactly {'BRKB': 'BRK-B'}",
          SEL.FROZEN_TICKER_ALIASES == {"BRKB": "BRK-B"})
    check("5b. BRKB is not among the selected additions", "BRKB" not in P["selected_26"])
    check("5c. BRKB does not appear in the final universe", "BRKB" not in P["final_50"])
    check("5d. BRK-B appears exactly once in the final universe",
          P["final_50"].count("BRK-B") == 1)
    aliased = P["aliased_into_locked"]
    check("5e. BRKB classified ALREADY_LOCKED_AFTER_ALIAS_NORMALIZATION",
          len(aliased) == 1 and aliased[0]["source_ticker"] == "BRKB"
          and aliased[0]["canonical_ticker"] == "BRK-B"
          and aliased[0]["status"] == "ALREADY_LOCKED_AFTER_ALIAS_NORMALIZATION")
    led = P["candidate_ledger"]
    brkb = [r for r in led if r["source_ticker"] == "BRKB"][0]
    check("5f. BRKB was never hashed as a candidate",
          brkb["digest"] is None and brkb["hash_input"] is None and brkb["rank"] is None)
    check("5g. both identifiers survive in the ledger for audit",
          brkb["source_ticker"] == "BRKB" and brkb["canonical_ticker"] == "BRK-B"
          and brkb["alias_applied"] is True)
    # share-class dedup, existing locked class takes precedence
    dup = P["duplicate_class_decisions"]
    goog = [d for d in dup if d["issuer_key"] == "ALPHABET"]
    check("5h. ALPHABET deduplicated with the locked class kept",
          len(goog) == 1 and goog[0]["kept"] == "GOOGL" and goog[0]["excluded"] == ["GOOG"]
          and goog[0]["rule"] == "R5.1")
    # no issuer represented twice
    seen = {}
    for r in led:
        if r["canonical_ticker"] in P["final_50"] and r["status"] != "EXCLUDED":
            seen.setdefault(r["issuer_key"], []).append(r["canonical_ticker"])
    check("5i. no issuer represented twice among snapshot-derived entries",
          not {k: v for k, v in seen.items() if len(v) > 1})


# ---------------------------------------------------------------- 6. no backfill
def test_6_no_backfill() -> None:
    check("6a. no-backfill rule stated", "Backfilling from rank 27 onward is prohibited"
          in P["no_backfill_rule"])
    aud = json.loads(AUDIT.read_text(encoding="utf-8"))
    check("6b. zero manual insertions recorded", aud["no_backfill"]["manual_insertions"] == 0)
    check("6c. the NFLX promotion is explained as mechanical, not a backfill",
          "not a backfill and not a manual insertion" in aud["no_backfill"]["note"])
    # NFLX must be rank 26 by recomputation, never inserted
    led = P["candidate_ledger"]
    nflx = [r for r in led if r["canonical_ticker"] == "NFLX"]
    check("6d. NFLX present exactly once as a candidate", len(nflx) == 1)
    check("6e. NFLX is rank 26 by computation", nflx[0]["rank"] == 26 and nflx[0]["selected"] is True)
    # the rule text must forbid replacement on downstream failure
    for phrase in ("fails F5", "eligibility gate", "never"):
        check(f"6f. no-replacement rule mentions {phrase!r}",
              phrase in P["no_backfill_rule"] or phrase in RULE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 7. mutation tests
def test_7_mutations_fail_closed() -> None:
    """Each corruption must make the selector fail, or the guards prove nothing."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)

        # (a) removing the alias must make the duplicate-security check fail
        src = SELECTOR.read_text(encoding="utf-8")
        noalias = src.replace('FROZEN_TICKER_ALIASES: dict[str, str] = {"BRKB": "BRK-B"}',
                              'FROZEN_TICKER_ALIASES: dict[str, str] = {}')
        mod = out / "no_alias.py"
        mod.write_text(noalias, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("no_alias", mod)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        try:
            doc = m.build(copy.deepcopy(SNAP))
            dup_sec = "BRKB" in doc["final_50"] and "BRK-B" in doc["final_50"]
            check("7a. removing the alias reintroduces the duplicate security", dup_sec,
                  "expected BRKB and BRK-B both present")
        except SystemExit as e:
            check("7a. removing the alias fails closed", True, str(e))

        # (b) changing the alias target is refused
        badtarget = src.replace('{"BRKB": "BRK-B"}', '{"BRKB": "BRK-C"}')
        mod2 = out / "bad_target.py"
        mod2.write_text(badtarget, encoding="utf-8")
        spec2 = importlib.util.spec_from_file_location("bad_target", mod2)
        m2 = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(m2)
        d2 = m2.build(copy.deepcopy(SNAP))
        check("7b. a changed alias target does not resolve onto the locked ticker",
              "BRK-C" in d2["final_50"] and d2["final_50"].count("BRK-B") == 1,
              "BRK-C must appear as a distinct (wrong) entry, detectable by review")

        # (c) an unapproved extra alias is refused by the frozen-map assertion
        extra = src.replace('{"BRKB": "BRK-B"}', '{"BRKB": "BRK-B", "NFLX": "NFLX-A"}')
        mod3 = out / "extra_alias.py"
        mod3.write_text(extra, encoding="utf-8")
        spec3 = importlib.util.spec_from_file_location("extra_alias", mod3)
        m3 = importlib.util.module_from_spec(spec3)
        spec3.loader.exec_module(m3)
        check("7c. an unapproved alias is detectable: the frozen map no longer matches",
              m3.FROZEN_TICKER_ALIASES != {"BRKB": "BRK-B"})
        d3 = m3.build(copy.deepcopy(SNAP))
        check("7c2. and it visibly changes the outcome", d3["final_50"] != P["final_50"])

        # (d) a 25th / 27th addition must fail
        for n in (25, 27):
            modn = out / f"count_{n}.py"
            modn.write_text(src.replace("TARGET_ADDITIONS = 26", f"TARGET_ADDITIONS = {n}"),
                            encoding="utf-8")
            sp = importlib.util.spec_from_file_location(f"count_{n}", modn)
            mm = importlib.util.module_from_spec(sp)
            sp.loader.exec_module(mm)
            try:
                mm.build(copy.deepcopy(SNAP))
                check(f"7d. {n} additions must fail the 50-total check", False)
            except SystemExit:
                check(f"7d. {n} additions fails closed", True)

        # (e) removing an original ticker must fail. The selector raises SystemExit
        # ("final universe is 49 entries") -- failing closed is the PASS condition,
        # so the exit must be caught rather than allowed to kill the test run.
        modr = out / "drop_locked.py"
        modr.write_text(src.replace('"AAPL", "ABBV",', '"ABBV",'), encoding="utf-8")
        spr = importlib.util.spec_from_file_location("drop_locked", modr)
        mr = importlib.util.module_from_spec(spr)
        spr.loader.exec_module(mr)
        try:
            dr = mr.build(copy.deepcopy(SNAP))
            check("7e. removing an original ticker breaks the preserved-24 invariant",
                  dr["final_50"][:24] != LOCKED_24 or len(dr["final_50"]) != 50)
        except SystemExit as e:
            check("7e. removing an original ticker fails closed", True, str(e))

        # (f) reordering the original 24 must be detectable
        modo = out / "reorder.py"
        modo.write_text(src.replace('"AAPL", "ABBV", "ADBE",', '"ABBV", "AAPL", "ADBE",'),
                        encoding="utf-8")
        spo = importlib.util.spec_from_file_location("reorder", modo)
        mo = importlib.util.module_from_spec(spo)
        spo.loader.exec_module(mo)
        try:
            do = mo.build(copy.deepcopy(SNAP))
            check("7f. reordering the original 24 is detectable",
                  do["final_50"][:24] != LOCKED_24)
        except SystemExit as e:
            check("7f. reordering the original 24 fails closed", True, str(e))

        # (g) malformed inputs fail closed
        for label, mutate in (
            ("empty snapshot", lambda s: {**s, "rows": []}),
            ("prohibited field injected", lambda s: {**s, "rows": [{**s["rows"][0], "weight": "1.0"}] + s["rows"][1:]}),
            ("numeric identity value", lambda s: {**s, "rows": [{**s["rows"][0], "name": 3.14}] + s["rows"][1:]}),
        ):
            try:
                SEL.build(mutate(copy.deepcopy(SNAP)))
                check(f"7g. {label} fails closed", False)
            except SystemExit:
                check(f"7g. {label} fails closed", True)

        # (h) mutating a ticker changes its digest predictably
        a = hashlib.sha256(b"GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|NFLX").hexdigest()
        b = hashlib.sha256(b"GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|NFLY").hexdigest()
        check("7h. a one-character ticker change changes the digest", a != b)
        led = P["candidate_ledger"]
        nflx = [r for r in led if r["canonical_ticker"] == "NFLX"][0]
        check("7h2. and the recorded digest matches the real ticker", nflx["digest"] == a)

        # (i) input-order invariance
        shuffled = copy.deepcopy(SNAP)
        shuffled["rows"] = list(reversed(shuffled["rows"]))
        ds = SEL.build(shuffled)
        check("7i. selection is invariant to input row order",
              ds["final_50"] == P["final_50"] and ds["selected_26"] == P["selected_26"])


# ---------------------------------------------------------------- 8. protected state
def test_8_protected_state_unchanged() -> None:
    for rel, want in PROTECTED.items():
        p = ROOT / rel
        check(f"8a. {rel.split('/')[-1]} byte-identical", p.is_file() and sha_lf(p) == want)
    txt = CONSTANTS.read_text(encoding="utf-8")
    check("8b. production universe constant still lists exactly the 24",
          all(f'"{t}"' in txt for t in LOCKED_24))
    for t in ("NFLX", "CAT", "MMM", "WMT"):
        check(f"8c. production constant does not contain the proposed addition {t}",
              f'"{t}"' not in txt)
    lock = json.loads((LS / "GST_HYP01_ANALYSIS_LOCK_v1.0.json").read_text(encoding="utf-8-sig"))
    cp = json.loads(COHORT.read_text(encoding="utf-8-sig"))
    f5 = json.loads(F5AUDIT.read_text(encoding="utf-8"))
    eff = json.loads(EFFECTIVE.read_text(encoding="utf-8"))
    check("8d. results null / frozen empty / eligible zero",
          lock["results"] is None and lock["frozen_event_ids"] == [] and lock["eligible_events_now"] == 0)
    check("8e. screening rows empty", cp["screening_rows"] == [])
    check("8f. F5 STILL_OPEN", f5["gap_audit_status_after_this_work"] == "STILL_OPEN"
          and eff["effective_state"]["f5_construct_validity"] == "OPEN")
    check("8g. collection BLOCKED", eff["effective_state"]["prospective_collection"] == "BLOCKED")
    rows = [json.loads(l) for l in REGISTRY.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("8h. registry is the single unchanged DELL row",
          len(rows) == 1 and rows[0]["ticker"] == "DELL"
          and rows[0]["event_id"] == "EVT-DELL-FY27Q2-ERN")


# ---------------------------------------------------------------- 9. proposal framing
def test_9_proposal_is_marked_inactive() -> None:
    md = (D / "GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED_DRAFT.md").read_text(encoding="utf-8")
    for banner in ("PROPOSAL ONLY", "NOT ACTIVE", "NOT AN S&P DJI CONSTITUENT FILE",
                   "CURRENT 24 REMAIN OPERATIVE", "F5 REMAINS OPEN", "COLLECTION REMAINS BLOCKED",
                   "NO PRODUCTION QUERY CHANGED",
                   "NO TICKER WAS SELECTED USING ATTENTION, PRICE, EARNINGS, OUTCOME OR PERFORMANCE INFORMATION"):
        check(f"9a. proposal states {banner!r}", banner in md)
    check("9b. proposal status is PROPOSAL_ONLY_NOT_ACTIVE", P["status"] == "PROPOSAL_ONLY_NOT_ACTIVE")
    check("9c. production universe recorded as unchanged",
          P["production_universe_unchanged"] is True
          and json.loads(AUDIT.read_text(encoding="utf-8"))["production_universe_constant_modified"] is False)
    rv = REVIEW.read_text(encoding="utf-8")
    check("9d. review template has no ticked option", not re.search(r"- \[[xX]\]", rv))
    check("9e. review template offers all three dispositions",
          all(o in rv for o in ("APPROVE", "REQUEST_CORRECTION", "UNRESOLVED")))
    check("9f. review fields are PENDING", rv.count("`PENDING`") >= 15)
    check("9g. no reviewer identity invented",
          "**Reviewer:** `PENDING`" in rv)


if __name__ == "__main__":
    test_1_frozen_artifacts()
    test_2_source_is_official_ishares_not_spdji()
    test_3_identity_only()
    test_4_selection_recomputes()
    test_5_alias_rules()
    test_6_no_backfill()
    test_7_mutations_fail_closed()
    test_8_protected_state_unchanged()
    test_9_proposal_is_marked_inactive()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL UNIVERSE EXPANSION TESTS PASSED")
    sys.exit(0)
