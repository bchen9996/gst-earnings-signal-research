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

**UPDATED July 26, 2026, after feasibility check (see Section 6a):** the full 425-ticker universe is NOT feasible for true daily coverage on current free access (QuantConnect free tier has no automation path at all; GitHub Actions + yfinance tops out around ~200-250 tickers/day before exhausting the free 2,000 Actions-minutes/month budget, and that estimate itself is unmeasured for the unconditional option-chain leg specifically).

**Decision: start with a reduced, known-good universe — the tickers that already produced clean real option-quote data across this project's historical pulls (Pass 1, Pass 2, H5 OOS, Attention Spread OOS) — rather than rotating the full 425 or guessing at a larger subset.** The real cross-checked union is 24 tickers: AAPL, ABBV, ADBE, AMZN, BKR, BRK-B, CTSH, DELL, DVN, GME, GOOGL, GPN, INTC, LDOS, MSFT, NCLH, NKE, QCOM, SBUX, STZ, SYK, TSLA, TTWO, UAL.

**DELL/GME note (corrected July 26, 2026 against the raw QC files — the original draft of this note misstated the failure pattern):** DELL and GME each appear in 3 separate events across the pooled samples. Each was excluded at exactly **one** specific event-date on an identical check ("implausible real_cost_pct_of_spot") — DELL at 2021-08-22 (118.4% of spot), GME at 2024-03-24 (25.6% of spot) — while their other 2 events each priced normally and are genuinely clean (e.g. DELL 2025-11-30 at 3.9% of spot; GME 2025-09-07 at 14.1% and 2023-03-19 clean in both H5 Supp and Attention Spread OOS). This is single-event data noise (an illiquid chain on one specific day), not a per-ticker defect, and it was not two different bugs — both exclusions used the same real_cost_pct_of_spot sanity check. Both tickers are kept in the Phase 2 universe on this basis.

Full-425 rotation (e.g. complete coverage every 2 days instead of every 1) remains a live option for later expansion, not ruled out — just not the starting design.

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

## 6a. Feasibility check — COMPLETE, July 26, 2026

- **QuantConnect free tier: ruled out entirely, independent of ticker count.** Every prior QC pull in this project has been manual (script handed to a human to run in the web Research UI). This isn't a workflow preference — free tier has no API/automation access at all; that requires QuantConnect's paid Quant Researcher tier ($60+/month for live/scheduled nodes). There is no unattended path on free access.
- **The only automation path that has ever worked: GitHub Actions + yfinance**, as already used by `GST_MultiTicker_Forward_Log.py`. That job currently only pulls option-chain/IV data for tickers actively inside their own earnings window — typically 0-3 of 29 tickers/day, not all 29. Unconditional daily IV for the full universe is a capability this project has never run at any scale.
- **Real production timing** (last 5 runs, via GitHub API): 5.5–13.5 min for 29 tickers with the option-chain leg mostly skipped. Private repo → GitHub's free 2,000 Actions-minutes/month budget, currently ~210 min/month used.
- **Extrapolated capacity, with the unconditional-option-chain-leg cost explicitly flagged as unmeasured:** roughly 180-375 tickers/day (central estimate ~240) before exhausting the free minutes budget, assuming ~13-27s/ticker all-in.
- **Not independently verified against Yahoo from GitHub Actions itself** — deliberately not run, since that means hitting a third party's production infrastructure at new scale from shared CI, which risks the IP reputation of the runner pool the existing production job depends on. Held pending explicit go-ahead if a precise number is ever needed.

**Verdict: not feasible at 425 tickers daily. Feasible at ~200-250 tickers/day under the current architecture — see Section 2's updated universe decision.**

## 6b. Before building: things still to resolve

- Resolve the DELL/GME inclusion question flagged in Section 2. **[RESOLVED July 26, 2026 — see Section 2. Both kept; single-event pricing noise, not a per-ticker defect.]**
- If the reduced ticker universe (Section 2) is confirmed as the actual starting scope, re-estimate Actions-minutes budget for that smaller N.
- Decide whether to eventually run the deliberate, sign-off-gated GitHub-Actions-hosted timing test (Section 6a) to replace the extrapolated 13-27s/ticker estimate with a measured one.
