#!/usr/bin/env python3
"""Hand review of the SCALED reverse-competitor search's confirmed leads
(HYP07_REVERSE_COMPETITOR_SEARCH_RAW_HITS_SCALED_2026-09-13.json).

Same discipline as run_hyp07_reverse_competitor_search_handreview.py (the
27-anchor first pass): every sentence is read by hand, not sampled.

=== THE REVIEW: 371 CONFIRMED LEADS, EVERY ONE READ, 370 GENUINE ===

`run_hyp07_reverse_competitor_search_scaled.py`'s completed live run
(2026-09-13, 788 anchors, 8,770 requests) confirmed 371 (anchor_ticker,
peer_cik) leads. Every one of the 371 was read in full -- not sampled --
the same discipline every prior round in this project applied. The result
is a dramatically cleaner hit rate than round 6's own customer/supplier
scaled review (277 confirmed, roughly half rejected across 12 genuine
false-positive genres): here, 370 of 371 (99.7%) are genuine, direct,
specific competitor-naming disclosures ("our competitors include ...
ANCHOR ..." / "we compete with ANCHOR"). This is not surprising in
hindsight -- `_looks_like_competitor_sentence()` requires the sentence
itself to match one of three real, calibrated COMPETITOR_ANCHORS regex
patterns, a structural check with no analog to the percent-figure
heuristic that let so much through round 6's own concentration-language
filter -- but it was verified by reading every real sentence, not assumed
from the mechanism's design.

**The single rejection**: NBIX / Symyx Technologies, Inc. (CIK
0001095330) -- the stored context is an explicit "Compensation Peer
Group" table (an executive-compensation benchmarking exhibit listing
~30 similarly-sized companies for pay-setting purposes), not a
competitive-landscape disclosure. Neurocrine Biosciences appears in that
list alongside Neurocrine itself and dozens of unrelated biotechs; nothing
in the passage claims Symyx competes with it. This is the COMPPEER
genre round 6's own scaled review already established -- see
REJECT_CATEGORIES below.

Every KEEP entry's note is a real, literal excerpt (up to 140 characters)
of the actual verified sentence, not a paraphrase -- so the decision list
below is itself a readable record of what was actually read, the same
transparency round 6's own terse-but-specific scaled-review notes
established as the right convention at this scale (as opposed to the
27-entry first pass's fuller paragraph-per-entry style, proportionate to
its much smaller size).

=== WHY KEYED BY (anchor_ticker, peer_cik), NOT peer_cik ALONE ===

Round 6's own scaled customer/supplier hand review already found this break
at scale (one CIK, two different anchors, two different correct answers),
and HYP-07's own 27-anchor first pass independently rediscovered the exact
same collision class (FISERV INC under AAPL/GOOGL/SBUX). At 788 anchors the
collision is close to certain to recur again. `Decision` here is keyed by
`(anchor_ticker, peer_cik)` from the start, not retrofitted after finding a
collision -- the shape is reused, not imported, since this module's own
raw-hits shape and (likely) review categories will differ from round 6's
customer/supplier-specific ones.

=== NO corrected_direction FIELD, SAME REASON AS THE FIRST PASS ===

A competitor relationship is symmetric -- there is no direction to get
wrong, unlike a customer/supplier concentration sentence. Every kept lead's
`direction` is simply `"competitor"`, fixed, exactly as in
`run_hyp07_reverse_competitor_search_handreview.py`.

=== REJECT_CATEGORIES: CARRIED FORWARD WHERE STRUCTURALLY GENERIC, NOT
    WHERE CONCENTRATION-SPECIFIC ===

Round 6's own scaled hand review found these false-positive genres, most of
which are about what the ANCHOR'S NAME collides with in an unrelated
filing, not about the concentration phrase itself -- so they are just as
plausible here: INST_OWN (asset-manager anchor in a filer's own beneficial-
ownership table), SOFR (CME Group cited as benchmark-rate administrator),
DEBT (bank/lender anchor named as lender/trustee), JV (joint-venture
ownership percentage, wrong schema), SANCTIONS (Iran Threat Reduction Act
boilerplate reciting an unrelated portfolio company), REIT (shopping-center
anchor-tenant leasing directory), MA (one-time acquisition/merger
announcement), COMPPEER (executive-compensation peer-group table), NOISE
(garbled text, name collision, self-match).

Two of round 6's categories are dropped as structurally inapplicable:
AGG and BELOW10 both require a percent-materiality figure --
`_looks_like_competitor_sentence()` has no percent requirement at all, so
there is no equivalent "aggregated, not anchor-specific" or "below the
ASC-280 threshold" failure mode to detect here.

One new category is added, anticipated (not yet observed) by
`run_hyp07_reverse_competitor_search_handreview.py`'s own docstring: MKTSTRUCT
-- a sentence using real competitor phrasing to describe market-share or
industry structure rather than a bilateral claim that the FILER itself
competes with the anchor (the Movie Gallery/Carnival PLC shape from HYP-05's
hand review, genuinely competitor-shaped rather than concentration-shaped).

This list is a starting point, not a claim of completeness -- exactly the
same "bounded, not exhaustive" discipline every phrase/anchor list in this
project is declared under. A genuinely new genre found while reading the
real leads gets its own new category, added here when that happens, not
forced into the nearest existing label.

Run:  python -m hyp04_supply_chain_hedge.run_hyp07_reverse_competitor_search_handreview_scaled --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple, Optional

from .run_hyp07_reverse_competitor_search_handreview import HandReviewError

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-13"

RAW_HITS_JSON = LSE / f"HYP07_REVERSE_COMPETITOR_SEARCH_RAW_HITS_SCALED_{AS_OF}.json"
OUT_NAME_SEARCH = LSE / f"HYP07_PEER_NAME_SEARCH_REVERSE_COMPETITOR_SEARCH_SCALED_HANDREVIEWED_{AS_OF}.json"
OUT_LINKAGE = LSE / f"HYP07_CANDIDATE_LINKAGE_REVERSE_COMPETITOR_SEARCH_SCALED_HANDREVIEWED_{AS_OF}.json"

SOURCE_HANDREVIEWED = (
    "EDGAR_10K_FULLTEXT_REVERSE_COMPETITOR_SEARCH_SCALED_HAND_REVIEWED")

#: Starting point, not exhaustive -- see module docstring,
#: "REJECT_CATEGORIES". A real new genre found while reading the actual
#: leads gets its own new label added here, not forced into an existing one.
REJECT_CATEGORIES = frozenset({
    "INST_OWN", "SOFR", "DEBT", "JV", "SANCTIONS", "REIT", "MA",
    "COMPPEER", "NOISE", "MKTSTRUCT",
})


class Decision(NamedTuple):
    anchor_ticker: str
    peer_cik: str
    keep: bool
    category: str              # "KEEP" or one of REJECT_CATEGORIES
    note: str = ""              # peer-specific detail beyond the category


#: HandReviewError is imported UNCHANGED from the first-pass hand-review
#: module above -- a genuinely identical marker exception, no divergence
#: risk. _key() is NOT imported despite looking identical at a glance: the
#: first-pass module's own _key does NOT uppercase anchor_ticker, while
#: this module's does (verified by reading both directly, not assumed) --
#: importing it would have silently dropped that normalization. Kept
#: separate rather than "fixed" into false consistency. apply_review()
#: itself is also not imported: its final per-decision field extraction
#: (category/note here vs. a single reason there) is a real difference
#: driven by the two Decision shapes, not incidental duplication.
def _key(anchor_ticker: str, peer_cik: str) -> tuple[str, str]:
    return (anchor_ticker.upper(), peer_cik)


SCALED_HAND_REVIEW_DECISIONS: tuple[Decision, ...] = (
    Decision('AAPL', '0000798354', True, 'KEEP',
            'FISERV INC: These newer 5 Table of Contents competitors include, but are not limited to, Alphabet Inc., Amazon.com, Inc., Apple Inc., Facebook, Inc., In'),
    Decision('ABBV', '0001496671', True, 'KEEP',
            'Calithera Biosciences, Inc.: Our principal competitors include Abbvie Inc., Advanced Cancer Therapeutics, LLC, Aeglea Biotherapeutics, Inc., Agios Pharmaceuticals, Inc.,'),
    Decision('ABBV', '0001787306', True, 'KEEP',
            'Arcutis Biotherapeutics, Inc.: For psoriasis, our primary competitors include injected biologic therapies such as Humira, marketed by AbbVie Inc. and Eisai Co., Ltd., and'),
    Decision('ABT', '0001420108', True, 'KEEP',
            'Glucose Health, Inc.: We compete directly with Glucerna® Advance, manufactured by Abbott Laboratories;'),
    Decision('ACGL', '0000913144', True, 'KEEP',
            'RENAISSANCERE HOLDINGS LTD: With respect to our Reinsurance operations, we believe that our principal competitors include other companies active in the Bermuda market,'),
    Decision('ACGL', '0001171500', True, 'KEEP',
            'PLATINUM UNDERWRITERS HOLDINGS LTD: Our competitors include Arch Capital Group Ltd., Axis Capital Holdings Limited, Endurance Specialty Holdings Ltd., Everest Re Group, Ltd., M'),
    Decision('ACI', '0000882829', True, 'KEEP',
            'STATER BROS HOLDINGS INC: Our primary competitors include Vons, Albertsons, Ralphs, and a number of independent supermarket operators.'),
    Decision('ACI', '0001563407', True, 'KEEP',
            'Smart & Final Stores, Inc.: Our principal competitors include conventional grocers such as Albertsons/Safeway and Kroger, warehouse clubs and discounters such as Costco'),
    Decision('ACM', '0000052988', True, 'KEEP',
            'JACOBS ENGINEERING GROUP INC /DE/: In the area of buildings, the Company\'s competitors include several of the competitors previously mentioned, as well as HDR, Inc., Hellmuth,'),
    Decision('ACM', '0000831641', True, 'KEEP',
            'TETRA TECH INC: We believe that our principal competitors include, in alphabetical order, AECOM Technology Corporation;'),
    Decision('ACM', '0000944480', True, 'KEEP',
            'GSE SYSTEMS INC: In our engineering market, we compete with firms primarily from North America such as Enercon Services, Kinetrics, Sargent & Lundy, and AECO'),
    Decision('ACM', '0001560905', True, 'KEEP',
            'Geo Point Resources, Inc.: Our principal competitors are AECOM Technology Corporation, URS, Kleinfelter, Levine Fricke, CH2M Hill Companies, Ltd., The Reynolds Group a'),
    Decision('ACN', '0001125011', True, 'KEEP',
            'KANBAY INTERNATIONAL INC: Our primary competitors include: • large consulting and other professional service firms, including Accenture, BearingPoint, Cap Gemini and'),
    Decision('ADBE', '0001002638', True, 'KEEP',
            'OPEN TEXT CORP: Our competitors include International Business Machines Corporation (IBM), EMC Corporation (EMC), Hewlett-Packard Company (HP) and Adobe Inc'),
    Decision('ADI', '0000097476', True, 'KEEP',
            'TEXAS INSTRUMENTS INC: Our primary competitors include Analog Devices, Inc.;'),
    Decision('ADI', '0000802851', True, 'KEEP',
            'LOGIC DEVICES INC: In the area of high-performance DSP circuits, we compete with Altera, Analog Devices, Fairchild Semiconductor, Intersil, Lucent Technologies'),
    Decision('ADI', '0000812927', True, 'KEEP',
            'IMP INC: Other competitors include Analog Devices Inc., Linfinity Microelectronics, Motorola, National Semiconductor Corporation, Texas Instruments,'),
    Decision('ADI', '0001116201', True, 'KEEP',
            'INTEGRATED TELECOM EXPRESS INC/ CA: Our principal competitors include Alcatel Microelectronics, Analog Devices, Inc., Centillium Communications, Inc., Conexant Systems, Inc., G'),
    Decision('ADP', '0000896878', True, 'KEEP',
            'INTUIT INC: In our payroll business we compete directly with Automatic Data Processing, Inc. (ADP), Paychex and many other companies with payroll offeri'),
    Decision('ADP', '0001133598', True, 'KEEP',
            'DealerAdvance, Inc.: Our competitors include the ADP Dealer Services division of Automatic Data Processing, Inc., The Cobalt Group, AutoManager, and Autobase, In'),
    Decision('ADP', '0001335795', True, 'KEEP',
            'FUND.COM INC.: Vensure competitors include companies that are focused on co-employment or PEO services, such as Administaff, Inc. and companies that primar'),
    Decision('AEIS', '0000780571', True, 'KEEP',
            'ITRON, INC.: Our primary competitors include LM Ericsson Telephone Company, Landis+Gyr, Advanced Energy Industries, and Xylem, Inc. We believe that our c'),
    Decision('AFG', '0001761312', True, 'KEEP',
            'Palomar Holdings, Inc.: Berkley, and Bowhead Specialty Holdings Inc. As an Approved Insurance Provider (“AIP”), we compete with 11 other insurance carriers in the f'),
    Decision('AIG', '0000002062', True, 'KEEP',
            'ACMAT CORP: The Company\'s principal competitors include certain insurance subsidiaries of American International Group, Inc. ("AIG"), Reliance Insurance'),
    Decision('AIG', '0001141719', True, 'KEEP',
            'MAX RE CAPITAL LTD: Our worldwide reinsurance competitors include ACE Limited, American International Group, Inc., Berkshire Hathaway, Inc., Swiss Reinsurance C'),
    Decision('AJG', '0001183186', True, 'KEEP',
            'NATIONAL FINANCIAL PARTNERS CORP: Our national competitors include Marsh & McLennan Companies, Inc., Aon Corporation, Hilb, Rogal and Hamilton Company, Arthur J. Gallagher &'),
    Decision('ALGN', '0001121302', True, 'KEEP',
            'SYBRON DENTAL SPECIALTIES INC: Our competitors include 3M Unitek (an affiliate of 3M Company), GAC International (a subsidiary of Dentsply), Align Technology Inc., America'),
    Decision('AMAT', '0000914329', True, 'KEEP',
            'FEI CO: Our principal competitors include JEOL Ltd., Hitachi, Ltd., Seiko Instruments Inc., Carl Zeiss SMT A.G., Applied Materials, Inc., Credence S'),
    Decision('AMCR', '0000842633', True, 'KEEP',
            'TRIMAS CORP: Depending on the product and customers served, our competitors include Aptar, Bericap, Berry Global (soon to be part of Amcor), Comar, Greif'),
    Decision('AMCR', '0001061507', True, 'KEEP',
            'GRAHAM PACKAGING HOLDINGS CO: The Company\'s primary competitors include Owens-Illinois, Inc., Ball Corporation, Constar International Inc., Consolidated Container Company'),
    Decision('AMCR', '0001378992', True, 'KEEP',
            'BERRY GLOBAL GROUP, INC.: Competitors include but are not limited to Amcor, Silgan, Aptar, 3M, and Sigma.'),
    Decision('AMD', '0000772406', True, 'KEEP',
            'CIRRUS LOGIC INC: Our principal competitors include: Analog Devices, Advanced Micro Devices, Broadcom, C-Cube, Conexant, Creative Technologies, ESS Technologi'),
    Decision('AME', '0000046129', True, 'KEEP',
            'ALLIED MOTION TECHNOLOGIES INC: Our competitors include Ametek, Danaher Motion, Parker Hannifin Corporation, and other smaller competitors.'),
    Decision('AME', '0001043337', True, 'KEEP',
            'STONERIDGE INC: Our primary competitors include Alcoa Fujikura, Ametek, Delphi, Sumitomo Electric, Siemens VDO, Visteon and Yazaki.'),
    Decision('AMGN', '0001787306', True, 'KEEP',
            'Arcutis Biotherapeutics, Inc.: For psoriasis, our primary competitors include injected biologic therapies such as Humira, marketed by AbbVie Inc. and Eisai Co., Ltd., and'),
    Decision('AMZN', '0001506439', True, 'KEEP',
            'SMTP, Inc.: Our principal competitors include providers of email management services for small to medium size businesses such as AuthSmtp.com, SMTP2Go.c'),
    Decision('ANET', '0000047217', True, 'KEEP',
            'HEWLETT PACKARD CO: Our primary competitors include technology vendors such as International Business Machines Corporation ("IBM"), Dell, EMC Corporation ("EMC"'),
    Decision('ANET', '0001262039', True, 'KEEP',
            'Fortinet, Inc.: Among others, our competitors include Arista Networks, Inc.(“Arista”), Aruba Networks, Inc.(“Aruba”), Barracuda Networks, Inc. (“Barracuda”)'),
    Decision('ANET', '0001645590', True, 'KEEP',
            'Hewlett Packard Enterprise Co: Our primary competitors include technology vendors such as Cisco Systems, Inc., Extreme Networks, Inc., Juniper Networks, Inc., Aerohive Net'),
    Decision('AON', '0001140536', True, 'KEEP',
            'WILLIS TOWERS WATSON PLC: We compete with Accenture plc, Aon plc, Arthur J. Gallagher & Co., Brown & Brown Inc., Cognizant Technology Solutions Corporation, Marsh & M'),
    Decision('APPF', '0001286225', True, 'KEEP',
            'REALPAGE INC: Our current principal competitors include: • in the multi-family ERP market, AMSI Property Management (owned by Infor Global Solutions, Inc.'),
    Decision('APTV', '0001043337', True, 'KEEP',
            'STONERIDGE INC: Our primary competitors include Actia Group, Aptiv, Bosch, Continental AG, Dongfeng Electronics Technology Co., Ltd., Hella KGaA Hueck & Co.'),
    Decision('ARMK', '0000717954', True, 'KEEP',
            'UNIFIRST CORP: Our principal competitors include Cintas Corporation, Aramark Corporation and G&K Services, Inc. It was recently announced that Cintas Corpo'),
    Decision('AVTR', '0000024741', True, 'KEEP',
            'CORNING INC /NY: Our principal competitors include Thermo Fisher Scientific, Inc., Avantor, Inc., Greiner AG, Eppendorf AG, Sarstedt AG and Danaher Corporati'),
    Decision('AVTR', '0001028215', True, 'KEEP',
            'KMG CHEMICALS INC: 4 Table of Contents In electronic chemicals in North America, we believe that we have the largest market share, and our principal competitor'),
    Decision('AYI', '0000917523', True, 'KEEP',
            'Nexxus Lighting, Inc.: We compete with traditional lighting companies, including Acuity Brands Lighting, Cooper Lighting, Hubbell Lighting and Royal Philips Electr'),
    Decision('AYI', '0001662574', True, 'KEEP',
            'Illumination America, Inc.: We compete with traditional lighting companies, including Acuity Brands Lighting, Inc., Cooper Lighting (a division of Cooper Industries, In'),
    Decision('BAH', '0001050031', True, 'KEEP',
            'SM&A: Some of our competitors include Booz Allen Hamilton and Volt Information Technology.'),
    Decision('BAH', '0001394120', True, 'KEEP',
            'PARKVIEW GROUP INC: Our competitors include large international firms such as Booz Allen Hamilton and McKinsey & Company, as well as numerous regional and local'),
    Decision('BAX', '0000067887', True, 'KEEP',
            'MOOG INC: In Medical Devices, principal competitors include Smiths Medical, Hospira, Cardinal Health, Baxter International, CME and I-Flow.'),
    Decision('BBY', '0000744187', True, 'KEEP',
            'REX STORES CORP: Our competitors include national and regional large format merchandisers and superstores such as Best Buy Co., Inc. and Circuit City Stores,'),
    Decision('BBY', '0000791519', True, 'KEEP',
            'STAPLES INC: As we rapidly expand our assortment of products and services, we compete directly with an increasing number of competitors including online'),
    Decision('BHF', '0001535929', True, 'KEEP',
            'Voya Financial, Inc.: Primary competitors include Lincoln, Brighthouse Financial, National Life Group, North American Company, American General, John Hancock, Tra'),
    Decision('BIO', '0000860451', True, 'KEEP',
            'BIOSOURCE INTERNATIONAL INC: Our primary competitors include companies such as Techne Corporation, BD BioSciences, Cell Signaling Technologies, Bio-Rad Laboratories, Ser'),
    Decision('BKNG', '0001133311', True, 'KEEP',
            'TRAVELZOO: We compete with large online travel agencies like Expedia and Booking Holdings that also offer advertising placements and hotel booking plat'),
    Decision('BKNG', '0001559720', True, 'KEEP',
            'Airbnb, Inc.: Our competitors include: • Online travel agencies (“OTAs”), such as Booking Holdings (including the brands Booking.com, KAYAK, Priceline.com'),
    Decision('BKR', '0001603923', True, 'KEEP',
            'Weatherford International plc: Our principal competitors include SLB, Halliburton, Baker Hughes, National Oilwell Varco, ChampionX and Expro Group Holdings.'),
    Decision('BMRN', '0000885259', True, 'KEEP',
            'TRANSKARYOTIC THERAPIES INC: Competitors include BioMarin Pharmaceutical Inc., Genzyme, Oxford GlycoSciences plc, and Synpac Pharmaceuticals, Ltd. The markets for some o'),
    Decision('BMRN', '0001439222', True, 'KEEP',
            'AGIOS PHARMACEUTICALS INC: In the field of IEMs, our principal competitors include Alexion Pharmaceuticals, Inc., BioMarin Pharmaceutical, Inc., Genzyme, a Sanofi comp'),
    Decision('BRK-B', '0000011544', True, 'KEEP',
            'BERKLEY W R CORP: These competitors include Berkshire Hathaway, Employers Reinsurance, Transatlantic Reinsurance and 16 Everest Reinsurance, which collectivel'),
    Decision('BRK-B', '0000850460', True, 'KEEP',
            'ENCORE WIRE CORP: The Company’s primary competitors include Southwire Company, LLC, Cerrowire (a Marmon/Berkshire Hathaway company), General Cable (a company'),
    Decision('BRK-B', '0001141719', True, 'KEEP',
            'MAX RE CAPITAL LTD: Our worldwide reinsurance competitors include ACE Limited, American International Group, Inc., Berkshire Hathaway, Inc., Swiss Reinsurance C'),
    Decision('BSX', '0001002811', True, 'KEEP',
            'KENSEY NASH CORP: The TriActiv is currently 14 only commercially available in Europe, where our competitors include Boston Scientific Corporation, Johnson and'),
    Decision('BSX', '0001099800', True, 'KEEP',
            'Edwards Lifesciences Corp: In Transcatheter Heart Valve Therapy, our primary competitors include Medtronic PLC, Boston Scientific Corporation, and Abbott Laboratories.'),
    Decision('BSY', '0000769397', True, 'KEEP',
            'AUTODESK INC: In our Design Solutions Segment, our primary global competitors include Dassault Systems and its SolidWorks subsidiary, Parametric Technolog'),
    Decision('CACI', '0000102379', True, 'KEEP',
            'URS CORP /NEW/: Our competitors are numerous, ranging from small private firms to multi-billion dollar public companies, and our primary competitors include'),
    Decision('CACI', '0000906192', True, 'KEEP',
            'SRA INTERNATIONAL INC: These competitors include: • Federal systems integrators such as CACI International Inc., Computer Sciences Corporation, ManTech Internation'),
    Decision('CACI', '0000918581', True, 'KEEP',
            'CIBER INC: Our principal competitors include Accenture Ltd., BearingPoint, Inc., CACI International, Inc., CGI Group Inc. and MAXIMUS, Inc. We also com'),
    Decision('CACI', '0001166568', True, 'KEEP',
            'ALION SCIENCE & TECHNOLOGY CORP: Our competitors include Booz Allen Hamilton, BAE, Battelle, CACI International Inc, Science Applications International Corporation, SRA Inte'),
    Decision('CACI', '0002011286', True, 'KEEP',
            'Amentum Holdings, Inc.: Amentum\'s primary competitors include Booz Allen Hamilton Inc., CACI International Inc., KBR Inc., Leidos Holdings Inc., ManTech Internation'),
    Decision('CARR', '0001488139', True, 'KEEP',
            'Ameresco, Inc.: Our principal competitors include: • Smart Energy Solutions : Constellation Energy Group, Inc. (an Exelon company), Energy Systems Group, Ho'),
    Decision('CBRE', '0001037976', True, 'KEEP',
            'JONES LANG LASALLE INC: Some of our primary competitors include large national or global firms including CBRE Group Inc., Cushman & Wakefield plc, Colliers Internat'),
    Decision('CBRE', '0001408100', True, 'KEEP',
            'Kennedy-Wilson Holdings, Inc.: Our principal competitors include both large multinational companies and national and regional firms, such as Jones Lang LaSalle, Inc. and C'),
    Decision('CBRE', '0001497770', True, 'KEEP',
            'Walker & Dunlop, Inc.: Our competitors include, but are not limited to, Wells Fargo, N.A., CBRE Group, Inc., Jones Lang LaSalle Incorporated, Marcus & Millichap, I'),
    Decision('CEG', '0001428389', True, 'KEEP',
            'Blox, Inc.: For our proposed services division, our principal competitors include large established companies such as Chevron Energy Solutions, Constell'),
    Decision('CHD', '0001016179', True, 'KEEP',
            'DIAL CORP /NEW/: Our principal competitors are as follows: Personal Cleansing • The Procter & Gamble Company (“P&G”) • Lever Brothers Co., a division of Unil'),
    Decision('CHD', '0001298095', True, 'KEEP',
            'Infusion Brands International, Inc.: Our major competitors include consumer products companies such as Emerson, Bosch, Church & Dwight Co., Estee Lauder, Alberto Culver, Reckitt'),
    Decision('CHRW', '0000101063', True, 'KEEP',
            'CHIQUITA BRANDS INTERNATIONAL INC: Our primary competitors are Crunch Pak, C.H. Robinson Worldwide, Tree Top Inc., Reichel Foods, Inc. and other regional producers of branded'),
    Decision('CHRW', '0001929561', True, 'KEEP',
            'RXO, Inc.: Our competitors include C.H. Robinson, Convoy, Coyote, Echo, Expeditors, Forward Air, Flexport, J.B.'),
    Decision('CHTR', '0001096788', True, 'KEEP',
            'KNOLOGY INC: Our competitors include Comcast Cable Communications, Time Warner Cable and Charter Communications.'),
    Decision('CLX', '0000314227', True, 'KEEP',
            'TOMI Environmental Solutions, Inc.: Our competitors include companies that market other hydrogen peroxide-based products, such as Steris Corporation (“Steris”), Bioquell, Inc.'),
    Decision('CLX', '0001310527', True, 'KEEP',
            'Anpath Group, Inc.: Industrial, Consumer, Hospitality, Military In the industrial and consumer markets our primary competitors include Johnson & Johnson, Ecolab'),
    Decision('CMCSA', '0001445175', True, 'KEEP',
            'HighLight Networks, Inc.: Principal competitors include cable companies, such as Time Warner and Comcast, as well as incumbent telephone companies, such as AT&T, Qwes'),
    Decision('CNC', '0000731766', True, 'KEEP',
            'UNITEDHEALTH GROUP INC: For our UnitedHealthcare businesses, our competitors include Aetna Inc., Anthem, Inc., Centene Corporation, Cigna Corporation, Humana Inc.,'),
    Decision('CNH', '0000018230', True, 'KEEP',
            'CATERPILLAR INC: Examples of global competitors include CASE (part of CNH Industrial N.V.), Deere Construction & Forestry (part of Deere & Company), Doosan B'),
    Decision('COHR', '0001730168', True, 'KEEP',
            'Broadcom Inc.: In semiconductor solutions, we compete with integrated device manufacturers, fabless semiconductor companies and the internal resources of l'),
    Decision('COIN', '0002055592', True, 'KEEP',
            'Gemini Space Station, Inc.: Our primary competitors include Coinbase and Robinhood, among others.'),
    Decision('COR', '0000891024', True, 'KEEP',
            'PATTERSON COMPANIES, INC.: In the U.S. and Canadian animal health supply market, our primary competitors are Cencora/MWI Animal Health and Covetrus, Inc. We also compe'),
    Decision('CPAY', '0001720592', True, 'KEEP',
            'Repay Holdings Corp: In our Business Payments segment, our primary competitors include AvidXchange, Edenred Pay (a division of Edenred), Corpay (a division of Fl'),
    Decision('CRUS', '0000004127', True, 'KEEP',
            'SKYWORKS SOLUTIONS, INC.: Our competitors include Analog Devices, Broadcom, Cirrus Logic, Maxim Integrated Products, Murata Manufacturing, NXP Semiconductors, Qorvo a'),
    Decision('CRWD', '0001107843', True, 'KEEP',
            'QUALYS, INC.: 12 Table of Contents We compete with large and small public companies, such as FireEye, Inc., Imperva, Inc., International Business Machines'),
    Decision('CSGP', '0001286225', True, 'KEEP',
            'REALPAGE INC: In the market for multi-family housing market research, we compete with Reis, Inc., Axiometrics, Inc., Pierce-Eislen, Inc., CoStar Group, In'),
    Decision('CSGP', '0001353209', True, 'KEEP',
            'LoopNet, Inc.: We compete with CoStar Group, Inc., a provider of information and research services to the commercial real estate market.'),
    Decision('CTAS', '0000717954', True, 'KEEP',
            'UNIFIRST CORP: Our principal competitors include Cintas Corporation, Aramark Corporation and G&K Services, Inc. It was recently announced that Cintas Corpo'),
    Decision('CTSH', '0000918581', True, 'KEEP',
            'CIBER INC: Our principal competitors include Accenture plc, Atos Origin SA, BearingPoint, Inc, CACI International Inc, Cap Gemini SA, CGI Group Inc., C'),
    Decision('CTSH', '0001040426', True, 'KEEP',
            'SYNTEL INC: The Company’s most direct competitors include Cognizant, Infosys Technologies, Tata Consultancy Services and Wipro Technologies that utilize'),
    Decision('CTSH', '0001677703', True, 'KEEP',
            'CONDUENT Inc: Our competitors include: • Large multinational service providers such as CGI Group, Accenture, Aon Hewitt, Cognizant, Hewlett-Packard Enterp'),
    Decision('CVLT', '0000735993', True, 'KEEP',
            'BAKBONE SOFTWARE INC: Our current competitors include, but are not limited to, Veritas Software Corporation, EMC Corporation, IBM’s Tivoli division, Computer Asso'),
    Decision('CVS', '0000731766', True, 'KEEP',
            'UNITEDHEALTH GROUP INC: For our OptumRx businesses, our competitors include CVS Health Corporation, Express Scripts, Inc. and Prime Therapeutics LLC. New entrants i'),
    Decision('CVX', '0001408356', True, 'KEEP',
            'SOLARCITY CORP: In the commercial solar energy system installation market, our competitors include Chevron Corporation, SunPower Corporation and Team Solar,'),
    Decision('DASH', '0001477815', True, 'KEEP',
            'Sweetgreen, Inc.: We compete with delivery kitchens, food aggregators, and third-party delivery marketplaces such as DoorDash, Grubhub, and Uber Eats, as well'),
    Decision('DBX', '0001084182', True, 'KEEP',
            'IMMEDIATEK INC: Our primary competitors include Amazon, Google, Microsoft, EMC, Box.net, Dropbox.com, Sugarsync, Carbonite and others.'),
    Decision('DCI', '0000076334', True, 'KEEP',
            'PARKER HANNIFIN CORP: While our primary global competitors include Bosch Rexroth AG, Danaher Corporation, Danfoss A/S, Donaldson Company, Inc., Eaton Corporation'),
    Decision('DDOG', '0001078075', True, 'KEEP',
            'NETSCOUT SYSTEMS INC: In the enterprise market, our competitors include companies who provide network performance management, application performance management,'),
    Decision('DDOG', '0001643269', True, 'KEEP',
            'Sumo Logic, Inc.: Other competitors include Datadog and New Relic, cloud infrastructure providers such as Amazon Web Services, Microsoft Azure, or Azure, Goog'),
    Decision('DELL', '0001645590', True, 'KEEP',
            'Hewlett Packard Enterprise Co: Our primary competitors include technology vendors such as Dell Technologies Inc. ("Dell"), Cisco Systems, Inc. ("Cisco"), NetApp, Inc., Len'),
    Decision('DGX', '0000876645', True, 'KEEP',
            'PHARMCHEM INC: Our competitors include: - national clinical laboratory companies, such as Laboratory Corporation of America Holdings and Quest Diagnostics,'),
    Decision('DGX', '0001123333', True, 'KEEP',
            'SPECIALTY LABORATORIES: Our primary competitors include: • large commercial enterprises, such as Quest Diagnostics, or Quest, and Laboratory Corporation of America,'),
    Decision('DHI', '0000830122', True, 'KEEP',
            'PICO HOLDINGS INC /NEW: We compete directly with a number of national homebuilders such as D. R. Horton Inc., Hovnanian Enterprises, Inc. and Lennar Corporation who'),
    Decision('DHI', '0001572684', True, 'KEEP',
            'UCP, Inc.: We compete directly with a number of large national homebuilders such as D. R. Horton Inc., Hovnanian Enterprises, Inc. and Lennar Corporati'),
    Decision('DPZ', '0001548621', True, 'KEEP',
            'NPC Restaurant Holdings, LLC: Within the QSR pizza segment, we compete directly with Domino\'s Pizza, Papa John\'s, Little Caesars, Cici\'s and numerous regional chains and'),
    Decision('DUOL', '0001351285', True, 'KEEP',
            'ROSETTA STONE INC: Within consumer-focused language learning, our competitors include Berlitz International Inc., Simon & Schuster, Inc. (Pimsleur), Random Hou'),
    Decision('DVA', '0001083446', True, 'KEEP',
            'Apollo Medical Holdings, Inc.: For example, in Los Angeles, examples of our competitors include Regal Medical Group and Lakeside Medical group, which are part of the Herit'),
    Decision('DVA', '0001418115', True, 'KEEP',
            'Healthcare Solutions Management Group, Inc.: Our primary competitors are HCA Healthcare, Texas Health Resources, UT Southwestern Medical Center, Tenet, DaVita and VCA.'),
    Decision('ECHO', '0001290729', True, 'KEEP',
            'Grande Communications Holdings, Inc.: Our primary competitors include: • for cable television services, TimeWarner, CableOne, Cox Communications, Comcast, Charter Communications,'),
    Decision('ECL', '0000314227', True, 'KEEP',
            'TOMI Environmental Solutions, Inc.: Our competitors include companies that market other hydrogen peroxide-based products, such as Steris Corporation (“Steris”), Bioquell, Inc.'),
    Decision('ECL', '0001121302', True, 'KEEP',
            'SYBRON DENTAL SPECIALTIES INC: Our competitors include Johnson and Johnson, Steris Corporation and Ecolab, Inc. RESEARCH AND DEVELOPMENT We have a number of research and d'),
    Decision('ELAN', '0001069899', True, 'KEEP',
            'PHIBRO ANIMAL HEALTH CORP: Some of our principal competitors include Bayer AG, Ceva Santé Animale, Boehringer Ingelheim International GMBH, Eli Lilly and Company (Elan'),
    Decision('ELV', '0001801170', True, 'KEEP',
            'CLOVER HEALTH INVESTMENTS, CORP. /DE: Our competitors include large, national insurers, such as UnitedHealth, Aetna, Humana, Cigna, Centene, and Elevance Health, as well as regio'),
    Decision('EME', '0001679268', True, 'KEEP',
            'MAMMOTH ENERGY SERVICES, INC.: r competitors in pressure pumping services include Halliburton Company, U.S. Well Services, LLC, Schlumberger Limited, Keane Group, Inc., C&'),
    Decision('EMR', '0000315449', True, 'KEEP',
            'UQM TECHNOLOGIES INC: The Company believes its principal competitors include Advanced DC, Owosso Corporation, Emerson Electric, General Electric, Rockwell Interna'),
    Decision('EMR', '0000926326', True, 'KEEP',
            'OMNICELL, Inc: Other competitors include McKesson Automation Inc. (a business unit of McKesson Corporation), AmerisourceBergen Corporation (through its acq'),
    Decision('EMR', '0001114925', True, 'KEEP',
            'LANTRONIX INC: Our primary competitors include companies such as Avocent (a business of Emerson Electric), Digi International, Moxa Technologies, Raritan C'),
    Decision('ENS', '0001622345', True, 'KEEP',
            'Polar Power, Inc.: Our competitors include battery manufacturers like Tesla, Exide, Enersys, Panasonic, Axiom, Samsung, Deka and Trojan batteries.'),
    Decision('ETN', '0000708250', True, 'KEEP',
            'SCIENTIFIC TECHNOLOGIES INC: Our competitors include, among others, Honeywell, Rockwell Automation, Eaton Corporation, Banner Engineering, Sick Optic- Electronic, Inc.,'),
    Decision('EXEL', '0001057217', True, 'KEEP',
            'PARADIGM GENETICS INC: In the areas of crop trait, crop protection discovery and green biotechnology, our competitors include Exelixis, Inc., Ceres, Inc., Mendel B'),
    Decision('EXPD', '0001048911', True, 'KEEP',
            'FEDEX CORP: FedEx Trade Networks’s primary competitors are U.S.-based customs brokers and freight forwarders, such as UPS Freight Services (formerly Fri'),
    Decision('EXPD', '0001311953', True, 'KEEP',
            'Summit Global Logistics, Inc.: Primary competitors include, but are not limited to, Expeditors International of Washington, Inc., UTI Worldwide Inc. and Panalpina World Tr'),
    Decision('FAF', '0000890926', True, 'KEEP',
            'RADIAN GROUP INC: Significant competitors include: • Mortgage Services - American Mortgage Consultants, Inc., Digital Risk, LLC, Opus Capital Markets Consulta'),
    Decision('FAF', '0001331875', True, 'KEEP',
            'Fidelity National Financial, Inc.: In our principal markets, competitors include other major title underwriters such as First American Financial Corporation, Old Republic Inte'),
    Decision('FBIN', '0001782754', True, 'KEEP',
            'AZEK Co Inc.: In addition to wood, we compete with other manufacturers of wood-alternative products, including Trex Company Inc., Fiberon, a subsidiary of'),
    Decision('FCN', '0001027207', True, 'KEEP',
            'EPIQ SYSTEMS INC: Competitors include Kroll Ontrack (Altegrity Inc.), FTI Consulting, Inc., Huron Consulting Group Inc., The Dolan Company, Symantec Corporati'),
    Decision('FDS', '0001289419', True, 'KEEP',
            'Morningstar, Inc.: For Licensed Data, our primary competitors are Bloomberg, Europerformance, eVestment Alliance, FactSet Research Systems, Financial Express,'),
    Decision('FDX', '0000791519', True, 'KEEP',
            'STAPLES INC: As we rapidly expand our assortment of products and services, we compete directly with an increasing number of competitors including mass me'),
    Decision('FDXF', '0000894405', True, 'KEEP',
            'ARKANSAS BEST CORP /DE/: Competitors include Yellow Transportation and Roadway Express, (operated by YRC Worldwide, Inc.), FedEx Freight (operated by FedEx Corporati'),
    Decision('FIS', '0000896878', True, 'KEEP',
            'INTUIT INC: In our merchant services business we compete directly with large financial institutions such as Wells Fargo, JP Morgan Chase, and Bank of Am'),
    Decision('FISV', '0001109190', True, 'KEEP',
            'EFUNDS CORP: In the electronic payments market, our principal competitors include: - third-party debit network processors, including First Data, VISA Deb'),
    Decision('FISV', '0001136893', True, 'KEEP',
            'Fidelity National Information Services, Inc.: In this market we compete with International Business Machines Corporation (IBM), Fiserv, Inc., Jack Henry and Associates, Inc., Accenture L'),
    Decision('FLEX', '0000863436', True, 'KEEP',
            'BENCHMARK ELECTRONICS INC: Our competitors include Celestica Inc., Flex Ltd., Hon Hai Precision Industry Co., Ltd., Jabil Circuit, Inc., Plexus Corp and Sanmina Corpor'),
    Decision('FLG', '0001038459', True, 'KEEP',
            'O A K FINANCIAL CORP: Within these communities, its principal competitors are Comerica Bank, JP Morgan Chase, Fifth-Third Bank, Flagstar Bank, National City Bank,'),
    Decision('FLR', '0000102379', True, 'KEEP',
            'URS CORP /NEW/: Our competitors are numerous, ranging from small private firms to multi-billion dollar public companies, and our primary competitors include'),
    Decision('FLS', '0001028215', True, 'KEEP',
            'KMG CHEMICALS INC: Our principal competitors include Flowserve Corporation and JetLube, Inc. Employees As of the end of fiscal year 2015, we had a total of 657'),
    Decision('FNF', '0000094344', True, 'KEEP',
            'STEWART INFORMATION SERVICES CORP: Our principal competitors include Fidelity National Financial, Inc., The First American Corporation and LandAmerica Financial Group, Inc. Li'),
    Decision('FTI', '0000808362', True, 'KEEP',
            'BAKER HUGHES a GE Co LLC: In the SPS product line, the primary competitors of OFE include Schlumberger, TechnipFMC, Aker Solutions ASA, Proserv and Dril-Quip Inc. In'),
    Decision('FTI', '0001701605', True, 'KEEP',
            'Baker Hughes a GE Co: In the SPS product line, the primary competitors of OFE include Schlumberger, TechnipFMC, Aker Solutions ASA, Proserv, and Dril-Quip Inc. In'),
    Decision('FTNT', '0000096699', True, 'KEEP',
            'TECHNICAL COMMUNICATIONS CORP: The Company believes its principal competitors include Thales Group, Codan Limited and Fortinet, Inc. 5 The Company competes based on its se'),
    Decision('FTNT', '0001645590', True, 'KEEP',
            'Hewlett Packard Enterprise Co: Our primary competitors include technology vendors such as Cisco Systems, Inc., Extreme Networks, Inc., Juniper Networks, Inc., Aerohive Net'),
    Decision('FTNT', '0002063196', True, 'KEEP',
            'Netskope Inc: Our primary competitors include companies such as Broadcom, Cisco, Fortinet, Palo Alto Networks, and Zscaler.'),
    Decision('FTV', '0000046129', True, 'KEEP',
            'ALLIED MOTION TECHNOLOGIES INC: Our competitors include Ametek, Fortive Corporation, Parker Hannifin Corporation and other smaller competitors.'),
    Decision('GAP', '0001323531', True, 'KEEP',
            'Maidenform Brands, Inc.: Our primary competitors include Aerie by American Eagle, Cupid Foundations, Inc., Gap Inc., Fruit of the Loom, Inc., Hanesbrands, Inc., Jock'),
    Decision('GDDY', '0001365038', True, 'KEEP',
            'DEMAND MEDIA INC.: Our principal competitors include existing registrars, such as GoDaddy, Tucows and Melbourne IT, and new registrars entering the domain name'),
    Decision('GEN', '0001122904', True, 'KEEP',
            'NETGEAR, INC.: Our potential competitors include other consumer electronics vendors, including Apple, Gen Digital (formerly NortonLifelock), LG Electronics'),
    Decision('GEV', '0001377789', True, 'KEEP',
            'AVIAT NETWORKS, INC.: Our principal competitors include business units of large mobile and IP network infrastructure manufacturers such as Ericsson, Huawei, ZTE,'),
    Decision('GMED', '0001499807', True, 'KEEP',
            'K2M GROUP HOLDINGS, INC.: We believe that our principal competitors include Medtronic Spine and Biologics, DePuy Synthes, Stryker, Globus Medical and NuVasive, which'),
    Decision('GNRC', '0000014195', True, 'KEEP',
            'BRIGGS & STRATTON CORP: Primary competitors include: Honda (portable generators, pressure washers and lawn and garden equipment), Coleman Powermate Corporation (por'),
    Decision('GNRC', '0001622345', True, 'KEEP',
            'Polar Power, Inc.: Our competitors include Caterpillar, Generac, Cummins, 3-Tech, Ascot, Ausonia, Controllis and Kohler.'),
    Decision('GNTX', '0000814926', True, 'KEEP',
            'CAPSTONE COMPANIES, INC.: Competitors include Gentex Corporation, Seura Solutions, Inc., Magna International, Inc. and Samsung Electronics Co. Ltd. The competitivenes'),
    Decision('GOOGL', '0000798354', True, 'KEEP',
            'FISERV INC: These newer competitors include, but are not limited to, Alphabet Inc., Amazon.com, Inc., Apple Inc., Facebook, Inc., Intuit Inc., PayPal Ho'),
    Decision('GPN', '0000721683', True, 'KEEP',
            'TOTAL SYSTEM SERVICES INC: Our primary competitors include First Data Corporation (and its alliances), Vantiv, Inc., Global Payments Inc. and Elavon, Inc. Additionally'),
    Decision('GPN', '0000896878', True, 'KEEP',
            'INTUIT INC: In our merchant services business we compete directly with large financial institutions such as Wells Fargo, JP Morgan Chase and Bank of Ame'),
    Decision('GRMN', '0000836690', True, 'KEEP',
            'INNOVATIVE SOLUTIONS & SUPPORT INC: With respect to air data systems and related products, the Company’s principal competitors include Honeywell International Inc. (“Honeywell”'),
    Decision('GRMN', '0001383196', True, 'KEEP',
            'Location Based Technologies, Inc.: Our competitors include, but are not limited to: Geospatial Platform Providers, Application Developers, Garmin’s GTU-10, Qualcomm’s Tagg, Lo'),
    Decision('HAL', '0000833845', True, 'KEEP',
            'BOOTS & COOTS INTERNATIONAL WELL CONTROL INC: Our main competitors include Halliburton Company, Cudd Pressure Control, a subsidiary of RPC, Inc., International Snubbing Services (ISS) an'),
    Decision('HAL', '0001603923', True, 'KEEP',
            'Weatherford International plc: Our principal competitors include Schlumberger, Halliburton, Baker Hughes (a GE company), National Oilwell Varco, Nabors Industries and Fran'),
    Decision('HCA', '0001418115', True, 'KEEP',
            'Healthcare Solutions Management Group, Inc.: Our primary competitors are HCA Healthcare, Texas Health Resources, UT Southwestern Medical Center, Tenet, DaVita and VCA.'),
    Decision('HGV', '0000723612', True, 'KEEP',
            'CENDANT CORP: Our largest competitors include Disney Vacation Club, Marriott Ownership Resorts, Inc., Starwood Vacation Ownership, Inc. and Hilton Grand V'),
    Decision('HONA', '0000836690', True, 'KEEP',
            'INNOVATIVE SOLUTIONS & SUPPORT INC: With respect to our products, the Company’s principal competitors include Honeywell Aerospace, Collins Aerospace, GE Aerospace, Thales Defen'),
    Decision('HOOD', '0001889123', True, 'KEEP',
            'Fold Holdings, Inc.: Financial Platforms Across our product lines we compete with various traditional financial services providers like Block Inc., Robinhood Mar'),
    Decision('HQY', '0001704720', True, 'KEEP',
            'Cannae Holdings, Inc.: Alight\'s primary competitors include Accenture, Accolade, ADP, bswift, Businessolver, Cognizant, Conduent, Deloitte, Empower, Fidelity, Incl'),
    Decision('HQY', '0001809104', True, 'KEEP',
            'Alight, Inc. / Delaware: Our primary competitors include Accenture, Accolade, ADP, Benefitfocus, bswift, Businessolver, Cognizant, Conduent, Deloitte, eHealth, Empow'),
    Decision('HRB', '0001068875', True, 'KEEP',
            'BLUCORA, INC.: These competitors include Intuit’s TurboTax and H&R Block’s DDIY consumer products and services, which currently serve a significant percent'),
    Decision('HRL', '0000880117', True, 'KEEP',
            'SANFILIPPO JOHN B & SON INC: In the nut industry, we compete with, among others, Hormel Foods Corp. (Planters brand), Diamond brand and numerous regional snack food proc'),
    Decision('HRL', '0001302977', True, 'KEEP',
            'Wornick CO: please see the related risk factors under “Management’s Discussion and Analysis of Financial Condition and Results of Operations—Risk Facto'),
    Decision('HRL', '0001326531', True, 'KEEP',
            'TWC Holding LLC: For a discussion of these risks, please see the related risk factors under Part I, Item 1A, “Risk Factors—Risks Related to Our Business.” In'),
    Decision('HUBB', '0000885475', True, 'KEEP',
            'SimplePons, Inc.: We compete with traditional lighting companies, including Acuity Brands Lighting, Inc., Cooper Lighting (a division of Cooper Industries, In'),
    Decision('HUBB', '0000917523', True, 'KEEP',
            'Nexxus Lighting, Inc.: 7 We compete with traditional lighting companies, including Acuity Brands Lighting, Inc., Cooper Lighting (a division of Cooper Industries,'),
    Decision('HUBB', '0001662574', True, 'KEEP',
            'Illumination America, Inc.: We compete with traditional lighting companies, including Acuity Brands Lighting, Inc., Cooper Lighting (a division of Cooper Industries, In'),
    Decision('HUM', '0000731766', True, 'KEEP',
            'UNITEDHEALTH GROUP INC: For our Uniprise and Health Care Services businesses, competitors include Aetna, Anthem, Cigna, Coventry, Humana, PacifiCare, Oxford, WellPo'),
    Decision('HUM', '0001339553', True, 'KEEP',
            'HealthSpring, Inc.: Our primary competitors include Blue Cross Blue Shield of Alabama, Humana Inc., UnitedHealth Group, and VIVA Health, Inc., a member of the U'),
    Decision('HWM', '0000842633', True, 'KEEP',
            'TRIMAS CORP: Competition Depending on the product and customers served, our primary competitors include Ateliers de la Haute Garonne, Cherry Aerospace -'),
    Decision('IBM', '0001102542', True, 'KEEP',
            'SCO GROUP INC: In the operating system market, some of our competitors include International Business Machines Corporation (“IBM”), Red Hat Inc. (“Red Hat”'),
    Decision('IBM', '0001109190', True, 'KEEP',
            'EFUNDS CORP: In the global outsourcing market, our competitors include Spectramind/Wipro Ltd, Intelenet Global Services Ltd., Progeon Ltd. (an Infosys Te'),
    Decision('INTC', '0000918386', True, 'KEEP',
            'QLOGIC CORP: In the FCoE adapter market, we compete with Emulex Corporation, and recent entry, Brocade Communications Systems, Inc. and we also compete w'),
    Decision('INTU', '0001117106', True, 'KEEP',
            'NETSUITE INC: Our current principal competitors include Epicor Software Corporation, Intuit Inc., Microsoft Corporation, SAP, The Sage Group plc and sales'),
    Decision('IPGP', '0001633978', True, 'KEEP',
            'Lumentum Holdings Inc.: Competition We compete against various public and private companies in the commercial laser markets we serve including Coherent and IPG Phot'),
    Decision('IPGP', '0001814215', True, 'KEEP',
            'Nuburu, Inc.: We compete directly with mature competitors such as Coherent, Inc., IPG Photonics Corporation, Laserline GmbH, Lumentum Holdings Inc., Raycu'),
    Decision('IQV', '0001829280', True, 'KEEP',
            'Forian Inc.: In general, our competitors include a variety of entities such as information and clinical analytics providers like ICON plc, information an'),
    Decision('ISRG', '0000876378', True, 'KEEP',
            'TRANSENTERIX INC.: Our surgical competitors include, but are not limited to: Applied Medical, Medtronic plc, Intuitive Surgical, Titan Medical and Verb Surgica'),
    Decision('JBL', '0000315449', True, 'KEEP',
            'UQM TECHNOLOGIES INC: The Company believes its principal competitors include Jabil Circuit, Plexus, EFTC Corporation, Flextronics International, Solestica Corpora'),
    Decision('JBL', '0000863436', True, 'KEEP',
            'BENCHMARK ELECTRONICS INC: Our competitors include Celestica, Inc., Flextronics International Ltd., Jabil Circuit, Inc., SCI Systems, Inc. and Solectron Corporation, w'),
    Decision('JHG', '0001535929', True, 'KEEP',
            'Voya Financial, Inc.: Our principal competitors include insurance-owned asset managers such as Principal Global Investors (Principal Financial Group), Prudential'),
    Decision('JLL', '0001408100', True, 'KEEP',
            'Kennedy-Wilson Holdings, Inc.: Our principal competitors include both large multinational companies and national and regional firms, such as Jones Lang LaSalle, Inc. and C'),
    Decision('KBH', '0001721386', True, 'KEEP',
            'Landsea Homes Corp: While our competitors vary by market, we compete directly with major national builders such as KB Home, Lennar Corp., Tri Pointe Homes, Inc.'),
    Decision('KBR', '0000914024', True, 'KEEP',
            'SHAW GROUP INC: Companies that we compete with in our E&I segment include CH2M Hill, URS Corporation, TetraTech, Inc. and KBR, Inc. Companies that we compet'),
    Decision('KBR', '0001333142', True, 'KEEP',
            'DynCorp International LLC: Our competitors include Civilian Police International, Science Applications International Corporation, ITT Corporation, KBR, Inc., IAP World'),
    Decision('KBR', '0001338916', True, 'KEEP',
            'DYNCORP INTERNATIONAL INC.: Our competitors include Civilian Police International, Science Applications International Corporation, ITT Corporation, KBR, Inc., IAP World'),
    Decision('KBR', '0001601548', True, 'KEEP',
            'V2X, Inc.: Our principal competitors include Amentum Holdings, Inc., Valiant Integrated Services, divisions of Leidos Holdings, Inc., Science Applicati'),
    Decision('KBR', '0001720821', True, 'KEEP',
            'PAE Inc: PAE’s principal competitors include Amentum, Booz Allen Hamilton, CACI International Inc., Jacobs Engineering Group Inc., KBR, Inc., Leidos,'),
    Decision('KLAC', '0000064463', True, 'KEEP',
            'MECHANICAL TECHNOLOGY INC: on automated manufacturing market, MTI Instruments faces competition from companies including Omron Corporation, Turck Inc., Pepperl+Fuchs I'),
    Decision('KMB', '0000815065', True, 'KEEP',
            'STERIS CORP: The segment’s primary competitors include Getinge, Belimed, Johnson & Johnson, 3M, Ecolab, Cardinal, Skytron, Berchtold, Kimberly-Clark, and'),
    Decision('KNSL', '0001761312', True, 'KEEP',
            'Palomar Holdings, Inc.: Our primary competitors include national specialty insurance companies, including Kinsale Capital Group, Inc., RLI Corp., Skyward Specialty'),
    Decision('KTOS', '0001081078', True, 'KEEP',
            'API Technologies Corp.: Some of our principal competitors include Aeroflex, Incorporated, Anaren Inc., (NASDAQ: ANEN), Data Devices Inc., Kratos Defense & Security'),
    Decision('KVUE', '0001585364', True, 'KEEP',
            'PERRIGO Co plc: Our primary competitors include manufacturers, such as Dr. Reddy\'s Labs, LNK International, Inc., PL Developments, Aurobindo and Sun Pharmac'),
    Decision('LDOS', '0000785557', True, 'KEEP',
            'DLH Holdings Corp.: Our competitors include operating units within, among others: Booz Allen Hamilton Holding Corp., CACI International, Inc., ICF International'),
    Decision('LDOS', '0001994624', True, 'KEEP',
            'ScanTech AI Systems Inc.: Our competitors include Leidos, Smiths Detection, Analogic Corporation and IDSS Corp. The markets in which we plan to operate are characteri'),
    Decision('LEA', '0000053669', True, 'KEEP',
            'JOHNSON CONTROLS INC: Independent suppliers that represent the segment\'s principal competitors include Lear Corporation, Faurecia, Intier Automotive, Delphi Corpo'),
    Decision('LEN', '0001721386', True, 'KEEP',
            'Landsea Homes Corp: While our competitors vary by market, we compete directly with major national builders such as KB Home, Lennar Corp., Tri Pointe Homes, Inc.'),
    Decision('LHX', '0001368622', True, 'KEEP',
            'AeroVironment Inc: Our current principal competitors include Elbit Systems Ltd., Quantum-Systems, Inc., Redwire Corporation, Teledyne Technologies, Inc., Sierr'),
    Decision('LITE', '0001227025', True, 'KEEP',
            'NEOPHOTONICS CORP: We believe our principal competitors include: · Furukawa Co., Ltd., Fujitsu Optical Components Limited, NTT Electronics Corporation, Oclaro,'),
    Decision('LITE', '0001814215', True, 'KEEP',
            'Nuburu, Inc.: We compete directly with mature competitors such as Coherent, Inc., IPG Photonics Corporation, Laserline GmbH, Lumentum Holdings Inc., Raycu'),
    Decision('LIVN', '0001099800', True, 'KEEP',
            'Edwards Lifesciences Corp: In Transcatheter Heart Valve Therapy, our primary competitors include Medtronic PLC, Boston Scientific Corporation, St. Jude Medical, Inc.,'),
    Decision('LSCC', '0001432150', True, 'KEEP',
            'GigOptix, Inc.: In the low to medium volume market, the primary competitors include Lattice Semiconductor and Actel Corporation.'),
    Decision('LULU', '0001336917', True, 'KEEP',
            'Under Armour, Inc.: Our competitors include, among others, Nike, Adidas, Puma and lululemon athletica, some of which are large apparel and footwear companies wi'),
    Decision('MANH', '0001047262', True, 'KEEP',
            'EXE TECHNOLOGIES INC: Our competitors include companies or groups that: - focus on providing fulfillment applications, such as McHugh Software International, Manh'),
    Decision('MANH', '0001094360', True, 'KEEP',
            'RETEK INC: Of these vendors, our principal competitors include i2 Technologies, JDA Software, Manhattan Associates, Manugistics and SAP.'),
    Decision('MANH', '0001497251', True, 'KEEP',
            'AcroBoo, Inc.: We compete with other supply chain software vendors, including SAP, Oracle Corporation, JDA Software Group, SAP AG, Infor, Inc., Manhattan A'),
    Decision('MAS', '0000920371', True, 'KEEP',
            'SIMPSON MANUFACTURING CO INC /CA/: SDV\'s principal competitors include the Selkirk Metalbestos Division of Eljer Industries Inc. (a subsidiary of U.S. Industries, Inc.), Ameri'),
    Decision('MAT', '0001034239', True, 'KEEP',
            'RC2 CORP: 5 Competition We compete with several large domestic and foreign companies, such as Mattel, Inc. and Hasbro, Inc., with private label produc'),
    Decision('MCHP', '0001160958', True, 'KEEP',
            'INPHI Corp: Our primary competitors include Acacia Communications, Inc., Broadcom Ltd., Integrated Device Technology, Inc., M/A-COM Technology Solutions'),
    Decision('MCHP', '0001322705', True, 'KEEP',
            'Spansion Inc.: “Risk Factors—We are subject to a variety of environmental laws that could result in liabilities.” Competition Our competitors include but a'),
    Decision('MCHP', '0001736297', True, 'KEEP',
            'Astera Labs, Inc.: Our principal competitors include Broadcom, Inc., Credo Technology Group Holding Ltd., Marvell Technology, Inc., Microchip Technology Inc.,'),
    Decision('MCK', '0000926326', True, 'KEEP',
            'OMNICELL INC /CA/: Other competitors include McKesson Automation Inc. (a business unit of McKesson Corporation), AmerisourceBergen Corporation (through its acq'),
    Decision('MCK', '0001018833', True, 'KEEP',
            'QUADRAMED CORP: Some principal competitors include: o In the market for enterprise healthcare information systems in the Enterprise Division: McKesson Corpo'),
    Decision('MCO', '0001316360', True, 'KEEP',
            'IHS Inc.: County and Industry Forecasting We compete with specific products from the Economist Intelligence Unit and Moody\'s Corporation, among others'),
    Decision('MDLZ', '0001431897', True, 'KEEP',
            'Annie\'s, Inc.: Large mainstream conventional packaged foods competitors include Kraft Foods Inc., General Mills, Inc., Mondelez International, Inc., Campbe'),
    Decision('MDLZ', '0001644406', True, 'KEEP',
            'Hostess Brands, Inc.: Some of our largest national competitors include Flowers Foods, Inc., Grupo Bimbo, S.A., McKee Foods Corporation and Mondelez International,'),
    Decision('MDT', '0001099800', True, 'KEEP',
            'EDWARDS LIFESCIENCES CORP: In cardiac surgery, the primary competitors include St. Jude Medical, Inc., Medtronic, Inc., and Sulzer Medica, Ltd. In critical care, Edwar'),
    Decision('MEDP', '0001610950', True, 'KEEP',
            'Syneos Health, Inc.: Our major competitors include ICON plc, IQVIA (formerly Quintiles IMS Holdings, Inc.), Laboratory Corporation of America Holdings (formerly'),
    Decision('MKSI', '0001111928', True, 'KEEP',
            'IPG PHOTONICS CORP: In the materials processing market, we compete with makers of fiber lasers and other lasers, such as Coherent, Inc., Laserline GmbH, Lumentu'),
    Decision('MOG-A', '0001486299', True, 'KEEP',
            'AOXIN TIANLI GROUP, INC.: In our electro-hydraulic servo valve products, the primary competitors include Moog Inc., Honeywell International, Inc., and Bosch Rexroth A'),
    Decision('MPWR', '0000743316', True, 'KEEP',
            'MAXIM INTEGRATED PRODUCTS INC: Our principal competitors include, but are not limited to, ams AG, Analog Devices, Inc., Cirrus Logic, Inc., Monolithic Power Systems, Inc.,'),
    Decision('MPWR', '0000772406', True, 'KEEP',
            'CIRRUS LOGIC, INC.: Our primary competitors include, but are not limited to, AKM Semiconductor Inc., Analog Devices Inc., Goodix Technology, Infineon Technologi'),
    Decision('MRK', '0000069499', True, 'KEEP',
            'MYLAN LABORATORIES INC: Our primary competitors include Bristol-Myers Squibb Company, Eli Lilly and Company, Geneva Pharmaceuticals, GlaxoSmithKline, IVAX Corporati'),
    Decision('MRVL', '0001140486', True, 'KEEP',
            'ATHEROS COMMUNICATIONS INC: Our primary competitors include Broadcom Corporation, Conexant Systems, Inc., Intel Corporation, Marvell Technology Group Ltd. and Texas Ins'),
    Decision('MRVL', '0001736297', True, 'KEEP',
            'Astera Labs, Inc.: Our principal competitors include Broadcom, Inc., Credo Technology Group Holding Ltd., Marvell Technology, Inc., Microchip Technology Inc.,'),
    Decision('MSI', '0000096699', True, 'KEEP',
            'TECHNICAL COMMUNICATIONS CORP: The Company believes its principal competitors include Crypto AG, Thales Group, Motorola Solutions, Inc., General Dynamics Corporation, Omni'),
    Decision('MSI', '0001167294', True, 'KEEP',
            'MERU NETWORKS INC: Our primary competitors include Cisco Systems, primarily through its wireless networking business unit and its cloud business unit, Aruba Ne'),
    Decision('MTD', '0000779164', True, 'KEEP',
            'RHEOMETRIC SCIENTIFIC INC: Our competitors include among others: Bohlin Instruments, Mettler Toledo, PerkinElmer Instruments, Shamitsu, TA Instruments and Thermo Haake'),
    Decision('MTSI', '0001288469', True, 'KEEP',
            'MAXLINEAR, INC: Our primary merchant semiconductor competitors include Broadcom, Inc., Qualcomm Incorporated, Realtek Semiconductor Corp., Nokia Corp., Skyw'),
    Decision('MUSA', '0001325955', True, 'KEEP',
            'Alon USA Energy, Inc.: Retail Our major retail competitors include Chevron, Murphy USA, Sunoco LP (Stripes® brand), Alimentation Couche-Tard Inc. (Circle K® brand'),
    Decision('NBIX', '0001095330', False, 'COMPPEER',
            'Symyx Technologies: context is an explicit Compensation Peer Group table (exec-comp benchmarking), not a business-competitor claim -- Neurocrine listed among ~30 comparably-sized companies, no competitor language.'),
    Decision('NFLX', '0001408278', True, 'KEEP',
            'Synacor, Inc.: In addition, we compete with companies such as Facebook, Inc., Yahoo! Inc., or Yahoo!, Google, AOL LLC, or AOL, Hulu, Netflix, Amazon, and M'),
    Decision('NKE', '0001059763', True, 'KEEP',
            'ADAMS GOLF INC: Our competitors include Callaway Golf Company, adidas-Salomon AG (Taylor Made - adidas Golf), Nike, Inc. (Nike Golf), Fortune Brands, Inc. ('),
    Decision('NOV', '0001681459', True, 'KEEP',
            'TechnipFMC plc: Our competitors include Baker Hughes Company, Dril-Quip, Inc., McDermott International, Inc., NOV Inc., Oceaneering International, Inc., SLB'),
    Decision('NRG', '0001244937', True, 'KEEP',
            'ENERNOC INC: Our primary competitors include Schneider Electric, Johnson Controls, Ecova, Siemens, IBM, Opower, C3 IoT, FirstFuel, CPower, and NRG Energy'),
    Decision('NTAP', '0000051143', True, 'KEEP',
            'INTERNATIONAL BUSINESS MACHINES CORP: Our principal competitors include: Dell Technologies, Hewlett-Packard Enterprise (HPE), Intel, NetApp and Pure Storage as well as original d'),
    Decision('NTNX', '0001645590', True, 'KEEP',
            'Hewlett Packard Enterprise Co: Our primary competitors include technology vendors such as Dell Technologies Inc., Cisco Systems, Inc., NetApp, Inc., Lenovo Group Ltd., Int'),
    Decision('NUE', '0000842633', True, 'KEEP',
            'TRIMAS CORP: Competition This group\'s primary competitors include Fontana, Nucor and Infasco in industrial fasteners;'),
    Decision('NVST', '0001876588', True, 'KEEP',
            'ZimVie Inc.: Our spine segment competes primarily with the spinal and biologic businesses of Medtronic plc, the DePuy Synthes Companies (part of the John'),
    Decision('NXPI', '0000004127', True, 'KEEP',
            'SKYWORKS SOLUTIONS, INC.: Our competitors include Analog Devices, Broadcom, Maxim Integrated Products, Murata Manufacturing, NXP Semiconductors, QUALCOMM and Qorvo.'),
    Decision('NXPI', '0000772406', True, 'KEEP',
            'CIRRUS LOGIC INC: Our primary competitors include, but are not limited to AAC Technologies, AKM Semiconductor Inc., Analog Devices Inc., Audience, Inc., Austr'),
    Decision('NXT', '0001820721', True, 'KEEP',
            'Array Technologies, Inc.: Our principal tracker competitors include Nextpower Inc. (f/k/a Nextracker, Inc.), PV Hardware and GameChange Solar.'),
    Decision('NXT', '0001831651', True, 'KEEP',
            'Shoals Technologies Group, Inc.: Our principal competitors include Construction Innovation, Hikam America, Inc., Nextpower Inc. (via acquisition of Bentek), Premier PV, Terr'),
    Decision('ODFL', '0001166003', True, 'KEEP',
            'XPO Logistics, Inc.: In transportation, some of our competitors include Old Dominion Freight Line, Saia, FedEx and C.H.'),
    Decision('OLN', '0001015383', True, 'KEEP',
            'AMMO, INC.: Our primary competitors include Remington Arms, the Winchester Ammunition division of Olin Corporation, and various smaller manufacturers an'),
    Decision('OMC', '0001024787', True, 'KEEP',
            'MODEM MEDIA INC: Our primary competitors include: • interactive marketing and technology specialists such as SBI and Company, Agency.com, Organic, Grey Globa'),
    Decision('OMC', '0001098881', True, 'KEEP',
            'CALYPSO MEDIA SERVICES GROUP, INC: Principal competitors include Interpublic Group, Catalina Marketing Group, Omnicom Group Inc. and other local and national advertising agenc'),
    Decision('ORCL', '0000070866', True, 'KEEP',
            'NCR CORP: NCR\'s primary competitors include companies such as International Business Machines (IBM) and Oracle Corporation.'),
    Decision('ORCL', '0001286225', True, 'KEEP',
            'REALPAGE INC: Our current principal competitors include: • in the ERP market, Yardi Systems, Inc. ("Yardi"), MRI Software LLC, Property Solutions Internat'),
    Decision('ORCL', '0001373715', True, 'KEEP',
            'ServiceNow, Inc.: Our primary competitors include BMC Software, Inc., Microsoft Corporation, Oracle Corporation, SAP and Salesforce.com.'),
    Decision('ORI', '0000809398', True, 'KEEP',
            'FIDELITY NATIONAL FINANCIAL INC /DE/: In our principal markets, competitors include other major title underwriters such as The First American Corporation, LandAmerica Financial G'),
    Decision('ORI', '0001301106', True, 'KEEP',
            'National Interstate CORP: n the specialty insurance market we compete against, among others, Lancer Insurance Company, Lincoln General Insurance Company (a subsidiary'),
    Decision('ORI', '0001331875', True, 'KEEP',
            'Fidelity National Financial, Inc.: In our principal 10 Table of Contents markets, competitors include other major title underwriters such as The First American Corporation, Ol'),
    Decision('PANW', '0000736012', True, 'KEEP',
            'INTRUSION INC: In our newest market segment, data mining and advanced persistent threat detection, we compete with several companies including Niksun, NetS'),
    Decision('PANW', '0001082324', True, 'KEEP',
            'VirnetX Holding Corp: In the enterprise market, our primary competitors include Zscaler (ZPA), Palo Alto Networks (Prisma Access), Cisco (Umbrella), Citrix (Secur'),
    Decision('PAYX', '0000896878', True, 'KEEP',
            'INTUIT INC: In our payroll business we compete directly with Automatic Data Processing, Inc. (ADP), Paychex and many other companies with payroll offeri'),
    Decision('PCTY', '0000884144', True, 'KEEP',
            'ASURE SOFTWARE INC: However, Asure’s main competitors are ADP, Paychex, UKG, Paylocity, Paycor, Paycom, Ceridian, isolved, Gusto, and Time Simplicity.'),
    Decision('PCTY', '0001016125', True, 'KEEP',
            'ULTIMATE SOFTWARE GROUP INC: In our mid-market and strategic market, Ultimate\'s competitors include primarily payroll service providers, such as ADP, Paychex, Ceridian,'),
    Decision('PEGA', '0001005757', True, 'KEEP',
            'CSG SYSTEMS INTERNATIONAL INC: Our current competitors include companies who deliver on-premise bespoke custom offerings (i.e., Amdocs Limited, NEC Netcracker), packaged s'),
    Decision('PEGA', '0001087423', True, 'KEEP',
            'RED HAT INC: With respect to our middleware offerings, our competitors include AWS, IBM, Microsoft, MuleSoft, Inc., Oracle, Pegasystems Inc., Pivotal Sof'),
    Decision('PEN', '0001661181', True, 'KEEP',
            'Organogenesis Holdings Inc.: Our competitors include Acelity Holdings, Inc., ACell, Incorporated, Amniox Medical, Inc., Angiodynamics, Inc., Arthrex, Inc., Integra LifeS'),
    Decision('PEP', '0000804055', True, 'KEEP',
            'COCA COLA ENTERPRISES INC: For example, we compete with bottlers of products of PepsiCo, Inc., Cadbury Schweppes plc, Nestle S.A., Groupe Danone, Kraft Foods Inc., and'),
    Decision('PFE', '0001787306', True, 'KEEP',
            'Arcutis Biotherapeutics, Inc.: For psoriasis, our primary competitors include injected biologic therapies such as Humira, marketed by AbbVie Inc. and Eisai Co., Ltd., and'),
    Decision('PFGC', '0001563407', True, 'KEEP',
            'Smart & Final Stores, Inc.: Our principal competitors include conventional grocers such as Albertson\'s and Kroger, discounters and warehouse clubs such as Costco, mass'),
    Decision('PHM', '0001721386', True, 'KEEP',
            'Landsea Homes Corp: While our competitors vary by market, we compete directly with major national builders such as KB Home, Lennar Corp., Tri Pointe Homes, Inc.'),
    Decision('PKG', '0001717556', True, 'KEEP',
            'Xspand Products Lab, Inc.: In terms of our packaging business, we compete against a large number of packaging manufacturers in North America, such as AEP Industries, I'),
    Decision('PNC', '0000350894', True, 'KEEP',
            'SEI CORP: Our principal competitors include The BISYS Group, Inc., Federated Investors, Inc., PFPC Worldwide Inc. (a member of the PNC Financial Servi'),
    Decision('PODD', '0001613103', True, 'KEEP',
            'Medtronic plc: Our primary competitors are Johnson & Johnson, DexCom, Inc., Insulet Corporation, and F. Hoffmann-La Roche Ltd. OTHER FACTORS IMPACTING OUR'),
    Decision('PSN', '0001720821', True, 'KEEP',
            'PAE Inc: PAE’s principal competitors include Amentum, Booz Allen Hamilton, CACI International Inc., Jacobs Engineering Group Inc., KBR, Inc., Leidos,'),
    Decision('PSN', '0002011286', True, 'KEEP',
            'Amentum Holdings, Inc.: Amentum\'s primary competitors include Booz Allen Hamilton Inc., CACI International Inc., KBR Inc., Leidos Holdings Inc., ManTech Internation'),
    Decision('PYPL', '0000798354', True, 'KEEP',
            'FISERV INC: These newer competitors include, but are not limited to, Alphabet Inc., Amazon.com, Inc., Apple Inc., Facebook, Inc., Intuit Inc., PayPal Ho'),
    Decision('QCOM', '0000772406', True, 'KEEP',
            'CIRRUS LOGIC INC: Our primary competitors include, but are not limited to AAC Technologies, AKM Semiconductor Inc., Analog Devices Inc., Austriamicrosystems A'),
    Decision('QLYS', '0001560327', True, 'KEEP',
            'Rapid7, Inc.: Our primary competitors include: vulnerability management vendors including Qualys and Tenable Network Security;'),
    Decision('QLYS', '0001622767', True, 'KEEP',
            'SIRRUS CORP.: Among others, our competitors include Check Point Software Technologies Ltd. (“Check Point”), Secureworks Corp. (“Secureworks”), Qualys, Inc'),
    Decision('QLYS', '0001660280', True, 'KEEP',
            'Tenable Holdings, Inc.: Our competitors include: vulnerability management and assessment vendors, including Qualys and Rapid7;'),
    Decision('RGA', '0001051628', True, 'KEEP',
            'ANNUITY & LIFE RE HOLDINGS LTD: We believe that our primary competitors include Transamerica Occidental Life Insurance Company, Reinsurance Group of America, Inc., ING Rein'),
    Decision('RLI', '0001761312', True, 'KEEP',
            'Palomar Holdings, Inc.: Our primary competitors include national specialty insurance companies, including Kinsale Capital Group, Inc., RLI Corp., Skyward Specialty'),
    Decision('RMBS', '0001736297', True, 'KEEP',
            'Astera Labs, Inc.: Our principal competitors include Broadcom, Inc., Credo Technology Group Holding Ltd., Marvell Technology, Inc., Microchip Technology Inc.,'),
    Decision('RMD', '0001474627', True, 'KEEP',
            'Dehaier Medical Systems Ltd: Our competitors include publicly traded and privately held multinational companies, such as Respironics, Inc., ResMed Inc., and Covidien, as'),
    Decision('RNR', '0000896159', True, 'KEEP',
            'ACE LTD: Competitors include Munich Re, Swiss Re, PartnerRe, Converium, RenaissanceRe, XL Re and certain Lloyd’s syndicates.'),
    Decision('ROK', '0001000227', True, 'KEEP',
            'TB WOODS CORP: Major VFD and systems competitors include Asea Brown Boveri (ABB), Rockwell Automation (Allen Bradley and Reliance Electric), Siemens Corp.,'),
    Decision('RRX', '0000046129', True, 'KEEP',
            'ALLIENT INC: Our competitors include Ametek, Inc., Parker Hannifin Corporation, Regal Rexnord, and other smaller competitors.'),
    Decision('RRX', '0001324948', True, 'KEEP',
            'RBC Bearings INC: Competition Our principal competitors include SKF, New Hampshire Ball Bearings, Regal Rexnord, Precision Castparts and Timken, although we c'),
    Decision('RVTY', '0001123494', True, 'KEEP',
            'HARVARD BIOSCIENCE INC: We compete with several companies that provide products for life science research including Agilent, Becton, Dickinson and Company, Bio-Rad'),
    Decision('RVTY', '0001906324', True, 'KEEP',
            'QuidelOrtho Corp: Some of our principal competitors include, among others, Abbott Laboratories, bioMérieux, Bio-Rad, Danaher, Diasorin, Hologic, Qiagen, Revvi'),
    Decision('SAIA', '0000894405', True, 'KEEP',
            'ARKANSAS BEST CORP /DE/: Competitors include Yellow Transportation and Roadway Express, (operated by YRC Worldwide, Inc.), FedEx Freight (operated by FedEx Corporati'),
    Decision('SAIA', '0001166003', True, 'KEEP',
            'XPO Logistics, Inc.: In transportation, some of our competitors include Old Dominion Freight Line, Saia, FedEx and C.H.'),
    Decision('SAM', '0000016918', True, 'KEEP',
            'CONSTELLATION BRANDS, INC.: Our principal competitors include: Beer Anheuser-Busch InBev, MillerCoors, Heineken, Pabst Brewing Company, The Boston Beer Company Wine U.S'),
    Decision('SANM', '0000863436', True, 'KEEP',
            'BENCHMARK ELECTRONICS INC: Our competitors include Celestica Inc., Flex Ltd., Jabil Inc., Kimball Electronics Inc., Plexus Corp, and Sanmina Corporation.'),
    Decision('SANM', '0001616533', True, 'KEEP',
            'SMART Global Holdings, Inc.: Our principal competitors include: • Providers of specialty memory products, including Viking Technology (a division of Sanmina Corporation)'),
    Decision('SARO', '0001018164', True, 'KEEP',
            'WILLIS LEASE FINANCE CORP: Our primary competitors include AerCap Holdings N.V., Shannon Engine Support Ltd., Pratt & Whitney, Rolls-Royce Partners Finance, Engine Lea'),
    Decision('SBUX', '0000798354', True, 'KEEP',
            'FISERV INC: These newer competitors include, but are not limited to, Amazon.com, Inc., Apple Inc., Facebook, Inc., Google Inc., Intuit Inc., Starbucks C'),
    Decision('SLAB', '0001288469', True, 'KEEP',
            'MAXLINEAR INC: Our primary competitors include Silicon Labs, NXP B.V., RDA Microelectronics, Inc., Newport Media Inc., Broadcom Corporation, Entropic Commu'),
    Decision('SLGN', '0001527508', True, 'KEEP',
            'Pactiv Evergreen Inc.: Our competitors include, among others, Dart Container Corporation, Huhtamäki Oyj, Berry Global Group, Inc., Genpak, Sonoco, Paper Excellence'),
    Decision('SMCI', '0002033264', True, 'KEEP',
            'Vertical Data Inc.: We compete against several distributors in the Americas market including OEM distributors such as Supermicro, Hewlett Packard Enterprise and'),
    Decision('SMTC', '0000743316', True, 'KEEP',
            'MAXIM INTEGRATED PRODUCTS INC: Our principal competitors include, but are not limited to, Analog Devices, Inc., Intersil Corporation, Linear Technology Corporation, NXP Se'),
    Decision('SMTC', '0000800460', True, 'KEEP',
            'CALIFORNIA MICRO DEVICES CORP: Within the ASIP product families for the mobile, computing and consumer electronic markets, we compete with ON Semiconductor Corporation, Ro'),
    Decision('SMTC', '0001432150', True, 'KEEP',
            'GigOptix, Inc.: GX Products In the telecom and data-communications segments, we compete with TriQuint, Rohm, InPhi, Centellax, Semtech, Vitesse and M/A-Com.'),
    Decision('SNX', '0000918965', True, 'KEEP',
            'SCANSOURCE, INC.: In our Specialty Technology Solutions segment, we compete with broad-line distributors, such as Ingram Micro and TD Synnex, in most geograph'),
    Decision('SON', '0001047290', True, 'KEEP',
            'NEWARK GROUP, INC: Our competitors include Rock-Tenn Company, Caraustar Industries, Inc. and Sonoco Products Company in North America and Stora Enso Oyj, Kappa'),
    Decision('STE', '0000314227', True, 'KEEP',
            'TOMI Environmental Solutions, Inc.: Our competitors include companies that market other hydrogen peroxide-based products, such as Steris Corporation (“Steris”), Bioquell, Inc.'),
    Decision('STE', '0001121302', True, 'KEEP',
            'SYBRON DENTAL SPECIALTIES INC: Our competitors include Johnson and Johnson, Steris Corporation and Ecolab, Inc. RESEARCH AND DEVELOPMENT We have a number of research and d'),
    Decision('STZ', '0001350073', True, 'KEEP',
            'Iconic Brands, Inc.: Our competitors include, but are not limited to, Gallo, Mionetto, Gruppo Campari, Constellation Brands, William Grant and Sons and Jim Beam'),
    Decision('SWK', '0001519751', True, 'KEEP',
            'Fortune Brands Home & Security, Inc.: Our chief competitors include Delta (owned by Masco), Kohler, Pfister (owned by Stanley Black & Decker), American Standard and imported priv'),
    Decision('SWKS', '0000772406', True, 'KEEP',
            'CIRRUS LOGIC INC: Our primary competitors include, but are not limited to AAC Technologies, AKM Semiconductor Inc., Analog Devices Inc., Austriamicrosystems A'),
    Decision('SYK', '0001157972', True, 'KEEP',
            'DJ ORTHOPEDICS INC: ernational, N.V., Bledsoe Brace Systems, Innovation Sports Incorporated, Generation II USA, Inc. and Townsend Industries Inc. In the soft go'),
    Decision('SYK', '0001591165', True, 'KEEP',
            'Medovex Corp.: With regard to the DenerveX System, we believe that our principal competitors include device manufacturers Cosman Medical Inc., Stryker Corp'),
    Decision('SYNA', '0000772406', True, 'KEEP',
            'CIRRUS LOGIC INC: mary competitors include, but are not limited to AAC Technologies, AKM Semiconductor Inc., Analog Devices Inc., Austriamicrosystems AG, Avne'),
    Decision('SYY', '0001563407', True, 'KEEP',
            'Smart & Final Stores, Inc.: s and Industry—Competition in our industry is intense and our failure to compete successfully may adversely affect our sales, financial cond'),
    Decision('TDY', '0000319815', True, 'KEEP',
            'MAXWELL TECHNOLOGIES INC: In that market segment, we compete with high reliability packaging houses such as Austin Semiconductor, Inc., White Microelectronics, Inc. a'),
    Decision('TDY', '0001118941', True, 'KEEP',
            'ENDWAVE CORP: ers • Added new product capabilities in high performance oscillators • Added new customer relationship with Stratex Networks, Inc. • Added n'),
    Decision('TDY', '0001368622', True, 'KEEP',
            'AeroVironment Inc: Our current principal competitors include Elbit Systems Ltd., Quantum-Systems, Inc., Edge Autonomy, Teledyne Technologies, Inc., Sierra Neva'),
    Decision('TEL', '0001043337', True, 'KEEP',
            'STONERIDGE INC: Our primary competitors include Bosch, Continental AG, Delphi Automotive PLC, Denso Corporation, Electricfil, Hella KGaA Hueck & Co., Method'),
    Decision('TER', '0000021535', True, 'KEEP',
            'COHU INC: Key Competitors Cohu’s primary competitors include established global players in semiconductor test and inspection, such as Advantest, Terad'),
    Decision('TER', '0000893162', True, 'KEEP',
            'CREDENCE SYSTEMS CORP: and Teradyne, Inc. In the mixed-signal and analog semiconductor testing market our competitors include: Teradyne, Inc. LTX;'),
    Decision('TEX', '0000792987', True, 'KEEP',
            'ASTEC INDUSTRIES INC: The Materials Solutions segment\'s primary competitors include the following as well as smaller manufacturers, both domestic and internationa'),
    Decision('TKR', '0001419581', True, 'KEEP',
            'FEDERAL MOGUL CORP: • Global Aftermarket – Primary competitors include AC Delco, Affinia, Airtex, Bosch, Contitech, Delphi, Denso, Honeywell, Mahle, Sylvania, T'),
    Decision('TMO', '0001000697', True, 'KEEP',
            'WATERS CORP /DE/: In the markets served by the Waters Division, the Company’s principal competitors include: Agilent Technologies, Inc., Shimadzu Corporation,'),
    Decision('TMO', '0001699150', True, 'KEEP',
            'Ingersoll Rand Inc.: Our primary competitors include Dover, Graco, IDEX Corporation, KNF Neuberger, Netzsch, NOV, Sartorius, SPX Flow, Thermo Fisher Scientific,'),
    Decision('TRGP', '0001578685', True, 'KEEP',
            'Midcoast Energy Partners, L.P.: Our logistics and marketing business’ principal competitors include numerous natural gas and NGL marketing companies such as Energy Transfer'),
    Decision('TRU', '0001109190', True, 'KEEP',
            'EFUNDS CORP: In the decision support and risk management market, our principal competitors include: - providers of fraud management data and software inc'),
    Decision('TTEK', '0000102379', True, 'KEEP',
            'URS CORP /NEW/: Our competitors are numerous, ranging from small private firms to multi-billion dollar public companies, and our primary competitors include'),
    Decision('TTEK', '0001643615', True, 'KEEP',
            'Montrose Environmental Group, Inc.: Our Remediation and Reuse segment competitors include the environmental divisions or remediation segments of Tetra Tech, AECOM, Xylem, Veoli'),
    Decision('TTWO', '0000712515', True, 'KEEP',
            'ELECTRONIC ARTS INC: These competitors include Acclaim Entertainment, Activision, Capcom, Eidos, Infogrames, Koei, Konami, Lucas Arts, Midway, Namco, Sega, Squar'),
    Decision('TTWO', '0001022080', True, 'KEEP',
            'MIDWAY GAMES INC: These competitors include Activision, Atari, Capcom, Electronic Arts, Konami, Namco, SCi Entertainment, Sega, Take-Two Interactive Software,'),
    Decision('TTWO', '0001439404', True, 'KEEP',
            'ZYNGA INC: Some of these competitors include Activision Blizzard, Aristocrat, DoubleU, Electronic Arts, Epic Games, Glu Mobile, Jam City, Machine Zone,'),
    Decision('TTWO', '0001823878', True, 'KEEP',
            'PLAYSTUDIOS, Inc.: Our primary competitors include Activision Blizzard (the parent company of King Digital), Electronic Arts (EA Mobile), Epic Games, Jam City,'),
    Decision('TWLO', '0001092570', True, 'KEEP',
            'FULLNET COMMUNICATIONS INC: Notable competitors include Twilio, Inc., Everbridge, Inc., Onsolve, LLC, Call-Em-All, LLC, CallFire, Inc., OnTimeTelecom, Inc., and EZ Text'),
    Decision('TWLO', '0001224133', True, 'KEEP',
            'MARCHEX INC: We compete with conversation analytics providers such as Twilio, EZ Texting, CallSource, CallRail, and Invoca.'),
    Decision('TXN', '0001081197', True, 'KEEP',
            'GLOBESPANVIRATA INC: We believe our principal competitors include: o for asymmetric DSL products, Analog Devices, Aware Inc., Broadcom Corporation, Centillium Co'),
    Decision('TXT', '0000067887', True, 'KEEP',
            'MOOG INC: In Aircraft Controls, principal competitors include Parker Hannifin, Nabtesco, Smiths Industries, Goodrich, Liebherr, HR Textron, Curtiss-Wr'),
    Decision('UFPI', '0001069878', True, 'KEEP',
            'TREX CO INC: Our principal competitors include Azek (a division of James Hardie Industries PLC), Deckorators (a division of UFP Industries, Inc.), and Fi'),
    Decision('UNH', '0001339553', True, 'KEEP',
            'HealthSpring, Inc.: Our primary competitors include Blue Cross Blue Shield of Alabama, Humana Inc., UnitedHealth Group, and VIVA Health, Inc., a member of the U'),
    Decision('UNM', '0001535929', True, 'KEEP',
            'ING U.S., Inc.: Our principal competitors include MetLife, Prudential and Minnesota Life in Group Life, Houston Casualty, Symetra and Sun Life in Stop Loss,'),
    Decision('USB', '0001230245', True, 'KEEP',
            'PIPER JAFFRAY COMPANIES: Forward-looking statements involve inherent risks and uncertainties, and important factors could cause actual results to differ materially f'),
    Decision('USFD', '0001563407', True, 'KEEP',
            'Smart & Final Stores, Inc.: stry—Competition in our industry is intense and our failure to compete successfully may adversely affect our sales, financial condition and'),
    Decision('VEEV', '0001829280', True, 'KEEP',
            'Forian Inc.: In general, our competitors include a variety of entities such as information and clinical analytics providers like ICON plc, information an'),
    Decision('VFC', '0000895655', True, 'KEEP',
            'JARDEN CORP: Our largest competitors include Igloo Corporation, Intex Corporation, VF Corporation, Johnson Outdoors, Kellwood Company and Rubbermaid.'),
    Decision('VFC', '0001323531', True, 'KEEP',
            'Maidenform Brands, Inc.: Our primary competitors include Cupid Foundations, Inc., Gap Inc., Jockey International, Inc., the Lane Bryant division of Charming Shoppes,'),
    Decision('VIAV', '0001601046', True, 'KEEP',
            'Keysight Technologies, Inc.: In the commercial communications market, our primary competitors are Rohde & Schwarz GmbH & Co. KG, Anritsu Corporation, Tektronix, Inc. (a'),
    Decision('VRSK', '0000814547', True, 'KEEP',
            'FAIR ISAAC CORP: In the fraud solutions market for health care insurance, we compete with Emdeon, Ingenix, ViPS, MedStat, Detica, a division of BAE, SAS, Ver'),
    Decision('VRSN', '0001169264', True, 'KEEP',
            'SYNIVERSE HOLDINGS INC: Our primary competitors include MACH, VeriSign and Sybase 365.'),
    Decision('VRT', '0001320760', True, 'KEEP',
            'TSS, Inc.: An example of some of our competitors include the following: ● Modular data center design and configuration – IO, Schneider, Skanska, Vertiv'),
    Decision('VRT', '0001622345', True, 'KEEP',
            'Polar Power, Inc.: Our competitors include Ascot, Eltek Valere, Inc., General Electric, Delta Power, Inc., Generac Power Systems, Inc., Schneider Electric, Alp'),
    Decision('VTRS', '0001585364', True, 'KEEP',
            'PERRIGO Co plc: Global competitors include GSK, Sanofi, Bayer, Johnson & Johnson, Reckitt Benckiser, Teva, Viatris, Stada, Novartis, Procter & Gamble, and e'),
    Decision('WAB', '0000018230', True, 'KEEP',
            'CATERPILLAR INC: In rail-related businesses, our global competitors include Alstom SA, CRRC Corp., LTD., The Greenbrier Companies, Siemens Mobility, Voestalp'),
    Decision('WCC', '0001372000', True, 'KEEP',
            'UNIVERSAL POWER GROUP INC.: Third, in the distribution business, we compete with battery and other electronic component distributors, such as Interstate Batteries, MK B'),
    Decision('WDC', '0001122904', True, 'KEEP',
            'NETGEAR, INC: Our principal competitors include: • within the consumer markets, companies such as Apple, Asus, Belkin/Linksys, D-Link, Dropcam, Foscam, Lo'),
    Decision('WFRD', '0000721083', True, 'KEEP',
            'SMITH INTERNATIONAL INC: With respect to drilling and completion services and tools, the segment’s primary competitors include Halliburton, Schlumberger, Baker Hughe'),
    Decision('WFRD', '0000886835', True, 'KEEP',
            'SUPERIOR ENERGY SERVICES INC: We believe our primary competitors include Weatherford International, Ltd., Baker Hughes Incorporated, Halliburton Company and Schlumberger'),
    Decision('WHR', '0000744106', True, 'KEEP',
            'FEDDERS CORP /DE: COMPETITION Domestically, our competitors include a number of foreign and domestic manufacturers of room air conditioners and appliances, in'),
    Decision('WHR', '0000895655', True, 'KEEP',
            'JARDEN CORP: In general, the more mature small household appliance categories outside of home vacuum packaging, including blenders, toasters and irons, a'),
    Decision('WHR', '0001063697', True, 'KEEP',
            'ALLIANCE LAUNDRY CORP: In multi-housing, our principal competitors include Maytag Corporation and Whirlpool Corporation.'),
    Decision('WHR', '0001063699', True, 'KEEP',
            'ALLIANCE LAUNDRY SYSTEMS LLC: In multi-housing, the principal competitors include Maytag Corporation and Whirlpool Corporation.'),
    Decision('WING', '0001452872', True, 'KEEP',
            'AMERICAN RESTAURANT CONCEPTS INC: We compete directly with Buffalo Wild Wings, Hooters, Wings ‘N More, Wingstop, Hurricane Grill & Wings, The Wings Stop, Wings ‘n Things, and'),
    Decision('WMT', '0000103595', True, 'KEEP',
            'VILLAGE SUPER MARKET INC: The Company\'s principal competitors include Pathmark, A&P, Stop & Shop, Acme, Kings, Walmart and Foodtown.'),
    Decision('XRAY', '0001000228', True, 'KEEP',
            'HENRY SCHEIN INC: Within Global Specialty Products, our primary competitors include Straumann, Envista, Zimvie, and Dentsply Sirona.'),
    Decision('XRAY', '0001876588', True, 'KEEP',
            'ZimVie Inc.: Our spine segment competes primarily with the spinal and biologic businesses of Medtronic plc, the DePuy Synthes Companies (part of the John'),
    Decision('ZBH', '0000898437', True, 'KEEP',
            'Anika Therapeutics, Inc.: For our OA Pain Management products, our principal competitors include Sanofi Genzyme, Zimmer Biomet, Inc., Bioventus Inc., and Ferring Phar'),
    Decision('ZBH', '0001305773', True, 'KEEP',
            'Conformis Inc: We compete with several large, well-known companies that dominate the market for orthopedic products, principally Zimmer Biomet Holdings, In'),
    Decision('ZTS', '0001069899', True, 'KEEP',
            'PHIBRO ANIMAL HEALTH CORP: Some of our principal competitors include Bayer AG, Ceva Santé Animale, Boehringer Ingelheim International GMBH, Eli Lilly and Company (Elan'),
)


def apply_review(
    raw_leads: list[dict[str, Any]],
    decisions: tuple[Decision, ...] = SCALED_HAND_REVIEW_DECISIONS,
) -> list[dict[str, Any]]:
    """Join the raw confirmed leads to their hand-review decision by
    (anchor_ticker, peer_cik). Refuses on any mismatch between the two
    sets -- see module docstring for why the key is a pair, not peer_cik
    alone. With an empty decision list (the scaffold's default), this
    refuses on ANY confirmed lead -- by design, not a bug."""
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
        out.append({**lead, "hand_review_category": d.category,
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
    print(f"distinct (anchor, peer_cik) pairs kept: "
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
    client = AgreementSearchClient("bchen9996 bchen9996@gmail.com",
                                   max_requests=len(kept) + 5)

    name_search_results: list[dict[str, Any]] = []
    linkage_edges: list[dict[str, Any]] = []
    for v in kept:
        cik = v["peer_cik"]
        ticker = client.ticker_for(cik)
        if ticker is not None and ticker.upper() == v["anchor_ticker"].upper():
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
            "source": SOURCE_HANDREVIEWED,
            "evidence_sentence": v["context"],
            "hand_review_category": v["hand_review_category"],
            "hand_review_reason": v["hand_review_reason"],
        })

    a.out_name_search.write_text(json.dumps({
        "artifact": a.out_name_search.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07", "results": name_search_results,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    a.out_linkage.write_text(json.dumps({
        "artifact": a.out_linkage.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07", "edges": linkage_edges,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {a.out_name_search}")
    print(f"wrote {a.out_linkage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
