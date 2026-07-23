# SPY Benchmark Audit — corrected figure

> **Note (2026-07-19):** the "147 canonical" population referenced below
> is superseded by the 152-event `FixedWindow_PerEvent_Canonical.csv` —
> see `STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md`. This audit's own
> finding (the corrected SPY figure) is unaffected; only the population
> label is now historical.

## Premise correction

The request described this as a "2014-2025" SPY figure. That date range does not
exist anywhere in this repo. The only SPY buy-and-hold total-return figure on
disk is `Live Signal Engine/CalendarTimePortfolio_Results.csv` (from
`GST_Task4_CalendarTimePortfolio.py`), rows `SPY_equiv_flat` /
`SPY_equiv_zprop`, both showing **`total_return_pct = 85.2`**. That script's
own window is **2021-03-16 to 2025-12-12** — `trades["entry_date"].min()` to
`trades["exit_date"].max()` across the 147 canonical z>=5 STRONG_EARNINGS
events (entry = spike-week anchor + 2 days, exit = anchor + 6 days, nearest
trading day on/before). This audit targets that figure, using its actual
window, not the "2014-2025" description.

## Corrected calculation — show your work

**Window:** 2021-03-16 to 2025-12-12 (matches the existing script's own
`entry_date.min()`/`exit_date.max()` exactly, reproduced independently from
`Earnings-Adjacent Spike vs No-Spike Test/group_a_z4_earnings_adjacent.csv`).

**Data:** SPY daily prices pulled fresh via `yfinance`, `auto_adjust=True`.
This adjusts the Close series for both stock splits and cash dividends
(dividends reinvested at the close on each ex-dividend date) — a standard
total-return-style adjusted close, not a raw/unadjusted price.

**Starting price:** $368.0833 (close on 2021-03-15, the last trading day
before the window's first counted daily return — the existing pipeline's own
date mask is `Date >= start_date`, which includes the return dated
2021-03-16 itself, i.e. the 3/15-to-3/16 move; using 2021-03-16's own close
as the entry price instead gives an almost-identical 83.93% rather than
83.70% — a ~0.2pt difference, immaterial next to the real bug below).

**Ending price:** $676.1581 (close on 2025-12-12).

**Total return:** 676.1581 / 368.0833 − 1 = **+83.70%**

## Existing figure vs corrected figure

| | Existing (CalendarTimePortfolio) | Corrected |
|---|---|---|
| SPY total return | **+85.2%** | **+83.7%** |
| Trading days compounded | 1,190 | 1,194 |

## Root cause of the discrepancy

**Not** the date range, **not** dividends (both figures already include
dividends — the existing pipeline does use `auto_adjust=True` throughout,
verified), and **not** a rounding artifact (per-day differences between the
stored data and a fresh pull are at most 0.00005, i.e. pure floating-point/
4-decimal-place rounding noise — far too small to explain a 1.5-point gap on
their own).

**The actual bug:** every "Daily Excess Return Data" CSV in this project is
pulled **one calendar year at a time** (`yf.download(ticker, start=f"{year}-
01-01", end=f"{year+1}-01-01", ...)`), and daily returns are computed via
`.pct_change().dropna()` **independently within each year's file**. The
first trading day of every year has no prior row *inside that same file* to
difference against, so `pct_change()` returns `NaN` for it — and `.dropna()`
silently discards it. This drops the first trading day of every calendar
year, for every ticker (SPY included), from every excess-return file in the
project.

Within the 2021-03-16 to 2025-12-12 window, the dropped days are:

| Missing date | Real SPY return that day |
|---|---|
| 2022-01-03 | +0.58% |
| 2023-01-03 | −0.42% |
| 2024-01-02 | −0.56% |
| 2025-01-02 | −0.25% |

Three of the four missing days were down days. Silently excluding them from
the compounding inflates the apparent total return — 1,190 days compound to
+85.2%, the true complete 1,194-day series compounds to +83.7%.

## What this does NOT change (per instructions — scope held to this one number)

This same per-year `.pct_change().dropna()` chunking bug is present in
**every** ticker's daily excess return file, not just SPY's copy of it, and
would equally affect any STRONG_EARNINGS straddle event whose entry-to-exit
window happens to straddle a Dec 31 -> Jan 2/3 year boundary (the realized
move for that event would be understated by the same missing-day mechanism).
That is a separate, broader fix and is **out of scope here** — this audit
only corrects the standalone SPY benchmark figure, as requested. The 147
STRONG_EARNINGS event population itself was not re-priced or re-checked for
year-boundary exposure in this pass.

## Bottom line

- Existing SPY figure (+85.2%) is **overstated by ~1.5 percentage points**.
- Corrected SPY buy-and-hold total return, 2021-03-16 to 2025-12-12,
  dividends reinvested: **+83.7%**.
- Cause: a data-completeness bug (missing first-trading-day-of-year rows in
  every per-year price pull), not a methodology error in date range,
  dividend treatment, or capital deployment assumptions.
