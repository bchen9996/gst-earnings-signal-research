#!/usr/bin/env python3
# Deterministic tests for the round-1 evidence audit and correction overlay.
#
# Offline. No retrieval, no socket, no candidate lookup, no round 2.
#
# Run directly: python test_market_response_round1_correction_overlay.py

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline audit")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

_BANNED_TOP = {"yfinance", "pytrends", "requests", "urllib3", "httpx", "aiohttp"}


class _BanProviders:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in _BANNED_TOP:
            raise ImportError("BLOCKED provider import: " + fullname)
        return None


sys.meta_path.insert(0, _BanProviders())

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(HERE))

from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE  # noqa: E402

DIR = HERE / "Live Signal Engine" / "Cohort_Screening_Round1"
LSE = HERE / "Live Signal Engine"
OVERLAY = json.loads((DIR / "ROUND1_CORRECTION_OVERLAY_v1.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((DIR / "SWEEP_MANIFEST_ROUND1.json").read_text(encoding="utf-8"))
P1 = json.loads((DIR / "sweep_raw_round1.json").read_text(encoding="utf-8"))
AUDIT = (DIR / "ROUND1_EVIDENCE_AUDIT.md").read_text(encoding="utf-8")
RUNBOOK = (DIR / "ROUND2_RENDERER_RUNBOOK.md").read_text(encoding="utf-8")
REGISTRY_P = LSE / "Market_Response_Event_Registry" / "registry.jsonl"

PROTOCOL_DISPOSITIONS = {
    d["code"] for d in json.loads(
        (LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json").read_text(encoding="utf-8"))["dispositions"]
}

PROHIBITED_FIELD = re.compile(
    r"gst_zscore|wiki_zscore|previous_close|realized_vol|implied_vol|straddle|option_"
    r"|surprise|analyst|news_tone|\bpnl\b|sharpe|\breturn\b", re.I)

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


def sha_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ===== 1. originals hash-locked and unchanged =============================

def test_1_originals_unchanged():
    declared = OVERLAY["original_artifacts_sha256_lf"]
    for name, want in declared.items():
        check(f"1. {name} matches its declared hash", sha_lf(DIR / name) == want)
    check("1b. the overlay declares the originals were not rewritten",
          OVERLAY["originals_rewritten"] is False)
    # And they must equal what is committed at HEAD. This comparison needs a git
    # work tree; a clean `git archive` export deliberately has no .git, so there
    # it is reported NOT APPLICABLE rather than failed. The declared-hash lock
    # above runs everywhere and is the load-bearing check.
    import subprocess
    in_git = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(HERE),
                            capture_output=True).stdout.strip() == b"true"
    if not in_git:
        print("NOTE: 1c. git HEAD comparison NOT APPLICABLE (no git work tree; "
              "declared-hash lock in 1. still enforced)")
    else:
        for name in declared:
            rel = (DIR / name).relative_to(HERE).as_posix()
            head = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=str(HERE),
                                  capture_output=True).stdout
            check(f"1c. {name} is byte-identical to the committed version",
                  hashlib.sha256(head).hexdigest() == sha_lf(DIR / name))
    check("1d. the audit document reproduces the same hashes",
          all(h in AUDIT for h in declared.values()))


# ===== 2. every correction references a real original row =================

def test_2_corrections_reference_real_rows():
    manifest_urls = {(r["ticker"], c["url"])
                     for r in MANIFEST["rows"] for c in r["checked_sources"]}
    manifest_tickers = {r["ticker"] for r in MANIFEST["rows"]}
    bad = []
    for c in OVERLAY["corrections"]:
        if c["url"] is not None:
            if (c["ticker"], c["url"]) not in manifest_urls:
                bad.append(c)
        elif c["ticker"] not in manifest_tickers:
            bad.append(c)
    check(f"2. every correction references a real original row (orphans={len(bad)})", not bad)
    check("2b. every correction records the original value",
          all(c.get("original_value") for c in OVERLAY["corrections"]))
    check("2c. every correction records the effective value",
          all("effective_value" in c for c in OVERLAY["corrections"]))
    check("2d. every correction gives a plain-language reason",
          all(len(c.get("reason", "")) > 30 for c in OVERLAY["corrections"]))
    check("2e. the overlay records the sweep round, PR head and cadence commit",
          OVERLAY["sweep_round"] == 1
          and OVERLAY["pr_head_audited"] == "12400f8c9394de5741bb37269dbf6e392b9245ad"
          and OVERLAY["cadence_commit"] == "153c62392131e86c7538c1c71b85d631039d8cc6")
    check("2f. the overlay records its authoring timestamp",
          re.match(r"20\d\d-\d\d-\d\dT", OVERLAY["authored_at_utc"] or ""))
    check("2g. every URL in the manifest is classified exactly once",
          len(OVERLAY["url_classifications"])
          == sum(len(r["checked_sources"]) for r in MANIFEST["rows"]))


# ===== 3. DVN spill-prevention =============================================

def test_3_dvn_invalid():
    spill = [u for u in OVERLAY["url_classifications"]
             if u["url"] == "https://www.devonenergy.com/sustainability/environment/spill-prevention"]
    check("3. the DVN spill-prevention URL is classified", len(spill) == 1)
    u = spill[0]
    check("3b. it is INVALID_OR_UNRELATED", u["effective_role"] == "INVALID_OR_UNRELATED")
    check("3c. it may not support a disposition", u["may_support_a_disposition"] is False)
    check("3d. the original mislabel is preserved in the overlay",
          u["original_source_type"] == "company_ir_events_calendar")
    check("3e. a correction row exists for it",
          any(c["url"] == u["url"] and c["kind"] == "SOURCE_TYPE_MISCLASSIFICATION"
              for c in OVERLAY["corrections"]))
    check("3f. the audit explains the substring root cause",
          "prevention" in AUDIT.lower() and "event" in AUDIT)
    # the search was not limited to DVN
    misc = [c for c in OVERLAY["corrections"] if c["kind"] == "SOURCE_TYPE_MISCLASSIFICATION"]
    check(f"3g. the misclassification search covered more than DVN ({len(misc)} found)",
          len(misc) > 1 and len({c["ticker"] for c in misc}) > 1)


# ===== 4-5. SEC submissions index and recent_8k ===========================

def test_4_5_sec_index():
    sec = [u for u in OVERLAY["url_classifications"] if "data.sec.gov/submissions" in u["url"]]
    check(f"4. every SEC submissions index is classified ({len(sec)})", len(sec) == 24)
    check("4b. all are RECONNAISSANCE_ONLY",
          all(u["effective_role"] == "RECONNAISSANCE_ONLY" for u in sec))
    check("4c. none may support a disposition",
          all(u["may_support_a_disposition"] is False for u in sec))
    r = OVERLAY["sec_submissions_index_rule"]
    check("4d. it is explicitly not a sec_filing_8k_earnings_date",
          r["is_sec_filing_8k_earnings_date"] is False)
    joined = " ".join(r["rules"])
    check("4e. an accession/date/Item 2.02 label establishes no candidate",
          "Item 2.02" in joined and "NO upcoming candidate" in joined)
    check("4f. a specific 8-K counts only once opened and explicit",
          "only after the exact filing is opened" in joined)
    check("4g. no filing content was opened in round 1",
          "NO FILING CONTENT WAS OPENED IN ROUND 1" in joined)
    m = r["recent_8k_metadata"]
    check("5. recent_8k metadata is retained in the raw artifact",
          m["retained_in_raw_artifact"] is True)
    check("5b. it is marked unused in the effective decision",
          m["used_in_effective_decision"] is False)
    check("5c. its use is prohibited", m["prohibited_from_use"] is True)
    # it must genuinely still be present in the untouched raw artifact
    present = any("recent_8k" in a for row in P1["rows"] for a in row["checked_urls"])
    check("5d. recent_8k is still physically present in the raw artifact", present)
    check("5e. future sweeps are told not to store it without an opened filing",
          "should not store recent-8-K lists" in m["future_guidance"])


# ===== 6-7. effective dispositions =======================================

def test_6_7_effective_dispositions():
    eff = {e["ticker"]: e for e in OVERLAY["effective_ticker_outcomes"]}
    check("6. every locked ticker has an effective outcome",
          set(eff) == set(LOCKED_24_TICKER_UNIVERSE))
    non_dell = [e for t, e in eff.items() if t != "DELL"]
    check("6b. every non-DELL effective proposed_disposition is null",
          all(e["effective_proposed_disposition"] is None for e in non_dell))
    check("6c. none is a canonical protocol disposition",
          all(e["is_canonical_protocol_disposition"] is False
              for e in eff.values()))
    check("6d. every non-DELL status is the noncanonical reconnaissance label",
          all(e["effective_status"] == "NO_ENROLLMENT_DECISION_REACHED" for e in non_dell))
    check("6e. the original pending values remain visible for comparison",
          all(e["original_proposed_disposition"] == "PENDING_OFFICIAL_DATE_UNAVAILABLE"
              for e in non_dell))
    check("6f. every non-DELL ticker stays eligible for the next scheduled sweep",
          all(e["remains_eligible_for_next_scheduled_sweep"] is True for e in non_dell))
    lab = OVERLAY["noncanonical_status_label"]
    check("7. the label is declared NOT one of the twelve protocol dispositions",
          lab["is_one_of_the_twelve_protocol_dispositions"] is False)
    check("7b. and it genuinely is not one", lab["label"] not in PROTOCOL_DISPOSITIONS)
    check("7c. no effective status is a protocol disposition code",
          not ({e["effective_status"] for e in eff.values()} & PROTOCOL_DISPOSITIONS))
    check("7d. the canonical-pending rule requires a real candidate identity",
          "ticker AND fiscal period" in OVERLAY["canonical_pending_rule"])
    check("7e. no fiscal period was fabricated",
          all(r["official_fiscal_period_label"] is None for r in MANIFEST["rows"]))


# ===== 8-10. round-2 sets ================================================

def test_8_10_round2_sets():
    s = OVERLAY["round2_sets"]
    cr = s["client_rendered_official_calendars"]
    check("8. renderer-required entries are enumerated with ticker and URL",
          cr and all(e.get("ticker") and e.get("url") for e in cr))
    check("8b. each states why static HTML was insufficient",
          all("client-side" in e["why_static_html_insufficient"] for e in cr))
    check("8c. each states whether rendering or human observation is required",
          all(e["browser_rendering_required"] is True
              and e["human_observation_acceptable_alternative"] is True for e in cr))
    check("8d. none of them was inaccessible",
          all(e["was_inaccessible"] is False for e in cr))
    check("8e. the count is recomputed, not assumed to be ten",
          s["client_rendered_ticker_count"] == len({e["ticker"] for e in cr}))
    af = s["access_failures"]
    check("9. access failures are a separate set", isinstance(af, list) and af)
    check("9b. every access-failure entry names at least one URL",
          all(e["urls"] for e in af))
    check("9c. access failure is explicitly not issuer-confirmed absence",
          all("NOT issuer-confirmed absence" in e["note"] for e in af))
    cr_t = {e["ticker"] for e in cr}
    af_t = {e["ticker"] for e in af}
    check("9d. no ticker is both client-rendered and an access failure", not (cr_t & af_t))
    ia = s["issuer_stated_no_upcoming_event"]
    check("10. issuer-stated absence is a separate set", isinstance(ia, list) and ia)
    ia_t = {e["ticker"] for e in ia}
    check("10b. issuer-stated absence never overlaps a parser/renderer failure",
          not (ia_t & cr_t) and not (ia_t & af_t))
    check("10c. each absence entry cites the issuer page it came from",
          all(e.get("url") and "issuer" in e["basis"] for e in ia))
    nc = s["no_events_calendar_located"]
    check("10d. a discovery gap is distinct from both failure and absence",
          not ({e["ticker"] for e in nc} & (cr_t | af_t | ia_t)))
    # every non-DELL ticker bucketed exactly once
    allocated = list(cr_t) + [e["ticker"] for e in af] + [e["ticker"] for e in ia] \
        + [e["ticker"] for e in nc]
    check(f"10e. all 23 non-DELL tickers are bucketed exactly once (got {len(allocated)})",
          sorted(allocated) == sorted(t for t in LOCKED_24_TICKER_UNIVERSE if t != "DELL"))
    check("10f. the conclusion forbids calling retrieval failure absence",
          "never described as issuer-confirmed absence"
          in OVERLAY["round1_conclusion"]["retrieval_failure_is_not_absence"])


# ===== 11-13. DELL, registry, screening log ==============================

def test_11_13_untouched():
    eff = {e["ticker"]: e for e in OVERLAY["effective_ticker_outcomes"]}
    d = eff["DELL"]
    check("11. DELL is the existing enrolled event, unchanged",
          d["effective_status"] == "EXISTING_ENROLLED_EVENT_UNCHANGED"
          and d["existing_event_id"] == "EVT-DELL-FY27Q2-ERN")
    check("11b. the conclusion lists exactly one unchanged enrolled event",
          OVERLAY["round1_conclusion"]["existing_enrolled_events_unchanged"]
          == ["EVT-DELL-FY27Q2-ERN"])
    raw = REGISTRY_P.read_bytes()
    check("12. the DELL registry is byte-identical to the baseline",
          hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
          == "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974")
    rows = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    check("12b. exactly one verified REGISTRATION row",
          len(rows) == 1 and rows[0]["verification_status"] == "verified")
    check("13. no canonical screening log exists",
          not (LSE / "Market_Response_Event_Registry" / "cohort_screening_log.jsonl").exists())
    c = OVERLAY["round1_conclusion"]
    check("13b. zero enrollable candidates", c["enrollable_candidates_established"] == 0)
    check("13c. zero canonical dispositions", c["canonical_candidate_dispositions_written"] == 0)
    check("13d. zero registry rows", c["registry_rows_written"] == 0)
    check("13e. zero human verifications", c["human_verifications_completed"] == 0)
    check("13f. round 1 is labelled reconnaissance, not a screening decision",
          "RECONNAISSANCE EVIDENCE" in c["classification"]
          and "not a completed canonical screening decision" in c["classification"])
    check("13g. no event log or stage marker exists",
          not list(HERE.rglob("EVT-*.jsonl")) and not list(HERE.rglob("EVT-*_MARKER.json")))


# ===== 14-15. prohibited fields; no network module =======================

def test_14_15_prohibitions():
    conclusion = json.dumps(OVERLAY["round1_conclusion"])
    hit = PROHIBITED_FIELD.search(conclusion)
    check(f"14. no prohibited research field in the effective conclusion "
          f"(hit={hit.group(0) if hit else None})", not hit)
    # the runbook names prohibited data only inside its own prohibition section
    offending = [ln.strip()[:80] for ln in RUNBOOK.splitlines()
                 if PROHIBITED_FIELD.search(ln)
                 and not re.search(r"\bno\b|never|not\b|prohibit|stop|may not", ln, re.I)]
    check(f"14b. every prohibited-data mention in the runbook is a prohibition "
          f"(offenders={offending})", not offending)
    check("14c. the runbook forbids search engines and third-party calendars",
          "No search engines" in RUNBOOK and "third-party calendars" in RUNBOOK)
    check("14d. the runbook requires screenshot plus DOM text hash",
          "screenshot" in RUNBOOK and "DOM text hash" in RUNBOOK)
    check("14e. the runbook forbids a registry or ENROLLED row before human verification",
          "until a named human verifies" in RUNBOOK)
    check("14f. the runbook has a hard stop on unisolatable prohibited data",
          "Stop immediately" in RUNBOOK)
    check("14g. the runbook is scheduled, not immediate",
          "Monday 09:00 America/Chicago" in RUNBOOK
          and "Do not execute this during the audit pass" in RUNBOOK)

    # this audit itself must not use a network module
    for name in ("build_correction_overlay.py",):
        tree = ast.parse((DIR / name).read_text(encoding="utf-8"))
        imported = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imported |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                imported.add(n.module)
        net = sorted(m for m in imported
                     if re.match(r"urllib\.request|http|socket|requests|ssl", m))
        check(f"15. {name} imports no network module (found={net})", not net)
    reached = []
    for host in ("www.sec.gov", "investors.delltechnologies.com"):
        try:
            socket.create_connection((host, 443), timeout=2)
            reached.append(host)
        except NetworkBlocked:
            pass
        except Exception:  # noqa: BLE001
            pass
    check(f"15b. sockets are blocked during this audit (reached={reached})", not reached)
    leaked = sorted(m for m in sys.modules if m.split(".")[0] in _BANNED_TOP)
    check(f"15c. no provider module reached sys.modules (leaked={leaked})", not leaked)


if __name__ == "__main__":
    test_1_originals_unchanged()
    test_2_corrections_reference_real_rows()
    test_3_dvn_invalid()
    test_4_5_sec_index()
    test_6_7_effective_dispositions()
    test_8_10_round2_sets()
    test_11_13_untouched()
    test_14_15_prohibitions()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL ROUND-1 CORRECTION OVERLAY TESTS PASSED")
    sys.exit(0)
