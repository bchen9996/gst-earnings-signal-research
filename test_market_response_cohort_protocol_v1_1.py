#!/usr/bin/env python3
# Deterministic tests for cohort protocol v1.1 -- the screening cadence.
#
# Protocol-definition tests only. No candidate screening, no provider, no
# socket, no observation.
#
# Run directly: python test_market_response_cohort_protocol_v1_1.py

from __future__ import annotations

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
    raise NetworkBlocked("network access attempted during protocol validation")


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

LSE = HERE / "Live Signal Engine"
V10_J = LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0.json"
V10_M = LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0_DRAFT.md"
V11_J = LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json"
V11_M = LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1_DRAFT.md"

V10 = json.loads(V10_J.read_text(encoding="utf-8"))
V11 = json.loads(V11_J.read_text(encoding="utf-8"))
MD = V11_M.read_text(encoding="utf-8")
CAD = V11["screening_cadence"]

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


# ===================== 1. the cadence itself ===============================

def test_1_cadence():
    check("1. version is 1.1", V11["protocol_version"] == "1.1")
    check("1b. initial sweep is immediately after the v1.1 push",
          "immediately after the v1.1 commit is pushed" in CAD["initial_sweep"]["when"])
    check("1c. initial sweep covers the full locked universe",
          "locked 24-ticker universe" in CAD["initial_sweep"]["scope"])
    r = CAD["recurring_sweep"]
    check("1d. recurring sweep is Monday", r["day"] == "Monday")
    check("1e. at 09:00", r["time_local"] == "09:00")
    check("1f. America/Chicago", r["timezone"] == "America/Chicago")
    m = CAD["missed_sweep_rule"]
    check("1g. a missed sweep runs the next available calendar day",
          m["policy"] == "run_on_next_available_calendar_day_and_record_the_delay")
    check("1h. a sweep is never silently skipped",
          m["never_silently_skipped"] is True and "never silently skipped" in m["statement"])
    check("1i. the delay and its cause are recorded",
          "documented technical failure" in m["statement"].lower()
          and "delay is recorded" in m["statement"])
    check("1j. a missed sweep is never back-dated", "never back-dated" in m["statement"])
    for needle in ("Monday", "09:00", "America/Chicago",
                   "next available calendar day", "never silently skipped"):
        check(f"1k. the Markdown states: {needle}", needle in MD)


def test_2_who_stays_on_cadence():
    who = " | ".join(CAD["who_stays_on_the_cadence"])
    check("2. pending candidates stay until enrolled or terminal",
          "until it is enrolled or receives a terminal disposition" in who)
    check("2b. enrolled events stay until their anchor begins",
          "until its pre-event anchor begins" in who)
    check("2c. enrolled recheck is date/time amendments only",
          "SOLELY to detect official date/time amendments" in who)
    check("2d. an enrolled recheck may never revisit enrollment",
          "never revisit enrollment itself" in CAD["enrolled_event_recheck_scope"])


def test_3_blinding_and_triggers():
    check("3. re-screening uses the same v1.0 permitted inputs and blinding",
          "v1.0 permitted inputs" in CAD["inputs_and_blinding"]
          and "blinding prohibitions" in CAD["inputs_and_blinding"])
    check("3b. nothing about a re-screen relaxes either",
          "relaxes either" in CAD["inputs_and_blinding"])
    trig = [t.lower() for t in CAD["no_unscheduled_rescreen_triggers"]]
    for needle in ("attention", "price", "volatility", "news", "options",
                   "earnings results", "perceived interestingness"):
        check(f"3c. '{needle}' cannot trigger an unscheduled re-screen", needle in trig)
    check("3d. a re-screen happens because the calendar says so",
          "because the calendar says so" in CAD["unscheduled_rescreen_rule"])
    check("3e. reaching 60 does not stop enrollment",
          "does NOT stop enrollment" in CAD["target_does_not_stop_enrollment"])
    check("3f. a cadence change needs a new dated version written beforehand",
          "written before the sweep it would affect" in CAD["cadence_change_rule"])


# ===================== 4. additive: v1.0 unchanged =========================

def test_4_additive_only():
    s = V11["supersedes"]
    check("4. v1.1 supersedes v1.0 prospectively only", s["mode"] == "prospective_only")
    check("4b. v1.0 is declared preserved byte-for-byte",
          s["v1_0_preserved_byte_for_byte"] is True)
    check("4c. the only methodological addition is the cadence",
          s["only_methodological_addition"] == "screening_cadence")
    check("4d. nothing decided under v1.0 is re-decided",
          "Nothing decided under v1.0 is re-decided" in s["statement"])
    # every substantive v1.0 rule carried forward identically
    for key in ("locked_universe", "collection_window", "target",
                "minimum_registration_lead", "inclusion_rules",
                "permitted_official_source_types", "prohibited_exclusion_reasons",
                "amendment_rules", "blinding_prohibitions",
                "relationship_to_v0_2_completeness", "analysis_separation",
                "display_gate", "enrollment_inputs", "derived_anchor"):
        check(f"4e. {key} is carried forward unchanged from v1.0", V11[key] == V10[key])
    check("4f. the universe still equals production, in order",
          V11["locked_universe"]["tickers"] == list(LOCKED_24_TICKER_UNIVERSE))
    check("4g. window unchanged", V11["collection_window"]["begins"] == "2026-09-01"
          and V11["collection_window"]["ends"] == "2027-05-31")
    check("4h. target unchanged", V11["target"]["min_registered_events"] == 60)
    check("4i. five-session lead unchanged",
          V11["minimum_registration_lead"]["sessions"] == 5)
    check("4j. all ten inclusion rules unchanged",
          [r["id"] for r in V11["inclusion_rules"]] == [f"INC-{i}" for i in range(1, 11)])
    # dispositions: same codes, same classes; only the dangling cadence
    # reference in ONE pending disposition is resolved
    codes10 = {d["code"]: d for d in V10["dispositions"]}
    codes11 = {d["code"]: d for d in V11["dispositions"]}
    check("4k. the disposition code set is unchanged", set(codes10) == set(codes11))
    check("4l. every disposition class is unchanged",
          all(codes10[c]["class"] == codes11[c]["class"] for c in codes10))
    changed = [c for c in codes10 if codes10[c] != codes11[c]]
    check(f"4m. exactly one disposition text changed (found={changed})",
          changed == ["PENDING_OFFICIAL_DATE_UNAVAILABLE"])
    check("4n. and it now points at the defined cadence",
          "Mondays 09:00 America/Chicago" in codes11["PENDING_OFFICIAL_DATE_UNAVAILABLE"]["meaning"])
    # The phrase still appears once, deliberately, where v1.1 QUOTES the v1.0
    # gap it is closing. What must not remain is a dangling reference inside a
    # rule -- so scope the check to the dispositions and the rule blocks.
    check("4o. no disposition still points at an undefined 'fixed cadence'",
          not any("fixed cadence" in d["meaning"] for d in V11["dispositions"]))
    check("4p. the only surviving mention is the quotation of the v1.0 gap",
          json.dumps(V11).count("fixed cadence") == 1
          and "fixed cadence" in CAD["why_this_exists"])


def test_5_v1_0_preserved_on_disk():
    # v1.0 must be byte-identical to what is committed at HEAD. This needs a git
    # work tree; a clean `git archive` export deliberately has none, so there it
    # is reported NOT APPLICABLE rather than failed. The field-by-field
    # carried-forward comparison in test_4 runs everywhere and is what actually
    # proves v1.1 is additive.
    import subprocess
    in_git = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(HERE),
                            capture_output=True).stdout.strip() == b"true"
    if not in_git:
        print("NOTE: 5. git HEAD comparison NOT APPLICABLE (no git work tree; "
              "test_4's field-by-field v1.0 comparison still enforced)")
        return
    for path in (V10_J, V10_M):
        rel = path.relative_to(HERE).as_posix()
        head = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=str(HERE),
                              capture_output=True).stdout
        disk = path.read_bytes().replace(b"\r\n", b"\n")
        check(f"5. {path.name} is byte-for-byte unchanged",
              hashlib.sha256(head).hexdigest() == hashlib.sha256(disk).hexdigest())


# ===================== 6. no candidates yet ================================

def test_6_no_candidates_yet():
    check("6. v1.1 carries zero screening rows", V11["screening_rows"] == [])
    check("6b. the note says it was published before the first IR page was inspected",
          "before the first candidate investor-relations page is inspected"
          in V11["screening_rows_note"].lower())
    check("6c. the Markdown says the same", "before the first candidate" in MD)
    ids = set(re.findall(r"EVT-[A-Z0-9-]+-FY\d{2}Q\d-[A-Z]+", json.dumps(V11) + MD))
    check(f"6d. no event id beyond the registered DELL event (found={sorted(ids)})",
          ids <= {"EVT-DELL-FY27Q2-ERN"})


def test_7_no_network():
    reached = []
    for host in ("investors.delltechnologies.com", "www.sec.gov", "trends.google.com"):
        try:
            socket.create_connection((host, 443), timeout=2)
            reached.append(host)
        except NetworkBlocked:
            pass
        except Exception:  # noqa: BLE001
            pass
    check(f"7. sockets are blocked in this test (reached={reached})", not reached)
    leaked = sorted(m for m in sys.modules if m.split(".")[0] in _BANNED_TOP)
    check(f"7b. no provider module reached sys.modules (leaked={leaked})", not leaked)


if __name__ == "__main__":
    test_1_cadence()
    test_2_who_stays_on_cadence()
    test_3_blinding_and_triggers()
    test_4_additive_only()
    test_5_v1_0_preserved_on_disk()
    test_6_no_candidates_yet()
    test_7_no_network()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL COHORT PROTOCOL v1.1 TESTS PASSED")
    sys.exit(0)
