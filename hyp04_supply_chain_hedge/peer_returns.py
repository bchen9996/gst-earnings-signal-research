#!/usr/bin/env python3
"""Peer-side return-series ingestion -- HYP-04.

This addresses the SECOND of the three capture gaps registry v1.2 names in
HYP-04's `status_basis`:

    "(2) There is no production capture path for PEER-side price or
     volatility series; no module ingests peer returns for a registered
     event."

It builds one. What it deliberately does NOT do is declare that gap closed --
that is a statement in the registry, the registry is append-only, and only a
governed version bump by the repo owner can make it. A module existing and a
registry acknowledging it are two different facts, and this project has been
bitten before by prose that asserted a state the code had drifted away from.

=== IT NEVER TOUCHES A PROVIDER ===

Same discipline as `gst_market_response.pre_event_capture`, and for the same
reason stated there: no network client, no credential read, no price lookup.
Closing prices are handed in -- from a CSV the operator produced, or from a
future fetcher that is a SEPARATE module -- and this one validates them.

That split is what keeps a live call from ever happening implicitly. A fetcher
can feed this module; this module cannot summon a fetcher.

=== IT NEVER IMPORTS THE EXCHANGE CALENDAR ===

`gst_market_response.exchange_calendar` is the authoritative XNYS session
source, and it imports `exchange_calendars`, which `requirements-hyp04.txt`
deliberately does NOT install -- HYP-04's CI job is scoped to its own
dependency file. Importing it here would break that job at import time.

So the session index is INJECTED: callers pass the ordered sessions they want
returns aligned to. A caller that has the real calendar available (anything
running under `requirements.txt`) can pass its sessions in and get authoritative
alignment; HYP-04's own tests pass an explicit list. The module gets calendar
correctness without taking a calendar dependency.

`test_hyp04_supply_chain_hedge_peer_returns.py` asserts that importing this
module leaks no heavy dependency, so the property is enforced rather than
merely intended.

=== COVERAGE IS DERIVED, NEVER ASSERTED ===

This is the same safety property `linkage_resolution.LinkageProvenance` applies
to `uses_placeholder_linkage`, applied to the other end of the pair.

`pair_eligibility` condition P5 asks whether a peer has usable return history
around an event, and denies when the answer is unknown. Today the answer is
supplied by the caller. A caller that can simply assert `True` makes P5 an
honour system in exactly the way an assertable `uses_placeholder_linkage` would
have made C5 one.

So nothing here accepts an availability flag. `coverage_for_event()` computes
it from the actual series -- whether the reference window and the full horizon
grid are populated with finite returns -- and `peer_history_map()` emits P5's
input from that computation.
"""
from __future__ import annotations

import csv
import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .constants import HORIZON_GRID, REFERENCE_WINDOW_TRADING_DAYS

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CLOSES_HEADERS: tuple[str, ...] = ("ticker", "session_date", "close")

# The blank schema an operator fills in, mirroring the linkage map's template.
# Headers only, always: a stray data row in a template is how half-finished
# content ships by accident, and the suite asserts it stays empty.
#
# One row per (ticker, session). `close` must be finite and strictly positive --
# a non-positive price makes log(p_t / p_{t-1}) undefined, and substituting
# anything would manufacture a return no trade produced. Dates must be sessions
# in the index the caller supplies; rows off that calendar are reported, not
# dropped. Gaps are never filled.
#
# Deliberately provider-agnostic. Which vendor the closes come from is an open
# decision, and it carries the same point-in-time exposure the linkage as-of
# dates do -- a vendor's "history" is not automatically survivorship-free or
# free of retroactive adjustment. This schema does not depend on that choice.
TEMPLATE_HEADERS_CSV = (
    Path(__file__).resolve().parent.parent / "Live Signal Engine"
    / "HYP04_Peer_Closes_TEMPLATE_headers.csv")

SOURCE_OPERATOR_CSV = "operator_csv"
SOURCE_IN_MEMORY = "in_memory"


class PeerReturnsError(ValueError):
    """Raised only for programming errors -- bad data is REPORTED, not raised.

    Row-level defects become `RowReject` entries so a partly-broken file yields
    a usable diagnosis instead of dying on its first bad line. Reserve the
    exception for callers misusing the API (e.g. an unsorted session index).
    """


@dataclass(frozen=True)
class RowReject:
    """One rejected input row, with enough detail to fix the source file."""

    row_number: int
    ticker: str
    field: str
    message: str


@dataclass(frozen=True)
class PriceObservation:
    ticker: str
    session_date: date
    close: float


# --------------------------------------------------------------------------
# parsing / validation
# --------------------------------------------------------------------------

def _parse_date(value: str) -> Optional[date]:
    if not DATE_RE.match(value or ""):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_close(value: str) -> Optional[float]:
    """A close must be finite and strictly positive.

    Zero and negatives are rejected rather than clamped: a log return needs
    log(p_t / p_{t-1}), and a non-positive price makes that undefined. Silently
    substituting anything here would manufacture a return that no trade
    produced.
    """
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or x <= 0.0:
        return None
    return x


def parse_close_rows(rows: Iterable[Sequence[str]],
                     *, header: Optional[Sequence[str]] = None,
                     ) -> tuple[list[PriceObservation], list[RowReject]]:
    """Validate raw close rows into observations plus per-row rejects.

    Duplicate (ticker, session_date) pairs are rejected -- the SECOND and any
    later occurrence. Two different closes for one ticker-session is a source
    defect, and picking one silently would hide it.
    """
    obs: list[PriceObservation] = []
    rejects: list[RowReject] = []
    seen: set[tuple[str, date]] = set()

    if header is not None:
        got = tuple(str(h).strip().lower() for h in header)
        if got != CLOSES_HEADERS:
            rejects.append(RowReject(
                row_number=1, ticker="", field="header",
                message=f"expected headers {CLOSES_HEADERS}, got {got}"))
            return [], rejects

    for i, raw in enumerate(rows, start=2 if header is not None else 1):
        if raw is None or len(list(raw)) < 3:
            rejects.append(RowReject(i, "", "row", "expected 3 columns"))
            continue
        ticker = str(raw[0]).strip().upper()
        d = _parse_date(str(raw[1]).strip())
        c = _parse_close(str(raw[2]).strip())

        if not ticker:
            rejects.append(RowReject(i, ticker, "ticker", "blank ticker"))
            continue
        if d is None:
            rejects.append(RowReject(i, ticker, "session_date",
                                     f"not a YYYY-MM-DD date: {raw[1]!r}"))
            continue
        if c is None:
            rejects.append(RowReject(i, ticker, "close",
                                     f"not a finite positive number: {raw[2]!r}"))
            continue
        key = (ticker, d)
        if key in seen:
            rejects.append(RowReject(i, ticker, "session_date",
                                     f"duplicate observation for {d.isoformat()}"))
            continue
        seen.add(key)
        obs.append(PriceObservation(ticker, d, c))

    return obs, rejects


def load_peer_closes(path: Path) -> tuple[list[PriceObservation], list[RowReject], str]:
    """Read an operator-produced closes CSV. Returns (obs, rejects, sha256)."""
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8-sig")
    reader = csv.reader(text.splitlines())
    try:
        header = next(reader)
    except StopIteration:
        return [], [RowReject(1, "", "header", "file is empty")], sha
    obs, rejects = parse_close_rows(list(reader), header=header)
    return obs, rejects, sha


# --------------------------------------------------------------------------
# alignment
# --------------------------------------------------------------------------

def normalize_sessions(sessions: Sequence[date]) -> tuple[date, ...]:
    """Validate an injected session index: strictly increasing, no duplicates.

    Raises rather than reports. An unsorted or duplicated session index is a
    caller bug, not source data, and every day index downstream would be
    meaningless -- so it must not be survivable.
    """
    out = tuple(sessions)
    for a, b in zip(out, out[1:]):
        if b <= a:
            raise PeerReturnsError(
                f"session index must be strictly increasing; {a} then {b}")
    return out


@dataclass(frozen=True)
class PeerReturnSeries:
    """One peer's log returns aligned to a shared session index.

    `log_returns[i]` is the return REALIZED on `sessions[i]`, i.e.
    log(close[i] / close[i-1]). Index 0 is always None: the first session has
    no prior close inside the index, and inventing one would fabricate a
    return. `None` means "not computable here", never zero.
    """

    ticker: str
    sessions: tuple[date, ...]
    log_returns: tuple[Optional[float], ...]
    closes_seen: int = 0
    sessions_covered: int = 0
    off_calendar_dates: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        if len(self.sessions) != len(self.log_returns):
            raise PeerReturnsError("sessions and log_returns length mismatch")

    @property
    def n_finite(self) -> int:
        return sum(1 for r in self.log_returns if r is not None)

    def window(self, start: int, stop: int) -> tuple[Optional[float], ...]:
        """Half-open [start, stop) with out-of-range treated as missing.

        Clipping silently would make a truncated window look complete, which
        is precisely the check `coverage_for_event` exists to make.
        """
        if start < 0 or stop > len(self.log_returns) or start >= stop:
            return ()
        return self.log_returns[start:stop]


def build_series(observations: Sequence[PriceObservation],
                 *, ticker: str,
                 sessions: Sequence[date]) -> PeerReturnSeries:
    """Align one ticker's closes to `sessions` and difference them into returns.

    Closes on dates NOT in the session index are recorded in
    `off_calendar_dates` and excluded. That is usually a source defect -- a
    weekend or holiday row -- and it is surfaced rather than dropped, because a
    file full of off-calendar dates means the operator built it against a
    different calendar and every downstream index would be shifted.

    A gap in the index is NEVER filled. If a session has no close, its return
    is None, and so is the following session's -- a return spanning a gap is
    not a one-session return, and treating it as one would inflate realized
    variance exactly where data is worst.
    """
    idx = normalize_sessions(sessions)
    pos = {d: i for i, d in enumerate(idx)}

    closes: list[Optional[float]] = [None] * len(idx)
    off: list[date] = []
    seen = 0
    tkr = ticker.strip().upper()

    for o in observations:
        if o.ticker.strip().upper() != tkr:
            continue
        seen += 1
        i = pos.get(o.session_date)
        if i is None:
            off.append(o.session_date)
            continue
        closes[i] = o.close

    rets: list[Optional[float]] = [None] * len(idx)
    for i in range(1, len(idx)):
        prev, cur = closes[i - 1], closes[i]
        if prev is None or cur is None:
            continue
        rets[i] = math.log(cur / prev)

    return PeerReturnSeries(
        ticker=tkr,
        sessions=idx,
        log_returns=tuple(rets),
        closes_seen=seen,
        sessions_covered=sum(1 for c in closes if c is not None),
        off_calendar_dates=tuple(sorted(set(off))),
    )


# --------------------------------------------------------------------------
# coverage -- the DERIVED input to pair_eligibility P5
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Coverage:
    """Whether one peer can actually support the target at one anchor event.

    Mirrors `target.raw_log_ratio_target`'s windows exactly, because a pair
    counted eligible whose target then evaluates to NaN is worse than one
    denied up front: it inflates the eligible-pair count with observations
    that silently vanish later.
    """

    peer: str
    event_id: str
    anchor_day: int
    reference_needed: int
    reference_have: int
    horizon_needed: int
    horizon_have: int
    reasons: tuple[str, ...] = ()

    @property
    def sufficient(self) -> bool:
        return not self.reasons

    def as_dict(self) -> dict[str, Any]:
        return {
            "peer": self.peer, "event_id": self.event_id,
            "anchor_day": self.anchor_day,
            "reference_needed": self.reference_needed,
            "reference_have": self.reference_have,
            "horizon_needed": self.horizon_needed,
            "horizon_have": self.horizon_have,
            "sufficient": self.sufficient,
            "reasons": list(self.reasons),
        }


def coverage_for_event(series: PeerReturnSeries, *, event_id: str,
                       anchor_day: int,
                       max_horizon: Optional[int] = None,
                       reference_window: int = REFERENCE_WINDOW_TRADING_DAYS,
                       ) -> Coverage:
    """Derive P5's answer for one (peer, event) from the series itself.

    Windows are taken to match `target.raw_log_ratio_target`:
      reference = the `reference_window` sessions ending AT anchor_day
      post      = [anchor_day + 1, anchor_day + max_horizon]

    Every return in BOTH windows must be finite. A partially-populated
    reference window is not a shorter reference window -- RVar_ref is a mean
    over a fixed count, and averaging over fewer days silently changes the
    estimator.
    """
    h = int(max_horizon if max_horizon is not None else max(HORIZON_GRID))
    reasons: list[str] = []
    n = len(series.log_returns)

    ref_start = anchor_day - reference_window + 1
    ref = series.window(ref_start, anchor_day + 1)
    ref_have = sum(1 for r in ref if r is not None)
    if ref_start < 0:
        reasons.append(
            f"reference window starts before the session index "
            f"(needs day {ref_start}, index starts at 0)")
    elif ref_have < reference_window:
        reasons.append(
            f"reference window has {ref_have}/{reference_window} finite returns")

    post = series.window(anchor_day + 1, anchor_day + 1 + h)
    post_have = sum(1 for r in post if r is not None)
    if anchor_day + h >= n:
        reasons.append(
            f"horizon window runs past the session index "
            f"(needs day {anchor_day + h}, index ends at {n - 1})")
    elif post_have < h:
        reasons.append(f"horizon window has {post_have}/{h} finite returns")

    return Coverage(peer=series.ticker, event_id=str(event_id),
                    anchor_day=int(anchor_day),
                    reference_needed=reference_window, reference_have=ref_have,
                    horizon_needed=h, horizon_have=post_have,
                    reasons=tuple(reasons))


def peer_history_map(series_by_peer: dict[str, PeerReturnSeries],
                     events: Sequence[dict[str, Any]],
                     *, max_horizon: Optional[int] = None,
                     reference_window: int = REFERENCE_WINDOW_TRADING_DAYS,
                     ) -> dict[str, bool]:
    """Build the per-peer availability dict P5 currently consumes.

    `events` entries need `event_id`, `anchor_day`, and `peers`.

    THE PER-PEER UNIT IS LOSSY AND THIS RESOLVES IT CONSERVATIVELY. Coverage is
    really a property of a (peer, event) PAIR -- a peer listed since 2015 has
    coverage for a 2020 event and none for a 2010 one. `resolve_from_curated_map`
    takes one bool per peer, so a peer is marked available only if it covers
    EVERY event it appears in. That undercounts, which is the safe direction and
    the one the rest of this package already takes on every unknown.

    Use `coverage_for_event` directly for the precise per-pair answer.
    """
    needed: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        for p in ev.get("peers", ()) or ():
            needed.setdefault(str(p).strip().upper(), []).append(ev)

    out: dict[str, bool] = {}
    for peer, evs in needed.items():
        s = series_by_peer.get(peer)
        if s is None:
            out[peer] = False          # no series is not "assume available"
            continue
        out[peer] = all(
            coverage_for_event(
                s, event_id=str(ev.get("event_id", "")),
                anchor_day=int(ev.get("anchor_day", -1)),
                max_horizon=max_horizon,
                reference_window=reference_window).sufficient
            for ev in evs)
    return out


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PeerReturnsProvenance:
    """Where the peer series came from, for the same reason C5 needs one.

    `usable` is derived, not settable: a path that read nothing, or read only
    rejects, has not produced a capture and must not read as though it had.
    """

    source: str
    source_path: Optional[str] = None
    source_sha256: Optional[str] = None
    rows_seen: int = 0
    rows_rejected: int = 0
    peers_loaded: int = 0
    sessions_in_index: int = 0
    rejects: tuple[RowReject, ...] = field(default_factory=tuple)

    @property
    def usable(self) -> bool:
        return self.peers_loaded > 0 and self.sessions_in_index > 0

    @property
    def loads_clean(self) -> bool:
        return self.rows_rejected == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "rows_seen": self.rows_seen,
            "rows_rejected": self.rows_rejected,
            "peers_loaded": self.peers_loaded,
            "sessions_in_index": self.sessions_in_index,
            "usable": self.usable,
            "loads_clean": self.loads_clean,
        }


@dataclass(frozen=True)
class PeerPanel:
    """Validated peer series plus the provenance of the read that produced them."""

    series: dict[str, PeerReturnSeries] = field(default_factory=dict)
    provenance: PeerReturnsProvenance = field(
        default_factory=lambda: PeerReturnsProvenance(source=SOURCE_IN_MEMORY))

    @property
    def peers(self) -> tuple[str, ...]:
        return tuple(sorted(self.series))


def build_panel(observations: Sequence[PriceObservation],
                *, sessions: Sequence[date],
                provenance: Optional[PeerReturnsProvenance] = None,
                rejects: Sequence[RowReject] = (),
                ) -> PeerPanel:
    idx = normalize_sessions(sessions)
    tickers = sorted({o.ticker.strip().upper() for o in observations})
    series = {t: build_series(observations, ticker=t, sessions=idx) for t in tickers}
    prov = provenance or PeerReturnsProvenance(
        source=SOURCE_IN_MEMORY,
        rows_seen=len(observations) + len(rejects),
        rows_rejected=len(rejects),
        peers_loaded=len(series),
        sessions_in_index=len(idx),
        rejects=tuple(rejects),
    )
    return PeerPanel(series=series, provenance=prov)


def load_panel(path: Path, *, sessions: Sequence[date]) -> PeerPanel:
    """Load an operator closes CSV into a validated, aligned panel."""
    idx = normalize_sessions(sessions)
    if not path.is_file():
        return PeerPanel(series={}, provenance=PeerReturnsProvenance(
            source=SOURCE_OPERATOR_CSV, source_path=str(path),
            sessions_in_index=len(idx)))

    obs, rejects, sha = load_peer_closes(path)
    tickers = sorted({o.ticker for o in obs})
    series = {t: build_series(obs, ticker=t, sessions=idx) for t in tickers}
    prov = PeerReturnsProvenance(
        source=SOURCE_OPERATOR_CSV, source_path=str(path), source_sha256=sha,
        rows_seen=len(obs) + len(rejects), rows_rejected=len(rejects),
        peers_loaded=len(series), sessions_in_index=len(idx),
        rejects=tuple(rejects))
    return PeerPanel(series=series, provenance=prov)
