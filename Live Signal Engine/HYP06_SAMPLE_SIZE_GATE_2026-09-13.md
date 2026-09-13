# HYP06_SAMPLE_SIZE_GATE_2026-09-13.md

**HYP-06** -- PROVISIONAL sample-size gate, reusing HYP-05's own provisional floor.

A provisional sample-size gate for HYP-06, reusing HYP-05's own provisional floor (same k range, same formula) rather than re-deriving it -- see module docstring for why this stays provisional despite HYP-06's design being fully fixed.

Naive single-test baseline (k=1, never the operative floor): **126**.

Provisional operative floor (borrowed k range [6.05, 6.34], conservative end): **195 (peer, anchor_event) pairs** (implied N range [193.3, 195.0]).

**Real universe size as of 2026-09-13:** **778** qualifying pairs (`Live Signal Engine\HYP05_PEER_UNIVERSE_SCALED_2026-09-13.json`). **Clears the provisional floor: True** (778 vs 195).

**Why still provisional:** HYP-06's design IS fully fixed (reused from HYP-05's own locked target/outcome/clustering), unlike HYP-05 at its own registration -- so a real measurement is possible in principle. It is not done in this pass: building and validating a synthetic-fixture generator shaped like the real 776-cluster design is real, separate work, and is not needed to clear a floor the real universe already clears several times over.

**Must be superseded by:** A fresh max-T permutation measurement against synthetic fixtures shaped like HYP-06's own 776-cluster design, written as a new dated version of this finding -- same mechanism HYP-04's Phase 0 used, same standard HYP-05's own gate document left unmet.
