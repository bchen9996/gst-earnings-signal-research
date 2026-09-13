#!/usr/bin/env python3
"""run_hyp05_reverse_concentration_search_scaled.py tests -- the anchor-
universe merge logic (load_expanded_anchor_universe) plus main()'s
pre-flight refusals. The LIVE search loop (discover_leads/verify_lead
themselves) is already tested in test_hyp04_supply_chain_hedge_reverse_
concentration_search.py and is NOT re-tested here -- this file only
covers what is NEW: merging round 4's hand-curated anchors with the
Russell1000-proxy universe.

Fully offline, synthetic fixtures written to a temp dir. Sockets blocked
before import.

Run directly: python test_hyp04_supply_chain_hedge_reverse_concentration_search_scaled.py
"""
from __future__ import annotations

import csv
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
    run_hyp05_reverse_concentration_search_scaled as M,
)

FAILURES: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="hyp05_scaled_search_test_"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


_PROXY_FIELDS = ("ticker", "company", "sector", "ambiguous_symbol",
                 "has_options", "n_expirations", "market_cap")


def _write_proxy_csv(rows: list[dict[str, str]]) -> Path:
    p = TMP / "proxy.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_PROXY_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({**{k: "" for k in _PROXY_FIELDS}, **r})
    return p


_HAND_CURATED = {"AAPL": ("Apple Inc.",), "NKE": ("NIKE, Inc.", "Nike, Inc.")}


def test_1_merge_adds_only_net_new_tickers() -> None:
    proxy = _write_proxy_csv([
        {"ticker": "AAL", "company": "American Airlines Group"},
        {"ticker": "aapl", "company": "Apple Inc"},  # already hand-curated, different case AND text
    ])
    variants, provenance = M.load_expanded_anchor_universe(
        hand_curated=_HAND_CURATED, proxy_csv=proxy)

    check("1a. a net-new proxy ticker is added",
          variants.get("AAL") == ("American Airlines Group",), str(variants.get("AAL")))
    check("1b. a ticker already hand-curated is NEVER overwritten, even "
          "case-insensitively, even though the proxy file's own company "
          "text differs",
          variants["AAPL"] == ("Apple Inc.",), str(variants["AAPL"]))
    check("1c. NKE (untouched by the proxy file at all) survives the "
          "merge unchanged",
          variants["NKE"] == ("NIKE, Inc.", "Nike, Inc."))
    check("1d. exactly 3 anchors total (2 hand-curated + 1 net-new)",
          len(variants) == 3, str(sorted(variants)))


def test_2_provenance_is_tagged_correctly() -> None:
    proxy = _write_proxy_csv([
        {"ticker": "AAL", "company": "American Airlines Group"},
        {"ticker": "AAPL", "company": "Apple Inc"},
    ])
    _variants, provenance = M.load_expanded_anchor_universe(
        hand_curated=_HAND_CURATED, proxy_csv=proxy)
    check("2a. the net-new ticker is tagged russell1000_proxy_company_name",
          provenance["AAL"] == M.PROVENANCE_RUSSELL1000_PROXY, str(provenance))
    check("2b. the already-hand-curated ticker stays tagged hand_curated",
          provenance["AAPL"] == M.PROVENANCE_HAND_CURATED, str(provenance))
    check("2c. NKE, never touched by the proxy file, is still tagged "
          "hand_curated", provenance["NKE"] == M.PROVENANCE_HAND_CURATED)


def test_3_blank_ticker_or_company_rows_are_skipped_not_crashed_on() -> None:
    proxy = _write_proxy_csv([
        {"ticker": "", "company": "No Ticker Co"},
        {"ticker": "BLANKCO", "company": ""},
        {"ticker": "GOOD1", "company": "A Real Company"},
    ])
    variants, provenance = M.load_expanded_anchor_universe(
        hand_curated={}, proxy_csv=proxy)
    check("3a. a blank ticker is skipped", "" not in variants)
    check("3b. a blank company name is skipped",
          "BLANKCO" not in variants, str(list(variants)))
    check("3c. the one well-formed row still gets added",
          variants.get("GOOD1") == ("A Real Company",))


def test_4_merge_against_the_real_repo_proxy_csv_does_not_crash() -> None:
    """Control: the ACTUAL Russell1000Proxy_Filtered_Universe.csv this
    module will read live, parsed with the real hand-curated dict, must
    produce a plausible-sized universe -- not a crash, not an empty one."""
    if not M.RUSSELL1000_PROXY_CSV.is_file():
        check("4a. the real proxy CSV is present on disk", False,
              str(M.RUSSELL1000_PROXY_CSV))
        return
    variants, provenance = M.load_expanded_anchor_universe()
    check("4a. merging against the real files produces more anchors than "
          "round 4's 27 alone",
          len(variants) > 27, str(len(variants)))
    check("4b. every hand-curated anchor survives the merge",
          all(t in variants for t in M.ANCHOR_NAME_VARIANTS),
          str(set(M.ANCHOR_NAME_VARIANTS) - set(variants)))
    check("4c. provenance covers every anchor, no anchor untagged",
          set(provenance) == set(variants))


def test_5_main_refuses_to_overwrite_existing_outputs() -> None:
    existing = TMP / "already_there.json"
    existing.write_text("{}", encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(["--out-name-search", str(existing),
                      "--out-linkage", str(TMP / "does_not_exist_1.json"),
                      "--out-raw-hits", str(TMP / "does_not_exist_2.json")])
    check("5a. refuses with a non-zero exit when an out path already exists",
          code != 0, str(code))
    check("5b. says why, on stderr", "already exists" in err.getvalue(),
          err.getvalue()[:200])
    check("5c. the existing file is untouched",
          existing.read_text(encoding="utf-8") == "{}")


def test_6_main_refuses_on_a_missing_proxy_csv() -> None:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(["--out-name-search", str(TMP / "ns2.json"),
                      "--out-linkage", str(TMP / "lk2.json"),
                      "--out-raw-hits", str(TMP / "rh2.json"),
                      "--proxy-csv", str(TMP / "does_not_exist.csv")])
    check("6a. refuses with a non-zero exit on a missing proxy csv",
          code != 0, str(code))
    check("6b. names the missing path", "does_not_exist.csv" in err.getvalue(),
          err.getvalue()[:200])


def test_7_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("7a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("7a. network blocked", True)


if __name__ == "__main__":
    test_1_merge_adds_only_net_new_tickers()
    test_2_provenance_is_tagged_correctly()
    test_3_blank_ticker_or_company_rows_are_skipped_not_crashed_on()
    test_4_merge_against_the_real_repo_proxy_csv_does_not_crash()
    test_5_main_refuses_to_overwrite_existing_outputs()
    test_6_main_refuses_on_a_missing_proxy_csv()
    test_7_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP05_REVERSE_CONCENTRATION_SEARCH_SCALED TESTS PASSED")
    sys.exit(0)
