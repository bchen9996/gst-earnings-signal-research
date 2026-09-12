# HYP05_SAMPLE_SIZE_GATE_2026-09-11.md

**HYP-05** -- PROVISIONAL sample-size gate.

A provisional sample-size gate for HYP-05, modelled on HYP-04's own (Live Signal Engine/HYP04_PHASE0_FEASIBILITY_STATUS_2026-08-18.md section 5). The naive baseline is a real number; the operative floor is PROVISIONAL, borrowed from HYP-04's own measurement as a planning assumption, and requires its own dedicated remeasurement before it may govern anything -- see provisional_operative_floor.must_be_superseded_by.

Naive single-test baseline (k=1, never the operative floor): **126**.

Provisional operative floor (borrowed k range [6.05, 6.34], conservative end): **195 anchor events** (implied N range [193.3, 195.0]).

**Why borrowed, not measured:** HYP-05 has not fixed a horizon grid or model spec, so there is no design yet whose correlation structure a max-T permutation run could honestly measure. A measurement attempted against a guessed-at synthetic panel this session returned k_eff=47.4, exceeding the 20-horizon upper bound, and was discarded as methodologically premature rather than reported.

**Must be superseded by:** A fresh max-T permutation measurement (inference.max_t_permutation via local_projection_analysis, same mechanism HYP-04's Phase 0 used) against synthetic fixtures shaped like HYP-05's OWN locked design, once that design exists -- written as a new dated version of this finding, exactly mirroring how HYP-04's own provisional '190-240' was superseded by its measured 193.

**Does not violate the power statement:** Both k values entering this derivation (HYP-04's measured 6.05-6.34) came from HYP-04's OWN Phase 0 SYNTHETIC-fixture diagnostic with known injected ground truth, not from any observed project result or real collected data. No HYP-05 data, real or synthetic-and-specific-to-HYP-05, entered this calculation.
