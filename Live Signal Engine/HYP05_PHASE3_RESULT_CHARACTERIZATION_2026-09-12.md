# HYP-05 Phase 3 result, characterized (2026-09-12)

`HYP05_PHASE3_RESULT_2026-09-12.json` was computed once, per the signed
Phase 2 lock (`HYP05_PHASE2_LOCK_2026-09-12.json`) and Phase 3 authorization
(`HYP05_PHASE3_AUTHORIZATION_2026-09-12.json`), and is reported as computed.
This note does not change, retroactively re-derive, or re-run any part of
that result. It exists because one field in it (`effective_independent_
tests`) is numerically real but not meaningfully interpretable, and this
repository's own standard is to characterize a result accurately rather
than let a strange number sit unexplained.

## Headline: not significant, explicitly EXPLORATORY

  * Sample: 8 anchor events (NVDA), 1 peer (AMBA). This is ~24x short of
    HYP-05's own provisional 195-event floor (`HYP05_SAMPLE_SIZE_GATE_
    2026-09-11.md`) -- disclosed inside the result itself
    (`sample_size_disclosure`), not only here.
  * Peak horizon: h=7, beta=-6.20, |t|=1.88.
  * Max-T permutation critical value (95th pct, 2000 permutations,
    unrestricted across the 8 events since `event_id` clustering makes
    every cluster a single event): 5.75.
  * `max_abs_t` (1.88) does not clear `max_t_critical_value` (5.75) ->
    `peak_significant: false`. `max_t_p_value: 0.64`.

This verdict is a direct, self-consistent comparison of the observed
statistic against the empirical permutation null computed from the SAME
data -- it does not depend on the field flagged below.

## The `effective_independent_tests` field is a numerical artifact here

The result reports `effective_independent_tests: 5,808,152.93`. Read at
face value this would say the 20-horizon grid carries as much independent
information as 5.8 million tests -- absurd on its face, and worth stating
plainly rather than passing through silently.

**Why it happens.** `inference.max_t_permutation` backs this number out by
asking what per-test alpha, applied independently across `k` tests, would
produce the empirically observed 95th-percentile critical value under a
*standard-normal* per-test null:

```
a1 = 2 * norm.sf(crit)
k_eff = ln(1 - 0.05) / ln(1 - a1)
```

With only 8 clusters (`event_id` primary clustering, one cluster per
locked event) and a Satterthwaite degrees-of-freedom of only ~1.99, the
CR2 t-distribution the fit is actually drawn from has far fatter tails
than a normal. The permutation null's empirical 95th percentile of
max-|t| across the horizon grid lands at 5.75 -- a value that is a
perfectly ordinary tail draw from a ~2-df t-distribution, but which
`norm.sf(5.75)` treats as `4.4e-9`-level extreme, since it is being
scored against the WRONG (much thinner-tailed) reference distribution.
Feeding that far-in-the-tail `a1` back through the k-solving formula
produces `k_eff` in the millions.

**This is a property of the formula's assumptions meeting an 8-cluster,
~2-df regime, not a coding defect and not something specific to AMBA or
NVDA.** `max_t_permutation` was built and validated against HYP-04's own
holdout, where `calendar_period` clustering produces enough clusters
(and Satterthwaite df) that the normal-tail approximation stays
reasonable. HYP-05's own re-decision to cluster primarily on `event_id`
(`clustered_se.HYP05_TWO_WAY_LIMITATION_NOTE`) is exactly the kind of
choice that, combined with an 8-event sample, exposes the formula's
small-sample blind spot. It is disclosed here as a genuine, reproducible
finding about the tool's range of validity, not swept past.

**What this does and does not affect.** It does NOT affect
`peak_significant`, `max_t_p_value`, `max_t_critical_value`, or any
`beta`/`se`/`t_stat` in `fits_by_horizon` -- all of those come from the
empirical permutation distribution directly, never from `k_eff`. It DOES
mean `effective_independent_tests` from this specific result must not be
read as "how much information the horizon grid carries" and must not be
fed into any other calculation (HYP-05's own sample-size gate math
included) without first re-deriving it in a regime where the normal-tail
back-solve is valid.

**Recommendation, not yet acted on:** `max_t_permutation`'s `k_eff`
back-solve could be hardened (e.g., score against the actual t-reference
distribution instead of a normal, or cap/flag `k_eff` when Satterthwaite
df falls below some threshold) so a future small-cluster run does not
reproduce this. That function is shared with HYP-04's own already-run,
already-reported Phase 3 result, so this is flagged for the repo owner's
decision rather than changed unilaterally here.

## The secondary robustness lens reports identical SEs -- also explained, not a bug

At every horizon the dual-cluster report discloses (5, 7, 10, 20),
`secondary_se == primary_se` exactly (`se_ratio_secondary_over_primary:
1.0`). This is not a computation error: all 8 locked events happen to fall
in 8 DIFFERENT calendar quarters (2016Q2, 2016Q4, 2017Q1, 2017Q2, 2017Q3,
2018Q1, 2020Q2, 2020Q3 -- verified from `locked_event_ids`). With one row
per event per horizon (one peer), clustering by `calendar_period` and by
`event_id` therefore partition the same 8 rows into the same 8 singleton
groups, so the two one-way clusterings are mathematically identical for
this particular event set. The secondary lens supplies no ADDITIONAL
robustness information in this specific run -- a fact about this sample,
not a defect in `dual_cluster_report`.

## Bottom line

HYP-05's one exploratory check against AMBA/NVDA found no significant
transmission at any horizon in an 8-event sample explicitly and
repeatedly labeled underpowered. This does not confirm or refute HYP-05's
underlying question -- it is what one severely underpowered look found,
reported honestly, exactly as agreed with the repo owner on 2026-09-12
before this check was run. The `effective_independent_tests` anomaly
above is a property of the tooling meeting an extreme small-N regime, not
a property of AMBA's or NVDA's data, and should not be read as evidence
either way about supply-chain transmission.
