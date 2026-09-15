# Discovery method, compared rigorously: reverse EDGAR search vs. hand-curated peer guessing (2026-09-14)

Written in direct response to external review, which flagged this project's
peer-discovery pivot as its most potentially novel contribution and asked
for the comparison to be documented rigorously rather than asserted. This
does not introduce any new computation -- every number below is already
recorded in `HYP05_PEER_UNIVERSE_2026-09-12.md` (rounds 1-6) and
`HYP07_DISCOVERY_AND_TARGET_METHODOLOGY_2026-09-13.md`; this document pulls
the comparison out of those narrative logs and states it on its own, with
the caveats a fair comparison requires.

## The two mechanisms, precisely

**Hand-curated guessing** (HYP-05 rounds 1-3, 2026-09-12): propose a
specific counterparty NAME from training-knowledge recall -- "NVDA's
competitor is probably Ambarella," "MCK's customer is probably Rite Aid" --
then ask EDGAR to confirm or deny that specific guess via full-text search
restricted to the anchor's own filings. The discoverer (Claude) has to
already know the small company exists before EDGAR is ever asked anything.

**Reverse search** (HYP-05 rounds 4-6, HYP-07 steps 1-2): search EDGAR's
full-text corpus, UNSCOPED by CIK, for `[an anchor's name] AND [a
disclosure tail-phrase]` -- e.g. `"Intel Corporation" "accounted for
approximately"`. A small company's OWN 10-K, disclosing that a large anchor
is a material share of ITS revenue (customer/supplier) or naming the anchor
as a named rival (competitor), surfaces directly. No name is ever guessed;
the disclosure finds itself.

Both mechanisms were followed by the same discipline: every raw hit was
hand-read for genuine relationship content before being trusted, not
sampled or aggregate-counted, and every resolved ticker went through the
same point-in-time market-cap eligibility gate (`peer_selection.py`,
PS-1..PS-4). The comparison below is between two ways of generating
candidates, not between careful and careless verification -- verification
was equally rigorous on both sides.

## Head-to-head, in the real numbers

| | Hand-curated guessing (rounds 1-3) | Reverse search (rounds 4-6) |
|---|---:|---:|
| Anchors covered | 7 | 27 (round 4) -> 788 (round 6) |
| Candidates generated | 96 human-authored name proposals, across 3 rounds | 136 searches (round 4) -> 3,180 searches (round 6); zero names guessed |
| Confirmed with genuine, readable filed evidence | 37 / 96 (39%) | 12 / 17 (71%, round 4) -> 101 / 277 (36%, round 6) |
| Resolved to a tradeable ticker | 5 | 5 (round 4) -> 39 (round 6) |
| Distinct qualifying peer tickers | 1 (AMBA) | 0 (round 4, blocked on missing anchor-shock data) -> 2 (round 5) -> 25 (round 6) |
| Qualifying (peer, event) pairs | 8 | 0 -> 69 (round 5) -> **778** (round 6) |

Three full rounds of human-generated guessing -- 96 proposals, refined
across a session, including a round-3 method that specifically MINED
already-confirmed sentences for more names rather than guessing blind --
produced exactly one company (Ambarella) that was both a real, filed
relationship AND resolved to a currently tradeable, sub-$2B ticker: 8
(peer, event) pairs. The reverse search, run once against a modestly larger
27-anchor set, found 12 genuine hand-verified relationships in its first
pass -- already more than hand-curation's entire 3-round output of
qualifying peers -- and scaling the identical, unmodified mechanism to 788
anchors (still zero guessed names) produced 778 qualifying pairs across 25
distinct tickers, roughly 97x hand-curation's own final sample.

## Why: reverse search removes the recall ceiling, not the noise

Round 3's own finding explains the structural reason hand-curation plateaus
regardless of effort: real, genuinely smaller, historically-named
counterparties of large anchors are heavily survivorship-selected against
staying both small AND independently tradeable for 15-20 years -- most get
acquired, taken private, or delisted (Reebok, Oakley, Saucony, Freescale,
Foot Locker, and others, all confirmed by hand in round 3). A human
proposing names from memory can only propose names that memory contains,
and the pool of "real, still-independently-trading small companies you'd
happen to recall as a rival of a specific giant" is thin by construction.

Reverse search does not depend on anyone having heard of the company first.
It depends only on the SMALL company's own disclosure existing and being
searchable -- and ASC 280 customer-concentration disclosure is close to a
formulaic, near-mandatory sentence once a customer crosses the materiality
threshold. Scaling from 27 to 788 anchors required zero new guessing, only
more search queries against a pre-existing, unrelated-purpose reference
universe (`Russell1000Proxy_Filtered_Universe.csv`) -- the mechanism scales
with anchor count, not with the discoverer's knowledge.

## The honest limitation: reverse search is noisier at scale, not more careful

Round 3's mined-sentence method actually confirmed at a HIGHER rate (86%,
24/28) than reverse search's scaled round 6 (36%, 101/277) -- precision is
not where reverse search wins. Widening the anchor set from 27 to 788
introduced real false-positive genres that a human guesser's narrower,
name-first approach never encountered at meaningful volume: institutional-
ownership 5%-beneficial-owner tables (the single largest false-positive
category at scale), SOFR-benchmark-rate citations, Iran Threat Reduction
Act boilerplate repeated verbatim across sponsor-affiliated filers, and
REIT mall-tenant directories. Every one of these was caught by the same
hand-read-every-hit discipline, not a sampling assumption -- but it took
more review effort per confirmed relationship as the anchor set widened.
The productivity advantage is in raw yield and scalability, not in
precision; both are disclosed, not just the favorable one.

## A second, independent confirmation: competitor relationships (HYP-07)

The same reverse-vs-forward asymmetry reappeared in a genuinely different
relationship type. HYP-07's Step 0 (`HYP07_DISCOVERY_AND_TARGET_
METHODOLOGY_2026-09-13.md`) first tried forward extraction -- reading an
anchor's OWN filing for its named competitors, the same already-calibrated
`extract_competitor_edges_from_text()` HYP-05 used -- and got the same
diagnosed failure mode: 56 edges found, but 0 of 108 evaluable pairs
qualified, because a filer's own prose names only its most PROMINENT
rivals, and prominent rivals are large. Reverse search, phrase-swapped for
competitor language and scaled to the same 788-anchor universe, found 195
qualifying pairs across 6 peers -- a second, independent confirmation that
the mechanism (not something specific to customer/supplier language)
is what drives the productivity gap.

## What this does and does not establish

This validates the DISCOVERY METHODOLOGY: reverse search over a broad,
pre-existing anchor reference list finds real, point-in-time-correct
eligible peers at a scale hand-curation could not reach for either
relationship type tested. **It does not, and must not, revise any
already-run result.** The 778 customer/supplier pairs round 6 found were
discovered AFTER HYP-05's Phase 3 test had already run and its 8-pair
holdout was spent; feeding a newly-discovered universe back into an
already-closed test is exactly the post-hoc data-mining this project's
Phase-2-lock / Phase-3-authorization sequence exists to prevent, regardless
of how rigorously the new universe was found. The 778-pair universe was
instead used to found an entirely new, freshly preregistered hypothesis
(HYP-06), with its own lock and its own not-yet-spent holdout -- the
correct way to act on a genuine discovery-method improvement without
compromising an already-completed test.

Artifacts underlying every number above: `HYP05_HAND_CURATED_
VERIFICATION_2026-09-12.json`, `_ROUND2_`, `_ROUND3_` (hand curation, all
three rounds); `HYP05_REVERSE_SEARCH_RAW_HITS_2026-09-12.json`,
`HYP05_CANDIDATE_LINKAGE_REVERSE_SEARCH_HANDREVIEWED_2026-09-12.json`
(round 4); `HYP05_PEER_UNIVERSE_AUGMENTED_ANCHORS_2026-09-12.json` (round
5); `HYP05_REVERSE_SEARCH_RAW_HITS_SCALED_2026-09-13.json`,
`HYP05_PEER_UNIVERSE_SCALED_2026-09-13.json` (round 6);
`HYP07_CANDIDATE_LINKAGE_REVERSE_COMPETITOR_SEARCH_SCALED_
HANDREVIEWED_2026-09-13.json`, `HYP07_PEER_UNIVERSE_REVERSE_SEARCH_
SCALED_2026-09-13.json` (HYP-07's independent confirmation).
