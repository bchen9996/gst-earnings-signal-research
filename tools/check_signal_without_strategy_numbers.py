#!/usr/bin/env python3
"""Executable numerical audit for the Signal Without Strategy synthesis.

This does not inspect declarations. It loads the committed source artifacts, recomputes
or reads the referenced field, and compares it against every numeric token that appears
in the manuscript, the executive summary, and the visible text of the three figures.

It fails on:
  * any numeric token that is neither allowlisted nor tied to a committed artifact field;
  * any displayed value inconsistent with its source at the precision shown;
  * overstating a null, promoting a secondary metric, calling vendor EPS GAAP, claiming a
    guaranteed point-in-time estimate vintage, claiming an investable strategy, calling
    the temporal replication successful, or denying the significant Spearman association.

SCOPE NOTE. Numeric scanning covers the manuscript body up to the References heading,
the whole executive summary, and SVG <text> content only. Bibliographic identifiers
(DOIs, volumes, page ranges) and SVG layout coordinates are not research claims and are
out of scope by construction, not by exception.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT = ROOT / "SIGNAL_WITHOUT_STRATEGY_MANUSCRIPT_v1.0.md"
SUMMARY = ROOT / "SIGNAL_WITHOUT_STRATEGY_EXECUTIVE_SUMMARY_v1.0.md"
FIGURES = sorted(ROOT.glob("SIGNAL_WITHOUT_STRATEGY_FIGURE_*.svg"))
MISMATCH_REV = "ddc848865bd79a8aecb782dacbb11082b83a25b9"
MISMATCH_PATH = "ATTENTION_ACTIVITY_MISMATCH_RESULTS_v1.0.json"
DIR_REPORT = "RETROSPECTIVE_DIRECTION_SIGNAL_REPORT_v1.0.md"

FAIL: list[str] = []
NUM = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def bad(msg):
    FAIL.append(msg)
    print("FAIL: " + msg)


def ok(msg):
    print("PASS: " + msg)


# ------------------------------------------------------------------ artifacts

def jload(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _show_bytes(rev, path):
    r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    return r.stdout if r.returncode == 0 else None


def sha256(b):
    import hashlib
    return hashlib.sha256(b).hexdigest()


# The weekly-volatility artifact is committed on `phase2-attention-activity-mismatch`
# (PR #30), which is NOT in this stacked branch's ancestry. During stacked review it is
# resolved from that pinned commit; once PR #30 is merged the in-tree copy is used
# instead. Whichever source is used must hash to exactly this content.
MISMATCH_CONTENT_SHA256 = \
    "8cd711cf2297480a838e5c69a499b6e41652283b45857a8b31649c4be7f9e79b"
MISMATCH_BLOB_SHA1 = "4802021306239ac5834b77fa0831d845fe1f185d"


def load_mismatch_artifact():
    """Prefer the in-tree artifact; fall back to the pinned commit during review.

    Fails if the resolved source does not match the expected content hash, and fails if
    an in-tree copy exists but disagrees with the pinned one.
    """
    in_tree = ROOT / MISMATCH_PATH
    pinned = _show_bytes(MISMATCH_REV, MISMATCH_PATH)
    tree_bytes = in_tree.read_bytes() if in_tree.exists() else None

    def norm(b):
        return None if b is None else b.replace(b"\r\n", b"\n")

    t, p = norm(tree_bytes), norm(pinned)
    if t is not None and p is not None and t != p:
        raise SystemExit(
            "volatility artifact disagreement: the in-tree copy of "
            f"{MISMATCH_PATH} differs from the pinned {MISMATCH_REV[:7]} version. "
            "Refusing to choose between two versions of a research result.")
    chosen, origin = (t, "in-tree") if t is not None else (p, f"pinned {MISMATCH_REV[:7]}")
    if chosen is None:
        raise SystemExit(
            f"{MISMATCH_PATH} is unavailable both in-tree and at {MISMATCH_REV[:7]}")
    got = sha256(chosen)
    if got != MISMATCH_CONTENT_SHA256:
        raise SystemExit(f"volatility artifact hash mismatch from {origin}: "
                         f"expected {MISMATCH_CONTENT_SHA256}, got {got}")
    print(f"PASS: volatility artifact resolved {origin}, content hash verified")
    if t is None:
        print("      NOTE: PR #30 (phase2-attention-activity-mismatch) must merge "
              "before PR #36 for main to be self-contained. PR #36 alone does not "
              "contain this source artifact.")
    return json.loads(chosen.decode("utf-8"))


def dig(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur


A = {
    "market": jload("RETROSPECTIVE_MARKET_RESPONSE_RESULTS_v1.0.json"),
    "direction": jload("RETROSPECTIVE_DIRECTION_SIGNAL_RESULTS_v1.0.json"),
    "magnitude": jload("RETROSPECTIVE_MAGNITUDE_FORECAST_RESULTS_v1.0.json"),
    "restaurant": jload("RESTAURANT_SEARCH_PILOT_RESULTS_v1.0.json"),
    "nowcast": jload("SEARCH_DEMAND_NOWCAST_RESULTS_v1.0.json"),
    "extraction": jload("SEMICONDUCTOR_EPS_ABSORPTION_RESULTS_v1.0.json"),
    "feasibility": jload("Live Signal Engine/Semiconductor_EPS_Absorption/"
                         "structured_earnings_feasibility_v1.0.json"),
    "pr34": jload("SEMICONDUCTOR_SURPRISE_ABSORPTION_V3_RESULTS_v1.0.json"),
    "pr35": jload("SEMICONDUCTOR_SURPRISE_TEMPORAL_REPLICATION_RESULTS_v1.0.json"),
    "mismatch": load_mismatch_artifact(),
}
DIRTXT = (ROOT / DIR_REPORT).read_text(encoding="utf-8")


def from_narrative(pattern, label):
    """Pull a value out of a committed report narrative (still a committed artifact)."""
    m = re.search(pattern, DIRTXT)
    if not m:
        raise SystemExit(f"narrative source missing for {label}: {pattern}")
    return float(m.group(1))


# CLAIMS: displayed token -> (source description, source value, scale)
# scale converts the artifact's units into the units displayed (e.g. 100 for percent).
def C(desc, value, scale=1.0):
    return (desc, float(value) * scale)


CLAIMS = {
    # ---- search attention: standalone vs incremental -------------------------
    "0.8543": C("market: scorecard[3] (Strategy E) mean_net_pct",
                dig(A["market"], "scorecard.3.mean_net_pct")),
    "+0.0131": C("market: clustered_inference.strategy_E_incremental_high_gst.coef_pp",
                 dig(A["market"], "clustered_inference.strategy_E_incremental_high_gst.coef_pp")),
    "0.0131": C("market: clustered_inference.strategy_E_incremental_high_gst.coef_pp",
                dig(A["market"], "clustered_inference.strategy_E_incremental_high_gst.coef_pp")),
    "0.98332": C("market: clustered_inference.strategy_E_incremental_high_gst.p_value",
                 dig(A["market"], "clustered_inference.strategy_E_incremental_high_gst.p_value")),
    # ---- direction model ------------------------------------------------------
    "0.2560": C("direction: pooled intercept_only_prevalence.brier",
                dig(A["direction"], "pooled_out_of_sample.intercept_only_prevalence.brier")),
    "0.2711": C("direction: pooled logistic_l2.brier",
                dig(A["direction"], "pooled_out_of_sample.logistic_l2.brier")),
    "0.4654": C("direction: pooled logistic_l2.auc",
                dig(A["direction"], "pooled_out_of_sample.logistic_l2.auc")),
    "0.479": C("direction: pooled logistic_l2.accuracy",
               dig(A["direction"], "pooled_out_of_sample.logistic_l2.accuracy")),
    "47.9": C("direction: pooled logistic_l2.accuracy (percent)",
              dig(A["direction"], "pooled_out_of_sample.logistic_l2.accuracy"), 100),
    "0.5347": C("direction: pooled always_positive.accuracy",
                dig(A["direction"], "pooled_out_of_sample.always_positive.accuracy")),
    "53.5": C("direction: pooled always_positive.accuracy (percent)",
              dig(A["direction"], "pooled_out_of_sample.always_positive.accuracy"), 100),
    "285": C("direction: sample.rows_in_source",
             dig(A["direction"], "sample.rows_in_source")),
    "217": C("direction: sample.unique_event_identities",
             dig(A["direction"], "sample.unique_event_identities")),
    "68": C("direction: sample.duplicate_rows_removed",
            dig(A["direction"], "sample.duplicate_rows_removed")),
    "-0.7027": C("direction: combined_strategy.direction_only.mean_net_pct",
                 dig(A["direction"], "combined_strategy.direction_only.mean_net_pct")),
    "0.7027": C("direction: |combined_strategy.direction_only.mean_net_pct|",
                abs(dig(A["direction"],
                        "combined_strategy.direction_only.mean_net_pct"))),
    # pre-correction values, quoted from the committed report narrative, INVALIDATED
    "63.6": C(f"{DIR_REPORT}: pre-correction accuracy (invalidated)",
              from_narrative(r"scored \*\*([\d.]+)% accuracy", "pre-accuracy")),
    "0.636": C(f"{DIR_REPORT}: pre-correction accuracy (invalidated)",
               from_narrative(r"scored \*\*([\d.]+)% accuracy", "pre-accuracy"), 0.01),
    "0.6395": C(f"{DIR_REPORT}: pre-correction AUC (invalidated)",
                from_narrative(r"AUC ([\d.]+), Brier", "pre-auc")),
    "0.23824": C(f"{DIR_REPORT}: pre-correction Brier (invalidated)",
                 from_narrative(r"Brier ([\d.]+)\*\*", "pre-brier")),
    "0.60": C(f"{DIR_REPORT}: pre-correction direction-only net (invalidated)",
              from_narrative(r"returned \*\*\+([\d.]+)% net", "pre-net")),
    "0.6000": C(f"{DIR_REPORT}: pre-correction direction-only net (invalidated)",
                from_narrative(r"returned \*\*\+([\d.]+)% net", "pre-net")),
    # ---- magnitude ------------------------------------------------------------
    "3.6284": C("magnitude: pooled B_baseline_no_gst.mae_pp",
                dig(A["magnitude"], "pooled_out_of_sample.B_baseline_no_gst.mae_pp")),
    "3.6299": C("magnitude: pooled C_baseline_plus_gst.mae_pp",
                dig(A["magnitude"], "pooled_out_of_sample.C_baseline_plus_gst.mae_pp")),
    "0.9827": C("magnitude: decisive_paired_loss_difference.clustered.p_value",
                dig(A["magnitude"],
                    "decisive_paired_loss_difference.clustered.p_value")),
    # ---- weekly volatility (cross-branch committed artifact) ------------------
    "0.0309": C(f"{MISMATCH_PATH}@{MISMATCH_REV[:7]}: volatility.mae_improvement_pct",
                abs(dig(A["mismatch"], "volatility.mae_improvement_pct"))),
    "0.420367": C(f"{MISMATCH_PATH}: volatility.metrics.B.mae",
                  dig(A["mismatch"], "volatility.metrics.B.mae")),
    "0.420497": C(f"{MISMATCH_PATH}: volatility.metrics.C.mae",
                  dig(A["mismatch"], "volatility.metrics.C.mae")),
    "0.0011023": C(f"{MISMATCH_PATH}: volatility bootstrap ci95[0]",
                   abs(dig(A["mismatch"],
                           "volatility.paired_bootstrap_B_minus_C.ci95.0"))),
    "+0.0010839": C(f"{MISMATCH_PATH}: volatility bootstrap ci95[1]",
                    dig(A["mismatch"],
                        "volatility.paired_bootstrap_B_minus_C.ci95.1")),
    "0.0010839": C(f"{MISMATCH_PATH}: volatility bootstrap ci95[1]",
                   dig(A["mismatch"],
                       "volatility.paired_bootstrap_B_minus_C.ci95.1")),
    # ---- restaurant pilot -----------------------------------------------------
    "0.20211": C("restaurant: models.B.brier", dig(A["restaurant"], "models.B.brier")),
    "0.23665": C("restaurant: models.C.brier", dig(A["restaurant"], "models.C.brier")),
    "0.24739": C("restaurant: models.D.brier", dig(A["restaurant"], "models.D.brier")),
    "5.4534": C("restaurant: continuous_mae_abs_move_pp.B",
                dig(A["restaurant"], "continuous_mae_abs_move_pp.B")),
    "5.6790": C("restaurant: continuous_mae_abs_move_pp.C",
                dig(A["restaurant"], "continuous_mae_abs_move_pp.C")),
    "5.8543": C("restaurant: continuous_mae_abs_move_pp.D",
                dig(A["restaurant"], "continuous_mae_abs_move_pp.D")),
    # ---- semiconductor extraction --------------------------------------------
    "0.9860": C("extraction: gates.heldout_conditional_precision.value",
                dig(A["extraction"], "gates.heldout_conditional_precision.value")),
    "0.9868": C("extraction: gates.conditional_precision.value",
                dig(A["extraction"], "gates.conditional_precision.value")),
    "0.7037": C("extraction: gates.reference_coverage.value",
                dig(A["extraction"], "gates.reference_coverage.value")),
    "0.2742": C("extraction: gates.usable_event_coverage.value",
                dig(A["extraction"], "gates.usable_event_coverage.value")),
    "0.80": C("extraction: gates.reference_coverage.required",
              dig(A["extraction"], "gates.reference_coverage.required")),
    "216": C("extraction: coverage.extracted_gaap_diluted_eps",
             dig(A["extraction"], "coverage.extracted_gaap_diluted_eps")),
    "47": C("extraction: binding_finding.fy_end_quarter_events",
            dig(A["extraction"], "binding_finding.fy_end_quarter_events")),
    "0.7824": C("extraction: binding_finding.max_attainable_reference_coverage",
                dig(A["extraction"],
                    "binding_finding.max_attainable_reference_coverage")),
    # ---- vendor feasibility audit --------------------------------------------
    "0.6719": C("feasibility: gates.g5_crosswalk_rate.value",
                dig(A["feasibility"], "gates.g5_crosswalk_rate.value")),
    "0.90": C("feasibility: gates.g5_crosswalk_rate.required",
              dig(A["feasibility"], "gates.g5_crosswalk_rate.required")),
    "267": C("feasibility: sec_index_events_with_parsed_fiscal_period",
             dig(A["feasibility"],
                 "crosswalk_diagnostics.sec_index_events_with_parsed_fiscal_period")),
    "306": C("feasibility: crosswalk_diagnostics.sec_index_events_total",
             dig(A["feasibility"], "crosswalk_diagnostics.sec_index_events_total")),
    "0.8344": C("feasibility: structural_ceiling_on_frozen_crosswalk_rate",
                dig(A["feasibility"],
                    "crosswalk_diagnostics.structural_ceiling_on_frozen_crosswalk_rate")),
    "320": C("feasibility: counts.complete_records",
             dig(A["feasibility"], "counts.complete_records")),
    "139": C("feasibility: provider_vs_sec_eps.overlapping_events",
             dig(A["feasibility"], "provider_vs_sec_eps.overlapping_events")),
    "0.0576": C("feasibility: provider_vs_sec_eps.match_rate_within_0_01",
                dig(A["feasibility"], "provider_vs_sec_eps.match_rate_within_0_01")),
    "0.26": C("feasibility: provider_vs_sec_eps.median_absolute_difference",
              dig(A["feasibility"], "provider_vs_sec_eps.median_absolute_difference")),
    # ---- PR #34 initial-reaction study ---------------------------------------
    "298": C("pr34: sample_gate.events.value",
             dig(A["pr34"], "sample_gate.events.value")),
    "116": C("pr34: stage1.n_oos", dig(A["pr34"], "stage1.n_oos")),
    "0.052506": C("pr34: stage1.mae_B", dig(A["pr34"], "stage1.mae_B")),
    "0.051203": C("pr34: stage1.mae_C", dig(A["pr34"], "stage1.mae_C")),
    "+2.482": C("pr34: stage1.mae_improvement_pct",
                dig(A["pr34"], "stage1.mae_improvement_pct")),
    "+0.13515": C("pr34: stage1 oos_spearman_surprise_vs_initial_reaction",
                  dig(A["pr34"],
                      "stage1.oos_spearman_surprise_vs_initial_reaction")),
    "0.148026": C("pr34: stage1.oos_spearman_p",
                  dig(A["pr34"], "stage1.oos_spearman_p")),
    "-0.0007272": C("pr34: stage1 bootstrap ci95[0]",
                    dig(A["pr34"], "stage1.bootstrap_mae_diff.ci95.0")),
    "0.0007272": C("pr34: |stage1 bootstrap ci95[0]|",
                   abs(dig(A["pr34"], "stage1.bootstrap_mae_diff.ci95.0"))),
    "+0.0031700": C("pr34: stage1 bootstrap ci95[1]",
                    dig(A["pr34"], "stage1.bootstrap_mae_diff.ci95.1")),
    "0.0031700": C("pr34: stage1 bootstrap ci95[1]",
                   dig(A["pr34"], "stage1.bootstrap_mae_diff.ci95.1")),
    "0.0012707": C("pr34: stage1 bootstrap mean",
                   dig(A["pr34"], "stage1.bootstrap_mae_diff.mean")),
    # ---- PR #35 temporal replication -----------------------------------------
    "462": C("pr35: sample_gate.events_2004_2017.value",
             dig(A["pr35"], "sample_gate.events_2004_2017.value")),
    "283": C("pr35: stage1_replication.n_oos",
             dig(A["pr35"], "stage1_replication.n_oos")),
    "0.044226": C("pr35: stage1_replication.mae_B",
                  dig(A["pr35"], "stage1_replication.mae_B")),
    "0.043246": C("pr35: stage1_replication.mae_C",
                  dig(A["pr35"], "stage1_replication.mae_C")),
    "+2.216": C("pr35: stage1_replication.mae_improvement_pct",
                dig(A["pr35"], "stage1_replication.mae_improvement_pct")),
    "+0.2169": C("pr35: oos_spearman_surprise_vs_initial_reaction",
                 dig(A["pr35"],
                     "stage1_replication.oos_spearman_surprise_vs_initial_reaction")),
    "0.000236": C("pr35: stage1_replication.oos_spearman_p",
                  dig(A["pr35"], "stage1_replication.oos_spearman_p")),
    "-0.0000561": C("pr35: stage1_replication bootstrap ci95[0]",
                    dig(A["pr35"],
                        "stage1_replication.bootstrap_mae_diff.ci95.0")),
    "0.0000561": C("pr35: |stage1_replication bootstrap ci95[0]|",
                   abs(dig(A["pr35"],
                           "stage1_replication.bootstrap_mae_diff.ci95.0"))),
    "+0.0021342": C("pr35: stage1_replication bootstrap ci95[1]",
                    dig(A["pr35"],
                        "stage1_replication.bootstrap_mae_diff.ci95.1")),
    "0.0021342": C("pr35: stage1_replication bootstrap ci95[1]",
                   dig(A["pr35"],
                       "stage1_replication.bootstrap_mae_diff.ci95.1")),
    "0.0009811": C("pr35: stage1_replication bootstrap mean",
                   dig(A["pr35"], "stage1_replication.bootstrap_mae_diff.mean")),
    "28": C("pr35: bootstrap block_days",
            dig(A["pr35"], "stage1_replication.bootstrap_mae_diff.block_days")),
    "20260817": C("pr35: bootstrap seed",
                  dig(A["pr35"], "stage1_replication.bootstrap_mae_diff.seed")),
    "2000": C("pr35: bootstrap draws",
              dig(A["pr35"], "stage1_replication.bootstrap_mae_diff.draws")),
    # ---- derived arithmetic over committed figures ---------------------------
    "2.4": C("derived: pr35 n_oos / pr34 n_oos",
             dig(A["pr35"], "stage1_replication.n_oos")
             / dig(A["pr34"], "stage1.n_oos")),
}

# Allowlist: structural, bibliographic, definitional or axis-tick values only.
ALLOW = {
    # section and subsection numbers
    **{str(i): "section number" for i in range(1, 13)},
    **{f"{a}.{b}": "subsection number" for a in (4, 5, 8) for b in range(1, 8)},
    # calendar years
    **{y: "year" for y in ("1950", "1968", "1984", "1989", "1995", "2008", "2010",
                           "2011", "2012", "2014", "2016", "2017", "2023", "2024",
                           "2025", "2004", "2007")},
    "1.0": "artifact version",
    "231": "declared abstract word count",
    "0.5": "AUC chance level (definition)",
    "100": "Google Trends index maximum (definition)",
    "0.01": "USD 0.01 EPS match tolerance (definition)",
    "95": "confidence level (definition)",
    "2.02": "SEC 8-K item number (regulatory identifier)",
    "09": "09:30 ET clock component", "30": "09:30/16:00 ET clock component",
    "16": "16:00 ET clock component", "00": "clock component",
    # figure 2 axis ticks
    "-0.001": "figure 2 axis tick", "0.000": "figure 2 axis tick",
    "0.001": "figure 2 axis tick", "0.002": "figure 2 axis tick",
    "0.003": "figure 2 axis tick",
    # structural counts stated as study design, not results
    "8": "count of replication years / gate count", "9": "count of firms with events",
    "10": "count of firms in universe / reference count",
    "5": "count of years where the augmented model won / horizon in sessions",
    "4": "count of firms helped / count of interpretation points",
    "3": "count of evidence levels", "2": "count of signal families",
    "7": "count of studies in the evidence matrix",
    "6": "count of gates", "11": "section number", "12": "section number",
    "13": "reference list index", "15": "article number",
    "01": "HYP-01 protocol identifier",
    "34": "pull-request identifier (PR #34)",
    "35": "pull-request identifier (PR #35)",
}


def scan_tokens():
    """Manuscript body (pre-References), whole summary, SVG text nodes only."""
    chunks = []
    man = MANUSCRIPT.read_text(encoding="utf-8").split("## References")[0]
    chunks.append((MANUSCRIPT.name, man))
    chunks.append((SUMMARY.name, SUMMARY.read_text(encoding="utf-8")))
    for f in FIGURES:
        body = f.read_text(encoding="utf-8")
        chunks.append((f.name, "\n".join(re.findall(r"<text[^>]*>(.*?)</text>",
                                                    body, re.S))))
    found = {}
    for name, text in chunks:
        text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)     # 2,000 -> 2000
        for m in NUM.finditer(text):
            found.setdefault(m.group(0), set()).add(name)
    return found


def check_value(token, desc, source):
    """A displayed token must equal its source at the precision actually shown."""
    try:
        shown = float(token)
    except ValueError:
        return bad(f"token {token!r} is not parseable as a number")
    frac = token.split(".")[1] if "." in token else ""
    nd = len(re.sub(r"[eE].*$", "", frac))
    tol = 0.5 * (10 ** -nd) + 1e-12
    if abs(shown - source) > tol:
        return bad(f"token {token!r} does not match {desc} "
                   f"(source {source!r}, tolerance {tol:g})")
    if round(source, nd) != round(shown, nd):
        return bad(f"token {token!r} is rounded inconsistently with {desc} "
                   f"(source {source!r})")
    return True


def main(argv=None):
    print("=" * 72)
    print("NUMERICAL AUDIT -- Signal Without Strategy")
    print("=" * 72)

    for f in [MANUSCRIPT, SUMMARY] + FIGURES:
        if not f.exists():
            bad(f"missing deliverable: {f.name}")
    if len(FIGURES) != 3:
        bad(f"expected exactly 3 figures, found {len(FIGURES)}")
    else:
        ok(f"three figures present: {[f.name for f in FIGURES]}")

    # 1. every claim resolves against its committed artifact
    for token, (desc, source) in sorted(CLAIMS.items()):
        check_value(token, desc, source)
    ok(f"{len(CLAIMS)} claimed values resolved against committed artifacts")

    # 2. no unaccounted numeric token
    found = scan_tokens()
    unaccounted = {t: sorted(v) for t, v in found.items()
                   if t not in CLAIMS and t not in ALLOW}
    if unaccounted:
        for t, where in sorted(unaccounted.items()):
            bad(f"unaccounted numeric token {t!r} in {where}")
    else:
        ok(f"all {len(found)} distinct numeric tokens accounted for "
           f"({len(CLAIMS)} claims, {len(ALLOW)} allowlisted)")

    # 3. allowlist hygiene -- an allowlist entry must not shadow a research claim
    shadow = sorted(set(ALLOW) & set(CLAIMS))
    if shadow:
        bad(f"allowlist shadows research claims: {shadow}")
    else:
        ok("allowlist does not shadow any research claim")

    # 4. prohibited interpretations
    man = MANUSCRIPT.read_text(encoding="utf-8")
    summ = SUMMARY.read_text(encoding="utf-8")
    both = man + "\n" + summ
    flat = " ".join(both.split())
    figs = "\n".join(f.read_text(encoding="utf-8") for f in FIGURES)
    everything = flat + " " + " ".join(figs.split())

    prohibited = [
        (r"\bGAAP earnings surprise\b(?!['’]?\s*[,.]?\s*not)", "calls vendor EPS a GAAP surprise"),
        (r"SEC-validated (EPS )?surprise", "calls vendor EPS an SEC-validated surprise"),
        (r"point[- ]in[- ]time (estimate )?(vintage )?(is |was )?guaranteed",
         "claims a guaranteed point-in-time estimate vintage"),
        (r"(?<!no )(?<!No )(?<!not )(?<!Not )(?<!never )(?<!Never )(?<!none )"
         r"\b(investable|tradable) (signal|strategy)\b",
         "claims an investable or tradable strategy"),
        (r"replication (succeeded|was successful|passed)",
         "calls the temporal replication successful"),
        (r"(no|zero|absent) association between surprise",
         "denies the significant Spearman association"),
        (r"\b(proven|guaranteed|risk[- ]free) (alpha|profit|return)",
         "overstates a result"),
        # The prespecification claim must stay narrow. A blanket statement that rules
        # were committed before results, without the designated/reactive distinction,
        # overstates what the record supports.
        (r"[Rr]ules were written down and committed before the corresponding results",
         "restates the overly broad prespecification claim"),
        (r"\b(all|every|the entire) (rules?|controls?|specifications?) (were|was) "
         r"(frozen|prespecified|committed) before",
         "claims blanket prespecification across the whole program"),
        (r"\bthe (program|research program|synthesis) was preregistered\b",
         "claims the program or synthesis was preregistered"),
        (r"\bwe (recommend|advise) (trading|deploying|investing)",
         "recommends deployment"),
    ]
    for pat, why in prohibited:
        m = re.search(pat, everything, re.I)
        if m:
            bad(f"prohibited claim -- {why}: {m.group(0)!r}")
    ok("no prohibited interpretation matched")

    # 5. required disclaimers actually present
    required = [
        ("VENDOR_DEFINED_REPORTED_EPS_SURPRISE", "vendor construct named"),
        ("POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED", "provenance limitation named"),
        ("not SEC-validated GAAP diluted EPS", "vendor EPS explicitly distinguished"),
        ("Not preregistered", "non-preregistration stated"),
        ("before that study's designated outcomes",
         "designated-vs-reactive prespecification distinction stated"),
        ("event-identity deduplication", "reactive control named"),
        ("strictly earlier lag-feature repair", "reactive control named"),
        ("research program and this synthesis were not preregistered",
         "program-level non-preregistration stated"),
    ]
    # Strip markdown emphasis only. Underscores are load-bearing inside the frozen
    # constant names, so they are never removed.
    plain = re.sub(r"[*`]+", "", everything)
    for needle, why in required:
        if needle.lower() not in plain.lower():
            bad(f"missing required disclaimer -- {why}: {needle!r}")
    ok("all required disclaimers present")

    # 6. nulls are not overstated and the association is not denied
    if "0.000236" not in flat or "+0.2169" not in flat:
        bad("the significant replication association is not reported in the manuscript")
    if not re.search(r"is not a null result|not describe it as one|real association",
                     flat, re.I):
        bad("the manuscript does not state that the significant association is not a null")
    else:
        ok("significant association reported and explicitly not called a null")
    if not re.search(r"None of the tested strategies qualifies as investable", flat):
        bad("the manuscript does not state that no strategy qualifies as investable")
    else:
        ok("explicit non-investability statement present")

    # 7. secondary metrics are not promoted over primary gates
    if re.search(r"(therefore|so) (the )?(strategy|signal) (works|is validated)", flat, re.I):
        bad("a secondary metric is promoted to a conclusion")
    else:
        ok("no secondary metric promoted over a primary gate")

    # 8. the replication is described as failed
    if "TEMPORAL_REPLICATION_FAILS" not in \
            A["pr35"]["decision_label"]:
        bad("pr35 artifact no longer carries the failing label")
    elif not re.search(r"replication failed its prespecified gate|failed the gate|"
                       r"gate failed", flat, re.I):
        bad("the manuscript does not state that the replication failed its gate")
    else:
        ok("replication correctly described as having failed its gate")

    print()
    if FAIL:
        print(f"{len(FAIL)} AUDIT FAILURE(S)")
        return 1
    print("NUMERICAL AUDIT PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
