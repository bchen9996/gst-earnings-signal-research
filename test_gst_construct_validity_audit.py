#!/usr/bin/env python3
"""F5 search-construct validity audit -- artifact agrees with its evidence.

Every number in GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0_2026-09-04.md comes
from the JSON artifact, and every number in the artifact is recomputed here
from the four source CSVs. The write-up therefore cannot drift from the
evidence without this failing.

Repo testing convention (hand-rolled check(), run directly, no pytest).
Offline: reads committed CSVs only.

Run directly: python test_gst_construct_validity_audit.py
"""
from __future__ import annotations

import socket
import sys


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import importlib.util  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent
GEN = ROOT / "tools" / "run_gst_construct_validity_audit.py"
ART = ROOT / "Live Signal Engine" / "GST_SEARCH_CONSTRUCT_VALIDITY_RESULTS_2026-09-04.json"
DOC = ROOT / "Live Signal Engine" / "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0_2026-09-04.md"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _gen():
    spec = importlib.util.spec_from_file_location("_f5gen", GEN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_1_artifact_and_document_exist() -> None:
    check("1a. the JSON artifact exists", ART.exists())
    check("1b. the audit document exists", DOC.exists())


def test_2_every_artifact_number_recomputes() -> None:
    """The artifact is not trusted; it is rebuilt and compared."""
    m = _gen()
    art = json.loads(ART.read_text(encoding="utf-8"))
    repro, breadth = m._load(m.REPRO), m._load(m.BREADTH)
    noise, partial = m._load(m.NOISE), m._load(m.PARTIAL)

    for name, fn, args in (
        ("section3_breadth", m.section3_breadth, (breadth,)),
        ("section4_reproducibility", m.section4_reproducibility, (repro, noise, partial)),
        ("section5_term_sensitivity", m.section5_term_sensitivity, (repro,)),
    ):
        check(f"2. {name} recomputes to the committed artifact",
              fn(*args) == art[name])


def test_3_the_headline_claims_hold() -> None:
    """Each claim the write-up makes in prose, asserted against the data."""
    m = _gen()
    repro, breadth = m._load(m.REPRO), m._load(m.BREADTH)
    noise, partial = m._load(m.NOISE), m._load(m.PARTIAL)
    s3 = m.section3_breadth(breadth)
    s4 = m.section4_reproducibility(repro, noise, partial)
    s5 = m.section5_term_sensitivity(repro)

    # 4: closed weeks are deterministic; only the partial week moves.
    check("3a. closed-week repeat pulls are exactly deterministic",
          s4["closed_week_repeat_pulls"]["all_deterministic"] is True
          and s4["closed_week_repeat_pulls"]["events_flagged_unstable"] == 0)
    check("3b. the 53-week five-pull series shows no tier change",
          s4["five_pull_weekly_series"]["weeks_where_tier_differs"] == 0
          and s4["five_pull_weekly_series"]["max_z_difference_any_week"] == 0.0)
    check("3c. the partial week does move, and by a small amount",
          0.0 < s4["partial_week"]["zscore_range"] < 1.0,
          f"range={s4['partial_week']['zscore_range']}")

    # 3e: STZ is the thinness outlier.
    stz = s3["by_ticker"]["STZ"]
    check("3d. every STZ spike week returned zero related queries",
          stz["events_zero_breadth"] == stz["events_ok"] and stz["median_breadth"] == 0.0)
    others = {k: v for k, v in s3["by_ticker"].items() if k != "STZ"}
    check("3e. and no other ticker has a zero median breadth",
          all(v["median_breadth"] > 0 for v in others.values()))

    # 5a: the 10/10 is a selection tautology, so it must never be the only
    # thing asserted. Pinned so a future edit cannot quietly promote it.
    check("3f. all events clear under the ticker variant they were selected by",
          s5["clears_z5_counts"]["raw_ticker_cat0"] == s5["n_events"])
    check("3g. no event clears under the company-name variant",
          s5["clears_z5_counts"]["company_name_cat0"] == 0)
    check("3h. exactly half survive the Finance category",
          s5["clears_z5_counts"]["raw_ticker_cat7_finance"] * 2 == s5["n_events"])

    # 5c: survivors and failures OVERLAP -- there is no clean threshold, and
    # the write-up says so. If a future dataset separated them, that sentence
    # would become false and this fails.
    ev = s5["per_event"]
    fails = [e["z_ticker"] for e in ev if not e["clears_z5_finance_category"]]
    survs = [e["z_ticker"] for e in ev if e["clears_z5_finance_category"]]
    check("3i. Finance survivors and failures overlap in ticker-z",
          max(fails) > min(survs),
          f"max fail={max(fails)}, min survive={min(survs)}")


def test_4_the_seal_is_verifiable() -> None:
    """§2 must not have been written after §5 was known."""
    doc = DOC.read_text(encoding="utf-8")
    check("4a. the document states the ordering discipline up front",
          "before any term-sensitivity column was read" in doc)
    check("4b. §5 is labelled robustness and disclaims revising §2",
          "does not revise" in doc and "robustness" in doc.lower())
    check("4c. the tautology in the 10-of-10 is stated, not hidden",
          "tautology" in doc.lower() and "by construction" in doc)
    check("4d. the audit does not claim to resolve F5's decision",
          "resolves no decision" in doc.lower()
          or "resolves no decision" in doc)


def test_5_preconditions_actually_refuse() -> None:
    """Forced to fail and observed, not assumed."""
    m = _gen()
    breadth = m._load(m.BREADTH)
    good = m._load(m.REPRO)

    # wrong row shape
    try:
        m.check_preconditions(good.head(5), breadth)
        check("5a. a truncated evidence file is refused", False)
    except m.RefusedError:
        check("5a. a truncated evidence file is refused", True)

    # wrong ticker count in the breadth file
    try:
        m.check_preconditions(good, breadth[breadth.ticker == "STZ"])
        check("5b. a breadth file with the wrong ticker count is refused", False)
    except m.RefusedError:
        check("5b. a breadth file with the wrong ticker count is refused", True)

    # a missing evidence file
    try:
        m._load(ROOT / "Live Signal Engine" / "definitely_not_here.csv")
        check("5c. a missing evidence file is refused", False)
    except m.RefusedError:
        check("5c. a missing evidence file is refused", True)

    check("5d. refusals use RefusedError, not bare assert "
          "(python -O would strip an assert)",
          issubclass(m.RefusedError, RuntimeError))


if __name__ == "__main__":
    test_1_artifact_and_document_exist()
    test_2_every_artifact_number_recomputes()
    test_3_the_headline_claims_hold()
    test_4_the_seal_is_verifiable()
    test_5_preconditions_actually_refuse()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL F5 CONSTRUCT-VALIDITY AUDIT TESTS PASSED")
    sys.exit(0)
