# HYP-04's first production measurement — anchor shocks

**Dated finding, 2026-08-31.** Append-only.

**Artifacts:**
[`HYP04_ANCHOR_SHOCKS_2026-08-31.json`](HYP04_ANCHOR_SHOCKS_2026-08-31.json) ·
[`HYP04_ANCHOR_SHOCKS_2026-08-31.csv`](HYP04_ANCHOR_SHOCKS_2026-08-31.csv)

> **The display gate is CLOSED, C4 MET, four denials, and the eligible-event
> count is still zero.** Nothing here is evidence about supply-chain
> transmission. No peer response, no direction, no effect estimate, no p-value.

---

## 1. What was measured

**324 of 342** calendar events now carry a well-measured anchor shock under
`HYP04-ANCHOR-SHOCK-RULE-v1`. The other 18 carry a stated denial.

| status | n |
|---|---|
| `shock_computed` | **324** |
| `denied_session` (AS-1, release session UNKNOWN) | 18 |
| `denied_closes` | **0** |
| total | 342 |

Every requested close came back: **1,267 of 1,267 rows filled, 0 missing, 0
rejected**, across 8 tickers (7 anchors plus SPY). AAPL appears in no request
because its membership span holds no candidate event — its whole interval
predates any earnings-specific 8-K item code.

The shock is `|log anchor return − 1.0 × log SPY return|` on the attributed
session, β fixed rather than estimated, split-and-dividend adjusted. Every
published value is **re-derived from the closes on disk** by the suite, not
trusted.

## 2. This is why the anchor side was worth separating

Since registry v1.9, `required_eligibility_class` is HYP-04's own shock rule
rather than HYP-01's attention screen. That is what made this possible today:
the anchor side needs the anchor's closes and the benchmark's, and **nothing
else** — no peer, no linkage edge, no attention series, no option chain.

So the anchor side is complete while the peer side is still blocked on C5 and on
a survivorship-bias-free peer source. The peer-side policy did not bite here:
all members are currently listed. That is an **observation about today's
universe**, not a property of the rule — the intervals include exits, and a
re-walk could admit a delisted anchor, so it is reported rather than assumed.

## 3. A blocker found on the way, and why it mattered

`gst_market_response.exchange_calendar` builds `xcals.get_calendar("XNYS")` with
no `start`, so its first session is **2006-08-31** — a package default, not a
data limit. **57 of the 342 events (17%) fall before it**: NVDA 15, JBL 13,
MCK 13, NKE 6, INTC 6, CTSH 4.

Resolving sessions with that instance raises `DateOutOfBounds` on every one.
Silently dropping them would have been **data availability deciding
membership** — refused twice already in this project, once for a filer's print
format and once for a regulator's item renumbering — and it would have discarded
more events than registry v1.10's Item 12 rule had just recovered, making that
decision self-defeating.

**`gst_market_response/` was not modified.** That instance is HYP-01's; widening
a shared calendar to suit HYP-04 would change another hypothesis's behaviour for
a reason unrelated to it. Instead HYP-04 builds its own wider index in
`sessions.py`, following the pattern `peer_returns` and `event_panel` already
set by *injecting* the session index.

**It is checked, not trusted.** A second calendar is a second answer to a
question that already has one, and the failure is silent: a session off by one is
look-ahead that raises nothing. `verify_agreement()` compares the two across
their whole overlap and the module **refuses** on any disagreement. Measured
against `exchange_calendars` 4.13.2: **5,281 overlapping sessions, zero
disagreements.**

## 4. Every event has a row

All 342 appear, computed or denied. A denied event is data: it keeps the
denominator visible, so a sample that shrank cannot look like one that was always
clean. The 18 denials are all AS-1 — an unresolved BMO/AMC classification, which
`earnings_events` refuses to guess — and they reconcile exactly with the
calendar's UNKNOWN rows in both directions.

Session attribution is asserted directly: **no AMC event is measured on its own
release date** (that session closed before the news), and **every BMO event is**.

## 5. What this does NOT do

- **It does not open the gate, and it does not move C2.**
  `display_gate.current_decision()` passes a literal `eligible_event_count=0`,
  and the gate cross-checks that count against the freeze record's event ids.
  **C2 and C3 move together or not at all.** Producing shocks supplies neither.
  Both are separate, separately authorised steps.
- **324 > 193 is not a met threshold.** The floor counts *eligible* anchor
  events. A computed shock satisfies the anchor-side requirement; it is not the
  same quantity.
- **No shock distribution is published on the dashboard.** How many events carry
  a well-measured shock is data availability, publishable for the same reason
  the coverage audit is. What those shocks *are* is a measured property, and it
  stays out of a page whose gate is closed.
- **It measures no transmission.** The peer side has not been touched.

## 6. Still open

- **The peer price source** — survivorship-bias-free, still unselected. The
  measured failure stands: the provider returns zero rows for ODP across its
  entire history.
- **The C5 linkage map**, still two curated draft rows.
- **`closes_requirements._load_sessions`** carries the same 2006-08-31 bound and
  will hit it on any pre-2006 peer event. Recorded, not fixed here.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
