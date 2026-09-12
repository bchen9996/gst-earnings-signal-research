#!/usr/bin/env python3
"""HYP-05 hand-curated peer candidates -- Pass 2.

Pass 1 (`HYP05_PEER_UNIVERSE_2026-09-12.md`) found that both automated
extraction paths (ASC 280 concentration, competitor/supplier prose --
latest-10-K and a full historical walk) structurally surface only a
filer's most PROMINENT named counterparties. HYP-05's actual question
needs smaller, less-obvious peers, which is exactly what hand curation is
for: naming a specific real-world relationship from general knowledge
rather than waiting for a filer's own prose to name it.

=== NOTHING HERE IS VERIFIED. EVERY ENTRY IS A PROPOSAL. ===

Each `ProposedCandidate` below is an assertion from general/training
knowledge, not something extracted from a filing read this session. That
is a DIFFERENT KIND of claim than everything else in this project (which
verifies against a specific filed disclosure before trusting anything),
and it is treated that way downstream:

  1. This module only lists proposals. It makes no network calls and
     writes nothing.
  2. `run_hyp05_verify_candidates.py` is the actual gate: for each
     proposal, it searches EDGAR's own full-text index for the exact
     counterparty name INSIDE the anchor's own 10-K filings. Only a real,
     citable hit -- with a real accession number, filing date, and the
     actual sentence it appears in -- lets a candidate through.
  3. A proposal with no full-text hit is reported as `filed_mention_
     confirmed: false` and goes NO FURTHER. It is not treated as false
     (the relationship may be real but never disclosed by name in a
     10-K), just as unconfirmed by this pass's evidence standard -- the
     same "unanswered is not a negative" discipline this project already
     applies to failed name searches.
  4. A confirmed full-text hit is evidence a company was NAMED near the
     anchor in a real filing. It is NOT independent confirmation of the
     specific `direction` (competitor/supplier/customer) claimed below --
     that classification is still mine. The context sentence captured by
     the verification step is included in its output specifically so
     that claim can be read and judged, not just trusted.

`direction` is one of "competitor", "supplier", "customer" (the same
vocabulary `edgar_linkage.py`'s extractor already uses). `basis` is a
one-line, honest note on why the candidate was proposed -- never a
claim of certainty, and never something written after seeing a
verification result (this list existed before the first verification
request was made).
"""
from __future__ import annotations

from typing import NamedTuple


class ProposedCandidate(NamedTuple):
    anchor_ticker: str
    counterparty_name: str
    direction: str
    basis: str


# Deliberately favouring companies believed to be SMALLER than the ones
# every automated pass already found (AMD, Samsung, Micron, SK Hynix,
# GlobalFoundries, SMIC, UMC, CVS Health) -- that skew-to-large result is
# exactly what this pass exists to counteract. Some of these will turn out
# wrong (never publicly traded, wrong legal name, no SEC registration, or
# simply never named in the anchor's own 10-K) -- that is what the
# verification step in run_hyp05_verify_candidates.py is for.
PROPOSED_CANDIDATES: tuple[ProposedCandidate, ...] = (
    # ---- ADBE (Adobe) ----
    ProposedCandidate("ADBE", "Shutterstock", "competitor",
                       "Stock-content/creative-asset rival to Adobe Stock; "
                       "publicly traded (SSTK), smaller than Adobe."),
    ProposedCandidate("ADBE", "Figma", "competitor",
                       "Design-tool competitor; Adobe attempted to acquire "
                       "Figma (deal blocked by regulators), Figma later "
                       "IPO'd independently."),
    ProposedCandidate("ADBE", "Smartsheet", "competitor",
                       "Work-management SaaS, adjacent to Adobe's "
                       "creative-collaboration/Workfront line."),

    # ---- CTSH (Cognizant) ----
    ProposedCandidate("CTSH", "Syntel", "competitor",
                       "Smaller IT-services/BPO competitor to Cognizant; "
                       "later acquired by Atos (2018)."),
    ProposedCandidate("CTSH", "Virtusa", "competitor",
                       "Smaller IT-services competitor to Cognizant; later "
                       "taken private (2021)."),
    ProposedCandidate("CTSH", "WNS", "competitor",
                       "Business-process-management competitor, smaller "
                       "than Cognizant."),
    ProposedCandidate("CTSH", "ExlService", "competitor",
                       "BPO/analytics-services competitor, smaller than "
                       "Cognizant."),
    ProposedCandidate("CTSH", "Mastech Digital", "competitor",
                       "IT-staffing competitor, materially smaller than "
                       "Cognizant."),

    # ---- INTC (Intel) ----
    ProposedCandidate("INTC", "MaxLinear", "competitor",
                       "Smaller semiconductor (networking/connectivity "
                       "chip) competitor to parts of Intel's product line."),
    ProposedCandidate("INTC", "Ambarella", "competitor",
                       "Smaller semiconductor (edge-AI/vision chip) "
                       "competitor to parts of Intel's product line."),
    ProposedCandidate("INTC", "Ichor", "supplier",
                       "Semiconductor-fab-equipment subsystem supplier; "
                       "smaller company plausibly in Intel's supply chain."),
    ProposedCandidate("INTC", "Ultra Clean Holdings", "supplier",
                       "Semiconductor-equipment/services supplier; smaller "
                       "company plausibly in Intel's supply chain."),
    ProposedCandidate("INTC", "Kulicke", "supplier",
                       "Semiconductor packaging/assembly equipment maker "
                       "(Kulicke & Soffa); smaller company plausibly in "
                       "Intel's supply chain."),

    # ---- JBL (Jabil) ----
    ProposedCandidate("JBL", "iRobot", "customer",
                       "Consumer-robotics company that has historically "
                       "outsourced manufacturing; small-cap."),
    ProposedCandidate("JBL", "GoPro", "customer",
                       "Consumer-hardware company that outsources "
                       "manufacturing; small-cap."),
    ProposedCandidate("JBL", "Sonos", "customer",
                       "Consumer-hardware company that outsources "
                       "manufacturing; small/mid-cap."),
    ProposedCandidate("JBL", "Fossil Group", "customer",
                       "Consumer wearables/watch company that outsources "
                       "manufacturing; small-cap."),
    ProposedCandidate("JBL", "Cricut", "customer",
                       "Consumer-hardware company that outsources "
                       "manufacturing; small/mid-cap."),

    # ---- MCK (McKesson) ----
    ProposedCandidate("MCK", "Diplomat Pharmacy", "customer",
                       "Smaller specialty-pharmacy distribution customer; "
                       "later acquired by OptumRx (2020)."),
    ProposedCandidate("MCK", "PharMerica", "customer",
                       "Smaller long-term-care pharmacy distribution "
                       "customer."),
    ProposedCandidate("MCK", "BioScrip", "customer",
                       "Smaller specialty/home-infusion pharmacy "
                       "distribution customer; later merged into Option "
                       "Care Health (2019)."),

    # ---- NKE (Nike) ----
    ProposedCandidate("NKE", "Allbirds", "competitor",
                       "Smaller, directly competing athletic-footwear "
                       "company; small-cap."),
    ProposedCandidate("NKE", "Wolverine World Wide", "competitor",
                       "Smaller footwear company (owns Merrell, Sperry); "
                       "small/mid-cap."),
    ProposedCandidate("NKE", "Under Armour", "competitor",
                       "Athletic-apparel competitor; once large, "
                       "materially smaller today -- worth checking at "
                       "specific anchor-event dates rather than assumed "
                       "either way."),

    # ---- NVDA (Nvidia) ----
    ProposedCandidate("NVDA", "Ambarella", "competitor",
                       "Smaller edge-AI/vision-chip competitor to parts of "
                       "Nvidia's product line."),
    ProposedCandidate("NVDA", "Astera Labs", "supplier",
                       "AI-data-center connectivity-chip company, adjacent "
                       "to Nvidia's own supply/ecosystem; recently IPO'd, "
                       "market cap uncertain -- worth checking rather than "
                       "assumed either way."),
)
