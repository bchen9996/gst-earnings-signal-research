# Signal Without Strategy: Search Attention, Earnings Surprise, and the Difference Between Association and Tradable Prediction

*Exploratory retrospective research synthesis. Not preregistered. No investable strategy is claimed.*

---

## 1. Abstract

Public information variables can be economically associated with market reactions without supplying
stable incremental forecasts or implementable trading returns. This paper synthesises a connected
research program that tested two such variables on United States equities: Google search attention
around earnings announcements, and a vendor-defined earnings surprise for ten large semiconductor
firms. We separate three distinct claims that are often conflated — association, incremental
out-of-sample prediction, and tradability after timing and costs — and evaluate each against
prespecified gates.

Search attention produced a standalone event strategy returning a mean net 0.8543% per event, but
its incremental contribution above a strong price-and-calendar baseline was 0.0131 percentage points
with p = 0.98332. Directional and magnitude models showed no incremental skill: a logistic direction
model scored a worse Brier score than an intercept-only baseline (0.2711 versus 0.2560), and
magnitude mean absolute error was 3.6299 with attention versus 3.6284 without (paired p = 0.9827).
Earnings surprise behaved differently. It showed a genuine positive association with the initial
price reaction that strengthened in an earlier temporal sample (Spearman +0.2169, p = 0.000236, over
283 out-of-sample events), yet the same frozen model improved forecast error in only five of eight
years and for four of nine firms, and its bootstrap interval included zero.

We also report a leakage episode in which duplicated events and a mis-specified lag feature produced
an apparent 63.6% directional accuracy that fell to 47.9% after correction. The contribution is a
worked demonstration of where explanatory signal stops becoming predictive strategy.

*(Abstract: 231 words.)*

---

## 2. Introduction

Two ideas motivate much of the modern "alternative data" literature. The first is that public
attention is informative: if unusually many people search for a company's name, something is
happening to that company, and prices may respond. The second is that earnings surprise is
informative: if reported profit differs from what was expected, the price should move to reflect the
news. Both ideas are intuitive, both have serious academic support, and both are widely marketed as
foundations for trading strategies.

This paper is about the gap between those two facts and a third claim that does not follow from
them. A variable can be reliably *associated* with market outcomes without *predicting* them
incrementally, and it can predict them incrementally without being *tradable* once one accounts for
when information actually becomes observable and what execution costs. These are three different
assertions requiring three different kinds of evidence. Conflating them is, in our reading, the most
common way that plausible research becomes an unreliable strategy.

**The research question.** Across a connected program of retrospective studies, do search attention
or vendor-defined earnings surprise supply *incremental, out-of-sample* forecasting power over
strong baselines — and if so, does that power survive realistic timing and costs?

**Main findings.** Search attention repeatedly failed the incremental test. Strategies built around
attention-selected earnings events were profitable in raw terms, but the profitability was
attributable to the underlying earnings event, not to attention: once a baseline containing price
and calendar information was in place, the marginal contribution of attention was economically and
statistically indistinguishable from zero. Earnings surprise told a more interesting story. Its
association with the first full-session price reaction was real, replicated in direction across two
non-overlapping time periods, and became statistically clear in the larger, earlier sample. But the
association did not translate into stable forecast-error reduction, so the downstream drift and
trading stages were never authorised.

Along the way, an internal defect produced a result that looked like a discovery. Correcting it
changed a directional model from apparently skilful to demonstrably unskilful. We report that
episode as a finding in its own right.

**Contribution.** We do not claim markets are efficient, that Google Trends is useless, that
earnings surprises do not matter, or that alternative data cannot work. We claim something narrower
and, we think, more useful: we locate precisely where two intuitively attractive signals stop being
predictive, and we document the methodological controls whose presence or absence changed the
answer.

**Roadmap.** Section 3 defines the three-level framework. Section 4 explains the data and study
architecture from first principles. Section 5 reports the search-attention results and Section 6 the
leakage episode. Sections 7 and 8 cover the earnings-surprise measurement work and its outcome
results including the temporal replication. Section 9 gives a cross-study evidence matrix, Section
10 discusses interpretation, Section 11 states limitations, and Section 12 concludes.

---

## 3. Conceptual framework: three levels of evidence

**Level 1 — Association.** A variable moves together with an outcome. Formally, some measure of
dependence between the variable and the outcome differs from zero in-sample. Association is cheap to
establish and is often contemporaneous: it can hold even when the variable is measured *at the same
time as* or *after* the outcome begins to form.

**Level 2 — Incremental prediction.** The variable improves a genuine out-of-sample forecast
*relative to a strong baseline*. Three words carry the weight. *Out-of-sample* means the model
never saw the evaluated observation during fitting or tuning. *Incremental* means the comparison is
against a baseline already containing everything cheaply available — not against an empty model.
*Strong* matters because a weak baseline makes almost anything look useful; an intercept-only
probabilistic forecast, for example, is a surprisingly hard benchmark to beat on calibration.

**Level 3 — Tradability.** The incremental forecast survives contact with implementation: the
signal must be observable strictly before the position is taken, the holding period must be
executable, and returns must survive transaction costs and realistic slippage.

Each level is strictly stronger than the last. Association does not imply prediction, because a
contemporaneous relationship carries no guarantee that the variable leads the outcome, and because
improvement against a *particular* baseline is not implied by correlation. Prediction does not imply
tradability, because a statistically real reduction in forecast error can be far smaller than the
cost of acting on it.

| Level | Claim | Minimum evidence required | Typical failure mode |
|---|---|---|---|
| 1. Association | The variable moves with the outcome | A dependence measure with an honest interval; no look-ahead in construction | Contemporaneous or post-hoc measurement |
| 2. Incremental prediction | It improves a proper OOS forecast | Chronological validation, a strong baseline, a prespecified loss, an uncertainty interval, stability across periods | Weak baseline; in-sample tuning; leakage |
| 3. Tradability | The forecast is implementable | Signal observable before entry; explicit entry/exit; costs deducted; clustered inference | Ignoring timing; ignoring costs; overfitting the backtest |

This ladder is the organising device for everything that follows. Each study is placed at the
highest level its evidence actually supports — not the highest level it was designed to reach.

---

## 4. Data and study architecture

### 4.1 Google Trends and search-query ambiguity

Google Trends does not report search counts. It reports a **relative** index: for a requested query,
region, and time window, Google scales the series so the maximum observed value equals 100 and
everything else is expressed as a proportion of that peak. Two consequences matter. First, the index
is not comparable across windows: extending the window can rescale every earlier point. Second, the
series is sampled, so repeated retrievals of the identical request can differ.

A subtler problem is **query ambiguity**. A ticker such as "AMD" is also an acronym in other
domains, and a company name such as "Apple" is also a fruit. Any attention series therefore measures
a mixture of the intended construct and unrelated interest. We treat search attention as a *noisy
proxy* for investor attention, not as a measurement of it.

Because Trends series retrieved today are a retrospective reconstruction, they cannot by themselves
establish that the identical series was available at the time a decision would have been made. This
limitation is recorded explicitly in the committed nowcast artifact and is not resolved anywhere in
this program.

### 4.2 Earnings announcements and event timing

United States issuers report quarterly results via a press release, filed with the Securities and
Exchange Commission (SEC) as an 8-K under **Item 2.02**, "Results of Operations and Financial
Condition". The SEC records an **acceptance timestamp** — when the filing was actually received —
which is the closest available proxy for when the information became public.

Timing determines which trading session can first reflect the news. We use a rule fixed before
outcomes were examined, in United States Eastern Time: a release accepted before 09:30 maps to that
same trading session; a release accepted at or after 16:00 maps to the next session; a release on a
weekend or market holiday maps to the next session; and a release accepted *during* market hours is
**excluded**, because a daily closing price cannot separate the pre-release from the post-release
part of that day. Getting this wrong is not a minor issue: mapping an after-close release to the
session that has already closed would import the outcome into the predictor.

### 4.3 Abnormal returns and benchmarks

A raw stock return mixes firm news with whatever the market did that day. We therefore work with
**abnormal returns**: the stock's return minus a benchmark's return over the identical window. For
the semiconductor studies the benchmark is SMH, a semiconductor sector exchange-traded fund, which
removes both market-wide and sector-wide movement and isolates the firm-specific component.

Two windows recur. The **initial abnormal reaction** spans the close before the event session to the
close of the event session — the first full session in which the news can be absorbed. The
**subsequent abnormal return** spans the event-session close to the close five sessions later, the
window in which post-announcement drift, if present, would appear.

### 4.4 Vendor-defined earnings surprise, and what it is not

Earnings surprise is conventionally *reported minus expected* earnings per share (EPS). Obtaining
this historically is harder than it appears, and the distinction drove a substantial part of this
program.

We initially attempted to parse EPS directly from SEC earnings-release exhibits. That work is
described in Section 7. When it proved infeasible at the required coverage, we moved to a commercial
vendor feed. The resulting variable is labelled **`VENDOR_DEFINED_REPORTED_EPS_SURPRISE`** throughout,
and the label is load-bearing. The vendor's `reportedEPS` is **not** SEC-validated GAAP diluted EPS:
on 139 events where a vendor value overlapped an SEC-validated parsed value, only 8 matched within
$0.01 — a match rate of 0.0576 — with a median absolute difference of $0.26. The differences were
not random. They decomposed into retroactive share-split restatement and a GAAP-versus-adjusted
definitional gap.

**The estimate-vintage limitation is unresolved.** The vendor publishes no guarantee that a
historical `estimatedEPS` is the consensus that existed *at the announcement* rather than a value
revised later. This program records that as
`POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED` and does not resolve it by assumption. If those
estimates were revised after the fact, the surprise variable is contaminated in an unknown
direction. This is the single largest threat to interpreting even our statistically clear
association, and we do not claim to have eliminated it.

Because share splits scale reported EPS, estimated EPS, and their difference proportionally, we use
**`surprisePercentage`** — a ratio — as the primary field, and verified mechanically on all 320
in-window vendor records that the ratio is invariant to proportional restatement. That neutralises
*split* restatement. It does **not** neutralise *estimate-vintage* revision.

### 4.5 Validation, metrics, and inference

All model evaluation uses **chronological expanding-window validation**: train on all data up to a
year, test on the following year, then expand. This mirrors how a forecaster would actually have
operated and prevents future observations from informing past predictions. Every transformation —
winsorisation limits, standardisation means and standard deviations, and hyperparameter selection —
is fitted **inside the training fold only** and then applied frozen to the test fold. A single
full-sample standardisation would leak distributional information from the test period backwards.

Metrics are chosen to match the target. **Mean absolute error (MAE)** measures average forecast
error for continuous outcomes. The **Brier score** is the mean squared error of probability
forecasts, where lower is better and calibration matters as much as discrimination [Brier 1950].
**AUC** (area under the receiver operating characteristic curve) measures ranking ability for binary
outcomes; 0.5 is chance. **Spearman correlation** measures monotonic association without assuming
linearity.

For uncertainty we use a **moving-block bootstrap**: resampling calendar blocks rather than
individual events preserves the fact that events cluster in earnings season and that firms within a
period share shocks. Where coefficient inference is reported, standard errors are clustered by firm
using a CR2/bias-reduced-linearisation estimator with Satterthwaite degrees of freedom, which is
appropriate when the number of clusters is small [Cameron et al. 2008].

### 4.6 Leakage

**Leakage** is the accidental presence, in a model's inputs, of information not available at
prediction time [Kaufman et al. 2012]. Two forms bit us directly. **Duplicated events** inflate
apparent sample size and can place copies of the same observation in both training and test folds.
**Same-event lag features** occur when a variable intended to carry the *previous* event's value
actually carries the current event's own outcome. Section 6 documents both.

### 4.7 Status of the components

Interpretation requires knowing what was fixed in advance and what was not.

- **Frozen before designated runs.** The semiconductor extraction quality gate; the feasibility
  design for the vendor data; the outcome design for the initial-reaction study; and the temporal
  replication design. Each was committed before the corresponding outcomes were opened.
- **Corrective controls introduced after defects were found.** Deduplication and the lag-feature fix
  in the direction study (Section 6); throttle-aware retrieval in the vendor audit. These improved
  validity but were reactive, and we label them as such.
- **Retrospective exploratory work.** Everything in this synthesis. No result here is a
  prospectively registered confirmation.
- **Never activated.** A separate prospective protocol (internally "HYP-01") was specified but never
  ran, so it contributes no evidence and appears nowhere in our results.

---

## 5. Search-attention results

We report the load-bearing evidence rather than every exploratory branch, and we do not claim that
all possible attention specifications have been tested.

### 5.1 Standalone profitability is not attention alpha

An event strategy selecting earnings events using an attention filter produced a mean net return of
**0.8543%** per event. Taken alone this looks like a working signal. The decisive test is
incremental: with a baseline already containing price and calendar information, the marginal
contribution attributable to attention was **+0.0131 percentage points** with **p = 0.98332**. The
point estimate is near zero and the p-value is close to 1.

The natural reading is that the strategy captured the well-documented tendency of prices to drift
after earnings announcements [Ball and Brown 1968; Foster et al. 1984; Bernard and Thomas 1989]
rather than anything contributed by search attention. Attention was, in effect, an event-selection
device that picked earnings events — and earnings events carry drift regardless of who is searching.

### 5.2 Direction

A logistic model predicting the sign of the initial price move was compared to an intercept-only
baseline that simply assigns the training-fold base rate to every observation. On pooled
out-of-sample data the baseline achieved a Brier score of **0.2560**; the logistic model achieved
**0.2711**. Lower is better, so the model was *worse calibrated than assuming the base rate*. Its
AUC was **0.4654**, below the 0.5 chance level.

### 5.3 Magnitude

A model forecasting the absolute size of the earnings move produced a pooled out-of-sample MAE of
**3.6299** percentage points with attention features versus **3.6284** without them. The
attention-augmented model was very slightly worse, and a paired test of the loss difference gave
**p = 0.9827**.

### 5.4 Weekly volatility

The final weekly volatility model showed a MAE change of **−0.0309%** (baseline MAE **0.420367**
versus augmented **0.420497**), with a paired block-bootstrap interval of
**[−0.0011023, +0.0010839]** spanning zero.

### 5.5 Product search and restaurant demand

A pilot testing whether product-level search improves prediction of restaurant-sector earnings moves
found that adding search blocks **worsened** both metrics: pooled Brier rose from **0.20211** to
**0.23665** to **0.24739** as search blocks were added, and continuous MAE for the absolute move
rose from **5.4534** to **5.6790** to **5.8543** percentage points. The committed decision label is
`NO_INCREMENTAL_SEARCH_VALUE`.

### 5.6 Fundamental nowcasting

An attempt to nowcast company fundamentals from search demand terminated at
`INSUFFICIENT_DATA`. It is reported for completeness and supports no conclusion in either
direction.

**Summary.** Search attention reached Level 1 in places — it does track when something is happening
— but did not reach Level 2 in any test we ran with a strong baseline.

---

## 6. Leakage as an empirical result

The directional study initially looked successful. With duplicates present, the logistic model
scored **63.6%** accuracy, AUC **0.6395**, and Brier **0.23824**. Those numbers would ordinarily
justify further development.

Two defects were then found. First, the event table contained **68** duplicated rows among **285**,
leaving **217** unique event identities after deduplication. Duplicates inflate the sample and can
put copies of one event on both sides of a train/test split. Second, a feature intended to carry the
*prior* event's gap direction was in fact reading the **same event's own** gap direction — the
model was being shown a transformation of the answer.

After deduplicating to unique identities and correcting the lag feature, the same model family
scored:

- accuracy **47.9%** (below the 53.5% achieved by always predicting positive),
- AUC **0.4654**,
- direction-only strategy net return **−0.7027%**.

The pre-correction figures are **invalidated** and are reported here only to document the size of
the distortion. This was an internal defect, discovered and corrected internally; we neither
sensationalise it nor conceal it.

The methodological point generalises. Nothing about the pre-correction output looked anomalous:
63.6% accuracy on a binary financial target is plausible enough to be believed and modest enough not
to invite suspicion. Realistic-looking alpha can be manufactured accidentally by two ordinary
data-handling mistakes, which is precisely why leakage audits belong in the standard protocol rather
than in the appendix [Kaufman et al. 2012].

---

## 7. Earnings-surprise measurement engineering

Measurement work and outcome evidence must be kept separate, because effort spent on the former is
not evidence for the latter.

A general attempt to parse EPS from earnings-release exhibits across a broad universe was abandoned
as infeasible. A semiconductor-specific parser performed substantially better, reaching a held-out
conditional precision of **0.9860** (combined **0.9868**) — that is, where a value could be
independently checked, it was almost always right.

But precision conditional on checkability is not coverage. Verified reference coverage reached only
**0.7037** against a required 0.80, and usable-event coverage **0.2742** against 0.60. The binding
constraint was structural rather than a parser deficiency: the audit design validated an extracted
quarterly EPS against the same quarter restated in a later quarterly filing, and a **fiscal-year-end
quarter is never restated that way**, because the next periodic report is the annual filing. Of
**216** extractions, **47** were fiscal-year-end quarters, capping attainable coverage at
**0.7824** — below the gate, independent of parser quality.

The extraction phase was therefore classified with two separate fields rather than one: a
`FAILED_EXTRACTION_QUALITY_GATE` decision alongside a characterisation of
`HIGH_CONDITIONAL_PRECISION_BUT_INSUFFICIENT_VERIFIED_COVERAGE`. The original single label was
corrected because it implied the parser was inaccurate, which the evidence contradicts.

A subsequent audit of the vendor feed found uniform coverage (**320** complete records, 10 firms)
and perfect internal arithmetic consistency, but its crosswalk gate failed at **0.6719** against
0.90 — again for a structural reason, since only **267** of **306** SEC events carried a parsed
fiscal period, capping that gate at **0.8344**. That gate failed and **remains failed**; the outcome
studies that follow used a successor exact-date crosswalk and are labelled accordingly.

---

## 8. Initial-reaction results and temporal replication

### 8.1 The 2023–2025 study

Using vendor `surprisePercentage` on **298** uniquely matched semiconductor events, with **116**
out-of-sample events across 2023–2025:

| | Baseline (firm effects) | + Surprise |
|---|---|---|
| MAE of initial abnormal reaction | 0.052506 | **0.051203** |
| Improvement | | **+2.482%** |

Spearman correlation between transformed surprise and the initial reaction was **+0.13515**
(**p = 0.148026**). The block-bootstrap 95% interval for the MAE difference was
**[−0.0007272, +0.0031700]**, which includes zero. The model improved MAE in **all three**
out-of-sample years.

Three of four prespecified gates passed; the uncertainty gate failed. Under the frozen rule the
study stopped.

### 8.2 The 2010–2017 temporal replication

The terminal replication applied the identical frozen model, grid, transformation, bootstrap, and
gates to an earlier, non-overlapping window, on **462** uniquely matched events with **283**
out-of-sample events across 2010–2017:

| | Baseline (firm effects) | + Surprise |
|---|---|---|
| MAE of initial abnormal reaction | 0.044226 | **0.043246** |
| Improvement | | **+2.216%** |

Spearman was **+0.2169** with **p = 0.000236** — larger in magnitude and now clearly significant, on
a sample roughly 2.4 times larger. The bootstrap interval was
**[−0.0000561, +0.0021342]**, again including zero, though only marginally at the lower bound. The
augmented model beat the baseline in **five of eight** years and helped **four of nine** firms —
while **all nine** firms showed a positive firm-level Spearman correlation. The replication failed
its prespecified gate.

### 8.3 Interpretation

The correct reading has four parts, and the order matters.

1. **Earnings surprise contains information about the contemporaneous reaction.** A Spearman of
   +0.2169 at p = 0.000236 across 283 events, positive for every one of nine firms, is not a null
   result and we do not describe it as one.
2. **The association replicated in direction and strengthened.** Both windows produced positive
   point estimates for both the MAE improvement and the correlation. The two samples do not overlap
   in time.
3. **The fixed model did not deliver stable forecast-error improvement.** Five of eight years, four
   of nine firms, and a bootstrap interval containing zero. The annual pattern was notably unstable —
   strong early, absent in the middle years, strong again at the end.
4. **Therefore the downstream stages were never authorised.** The information–price gap was never
   constructed, the drift model never fitted, and no trading was simulated. A gate that exists to
   prevent building on unstable foundations only works if it is honoured when it fails.

The two windows were never pooled. Combining two independent failures of the same gate to
manufacture a pass would invert the purpose of the gate, and no such combination was performed.

---

## 9. Cross-study synthesis

| Construct | Target | Sample | Association | Incremental prediction | Trading | Principal limitation | Final interpretation |
|---|---|---|---|---|---|---|---|
| Search attention | Absolute earnings move | Retrospective US equities | Present in places | **No** — +0.0131 pp, p = 0.98332 | Standalone 0.8543% net, not incremental | Drift confound | Event selector, not alpha |
| Search attention | Move direction | 217 unique events | None detected | **No** — Brier 0.2711 vs 0.2560; AUC 0.4654 | −0.7027% net | Leakage before correction | No directional skill |
| Search attention | Move magnitude | Retrospective panel | Weak | **No** — MAE 3.6299 vs 3.6284, p = 0.9827 | Not run | Noisy normalisation | No incremental value |
| Search attention | Weekly volatility | Weekly panel | Weak | **No** — −0.0309%, interval spans zero | Not run | Small effect size | No incremental value |
| Product search | Restaurant earnings moves | Sector pilot | Not established | **No** — Brier and MAE both worsened | Not run | Small sample | `NO_INCREMENTAL_SEARCH_VALUE` |
| Vendor earnings surprise | Initial reaction 2023–2025 | 116 OOS events | Positive, not significant (+0.13515, p = 0.148026) | **Gate failed** — +2.482%, interval spans zero | Not authorised | Estimate vintage | Suggestive, not established |
| Vendor earnings surprise | Initial reaction 2010–2017 | 283 OOS events | **Positive and significant** (+0.2169, p = 0.000236) | **Gate failed** — +2.216%, 5 of 8 years | Not authorised | Estimate vintage | Real association, unstable prediction |

No new score, ranking, or aggregate is computed from this table.

---

## 10. Discussion

**Why a variable can explain a reaction yet fail to forecast it.** The initial-reaction studies
regress a same-session outcome on a variable released just before that session. That is close to a
*contemporaneous* relationship: surprise and reaction are two views of one event. Forecasting is a
harder task requiring the variable to carry information the baseline lacks *and* to do so
consistently enough that average error falls. A modest, unstable edge can be genuinely present and
still fail to reduce mean absolute error reliably.

**Rapid incorporation.** If prices absorb earnings news within the first session, then by the time a
daily-close-based strategy can act, the informative content is largely priced. Our design measures
the reaction over the first full session and would enter only at that session's close — after the
absorption we measure.

**Regime and firm heterogeneity.** The replication's annual pattern was strong in the early years,
absent in the middle, and strong again at the end, and the model helped only four of nine firms. One
natural hypothesis is that the relationship is regime-dependent. We record this as a hypothesis
*generated by* the observed instability. We did not test it, it is not established, and testing it
retrospectively on the same data would be exactly the multiple-testing error this program is trying
to avoid [Harvey et al. 2016].

**Measurement error.** Both constructs are proxies. Search attention mixes investor interest with
unrelated queries and is delivered on a rescaled, sampled index. Vendor EPS is restated for splits
and follows an adjusted rather than GAAP definition. Classical measurement error attenuates
estimated relationships, so our nulls may understate any true effect — a limitation, not a defence.

**Sample size and power.** With 116 and 283 out-of-sample events and firm-level clustering, our
power to detect a small MAE improvement is limited. Failing an interval-based gate is at least as
consistent with low power as with no effect, and we prefer that honest ambiguity to a claim in
either direction.

**Strong baselines.** The single most consequential design choice was comparing against strong
baselines. An intercept-only probability forecast beat a fitted logistic model; a firm-effects
baseline absorbed most of what surprise appeared to offer. Against an empty baseline, several of
these signals would have looked successful.

**Why null incremental results are useful.** Published financial signals are filtered by
positive results, so the aggregate literature overstates how many work [Harvey et al. 2016; Bailey
and López de Prado 2014]. Documented nulls with prespecified gates and honest intervals are a
partial corrective — particularly when, as here, the nulls are *incremental* nulls that leave the
underlying association intact.

---

## 11. Limitations

These are material and we state them prominently.

1. **This is a set of connected exploratory studies, not one preregistered experiment.** Designs
   were frozen before their own designated runs, but the program as a whole evolved.
2. **This synthesis is not preregistered.** It was written after the results were known.
3. **Some controls were introduced after defects were discovered** — deduplication and the
   lag-feature correction most importantly. They are corrective, not prespecified.
4. **Selected company universes.** Ten semiconductor firms; sector-specific pilots elsewhere.
   Findings need not generalise.
5. **Vendor-defined, retrospectively restated EPS**, not SEC-validated GAAP EPS.
6. **No guaranteed point-in-time estimate vintage.** The largest single threat to interpreting even
   the significant association.
7. **Limited cluster counts.** Nine to ten firms is few for clustered inference.
8. **Daily rather than intraday execution** in several studies; intraday releases were excluded
   because daily bars cannot isolate them.
9. **No historical options baseline**, so we cannot say whether options markets already priced these
   moves.
10. **No live capital was deployed** and no prospective result exists.
11. **We make no claim of universal market efficiency.** We tested specific signals, on specific
    universes, over specific windows, with specific models.

---

## 12. Conclusion

Attention and earnings surprise both carry descriptive information about how prices react to public
news. In the strongest case we measured, vendor-defined earnings surprise showed a positive,
statistically clear association with the first full-session reaction across 283 out-of-sample
semiconductor events, positive for every firm examined.

Descriptive information alone is not alpha. The same variable, in the same frozen model, improved
forecast error in only five of eight years and for four of nine firms, with a bootstrap interval
including zero — and search attention, tested against strong baselines, failed to add incremental
value in every specification we ran.

Method changed conclusions materially. Correcting duplicated events and one mis-specified lag
feature turned an apparent 63.6% directional accuracy into 47.9%. Requiring a strong baseline turned
a 0.8543% standalone strategy into an incremental contribution of 0.0131 percentage points at
p = 0.98332. Requiring temporal replication turned a suggestive 2023–2025 result into a
better-identified but still unstable 2010–2017 one.

**None of the tested strategies qualifies as investable, and none is offered as such.** The
contribution of this work is not a signal. It is a reasonably careful map of where explanatory
signal stops becoming predictive strategy — and a demonstration that the boundary sits earlier, and
is easier to cross accidentally, than intuition suggests.

---

## References

1. Ball, R., and Brown, P. (1968). An empirical evaluation of accounting income numbers.
   *Journal of Accounting Research*, 6(2), 159–178. https://doi.org/10.2307/2490232
2. Bailey, D. H., and López de Prado, M. (2014). The deflated Sharpe ratio: correcting for selection
   bias, backtest overfitting and non-normality. *Journal of Portfolio Management*, 40(5), 94–107.
   https://doi.org/10.3905/jpm.2014.40.5.094 (also SSRN 2460551:
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
3. Bernard, V. L., and Thomas, J. K. (1989). Post-earnings-announcement drift: delayed price response
   or risk premium? *Journal of Accounting Research*, 27, 1–36. https://doi.org/10.2307/2491062
4. Brier, G. W. (1950). Verification of forecasts expressed in terms of probability.
   *Monthly Weather Review*, 78(1), 1–3.
   https://doi.org/10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2
5. Cameron, A. C., Gelbach, J. B., and Miller, D. L. (2008). Bootstrap-based improvements for
   inference with clustered errors. *Review of Economics and Statistics*, 90(3), 414–427.
   https://doi.org/10.1162/rest.90.3.414
6. Da, Z., Engelberg, J., and Gao, P. (2011). In search of attention. *Journal of Finance*, 66(5),
   1461–1499. https://doi.org/10.1111/j.1540-6261.2011.01679.x
7. Diebold, F. X., and Mariano, R. S. (1995). Comparing predictive accuracy.
   *Journal of Business and Economic Statistics*, 13(3), 253–263.
   https://doi.org/10.1080/07350015.1995.10524599
8. Foster, G., Olsen, C., and Shevlin, T. (1984). Earnings releases, anomalies, and the behavior of
   security returns. *The Accounting Review*, 59(4), 574–603. https://www.jstor.org/stable/247321
9. Harvey, C. R., Liu, Y., and Zhu, H. (2016). ... and the cross-section of expected returns.
   *Review of Financial Studies*, 29(1), 5–68. https://doi.org/10.1093/rfs/hhv059
10. Kaufman, S., Rosset, S., Perlich, C., and Stitelman, O. (2012). Leakage in data mining:
    formulation, detection, and avoidance. *ACM Transactions on Knowledge Discovery from Data*,
    6(4), Article 15. https://doi.org/10.1145/2382577.2382579

---

## Source artifacts

Every figure in this manuscript is drawn from a committed artifact in this repository:

- `RETROSPECTIVE_MARKET_RESPONSE_RESULTS_v1.0.json`
- `RETROSPECTIVE_DIRECTION_SIGNAL_RESULTS_v1.0.json` and
  `RETROSPECTIVE_DIRECTION_SIGNAL_REPORT_v1.0.md`
- `RETROSPECTIVE_MAGNITUDE_FORECAST_RESULTS_v1.0.json`
- `RESTAURANT_SEARCH_PILOT_RESULTS_v1.0.json`
- `SEARCH_DEMAND_NOWCAST_RESULTS_v1.0.json`
- `ATTENTION_ACTIVITY_MISMATCH_RESULTS_v1.0.json` (branch `phase2-attention-activity-mismatch`)
- `SEMICONDUCTOR_EPS_ABSORPTION_RESULTS_v1.0.json`
- `Live Signal Engine/Semiconductor_EPS_Absorption/structured_earnings_feasibility_v1.0.json`
- `SEMICONDUCTOR_SURPRISE_ABSORPTION_V3_RESULTS_v1.0.json`
- `SEMICONDUCTOR_SURPRISE_TEMPORAL_REPLICATION_RESULTS_v1.0.json`
