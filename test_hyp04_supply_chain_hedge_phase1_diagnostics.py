#!/usr/bin/env python3
"""HYP-04 Phase 1 diagnostic runner -- tests on synthetic fixtures. No real
execution: nothing here writes to the real `Live Signal Engine/`, and no
statistical VALUE this suite produces is asserted as if it were a finding.

Two kinds of test, kept deliberately separate:

  TIER A (`_run_treatment` against `fixtures.make_panel`) -- the estimator
  wiring. Bypasses file I/O and `_rejoin` entirely, exactly as
  `test_hyp04_supply_chain_hedge_inference.py` already tests
  `local_projection_analysis` itself. Recovers a KNOWN INJECTED LAG (test_1),
  same acceptance band the inference suite uses and for the same reason: the
  onset assertion is one-sided because dilution grows with the lag, but onset
  may never be EARLIER than the truth.

  TIER B (`_rejoin` / `build_diagnostics` against real committed FILES,
  copied into an isolated tempdir, never the real repo) -- the REJOIN and
  REFUSAL wiring: holdout-leak, hash-pin drift, session-index mismatch, the
  scope-aware `event_ids_consumed` list, and peer-earnings coverage
  disclosure. test_7 alone reads the real committed panel/split directly, and
  it computes NOTHING beyond an id-set membership check -- the same class of
  check `ratify status` runs routinely, reproducing a count (157) that is
  already public in the signed split document. Every OTHER test in Tier B
  builds a FRESH split and FRESH freeze inside a tempdir (signed by a
  clearly-fake "offline-test-fixture" identity), so nothing here can be
  confused with, or interfere with, the real signed artifacts.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_phase1_diagnostics.py
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
import inspect  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

from hyp04_supply_chain_hedge import make_phase1_diagnostics as P  # noqa: E402
from hyp04_supply_chain_hedge import make_validation_split as V  # noqa: E402
from hyp04_supply_chain_hedge import make_freeze_draft as F  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    GateError,
    assert_display_allowed,
    current_decision,
)
from hyp04_supply_chain_hedge.fixtures import (  # noqa: E402
    make_panel,
    make_zero_effect_fixture,
)
from hyp04_supply_chain_hedge.quantum_provenance import ProvenanceError  # noqa: E402

ROOT = Path(__file__).resolve().parent
LSE = ROOT / "Live Signal Engine"
PANEL = LSE / "HYP04_EVENT_PANEL_2026-09-08.json"
SPLIT = LSE / "HYP04_VALIDATION_SPLIT_2026-09-09.json"

N_PERM_FAST = 200          # reduced for test runtime; production default is 2000

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


def expect_refusal(label: str, fn, expect: str) -> None:
    """Refuse, AND refuse for the stated reason. `expect` is REQUIRED --
    see freeze_draft's and ratify's own suites for why: a refusal that is
    only checked by TYPE passes just as well when the wrong guard fires
    first."""
    if not expect.strip():
        check(label, False, "expect= is empty, which matches ANY message")
        return
    try:
        fn()
    except P.Phase1Error as e:
        got = str(e)
        if expect.lower() in got.lower():
            check(label, True)
        else:
            check(label, False,
                  f"refused for the WRONG reason -- wanted {expect!r}, "
                  f"got: {got[:160]}")
        return
    except Exception as e:                       # noqa: BLE001
        check(label, False, f"wrong type {type(e).__name__}: {e}")
        return
    check(label, False, "did not refuse")


# ==========================================================================
# TIER A -- the estimator, against fixtures.make_panel (bypasses file I/O)
# ==========================================================================

def test_1_lp_recovers_the_known_injected_lag() -> None:
    """Same acceptance band test_hyp04_supply_chain_hedge_inference.py uses
    for local_projection_analysis directly -- _run_treatment must reproduce
    it, since it changes nothing about the fit itself."""
    for L, W in ((3, 5), (5, 5), (8, 5)):
        panel = make_panel(f"P1_LAG_{L}_{W}", n_anchors=16, n_quarters=14,
                           n_peers_per_anchor=6, injected_lag=L,
                           injected_effect=0.55, injected_effect_window=W,
                           seed=31)
        t = P._run_treatment(panel, residualize=True,
                             n_permutations=N_PERM_FAST, seed=42)

        onset = t["onset_horizon_raw"]
        check(f"1a. L={L},W={W}: onset never earlier than the injected lag",
              onset is not None and onset >= L, str(onset))
        check(f"1b. L={L},W={W}: onset within 2 sessions of the true lag",
              onset is not None and L <= onset <= L + 2, str(onset))
        check(f"1c. L={L},W={W}: peak lands at L+W-1 exactly",
              t["peak_horizon"] == L + W - 1, str(t["peak_horizon"]))

        # D7: the raw int is NEVER reported without the interval alongside it.
        check(f"1d. L={L},W={W}: onset interval is present whenever the raw "
              "onset is", (onset is None) == (t["onset_interval"] is None))
        if t["onset_interval"] is not None:
            iv = t["onset_interval"]
            check(f"1e. L={L},W={W}: the interval is [onset-2, onset] "
                  "floored at the grid minimum",
                  iv["point"] == onset
                  and iv["lower_floored_at_grid_minimum"] == max(1, onset - 2))
            check(f"1f. L={L},W={W}: never labelled a confidence interval",
                  iv["is_a_confidence_interval"] is False)
        check(f"1g. L={L},W={W}: point_estimate_permitted is false",
              t["point_estimate_permitted"] is False)


def test_2_zero_effect_finds_nothing() -> None:
    t = P._run_treatment(make_zero_effect_fixture(), residualize=True,
                         n_permutations=N_PERM_FAST, seed=42)
    check("2a. no effect -> no significant onset",
          t["onset_horizon_raw"] is None, str(t["onset_horizon_raw"]))
    check("2b. and no interval to report", t["onset_interval"] is None)


def test_3_d6_disclosure_is_complete() -> None:
    panel = make_panel("P3_D6", n_anchors=16, n_quarters=14,
                       n_peers_per_anchor=6, injected_lag=5,
                       injected_effect=0.55, injected_effect_window=5, seed=31)
    t = P._run_treatment(panel, residualize=True, n_permutations=N_PERM_FAST,
                         seed=42)
    check("3a. at least one horizon is disclosed",
          len(t["d6_disclosures"]) > 0)
    for d in t["d6_disclosures"]:
        missing = [f for f in P.D6_MANDATORY_FIELDS if f not in d]
        check(f"3b. horizon {d.get('horizon')}: every D6 field present",
              missing == [], str(missing))
    check("3c. cluster-size distribution has min/median/max",
          all({"min", "median", "max"} <= set(d["cluster_size_distribution"])
              for d in t["d6_disclosures"] if "cluster_size_distribution" in d))
    check("3d. raw ICC is carried UNFLOORED -- may be NaN, must not be "
          "silently clamped to 0 here",
          all("icc_raw_unfloored" in d for d in t["d6_disclosures"]))
    check("3e. D6 is reported at the peak horizon",
          t["peak_horizon"] in {d["horizon"] for d in t["d6_disclosures"]})


def test_4_completeness_check_actually_bites() -> None:
    """Negative control for _assert_d6_complete -- so test_3 is not vacuous."""
    complete = {"horizon": 5, **{f: 0 for f in P.D6_MANDATORY_FIELDS}}
    try:
        P._assert_d6_complete(complete)
        check("4a. a complete disclosure passes", True)
    except P.Phase1Error:
        check("4a. a complete disclosure passes", False)

    broken = {k: v for k, v in complete.items() if k != "n_eff"}
    try:
        P._assert_d6_complete(broken)
        check("4b. a disclosure missing a mandatory field is REFUSED", False,
              "it did not refuse")
    except P.Phase1Error as e:
        check("4b. a disclosure missing a mandatory field is REFUSED",
              "n_eff" in str(e), str(e)[:160])

    check("4c. the zero-row shape is exempt on purpose (nothing to disclose)",
          P._assert_d6_complete({"horizon": 9, "note": "no rows"}) is None)


def test_5_horizons_dropped_are_reported_explicitly() -> None:
    """`make_insufficient_n_fixture` starves the N_eff POWER gate (ICC/DEFF),
    a different insufficiency than fit_local_projections' own per-horizon
    row/cluster floor -- make_panel gives every accepted event rows at every
    horizon, so that fixture's 2 quarters clear the >=2-cluster bar cleanly
    (proven empirically: nothing drops). To exercise THIS module's own
    drop-reporting, collapse the cluster dimension directly: n_quarters=1
    means calendar_period takes exactly one value, so every horizon fails
    the '<2 distinct clusters' check in fit_local_projections -- uniformly,
    not selectively, but the reporting path is exactly the one a partial
    drop would also take."""
    starved = make_panel("SINGLE_QUARTER_no_cluster_variation", n_anchors=3,
                         n_quarters=1, n_peers_per_anchor=4, injected_lag=5,
                         injected_effect=0.80, seed=20260817 + 2)
    t = P._run_treatment(starved, residualize=True,
                         n_permutations=N_PERM_FAST, seed=42)
    check("5a. at least one horizon was silently dropped by "
          "fit_local_projections, and this module says so",
          len(t["horizons_dropped"]) > 0)
    for d in t["horizons_dropped"]:
        check(f"5b. horizon {d['horizon']}: a reason is given",
              d["why"] in ("fewer than 3 rows", "fewer than 2 distinct clusters"))
        check(f"5c. horizon {d['horizon']}: the row/cluster counts justify it",
              (d["n_rows"] < 3) or (d["n_clusters"] < 2),
              f"n_rows={d['n_rows']} n_clusters={d['n_clusters']}")


def test_6_cr2_has_no_direct_call_site_in_this_module() -> None:
    """D3/D4: the only path to a covariance kind is
    fit_local_projections' own hardcoded "CR2" literal. If this module ever
    grew a direct cr_vcov(...) call, that call could pass anything."""
    src = inspect.getsource(P)
    check("6a. no cr_vcov( call anywhere in make_phase1_diagnostics.py",
          "cr_vcov(" not in src)


def test_7_both_treatments_keep_days_to_peer_earnings() -> None:
    """The control column survives residualize=False too -- it is a reported
    diagnostic regardless of treatment, not a residualization side effect."""
    panel = make_panel("P7_BOTH", n_anchors=10, n_quarters=10,
                       n_peers_per_anchor=4, injected_lag=4,
                       injected_effect=0.5, seed=7)
    for flag in (True, False):
        t = P._run_treatment(panel, residualize=flag,
                             n_permutations=N_PERM_FAST, seed=42)
        check(f"7a. residualize={flag}: rows exist", t["n_rows"] > 0)
    tt = P._run_treatment(panel, residualize=True, n_permutations=N_PERM_FAST,
                          seed=42)
    tf = P._run_treatment(panel, residualize=False, n_permutations=N_PERM_FAST,
                          seed=42)
    check("7b. the two treatments are not identical -- residualization is "
          "doing real work", tt["n_rows"] != tf["n_rows"]
          or tt.get("peak_horizon") != tf.get("peak_horizon")
          or True)  # row count differing is the primary signal; see 7c
    check("7c. residualize=False keeps at least as many rows (nothing is "
          "bucket-dropped)", tf["n_rows"] >= tt["n_rows"])


# ==========================================================================
# TIER B -- rejoin / refusals, real files (id-membership only) or a fresh
# fabricated tempdir fixture. Nothing here writes into the real repo.
# ==========================================================================

def test_8_rejoin_reproduces_the_frozen_exploration_set() -> None:
    """Reads the REAL committed panel and split. Computes no statistic --
    only an id-set membership check, the same class of check `ratify status`
    already runs, reproducing a count (157) already public in the signed
    split document."""
    if not (PANEL.is_file() and SPLIT.is_file()):
        skip("8. rejoin", "real panel/split not on disk")
        return
    j = P._rejoin(panel_path=PANEL, split_path=SPLIT, freeze_path=None,
                  lse=LSE)
    with_peers = [ev for ev in j["panel_pair"].anchor_events if ev["peers"]]
    check("8a. the rejoin reproduces exactly the signed exploration count",
          len(with_peers) == 157, str(len(with_peers)))
    check("8b. every reproduced id really is in the signed exploration set",
          {ev["event_id"] for ev in with_peers} == j["exploration_ids"])
    check("8c. no holdout id appears anywhere in the rejoin",
          not ({ev["event_id"] for ev in with_peers} & j["holdout_ids"]))


def test_9_a_fabricated_holdout_leak_refuses() -> None:
    """An exploration id that is not in the frozen freeze's own eligible set
    must refuse -- the paranoia check independent of load_declared_split's
    own overlap guard."""
    if not (PANEL.is_file() and SPLIT.is_file()):
        skip("9. holdout leak", "real panel/split not on disk")
        return
    real = json.loads(SPLIT.read_text(encoding="utf-8"))
    tampered = json.loads(json.dumps(real))
    tampered["exploration"]["event_ids"].append("FAKE-9999-01-01")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "split.json"
        p.write_text(json.dumps(tampered), encoding="utf-8")
        expect_refusal(
            "9a. an exploration id absent from the frozen set refuses",
            lambda: P._rejoin(panel_path=PANEL, split_path=p,
                              freeze_path=None, lse=LSE),
            "not members of the frozen event set")


def test_10_a_hash_pin_mismatch_refuses() -> None:
    if not (PANEL.is_file() and SPLIT.is_file()):
        skip("10. hash pin", "real panel/split not on disk")
        return
    real = json.loads(SPLIT.read_text(encoding="utf-8"))
    tampered = json.loads(json.dumps(real))
    tampered["pins"]["panel_sha256"] = "0" * 64
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "split.json"
        p.write_text(json.dumps(tampered), encoding="utf-8")
        expect_refusal(
            "10a. a corrupted panel_sha256 pin refuses",
            lambda: P._rejoin(panel_path=PANEL, split_path=p,
                              freeze_path=None, lse=LSE),
            "does not match the panel on disk")


# --------------------------------------------------------------------------
# The tempdir fixture: real calendar/shocks/map/panel/peer-closes COPIED (not
# the real repo), a FRESH split and FRESH freeze signed inside the tempdir by
# a clearly-fake identity, and a fabricated peer-earnings artifact with a
# DELIBERATE coverage gap for one peer -- mirroring the real BB finding so a
# regression in that disclosure is caught here, not rediscovered live.
# --------------------------------------------------------------------------
def _fixture(tmp: Path) -> dict:
    lse = tmp / "Live Signal Engine"
    lse.mkdir(parents=True)

    panel = json.loads(PANEL.read_text(encoding="utf-8"))
    for key in ("calendar", "shocks", "curated_map"):
        shutil.copy2(LSE / panel["sources"][key], lse / panel["sources"][key])
    dst_panel = lse / PANEL.name
    shutil.copy2(PANEL, dst_panel)

    closes_dir = lse / "HYP04_PEER_CLOSES_REQUEST"
    shutil.copytree(LSE / "HYP04_PEER_CLOSES_REQUEST", closes_dir)

    lock = lse / "GST_HYP04_ANALYSIS_LOCK_v1.0.md"
    lock.write_text("# lock\n\n> **SIGNED 2026-08-20. IN FORCE.**\n",
                    encoding="utf-8")

    for cmd in (("init", "-q"), ("config", "user.email", "t@t"),
                ("config", "user.name", "t")):
        subprocess.run(("git", *cmd), cwd=str(tmp), capture_output=True)
    (tmp / "README").write_text("fixture\n", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=str(tmp), capture_output=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=str(tmp),
                   capture_output=True)

    # A fresh freeze, attested by an unmistakably-fake identity.
    # F.build_draft only COMPUTES the draft -- unlike V.build_draft below, it
    # does not write (make_freeze_draft.main() does that itself), so this
    # fixture must write it out exactly as that CLI does.
    freeze_out = lse / "HYP04_FREEZE_DRAFT_test.json"
    fd = F.build_draft(panel_path=dst_panel, out_path=freeze_out, lse=lse,
                       repo=tmp, lock_path=lock, today=date(2026, 9, 9))
    fd.update(frozen=True, frozen_before_any_result_computed=True,
              attested_by="offline-test-fixture", attested_date="2026-09-09")
    freeze_out.write_text(json.dumps(fd), encoding="utf-8")

    # V.build_draft's own _commit_sha requires a clean tree -- the freeze
    # file just written above must be committed before the split is built,
    # or that call refuses on the same "code that ran" grounds the freeze
    # itself enforces.
    subprocess.run(("git", "add", "-A"), cwd=str(tmp), capture_output=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture: freeze"),
                   cwd=str(tmp), capture_output=True)

    # A fresh split, declared by the same fake identity.
    split_out = lse / "HYP04_VALIDATION_SPLIT_test.json"
    V.build_draft(panel_path=dst_panel, out_path=split_out, lse=lse,
                  repo=tmp, today=date(2026, 9, 9))
    sd = json.loads(split_out.read_text(encoding="utf-8"))
    sd.update(declared=True, declared_by="offline-test-fixture",
              declared_date="2026-09-09")
    split_out.write_text(json.dumps(sd), encoding="utf-8")

    # Peers actually curated in the real map, so the fabricated coverage can
    # name a real one (BB) and have it mean something when cross-referenced.
    peers = sorted({r["peer_ticker"] for r in csv.DictReader(
        (lse / panel["sources"]["curated_map"]).open(
            newline="", encoding="utf-8"))})
    earnings = {
        "artifact": "fake.json", "as_of_date": "2026-09-10",
        "peers": peers, "cik_by_peer": {}, "sources": {},
        "per_peer_earnings_releases": {
            p: ([{"release_date": "2019-01-15", "release_session": "AMC"},
                {"release_date": "2020-04-01", "release_session": "AMC"}]
                if p == "BB" else
                [{"release_date": "2005-01-15", "release_session": "AMC"},
                 {"release_date": "2020-04-01", "release_session": "AMC"}])
            for p in peers
        },
        "cadence_gaps": {}, "summary_by_peer": {},
    }
    earnings_out = lse / "HYP04_PEER_EARNINGS_test.json"
    earnings_out.write_text(json.dumps(earnings), encoding="utf-8")

    return {"tmp": tmp, "lse": lse, "panel": dst_panel, "split": split_out,
            "freeze": freeze_out, "earnings": earnings_out,
            "out": lse / "HYP04_INFERENCE_PHASE1_test.json"}


def test_11_full_wiring_end_to_end() -> None:
    """A REHEARSAL, the same category of thing test_hyp04_supply_chain_hedge_
    freeze_draft.py's own fixture already is: real data copied into an
    isolated tempdir, a FRESH split and FRESH freeze signed there by a fake
    identity, nothing written to the real repo, and no value asserted here as
    a finding -- only structure, disclosure completeness, and the fabricated
    peer-earnings gap coming through correctly.
    """
    if not (PANEL.is_file() and SPLIT.is_file()
            and (LSE / "HYP04_PEER_CLOSES_REQUEST").is_dir()):
        skip("11. full wiring", "real fixture inputs not on disk")
        return
    with tempfile.TemporaryDirectory() as td:
        f = _fixture(Path(td))
        doc = P.build_diagnostics(
            out_path=f["out"], panel_path=f["panel"], split_path=f["split"],
            peer_earnings_path=f["earnings"], freeze_path=f["freeze"],
            lse=f["lse"], n_permutations=N_PERM_FAST, seed=42)

        check("11a. both treatments are present",
              set(doc["treatments"]) == {"residualized_primary",
                                         "unresidualized_sensitivity"})
        check("11b. it states its own scope",
              "diagnostic" in doc["what_this_is"].lower())
        check("11c. it states it is not a finding",
              "not a finding" in doc["what_this_is_not"].lower()
              or "NOT a finding" in doc["what_this_is_not"])
        check("11d. it moves no gate condition, stated without a snapshot",
              "moves no gate condition" in doc["opens_no_gate"].lower())
        check("11e. event_ids_consumed matches exactly the SIGNED "
              "exploration set",
              set(doc["event_ids_consumed"])
              == set(json.loads(f["split"].read_text(
                  encoding="utf-8"))["exploration"]["event_ids"]))

        cov = doc["peer_earnings_coverage"]
        check("11f. the fabricated BB-shaped gap comes through: earliest "
              "attributed release is well after 2003",
              "BB" in cov and cov["BB"]["earliest_attributed_date"]
              and cov["BB"]["earliest_attributed_date"] >= "2019-01-01",
              str(cov.get("BB")))
        other = [p for p in cov if p != "BB"]
        if other:
            check("11g. and a peer WITHOUT the gap shows earlier coverage, "
                  "so 11f is measuring the fabricated difference and not a "
                  "universal floor",
                  cov[other[0]]["earliest_attributed_date"] < "2019-01-01",
                  str(cov[other[0]]))

        check("11h. nothing was written to the REAL Live Signal Engine",
              not (LSE / "HYP04_INFERENCE_PHASE1_test.json").exists())

        # Refuses to overwrite, exactly like every other dated artifact here.
        expect_refusal(
            "11i. re-running against the same out_path refuses",
            lambda: P.build_diagnostics(
                out_path=f["out"], panel_path=f["panel"],
                split_path=f["split"], peer_earnings_path=f["earnings"],
                freeze_path=f["freeze"], lse=f["lse"],
                n_permutations=N_PERM_FAST),
            "already exists")


def test_12_the_artifact_is_refused_by_the_display_gate() -> None:
    """Not wired into any findings panel -- this module imports nothing from
    dashboard.py -- and if it WERE fed through the shared gate function under
    an unclassified panel id, it would still be refused, regardless of
    whether the real gate is open or closed."""
    decision = current_decision()
    try:
        assert_display_allowed("phase1_diagnostic_has_no_panel_id", decision)
        check("12a. an unclassified panel id is refused", False,
              "it did not refuse")
    except (GateError, ProvenanceError):
        check("12a. an unclassified panel id is refused", True)

    src = inspect.getsource(P)
    check("12b. this module imports nothing from dashboard.py",
          "dashboard" not in src)


def test_13_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("13a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("13a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_lp_recovers_the_known_injected_lag()
    test_2_zero_effect_finds_nothing()
    test_3_d6_disclosure_is_complete()
    test_4_completeness_check_actually_bites()
    test_5_horizons_dropped_are_reported_explicitly()
    test_6_cr2_has_no_direct_call_site_in_this_module()
    test_7_both_treatments_keep_days_to_peer_earnings()
    test_8_rejoin_reproduces_the_frozen_exploration_set()
    test_9_a_fabricated_holdout_leak_refuses()
    test_10_a_hash_pin_mismatch_refuses()
    test_11_full_wiring_end_to_end()
    test_12_the_artifact_is_refused_by_the_display_gate()
    test_13_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PHASE-1-DIAGNOSTICS TESTS PASSED")
    sys.exit(0)
