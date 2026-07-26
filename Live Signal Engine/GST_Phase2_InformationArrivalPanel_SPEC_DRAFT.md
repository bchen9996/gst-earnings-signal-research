# Phase 2 Spec (DRAFT) — Information Arrival Panel
**Not yet built. This is a locked-scope planning document to hand to Claude Code when you're ready to actually build it — not a task for tonight.**

---

## 0. Why this exists

Everything through July 26, 2026 was earnings-event-triggered: GST only gets computed for a ticker within 5 days of its own earnings. That's a narrow, sparse dataset by design.

This phase reframes the unit of analysis from "earnings event" to "day." Instead of asking "does a spike near earnings predict a big move," the long-run question becomes "which daily attention/liquidity patterns, across any day, precede abnormal market reactions." This is a genuinely different and richer dataset — not a bigger version of the same one.

**This does not replace Candidate B or the multiticker log. It runs alongside them.**

---

## 1. What gets logged, daily, for every ticker in the universe

- GST z-score (existing methodology, unchanged)
- Wikipedia pageview z-score (existing methodology, unchanged — built July 26, 2026)
- Implied volatility (real, from whatever option-chain source is being used that day)
- Realized volatility (trailing, real price data)
- Price, volume
- Days-to/from-nearest-earnings (so the existing earnings-triggered logic remains a filterable subset of this panel, not a separate system)
- [Open question, not yet decided: news velocity as a third attention source — GDELT was flagged as a free candidate but not yet vetted]

## 2. Universe

- Start with the existing 425-ticker list already used for the batch scanner. Do not expand the universe until this is running cleanly — get the daily mechanics right on a known set before scaling wider.

## 3. Governance — carried over unchanged from the rest of this project

- No hypothesis gets tested on this panel until a **pre-set minimum sample size is hit, decided now, not adjusted later.** Proposed floor: do not touch this data for any hypothesis test until at least 6 months of daily collection exist, or until n reaches whatever was locked in the H16/Wikipedia pre-registration — whichever is later. Write the actual number down before collection starts, not after looking at how much has accumulated.
- Every hypothesis tested against this panel gets its own dated pre-registration file, same format as H5/Attention Spread/H16.
- No editing collected rows after the fact. Corrections are new dated entries, same as CHANGELOG discipline elsewhere in this project.

## 4. The one hypothesis already motivated and worth pre-registering when data is ready

**"Does agreement between GST and Wikipedia z-scores (both elevated simultaneously) predict move size or volatility better than either alone?"**

Motivated directly by the July 26, 2026 independence finding (r=0.244, ~6% shared variance) — not a new fishing expedition, a direct follow-up to an observed result. This should be the first thing pre-registered once the panel has enough data, not before.

## 5. Explicitly out of scope for now

- News velocity, Reddit, SEC EDGAR download logs, or any other third attention source — worth considering later, not part of this build.
- Any trading/monetization framing. This phase is pure data collection and observational research, same "no real capital" boundary as everything else in this project.

## 6. Before building: things to resolve first

- Confirm daily (not earnings-triggered) IV pulls are feasible at this scale without hitting the same cost/access walls that ruled out Cboe/ThetaData/ORATS/Polygon for the historical work — QuantConnect's free tier may not be built for a always-on daily cross-sectional pull across 425 tickers. This needs a feasibility check before committing to the design, not after.
- Decide who/what runs this (GitHub Actions, same as the existing forward loggers) and confirm it can handle the added daily volume without hitting rate limits on any of the four+ data sources involved.
