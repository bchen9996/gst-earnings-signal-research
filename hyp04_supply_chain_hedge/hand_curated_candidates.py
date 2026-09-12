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


# ==========================================================================
# ROUND 2 -- appended after Pass 2's first live run confirmed 6 of the 26
# proposals above and qualified one real peer (AMBA/NVDA). This batch
# widens coverage rather than re-litigating round 1: round-1 entries above
# are left exactly as written.
#
# Three of these (Marvell Technology Group, Mobileye, STMicroelectronics
# for NVDA; Puma, Li Ning, Crocs for NKE) are not blind proposals -- they
# were read directly in the ACTUAL filed context sentences round 1's
# verification step already captured and committed
# (HYP05_HAND_CURATED_VERIFICATION_2026-09-12.json): NVDA's own 10-K names
# "...Ambarella, Inc., AMD, Apple, Inc., Avago Technologies Ltd., Intel,
# Marvell Technology Group Ltd., Mediatek, Mobileye N.V., Qualcomm
# Incorporated, Renesas Electronics Corporation, Samsung, ST
# Microelectronics, and Texas Instruments..." as SOC-product competitors,
# and NKE's own 10-K names "...Corp., Puma, Li Ning and Under Armour..."
# as apparel/footwear competitors, with Crocs (like Wolverine World Wide)
# co-listed in the Dow Jones U.S. Footwear Index performance-graph table
# rather than a competition-section sentence -- same weak-evidence caveat
# as Wolverine applies to Crocs specifically. These six still go through
# the same full-text re-verification step as everything else (a name
# already seen in one filing must still resolve to a real, continuous
# registrant, and this script's own job is to fetch the citable accession,
# not to shortcut on a memory of what was read once).
# ==========================================================================
PROPOSED_CANDIDATES = PROPOSED_CANDIDATES + (
    # ---- ADBE (Adobe) ----
    ProposedCandidate("ADBE", "Box", "competitor",
                       "Cloud content-management company, adjacent to "
                       "Adobe Document Cloud; small/mid-cap."),
    ProposedCandidate("ADBE", "DocuSign", "competitor",
                       "E-signature competitor to Adobe Acrobat Sign; "
                       "market cap has fallen sharply since 2021, worth "
                       "checking at specific dates rather than assumed."),
    ProposedCandidate("ADBE", "Wix.com", "competitor",
                       "Website-building competitor, adjacent to Adobe's "
                       "web-design tools."),
    ProposedCandidate("ADBE", "Squarespace", "competitor",
                       "Website-building competitor, adjacent to Adobe's "
                       "web-design tools; later taken private (2024)."),
    ProposedCandidate("ADBE", "Monotype", "competitor",
                       "Typography/font company, adjacent to Adobe Fonts; "
                       "later taken private (2019)."),
    ProposedCandidate("ADBE", "Asana", "competitor",
                       "Work-management software, adjacent to Adobe "
                       "Workfront; market cap has at times been under $2B."),

    # ---- CTSH (Cognizant) ----
    ProposedCandidate("CTSH", "Perficient", "competitor",
                       "Smaller digital/IT consulting competitor to "
                       "Cognizant; small-cap."),
    ProposedCandidate("CTSH", "Endava", "competitor",
                       "Smaller IT-services competitor to Cognizant."),
    ProposedCandidate("CTSH", "Globant", "competitor",
                       "IT-services/digital competitor to Cognizant; "
                       "smaller historically than today."),
    ProposedCandidate("CTSH", "iGate", "competitor",
                       "Smaller IT-services competitor to Cognizant; "
                       "later acquired by Capgemini (2015)."),
    ProposedCandidate("CTSH", "Sapient", "competitor",
                       "Smaller digital/IT consulting competitor to "
                       "Cognizant; later acquired by Publicis (2015)."),

    # ---- INTC (Intel) ----
    ProposedCandidate("INTC", "Lattice Semiconductor", "competitor",
                       "Smaller FPGA semiconductor competitor to parts of "
                       "Intel's product line."),
    ProposedCandidate("INTC", "Cirrus Logic", "competitor",
                       "Smaller analog-semiconductor competitor to parts "
                       "of Intel's product line."),
    ProposedCandidate("INTC", "Synaptics", "competitor",
                       "Smaller semiconductor (human-interface chip) "
                       "competitor to parts of Intel's product line."),
    ProposedCandidate("INTC", "Diodes Incorporated", "competitor",
                       "Small-cap discrete/analog semiconductor company, "
                       "plausible competitor in some product lines."),
    ProposedCandidate("INTC", "Axcelis Technologies", "supplier",
                       "Semiconductor-fab ion-implantation equipment "
                       "maker; smaller company plausibly in Intel's supply "
                       "chain."),
    ProposedCandidate("INTC", "Nova Ltd", "supplier",
                       "Semiconductor metrology/inspection equipment "
                       "maker; smaller company plausibly in Intel's supply "
                       "chain."),
    ProposedCandidate("INTC", "FormFactor", "supplier",
                       "Semiconductor wafer-test equipment maker; smaller "
                       "company plausibly in Intel's supply chain."),
    ProposedCandidate("INTC", "Veeco Instruments", "supplier",
                       "Semiconductor-process equipment maker; smaller "
                       "company plausibly in Intel's supply chain."),

    # ---- JBL (Jabil) ----
    ProposedCandidate("JBL", "Vizio", "customer",
                       "Consumer-electronics (TV) company that has used "
                       "contract manufacturing; small/mid-cap; later "
                       "acquired by Walmart (2024)."),
    ProposedCandidate("JBL", "Turtle Beach", "customer",
                       "Consumer-hardware (gaming headset) company that "
                       "outsources manufacturing; small-cap."),
    ProposedCandidate("JBL", "Nautilus", "customer",
                       "Fitness-equipment company that outsources "
                       "manufacturing; small-cap."),
    ProposedCandidate("JBL", "Tandem Diabetes Care", "customer",
                       "Medical-device company; Jabil has a real medical-"
                       "device contract-manufacturing business, worth "
                       "checking rather than assumed."),

    # ---- MCK (McKesson) ----
    ProposedCandidate("MCK", "Rite Aid", "customer",
                       "Major US pharmacy chain; McKesson has been a "
                       "longtime pharmaceutical-distribution partner, "
                       "but the exact wholesaler relationship at any "
                       "given date is worth checking rather than assumed."),
    ProposedCandidate("MCK", "Owens & Minor", "customer",
                       "Medical/surgical supply distributor, adjacent "
                       "sector to McKesson's pharma distribution; "
                       "small/mid-cap."),
    ProposedCandidate("MCK", "Option Care Health", "customer",
                       "Home-infusion pharmacy company formed from the "
                       "2019 BioScrip merger; worth checking rather than "
                       "assumed."),

    # ---- NKE (Nike) ----
    ProposedCandidate("NKE", "Deckers Outdoor", "competitor",
                       "Footwear company (UGG, Hoka); was materially "
                       "smaller historically than its recent market cap."),
    ProposedCandidate("NKE", "Genesco", "competitor",
                       "Small-cap footwear retailer/wholesaler (Journeys, "
                       "Schuh)."),
    ProposedCandidate("NKE", "Columbia Sportswear", "competitor",
                       "Mid-cap outdoor-apparel competitor."),
    ProposedCandidate("NKE", "Skechers", "competitor",
                       "Athletic-footwear competitor; mid-cap."),
    ProposedCandidate("NKE", "Steven Madden", "competitor",
                       "Footwear competitor; mid-cap."),
    ProposedCandidate("NKE", "Caleres", "competitor",
                       "Small-cap footwear company (formerly Brown Shoe "
                       "Company)."),
    ProposedCandidate("NKE", "Rocky Brands", "competitor",
                       "Small-cap footwear company."),
    ProposedCandidate("NKE", "Puma", "competitor",
                       "Directly read in NKE's own 10-K competitor "
                       "sentence during round-1 verification (\"...Corp., "
                       "Puma, Li Ning and Under Armour, among others.\"); "
                       "not previously proposed as its own candidate."),
    ProposedCandidate("NKE", "Li Ning", "competitor",
                       "Directly read in the same NKE 10-K sentence as "
                       "Puma (see above); Chinese company, US SEC "
                       "registration status genuinely unknown -- worth "
                       "checking rather than assumed."),
    ProposedCandidate("NKE", "Crocs", "competitor",
                       "Co-listed with Wolverine World Wide in the same "
                       "Dow Jones U.S. Footwear Index performance-graph "
                       "table round 1 found -- same weak-evidence caveat "
                       "as Wolverine applies here, not a competition-"
                       "section claim."),

    # ---- NVDA (Nvidia) ----
    ProposedCandidate("NVDA", "Mobileye", "competitor",
                       "Directly read in NVDA's own 10-K competitor "
                       "sentence during round-1 verification. Was public "
                       "(NYSE: MBLY) from its 2014 IPO until Intel's 2017 "
                       "acquisition, then re-IPO'd independently in 2022 "
                       "-- a genuinely interesting lineage case for the "
                       "point-in-time test."),
    ProposedCandidate("NVDA", "Marvell Technology Group", "competitor",
                       "Directly read in NVDA's own 10-K competitor "
                       "sentence during round-1 verification; likely too "
                       "large to pass the market-cap threshold, included "
                       "for completeness rather than because it's "
                       "expected to qualify."),
    ProposedCandidate("NVDA", "ST Microelectronics", "competitor",
                       "Directly read in NVDA's own 10-K competitor "
                       "sentence during round-1 verification; likely too "
                       "large to pass the market-cap threshold, included "
                       "for completeness rather than because it's "
                       "expected to qualify."),
    ProposedCandidate("NVDA", "Cerence", "competitor",
                       "Automotive AI/voice company spun off from Nuance "
                       "(2019); adjacent to Nvidia's automotive Drive "
                       "platform; small-cap."),
    ProposedCandidate("NVDA", "Credo Technology", "supplier",
                       "AI-data-center connectivity-chip company, "
                       "adjacent to Nvidia's own supply/ecosystem (same "
                       "category as Astera Labs above); recently IPO'd."),
    ProposedCandidate("NVDA", "indie Semiconductor", "competitor",
                       "Small-cap automotive-chip company, plausible "
                       "competitor in Nvidia's automotive segment."),
)


# ==========================================================================
# ROUND 3 -- a different METHOD, not just more of round 2's. Rounds 1-2
# mostly guessed "a smaller company in the same industry" and hoped it was
# named; the hit rate for that kind of guess was low (INTC: 0 of 10
# proposed competitors/suppliers confirmed across both rounds, with no
# rich sentence found to mine -- deliberately NOT extended further here,
# since there's no specific citable reason left to try, only more
# guessing). This round instead MINES real sentences round 1-2's own
# verification already confirmed and captured, for names not yet
# proposed as their own candidates -- a specific, citable reason for
# every entry, not a size-matched guess:
#
#   * NKE's own 2002 10-K "BY WAY OF ILLUSTRATION ONLY, examples of NIKE
#     competitors include..." sentence names 23 companies; only three
#     (Puma, Li Ning were read from a different, later sentence; Columbia
#     Sportswear) had been proposed before this round.
#   * CTSH's own 2007 10-K "Peer Group Index of other information
#     technology consulting firms" sentence names 12 companies; only
#     three (iGate, Sapient, Syntel) had been proposed before this round.
#   * NVDA's own 10-K competitor sentences (2007, 2015) name several
#     companies not yet proposed (Freescale Semiconductor, Imagination
#     Technologies, ARM Holdings).
#   * ADBE's own 10-K names Citrix in the same sentence as the already-
#     confirmed DocuSign.
#   * JBL's own 2017 10-K "our largest customers include..." sentence
#     names two more real, ADR-listed companies (Ericsson, Nokia) --
#     both very likely too large, included for completeness the same way
#     Marvell/ST Microelectronics were in round 2, not because they're
#     expected to qualify.
#   * MCK's own 2001 receivables-purchase-agreement exhibit -- the SAME
#     real document Rite Aid's round-2 evidence came from -- names
#     Albertson's (American Stores and Osco Drug) as a "Special Obligor"
#     alongside Rite Aid and CVS, read directly by fetching and reading
#     the fuller document rather than guessing (Wal-Mart, also named
#     there, is excluded -- always too large to be worth a request).
#
# Several of the NKE names below were real, independently public
# companies at the time (2002) that were LATER acquired or taken private
# (Reebok by Adidas 2006, Oakley by Luxottica 2007, Converse by NIKE
# itself 2003, Saucony by Stride Rite 2005, Tommy Hilfiger Corp by Apparel
# Corp/PVH 2010, Sports Authority by KKR 2006 then bankrupt 2016) -- real
# history, not a defect in the proposal; the lineage/tradeability test
# will report each honestly.
# ==========================================================================
PROPOSED_CANDIDATES = PROPOSED_CANDIDATES + (
    # ---- NKE (Nike) -- mined from the real 2002 10-K sentence ----
    ProposedCandidate("NKE", "Reebok", "competitor",
                       "Named in NKE's own 2002 10-K 'examples of NIKE "
                       "competitors' sentence. Was independently US-"
                       "listed (Reebok International Ltd) until Adidas "
                       "acquired it in 2006."),
    ProposedCandidate("NKE", "Oakley", "competitor",
                       "Named in the same NKE sentence. Was "
                       "independently US-listed (NYSE: OO) until "
                       "Luxottica acquired it in 2007; historically a "
                       "small/mid-cap."),
    ProposedCandidate("NKE", "Converse", "competitor",
                       "Named in the same NKE sentence. Was "
                       "independently US-listed until NIKE itself "
                       "acquired Converse in 2003 -- interesting "
                       "specifically because NKE's own 10-K names its "
                       "own future acquisition target as a competitor."),
    ProposedCandidate("NKE", "Saucony", "competitor",
                       "Named in the same NKE sentence. Was "
                       "independently US-listed (Nasdaq: SCNY) until "
                       "Stride Rite acquired it in 2005; small-cap."),
    ProposedCandidate("NKE", "Tommy Hilfiger", "competitor",
                       "Named in the same NKE sentence. Tommy Hilfiger "
                       "Corporation was independently US-listed (NYSE: "
                       "TOM) until Apparel Corp/PVH acquired it in 2010."),
    ProposedCandidate("NKE", "Foot Locker", "customer",
                       "Originally proposed as a competitor (named in "
                       "the same NKE sentence as 'Venator "
                       "(Footlockers)'), but round-3 verification found "
                       "the real, genuine evidence is a DIFFERENT, "
                       "stronger sentence -- a real customer-"
                       "concentration disclosure: 'Foot Locker, Inc. ... "
                       "accounted for approximately 11 percent of global "
                       "net sales of NIKE brand products during fiscal "
                       "2002.' Corrected to 'customer' to match what the "
                       "filed text actually says, not the original "
                       "guess. Real, currently-trading company, market "
                       "cap has been volatile enough to dip near or "
                       "below $2B at various points."),
    ProposedCandidate("NKE", "Sports Authority", "competitor",
                       "Named in the same NKE sentence. The Sports "
                       "Authority, Inc. was independently US-listed "
                       "(NYSE: TSA) until taken private (KKR) in 2006, "
                       "later bankrupt in 2016; historically small/"
                       "mid-cap."),
    ProposedCandidate("NKE", "Callaway Golf", "competitor",
                       "Named in the same NKE sentence. Independently "
                       "US-listed (NYSE: ELY, now Topgolf Callaway "
                       "Brands); golf-equipment niche, historically "
                       "small/mid-cap."),
    ProposedCandidate("NKE", "Titleist", "competitor",
                       "Named in the same NKE sentence. Titleist's "
                       "parent, Acushnet Company, did not IPO "
                       "independently (Acushnet Holdings Corp, NYSE: "
                       "GOLF) until 2016 -- well after this 2002 filing, "
                       "so this is expected to fail the disclosure-date "
                       "lineage test rather than qualify; included for "
                       "an honest, complete accounting of the sentence."),
    ProposedCandidate("NKE", "Adidas", "competitor",
                       "Named in the same NKE sentence. German company; "
                       "US SEC registration status genuinely unknown -- "
                       "worth checking rather than assumed."),
    ProposedCandidate("NKE", "FILA", "competitor",
                       "Named in the same NKE sentence. US SEC "
                       "registration status genuinely unknown -- worth "
                       "checking rather than assumed."),
    ProposedCandidate("NKE", "DKNY", "competitor",
                       "Named in the same NKE sentence. Donna Karan "
                       "International was independently US-listed until "
                       "LVMH acquired it in a deal that closed shortly "
                       "before this filing -- likely to fail the "
                       "disclosure-date lineage test, included for a "
                       "complete accounting of the sentence."),
    ProposedCandidate("NKE", "Asics", "competitor",
                       "Named in the same NKE sentence. Japanese "
                       "company; US SEC registration status genuinely "
                       "unknown -- worth checking rather than assumed."),
    ProposedCandidate("NKE", "Umbro", "competitor",
                       "Named in the same NKE sentence. UK company; US "
                       "SEC registration status genuinely unknown -- "
                       "worth checking rather than assumed."),

    # ---- CTSH (Cognizant) -- mined from the real 2007 10-K sentence ----
    ProposedCandidate("CTSH", "Computer Horizons", "competitor",
                       "Named in CTSH's own 2007 10-K 'Peer Group Index "
                       "of other information technology consulting "
                       "firms' sentence. Computer Horizons Corp was a "
                       "real, small-cap IT-staffing/services company, "
                       "later dissolved (~2007)."),
    ProposedCandidate("CTSH", "Computer Task Group", "competitor",
                       "Named in the same CTSH sentence. Computer Task "
                       "Group, Inc. (CTG) was a real, small-cap Nasdaq-"
                       "listed IT-services company, later acquired by "
                       "Cegeka (2023)."),
    ProposedCandidate("CTSH", "Covansys", "competitor",
                       "Named in the same CTSH sentence. Covansys "
                       "Corporation was a real, small-cap IT-services "
                       "company, later acquired by CSC (2007)."),
    ProposedCandidate("CTSH", "Diamond Cluster", "competitor",
                       "Named in the same CTSH sentence. DiamondCluster "
                       "International, Inc. was a real, small-cap "
                       "management/IT-consulting firm."),
    ProposedCandidate("CTSH", "Keane", "competitor",
                       "Named in the same CTSH sentence. Keane, Inc. was "
                       "a real, small-cap IT-services company, later "
                       "acquired by Caritor (2007)."),

    # ---- NVDA (Nvidia) -- mined from the real competitor sentences ----
    ProposedCandidate("NVDA", "Freescale Semiconductor", "competitor",
                       "Named in NVDA's own 2007 10-K competitor "
                       "sentence. Was independently NYSE-listed (FSL) "
                       "2011-2015 before merging into NXP "
                       "Semiconductors; smaller-mid-cap during its "
                       "independent years."),
    ProposedCandidate("NVDA", "Imagination Technologies", "competitor",
                       "Named in the same NVDA sentence. UK company "
                       "(LSE: IMG), taken private in 2017; US SEC "
                       "registration status genuinely unknown -- worth "
                       "checking rather than assumed."),
    ProposedCandidate("NVDA", "ARM Holdings", "competitor",
                       "Named in the same NVDA sentence. Was "
                       "independently public until SoftBank acquired it "
                       "in 2016, then re-IPO'd in 2023 (Nasdaq: ARM) -- "
                       "the 2007 as_of_date predates any US listing, so "
                       "this is expected to fail the disclosure-date "
                       "lineage test; included for a complete accounting "
                       "of the sentence."),

    # ---- ADBE (Adobe) -- mined from the real DocuSign sentence ----
    ProposedCandidate("ADBE", "Citrix", "competitor",
                       "Named in the same ADBE sentence as the already-"
                       "confirmed DocuSign ('DocuSign, Citrix, and "
                       "others are incorporating competitive e-"
                       "signature...'). Citrix Systems, Inc. was "
                       "independently NYSE-listed until taken private "
                       "in 2022; likely too large to pass the market-cap "
                       "threshold, included for completeness."),

    # ---- JBL (Jabil) -- mined from the real GoPro customer sentence ----
    ProposedCandidate("JBL", "LM Ericsson", "customer",
                       "Named in the same JBL 'our largest customers "
                       "include...' sentence as the already-confirmed "
                       "GoPro. Telefonaktiebolaget LM Ericsson trades as "
                       "an ADR (ERIC); likely too large to pass the "
                       "market-cap threshold, included for completeness."),
    ProposedCandidate("JBL", "Nokia Networks", "customer",
                       "Named in the same JBL sentence. Nokia "
                       "Corporation trades as an ADR (NOK); likely too "
                       "large to pass the market-cap threshold, included "
                       "for completeness."),

    # ---- MCK (McKesson) -- mined from the real receivables-purchase-
    # agreement document (the SAME filing Rite Aid's round-2 evidence
    # came from; read in full rather than guessed) ----
    ProposedCandidate("MCK", "Albertson's", "customer",
                       "Named as a 'Special Obligor' alongside Rite Aid "
                       "and CVS Corp. in MCK's own 2001 receivables-"
                       "purchase-agreement exhibit. Albertsons Companies "
                       "has a complex real history (went private 2006, "
                       "re-IPO'd as ACI in 2020) -- worth checking "
                       "rather than assumed."),
    ProposedCandidate("MCK", "American Stores", "customer",
                       "Named parenthetically alongside Albertson's in "
                       "the same MCK exhibit ('Albertson's (American "
                       "Stores and Osco Drug)'). American Stores Company "
                       "was a real, independently US-listed company "
                       "before Albertson's acquired it in 1999 -- likely "
                       "to fail the disclosure-date lineage test given "
                       "this 2001 filing postdates that acquisition, "
                       "included for a complete accounting of the "
                       "exhibit."),
    ProposedCandidate("MCK", "Osco Drug", "customer",
                       "Named in the same parenthetical as American "
                       "Stores above. A drugstore chain/brand, not "
                       "independently SEC-registered as far as is known "
                       "-- worth checking rather than assumed."),
)
