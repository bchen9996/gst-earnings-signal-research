#!/usr/bin/env python3
"""make_hyp06_phase3_run.py tests -- offline except LOCAL git subprocess
calls (no network), same pattern test_hyp04_supply_chain_hedge_hyp05_
phase3_run.py already uses for `_commit_sha`.

Everything here runs against a SYNTHETIC multi-peer, multi-anchor fixture
built in an isolated tempdir with its own throwaway git repo and a
clearly-fake "offline-test-fixture" signer -- never the real repo, never
the real committed HYP06_PHASE2_LOCK/AUTHORIZATION/RESULT artifacts, and
no computed value here is asserted as a finding about any real peer or
anchor. The five hash pins this module reads from the Phase 2 lock
(target.py, constants.py, clustered_se.py, the peer universe, and the
anchor shocks) are computed from the REAL files already committed in this
repo, exactly the same control-test discipline
test_hyp04_supply_chain_hedge_hyp06_phase2_lock.py already uses; the two
NEW pins this module's own authorization carries (peer closes, peer
earnings) are entirely synthetic here, since HYP-06's real peer-closes/
earnings artifacts do not exist until the real live fetch runs.

  THE REHEARSAL RUNS STANDALONE (test_1).

  A REAL MULTI-PEER PANEL IS BUILT, EVENTS GROUPED BY event_id (test_2) --
  two peers sharing one anchor event_id collapse into ONE anchor_events
  entry with both peers listed; a wrong-ticker-set closes file and an
  attributed session outside the shared calendar both refuse; an
  internally-inconsistent event_id (same id, different shock) refuses.

  THE SECONDARY LENS REPORTS WHAT IT CAN AND REFUSES WHAT IT CANNOT
  (test_3).

  NO AUTHORIZATION, NO RUN (test_4). DRIFT ON EVERY PINNED DIMENSION IS
  CAUGHT (test_5) -- including the two peer-data pins this module adds
  beyond HYP-05's own set.

  THE HAPPY PATH PRODUCES A SANE, EXPLORATORY-LABELED RESULT AND CONSUMES
  THE AUTHORIZATION (test_6). NO RE-RUN (test_7). A CONSUMED
  AUTHORIZATION REFUSES EVEN AFTER ITS RESULT IS REMOVED (test_8).

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_hyp06_phase3_run.py
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

import numpy as np  # noqa: E402

from hyp04_supply_chain_hedge import make_hyp06_phase3_run as P3  # noqa: E402
from hyp04_supply_chain_hedge.make_freeze_draft import _sha256  # noqa: E402
from hyp04_supply_chain_hedge.make_hyp06_phase2_lock import (  # noqa: E402
    ANCHOR_SHOCKS_CSVS, CLUSTERED_SE_PY, CONSTANTS_PY, PEER_UNIVERSE_JSON,
    TARGET_PY,
)

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
# fixture: a synthetic 2-peer, 2-anchor panel, in its own git repo
# --------------------------------------------------------------------------

N_DAYS = 260
BASE = date(2016, 1, 1)
PEERS = ("PEERA", "PEERB")
# event day-offsets: two NVDA events (one shared by both peers), one GOOGL
# event (PEERB only)
EVENTS = (
    {"day": 40, "anchor": "NVDA", "shock": 0.20, "peers": ("PEERA", "PEERB")},
    {"day": 130, "anchor": "NVDA", "shock": -0.15, "peers": ("PEERA",)},
    {"day": 200, "anchor": "GOOGL", "shock": 0.10, "peers": ("PEERB",)},
)
EARNINGS_DAYS = {"PEERA": (15, 90, 160, 230), "PEERB": (20, 95, 165, 235)}


def _git(tmp: Path, *args: str) -> str:
    out = subprocess.run(("git", *args), cwd=str(tmp), capture_output=True,
                         text=True)
    return out.stdout.strip()


def _commit_all(tmp: Path) -> None:
    subprocess.run(("git", "add", "-A"), cwd=str(tmp), capture_output=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture step"), cwd=str(tmp),
                   capture_output=True)


def _write_closes(path: Path, peers: tuple[str, ...] = PEERS) -> tuple[list[date], str]:
    sessions = [BASE + timedelta(days=i) for i in range(N_DAYS)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "session_date", "close"])
        for peer_i, peer in enumerate(peers):
            for i, d in enumerate(sessions):
                close = (100.0 + peer_i * 10 + 2.0 * math.sin(i * 0.7)
                        + 0.5 * math.cos(i * 1.3))
                w.writerow([peer, d.isoformat(), f"{close:.6f}"])
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
                "peer_ticker": peer, "relationship_type": "direct_supplier",
                "as_of_date": "2010-01-01",
                "release_date": d.isoformat(), "attributed_session": d.isoformat(),
                "shock": ev["shock"],
            })
    return rows


def _write_lock(path: Path, *, peer_closes_sha: str, peer_earnings_sha: str,
                n_permutations: int = 200,
                events: list[dict] | None = None) -> str:
    events = events if events is not None else _locked_events_rows()
    locked_peers = sorted({e["peer_ticker"] for e in events})
    locked_anchors = sorted({e["anchor_ticker"] for e in events})
    doc = {
        "artifact": path.name,
        "locked_peers": locked_peers, "locked_anchors": locked_anchors,
        "locked_events": events, "n_locked_events": len(events),
        "pins": {
            "peer_universe_sha256": _sha256(PEER_UNIVERSE_JSON),
            "anchor_shocks_sha256": [_sha256(p) for p in ANCHOR_SHOCKS_CSVS],
            "target_py_sha256": _sha256(TARGET_PY),
            "constants_py_sha256": _sha256(CONSTANTS_PY),
            "clustered_se_py_sha256": _sha256(CLUSTERED_SE_PY),
        },
        "model_spec": {
            "primary_cluster_key": "event_id",
            "residualize": False,        # sidesteps earnings-cycle bucket
                                          # population -- see HYP-05's own
                                          # test fixture, same reasoning
            "n_permutations": n_permutations, "random_seed": 42,
        },
        "sample_size_disclosure": {
            "n_locked_events": len(events),
            "framing": "EXPLORATORY, FLOOR CLEARED (provisional floor)",
            "why": "offline-test-fixture -- not a real disclosure",
        },
        "look_ahead_disclosure": {
            "already_touched": "offline-test-fixture",
            "not_touched": "offline-test-fixture",
        },
        "declared": True, "declared_by": "offline-test-fixture",
        "declared_date": "2026-09-13", "status": "DECLARED -- offline-test-fixture",
    }
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return _sha256(path)


def _write_authorization(path: Path, *, tmp: Path, lock_sha256: str,
                         closes_sha256: str, earnings_sha256: str,
                         consumed: bool = False) -> None:
    doc = {
        "artifact": path.name, "declared": True,
        "declared_by": "offline-test-fixture", "declared_date": "2026-09-13",
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
    lock_path = lse / "HYP06_PHASE2_LOCK_test.json"
    auth_path = lse / "HYP06_PHASE3_AUTHORIZATION_test.json"

    sessions, closes_sha = _write_closes(closes_path)
    earnings_sha = _write_earnings(earnings_path)
    lock_sha = _write_lock(lock_path, peer_closes_sha=closes_sha,
                           peer_earnings_sha=earnings_sha)
    _commit_all(tmp)  # clean tree required before _commit_sha runs
    _write_authorization(auth_path, tmp=tmp, lock_sha256=lock_sha,
                         closes_sha256=closes_sha, earnings_sha256=earnings_sha)
    _commit_all(tmp)  # _commit_sha is called again inside build_result

    return {"tmp": tmp, "lse": lse, "closes": closes_path,
            "earnings": earnings_path, "lock": lock_path, "auth": auth_path,
            "sessions": sessions, "out": lse / "HYP06_PHASE3_RESULT_test.json"}


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
    check("1b. a real D6 disclosure exists", bool(result["d6_disclosures"]))
    check("1c. clustered on HYP-06's own primary key",
          "event_id" in result["d2_residual_limitation"],
          result["d2_residual_limitation"][:120])


# --------------------------------------------------------------------------
# 2. building the real, multi-peer panel
# --------------------------------------------------------------------------

def test_2_real_multi_peer_panel_grouped_by_event_id() -> None:
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

        check("2a. three distinct anchor events (event_ids), not four rows",
              len(panel.anchor_events) == 3, str(len(panel.anchor_events)))
        check("2a2. n_pairs across events equals the 4 locked rows",
              extra["n_pairs"] == 4, str(extra))

        # `_session_index` builds a REAL XNYS trading calendar (weekends/
        # holidays excluded), not the naive every-calendar-day list this
        # fixture writes closes for -- so events are matched by their
        # distinct shock value, not by re-deriving a session position here.
        by_shock = {round(ev["shock"], 6): ev for ev in panel.anchor_events}
        ev0 = by_shock[round(EVENTS[0]["shock"], 6)]
        check("2b. the shared NVDA event lists BOTH peers",
              sorted(ev0["peers"]) == ["PEERA", "PEERB"], str(ev0))

        ev1 = by_shock[round(EVENTS[1]["shock"], 6)]
        check("2c. the PEERA-only NVDA event lists exactly PEERA",
              ev1["peers"] == ["PEERA"], str(ev1))

        check("2d. n_trading_days is internally consistent with the "
              "provenance report",
              panel.n_trading_days == extra["n_sessions"], str(extra))
        check("2e. extra provenance names the real sha256",
              extra["peer_closes_sha256"] == _sha256(closes_path))
        check("2f. both peers have a returns series",
              set(panel.returns.keys()) == {"PEERA", "PEERB"})

        # wrong ticker set in the closes file (missing PEERB)
        bad_closes = tmp / "bad_closes.csv"
        _write_closes(bad_closes, peers=("PEERA",))
        expect_refusal(
            "2g. a closes file missing a locked peer refuses",
            lambda: P3._build_real_panel(
                lock=lock, peer_closes_path=bad_closes,
                peer_earnings_path=earnings_path),
            substring="PEERA")

        # attributed session on a real, non-trading day (BASE + 1 day is a
        # Saturday -- BASE itself, 2016-01-01, is a Friday) -- _session_index
        # builds a REAL XNYS calendar, so this (not an arbitrary far-off
        # date, which the padded range would happily include) is what
        # "outside the shared trading calendar" actually means here.
        saturday = (BASE + timedelta(days=1)).isoformat()
        lock_bad = {"locked_events": [
            {"event_id": f"NVDA-{saturday}", "anchor_ticker": "NVDA",
             "peer_ticker": "PEERA", "attributed_session": saturday,
             "shock": 0.2},
        ]}
        expect_refusal(
            "2h. an attributed session on a non-trading day refuses",
            lambda: P3._build_real_panel(
                lock=lock_bad, peer_closes_path=bad_closes,
                peer_earnings_path=earnings_path),
            substring=saturday)

        # same event_id, inconsistent shock across its own rows
        d = BASE + timedelta(days=40)
        lock_inconsistent = {"locked_events": [
            {"event_id": "NVDA-inconsistent", "anchor_ticker": "NVDA",
             "peer_ticker": "PEERA", "attributed_session": d.isoformat(),
             "shock": 0.20},
            {"event_id": "NVDA-inconsistent", "anchor_ticker": "NVDA",
             "peer_ticker": "PEERB", "attributed_session": d.isoformat(),
             "shock": 0.99},
        ]}
        expect_refusal(
            "2i. an event_id with inconsistent shock across its own rows "
            "refuses",
            lambda: P3._build_real_panel(
                lock=lock_inconsistent, peer_closes_path=closes_path,
                peer_earnings_path=earnings_path),
            substring="NVDA-inconsistent")


# --------------------------------------------------------------------------
# 3. the secondary robustness lens
# --------------------------------------------------------------------------

def test_3_secondary_lens_reports_or_refuses_per_horizon() -> None:
    from hyp04_supply_chain_hedge.fixtures import SyntheticPanel

    n = N_DAYS
    rng_returns = np.array(
        [0.0] + [0.01 * math.sin(i) for i in range(1, n)], dtype=float)
    panel = SyntheticPanel(
        name="lens-test", returns={"PEERA": rng_returns, "PEERB": rng_returns},
        peer_earnings_days={"PEERA": [15, 90, 160], "PEERB": [20, 95, 165]},
        anchor_events=[
            {"anchor": "NVDA", "anchor_day": 40, "shock": 0.2,
             "peers": ["PEERA", "PEERB"], "calendar_period": 20161},
            {"anchor": "NVDA", "anchor_day": 100, "shock": 0.1,
             "peers": ["PEERA"], "calendar_period": 20162},
            {"anchor": "GOOGL", "anchor_day": 130, "shock": -0.1,
             "peers": ["PEERB"], "calendar_period": 20162},
        ],
        n_trading_days=n, injected_lag=None, injected_effect=0.0,
        injected_effect_window=0, peer_base_vol={}, earnings_ramp_amplitude=0.0,
    )
    out = P3._secondary_lens(panel, [1, 5], residualize=False)
    by_h = {r["horizon"]: r for r in out}
    check("3a. horizon 1 is computed (>=3 pairs, >=2 distinct clusters both dims)",
          "beta_shock" in by_h[1], str(by_h[1]))

    empty_panel = SyntheticPanel(
        name="lens-empty", returns={"PEERA": np.full(n, np.nan)},
        peer_earnings_days={"PEERA": []},
        anchor_events=[{"anchor": "NVDA", "anchor_day": 40, "shock": 0.2,
                       "peers": ["PEERA"], "calendar_period": 20161}],
        n_trading_days=n, injected_lag=None, injected_effect=0.0,
        injected_effect_window=0, peer_base_vol={}, earnings_ramp_amplitude=0.0,
    )
    out2 = P3._secondary_lens(empty_panel, [1], residualize=False)
    check("3b. all-NaN returns -> 'no secondary lens computed', not a crash",
          "note" in out2[0] and "beta_shock" not in out2[0], str(out2[0]))


# --------------------------------------------------------------------------
# 4. no authorization, no run
# --------------------------------------------------------------------------

def test_4_no_authorization_no_run() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        f["auth"].unlink()
        expect_refusal("4a. no authorization on disk refuses", lambda: _build(f),
                       substring="no HYP-06 Phase 3 authorization")


# --------------------------------------------------------------------------
# 5. drift on every pinned dimension
# --------------------------------------------------------------------------

def test_5_drift_on_every_pin_is_caught() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        lock = json.loads(f["lock"].read_text())
        lock["pins"]["target_py_sha256"] = "0" * 64
        f["lock"].write_text(json.dumps(lock, indent=1))
        expect_refusal("5a. target.py hash mismatch refuses", lambda: _build(f),
                       substring="target.py")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        lock = json.loads(f["lock"].read_text())
        lock["pins"]["anchor_shocks_sha256"] = ["0" * 64] * len(ANCHOR_SHOCKS_CSVS)
        f["lock"].write_text(json.dumps(lock, indent=1))
        expect_refusal("5b. anchor-shocks hash mismatch refuses",
                       lambda: _build(f), substring="anchor shocks")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = json.loads(f["auth"].read_text())
        doc["pinned_phase2_lock_sha256"] = "0" * 64
        f["auth"].write_text(json.dumps(doc, indent=1))
        _commit_all(f["tmp"])
        expect_refusal("5c. authorization pinned to a different lock hash refuses",
                       lambda: _build(f), substring="lock on disk now hashes")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = json.loads(f["auth"].read_text())
        doc["pinned_peer_closes_sha256"] = "0" * 64
        f["auth"].write_text(json.dumps(doc, indent=1))
        _commit_all(f["tmp"])
        expect_refusal("5d. authorization pinned to a different peer-closes "
                       "hash refuses",
                       lambda: _build(f), substring="peer-closes hash")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = json.loads(f["auth"].read_text())
        doc["pinned_peer_earnings_sha256"] = "0" * 64
        f["auth"].write_text(json.dumps(doc, indent=1))
        _commit_all(f["tmp"])
        expect_refusal("5e. authorization pinned to a different peer-"
                       "earnings hash refuses",
                       lambda: _build(f), substring="peer-earnings hash")


# --------------------------------------------------------------------------
# 6. the happy path
# --------------------------------------------------------------------------

def test_6_happy_path_produces_a_sane_labeled_result() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = _build(f)

        check("6a. wrote the result file", f["out"].is_file())
        check("6b. locked_peers/anchors are correct",
              sorted(doc["locked_peers"]) == ["PEERA", "PEERB"]
              and sorted(doc["locked_anchors"]) == ["GOOGL", "NVDA"])
        check("6c. n_locked_events == 4", doc["n_locked_events"] == 4)
        check("6d. reported_regardless_of_outcome is True",
              doc["reported_regardless_of_outcome"] is True)
        check("6e. no_rerun_permitted is True", doc["no_rerun_permitted"] is True)
        check("6f. carries the sample_size_disclosure verbatim from the lock",
              "FLOOR CLEARED" in doc["sample_size_disclosure"]["framing"])
        check("6g. carries a clustering_label_note explaining the "
              "HYP-04-authored 'SENSITIVITY' label",
              "HYP-04" in doc["clustering_label_note"])
        check("6h. treatment is clustered on event_id",
              "event_id" in doc["treatment"]["d2_residual_limitation"])
        check("6i. secondary robustness lens dimension is calendar_period",
              doc["secondary_cluster_robustness_lens"]["dimension"] == "calendar_period")
        check("6j. the authorization is now consumed",
              json.loads(f["auth"].read_text())["consumed"] is True)
        check("6k. consumed_by_result names this exact result artifact",
              json.loads(f["auth"].read_text())["consumed_by_result"]
              == f["out"].name)


# --------------------------------------------------------------------------
# 7. no re-run, even with a fresh authorization
# --------------------------------------------------------------------------

def test_7_no_rerun_even_with_a_fresh_authorization() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        _build(f)

        auth2 = f["lse"] / "HYP06_PHASE3_AUTHORIZATION_test2.json"
        lock_sha = _sha256(f["lock"])
        closes_sha = _sha256(f["closes"])
        earnings_sha = _sha256(f["earnings"])
        _write_authorization(auth2, tmp=f["tmp"], lock_sha256=lock_sha,
                             closes_sha256=closes_sha, earnings_sha256=earnings_sha)

        out2 = f["lse"] / "HYP06_PHASE3_RESULT_test2.json"
        expect_refusal(
            "7a. a second result refuses even with a brand-new authorization",
            lambda: P3.build_result(
                out_path=out2, phase2_lock_path=f["lock"],
                peer_closes_path=f["closes"], peer_earnings_path=f["earnings"],
                lse=f["lse"], repo=f["tmp"]),
            substring="already exists")


# --------------------------------------------------------------------------
# 8. a consumed authorization refuses even after its result is removed
# --------------------------------------------------------------------------

def test_8_consumed_authorization_refuses_after_result_removed() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        _build(f)
        f["out"].unlink()

        out2 = f["lse"] / "HYP06_PHASE3_RESULT_test2.json"
        expect_refusal(
            "8a. the SAME (now-consumed) authorization refuses a second run "
            "even with the original result deleted",
            lambda: P3.build_result(
                out_path=out2, phase2_lock_path=f["lock"],
                peer_closes_path=f["closes"], peer_earnings_path=f["earnings"],
                lse=f["lse"], repo=f["tmp"]),
            substring="already consumed")


def test_9_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("9a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("9a. network blocked", True)


if __name__ == "__main__":
    test_1_rehearsal_runs_standalone()
    test_2_real_multi_peer_panel_grouped_by_event_id()
    test_3_secondary_lens_reports_or_refuses_per_horizon()
    test_4_no_authorization_no_run()
    test_5_drift_on_every_pin_is_caught()
    test_6_happy_path_produces_a_sane_labeled_result()
    test_7_no_rerun_even_with_a_fresh_authorization()
    test_8_consumed_authorization_refuses_after_result_removed()
    test_9_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP06_PHASE3_RUN TESTS PASSED")
    sys.exit(0)
