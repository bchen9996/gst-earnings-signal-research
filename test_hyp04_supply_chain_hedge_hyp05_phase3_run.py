#!/usr/bin/env python3
"""make_hyp05_phase3_run.py tests -- offline except LOCAL git subprocess
calls (no network), same pattern test_hyp04_supply_chain_hedge_freeze_draft
.py and test_hyp04_supply_chain_hedge_phase3_run.py already use for
`_commit_sha`.

Everything here runs against a SYNTHETIC 2-event AMBA/NVDA fixture built in
an isolated tempdir with its own throwaway git repo and a clearly-fake
"offline-test-fixture" signer -- never the real repo, never the real
committed HYP05_PHASE2_LOCK/AUTHORIZATION/RESULT artifacts, and no computed
value here is asserted as a finding about AMBA or NVDA. The five hash pins
this module cannot redirect (target.py, constants.py, clustered_se.py,
the peer universe, and the anchor shocks -- see make_hyp05_phase3_run.py's
own module constants) are computed from the REAL files already committed
in this repo, exactly the same control-test discipline
test_hyp04_supply_chain_hedge_hyp05_phase2_lock.py already uses.

  THE REHEARSAL RUNS STANDALONE (test_1) -- touches no real file, requires
  no authorization, and actually exercises the estimator (nonzero rows, a
  real D6 disclosure) rather than passing vacuously.

  A REAL PANEL IS BUILT FROM AMBA'S OWN CALENDAR (test_2) -- the locked
  events' attributed sessions map to the correct day-index positions;
  wrong-ticker closes and an attributed session outside AMBA's own trading
  calendar both refuse rather than guessing.

  THE SECONDARY LENS REPORTS WHAT IT CAN AND REFUSES WHAT IT CANNOT
  (test_3) -- a computed dual-cluster horizon, a too-thin-row refusal, and
  a too-few-distinct-clusters refusal are all distinct, correctly labeled
  outcomes, never silently coerced into one of the others.

  NO AUTHORIZATION, NO RUN (test_4). DRIFT ON EVERY PINNED DIMENSION IS
  CAUGHT (test_5) -- the Phase 2 lock hash, target.py/constants.py/
  clustered_se.py, and the peer closes/earnings files each refuse
  independently when tampered.

  THE HAPPY PATH PRODUCES A SANE, EXPLORATORY-LABELED RESULT AND CONSUMES
  THE AUTHORIZATION (test_6). NO RE-RUN, EVEN WITH A FRESH AUTHORIZATION
  (test_7) -- and a CONSUMED authorization refuses a second run even after
  its result artifact is removed (test_8), because "no re-run" is enforced
  by the authorization's own state, not merely by the result file existing.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_hyp05_phase3_run.py
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

from hyp04_supply_chain_hedge import make_hyp05_phase3_run as P3  # noqa: E402
from hyp04_supply_chain_hedge.make_freeze_draft import _sha256  # noqa: E402
from hyp04_supply_chain_hedge.make_hyp05_phase2_lock import (  # noqa: E402
    ANCHOR_SHOCKS_CSV, CLUSTERED_SE_PY, CONSTANTS_PY, PEER_UNIVERSE_JSON,
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
# fixture: a synthetic 2-event AMBA/NVDA panel, in its own git repo
# --------------------------------------------------------------------------

N_DAYS = 170
BASE = date(2016, 1, 1)
EVENT_DAYS = (40, 130)          # 2016-02-10 (Q1) and 2016-05-10 (Q2)
EARNINGS_DAYS = (15, 90, 160)


def _git(tmp: Path, *args: str) -> str:
    out = subprocess.run(("git", *args), cwd=str(tmp), capture_output=True,
                         text=True)
    return out.stdout.strip()


def _commit_all(tmp: Path) -> None:
    subprocess.run(("git", "add", "-A"), cwd=str(tmp), capture_output=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture step"), cwd=str(tmp),
                   capture_output=True)


def _write_closes(path: Path) -> tuple[list[date], str]:
    sessions = [BASE + timedelta(days=i) for i in range(N_DAYS)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "session_date", "close"])
        for i, d in enumerate(sessions):
            close = 100.0 + 2.0 * math.sin(i * 0.7) + 0.5 * math.cos(i * 1.3)
            w.writerow(["AMBA", d.isoformat(), f"{close:.6f}"])
    return sessions, _sha256(path)


def _write_earnings(path: Path) -> str:
    rows = []
    for i, day in enumerate(EARNINGS_DAYS):
        d = BASE + timedelta(days=day)
        rows.append({"release_date": d.isoformat(),
                    "release_session": "BMO" if i % 2 == 0 else "AMC"})
    doc = {"per_peer_earnings_releases": {"AMBA": rows}}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return _sha256(path)


def _write_lock(path: Path, *, peer_closes_sha: str, peer_earnings_sha: str,
                n_permutations: int = 200) -> str:
    events = []
    for day in EVENT_DAYS:
        d = BASE + timedelta(days=day)
        events.append({
            "event_id": f"NVDA-{d.isoformat()}",
            "anchor_ticker": "NVDA", "peer_ticker": "AMBA",
            "release_date": d.isoformat(), "attributed_session": d.isoformat(),
            "shock": 0.20 if day == EVENT_DAYS[0] else -0.15,
        })
    doc = {
        "artifact": path.name,
        "locked_peer": "AMBA", "locked_anchor": "NVDA",
        "locked_events": events, "n_locked_events": len(events),
        "pins": {
            "peer_universe_sha256": _sha256(PEER_UNIVERSE_JSON),
            "anchor_shocks_sha256": _sha256(ANCHOR_SHOCKS_CSV),
            "peer_closes_sha256": peer_closes_sha,
            "peer_earnings_sha256": peer_earnings_sha,
            "target_py_sha256": _sha256(TARGET_PY),
            "constants_py_sha256": _sha256(CONSTANTS_PY),
            "clustered_se_py_sha256": _sha256(CLUSTERED_SE_PY),
        },
        "model_spec": {
            "primary_cluster_key": "event_id",
            "residualize": False,        # sidesteps earnings-cycle bucket
                                          # population -- see module docstring
            "n_permutations": n_permutations, "random_seed": 42,
        },
        "sample_size_disclosure": {
            "n_locked_events": len(events), "framing": "EXPLORATORY, NOT CONFIRMATORY",
            "why": "offline-test-fixture -- not a real disclosure",
        },
        "look_ahead_disclosure": {
            "already_touched": "offline-test-fixture", "not_touched": "offline-test-fixture",
        },
        "declared": True, "declared_by": "offline-test-fixture",
        "declared_date": "2026-09-12", "status": "DECLARED -- offline-test-fixture",
    }
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return _sha256(path)


def _write_authorization(path: Path, *, tmp: Path, lock_sha256: str,
                         consumed: bool = False) -> None:
    doc = {
        "artifact": path.name, "declared": True,
        "declared_by": "offline-test-fixture", "declared_date": "2026-09-12",
        "attestation_text": "offline-test-fixture",
        "pinned_commit_sha": _git(tmp, "rev-parse", "HEAD"),
        "pinned_phase2_lock_sha256": lock_sha256,
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
    lock_path = lse / "HYP05_PHASE2_LOCK_test.json"
    auth_path = lse / "HYP05_PHASE3_AUTHORIZATION_test.json"

    sessions, closes_sha = _write_closes(closes_path)
    earnings_sha = _write_earnings(earnings_path)
    lock_sha = _write_lock(lock_path, peer_closes_sha=closes_sha,
                           peer_earnings_sha=earnings_sha)
    _commit_all(tmp)  # clean tree required before _commit_sha runs
    _write_authorization(auth_path, tmp=tmp, lock_sha256=lock_sha)
    _commit_all(tmp)  # _commit_sha is called again inside build_result

    return {"tmp": tmp, "lse": lse, "closes": closes_path,
            "earnings": earnings_path, "lock": lock_path, "auth": auth_path,
            "sessions": sessions, "out": lse / "HYP05_PHASE3_RESULT_test.json"}


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
    check("1c. clustered on HYP-05's own primary key",
          "event_id" in result["d2_residual_limitation"],
          result["d2_residual_limitation"][:120])


# --------------------------------------------------------------------------
# 2. building the real panel
# --------------------------------------------------------------------------

def test_2_real_panel_built_from_ambas_calendar() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        closes_path = tmp / "closes.csv"
        earnings_path = tmp / "earnings.json"
        sessions, _ = _write_closes(closes_path)
        _write_earnings(earnings_path)
        lock = {"locked_events": [
            {"event_id": f"NVDA-{(BASE + timedelta(days=EVENT_DAYS[0])).isoformat()}",
             "anchor_ticker": "NVDA",
             "attributed_session": (BASE + timedelta(days=EVENT_DAYS[0])).isoformat(),
             "shock": 0.2},
        ]}
        panel, extra = P3._build_real_panel(
            lock=lock, peer_closes_path=closes_path,
            peer_earnings_path=earnings_path)
        check("2a. one anchor event built", len(panel.anchor_events) == 1)
        ev = panel.anchor_events[0]
        check("2b. anchor_day matches the attributed session's position",
              sessions[ev["anchor_day"]] == BASE + timedelta(days=EVENT_DAYS[0]))
        check("2c. peers is exactly [AMBA]", ev["peers"] == ["AMBA"], str(ev))
        check("2d. n_trading_days matches the session count",
              panel.n_trading_days == len(sessions))
        check("2e. extra provenance names the real sha256",
              extra["peer_closes_sha256"] == _sha256(closes_path))

        # wrong ticker in the closes file
        bad_closes = tmp / "bad_closes.csv"
        with bad_closes.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["ticker", "session_date", "close"])
            w.writerow(["NOTAMBA", "2016-01-01", "100.0"])
        expect_refusal(
            "2f. wrong ticker in the closes file refuses",
            lambda: P3._build_real_panel(
                lock=lock, peer_closes_path=bad_closes,
                peer_earnings_path=earnings_path),
            substring="NOTAMBA")

        # attributed session outside AMBA's own trading calendar
        lock_bad = {"locked_events": [
            {"event_id": "NVDA-2099-01-01", "anchor_ticker": "NVDA",
             "attributed_session": "2099-01-01", "shock": 0.2},
        ]}
        expect_refusal(
            "2g. an attributed session outside AMBA's calendar refuses",
            lambda: P3._build_real_panel(
                lock=lock_bad, peer_closes_path=closes_path,
                peer_earnings_path=earnings_path),
            substring="2099-01-01")


# --------------------------------------------------------------------------
# 3. the secondary robustness lens
# --------------------------------------------------------------------------

def test_3_secondary_lens_reports_or_refuses_per_horizon() -> None:
    from hyp04_supply_chain_hedge.fixtures import SyntheticPanel

    # Enough rows and >=2 distinct clusters on BOTH dimensions at horizon 1.
    n = N_DAYS
    rng_returns = np.array(
        [0.0] + [0.01 * math.sin(i) for i in range(1, n)], dtype=float)
    panel = SyntheticPanel(
        name="lens-test", returns={"AMBA": rng_returns},
        peer_earnings_days={"AMBA": [15, 90, 160]},
        anchor_events=[
            {"anchor": "NVDA", "anchor_day": 40, "shock": 0.2, "peers": ["AMBA"],
             "calendar_period": 20161},
            {"anchor": "NVDA", "anchor_day": 100, "shock": 0.1, "peers": ["AMBA"],
             "calendar_period": 20162},
            {"anchor": "NVDA", "anchor_day": 130, "shock": -0.1, "peers": ["AMBA"],
             "calendar_period": 20162},
        ],
        n_trading_days=n, injected_lag=None, injected_effect=0.0,
        injected_effect_window=0, peer_base_vol={}, earnings_ramp_amplitude=0.0,
    )
    out = P3._secondary_lens(panel, [1, 5], residualize=False)
    by_h = {r["horizon"]: r for r in out}
    check("3a. horizon 1 is computed (3 events, >=2 distinct clusters both dims)",
          "beta_shock" in by_h[1], str(by_h[1]))
    check("3b. primary_n_clusters is 3 (event_id)",
          by_h[1].get("primary_n_clusters") == 3, str(by_h[1]))
    check("3c. secondary_n_clusters is 2 (calendar_period)",
          by_h[1].get("secondary_n_clusters") == 2, str(by_h[1]))

    # Too few rows.
    empty_panel = SyntheticPanel(
        name="lens-empty", returns={"AMBA": np.full(n, np.nan)},
        peer_earnings_days={"AMBA": []},
        anchor_events=[{"anchor": "NVDA", "anchor_day": 40, "shock": 0.2,
                       "peers": ["AMBA"], "calendar_period": 20161}],
        n_trading_days=n, injected_lag=None, injected_effect=0.0,
        injected_effect_window=0, peer_base_vol={}, earnings_ramp_amplitude=0.0,
    )
    out2 = P3._secondary_lens(empty_panel, [1], residualize=False)
    check("3d. all-NaN returns -> 'no secondary lens computed', not a crash",
          "note" in out2[0] and "beta_shock" not in out2[0], str(out2[0]))

    # Only one distinct calendar_period across both events (same quarter).
    same_q_panel = SyntheticPanel(
        name="lens-samequarter", returns={"AMBA": rng_returns},
        peer_earnings_days={"AMBA": [15, 90, 160]},
        anchor_events=[
            {"anchor": "NVDA", "anchor_day": 40, "shock": 0.2, "peers": ["AMBA"],
             "calendar_period": 20161},
            {"anchor": "NVDA", "anchor_day": 45, "shock": -0.1, "peers": ["AMBA"],
             "calendar_period": 20161},
            {"anchor": "NVDA", "anchor_day": 50, "shock": 0.05, "peers": ["AMBA"],
             "calendar_period": 20161},
        ],
        n_trading_days=n, injected_lag=None, injected_effect=0.0,
        injected_effect_window=0, peer_base_vol={}, earnings_ramp_amplitude=0.0,
    )
    out3 = P3._secondary_lens(same_q_panel, [1], residualize=False)
    check("3e. one distinct calendar_period -> refuses the secondary lens "
          "rather than reporting a meaningless single-cluster SE",
          "fewer than 2 distinct clusters" in out3[0].get("note", ""),
          str(out3[0]))


# --------------------------------------------------------------------------
# 4. no authorization, no run
# --------------------------------------------------------------------------

def test_4_no_authorization_no_run() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        f["auth"].unlink()
        expect_refusal("4a. no authorization on disk refuses", lambda: _build(f),
                       substring="no HYP-05 Phase 3 authorization")


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
        lock["pins"]["clustered_se_py_sha256"] = "0" * 64
        f["lock"].write_text(json.dumps(lock, indent=1))
        expect_refusal("5b. clustered_se.py hash mismatch refuses",
                       lambda: _build(f), substring="clustered_se.py")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        with f["closes"].open("a", encoding="utf-8") as fh:
            fh.write("AMBA,2099-01-01,999.0\n")
        expect_refusal("5c. peer-closes drift after signing refuses",
                       lambda: _build(f), substring="peer closes")

    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = json.loads(f["auth"].read_text())
        doc["pinned_phase2_lock_sha256"] = "0" * 64
        f["auth"].write_text(json.dumps(doc, indent=1))
        _commit_all(f["tmp"])  # this check happens AFTER _commit_sha runs
        expect_refusal("5d. authorization pinned to a different lock hash refuses",
                       lambda: _build(f), substring="lock on disk now hashes")


# --------------------------------------------------------------------------
# 6. the happy path
# --------------------------------------------------------------------------

def test_6_happy_path_produces_a_sane_labeled_result() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = _build(f)

        check("6a. wrote the result file", f["out"].is_file())
        check("6b. locked_peer/anchor are correct",
              doc["locked_peer"] == "AMBA" and doc["locked_anchor"] == "NVDA")
        check("6c. n_locked_events == 2", doc["n_locked_events"] == 2)
        check("6d. reported_regardless_of_outcome is True",
              doc["reported_regardless_of_outcome"] is True)
        check("6e. no_rerun_permitted is True", doc["no_rerun_permitted"] is True)
        check("6f. carries the sample_size_disclosure verbatim from the lock",
              doc["sample_size_disclosure"]["framing"] == "EXPLORATORY, NOT CONFIRMATORY")
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
        _build(f)   # first, real run -- succeeds

        # A second, DIFFERENT authorization, freshly signed.
        auth2 = f["lse"] / "HYP05_PHASE3_AUTHORIZATION_test2.json"
        lock_sha = _sha256(f["lock"])
        _write_authorization(auth2, tmp=f["tmp"], lock_sha256=lock_sha)

        out2 = f["lse"] / "HYP05_PHASE3_RESULT_test2.json"
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
        f["out"].unlink()   # the result is gone; the authorization is not

        out2 = f["lse"] / "HYP05_PHASE3_RESULT_test2.json"
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
    test_2_real_panel_built_from_ambas_calendar()
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
    print("ALL HYP05_PHASE3_RUN TESTS PASSED")
    sys.exit(0)
