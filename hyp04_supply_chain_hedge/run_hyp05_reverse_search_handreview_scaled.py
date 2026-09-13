#!/usr/bin/env python3
"""Hand review of the SCALED reverse-concentration search's 277 raw
confirmed leads (HYP05_REVERSE_SEARCH_RAW_HITS_SCALED_2026-09-13.json).

Same discipline as run_hyp05_reverse_search_handreview.py (round 4): every
sentence was actually read, not sampled. NOT the same Decision/apply_review
shape, for one real reason found while doing this at scale -- see below.

=== WHY KEYED BY (anchor_ticker, peer_cik), NOT peer_cik ALONE ===

Round 4's Decision keyed by peer_cik alone, which is safe only if no peer
CIK appears under two different anchors. That held for round 4's 17 leads
by luck, not by design. At 277 leads it breaks for real: CIK 0001113481
(The Medicines Company) is a genuine McKesson (MCK) supplier AND a false
positive under Franklin Resources (BEN, an institutional-ownership-table
mismatch) -- one CIK, two anchors, two different correct answers. Keying
by (anchor_ticker, peer_cik) is the direct fix; round 4's own module is
untouched since its data never needed this.

=== NEW FALSE-POSITIVE GENRES FOUND AT THIS SCALE ===

Round 4 already knew: bond-coupon rate, market-share-among-competitors,
name collision, wrong-schema JV ownership. This pass found several more,
each because a NEW kind of anchor was searched for the first time:

  INST_OWN   Anchor is an asset manager (BlackRock/BLK, Ameriprise/AMP,
             Franklin Resources/BEN, Invesco/IVZ, Janus Henderson/JHG,
             T. Rowe Price/TROW, Prudential/PRU, Raymond James/RJF) whose
             name appears in the FILER'S OWN beneficial-ownership /
             5%-stockholder table -- the asset manager owns shares in the
             filer, which is not a customer or supplier relationship.
             Overwhelmingly the largest single false-positive category.
  SOFR       Anchor is CME Group, cited only as the administrator of the
             Term SOFR benchmark rate in an unrelated loan agreement.
  DEBT       Anchor is a bank/lender (Ally, BNY Mellon, U.S. Bank) named
             as a lender, bond trustee, or rate reference, not a
             commercial counterparty.
  JV         A stated ownership PERCENTAGE in a joint venture or
             subsidiary -- a real relationship, wrong schema (same
             category round 4 found once for Micron/INTC).
  SANCTIONS  Iran Threat Reduction Act boilerplate: SEVEN unrelated Apollo
             portfolio companies' 10-Ks recite the IDENTICAL mandated
             sentence about ANOTHER Apollo holding (LyondellBasell)
             because they share a private-equity sponsor, not a business
             relationship with LyondellBasell itself.
  REIT       A shopping-center/REIT filing listing which retailers
             physically occupy ("anchor") a property -- a leasing
             directory, not a revenue-concentration disclosure.
  MKTSHARE   Same as round 4's genre: the anchor named as a rival with a
             market-share percentage, not a customer/supplier.
  AGG        A percentage is real but is a COMBINED total across several
             named companies with no anchor-specific breakout (e.g. "top
             five customers accounted for 15%") -- cannot attribute a
             concentration to this anchor specifically.
  BELOW10    An anchor-specific percentage IS given but is below the 10%
             ASC-280 materiality bar this project uses elsewhere
             (anchor_universe.CONCENTRATION_THRESHOLD_PCT) -- applied here
             for the same reason, not a false positive but immaterial.
  MA         A one-time acquisition/merger announcement, not an ongoing
             relationship.
  COMPPEER   An executive-compensation stock-performance peer-group table.
  NOISE      The extracted sentence window contains no readable
             relationship to the named anchor at all (garbled XBRL tags,
             an unrelated table, a name-collision on a common word like
             "target", or a same-corporate-family subsidiary CIK that the
             anchor-CIK self-match guard did not catch).

=== DIRECTION ===

Corrected by hand, per sentence, exactly as round 4 did -- the raw
extractor hardcodes "customer" for every hit. `direction` is the PEER's
role: "supplier" means the peer sells to the anchor; "customer" means the
peer buys from the anchor.

Run: python -m hyp04_supply_chain_hedge.run_hyp05_reverse_search_handreview_scaled --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple, Optional

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-13"
RAW_HITS_JSON = LSE / "HYP05_REVERSE_SEARCH_RAW_HITS_SCALED_2026-09-13.json"
OUT_NAME_SEARCH = LSE / f"HYP05_PEER_NAME_SEARCH_REVERSE_SEARCH_SCALED_HANDREVIEWED_{AS_OF}.json"
OUT_LINKAGE = LSE / f"HYP05_CANDIDATE_LINKAGE_REVERSE_SEARCH_SCALED_HANDREVIEWED_{AS_OF}.json"

SOURCE_HANDREVIEWED = "EDGAR_10K_FULLTEXT_REVERSE_CONCENTRATION_SEARCH_SCALED_HAND_REVIEWED"

REJECT_CATEGORIES = frozenset({
    "INST_OWN", "SOFR", "DEBT", "JV", "SANCTIONS", "REIT", "MKTSHARE",
    "AGG", "BELOW10", "MA", "COMPPEER", "NOISE",
})


class Decision(NamedTuple):
    anchor_ticker: str
    peer_cik: str
    keep: bool
    direction: Optional[str]   # only meaningful when keep is True
    category: str              # "KEEP" or one of REJECT_CATEGORIES
    note: str = ""              # peer-specific detail beyond the category


class HandReviewError(RuntimeError):
    pass


#: One entry per raw confirmed (anchor, peer_cik) lead. A control test
#: asserts this set matches the real raw file's confirmed set exactly.
SCALED_HAND_REVIEW_DECISIONS: tuple[Decision, ...] = (
    Decision("AAPL", "0001441634", True, "supplier", "KEEP", "Avago -- round4 dup"),
    Decision("AAPL", "0001201663", True, "supplier", "KEEP", "Audience Inc -- round4 dup"),
    Decision("ABBV", "0000882104", False, None, "NOISE", "PDL Biopharma bond coupon -- round4 dup"),
    Decision("ABNB", "0001893311", False, None, "AGG", "LuxUrban: 90% via 4 combined platforms, no Airbnb-specific %"),
    Decision("ABT", "0000883984", True, "supplier", "KEEP", "ICU Medical: largest customer Abbott 57%"),
    Decision("ADSK", "0000852437", True, "customer", "KEEP", "Avatech resells Autodesk software, buys from Autodesk"),
    Decision("AEIS", "0001114973", True, "supplier", "KEEP", "Advanced Power Tech: AEIS 17% of net sales"),
    Decision("AEIS", "0001316656", False, None, "NOISE", "Dresser-Rand: tax-rate table, no AEIS content"),
    Decision("AEP", "0000721447", False, None, "NOISE", "CCA Industries: own investment-portfolio holdings table"),
    Decision("AEP", "0001065059", True, "supplier", "KEEP", "Centrus Energy: AEP 12% of LEU segment revenue"),
    Decision("AES", "0000945436", False, None, "JV", "SunEdison/AES Solar equity ownership interest"),
    Decision("AFG", "0001128725", False, None, "NOISE", "InterCloud Systems: stockholder table, no AFG content"),
    Decision("ALLY", "0000949852", False, None, "DEBT", "Thanksgiving Coffee: loan payable to Ally, not customer/supplier"),
    Decision("ALLY", "0000825324", False, None, "DEBT", "Good Times Restaurants: notes payable to Ally"),
    Decision("AMAT", "0001160513", True, "supplier", "KEEP", "Suntron: AMAT 22% of net sales"),
    Decision("AMAT", "0000046709", True, "supplier", "KEEP", "Helix Technology: AMAT 21% of net sales"),
    Decision("AMGN", "0001037975", True, "customer", "KEEP", "Priority Healthcare: text calls Amgen 'a supplier' -- peer is Amgen's customer"),
    Decision("AMP", "0001386198", False, None, "NOISE", "MEMSIC: VC ownership table, no AMP content"),
    Decision("AMP", "0001362491", False, None, "INST_OWN", "Metals USA: Ameriprise 5.3% beneficial owner"),
    Decision("AMP", "0000822663", False, None, "INST_OWN", "Inter Parfums: Ameriprise 6.0% beneficial owner"),
    Decision("AMP", "0001825480", False, None, "INST_OWN", "Poshmark: Ameriprise 7.4% beneficial owner"),
    Decision("AMP", "0001471038", False, None, "INST_OWN", "Global Defense Tech: Ameriprise 10.42% beneficial owner"),
    Decision("AMP", "0001002638", False, None, "INST_OWN", "Open Text: Ameriprise 6.53% beneficial owner"),
    Decision("AMP", "0001270400", False, None, "INST_OWN", "Telewest Global: Ameriprise 11.4% beneficial owner"),
    Decision("AMT", "0000826773", True, "supplier", "KEEP", "Berliner Communications: AMT is largest of several >5% customers"),
    Decision("APD", "0000804212", True, "customer", "KEEP", "Airgas: Air Products supplies 35% of gas requirements TO Airgas"),
    Decision("APD", "0001158062", True, "customer", "KEEP", "Red-D-Arc: same Air Products supply agreement"),
    Decision("APO", "0001361394", False, None, "INST_OWN", "Affinion Group Holdings: Apollo funds own 97% of Holdings' stock"),
    Decision("ARES", "0001507079", False, None, "INST_OWN", "Floor & Decor: Ares owns 12.1% of Class A stock"),
    Decision("ARMK", "0000040528", True, "supplier", "KEEP", "Aduromed: sales derived FROM Aramark, Aduromed is supplier"),
    Decision("ARW", "0000768251", True, "supplier", "KEEP", "Altera: distributor Arrow Electronics >10% of sales"),
    Decision("ARW", "0000791915", True, "supplier", "KEEP", "Cypress Semiconductor: distributor Arrow 10% of revenues"),
    Decision("AVT", "0000791915", True, "supplier", "KEEP", "Cypress Semiconductor: distributor Avnet 17% of AR"),
    Decision("AVT", "0001173752", True, "supplier", "KEEP", "Aruba Networks: channel partner Avnet Logistics 14.1%"),
    Decision("AVY", "0001114995", True, "supplier", "KEEP", "Impinj: Avery Dennison 22% of revenue"),
    Decision("AXP", "0001049505", True, "supplier", "KEEP", "US Dataworks: American Express 47% of net revenue"),
    Decision("BAC", "0001054374", False, None, "DEBT", "Broadcom: Bank of America prime rate reference in credit facility"),
    Decision("BAX", "0001405197", False, None, "MKTSHARE", "Talecris: explicitly names Baxter a 'competitor', market share"),
    Decision("BDX", "0000075252", True, "customer", "KEEP", "Owens & Minor: distributes products supplied by Becton Dickinson"),
    Decision("BEN", "0001047188", False, None, "INST_OWN", "Penwest Pharmaceuticals: Franklin Resources 8.6% beneficial owner"),
    Decision("BEN", "0001009829", False, None, "INST_OWN", "JAKKS Pacific: Franklin Resources 5.6% beneficial owner"),
    Decision("BEN", "0001113481", False, None, "INST_OWN", "Medicines Co: Franklin Resources 6.1% owner -- see also MCK KEEP below, same CIK different anchor"),
    Decision("BEN", "0001517228", False, None, "INST_OWN", "CommScope: Franklin Resources 7.63% beneficial owner"),
    Decision("BEN", "0000874689", False, None, "INST_OWN", "Integrated Circuit Systems: Franklin Resources 9.1% beneficial owner"),
    Decision("BHF", "0000766829", False, None, "DEBT", "SJW Group: Brighthouse Financial as a note purchaser/lender"),
    Decision("BIIB", "0001156295", False, None, "BELOW10", "SeraCare: Biogen explicitly stated as under 10% of net sales"),
    Decision("BKNG", "0001606745", False, None, "AGG", "TripAdvisor: Booking Holdings combined with Expedia, no individual %"),
    Decision("BLK", "0001375365", False, None, "INST_OWN", "Super Micro: director/officer table, no BlackRock-specific content"),
    Decision("BLK", "0000872448", False, None, "INST_OWN", "Atmel: BlackRock 6.73% beneficial owner"),
    Decision("BLK", "0000769397", False, None, "INST_OWN", "Autodesk: BlackRock 8.9% beneficial owner -- see also SNX KEEP below, same CIK different anchor"),
    Decision("BLK", "0000890801", False, None, "INST_OWN", "McAfee: BlackRock/institutional table"),
    Decision("BLK", "0000003116", False, None, "INST_OWN", "Akorn: BlackRock 6.4% beneficial owner"),
    Decision("BLK", "0000878526", False, None, "INST_OWN", "Natus Medical: BlackRock 12.2% beneficial owner"),
    Decision("BLK", "0001337298", False, None, "INST_OWN", "FutureFuel: BlackRock 9.2% beneficial owner"),
    Decision("BNY", "0000008818", False, None, "DEBT", "Avery Dennison: BNY Mellon as bond trustee"),
    Decision("BURL", "0000913241", False, None, "AGG", "Steven Madden: named in customer list, % belongs to Walmart not Burlington"),
    Decision("BYD", "0000789570", False, None, "JV", "MGM Mirage: Boyd Gaming owns other 50% of a resort"),
    Decision("CAH", "0001319439", False, None, "AGG", "Adams Respiratory: distribution-channel table, no Cardinal-specific % legible"),
    Decision("CAH", "0001127393", True, "supplier", "KEEP", "HemoSense: distributor Cardinal Health 13% of revenue"),
    Decision("CDE", "0000085535", False, None, "NOISE", "Royal Gold: royalty table, no legible CDE relationship"),
    Decision("CDW", "0001366527", False, None, "NOISE", "Carbon Black: % belongs to Optiv Security, not CDW, in a multi-partner list"),
    Decision("CEG", "0001312500", False, None, "JV", "Ormat Funding: explicitly states Constellation Energy is NOT an affiliate"),
    Decision("CEG", "0000813747", True, "supplier", "KEEP", "Spescom Software: Constellation Energy Group 15% of revenue"),
    Decision("CFG", "0001133016", False, None, "MA", "Hub International: one-time acquisition of brokerages from Citizens Financial"),
    Decision("CHRW", "0000815556", False, None, "NOISE", "Fastenal: director bio text, no CHRW content"),
    Decision("CHTR", "0001005757", False, None, "AGG", "CSG Systems: Charter named in client list, no specific % visible"),
    Decision("CIEN", "0001056794", True, "supplier", "KEEP", "Avanex: Ciena >10% of net revenue"),
    Decision("CLF", "0000849979", True, "customer", "KEEP", "Weirton Steel: purchases 100% of iron-ore pellets from Cleveland-Cliffs"),
    Decision("CLF", "0000918577", True, "customer", "KEEP", "Rouge Industries: 65% of pellet requirements from Cleveland-Cliffs"),
    Decision("CLX", "0000719733", True, "supplier", "KEEP", "Key Tronic: explicitly 'a new customer' Clorox, 39% of revenue"),
    Decision("CMCSA", "0000067215", False, None, "NOISE", "Dycom Industries: garbled XBRL tag text"),
    Decision("CMCSA", "0001104855", False, None, "NOISE", "Support.com: SEC comment-letter procedural text"),
    Decision("CMCSA", "0001110458", False, None, "JV", "Insight Midwest: 50/50 owned by a Comcast subsidiary"),
    Decision("CME", "0001864943", False, None, "SOFR", "FGI Industries: CME as SOFR benchmark administrator"),
    Decision("CME", "0001142417", False, None, "SOFR", "Nexstar Media: CME as SOFR term rate administrator"),
    Decision("CME", "0001083446", False, None, "SOFR", "Astrana Health: CME as SOFR benchmark administrator"),
    Decision("CME", "0000029534", False, None, "SOFR", "Dollar General: CME as SOFR benchmark administrator"),
    Decision("CME", "0000796505", False, None, "SOFR", "Clearfield: CME one-month term SOFR reference"),
    Decision("COP", "0001357371", True, "supplier", "KEEP", "BreitBurn Energy: ConocoPhillips 30% of net sales revenues"),
    Decision("COR", "0001723128", False, None, "AGG", "Amneal Pharma: 4 largest customers combined 70%, no Cencora-specific %"),
    Decision("COR", "0001739104", True, "supplier", "KEEP", "Elanco: largest customer a Cencora affiliate, 11% individually"),
    Decision("CRM", "0001378590", False, None, "NOISE", "Bridgeline Digital: marketing copy, no percentage at all"),
    Decision("CSCO", "0001111721", True, "supplier", "KEEP", "Stratos Lightwave: Cisco 10% of net sales"),
    Decision("CSCO", "0000921365", False, None, "AGG", "Merix Corp: market-segment breakdown, no Cisco-specific %"),
    Decision("CSX", "0000943452", False, None, "AGG", "Wabtec: top-5-customers combined 15%, no CSX-specific %"),
    Decision("CUBE", "0001852575", False, None, "MKTSHARE", "Strategic Storage Trust VI: self-storage industry market share"),
    Decision("CVLT", "0000891788", True, "supplier", "KEEP", "DiSC Inc: explicitly 'OEM customer' Commvault 13% of revenue"),
    Decision("CVX", "0001009404", False, None, "JV", "Triton Energy: Chevron subsidiary 65% JV interest"),
    Decision("CVX", "0001027884", False, None, "JV", "Chicago Bridge & Iron: Chevron 50% JV interest"),
    Decision("CVX", "0001338613", True, "supplier", "KEEP", "Regency Energy: explicitly 'largest customer' Chevron 14%"),
    Decision("CVX", "0000098222", True, "supplier", "KEEP", "Tidewater: Chevron 16.3% of revenues"),
    Decision("DKS", "0001286043", False, None, "REIT", "Kite Realty: mall anchor-tenant directory"),
    Decision("DKS", "0001158265", False, None, "REIT", "Heritage Property Investment: mall anchor-tenant directory"),
    Decision("DLTR", "0000828916", False, None, "REIT", "Weingarten Realty: mall anchor-tenant directory"),
    Decision("DOCU", "0001398733", False, None, "NOISE", "Aquestive Therapeutics: Pharmanovia pharma agreement, no DocuSign content"),
    Decision("DUK", "0000904080", True, "supplier", "KEEP", "Stone Energy: Duke Energy Trading 24% of oil/gas revenue"),
    Decision("DUK", "0000099302", False, None, "AGG", "Transcat: Fortune-500 customer list combined 33%, no Duke-specific %"),
    Decision("DUK", "0000015486", False, None, "NOISE", "Burke Mills: Duke as electricity supplier, % is a RATE increase not revenue share"),
    Decision("DUK", "0000037748", True, "supplier", "KEEP", "Massey Energy: explicitly '30-year customer' Duke Energy 11% of coal revenue"),
    Decision("DUK", "0000860546", False, None, "NOISE", "Corporate Office Properties: lease table, no legible Duke content"),
    Decision("DUK", "0001710366", True, "supplier", "KEEP", "CONSOL Energy: explicitly 'customers' Duke Energy >10% of coal revenue"),
    Decision("DELL", "0001050377", True, "customer", "KEEP", "PC Connection -- round4 dup"),
    Decision("DVN", "0001084991", True, "supplier", "KEEP", "Natural Gas Services Group -- round4 dup"),
    Decision("EBAY", "0001633917", False, None, "MA", "PayPal Holdings: one-time spinoff/distribution history"),
    Decision("EBAY", "0001053676", False, None, "INST_OWN", "FairMarket: eBay as a Series B preferred equity investor"),
    Decision("ECL", "0000708484", False, None, "MKTSHARE", "Alcide Corp: Ecolab named among top-4 competitors, market share"),
    Decision("EOG", "0000352955", True, "customer", "KEEP", "CKX Lands: EOG Resources 15.73% of royalty-type revenue"),
    Decision("ETR", "0000202584", False, None, "NOISE", "Entergy Mississippi LLC: self-match, a subsidiary of the anchor itself"),
    Decision("ETR", "0000352955", True, "customer", "KEEP", "CKX Lands: Entergy Corporation 5.29% of royalty-type revenue"),
    Decision("EVR", "0000757011", False, None, "NOISE", "USG Corp: Evercore as independent fiduciary/trustee, no %"),
    Decision("EXC", "0001065059", True, "supplier", "KEEP", "Centrus Energy: Exelon 15% of LEU segment revenue"),
    Decision("EXC", "0001541354", False, None, "NOISE", "Aspirity Holdings: garbled ERCOT/spinoff text"),
    Decision("EXC", "0001412043", True, "supplier", "KEEP", "Opower: Exelon 15% of total revenue"),
    Decision("FAF", "0000036047", False, None, "COMPPEER", "CoreLogic: executive-compensation peer-group comparator table"),
    Decision("FDXF", "0001410997", False, None, "NOISE", "American Realty Capital Trust: fragmentary lease-table row"),
    Decision("FFIV", "0000890394", True, "supplier", "KEEP", "Peraso: F5 Inc 11% of net revenues"),
    Decision("FHI", "0000895051", False, None, "NOISE", "CASI Pharmaceuticals: ownership table, no legible FHI content"),
    Decision("FISV", "0001003607", True, "supplier", "KEEP", "AltiGen Communications: Fiserv 10% of net revenue"),
    Decision("FIVE", "0000842183", False, None, "REIT", "Ramco-Gershenson Properties: mall anchor-tenant directory"),
    Decision("FNF", "0001046859", False, None, "INST_OWN", "Remy International: FNF subsidiary is majority (51%) stockholder"),
    Decision("FTV", "0001374535", False, None, "NOISE", "Altra Industrial Motion: generic post-acquisition demand text, no clear %"),
    Decision("GME", "0000925178", False, None, "MKTSHARE", "Movie Gallery -- round4 dup"),
    Decision("GOOGL", "0000946581", True, "supplier", "KEEP", "Take-Two Interactive -- round4 dup"),
    Decision("GOOGL", "0001094808", True, "supplier", "KEEP", "Vertro Inc -- round4 dup"),
    Decision("GPK", "0001056696", False, None, "AGG", "Manhattan Associates: client name list, no percentages"),
    Decision("GPN", "0000933020", False, None, "NOISE", "Global Payment Technologies -- round4 dup, name collision"),
    Decision("GWRE", "0001175609", False, None, "COMPPEER", "Cavium: peer-company list, no percentage or GWRE relationship"),
    Decision("HAE", "0001596946", False, None, "DEBT", "Quotient Ltd: interest charges on borrowings from Haemonetics"),
    Decision("HBAN", "0000855876", False, None, "MA", "Sky Financial Group: one-time merger announcement"),
    Decision("HCA", "0001027532", True, "supplier", "KEEP", "AmeriPath: net revenue from 31 HCA-operated hospitals"),
    Decision("HPQ", "0001050377", True, "customer", "KEEP", "PC Connection: explicitly 'largest supplier' HP Inc 12% of purchases"),
    Decision("HRB", "0001528930", False, None, "MKTSHARE", "JTH Holding: H&R Block named as a competitor, market share"),
    Decision("HUM", "0000803352", True, "supplier", "KEEP", "ContinuCare: 96% of revenue under managed-care agreements incl. Humana"),
    Decision("HWM", "0000017843", True, "supplier", "KEEP", "Carpenter Technology: Howmet Aerospace 10-12% of net sales"),
    Decision("IBM", "0001050550", True, "supplier", "KEEP", "Volterra Semiconductor: IBM >10% of net revenue"),
    Decision("INTC", "0000723125", False, None, "JV", "Micron Technology -- round4 dup"),
    Decision("INTC", "0000893162", True, "supplier", "KEEP", "Credence Systems -- round4 dup"),
    Decision("INTC", "0000836106", True, "supplier", "KEEP", "Novellus Systems -- round4 dup"),
    Decision("INTC", "0000006951", True, "supplier", "KEEP", "Applied Materials -- round4 dup"),
    Decision("IPGP", "0000889971", False, None, "BELOW10", "LightPath Technologies: IPG Photonics only 6% of revenue"),
    Decision("IQV", "0000002034", False, None, "NOISE", "Aceto Corp: generic IQVIA Institute market-data citation"),
    Decision("IRM", "0000708717", False, None, "INST_OWN", "Alfacell: beneficial-ownership table, no legible IRM content"),
    Decision("IRM", "0001170991", True, "supplier", "KEEP", "Dividend Capital Trust: Iron Mountain 7.64% of portfolio rents (REIT lease revenue, borderline but specific and material)"),
    Decision("ITW", "0000764039", True, "supplier", "KEEP", "Techdyne: explicitly 'sells to' ITW, 19% of sales"),
    Decision("IVZ", "0000722723", False, None, "INST_OWN", "Hanger Inc: Invesco 13.1% beneficial owner"),
    Decision("IVZ", "0001340786", False, None, "INST_OWN", "Fuel Systems Solutions: Invesco 9.1% beneficial owner"),
    Decision("IVZ", "0001145460", False, None, "INST_OWN", "Alere: Invesco 8.19% beneficial owner"),
    Decision("IVZ", "0001550695", False, None, "INST_OWN", "Performant Financial: Invesco 19.1% beneficial owner"),
    Decision("IVZ", "0001779020", False, None, "INST_OWN", "Danimer Scientific: Invesco/Vanguard beneficial-ownership table"),
    Decision("JCI", "0000890080", True, "supplier", "KEEP", "Foamex LP: Johnson Controls 17.3% of net sales"),
    Decision("JEF", "0001056035", False, None, "INST_OWN", "Sheridan Group: Jefferies Capital Partners 84.8% owner"),
    Decision("JEF", "0001038185", False, None, "INST_OWN", "Telex Communications: Jefferies Capital Partners >50% voting power"),
    Decision("JEF", "0000920424", False, None, "NOISE", "Investment Technology Group: formerly named 'Jefferies Group', corporate lineage not a relationship"),
    Decision("JHG", "0001326190", False, None, "INST_OWN", "Altimmune: Janus Henderson 7.8% beneficial owner"),
    Decision("JHG", "0001604665", False, None, "INST_OWN", "Westlake Chemical Partners: Janus Henderson 5.45% beneficial owner"),
    Decision("JHG", "0001029831", False, None, "NOISE", "Hillman Companies: Janus fund as a 401k investment OPTION, not a relationship"),
    Decision("JHG", "0000878526", False, None, "INST_OWN", "Natus Medical: BlackRock/institutional table (Janus not the specific line)"),
    Decision("JHG", "0001679268", False, None, "INST_OWN", "Mammoth Energy Services: Janus Henderson 5.7% beneficial owner"),
    Decision("KBH", "0000276720", True, "customer", "KEEP", "Pure Cycle Corp: KB Home 10% of total revenue"),
    Decision("KEX", "0001411207", True, "supplier", "KEEP", "Allison Transmission: Kirby Corp 15% of accounts receivable"),
    Decision("KMI", "0001339048", False, None, "NOISE", "Western Refining: fragmentary pipeline-feedstock table, no specific KMI %"),
    Decision("LEA", "0000805583", False, None, "NOISE", "Donnelly Corp: JV name reference (Lear Donnelly), no clean %"),
    Decision("LEA", "0001016177", True, "supplier", "KEEP", "Dura Automotive: Lear + Johnson Controls 11% of revenues"),
    Decision("LYB", "0001395864", False, None, "SANCTIONS", "Verso Paper: Iran-sanctions Apollo boilerplate re LyondellBasell"),
    Decision("LYB", "0001439288", False, None, "SANCTIONS", "Rexnord Corp: same Iran-sanctions boilerplate"),
    Decision("LYB", "0001362491", False, None, "SANCTIONS", "Metals USA Holdings: same Iran-sanctions boilerplate"),
    Decision("LYB", "0001404624", False, None, "SANCTIONS", "Affinion Group Holdings: same Iran-sanctions boilerplate"),
    Decision("LYB", "0001361394", False, None, "SANCTIONS", "Affinion Group Inc: same Iran-sanctions boilerplate"),
    Decision("LYB", "0000034115", False, None, "SANCTIONS", "Claire's Stores: same Iran-sanctions boilerplate"),
    Decision("LYB", "0000922863", False, None, "SANCTIONS", "Quality Distribution: same Iran-sanctions boilerplate"),
    Decision("MCD", "0001058090", False, None, "INST_OWN", "Chipotle: McDonald's as former 87% majority owner"),
    Decision("MCD", "0000054883", False, None, "AGG", "Keane Inc: industry-segment breakdown, no MCD-specific %"),
    Decision("MCK", "0001113481", True, "supplier", "KEEP", "Medicines Co: AmerisourceBergen/McKesson/Cardinal >88% combined -- round4 dup; see BEN reject above, same CIK different anchor"),
    Decision("MDLZ", "0000713425", False, None, "AGG", "American Software: vendor name list, no percentages"),
    Decision("MMM", "0001368765", False, None, "DEBT", "Umami Sustainable Seafood: 3M JPY LIBOR+6.5% loan reference"),
    Decision("MPC", "0000821026", False, None, "JV", "Andersons Inc: Marathon Petroleum 49.9% JV interest"),
    Decision("MRK", "0001318310", False, None, "NOISE", "ev3 Inc: segment revenue table, no specific Merck % legible"),
    Decision("MSFT", "0001013786", True, "supplier", "KEEP", "Zones Inc: explicitly 'customer' Microsoft 14.7-28.7% of sales"),
    Decision("MTG", "0000036047", False, None, "COMPPEER", "CoreLogic: same executive-comp peer-group table as FAF"),
    Decision("MTZ", "0001441769", False, None, "AGG", "DirectView Holdings: 4 clients combined 87%, no MasTec-specific %"),
    Decision("NCLH", "0001125259", False, None, "MKTSHARE", "Carnival PLC -- round4 dup"),
    Decision("NEE", "0001274494", True, "supplier", "KEEP", "First Solar: explicitly 'individually >10%' NextEra Energy"),
    Decision("NEE", "0000099302", False, None, "AGG", "Transcat: Fortune-500 list combined 29%, no NextEra-specific %"),
    Decision("NKE", "0000895447", True, "customer", "KEEP", "Shoe Carnival -- round4 dup"),
    Decision("NOC", "0000722313", True, "supplier", "KEEP", "Nortech Systems: Northrop Grumman 10% of net sales"),
    Decision("NOC", "0000720145", True, "supplier", "KEEP", "Cipprico: Northrop Grumman 10% of net sales"),
    Decision("NRG", "0000013547", True, "supplier", "KEEP", "Entrx Corp: NRG Energy 10.7% of revenues"),
    Decision("NSA", "0001852575", False, None, "MKTSHARE", "Strategic Storage Trust VI: self-storage industry market share"),
    Decision("NSC", "0001320854", True, "supplier", "KEEP", "FreightCar America: Norfolk Southern 16% of total revenue"),
    Decision("NTNX", "0001616533", True, "supplier", "KEEP", "SMART Global Holdings: Nutanix 11% of net sales"),
    Decision("NXPI", "0000021535", True, "supplier", "KEEP", "Cohu Inc: NXP named in a customer-concentration table alongside Intel 18%"),
    Decision("NXPI", "0001036044", False, None, "NOISE", "SCM Microsystems: generic industry growth-rate commentary"),
    Decision("NYT", "0000796577", True, "supplier", "KEEP", "Quipp Inc: NYT 11% of net sales"),
    Decision("ODFL", "0000015357", False, None, "NOISE", "Chase General Corp: name collision, 'Old Dominion' peanut candy brand vs Old Dominion Freight Line"),
    Decision("OXY", "0001360901", False, None, "NOISE", "Evercore Partners: M&A tombstone/deal-credits list, no OXY content"),
    Decision("PAYX", "0001144354", False, None, "MKTSHARE", "Heartland Payment Systems: Paychex named among competitors, market share"),
    Decision("PCG", "0001562151", False, None, "MA", "Crimson Wine Group: PG&E wildfire-settlement/bankruptcy text, one-time"),
    Decision("PEN", "0000885725", False, None, "MA", "Boston Scientific: one-time acquisition announcement of Penumbra"),
    Decision("PEP", "0001084230", True, "customer", "KEEP", "PepsiAmericas: bottles under PepsiCo license, 91% of volume"),
    Decision("PFE", "0001372813", True, "customer", "KEEP", "Animal Health International: Pfizer explicitly 'top manufacturer/supplied' 20% of net sales"),
    Decision("PFE", "0001040853", True, "supplier", "KEEP", "Pharsight Corp: explicitly 'largest customer' Pfizer 25% of revenue"),
    Decision("PGR", "0001117297", True, "supplier", "KEEP", "QuinStreet: Progressive Corp 17% of net revenue"),
    Decision("PHM", "0001562476", False, None, "COMPPEER", "Taylor Morrison: Black-Scholes comparable-peer-set table"),
    Decision("PII", "0001207074", False, None, "NOISE", "Virtusa Corp: name collision, 'Polaris Consulting & Services' vs Polaris Industries"),
    Decision("PLNT", "0000060876", True, "supplier", "KEEP", "Cybex International: Planet Fitness Equipment 10.4% of net sales"),
    Decision("PNC", "0000902272", False, None, "INST_OWN", "Aldila Inc: PNC Financial Services 11.7% beneficial owner"),
    Decision("POR", "0001061134", True, "supplier", "KEEP", "ICON Income Fund: lease to Portland General Electric 19% of revenue"),
    Decision("POST", "0001828972", False, None, "NOISE", "BuzzFeed Inc: BuzzFeed Japan JV table, no legible Post Holdings content"),
    Decision("PPG", "0000006845", False, None, "JV", "Apogee Enterprises: PPG Auto Glass 34% JV interest"),
    Decision("PRI", "0001122099", False, None, "NOISE", "VillageEDocs: revenue via INDEPENDENT REPRESENTATIVES of Primerica, indirect/attenuated"),
    Decision("PRU", "0001058057", False, None, "INST_OWN", "Marvell Technology: Prudential Financial 6.1% beneficial owner"),
    Decision("PSX", "0001357371", True, "supplier", "KEEP", "BreitBurn Energy: Phillips 66 15% of net sales revenues"),
    Decision("PSX", "0001609253", True, "supplier", "KEEP", "California Resources: ConocoPhillips/Phillips 66 >10% of revenue"),
    Decision("PSX", "0000904080", True, "supplier", "KEEP", "Stone Energy: Phillips 66 Company 18% of oil/gas revenue"),
    Decision("PSX", "0000805022", False, None, "JV", "Buckeye Partners: Buckeye Texas JV, 20% interest acquisition"),
    Decision("PSX", "0001486159", True, "supplier", "KEEP", "Oasis Petroleum: Phillips 66 15% of total product sales"),
    Decision("RBC", "0001374535", False, None, "COMPPEER", "Altra Industrial Motion: stock-performance peer-group index"),
    Decision("RJF", "0001165921", False, None, "INST_OWN", "Law Enforcement Associates: Raymond James Financial 51% controlling owner"),
    Decision("RJF", "0000745456", False, None, "NOISE", "Monroe Bancorp: describes filer's own Raymond James-affiliated brokerage unit"),
    Decision("ROK", "0001506546", False, None, "INST_OWN", "Aspect Software: Rockwell Automation Holdings 9.5% stockholder"),
    Decision("ROST", "0000913241", False, None, "AGG", "Steven Madden: named in customer list, % belongs to Walmart not Ross Stores"),
    Decision("RRC", "0001306527", True, "customer", "KEEP", "Hiland Partners: Range Resources is a primary gas SUPPLIER to the gathering system"),
    Decision("RTX", "0000108312", True, "supplier", "KEEP", "Woodward Inc: RTX Corporation among customers >10% of net sales"),
    Decision("SFM", "0000828916", False, None, "REIT", "Weingarten Realty: mall anchor-tenant directory"),
    Decision("SHW", "0000943897", True, "supplier", "KEEP", "BWAY Corp: Sherwin-Williams 16% of metal-packaging net sales"),
    Decision("SHW", "0001392179", True, "supplier", "KEEP", "BWAY Holding Co: same Sherwin-Williams 16% relationship"),
    Decision("SLB", "0000030305", False, None, "BELOW10", "Ducommun Inc: Schlumberger only 4.1% of total net sales"),
    Decision("SLM", "0000007789", False, None, "DEBT", "Associated Banc-Corp: SLM student-loan asset-backed securities holding"),
    Decision("SNX", "0001050377", True, "customer", "KEEP", "PC Connection: TD Synnex 23% of product purchases"),
    Decision("SNX", "0000769397", True, "supplier", "KEEP", "Autodesk: largest distributor TD Synnex 39% of net revenue"),
    Decision("SPG", "0000832988", True, "customer", "KEEP", "Signet Jewelers: leases 16% of store locations from Simon Property Group"),
    Decision("STWD", "0001476045", False, None, "DEBT", "Chatham Lodging Trust: Starwood Property Trust as one of several mortgage lenders"),
    Decision("TER", "0000921365", False, None, "AGG", "Merix Corp: same market-segment breakdown as CSCO, no Teradyne-specific %"),
    Decision("TFC", "0001401521", True, "supplier", "KEEP", "United Insurance Holdings: AmRisc (Truist-owned) 100% of commercial-lines revenue via exclusive agreement"),
    Decision("TGT", "0000913241", False, None, "AGG", "Steven Madden: named in customer list, % belongs to Walmart not Target"),
    Decision("TGT", "0001067797", False, None, "NOISE", "Primus Knowledge Solutions: generic anti-takeover statute 'target corporation', not the retailer"),
    Decision("THC", "0002071288", False, None, "JV", "Lumexa Imaging Holdings: healthcare JV ownership percentages table"),
    Decision("THO", "0000076605", True, "supplier", "KEEP", "Patrick Industries: Thor Industries >10% of consolidated net sales"),
    Decision("TJX", "0000793983", True, "supplier", "KEEP", "Bernard Chaus: TJX Companies 22% of net revenue, individually broken out"),
    Decision("TLN", "0001085392", False, None, "JV", "Puget Energy: Talen Energy 50% co-ownership of power-plant units"),
    Decision("TMO", "0001033905", True, "supplier", "KEEP", "Luminex Corp: Thermo Fisher Scientific 15% of total revenues"),
    Decision("TRMB", "0000880266", False, None, "JV", "AGCO Corp: Trimble Ag joint-venture formation"),
    Decision("TROW", "0001086774", False, None, "INST_OWN", "Centerplate: T. Rowe Price 6.6% beneficial owner"),
    Decision("TROW", "0001101302", False, None, "INST_OWN", "Entegris: T. Rowe Price 6.9% beneficial owner"),
    Decision("TROW", "0001535031", False, None, "INST_OWN", "Tumi Holdings: 5%-stockholder table, no T. Rowe-specific line legible"),
    Decision("TROW", "0000923571", False, None, "INST_OWN", "US Xpress Enterprises: 5%-holders table"),
    Decision("TROW", "0001075316", False, None, "INST_OWN", "Webtrends Corp: T. Rowe Price 15.1% beneficial owner"),
    Decision("TROW", "0001158172", False, None, "INST_OWN", "comScore: T. Rowe Price 6.0% beneficial owner"),
    Decision("TROW", "0001120914", False, None, "INST_OWN", "PDF Solutions: T. Rowe Price 10.47% beneficial owner"),
    Decision("TSN", "0000802481", False, None, "MA", "Pilgrim's Pride: one-time acquisition of Provemex from Tyson Foods"),
    Decision("TSN", "0001092605", False, None, "MKTSHARE", "eMerge Interactive: Tyson named among beef-packing competitors, industry share"),
    Decision("TSN", "0001297667", False, None, "NOISE", "ATEL Capital Equipment Fund: Tyson-specific row not visible in the excerpt"),
    Decision("TTMI", "0000076267", True, "supplier", "KEEP", "Park Electrochemical: 14.9% of sales to TTM Technologies"),
    Decision("TXN", "0000909326", False, None, "BELOW10", "Asyst Technologies: TXN only 6.6% of net sales"),
    Decision("TXN", "0001113232", False, None, "AGG", "Axcelis Technologies: 3 customers combined 28.0%, no TXN-specific %"),
    Decision("TXN", "0001040470", True, "supplier", "KEEP", "Aehr Test Systems: TXN 45% of net sales"),
    Decision("TXN", "0000357020", True, "supplier", "KEEP", "LTX-Credence: TXN 23% of net sales"),
    Decision("ULTA", "0000828916", False, None, "REIT", "Weingarten Realty: mall anchor-tenant directory"),
    Decision("UNH", "0001170650", True, "supplier", "KEEP", "Medco Health Solutions: UnitedHealth Group 18% of net revenues, largest client"),
    Decision("UNH", "0001094348", True, "supplier", "KEEP", "eLoyalty Corp: UnitedHealth Group 14% of 2002 revenue"),
    Decision("URI", "0001094348", True, "supplier", "KEEP", "eLoyalty Corp: United Rentals 13% of gross accounts receivable"),
    Decision("USB", "0001088811", False, None, "DEBT", "G&G Retail: U.S. Bank as bond trustee"),
    Decision("VLO", "0000052988", True, "supplier", "KEEP", "Jacobs Engineering: Valero Energy 10.2% of total revenues"),
    Decision("VRT", "0000032604", False, None, "INST_OWN", "Emerson Electric: Emerson's own subordinated-interest gain from spun-off Vertiv, an investment stake"),
    Decision("VTR", "0001962481", False, None, "NOISE", "BranchOut Food: Peru VAT tax commentary, no Ventas content"),
    Decision("WBD", "0001142417", False, None, "MA", "Nexstar Media: one-time acquisition of a 75% interest in The CW"),
    Decision("WDC", "0000813347", True, "supplier", "KEEP", "Komag Inc: Western Digital 50% of net sales to major customers"),
    Decision("WMB", "0000054883", False, None, "AGG", "Keane Inc: ten largest clients combined 29%, no Williams-specific %"),
    Decision("WMG", "0000795212", False, None, "AGG", "Trans World Entertainment: 10 suppliers combined 70%, no WMG-specific %"),
    Decision("WMT", "0000869487", False, None, "AGG", "Tandy Brands Accessories: retailer name list, no percentages at all"),
    Decision("WPC", "0001390213", False, None, "NOISE", "Corporate Property Associates 17: 0.01% GP interest, immaterial fund structure"),
    Decision("WPC", "0001558235", False, None, "NOISE", "Corporate Property Associates 18: 0.03% GP interest, immaterial fund structure"),
    Decision("WSO", "0000101829", False, None, "JV", "United Technologies: Carrier/Watsco joint-venture contribution"),
    Decision("XOM", "0000933738", True, "supplier", "KEEP", "EnGlobal Corp: ExxonMobil 36% of total revenues"),
    Decision("ZBRA", "0000311505", False, None, "MKTSHARE", "Printronix: Zebra Technologies named among competitors, market share"),
    Decision("ZBRA", "0000719733", True, "supplier", "KEEP", "Key Tronic: Zebra Technologies 12% of consolidated revenues"),
    Decision("ZION", "0001079996", False, None, "INST_OWN", "Quotesmith.com: Zions Bancorporation as a controlling shareholder"),
)


def _key(anchor_ticker: str, peer_cik: str) -> tuple[str, str]:
    return (anchor_ticker.upper(), peer_cik)


def apply_review(
    raw_leads: list[dict[str, Any]],
    decisions: tuple[Decision, ...] = SCALED_HAND_REVIEW_DECISIONS,
) -> list[dict[str, Any]]:
    """Join the raw confirmed leads to their hand-review decision by
    (anchor_ticker, peer_cik). Refuses on any mismatch between the two
    sets -- see module docstring for why the key is a pair, not peer_cik
    alone."""
    confirmed = {
        _key(l["anchor_ticker"], l["peer_cik"]): l
        for l in raw_leads if l.get("filed_mention_confirmed")
    }
    decided = {_key(d.anchor_ticker, d.peer_cik): d for d in decisions}

    missing = sorted(set(confirmed) - set(decided))
    if missing:
        raise HandReviewError(
            f"{len(missing)} confirmed lead(s) have no hand-review decision: "
            f"{missing}. Every confirmed lead must be reviewed explicitly.")
    orphan = sorted(set(decided) - set(confirmed))
    if orphan:
        raise HandReviewError(
            f"{len(orphan)} decision(s) name an (anchor, peer_cik) not in "
            f"the raw confirmed set: {orphan}. The raw hits file has "
            "changed since this review was written -- re-review rather "
            "than trusting a stale decision list.")

    out = []
    for key, lead in confirmed.items():
        d = decided[key]
        if not d.keep:
            continue
        out.append({**lead, "corrected_direction": d.direction,
                   "hand_review_category": d.category,
                   "hand_review_reason": d.note})
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-hits", type=Path, default=RAW_HITS_JSON)
    ap.add_argument("--out-name-search", type=Path, default=OUT_NAME_SEARCH)
    ap.add_argument("--out-linkage", type=Path, default=OUT_LINKAGE)
    ap.add_argument("--write", action="store_true",
                    help="actually write the two reviewed artifacts "
                         "(default prints the review and exits)")
    a = ap.parse_args(argv)

    if not a.raw_hits.is_file():
        print(f"REFUSED: {a.raw_hits} does not exist", file=sys.stderr)
        return 1
    raw = json.loads(a.raw_hits.read_text(encoding="utf-8"))

    try:
        kept = apply_review(raw["leads"])
    except HandReviewError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1

    from collections import Counter
    cats = Counter(d.category for d in SCALED_HAND_REVIEW_DECISIONS)
    print(f"confirmed leads reviewed: {len(SCALED_HAND_REVIEW_DECISIONS)}")
    print(f"kept (genuine): {cats['KEEP']}")
    print("rejected by category:")
    for cat, n in sorted(cats.items(), key=lambda kv: -kv[1]):
        if cat != "KEEP":
            print(f"  {cat:10s} {n}")
    print(f"distinct peer tickers kept: "
          f"{len({(d.anchor_ticker, d.peer_cik) for d in SCALED_HAND_REVIEW_DECISIONS if d.keep})}")

    if not a.write:
        print("\nDry run (no --write). Nothing written.")
        return 0

    for p in (a.out_name_search, a.out_linkage):
        if p.exists():
            print(f"REFUSED: {p} already exists. Dated artifacts are "
                  "never overwritten.", file=sys.stderr)
            return 1

    from .edgar_agreements import AgreementSearchClient
    client = AgreementSearchClient("bchen9996 bchen9996@gmail.com")

    name_search_results: list[dict[str, Any]] = []
    linkage_edges: list[dict[str, Any]] = []
    for v in kept:
        cik = v["peer_cik"]
        ticker = client.ticker_for(cik)
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
            "direction": v["corrected_direction"],
            "as_of_date": v["file_date"],
            "source": SOURCE_HANDREVIEWED,
            "evidence_sentence": v["context"],
            "hand_review_category": v["hand_review_category"],
            "hand_review_reason": v["hand_review_reason"],
        })

    a.out_name_search.write_text(json.dumps({
        "artifact": a.out_name_search.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05", "results": name_search_results,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    a.out_linkage.write_text(json.dumps({
        "artifact": a.out_linkage.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05", "edges": linkage_edges,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {a.out_name_search}")
    print(f"wrote {a.out_linkage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
