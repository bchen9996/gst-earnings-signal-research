# HYP-06 Phase 3 result, characterized (2026-09-14)

Written in direct response to external review. `HYP06_PHASE3_RESULT_
2026-09-13.json` was computed once, per the signed Phase 2 lock
(`HYP06_PHASE2_LOCK_2026-09-13.json`) and Phase 3 authorization
(`HYP06_PHASE3_AUTHORIZATION_2026-09-13.json`), and is reported as
computed. This note does not change, retroactively re-derive, or re-run
any part of that result — every number below except the corrected
framing note is either already present in the result, or re-derived
offline from already-committed artifacts (the signed lock, the real
fetched peer closes/earnings) by calling the same pure functions the
original run called, never by re-running the holdout itself. It exists
because the result's own `sample_size_disclosure` describes the LOCKED
sample (778 pairs), not the ANALYZED sample the regression actually ran
on (648 observations, 646 clusters), and because one exclusion category
— the largest one — never made it into the written artifact at all.

## Was the holdout actually run? Yes.

`HYP06_PHASE3_RESULT_2026-09-13.json` exists, `reported_regardless_of_
outcome: true`, `no_rerun_permitted: true`, tied to a real, declared
`HYP06_PHASE3_AUTHORIZATION_2026-09-13.json` (declared_by `bchen9996`,
2026-09-13, now `consumed: true`, `consumed_by_result:
"HYP06_PHASE3_RESULT_2026-09-13.json"`). This is not a rehearsal and not
a draft.

## Headline: not significant, explicitly EXPLORATORY

  * **Locked sample**: 778 (peer, anchor-event) pairs, 25 peers, 29
    anchors — fixed before this run, per the signed Phase 2 lock.
  * **Analyzed sample** (after residualization exclusions, constant
    across all 20 horizons): **648 observations, clustered into 646
    distinct `event_id` values** (one-way `event_id` clustering — HYP-05's
    own re-decision away from HYP-04's D1-locked `calendar_period`,
    reused unchanged by HYP-06; see `clustered_se.HYP05_TWO_WAY_
    LIMITATION_NOTE`).
  * Peak horizon: h=1, beta=+3.5066, se=2.6996, **t=+1.299**
    (Satterthwaite dof≈78.6).
  * Max-T permutation critical value (95th pct, 2000 permutations,
    k_eff≈7.45): **2.703**.
  * `max_abs_t` (1.299) does not clear `max_t_critical_value` (2.703) ->
    `peak_significant: false`. `max_t_p_value: 0.621`.

This verdict is a direct comparison of the observed statistic against
the empirical permutation null computed from the SAME analyzed 648-row
table — the inference itself was always computed correctly on the real,
post-exclusion sample. What was wrong is only the DESCRIPTION of that
sample size elsewhere in the artifact (see below).

## The full 778 -> 648 exclusion ladder

Re-derived offline by calling `make_hyp06_phase3_run._build_real_panel`
and `target.build_feature_table` directly against the real, signed lock
and the real, already-fetched peer closes/earnings — the exact same pure
functions the original run called, with no new computation against any
locked peer's outcome beyond what already happened on 2026-09-13.

| Stage | Rows remaining | Excluded this stage | Reason |
|---|---:|---:|---|
| Locked pairs x horizon grid | 15,560 | — | 778 pairs x 20 horizons, the theoretical maximum |
| After `raw_log_ratio_target` finiteness | 15,540 | 20 | reference or forward return window not fully available (short/missing window) |
| After `pre_earnings_history` | 13,360 | **2,180** | the anchor event predates this peer's OWN first recorded 8-K earnings release, so no days-to-own-earnings figure at that point is evidentially grounded |
| After `bucket_population` | **12,960** | 400 | the peer's days-to-own-earnings bucket was under-populated (Patch 12 "accept-and-report": excluded, never imputed, never widened after seeing the count) |
| **Final table** | **12,960 rows = 648/horizon x 20 horizons** | **2,600 total (16.7%)** | |

**646 clusters, defined precisely:** of the 776 distinct `event_id`
values in the full 778-pair locked set, only **646** retain at least one
surviving (peer, event) observation after the exclusions above — the
other 130 clusters lost every peer attached to them and disappear from
the regression entirely. 648 surviving observations across 646 clusters
means two clusters carry 2 peers each (or one carries 3); the rest are
singletons — consistent with HYP-06's own real universe, where the large
majority of peers pair with exactly one anchor.

**Why the ladder is horizon-independent** (n_obs=648 at every one of the
20 horizons, not just at the peak): `EarningsCycleBaseline` is estimated
per `(peer, horizon)`, so the code technically allows exclusion to vary
by horizon — but in practice, whether a (peer, event) pair predates that
peer's earnings history, or falls in an under-populated bucket, turns out
not to depend on which forward horizon is being computed for this real
dataset. Verified directly: every one of the 20 `fits_by_horizon` entries
reports `n_obs: 648, n_clusters: 646`, exactly.

## The largest exclusion category was never written to the result at all

`target.build_feature_table` computes and returns three separate
disclosures: `retained_history`, `bucket_population`, and
`pre_earnings_history`. `make_phase1_diagnostics._run_treatment` —
imported unchanged by `make_hyp06_phase3_run.py`, the same reused
function HYP-04's own Phase 1 exploration and HYP-06's Phase 3 both call
— carries only the first two into its own returned dict. `pre_earnings_
history` is silently dropped. Confirmed directly: `HYP06_PHASE3_RESULT_
2026-09-13.json`'s `treatment.pre_earnings_history` field is `null`.

This means the SINGLE LARGEST exclusion source (2,180 of 2,600 excluded
candidate rows — 84% of all exclusions, and by itself a 14.0% cut of the
15,540-row candidate pool) was computed correctly and then never
surfaced in the artifact a reader would actually look at. Only the
smaller 400-row `bucket_population` exclusion (2.6%) was visible. This is
a real, reproducible gap in the tooling, not a defect specific to any one
peer or anchor — `_run_treatment` is shared, already-reused code, and this
same silent drop would recur in any future hypothesis that reuses it with
residualization on.

**Recommendation, not yet acted on:** add `pre_earnings_history` to
`_run_treatment`'s returned dict (`make_phase1_diagnostics.py`) so a
future result surfaces all three exclusion disclosures `target.
build_feature_table` already computes. That function is shared with
HYP-04's own already-run, already-reported Phase 1 diagnostic and with
HYP-06's own already-signed, already-spent Phase 3 result, so — same
discipline HYP-05's own characterization used for its `k_eff` anomaly —
this is flagged for the repo owner's decision rather than changed
unilaterally here. Fixing it forward changes nothing about either
already-computed result; it only affects what a FUTURE reuse of that
function would report.

## The "4x" / "nearly 4x" floor-clearance framing needs correcting

`HYP06_PHASE2_LOCK_2026-09-13.json`'s `sample_size_disclosure.why` field
(copied verbatim into `HYP06_PHASE3_RESULT_2026-09-13.json`'s own
`sample_size_disclosure`, since `build_result` carries the lock's
disclosure through unchanged) reads:

> "778 locked (peer, event) pairs clears the provisional 195-pair floor
> by 4.0x"

This is arithmetically correct for the LOCKED set (778/195 = 3.99x) but
describes a sample that was never actually regressed. The ANALYZED
sample that produced the reported t-stats and p-value is 648
observations / 646 clusters:

  * 648 / 195 = **3.32x** — "clears by over 3x," not "nearly 4x."
  * 646 distinct clusters / 195 = **3.31x** on the clustering dimension
    that actually governs the CR2 standard errors.

`HYP06_ScaledSupplyChainRelationshipLag_MODEL_PLAN_2026-09-13.md` (written
2026-09-13, BEFORE this run, when 778 was the only number knowable) and
`HYP06_SAMPLE_SIZE_GATE_2026-09-13.md` (same) both use 778 for the same
reason — that framing was correct and honest for a document written
before the holdout ran, since the analyzed-sample reduction is only
knowable once residualization actually executes against real data. Only
the RESULT document's own disclosure — written AFTER the real
computation, when 648 was already known — should have used the analyzed
number and did not, because it inherited the lock's pre-run text
unchanged rather than being recomputed post-run.

**The qualitative conclusion is unchanged**: 648 (and 646 clusters) still
clears the provisional 195 floor comfortably, just not by "nearly 4x" —
by "over 3x." Nothing about `peak_significant`, `max_t_p_value`, or any
`beta`/`se`/`t_stat` moves; those were always computed on the real
648-row table.

## Bottom line

HYP-06's one exploratory check — 778 locked pairs, 648 actually analyzed
across 646 clusters, after a real and now fully-itemized exclusion ladder
— found no significant delayed transmission at any of 20 horizons
(max_abs_t 1.30 vs. critical value 2.70, p=0.62), the third null result in
this project's supply-chain-hedge line after HYP-04 and HYP-05, now on a
sample that clears its own provisional power floor by a real, if smaller
than previously stated, margin. This does not establish that delayed
supply-chain earnings-information transmission never occurs — it
establishes that this specific construction (customer/supplier
relationships, a 1-to-20-trading-day horizon grid, `event_id` clustering,
the residualized log realized-variance-ratio target) did not detect it,
on the largest, most systematically-discovered sample this project has
built. Combined with HYP-04's and HYP-05's own null results on the same
underlying mechanism at smaller scale (three real, preregistered
constructions of customer/supplier delayed transmission, all null), and
now HYP-07's own separate null result (2026-09-14, a genuinely different
mechanism — competitor relationships — and a genuinely different, signed
target), this project has four real, honest null results across every
construction of earnings-information transmission it has tested, none
of them close to significant.
