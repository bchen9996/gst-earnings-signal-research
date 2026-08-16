# Sector-Composition Audit — Recorded Disposition v1.0

## Disposition

**`ACCEPT_CURRENT_BROAD_PROPOSAL`**

No stratified or sector-specific redesign is required before F5.

## Attribution

| | |
|---|---|
| **Audit author** | **Claude Code** |
| **Technical reviewer** | **ChatGPT/Codex — a separate AI system from the audit author** |
| **Review character** | **External AI technical review.** Not human review, and not credentialed-methodologist review. |
| **Owner decision** | **Explicitly accepted** by the repository owner (see the verbatim statement below) |
| **GitHub approving reviews** | **None** |
| **Human review template** | **Unsigned — every finding and disposition `PENDING`** |
| Date recorded | 2026-08-16 |

The technical review was performed by a **different AI system than the one that wrote this audit**,
and it returned `REQUEST_CORRECTION` twice before this acceptance: first on the issuer-versus-security
proxy denominator and the unavailable reproduction inputs, then on the tracked-test enumeration and
skip coverage. Each finding was corrected in the branch history rather than argued away.

**No statistician, methodologist or human domain expert reviewed or approved this audit.** The
committed reviewer template (`GST_UNIVERSE_50_SECTOR_COMPOSITION_REVIEW_TEMPLATE_v1.0.md`) is
deliberately left **unsigned, with every finding and all four dispositions `PENDING`**, and GitHub
contains **no approving review** for PR #21. Anyone relying on this disposition should read it as:
*two independent AI systems mechanically verified the arithmetic and provenance, and the repository
owner accepted the result on that basis* — not as human or credentialed methodological endorsement.

The reviewer's identity as a separate AI system is recorded on the repository owner's attestation;
it is not something this repository can verify from its own artifacts.

## Repository-owner decision, verbatim

> "I accept the current broad 50-ticker proposal based on the sector-composition audit. No
> stratified or sector-specific redesign is required before F5."

## Stated reason for acceptance

The corrected issuer-level audit shows the final 50:

- covers **all 12** FF12 categories, none absent;
- has a largest-category share of **24.0000%** (`BusEq`, 12 of 50);
- has **lower concentration than the legacy 24 on every specified metric** — HHI 0.225694 →
  0.140800, effective categories 6.224330 → 8.549585, largest share 41.6667% → 24.0000%;
- **closely tracks the 100-issuer OEF proxy under equal weights** — every category within ±3.0
  percentage points, largest gap `NoDur` −3.0 pp;
- has **stable leave-one-out results** — largest share 22.4490%–24.4898%, HHI 0.137026–0.146189.

## What this disposition does and does not change

**Does not** alter, reorder or replace any of the 50 tickers; create a selection; introduce a sector
quota; activate the proposed universe; modify the production 24; change HYP-01; close F5; or
unblock collection. F5 remains `OPEN`. Prospective collection remains `BLOCKED`. The production
universe remains the original 24.

The audit itself remains descriptive: it froze **no** concentration threshold, drew no accept/reject
conclusion from the numbers, and called no distribution representative, balanced, acceptable,
unacceptable, biased or statistically significant. This disposition is a **judgment recorded on top
of** that evidence, not a result computed from it.

## Outcome blindness

This disposition was reached **without consulting GST attention data, prices, returns, earnings
results or any prospective outcome**. No such data was retrieved, inspected or available to the
audit. Choosing a universe after seeing outcomes would make the sampling frame outcome-dependent;
that did not occur here.
