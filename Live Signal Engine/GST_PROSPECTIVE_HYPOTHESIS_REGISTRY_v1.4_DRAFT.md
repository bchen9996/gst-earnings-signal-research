# GST Prospective Hypothesis Registry — v1.4 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.4.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.4.json)
**Authored:** 2026-08-23 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.3.json` (sha256 `03ef40768fa4a45b…`)
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **This version fixes a document defect, not a measurement.** It resolves a
> self-contradiction v1.3 introduced. No hypothesis, threshold, measurement,
> capture path, decision or result changes. The gate is unchanged.

---

## 1. What was wrong

v1.3 corrected HYP-04's linkage availability from `does_not_exist` to `exists_partial`. It left **two other statements in the same document** asserting that no linkage map exists:

| Path | Said |
|---|---|
| `eligible_event_counts.note` | "no peer linkage map exists" |
| `statistical_governance.adding_a_hypothesis_rule` | "no linkage map exists" |

Both were inherited unchanged from v1.1, where they were true.

**Nothing computed from either sentence.** No display-gate condition reads them, no eligibility rule consults them, and no result or decision was affected. The defect was that a governance document asserted two incompatible things — which is the failure these documents exist to prevent, and "nothing reads it" is the argument that lets prose rot.

## 2. Why it happened

This is the same failure the rest of that day's work was spent removing: **a fact corrected in one place while a copy of it survives somewhere else.** It was produced *by* the correction.

v1.3's generator carried real guards — it verified that HYP-04's immovable fields had not moved, that no other hypothesis changed, and that the decision ledger was byte-identical. **None of them asked whether the field being corrected still had copies elsewhere in the document.**

## 3. What v1.4 changes

**`eligible_event_counts.note`** — no longer claims the map does not exist, and now says why a curated map does not move an event counter:

> A curated linkage map now exists in part (availability `exists_partial`) and is nowhere near sufficient; it is **NOT** a reason these counters are non-zero, because they count eligible **ANCHOR EVENTS**, which curating linkage edges does not produce.

**`statistical_governance.adding_a_hypothesis_rule`** — made explicitly historical. It describes the conditions when v1.1 *added* HYP-04, which is a legitimate thing to record; it simply read as a present-tense claim:

> v1.1 added HYP-04 under that rule: **AT THAT TIME** zero HYP-04 eligible events existed, no linkage map existed … That is a statement about the conditions when HYP-04 was added, not about the present.

**`contradiction_corrected`** — a new block recording what was wrong, why it happened, that no result was affected, and what guard now prevents it.

## 4. The guard, which is the actual deliverable

`make_registry_v1_4.find_availability_contradictions()` walks an entire registry document and reports every string still asserting the linkage map does not exist while the availability field says otherwise. **`build_v1_4()` runs it on its own output and refuses to write a document that fails.**

Two design points matter:

**It is vacuous by design when availability *is* `does_not_exist`.** A document may say the map is absent as often as it likes while the map is absent. The suite asserts that the *same* document with `exists_partial` does report the contradictions, so the vacuous case is about the value rather than a dead guard.

**The exemptions are narrow and listed.** A change summary saying the value moved *from* `does_not_exist`, and the vocabulary that *defines* that word, must not trip it — otherwise a document could not explain its own history. An exemption list is how a guard quietly stops guarding, so the suite checks both directions: exempt fields are ignored, and the identical phrase in a non-exempt field is still caught.

## 5. v1.3 keeps its contradiction, deliberately

`v1.3.json` remains on disk byte for byte, **contradiction included**. Two reasons:

1. **Append-only.** v1.3 asserts that rule about v1.2, and it applies to itself. A superseded version is allowed to be wrong — that is what superseded means.
2. **It is the guard's regression fixture.** `test_2` points the guard at the real published v1.3 and requires it to find both contradictions. A guard written after the fact is easy to write so that it passes; testing it against the actual defect is what makes it meaningful. If v1.3 were quietly fixed, that test would pass vacuously forever.

## 6. What is unchanged

| | |
|---|---|
| HYP-04 status | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` |
| `required_external_measurement` | byte-identical, including `exists_partial` |
| `capture_path_modules` | byte-identical, both still `data_captured: false` |
| Decision ledger | byte-identical — v1.4 resolves and reopens nothing |
| Event floor | 193 eligible anchor events |
| Eligible event counts | all zero |
| `results` | `null` |
| Display gate | **CLOSED**, C4 MET, exactly 4 denials — verified before and after repointing |
| HYP-01 / HYP-02 / HYP-03 | unchanged, still incorporated by reference to v1.0 |

## 7. What is still true

- HYP-04 is **not implemented** and displays nothing.
- No peer price data has ever been captured; both capture paths record `data_captured: false`.
- Two curated edges is not a linkage map. `exists_partial` exists precisely so that is not mistaken for sufficiency.
- Nothing in this version is evidence about supply-chain transmission.
