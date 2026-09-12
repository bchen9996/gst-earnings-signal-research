# HYP-05: Supply-Chain Relationship-Lag Model — Build Plan (v0.1, DRAFT)

**Status:** proposal / not yet preregistered. No data has been pulled for
this hypothesis, no anchor or peer ticker has been selected, and no relationship
has been curated. Written to define the build sequence and the decision
points that need to be locked before any real event is touched, consistent
with this project's existing HYP-01/HYP-04 discipline.

## 1. Where this comes from

HYP-04 ran its one preregistered holdout test (Phase 3, 2026-09-11) and
reported **NOT_SIGNIFICANT** at every tested horizon
(`HYP04_PHASE3_RESULT_2026-09-11.json`; registry closure
`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.13.json`, status
`HOLDOUT_TESTED_NULL`). That result is bounded and does not establish that
supply-chain earnings information never diffuses slowly — it establishes
only that HYP-04's specific construction did not detect an effect. HYP-04's
construction was: four large, analyst-covered anchors; six large,
analyst-covered peers; all seven curated relationship edges of the SAME
type (`direct_customer`); a coarse two-feature model
(`shock_magnitude`, `days_to_peer_earnings`) with no linkage-strength or
liquidity/coverage term.

**The question this hypothesis asks:** does delayed earnings-information
transmission appear specifically in clearly signed supplier/customer/
competitor relationships among lower-coverage or less-liquid peers — the
place HYP-04's own construction was least able to detect it, and the place
slow diffusion is most plausible a priori (thin coverage, less analyst
attention processing the anchor's news quickly).

This is a **fresh hypothesis**, not a reopening of HYP-04's holdout. Nothing
here revisits `HYP04_PHASE3_RESULT_2026-09-11.json` or any decision the
signed HYP-04 Phase 2 lock made.

## 2. What HYP-04 leaves buildable, and what is genuinely new

A feasibility audit (2026-09-11, this session) found the pieces below mostly
already exist and need extension, not invention from scratch:

| Need | Source | Status |
|---|---|---|
| Relationship type beyond customer-concentration | `curated_linkage.py`'s `RELATIONSHIP_TYPES` already includes `direct_supplier`, `sector_competitor`, `loose_sector_neighbor`; `edgar_linkage.py` gained `extract_competitor_edges_from_text()` this session | **Built, UNCALIBRATED.** Real, offline-tested, but never run against a real 10-K Competition section and deliberately not wired into `extract_for_universe()`. See its module docstring. Calibrating it is real work and is out of scope until curation actually starts. |
| A structured linkage-strength proxy | `curated_linkage.py` gained an optional `concentration_pct` column this session (v2 header schema, additive, existing HYP-04 maps untouched) | **Built.** Surfaces the disclosed concentration percentage as a queryable float instead of only free-text. |
| Ex-ante liquidity/coverage cutoff | `GST_Russell1000Proxy_LiquidityScreen.py` / `GST_SmallMidCap_UniverseExpansion_LiquidityCheck.py` (repo root): `pull_atm_spread`, `check_options_and_marketcap`, `is_ambiguous` all take a bare ticker, already universe-agnostic | **Buildable independently.** GDELT news-volume is explicitly NOT usable (`GDELT_PreSpike_NewsVolume_Test_NOTES.md`: terminated after 17.3 hours, 80/319 events, rate-limited) — dropped, not resurrected. |
| Non-outcome-driven universe selection | `anchor_universe.py`'s AU-1..AU-6 + `NEVER_CONDITIONS` pattern (constants → conditions table → forbidden-criteria table → fail-closed `evaluate_ticker` → `derive_universe`) | **Template exists**, EDGAR/HYP-04-specific guts do not transfer — a HYP-05 peer-selection module would follow the same SHAPE, not import this one. |
| Anchor/peer universe itself | — | **Not chosen.** No ticker has been selected for either side. |
| Target/outcome definition | — | **Not chosen.** |
| Exact liquidity/coverage percentile cutoff | — | **Not chosen.** A design decision, not a data question — see §5. |

## 3. Candidate features

Per peer, per anchor event, building on HYP-04's own list (its plan §3.4)
but now naming what actually backs each one:

- **Anchor shock magnitude** — unchanged from HYP-04, already validated.
- **Relationship type, with real variation** — `direct_supplier`,
  `direct_customer`, `sector_competitor`, or `loose_sector_neighbor`,
  sourced from BOTH the existing customer-concentration extractor and the
  new (uncalibrated) competitor/supplier-context extractor. **Not pooled
  without checking** — HYP-04's own null was measured on relationships that
  were entirely one type; this hypothesis exists partly to see whether type
  matters, so type must vary in the curated sample, not be assumed away.
- **Linkage strength** — the disclosed `concentration_pct` where a
  customer-concentration disclosure exists; a `NEVER_CONDITIONS`-clean,
  pre-defined proxy for relationships sourced from the (uncalibrated)
  competitor/supplier path, not an after-the-fact correlation of returns.
  Requiring the measure to be defined **before** looking at any outcome is
  the same discipline as `PARTY_LOOKBACK_CHARS`/`clean_party` — decided by
  construction, not fit.
- **Peer coverage/liquidity** — an ex-ante percentile cutoff on market cap
  and/or options liquidity (via the Russell1000Proxy/SmallMidCap screen
  functions), decided BEFORE any candidate ticker's returns are examined.
- **Days between the anchor's earnings and the peer's own next earnings**
  — unchanged from HYP-04.

**Model choice.** Same caution as HYP-04's own plan: a small
(anchor event × peer) sample is the single biggest risk. A richer feature
set raises overfitting risk further, not just corrects for HYP-04's
coarseness — regularization (ridge/lasso) stays load-bearing, and a
tree-based or deep model remains off the table for the same reason HYP-04's
plan gave.

## 4. Sample-size gate — PROVISIONAL

`hyp04_supply_chain_hedge/make_hyp05_sample_size_gate.py` (this session):
same method as HYP-04's own floor — Šidák correction over an empirically
max-T-permutation-measured effective-test count, hypothetical
Cohen's d = 0.5, α = 0.05, power = 0.80. The naive single-test baseline is a
real number today: **126** (design-independent). The **operative floor is
NOT yet measured** — HYP-05 has no fixed horizon grid or model spec for a
permutation run to measure the correlation structure OF. A provisional
floor of **195 anchor events** is recorded, borrowed from HYP-04's own
measured k range (6.05–6.34, conservative end) as a planning assumption
only — not a claim about HYP-05's design, and not a use of any observed
project result (both borrowed values come from HYP-04's own Phase 0
SYNTHETIC-fixture diagnostic). See
`HYP05_SAMPLE_SIZE_GATE_2026-09-11.md` for the full derivation and what
must supersede it once a design exists to measure for real.

## 5. What is explicitly NOT yet decided

Listed the same way HYP-04's own plan listed its open items — each must be
resolved, dated, before curation begins:

1. **The exact liquidity/coverage percentile cutoff.** Method is named
   (§2); the number is not chosen. Choosing it after looking at which
   candidate peers "look promising" would be exactly the outcome-driven
   selection `NEVER_CONDITIONS` exists to forbid.
2. **The target anchor/peer universe.** No ticker, on either side, has
   been selected.
3. **The target/outcome definition.** HYP-04's target is not assumed
   carried forward; a fresh hypothesis re-derives this from its own
   question, not by inheritance.
4. **Two-way clustering, options benchmark, and any other item HYP-04's own
   analysis lock left as `PENDING_SEPARATE_ANALYSIS_LOCK`** — HYP-05 is a
   different hypothesis and re-decides these on its own terms rather than
   inheriting HYP-04's resolutions by default.

## 6. Explicitly NOT in this document

- **No curation.** No EDGAR pull against a real filing, no liquidity screen
  run against a real candidate list.
- **No registration commitment beyond the light shape** this document
  supports — see the registry entry this plan feeds
  (`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.14.json`), which is deliberately
  as light as HYP-04's own first registration (v1.1) was.
- **No freeze, lock, or Phase 1–3 machinery.** Far downstream of curation,
  which has not started.
