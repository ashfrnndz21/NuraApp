"""Health words: whether a line of prose names a medicine or a condition (E03-03).

A few short free-text columns are allowed on the graph: the patient's own note, the family's
messages (E12) and the chief's notes about a clinic (E03). A note about a clinic is about the
place — "parking at B2", "long waits, go early" — never about him, so that nothing clinical
sits in prose where no provenance, no confidence and no review can reach it. `names_health`
is the check. A medicine is found by the licensed registry's own answer (`identify`, through
the port, never a list of our own), by the high-risk table, by the chemical names the
glossary keeps second and small, and by his own names for them; a condition from
`CONDITIONS`, in English, Malay and Chinese. It says which kind it found and never the word,
so a refusal built on it carries nothing of what was written.

A message the family writes to him is held tighter (#164): it may name no medicine and no
dose at all (`names_medicine_or_dose`) — the same finders, plus the plain words for any
medicine ("tablet", "ubat", "药") and an amount with its unit ("5 mg", "2 biji", "两片"). His
medicine reminders come only from his confirmed list, never from a line someone typed.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from itertools import pairwise

from app.drugs.registry import DrugRegistry, LabelFields
from app.medicines.strings import PLAIN_NAME
from app.safety.high_risk import HIGH_RISK_CLASSES

MEDICINE = "medicine"
CONDITION = "condition"

CHEMICAL_NAMES = frozenset(
    {
        "diuretic",
        "furosemide",
        "frusemide",
        "antihypertensive",
        "amlodipine",
        "statin",
        "atorvastatin",
        "simvastatin",
        "metformin",
        "anticoagulant",
        "opioid",
        "chemotherapy",
        "chemo",
    }
)
"""The chemical and class names docs/plain-words.md keeps second to his names."""

CONDITIONS: Mapping[str, frozenset[str]] = {
    "en": frozenset(
        {
            "diabetes",
            "diabetic",
            "hypertension",
            "high blood pressure",
            "cancer",
            "tumour",
            "tumor",
            "stroke",
            "heart failure",
            "heart attack",
            "heart disease",
            "kidney disease",
            "kidney failure",
            "dementia",
            "alzheimer",
            "alzheimers",
            "parkinson",
            "parkinsons",
            "asthma",
            "copd",
            "arthritis",
            "gout",
            "depression",
            "pneumonia",
            "infection",
            "hepatitis",
            "hiv",
            "tuberculosis",
            "epilepsy",
            "cholesterol",
            "angina",
            "glaucoma",
            "cataract",
            "osteoporosis",
            "diagnosis",
            "diagnosed",
        }
    ),
    "ms": frozenset(
        {
            "kencing manis",
            "darah tinggi",
            "kanser",
            "barah",
            "strok",
            "sakit jantung",
            "penyakit jantung",
            "sakit buah pinggang",
            "asma",
            "lelah",
            "jangkitan",
            "kolesterol",
            "nyanyuk",
        }
    ),
    "zh": frozenset(
        {
            "糖尿病",
            "高血压",
            "癌",
            "中风",
            "心脏病",
            "肾病",
            "哮喘",
            "痛风",
            "肺炎",
            "感染",
            "胆固醇",
            "痴呆",
            "失智",
        }
    ),
}
"""Conditions a note about a place has no business naming. Short on purpose: the words a
family would actually type, in the three languages the product speaks."""

MEDICINE_WORDS: Mapping[str, frozenset[str]] = {
    "en": frozenset(
        {
            "medicine",
            "medicines",
            "medication",
            "medications",
            "tablet",
            "tablets",
            "pill",
            "pills",
            "capsule",
            "capsules",
            "dose",
            "doses",
            "dosage",
            "injection",
            "injections",
            "insulin",
            "inhaler",
            "syrup",
            "prescription",
        }
    ),
    "ms": frozenset({"ubat", "pil", "tablet", "kapsul", "dos", "suntikan", "preskripsi"}),
    "zh": frozenset({"药", "胶囊", "剂量", "打针", "胰岛素"}),
}
"""The plain words for any medicine or a dose of one. A message to him names none of them."""

_DOSE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ml|iu|g|units?|tabs?|caps?|puffs?|drops?|biji|sudu"
    r"|粒|片|颗|毫克|毫升|滴|单位)(?![a-z])",
    re.IGNORECASE,
)
"""An amount with its unit after a digit: "5 mg", "2 biji", "2片". A number in words ("two
tablets") comes with a medicine word, which `MEDICINE_WORDS` catches."""

_LATIN = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")
_CJK = re.compile(r"[㐀-䶿一-鿿]")
_PREFIXES = ("your ", "the ", "您的")
_SUFFIXES = (" anda",)


def _plain_names() -> frozenset[str]:
    """His own names for each medicine, every language, without "your" and "the"."""
    found: set[str] = set()
    for names in PLAIN_NAME.values():
        for name in names.values():
            low = name.lower()
            for prefix in _PREFIXES:
                low = low.removeprefix(prefix)
            for suffix in _SUFFIXES:
                low = low.removesuffix(suffix)
            found.add(low)
    return frozenset(found)


def _medicine_phrases() -> frozenset[str]:
    generics = {name for names in HIGH_RISK_CLASSES.values() for name in names}
    classes = {name.replace("_", " ") for name in HIGH_RISK_CLASSES}
    return frozenset(generics | classes | CHEMICAL_NAMES | _plain_names())


MEDICINE_PHRASES = _medicine_phrases()


def _words(text: str) -> list[str]:
    return [word.replace("’", "'") for word in _LATIN.findall(text.lower())]


def _has(phrase: str, joined: str, raw: str) -> bool:
    if _CJK.search(phrase):
        return phrase in raw
    return f" {phrase} " in joined


def _grams(words: list[str]) -> Iterator[str]:
    """Each word, and each two words together, for a brand of two words."""
    yield from words
    for first, second in pairwise(words):
        yield f"{first} {second}"


def names_medicine(text: str, registry: DrugRegistry | None = None) -> bool:
    """Whether the text names a medicine: his names for one, the high-risk table's, the
    chemical names, or — through the port — one the licensed registry knows."""
    words = _words(text)
    joined = f" {' '.join(words)} "
    if any(_has(phrase, joined, text) for phrase in MEDICINE_PHRASES):
        return True
    if registry is not None:
        for gram in _grams(words):
            if registry.identify(LabelFields(generic=gram)) or registry.identify(
                LabelFields(brand=gram)
            ):
                return True
    return False


def names_medicine_or_dose(text: str, registry: DrugRegistry | None = None) -> bool:
    """Whether a line to him names a medicine or a dose (#164). Never which word."""
    if names_medicine(text, registry):
        return True
    words = set(_words(text))
    for table in MEDICINE_WORDS.values():
        for word in table:
            if (word in text) if _CJK.search(word) else (word in words):
                return True
    return _DOSE.search(text) is not None


def names_health(text: str, registry: DrugRegistry | None = None) -> str | None:
    """`MEDICINE` or `CONDITION` if the text names one, else None. Never the word itself."""
    words = _words(text)
    joined = f" {' '.join(words)} "
    for phrase in MEDICINE_PHRASES:
        if _has(phrase, joined, text):
            return MEDICINE
    for phrases in CONDITIONS.values():
        for phrase in phrases:
            if _has(phrase, joined, text):
                return CONDITION
    if registry is not None:
        for gram in _grams(words):
            if registry.identify(LabelFields(generic=gram)) or registry.identify(
                LabelFields(brand=gram)
            ):
                return MEDICINE
    return None


__all__ = [
    "CONDITION",
    "CONDITIONS",
    "MEDICINE",
    "MEDICINE_PHRASES",
    "MEDICINE_WORDS",
    "names_health",
    "names_medicine",
    "names_medicine_or_dose",
]
