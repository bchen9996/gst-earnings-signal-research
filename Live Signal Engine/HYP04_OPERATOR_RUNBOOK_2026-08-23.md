# HYP-04 operator runbook — from a curated edge to a target value (2026-08-23)

**What this is:** the end-to-end path through the HYP-04 modules that now compose, written down because it currently exists only in code and in one integration test.

*(No module count is stated here on purpose. A number in prose goes stale the next time the chain gains a step, which is the failure this project keeps repeating — see the `%d checks` and `zero rows are curated` corrections. The diagram below is the count.)*

**What this is NOT:** permission to display anything. Every step below runs with the display gate **CLOSED**. Completing all of them produces a number; it does not produce a finding, and it does not move any gate condition. See §7.

---

## 0. The chain

```
  curated linkage map        HYP04_Linkage_Map_v1.0.csv
        |                    (curated_linkage.py validates it)
        v
  anchor events  --------->  event_panel.py       calendar date -> session index
        |                    (resolve_events)
        v
  closes request  -------->  closes_requirements.py   which closes to collect
        |                    (requirements_for / CLI)
        v
  operator CSV   --------->  peer_returns.py      closes -> daily log returns
        |                    (load_panel, coverage_for_event)
        v
  eligibility    --------->  linkage_resolution.py + pair_eligibility.py
        |                    (P1-P7; P5 fed by DERIVED coverage)
        v
  target         --------->  target.py            RVar log-ratio per horizon
```

Each arrow is a real function call, exercised together in
`test_hyp04_supply_chain_hedge_event_panel.py::test_6`.

## 1. Resolve the response session — do this first, and do not skip it

An anchor event has an **earnings date**. The analysis needs the **session the market response is measured from**. These differ for every after-close release.

```python
from gst_market_response.exchange_calendar import (
    compute_expected_next_full_trading_session_xnys)

response_session = compute_expected_next_full_trading_session_xnys(
    earnings_date, release_market_session)   # "BMO" or "AMC"
```

- **BMO** on a trading day → that same session.
- Everything else → the next session.

**If you pass a raw earnings date instead, every AMC event is one session early.** Nothing raises. The target still returns a finite, ordinary-looking number, computed from a window that begins before the news. This is the single most dangerous mistake in the whole chain.

`event_panel.assert_sessions_resolved()` will flag dates that are not sessions at all — the signature of unresolved input, since weekends and holidays cannot survive resolution. It cannot catch a BMO release that legitimately lands on its own earnings date, so it is a smoke alarm, not a proof.

## 2. Ask what closes you need

> **The event dates below are INVENTED, and exist only to show the CLI's output
> shape.** `MCK-2020Q3:MCK:2020-02-05` and `PKG-2020:PKG:2020-02-24` are not
> sourced earnings dates, were never verified against a filing or a calendar,
> and have not been through the §1 response-session resolution. **No real HYP-04
> anchor event exists** -- `eligible_event_counts` is zero for every hypothesis
> in registry v1.4. Do not collect closes for these windows; they are a
> demonstration, not a work order.
>
> This warning exists because the illustrative dates originally appeared here
> unlabelled, immediately after §1 warns that an unresolved date silently
> corrupts every AMC event -- the exact trap this document describes.

```
PYTHONPATH=. .venv/Scripts/python.exe -m hyp04_supply_chain_hedge.closes_requirements \
    --event MCK-2020Q3:MCK:2020-02-05 \
    --event PKG-2020:PKG:2020-02-24
```

Output names the exact sessions:

```
CVS: 41 session(s) 2020-01-07 .. 2020-03-05  for event(s) MCK-2020Q3
ODP: 41 session(s) 2020-01-24 .. 2020-03-23  for event(s) PKG-2020
TOTAL ROWS TO PRODUCE: 82
```

**41 per (peer, event), not 40.** 20 reference + 20 horizon = 40 *returns*, but a return needs the close before it too, so the window starts one session earlier. Collect 40 and coverage denies with *"reference window has 19/20 finite returns"* — accurate, and pointing at the window rather than at the close you missed.

The tool **requires the authoritative XNYS calendar** and refuses without it (`pip install exchange_calendars`) rather than approximating with weekdays. A weekday approximation puts market holidays into the request; you would collect closes that do not exist.

Pairs that condition **P3** would deny — the edge was disclosed on or after the event — are reported as `SKIPPED` with the reason. That is not a bug: collecting them would waste effort on observations the analysis must discard.

## 3. Produce the CSV

Schema: `HYP04_Peer_Closes_TEMPLATE_headers.csv`

```csv
ticker,session_date,close
CVS,2020-01-07,74.11
```

Rules the loader enforces, all of which reject rather than repair:

| Rule | Why |
|---|---|
| `close` finite and **strictly positive** | `log(p_t / p_{t-1})` is undefined otherwise; substituting anything invents a return no trade produced |
| dates must be **sessions in the index** | off-calendar rows are reported in `off_calendar_dates`, usually meaning the file was built against a different calendar |
| no duplicate `(ticker, session_date)` | two closes for one session is a source defect; picking one hides it |
| **gaps are never filled** | a missing close kills the return on *both* adjacent sessions — a return spanning a gap is not a one-session return, and admitting it inflates realized variance exactly where the data is worst |

Missing is `None`, never `0.0`. A zero return is a real observation (a halt, a flat close) and must not be confused with absent data.

## 4. Load and check coverage

```python
from hyp04_supply_chain_hedge.peer_returns import load_panel, coverage_for_event

panel = load_panel(csv_path, sessions=sessions)
assert panel.provenance.loads_clean, panel.provenance.as_dict()

cov = coverage_for_event(panel.series["CVS"], event_id="MCK-2020Q3",
                         anchor_day=day_index)
print(cov.sufficient, cov.reasons)
```

`Coverage.reasons` distinguishes *window runs off the index* from *window has a hole*. Those need different fixes — extend the index versus find the missing close.

## 5. Resolve pairs

```python
from hyp04_supply_chain_hedge.peer_returns import peer_history_map
from hyp04_supply_chain_hedge.linkage_resolution import resolve_from_curated_map

hist = peer_history_map(panel.series, events)          # DERIVED, never asserted
res  = resolve_from_curated_map(events, map_path=map_path,
                                anchor_eligibility=elig, peer_history=hist)
print(res.denial_reasons())
```

**`peer_history` must come from `peer_history_map`.** P5 exists to ask whether a peer has usable history; a caller that can simply assert `True` makes it an honour system, in exactly the way an assertable `uses_placeholder_linkage` would have made C5 one.

Read `denial_reasons()` rather than only the count. P3-heavy denials are a *curation* problem (the map's as-of dates do not reach far enough back); P5-heavy denials are a *data* problem. A single total cannot tell them apart.

`anchor_eligibility` is **required** for P1. Omit it and every pair denies on P1 — correctly, since an unchecked event is not an eligible event.

## 6. Compute the target

```python
import numpy as np
from hyp04_supply_chain_hedge.target import raw_log_ratio_target

arr = np.array([np.nan if r is None else r
                for r in panel.series["CVS"].log_returns], dtype=float)
val = raw_log_ratio_target(arr, anchor_day, horizon)
```

**Encode missing as `np.nan`, never `0.0`.** A zero substitution fabricates the observation the loader refused to invent, and makes the target return a finite number from data that does not exist. This exact mistake was made while writing the peer-returns suite and caught only because coverage and the target were asserted to agree at *every* day index.

## 7. What you have, and what you do not

After every step above you have a **target value for one (event, peer, horizon)**.

You do **not** have:

- a finding — the display gate is CLOSED and every finding panel is empty
- evidence about supply-chain transmission
- anything displayable at any event count

The gate's conditions are unchanged by everything above:

| | |
|---|---|
| **C1** status | HYP-04 is `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` |
| **C2** threshold | 193 eligible **anchor events**. Curating edges does not move this — only observed anchor events do |
| **C3** freeze | no event-set freeze record exists |
| **C4** decisions | MET since registry v1.2 |
| **C5** linkage | denies while the analysis path runs on the positional-synthetic placeholder |

**C5 does not clear because a curated map exists.** It reads `FreezeRecord.uses_placeholder_linkage`, which `linkage_resolution.freeze_record_fields()` *derives* from what a run actually read. A freeze claiming non-placeholder linkage can only come from a run that genuinely used a curated map.

## 8. Known limitations, recorded rather than absorbed

- **`peer_history_map` is per-peer, and coverage is really per-pair.** A peer is marked available only if it covers **every** event it appears in, which undercounts. Use `coverage_for_event` for the precise per-pair answer. Decision of 2026-08-23: keep the conservative form for now.
- **Two curated edges is not a linkage map.** Registry v1.3 records `exists_partial` precisely so this is not mistaken for sufficiency.
- **No peer price data has ever been captured.** The registry records `data_captured: false` for both capture paths. A module that can ingest is not ingested data.
- **No real anchor events exist.** `eligible_event_counts` is zero across the board; that is HYP-01's registry, not HYP-04's to fill.
