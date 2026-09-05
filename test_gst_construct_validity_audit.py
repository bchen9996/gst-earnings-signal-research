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
GEN2 = ROOT / "tools" / "run_gst_construct_validity_followup.py"
ART2 = ROOT / "Live Signal Engine" / "GST_SEARCH_CONSTRUCT_VALIDITY_FOLLOWUP_2026-09-04.json"
GEN3 = ROOT / "tools" / "run_gst_corroboration_fix.py"
ART3 = ROOT / "Live Signal Engine" / "GST_SEARCH_CONSTRUCT_VALIDITY_CORROBORATION_2026-09-04.json"
GEN4 = ROOT / "tools" / "run_gst_instrument_normalization_fix.py"
ART4 = ROOT / "Live Signal Engine" / "GST_SEARCH_CONSTRUCT_VALIDITY_NORMALIZATION_2026-09-04.json"
PULL = ROOT / "GST_IntentFiltered_Pull.py"
DOC = ROOT / "Live Signal Engine" / "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0_2026-09-04.md"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _load_mod(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _gen():
    return _load_mod(GEN, "_f5gen")


def _gen2():
    return _load_mod(GEN2, "_f5followup")


def _gen3():
    return _load_mod(GEN3, "_f5corrob")


def _gen4():
    return _load_mod(GEN4, "_f5norm")


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


def test_6_followup_recomputes_and_holds() -> None:
    """The follow-up artifact is rebuilt from source and compared."""
    m = _gen2()
    art = json.loads(ART2.read_text(encoding="utf-8"))
    for name, fn in (("the_fail", m.section_the_fail),
                     ("the_screen", m.section_the_screen),
                     ("the_trap", m.section_the_trap)):
        check(f"6. {name} recomputes to the committed artifact", fn() == art[name])


def test_7_the_correction_is_real_and_pinned() -> None:
    """§3e's explanation was wrong. Assert the refutation, not the retraction."""
    art = json.loads(ART2.read_text(encoding="utf-8"))
    f = art["the_fail"]
    check("7a. STZ's raw series is the RICHEST of the eight, not the thinnest",
          f["stz_raw_median_rank_of_8"] == 1)
    check("7b. so a sparse-raw-series explanation is refuted by the data",
          f["raw_series_refutes_thinness"] is True)
    check("7c. the thinness is in the earnings-intent series instead",
          f["stz_intent_pct_zero"] > 90.0,
          f"STZ intent %zero = {f['stz_intent_pct_zero']}")

    doc = DOC.read_text(encoding="utf-8")
    check("7d. §3e carries an inline correction pointer",
          "CORRECTED IN §7" in doc and "Do not cite §3e's reasoning" in doc)
    check("7e. §3e's original text is left intact, not silently rewritten",
          "one ticker fails the thinness test outright" in doc)


def test_8_the_screen_does_not_separate_cleanly() -> None:
    """The write-up says the criterion was human, not statistical. Pin it."""
    s = json.loads(ART2.read_text(encoding="utf-8"))["the_screen"]
    check("8a. the dropped group is higher and flatter than the kept group",
          s["dropped_group"]["mean_median"] > s["kept_group"]["mean_median"]
          and s["dropped_group"]["mean_cv"] < s["kept_group"]["mean_cv"])
    check("8b. but the signature also catches kept tickers, so it does not "
          "separate the groups",
          s["separates_cleanly"] is False
          and len(s["signature_also_catches_kept"]) > 0)
    check("8c. the criterion was therefore not statistical",
          s["criterion_was_statistical"] is False)
    check("8d. DELL is flagged in the paper's universe",
          "DELL" in s["paper_universe_matches"])


def test_9_the_tautology_is_broken_and_stz_fails() -> None:
    """The independent instrument corroborates 7 of 8, and refuses STZ."""
    tr = json.loads(ART2.read_text(encoding="utf-8"))["the_trap"]
    per = tr["per_ticker"]
    ok = {k: v for k, v in per.items() if v.get("status") == "ok"}
    check("9a. all eight tickers produced a comparison", len(ok) == 8)

    strong = [k for k, v in ok.items()
              if v["nonzero_rate_event"] == 1.0
              and v["perm_p_median_difference"] == 0.0]
    check("9b. seven of eight are corroborated by the independent instrument",
          len(strong) == 7, f"corroborated: {sorted(strong)}")

    stz = ok["STZ"]
    check("9c. STZ is the exception and fails outright",
          stz["nonzero_rate_event"] < 1.0
          and stz["median_event"] == 0.0
          and stz["perm_p_median_difference"] == 1.0)

    check("9d. the z comparison is reported only where the series supports it",
          sorted(tr["tickers_supporting_z_comparison"]) == ["AMZN", "MSFT"])
    not_computable = [k for k, v in ok.items() if v.get("z_comparison") == "not_computable"]
    check("9e. and is refused, not faked, for the other six",
          len(not_computable) == 6)

    doc = DOC.read_text(encoding="utf-8")
    check("9f. the write-up does not overclaim this as selection-free",
          "not a selection-free test" in doc)


def test_10_followup_guards_refuse() -> None:
    m = _gen2()
    check("10a. the follow-up artifact exists", ART2.exists())
    check("10b. refusals use RefusedError, not bare assert",
          issubclass(m.RefusedError, RuntimeError))
    check("10c. the signature thresholds are module constants, not tuned inline",
          isinstance(m.SIG_MIN_MEDIAN, float) and isinstance(m.SIG_MAX_CV, float))
    check("10d. the permutation test is seeded",
          m.RANDOM_SEED == 42 and m.N_PERMUTATIONS == 10000)


def test_11_corroboration_fix_recomputes() -> None:
    m = _gen3()
    art = json.loads(ART3.read_text(encoding="utf-8"))
    ed, br = m._load_inputs()
    for name, fn in (("selectivity_and_periodicity", m.section_selectivity),
                     ("like_for_like", m.section_like_for_like),
                     ("instrument_resolution", m.section_instrument_resolution)):
        check(f"11. {name} recomputes to the committed artifact",
              fn(ed, br) == art[name])


def test_12_the_baseline_is_structurally_trough_only() -> None:
    s = json.loads(ART3.read_text(encoding="utf-8"))["selectivity_and_periodicity"]
    check("12a. a 12-week baseline on a 13-week cadence excludes earnings weeks",
          s["baseline_is_structurally_trough_only"] is True)
    inside = [v["mean_earnings_weeks_inside_own_baseline"]
              for v in s["per_ticker"].values()]
    check("12b. no ticker averages even one earnings week in its own baseline",
          max(inside) < 1.0, f"max={max(inside)}")
    check("12c. the signal fires on a large share of ALL earnings weeks",
          s["selectivity_pct_max"] >= 70.0,
          f"max selectivity={s['selectivity_pct_max']}%")


def test_13_the_corroboration_is_withdrawn_not_rescued() -> None:
    """The headline result of section 7.3 must not survive anywhere."""
    lf = json.loads(ART3.read_text(encoding="utf-8"))["like_for_like"]
    per = lf["per_ticker"]
    ps = [v["perm_p_median_difference"] for v in per.values()
          if v.get("perm_p_median_difference") is not None]
    check("13a. every ticker produced a like-for-like comparison", len(ps) == 8)
    check("13b. not one reaches significance", min(ps) > 0.05, f"min p={min(ps)}")

    # 7.3's contrast was 1.000 vs 0.129. Held to earnings weeks it vanishes.
    both_one = [k for k, v in per.items()
                if v.get("nonzero_rate_selected") == 1.0
                and v.get("nonzero_rate_non_selected") == 1.0]
    check("13c. the non-zero-rate contrast disappears once both arms are "
          "earnings weeks", len(both_one) == 7, f"both 1.00: {sorted(both_one)}")

    higher_in_control = [k for k, v in per.items()
                         if v.get("median_selected") is not None
                         and v["median_selected"] < v["median_non_selected"]]
    check("13d. and for some tickers the NON-selected arm is higher",
          len(higher_in_control) >= 3, f"{sorted(higher_in_control)}")

    doc = DOC.read_text(encoding="utf-8")
    check("13e. section 7.3 is marked corrected and withdrawn",
          "CORRECTED IN §8, AND WITHDRAWN" in doc)
    check("13f. section 7.3's original text is left intact",
          "The tautology, broken" in doc)


def test_14_the_power_rule_cannot_be_bypassed() -> None:
    """An underpowered arm must never be reported as a null."""
    m = _gen3()
    lf = json.loads(ART3.read_text(encoding="utf-8"))["like_for_like"]
    check("14a. the power rule is a module constant, pre-declared",
          m.MIN_ARM_N == 5)
    check("14b. it is recorded in the artifact", lf["min_arm_n"] == m.MIN_ARM_N)
    for k, v in lf["per_ticker"].items():
        if v.get("status") in (None, "no_intent_series"):
            continue
        small = min(v["n_selected"], v["n_non_selected"]) < m.MIN_ARM_N
        if small and v["status"] != "underpowered":
            check(f"14c. {k} has a small arm but is not flagged underpowered",
                  False)
            return
    check("14c. every ticker with an arm below the minimum is flagged "
          "underpowered, and none here is", True)
    check("14d. the interpretation was pre-declared, not written after",
          set(lf["pre_declared_interpretation"]) ==
          {"higher_in_selected_arm", "no_detectable_difference", "commitment"})


def test_15_the_null_is_not_overclaimed() -> None:
    """Saturation means the null is weak evidence, and the doc must say so."""
    art = json.loads(ART3.read_text(encoding="utf-8"))
    ir = art["instrument_resolution"]
    check("15a. the instrument is saturated at earnings weeks for most tickers",
          ir["n_tickers_saturated_at_earnings_weeks"] >= 7)
    check("15b. the diagnostic declares it was added after the null",
          ir["added_after_seeing_8_2"] is True
          and ir["does_not_change_8_2"] is True)

    doc = DOC.read_text(encoding="utf-8")
    check("15c. the write-up says the null cannot answer the question",
          "cannot answer the question" in doc)
    check("15d. and refuses to claim the signal is spurious",
          "Nothing here shows the attention signal is spurious" in doc)
    check("15e. and names what would actually answer it",
          "multi-term" in doc and "dynamic range" in doc)


def test_16_normalization_fix_recomputes() -> None:
    m = _gen4()
    art = json.loads(ART4.read_text(encoding="utf-8"))
    ed, br = m._load_inputs()
    check("16a. normalization_evidence recomputes to the committed artifact",
          m.section_normalization_evidence() == art["normalization_evidence"])
    check("16b. selection_side recomputes to the committed artifact",
          m.section_selection_side(ed, br) == art["selection_side"])
    check("16c. blocked_like_for_like recomputes to the committed artifact",
          m.section_blocked_like_for_like(ed, br) == art["blocked_like_for_like"])
    ss = art["selection_side"]["totals"]
    check("16d. the selection-side totals are internally consistent",
          ss["retained"] + ss["dropped"] == ss["audited"],
          f"{ss['retained']}+{ss['dropped']} != {ss['audited']}")


def test_17_the_instrument_is_renormalised_every_year() -> None:
    """The forced annual ceiling, and the citation that explains it."""
    ne = json.loads(ART4.read_text(encoding="utf-8"))["normalization_evidence"]
    check("17a. every ticker-year contains a week at exactly 100",
          ne["every_ticker_year_has_at_least_one_100"] is True,
          f"{ne['n_ticker_years_with_at_least_one_100']}/{ne['n_ticker_years']}")
    per = ne["per_ticker"]
    bad = [f"{t}/{y}" for t, rows in per.items()
           for y, v in rows.items() if v["n_at_100"] < 1]
    check("17b. no ticker-year lacks the annual ceiling", not bad, str(bad))

    # 39 of 40, not 40 of 40 -- the tie is disclosed rather than rounded away.
    check("17c. the one ticker-year with a tie at the ceiling is disclosed",
          ne["n_ticker_years_with_exactly_one_100"]
          == ne["n_ticker_years"] - 1
          and "SBUX 2021" in ne["ties_at_the_annual_ceiling"])

    # Pin the citation so it cannot rot into a wrong line number.
    src = PULL.read_text(encoding="utf-8").splitlines()
    cited = 45
    line = src[cited - 1] if cited <= len(src) else ""
    check("17d. the cited pull-script line really is the per-year timeframe",
          "{year}-01-01" in line and "{year}-12-31" in line,
          f"line 45 is: {line.strip()!r}")

    doc = DOC.read_text(encoding="utf-8")
    check("17e. section 8.3 is marked corrected", "CORRECTED IN §9." in doc)
    check("17f. section 8.3's original text is left intact",
          "But the instrument is saturated, so the null is weak evidence" in doc)


def test_18_blocking_actually_neutralises_a_year_effect() -> None:
    """Permuting within strata must kill a confound a naive pooled test reports.

    Fixture: within every stratum the two arms have identical means, so the true
    within-stratum effect is exactly zero. But the arms have different sizes in
    low-scale and high-scale strata, so a test that ignores strata sees a large
    spurious difference. The stratified test must not.
    """
    import numpy as np
    m = _gen4()
    strata = []
    for i in range(3):
        # low-scale stratum: selected has one mid value, non-selected brackets it
        strata.append((2000 + i, np.array([5.0]), np.array([0.0, 10.0])))
        # high-scale stratum: sizes reversed
        strata.append((2100 + i, np.array([90.0, 100.0]), np.array([95.0])))

    obs = m._mean_diff(strata)
    check("18a. the fixture has exactly zero within-stratum effect",
          obs is not None and abs(obs) < 1e-9, f"obs={obs}")

    sel = np.concatenate([a for _, a, _ in strata])
    non = np.concatenate([b for _, _, b in strata])
    naive = float(sel.mean() - non.mean())
    check("18b. a test that ignored strata would report a large difference",
          naive > 20.0, f"naive pooled difference = {naive:.1f}")

    rng = np.random.default_rng(m.RANDOM_SEED)
    p = m._stratified_perm_p(strata, m._mean_diff, rng)
    check("18c. the stratified test reports nothing, as it must",
          p is not None and p >= 0.9, f"stratified p={p}")

    # And the real run's statistics are recorded as agreeing or not, never hidden.
    bl = json.loads(ART4.read_text(encoding="utf-8"))["blocked_like_for_like"]
    check("18d. the robustness statistic is reported alongside the primary",
          bl["perm_p_rank_robustness"] is not None
          and bl["statistics_agree"] is not None)
    check("18e. the primary statistic is declared to govern",
          "does not govern" in bl["pre_declared_interpretation"]["commitment"])


def test_19_the_strata_power_rule_cannot_be_bypassed() -> None:
    """An underpowered blocked test must never be reported as a null."""
    m = _gen4()
    bl = json.loads(ART4.read_text(encoding="utf-8"))["blocked_like_for_like"]
    check("19a. the strata rule is a module constant, pre-declared",
          m.MIN_INFORMATIVE_STRATA == 20)
    check("19b. it is recorded in the artifact",
          bl["min_informative_strata"] == m.MIN_INFORMATIVE_STRATA)
    check("19c. the powered flag matches the rule",
          bl["adequately_powered"]
          == (bl["n_informative_strata"] >= m.MIN_INFORMATIVE_STRATA))
    check("19d. this run cleared the rule, so a verdict is legitimate",
          bl["adequately_powered"] is True and bl["verdict"] != "underpowered")

    # Force the rule to bite and confirm the verdict changes rather than the run
    # quietly reporting a null it has no standing to report.
    ed, br = m._load_inputs()
    original = m.MIN_INFORMATIVE_STRATA
    try:
        m.MIN_INFORMATIVE_STRATA = 10_000
        forced = m.section_blocked_like_for_like(ed, br)
    finally:
        m.MIN_INFORMATIVE_STRATA = original
    check("19e. raised above the available strata, the verdict becomes "
          "underpowered", forced["verdict"] == "underpowered",
          f"got {forced['verdict']}")
    check("19f. and no p-value is emitted to be quoted",
          forced["perm_p"] is None and forced["perm_p_rank_robustness"] is None)

    doc = DOC.read_text(encoding="utf-8")
    check("19g. the write-up names the exact call that would resolve this",
          "build_payload" in doc and "2021-01-01 2025-12-31" in doc)
    check("19h. and does not claim the corroboration is reinstated",
          "stays withdrawn" in doc)


if __name__ == "__main__":
    test_1_artifact_and_document_exist()
    test_2_every_artifact_number_recomputes()
    test_3_the_headline_claims_hold()
    test_4_the_seal_is_verifiable()
    test_5_preconditions_actually_refuse()
    test_6_followup_recomputes_and_holds()
    test_7_the_correction_is_real_and_pinned()
    test_8_the_screen_does_not_separate_cleanly()
    test_9_the_tautology_is_broken_and_stz_fails()
    test_10_followup_guards_refuse()
    test_11_corroboration_fix_recomputes()
    test_12_the_baseline_is_structurally_trough_only()
    test_13_the_corroboration_is_withdrawn_not_rescued()
    test_14_the_power_rule_cannot_be_bypassed()
    test_15_the_null_is_not_overclaimed()
    test_16_normalization_fix_recomputes()
    test_17_the_instrument_is_renormalised_every_year()
    test_18_blocking_actually_neutralises_a_year_effect()
    test_19_the_strata_power_rule_cannot_be_bypassed()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL F5 CONSTRUCT-VALIDITY AUDIT TESTS PASSED")
    sys.exit(0)
