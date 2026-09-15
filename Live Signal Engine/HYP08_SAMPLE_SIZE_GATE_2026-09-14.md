# HYP08_SAMPLE_SIZE_GATE_2026-09-14.md

**HYP-08** -- sample-size gate (k EXACT, not provisional -- see below).

HYP-08's sample-size gate. Unlike HYP-05/06/07's borrowed, explicitly provisional k range, this floor is exact for the reason given in operative_floor.why_not_provisional -- see the module's own docstring for the full derivation.

Naive single-test baseline (k=1, never the operative floor): **126**.

Operative floor (k=2, exact): **152 (peer, anchor-event) pairs**.

**Why k is exact, not provisional:** Every prior hypothesis's k required measuring how adjacent horizons in a 20-point grid correlate under that specific target's geometry -- a real empirical question with its own uncertainty, which is why HYP-05/06/07 all borrowed a range rather than a point value. HYP-08's family size is fixed by its OWN design (exactly 2 tests, no horizon search), so k=2 is exact the moment this document is written, not an estimate awaiting its own measurement.

**Does not violate the power statement:** d=0.5, alpha=0.05, and power=0.80 are the same hypothetical, externally chosen inputs every prior gate in this project used -- not derived from any observed project result, real or synthetic-and-specific-to-HYP-08.
