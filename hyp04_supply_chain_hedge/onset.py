#!/usr/bin/env python3
"""The reported lag quantity, as D7 requires it to be reported.

GST_HYP04_ANALYSIS_LOCK_v1.0 D7 (SIGNED 2026-08-20, IN FORCE):

    "`onset_horizon` is reported as the interval `[onset - 2, onset]`, never
     as a point estimate."

Until this module existed, `onset_horizon` was a bare `Optional[int]` on both
`LocalProjectionResult` and `Stage1Score`, and Stage 2 serialised that bare int
straight into a recommendation record. D8's *arithmetic* was brought into line
with the lock on 2026-09-04; D7's *reporting* requirement was not, because
there was no interval anywhere to report. This type is that interval.

=== WHAT THIS INTERVAL IS NOT ===

**It is not a confidence interval, and must never be reported as one.** D7 says
so in as many words (`is_a_confidence_interval: false`,
`must_never_be_reported_as: "a confidence interval"`). The widening corrects a
MECHANICAL BIAS: under an expanding-window target only 1/L of the averaging
window is affected at the true onset, so measured |t| thins as the lag deepens
and a noisy draw reports onset LATE. It cannot err early -- |t| at h < L was
0.71 on the draw where h = L measured 2.08. That is why the interval extends
backward only.

It therefore says **nothing about sampling uncertainty**, which at the df D2
establishes (approximately 5.7 at the gate threshold) is not small. Adding a
noise-based band requires a new dated amendment, not a change here.

**k is imprecise and deliberately frozen anyway.** k = 2 was measured on
synthetic fixtures at particular (L, W) combinations, and dilution grows with
L, so a constant k under-covers deep lags and over-covers shallow ones. Fixing
it before real data is what stops it being tuned later.

=== THE FLOOR, AND WHY IT DOES NOT REACH TENOR ===

The lock sets no floor on `onset - 2`. At onset = 1 the raw lower bound is -1,
which is not a horizon HORIZON_GRID can express, so a reported interval of
[-1, 1] would claim an observation that cannot exist.

`lower_floored` clamps the REPORTED bound into the grid. `lower_raw` is kept
and always reported beside it, exactly as `gate.py` keeps `icc_raw` beside
`icc_floored`.

**The floor stops here. It does not reach Stage 2's tenor.** D8 states the
quantity it sizes off literally, as `onset_horizon - 2`, so `_tenor_from_onset`
still computes on the raw value and its behaviour is unchanged at every onset.
The two diverge only at onset in {1, 2}, and that divergence is reported rather
than smoothed over: `diverges_from_tenor_basis` says when it is happening.

Decided 2026-09-04. Floor the report, keep the tenor arithmetic literal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .constants import ONSET_INTERVAL_K, ONSET_LOWER_FLOOR


class RefusedError(RuntimeError):
    """An onset interval was asked for that cannot be constructed honestly.

    RefusedError rather than `assert`: `python -O` strips asserts, and a
    guard that vanishes under an optimisation flag is not a guard.
    """


@dataclass(frozen=True)
class OnsetInterval:
    """`[lower, point]` -- the only shape D7 permits onset to be reported in.

    `point` is the detected onset horizon. `lower_raw` is `point - k` with no
    clamping, `lower_floored` is that value clamped into HORIZON_GRID. Render
    with `str()`, which uses the floored bound, or serialise with `as_dict()`,
    which carries both so a reader can see the clamp happen.
    """

    point: int
    lower_raw: int
    lower_floored: int
    k: int = ONSET_INTERVAL_K
    is_a_confidence_interval: bool = False
    covers: str = (
        "the one-sided mechanical late-detection bias only; NOT sampling "
        "uncertainty, which at D2's df (approx 5.7) is not small"
    )

    @classmethod
    def from_onset(cls, onset: Optional[int]) -> Optional["OnsetInterval"]:
        """Build the interval for a detected onset, or None if none was.

        None in, None out: no onset cleared significance, so there is no lag
        quantity to report. That is a different statement from an interval
        with a small lower bound, and Stage 2's R3 rule already depends on the
        difference.
        """
        if onset is None:
            return None
        if isinstance(onset, bool) or not isinstance(onset, int):
            raise RefusedError(
                f"onset horizon must be an int, got {type(onset).__name__}: "
                f"{onset!r}. A bool is not an int here."
            )
        if onset < ONSET_LOWER_FLOOR:
            raise RefusedError(
                f"onset horizon {onset} is below the smallest horizon the grid "
                f"can express ({ONSET_LOWER_FLOOR}). Detection cannot return a "
                "horizon that was never fitted."
            )
        lower_raw = onset - ONSET_INTERVAL_K
        return cls(
            point=onset,
            lower_raw=lower_raw,
            lower_floored=max(ONSET_LOWER_FLOOR, lower_raw),
        )

    def __post_init__(self) -> None:
        if self.lower_floored > self.point:
            raise RefusedError(
                f"lower bound {self.lower_floored} exceeds the point estimate "
                f"{self.point}; that is not an interval."
            )
        if self.lower_floored < self.lower_raw:
            raise RefusedError(
                f"floored bound {self.lower_floored} is below the raw bound "
                f"{self.lower_raw}; flooring may only raise it."
            )
        if self.is_a_confidence_interval:
            raise RefusedError(
                "D7 states this interval is not a confidence interval and "
                "must never be reported as one."
            )

    @property
    def diverges_from_tenor_basis(self) -> bool:
        """True when the reported bound and D8's tenor basis differ.

        Reachable only at onset in {1, 2}. Surfaced rather than hidden: a
        reader comparing the reported interval against a tenor should be able
        to see that the two were computed off different bounds, and why.
        """
        return self.lower_floored != self.lower_raw

    def __str__(self) -> str:
        return f"[{self.lower_floored}, {self.point}]"

    def as_dict(self) -> dict[str, Any]:
        return {
            "reported_interval": str(self),
            "point": self.point,
            "lower_raw_unfloored": self.lower_raw,
            "lower_floored_at_grid_minimum": self.lower_floored,
            "k": self.k,
            "widening": "one-sided",
            "is_a_confidence_interval": self.is_a_confidence_interval,
            "covers": self.covers,
            "tenor_basis_is_lower_raw_per_D8": self.lower_raw,
            "diverges_from_tenor_basis": self.diverges_from_tenor_basis,
        }
