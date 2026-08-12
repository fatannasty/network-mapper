"""Hostname → site decoding for Sprint 13 site attribution.

Amtrak hostnames encode location as AMTR<CODE><STATE> (e.g. AMTRMIAFL,
AMTRWASDC, MRSAMTRCHIIL). The <CODE> is the Amtrak station code; <STATE> is
the two-letter state. This module decodes those codes into readable site names
so the site-mapping table can be auto-seeded, with a curated override map for
internal yard/shop codes and legacy hostnames that don't follow the pattern.

Sources:
  - Official Amtrak station codes (FRA/BTS "Amtrak Stations" dataset).
  - Curated overrides for internal codes (Rensselaer shop, Sunnyside Yard,
    Ivy City, Bear DE, etc.).
"""

from __future__ import annotations

import re

STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
}

# Official Amtrak station codes → (city, state). Abridged to codes seen in
# our hostnames plus common ones; add more from the FRA dataset as needed.
AMTRAK_CODES = {
    "ABE": ("Aberdeen", "MD"), "ALB": ("Albany-Rensselaer", "NY"),
    "ALN": ("Alton", "IL"), "ALT": ("Altoona", "PA"), "ALX": ("Alexandria", "VA"),
    "ANA": ("Anaheim", "CA"), "ATB": ("Attleboro", "MA"), "ATL": ("Atlanta", "GA"),
    "BAL": ("Baltimore", "MD"), "BBY": ("Boston", "MA"), "BER": ("Berlin", "CT"),
    "BFX": ("Buffalo-Exchange St.", "NY"), "BHM": ("Birmingham", "AL"),
    "BNC": ("Burlington", "NC"), "BND": ("Bond Hill", "OR"), "BON": ("Boston", "MA"),
    "BOS": ("Boston", "MA"), "BRA": ("Brattleboro", "VT"), "BRK": ("Brunswick", "ME"),
    "BRN": ("Berwyn", "PA"), "BRP": ("Bridgeport", "CT"), "BTL": ("Battle Creek", "MI"),
    "BUF": ("Buffalo-Depew", "NY"), "CAR": ("Carbondale", "IL"),
    "CCH": ("Chicago", "IL"), "CHI": ("Chicago", "IL"), "CHS": ("Charleston", "SC"),
    "CIN": ("Cincinnati", "OH"), "CLE": ("Cleveland", "OH"), "CLT": ("Charlotte", "NC"),
    "CMI": ("Champaign", "IL"), "CNO": ("New Castle", "DE"), "CPN": ("Carpinteria", "CA"),
    "CRO": ("Crockett", "CA"), "CSL": ("Castroville", "CA"), "CVS": ("Charlottesville", "VA"),
    "CYN": ("Cary", "NC"), "DAV": ("Davis", "CA"), "DET": ("Detroit", "MI"),
    "DHM": ("Durham", "NH"), "DLD": ("DeLand", "FL"), "DOV": ("Dover", "NH"),
    "DRD": ("Durand", "MI"), "DUR": ("Durham", "NC"), "ELP": ("El Paso", "TX"),
    "ELT": ("Elizabethtown", "PA"), "EMY": ("Emeryville", "CA"), "EUG": ("Eugene", "OR"),
    "EWR": ("Newark Liberty Airport", "NJ"), "FAR": ("Fargo", "ND"), "FAT": ("Fresno", "CA"),
    "FAY": ("Fayetteville", "NC"), "FLG": ("Flagstaff", "AZ"), "FLO": ("Florence", "SC"),
    "FMS": ("Fort Madison", "IA"), "FNO": ("Fresno", "CA"), "FTW": ("Fort Worth", "TX"),
    "FUL": ("Fullerton", "CA"), "GAC": ("Santa Clara-Great American", "CA"),
    "GBO": ("Greensboro", "NC"), "GCK": ("Garden City", "KS"), "GJT": ("Grand Junction", "CO"),
    "GPK": ("East Glacier Park", "MT"), "GRR": ("Grand Rapids", "MI"),
    "GRV": ("Greenville", "SC"), "GSC": ("Glenwood Springs", "CO"),
    "GTA": ("Goleta", "CA"), "GUA": ("Guadalupe", "CA"), "GVB": ("Grover Beach", "CA"),
    "HAM": ("Hamlet", "NC"), "HAR": ("Harrisburg", "PA"), "HFD": ("Hartford", "CT"),
    "HVN": ("New Haven", "CT"),
    "HGB": ("Hattiesburg", "MS"), "HHI": ("Homewood", "IL"), "HMD": ("Hammond", "LA"),
    "HMW": ("Homewood", "IL"), "HNF": ("Hanford", "CA"), "HOL": ("Hollywood", "FL"),
    "HOM": ("Holland", "MI"), "HOU": ("Houston", "TX"), "HPT": ("High Point", "NC"),
    "HUD": ("Hudson", "NY"), "HUN": ("Huntington", "WV"), "HYD": ("Hoboken", "NJ"),
    "ILG": ("Wilmington", "DE"), "IND": ("Indianapolis", "IN"), "JAN": ("Jackson", "MS"),
    "JAX": ("Jacksonville", "FL"), "JOL": ("Joliet", "IL"), "JXN": ("Jackson", "MI"),
    "KAL": ("Kalamazoo", "MI"), "KAN": ("Kannapolis", "NC"), "KIS": ("Kissimmee", "FL"),
    "LAF": ("Lafayette", "IN"), "LAJ": ("La Junta", "CO"), "LAK": ("Lakeland", "FL"),
    "LAW": ("Lansing", "MI"),     "LAX": ("Los Angeles", "CA"), "LIC": ("Long Island City", "NY"),
    "LIN": ("Lincoln", "NE"), "LNK": ("Lincoln", "NE"), "LNS": ("East Lansing", "MI"),
    "LOR": ("Lorton", "VA"),
    "LPV": ("Lynchburg", "VA"), "LRK": ("Little Rock", "AR"), "LSE": ("La Crosse", "WI"),
    "LVW": ("Longview", "TX"), "LYH": ("Lynchburg", "VA"), "MAE": ("Miami", "FL"),
    "MCD": ("Merced", "CA"), "MDH": ("Macomb", "IL"), "MEI": ("Meridian", "MS"),
    "MEM": ("Memphis", "TN"), "MET": ("Metropark", "NJ"), "MIA": ("Miami", "FL"),
    "MKA": ("Milwaukee Mitchell Airport", "WI"), "MKE": ("Milwaukee", "WI"),
    "MOD": ("Modesto", "CA"), "MOE": ("Mobile", "AL"), "MOT": ("Minot", "ND"),
    "MRB": ("Martinsburg", "WV"), "MSP": ("Minneapolis", "MN"), "MSS": ("Manassas", "VA"),
    "MSV": ("Manassas", "VA"),     "MSY": ("New Orleans", "LA"), "MVW": ("Mount Vernon", "WA"),
    "NNS": ("Newport News", "VA"), "OAK": ("Oakland", "CA"),
    "MYS": ("Mystic", "CT"), "NBK": ("New Brunswick", "NJ"), "NCA": ("New Carrollton", "MD"),
    "NCD": ("New Castle", "DE"), "NEW": ("Newton", "KS"), "NFK": ("Norfolk", "VA"),
    "NFL": ("Niagara Falls", "NY"), "NHV": ("New Haven", "CT"), "NLC": ("New London", "CT"),
    "NLS": ("Niles", "MI"), "NRO": ("New Rochelle", "NY"), "NYC": ("New York", "NY"),
    "OMA": ("Omaha", "NE"), "ORB": ("Old Orchard Beach", "ME"), "ORL": ("Orlando", "FL"),
    "OSB": ("Old Saybrook", "CT"), "OTM": ("Ottumwa", "IA"), "OXN": ("Oxnard", "CA"),
    "SAC": ("Sacramento", "CA"),
    "PAO": ("Paoli", "PA"), "PEN": ("Pontiac", "MI"), "PHL": ("Philadelphia", "PA"),
    "PJC": ("Princeton Junction", "NJ"), "PIT": ("Pittsfield", "MA"), "PNB": ("New York", "NY"),
    "POR": ("Portland", "OR"), "POU": ("Poughkeepsie", "NY"), "PRC": ("Prince", "WV"),
    "PRI": ("Princeton", "NJ"), "PSC": ("Pasco", "WA"), "PTB": ("Petersburg", "VA"),
    "PTH": ("Port Huron", "MI"), "PVD": ("Providence", "RI"), "PYV": ("Perryville", "MD"),
    "QCY": ("Quincy", "IL"),
    "REN": ("Rensselaer", "IN"), "RGH": ("Raleigh", "NC"), "RHI": ("Rhinecliff", "NY"),
    "RIC": ("Richmond", "CA"), "RLN": ("Rocklin", "CA"), "ROC": ("Rochester", "NY"),
    "RTE": ("Route 128", "MA"), "RVM": ("Richmond", "VA"), "RVR": ("Richmond", "VA"),
    "SAB": ("St. Albans", "VT"), "SAI": ("St. Paul", "MN"), "SAJ": ("San Jose", "CA"),
    "SAO": ("Saco", "ME"), "SAV": ("Savannah", "GA"), "SBA": ("Santa Barbara", "CA"),
    "SCH": ("Schriever", "LA"), "SDY": ("Schenectady", "NY"), "SEA": ("Seattle", "WA"),
    "SFA": ("Sanford", "FL"), "SFB": ("Sanford", "FL"), "SJC": ("San Jose", "CA"),
    "SKN": ("Stockton", "CA"), "SLC": ("Salt Lake City", "UT"), "SLM": ("Salem", "OR"),
    "SLO": ("San Luis Obispo", "CA"), "SNS": ("Salinas", "CA"), "SPG": ("Springfield", "MA"),
    "SPI": ("Springfield", "IL"), "SSM": ("Selma-Smithfield", "NC"), "STM": ("Stamford", "CT"),
    "SUI": ("Suisun-Fairfield", "CA"), "SVT": ("Sturtevant", "WI"), "SYR": ("Syracuse", "NY"),
    "TAC": ("Tacoma", "WA"), "TCL": ("Tuscaloosa", "AL"), "TOL": ("Toledo", "OH"),
    "TOP": ("Topeka", "KS"), "TPA": ("Tampa", "FL"), "TPL": ("Temple", "TX"),
    "TRE": ("Trenton", "NJ"), "TTN": ("Trenton", "NJ"), "TUK": ("Tukwila", "WA"), "TUS": ("Tucson", "AZ"),
    "VAN": ("Vancouver", "WA"), "VNC": ("Van Nuys", "CA"),
    "WAS": ("Washington", "DC"),
    "WEM": ("Wells", "ME"), "WFH": ("Whitefish", "MT"), "WIL": ("Wilmington", "DE"),
    "WIN": ("Winona", "MN"), "WOB": ("Woburn", "MA"), "WPK": ("Winter Park", "FL"),
    "WTN": ("Williston", "ND"),
}

# Curated overrides for internal/legacy codes not in the official list.
AMTRAK_EXTRA = {
    "BEE": ("Beech Grove", "IN"),   # Beech Grove Shops
    "CHII": ("Chicago", "IL"), "CCHII": ("Chicago", "IL"),
    "FWT": ("Fort Worth", "TX"),    # hostname transposition of FTW
    "HIA": ("Hialeah", "FL"), "HLF": ("Hialeah", "FL"),
    "QASH": ("Ashland", "VA"), "QCHI": ("Chicago", "IL"), "QPHL": ("Philadelphia", "PA"),
    "RER": ("Rensselaer", "NY"),    # Rensselaer (Albany) yard
    "PORT": ("Portland", "OR"),
}

# Hostname-prefix → site for legacy hostnames that don't follow AMTR<CODE><STATE>.
OVERRIDES = {
    "NYPM": "New York, NY", "NYP": "New York, NY", "NYPP": "New York, NY",
    "PSCCNY": "New York, NY", "NYCNYS": "New York, NY", "NYCNYT": "New York, NY",
    "MOYNYS": "New York, NY", "PNBNYB": "New York, NY",
    "SSY": "Sunnyside, NY", "SSYNYY": "Sunnyside, NY",
    "CHI": "Chicago, IL", "CHIILY": "Chicago, IL", "CHIILS": "Chicago, IL",
    "CHISIM": "Chicago, IL", "CDL": "Chicago, IL",
    "PHLPAS": "Philadelphia, PA", "PHLPAY": "Philadelphia, PA", "PHL": "Philadelphia, PA",
    "PHIL": "Philadelphia, PA", "PHLPAO": "Philadelphia, PA",
    "WIL": "Wilmington, DE", "WILSIM": "Wilmington, DE", "WILDES": "Wilmington, DE",
    "WILDEY": "Wilmington, DE",
    "WASDCY": "Washington, DC", "WASDCS": "Washington, DC", "WASDCO": "Washington, DC",
    "WASDCIV": "Washington, DC", "IVY": "Washington, DC", "AMTWAS": "Washington, DC",
    "WUS": "Washington, DC", "AMTRNEWNJ": "New Jersey, NJ",
    "LA-YARD": "Los Angeles, CA",       # "LA Yard" APs
    "AMYDBA": "Baltimore, MD", "AMSTBA": "Baltimore, MD",
    "REA": "Reading, PA", "LOR": "Lorton, VA", "NOL": "New Orleans, LA",
    "STL": "St. Louis, MO",     "BOS": "Boston, MA", "SEA": "Seattle, WA",
    "AMT1MASS": "Massachusetts, MA",
    "SEAWAY": "Seattle, WA", "SEAWAS": "Seattle, WA",
    "LAX": "Los Angeles, CA", "LAXCAY": "Los Angeles, CA", "LOSCAY": "Los Angeles, CA",
    "LAXCAS": "Los Angeles, CA", "LOSCAS": "Los Angeles, CA",
    "OAK": "Oakland, CA", "OAKCAY": "Oakland, CA", "OKJ": "Oakland, CA",
    "OAKSIM": "Oakland, CA", "SAC": "Sacramento, CA", "SACCAS": "Sacramento, CA",
    "SAN-CA": "San Diego, CA", "SANCAS": "San Diego, CA", "SAN-CR": "San Diego, CA",
    "SANFL": "Sanford, FL", "SANFLS": "Sanford, FL",
    "SANDIEGO": "San Diego, CA",  # legacy Catalyst asset named host
    "SFA": "Sanford, FL", "MIA": "Miami, FL", "MIAFLY": "Miami, FL",
    "MIAFLS": "Miami, FL", "MIFLST": "Miami, FL", "MIFL": "Miami, FL",
    "MIAST": "Miami, FL", "HIAFLY": "Hialeah, FL", "HIA": "Hialeah, FL",
    "BEE": "Beech Grove, IN", "BEEINS": "Beech Grove, IN",
    "BHM": "Birmingham, AL", "ATL": "Atlanta, GA", "MEM": "Memphis, TN",
    "LNC": "Lancaster, PA", "LNCPAS": "Lancaster, PA", "LNL": "Lansdale, PA",
    "HAR": "Harrisburg, PA", "HARPAS": "Harrisburg, PA",
    "RGH": "Raleigh, NC", "PDX": "Portland, OR", "PDXORS": "Portland, OR",
    "PVD": "Providence, RI", "PVDRIS": "Providence, RI", "MSP": "Minneapolis, MN",
    "SLC": "Salt Lake City, UT", "SLCUTS": "Salt Lake City, UT", "EMY": "Emeryville, CA",
    "ROC": "Rochester, NY", "JAN": "Jackson, MS", "ELP": "El Paso, TX", "ELPTXS": "El Paso, TX",
    "LIN": "Lincoln, NE", "NCR": "New Carrollton, MD", "REN": "Rensselaer, NY",
    "RENDEO": "Rensselaer, NY", "ALB": "Albany, NY", "ALBNMS": "Albany, NY",
    "ANACAS": "Anaheim, CA", "BEADEY": "Bear, DE", "BEAR": "Bear, DE",
    "BFD": "Bakersfield, CA", "GROTON": "Groton, CT", "GROCTO": "Groton, CT",
    "NHV": "New Haven, CT", "NHVSIM": "New Haven, CT", "NWK": "Newark, NJ",
    "GTW": "Secaucus, NJ", "PCY": "Baltimore, MD", "PCYPAY": "Baltimore, MD",
    "NEWNJS": "New Jersey, NJ", "DENCOS": "Denver, CO", "OCECAS": "Oceanside, CA",
    "SNACAS": "Santa Ana, CA", "TRENJS": "Trenton, NJ", "WATCTO": "Waterbury, CT",
    "RAHNJS": "Rahway, NJ", "NCCDEO": "New Castle, DE", "LICNYT": "Long Island City, NY",
    "LICNYH": "Long Island City, NY",
    "AMSTRV": "Richmond, VA",            # AMSTRVRVA...
    "AMTRMOYNYS": "New York, NY",        # Moynihan Train Hall
    "AMTRPLNYC": "New York, NY",         # Penn Station platform
    "AMTRWASDCIV": "Washington, DC",     # Ivy City (WAS DC Ivy)
    "AMTRLNSPA": "Lansdale, PA",         # LNS+PA (CSV's LNS is East Lansing MI)
    "MRSAMTRLNSPA": "Lansdale, PA",
    "AMTRRENDE": "Rensselaer, NY",       # Rensselaer yard (RENDE = shop block)
    "MRSAMTRRENDE": "Rensselaer, NY",
    "AMTRRERNY": "Rensselaer, NY",
}


def decode(hostname: str) -> str | None:
    """Decode a hostname into a site name, or None if it can't be identified."""
    clean = (hostname or "").split(".")[0].upper().strip()
    if not clean:
        return None

    # 1. Curated overrides (longest prefix wins).
    best = (0, "")
    for pfx, site in OVERRIDES.items():
        if clean.startswith(pfx) and len(pfx) > best[0]:
            best = (len(pfx), site)
    if best[0]:
        return best[1]

    # 2. Code-chain: MRSAMTR<CODE><STATE>, USNRPC<CODE><STATE>.
    for chain in ("MRSAMTR", "USNRPC"):
        if clean.startswith(chain):
            rest = clean[len(chain):]
            m = re.match(r"^[A-Z]+", rest)
            if not m:
                return None
            return _decode_codestate_block(m.group(0))

    # 3. AMTR<CODE><STATE>.
    m = re.match(r"^AMTR([A-Z]{4,9})", clean)
    if m:
        block = m.group(1)
        # Peek the trailing state/yard suffix: WASDCIVY -> WAS DC + IVY.
        for split in range(len(block) - 2, 1, -1):
            code, tail = block[:split], block[split:]
            if tail in STATES:
                hit = AMTRAK_CODES.get(code) or AMTRAK_EXTRA.get(code)
                if hit:
                    return f"{hit[0]}, {hit[1]}"
        # no explicit state tail: try whole block
        return _decode_codestate_block(block)

    # 4. <CODE>-<STATE> legacy (e.g. HAR-PA-AP01).
    m = re.match(r"^([A-Z]{2,4})-([A-Z]{2})", clean)
    if m:
        code, st = m.group(1), m.group(2)
        if st not in STATES:
            return None
        hit = AMTRAK_CODES.get(code)
        if hit:
            return f"{hit[0]}, {st}"
    return None


def _decode_codestate_block(block: str) -> str | None:
    """Decode a '<CODE><STATE>' block, checking state agreement.

    The state may not be the trailing two letters (sub-site letters can follow,
    e.g. NCAMDS = NCA + MD + 'S'), so scan every possible state position.
    """
    if len(block) < 4:
        return None
    for i in range(2, len(block) - 1):
        st = block[i:i + 2]
        if st not in STATES:
            continue
        for clen in range(i, 1, -1):
            hit = AMTRAK_CODES.get(block[:clen]) or AMTRAK_EXTRA.get(block[:clen])
            if hit:
                city, known = hit
                if st != known:
                    return None  # hostname state disagrees with the code's state
                return f"{city}, {known}"
    return None


def propose_mappings(hostnames) -> dict[str, str]:
    """Build {prefix: site} from a list of blank-site hostnames.

    Each rule's prefix is the longest hostname-prefix that shares the decode
    (the code+state block or the curated override), so rules are shared across
    many devices and longest-prefix-wins matching works in apply_site_mappings.
    """
    mapping: dict[str, str] = {}
    for h in hostnames:
        clean = (h or "").split(".")[0].upper().strip()
        if not clean:
            continue
        site = decode(h)
        if not site:
            continue
        # Reconstruct the matching prefix. Pick the longest candidate so a
        # more specific form (e.g. legacy ALB-NY) beats a shorter override
        # (e.g. "ALB") that also happens to match.
        candidates = []
        for override in OVERRIDES:
            if clean.startswith(override):
                candidates.append(override)
        for chain in ("MRSAMTR", "USNRPC"):
            if clean.startswith(chain):
                rest = clean[len(chain):]
                m = re.match(r"^[A-Z]+", rest)
                if m:
                    candidates.append(clean[: len(chain) + len(m.group(0))])
                break
        if clean.startswith("AMTR"):
            m = re.match(r"^AMTR[A-Z]+", clean)
            if m:
                candidates.append(m.group(0))
        m = re.match(r"^[A-Z]{2,4}-[A-Z]{2}", clean)
        if m:
            candidates.append(m.group(0))
        pfx = max(candidates, key=len) if candidates else None
        if pfx and (len(pfx) >= 4 or pfx in OVERRIDES):
            mapping[pfx] = site
    return mapping
