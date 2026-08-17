# Signal Without Strategy — Executive Summary

*Companion to `SIGNAL_WITHOUT_STRATEGY_MANUSCRIPT_v1.0.md`. Exploratory retrospective research.
Not preregistered. No investable strategy is claimed or offered.*

---

## What the project set out to do

The project began with a widely believed idea: that publicly visible signals — how many people are
searching for a company, and whether its earnings beat expectations — should help anticipate how its
stock reacts. Both ideas have genuine academic support. The question was narrower and more
demanding: do these signals add *forecasting* value beyond what a sensible baseline already knows,
and does any such value survive real-world timing and trading costs?

To answer that, the work drew a line between three claims that are easy to blur:

1. **Association** — the signal moves with the outcome.
2. **Incremental prediction** — the signal improves an honest out-of-sample forecast compared with a
   strong baseline.
3. **Tradability** — that improvement survives when you can only act on information after it is
   observable, and after costs.

Each level is harder than the one before it. Most of what gets called a "signal" clears the first
and is quietly assumed to clear the other two.

## What was tested

Two families of signals, across several studies:

- **Google search attention** around earnings announcements, tested against the direction of the
  price move, the size of the move, weekly volatility, and — in a separate pilot — restaurant-sector
  demand from product-level searches.
- **Earnings surprise** for ten large semiconductor companies, tested against the first full trading
  session's price reaction, measured relative to a semiconductor sector benchmark.

Everything used chronological validation: train on the past, test on the following year, never the
reverse. Rules were written down and committed *before* the corresponding results were opened.

## What looked promising

An attention-based strategy on earnings events earned a mean net **0.8543%** per event. In
isolation, that looks like a discovery.

A directional model appeared to reach **63.6%** accuracy at predicting whether a stock would open up
or down.

And earnings surprise showed a real relationship with the first-session price reaction — one that
got *stronger* when tested on an earlier, larger sample.

## What failed, and why

**The attention strategy was not attention alpha.** Once compared against a baseline that already
contained price and calendar information, the marginal contribution of search attention was
**+0.0131 percentage points** with a p-value of **0.98332** — indistinguishable from zero. The
profits came from the earnings event itself, a long-documented effect, not from who was searching.
Across direction, magnitude, weekly volatility, and the restaurant pilot, attention never improved
on a strong baseline; in several cases it made forecasts slightly worse.

**The 63.6% directional result was a data defect.** The event table contained **68** duplicated rows
among **285**, and a feature meant to carry the *previous* event's direction was actually reading the
*current* event's own outcome. After deduplicating to **217** unique events and fixing the feature,
accuracy fell to **47.9%** — worse than always guessing "up" — with an AUC of **0.4654** and a
strategy return of **−0.7027%**. The earlier numbers are invalidated. This is reported openly,
because it is the most transferable lesson in the project: two ordinary mistakes produced a result
that looked entirely believable.

**Earnings surprise cleared association but not prediction.** In the 2010–2017 replication, across
**283** out-of-sample events, the correlation between surprise and the initial reaction was
**+0.2169** with **p = 0.000236**, and it was positive for **all nine** companies tested. That is a
real finding and is not described here as a null. But the same frozen model reduced forecast error
in only **five of eight** years and helped only **four of nine** companies, and its uncertainty
interval included zero. Under the rules fixed in advance, that failed the gate — so the follow-on
drift model and the trading simulation were never run.

## What remains genuinely supported

- Earnings surprise carries measurable information about the contemporaneous price reaction, and
  that association replicated in direction across two non-overlapping periods.
- Search attention tracks *that* something is happening, but did not forecast *what* will happen
  beyond a strong baseline in any test conducted.
- Strong baselines, leakage audits, and out-of-period replication each changed a conclusion
  materially. None was optional.

## Why this matters

Published financial signals are filtered toward positive results, so the visible literature
overstates how many work. Carefully documented negative *incremental* results — where the underlying
association is left intact rather than denied — are a useful corrective. The project also produced a
concrete case study of accidental data leakage, with before-and-after numbers, which is rarer in
public than it should be.

## What was built

- A frozen-design protocol in which rules, thresholds, and decision labels are committed before the
  corresponding results are examined.
- Deterministic, reproducible analysis runners whose outputs recompute from committed data.
- Automated integrity tests that fail on deliberately leaked, duplicated, mistimed, or relabeled
  inputs.
- A numerical audit that ties every number in this write-up back to a specific committed artifact.

## Why no strategy is being marketed

Because none earned it. No tested configuration cleared all three levels of evidence. The vendor
earnings data is not SEC-validated GAAP accounting data, and there is no guarantee that its
historical analyst estimates are the ones that existed at the time — an unresolved limitation that
alone would preclude a performance claim. No capital was deployed and no prospective test was run.

The contribution here is not a signal. It is a reasonably careful map of where explanatory signal
stops becoming predictive strategy.

---

## Contributions

*To be completed by the project owner. No contributor identities are assigned here.*

| Role | Contributor(s) |
|---|---|
| Conceptualisation and research question | |
| Study design and preregistration of frozen rules | |
| Data engineering and retrieval | |
| Parser and measurement development | |
| Statistical modelling and validation | |
| Leakage detection and correction | |
| Replication design and execution | |
| Manuscript drafting | |
| Review, editing, and verification | |
| Project supervision | |
