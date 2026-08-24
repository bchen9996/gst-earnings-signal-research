# HYP-04: Supply-Chain Hedge-Lag Model -- Phase 0 (feasibility only).
#
# Placeholder linkage throughout -- POSITIONAL-SYNTHETIC pairing, not
# same-sector. Peers are the non-anchor tickers from AllTickers_Sectors.csv,
# assigned to anchors by list position; the sector column is not read for
# pairing. (Corrected 2026-08-18: the earlier "same-sector peers" wording
# described GST_Task2_PeerDivergence.py's approach, not this package's.)
#
# As of 2026-08-18 the automated teammate mapping is deprioritised in favour
# of hand curation (curated_linkage.py is the reader). Curation began
# 2026-08-22, so the map is no longer empty -- but it is nowhere near
# sufficient, and NOTHING in this package runs on curated data yet. For the
# registry's own position, READ the registry -- do not restate its value here;
# a value copied into a comment is a value that goes stale the next time it is
# corrected, which is exactly what happened to the wording this replaces. The placeholder described above is still what the
# analysis path uses. See
# Live Signal Engine/HYP04_LINKAGE_SOURCE_DECISION_2026-08-18.md.
#
# No real capital logic. No claim anywhere in this package that a hedging edge
# has been found.
#
# See Live Signal Engine/HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md -- the
# single authoritative build plan as of 2026-08-19. It is self-contained: v0.1
# and HYP04_PLAN_ROUND2_EDITS.md are superseded historical records, and the
# marker convention that used to be needed to reconcile them no longer applies.
#
# Importing this package performs no network calls and no filesystem writes.
from __future__ import annotations
