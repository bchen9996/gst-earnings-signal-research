# Usage note (read this part yourself, don't paste it into Claude Code)

1. Drop `HYP02_SupplyChain_HedgeLag_MODEL_PLAN_v0.1_DRAFT.md` (the plan I sent earlier) into the repo at `Live Signal Engine/HYP02_SupplyChain_HedgeLag_MODEL_PLAN_v0.1_DRAFT.md`, alongside the existing HYP-01 spec docs.
2. Open a Claude Code session with your working directory set to your local clone of `gst-earnings-signal-research` (the `bchen9996` fork or wherever you're working).
3. Paste everything below the `---` line as your first message to Claude Code.
4. Everything in the prompt is scoped to Phase 0 (feasibility, placeholder linkage) — it does not touch real capital logic or claim any result. That's intentional; later phases depend on your supply-chain teammate's real linkage map.

---

You're working inside the `gst-earnings-signal-research` repo. Before doing anything, read `Live Signal Engine/HYP02_SupplyChain_HedgeLag_MODEL_PLAN_v0.1_DRAFT.md` in full — it is the build plan you're implementing. Also skim the existing repo conventions before writing anything: `gst_market_response/` (the existing package structure and CLI pattern to follow), a couple of files in `Live Signal Engine/` (e.g. `GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md`) for this project's documentation/locking style, and 2-3 of the root `test_market_response_*.py` files for the testing conventions (pytest, dated amendment tests, mutation/tamper tests). Match this project's existing rigor and naming style rather than introducing a different pattern — this team preregisters decisions, gates result visibility, and writes dated lock/amendment docs instead of quietly overwriting prior conclusions.

## Scope: Phase 0 only

Implement Phase 0 from the plan — the feasibility/plumbing check — and nothing past it. Phase 0 explicitly uses a **placeholder linkage** (same-sector peers, the same limitation `GST_Task2_PeerDivergence.py` already has) because the real supply-chain/competitor linkage map from a teammate doesn't exist yet. Every place that placeholder linkage is used must be clearly labeled as a placeholder in code comments, docstrings, and any output — do not let it read as a real finding. Do not implement Phase 1 (exploratory), Phase 2 (lock), Phase 3 (out-of-sample test), or Phase 4 (paper trading) — those require the real linkage map and are out of scope for this task.

## What to build

**1. A new package**, `hyp02_supply_chain_hedge/`, structured like `gst_market_response/` (separate modules for data providers, feature computation, the model, and a CLI entrypoint — not one giant script).

**2. Stage 1 pipeline** (Link-Strength & Lag):
- A function that computes the target variable defined in Section 3 of the plan — peer volatility/IV change in the [anchor earnings date, peer's next earnings date] window vs. a matched control window — reusing this repo's existing price/return data and exchange-calendar utilities rather than reimplementing them.
- Feature computation for the candidate features listed in the plan (anchor shock magnitude, historical correlation/beta placeholder, relationship-type placeholder, coverage/thinness proxy from existing GST/GDELT infra, days-until-peer-earnings).
- **Lag detection**: implement the classical cross-correlation function (CCF) between the anchor's shock series and each peer's volatility/IV series across a range of lags (e.g. 0–20 trading days) as the primary, decision-driving lag-estimation method, with Bartlett confidence bands or a permutation-based null (reuse the placebo-test infrastructure below for the null). This is the method that determines the estimated diffusion lag — treat it as load-bearing, not a placeholder.
- **Experimental cross-check only, not load-bearing**: if you also implement a "quantum-inspired" autocorrelation variant (quantum time-correlation-function-style formalism), it must live in an isolated module clearly labeled experimental, must never feed into any Stage 1 output, Stage 2 decision, or the feasibility status doc's conclusions, and its only job in Phase 0 is to log where it agrees or disagrees with the classical CCF on the same fixture data — mirroring how this repo's R cross-check (`tools/hyp01_r_reference/`) validates the Python stats before anything is trusted, not the other way around. If you don't have a well-defined, citable construction for this, skip it and say so in the status doc rather than improvising a numerical procedure that just sounds quantum-flavored.
- A simple regularized regression (ridge or lasso; scikit-learn is fine) — explicitly not a tree-based or deep model, per the plan's overfitting concerns given the small sample.
- Leave-one-anchor-out cross-validation (not random k-fold — implement this correctly, it matters).
- A placebo test that shuffles anchor-peer assignments and compares real-linkage results to randomized-linkage results, following the same permutation-test pattern as `GST_Task1_PlaceboPermutationTest.py`.

**3. Stage 2 rules engine** (Hedge Structure Selection):
- A small, explicit decision function (not a trained model) that takes a Stage 1 score plus peer options-market inputs (liquidity, skew, term structure, a cost budget parameter) and returns one of: no position, protective put, put spread, collar, or sector-ETF proxy hedge. Implement it as a readable rules table or constrained optimization, and make every recommendation traceable to the inputs that produced it — no opaque scoring.

**4. Tests**, following this repo's `test_*.py` naming and pytest conventions — cover the target-variable computation, the CCF lag-detection logic (assert it recovers a known injected lag on synthetic data), the leave-one-anchor-out split logic (no leakage across correlated anchor events), the placebo test's own correctness (it should show no effect on genuinely random data), and the Stage 2 decision table's edge cases (illiquid peer, no options market, zero budget).

**4b. Smoke test (required, separate from the tests above).** Add one end-to-end smoke test that runs the full Phase 0 pipeline — ingest → features → CCF lag estimate → Stage 1 model → Stage 2 rules-table decision — on a small fixed fixture (2–3 synthetic anchor events, placeholder linkage) and asserts only that it completes without error and every output matches its expected schema. This is not a statistical-correctness test (that's item 4) — it exists purely to catch integration breakage (a broken join, silent empty dataframe, schema drift) fast. Wire it into the same CI workflow pattern as the existing `.github/workflows/*.yml` files so it runs on every push, not just locally.

**5. A short dated status doc** in `Live Signal Engine/`, matching the naming convention of existing docs (something like `HYP02_PHASE0_FEASIBILITY_STATUS_<date>.md`), reporting: does the pipeline run end to end, what sample size resulted from the placeholder linkage, and an honest assessment of whether that sample size is large enough to be worth continuing to Phase 1 once the real linkage map arrives. This is a feasibility report, not a results report — it must not contain any performance claim about the hedge strategy itself.

## Colab notebook

Produce a single self-contained `.ipynb` (e.g. `notebooks/HYP02_Phase0_Colab.ipynb`) that:
- Starts with a `!git clone` or `!pip install -e .` cell so it works from a fresh Colab runtime with no local file dependencies assumed.
- Installs all required packages explicitly in a cell (don't assume Colab's preinstalled set matches this repo's `requirements.txt`).
- Walks through the Phase 0 pipeline step by step with markdown cells explaining each stage, runs the placeholder-linkage feasibility check, and renders the leave-one-anchor-out CV results and placebo-test comparison inline (tables/plots, matplotlib is fine, no need for a full dashboard).
- Clearly bannered at the top as a Phase 0 / placeholder-linkage feasibility notebook, not a live signal.

## VS Code hosting

Make the repo (or at minimum the new `hyp02_supply_chain_hedge/` package) comfortable to open and run as a standalone VS Code workspace:
- A `requirements.txt` (or update the existing one if the repo already has one) pinning the packages this new code needs.
- `.vscode/settings.json` with the Python interpreter/venv path convention this repo already uses if one exists, otherwise a sensible default (e.g. `.venv`), plus pytest as the configured test runner so the new tests show up in VS Code's Test Explorer.
- `.vscode/launch.json` with a debug configuration for running the Stage 1 pipeline and the CLI entrypoint directly from VS Code.
- A short `README.md` inside `hyp02_supply_chain_hedge/` covering: what this module is (link to the plan doc), how to set up the venv, how to run the tests, how to run the Phase 0 CLI, and an explicit note that it's placeholder-linkage-only until the real supply-chain map lands.

## Non-negotiables

- No real-capital or live-trading logic — this is Phase 0 only.
- No claim, anywhere in code comments, docstrings, notebook markdown, or the status doc, that a hedging edge has been found. This phase tests plumbing and sample-size feasibility on placeholder data, nothing more.
- Don't silently swap in a different linkage source or model family than what's specified without flagging it clearly — if something in the plan turns out to be infeasible as written, stop and document why rather than improvising a replacement.
- Match this repo's existing documentation and locking conventions rather than introducing a new style.

## Definition of done

- `hyp02_supply_chain_hedge/` package with Stage 1 (including CCF lag detection) + Stage 2 implemented, passing tests.
- The Phase 0 smoke test exists, is wired into CI, and passes.
- Colab notebook runs top-to-bottom on a fresh runtime with no manual setup beyond the first cell.
- VS Code workspace config lets someone clone the repo, open it in VS Code, and run/debug the pipeline and tests without extra setup instructions beyond the README.
- Dated Phase 0 feasibility status doc committed to `Live Signal Engine/`, including the smoke test's pass/fail status and, if built, the experimental quantum-inspired cross-check's agreement/disagreement log with the classical CCF (clearly marked as non-load-bearing).
