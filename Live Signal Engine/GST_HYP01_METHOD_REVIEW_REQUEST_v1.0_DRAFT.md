# Request for Methodological Review — HYP-01 (v1.0 DRAFT)

**Draft. No recipient is named, and no reviewer has been approached.** This is the text intended to accompany a future request to an econometrics or statistics faculty member. It is stored in the repository so the request itself is on the record.

---

## The request in one paragraph

We are running a small preregistered observational study and we have deliberately stopped before collecting any data, because four statistical choices are unresolved and we do not think we are qualified to make them. We would like about **90 minutes to two hours** of your time to tell us whether our proposed answers are defensible, and to correct them where they are not. **We have not seen a single outcome**, and we will not begin collection until this is settled.

## What the study is

We are two high-school researchers in St. Louis, working with a Saint Louis University faculty member, studying whether unusual public attention around a company's earnings announcement is associated with the size of the market's reaction to it.

Attention is measured with Google Search Trends, as an abnormality z-score computed at a mechanically derived date before the announcement. The outcome is the **absolute** overnight price gap across the announcement — magnitude, not direction. The universe is a **fixed list of 24 large-cap tickers, locked before screening began.**

The single primary hypothesis, fixed before any candidate was screened:

> **Does higher abnormal pre-earnings Google-search attention associate with a greater absolute overnight earnings response?**

    abs_overnight_gap ~ gst_zscore        (OLS, two-sided, alpha = 0.05,
                                           cluster-robust on ticker)

## The structure that creates the problem

- **n = 60** eligible earnings events, collected prospectively between 2026-09-01 and 2027-05-31.
- **At most 24 clusters**, because a cluster is a ticker and the universe is locked at 24. Fewer if some tickers contribute no eligible event.
- **Unbalanced by construction** — a ticker may contribute three eligible quarters in the window, or one, or none.

So this is a small-cluster problem, and from what we have read the conventional cluster-robust standard error is biased *downward* here, which inflates apparent significance. That is the direction of error we least want in a confirmatory test.

A synthetic exercise on data shaped like ours (no real values, fixed seed) suggested the effective degrees of freedom at 24 clusters and 60 observations is roughly **7 to 11, not 23** — consistent with published Monte Carlo results showing effective df averaging about 9.4 at 20 nominal clusters.

## Why no outcome has been looked at

The analysis lock — predictor, outcome, model, alpha, sample size, event ordering, no interim analysis, no optional stopping — was written and committed to a public repository **before any candidate was screened**. Display gates are closed: no effect estimate, direction, plot, interim p-value or confidence interval may be shown before the full 60-event set is frozen. Currently `results: null`, `frozen_event_ids: []`, and the eligible-event count is **0**.

We would rather ask you now, with nothing to bias the answer, than after we have data and a motive.

## What we are asking

Four decisions, each independently answerable. Full detail and sources are in the review packet.

1. **Covariance estimator.** We propose **CV2** (bias-reduced linearization, Bell & McCaffrey 2002), clustered on ticker. Is that right at G ≤ 24, n = 60? **Would you prefer CV3 with t(G−1)** — the published performance looks comparable and the degrees-of-freedom rule is simpler?
2. **Finite-sample inference.** We propose **Satterthwaite / Bell–McCaffrey degrees of freedom** computed from the realized design, keeping α = 0.05 two-sided. Is that appropriate, or would a fixed `t(G−1)` with a bias-corrected estimator be better?
3. **Multiplicity.** We have exactly one primary confirmatory hypothesis; two further hypotheses are registered as secondary and exploratory and cannot change the confirmatory conclusion. We propose **no adjustment for the primary test**. Is that defensible, or is an adjustment required, and over what family?
4. **A failure rule we deliberately did not write.** If eligible events concentrate in a few tickers, the effective degrees of freedom could fall very low. **Is there a floor below which we should not draw a confirmatory conclusion at all — and if so, what value, and what should happen instead?** We left this blank on purpose: putting a number there ourselves would make an unqualified guess look like a locked decision.

Two smaller questions, if you have appetite: the encoding of sector fixed effects in a secondary model, and whether a pre-data design-sensitivity analysis is worth doing.

**And most usefully: tell us if the framing itself is wrong.** We are not methodologists. "You are asking the wrong question" is a valuable answer.

## Estimated burden

| | |
|---|---|
| Review packet | ~15 pages, structured, with a comparison table and a bibliography of primary sources |
| Proposed amendment | ~4 pages |
| Signoff form | a structured form; every field currently `PENDING` |
| **Realistic total** | **90 minutes to 2 hours** if you engage with the packet's tables and skip the appendices |
| Minimum useful | Answering questions 1–4 alone would unblock us |

The packet is written to be skimmable: §2 is the exact list of unresolved choices, §4 is the comparison table, §7 is the numbered questions.

## Documents

| Document | Path |
|---|---|
| Method review packet | `Live Signal Engine/GST_HYP01_STATISTICAL_METHOD_REVIEW_PACKET_v1.0_DRAFT.md` |
| Proposed amendment (Markdown) | `Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED_DRAFT.md` |
| Proposed amendment (JSON) | `Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json` |
| **Current authoritative lock** | `Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md` |
| Signoff form | `Live Signal Engine/GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md` |
| Preregistration gap audit | `PREREGISTRATION_GAP_AUDIT_v1.0.md` |
| Project overview | `README.md` |

## What we commit to

**We will report a null result.** The success criterion for this project is a trustworthy answer, not a positive one. If the coefficient is zero we publish the coefficient, its confidence interval and its p-value exactly as we would if it were not.

We have a track record of this, and it is public. Our earlier options backtest showed a +145.5% median return; recalibrating against real quoted option costs reversed it to −10.7%, and both figures appear side by side on the front page of the repository. A prior reconstruction was quarantined for confirmed look-ahead contamination. Two out-of-sample hypotheses are recorded as dead. Nothing was quietly deleted.

We will also record your decisions verbatim — including any place where you tell us our proposal is wrong.

## What reviewing this does *not* imply

- **No endorsement** of the project, its methods, or its conclusions.
- **No authorship** and no expectation of any.
- **No public naming.** You will not be named in the repository or in any publication unless you explicitly consent on the signoff form. Declining to be named does not reduce the value of the review to us.
- **No ongoing commitment.** A single review with no follow-up is a complete and useful contribution.
- **No liability** for what we do with the advice.

If you would rather give an informal opinion than complete a form, that is fine — we will record it as an informal opinion and say so.

## Contact

Harshith Akurati — `PENDING`
Tyler He — `PENDING`
Faculty contact, Saint Louis University: Professor Marcus Painter — `PENDING`

Repository: https://github.com/harshith-akurati/gst-earnings-signal-research

---

*No recipient is named in this draft, and no request has been sent.*
