# HYP-04: Supply-Chain Hedge-Lag Model -- Phase 0 (feasibility only).
#
# Placeholder linkage throughout -- POSITIONAL-SYNTHETIC pairing, not
# same-sector. Peers are the non-anchor tickers from AllTickers_Sectors.csv,
# assigned to anchors by list position; the sector column is not read for
# pairing. (Corrected 2026-08-18: the earlier "same-sector peers" wording
# described GST_Task2_PeerDivergence.py's approach, not this package's.)
#
# The real supply-chain linkage map does not exist. As of 2026-08-18 the
# automated teammate mapping is deprioritised in favour of hand curation; an
# ingestion path exists in curated_linkage.py but NO curated data does. See
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
