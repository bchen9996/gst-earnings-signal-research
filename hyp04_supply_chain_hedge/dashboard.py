#!/usr/bin/env python3
"""HYP-04 Phase 0 status dashboard -- infrastructure and process metrics.

READS EXISTING OUTPUTS. COMPUTES NO NEW STATISTICS.

Every number rendered here is either read from a committed artifact or is a
count of test results produced by running the committed suites. This module
performs no regression, no permutation, no estimation of any kind. If a figure
is not already on disk or already established as instrument calibration, it
does not appear.

WHAT IS SHOWN vs WHAT IS GATED

Shown, because it is PROGRESS and the governing document explicitly permits it
("Progress is public; findings are gated"):

  * build and test status, per suite
  * options-coverage audit: tickers, coverage %, expiration/contract spread
  * instrument calibration: how the 193 floor was derived, and why
  * registry status, and the Phase 0 -> 4 roadmap with the Phase 1 blocker

GATED, and locked in code rather than by convention:

  * lag scores, onset/peak horizons, beta_h coefficients, direction,
    link-strength scores, CCF and placebo outcomes, Stage 2 recommendations

Those panels are not omitted by editorial choice -- they route through
`display_gate.assert_display_allowed`, which raises unless every condition of
`GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md` holds. The dashboard cannot
render one by accident, and an unclassified panel is treated as a finding and
denied rather than shown.

A SECOND, INDEPENDENT CONTROL runs through the same chokepoint: any
quantum-derived model output is refused from EVERY panel -- findings and
progress alike -- unless it has been validated against the classical reference
on known cases, regardless of whether it came from this project's own tertiary
cross-check module or from outside the repository. See quantum_provenance.py.
That control is not the gate and the gate is not that control; both must pass.

THE AUDIT NUMBERS ARE DATA AVAILABILITY, NOT A HYPOTHESIS CLAIM. 100% option
chain coverage says option chains exist. It says nothing about transmission,
and yfinance serves current chains only, so it does not establish that implied
volatility is usable as a target at all.

Usage:
    python -m hyp04_supply_chain_hedge.dashboard --out dashboard.html
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .display_gate import (
    FINDINGS_PANELS,
    PENDING_TOKEN,
    GateDecision,
    assert_display_allowed,
    current_decision,
    locked_panel_placeholder,
)
from .quantum_provenance import MethodProvenance
from .quantum_provenance import current_status as quantum_control_status

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

CANARY = LSE / "HYP04_PHASE0_COVERAGE_AUDIT_CANARY_2026-08-17.json"
FULL = LSE / "HYP04_PHASE0_COVERAGE_AUDIT_FULL_2026-08-17.json"
REGISTRY = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.10.json"

# Suites this page runs.
#
# HYP-04's own suites are DISCOVERED, not enumerated. A hand-maintained tuple
# stood here and silently omitted three of them -- agreements, curated_linkage
# and edgar -- so a page titled "HYP-04 Phase 0" reported 641 checks when the
# package actually carried 768. The suites were passing the whole time; the
# page just wasn't looking at them. That is the same failure the docstring
# below warns about, one scope down, so the list is now derived from disk.
#
# The glob matches the one in .github/workflows/hyp04-supply-chain-hedge-tests.yml,
# so CI and this page cover the same set by construction rather than by two
# lists being edited in step. The CI guard that keeps side-effecting runners
# (the live audit runners, make_registry_v1_2.py) off the test_* pattern is
# what makes discovery safe here too.
HYP04_SUITE_GLOB = "test_hyp04_supply_chain_hedge*.py"

# Not HYP-04's own, but governs the registry this page's gate reads, so a
# regression there would invalidate the gate state shown above. Named
# explicitly because it does not match the glob.
EXTRA_SUITES = (
    "test_market_response_hypothesis_registry_v1_1.py",
)


def _discover_suites() -> tuple[str, ...]:
    found = sorted(p.name for p in REPO_ROOT.glob(HYP04_SUITE_GLOB))
    return tuple(found) + tuple(
        n for n in EXTRA_SUITES if (REPO_ROOT / n).is_file())


TEST_SUITES = _discover_suites()


# ==========================================================================
# Readers -- each returns what is on disk, or an explicit "unavailable".
# ==========================================================================
def _n_root_test_files() -> int:
    """How many test files the repository root carries.

    A count of files on disk, not a count of checks. The distinction matters:
    this page runs the suites in TEST_SUITES and reports what they printed, so
    it can state their check counts honestly. It cannot state a repo-wide check
    total without running everything, and a hand-maintained one goes stale --
    which is exactly what happened to the figure this replaced.

    No count of suites is written here either, for the same reason: TEST_SUITES
    is discovered, and a number in this sentence would be one more thing that
    silently stops being true.
    """
    return len(list(REPO_ROOT.glob("test_*.py")))


def _read_json(p: Path) -> Optional[dict]:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return None


def read_audit() -> dict[str, Any]:
    """Combined coverage audit. Pure aggregation of two committed reports."""
    canary, full = _read_json(CANARY), _read_json(FULL)
    if canary is None or full is None:
        return {"available": False,
                "why": "one or both coverage-audit reports are missing or unreadable"}

    rows = [r for r in canary["per_ticker"] + full["per_ticker"]
            if r["coverage"] != "not_attempted"]
    ok = [r for r in rows if r["coverage"] == "ok"]
    exps = sorted(r["n_expirations"] for r in ok if r["n_expirations"] is not None)
    contracts = sorted((r["n_calls_contracts"] or 0) + (r["n_puts_contracts"] or 0)
                       for r in ok)

    def _q(xs: list[int], f: float) -> Optional[int]:
        if not xs:
            return None
        return xs[min(len(xs) - 1, int(f * (len(xs) - 1)))]

    return {
        "available": True,
        "stages": [
            {"stage": "canary", "tickers": canary["summary"]["tickers_attempted"],
             "calls": canary["summary"]["total_calls"],
             "cap": canary["summary"]["hard_cap_calls"],
             "ok": canary["summary"]["coverage_ok"],
             "transport_failures": canary["summary"]["transport_failures"],
             "pacing_s": canary.get("inter_call_delay_seconds", 0.0)},
            {"stage": "full", "tickers": full["summary"]["tickers_attempted"],
             "calls": full["summary"]["total_calls"],
             "cap": full["summary"]["hard_cap_calls"],
             "ok": full["summary"]["coverage_ok"],
             "transport_failures": full["summary"]["transport_failures"],
             "pacing_s": full.get("inter_call_delay_seconds", 0.0)},
        ],
        "total_tickers": len(rows),
        "total_calls": canary["summary"]["total_calls"] + full["summary"]["total_calls"],
        "coverage_ok": len(ok),
        "coverage_pct": 100.0 * len(ok) / len(rows) if rows else 0.0,
        "transport_failures": (canary["summary"]["transport_failures"]
                               + full["summary"]["transport_failures"]),
        "calls_per_ticker_constant": (canary["summary"]["calls_per_ticker_constant"]
                                      and full["summary"]["calls_per_ticker_constant"]),
        "provider": canary["provider"],
        "credentials": canary["credentials_used"],
        "expirations": {"min": exps[0] if exps else None,
                        "p50": _q(exps, 0.5), "max": exps[-1] if exps else None},
        "contracts": {"min": contracts[0] if contracts else None,
                      "p50": _q(contracts, 0.5),
                      "max": contracts[-1] if contracts else None},
        "thinnest": sorted(ok, key=lambda r: (r["n_calls_contracts"] or 0)
                           + (r["n_puts_contracts"] or 0))[:3],
        "deepest": sorted(ok, key=lambda r: -((r["n_calls_contracts"] or 0)
                          + (r["n_puts_contracts"] or 0)))[:3],
    }


def read_curated_linkage() -> dict[str, Any]:
    """How many linkage edges are actually curated, READ FROM DISK.

    This replaces the sentence "zero rows are curated", which was hardcoded
    into the page and into the display gate's C5 denial. It was true when
    written and stopped being true on 2026-08-22, which is the same failure
    this file's own suite-discovery comment describes: a number asserted in
    prose goes stale silently, and a governance page asserting a stale zero is
    worse than one asserting nothing.
    """
    from .curated_linkage import load_curated_linkage

    maps = sorted(p for p in LSE.glob("HYP04_Linkage_Map*.csv")
                  if "TEMPLATE" not in p.name.upper())
    if not maps:
        return {"available": True, "map_present": False, "edges": 0,
                "rows_rejected": 0, "source": None}
    res = load_curated_linkage(maps[0])
    return {
        "available": True,
        "map_present": True,
        "source": maps[0].name,
        "edges": len(res.edges),
        "rows_seen": res.rows_seen,
        "rows_rejected": res.rows_rejected,
        "loads_clean": res.ok,
    }


# NEWEST, NOT FIRST.
#
# These readers globbed a dated pattern and took `sorted(...)[0]` -- the
# EARLIEST name. That was harmless only while exactly one artifact existed. The
# moment a same-day revision appears (the `_vN` convention the linkage-history
# artifacts already use), `[0]` pins the page to the SUPERSEDED file while the
# page goes on looking current -- a stale number rendered with full confidence,
# which is the failure class this dashboard's derive-at-render-time rule exists
# to prevent.
#
# Lexical sort is correct for these names because the date is ISO and the
# revision suffix sorts after the bare name: 2026-08-29 < 2026-08-29_v2, and
# 2026-08-29_v2 < 2026-08-30. It is not correct in general, so if the naming
# convention ever changes this has to change with it.
def _newest(paths: "list[Any]") -> Any:
    return sorted(paths)[-1]


def read_anchor_event_calendar() -> dict[str, Any]:
    """The anchor-event CALENDAR, COUNTED FROM DISK at render time.

    Different from `read_anchor_event_candidates`, which reads a per-ticker
    walk with no membership filter. This reads the calendar: releases that fall
    INSIDE a span during which the filer was a registered anchor.

    The totals are COUNTED FROM THE CSV ROWS, not read out of the JSON's own
    summary fields, so a stale summary in the artifact cannot render as a
    current number. Only the two things the CSV cannot express -- the measured
    alternative that was not adopted, and the member-years with no results item
    code -- are taken from the JSON.
    """
    import csv as _csv
    import json as _json

    csvs = list(LSE.glob("HYP04_ANCHOR_EVENT_CALENDAR_*.csv"))
    if not csvs:
        return {"present": False}
    newest_csv = _newest(csvs)
    rows = list(_csv.DictReader(newest_csv.open(encoding="utf-8", newline="")))

    by_session: dict[str, int] = {}
    by_anchor: dict[str, int] = {}
    for r in rows:
        by_session[r.get("release_session", "?")] = \
            by_session.get(r.get("release_session", "?"), 0) + 1
        by_anchor[r.get("anchor_ticker", "?")] = \
            by_anchor.get(r.get("anchor_ticker", "?"), 0) + 1

    out: dict[str, Any] = {
        "present": True,
        "source": newest_csv.name,
        "total": len(rows),
        "by_session": by_session,
        "by_anchor": by_anchor,
        "resolved_session": by_session.get("BMO", 0) + by_session.get("AMC", 0),
        "alternative_total": None,
        "blind_member_years": None,
        "superseded": None,
    }
    js = list(LSE.glob("HYP04_ANCHOR_EVENT_CALENDAR_*.json"))
    if js:
        try:
            d = _json.loads(_newest(js).read_text(encoding="utf-8"))
        except ValueError:
            return out
        primary = (d.get("primary_specification")
                   or d.get("primary_specification_unchanged") or {})
        alt = (d.get("superseded_specification_reproduced")
               or d.get("measured_alternative_not_adopted") or {})
        out["alternative_total"] = alt.get("candidate_events_total")
        out["superseded"] = primary.get("duplicate_filings_superseded")
        out["blind_member_years"] = \
            primary.get("member_years_with_no_results_item_code")
        # A disagreement between the artifact's own summary and the rows it
        # shipped with is a fact worth surfacing, not smoothing over.
        out["summary_disagrees"] = (
            primary.get("candidate_events_total") not in (None, len(rows)))
    return out


def read_anchor_event_candidates() -> dict[str, Any]:
    """Candidate anchor events, COUNTED FROM DISK at render time.

    Never bake these numbers into the page. The count changes every time the
    walk is re-run or the addenda file gains a row, and a hardcoded total is
    the same defect as the "zero rows are curated" sentence this file already
    had to remove once.

    Counted separately by provenance, because a derived row is reproducible by
    re-running the walk and a curated row is somebody's reading of a filing.
    Collapsing them would hide which is which.
    """
    import csv as _csv

    files = list(LSE.glob("HYP04_ANCHOR_EVENT_CANDIDATES*.csv"))
    if not files:
        return {"present": False}

    newest = _newest(files)
    rows = list(_csv.DictReader(newest.open(encoding="utf-8", newline="")))
    by_anchor: dict[str, int] = {}
    by_session: dict[str, int] = {}
    by_prov: dict[str, int] = {}
    for r in rows:
        by_anchor[r.get("anchor_ticker", "?")] = \
            by_anchor.get(r.get("anchor_ticker", "?"), 0) + 1
        by_session[r.get("release_session", "?")] = \
            by_session.get(r.get("release_session", "?"), 0) + 1
        by_prov[r.get("provenance", "unrecorded")] = \
            by_prov.get(r.get("provenance", "unrecorded"), 0) + 1
    dates = sorted(r.get("release_date", "") for r in rows if r.get("release_date"))
    # Per-anchor release DATES, because registry v1.6 makes membership a span
    # rather than a flag: a candidate event counts only if its anchor was a
    # registered member ON THAT DATE. Counting by ticker alone would credit an
    # anchor for events outside its own interval.
    dates_by_anchor: dict[str, list[str]] = {}
    for r in rows:
        d = r.get("release_date")
        if d:
            dates_by_anchor.setdefault(r.get("anchor_ticker", "?"), []).append(d)
    return {
        "present": True,
        "dates_by_anchor": dates_by_anchor,
        "source": newest.name,
        "total": len(rows),
        "by_anchor": by_anchor,
        "by_session": by_session,
        "by_provenance": by_prov,
        "earliest": dates[0] if dates else None,
        "latest": dates[-1] if dates else None,
    }


def _registry_title(registry: dict[str, Any]) -> str:
    """Title read from the artifact.

    This was the literal string "Hypothesis registry v1.1" through three
    version bumps -- a copy of a fact that had moved. Deriving it means the
    next bump cannot leave it behind.
    """
    v = registry.get("registry_version")
    return f"Hypothesis registry v{v}" if v else "Hypothesis registry"


def read_registry() -> dict[str, Any]:
    doc = _read_json(REGISTRY)
    if doc is None:
        return {"available": False}
    entry = next((h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-04"), None)
    return {
        "available": True,
        "registry_version": doc["registry_version"],
        "authored": doc["authored_at_utc"],
        "supersedes": doc.get("supersedes"),
        "named_hypotheses": doc["critical_distinction"]["named_hypotheses"],
        "hyp04_status": entry["status"] if entry else None,
        "hyp04_class": entry["classification"] if entry else None,
        "hyp04_threshold": entry["minimum_eligible_events"] if entry else None,
        "hyp04_unit": entry.get("minimum_eligible_events_unit") if entry else None,
        "eligible_counts": doc["eligible_event_counts"],
        # Filter on STATE, not mere presence. Resolution is recorded by marking
        # a decision resolved and leaving it in the ledger, so listing every
        # entry would keep reporting resolved decisions as pending forever.
        "pending_decisions": [
            d["decision"]
            for d in (entry.get("unresolved_analysis_decisions", []) if entry else [])
            if isinstance(d, dict) and d.get("state") == PENDING_TOKEN
        ],
        "options_status": doc["options_related_classes"]["result_display_status"],
        # v1.3 fields. Read with .get() and rendered only when present, so
        # this page keeps working against v1.2 and earlier rather than
        # crashing on a registry that predates them.
        "linkage_availability": (
            (entry.get("required_external_measurement") or {}).get("availability")
            if entry else None),
        "capture_paths": (entry.get("capture_path_modules") or {}) if entry else {},
        # v1.5 field. Read with .get() and rendered only when present, so this
        # page keeps working against v1.4 and earlier rather than crashing on
        # a registry that predates the declaration.
        "anchor_universe": (entry.get("anchor_universe") or {}) if entry else {},
    }


def run_test_suites(skip_run: bool = False) -> dict[str, Any]:
    """Execute the committed suites and count their own reported results.

    Counts PASS/FAIL/SKIP lines the suites print themselves. This is reading
    test output, not computing a statistic.
    """
    if skip_run:
        return {"available": False, "why": "suite execution skipped (--no-run)"}

    # Discovery finding nothing must not render as success. all([]) is True, so
    # without this an empty TEST_SUITES would report ALL GREEN over zero checks
    # -- the same vacuous pass the CI workflow guards against, and a live risk
    # now that the list is globbed rather than hardcoded.
    if not TEST_SUITES:
        return {"available": False,
                "why": f"no suite matched {HYP04_SUITE_GLOB!r} in {REPO_ROOT} "
                       "-- refusing to report a vacuous pass over zero suites"}

    results = []
    env_root = str(REPO_ROOT)
    for name in TEST_SUITES:
        p = REPO_ROOT / name
        if not p.is_file():
            results.append({"suite": name, "status": "MISSING",
                            "passed": 0, "skipped": 0})
            continue
        proc = subprocess.run([sys.executable, str(p)], capture_output=True,
                              text=True, cwd=env_root,
                              env={**dict(__import__("os").environ),
                                   "PYTHONPATH": env_root},
                              timeout=3600)
        out = proc.stdout or ""
        results.append({
            "suite": name,
            "status": "PASS" if proc.returncode == 0 else "FAIL",
            "passed": out.count("\nPASS:") + (1 if out.startswith("PASS:") else 0),
            "skipped": out.count("\nSKIP:") + (1 if out.startswith("SKIP:") else 0),
        })
    return {
        "available": True,
        "suites": results,
        "total_passed": sum(r["passed"] for r in results),
        "total_skipped": sum(r["skipped"] for r in results),
        "all_green": all(r["status"] == "PASS" for r in results),
    }


# --- instrument calibration: constants already established, not recomputed --
CALIBRATION = {
    "naive_single_test_n": 126,
    "k_effective_tests": "6.05 - 6.34",
    "n_horizons": 20,
    "operative_target_n": 193,
    "provisional_placeholder": "190 - 240",
    "assumed_d": 0.5,
    "alpha": 0.05,
    "power": 0.80,
    "deff_formula": "DEFF = 1 + (m̄ − 1) · ICC",
    "neff_formula": "N_eff = N_pairs / DEFF",
    "icc_floor": 0,
}

PHASES = [
    ("Phase 0", "Feasibility on placeholder linkage", "COMPLETE",
     "Pipeline runs end-to-end; estimator recovers a known injected lag on "
     "synthetic fixtures and correctly finds nothing when nothing is there."),
    ("Phase 1", "Exploratory, non-binding", "BLOCKED",
     "Requires the real supply-chain linkage map, including a "
     "first-known/established-as-of date per pair. Source switched 2026-08-18 "
     "from the deprioritised automated teammate mapping to hand curation, and "
     "curation began 2026-08-22 -- see the live edge count below. The blocker "
     "is unchanged: the gate's threshold counts anchor EVENTS, which curating "
     "edges does not move, and rows on disk never change a registry field."),
    ("Phase 2", "Preregistration lock", "NOT STARTED",
     "Freeze target, features, model spec and validation split in a dated "
     "lock before touching any holdout."),
    ("Phase 3", "Out-of-sample test", "NOT STARTED",
     "Run the locked model against the holdout once; report regardless of outcome."),
    ("Phase 4", "Paper-trading gate", "NOT STARTED",
     "Only if Phase 3 clears its preregistered bar. Also where formal options "
     "eligibility would have to be resolved."),
]


# ==========================================================================
# Rendering
# ==========================================================================
def _e(x: Any) -> str:
    return html.escape(str(x))


def _panel(panel_id: str, title: str, body: str, decision: GateDecision,
           provenance: Optional[MethodProvenance] = None) -> str:
    """Render a panel THROUGH the gate. Findings panels cannot bypass this.

    `provenance` declares what produced the numbers in `body`, and is forwarded
    unchanged to the shared enforcement function. The renderer never inspects
    it and never decides on it -- a declared quantum-derived result without a
    classical-validation attestation is refused there, for every panel,
    whatever the gate says.

    Findings panels below pass nothing, because none of them has a number: the
    gate is closed on five independent grounds. If it ever opens, an
    undeclared provenance raises rather than renders, which is the intended
    behaviour -- an unattributed figure should stop the page, not appear on it.
    """
    try:
        assert_display_allowed(panel_id, decision, provenance)
    except Exception:
        ph = locked_panel_placeholder(panel_id, decision)
        reasons = "".join(f"<li>{_e(r)}</li>" for r in ph["why"])
        conds = "".join(
            f'<span class="cond {"ok" if v else "no"}">{_e(k)}</span>'
            for k, v in ph["conditions_met"].items())
        return f"""
        <section class="panel locked" id="{_e(panel_id)}">
          <h3><span class="lock">&#128274;</span> {_e(title)}
              <span class="badge closed">GATE CLOSED</span></h3>
          <p class="muted">This panel is locked in code, not omitted by convention.
             It shows no value, direction or magnitude.</p>
          <div class="conds">{conds}</div>
          <details><summary>Why it is locked ({len(ph['why'])} independent reasons)</summary>
            <ul>{reasons}</ul>
            <p class="muted"><strong>Unlocks when:</strong> {_e(ph['what_unlocks_it'])}</p>
          </details>
          <p class="muted small">{_e(ph['note'])}</p>
        </section>"""
    return f"""
        <section class="panel" id="{_e(panel_id)}">
          <h3>{_e(title)}</h3>
          {body}
        </section>"""


def render(tests: dict, audit: dict, registry: dict,
           decision: GateDecision, linkage: Optional[dict] = None) -> str:
    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    quantum = quantum_control_status()
    linkage = linkage if linkage is not None else read_curated_linkage()

    # --- build/test ---
    if tests.get("available"):
        rows = "".join(
            f"<tr><td class='mono'>{_e(r['suite'])}</td>"
            f"<td><span class='badge {'pass' if r['status']=='PASS' else 'fail'}'>"
            f"{_e(r['status'])}</span></td>"
            f"<td class='num'>{r['passed']}</td>"
            f"<td class='num'>{r['skipped'] or '&mdash;'}</td></tr>"
            for r in tests["suites"])
        tests_body = f"""
          <div class="kpis">
            <div class="kpi"><div class="v">{tests['total_passed']}</div><div class="l">checks passed</div></div>
            <div class="kpi"><div class="v">{tests['total_skipped']}</div><div class="l">skipped</div></div>
            <div class="kpi"><div class="v">{'ALL GREEN' if tests['all_green'] else 'FAILING'}</div><div class="l">suite status</div></div>
          </div>
          <table><thead><tr><th>Suite</th><th>Status</th><th>Passed</th><th>Skipped</th></tr></thead>
          <tbody>{rows}</tbody></table>
          <p class="muted small">Skips are counted separately and never as passes.
             The counts above are what these {len(TEST_SUITES)} suites reported when this
             page was generated &mdash; read from their own output, not recorded by hand.
             The repository as a whole carries {_n_root_test_files()} test files; this page
             does not run them, so it states no total for them. A hand-maintained
             repo-wide figure previously sat here and had gone stale, which is the
             failure mode this page's own rule exists to prevent: if a number is not
             read from disk, counted from test output, or established calibration, it
             does not appear.</p>"""
    else:
        tests_body = f"<p class='muted'>{_e(tests.get('why','unavailable'))}</p>"

    # --- audit ---
    if audit.get("available"):
        stage_rows = "".join(
            f"<tr><td>{_e(s['stage'])}</td><td class='num'>{s['tickers']}</td>"
            f"<td class='num'>{s['calls']} / {s['cap']}</td>"
            f"<td class='num'>{s['ok']}</td><td class='num'>{s['transport_failures']}</td>"
            f"<td class='num'>{s['pacing_s']}s</td></tr>"
            for s in audit["stages"])
        thin = ", ".join(f"{_e(r['ticker'])} ({(r['n_calls_contracts'] or 0)+(r['n_puts_contracts'] or 0)})"
                         for r in audit["thinnest"])
        deep = ", ".join(f"{_e(r['ticker'])} ({(r['n_calls_contracts'] or 0)+(r['n_puts_contracts'] or 0)})"
                         for r in audit["deepest"])
        audit_body = f"""
          <div class="kpis">
            <div class="kpi"><div class="v">{audit['total_tickers']}</div><div class="l">peers checked</div></div>
            <div class="kpi"><div class="v">{audit['coverage_pct']:.0f}%</div><div class="l">chain coverage</div></div>
            <div class="kpi"><div class="v">{audit['total_calls']}</div><div class="l">provider calls</div></div>
            <div class="kpi"><div class="v">{audit['transport_failures']}</div><div class="l">transport failures</div></div>
          </div>
          <table><thead><tr><th>Stage</th><th>Tickers</th><th>Calls / cap</th><th>OK</th><th>Fails</th><th>Pacing</th></tr></thead>
          <tbody>{stage_rows}</tbody></table>
          <table class="mt"><thead><tr><th>Distribution</th><th>min</th><th>median</th><th>max</th></tr></thead>
          <tbody>
            <tr><td>Expirations per peer</td><td class="num">{audit['expirations']['min']}</td>
                <td class="num">{audit['expirations']['p50']}</td><td class="num">{audit['expirations']['max']}</td></tr>
            <tr><td>Contracts per peer</td><td class="num">{audit['contracts']['min']}</td>
                <td class="num">{audit['contracts']['p50']}</td><td class="num">{audit['contracts']['max']}</td></tr>
          </tbody></table>
          <p class="muted small">Thinnest: {thin}. Deepest: {deep}.
             Calls per ticker constant: {audit['calls_per_ticker_constant']}.
             Provider: {_e(audit['provider'])} &mdash; {_e(audit['credentials'])}.</p>
          <div class="caveat"><strong>This is data availability, not a hypothesis claim.</strong>
             100% coverage means option chains exist for these peers. It says nothing
             about transmission. The provider serves <em>current</em> chains only and has
             no historical endpoint, so this does <em>not</em> establish that implied
             volatility is usable as a Stage&nbsp;1 target &mdash; realized volatility
             remains the default.</div>"""
    else:
        audit_body = f"<p class='muted'>{_e(audit.get('why','unavailable'))}</p>"

    # --- calibration ---
    c = CALIBRATION
    calib_body = f"""
          <p>How the <strong>193</strong> floor was derived. This is
             <em>instrument calibration</em> &mdash; a property of the measuring
             apparatus, fixed before any real data exists. It is not a result.</p>
          <table><thead><tr><th>Step</th><th>Value</th><th>Meaning</th></tr></thead><tbody>
            <tr><td>Naive single-test N</td><td class="num">{c['naive_single_test_n']}</td>
                <td>Labelled baseline only. Never the operative floor.</td></tr>
            <tr><td>Horizons tested</td><td class="num">{c['n_horizons']}</td>
                <td>h = 1&hellip;20, one grid for target and lag detection.</td></tr>
            <tr><td>Effective independent tests</td><td class="num">{c['k_effective_tests']}</td>
                <td>Measured by max-T permutation on synthetic fixtures &mdash; not assumed.
                    Far below 20 because an expanding-window target makes adjacent
                    horizons correlated by construction.</td></tr>
            <tr><td><strong>Operative floor</strong></td><td class="num"><strong>{c['operative_target_n']}</strong></td>
                <td>Šidák-corrected at the measured k. Stated in <strong>anchor events</strong>,
                    the same unit as HYP-01/02/03's 60/60/40.</td></tr>
            <tr><td>Provisional placeholder</td><td class="num">{c['provisional_placeholder']}</td>
                <td>Superseded by the measured figure above.</td></tr>
          </tbody></table>
          <p class="mono small">{_e(c['deff_formula'])} &nbsp;&nbsp; {_e(c['neff_formula'])}
             &nbsp;&nbsp; ICC floored at {c['icc_floor']} for DEFF only; the raw value is still reported.</p>
          <div class="caveat"><strong>A governance floor, not a power guarantee.</strong>
             Inputs were a hypothetical d&nbsp;=&nbsp;{c['assumed_d']} chosen before any data,
             &alpha;&nbsp;=&nbsp;{c['alpha']}, power&nbsp;=&nbsp;{c['power']}, on synthetic
             fixtures with known injected ground truth. No observed project result entered it.
             Reaching a threshold licenses <em>looking</em>, not <em>concluding</em>.</div>"""

    # --- capture paths (registry v1.3 and later) -------------------------
    # Built in Python rather than inside the f-string, and omitted entirely
    # when the registry predates these fields -- an empty section reads as
    # "nothing here", which is a different claim from "not recorded".
    avail = registry.get("linkage_availability")
    paths = registry.get("capture_paths") or {}
    if not avail and not paths:
        capture_block = ""
    else:
        rows = []
        for key, val in sorted(paths.items()):
            if not isinstance(val, dict):
                continue
            captured = val.get("data_captured")
            rows.append(
                "<tr><td><span class='mono'>%s</span></td>"
                "<td class='small'>%s</td>"
                "<td><span class='badge %s'>%s</span></td></tr>"
                % (_e(str(val.get("module", key))),
                   _e(str(val.get("note", ""))),
                   "fail" if captured is False else "idle",
                   "no data captured" if captured is False else _e(str(captured))))
        table = ("<table><thead><tr><th>Capture path</th><th>Note</th>"
                 "<th>Data</th></tr></thead><tbody>%s</tbody></table>"
                 % "".join(rows)) if rows else ""
        capture_block = f"""
          <p class="mt"><strong>Required external measurement</strong> &mdash;
             linkage availability
             <span class="mono">{_e(str(avail or 'not recorded'))}</span>.</p>
          {table}
          <div class="caveat"><strong>A module that can ingest is not ingested
             data.</strong> The rows above report that a capture path EXISTS.
             Every one reports no data captured, which is why HYP-04's status
             does not move. Availability is read from the registry, which is the
             authority &mdash; this page does not restate it from memory.</div>"""

    # --- candidate anchor events -----------------------------------------
    # Every number here is COUNTED FROM THE FILE at render time. If the file
    # is absent the block is omitted entirely rather than rendered as zero:
    # "no file" and "a file saying zero" are different claims.
    cand = read_anchor_event_candidates()
    if not cand.get("present"):
        candidates_block = ""
    else:
        anchors = " &middot; ".join(
            f"{_e(k)} {v}" for k, v in sorted(cand["by_anchor"].items()))
        sess = " &middot; ".join(
            f"{_e(k)} {v}" for k, v in sorted(cand["by_session"].items()))
        prov = " &middot; ".join(
            f"{_e(k)} {v}" for k, v in sorted(cand["by_provenance"].items()))
        floor = registry.get("hyp04_threshold")
        shortfall = ("" if not isinstance(floor, int) else
                     f" That is {cand['total']} against a floor of {floor}.")
        candidates_block = f"""
          <div class="kpis">
            <div class="kpi"><div class="v">{cand['total']}</div><div class="l">candidate anchor events</div></div>
            <div class="kpi"><div class="v">0</div><div class="l">ELIGIBLE anchor events</div></div>
          </div>
          <p class="small">{anchors} &mdash; {_e(str(cand['earliest']))} to
             {_e(str(cand['latest']))}. Release session: {sess}.
             Provenance: {prov}. Source
             <span class="mono">{_e(cand['source'])}</span>.</p>
          <div class="caveat blocker"><strong>Candidates are NOT eligible
             events, and this number does not move C2.</strong> Nothing here
             has been screened against HYP-01's eligibility rules; the eligible
             count remains zero.{shortfall} C2 counts ELIGIBLE anchor events,
             so deriving release dates does not advance it. Since registry
             v1.9 the anchor-side requirement is HYP-04's own
             <span class="mono">HYP04-ANCHOR-SHOCK-RULE-v1</span>, not HYP-01's
             attention screen; it needs the anchor's and the benchmark's closes
             for the attributed session, no price source is decided, and no
             shock has been computed from production data.
             These counts are read from the file at render time; this page does
             not carry a copy of them.</div>"""

    # --- anchor-event calendar -------------------------------------------
    # The candidate walk above counts a ticker's releases. This counts the
    # releases that fall INSIDE a membership span, which is the number the
    # feasibility question actually asks about. Every figure is counted from
    # the shipped CSV rows at render time; none may be written as a literal
    # here, in code OR in a comment.
    cal = read_anchor_event_calendar()
    if not cal.get("present"):
        calendar_block = ""
    else:
        cfloor = registry.get("hyp04_threshold")
        vs = ("" if not isinstance(cfloor, int) else
              f" The registered floor is {cfloor}.")
        alt = ("" if not cal.get("alternative_total") else
               f" A measured alternative that recovers the pre-2004 SEC item "
               f"numbering reaches {cal['alternative_total']}; it is "
               f"<strong>not adopted</strong> and is published beside the "
               f"primary specification, not in place of it.")
        blind = ("" if cal.get("blind_member_years") in (None, 0) else
                 f" {cal['blind_member_years']} member-years fall before any "
                 f"earnings-specific 8-K item code existed and are invisible "
                 f"to an index-level rule entirely.")
        dropped = ("" if not cal.get("superseded") else
                   f" {cal['superseded']} same-release re-filings were "
                   f"superseded by the earliest acceptance rather than counted "
                   f"twice.")
        warn = ("" if not cal.get("summary_disagrees") else
                "<div class=\"caveat blocker\"><strong>The artifact's own "
                "summary disagrees with the rows it shipped with.</strong> The "
                "figures above are the rows.</div>")
        csess = " &middot; ".join(
            f"{_e(k)} {v}" for k, v in sorted(cal["by_session"].items()))
        calendar_block = f"""
          <div class="kpis">
            <div class="kpi"><div class="v">{cal['total']}</div><div class="l">candidate events INSIDE a membership span</div></div>
            <div class="kpi"><div class="v">{cal['resolved_session']}</div><div class="l">of those with a resolved session</div></div>
            <div class="kpi"><div class="v">0</div><div class="l">ELIGIBLE anchor events</div></div>
          </div>
          <p class="small">Release session: {csess}. Source
             <span class="mono">{_e(cal['source'])}</span>.{dropped}{alt}{blind}</p>
          {warn}
          <div class="caveat blocker"><strong>A ceiling above the floor is not
             a met threshold, and this moves no gate.</strong>{vs} Each of these
             still has to survive
             <span class="mono">HYP04-ANCHOR-SHOCK-RULE-v1</span>, which needs
             the anchor's and the benchmark's closes for the attributed
             session. No price source is decided, none has been put through it,
             and the eligible count is zero.</div>"""

    # --- anchor universe (registry v1.5 and later) -----------------------
    # The candidate counts above are a floor on RELEASES, not on usable
    # anchors. Showing a candidate total without showing how much of it belongs
    # to a ticker outside the registered universe would let this page imply the
    # whole total is available -- the same defect as a hardcoded count.
    #
    # Every number below is computed from the registry and the candidates file
    # at render time. None may be written here as a literal, in code OR in a
    # comment: test_13d greps this source for the live total near the word
    # "candidate", and an out-of-date comment is exactly what it is guarding.
    au = registry.get("anchor_universe") or {}
    universe_block = ""
    if au:
        # v1.6 declares membership as INTERVALS and removes v1.5's snapshot
        # fields. Read both shapes: this page must keep working against an
        # older registry rather than silently rendering an empty universe,
        # which would read as "nobody qualifies" instead of "wrong shape".
        intervals = au.get("membership_intervals") or []
        members = list(au.get("members_ever") or au.get("derived_members") or [])

        if intervals:
            rows = "".join(
                f"<tr><td class='mono'>{_e(str(i.get('ticker')))}</td>"
                f"<td class='mono'>{_e(str(i.get('start_date')))}</td>"
                f"<td class='mono'>{_e(str(i.get('end_date') or 'current'))}</td>"
                f"<td>{_e(str((i.get('evidence', {}).get('qualifying_disclosures') or [{}])[0].get('counterparty')))}</td>"
                f"<td class='num'>{_e(str((i.get('evidence', {}).get('qualifying_disclosures') or [{}])[0].get('concentration_pct')))}%</td>"
                f"<td class='num'>{_e(str(i.get('filings_qualifying')))}</td></tr>"
                for i in intervals)
            head = ("<tr><th>Anchor</th><th>From</th><th>To</th>"
                    "<th>Counterparty</th><th>Concentration</th>"
                    "<th>Filings</th></tr>")
        else:
            prov = au.get("derived_members_provenance", {}) or {}
            rows = "".join(
                f"<tr><td class='mono'>{_e(str(t))}</td>"
                f"<td class='mono'>{_e(str(e.get('as_of_date')))}</td>"
                f"<td class='mono'>&mdash;</td>"
                f"<td>{_e(str(e.get('counterparty')))}</td>"
                f"<td class='num'>{_e(str(e.get('concentration_pct')))}%</td>"
                f"<td class='num'>1</td></tr>"
                for t in members for e in (prov.get(t) or []))
            head = ("<tr><th>Anchor</th><th>As of</th><th>To</th>"
                    "<th>Counterparty</th><th>Concentration</th>"
                    "<th>Filings</th></tr>")

        # Candidate events split by whether the anchor was a member ON the
        # release date. Computed here from the registry and the candidates
        # file; no count is written into this source.
        split = ""
        dba = cand.get("dates_by_anchor", {}) if cand.get("present") else {}
        if dba and intervals:
            spans: dict[str, list[tuple[str, str]]] = {}
            for i in intervals:
                spans.setdefault(str(i.get("ticker")), []).append(
                    (str(i.get("start_date") or ""), str(i.get("end_date") or "")))
            inside = outside = 0
            outside_tickers: set[str] = set()
            for t, ds in dba.items():
                for d in ds:
                    ok = any(st and d >= st and (not en or d < en)
                             for st, en in spans.get(t, []))
                    if ok:
                        inside += 1
                    else:
                        outside += 1
                        outside_tickers.add(t)
            if outside:
                split = (
                    "<div class='caveat blocker'><strong>"
                    f"{outside} of the {inside + outside} candidate anchor "
                    "events fall OUTSIDE every membership interval</strong> "
                    f"({_e(', '.join(sorted(outside_tickers)))}). Membership is "
                    "a span, not a flag: an event counts only if its anchor was "
                    "a registered member on the release date. These are "
                    "correctly dated releases and are not deleted.</div>")

        universe_block = f"""
          <p class="mt"><strong>Anchor universe</strong> &mdash; a RULE
             (<span class="mono">{_e(str(au.get('rule_id')))}</span>), evaluated
             over {_e(str((au.get('screening_frame') or {}).get('size')))} tickers
             {_e('at each filing in force' if intervals else 'at one cutoff')}.
             Members qualify by meeting a criterion fixed in advance; none is
             named in. Threshold {_e(str(au.get('threshold_pct')))}% of
             <span class="mono">{_e(str(au.get('required_denominator')))}</span>,
             both taken from ASC 280-10-50-42.</p>
          <table><thead>{head}</thead><tbody>{rows}</tbody></table>
          {split}
          <div class="caveat"><strong>Membership is not eligibility.</strong>
             Declaring who may be an anchor creates no eligible anchor event.
             C2 counts eligible anchor events and still reads zero.</div>"""

    # --- registry ---
    if registry.get("available"):
        pend = "".join(f"<li>{_e(d)}</li>" for d in registry["pending_decisions"])
        counts = "".join(f"<tr><td class='mono'>{_e(k)}</td><td class='num'>{v}</td></tr>"
                         for k, v in registry["eligible_counts"].items() if k != "note")
        reg_body = f"""
          <div class="kpis">
            <div class="kpi"><div class="v">v{_e(registry['registry_version'])}</div><div class="l">registry version</div></div>
            <div class="kpi"><div class="v">{len(registry['named_hypotheses'])}</div><div class="l">registered hypotheses</div></div>
            <div class="kpi"><div class="v">{registry['hyp04_threshold']}</div><div class="l">HYP-04 floor ({_e(registry['hyp04_unit'])})</div></div>
          </div>
          <p><strong>HYP-04</strong> &mdash; {_e(registry['hyp04_class'])},
             status <span class="mono">{_e(registry['hyp04_status'])}</span>.
             Registered {_e(registry['authored'])} in a new dated version;
             {_e(registry['supersedes'])} is unedited.</p>
          <table><thead><tr><th>Hypothesis</th><th>Eligible events</th></tr></thead>
          <tbody>{counts}</tbody></table>
          {candidates_block}
          {calendar_block}
          {universe_block}
          <p class="mt"><strong>Unresolved analysis decisions</strong> (each blocks the
             display gate independently):</p>
          <ul>{pend}</ul>
          {capture_block}
          <p class="muted small">Options classes: <span class="mono">{_e(registry['options_status'])}</span>
             &mdash; unchanged; HYP-04 is not registered against an options class.</p>"""
    else:
        reg_body = "<p class='muted'>registry unavailable</p>"

    # --- roadmap ---
    # Describe the curated map in Python, not inside the f-string. Only the
    # filename is untrusted and gets escaped; the em-dash entity must NOT go
    # through _e() or it renders as the literal text "&mdash;".
    if not linkage.get("map_present"):
        linkage_where = "&mdash; no curated map on disk"
    else:
        linkage_where = "from <span class='mono'>%s</span>" % _e(str(linkage.get("source")))
    # A map that exists but fails validation must never read the same as an
    # absent one. Both yield 0 usable edges; only one of them is a defect.
    rejected = int(linkage.get("rows_rejected", 0) or 0)
    if linkage.get("map_present") and (rejected or not linkage.get("loads_clean", True)):
        linkage_health = (
            " <strong>That map does not load clean: %d of %d row(s) "
            "rejected.</strong> Rejected rows are not curated linkage; the usable "
            "count above already excludes them."
            % (rejected, int(linkage.get("rows_seen", 0) or 0)))
    else:
        linkage_health = ""

    phase_rows = "".join(
        f"<tr><td><strong>{_e(n)}</strong></td><td>{_e(t)}</td>"
        f"<td><span class='badge {'pass' if s=='COMPLETE' else ('fail' if s=='BLOCKED' else 'idle')}'>{_e(s)}</span></td>"
        f"<td class='small'>{_e(d)}</td></tr>"
        for n, t, s, d in PHASES)
    roadmap_body = f"""
          <table><thead><tr><th>Phase</th><th>What</th><th>Status</th><th>Notes</th></tr></thead>
          <tbody>{phase_rows}</tbody></table>
          <div class="caveat blocker"><strong>Phase 1 is blocked on one thing:</strong>
             the real supply-chain / competitor linkage map &mdash; ticker pairs,
             relationship type, confidence, <strong>and a first-known /
             established-as-of date per pair</strong>. The date column is required,
             not optional: a map built today encodes relationships known today, and
             applying it to historical anchor events without it is look-ahead bias.
             A map delivered without that column is a blocking data-quality failure,
             not a partial delivery.
             <br><br>
             <strong>Source changed 2026-08-18.</strong> The automated teammate
             mapping is deprioritised; the project switched to hand curation
             against a 15-column template, validated by
             <span class="mono">curated_linkage.py</span>.
             <br><br>
             <strong>Curated to date: {_e(str(linkage.get('edges', 0)))} usable edge(s)</strong>
             {linkage_where}.{linkage_health}
             Read from disk at render time, not asserted: this sentence previously
             hardcoded &ldquo;zero rows are curated&rdquo;, which was true when written
             and later was not.
             <br><br>
             The count is <em>not</em> the blocker it once was, but the threshold
             is: condition C2 requires <strong>193 eligible anchor events</strong>,
             a unit the registry fixes deliberately. Curating more edges does not
             move it &mdash; only observed anchor events do.</div>"""

    findings = "".join(
        _panel(p, p.replace("_", " ").title(), "", decision) for p in FINDINGS_PANELS)

    conds = "".join(
        f"<tr><td class='mono'>{_e(k)}</td>"
        f"<td><span class='badge {'pass' if v else 'fail'}'>{'MET' if v else 'NOT MET'}</span></td></tr>"
        for k, v in decision.conditions.items())

    return f"""<!-- generated {gen} -->
<style>
  :root {{
    --bg:#f6f7f9; --card:#fff; --ink:#16181d; --muted:#6b7280; --line:#e5e7eb;
    --pass:#0f7b3f; --pass-bg:#e7f5ec; --fail:#a3341f; --fail-bg:#fdecea;
    --idle:#5b6270; --idle-bg:#eef0f3; --accent:#1f4e79; --warn-bg:#fff8e6; --warn-line:#e0b34d;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:24px; background:var(--bg); color:var(--ink);
         font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:1080px; margin:0 auto; }}
  header {{ margin-bottom:20px; }}
  h1 {{ font-size:24px; margin:0 0 4px; }}
  h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.08em;
        color:var(--muted); margin:28px 0 10px; }}
  h3 {{ font-size:16px; margin:0 0 10px; display:flex; align-items:center; gap:8px; }}
  .panel {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
            padding:18px 20px; margin-bottom:14px; }}
  .panel.locked {{ background:#fbfbfc; border-style:dashed; }}
  .lock {{ font-size:15px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  table.mt {{ margin-top:14px; }}
  th {{ text-align:left; font-size:12px; text-transform:uppercase; letter-spacing:.04em;
        color:var(--muted); border-bottom:1px solid var(--line); padding:6px 8px; }}
  td {{ padding:7px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; }}
  .small {{ font-size:13px; }}
  .muted {{ color:var(--muted); }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:20px; font-size:11px;
            font-weight:600; letter-spacing:.03em; }}
  .badge.pass {{ background:var(--pass-bg); color:var(--pass); }}
  .badge.fail, .badge.closed {{ background:var(--fail-bg); color:var(--fail); }}
  .badge.idle {{ background:var(--idle-bg); color:var(--idle); }}
  .kpis {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:14px; }}
  .kpi {{ flex:1 1 130px; background:var(--bg); border:1px solid var(--line);
          border-radius:8px; padding:12px; }}
  .kpi .v {{ font-size:22px; font-weight:600; font-variant-numeric:tabular-nums; }}
  .kpi .l {{ font-size:12px; color:var(--muted); margin-top:2px; }}
  .caveat {{ margin-top:14px; padding:11px 13px; background:var(--warn-bg);
             border-left:3px solid var(--warn-line); border-radius:0 6px 6px 0; font-size:13.5px; }}
  .caveat.blocker {{ background:var(--fail-bg); border-left-color:var(--fail); }}
  .cond {{ display:inline-block; padding:2px 8px; margin:0 5px 5px 0; border-radius:5px;
           font-size:11.5px; font-family:ui-monospace,monospace; }}
  .cond.ok {{ background:var(--pass-bg); color:var(--pass); }}
  .cond.no {{ background:var(--fail-bg); color:var(--fail); }}
  .conds {{ margin:8px 0; }}
  details {{ margin-top:8px; font-size:13.5px; }}
  summary {{ cursor:pointer; color:var(--accent); }}
  ul {{ margin:8px 0; padding-left:20px; }}
  li {{ margin-bottom:4px; font-size:13.5px; }}
  .banner {{ background:#eef3f8; border:1px solid #c9dcef; border-left:3px solid var(--accent);
             border-radius:0 8px 8px 0; padding:13px 16px; margin-bottom:18px; font-size:14px; }}
</style>

<div class="wrap">
<header>
  <h1>HYP-04 Phase 0 &mdash; Build &amp; Process Status</h1>
  <p class="muted small">Infrastructure and process metrics. Generated {gen}.
     Reads committed artifacts; computes no new statistics.</p>
</header>

<div class="banner">
  <strong>Placeholder linkage. No findings shown.</strong>
  Peers are the non-anchor tickers from the sector file, assigned to anchors by
  <em>list position</em> &mdash; the sector column is not used for pairing, so this
  is positional-synthetic, not same-sector. Hand curation of a real map began
  2026-08-22 (count below), but <em>every analysis path on this page still runs
  on the placeholder</em>, and the gate treats it accordingly. Nothing on this
  page is a finding about supply-chain transmission, and no hedging edge is
  claimed. Progress is public; findings are gated.
</div>

<h2>Build &amp; test status</h2>
{_panel("build_test_status", "Governance and package suites", tests_body, decision)}

<h2>Data availability</h2>
{_panel("audit_coverage", "Options-coverage audit (27 placeholder peers)", audit_body, decision)}

<h2>Instrument calibration</h2>
{_panel("instrument_calibration", "How the 193-event floor was derived", calib_body, decision)}

<h2>Registry</h2>
{_panel("registry_status", _registry_title(registry), reg_body, decision)}

<h2>Roadmap</h2>
{_panel("phase_roadmap", "Phase 0 &rarr; 4", roadmap_body, decision)}

<h2>Findings &mdash; gate {decision.status}</h2>
<div class="panel">
  <h3>Result-display gate <span class="badge {'pass' if decision.open else 'closed'}">{decision.status}</span></h3>
  <p class="small">Mirrors <span class="mono">GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md</span>,
     the same document governing HYP-01. Every condition must hold simultaneously;
     absence of a rule is never read as permission.</p>
  <table><thead><tr><th>Condition</th><th>State</th></tr></thead><tbody>{conds}</tbody></table>
  <p class="muted small" style="margin-top:10px">The panels below are locked
     <strong>in code</strong>. Rendering routes through
     <span class="mono">display_gate.assert_display_allowed</span>, which raises rather
     than returning a value &mdash; and an unclassified panel is treated as a finding
     and denied, so forgetting to classify one fails closed.</p>
  <div class="caveat"><strong>Second, independent control: quantum-derived results.</strong>
     The five conditions above describe the state of the <em>hypothesis</em>. They say
     nothing about <em>how</em> a number was computed, so on their own they would let a
     result from an unvalidated method through an open gate.
     <span class="mono">quantum_provenance.py</span> blocks that separately: any
     quantum-derived model output is refused from every panel and from the Stage&nbsp;1
     Link-Strength score unless it carries a complete attestation that it was validated
     against the classical reference on known cases &mdash; and
     <strong>{_e(quantum['validated_results_on_file'])} such validations and
     {_e(quantum['agreement_logs_on_file'])} agreement logs are on file</strong>.
     The block applies <strong>regardless of source</strong>: a result from this
     project's own tertiary cross-check module and one supplied from outside the
     repository are treated identically. Opening the gate does not lift it, and clearing
     it does not open the gate. Per the model plan, the quantum autocorrelation function
     is tertiary, non-load-bearing, and feeds no decision; it was skipped because no
     citable construction exists for applying it to classical return series.</div>
</div>
{findings}

<p class="muted small" style="margin-top:24px">
  Nothing in this dashboard constitutes investment advice, a solicitation, or a
  representation that any approach is profitable.
</p>
</div>"""


def build(out_path: Path, skip_run: bool = False) -> dict[str, Any]:
    decision = current_decision()
    tests = run_test_suites(skip_run=skip_run)
    audit = read_audit()
    registry = read_registry()
    linkage = read_curated_linkage()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(tests, audit, registry, decision, linkage),
                        encoding="utf-8")
    return {"gate": decision.status, "tests": tests, "audit_available": audit.get("available"),
            "curated_edges": linkage.get("edges", 0), "out": str(out_path)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="HYP-04 Phase 0 status dashboard.")
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "Live Signal Engine" / "HYP04_PHASE0_DASHBOARD.html")
    ap.add_argument("--no-run", action="store_true",
                    help="skip executing the test suites (renders build status as unavailable)")
    a = ap.parse_args(argv)

    info = build(a.out, skip_run=a.no_run)
    d = current_decision()
    print(f"gate: {d.status}  ({len(d.denials)} denial(s))")
    for k, v in d.conditions.items():
        print(f"   {'MET    ' if v else 'NOT MET'}  {k}")
    if info["tests"].get("available"):
        print(f"tests: {info['tests']['total_passed']} passed, "
              f"{info['tests']['total_skipped']} skipped, "
              f"all_green={info['tests']['all_green']}")
    print(f"wrote: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
