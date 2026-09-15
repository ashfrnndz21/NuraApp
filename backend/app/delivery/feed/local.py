"""Where he lives, what is going on around him, and what the season is: the inputs of the
local alert and the seasonal card (E09-07, docs/health-feed-spec.md §2).

**Only when a condition makes it relevant.** A dengue, haze or heat bulletin is not news for
everyone: it becomes a card for him only when a condition he told (E01) or a medicine on his
list is one the health authorities name for that hazard (`HAZARDS`). A profile with none of
them gets no alert, whatever the bulletin says. The table is data a pharmacist reviews, the
way the allowlist is.

**His area stays here.** The bulletins are fetched for the whole region and matched to his
area on this server (`area_matches`); the area is never part of a search sent anywhere.

**Seasons.** A season has its dates, a lead time, and the conditions that make it relevant.
The festive-food season is planned from his conditions. The fasting month is added by him or
his chief by hand ("Watching for Pa"): whether a person fasts is his to say, and Nura does not
guess it from a name or a language.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.errors import Refusal
from app.regions import Region


class NotACoarseArea(Refusal):
    """An area is a town or district from the list, or the first digits of a postcode — never
    a street, a house or a whole postcode."""


class NotAHazard(Refusal):
    """A local watch is for dengue, haze or heat."""


class NotASeason(Refusal):
    """A seasonal watch is for the fasting month or festive food."""


@dataclass(frozen=True, slots=True)
class Hazard:
    """What makes a bulletin about this hazard relevant to him: the conditions (the codes of
    `app/onboarding/conditions.json`) and the medicines (generic names) the health
    authorities name for it."""

    code: str
    conditions: frozenset[str]
    medicines: frozenset[str]


HAZARDS: Mapping[str, Hazard] = {
    # Severe dengue is more likely with long-term conditions, and bleeding is the danger on a
    # blood thinner (MOH and WHO consumer guidance). "blood_thinner" is what he told when the
    # setup asked (E01), before any label.
    "dengue": Hazard(
        "dengue",
        frozenset(
            {"diabetes", "high_blood_pressure", "heart", "weak_heart", "kidneys", "blood_thinner"}
        ),
        frozenset(
            {"warfarin", "aspirin", "clopidogrel", "ticagrelor", "prasugrel", "ticlopidine",
             "apixaban", "rivaroxaban", "dabigatran", "edoxaban"}
        ),
    ),
    # Haze advisories name long-term heart and lung conditions; an inhaler on his list is the
    # lungs' own marker.
    "haze": Hazard(
        "haze",
        frozenset({"heart", "weak_heart", "uneven_heartbeat", "breathing", "stroke"}),
        frozenset(
            {"salbutamol", "terbutaline", "ipratropium", "tiotropium", "budesonide",
             "fluticasone", "beclometasone", "formoterol", "salmeterol", "montelukast"}
        ),
    ),
    # Heat advisories name long-term heart, kidney and sugar conditions, and water pills.
    "heat": Hazard(
        "heat",
        frozenset({"heart", "weak_heart", "kidneys", "diabetes", "water_pill"}),
        frozenset(
            {"frusemide", "furosemide", "bumetanide", "torasemide", "torsemide",
             "hydrochlorothiazide", "chlorthalidone", "indapamide", "metolazone",
             "spironolactone", "amiloride"}
        ),
    ),
}
"""The hazards a local watch can be for, and who each is relevant to."""


def relevant_to(hazard: str, conditions: Iterable[str], medicines: Iterable[str]) -> list[str]:
    """What on his record makes this hazard relevant: the conditions and medicines that
    match, sorted. Empty means it is not for him, and no card is made."""
    rule = HAZARDS.get(hazard)
    if rule is None:
        raise NotAHazard(f"{hazard!r} is not a hazard a local watch covers")
    held = {code for code in conditions} & rule.conditions
    taken = {generic for name in medicines if (generic := generic_of(name)) in rule.medicines}
    return sorted(held | taken)


SYNONYMS: Mapping[str, str] = {"acetylsalicylic acid": "aspirin", "albuterol": "salbutamol"}
"""Other names a label gives the same medicine, by the name the table uses."""

_NOT_THE_MEDICINE = re.compile(
    r"\b(?:sodium|potassium|calcium|hydrochloride|hcl|bisulfate|besylate|besilate|maleate|"
    r"mesylate|etexilate|tosylate|bromide|sulfate|sulphate|dipropionate|propionate|"
    r"xinafoate|fumarate|tablets?|capsules?|\d+(?:\.\d+)?\s*(?:mg|mcg|g))\b"
)


def generic_of(name: str) -> str:
    """A medicine's name as the table knows it: lower case, its salt and strength left off
    ("Warfarin Sodium 5 mg" is warfarin), another name for it made the table's own."""
    cleaned = " ".join(_NOT_THE_MEDICINE.sub(" ", name.strip().lower()).split())
    return SYNONYMS.get(cleaned, cleaned)


# --- seasons ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Season:
    """A time of year with a card: its code, the search term a job asks for, the dates it
    runs in each year (the same in both regions here), how long before it the card may show,
    whether the date is fixed or announced nearer the time, whether the planner adds the watch
    by itself, and the conditions that make it relevant."""

    code: str
    term: str
    dates: tuple[tuple[date, date], ...]
    lead: timedelta
    exact: bool
    planned: bool
    conditions: frozenset[str]


SEASONS: tuple[Season, ...] = (
    Season(
        "mid_autumn",
        "festive food",
        # The fifteenth day of the eighth lunar month.
        ((date(2026, 9, 25), date(2026, 9, 25)), (date(2027, 9, 15), date(2027, 9, 15))),
        timedelta(days=21),
        exact=True,
        planned=True,
        conditions=frozenset({"diabetes", "cholesterol"}),
    ),
    Season(
        "fasting_month",
        "fasting month",
        # Expected dates; the start is announced by the religious authorities nearer the time,
        # so the card says "around". Health advice is to plan with the doctor 1–2 months ahead,
        # so the card may show from two months before.
        ((date(2026, 2, 18), date(2026, 3, 19)), (date(2027, 2, 8), date(2027, 3, 9))),
        timedelta(days=60),
        exact=False,
        planned=False,
        conditions=frozenset({"diabetes"}),
    ),
)
"""The seasons with a card. Adding one is adding its dates, its fixture page and its words."""

SEASON_TERMS: frozenset[str] = frozenset(season.term for season in SEASONS)


@dataclass(frozen=True, slots=True)
class OpenSeason:
    season: Season
    starts: date
    ends: date


def open_season(code: str, today: date) -> OpenSeason | None:
    """The season with this code, if today is inside its window: from its lead time before
    it starts to the day it ends."""
    for season in SEASONS:
        if season.code != code:
            continue
        for starts, ends in season.dates:
            if starts - season.lead <= today <= ends:
                return OpenSeason(season, starts, ends)
    return None


def seasons_for(term: str) -> list[Season]:
    return [season for season in SEASONS if season.term == term]


def check_season_term(term: str) -> str:
    cleaned = term.strip().lower()
    if cleaned not in SEASON_TERMS:
        raise NotASeason(f"{term!r} is not a season Nura watches")
    return cleaned


def check_hazard(term: str) -> str:
    cleaned = term.strip().lower()
    if cleaned not in HAZARDS:
        raise NotAHazard(f"{term!r} is not a hazard a local watch covers")
    return cleaned


# --- his area -----------------------------------------------------------------------------------

DISTRICTS: Mapping[Region, tuple[str, ...]] = {
    Region.SG: (
        "Ang Mo Kio", "Bedok", "Bishan", "Bukit Batok", "Bukit Merah", "Bukit Panjang",
        "Bukit Timah", "Choa Chu Kang", "Clementi", "Geylang", "Hougang", "Jurong East",
        "Jurong West", "Kallang", "Marine Parade", "Pasir Ris", "Punggol", "Queenstown",
        "Sembawang", "Sengkang", "Serangoon", "Tampines", "Toa Payoh", "Woodlands", "Yishun",
    ),
    Region.MY: (
        "Air Itam", "Balik Pulau", "Bayan Lepas", "Bukit Mertajam", "Butterworth", "Gelugor",
        "George Town", "Jelutong", "Nibong Tebal", "Tanjung Bungah", "Cheras", "Kepong",
        "Klang", "Petaling Jaya", "Shah Alam", "Subang Jaya", "Ipoh", "Johor Bahru",
    ),
}
"""The towns and districts an area may name, per region: coarse enough that a card about
dengue near him says where, and never where he lives to the street."""

PREFIX_DIGITS: Mapping[Region, tuple[int, ...]] = {Region.SG: (2,), Region.MY: (2, 3)}
"""How many leading digits of a postcode an area may be: Singapore's two-digit sector, the
first two or three of a Malaysian postcode — never the whole of either (six, five digits)."""

_SPACES = re.compile(r"\s+")


def check_area(text: str, region: Region) -> str:
    """The area as it is kept: a district from the list, spelled as the list spells it, or
    a postcode's first digits. Anything else — a street, a house number, a whole postcode —
    is `NotACoarseArea`."""
    cleaned = _SPACES.sub(" ", text.strip())
    if cleaned.isdigit():
        if len(cleaned) in PREFIX_DIGITS[region]:
            return cleaned
        raise NotACoarseArea("only the first digits of a postcode, never the whole of it")
    for district in DISTRICTS[region]:
        if district.casefold() == cleaned.casefold():
            return district
    raise NotACoarseArea("a town or district from the list, or the first digits of a postcode")


def area_matches(area: str | None, page_areas: Sequence[str]) -> bool:
    """Whether a bulletin is about his area. A bulletin that names no area is about the whole
    region; one that names some is about him when his area is among them — the same district,
    or postcode digits where one begins the other."""
    if not page_areas:
        return True
    if area is None:
        return False
    for named in page_areas:
        if named.isdigit() and area.isdigit():
            if named.startswith(area) or area.startswith(named):
                return True
        elif named.casefold() == area.casefold():
            return True
    return False
