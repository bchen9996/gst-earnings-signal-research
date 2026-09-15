#!/usr/bin/env python3
"""make_hyp08_phase3_run.py tests -- offline except LOCAL git subprocess
calls (no network), same pattern test_hyp04_supply_chain_hedge_hyp07_
phase3_run.py already uses for `_commit_sha`.

Everything here runs against a SYNTHETIC multi-peer, multi-anchor fixture
built in an isolated tempdir with its own throwaway git repo and a
clearly-fake "offline-test-fixture" signer -- never the real repo, never
the real committed HYP08_PHASE2_LOCK/AUTHORIZATION/RESULT artifacts. The
five hash pins this module reads from the Phase 2 lock (target_same_
session.py, inference.py, clustered_se.py, anchor_shock.py, make_hyp08_
sample_size_gate.py) plus the two source-lock pins (HYP-06's, HYP-07's
own signed locks) and the anchor-shocks CSVs are computed from the REAL
files already committed in this repo, same control-test discipline every
prior hypothesis's own Phase 3 test file uses; the two NEW pins this
module's own authorization carries (peer closes, peer earnings) are
entirely synthetic here.

  THE REHEARSAL RUNS STANDALONE, BOTH FITS PRODUCED (test_1).

  A REAL POOLED PANEL IS BUILT, EVENTS GROUPED BY event_id, AND THE shock
  FIELD HOLDS excess_return -- NOT shock's OWN MAGNITUDE (test_2), same
  field-name substitution every signed/same-session module's own
  docstring calls out. relationship_type rides along per event, and an
  event mixing relationship_type across its own peers refuses.

  NO AUTHORIZATION, NO RUN (test_3). DRIFT ON EVERY PINNED DIMENSION IS
  CAUGHT (test_4).

  THE HAPPY PATH PRODUCES A SANE, EXPLORATORY-LABELED RESULT WITH BOTH
  FITS AND CONSUMES THE AUTHORIZATION (test_5). NO RE-RUN (test_6). A
  CONSUMED AUTHORIZATION REFUSES EVEN AFTER ITS RESULT IS REMOVED (test_7).

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_hyp08_phase3_run.py
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

import csv  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from datetime import date, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import make_hyp08_phase3_run as P3  # noqa: E402
from hyp04_supply_chain_hedge.make_freeze_draft import _sha256  # noqa: E402
from hyp04_supply_chain_hedge.make_hyp08_phase2_lock import (  # noqa: E402
    ANCHOR_SHOCK_PY, ANCHOR_SHOCKS_CSVS, CLUSTERED_SE_PY,
    HYP06_PHASE2_LOCK_JSON, HYP07_PHASE2_LOCK_JSON, INFERENCE_PY,
    SAMPLE_SIZE_GATE_PY, TARGET_SAME_SESSION_PY,
)
from hyp04_supply_chain_hedge.target_same_session import BENCHMARK_TICKER  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def expect_refusal(label: str, fn, *, substring: str = "") -> None:
    try:
        fn()
        check(label, False, "it did not refuse")
    except P3.Phase3Error as e:
        ok = substring in str(e) if substring else True
        check(label, ok, str(e)[:220])


# --------------------------------------------------------------------------
# fixture: a synthetic panel, 2 customer/supplier peers + 1 competitor peer,
# + SPY, in its own git repo
# --------------------------------------------------------------------------

N_DAYS = 260
BASE = date(2016, 1, 1)
PEERS = ("PEERA", "PEERB", "PEERC", "PEERD", "PEERE")
ALL_TICKERS = (*PEERS, BENCHMARK_TICKER)
# PEERA/PEERB share one direct_supplier NVDA event; PEERC has its own
# sector_competitor GOOGL event; PEERD/PEERE share a direct_customer MSFT
# event -- 6 total (peer, event) pairs, enough to clear fit_interaction_
# model's own n>=6 floor so the happy-path test exercises both fits, not
# just the primary one. excess_return = -shock deliberately, same
# discipline as every prior phase3 test fixture in this package.
EVENTS = (
    {"day": 40, "anchor": "NVDA", "shock": 0.20, "peers": ("PEERA", "PEERB"),
     "relationship_type": "direct_supplier"},
    {"day": 130, "anchor": "NVDA", "shock": -0.15, "peers": ("PEERA",),
     "relationship_type": "direct_supplier"},
    {"day": 200, "anchor": "GOOGL", "shock": 0.10, "peers": ("PEERC",),
     "relationship_type": "sector_competitor"},
    {"day": 110, "anchor": "MSFT", "shock": 0.12, "peers": ("PEERD", "PEERE"),
     "relationship_type": "direct_customer"},
)
EARNINGS_DAYS = {"PEERA": (15, 90, 160, 230), "PEERB": (20, 95, 165, 235),
                 "PEERC": (25, 100, 170, 240), "PEERD": (30, 105, 175, 245),
                 "PEERE": (35, 110, 180, 250)}


def _git(tmp: Path, *args: str) -> str:
    out = subprocess.run(("git", *args), cwd=str(tmp), capture_output=True,
                         text=True)
    return out.stdout.strip()


def _commit_all(tmp: Path) -> None:
    subprocess.run(("git", "add", "-A"), cwd=str(tmp), capture_output=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture step"), cwd=str(tmp),
                   capture_output=True)


def _write_closes(path: Path, tickers: tuple[str, ...] = ALL_TICKERS
                  ) -> tuple[list[date], str]:
    sessions = [BASE + timedelta(days=i) for i in range(N_DAYS)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "session_date", "close"])
        for t_i, ticker in enumerate(tickers):
            for i, d in enumerate(sessions):
                close = (100.0 + t_i * 10 + 2.0 * math.sin(i * 0.7)
                        + 0.5 * math.cos(i * 1.3))
                w.writerow([ticker, d.isoformat(), f"{close:.6f}"])
    return sessions, _sha256(path)


def _write_earnings(path: Path, peers: tuple[str, ...] = PEERS) -> str:
    releases: dict[str, list[dict]] = {}
    for peer in peers:
        rows = []
        for i, day in enumerate(EARNINGS_DAYS[peer]):
            d = BASE + timedelta(days=day)
            rows.append({"release_date": d.isoformat(),
                        "release_session": "BMO" if i % 2 == 0 else "AMC"})
        releases[peer] = rows
    doc = {"per_peer_earnings_releases": releases}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return _sha256(path)


def _locked_events_rows() -> list[dict]:
    rows = []
    for ev in EVENTS:
        d = BASE + timedelta(days=ev["day"])
        eid = f"{ev['anchor']}-{d.isoformat()}"
        for peer in ev["peers"]:
            rows.append({
                "event_id": eid, "anchor_ticker": ev["anchor"],
                "peer_ticker": peer,
                "relationship_type": ev["relationship_type"],
                "as_of_date": "2010-01-01",
                "release_date": d.isoformat(), "attributed_session": d.isoformat(),
                "shock": ev["shock"], "excess_return": -ev["shock"],
            })
    return rows


def _write_lock(path: Path, *, events: list[dict] | None = None) -> str:
    events = events if events is not None else _locked_events_rows()
    locked_peers = sorted({e["peer_ticker"] for e in events})
    locked_anchors = sorted({e["anchor_ticker"] for e in events})
    n_cs = sum(1 for e in events if e["relationship_type"] != "sector_competitor")
    n_comp = len(events) - n_cs
    doc = {
        "artifact": path.name,
        "locked_peers": locked_peers, "locked_anchors": locked_anchors,
        "locked_events": events, "n_locked_events": len(events),
        "n_locked_events_customer_supplier": n_cs,
        "n_locked_events_competitor": n_comp,
        "pins": {
            "hyp06_phase2_lock_sha256": _sha256(HYP06_PHASE2_LOCK_JSON),
            "hyp07_phase2_lock_sha256": _sha256(HYP07_PHASE2_LOCK_JSON),
            "anchor_shocks_sha256": [_sha256(p) for p in ANCHOR_SHOCKS_CSVS],
            "target_same_session_py_sha256": _sha256(TARGET_SAME_SESSION_PY),
            "inference_py_sha256": _sha256(INFERENCE_PY),
            "clustered_se_py_sha256": _sha256(CLUSTERED_SE_PY),
            "anchor_shock_py_sha256": _sha256(ANCHOR_SHOCK_PY),
            "sample_size_gate_py_sha256": _sha256(SAMPLE_SIZE_GATE_PY),
        },
        "target_definition": {"sign_convention": "offline-test-fixture"},
        "model_spec": {
            "primary_cluster_key": "event_id",
            "residualize": False,
            "test_family": {"k": 2, "note": "offline-test-fixture"},
        },
        "sample_size_disclosure": {
            "n_locked_events": len(events),
            "framing": "EXPLORATORY -- floor is EXACT (k=2 by design)",
            "why": "offline-test-fixture -- not a real disclosure",
        },
        "look_ahead_disclosure": {
            "already_touched": "offline-test-fixture",
            "not_touched": "offline-test-fixture",
        },
        "declared": True, "declared_by": "offline-test-fixture",
        "declared_date": "2026-09-14", "status": "DECLARED -- offline-test-fixture",
    }
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return _sha256(path)


def _write_authorization(path: Path, *, tmp: Path, lock_sha256: str,
                         closes_sha256: str, earnings_sha256: str,
                         consumed: bool = False) -> None:
    doc = {
        "artifact": path.name, "declared": True,
        "declared_by": "offline-test-fixture", "declared_date": "2026-09-14",
        "attestation_text": "offline-test-fixture",
        "pinned_commit_sha": _git(tmp, "rev-parse", "HEAD"),
        "pinned_phase2_lock_sha256": lock_sha256,
        "pinned_peer_closes_sha256": closes_sha256,
        "pinned_peer_earnings_sha256": earnings_sha256,
        "consumed": consumed, "consumed_by_result": None,
    }
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")


def _fixture(tmp: Path) -> dict:
    for cmd in (("init", "-q"), ("config", "user.email", "t@t"),
               ("config", "user.name", "t")):
        subprocess.run(("git", *cmd), cwd=str(tmp), capture_output=True)
    lse = tmp / "Live Signal Engine"
    lse.mkdir(parents=True)

    closes_path = lse / "closes.csv"
    earnings_path = lse / "earnings.json"
    lock_path = lse / "HYP08_PHASE2_LOCK_test.json"
    auth_path = lse / "HYP08_PHASE3_AUTHORIZATION_test.json"

    sessions, closes_sha = _write_closes(closes_path)
    earnings_sha = _write_earnings(earnings_path)
    lock_sha = _write_lock(lock_path)
    _commit_all(tmp)
    _write_authorization(auth_path, tmp=tmp, lock_sha256=lock_sha,
                         closes_sha256=closes_sha, earnings_sha256=earnings_sha)
    _commit_all(tmp)

    return {"tmp": tmp, "lse": lse, "closes": closes_path,
            "earnings": earnings_path, "lock": lock_path, "auth": auth_path,
            "sessions": sessions, "out": lse / "HYP08_PHASE3_RESULT_test.json"}


def _build(f: dict, **kw):
    return P3.build_result(out_path=f["out"], phase2_lock_path=f["lock"],
                           peer_closes_path=f["closes"],
                           peer_earnings_path=f["earnings"],
                           lse=f["lse"], repo=f["tmp"], **kw)


# --------------------------------------------------------------------------
# 1. the rehearsal
# --------------------------------------------------------------------------

def test_1_rehearsal_runs_standalone() -> None:
    result = P3.run_rehearsal()
    check("1a. nonzero rows", result["n_rows"] > 0, str(result["n_rows"]))
    check("1b. a primary fit was produced", result["primary_fit"] is not None)
    check("1c. a heterogeneity fit was produced",
          result["heterogeneity_fit"] is not None)
    check("1d. carries the sign_convention_reminder",
          "NEGATIVE" in result["sign_convention_reminder"]
          and "POSITIVE" in result["sign_convention_reminder"])
    check("1e. descriptive-only context is present but separate from the "
          "verdicted fields",
          "descriptive_context_not_verdicted"
          in result["heterogeneity_fit"])


# --------------------------------------------------------------------------
# 2. building the real, pooled panel
# --------------------------------------------------------------------------

def test_2_real_pooled_panel_uses_excess_return_not_shock() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        closes_path = tmp / "closes.csv"
        earnings_path = tmp / "earnings.json"
        sessions, _ = _write_closes(closes_path)
        _write_earnings(earnings_path)
        events = _locked_events_rows()
        lock = {"locked_events": events}
        panel, extra = P3._build_real_panel(
            lock=lock, peer_closes_path=closes_path,
            peer_earnings_path=earnings_path)

        check("2a. four distinct anchor events (event_ids), not six rows",
              len(panel.anchor_events) == 4, str(len(panel.anchor_events)))
        check("2a2. n_pairs across events equals the 6 locked rows",
              extra["n_pairs"] == 6, str(extra))

        by_original_shock = {round(-ev["shock"], 6): ev
                             for ev in panel.anchor_events}
        ev0 = by_original_shock[round(EVENTS[0]["shock"], 6)]
        check("2b. the panel's shock slot holds excess_return (negated "
              "shock in this fixture), not shock itself",
              round(ev0["shock"], 6) == round(-EVENTS[0]["shock"], 6), str(ev0))
        check("2c. the shared NVDA event lists BOTH peers",
              sorted(ev0["peers"]) == ["PEERA", "PEERB"], str(ev0))
        check("2c2. it carries the right relationship_type",
              ev0["relationship_type"] == "direct_supplier", str(ev0))

        ev1 = by_original_shock[round(EVENTS[1]["shock"], 6)]
        check("2d. the PEERA-only NVDA event lists exactly PEERA",
              ev1["peers"] == ["PEERA"], str(ev1))

        ev2 = by_original_shock[round(EVENTS[2]["shock"], 6)]
        check("2d2. the competitor event carries sector_competitor",
              ev2["relationship_type"] == "sector_competitor", str(ev2))

        check("2e. n_trading_days is internally consistent with the "
              "provenance report",
              panel.n_trading_days == extra["n_sessions"], str(extra))
        check("2f. extra provenance names the real sha256 and benchmark ticker",
              extra["peer_closes_sha256"] == _sha256(closes_path)
              and extra["benchmark_ticker"] == BENCHMARK_TICKER)
        check("2g. SPY rides along in panel.returns without being a "
              "'locked peer'",
              set(panel.returns.keys()) == {"PEERA", "PEERB", "PEERC",
                                            "PEERD", "PEERE", BENCHMARK_TICKER})

        bad_closes = tmp / "bad_closes.csv"
        _write_closes(bad_closes, tickers=("PEERA", "PEERC", BENCHMARK_TICKER))
        expect_refusal(
            "2h. a closes file missing a locked peer refuses",
            lambda: P3._build_real_panel(
                lock=lock, peer_closes_path=bad_closes,
                peer_earnings_path=earnings_path),
            substring="PEERB")

        no_spy_closes = tmp / "no_spy_closes.csv"
        _write_closes(no_spy_closes, tickers=PEERS)
        expect_refusal(
            "2i. a closes file with every locked peer but no SPY refuses",
            lambda: P3._build_real_panel(
                lock=lock, peer_closes_path=no_spy_closes,
                peer_earnings_path=earnings_path),
            substring=BENCHMARK_TICKER)

        saturday = (BASE + timedelta(days=1)).isoformat()
        lock_bad = {"locked_events": [
            {"event_id": f"NVDA-{saturday}", "anchor_ticker": "NVDA",
             "peer_ticker": "PEERA", "attributed_session": saturday,
             "shock": 0.2, "excess_return": -0.2,
             "relationship_type": "direct_supplier"},
        ]}
        single_peer_closes = tmp / "single_peer_closes.csv"
        _write_closes(single_peer_closes, tickers=("PEERA", BENCHMARK_TICKER))
        expect_refusal(
            "2j. an attributed session on a non-trading day refuses",
            lambda: P3._build_real_panel(
                lock=lock_bad, peer_closes_path=single_peer_closes,
                peer_earnings_path=earnings_path),
            substring=saturday)

        d = BASE + timedelta(days=40)
        lock_inconsistent = {"locked_events": [
            {"event_id": "NVDA-inconsistent", "anchor_ticker": "NVDA",
             "peer_ticker": "PEERA", "attributed_session": d.isoformat(),
             "shock": 0.20, "excess_return": -0.20,
             "relationship_type": "direct_supplier"},
            {"event_id": "NVDA-inconsistent", "anchor_ticker": "NVDA",
             "peer_ticker": "PEERB", "attributed_session": d.isoformat(),
             "shock": 0.20, "excess_return": -0.20,
             "relationship_type": "sector_competitor"},
        ]}
        two_peer_closes = tmp / "two_peer_closes.csv"
        _write_closes(two_peer_closes, tickers=("PEERA", "PEERB", BENCHMARK_TICKER))
        expect_refusal(
            "2k. an event_id with inconsistent relationship_type across "
            "its own rows refuses",
            lambda: P3._build_real_panel(
                lock=lock_inconsistent, peer_closes_path=two_peer_closes,
                peer_earnings_path=earnings_path),
            substring="NVDA-inconsistent")


# --------------------------------------------------------------------------
# 3. no authorization, no run
# --------------------------------------------------------------------------

def test_3_no_authorization_no_run() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        f["auth"].unlink()
        expect_refusal("3a. no authorization on disk refuses", lambda: _build(f),
                       substring="no HYP-08 Phase 3 authorization")


# --------------------------------------------------------------------------
# 4. drift on every pinned dimension
# --------------------------------------------------------------------------

def test_4_drift_on_every_pin_is_caught() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        lock = json.loads(f["lock"].read_text())
        lock["pins"]["target_same_session_py_sha256"] = "0" * 64
        f["lock"].write_text(json.dumps(lock, indent=1))
        expect_refusal("4a. target_same_session.py hash mismatch refuses",
                       lambda: _build(f), substring="target_same_session.py")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        lock = json.loads(f["lock"].read_text())
        lock["pins"]["hyp06_phase2_lock_sha256"] = "0" * 64
        f["lock"].write_text(json.dumps(lock, indent=1))
        expect_refusal("4b. HYP-06 source-lock hash mismatch refuses",
                       lambda: _build(f), substring="HYP-06 Phase 2 lock")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        lock = json.loads(f["lock"].read_text())
        lock["pins"]["hyp07_phase2_lock_sha256"] = "0" * 64
        f["lock"].write_text(json.dumps(lock, indent=1))
        expect_refusal("4c. HYP-07 source-lock hash mismatch refuses",
                       lambda: _build(f), substring="HYP-07 Phase 2 lock")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        lock = json.loads(f["lock"].read_text())
        lock["pins"]["anchor_shocks_sha256"] = ["0" * 64] * len(ANCHOR_SHOCKS_CSVS)
        f["lock"].write_text(json.dumps(lock, indent=1))
        expect_refusal("4d. anchor-shocks hash mismatch refuses",
                       lambda: _build(f), substring="anchor shocks")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = json.loads(f["auth"].read_text())
        doc["pinned_phase2_lock_sha256"] = "0" * 64
        f["auth"].write_text(json.dumps(doc, indent=1))
        _commit_all(f["tmp"])
        expect_refusal("4e. authorization pinned to a different lock hash refuses",
                       lambda: _build(f), substring="lock on disk now hashes")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = json.loads(f["auth"].read_text())
        doc["pinned_peer_closes_sha256"] = "0" * 64
        f["auth"].write_text(json.dumps(doc, indent=1))
        _commit_all(f["tmp"])
        expect_refusal("4f. authorization pinned to a different peer-closes "
                       "hash refuses",
                       lambda: _build(f), substring="peer-closes hash")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = json.loads(f["auth"].read_text())
        doc["pinned_peer_earnings_sha256"] = "0" * 64
        f["auth"].write_text(json.dumps(doc, indent=1))
        _commit_all(f["tmp"])
        expect_refusal("4g. authorization pinned to a different peer-"
                       "earnings hash refuses",
                       lambda: _build(f), substring="peer-earnings hash")


# --------------------------------------------------------------------------
# 5. the happy path
# --------------------------------------------------------------------------

def test_5_happy_path_produces_a_sane_labeled_result() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = _build(f)

        check("5a. wrote the result file", f["out"].is_file())
        check("5b. locked_peers/anchors are correct",
              sorted(doc["locked_peers"])
              == ["PEERA", "PEERB", "PEERC", "PEERD", "PEERE"]
              and sorted(doc["locked_anchors"]) == ["GOOGL", "MSFT", "NVDA"])
        check("5c. n_locked_events == 6", doc["n_locked_events"] == 6)
        check("5d. reported_regardless_of_outcome is True",
              doc["reported_regardless_of_outcome"] is True)
        check("5e. no_rerun_permitted is True", doc["no_rerun_permitted"] is True)
        check("5f. carries the sample_size_disclosure verbatim from the lock",
              "EXACT" in doc["sample_size_disclosure"]["framing"])
        check("5g. treatment carries both fits",
              doc["treatment"]["primary_fit"] is not None
              and doc["treatment"]["heterogeneity_fit"] is not None)
        check("5h. the authorization is now consumed",
              json.loads(f["auth"].read_text())["consumed"] is True)
        check("5i. consumed_by_result names this exact result artifact",
              json.loads(f["auth"].read_text())["consumed_by_result"]
              == f["out"].name)
        check("5j. carries sign_convention from the lock's own "
              "target_definition",
              doc["sign_convention"] == "offline-test-fixture")
        check("5k. residualize is False, not a caller choice",
              doc["treatment"]["residualize"] is False)
        check("5l. n_rows splits by relationship type",
              doc["treatment"]["n_rows_customer_supplier"]
              + doc["treatment"]["n_rows_competitor"]
              == doc["treatment"]["n_rows"])


# --------------------------------------------------------------------------
# 6. no re-run, even with a fresh authorization
# --------------------------------------------------------------------------

def test_6_no_rerun_even_with_a_fresh_authorization() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        _build(f)

        auth2 = f["lse"] / "HYP08_PHASE3_AUTHORIZATION_test2.json"
        lock_sha = _sha256(f["lock"])
        closes_sha = _sha256(f["closes"])
        earnings_sha = _sha256(f["earnings"])
        _write_authorization(auth2, tmp=f["tmp"], lock_sha256=lock_sha,
                             closes_sha256=closes_sha, earnings_sha256=earnings_sha)

        out2 = f["lse"] / "HYP08_PHASE3_RESULT_test2.json"
        expect_refusal(
            "6a. a second result refuses even with a brand-new authorization",
            lambda: P3.build_result(
                out_path=out2, phase2_lock_path=f["lock"],
                peer_closes_path=f["closes"], peer_earnings_path=f["earnings"],
                lse=f["lse"], repo=f["tmp"]),
            substring="already exists")


# --------------------------------------------------------------------------
# 7. a consumed authorization refuses even after its result is removed
# --------------------------------------------------------------------------

def test_7_consumed_authorization_refuses_after_result_removed() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        _build(f)
        f["out"].unlink()

        out2 = f["lse"] / "HYP08_PHASE3_RESULT_test2.json"
        expect_refusal(
            "7a. the SAME (now-consumed) authorization refuses a second run "
            "even with the original result deleted",
            lambda: P3.build_result(
                out_path=out2, phase2_lock_path=f["lock"],
                peer_closes_path=f["closes"], peer_earnings_path=f["earnings"],
                lse=f["lse"], repo=f["tmp"]),
            substring="already consumed")


def test_8_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("8a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("8a. network blocked", True)


if __name__ == "__main__":
    test_1_rehearsal_runs_standalone()
    test_2_real_pooled_panel_uses_excess_return_not_shock()
    test_3_no_authorization_no_run()
    test_4_drift_on_every_pin_is_caught()
    test_5_happy_path_produces_a_sane_labeled_result()
    test_6_no_rerun_even_with_a_fresh_authorization()
    test_7_consumed_authorization_refuses_after_result_removed()
    test_8_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP08_PHASE3_RUN TESTS PASSED")
    sys.exit(0)
