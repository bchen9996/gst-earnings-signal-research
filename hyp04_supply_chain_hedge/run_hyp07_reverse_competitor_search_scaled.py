#!/usr/bin/env python3
"""LIVE. Scaled reverse-direction EDGAR full-text search for HYP-07
competitor candidates: the SAME mechanism as
run_hyp07_reverse_competitor_search.py (round-4-equivalent first pass), run
over a much larger anchor set. MAKES REAL PROVIDER CALLS.

=== WHY A SEPARATE SCRIPT, NOT A MODIFIED FIRST-PASS ONE ===

The first-pass script is already tested and committed. This reuses its
exact, UNCHANGED `discover_leads()` / `verify_lead()` / `COMPETITOR_PHRASES`
/ `MAX_HITS_PER_QUERY` / `SOURCE_REVERSE_COMPETITOR_SEARCH` rather than
editing it -- the identical "new script, shared pure functions" pattern
`run_hyp05_reverse_concentration_search_scaled.py` already established
against round 4's customer/supplier module.

=== THE EXPANDED ANCHOR SET: THE SAME ONE ROUND 6 USED, NOT A NEW DECISION
===

HYP-07's first pass searched the same 27 anchors round 4 used (for direct
comparability). Scaling further reuses round 6's own already-principled
choice verbatim: `load_expanded_anchor_universe()` is imported UNCHANGED
from `run_hyp05_reverse_concentration_search_scaled.py` -- the SAME
`Small-Mid Cap Universe Expansion/Russell1000Proxy_Filtered_Universe.csv`
(788 tickers, predates this decision, built for an unrelated liquidity-
screen purpose), merged against THIS module's own `ANCHOR_NAME_VARIANTS`
(imported from the first-pass competitor module, itself imported from round
4's customer/supplier module -- the same 27 hand-curated anchors either way).
Reusing the merge function rather than reimplementing it means the exact
same "never overwrite a hand-curated entry" / "skip blank rows" logic
applies here for free, already tested in
test_hyp04_supply_chain_hedge_reverse_concentration_search_scaled.py.

Every one of the ~815 companies is searched, unconditionally -- no
plausibility filter, matching both round 4's and round 6's own stated
discipline.

=== CHECKPOINTED: A TRANSIENT FAILURE PARTWAY THROUGH DOES NOT LOSE REAL
    PROGRESS ===

efts.sec.gov's intermittent 500s (edgar_agreements.py's own RETRY_STATUSES
comment: "observed on 2 of 30 canary searches") are retried 3x with backoff
inside `_get()` already, but at ~4,000-9,000 requests across 788 anchors a
query can still exhaust all 3 attempts. This was NOT hypothetical: two live
runs of this exact script both failed on an unrelated, different query
after making real, substantial progress (1,753 leads at 275/788 anchors;
4,185 leads at 675/788 anchors) -- discovery kept everything in memory and
wrote nothing until the very end, so both runs lost their entire progress
on a single transient error. A third blind retry would risk the same
outcome for no better reason than luck.

`--checkpoint` (default: `.hyp07_scaled_search_checkpoint/<out-raw-hits
stem>.json`, gitignored -- same convention as `.edgar_cache/`: reproducible
by re-running, not research output, never committed) persists BOTH phases
incrementally: `discover_leads()`'s result is written per-anchor as each
anchor completes, and `verify_lead()`'s result is written per-lead as each
lead is verified. A restart loads the checkpoint, reuses every anchor/lead
already done (making zero redundant requests against SEC for them, which
also respects the fair-access spirit `REQUEST_SPACING_SECONDS` exists
for), and only does live work for what remains. The three real dated
output artifacts are written only once every anchor is discovered AND every
lead is verified -- the checkpoint is scratch machinery, not a fourth
output.

=== EVERYTHING ELSE IS IDENTICAL TO THE FIRST PASS ===

Same phrases, same MAX_HITS_PER_QUERY, same verification
(`classify_context` plus `_looks_like_competitor_sentence`, both reused
unchanged), same output shapes, same source tag -- distinguished from the
first pass's artifacts by filename/date alone.

STAGED. Without --yes-run-live it prints the plan and exits.

  python -m hyp04_supply_chain_hedge.run_hyp07_reverse_competitor_search_scaled
  python -m hyp04_supply_chain_hedge.run_hyp07_reverse_competitor_search_scaled --yes-run-live
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .run_hyp05_reverse_concentration_search_scaled import (
    PROVENANCE_HAND_CURATED,
    PROVENANCE_RUSSELL1000_PROXY,
    RUSSELL1000_PROXY_CSV,
    load_expanded_anchor_universe,
)
from .run_hyp07_reverse_competitor_search import (
    ANCHOR_NAME_VARIANTS,
    COMPETITOR_PHRASES,
    CONTACT,
    MAX_HITS_PER_QUERY,
    SOURCE_REVERSE_COMPETITOR_SEARCH,
    discover_leads,
    verify_lead,
)

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-13"

OUT_NAME_SEARCH = LSE / f"HYP07_PEER_NAME_SEARCH_REVERSE_COMPETITOR_SEARCH_SCALED_{AS_OF}.json"
OUT_LINKAGE = LSE / f"HYP07_CANDIDATE_LINKAGE_REVERSE_COMPETITOR_SEARCH_SCALED_{AS_OF}.json"
OUT_RAW_HITS = LSE / f"HYP07_REVERSE_COMPETITOR_SEARCH_RAW_HITS_SCALED_{AS_OF}.json"

#: Gitignored, same convention as .edgar_cache/ -- reproducible by
#: re-running, scratch machinery, never a research artifact. See module
#: docstring, "CHECKPOINTED".
CHECKPOINT_DIR = Path(".hyp07_scaled_search_checkpoint")
CHECKPOINT_DEFAULT = CHECKPOINT_DIR / f"{OUT_RAW_HITS.stem}.checkpoint.json"

#: Requests needed scale with ~815 anchors, not 27 -- see module docstring.
#: Set generously above the realistic estimate, same reasoning as round 6's
#: own MAX_REQUESTS, so a real run fails LOUD on a genuine runaway rather
#: than being silently truncated by too-tight a cap.
MAX_REQUESTS = 50_000


def _verification_key(lead: dict[str, Any]) -> str:
    return f"{lead['anchor_ticker']}|{lead['peer_cik']}"


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"discovery": {}, "verification": {}}


def _save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    """Atomic-ish: write to a temp file then rename over the real one, so a
    process killed mid-write never leaves a truncated, unparseable
    checkpoint behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--proxy-csv", type=Path, default=RUSSELL1000_PROXY_CSV)
    ap.add_argument("--out-name-search", type=Path, default=OUT_NAME_SEARCH)
    ap.add_argument("--out-linkage", type=Path, default=OUT_LINKAGE)
    ap.add_argument("--out-raw-hits", type=Path, default=OUT_RAW_HITS)
    ap.add_argument("--checkpoint", type=Path, default=CHECKPOINT_DEFAULT,
                    help="resume progress from here after a failure -- "
                         "see module docstring, 'CHECKPOINTED'")
    a = ap.parse_args(argv)

    for p in (a.out_name_search, a.out_linkage, a.out_raw_hits):
        if p.exists():
            print(f"REFUSED: {p} already exists. Dated artifacts are "
                  "never overwritten.", file=sys.stderr)
            return 1
    if not a.proxy_csv.is_file():
        print(f"REFUSED: {a.proxy_csv} does not exist", file=sys.stderr)
        return 1

    variants, provenance = load_expanded_anchor_universe(
        hand_curated=ANCHOR_NAME_VARIANTS, proxy_csv=a.proxy_csv)
    n_hand_curated = sum(1 for v in provenance.values()
                         if v == PROVENANCE_HAND_CURATED)
    n_proxy = sum(1 for v in provenance.values()
                 if v == PROVENANCE_RUSSELL1000_PROXY)
    n_variants = sum(len(v) for v in variants.values())
    n_queries = n_variants * len(COMPETITOR_PHRASES)
    print(f"anchors: {len(variants)}  (hand_curated: {n_hand_curated}, "
          f"russell1000_proxy: {n_proxy})")
    print(f"name variants: {n_variants}   phrases: {len(COMPETITOR_PHRASES)}")
    print(f"planned unscoped searches: {n_queries} "
          f"(up to {MAX_HITS_PER_QUERY} hits kept per search)")
    print("document-fetch count depends on how many distinct peer CIKs "
          "the searches surface -- unknown until run")

    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .edgar_agreements import AgreementSearchClient

    client = AgreementSearchClient(CONTACT, max_requests=MAX_REQUESTS)

    checkpoint = _load_checkpoint(a.checkpoint)
    n_anchors_from_checkpoint = len(checkpoint["discovery"])
    n_verified_from_checkpoint = len(checkpoint["verification"])
    if n_anchors_from_checkpoint or n_verified_from_checkpoint:
        print(f"resuming from checkpoint {a.checkpoint}: "
              f"{n_anchors_from_checkpoint} anchor(s) already discovered, "
              f"{n_verified_from_checkpoint} lead(s) already verified")

    all_leads: list[dict[str, Any]] = []
    ordered = sorted(variants.items())
    for i, (anchor_ticker, name_variants) in enumerate(ordered, 1):
        cached = checkpoint["discovery"].get(anchor_ticker)
        if cached is not None:
            leads = cached
        else:
            leads = discover_leads(client, anchor_ticker, name_variants)
            for lead in leads:
                lead["anchor_variant_provenance"] = provenance[anchor_ticker]
            checkpoint["discovery"][anchor_ticker] = leads
            _save_checkpoint(a.checkpoint, checkpoint)
        all_leads.extend(leads)
        if i % 25 == 0 or i == len(ordered):
            print(f"  [{i}/{len(ordered)}] {anchor_ticker:6s}: "
                  f"{len(leads)} peer CIK(s)  (requests so far: "
                  f"{client.requests_made}, total leads so far: "
                  f"{len(all_leads)})")

    print(f"\ntotal distinct (anchor, peer_cik) leads: {len(all_leads)}")

    #: Checkpointed every VERIFICATION_SAVE_EVERY leads, not every single
    #: one: saving unconditionally rewrote the ENTIRE (and constantly
    #: growing) checkpoint file on every lead, which is O(n^2) total I/O
    #: over a run of thousands of leads -- real, if small at this scale,
    #: overhead a review pass flagged. Batching bounds a crash's data loss
    #: to at most this many not-yet-saved verifications (small, acceptable
    #: -- discovery, the more request-heavy phase, already checkpoints far
    #: more granularly, once per anchor) while cutting total checkpoint
    #: writes by the same factor.
    VERIFICATION_SAVE_EVERY = 20

    verified: list[dict[str, Any]] = []
    n_verified_this_run = 0
    for lead in all_leads:
        vkey = _verification_key(lead)
        cached_v = checkpoint["verification"].get(vkey)
        if cached_v is not None:
            verified.append(cached_v)
            continue
        v = verify_lead(client, lead)
        checkpoint["verification"][vkey] = v
        verified.append(v)
        n_verified_this_run += 1
        if n_verified_this_run % VERIFICATION_SAVE_EVERY == 0:
            _save_checkpoint(a.checkpoint, checkpoint)
        if n_verified_this_run % 200 == 0:
            print(f"  verified {n_verified_this_run} new lead(s) this run "
                  f"(requests so far: {client.requests_made})")
    if n_verified_this_run % VERIFICATION_SAVE_EVERY != 0:
        _save_checkpoint(a.checkpoint, checkpoint)

    n_confirmed = sum(1 for v in verified if v.get("filed_mention_confirmed"))
    print(f"confirmed (real, readable, competitor-shaped sentence): "
          f"{n_confirmed} / {len(verified)}")
    print(f"total requests made: {client.requests_made}")

    a.out_raw_hits.parent.mkdir(parents=True, exist_ok=True)
    a.out_raw_hits.write_text(json.dumps({
        "artifact": a.out_raw_hits.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07",
        "what_this_is": (
            "The first pass's exact mechanism (search_unscoped for [anchor "
            "name] AND [competitor phrase], classify_context plus "
            "_looks_like_competitor_sentence), run over the first pass's 27 "
            "hand-curated anchors PLUS every one of the 788 Russell1000-"
            "proxy tickers not already among them -- see module docstring."),
        "proxy_csv": str(a.proxy_csv),
        "competitor_phrases": list(COMPETITOR_PHRASES),
        "max_hits_per_query": MAX_HITS_PER_QUERY,
        "n_anchors": len(variants),
        "n_anchors_hand_curated": n_hand_curated,
        "n_anchors_russell1000_proxy": n_proxy,
        "requests_made": client.requests_made,
        "n_leads_discovered": len(verified),
        "n_confirmed": n_confirmed,
        "leads": verified,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.out_raw_hits}")

    name_search_results: list[dict[str, Any]] = []
    linkage_edges: list[dict[str, Any]] = []
    for v in verified:
        if not v.get("filed_mention_confirmed"):
            continue
        cik = v["peer_cik"]
        ticker = client.ticker_for(cik)
        if ticker is not None and ticker.upper() == v["anchor_ticker"].upper():
            # Backstop against a self-match the CIK exclusion in
            # discover_leads should already have caught -- kept as a
            # second, independent check rather than trusting one alone.
            continue
        counterparty = v["peer_registrant_name"]
        name_search_results.append({
            "counterparty": counterparty,
            "anchor_ticker": v["anchor_ticker"],
            "registrant_cik": cik,
            "peer_ticker": ticker,
            "tradeable": ticker is not None,
        })
        linkage_edges.append({
            "anchor_ticker": v["anchor_ticker"],
            "counterparty_is_named": True,
            "named_counterparty": counterparty,
            "direction": "competitor",
            "as_of_date": v["file_date"],
            "source": SOURCE_REVERSE_COMPETITOR_SEARCH,
            "evidence_sentence": v["context"],
        })

    a.out_name_search.write_text(json.dumps({
        "artifact": a.out_name_search.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07",
        "results": name_search_results,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    a.out_linkage.write_text(json.dumps({
        "artifact": a.out_linkage.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07",
        "edges": linkage_edges,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.out_name_search}")
    print(f"wrote {a.out_linkage}")

    n_tradeable = sum(1 for r in name_search_results if r["tradeable"])
    print(f"\nconfirmed: {len(name_search_results)}   tradeable: {n_tradeable}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
