# Signal Without Strategy — Executive Summary

*Companion to `SIGNAL_WITHOUT_STRATEGY_MANUSCRIPT_v1.0.md`. Exploratory retrospective research.
Not preregistered. No investable strategy is claimed or offered.*

---

## What the project set out to do

The project began with a widely believed idea: that publicly visible signals — how many people are
searching for a company, and whether its earnings beat expectations — should help anticipate how its
stock reacts. Both have genuine academic support. The question was narrower: do they add
*forecasting* value beyond what a sensible baseline already knows, and does it survive real-world
timing and costs?

That requires separating three claims that are easy to blur:

1. **Association** — the signal moves with the outcome.
2. **Incremental prediction** — it improves an honest out-of-sample forecast against a strong
   baseline.
3. **Tradability** — that improvement survives acting only on observable information, after costs.

Each level is harder than the one before. Most of what gets called a "signal" clears the first and
is quietly assumed to clear the other two.

## What was tested

**Google search attention** around earnings announcements, against move direction, move size, weekly
volatility and — in a separate pilot — restaurant demand from product searches. And **earnings
surprise** for ten large semiconductor companies, against the first full session's price reaction
relative to a sector benchmark. All of it used chronological validation: train on the past, test on
the following year, never the reverse.

## Methodological status, stated precisely

For each designated study, the model specification, the primary metric, the decision gates, and the
temporal-replication rules were written down and committed **before that study's designated outcomes
were opened**. That is the strongest claim the record supports, and it is narrower than
"prespecified".

Other controls were **reactive**, introduced only after a defect was found — above all
**event-identity deduplication** and the **strictly earlier lag-feature repair** below. They
improved validity but were corrective, not planned.

**The overall research program and this synthesis were not preregistered.** The program evolved as
results accumulated, and this summary was written after the results were known.

## What looked promising

An attention-based strategy on earnings events earned a mean net **0.8543%** per event. A
directional model appeared to reach **63.6%** accuracy at predicting the opening direction. And
earnings surprise showed a real relationship with the first-session price reaction — one that got
*stronger* on an earlier, larger sample.

## What failed, and why

**The attention strategy was not attention alpha.** Against a baseline already containing price and
calendar information, the marginal contribution of search attention was **+0.0131 percentage
points** at **p = 0.98332** — indistinguishable from zero. The profits came from the earnings event
itself, a long-documented effect, not from who was searching. Across direction, magnitude, weekly
volatility and the restaurant pilot, attention never beat a strong baseline; several times it made
forecasts slightly worse.

**The 63.6% directional result was a data defect.** The event table contained **68** duplicated rows
among **285**, and a feature meant to carry the *previous* event's direction was actually reading
the *current* event's own outcome. After deduplicating to **217** unique events and repairing the
feature to use a strictly earlier event, accuracy fell to **47.9%** — worse than always guessing
"up" — with an AUC of **0.4654** and a strategy return of **−0.7027%**. The earlier numbers are
invalidated. Two ordinary mistakes produced a result that looked entirely believable.

**Earnings surprise cleared association but not prediction.** In the 2010–2017 replication, across
**283** out-of-sample events, the correlation between surprise and the initial reaction was
**+0.2169** with **p = 0.000236**, positive for **all nine** companies tested. That is a real
finding and is not described here as a null. But the same frozen model reduced forecast error in
only **five of eight** years, helped only **four of nine** companies, and its uncertainty interval
included zero. Under the rules fixed in advance that failed the gate, so the follow-on drift model
and trading simulation were never run.

## What remains genuinely supported

Earnings surprise carries measurable information about the contemporaneous price reaction, and that
association replicated in direction across two non-overlapping periods. Search attention tracks
*that* something is happening, but never forecast *what* will happen beyond a strong baseline.
Strong baselines, leakage audits and out-of-period replication each changed a conclusion
materially; none was optional.

## Why this matters, and what was built

Published financial signals are filtered toward positive results, so the literature overstates how
many work. Documented negative *incremental* results — where the underlying association is left
intact rather than denied — are a useful corrective, as is a case study of accidental leakage with
before-and-after numbers.

Supporting that: a frozen-design protocol; deterministic runners whose outputs recompute from
committed data; integrity tests that fail on deliberately leaked, duplicated, mistimed or relabeled
inputs; and a numerical audit tying every number here to a committed artifact.

## Why no strategy is being marketed

Because none earned it. No tested configuration cleared all three levels. The vendor earnings data
is not SEC-validated GAAP accounting data, and there is no guarantee its historical analyst
estimates are the ones that existed at the time — an unresolved limitation that alone would preclude
a performance claim. No capital was deployed and no prospective test was run.

The contribution is not a signal. It is a careful map of where explanatory signal stops becoming
predictive strategy.

---

## Contributions

*To be completed by the project owner. No contributor identities are assigned.*

| Role | Contributor(s) |
|---|---|
| Conceptualisation and research question | |
| Study design and freezing of designated rules | |
| Data engineering and retrieval | |
| Parser and measurement development | |
| Statistical modelling and validation | |
| Leakage detection and correction | |
| Replication design and execution | |
| Manuscript drafting | |
| Review, editing, and verification | |
| Project supervision | |
