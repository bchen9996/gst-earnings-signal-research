# Constants mirrored verbatim from existing, unchanged sources -- see
# SPEC_v0.1_DRAFT.md "Reused components" table. These are copied rather than
# imported because GST_Phase2_DailyPanel.py is a large module with unrelated
# top-level side effects. A copy carries a provenance comment; it is never
# silently redefined.
#
# Provenance correction (2026-08-06): this header previously also justified
# the copy by saying the Event Dossier Protocol was "on the sibling
# phase2-event-dossiers worktree/branch ... literally unreachable at runtime
# from a different git worktree". That is no longer true -- PR #2 merged the
# protocol into main, and main is merged into this branch, so the canonical
# Event_Dossier_Protocol/locked_universe_v0.1.json sits in this same tree.
# The copy below is now guarded rather than merely asserted:
# test_market_response_canonical_drift.py compares it element-by-element
# against that canonical JSON and fails on any divergence.
from __future__ import annotations

# Mirrored verbatim from GST_Phase2_DailyPanel.py:229-233 (branch
# phase2-wikipedia-reliability @ b400af239d89b313f7705e941ddfa7b4c2beb76b).
# UNCHANGED by this module. No code path in this package may add, remove, or
# reorder this list.
LOCKED_24_TICKER_UNIVERSE: tuple[str, ...] = (
    "AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "CTSH", "DELL", "DVN", "GME",
    "GOOGL", "GPN", "INTC", "LDOS", "MSFT", "NCLH", "NKE", "QCOM", "SBUX", "STZ",
    "SYK", "TSLA", "TTWO", "UAL",
)

# Mirrored from GST_Live_Signal_Engine.py's compute_latest_zscore() constants.
# UNCHANGED. Reused only as the elevation threshold for gst_persistence_v0.1
# (SPEC section 4.1); never used to alter the core GST z-score formula.
GST_ROLLING_WINDOW = 12
GST_MIN_PERIODS = 8
GST_STD_EPSILON_FLOOR = 1.0
GST_Z_THRESHOLD = 2.0

# Six-field contract, mirrored verbatim from GST_Phase2_DailyPanel.py header
# (lines 4-7) / process_ticker() six_fields list. UNCHANGED. This module's own
# schema (SPEC sections 4-8) is additive and distinct -- it does not redefine
# or overload these six names.
SIX_FIELD_CONTRACT: tuple[str, ...] = (
    "gst_zscore", "wiki_zscore", "implied_volatility", "realized_vol", "price", "volume",
)


def is_locked_universe_member(ticker: str) -> bool:
    return ticker in LOCKED_24_TICKER_UNIVERSE
