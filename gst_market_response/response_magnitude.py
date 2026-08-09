# Canonical persistence of the absolute market-response fields.
#
# THIS IMPLEMENTS AN EXISTING SPECIFICATION. It introduces no formula and no
# analytical decision. SPEC v0.1 already requires:
#
#   abs_overnight_gap, abs_open_to_30m, abs_thirty_min_to_close,
#   abs_open_to_close, abs_close_T1_to_close_T2, abs_close_T1_to_close_T3
#     -- "abs() of the corresponding signed return, stored alongside it
#        (never replacing it)"
#
# and field dictionary v0.1 repeats it. The merged HYP-01 analysis lock names
# abs_overnight_gap as its primary outcome and recorded, truthfully, that the
# capture path did not yet emit it. This module closes exactly that gap.
#
# WHAT IS AND IS NOT CHANGED
#
#   * The signed values are untouched. They remain present, byte-for-value, and
#     are never replaced -- the abs_* fields are stored ALONGSIDE them.
#   * D1_REQUIRED_FIELDS and D3_REQUIRED_FIELDS are NOT extended. The absolute
#     fields are canonical derived OUTPUTS, not new lifecycle requirements; a
#     record is neither made complete nor made incomplete by their presence.
#   * No signed-return formula is recomputed here. Only derivations.abs_or_none
#     is applied, so there is exactly one definition of abs() in the package.
#   * No imputation, winsorization, clipping, rounding or outlier removal. A
#     missing signed value yields None -- never 0.0 -- and a legitimate 0.0
#     yields 0.0.
#
# CALLERS DO NOT GET TO CHOOSE THESE VALUES. The pipeline derives them. A
# caller-supplied abs_* value is accepted only when it is exactly the canonical
# value; anything else raises AbsoluteFieldConflictError BEFORE the first
# event-log or marker byte is written.
from __future__ import annotations

from typing import Any, Optional

from .derivations import abs_or_none

# Signed field -> its canonical absolute counterpart. These pairs are fixed by
# SPEC v0.1; this mapping is the single place they are written down.
D1_ABS_FIELD_MAP: dict[str, str] = {
    "overnight_gap": "abs_overnight_gap",
    "open_to_30m": "abs_open_to_30m",
    "thirty_min_to_close": "abs_thirty_min_to_close",
    "open_to_close": "abs_open_to_close",
}

D3_ABS_FIELD_MAP: dict[str, str] = {
    "close_T1_to_close_T2": "abs_close_T1_to_close_T2",
    "close_T1_to_close_T3": "abs_close_T1_to_close_T3",
}

ALL_ABS_FIELD_MAP: dict[str, str] = {**D1_ABS_FIELD_MAP, **D3_ABS_FIELD_MAP}

D1_ABS_FIELDS: tuple[str, ...] = tuple(D1_ABS_FIELD_MAP.values())
D3_ABS_FIELDS: tuple[str, ...] = tuple(D3_ABS_FIELD_MAP.values())
ALL_ABS_FIELDS: tuple[str, ...] = D1_ABS_FIELDS + D3_ABS_FIELDS


class AbsoluteFieldConflictError(ValueError):
    """Fail-closed: a caller supplied an abs_* value that is not the canonical
    abs() of its signed counterpart.

    Raised BEFORE any state record or marker byte is written, so a disagreeing
    caller can never leave a partially-written or self-inconsistent record. The
    fix is to correct the caller, never to overwrite the signed value.
    """


def derive_absolute_fields(fields: dict[str, Any],
                           field_map: dict[str, str]) -> dict[str, Optional[float]]:
    """The canonical abs_* values for `field_map`, derived from the signed
    values actually present.

    A signed key that is absent from `fields` produces no abs_* key at all --
    absence is preserved as absence, not manufactured as None or 0.0. A signed
    key present with value None produces None.
    """
    derived: dict[str, Optional[float]] = {}
    for signed_key, abs_key in field_map.items():
        if signed_key not in fields:
            continue
        derived[abs_key] = abs_or_none(fields[signed_key])
    return derived


def _conflicts(supplied: Any, canonical: Optional[float]) -> bool:
    """Does a caller-supplied value disagree with the canonical one?

    None and a number are different. Two numbers agree only on exact equality
    -- no tolerance, because the canonical value is a pure abs() of a value the
    caller already has, so any difference is a real disagreement rather than
    floating-point noise.
    """
    if supplied is None or canonical is None:
        return supplied is not canonical
    if isinstance(supplied, bool) or not isinstance(supplied, (int, float)):
        return True
    return float(supplied) != float(canonical)


def apply_absolute_fields(fields: dict[str, Any],
                          field_map: dict[str, str]) -> dict[str, Any]:
    """Return `fields` plus its canonical abs_* counterparts.

    The input dict is not mutated. Signed values are copied through unchanged.
    A caller-supplied abs_* value is validated against the canonical value and
    then replaced by it; a disagreement raises AbsoluteFieldConflictError.
    """
    canonical = derive_absolute_fields(fields, field_map)
    conflicts = []
    for abs_key, canonical_value in canonical.items():
        if abs_key in fields and _conflicts(fields[abs_key], canonical_value):
            signed_key = next(s for s, a in field_map.items() if a == abs_key)
            conflicts.append(
                f"{abs_key}={fields[abs_key]!r} does not equal abs({signed_key})="
                f"{canonical_value!r}"
            )
    if conflicts:
        raise AbsoluteFieldConflictError(
            "caller-supplied absolute response field(s) disagree with the canonical "
            "abs() of their signed counterparts, so nothing was written: "
            + "; ".join(sorted(conflicts))
            + ". The absolute fields are derived by the pipeline; correct the caller "
              "rather than the stored signed value."
        )
    # A caller-supplied abs_* key whose signed counterpart is absent is left
    # exactly as given -- there is nothing to derive it from, and silently
    # dropping or zeroing it would be its own kind of fabrication.
    return {**fields, **canonical}


def absolute_fields_present(fields: dict[str, Any],
                            field_map: dict[str, str]) -> bool:
    """True when every abs_* counterpart of a present signed field exists."""
    return all(abs_key in fields
               for signed_key, abs_key in field_map.items() if signed_key in fields)


def response_magnitude_block(fields: dict[str, Any],
                             field_map: dict[str, str]) -> dict[str, Optional[float]]:
    """The abs_* subset of a stored record, for echoing into a stage marker."""
    return {abs_key: fields.get(abs_key)
            for abs_key in field_map.values() if abs_key in fields}


__all__ = [
    "ALL_ABS_FIELDS", "ALL_ABS_FIELD_MAP", "AbsoluteFieldConflictError",
    "D1_ABS_FIELDS", "D1_ABS_FIELD_MAP", "D3_ABS_FIELDS", "D3_ABS_FIELD_MAP",
    "absolute_fields_present", "apply_absolute_fields", "derive_absolute_fields",
    "response_magnitude_block",
]
