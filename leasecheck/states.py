# --- Which US state a lease is for (plain code, no AI) ---
# AI-assisted: Claude Code, see AI_DISCLOSURE.md
"""Decide which state a lease belongs to, before any model call.

The app only knows Massachusetts law, so a lease for a property elsewhere would be judged against the wrong
rules. No single clue is reliable (an address may be the landlord's office, "Washington" may be a street),
so seven independent kinds of evidence are collected for every state and weighed together:

  premises  the sentence that says where the apartment is ("the apartment at ..., Boston, Massachusetts")
  law       governing-law wording ("laws of the State of Texas", "New Jersey law")
  statute   a citation in that state's own format ("M.G.L. c. 186", "N.J.S.A. 46:8", "Cal. Civ. Code")
  address   "City, ST 12345" or "City, State 12345"; stronger when the ZIP code really belongs to that state
  term      wording only that state uses ("940 CMR", "Truth in Renting", "Greater Boston Real Estate Board")
  city      a well-known city or neighbourhood of the state ("Brookline", "Jersey City")
  name      the state's name on its own, three times or more (not "Washington Street" or "a Delaware company")

state_verdict() turns the evidence into one of five outcomes; parsing.load_document rejects or warns on it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
MA = "Massachusetts"
_BY_UPPER = {name.upper(): name for name in STATES.values()}
# Longest first, so "West Virginia" is never read as "Virginia". Written as in the lease or in ALL CAPS.
_NAMES = "|".join(sorted((re.escape(n) for n in [*STATES.values(), *_BY_UPPER]), key=len, reverse=True))
_CODES = "|".join(STATES)

# The first three digits of a ZIP code tell the state (US Postal Service prefixes).
_ZIP_RANGES = {
    "AL": "350-369", "AK": "995-999", "AZ": "850-865", "AR": "716-729", "CA": "900-961", "CO": "800-816",
    "CT": "060-069", "DE": "197-199", "DC": "200,202-205", "FL": "320-349", "GA": "300-319,398-399",
    "HI": "967-968", "ID": "832-838", "IL": "600-629", "IN": "460-479", "IA": "500-528", "KS": "660-679",
    "KY": "400-427", "LA": "700-714", "ME": "039-049", "MD": "206-219", "MA": "010-027,055", "MI": "480-499",
    "MN": "550-567", "MS": "386-397", "MO": "630-658", "MT": "590-599", "NE": "680-693", "NV": "889-898",
    "NH": "030-038", "NJ": "070-089", "NM": "870-884", "NY": "005,100-149", "NC": "270-289", "ND": "580-588",
    "OH": "430-459", "OK": "730-749", "OR": "970-979", "PA": "150-196", "RI": "028-029", "SC": "290-299",
    "SD": "570-577", "TN": "370-385", "TX": "750-799,885", "UT": "840-847", "VT": "050-054,056-059",
    "VA": "201,220-246", "WA": "980-994", "WV": "247-268", "WI": "530-549", "WY": "820-831",
}
ZIP_STATE: dict[str, str] = {}
for _code, _ranges in _ZIP_RANGES.items():
    for _part in _ranges.split(","):
        _lo, _, _hi = _part.partition("-")
        for _prefix in range(int(_lo), int(_hi or _lo) + 1):
            ZIP_STATE[f"{_prefix:03d}"] = STATES[_code]

# A citation in a state's own format. Each pattern can only mean that state.
_STATUTES = {
    MA: r"\bM\.?\s?G\.?\s?L\.?(?:\s?A\.?)?\b|\bG\.\s?L\.\s?c\.|\bMass\.\s?Gen(?:eral|\.)\s?Laws?\b|\b\d{3}\s+C\.?M\.?R\.?\b",
    "New Jersey": r"\bN\.?J\.?S\.?A\.?\b|\bN\.?J\.?A\.?C\.?\b",
    "New York": r"\bN\.Y\.\s?(?:Real\s?Prop|Gen\.\s?Oblig|Mult\.\s?Dwell)|\bReal Property (?:Actions and Proceedings )?Law\b"
                r"|\bRPAPL\b|\bGeneral Obligations Law\b",
    "California": r"\bCal(?:ifornia|\.)\s+Civ(?:il|\.)\s+Code\b|\bCivil Code [Ss]ection 19\d\d",
    "Texas": r"\bTex(?:as|\.)\s+Prop(?:erty|\.)\s+Code\b",
    "Florida": r"\bFla\.\s?Stat\.|\bFlorida Statutes\b|\bF\.S\.\s?(?:§|[Ss]ection)?\s?83\.",
    "Illinois": r"\b\d{3}\s+ILCS\b",
    "Washington": r"\bRCW\s+\d",
    "Georgia": r"\bO\.C\.G\.A\.",
    "Oregon": r"\bORS\s+\d",
    "Colorado": r"\bC\.R\.S\.",
    "Arizona": r"\bA\.R\.S\.",
    "Nevada": r"\bN\.?R\.?S\.?\s+\d{2,3}[A-Z]?\.",
    "Connecticut": r"\bConn\.\s?Gen\.\s?Stat\.|\bC\.G\.S\.",
    "Rhode Island": r"\bR\.I\.\s?Gen\.\s?Laws\b|\bR\.I\.G\.L\.",
    "New Hampshire": r"\bRSA\s+\d",
    "Maine": r"\bM\.R\.S\.(?:A\.)?",
    "Vermont": r"\bV\.S\.A\.",
    "Pennsylvania": r"\bPa\.\s?C\.S\.|\b\d+\s+P\.S\.\s",
    "Maryland": r"\bMd\.\s+Code\b",
    "Virginia": r"\bVa\.\s+Code\b|\bCode of Virginia\b",
    "North Carolina": r"\bN\.C\.G\.S\.|\bN\.C\.\s?Gen\.\s?Stat\.",
    "Ohio": r"\bOhio Rev(?:ised|\.)\s+Code\b|\bO\.R\.C\.",
    "Michigan": r"\bMCL\s+\d|\bM\.C\.L\.",
    "Minnesota": r"\bMinn\.\s?Stat\.",
    "Wisconsin": r"\bWis\.\s?Stat\.",
}
# Wording only one state's leases use (agencies, forms, named laws).
_TERMS = {
    MA: r"\b\d{3}\s+CMR\b|\bState Sanitary Code\b|\bGreater Boston Real Estate Board\b|\bGBREB\b"
        r"|\bMassachusetts Association of Realtors\b|\bBoston Housing Court\b|\bMass\.(?!\s?Gen)",
    "New Jersey": r"\bTruth[- ]in[- ]Renting\b|\bAnti-Eviction Act\b|\bN\.J\.(?![SA]\.)",
    "New York": r"\bRent Stabilization\b|\bDHCR\b|\bN\.Y\.(?!\s?(?:Real|Gen|Mult))",
    "California": r"\bCalif\.|\bProposition 65\b",
    "Connecticut": r"\bConn\.(?!\s?Gen)",
    "Pennsylvania": r"\bPenna?\.",
}
# Well-known cities and neighbourhoods. Weak evidence on its own: several names exist in more than one state.
_CITIES = {
    MA: "Boston|Cambridge|Somerville|Brookline|Allston|Brighton|Jamaica Plain|Dorchester|Roxbury|Fenway|Back Bay"
        "|South Boston|East Boston|Charlestown|Newton|Medford|Malden|Quincy|Waltham|Watertown|Worcester|Lowell"
        "|Framingham|Revere|Chelsea|Everett|Lynn|Braintree|Dedham|Needham|Belmont",
    "New Jersey": "Newark|Jersey City|Hoboken|Trenton|Paterson|Elizabeth|Edison|Hackensack|Bayonne|Camden",
    "New York": "Brooklyn|Manhattan|Queens|Bronx|Staten Island|New York City|Buffalo|Yonkers|Albany",
    "California": "Los Angeles|San Francisco|San Diego|San Jose|Oakland|Sacramento|Pasadena|Berkeley",
    "Texas": "Houston|Dallas|Austin|San Antonio|Fort Worth|El Paso",
    "Illinois": "Chicago", "Pennsylvania": "Philadelphia|Pittsburgh", "Florida": "Miami|Orlando|Tampa|Jacksonville",
    "Washington": "Seattle|Tacoma|Spokane", "Georgia": "Atlanta", "Colorado": "Denver|Boulder",
    "Arizona": "Phoenix|Tucson", "Rhode Island": "Providence|Pawtucket", "Connecticut": "Hartford|New Haven|Stamford",
    "New Hampshire": "Nashua", "Maryland": "Baltimore", "Michigan": "Detroit|Ann Arbor", "Ohio": "Cleveland|Cincinnati",
    "Nevada": "Las Vegas|Reno", "Oregon": "Portland", "Minnesota": "Minneapolis|Saint Paul",
    "North Carolina": "Charlotte|Raleigh|Durham",
}

_LAW = [
    re.compile(rf"\b(?i:state|commonwealth)\s+(?i:of)\s+({_NAMES})\b"),
    re.compile(rf"\b(?i:laws?\s+of\s+(?:the\s+)?(?:state\s+of\s+|commonwealth\s+of\s+)?)({_NAMES})\b"),
    re.compile(rf"\b({_NAMES})(?:'s)?\s+(?i:law|laws|statutes?|general\s+laws|revised\s+statutes|courts?)\b"),
]
_ADDRESS_NAME = re.compile(rf",\s*({_NAMES})\.?,?\s+(\d{{5}})\b")           # Austin, Texas 78701
_ADDRESS_CODE = re.compile(rf",\s*({_CODES})\.?,?\s+(\d{{5}})(?:-\d{{4}})?\b")  # Austin, TX 78701
_ADDRESS_BLANK = re.compile(rf",\s*({_NAMES}),?\s+\(?\s*(?i:zip)")              # (city), New Jersey, (zip code)
# The sentence that places the apartment: "the apartment at 5 Elm St, Boston, MA", "Premises: ... , Texas".
_PREMISES = re.compile(
    r"\b(?i:premises|apartment|dwelling(?:\s+unit)?|unit|residence|property|room)\b[^;]{0,40}?"
    r"(?:\b(?i:at|located|known\s+as|in)\b|:)([^;]{0,170})")
_CODE_IN = re.compile(rf",\s*({_CODES})\b\.?(?=\s*,|\s+\d{{5}}|\s*$|\s*\()")
# A state's name on its own counts only when it is not part of a street, company or publication name.
_NOT_A_STATE = (r"(?!\s+(?:Street|St\b|Avenue|Ave\b|Road|Rd\b|Boulevard|Blvd|Drive|Place|Square|Park|Life|Times|"
                r"University|Mutual|limited|corporation|company|LLC|L\.L\.C|Inc|LP\b|City\b)|,?\s*D\.?\s?C\b)")
_BARE = re.compile(rf"\b({_NAMES})\b{_NOT_A_STATE}")
MIN_BARE_MENTIONS = 3

WEIGHTS = {"premises": 6, "law": 5, "statute": 5, "address": 3, "term": 3, "city": 1, "name": 1}
MAX_COUNTED = {"premises": 1, "law": 2, "statute": 2, "address": 3, "term": 2, "city": 3, "name": 5}
STRONG = ("premises", "law", "statute")
LABELS = {"premises": "the apartment's address", "law": "governing-law wording", "statute": "law citations",
          "address": "addresses", "term": "state-specific wording", "city": "city names", "name": "the state's name"}


def _state(name: str) -> str:
    return _BY_UPPER.get(name.upper(), name)


@dataclass
class Evidence:
    counts: dict[str, float] = field(default_factory=dict)

    def add(self, kind: str, amount: float = 1) -> None:
        self.counts[kind] = self.counts.get(kind, 0) + amount

    @property
    def kinds(self) -> list[str]:
        return [k for k in WEIGHTS if self.counts.get(k)]

    @property
    def score(self) -> float:
        return sum(WEIGHTS[k] * min(n, MAX_COUNTED[k]) for k, n in self.counts.items())

    @property
    def strong(self) -> bool:
        return any(self.counts.get(k) for k in STRONG)

    def describe(self) -> str:
        return ", ".join(LABELS[k] for k in self.kinds)


def state_evidence(text: str) -> dict[str, Evidence]:
    """Every kind of evidence found for every state. States with no evidence are left out."""
    found: dict[str, Evidence] = {}

    def add(state: str, kind: str, amount: float = 1) -> None:
        found.setdefault(state, Evidence()).add(kind, amount)

    for pattern in _LAW:
        for m in pattern.finditer(text):
            add(_state(m.group(1)), "law")
    for m in _ADDRESS_NAME.finditer(text):
        state = _state(m.group(1))
        add(state, "address", 1 if ZIP_STATE.get(m.group(2)[:3], state) == state else 1 / 3)
    for m in _ADDRESS_CODE.finditer(text):
        state = STATES[m.group(1)]
        # A ZIP code that belongs to another state makes this a weak clue (a typo, or not an address at all).
        add(state, "address", 1 if ZIP_STATE.get(m.group(2)[:3]) == state else 1 / 3)
    for m in _ADDRESS_BLANK.finditer(text):
        add(_state(m.group(1)), "address")
    for m in _PREMISES.finditer(text):
        tail = m.group(1)
        name = _BARE.search(tail)  # skips "Washington Street"
        code = _CODE_IN.search(tail)
        if name:
            add(_state(name.group(1)), "premises")
        elif code:
            add(STATES[code.group(1)], "premises")
    for state, pattern in _STATUTES.items():
        n = len(re.findall(pattern, text))
        if n:
            add(state, "statute", n)
    for state, pattern in _TERMS.items():
        n = len(re.findall(pattern, text))
        if n:
            add(state, "term", n)
    for state, cities in _CITIES.items():
        n = len(re.findall(rf"\b(?:{cities})\b", text))
        if n:
            add(state, "city", n)
    bare: dict[str, int] = {}
    for m in _BARE.finditer(text):
        bare[_state(m.group(1))] = bare.get(_state(m.group(1)), 0) + 1
    for state, n in bare.items():
        # "Massachusetts" cannot be anything else, so one mention counts; other names need three, or support.
        if state == MA or n >= MIN_BARE_MENTIONS or state in found:
            add(state, "name", n)
    return found


@dataclass
class StateVerdict:
    status: str                 # massachusetts | mixed | other | other_likely | unknown
    state: str | None           # the state the lease most likely belongs to
    evidence: dict[str, Evidence]

    @property
    def others(self) -> list[str]:
        """Other states with real evidence, strongest first."""
        rest = [s for s in self.evidence if s != MA and self.evidence[s].kinds != ["city"]]
        return sorted(rest, key=lambda s: -self.evidence[s].score)


def state_verdict(text: str) -> StateVerdict:
    """Weigh the evidence.

    massachusetts  only Massachusetts has evidence (beyond a stray city name)
    mixed          Massachusetts and another state both have evidence, and Massachusetts is not clearly outweighed
    other          another state clearly owns the lease: reject before any model call
    other_likely   another state has some evidence and Massachusetts has none: warn
    unknown        no state has evidence: warn that the state could not be confirmed
    """
    evidence = state_evidence(text)
    verdict = StateVerdict("unknown", None, evidence)
    ma = evidence.get(MA)
    others = verdict.others
    if not others:
        if ma:
            verdict.status, verdict.state = "massachusetts", MA
        return verdict
    top = evidence[others[0]]
    verdict.state = others[0]
    if ma is None:
        # No trace of Massachusetts. One office address must not reject (its city and state name are the same
        # clue three times), so "clear" needs strong evidence backed by a second kind, or two addresses, or
        # the state's name three times backed by a second kind.
        counts = top.counts
        clear = ((top.strong and len(top.kinds) >= 2) or counts.get("address", 0) >= 2
                 or (counts.get("name", 0) >= MIN_BARE_MENTIONS and len(top.kinds) >= 2))
        verdict.status = "other" if clear else "other_likely"
    elif top.strong and not ma.strong and "term" not in ma.kinds and top.score >= 3 * ma.score:
        # Massachusetts appears only in passing (an office address, a city name) against strong evidence.
        verdict.status = "other"
    else:
        verdict.status, verdict.state = "mixed", MA if ma.score >= top.score else others[0]
    return verdict
