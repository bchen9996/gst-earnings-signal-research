# Protocol boundary: the single, explicit translation point between this
# package's vocabulary and the Event Dossier Protocol's vocabulary.
#
# WHY THIS MODULE EXISTS
#
# Both sides model "which market session did the release land in", and both
# call the field release_market_session -- but they use different value
# domains:
#
#     Market Response (gst_market_response.identity.VALID_RELEASE_SESSIONS)
#         BMO | INTRADAY | AMC
#
#     Event Dossier Protocol (validate_event_dossier.RELEASE_MARKET_SESSIONS)
#         before_open | during_session | after_close
#
# They correspond one-to-one, but the strings differ, so a market-response
# record written straight into the protocol's events.csv is rejected by the
# validator's enum gate. Rather than renaming or widening either enum -- both
# are load-bearing and locked -- the conversion lives here, once, as a pure
# total function with a fail-closed error.
#
# RULES
#
#   * Neither existing enum is renamed or expanded. Each side keeps its own
#     vocabulary internally; only values crossing the boundary are converted.
#   * The mapping is by declared session value ONLY. This boundary never
#     infers a session from a timestamp -- inferring "after_close" from a
#     20:05 UTC release would silently manufacture a protocol field from a
#     clock reading, which is exactly the kind of fabrication the registry's
#     human-verification requirement exists to prevent.
#   * Unknown, blank, malformed, or unsupported values raise
#     SessionVocabularyError. There is no default, no passthrough, and no
#     "best guess" branch.
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# Repository root as seen from this file: gst_market_response/ -> repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_ROOT = _REPO_ROOT / "Event_Dossier_Protocol"

LOCKED_UNIVERSE_JSON = PROTOCOL_ROOT / "locked_universe_v0.1.json"
VALIDATOR_DIR = PROTOCOL_ROOT / "validator"
LAYER_B_SCHEMA_CSV = (
    PROTOCOL_ROOT / "B_Market_Response_Addendum" / "schemas" / "market_response_addendum.csv"
)


class ProtocolBoundaryError(ValueError):
    """Base class for every fail-closed condition at this boundary."""


class SessionVocabularyError(ProtocolBoundaryError):
    """Raised when a release-market-session value cannot be translated.

    Deliberately specific: the caller must route the event to
    ABSTAIN_DATA_QUALITY (or refuse to emit) rather than substituting a
    plausible session.
    """


# The one mapping. Keys are exactly gst_market_response.identity's
# VALID_RELEASE_SESSIONS; values are exactly the protocol validator's
# RELEASE_MARKET_SESSIONS. Both sides are asserted against their canonical
# definitions by test_market_response_canonical_drift.py.
MARKET_RESPONSE_TO_PROTOCOL_SESSION: dict[str, str] = {
    "BMO": "before_open",
    "INTRADAY": "during_session",
    "AMC": "after_close",
}

PROTOCOL_TO_MARKET_RESPONSE_SESSION: dict[str, str] = {
    protocol: mr for mr, protocol in MARKET_RESPONSE_TO_PROTOCOL_SESSION.items()
}


def to_protocol_release_session(market_response_session: Optional[str]) -> str:
    """BMO/INTRADAY/AMC -> before_open/during_session/after_close.

    Raises SessionVocabularyError for None, blank, whitespace-only,
    wrong-typed, wrong-cased, or unrecognised input. Matching is exact and
    case-sensitive: 'amc' is not accepted, because a lowercase value did not
    come from VALID_RELEASE_SESSIONS and its provenance is therefore unknown.
    """
    if market_response_session is None:
        raise SessionVocabularyError(
            "release_market_session is None -- cannot translate to the Event Dossier "
            "Protocol vocabulary; the event must not be emitted with a guessed session"
        )
    if not isinstance(market_response_session, str):
        raise SessionVocabularyError(
            f"release_market_session must be a str, got {type(market_response_session).__name__}"
        )
    if market_response_session.strip() == "":
        raise SessionVocabularyError(
            "release_market_session is blank -- cannot translate to the Event Dossier "
            "Protocol vocabulary"
        )
    try:
        return MARKET_RESPONSE_TO_PROTOCOL_SESSION[market_response_session]
    except KeyError:
        raise SessionVocabularyError(
            f"release_market_session {market_response_session!r} is not one of "
            f"{tuple(MARKET_RESPONSE_TO_PROTOCOL_SESSION)} -- no translation exists and none "
            f"will be inferred"
        ) from None


def to_market_response_release_session(protocol_session: Optional[str]) -> str:
    """The exact inverse, for reading a protocol events.csv row back in."""
    if protocol_session is None or not isinstance(protocol_session, str) or protocol_session.strip() == "":
        raise SessionVocabularyError(
            f"protocol release_market_session {protocol_session!r} is missing or malformed"
        )
    try:
        return PROTOCOL_TO_MARKET_RESPONSE_SESSION[protocol_session]
    except KeyError:
        raise SessionVocabularyError(
            f"protocol release_market_session {protocol_session!r} is not one of "
            f"{tuple(PROTOCOL_TO_MARKET_RESPONSE_SESSION)}"
        ) from None


# --- canonical-definition accessors ----------------------------------------
#
# Used by the drift guards so they compare against executable/authoritative
# definitions rather than prose documentation.


def load_canonical_locked_universe() -> tuple[str, ...]:
    """The protocol's locked_universe_v0.1.json ticker list, in file order."""
    data = json.loads(LOCKED_UNIVERSE_JSON.read_text(encoding="utf-8"))
    return tuple(data["tickers"])


def load_validator_module():
    """Import the Event Dossier validator as a module.

    The validator is a plain script in a non-package directory, so it is
    loaded by path rather than imported normally. It performs no network or
    operational access at import time (asserted by the protocol's own
    test_validator_never_touches_network_or_operational_paths).
    """
    import importlib.util
    import sys

    path = VALIDATOR_DIR / "validate_event_dossier.py"
    spec = importlib.util.spec_from_file_location("_gst_validate_event_dossier", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ProtocolBoundaryError(f"cannot load the Event Dossier validator from {path}")
    module = importlib.util.module_from_spec(spec)
    # Registering in sys.modules keeps dataclasses/typing resolution happy and
    # makes repeat loads cheap within a single test process.
    sys.modules.setdefault("_gst_validate_event_dossier", module)
    spec.loader.exec_module(module)
    return module


def load_layer_b_schema_columns() -> tuple[str, ...]:
    """The Layer B addendum column order, read from the protocol's own schema
    CSV header. Never hardcoded here -- the schema file is authoritative."""
    header = LAYER_B_SCHEMA_CSV.read_text(encoding="utf-8").splitlines()[0]
    return tuple(c.strip() for c in header.split(","))
