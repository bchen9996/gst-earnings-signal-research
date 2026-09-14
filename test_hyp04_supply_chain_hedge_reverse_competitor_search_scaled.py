#!/usr/bin/env python3
"""run_hyp07_reverse_competitor_search_scaled.py tests -- this module adds
NO new anchor-merge logic of its own (load_expanded_anchor_universe is
imported unchanged from round 6's already-tested
run_hyp05_reverse_concentration_search_scaled.py, and already covered by
test_hyp04_supply_chain_hedge_reverse_concentration_search_scaled.py). What
IS new here: that this module wires the competitor-specific pieces
(ANCHOR_NAME_VARIANTS/COMPETITOR_PHRASES/discover_leads/verify_lead) into
that shared scaling mechanism correctly, plus main()'s own pre-flight
refusals.

Fully offline, synthetic fixtures written to a temp dir. Sockets blocked
before import.

Run directly: python test_hyp04_supply_chain_hedge_reverse_competitor_search_scaled.py
"""
from __future__ import annotations

import socket
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import io  # noqa: E402
from contextlib import redirect_stderr, redirect_stdout  # noqa: E402

from hyp04_supply_chain_hedge import (  # noqa: E402
    run_hyp05_reverse_concentration_search_scaled as SCALED_CONCENTRATION,
    run_hyp07_reverse_competitor_search as FIRST_PASS,
    run_hyp07_reverse_competitor_search_scaled as M,
)

FAILURES: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="hyp07_scaled_search_test_"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_imports_the_shared_merge_function_unchanged() -> None:
    check("1a. load_expanded_anchor_universe is the SAME function object "
          "round 6's own scaled module defines -- not a reimplementation",
          M.load_expanded_anchor_universe is
          SCALED_CONCENTRATION.load_expanded_anchor_universe)
    check("1b. PROVENANCE_HAND_CURATED constant is shared, not redefined",
          M.PROVENANCE_HAND_CURATED == SCALED_CONCENTRATION.PROVENANCE_HAND_CURATED)
    check("1c. PROVENANCE_RUSSELL1000_PROXY constant is shared",
          M.PROVENANCE_RUSSELL1000_PROXY == SCALED_CONCENTRATION.PROVENANCE_RUSSELL1000_PROXY)


def test_2_wires_competitor_specific_pieces_not_concentration_ones() -> None:
    check("2a. discover_leads is the competitor module's own function, "
          "not customer/supplier's",
          M.discover_leads is FIRST_PASS.discover_leads)
    check("2b. verify_lead is the competitor module's own function",
          M.verify_lead is FIRST_PASS.verify_lead)
    check("2c. ANCHOR_NAME_VARIANTS is the competitor first pass's own 27 "
          "anchors (itself imported from round 4's customer/supplier "
          "module), not redefined here",
          M.ANCHOR_NAME_VARIANTS is FIRST_PASS.ANCHOR_NAME_VARIANTS)
    check("2d. COMPETITOR_PHRASES is the competitor module's own phrase set",
          M.COMPETITOR_PHRASES == FIRST_PASS.COMPETITOR_PHRASES)
    check("2e. source tag is the competitor-search tag, not the "
          "concentration one",
          M.SOURCE_REVERSE_COMPETITOR_SEARCH ==
          FIRST_PASS.SOURCE_REVERSE_COMPETITOR_SEARCH)
    check("2f. hypothesis_id used in the merge would be HYP-07's own anchor "
          "set -- confirmed by checking a real anchor (JBL) present in it",
          "JBL" in M.ANCHOR_NAME_VARIANTS)


def test_3_merge_against_the_real_repo_proxy_csv_does_not_crash() -> None:
    """Control: merging the ACTUAL Russell1000Proxy_Filtered_Universe.csv
    against HYP-07's own hand-curated set must produce a plausible-sized
    universe -- not a crash, not an empty one."""
    if not M.RUSSELL1000_PROXY_CSV.is_file():
        check("3a. the real proxy CSV is present on disk", False,
              str(M.RUSSELL1000_PROXY_CSV))
        return
    variants, provenance = M.load_expanded_anchor_universe(
        hand_curated=M.ANCHOR_NAME_VARIANTS)
    check("3a. merging against the real files produces more anchors than "
          "the first pass's 27 alone",
          len(variants) > 27, str(len(variants)))
    check("3b. every hand-curated (competitor first-pass) anchor survives "
          "the merge",
          all(t in variants for t in M.ANCHOR_NAME_VARIANTS),
          str(set(M.ANCHOR_NAME_VARIANTS) - set(variants)))
    check("3c. provenance covers every anchor, no anchor untagged",
          set(provenance) == set(variants))


def test_4_main_refuses_to_overwrite_existing_outputs() -> None:
    existing = TMP / "already_there.json"
    existing.write_text("{}", encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(["--out-name-search", str(existing),
                      "--out-linkage", str(TMP / "does_not_exist_1.json"),
                      "--out-raw-hits", str(TMP / "does_not_exist_2.json")])
    check("4a. refuses with a non-zero exit when an out path already exists",
          code != 0, str(code))
    check("4b. says why, on stderr", "already exists" in err.getvalue(),
          err.getvalue()[:200])
    check("4c. the existing file is untouched",
          existing.read_text(encoding="utf-8") == "{}")


def test_5_main_refuses_on_a_missing_proxy_csv() -> None:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(["--out-name-search", str(TMP / "ns2.json"),
                      "--out-linkage", str(TMP / "lk2.json"),
                      "--out-raw-hits", str(TMP / "rh2.json"),
                      "--proxy-csv", str(TMP / "does_not_exist.csv")])
    check("5a. refuses with a non-zero exit on a missing proxy csv",
          code != 0, str(code))
    check("5b. names the missing path", "does_not_exist.csv" in err.getvalue(),
          err.getvalue()[:200])


def test_6_dry_run_prints_a_plan_and_writes_nothing() -> None:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(["--out-name-search", str(TMP / "ns3.json"),
                      "--out-linkage", str(TMP / "lk3.json"),
                      "--out-raw-hits", str(TMP / "rh3.json")])
    check("6a. dry run exits 0", code == 0, str(code))
    check("6b. prints the anchor/query-count plan",
          "planned unscoped searches" in out.getvalue(), out.getvalue()[:300])
    check("6c. writes nothing without --yes-run-live",
          not (TMP / "ns3.json").exists())


def test_7_checkpoint_round_trips_and_starts_empty_when_absent() -> None:
    p = TMP / "does_not_exist_yet.checkpoint.json"
    cp = M._load_checkpoint(p)
    check("7a. loading a nonexistent checkpoint returns an empty, "
          "well-shaped structure, not a crash",
          cp == {"discovery": {}, "verification": {}}, str(cp))

    cp["discovery"]["AAPL"] = [{"peer_cik": "0000000001"}]
    cp["verification"]["AAPL|0000000001"] = {"filed_mention_confirmed": True}
    M._save_checkpoint(p, cp)
    check("7b. save creates the checkpoint file", p.is_file())

    reloaded = M._load_checkpoint(p)
    check("7c. a reloaded checkpoint round-trips exactly",
          reloaded == cp, str(reloaded))

    check("7d. no stray .tmp file left behind after a save",
          not p.with_suffix(".tmp").exists())


def test_8_verification_key_is_the_anchor_peer_cik_pair() -> None:
    lead = {"anchor_ticker": "AAPL", "peer_cik": "0000000001",
           "peer_registrant_name": "SOME CO"}
    check("8a. verification key combines anchor_ticker and peer_cik",
          M._verification_key(lead) == "AAPL|0000000001")

    lead_other_anchor = {**lead, "anchor_ticker": "GOOGL"}
    check("8b. the SAME peer_cik under a DIFFERENT anchor gets a DIFFERENT "
          "key -- the same (anchor_ticker, peer_cik) discipline this "
          "project already applies everywhere else",
          M._verification_key(lead_other_anchor) != M._verification_key(lead))


def test_9_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("9a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("9a. network blocked", True)


if __name__ == "__main__":
    test_1_imports_the_shared_merge_function_unchanged()
    test_2_wires_competitor_specific_pieces_not_concentration_ones()
    test_3_merge_against_the_real_repo_proxy_csv_does_not_crash()
    test_4_main_refuses_to_overwrite_existing_outputs()
    test_5_main_refuses_on_a_missing_proxy_csv()
    test_6_dry_run_prints_a_plan_and_writes_nothing()
    test_7_checkpoint_round_trips_and_starts_empty_when_absent()
    test_8_verification_key_is_the_anchor_peer_cik_pair()
    test_9_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP07_REVERSE_COMPETITOR_SEARCH_SCALED TESTS PASSED")
    sys.exit(0)
