# Canonical capture-input fingerprint (PROTOCOL v0.2).
#
# TWO problems are solved by one canonicalisation:
#
# 1. A DANGLING PRE_EVENT_PENDING. A crash between the PRE_EVENT_PENDING append
#    and the PRE_EVENT_CAPTURED append used to leave the event permanently
#    stuck: every rerun refused because a pre-event stage already existed, and
#    the pending record itself may never be deleted or rewritten. Resuming is
#    only safe if the rerun is provably capturing THE SAME THING, so
#    PRE_EVENT_PENDING now carries a fingerprint of its own inputs and a rerun
#    may proceed only on an exact match.
#
# 2. OPTION-INPUT BINDING. Validation approved one option-disposition artifact;
#    execution accepted whatever dict the caller passed the second time. The
#    digest below is stored in the ValidationReport and re-derived at execution,
#    so validating UNAVAILABLE_NO_VERIFIED_SOURCE and then executing with a
#    different disposition -- or a claimed OPRA artifact -- fails before the
#    first byte.
#
# The fingerprint is deliberately a HASH OF IDENTITIES, not of file contents:
# the panel CSV/marker SHA-256s are already computed by the adapter, so nothing
# here re-reads a file, and nothing here touches a provider, a clock, or a
# random source. Identical inputs always produce identical bytes.
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

CAPTURE_FINGERPRINT_VERSION = "1"

# Every field the fingerprint covers. Changing this tuple changes the contract:
# a pending record written under one version can never silently match a rerun
# computed under another, because the version is itself a covered field.
CAPTURE_FINGERPRINT_KEYS = (
    "capture_fingerprint_version",
    "event_id",
    "ticker",
    "anchor_session",
    "panel_csv_sha256",
    "panel_marker_sha256",
    "research_commit_sha",
    "methodology_version",
    "option_fields_digest",
)

CAPTURE_FINGERPRINT_KEY = "capture_fingerprint"


class CaptureFingerprintError(ValueError):
    """Fail-closed: a pending record's fingerprint is absent, malformed,
    internally inconsistent, or disagrees with the current inputs. Nothing is
    written and the pending record is never deleted or rewritten."""


def canonical_json(obj: Any) -> str:
    """Deterministic canonical form: sorted keys, no insignificant whitespace.

    Dict ordering, indentation and float repr must not change the digest, so
    two callers that supply the same option disposition always agree.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def canonical_option_fields(option_fields: Optional[dict[str, Any]]) -> str:
    """Canonical text for the COMPLETE option disposition artifact.

    Every key is covered -- status, reason, feed and every benchmark value --
    so a change to any one of them changes the digest. `None` (no dict at all)
    is canonicalised distinctly from `{}`.
    """
    if option_fields is None:
        return canonical_json(None)
    return canonical_json(dict(option_fields))


def option_fields_digest(option_fields: Optional[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_option_fields(option_fields).encode("utf-8")).hexdigest()


def _digest_of(fingerprint: dict[str, Any]) -> str:
    covered = {k: fingerprint.get(k) for k in CAPTURE_FINGERPRINT_KEYS}
    return hashlib.sha256(canonical_json(covered).encode("utf-8")).hexdigest()


def compute_capture_fingerprint(
    *,
    event_id: str,
    ticker: str,
    anchor_session: str,
    panel_csv_sha256: str,
    panel_marker_sha256: str,
    research_commit_sha: str,
    methodology_version: str,
    option_fields: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """The canonical fingerprint of one pre-event capture's inputs."""
    fp: dict[str, Any] = {
        "capture_fingerprint_version": CAPTURE_FINGERPRINT_VERSION,
        "event_id": event_id,
        "ticker": ticker,
        "anchor_session": anchor_session,
        "panel_csv_sha256": panel_csv_sha256,
        "panel_marker_sha256": panel_marker_sha256,
        "research_commit_sha": research_commit_sha,
        "methodology_version": methodology_version,
        "option_fields_digest": option_fields_digest(option_fields),
    }
    fp["capture_fingerprint_sha256"] = _digest_of(fp)
    return fp


def read_capture_fingerprint(record_fields: dict[str, Any]) -> dict[str, Any]:
    """Read a fingerprint off a stored PRE_EVENT_PENDING record, fail-closed.

    Absent, non-dict, missing a covered field, or carrying a self-digest that
    does not recompute -- all raise. A pending record whose fingerprint cannot
    be trusted is never resumable, and is never repaired in place.
    """
    if not isinstance(record_fields, dict):
        raise CaptureFingerprintError("pending record has no fields object")
    fp = record_fields.get(CAPTURE_FINGERPRINT_KEY)
    if not isinstance(fp, dict):
        raise CaptureFingerprintError(
            "PRE_EVENT_PENDING carries no capture fingerprint; it predates the v0.2 resume "
            "contract and cannot be resumed automatically. It is left exactly as written."
        )
    missing = [k for k in CAPTURE_FINGERPRINT_KEYS if k not in fp]
    if missing:
        raise CaptureFingerprintError(
            f"pending capture fingerprint is malformed (missing {sorted(missing)})"
        )
    stored = fp.get("capture_fingerprint_sha256")
    if not isinstance(stored, str) or not stored.strip():
        raise CaptureFingerprintError("pending capture fingerprint has no self-digest")
    if _digest_of(fp) != stored:
        raise CaptureFingerprintError(
            "pending capture fingerprint does not recompute to its own stored digest; "
            "failing closed rather than guessing which side is right"
        )
    return fp


def fingerprints_match(stored: dict[str, Any], current: dict[str, Any]) -> tuple[bool, list[str]]:
    """Exact field-for-field equality plus digest equality."""
    diffs = [k for k in CAPTURE_FINGERPRINT_KEYS if stored.get(k) != current.get(k)]
    if stored.get("capture_fingerprint_sha256") != current.get("capture_fingerprint_sha256"):
        diffs.append("capture_fingerprint_sha256")
    return (not diffs), diffs


__all__ = [
    "CAPTURE_FINGERPRINT_KEY", "CAPTURE_FINGERPRINT_KEYS", "CAPTURE_FINGERPRINT_VERSION",
    "CaptureFingerprintError", "canonical_json", "canonical_option_fields",
    "compute_capture_fingerprint", "fingerprints_match", "option_fields_digest",
    "read_capture_fingerprint",
]
