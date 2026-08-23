# GST Prospective Hypothesis Registry — v1.3 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.3.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.3.json)
**Authored:** 2026-08-22 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.2.json` (sha256 `9a2782b82d834dc4…`)
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **This version is a FACTUAL CORRECTION, not a decision.** It records state that
> changed after v1.2 was authored. It resolves nothing, promotes nothing,
> re-thresholds nothing, reports no result, and opens no gate.

---

## 1. What changed from v1.2

| | v1.2 | v1.3 |
|---|---|---|
| HYP-04 linkage `availability` | `does_not_exist` | **`exists_partial`** |
| HYP-04 `placeholder_used_in_phase_0` | "same-sector peers" | **positional-synthetic** (`peers[i*k:(i+1)*k]`) |
| HYP-04 `status_basis` | three capture gaps, all open | **two now have modules; no data has flowed** |
| Availability vocabulary | undefined | **defined, three states** |
| HYP-04 status | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` | **unchanged** |
| HYP-04 event floor | 193 anchor events | **unchanged** |
| HYP-04 decision ledger | four `RESOLVED_IN_DATED_ANALYSIS_LOCK` | **unchanged, byte-identical** |
| HYP-01 / HYP-02 / HYP-03 | defined in v1.0, by reference | **unchanged, still by reference** |
| Eligible event counts | all zero | **all zero** |
| `results` | `null` | **`null`** |
| Display gate | CLOSED, C4 MET, 4 denials | **CLOSED, C4 MET, 4 denials** |

## 2. Why `exists_partial` and not `exists`

Two curated edges are not a linkage map.

Flipping to `exists` would have made that word mean "some rows are present", and every other place the registry uses it would weaken to match. `exists_partial` says what is true: **real curated data exists, and it is nowhere near sufficient.**

The three states are now **defined in the document** rather than left for a reader to infer from usage:

| State | Meaning |
|---|---|
| `does_not_exist` | No curated data of this kind exists anywhere in the repository. |
| `exists_partial` | Real curated data exists and validates, but is nowhere near sufficient. **Never means the measurement is satisfied.** |
| `exists` | Curated data exists and is sufficient. **Not yet used by any hypothesis.** |

**`exists_partial` moves nothing toward display.** The gate's threshold counts eligible **anchor events**; curating linkage edges does not change that count. This is stated twice in the JSON — once in the vocabulary and once on the field itself — because it is the single most likely thing for a later reader to get wrong.

## 3. Two capture paths now have modules. **No data has flowed.**

v1.2 named three missing capture paths. Two now have production modules:

| Gap | Module | Data captured |
|---|---|---|
| (2) peer-side return series | `hyp04_supply_chain_hedge/peer_returns.py` | **none** |
| (3) event → peer join | `hyp04_supply_chain_hedge/linkage_resolution.py` | **none** |

Both are recorded in `capture_path_modules` with **`data_captured: false`**, and the JSON states the distinction outright:

> A module that CAN ingest is not ingested data.

**This is why HYP-04's status does not move.** Zero peer price observations have been captured, and no production run has used either module. Gap (1), the linkage map, remains the binding blocker on Phase 1.

The rule from v1.2 is unchanged and still governs: *working analysis code operating on synthetic fixtures is not a production capture path, and this registry does not treat it as one.*

## 4. The "same-sector" correction

v1.0 through v1.2 described the Phase 0 placeholder as **"same-sector peers"**.

That was wrong. The pairing is `peers[i*k:(i+1)*k]` in `fixtures.py` — **list position** — and the sector column is never read. The wording described `GST_Task2_PeerDivergence.py`, which *is* genuinely sector-based, and was inherited here in error.

**The error ran in the dangerous direction: it overstated the placeholder's quality, in a field whose entire purpose is to warn.**

The package corrected this in `__init__.py` on **2026-08-18** and in its README on **2026-08-22**. This registry version is the last of the three to catch up. Earlier registry versions keep the original wording — they are not edited — and `test_market_response_hypothesis_registry_v1_1.py` still asserts v1.1 says "same-sector", correctly, because v1.1 does.

## 5. v1.2 is not edited in place

`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.2.json` remains on disk, byte for byte, and its own governance suites continue to run against it. v1.3 records v1.2's SHA-256 in `supersedes_sha256`, so any later drift in v1.2 is detectable.

`v1.0` remains the authoritative source for HYP-01, HYP-02 and HYP-03. They are **not restated here** — restating them would create two mutable copies of governed text. The generator verifies v1.0 is still present and refuses if the carried-forward block was touched.

## 6. How this file was produced

Generated by `hyp04_supply_chain_hedge/make_registry_v1_3.py`, which is deliberately named off the `test_*` pattern so CI never runs it.

**The facts it records are derived, not asserted.** It reads the committed linkage map through the validating loader and **refuses to write `exists_partial`** unless the map genuinely loads clean with at least one usable edge; it verifies both capture modules import before recording that they exist. A registry that recorded `exists_partial` because an operator typed it would be worth no more than a freeze record claiming non-placeholder linkage because a caller set a flag.

It also refuses if any of these moved: the hypothesis list, the carried-forward block, or HYP-04's status, classification, thresholds, eligibility class, display rule, forbidden substitutions or decision ledger.

`test_hyp04_supply_chain_hedge_registry_v1_3.py` exercises those refusals directly rather than trusting them — including against a deliberately tampered document, because a guard only ever reached through the happy path is a guard nobody has seen fire.

## 7. What is still true

- HYP-04 is **not implemented** and displays nothing.
- The display gate is **CLOSED**: C1, C2, C3 and C5 all deny. C4 is MET, as it has been since v1.2.
- No result, effect estimate, direction or p-value exists for HYP-04.
- Phase 1 is blocked on the linkage map, which now exists in part and is far from sufficient.
- Nothing in this version is evidence about supply-chain transmission.
